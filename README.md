# Crawl4ai Local for Windows

Local MCP server for Crawl4ai on Windows. No need to install WSL—just run it directly.

See also:
    - [https://github.com/unclecode/crawl4ai](https://github.com/unclecode/crawl4ai)
    - [https://docs.crawl4ai.com/](https://docs.crawl4ai.com/)

## Requirements

This project requires uv and Python 3.14.

## Installation

```bash
uv sync
```

## Running

🚨️ If you connect the MCP correctly to a coding agent, it starts the server automatically—no need to run it separately.

```bash
uv run main
```

To run in debugging mode (MCP Inspector) from the terminal:

```bash
uv run mcp dev src/crawl4ai_local_for_windows/server.py
```

## Adding MCP to an Agent

### Claude Code

```bash
claude mcp add --transport stdio --scope user crawl4ai -- uv run --directory <parent_location>\crawl4ai-local-for-windows main
```

parent_location: Write it like `C:\dev\repo\fix-a-lot`
- e.g. `claude mcp add --transport stdio --scope user crawl4ai -- uv run --directory C:\dev\repo\fix-a-lot\crawl4ai-local-for-windows main`

```bash
# Check MCP installation
claude mcp list
claude mcp get crawl4ai
```

### Hermes Agent

```json
{
  "mcpServers": {
    "crawl4ai": {
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "<parent_location>\\crawl4ai-local-for-windows",
        "main"
      ]
    }
  }
}
```

parent_location: Write it like `C:\\dev\\repo\\fix-a-lot`
- e.g. `C:\\dev\\repo\\fix-a-lot\\crawl4ai-local-for-windows`

---

## 🚧 Commands used when scaffolding the project

```bash
uv init
uv add crawl4ai mcp
uv run crawl4ai-setup
```
