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

🚨 This server operates as a stdio server, so there is no need to keep it running like a network server. The agent will automatically instantiate the server instance.

```bash
# Terminate after checking the welcome message
uv run main
```

✅ Once the welcome message has been confirmed, the agent can connect to the MCP.

To run in debugging mode (MCP Inspector) from the terminal:

```bash
uv run mcp dev src/crawl4ai_local_for_windows/server.py
```

## Adding MCP to an Agent

### Claude Code

```bash
claude mcp add --transport stdio --scope user crawl4ai -- uv run --directory <parent_location>\crawl4ai-local-for-windows main
```

- `parent_location`: Write it like `C:\dev\repo\fix-a-lot`
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

- `parent_location`: Write it like `C:\\dev\\repo\\fix-a-lot`
- e.g. `C:\\dev\\repo\\fix-a-lot\\crawl4ai-local-for-windows`

## Waiting Options (Dynamic Pages)

For dynamic pages that render content late using JS, use the waiting options of `crawl_markdown`.

```python
# Method 1: Wait for a fixed duration (seconds)
crawl_markdown(url="https://example.com", wait_seconds=5)

# Method 2: Wait until a CSS selector appears (Takes precedence over wait_seconds when specified)
crawl_markdown(url="https://example.com", wait_selector="div.result-list")

```

### Verification Results (2026-08-25)

Comparison of 3 cases on a local test page that updates content via JS after 3 seconds:

| Case | success | Captures Dynamic Content |
| --- | --- | --- |
| No waiting option | True | ❌ Returns only "Loading..." |
| `wait_seconds=5` | True | ✅ Accurately captures final content |
| `wait_selector="#dynamic"` | True | ❌ Passes immediately if the element already exists in the initial HTML |

### Findings / Cautions

1. **`wait_selector` is valid only for "newly created elements."** If the text of an element already present in the initial HTML (e.g., `<article id="dynamic">Loading...</article>`) changes later, the selector matches immediately and passes without waiting. Pages that update text dynamically should use `wait_seconds`.
2. **Extreme pages trigger anti-bot heuristics.** Pages with minimal content and an excessive number of script tags are flagged by crawl4ai's anti-bot detector as `Blocked by anti-bot protection: Structural: no_content_elements, script_heavy_shell`, resulting in `success=False`. Although rare in actual production pages, testing should ideally be conducted on pages containing at least basic static content (such as navigation bars or paragraphs).
