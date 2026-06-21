# Claude Code MCP And Onboarding

This guide describes the Claude Code host surface for AIppocampus. It is about
connecting Claude Code to the AIppocampus MCP server and explicitly onboarding
Claude Code transcript source. It does not replace the provider/clean-source
contract in `docs/architecture/runtime-script-map.md`.

## First Success In Claude Code

If AIppocampus source is already registered, start with one source-backed
moment before host diagnostics:

```sh
aippocampus agent recall "old decision or handoff cue" --json
aippocampus agent deepen --request 1 --recall-selector <emitted-selector> --json
aippocampus search "a distinctive old phrase" --cwd "$PWD"
```

If Claude Code source is not registered yet, preview the local transcript
registration first, write only after explicit approval, then return to the
search/recall path above:

```sh
aippocampus onboard --provider claude-code --dry-run --json
aippocampus onboard --provider claude-code --json
```

Use the MCP setup and smokes below when Claude Code itself needs to call
AIppocampus tools, or when the first success path is blocked by host wiring.

## MCP Setup

Anthropic documents Claude Code MCP servers through `claude mcp add`,
`claude mcp list`, and `claude mcp get`. AIppocampus uses a local stdio server:

```sh
claude mcp add aippocampus -- aippocampus mcp
claude mcp list
claude mcp get aippocampus
```

For a clone-free package probe, use the packaged facade through `uvx`:

```sh
claude mcp add aippocampus -- uvx aippocampus mcp
claude mcp get aippocampus
```

Use the direct script path when you are developing from a local clone. Use the
PyPI `uvx aippocampus ...` path when an agent needs a copyable public command.
Use GitHub `uvx --from git+...` only for unreleased main-branch snapshots.

Use the repository probe to record the current host status without reading
private transcripts:

```sh
python3 tools/aippocampus/smoke/smoke_claude_code_mcp_host.py --json
```

If the `claude` CLI is missing or the server is not configured, the smoke
returns a concrete blocker. That blocker is evidence of host setup state, not a
failure of the core clean-source runtime.

For a persistent-config diagnostic that does not mutate Claude settings or
spend model budget, add `--persistent-diagnostic`:

```sh
python3 tools/aippocampus/smoke/smoke_claude_code_mcp_host.py --json --persistent-diagnostic --cwd "$PWD"
```

This parses `claude mcp get aippocampus`, redacts local paths and secret-like
values, then runs a minimal stdio JSON-RPC `memory_health` call against the
configured persistent server. Keep this result separate from the temporary
strict-config proof below. The diagnostic reports one of:
`missing_config`, `bad_command_path`, `runtime_import_failure`,
`server_start_failure`, `tool_schema_failure`, `tool_call_failure`, or
`healthy`.

Minimal healthy persistent config:

| Claude field | Expected value |
| --- | --- |
| `Type` | `stdio` |
| `Command` | `aippocampus` |
| `Args` | `mcp` |
| diagnostic status | `persistent_config_healthy` |
| nested diagnostic status | `healthy` |

`bad_command_path` means the configured command or a path-like argument no
longer resolves. The common stale local-clone failure is
`path_check=configured_arg_path_missing`, which should be repaired by removing
the stale local entry and adding the portable `aippocampus mcp` command again.
Do not commit or paste the local path from `claude mcp get`; the smoke output
redacts it for public reports.

Common manual repairs:

- `missing_config`: run `claude mcp add aippocampus -- aippocampus mcp`.
- `bad_command_path`: remove the stale entry with
  `claude mcp remove "aippocampus" -s local`, then add the current command
  again.
- `runtime_import_failure`: reinstall or run the command from the Python
  environment that contains AIppocampus.
- `tool_schema_failure`: verify the configured server is the AIppocampus MCP
  server and exposes `memory_health`.
- `tool_call_failure`: run `aippocampus health` and repair local artifacts
  before claiming persistent MCP health.

For an opt-in live Claude Code tool-call proof, run:

```sh
python3 tools/aippocampus/smoke/smoke_claude_code_mcp_host.py --json --call-tool --cwd "$PWD" --max-budget-usd 0.20
```

