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

## Safe Checks

Run these read-only checks before relying on AIppocampus:

```sh
aippocampus mcp list-tools
aippocampus onboard --status --cwd "$PWD"
python tools/aippocampus/smoke/smoke_claude_code_mcp_host.py --json
```

If the MCP host is configured and the user wants a live proof, use the opt-in
tool-call smoke:

```sh
python tools/aippocampus/smoke/smoke_claude_code_mcp_host.py --json --call-tool --cwd "$PWD" --max-budget-usd 0.20
```

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

Do not install hooks, mutate Claude Code settings, or ingest private host
history from this skill unless the user explicitly approves that exact action.

AIppocampus does not currently provide a Claude Code hook installer. The
`aippocampus hooks ...` commands are Codex-only hook installers/status tools;
using `--provider claude-code` for onboarding does not make host hook support
available.
