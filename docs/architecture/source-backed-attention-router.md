# Source-Backed Attention Router

Role: current contract.

This contract defines attention-style routing for AIppocampus as navigation, not
memory truth. Attention may choose where to look; only reopened source may say
what happened.

## Contract

The router has three non-negotiable boundaries:

- Hard masks are eligibility gates, not weighted attention heads.
- Values are route packets with handles, not source text or memory facts.
- Output levels follow the existing action grammar.
- Bounded summaries are route objects, not source-backed evidence.

The first runtime contract lives in
`aippocampus_runtime.navigation.attention_router_contract`. It is a fixture and
schema surface, not the full router.

## Hard Masks

Hard masks run before lexical, semantic, salience, temporal, or action scores.
A masked source cannot be recovered by high relevance.

Initial mask names:

- `privacy_domain`
- `source_visibility`
- `transfer_allowed`
- `deleted_source`
- `no_recall`
- `no_cross_domain`
- `stale_handle_invalid`
- `high_risk_no_source`

When any hard mask applies, the route packet must use:

- `output_mode="silence"`
- `action_grammar="ignore_or_blocked"`
- `claim_permission="blocked"`
- `emitted=false`

Blocked diagnostics may name mask ids and reason codes, but they must not emit
raw source text or source handles that would bypass the mask.

## Route Packet Shape

A route packet may contain:

- `route_id`
- `output_mode`
- `action_grammar`
- `claim_permission`
- `source_handles`
- `bounded_summary`
- `summary_fallback_reason_codes`
- `head_votes`
- `masks_applied`
- `contract`

`source_handles` are reopen handles, not claims. They may carry stable source
ids, segment ids, turn ranges, and `reopen_required`. They must not carry raw
private text in public reports.

`head_votes` explain why the route was considered. They may include head name,
score, and reason code. They do not become evidence.

`bounded_summary` may orient an agent with explicit scope, source coverage,
freshness, claim permission, and a reopen path. It must not include open-ended
memory prose or raw private source text in public reports.

## Output Levels

The router maps to the existing action grammar instead of adding a new authority
taxonomy:

| Output mode | Action grammar | Claim permission |
| --- | --- | --- |
| `silence` | `ignore_or_blocked` | `blocked` |
| `direction_only` | `direction_only` | `no_claim_before_reopen` |
| `bounded_summary_as_route` | `direction_only` | `no_claim_before_reopen` |
| `reopenable_route` | `reopenable_route` | `no_claim_before_reopen` |
| `bounded_evidence` | `bounded_evidence` | `bounded_claim_allowed` |

`bounded_summary_as_route` sits between scent and reopenable route. It can say
"this scoped summary may help decide where to reopen source next"; it cannot
support exact quotes, current facts, disputed facts, or high-risk claims. If
coverage is weak, stale, conflicted, high-risk, or privacy-sensitive, the
router must fall back to `direction_only`, `reopenable_route`, or `silence`
according to the available source handles and masks.

`bounded_evidence` is allowed only after source is already open and bounded to
a declared scope. Exact quotes, sensitive claims, stale/currentness questions,
conflicts, and high-risk actions still require source-court behavior.

## Invariants

- Attention score is not evidence.
- Salience is not truth.
- Semantic similarity is not support.
- Privacy masks are non-negotiable.
- Currentness requires source reopen or an explicit currentness chain.
- Conflict raises the burden of proof.
- Source refs must be reopenable before claims.
- Route packets may guide the next action, but they do not answer from memory.

## Current Fixture

`build_contract_fixture_report()` covers six contract cases:

- high lexical/semantic relevance blocked by `privacy_domain`;
- a source-backed `reopenable_route`;
- source-open bounded evidence;
- source-thin `direction_only` scent;
- a valid bounded summary route;
- stale / weak summary fallback to `direction_only`.

The fixture reports:

- `masked_source_resurrection_count`;
- `source_backed_claim_without_reopen`;
- `summary_claim_ready_without_reopen_count`;
- `bounded_summary_fallback_count`;
- public-safe privacy boundaries;
- cannot-claim entries for broad router quality, private-history behavior,
  model training, route packets as source truth, and default foreground
  adoption.

## Cold Route Sidecars

