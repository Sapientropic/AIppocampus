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
- `head_votes`
- `masks_applied`
- `contract`

`source_handles` are reopen handles, not claims. They may carry stable source
ids, segment ids, turn ranges, and `reopen_required`. They must not carry raw
private text in public reports.

`head_votes` explain why the route was considered. They may include head name,
score, and reason code. They do not become evidence.

## Output Levels

The router maps to the existing action grammar instead of adding a new authority
taxonomy:

| Output mode | Action grammar | Claim permission |
| --- | --- | --- |
| `silence` | `ignore_or_blocked` | `blocked` |
| `direction_only` | `direction_only` | `no_claim_before_reopen` |
| `reopenable_route` | `reopenable_route` | `no_claim_before_reopen` |
| `bounded_evidence` | `bounded_evidence` | `bounded_claim_allowed` |

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

`build_contract_fixture_report()` covers four contract cases:

- high lexical/semantic relevance blocked by `privacy_domain`;
- a source-backed `reopenable_route`;
- source-open bounded evidence;
- source-thin `direction_only` scent.

The fixture reports:

- `masked_source_resurrection_count`;
- `source_backed_claim_without_reopen`;
- public-safe privacy boundaries;
- cannot-claim entries for broad router quality, private-history behavior,
  model training, route packets as source truth, and default foreground
  adoption.

## Relationship To Other Contracts

- The stable action grammar lives in
  [`../agent-context.md`](../agent-context.md) and
  [`../../skills/aippocampus/references/ambient-hooks.md`](../../skills/aippocampus/references/ambient-hooks.md).
- The Memory Evidence Drawer explains surfaced recall routes without becoming a
  truth layer; see [`memory-evidence-drawer.md`](memory-evidence-drawer.md).
- Source-open and high-risk claim gates remain separate answer-time authority
  checks; see [`high-risk-answer-gates.md`](high-risk-answer-gates.md).

## Cannot Claim

This contract does not prove broad attention-router quality, private-history
behavior, live foreground usefulness, score-fusion calibration, model training,
or default router adoption.
