import asyncio
import base64
import logging
import os

from mcp.server import MCPServer
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode
from crawl4ai.extraction_strategy import JsonCssExtractionStrategy

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("crawl4ai-mcp")

mcp = MCPServer("crawl4ai")

_crawler: AsyncWebCrawler | None = None
_crawler_lock = asyncio.Lock()

# 초기 시도 1회 + 재생성 재시도 횟수. 메시지 기반 붕괴/예외 기반 붕괴 둘 다
# 이 횟수만큼 균등하게 재시도한다 (이전 버전은 예외 경로만 루프를 돌고
# 메시지 경로는 1회로 끝나는 비대칭이 있었음).
_MAX_RECREATE_ATTEMPTS = 2


async def get_crawler() -> AsyncWebCrawler:
    global _crawler
    if _crawler is None:
        async with _crawler_lock:
            if _crawler is None:
                crawler = AsyncWebCrawler(config=BrowserConfig(headless=True))
                await crawler.__aenter__()
                _crawler = crawler
    return _crawler


async def reset_crawler() -> None:
    """죽었거나 오염된 크롤러를 버린다. 다음 get_crawler()에서 새로 생성된다.

    get_crawler()와 같은 lock으로 감싸서, 리셋 도중 다른 요청이 None을 보고
    새 인스턴스를 만드는 것과 겹치지 않게 한다.
    """
    global _crawler
    async with _crawler_lock:
        crawler, _crawler = _crawler, None
    if crawler is not None:
        try:
            await crawler.__aexit__(None, None, None)
        except Exception:
            logger.exception("크롤러 종료 중 예외 (무시하고 재생성)")


def _looks_like_browser_crash(exc: Exception) -> bool:
    msg = str(exc).lower()
    # 대상 사이트 쪽 문제(네트워크 오류, 안티봇 차단, 타임아웃 등)와 겹치지
    # 않도록 브라우저/세션 자체가 죽었을 때만 나오는 문구로 좁힘.
    keywords = (
        "target page, context or browser has been closed",
        "target closed",
        "browser has been closed",
        "browser has crashed",
        "browsertype.launch",
    )
    return any(k in msg for k in keywords)


def _looks_like_browser_crash_message(error_message: str) -> bool:
    msg = (error_message or "").lower()
    keywords = (
        "target page, context or browser has been closed",
        "target closed",
        "browser has been closed",
        "browser has crashed",
    )
    return any(k in msg for k in keywords)


async def run_with_recovery(url: str, config: CrawlerRunConfig):
    """arun을 실행하고, 브라우저 자체 붕괴로 보이면 재생성 후 재시도한다.

    예외로 튀는 경우와 result.success=False로 조용히 돌아오는 경우를
    매 시도마다 동일하게 검사한다 (이전 버전은 재시도 루프에서 메시지
    기반 붕괴를 다시 검사하지 않아 사실상 1회만 재시도되는 비대칭이 있었음).
    """
    last_result = None
    last_exc: Exception | None = None

    for attempt in range(1, _MAX_RECREATE_ATTEMPTS + 1):
        crawler = await get_crawler()
        try:
            result = await crawler.arun(url=url, config=config)
        except Exception as exc:
            logger.exception("arun 예외 (시도 %d/%d): %s", attempt, _MAX_RECREATE_ATTEMPTS, url)
            if not _looks_like_browser_crash(exc):
                raise
            last_exc = exc
            last_result = None
            await reset_crawler()
            continue

        if not result.success and _looks_like_browser_crash_message(result.error_message or ""):
            logger.warning(
                "브라우저 붕괴 의심 (시도 %d/%d, %s): %s",
                attempt, _MAX_RECREATE_ATTEMPTS, url, result.error_message,
            )
            last_result = result
            last_exc = None
            await reset_crawler()
            continue

        return result

    if last_exc is not None:
        raise last_exc
    return last_result  # 재시도 소진 — 마지막 실패 결과를 그대로 반환해 호출부가 처리


def _build_config(wait_seconds: float, wait_selector: str, **extra) -> CrawlerRunConfig:
    kwargs: dict = {"cache_mode": CacheMode.BYPASS, **extra}
    if wait_selector:
        kwargs["wait_for"] = f"css:{wait_selector}"
    elif wait_seconds > 0:
        kwargs["delay_before_return_html"] = wait_seconds
    return CrawlerRunConfig(**kwargs)