The Source-Backed Familiarity Map is cold route sidecar metadata for the
attention router. It says how a route was previously walked, which source to
reopen first, what invalidates it, and which paths were dead ends. It is not an
attention head, an output level, a warning channel, or a truth source.

Familiarity cards may feed future `scope_head`, `episode_head`, `action_head`,
or `currentness_head` features as metadata. The integration path remains the
existing `aippocampus_runtime.navigation.repo_familiarity` projection; a router
prototype should reuse that projection or document why it cannot.

Minimal sidecar fields map to the existing repo familiarity card contract:

- `first_source_to_reopen`
- `stop_after`
- `freshness`
- `invalidation`
- `decision_shadow`
- `rejected_route`
- `source_refs`
- `do_not_use_for`

Stale familiarity may request refresh or source reopen. It must not become
claim-ready support, current-code proof, or an independent foreground warning.

Context links: the source-backed familiarity seed is
[#249](https://github.com/Sapientropic/AIppocampus/discussions/249); active
tracks include [#250](https://github.com/Sapientropic/AIppocampus/issues/250)
and [#847](https://github.com/Sapientropic/AIppocampus/issues/847); foreground
repo familiarity slices landed in
[#631](https://github.com/Sapientropic/AIppocampus/pull/631) and
[#649](https://github.com/Sapientropic/AIppocampus/pull/649).

## Route Token Hierarchy

The token projection layer lives in
`aippocampus_runtime.navigation.attention_route_tokens`. It turns clean-source
containers and existing sidecars into compact route tokens before any router
scoring happens:

```text
source_span_token -> event_token -> episode_or_question_token
```

`source_span_token` is the tightest reopenable unit, such as a line range,
sentence, clause, or code block. It may point into a larger event with
`parent_event_token_id` and must preserve source handles for the exact span.

`event_token` represents a clean-source turn or event with role, turn id,
timestamp, thread, phase, source refs, and any child span ids. The event is a
container, not the smallest ranking target.

`episode_or_question_token` groups event/span tokens into a question frontier,
rejected route, conflict/update chain, or episode arc. It remains
`direction_only` with `no_claim_before_reopen`; grouping route tokens does not
create claim support.

All token levels carry optional route metadata slots for `salience`,
`currentness`, `privacy`, and `conflict`. Missing slots stay `unknown`; callers
must not invent certainty to make a head score cleaner.

## Deterministic Hot Router V0

The first router prototype lives in
`aippocampus_runtime.navigation.attention_hot_router`. It accepts query state
and route tokens, applies hard masks before scoring, computes auditable head
votes, then emits the route-packet contract from
`attention_router_contract`.

The V0 heads are deterministic diagnostics:

- `lexical_head`
- `semantic_head` when a supplied sidecar score exists
- `action_head`
- `evidence_packaging_head` when packaged span features exist
- `scope_head`
- `salience_head`
- `currentness_head`
- `conflict_head`
- `risk_head`
- `abstention_head`

The default score-fusion policy is `calibrated_rule_grid_v1`. It is a
deterministic runtime policy adopted from the public-safe #1112/#1230
calibration fixture, not a trained model. The policy lifts source handles and
evidence-packaging signals, penalizes anti-nag repeats, and keeps hard masks
outside scoring. Masked candidates may retain high diagnostic scores, but they
still emit `silence`.

The adaptive threshold remains a local deterministic gate over risk, conflict,
currentness, salience, and scope. It is not learned attention and must not be
treated as production traffic calibration.

## Semantic Warming Route Producer

`aippocampus_runtime.navigation.semantic_warm_route_producer` is the #1139
bridge from background semantic warming to the deterministic router. It accepts
already-materialized scout output and projects it into the existing
`attention_route_token` shape:

```text
background semantic warming / scouts
  -> sanitized route tokens
  -> deterministic hot router
  -> compact route packet
```

The producer may carry semantic scores, aliases, scout-family votes,
source-ref fingerprints, topic-epoch labels, guard status, cache/related-cache
status, and source-bridge diagnostics. It must not carry raw prompt text, raw
source snippets, local paths, private ids, or raw semantic model reasoning in
public/debug output.

Foreground budget boundaries:

- Tier 0 foreground may read cache/handles only and must not make fresh
  external semantic calls.
- Tier 1 foreground warm-read may consume already-materialized semantic route
  material under local budget.
- Tier 2 background may run selected scout profiles and write route material
  for later turns.
- Tier 3 diagnostic/benchmark may run full scout sweeps.

Topic-epoch reuse must come from stable source/candidate fingerprints, scout
topic decisions, semantic trigger ids, scope labels, or source-ref fingerprints.
Raw prompt fuzzy matching is not a route-reuse authority.

Live agent recall now has a narrow route-producer slice: clean-source recall
hits can be projected into compact foreground packets with fixed-vocabulary
`route_topic`, `route_label`, `label_granularity`, and specificity metrics.
This is enough to distinguish routes that share broad buckets such as
`technical_work`, but it is not the full #1188 promotion. It does not add fresh
semantic warming, familiarity-map scoring, trained topic inference, source
support, or default foreground hooks.

The #1301 bridge into the recall-navigation promotion harness is still
diagnostic: `attention_router_navigation_only` runs the deterministic hot router
over the same `recall_context` candidate set and records route-family selection,
foreground packet bytes, and deictic fail-closed behavior. It does not reopen
source, answer the question, or replace the live `recall_context` ordering. The
public fixture includes a light Arabic continuity cue for the AIppocampus/little
hippocampus route family plus a pure deictic Arabic negative control; the former
may select a route before manual search, and the latter must ask to clarify or
recall rather than bind to visible context.

ROI status can reduce low-yield non-guard scout families to watch or diagnostic
surfaces, but required guard families remain `guard_required`. Quiet privacy or
evidence-gap guards are not retirement candidates merely because they rarely
emit visible packets.

## Action-Time Query Features

`attention_hot_router.extract_action_query_features()` projects synthetic
pending-action payloads into public-safe query features: tool name, normalized
file-path terms, issue ids, command/test/branch terms, topic epoch, active locks,
anti-nag token ids, and risk mode. It does not emit raw tool args or raw command
text.

The router consumes these features through `action_head`. Action cues can lift a
route when the prompt is too vague but the pending action reveals a matching
path, issue id, test, or command-failure chain. This remains diagnostic routing:
hard masks run first, anti-nag suppression can force `direction_only`, and
action-matched packets still carry `no_claim_before_reopen`.

## Evidence Packaging Head

`aippocampus_runtime.navigation.attention_evidence_packager` is the #1110
diagnostic layer between source-window routing and exact source-span support. It
preserves the first-stage retrieval window separately, then packages compact
span handles, candidate counts, selected span rank, window radius,
currentness/conflict flags, and optional counter-evidence handles.

This head exists because source-window routing can be strong while exact-line
ranking remains weaker. It may tighten the next source handle to reopen, but it
does not make reranker or packaging output true. `bounded_evidence` is allowed
only when the selected span is already source-open, bounded to a declared scope,
current, and unconflicted. Stale, superseded, conflicted, hard-masked, or
wrong-source spans must stay reopenable/navigation-only or be rejected with an
auditable reason code.

The public fixture mirrors the LongMemEval-style distinction: a context-visible
span can become a tighter packet, while wrong-source, stale, and conflicted
controls cannot become claim-ready support. The report omits raw source text,
gold answers, and miss taxonomy.

## Three Powers Route Facets

`aippocampus_runtime.macro.three_powers` is a deterministic macro-orientation
helper for layer-aware fanout. It maps route source families into:

- `earth` / 地: clean source, tests, benchmark reports, artifacts, and
  implementation facts;
- `human` / 人: issues, PRs, handoffs, workflow, agent decisions, and current
  task routes;
- `heaven` / 天: roadmap, discussions, product claims, public positioning, and
  long-horizon purpose.

The helper may infer or accept an active layer, rank route candidates by that
layer, and consume perturbation-amplitude packets to choose narrow, medium, or
broad fanout. Large shifts request stale/conflict checks; inversion requests
source reopen or conflict review before high-risk action or public claims.

Three Powers facets do not replace hard masks, router heads, action grammar, or
source-backed authority. They are route metadata and diagnostics only. Layer
disagreements such as `earth_supports_but_heaven_not_ready` or
`heaven_direction_clear_but_earth_evidence_missing` may guide the next reopen
path, but they cannot promote a weak macro orientation into fact.

`aippocampus_runtime.macro.stage_tracker` uses the same boundary for project
stage updates. King Wen adjacency can classify source-backed project movement
as advanced, stalled, reversed, jumped, or forked, but source events decide the
movement. Unpromoted Journey/thread arcs cannot move project stage, and stale
or contradictory later source degrades a stage packet back to recheck
diagnostics.

`aippocampus_runtime.macro.momentum` adds the twelve-phase momentum signal for
macro orientation. It compresses existing source-backed deltas such as
`support_delta`, `counter_evidence_delta`, `route_success_delta`,
`staleness_delta`, and `user_correction_delta` into a navigation-only phase and
direction. Momentum answers whether the route is rising, peaking, declining,
turning, or hibernating; perturbation amplitude still answers how large the
orientation shift is. The two signals should stay orthogonal: momentum may add
recheck triggers or compact packet text, but it cannot widen fanout, support a
fact claim, or replace reopened source.

`aippocampus_runtime.macro.line_topology` adds diagnostic-only six-line
topology for macro orientation. It uses one explicit fixture mapping from
bottom-to-top lines into earth/human/heaven axes, then reports adjacent
`乘` / `承` / `比` / `不比` structure and cross-line `应` couplings such as
earth-human, earth-heaven, and human-heaven. This is an attention-dependency
analogy: topology may explain why a route fanout was widened or why a
cross-layer pair was flagged, but it must not become evidence, ranking weight,
or source support. Perturbation chooses where to look; reopened source decides
what happened.

`aippocampus_runtime.navigation.macro_router_interface` owns the explicit
bidirectional contract between Macro Orientation and the router. Macro state may
project a `macro_router_context` as navigation priors: active layer,
perturbation band, momentum direction, and recheck triggers. Router output may
project a `router_macro_observation` with layer distribution, source refs, and
source-backed delta signals for a later integration worker or macro-state
rebuild. The asymmetry is mandatory: hard masks run before any macro bias, and a
single hot-router result must not mutate project-level macro state.

## Relationship To Other Contracts

- The stable action grammar lives in
  [`../agent-context.md`](../agent-context.md) and
  [`../../skills/aippocampus/references/ambient-hooks.md`](../../skills/aippocampus/references/ambient-hooks.md).
- The agent-native recall/deepen/explain facade is the small foreground
  projection over route packets; see
  [`agent-native-recall-facade.md`](agent-native-recall-facade.md).
- Packet topology diagnostics can name post-packet relation failures such as
  navigation-as-claim, missing-middle, and route-cycle shapes; see
  [`packet-topology-diagnostics.md`](packet-topology-diagnostics.md). They do
  not change router weights or route-packet authority.
- The Memory Evidence Drawer explains surfaced recall routes without becoming a
  truth layer; see [`memory-evidence-drawer.md`](memory-evidence-drawer.md).
- The Source-Backed Familiarity Map is the current cold-sidecar owner; see
  [`source-backed-familiarity-map.md`](source-backed-familiarity-map.md).
- Hierarchical route tokens provide the source span / event / episode input
  shape for future router heads.
- The deterministic hot router is the V0 scoring prototype over route tokens;
  it uses `calibrated_rule_grid_v1` by default for route-token score fusion,
  but it does not replace recall/search paths or enable foreground hooks by
  default.
- Semantic warming can produce router-consumable route material only after it
  has been materialized in the background/cache path; the hot router consumes
  route features, not fresh semantic model output.
- Action-time features add pending-tool context to the query surface, but they
  do not mutate hooks, settings, or live foreground behavior by default.
- Evidence packaging can narrow a source window to source-span handles, but it
  does not retire exact-line retrieval quality work or make source-window
  evidence equivalent to final citations.
- Source-open and high-risk claim gates remain separate answer-time authority
  checks; see [`high-risk-answer-gates.md`](high-risk-answer-gates.md).

## Cannot Claim

This contract does not prove broad attention-router quality, private-history
behavior, live foreground usefulness, production score-fusion calibration,
model training, default foreground-hook adoption, or summary text as
source-backed evidence.
