# Crawl4ai Local for Windows

[🇰🇷 한국어](README.ko.md) | [English](README.md)

Local MCP server for Crawl4ai on Windows. Runs directly on Windows without WSL.

🤖 Most of the code was generated with AI assistance.

See also:

- [https://github.com/unclecode/crawl4ai](https://github.com/unclecode/crawl4ai)
- [https://docs.crawl4ai.com/](https://docs.crawl4ai.com/)

## Requirements

- [uv](https://docs.astral.sh/uv/)
- Python 3.14 (installed automatically via uv)

## Installation

```bash
uv sync
```

## Running

🚨 This server is a stdio server — no need to keep it running like a network server. When connected to an agent as MCP, the agent automatically spins up the server instance.

```bash
# Check for the "🚀 Crawl4ai MCP server started." message, then exit
uv run main
```

✅ After confirming the welcome message, press <kbd>Ctrl+C</kbd> to exit, then add the MCP to your agent.

```bash
# Tip: debugging mode (MCP Inspector)
uv run mcp dev src/crawl4ai_local_for_windows/server.py
```

## Adding MCP to an Agent

### Claude Code

```bash
claude mcp add --transport stdio --scope user crawl4ai -- uv run --directory <parent_location>/crawl4ai-local-for-windows main
```

- `parent_location`: Write it like `C:/dev/hermes-workspace`
- e.g. `claude mcp add --transport stdio --scope user crawl4ai -- uv run --directory C:/dev/hermes-workspace/crawl4ai-local-for-windows main`

```bash
# Check MCP installation
claude mcp list
claude mcp get crawl4ai
```

### Hermes Agent

```bash
hermes mcp add crawl4ai --command "uv" --args "run" "--directory" "<parent_location>/crawl4ai-local-for-windows" "main"
```

- `parent_location`: Write it like `C:/dev/hermes-workspace`
- e.g. `C:/dev/hermes-workspace/crawl4ai-local-for-windows`

```bash
# Check MCP installation
hermes mcp list
```

## Tools

### `crawl_markdown(url, wait_seconds=0, wait_selector="")`

Crawl a URL and return the content as Markdown.

### `crawl_structured(url, selector, fields, wait_seconds=0, wait_selector="")`

Extract repeated elements as JSON using CSS selectors.

```python
crawl_structured(
    url="https://books.toscrape.com/",
    selector="article.product_pod",
    fields={"제목": "h3@title", "가격": ".price_color:text"},
)
# → [{"제목": "A Light in the Attic", "가격": "£51.77"}, ...]
```

Field spec syntax:

| Spec | Meaning |
| --- | --- |
| `"td"` or `"td:text"` | Text of the matched element |
| `"a@href"` | Attribute of a child element (`element@attribute`) |
| `"@data-value"` | Attribute of the base element itself |
| `"td:nth-of-type(1)"` | Nth element — use standard CSS (`:eq()` is **not** supported) |

Both tools share the waiting options (see below).

### `crawl_screenshot(url, output_path)`

Capture a full-page screenshot and save it to a file. Parent directories are created automatically.

## Browser Reuse & Crash Recovery

Instead of launching Chromium on every call (which is expensive), the server keeps one browser instance for the process lifetime. If the shared browser crashes mid-session, the server detects it and recovers automatically:

- Crash detection matches Playwright collapse signatures only — `Target page, context or browser has been closed`, `browser has crashed`, `browsertype.launch` failures, etc. Network errors, anti-bot blocks, and timeouts are **page-side causes** and are never retried with a fresh browser.
- On crash: dispose the dead instance → launch a new one → retry, up to `_MAX_RECREATE_ATTEMPTS = 2` attempts.
- Both failure paths are checked equally on every attempt: exceptions raised by `arun()` **and** `result.success=False` + crash message in `error_message`.
- Preventive recycling (e.g., refresh every N pages) is intentionally left to Crawl4ai's built-in browser recycling; the server only reacts to actual collapses.

Concurrency note: multiple simultaneous `arun()` calls on the shared crawler are safe — Crawl4ai serializes page creation internally (`_page_lock`, GH-1198 fix) and manages context lifecycle with refcounting + LRU. Verified with concurrent multi-site smoke tests.

## Waiting Options (Dynamic Pages)

For dynamic pages that render content late using JS, use the waiting options of `crawl_markdown` / `crawl_structured`.

```python
# Method 1: Wait for a fixed duration (seconds)
crawl_markdown(url="https://example.com", wait_seconds=5)

# Method 2: Wait until a CSS selector appears (takes precedence over wait_seconds when specified)
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

1. **`wait_selector` is only valid for "newly created elements."** If the text of an element already present in the initial HTML (e.g., `<article id="dynamic">Loading...</article>`) changes later, the selector matches immediately and passes without waiting. For pages that update text dynamically, use `wait_seconds`.
2. **Extreme pages trigger anti-bot heuristics.** Pages with minimal content and many script tags are flagged by Crawl4ai's anti-bot detector as `Blocked by anti-bot protection: Structural: no_content_elements, script_heavy_shell`, resulting in `success=False`. Although rare in production pages, testing should be done on pages containing basic static content (navigation bars, paragraphs, etc.).
