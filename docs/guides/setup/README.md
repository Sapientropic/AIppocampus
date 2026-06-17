# Setup Guides

Role: setup and operator guide index.
Status: current guide layer.

## Foreground Setup Chooser

Choose the narrow setup path that matches the current host before reading the
operator docs below.

| Situation | Recommended command | Mutation boundary |
| --- | --- | --- |
| Trusted Codex setup | `aippocampus plugin install --codex --verify` | Installs/verifies the Codex plugin path only after the local agent was asked to set it up. Follow with `aippocampus update status --agent-json` if tools are not visible. |
| Codex hooks or action hints | `aippocampus hooks action status --json` | Read-only status first. Install Codex hooks or write hint caches only after reviewing the explicit install/write command and rollback. |
| Claude Code setup | `aippocampus hooks claude-code status --json` | Read-only status for scoped `UserPromptSubmit` / `Stop` handlers. `dry-run` previews; `install` and `uninstall` mutate only AIppocampus-owned Claude settings entries. |
| No clone or read-only probe | `uvx aippocampus --help` | Read-only package probe. Use `uvx aippocampus onboard --provider auto --status` to inspect provider readiness without registration. |
| Explicit export/import | `uvx aippocampus import conversation --format generic-jsonl --input ./conversation.jsonl --dry-run --json` | Dry-run first with a real user-selected file. Import writes only after explicit consent. |
| Rollback or uninstall | `aippocampus hooks claude-code uninstall --json` | Removes scoped AIppocampus-owned Claude hook entries. For Codex/plugin rollback, inspect `aippocampus update status --agent-json` and the relevant uninstall card before mutating. |

Codex prompt/lifecycle hooks are Codex-only. Claude Code supports
local-history onboarding, MCP/project-skill setup, and scoped explicit
AIppocampus hook handlers for `UserPromptSubmit` and `Stop`; do not claim
real-host firing, `PostToolUse` / `PostToolBatch` capture, compaction hook
utility, all Claude Code versions, or broad native ambient quality without
source/event evidence.

## Operator Docs

| File | Use |
| --- | --- |
| [claude-code-mcp.md](claude-code-mcp.md) | Claude Code MCP setup, provider onboarding states, and privacy boundary. |
| [dependency-contract.md](dependency-contract.md) | Runtime, optional integration, benchmark, dev, release, and CI dependency taxonomy. |
| [object-storage-providers.md](object-storage-providers.md) | S3, R2, and GCS XML provider setup plus object-storage pitfalls. |
| [release-checklist.md](release-checklist.md) | Repeatable release, tag, coverage, and public-boundary gates. |
| [safe-environment.md](safe-environment.md) | `.env.example`, plugin MCP env inheritance, and isolated-runtime boundary. |
