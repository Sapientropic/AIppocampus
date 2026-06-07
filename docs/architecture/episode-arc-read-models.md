# Episode/Arc Read Models

Role: active design.

Status: first deterministic coding slice implemented in
`aippocampus_runtime/coding/episode_arcs.py`; broader Episode/Arc coverage
remains an active owner track and should not be claimed complete from this
slice alone.

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

`build_reopen_plan()` returns a source-window navigation plan: source event ids,
source refs, source hashes, turn range, safe uses, and `cannot_claim`. It is a
route back to source, not evidence that the route remains valid.

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

## Cannot Claim

This slice cannot claim:

- the broader #663 Episode/Arc owner track is complete;
- live private-history behavior lift;
- Journey instantiation quality;
- current code or user intent validity without source reopen;
- that behavior-only events are factual source text.

Future slices should deepen source adapters and real-history adjudication
without duplicating this schema contract elsewhere.
