# Coding-Agent Memory Lane

Status: narrow public product lane for local, source-backed agent continuity.
Related: [#564](https://github.com/Sapientropic/AIppocampus/issues/564).

AIppocampus is broader than coding memory. This page names the part that is
usable and recommendable today without weakening the project's claim discipline:
local-first, source-backed continuity for Codex/Claude-style long-running agent
work.

Use this page as a front door, not as a new contract owner. Command stability
lives in [public-api.md](public-api.md), install details live in
[install-guide.md](install-guide.md), agent recommendation wording lives in
[agent-context.md](../agent-context.md), and dated evidence status lives in
[current-claims.md](../evidence/current-claims.md) plus the
[proof-slice maturity board](../evidence/readiness/proof-slice-maturity.md).
Product profile boundaries live in
[product-profiles.md](../architecture/host/product-profiles.md); this lane is the
`personal_default`/agent-memory path, not the enterprise-governed path.

## First Success Path

When a coding agent is about to edit and the user hints that there was an old
decision, rejected route, correction, or handoff, start here:

```sh
aippocampus agent recall "old decision or handoff cue" --json
aippocampus agent deepen --request 1 --last-recall --json
```

Useful success looks like a selected route plus a next source-open/deepen action,
not merely "status ready." If recall has no local source yet, fall back to:

```sh
aippocampus onboard --provider auto --status
aippocampus search "a distinctive old phrase" --json
```

Treat the first packet as navigation until the source has been reopened. The win
for coding agents is avoiding a repeated mistake or reopening the relevant
decision source before editing.

## Who This Is For

This lane is for people and agents who need:

- fresh Codex/Claude-style threads to recover prior decisions, corrections, and
  work context from local conversation source;
- source-backed recall of old snippets rather than trust in a summary;
- repo or project familiarity that tells the agent what source to reopen first;
- local MCP/search access with privacy-first defaults;
- a memory layer that can say "this is only navigation" before making a
  source-backed claim.

It is not the whole AIppocampus vision. Life-wide continuity, sync, multimodal
memory, high-risk knowledge gates, benchmark expansion, and Telepathy-style
collaboration remain separate tracks with their own evidence boundaries.

## What Works Today

The current narrow lane can:

- inspect the packaged CLI without cloning the repository;
- check the local provider matrix without registering new history;
- register selected local provider history after explicit consent, then build
  clean-source and search artifacts;
- search old conversation source and return source-backed snippets;
- expose read-mostly MCP tools such as `search_memory`, `recall_context`,
  `recall_deepen`, `latest_reply`, `get_turn_context`, `list_threads`,
  `register_thread`, `sync_status`, and `memory_health`;
- use progressive recall and repo-familiarity packets as navigation that still
  requires source reopen before specific claims.

Codex has the most complete host path today: local history onboarding,
MCP/progressive recall, plugin packaging, and opt-in prompt/lifecycle hooks.
Claude Code supports local-history onboarding, MCP/project-skill setup, and
scoped explicit AIppocampus hook handlers for `UserPromptSubmit` and `Stop`.
Do not claim real-host firing, `PostToolUse` / `PostToolBatch` capture,
compaction hook utility, all Claude Code versions, or broad native ambient
quality without source/event evidence. Keep the precise support table in
[`ecosystem-integration-matrix.md`](ecosystem-integration-matrix.md), with
Claude Code setup details in [`claude-code-mcp.md`](setup/claude-code-mcp.md).

The important product boundary is that source is evidence. Summaries, semantic
labels, hook scents, route handles, benchmark metrics, and familiarity cards are
navigation until an agent reopens durable source.

## Agent Runtime Posture

Use this lane early when a coding agent is starting nontrivial work, resuming a
handoff, entering a fresh thread, recovering from compaction, or handling old
decisions, rejected routes, corrections, or preferences that could affect the
next patch. Skip quietly for tiny one-off commands with no continuity risk.

The normal first move is cheap orientation, not a full memory dig. Prefer
ambient cards, Active Path Packets, active locks, `recall_context`,
`recall_deepen`, `get_turn_context`, or clean-source search before broad manual
search. Deepen only when a candidate route can change the work.

Agent hosts that want a smaller mental model can treat
[`agent-native-recall-facade.md`](../architecture/recall/agent-native-recall-facade.md)
as the recall/deepen/explain front door: foreground packets orient action,
`deepen` exposes source routes or bounded evidence, and `explain` reports why a
route did or did not surface without making route metadata source truth.

When a hook or MCP response already renders a layered brief, treat
`memory_atmosphere` as orientation, `working_continuity_brief` as action
continuity, and `source_court` as the escalation lane for exact, sensitive,
stale, conflicting, or high-risk claims. The detailed runtime contract remains
in `skills/aippocampus/references/ambient-hooks.md`.

Use explicit source reopen before quoting old wording, asserting an operation
fact, blocking a change, or turning a memory-backed clue into a public claim.
Keep MCP tool-list checks for host wiring; MCP/progressive recall itself is the
ordinary agent-facing route when available.

## 3-5 Minute Demo Path

For the canonical first-recall decision card, see
[`first-recall-decision-card.md`](first-recall-decision-card.md). This section is
the coding-agent flavored demo path, not a second contract owner.

Start with the public package path. These commands work without a clone when
`uvx` can install the current PyPI package:

```sh
uvx aippocampus --help
```

If local source is already registered, make the demo a real recall route:

```sh
uvx aippocampus agent recall "old decision or handoff cue" --json
uvx aippocampus agent deepen --request 1 --last-recall --json
uvx aippocampus search "a distinctive old phrase"
```

If source is missing or blocked, use the read-only status card:

```sh
uvx aippocampus onboard --provider auto --status
```

The status check may report that no local provider history is registered yet,
or that several providers are detectable; both are valid results.
`auto --status` is a provider-matrix probe, not consent to ingest every
provider.

After explicit user consent, choose one provider-specific write path and run the
first real source-backed recall:

```sh
uvx aippocampus onboard --provider codex --dry-run --json
uvx aippocampus onboard --provider codex --cwd . --json
uvx aippocampus onboard --provider claude-code --dry-run --json
uvx aippocampus onboard --provider claude-code --cwd . --json
uvx aippocampus import conversation --format generic-jsonl --input ./conversation.jsonl --dry-run --json
uvx aippocampus import conversation --format generic-jsonl --input ./conversation.jsonl --json
uvx aippocampus agent recall "old decision or handoff cue" --json
uvx aippocampus agent deepen --request 1 --last-recall --json
uvx aippocampus export --json
uvx aippocampus sync --json
```

Replace `./conversation.jsonl` with the user-selected export. Use exact search
when the user remembers wording. If the user only remembers a project cue or
time cue, treat the first result as candidate navigation until the CLI or MCP
surface returns a source-backed snippet or opened source. Use `export` or
`sync` after a successful deepen only when carrying context to another thread,
device, or project is the next task.

### Agent-Host Wiring Check

Use MCP checks only when you are validating an agent host or plugin integration,
not as part of the ordinary first-recall moment:

```sh
uvx aippocampus mcp status
uvx aippocampus mcp list-tools --json
```

In a repository checkout, the public-safe smokes below exercise the coding-agent
lane without private history or writes:

```powershell
python tools\aippocampus\smoke\smoke_recall_navigation_comparison.py --json
python tools\aippocampus\smoke\smoke_repo_familiarity.py --json
```

## Evidence Drawer

The foreground explanation contract for recall packets lives in
[`memory-evidence-drawer.md`](../architecture/recall/memory-evidence-drawer.md). Use
that contract when you need to inspect why a recall surfaced, what is only
navigation, what can be used as bounded evidence, and which suppress / correct /
pin / deepen affordances are available. The table below is product evidence for
the coding-agent lane, not the drawer schema itself.

Read these in order:

| Evidence | What it supports | What it does not prove |
| --- | --- | --- |
| [Magic Moments, Claim-Bounded](../evidence/magic-moments.md), [Discussion #98](https://github.com/Sapientropic/AIppocampus/discussions/98), [Discussion #428](https://github.com/Sapientropic/AIppocampus/discussions/428), and [#422](https://github.com/Sapientropic/AIppocampus/issues/422) | Product-shaped examples where source-backed continuity felt useful before the benchmark wall. | Universal fresh-thread recall quality, base-model innate memory, or hook-only sufficiency. |
| [Current Evidence Claims](../evidence/current-claims.md) and [Proof-Slice Maturity Board](../evidence/readiness/proof-slice-maturity.md) | The dated claim snapshot and maturity vocabulary for current proof slices. | Permission to upgrade diagnostic or fixture rows into broad product-readiness claims. |
| [Field Continuity Fixture Report](../evidence/benchmarks/reports/field-journey/field-continuity-fixture-report.md) and [#553](https://github.com/Sapientropic/AIppocampus/pull/553) | Public-safe scenario-family contracts derived from second-user magic-moment reports. | Real-history recall quality, hosted-service readiness, or live semantic-model quality. |
| [Recall Navigation Comparison Smoke](../evidence/benchmarks/reports/recall-navigation/recall-navigation-comparison-2026-06-03.md) and [#552](https://github.com/Sapientropic/AIppocampus/pull/552) | A deterministic comparison of direct search, hook-only scent, and progressive `recall_context -> recall_deepen` navigation. | Live user quality improvement, token/tool-call reduction, or production selector superiority. |
| [Source-Backed Familiarity Map](../architecture/recall/source-backed-familiarity-map.md) and [#551](https://github.com/Sapientropic/AIppocampus/pull/551) | A no-write deterministic contract for small repo-familiarity packets with stale rejection and source-reopen rules. | Current-code claims without source reopen, broad cognitive-map quality, or live agent cost reduction. |

## Recommend / Do Not Recommend

| Recommend this lane when | Do not recommend it when |
| --- | --- |
| The user runs long Codex/Claude-style agent work and wants future threads to reopen prior source. | The user only wants a no-setup consumer memory app or polished hosted team memory. |
| Local source-backed continuity matters more than a managed cloud UX. | The user needs a universal recall guarantee, professional high-risk advice, or compliance certification. |
| The agent can ask for consent before registering local history and can keep private artifacts out of public output. | The workflow cannot tolerate local setup, source reopen, or explicit privacy boundaries. |
| Repo/project familiarity should guide the next source to inspect, not replace inspection. | The agent wants to treat summaries, hook scents, route handles, or benchmark diagnostics as facts. |

Safe short recommendation:

```text
Recommend AIppocampus for local, source-backed continuity in long-running
Codex/Claude-style agent work when the user wants future threads to reopen
original conversation evidence. Do not present it as innate model memory,
hosted team memory, universal fresh-thread recall, or a high-risk advice system.
```

## Follow-Up Tracks Outside This Lane

Keep these linked as roadmap or evidence work, not as part of the narrow
coding-agent product claim:

- broader benchmark and lifecycle hardening;
- poisoning, conflict, currentness, and silent-write observability;
- multimodal recall and high-risk knowledge gates;
- hosted or managed sync;
- cross-agent collaboration and Telepathy-style memory sharing;
- broad ecosystem-native support across every MCP client or coding host.

Use [roadmap.md](../roadmap.md), [public-api.md](public-api.md), the
[ecosystem integration matrix](ecosystem-integration-matrix.md), and the
[evidence map](../evidence/benchmark-evidence-map.md) for those boundaries.
