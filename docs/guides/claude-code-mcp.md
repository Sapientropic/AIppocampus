# Claude Code MCP And Onboarding

This guide describes the Claude Code host surface for AIppocampus. It is about
connecting Claude Code to the AIppocampus MCP server and explicitly onboarding
Claude Code transcript source. It does not replace the provider/clean-source
contract in `docs/architecture/runtime-script-map.md`.

## MCP Setup

Anthropic documents Claude Code MCP servers through `claude mcp add`,
`claude mcp list`, and `claude mcp get`. AIppocampus uses a local stdio server:

```sh
claude mcp add aippocampus -- python /path/to/AIppocampus/skills/aippocampus/scripts/aippocampus_mcp_server.py
claude mcp list
claude mcp get aippocampus
```

Use the repository probe to record the current host status without reading
private transcripts:

```sh
python tools/aippocampus/smoke/smoke_claude_code_mcp_host.py --json
```

If the `claude` CLI is missing or the server is not configured, the smoke
returns a concrete blocker. That blocker is evidence of host setup state, not a
failure of the core clean-source runtime.

## Onboarding States

Check detected providers first:

```sh
aippocampus onboard --status --cwd "$PWD"
```

Provider states mean:

- `blocked`: the provider is missing, unconfigured, or has no discoverable
  transcripts for the current environment.
- `dry_run`: the provider can preview planned registration without writing.
- `write_enabled`: the provider has a clean-source parser and can write registry
  artifacts when explicitly selected.

Register Claude Code transcripts only with an explicit provider:

```sh
aippocampus onboard --provider claude-code --dry-run --format json
aippocampus onboard --provider claude-code --format json
```

`auto` remains conservative and defaults to Codex. It may report Claude Code as
detected, but it must not silently ingest private Claude Code history.

## Privacy Boundary

Claude Code transcripts, local paths, cwd values, and host settings are private
local locators. AIppocampus clean source keeps visible user/assistant text plus
source refs; thinking blocks, tool payloads, attachments, and non-message rows
do not enter daily recall by default.

MCP tool results redact local paths unless a local operator explicitly requests
`include_private_paths: true` for repair/debug work.

## Hooks

Do not reuse Codex hook installers as Claude Code hook support. If Claude Code
hooks are added later, they need their own opt-in installer, status command, and
privacy notes. This guide only claims MCP setup and explicit transcript
onboarding.
