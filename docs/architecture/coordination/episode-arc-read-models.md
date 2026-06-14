# Episode/Arc Read Models

Role: active design.

Status: deterministic coding slices implemented in
`aippocampus_runtime/coding/episode_arcs.py` and
`aippocampus_runtime/coding/sequence_reopen.py`; aggregate private-history
adjudication is implemented in
`aippocampus_runtime/coding/episode_arc_private_adjudication.py`; public
gappy-chain fixture calibration is exposed by
`build_public_gappy_chain_calibration_report()`. The public route-producer
fixture is exposed by
`aippocampus_runtime.coding.episode_arc_route_producer`. Broader Episode/Arc
coverage remains an active owner track and should not be claimed complete from
these slices alone.

Episode/Arc read-models preserve ordered local causality that is easy to lose
in flattened memory: tried route, failed check, user correction, accepted
workaround, supersession, or temporary concern extinction. They are source
navigation and host-agent caution surfaces, not a new ground-truth memory layer.

## Layer Boundaries

| Layer | Owns | Must not claim |
| --- | --- | --- |
| Event lane | Clean-source messages, behavior events, coding decision events, and operation-integrity rows. | Ordered causal meaning beyond the row's own source event. |
| Episode/Arc read-model | Ordered source-event chain, source refs, causal edges, gaps, and read-time reopen plan. | Current validity, user traits, emotions, or formal memory promotion. |
| Sequence packet | Host-facing `aippocampus_sequence_packet` with timeline, current assessment, and `cannot_claim`. | That an old route is still rejected without reopening source. |
| Journey | Long-running multi-thread narrative/waypoint context. | Ordinary task interactions becoming Journey by default. |
| Repo familiarity | Code navigation, module familiarity, and source-backed repo wayfinding. | User intent, rejected-route validity, or behavior evidence. |
| Host ticket | Action-time reminder, warning, ask, or source-refresh request. | Evidence itself; tickets must point back to source routes. |

## Schema Contract

`aippocampus_episode_arc_read_model` rows use
`schema_version: aippocampus.episode_arc_read_model.v1` and include:

- `episode_kind`: narrow arc type such as `rejected_route_arc`,
  `correction_arc`, `supersession_arc`, `temporary_concern_arc`, or
  `tacit_constraint_arc`.
- `source_event_ids`: ordered ids of the underlying source/event rows.
- `source_refs` and `source_ref_hashes`: reopenable source handles and
  public-safe hashes; raw source text is not stored in the arc.
- `turn_range`: first/last turn and source-line hints for reopening the local
  window.
- `affected_scope`: files, modules, or symbols from the event rows, when known.
- `event_order` and `causal_edges`: ordered event kinds and deterministic
  adjacent relations.
- `outcome`: local arc outcome such as `route_rejected`, `needs_reopen`,
  `superseded`, or `constraint_not_current`.
- `current_validity`: read-model weather such as `needs_reopen`,
  `superseded`, or `local_only`; never a current fact claim.
- `truth_status`: always
  `source_backed_chain_not_current_validity_fact`.
- `sequence_gaps`: missing middle event, semantic order mismatch, single-point
  trap, or other reasons the foreground agent must ask or refresh sources.

`render_sequence_packet()` projects an arc into
`kind: aippocampus_sequence_packet` with ordered `timeline`,
`current_assessment`, and `cannot_claim`. Thin or gappy chains may only propose
`ask`/`refresh_sources` style use. Visible reminders require enough ordered
source thickness and still carry `current_validity_requires_source_reopen`.

`build_reopen_plan()` returns a source-window navigation plan from a full
Episode/Arc row: source event ids, source refs, source hashes, turn range, safe
uses, and `cannot_claim`. `build_sequence_packet_reopen_plan()` handles the
host-facing packet case: it resolves packet timeline event ids / source-ref
hashes through a caller-provided clean source-ref catalog. If the catalog is
missing or incomplete, the plan degrades to `ask` / `refresh_sources` and marks
`source_catalog_required_for_reopen`. Both plans are routes back to source, not
evidence that the route remains valid.

## Deterministic Slice

The implemented coding slice accepts event rows with `episode_id`/`arc_id`/
`sequence_id`, `event_id`, `event_kind` or `event_type`, `source_refs`,
turn/source-line hints, optional `sequence_index`, and optional
`affected_scope`. It groups rows, preserves explicit sequence order when
provided, otherwise preserves input order, and marks wrong-order or thin chains
as gappy instead of silently repairing them.

