---
name: AIppocampus
description: Use AIppocampus source-backed continuity through the repo MCP and CLI surfaces.
disable-model-invocation: true
---

# AIppocampus

Use this when the user asks Claude Code to recall project context, check
AIppocampus memory health, or prepare explicit Claude Code transcript
onboarding.

AIppocampus is source-backed continuity. Do not claim model-native memory,
innate recall, or private transcript access. Treat summaries as navigation
layers; when answering from memory, prefer source ids, source refs, and
clean-source evidence over unsupported paraphrase.

## First Success Path

Aim for one source-backed recall moment before diagnostics. If source is
already registered, search or ask for a bounded agent route:

```sh
aippocampus search "a distinctive old phrase" --cwd "$PWD"
aippocampus agent recall "old decision or handoff cue" --json
aippocampus agent deepen --request 1 --last-recall --json
```

Treat search hits, recall routes, and AIppo/self-note packets as navigation
until source is reopened for exact, stale, sensitive, disputed, or high-risk
claims.

## Claude Code Onboarding

Preview Claude Code transcript registration before writing anything:

```sh
aippocampus onboard --provider claude-code --dry-run --format json
```

Only run the write form after the user explicitly asks to register Claude Code
history:

```sh
aippocampus onboard --provider claude-code --format json
```

After registration, return to the first success path and search for one
source-backed snippet.

## Repair And Host Diagnostics

Use these checks when the first success path is blocked, or when the task is
specifically host/MCP verification:

```sh
aippocampus health --cwd "$PWD"
aippocampus onboard --status --provider auto --cwd "$PWD"
aippocampus mcp status
aippocampus mcp list-tools --json
python tools/aippocampus/smoke/smoke_claude_code_mcp_host.py --json
```

If the MCP host is configured and the user wants a live proof, use the opt-in
tool-call smoke:

```sh
python tools/aippocampus/smoke/smoke_claude_code_mcp_host.py --json --call-tool --cwd "$PWD" --max-budget-usd 0.20
```

Do not install hooks, mutate Claude Code settings, or ingest private host
history from this skill unless the user explicitly approves that exact action.

AIppocampus provides Claude Code hook status/dry-run/smoke commands for the
scoped `UserPromptSubmit` and `Stop` contract:

```sh
aippocampus hooks claude-code status --json
aippocampus hooks claude-code dry-run --json
aippocampus hooks claude-code smoke --json
```

These commands do not mutate Claude Code settings. `aippocampus hooks prompt`
and `aippocampus hooks lifecycle` remain Codex-only installer/status tools, so
using `--provider claude-code` for onboarding does not install Claude Code host
hooks.
