# Browser Memory Companion Prototype

This folder contains the first public-safe Claude.ai local `memory_search` MVP
for issue #61.

## What It Proves

- Capture is off by default.
- The user must explicitly enable capture/search in the visible panel.
- Captured turns stay in browser `localStorage` for the current device.
- `<memory_search query="..." max="...">` requests can be parsed locally.
- Search uses small browser-local lexical matching with CJK bigrams.
- Results are redacted, length-bounded, and shown as a visible handoff for the
  user to review before sending anything back to Claude.

## What It Does Not Prove

- It does not prove current Claude.ai DOM selectors, cookies, REST endpoints, or
  SSE shapes are stable.
- It does not inject official Claude tool schemas.
- It does not use Claude remote MCP, ChatGPT Apps SDK, or ChatGPT internal
  endpoints.
- It does not implement `memory_save`, side panels, sync, concept graphs, or
  multi-platform support.

## Manual Smoke

Install `claude-memory-search.user.js` in Tampermonkey, open `https://claude.ai`,
enable `AIppocampus capture/search`, paste a user/assistant turn into the local
capture fields, and click `Capture local turn`.

Then paste a virtual tool request such as:

```xml
<memory_search query="脚本架构" max="2" />
```

Click `Run visible search`. The output should show an
`AIppocampus memory_search results` block with a `source-boundary` line,
redaction markers when sensitive-looking text is present, and `truncated` when
the bounded result would exceed the local limit.

## Automated Coverage

Run:

```powershell
python -m unittest tests.aippocampus.test_browser_memory_companion
```

The tests load the userscript through Node and cover explicit enablement,
capture, XML-style request parsing, CJK search, credential/path/prompt-injection
redaction, and long-result truncation.