The adapter path is intentionally small and deterministic. Existing behavior
rows such as `tool_call_observed` with a failed test/check exit become
`failed_check`; generic failed tool rows become `tool_failure`; coding
`decision_event` rows can contribute `rejected_route`, `user_correction`, or
`accepted_decision` steps without becoming source truth. Mixed behavior and
decision rows may form one arc, but the output remains a read-model and still
requires source reopen before foreground action.

Current deterministic arc profiles cover:

- rejected route: `attempted_route -> failed_check/tool_failure ->
  route_rejected`
- correction: `user_correction -> accepted_workaround/accepted_decision ->
  source_reopen`
- supersession: `old_rule -> new_rule/superseded_by ->
  current_rule_selected`
- temporary concern extinction: `temporary_concern ->
  later_normal_progress`

Negative controls are intentional product behavior. The same event set in the
wrong order becomes `event_order_semantic_mismatch`; a single source hint
becomes `single_point_trap`; a chain missing an expected middle event becomes
`missing_middle_event`; a temporary concern followed by later normal progress
becomes `temporary_concern_arc` / `local_only`, not a current constraint. These
cases should navigate the agent back to source, not make it warn or block from
the derived arc alone.

`build_public_gappy_chain_calibration_report()` is the public reproducible #663
fixture surface for these negative controls. It accepts public-safe synthetic
event rows, builds arcs, projects sequence packets / reopen plans, and reports
`complete_arc_count`, `gappy_arc_count`, gap buckets, reopen-only counts,
`single_point_overclaim_rate`, and `needs_reopen_projection_rate`. The report
serializes case ids, event-kind order, gap labels, source-ref hash counts, and
safe-use projections only. It must not serialize raw source text, source refs,
event ids, thread ids, registry paths, or local machine paths. This is a
selected deterministic fixture, not live behavior evidence or a broad public
corpus.

`episode_arc_route_producer.build_public_episode_arc_route_producer_report()`
adds the #1362/#1363 public route-producer slice. It runs a small public
VCS/hard-event-style cohort over commit revert, PR rejection/merge, issue
reopen, patch supersession, workaround removal, missing-middle, and wrong-order
families. The report proves the intended live-recall route shape without
adopting it by default: complete rejected-route chains may produce compact
`prevent_repeated_wrong_route` guidance, unresolved frontiers become
`reopenable_route`, and gappy/wrong-order chains degrade to refresh-source
guidance. The report serializes family names, event-kind order, gap labels,
source-ref hash counts, and aggregate metrics only; it does not serialize raw
source text, source refs, event ids, thread ids, registry paths, or local paths.
This closes the public deterministic route-producer/evidence slice and the
bounded #663 owner track, not live host behavior lift or default route-producer
adoption.

`benchmark_episode_arc_sequence_usefulness.py` adds the #1440 sequence
usefulness workload. It reuses the same public route-producer cases and compares
`baseline_no_episode_arc` against `episode_arc_route_packet` under the same
source-ref-hash budget. The dated 2026-06-14 report shows treatment wins for
repeated wrong-route avoidance, frontier/source reopen, and patch supersession
with no wrong-project contamination or source-truth overclaim. This upgrades the
public evidence from route shape to selected sequence usefulness, but it still
does not prove live host behavior lift, private-history generality, or default
route-producer adoption.

The sequence-packet reopen helper is intentionally stricter than the arc
builder. A packet cannot reopen source by itself because it only carries compact
timeline handles and hashes. The helper needs a clean source-ref catalog from
the caller and reports `complete`, `partial`, `unresolved`, or
`invalid_packet`. Complete resolution may allow a visible reminder after source
reopen; gappy, partial, unresolved, or invalid packets may only ask or refresh
sources. Raw source text is never serialized in this public-safe route plan.

The aggregate private-history adjudication helper is an owner diagnostic for
#663. `aippocampus episode-arcs --json` scans local registry clean-source
messages/events, extracts source-backed coding decision candidates, pairs
rejected-route decisions with nearby failed behavior events when available, and
reports only aggregate counts and buckets. It does not serialize raw source
text, raw command text, source refs, source-ref hash samples, event ids, thread
ids, local paths, or registry paths. The first dated evidence slice is
`docs/evidence/reports/episode-arc-private-history-adjudication-2026-06-08.md`.

## Cannot Claim

This slice cannot claim:

- live private-history behavior lift;
- private-history generality beyond the aggregate cohort;
- Journey instantiation quality;
- current code or user intent validity without source reopen;
- host-facing sequence packets as source evidence by themselves;
- that behavior-only events are factual source text.

Future slices should deepen source adapters and real-history adjudication
without duplicating this schema contract elsewhere.
