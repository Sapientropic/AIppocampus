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
- Captured turns can be explicitly exported as AIppocampus `generic-jsonl` rows
  for local registry import.

## What It Does Not Prove

- It does not prove current Claude.ai DOM selectors, cookies, REST endpoints, or
  SSE shapes are stable.
- It does not inject official Claude tool schemas.
- It does not use Claude remote MCP, ChatGPT Apps SDK, or ChatGPT internal
  endpoints.
- It does not implement `memory_save`, side panels, sync, concept graphs, or
  multi-platform support.
- It does not automatically import browser captures into AIppocampus. Export
  creates a private local file; the registry import remains a separate user-run
  command.

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

To make captured turns durable in AIppocampus, click `Export generic JSONL`.
The downloaded file contains redacted visible rows only: `session_id`, `role`,
`text`, `timestamp`, `turn_id`, `source_ref`, and `provider_metadata`.
Assistant-only captures are skipped so the generic importer never receives an
orphan assistant row.

Validate the export first:

```powershell
python skills\aippocampus\scripts\aippocampus_cli.py import conversation --format generic-jsonl --input path\to\aippocampus-browser-memory-SESSION.jsonl --dry-run --json
```

Then import it into the local registry:

```powershell
python skills\aippocampus\scripts\aippocampus_cli.py import conversation --format generic-jsonl --input path\to\aippocampus-browser-memory-SESSION.jsonl --json
```

## Automated Coverage

Run:

```powershell
python -m unittest tests.aippocampus.test_browser_memory_companion
```

The tests load the userscript through Node and cover explicit enablement,
capture, XML-style request parsing, CJK search, credential/path/prompt-injection
redaction, long-result truncation, generic JSONL export, registry dry-run
validation, and malformed export rejection.
