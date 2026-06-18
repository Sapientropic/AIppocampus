# Ten-Minute Public Path

Role: short public first-use path.
Status: current foreground guide.

Use this path when an external user, agent host, or downstream script needs the
smallest dependable AIppocampus probe before reading the full
[public API contract](public-api.md). The goal is one useful source-backed
continuity route, not operator setup.

For an ordinary Codex setup where the user has asked an agent to install
AIppocampus locally, prefer the
[agent-mediated Codex plugin path](install-guide.md#agent-mediated-codex-plugin-path).
This page is the no-clone, read-only, or public-stability path.

## 1. Package Probe

Verify the packaged CLI without cloning or writing local memory artifacts:

```sh
uvx aippocampus --help
```

This is read-only. It proves the package entrypoint resolves; it does not prove
that local history is registered or that any host integration is live.

## 2. First Useful Recall

If local source is already registered, try the source-backed route:

```sh
uvx aippocampus agent recall "old decision or handoff cue" --json
uvx aippocampus agent deepen --request 1 --last-recall --json
```

Use exact search when the user remembers wording or the recall route is blocked:

```sh
uvx aippocampus search "a distinctive old phrase"
```

Recall routes and background findings are navigation until source is reopened.
Deepen before exact wording, public claims, stale disputes, sensitive facts, or
high-risk action.

## 3. Read-Only Provider Status

If source is missing or blocked, check whether a local provider has usable
source without registering new history:

```sh
uvx aippocampus onboard --provider auto --status
```

Human-readable output is the default. Add `--format json` only for automation.
`auto` may report Codex, Claude Code, or generic JSONL readiness; it must not
silently ingest private history.

## 4. Explicit Write Paths

Only after the user consents to register selected local history, choose a
scoped write path:

```sh
uvx aippocampus onboard --provider codex --dry-run --json
uvx aippocampus onboard --provider codex --cwd . --json
uvx aippocampus onboard --provider claude-code --dry-run --json
uvx aippocampus onboard --provider claude-code --cwd . --json
uvx aippocampus import conversation --format generic-jsonl --input ./conversation.jsonl --dry-run --json
uvx aippocampus import conversation --format generic-jsonl --input ./conversation.jsonl --json
```

The generic JSONL path requires a real user-selected local file. Do not paste
placeholder paths as runnable commands.

After registration, ask for one route again:

```sh
uvx aippocampus agent recall "old decision or handoff cue" --json
uvx aippocampus agent deepen --request 1 --last-recall --json
uvx aippocampus export --json
uvx aippocampus sync --json
```

Use `export` or `sync` only after a source-backed route has been reopened and
the next goal is carrying that context into another thread, device, or project.

## 5. Optional Host Checks

Only when an agent host, plugin, or operator check needs those surfaces, inspect
the MCP catalog or local health card:

```sh
aippocampus health --cwd "$PWD" --json
aippocampus mcp status
aippocampus mcp list-tools --json
```

This path intentionally does not require MCP, cognitive-map jobs, sync, plugin
packaging, object storage, or benchmark runners.

## Write And Privacy Boundaries

Generated memory artifacts use the configured AIppocampus registry:
`AIPPOCAMPUS_REGISTRY_DIR`, then `AIPPOCAMPUS_HOME/registry`, then legacy Codex
registry fallback. Project repositories should not receive raw rollouts,
registry exports, generated indexes, sync bundles, or private local paths.

Hook installation is explicit opt-in. Trusted Codex users can review action-time
hint status with `aippocampus hooks action status --json`; install only after
that review. Claude Code supports local-history onboarding, MCP/project-skill
setup, and scoped explicit AIppocampus hook handlers for `UserPromptSubmit` and
`Stop`; do not claim real-host firing, `PostToolUse` / `PostToolBatch` capture,
compaction hook utility, all Claude Code versions, or broad native ambient
quality without source/event evidence.

The personal control vocabulary is pause / forget / do-not-use-here / export /
why-not. `export`, `why-not`, and `do-not-use-here` have concrete public command
surfaces today. `pause` and `forget` are safe foreground control cards first:
they explain the boundary and nearest explicit route without claiming global
pause or destructive deletion.

When you need stable API, MCP, JSON, environment, or Python import details, move
to [public-api.md](public-api.md).
