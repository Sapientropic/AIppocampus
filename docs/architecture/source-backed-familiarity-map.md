# Source-Backed Familiarity Map

Role: active design.

Status: first deterministic repo-adapter slice.
Related: #250, `aippocampus_runtime.navigation.repo_familiarity`,
`tools/aippocampus/smoke/smoke_repo_familiarity.py`,
`tools/aippocampus/smoke/smoke_repo_familiarity_foreground_experiment.py`.

AIppocampus can make a future agent feel oriented without pretending the model
has innate memory. A familiarity map is the layer that says "this source area
may change your next move." It is not a fact store, a repo knowledge graph, or a
reason to skip source reopen.

The first pressure-test adapter is repo familiarity because repositories have
clear source files, docs, tests, import owners, and stale-state failure modes.
This is deliberately not a coding-only pivot. The intended general shape is
`source_backed_familiarity_map`: compact cards can later describe projects,
relationships, policies, or capability contracts, as long as they remain
source-backed navigation rather than truth.

## Card Contract

Each foreground-eligible card must carry:

- `domain = repo`
- `landmark`: the subsystem or boundary being named
- `boundary`: what not to cross casually
- `route`: files, tests, docs, or commands to inspect first
- `source_refs`: reopenable source anchors
- `freshness` and `invalidation`: commit or file-fingerprint guards
- `why_now`: why this task might need the card
- `action_delta_required`: the next action this card may change
- `first_source_to_reopen`: the first source to check before using the card
- `stop_after`: when enough source has been reopened and extra verification is
  optional or noisy
- `do_not_use_for`: contexts where the card should stay quiet

Cards that lack an action delta or stop rule should not enter the foreground
packet. More context is not better if it only gives the agent more material to
audit.

## Selector Contract

The selector must prefer tiny packets over broad maps:

- default foreground limit is 1-3 cards
- byte budget is explicit
- stale file-hash or commit mismatch is a fast rejection
- irrelevant cards are rejected before they become verification work
- selected cards are navigation and always require source reopen

The deterministic `cost_delta_report` is only a proxy: selected count, packet
bytes, estimated source-reopen count, and fast rejects. It must not claim live
token, tool-call, or wall-clock savings without a separate benchmark arm.

The repo smoke is no-write and public-safe. It uses repository docs/code/test
paths as source rows, computes relative-path fingerprints, and includes an
adversarial stale-card arm plus an unrelated README task arm. Passing the smoke
only proves the deterministic contract, not live agent helpfulness.

## Navigation Affordance Integration

Selected repo familiarity cards now feed the shared navigation-potential
projection instead of living as a separate coding-orientation packet. The adapter
turns a card into a source-reopen route with the original
`first_source_to_reopen`, `stop_after`, `do_not_use_for`, freshness, invalidation,
and decision-shadow boundary attached.

This integration is intentionally downstream of the selector contract. A
non-coding prompt should not receive repo-card affordances because irrelevant
cards are rejected before projection. A stale card may become backstage source
refresh, but not a foreground coding route. A rejected-route card can warn or
constrain the next coding move, but it still cannot prove current code state
without reopening source.

## Opt-In Foreground Experiment Evidence

The opt-in foreground experiment smoke compares public-safe fixture arms plus a
public current-checkout case for `no_card`, `selected_card`, and
`stale_or_irrelevant_card`. The current-checkout case reuses the same
repo-relative source rows and file fingerprints as the packet smoke, so the
experiment is no longer fixture-only while still serializing no local absolute
paths or raw source text.

It reports only proxy metrics: `route_quality_proxy`, `tool_call_count`,
`input_token_proxy`, `elapsed_ms_proxy`, fast rejects, and stale-route drag.
These fields define the evidence envelope for future live runs; they do not
prove live answer quality, token/tool-call savings, default prompt-hook lift, or
multi-agent familiarity sharing.

## Non-Claims

This slice does not prove:

- production live quality
- cross-agent or multi-host familiarity sharing
- broad source-backed cognitive-map quality
- that familiarity packets reduce cost in real agent runs
- that cards can make current-code claims without reopening source

The useful first claim is narrower: AIppocampus now has a deterministic contract
for small, source-backed repo familiarity packets that can be tested before any
future hook or host integration tries to surface them.
