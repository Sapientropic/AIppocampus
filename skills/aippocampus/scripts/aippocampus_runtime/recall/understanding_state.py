"""Task-time Understanding State read model.

The read model is a richer internal composition layer for Task Orientation
Packets. It is still navigation only: upstream pointers may help an agent pick
the first source to reopen, but clean source after reopen remains the only
truth authority. Keep the default foreground projection intentionally small so
future "make it more complete" edits do not turn TOP into an audit console.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from typing import Any

from aippocampus_runtime import core
from aippocampus_runtime.coding import episode_arcs
from aippocampus_runtime.journey import live as journey_live
from aippocampus_runtime.navigation import repo_familiarity
from aippocampus_runtime.ops.route_readiness import safe_source_refs
from aippocampus_runtime.privacy import redact_private_paths, redact_sensitive_values
from aippocampus_runtime.recall import continuity_domains, continuity_pathlets

KIND = "aippocampus_understanding_state"
SCHEMA_VERSION = "aippocampus_understanding_state.v1"
FOREGROUND_BYTE_BUDGET = 6000


def _public_payload(payload: Any) -> Any:
    return redact_sensitive_values(redact_private_paths(payload))


def _text(value: Any, limit: int = 180) -> str:
    return core.compact_text(str(value or "").strip(), limit)


def _iter_mappings(value: Iterable[Mapping[str, Any]] | None) -> list[Mapping[str, Any]]:
    return [item for item in (value or []) if isinstance(item, Mapping)]


def _component(
    name: str,
    *,
    status: str,
    foreground_projection: str,
    item_count: int = 0,
    boundary: str = "navigation_only_not_fact",
    gap: str = "",
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "component": name,
        "status": status,
        "foreground_projection": foreground_projection,
        "item_count": item_count,
        "authority": boundary,
    }
    if gap:
        out["gap"] = gap
    return out


def _source_boundary() -> dict[str, Any]:
    return {
        "navigation_not_truth": True,
        "clean_source_is_authority": True,
        "source_reopen_required_before_claim": True,
        "source_reopen_required_before_code_changing_action": True,
        "raw_source_text_serialized": False,
        "raw_private_text_serialized": False,
        "local_paths_serialized": False,
        "secret_values_serialized": False,
        "model_generated_summary_is_truth": False,
    }


def working_conclusion_exposure_strategy() -> dict[str, Any]:
    return {
        "passive_hook": "suppress_working_conclusions",
        "active_foreground_pull": "compact_orientation_only",
        "task_orientation_packet": "situation_frontier_unknowns_and_routes",
        "detail_profile": "lifecycle_and_gap_fields_allowed",
        "deepen": "source_window_required_for_exact_claims",
        "default_granularity": [
            "title",
            "one_line_situation",
            "frontier",
            "load_bearing_unknown",
        ],
        "lifecycle_projection": {
            "active": "foreground_orientation",
            "contested": "load_bearing_unknown_reopen_before_action",
            "stale": "load_bearing_unknown_reopen_before_claim",
            "superseded": "suppress_as_current_route",
            "blocked": "ask_or_detail_only",
            "retired": "suppress",
        },
        "truth_boundary": "working_conclusions_are_navigation_not_source_truth",
    }


def _route_cue(
    *,
    route_id: str,
    title: str,
    origin: str,
    why: str,
    source_refs: Any = None,
    action: str = "reopen",
    lifecycle_status: str = "active",
) -> dict[str, Any]:
    return {
        "route_id": _text(route_id, 120),
        "title": _text(title, 160),
        "origin": _text(origin, 80),
        "action": _text(action, 40) or "reopen",
        "why": _text(why, 220),
        "lifecycle_status": _text(lifecycle_status, 60) or "active",
        "source_refs": safe_source_refs(source_refs)[:3],
        "claim_boundary": "source_reopen_required_before_claim",
    }


def _constraint_item(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "constraint_id": _text(
            row.get("constraint_id") or row.get("guidance_id") or row.get("clause_id"),
            120,
        ),
        "source": _text(row.get("source") or row.get("kind") or "learning_loop", 80),
        "summary": _text(
            row.get("summary") or row.get("guidance_text") or row.get("guidance"),
            220,
        ),
        "authority": "navigation_only_not_fact",
        "source_refs": safe_source_refs(row.get("source_refs"))[:3],
        "why": _text(
            row.get("why")
            or "Mature guidance can change action order, but not source truth.",
            180,
        ),
        "reopen_requirement": "reopen_source_before_applying_broadly",
    }


def _external_anchor_routes(anchors: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    cues: list[dict[str, Any]] = []
    for anchor in anchors:
        cues.append(
            _route_cue(
                route_id=str(anchor.get("anchor_id") or anchor.get("public_ref") or "anchor"),
                title=f"{anchor.get('source_kind') or 'source'}: {anchor.get('project_role') or 'project route'}",
                origin="external_source_anchor",
                why="Role-labelled external anchor; reopen before quoting or closing.",
                source_refs=[{"source_id": f"{anchor.get('source_kind')}:{anchor.get('anchor_id')}"}],
                lifecycle_status=str(anchor.get("lifecycle_status") or "current"),
            )
        )
    return cues


def _continuity_domain_routes(task: str, snapshot: Mapping[str, Any] | None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    pointers = continuity_domains.match_continuity_domain_pointers(task, snapshot, limit=3)
    cues = [
        _route_cue(
            route_id=str(pointer.get("domain_id") or pointer.get("label")),
            title=str(pointer.get("label") or "continuity domain"),
            origin="continuity_domains",
            why=str(pointer.get("why_it_may_matter_now") or "Continuity domain overlaps the task."),
            source_refs=pointer.get("source_refs"),
            lifecycle_status=str(pointer.get("status") or "active"),
        )
        for pointer in pointers
    ]
    component = _component(
        "continuity_domains",
        status="projected" if cues else ("no_input" if not snapshot else "no_relevant_route"),
        foreground_projection="route_pointer",
        item_count=len(cues),
        gap="" if cues else "no matching source-trailed continuity domain",
    )
    return cues, component


def _continuity_pathlet_routes(task: str, pathlets: Iterable[Mapping[str, Any]] | Mapping[str, Any] | None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    snapshot: Mapping[str, Any] | None
    row_count = 0
    if isinstance(pathlets, Mapping):
        snapshot = pathlets
        raw_rows = snapshot.get("pathlets") or []
        row_count = len(raw_rows) if isinstance(raw_rows, list) else 0
    else:
        rows = _iter_mappings(pathlets)
        snapshot = {"pathlets": rows} if rows else None
        row_count = len(rows)
    pointers = continuity_pathlets.match_continuity_pathlet_pointers(task, snapshot, limit=3)
    cues = [
        _route_cue(
            route_id=str(pointer.get("pathlet_id") or pointer.get("label")),
            title=str(pointer.get("label") or "continuity pathlet"),
            origin="continuity_pathlets",
            why=str(pointer.get("why_it_may_matter_now") or "Ordered source route overlaps the task."),
            source_refs=pointer.get("source_refs"),
            lifecycle_status=str(pointer.get("status") or "active"),
        )
        for pointer in pointers
    ]
    component = _component(
        "continuity_pathlets",
        status="projected" if cues else ("no_input" if not row_count else "no_relevant_route"),
        foreground_projection="ordered_reopen_route",
        item_count=len(cues),
    )
    return cues, component


def _journey_routes(task: str, journeys: Iterable[Mapping[str, Any]] | None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    cues: list[dict[str, Any]] = []
    seen = 0
    for row in _iter_mappings(journeys):
        seen += 1
        hint = journey_live.build_foreground_journey_hint(journey=row, prompt=task)
        raw_visible = hint.get("agent_visible")
        visible: Mapping[str, Any] = raw_visible if isinstance(raw_visible, Mapping) else {}
        if hint.get("decision") != "agent_visible_hint":
            continue
        cues.append(
            _route_cue(
                route_id=str(hint.get("private_route_handle") or visible.get("path_label")),
                title=str(visible.get("path_label") or "journey route"),
                origin="journey",
                why=str(visible.get("frontier") or hint.get("reason") or "Journey frontier overlaps the task."),
                source_refs=row.get("source_refs"),
                lifecycle_status=str(visible.get("status") or row.get("status") or "active"),
            )
        )
    component = _component(
        "journey",
        status="projected" if cues else ("no_input" if not seen else "backstage_or_not_relevant"),
        foreground_projection="gentle_frontier_nudge",
        item_count=len(cues),
    )
    return cues, component


def _episode_routes(task: str, arcs: Iterable[Mapping[str, Any]] | None) -> tuple[list[dict[str, Any]], dict[str, Any], list[dict[str, Any]]]:
    cues: list[dict[str, Any]] = []
    cautions: list[dict[str, Any]] = []
    rows = _iter_mappings(arcs)
    for arc in rows[:3]:
        packet = episode_arcs.render_sequence_packet(arc, trigger="task_orientation", why_relevant=task)
        plan = episode_arcs.build_reopen_plan(arc)
        gaps = list(packet.get("sequence_gaps") or [])
        if gaps:
            cautions.append(
                {
                    "kind": "episode_arc_gap",
                    "status": "review_before_action",
                    "reason": "gappy_episode_arc",
                    "gaps": gaps[:3],
                    "claim_boundary": "episode_arc_is_not_current_truth",
                }
            )
        cues.append(
            _route_cue(
                route_id=str(plan.get("episode_id") or arc.get("episode_id")),
                title=f"episode arc: {plan.get('episode_kind') or arc.get('episode_kind') or 'route'}",
                origin="episode_arcs",
                why=str(plan.get("recommended_use") or "Episode arc may change action order."),
                source_refs=(plan.get("route") or {}).get("source_refs"),
                lifecycle_status=str((packet.get("current_assessment") or {}).get("freshness") or "needs_reopen"),
            )
        )
    component = _component(
        "episode_arcs",
        status="projected" if cues else "no_input",
        foreground_projection="caution_route",
        item_count=len(cues),
    )
    return cues, component, cautions


def _repo_routes(task: str, manifest: Mapping[str, Any] | None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not isinstance(manifest, Mapping):
        return [], _component(
            "repo_familiarity",
            status="no_input",
            foreground_projection="first_source_hint",
            item_count=0,
        )
    cards = repo_familiarity.build_repo_familiarity_cards(manifest)
    packet = repo_familiarity.select_repo_familiarity_packet(cards, task=task)
    selected = [row for row in packet.get("selected_cards") or [] if isinstance(row, Mapping)]
    cues = [
        _route_cue(
            route_id=str(card.get("card_id") or card.get("landmark")),
            title=str(card.get("landmark") or "repo familiarity"),
            origin="repo_familiarity",
            why=str(card.get("action_delta_required") or card.get("why_now") or "Repo familiarity can reduce broad search."),
            source_refs=card.get("source_refs"),
            lifecycle_status=str(card.get("freshness") or "unknown"),
        )
        for card in selected[:3]
    ]
    component = _component(
        "repo_familiarity",
        status="projected" if cues else "no_relevant_route",
        foreground_projection="first_source_hint",
        item_count=len(cues),
        gap="" if cues else "no card survived task relevance and freshness filters",
    )
    return cues, component


def _reviewed_background_routes(
    findings: Iterable[Mapping[str, Any]] | None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    cues: list[dict[str, Any]] = []
    rows = _iter_mappings(findings)
    for finding in rows[:3]:
        source_summary = finding.get("source_summary")
        source_map = source_summary if isinstance(source_summary, Mapping) else {}
        source_ids = [
            str(item)
            for item in source_map.get("source_finding_ids") or []
            if str(item).strip()
        ]
        finding_id = str(finding.get("finding_id") or "").strip()
        if not source_ids and not int(source_map.get("source_ref_count") or 0):
            continue
        source_refs = [{"source_id": value} for value in (source_ids or [f"reviewed_background:{finding_id}"])]
        cues.append(
            _route_cue(
                route_id=f"reviewed_background:{finding_id or len(cues) + 1}",
                title=str(finding.get("finding_title") or finding.get("shape_label") or "reviewed background finding"),
                origin="reviewed_background",
                why=str(
                    finding.get("why_it_may_matter_now")
                    or finding.get("match_reason")
                    or "Reviewed background finding matched this task."
                ),
                source_refs=source_refs,
                action="reopen_reviewed_background_route",
                lifecycle_status="reviewed_navigation",
            )
        )
    return cues, _component(
        "reviewed_background_findings",
        status="projected" if cues else ("no_input" if not rows else "no_source_backed_route"),
        foreground_projection="compact_reviewed_background_route",
        item_count=len(cues),
        boundary="reviewed_background_navigation_not_source_truth",
    )


def _reflection_adjustment_routes(
    adjustments: Iterable[Mapping[str, Any]] | None,
) -> tuple[list[dict[str, Any]], dict[str, Any], list[dict[str, Any]]]:
    cues: list[dict[str, Any]] = []
    cautions: list[dict[str, Any]] = []
    rows = _iter_mappings(adjustments)
    for row in rows[:6]:
        refs = safe_source_refs(row.get("source_refs"))[:3]
        if not refs:
            continue
        action = str(row.get("feedback_action") or "").strip()
        surface = str(row.get("surface") or "navigation").strip()
        delta = row.get("delta")
        target_id = str(row.get("target_id") or "").strip()
        reason = str(row.get("reason") or action or "reviewed Reflection feedback")
        if delta is None:
            numeric_delta = 0.0
        else:
            try:
                numeric_delta = float(delta)
            except (TypeError, ValueError):
                numeric_delta = 0.0
        if action in {"recall_helpful", "revive", "turning_point"} or numeric_delta > 0:
            cues.append(
                _route_cue(
                    route_id=f"reflection_adjustment:{target_id or len(cues) + 1}",
                    title=f"Reflection feedback: {action or surface}",
                    origin="reflection_adjustment",
                    why=reason,
                    source_refs=refs,
                    action="prefer_or_recheck_route",
                    lifecycle_status="reviewed_navigation",
                )
            )
        if action in {"recall_ignored", "user_correction", "abandon"} or numeric_delta < 0:
            cautions.append(
                {
                    "kind": "reflection_adjustment",
                    "status": "review_before_reusing_route",
                    "surface": _text(surface, 60),
                    "feedback_action": _text(action, 60),
                    "target_id": _text(target_id, 120),
                    "reason": _text(reason, 220),
                    "claim_boundary": "reflection_feedback_is_navigation_not_source_truth",
                    "clean_source_mutation": False,
                    "source_reopen_required": True,
                }
            )
    return cues, _component(
        "reflection_adjustments",
        status="projected" if (cues or cautions) else ("no_input" if not rows else "no_source_backed_adjustment"),
        foreground_projection="route_visibility_and_caution",
        item_count=len(cues) + len(cautions),
        boundary="low_authority_feedback_not_truth",
    ), cautions


def build_understanding_state_read_model(
    task: str,
    *,
    project: str = "AIppocampus",
    issue_packet: Mapping[str, Any] | None = None,
    external_source_anchors: Iterable[Mapping[str, Any]] | None = None,
    suppressed_external_source_anchors: Iterable[Mapping[str, Any]] | None = None,
    learning_constraints: Iterable[Mapping[str, Any]] | None = None,
    suppressed_constraints: Iterable[Mapping[str, Any]] | None = None,
    continuity_snapshot: Mapping[str, Any] | None = None,
    continuity_pathlet_rows: Iterable[Mapping[str, Any]] | None = None,
    journeys: Iterable[Mapping[str, Any]] | None = None,
    episode_arc_rows: Iterable[Mapping[str, Any]] | None = None,
    episode_arcs: Iterable[Mapping[str, Any]] | None = None,
    reflection_adjustments: Iterable[Mapping[str, Any]] | None = None,
    reviewed_background_findings: Iterable[Mapping[str, Any]] | None = None,
    sidecar_components: Iterable[Mapping[str, Any]] | None = None,
    repo_familiarity_manifest: Mapping[str, Any] | None = None,
    max_foreground_routes: int = 3,
) -> dict[str, Any]:
    clean_task = _text(task, 240)
    anchors = _iter_mappings(external_source_anchors)
    suppressed_anchors = _iter_mappings(suppressed_external_source_anchors)
    constraints = _iter_mappings(learning_constraints)
    suppressed = _iter_mappings(suppressed_constraints)

    route_cues: list[dict[str, Any]] = []
    caution_packets: list[dict[str, Any]] = []
    components: list[dict[str, Any]] = []

    route_cues.extend(_external_anchor_routes(anchors))
    components.append(
        _component(
            "external_source_anchors",
            status="projected" if anchors else "no_input",
            foreground_projection="role_labelled_anchor_route",
            item_count=len(anchors),
        )
    )

    domain_cues, domain_component = _continuity_domain_routes(clean_task, continuity_snapshot)
    route_cues.extend(domain_cues)
    components.append(domain_component)

    pathlet_cues, pathlet_component = _continuity_pathlet_routes(clean_task, continuity_pathlet_rows)
    route_cues.extend(pathlet_cues)
    components.append(pathlet_component)

    journey_cues, journey_component = _journey_routes(clean_task, journeys)
    route_cues.extend(journey_cues)
    components.append(journey_component)

    arc_input = episode_arcs if episode_arcs is not None else episode_arc_rows
    episode_cues, episode_component, episode_cautions = _episode_routes(clean_task, arc_input)
    route_cues.extend(episode_cues)
    caution_packets.extend(episode_cautions)
    components.append(episode_component)

    repo_cues, repo_component = _repo_routes(clean_task, repo_familiarity_manifest)
    route_cues.extend(repo_cues)
    components.append(repo_component)

    background_cues, background_component = _reviewed_background_routes(
        reviewed_background_findings
    )
    route_cues.extend(background_cues)
    components.append(background_component)

    reflection_cues, reflection_component, reflection_cautions = _reflection_adjustment_routes(
        reflection_adjustments
    )
    route_cues.extend(reflection_cues)
    caution_packets.extend(reflection_cautions)
    components.append(reflection_component)

    for item in _iter_mappings(sidecar_components):
        components.append(
            _component(
                f"sidecar_loader:{item.get('component') or 'unknown'}",
                status=str(item.get("status") or "unknown"),
                foreground_projection="loader_status",
                item_count=int(item.get("item_count") or 0),
                gap=str(item.get("next_action") or ""),
            )
        )

    learning_refs = [_constraint_item(row) for row in constraints]
    components.append(
        _component(
            "learning_loop_constraints",
            status="projected" if learning_refs else "no_input",
            foreground_projection="mature_constraint_ref",
            item_count=len(learning_refs),
        )
    )

    for row in [*suppressed_anchors, *suppressed]:
        caution_packets.append(
            {
                "kind": _text(row.get("source_kind") or row.get("source") or "suppressed_route", 80),
                "status": "suppressed_or_review_only",
                "reason": _text(
                    row.get("suppression_reason")
                    or row.get("lifecycle_status")
                    or "not_current_foreground_guidance",
                    120,
                ),
                "claim_boundary": "do_not_rank_as_current_route",
            }
        )

    if issue_packet:
        route_cues.insert(
            0,
            _route_cue(
                route_id="issue_work_guard",
                title="issue work guard",
                origin="issue_work_guard",
                why=str(issue_packet.get("suggested_agent_action") or "Check existing owner routes before broad search."),
                source_refs=[{"source_id": "runtime:ops.issue_work_guard"}],
                lifecycle_status="active" if issue_packet.get("should_pull") else "quiet",
            ),
        )
        components.insert(
            0,
            _component(
                "issue_work_guard",
                status="active_pull" if issue_packet.get("should_pull") else "quiet",
                foreground_projection="owner_route_guard",
                item_count=len(issue_packet.get("existing_owner_ref_ids") or []),
            ),
        )

    foreground: dict[str, Any] = {
        "situation_summary": (
            f"{project} task orientation: choose a source-backed route before broad search."
        ),
        "frontier": "recover project state, then reopen the load-bearing route before claims or code changes",
        "load_bearing_unknowns": [
            "which route is current after the latest issue comments",
            "whether a learning constraint should change action order",
            "whether private replay aggregate has been explicitly opted in",
        ],
        "first_routes_to_reopen": route_cues[: max(0, max_foreground_routes)],
        "mature_constraints": learning_refs[:3],
        "boundary": "Plan with this as orientation only; reopen source for exact, stale, public, disputed, or code-changing claims.",
    }
    foreground["byte_size"] = len(
        json.dumps(foreground, ensure_ascii=False, sort_keys=True).encode("utf-8")
    )
    foreground["byte_budget"] = FOREGROUND_BYTE_BUDGET
    foreground["too_heavy"] = foreground["byte_size"] > FOREGROUND_BYTE_BUDGET

    state = {
        "kind": KIND,
        "schema_version": SCHEMA_VERSION,
        "project": project,
        "task": clean_task,
        "authority": "navigation_only_not_fact",
        "truth_authority": "clean_source_after_reopen",
        "storage": "derived_no_new_truth_store",
        "projection_source": "task_orientation_active_path_plus_upstream_read_models",
        "working_conclusion_exposure_strategy": working_conclusion_exposure_strategy(),
        "upstream_components": components,
        "working_conclusions": [
            {
                "conclusion_id": "task_orientation_current_frontier",
                "summary": "The safe first move is route selection, not broad manual search.",
                "lifecycle_status": "active",
                "allowed_surface": "active_foreground_pull",
                "authority": "navigation_only_not_fact",
            }
        ],
        "route_cues": route_cues,
        "caution_packets": caution_packets,
        "learning_constraint_refs": learning_refs,
        "reading_budget": {
            "max_foreground_routes": max_foreground_routes,
            "broad_manual_search_after": "only_after_reopen_routes_fail_or_are_stale",
            "stop_conditions": [
                "stop if the route is stale, superseded, private, or missing source",
                "stop once the reopened source answers the load-bearing unknown",
                "ask the user when no route can decide the next action",
            ],
        },
        "foreground_projection": foreground,
        "source_boundary": _source_boundary(),
        "metrics": {
            "upstream_component_count": len(components),
            "route_cue_count": len(route_cues),
            "foreground_route_count": len(foreground["first_routes_to_reopen"]),
            "learning_constraint_ref_count": len(learning_refs),
            "caution_packet_count": len(caution_packets),
            "foreground_too_heavy": foreground["too_heavy"],
            "raw_source_text_serialized": 0,
            "local_path_serialized": 0,
        },
        "cannot_claim": [
            "understanding_state_is_source_truth",
            "working_conclusion_is_current_fact_without_reopen",
            "private_replay_lift_without_opt_in_aggregate_eval",
        ],
    }
    return _public_payload(state)


__all__ = [
    "FOREGROUND_BYTE_BUDGET",
    "KIND",
    "SCHEMA_VERSION",
    "build_understanding_state_read_model",
    "working_conclusion_exposure_strategy",
]
