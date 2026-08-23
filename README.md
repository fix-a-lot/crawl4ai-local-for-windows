# Crawl4ai Local for Windows

Local MCP server for Crawl4ai on Windows. No need to install WSL—just run it directly.

## Requirements

This project requires uv and Python 3.14.

## Installation

```bash
uv sync
```

## Running

Run the `run-mcp-server.bat` file, or execute the following command in the terminal:

```bash
uv run main
```

ℹ️ To run in debugging mode (MCP Inspector) from the terminal:

```bash
uv run mcp dev src/crawl4ai_local_for_windows/server.py
```

## Adding MCP to an Agent

### Claude Code

```bash
claude mcp add --transport stdio --scope user crawl4ai -- uv run --directory <parent_location>\crawl4ai-local-for-windows main
# parent_location: Write it like C:\dev\repo\fix-a-lot
# claude mcp add --transport stdio --scope user crawl4ai -- uv run --directory C:\dev\repo\fix-a-lot\crawl4ai-local-for-windows main
```

```bash
# Check MCP installation
claude mcp list
claude mcp get crawl4ai
```

---

## 🚧 Commands used when scaffolding the project

```bash
uv init
uv add crawl4ai mcp
uv run crawl4ai-setup
```