@mcp.tool()
async def crawl_markdown(
    url: str,
    wait_seconds: float = 0,
    wait_selector: str = "",
) -> str:
    """주어진 URL을 크롤링해서 마크다운으로 반환한다.

    Args:
        url: 크롤링할 URL.
        wait_seconds: HTML을 받기 전 대기 시간(초). JS 동적 로딩 페이지에 사용.
        wait_selector: 이 CSS 셀렉터가 나타날 때까지 대기. 지정 시 wait_seconds보다 우선.
    """
    try:
        config = _build_config(wait_seconds, wait_selector)
        result = await run_with_recovery(url, config)
    except Exception as exc:
        logger.exception("crawl_markdown 실패: %s", url)
        return f"크롤링 중 예외 발생: {exc}"

    if not result.success:
        return f"크롤링 실패: {result.error_message}"
    return result.markdown


@mcp.tool()
async def crawl_structured(
    url: str,
    selector: str,
    fields: dict,
    wait_seconds: float = 0,
    wait_selector: str = "",
) -> str:
    """CSS 셀렉터로 반복 요소를 잡아 지정한 필드만 JSON으로 추출한다.

    Args:
        url: 크롤링할 URL.
        selector: 반복 요소를 잡는 CSS 셀렉터 (예: "table tr.item", "div.product-card").
        fields: 추출할 필드. 키=필드명, 값=추출 지정 문자열.
            - 텍스트: "td" 또는 "td:text"
            - 속성: "a@href" (요소@속성명), 요소 자체 속성은 "@data-value"
            - N번째 요소는 CSS 문법 "td:nth-of-type(1)" 사용 (":eq()" 미지원)
            예: {"이름": "td:nth-of-type(1):text", "링크": "a@href"}
        wait_seconds: HTML을 받기 전 대기 시간(초). JS 동적 로딩 페이지에 사용.
        wait_selector: 이 CSS 셀렉터가 나타날 때까지 대기. 지정 시 wait_seconds보다 우선.
    """
    schema_fields = []
    for name, spec in fields.items():
        if "@" in spec:
            sel, attr = spec.rsplit("@", 1)
            field = {"name": name, "type": "attribute", "attribute": attr}
            if sel:
                field["selector"] = sel
        elif ":text" in spec:
            field = {"name": name, "type": "text", "selector": spec.replace(":text", "")}
        else:
            field = {"name": name, "type": "text", "selector": spec}
        schema_fields.append(field)
    schema = {
        "name": "extraction",
        "baseSelector": selector,
        "fields": schema_fields,
    }

    try:
        config = _build_config(
            wait_seconds,
            wait_selector,
            extraction_strategy=JsonCssExtractionStrategy(schema),
        )
        result = await run_with_recovery(url, config)
    except Exception as exc:
        logger.exception("crawl_structured 실패: %s", url)
        return f"크롤링 중 예외 발생: {exc}"

    if not result.success:
        return f"크롤링 실패: {result.error_message}"
    content = result.extracted_content
    if not content:
        return "추출 결과 없음 — selector가 페이지에 매칭되는지 확인하세요."
    return content


@mcp.tool()
async def crawl_screenshot(url: str, output_path: str) -> str:
    """스크린샷을 찍어 파일로 저장한다."""
    try:
        result = await run_with_recovery(
            url,
            CrawlerRunConfig(screenshot=True, cache_mode=CacheMode.BYPASS),
        )
    except Exception as exc:
        logger.exception("crawl_screenshot 실패: %s", url)
        return f"크롤링 중 예외 발생: {exc}"

    if not result.success:
        return f"크롤링 실패: {result.error_message}"
    if not result.screenshot:
        return "스크린샷 실패: 크롤링은 성공했지만 이미지가 반환되지 않음"

    output_dir = os.path.dirname(output_path)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    try:
        with open(output_path, "wb") as f:
            f.write(base64.b64decode(result.screenshot))
    except OSError as exc:
        logger.exception("스크린샷 저장 실패: %s", output_path)
        return f"파일 저장 실패: {exc}"

    return f"저장 완료: {output_path}"


async def shutdown_crawler() -> None:
    await reset_crawler()


def main() -> None:
    logger.info("🚀 Crawl4ai MCP server started.")
    try:
        mcp.run()
    except KeyboardInterrupt:
        logger.info("🛑 Crawl4ai MCP server stopped.")
    finally:
        asyncio.run(shutdown_crawler())


if __name__ == "__main__":
    main()
