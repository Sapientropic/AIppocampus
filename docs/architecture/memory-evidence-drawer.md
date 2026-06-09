# Memory Evidence Drawer

Role: current contract.

The Memory Evidence Drawer is a foreground explanation packet for recall
surfaces. It explains why something surfaced, where the route points, what
authority it has, and what the agent or user can do next. It is not a new truth
layer, dashboard, scorer, or memory writer.

The runtime owner is
`aippocampus_runtime.recall.evidence_drawer`. The first slice is pure and
no-write: it projects existing ambient cards, Active Path Packet paths,
`recall_context`-style route rows, and bounded evidence contexts into a compact
JSON/dataclass shape.

## Contract Shape

A drawer packet has:

- `kind="aippocampus_memory_evidence_drawer"`
- `schema_version=1`
- `items`: compact drawer rows
- `privacy_boundary`: no raw prompts, raw source text, source windows, local
  paths, or secret values
- `source_boundary`: drawer explains recall, but clean source remains authority
- `affordance_contract`: suppress, correct, pin, and deepen are declared as
  user/agent affordances
- `cannot_claim`: packet-level anti-overclaim rules

Each item has:

- `why_this_surfaced`
- `source_refs`
- `reopen_plan`
- `action_grammar`
- `trust_level`
- `authority_label`
- `route_strength`
- `navigation_only`
- `can_support_factual_claim`
- `exact_claim_requires_source_reopen`
- `abstention_reason`
- `affordances`
- `source_boundary`
- `cannot_claim`

The drawer reuses the existing action grammar from `recall.authority`:
`direction_only`, `direction_with_ref`, `reopenable_route`,
`bounded_evidence`, `source_open`, and `ignore_or_blocked`. Do not add a second
authority taxonomy or treat route strength as truth.

## Authority Boundary

The drawer is lower authority than reopened source. It may tell a foreground
agent:

- this is only navigation;
- this source route is ready to reopen;
- this bounded evidence can support the current answer within scope;
- this source-open item can support exact wording inside redaction boundaries;
- this route is blocked or insufficient, so abstain or report the boundary.

It must not let navigation-only cues masquerade as factual evidence. Candidate
refs, semantic hints, continuity-domain pointers, and active-path routes can
justify source reopen or route choice, but they cannot support factual claims
without source reopen.

Bounded evidence is usable only inside its declared scope. Exact quotes,
sensitive facts, stale/currentness questions, conflicts, broader context, and
high-risk actions still go through source-court/source-open behavior.

## Affordance Boundary

The first drawer slice declares affordances; it does not implement a complete
interactive state machine.

- `suppress`: hide or ignore this route/card for the current foreground use.
- `correct`: route an explicit correction back to source-backed memory.
- `pin`: promote a source-trailed route or boundary, not drawer prose.
- `deepen`: call `recall_deepen`, `get_turn_context`, or another source reopen
  path before stronger claims.

Future suppress/correct/pin writes must preserve source refs, redaction, and
append-only or auditable mutation rules. A drawer click must not silently edit
clean source, registry rows, or private history.

## Privacy Boundary

The default drawer is ids-only. It must not serialize raw prompt text, raw
source windows, source snippets, local machine paths, credentials, or full
private-history text. If a host wants to show raw evidence, it must use an
explicit source-open/reopen surface whose scope and redaction boundary are
visible.

## Non-Goals

- No heavy dashboard in this slice.
- No hook-wide large drawer payload by default.
- No new retrieval, ranking, or attribution layer.
- No confidence-as-authority behavior.
- No broad claim that the drawer proves recall quality, answer quality, or live
  foreground lift.
