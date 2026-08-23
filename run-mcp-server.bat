@echo off
setlocal

cd /d "%~dp0"

echo Starting Crawl4ai MCP server...
uv run main

echo.
echo Crawl4ai MCP server stopped.
pause
