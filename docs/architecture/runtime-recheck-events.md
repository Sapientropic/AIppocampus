# Runtime Recheck Events

Role: current contract.

`runtime_recheck_event` is the shared low-authority event shape for runtime
surfaces that need a later review without mutating source truth. It is a
navigation diagnostic, not a memory fact, task, claim, or foreground answer.

The runtime owner is
`aippocampus_runtime.runtime_recheck_events`. Producers may build events through
`build_runtime_recheck_event`; continuity-domain snapshots may project lifecycle
pressure through `runtime_recheck_events_from_continuity_domains_snapshot`;
adjudicated Dream findings may project macro review pressure through
`runtime_recheck_event_from_dream_finding`.
Source-shape descriptor construction and active-recall priority adaptation are
owned by `aippocampus_runtime.source_shape`; see
`docs/architecture/source-shape-runtime-spine.md`.

## Shape

Every event carries:

- `kind = runtime_recheck_event`
- `event_id` and `dedupe_key`
- `producer`
- `reason_code` and `reason_family`
- `source_refs`
- `source_shape_id`
- `scope`
- `authority_level = direction_only`
- `claim_permission = none`
- `degrade_to`
- `target_surfaces`
- `created_at`
- `consumer_policy`

`event_id` and `dedupe_key` are stable for the producer, reason, source shape,
scope, and safe source refs. Consumers may use them to collapse duplicate or
superseded pressure, but they must not use event freshness as evidence that a
claim is true.

Known first reason codes include:

- `semantic_invalidation`
- `dream_macro_recheck`
- `dream_obstruction_recheck`
- `dream_compensatory_probe_accepted`
- `dream_shadow_route_reopen`
- `dream_cut_point_stage_review`
- `avatar_shadowed`
- `decision_shadow_reopen`
- `local_global_obstruction`
- `parallel_derivation_tension`
- `continuity_domain_conflict_recheck`
- `continuity_domain_currentness_recheck`
- `continuity_domain_boundary_constraint`
- `continuity_domain_route_unavailable`

## Consumer Policy

Consumers may:

- route an event into a macro recheck queue;
- seed backstage Dream/subconscious candidate generation;
- raise active-recall priority for source reopen;
- expose aggregate debug counts or sanitized diagnostics.

Consumers must not:

- mutate clean source, continuity domains, or source truth from the event;
- raise authority above `direction_only`;
- grant foreground eligibility or claim permission;
- emit a factual foreground answer from event fields;
- bypass source reopen or adjudication when a stronger claim is needed.

## Continuity-Domain Bridge

Continuity-domain lifecycle and evidence-trail pressure may be projected into
runtime recheck events:

- contested, counter, or correction-heavy domains produce conflict recheck
  diagnostics;
- stale or superseded domains produce currentness recheck diagnostics;
- pinned boundaries produce restriction diagnostics and Dream seed constraints;
- blocked or retired domains produce route-unavailable diagnostics.

The bridge intentionally carries refs and compact scope only. Domain titles,
working summaries, and conclusions do not become event evidence. Active recall,
macro, and Dream consumers should treat the bridge as "reopen this route before
using it", not as a claim about the underlying source.

## Dream-To-Macro Bridge

Accepted/adjudicated Dream findings may ask Macro/Yi consumers to recheck
stage, topology, source-shape, or timing diagnostics. They do this by emitting a
`runtime_recheck_event` targeted at `macro_recheck`, not by mutating hexagram,
momentum, three-powers, stage-tracker state, or source truth.

Non-adjudicated or source-free Dream rows must return a rejection diagnostic
instead of an event. Macro consumers may adapt an event into a sanitized
`macro_recheck_review_input`, but the review input has `write_effect = none`,
`fact_claim_allowed = false`, and still requires source reopen before any
claim.

## Issue Boundary

This contract implements the shared event shape requested by #1421 and the
continuity-domain lifecycle bridge requested by #1434. It plugs into the
source-shape runtime spine tracked by #1417, the Dream/Macro recheck bridge
tracked by #1412/#1416, and the opt-in continuity production work from
#1432/#1435 without duplicating those broader designs.
