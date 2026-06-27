# Start Here

This page routes readers to the right owner docs without making every path pass
through architecture, benchmarks, planning notes, and research memos.

## First Recall

Goal: choose the right owner doc for the first source-backed recall moment
without turning this page into another quickstart.

Use the root [README First Use Path](../README.md#first-use-path) for the one
install/probe -> recall -> deepen/source-open -> daily-use loop. Come back here
only when you need a role-specific branch:

- Codex local setup:
  [agent-mediated Codex plugin path](guides/install-guide.md#agent-mediated-codex-plugin-path)
  and [first recall install path](guides/install-guide.md#first-recall-path).
  Register Codex source only after explicit consent; plugin install is host
  integration, not the first recall itself.
- Claude Code local setup:
  [Claude Code MCP setup](guides/setup/claude-code-mcp.md) and the
  [Install Guide](guides/install-guide.md). Preview provider status before
  writing source and install hooks only after reviewing the dry run.
- No-clone or public-safe probe:
  [10-Minute Public Path](guides/ten-minute-public-path.md) and
  [Demo Scenarios](guides/demo-scenarios.md#first-useful-recall-demo).
- Existing source memory:
  use the README loop, then [Public API](guides/public-api.md) only when a tool
  needs stable CLI, MCP, JSON, SDK, or Python import contracts.

After the first useful route, `aippocampus export --json` and
`aippocampus sync --json` are carry-forward checks, not prerequisites for
recall. Use [Product Profiles](architecture/host/product-profiles.md) before
promoting sync, governed/high-risk behavior, or unreviewed background work into
the ordinary path.

Read [Magic Moments, Claim-Bounded](evidence/magic-moments.md) for why the
first source-backed moment should feel worth the setup. You do not need
benchmark ledgers, Dream design, cognitive maps, or release evidence before
the first recall moment.

## See And Add To Memory

Goal: after one source-backed route is visible, make memory human-readable or
leave one small agent note without opening the operator references first.

```sh
aippocampus vault sync --json
aippocampus self-note list --current-thread --json
echo "What mattered in this thread, in one sentence." | aippocampus self-note append --current-thread --stdin --json
```

`vault sync` previews a local human-readable vault/dashboard route by default;
use the returned action card before writing under `AIPPOCAMPUS_VAULT` or
`~/AIppocampus Memory`. `self-note append` writes a short current-thread margin
note for future orientation; it is a route hint, not a user profile fact.
Detailed contracts live in
[`retrieval-and-storage.md#vault-and-dashboard`](../skills/aippocampus/references/retrieval-and-storage.md#vault-and-dashboard)
and
[`retrieval-and-storage.md#agent-self-notes`](../skills/aippocampus/references/retrieval-and-storage.md#agent-self-notes).

## Coding Agent User

Goal: decide whether AIppocampus helps Codex/Claude-style long-running work.

1. Start with [Coding-Agent Memory Lane](guides/coding-agent-memory.md).
2. Use [Agent Context](agent-context.md) for the compact recommendation and
   comparison boundary that an AI assistant can read.
3. Use [Ten-Minute Public Path](guides/ten-minute-public-path.md) for first-use
   probes, then [Public API](guides/public-api.md) only when another tool needs
   a stable CLI, MCP, JSON, SDK, or Python import contract.

Recall scents, familiarity, and model-organized packets are navigation until
source is reopened.

## Maintainer

Goal: change runtime, search, hook, sync, registry, or storage behavior.

1. Start with [Architecture Index](architecture/README.md) to find the current
   contract or implementation map.
2. If the work crosses Macro/Yi, Dream, local/global compatibility,
   familiarity cards, avatar illumination, or active recall, use
   [Source-Shape Runtime Spine](architecture/source-shape-runtime-spine.md)
   before reading individual design memos.
3. Use [Runtime Script Map](architecture/runtime-script-map.md) before changing
   high-risk runtime entrypoints.
4. Use the relevant skill reference under `skills/aippocampus/references/`
   when the behavior is part of the installable agent-facing runtime.

Planning docs are handoff context, not the final contract. Evidence docs show
what has been verified, not what the runtime should do next.

## Benchmark Or Claim Reviewer

Goal: check what AIppocampus can honestly claim.

1. Start with [Evidence Index](evidence/README.md).
2. Use [Can-Claim Ladder](evidence/can-claim-ladder.md) when you need the
   positive proof map before the caveat ledger.
3. Use [Public Provenance And Current Value Ledger](evidence/public-provenance-ledger.md)
   when you need the compact origin/current-value trail before issue
   archaeology.
4. Use [Current Claims](evidence/current-claims.md) for present-tense benchmark
   and readiness numbers.
5. Use [Benchmark And Evidence Map](evidence/benchmark-evidence-map.md) when
   you need runner, corpus, smoke, or dated-result owners.
6. Use [Public Readiness Verification](evidence/readiness/public-readiness-verification.md)
   only when you need dated command evidence.

Community reports and magic moments are useful product signals. They do not
become official claims until promoted through the current evidence flow.

## Continuity And Research Reader

Goal: understand the broader life-wide / relationship-continuity idea.

1. Start with the origin essay:
   [未干的地图](未干的地图.md) or [The Unfinished Map](the-unfinished-map.md).
2. Read [Roadmap](roadmap.md) for the product north star and layer map.
3. Use [Research Notes](research/README.md) for Pearl, source-as-world,
   journey, reflection, Dream, ambient recall, correction reconsolidation, and
   long-shot activation ideas.

Research notes preserve possibility. Runtime contracts and public claims still
need source-backed owners elsewhere.

## Historical Or Superseded Material

Goal: reopen old planning context without mistaking it for current truth.

Start with [Archive](archive/README.md). Archived notes should point back to a
current owner such as `docs/README.md`, `docs/roadmap.md`, a local folder index,
or the implementation itself.
