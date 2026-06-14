# Parallel Derivation Compatibility

Role: current contract.

Parallel derivation compatibility is the runtime contract for checking
macro-derived navigation signals before route, fanout, or foreground surfaces
flatten them into ordinary affordances. It is deliberately narrow: it reports
whether a set of already-produced derivations share enough source basis,
dependency order, and cross-layer agreement to be used as route pressure. It is
not a scorer, source oracle, or claim authority.

Runtime owner:

- `aippocampus_runtime.navigation.parallel_derivation_bundle`
- Downstream consumers:
  - `aippocampus_runtime.macro.three_powers`
  - `aippocampus_runtime.navigation.navigation_potential`
  - `aippocampus_runtime.navigation.macro_router_interface`
  - `aippocampus_runtime.source_shape`
- Tests: `tests/aippocampus/test_parallel_derivation_bundle.py`

## Bundle API

`build_parallel_derivation_bundle(...)` accepts public-safe derivation rows and
returns a `parallel_derivation_bundle` with:

- normalized derivation ids, kinds, shapes, source families, source refs, and
  prerequisite derivation ids.
- `source_basis`: per-derivation source handles plus shared, partial, no-overlap,
  or missing classification.
- `dependency_dag`: dependency edges, topological order, missing prerequisites,
  cycle diagnostics, and input-order repair markers.
- `compatibility`: status, severity, reason codes, degrade target, and
  projection permission.
- `source_shape_descriptor`: the shared source-shape descriptor for downstream
  active-recall and explain/deepen surfaces.

Inputs are source handles, shape summaries, and derivation metadata. Shared
vocabulary, matching macro coordinates, or equal symbolic labels do not count
as source support.

## Source Basis

Source basis alignment has four states:

| State | Meaning | Route consequence |
| --- | --- | --- |
| `shared` | Every derivation has refs and all share at least one source key. | Compatible unless another guard finds tension. |
| `partial_overlap` | Some derivations share source keys but not all derivations are covered by the same source set. | Tension; recheck or narrow before broad fanout. |
| `no_overlap` | Derivations have refs, but no source keys overlap. | Obstruction; reopen/review source before route use. |
| `missing` | No usable source basis exists. | Diagnostic-only or obstruction depending on the consumer. |

The alignment is about source reachability, not factual correctness. A shared
source basis only means the derivations can be compared against a common source
trail; it does not let the bundle state source facts.

## Dependency DAG

Derivations may declare `prerequisite_derivation_ids`. The bundle records the
dependency graph before downstream projection so consumers can see when:

- prerequisites are missing.
- derivations form a cycle.
- input order was repaired by topological sorting.

Missing or cyclic dependencies block flattening. Repaired order is tension, not
failure: consumers may continue only after surfacing that the snapshot was
reordered for fidelity.

## Compatibility Status

Compatibility status is navigation-only:

| Status | Meaning | `degrade_to` |
| --- | --- | --- |
| `compatible` | Source basis and dependencies are usable and no cross-layer tension was detected. | `reopenable_route` |
| `tension` | The derivations may be useful, but broad route/fanout projection should be narrowed or rechecked. | `recheck_or_narrow` |
| `obstruction` | Source basis, dependency, or cross-layer conflict blocks flattening. | `source_reopen_review` |
| `incomplete` | Compatibility diagnostics were not computed or are unavailable. | `diagnostic_only` |

The contract intentionally keeps `authority_level = navigation_only`,
`claim_permission = none`, and `fact_claim_allowed = false` for every status.
Downstream ranking cannot promote a bundle into evidence or factual authority.

## Cross-Derivation Fixtures

The current fixture set protects the #1316 compatibility cases:

- rising momentum plus collapsing or blocked shadow route:
  `latent_route_conflict`.
- large perturbation plus narrow Three Powers active axis: `fanout_tension`.
- clear heaven direction plus missing earth evidence: `interlayer_obstruction`.
- same transform orbit across divergent source families:
  `same_structure_different_source_family`.
- stage reversal or fork against rising momentum or large perturbation:
  `stage_movement_conflict`.

These names are stable diagnostic reason codes. They are not a promise that the
runtime has interpreted the source text; they point the next agent toward the
source trail that needs reopening.

## Pre-Flattening Gate

`preflattening_gate_for_route_affordance(bundle)` is the consumer-facing gate.
It should run before route affordances, fanout candidates, or macro-router
context flatten a bundle into ordinary navigation output.

Gate behavior:

- `compatible`: allow ordinary navigation projection.
- `tension`: block broad flattening; consumers may narrow to a small recheck
  surface or ask for source review.
- `obstruction` / `incomplete`: block flattening and require source reopen,
  review, or rebuilding the bundle.

`three_powers` uses the gate to reduce candidate fanout to zero for obstruction
and to one candidate for tension. `navigation_potential` turns blocked bundles
into recheck preconditions instead of offer-next-step affordances.
`macro_router_interface` adds compact recheck triggers for the router context.

## Source-Shape Link

The bundle builds a `source_shape_descriptor` so the shared source-shape spine
can route recheck pressure into active recall or explain/deepen surfaces. The
descriptor inherits the same source refs, dependency DAG, compatibility status,
temporal fields, and projection guard. It does not create a new routing layer;
it is the common diagnostic envelope for consumers that already understand
source-shape descriptors.

## Boundary

Parallel compatibility should be used when multiple derived navigation shapes
are about to influence route selection, foreground offer wording, or fanout
width. It is unnecessary for a single already-source-open factual answer, and
it must not be used as a substitute for reopening source when exact wording,
public claims, privacy-sensitive history, or disputed currentness matters.
