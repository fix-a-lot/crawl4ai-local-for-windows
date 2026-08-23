import logging
import base64
import logging

from mcp.server import MCPServer
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode

mcp = MCPServer("crawl4ai")


@mcp.tool()
async def crawl_markdown(url: str) -> str:
    """주어진 URL을 크롤링해서 마크다운으로 반환한다."""
    async with AsyncWebCrawler(config=BrowserConfig(headless=True)) as crawler:
        result = await crawler.arun(
            url=url,
            config=CrawlerRunConfig(cache_mode=CacheMode.BYPASS),
        )
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