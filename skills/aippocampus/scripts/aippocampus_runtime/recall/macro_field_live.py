"""Live recall adapter for macro-field atlas inputs.

This module is only a query-time bridge. It turns already-selected recall
routes and bounded runtime outcome rows into macro-field atlas inputs, then
lets the atlas and router keep their normal navigation-only authority.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from aippocampus_runtime.core import stable_json_lines_id
from aippocampus_runtime.macro import timing_affordance, transform_orbit
from aippocampus_runtime.navigation import macro_field_atlas
from aippocampus_runtime.ops.route_readiness import safe_source_refs
from aippocampus_runtime.recall import macro_live_recall
from aippocampus_runtime.subconscious import posture_relation_policy
from aippocampus_runtime.subconscious.posture_relation_history import (
    posture_relation_calibration_from_history,
)

SCHEMA_VERSION = 1


def _text(value: Any) -> str:
    return str(value or "").strip()


def sections_from_recall_routes(routes: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    sections: list[dict[str, Any]] = []
    for index, route in enumerate(routes):
        refs = safe_source_refs(route.get("source_refs"))
        if not refs:
            continue
        family = macro_live_recall.route_source_family(route)
        posture = _text(route.get("posture_id") or route.get("macro_posture_id"))
        if posture == "ambiguous_posture":
            posture = ""
        sections.append(
            {
                "section_id": _text(route.get("section_id"))
                or stable_json_lines_id(
                    "recall_section",
                    route.get("handle"),
                    index,
                    ensure_ascii=False,
                    default_str=False,
                ),
                "title": macro_live_recall.route_label(route),
                "scope": _text(route.get("scope_bucket") or route.get("scope") or "recall_route"),
                "topic_epoch": _text(route.get("topic_epoch") or "current"),
                "task_family": family,
                "route_topic": _text(route.get("route_topic") or family),
                "freshness": _text(route.get("freshness") or route.get("currentness") or "current"),
                "privacy_state": _text(route.get("privacy_state") or route.get("privacy") or "public_safe"),
                "source_refs": refs,
                "posture_id": posture,
            }
        )
    return sections


def declared_edges_from_recall_routes(
    routes: Sequence[Mapping[str, Any]],
    sections: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    section_ids = [str(section.get("section_id") or "") for section in sections]
    by_route_id: dict[str, str] = {}
    for section, route in zip(sections, [row for row in routes if safe_source_refs(row.get("source_refs"))], strict=False):
        for key in ("route_id", "handle", "section_id"):
            value = _text(route.get(key))
            if value:
                by_route_id[value] = str(section.get("section_id") or "")
    edges: list[dict[str, Any]] = []
    for route in routes:
        for raw in route.get("declared_edges") or route.get("declared_edge_events") or []:
            if not isinstance(raw, Mapping):
                continue
            refs = safe_source_refs(raw.get("source_refs") or route.get("source_refs"))
            privacy = _text(raw.get("privacy_state") or route.get("privacy_state") or "public_safe")
            freshness = _text(raw.get("freshness") or route.get("freshness") or "current")
            if not refs or privacy in {"blocked", "private_blocked"} or freshness in {"stale", "superseded"}:
                continue
            source = by_route_id.get(_text(raw.get("from_route_id"))) or _text(raw.get("from_section_id"))
            target = by_route_id.get(_text(raw.get("to_route_id"))) or _text(raw.get("to_section_id"))
            if not source or not target or source == target:
                continue
            if source not in section_ids or target not in section_ids:
                continue
            edges.append(
                {
                    "source_event_id": _text(raw.get("source_event_id") or raw.get("event_id") or route.get("handle")),
                    "from_section_id": source,
                    "to_section_id": target,
                    "relation": _text(raw.get("relation") or raw.get("relation_kind") or "shared_source_event"),
                    "source_refs": refs,
                    "authority": "direction_only",
                    "reasons": [str(item) for item in raw.get("reasons") or ["explicit_source_relation"]][:4],
                }
            )
    return edges


def posture_policies_from_recall_routes(routes: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    report = posture_relation_calibration_from_history(routes)
    policies: list[dict[str, Any]] = []
    for candidate in report["calibration"].get("candidates") or []:
        policy = posture_relation_policy.promotion_gate(candidate)
        if policy["accepted"]:
            policies.append(policy)
    return policies


def warning_inputs_from_runtime_streams(
    *,
    foreground_outcomes: Sequence[Mapping[str, Any]] | None = None,
    macro_transition_history: Sequence[Any] | None = None,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    timing = None
    diagnostics: list[dict[str, Any]] = []
    if foreground_outcomes:
        timing = timing_affordance.timing_affordance_feedback_gate(foreground_outcomes)
    if macro_transition_history:
        history = list(macro_transition_history)
        if len(history) >= 2:
            diagnostics.append(
                transform_orbit.source_reanchoring_audit(
                    history[0],
                    history[-1],
                    history,
                    source_reopened=False,
                )
            )
            diagnostics.append(transform_orbit.orbit_oscillation_audit(history))
    return timing, diagnostics


def materialize_for_recall(
    *,
    query: str,
    routes: Sequence[Mapping[str, Any]],
    foreground_outcomes: Sequence[Mapping[str, Any]] | None = None,
    macro_transition_history: Sequence[Any] | None = None,
    top_n: int = 5,
) -> dict[str, Any] | None:
    sections = sections_from_recall_routes(routes)
    if not sections:
        return None
    declared_edges = declared_edges_from_recall_routes(routes, sections)
    policies = posture_policies_from_recall_routes(routes)
    timing, diagnostics = warning_inputs_from_runtime_streams(
        foreground_outcomes=foreground_outcomes,
        macro_transition_history=macro_transition_history,
    )
    atlas = macro_field_atlas.materialize_macro_field_atlas(
        sections,
        query=query,
        top_n=top_n,
        declared_edges=declared_edges,
        posture_policies=policies,
        timing_affordance=timing,
        invariant_diagnostics=diagnostics,
    )
    return {
        "kind": "macro_field_live_recall_materialization",
        "schema_version": SCHEMA_VERSION,
        "atlas": atlas,
        "foreground_projection": atlas["foreground_projection"],
        "declared_edge_count": len(declared_edges),
        "posture_policy_count": len(policies),
        "timing_warning_count": len(atlas["foreground_projection"].get("warnings") or []),
        "authority_level": "direction_only",
        "claim_permission": "none",
        "source_reopen_required_before_claim": True,
    }


def merge_projection(
    projection: Mapping[str, Any],
    live_materialization: Mapping[str, Any] | None,
) -> dict[str, Any]:
    payload = dict(projection)
    if not isinstance(live_materialization, Mapping):
        return payload
    foreground = live_materialization.get("foreground_projection")
    if isinstance(foreground, Mapping):
        payload["foreground_projection"] = dict(foreground)
        payload["macro_field_projection"] = dict(foreground)
        payload["macro_field_live"] = {
            "declared_edge_count": live_materialization.get("declared_edge_count", 0),
            "posture_policy_count": live_materialization.get("posture_policy_count", 0),
            "timing_warning_count": live_materialization.get("timing_warning_count", 0),
            "source_reopen_required_before_claim": True,
        }
    return payload


__all__ = [
    "declared_edges_from_recall_routes",
    "materialize_for_recall",
    "merge_projection",
    "posture_policies_from_recall_routes",
    "sections_from_recall_routes",
    "warning_inputs_from_runtime_streams",
]
