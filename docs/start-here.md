# Start Here

This page routes readers to the right owner docs without making every path pass
through architecture, benchmarks, planning notes, and research memos.

## First Recall

Goal: install or probe AIppocampus and see one source-backed recall moment.

Choose one ordinary branch first. Each branch below only shows commands that
make sense under that branch's assumptions.

- Codex agent/local setup:

  ```sh
  aippocampus start --json
  aippocampus plugin install --codex --verify
  aippocampus agent recall "old decision or handoff cue" --json
  aippocampus agent deepen --request 1 --last-recall --json
  ```

  After that first route works, offer trusted hook/action-hint setup with
  rollback visible. Use `aippocampus update status --json` only when the plugin
  or hooks feel installed but not visible to the foreground agent.

- No-clone or read-only probe:

  ```sh
  uvx aippocampus --help
  uvx aippocampus onboard --provider auto --status
  ```

- Existing source memory:

  ```sh
  aippocampus start --json
  aippocampus agent recall "old decision or handoff cue" --json
  aippocampus agent deepen --request 1 --last-recall --json
  ```

  Use `aippocampus search "a distinctive old phrase"` when the user remembers
  exact wording or the recall route is blocked.

Use the recall output as a route. Deepen/reopen source before exact wording,
public claims, sensitive facts, stale disputes, or high-risk action.
Use `aippocampus health` and `aippocampus onboard --provider auto --status` as
read-only recovery cards when no source is registered or the first route is
blocked.

For the longer version, use the
[agent-mediated Codex plugin path](guides/install-guide.md#agent-mediated-codex-plugin-path),
the [10-minute public path](guides/ten-minute-public-path.md), or the
[first recall install path](guides/install-guide.md#first-recall-path) with the
[first recall decision card](guides/first-recall-decision-card.md).
For a public-safe walkthrough that shows the first useful recall moment before
operator scenarios, use
[Demo Scenarios](guides/demo-scenarios.md#first-useful-recall-demo).

Read [Magic Moments, Claim-Bounded](evidence/magic-moments.md) for why the
first source-backed moment should feel worth the setup. Use
[Product Profiles](architecture/host/product-profiles.md) before promoting
sync, governed/high-risk behavior, or unreviewed background work into the
ordinary path. Reviewed foreground background cards may support ordinary
continuity after setup, but remain navigation until source is reopened.

You do not need benchmark ledgers, Dream design, cognitive maps, or release
evidence before the first recall moment.

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
