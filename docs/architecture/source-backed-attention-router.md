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
- `scope_head`
- `salience_head`
- `currentness_head`
- `conflict_head`
- `risk_head`
- `abstention_head`

The adaptive threshold is a local deterministic gate over risk, conflict,
currentness, salience, and scope. It is not calibrated model attention and must
not be treated as learned score fusion. Masked candidates may retain high
diagnostic scores, but they still emit `silence`.

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

## Relationship To Other Contracts

- The stable action grammar lives in
  [`../agent-context.md`](../agent-context.md) and
  [`../../skills/aippocampus/references/ambient-hooks.md`](../../skills/aippocampus/references/ambient-hooks.md).
- The Memory Evidence Drawer explains surfaced recall routes without becoming a
  truth layer; see [`memory-evidence-drawer.md`](memory-evidence-drawer.md).
- The Source-Backed Familiarity Map is the current cold-sidecar owner; see
  [`source-backed-familiarity-map.md`](source-backed-familiarity-map.md).
- Hierarchical route tokens provide the source span / event / episode input
  shape for future router heads.
- The deterministic hot router is the V0 scoring prototype over route tokens;
  it does not replace recall/search paths by default.
- Action-time features add pending-tool context to the query surface, but they
  do not mutate hooks, settings, or live foreground behavior by default.
- Evidence packaging can narrow a source window to source-span handles, but it
  does not retire exact-line retrieval quality work or make source-window
  evidence equivalent to final citations.
- Source-open and high-risk claim gates remain separate answer-time authority
  checks; see [`high-risk-answer-gates.md`](high-risk-answer-gates.md).

## Cannot Claim

This contract does not prove broad attention-router quality, private-history
behavior, live foreground usefulness, score-fusion calibration, model training,
default router adoption, or summary text as source-backed evidence.
