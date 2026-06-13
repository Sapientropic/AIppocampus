# Local/Global Compatibility

Role: current contract.

Local/global compatibility asks whether packet-shaped local sections can be
viewed together as a route, partial route, obstruction, or blocked boundary
without raising authority. It is an explain/deepen/Campus diagnostic surface,
not a source of facts, ranking weights, or default foreground prose.

Runtime owners:

- `aippocampus_runtime.navigation.local_global_compatibility`
- `aippocampus_runtime.navigation.local_global_sections`
- Fixture catalog: `aippocampus_runtime.navigation.local_global_fixture_catalog`
- Tests: `tests/aippocampus/test_local_global_compatibility.py`

## Section Contract

A typed Section is the small shared object language for MemoryPacket, Macro,
Dream, Telepathy, AIppo, topology, and route-shaped inputs. The runtime exposes
the contract as `section_contracts` on compatibility rows.

Minimum fields:

- `section_id`
- `section_kind`
- `scope`
- `restriction_path`
- `time_semantics`
- `privacy_domain`
- `authority_level`
- `claim_permission`
- `source_count`

The contract is intentionally public-safe. It carries ids, source-handle
counts, and diagnostic labels, not raw private text, chain-of-thought, local
paths, or raw private source handles.

## Restriction

Restriction narrows a Section for review. Supported V0 shapes include:

- project -> thread family -> thread.
- cluster -> agent.
- broad source epoch -> narrower source coverage window.
- authority / claim-permission downgrade.

Restriction is transitive and order-preserving. It may never raise authority,
claim permission, privacy access, source support, or source truth.

`partial_glue` can now report a broad obstruction plus a narrowed
`glued_route`, for example when two sections do not share the broad scope but
do share a source-backed thread-family restriction. If no safe common
restriction exists, the result remains `obstruction`.

Privacy, missing-source, stale, and blocked-boundary cases are not made usable
by narrowing. Shared vocabulary alone still does not count as overlap.

## Time Semantics

Time fields are separated:

- `source_coverage_time`: the source event/window covered by the Section.
- `packet_created_at`: when the packet or diagnostic was materialized.
- `validity_window`: `valid_after`, `valid_until`, and `review_after`.

Matching source handles and scopes do not glue when source coverage windows are
incompatible. Creation time does not replace source coverage time, and review
windows do not make stale source current.

## Obstruction Cause

Topology `shape` and glue failure `obstruction_kind` are separate axes.

Example shapes include `cycle`, `cut_point`, `weak_bridge`, `knot`, and
`island`. Example obstruction causes include `missing_middle`, `conflict`,
`stale_boundary`, `privacy_boundary`, `agent_scope_split`, and
`time_window_mismatch`.

A `cut_point` can be stale in one case and a missing middle in another. The
runtime must not hard-code shape -> cause as a fixed mapping.

## Adjudicated Metrics

The report includes an adjudication schema for:

- `useful_obstruction_later_used_count`
- `false_glue_regression_count`
- `no_help_count`
- `ambiguous_correlation_only_count`

These are offline/shadow review metrics. They are not live attribution, and
diagnostic counts are not product-lift claims. A false glue is a compatibility
result later overturned by source review, not merely an unused route.

## Shi/Ying Decision

V0 keeps Shi/Ying as `v0_project_scoped_navigation_hint`.

Current runtime may emit a restriction edge when project-scoped Macro or
Telepathy packets contain Shi/Ying relation-position hints. Classical bagua
position tables are out of runtime scope until a concrete usefulness case and
tests justify them.

Shi/Ying restriction edges remain navigation-only. They cannot infer agent
identity, user intent, personality, fate, source truth, or claim readiness.

## Boundary

This contract supports a narrow claim:

```text
AIppocampus has deterministic local/global compatibility diagnostics with typed
Section, restriction narrowing, source/time boundaries, obstruction-cause
separation, and adjudicated metric scaffolding.
```

It does not prove live usefulness, route quality, Dream truth, Macro truth,
mathematical sheaf correctness, or foreground actionability.