`--call-tool` starts a minimal `claude -p --bare --strict-mcp-config` session
with only the AIppocampus MCP server and calls `memory_health`. It may spend a
small live-model budget. The smoke uses Claude Code `stream-json` events to
confirm both the MCP `tool_use` and the matching `tool_result` without printing
the raw event body. A stale-index or stale-clean-source health result means the
MCP tool was reached, but local AIppocampus memory artifacts need refresh.

To test a Windows standalone binary as the stdio MCP server instead of the
Python script, build the artifact first and pass the binary command explicitly:

```sh
python3 tools/aippocampus/smoke/smoke_claude_code_mcp_host.py --json --call-tool --cwd "$PWD" --max-budget-usd 0.20 --server-command /path/to/aippocampus.exe --server-arg mcp
```

This uses a temporary strict MCP config only; it does not replace the user's
persistent Claude Code MCP settings.

## Project Skill Adapter

This repository ships a Claude Code project skill at
`.claude/skills/aippocampus/SKILL.md`. Claude Code discovers project skills
from `.claude/skills/`, so users can invoke `/aippocampus` in this repository
without installing a Codex plugin or mutating Claude Code settings.

The skill is intentionally small. It points Claude Code at the existing
AIppocampus MCP and CLI surfaces, reminds the agent that recall is source-backed
rather than model-native memory, and makes Claude Code transcript registration a
dry-run-first, explicit write action.

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
aippocampus onboard --provider claude-code --dry-run --json
aippocampus onboard --provider claude-code --json
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

Claude Code supports local-history onboarding, MCP/project-skill setup, and
scoped explicit AIppocampus hook handlers for `UserPromptSubmit` and `Stop`.
Do not claim real-host firing, `PostToolUse` / `PostToolBatch` capture,
compaction hook utility, all Claude Code versions, or broad native ambient
quality without source/event evidence.

Claude Code has its own upstream hook settings and event schemas. AIppocampus
intakes that official Claude Code hooks contract through a scoped surface with
read-only status/dry-run plus explicit install/uninstall commands. Start with
`aippocampus hooks claude-code status --json`:

```sh
aippocampus hooks claude-code status --json
aippocampus hooks claude-code dry-run --json
aippocampus hooks claude-code install --json
aippocampus hooks claude-code uninstall --json
aippocampus hooks claude-code smoke --json
```

`install` writes only AIppocampus-owned `UserPromptSubmit` and `Stop` handlers
after an explicit local command. It preserves unrelated Claude settings and
unrelated hook handlers. `uninstall` removes only AIppocampus-owned handlers and
is the command-based rollback shown by dry-run and install output. `status` and
`dry-run` never mutate `~/.claude/settings.json`, project settings, or local
settings.

The dry-run output validates whether the displayed handler command is copy-paste
ready in the current environment and shows the same rollback command. It prefers
`aippocampus hooks claude-code handle` when the console script is on `PATH`; if
the console script is missing but a Python module entrypoint is available, it
shows a `python3 -m aippocampus_runtime.cli.facade hooks claude-code handle`
style fallback instead. If neither command can be resolved without exposing
local executable paths, dry-run reports that operator `PATH` setup is still
required before copying handlers.

The scoped handler is fail-open and privacy-first:

- `UserPromptSubmit` can stay silent or emit bounded context without logging raw
  prompt text, transcript paths, session ids, or source refs.
- `Stop` can run as a completion lifecycle hook without blocking Claude Code
  completion.
- `PostToolUse`, `PostToolBatch`, `PreCompact`, and `PostCompact` remain
  event-level cannot-claim boundaries until they have payload sanitizers,
  summary/source-truth handling, and real-host firing evidence.
- Malformed or non-object Claude settings are reported as `blocked` with a
  redacted settings path. Repair the local JSON first, then rerun status before
  installing.

Do not reuse Codex hook installers as Claude Code hook support: `aippocampus
hooks prompt ...` and `aippocampus hooks lifecycle ...` still mutate Codex
`hooks.json` and report `host_integration.host = "codex"`.
