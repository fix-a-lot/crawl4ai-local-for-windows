import asyncio
import base64
import binascii
import logging
import ntpath
import os

from mcp.server import MCPServer
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode
from crawl4ai.extraction_strategy import JsonCssExtractionStrategy

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("crawl4ai-mcp")

mcp = MCPServer("crawl4ai")

# --- output_path 안전장치 (Windows 시스템 경로 쓰기 차단) ---------------------
#
# 에이전트가 실수로(또는 프롬프트 인젝션 등으로) 스크린샷 저장 경로를
# 시스템 디렉터리로 넘길 가능성을 막는다. 화이트리스트가 아니라
# 블랙리스트 방식 — 알려진 시스템 경로 몇 곳만 차단하고 나머지는 허용한다.
# 완전한 샌드박싱이 아니라 "실수 방지" 수준의 가드레일이다.
_WINDOWS_SYSTEM_ROOTS = (
    r"c:\windows",
    r"c:\program files",
    r"c:\program files (x86)",
    r"c:\programdata",
    r"c:\system volume information",
    r"c:\$recycle.bin",
    r"c:\users\all users",
    r"c:\users\default",
)


def _is_blocked_system_path(path: str) -> bool:
    """path가 알려진 Windows 시스템 경로 하위인지 확인한다.

    이 서버는 Windows 전용(WSL 없이 동작)이지만 개발 시엔 다른 OS에서도
    문법 검사가 이뤄질 수 있으므로, ntpath 기반 문자열 정규화만으로
    판단한다 (os.path.realpath는 실행 플랫폼에 따라 Windows 드라이브
    표기를 그대로 리터럴로 취급해 비교가 깨질 수 있음).

    - ntpath.normpath로 ".."/혼합 구분자(\\, /)를 정규화해 우회를 막는다.
    - Windows 경로는 대소문자를 구분하지 않으므로 소문자로 비교한다.
    - 정규화된 경로가 시스템 루트와 "정확히 같거나" 그 하위 디렉터리일
      때만 차단한다 (단순 prefix 매칭은 "C:\\Windows2\\x.png" 같은 걸
      "C:\\Windows"의 하위로 오판할 수 있어 구분자 경계까지 확인한다).
    """
    if not path:
        return True

    normalized = ntpath.normpath(path).lower()

    for root in _WINDOWS_SYSTEM_ROOTS:
        root_normalized = ntpath.normpath(root).lower()
        if normalized == root_normalized or normalized.startswith(
            root_normalized + ntpath.sep
        ):
            return True
    return False

# 브라우저를 매 호출마다 새로 띄우면 비용이 크므로, 프로세스 안에서 하나만 만들어 재사용한다.
_crawler: AsyncWebCrawler | None = None
_crawler_lock = asyncio.Lock()

# 재사용 중인 브라우저가 죽었을 때(좀비 프로세스, 대상 페이지 붕괴 등) 한 번만 새로
# 띄워본다. 예방적 N회 갱신은 crawl4ai 내부(_pages_served / 브라우저 버전 bump)가 담당.
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


async def run_with_recovery(url: str, config: CrawlerRunConfig):
    """arun을 실행하고, 브라우저 자체 붕괴로 보이면 재생성 후 재시도한다.

    예외로 튀는 경우와 result.success=False로 조용히 돌아오는 경우를
    매 시도마다 동일하게 검사한다 (이전 버전은 재시도 루프에서 메시지
    기반 붕괴를 다시 검사하지 않아 사실상 1회만 재시도되는 비대칭이 있었음).
    네트워크 오류·안티봇 차단 등 페이지 쪽 원인은 재시도하지 않는다.

    마지막 시도가 실패한 경우, 그 결과/예외를 그대로 호출부에 돌려주되
    reset_crawler()는 다시 호출하지 않는다 — 이미 죽은 크롤러를 정리하는
    것은 직전 루프에서 끝났으므로, 여기서 한 번 더 리셋하면 그 사이 다른
    요청이 새로 만든 정상 인스턴스를 괜히 파괴할 수 있다.
    """
    last_result = None
    last_exc: Exception | None = None

    for attempt in range(1, _MAX_RECREATE_ATTEMPTS + 1):
        crawler = await get_crawler()
        is_last_attempt = attempt == _MAX_RECREATE_ATTEMPTS

        try:
            result = await crawler.arun(url=url, config=config)
        except Exception as exc:
            logger.exception(
                "arun 예외 (시도 %d/%d): %s", attempt, _MAX_RECREATE_ATTEMPTS, url
            )
            if not _looks_like_browser_crash(exc):
                raise
            last_exc = exc
            last_result = None
            if not is_last_attempt:
                await reset_crawler()
            continue

        if not result.success and _looks_like_browser_crash_message(
            result.error_message or ""
        ):
            logger.warning(
                "브라우저 붕괴 의심 (시도 %d/%d, %s): %s",
                attempt,
                _MAX_RECREATE_ATTEMPTS,
                url,
                result.error_message,
            )
            last_result = result
            last_exc = None
            if not is_last_attempt:
                await reset_crawler()
            continue

        return result

    if last_exc is not None:
        raise last_exc
    return last_result  # 재시도 소진 — 마지막 실패 결과를 그대로 반환해 호출부가 처리


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


async def shutdown_crawler() -> None:
    await reset_crawler()


def _build_config(wait_seconds: float, wait_selector: str, **extra) -> CrawlerRunConfig:
    kwargs: dict = {"cache_mode": CacheMode.BYPASS, **extra}
    if wait_selector:
        kwargs["wait_for"] = f"css:{wait_selector}"
    elif wait_seconds > 0:
        kwargs["delay_before_return_html"] = wait_seconds
    return CrawlerRunConfig(**kwargs)


def _parse_field_spec(spec: str) -> dict:
    """필드 스펙 문자열을 JsonCssExtractionStrategy용 필드 딕셔너리로 변환한다.

    - "a@href" -> 속성 추출 (요소@속성명)
    - "@data-value" -> 베이스 요소 자체의 속성
    - "td:text" -> 텍스트 추출, 끝의 ":text" 접미사만 제거
    - "td" -> 텍스트 추출 (접미사 없음)

    ":text"는 접미사로만 취급한다. 과거 구현은 spec.replace(":text", "")로
    문자열 어디에 있든 제거했기 때문에, selector 자체에 "text"라는 부분
    문자열이 포함된 클래스명(예: ".text-bold:text")이 있으면 의도치 않게
    깨졌다.
    """
    if "@" in spec:
        sel, attr = spec.rsplit("@", 1)
        field = {"name": "", "type": "attribute", "attribute": attr}
        if sel:
            field["selector"] = sel
        return field

    if spec.endswith(":text"):
        selector = spec[: -len(":text")]
    else:
        selector = spec
    return {"name": "", "type": "text", "selector": selector}


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
    fields: dict[str, str],
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
        field = _parse_field_spec(spec)
        field["name"] = name
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
    if _is_blocked_system_path(output_path):
        return f"저장 거부: 시스템 경로에는 저장할 수 없습니다: {output_path}"

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

    try:
        image_bytes = base64.b64decode(result.screenshot)
    except (binascii.Error, ValueError) as exc:
        logger.exception("스크린샷 디코딩 실패: %s", url)
        return f"스크린샷 디코딩 실패: {exc}"

    output_dir = os.path.dirname(output_path)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    try:
        with open(output_path, "wb") as f:
            f.write(image_bytes)
    except OSError as exc:
        logger.exception("스크린샷 저장 실패: %s", output_path)
        return f"파일 저장 실패: {exc}"

    return f"저장 완료: {output_path}"


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
