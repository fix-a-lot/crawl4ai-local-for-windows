import logging
import base64
import logging

from mcp.server import MCPServer
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode

mcp = MCPServer("crawl4ai")


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
    config_kwargs: dict = {"cache_mode": CacheMode.BYPASS}
    if wait_selector:
        config_kwargs["wait_for"] = f"css:{wait_selector}"
    elif wait_seconds > 0:
        config_kwargs["delay_before_return_html"] = wait_seconds
    async with AsyncWebCrawler(config=BrowserConfig(headless=True)) as crawler:
        result = await crawler.arun(url=url, config=CrawlerRunConfig(**config_kwargs))
        if not result.success:
            return f"크롤링 실패: {result.error_message}"
        return result.markdown


@mcp.tool()
async def crawl_screenshot(url: str, output_path: str) -> str:
    """스크린샷을 찍어 파일로 저장한다."""
    async with AsyncWebCrawler(config=BrowserConfig(headless=True)) as crawler:
        result = await crawler.arun(
            url=url,
            config=CrawlerRunConfig(screenshot=True, cache_mode=CacheMode.BYPASS),
        )
        if not result.screenshot:
            return "스크린샷 실패"
        with open(output_path, "wb") as f:
            f.write(base64.b64decode(result.screenshot))
        return f"저장 완료: {output_path}"


def main() -> None:
    logging.info("Crawl4ai MCP server started.")
    try:
        mcp.run()
    except KeyboardInterrupt:
        logging.info("Crawl4ai MCP server stopped.")

if __name__ == "__main__":
    main()