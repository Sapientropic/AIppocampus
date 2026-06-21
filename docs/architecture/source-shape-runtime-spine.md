# Source-Shape Runtime Spine

Role: current contract.

The source-shape runtime spine is the small shared contract for turning
producer-owned diagnostics into navigation-only route pressure. It connects
parallel derivation bundles, local/global compatibility, Dream/Macro recheck,
avatar or familiarity posture, and active recall without creating a second
recall pipeline or a new source of truth.

Runtime owner:

- `aippocampus_runtime.source_shape`
- APW adapter: `aippocampus_runtime.recall.associative_path_source_shape`
- Producer contract: `docs/architecture/parallel-derivation-compatibility.md`
- Tests: `tests/aippocampus/test_source_shape_runtime.py` and the source-shape
  fixture in `tests/aippocampus/test_active_recall.py`

## Runtime API

`build_source_shape_descriptor(...)` builds a `source_shape_descriptor` from
safe source refs, source-snapshot ids, optional derivation summaries,
compatibility diagnostics, temporal semantics, guard inputs, and producer
signals.

Callers must be able to read `descriptor_state`:

- `complete`: source refs, required time semantics, compatible derivation, and
  projection policy passed.
- `incomplete`: a source-backed route exists, but freshness, authority,
  compatibility, derivation, or time semantics require reopen/recheck first.
- `diagnostic_only`: privacy/source availability blocks ordinary projection.

`project_source_shape_for_foreground(...)` returns the default compact
foreground projection. It may carry route posture, source-ref count,
`risk_flags`, `triage_rank_reason_codes`, and a source-reopen instruction. It
does not expose guard internals, raw diagnostics, Dream text, avatar internals,
macro state, local paths, or private source text.

`explain_source_shape_descriptor(...)` returns the public-safe explain/deepen
surface with guard diagnostics, temporal semantics, derivation summary, and
safe source refs. This is where omitted reason codes are recovered.

`source_shape_active_recall_priorities(...)` and
`apply_source_shape_priority_to_active_recall_context(...)` adapt
`source_shape_descriptor` and `runtime_recheck_event` rows into active-recall
priority input. They may reorder or front-load source reopen routes and add
navigation-only risk flags. They cannot raise authority or grant claim
permission.

## Invocation Modes

Foreground recall may consume compact projection only. It can use source-shape
pressure to decide what to reopen first, not what to say as fact.

Associative Path Walker consumes this spine through its recall fallback adapter.
Current recall posture is `semi_default_recovery`: APW can add one secondary
source-reopen action for weak or silent recall when APW candidate sidecars are
present, but it cannot change ordinary recall ranking or raise claim authority.
`docs/architecture/recall/source-backed-product-discipline.md` owns the product
promotion boundary and rollback mode.

Explicit explain/deepen may inspect diagnostics and temporal semantics, then
reopen source or run the relevant producer again.

Background Dream, Macro, or compatibility workers may emit descriptors or
`runtime_recheck_event` rows as backstage candidates. They remain
direction-only until source is reopened or a stronger source-backed packet is
built by an existing owner.

Tests and fixtures may build descriptors directly from synthetic refs. This is
the supported fixture path; direct module outputs from Dream, Macro, avatar, or
compatibility code are not automatically projection-ready source-shape output.

## Temporal Semantics

A descriptor separates these fields:

- `source_coverage_time`: source event/window coverage. A Section local
  `section_time_window` maps here; the spine does not create a competing local
  time model.
- `materialized_at`: when the producer extracted or materialized the artifact.
- `built_at`: when the descriptor was built.
- `valid_after`, `valid_until`, `review_after`: validity or review windows.
- `topic_epoch`, `source_epoch`, `invalidation_epoch`: epoch comparison fields.
- `invalidation_reasons`, `recheck_on`: signals that can request reopen/recheck.

Missing coverage time degrades to reopen/diagnostic behavior. Calendar age
alone is not semantic staleness. Epoch mismatch, explicit invalidation, stale
currentness, conflicts, or missing time can request source reopen; privacy and
missing refs can block projection.

## Guard Order

Guards run in this order, and earlier blocking or degrading guards win:

1. Privacy / blocked boundary.
2. Source availability and source refs.
3. Freshness / invalidation / recheck triggers.
4. Authority and claim permission.
5. Local/global compatibility.
6. Parallel derivation compatibility / source-shape completeness.
7. Route/avatar/Dream projection permission.
8. Ranking, delivery, or foreground formatting.

Later projection, ranking, or formatting cannot raise a descriptor above
`authority_level = direction_only` or `claim_permission = none`. Diagnostics
remain inspectable through explain/deepen even when foreground receives only a
compact posture.

## Foreground Boundary

Default foreground projection is intentionally tiny:

- `source_shape_id`
- `route_posture`: `active`, `shadowed`, or `blocked`
- `action_grammar`: `reopenable_route`, `direction_with_ref`, or
  `ignore_or_blocked`
- `source_ref_count`
- `risk_flags`
- `triage_rank_reason_codes`
- `recommended_next`
- `source_reopen_required_before_claim`

Debug-only or explain/deepen-only fields include guard diagnostics, temporal
internals, derivation summaries, compatibility detail, Dream hypotheses,
avatar posture detail, Macro state, raw source snippets, and local paths.

Blocked, stale, private, or incomplete descriptors must not produce an active
foreground posture or route claim. At most they produce shadow/blocked reopen
guidance.

## Runtime Terms

Use engineering terms in code, tests, public contracts, and foreground packets:

| Term | Meaning |
| --- | --- |
| `source_shape_descriptor` | Normalized navigation-only descriptor built by the runtime spine. |
| `source_snapshot` | Safe ids, epochs, and coverage handles for the source basis. |
| `derivation_dag` | Producer-owned derivation structure summarized by presence/counts here. |
| `compatibility_diagnostic` | Guard result that may block or degrade projection. |
| `invalidation_reason` | Freshness/currentness signal requesting reopen or recheck. |
| `projection_allowed` | Whether compact route guidance may be projected after all guards. |
| `degrade_to` | Lower-authority surface for blocked or suspect descriptors. |
| `runtime_recheck_event` | Direction-only event that asks consumers to reopen or recheck source. |

Design vocabulary from Dream/Yi/avatar discussions remains useful source
context, but ordinary runtime packets should lead with these engineering terms
and keep symbolic vocabulary in design/debug material only.
