# Claude Code Real-Host Dogfood Refresh

Role: dated public-safe evidence note.
Status: current #998 / #1021 dogfood report for the 2026-06-09 Windows
operator host.

This note records a sanitized Claude Code local-history and MCP dogfood run for
AIppocampus. It separates local-history parsing, dry-run onboarding, clean-source
cross-agent retrieval, persistent Claude MCP configuration, temporary strict
MCP tool-call reachability, and claim boundaries. Do not paste raw JSON output
from these commands into public docs: host output can include local paths,
server names, or private configuration shape.

## Commands

- `python tools\aippocampus\smoke\smoke_cross_agent_continuity.py --json`
- `python tools\aippocampus\smoke\smoke_claude_code_history.py --json`
- `python tools\aippocampus\smoke\smoke_claude_code_mcp_host.py --json`
- `python tools\aippocampus\smoke\smoke_claude_code_mcp_host.py --json --persistent-diagnostic --cwd . --diagnostic-timeout 30`
- `python tools\aippocampus\smoke\smoke_claude_code_mcp_host.py --json --call-tool --cwd . --max-budget-usd 0.20 --tool-timeout 180`
- `python -m aippocampus_runtime.cli.facade onboard --provider claude-code --dry-run --format json --cwd .`
- `python -m aippocampus_runtime.cli.facade onboard --status --format json --cwd .`

For the `python -m aippocampus_runtime.cli.facade ...` commands, the run used
the checkout `skills/aippocampus/scripts` directory on `PYTHONPATH`.

## Result

The public-safe synthetic cross-agent smoke passed. It registered one synthetic
Codex source and one synthetic Claude Code source in a temporary registry,
retrieved both through MCP `search_memory`, observed two matches in each
direction, preserved `codex:session:` and `claude-code:session:` source refs,
and kept registry/search paths redacted.

The local Claude Code history smoke passed against the operator machine. It
found 222 candidate Claude Code sessions, matched the current workspace, and
parsed three newest samples using booleans and counts only:

| sample | message_count | turn_count |
| --- | ---: | ---: |
| 1 | 18 | 3 |
| 2 | 64 | 20 |
| 3 | 54 | 17 |

The Claude Code onboarding dry-run passed without writing registry data. It
planned 223 Claude Code registrations, found three stale indexes that would be
repaired on an explicit write run, and reported `action_count=0`.

The provider-matrix status command passed. It reported Codex, Claude Code, and
generic JSONL as detected and `write_enabled`; `auto` still defaults to Codex
and lists other providers separately.

The persistent Claude Code MCP configuration is not currently healthy on this
host. `claude mcp get aippocampus` returned a zero process status but reported
`Status: Failed to connect`, so the smoke returns `host_config_ok=false` and
`reason=claude_mcp_get_reported_failed_connection`.

The #1021 persistent-config diagnostic narrowed the blocker. It parsed the
configured stdio command without mutating Claude settings, redacted the local
path-bearing argument, and returned `status=persistent_config_bad_command_path`
with `persistent_config_status=bad_command_path`,
`command_resolved=true`, and `path_check=configured_arg_path_missing`. The
diagnostic did not attempt a server startup after detecting that the configured
script path was missing.

The opt-in strict-config live MCP tool-call smoke passed. It used a temporary
strict MCP config instead of the persistent Claude Code MCP config, called
`mcp__aippocampus__memory_health`, observed both the Claude Code `tool_use` and
the matching `tool_result`, and returned
`status=tool_call_reachable_with_persistent_config_blocker`.

## Smoke Fix

This dogfood run exposed a smoke false positive: the older
`smoke_claude_code_mcp_host.py` treated successful `claude mcp list/get`
process return codes as host reachability even when `claude mcp get` reported
`Status: Failed to connect`.

The smoke now parses the sanitized `claude mcp get` text for failed-connection
markers, returns `blocked_host_config` for the persistent configuration, and
still allows `--call-tool` to prove the temporary strict-config path separately.

The follow-up diagnostic adds a persistent-config-only taxonomy:
`missing_config`, `bad_command_path`, `runtime_import_failure`,
`server_start_failure`, `tool_schema_failure`, `tool_call_failure`, and
`healthy`. On this host the current blocker is `bad_command_path`, not a
runtime import failure, MCP schema gap, or `memory_health` tool-call failure.

## Cannot Claim

This slice does not claim Claude Code prompt or lifecycle hook support,
unattended ingestion of private Claude history, cross-device sync, hosted/cloud
continuity, public marketplace readiness, private-history quality, or broad
cross-host relationship continuity.

The synthetic cross-agent smoke proves source-backed retrieval and source-ref
shape over public-safe fixtures. The local-history smoke proves local parser
reachability and counts only. The strict-config live tool-call smoke proves a
minimal Claude Code host can call AIppocampus MCP through a temporary config;
it does not prove the user's persistent Claude Code MCP configuration is
healthy. The #1021 persistent diagnostic proves the remaining local blocker is
a stale/missing configured command path, not persistent MCP health.
