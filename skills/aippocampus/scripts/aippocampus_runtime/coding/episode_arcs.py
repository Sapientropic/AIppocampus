#!/usr/bin/env python3
"""Build ordered Episode/Arc read-models for coding continuity events.

Episode/Arc rows sit between source events and host-agent action tickets. They
preserve ordered local causality such as "attempted route -> failed check ->
rejected route", but they are still derived navigation weather. Current
validity always requires reopening source before the foreground agent acts.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping, Sequence

from aippocampus_runtime.coding import sequence_packets
from aippocampus_runtime.question.source_refs import clean_source_ref, source_ref_key
from aippocampus_runtime.registry.api import unique_preserve

EPISODE_ARC_KIND = "aippocampus_episode_arc_read_model"
EPISODE_ARC_SCHEMA_VERSION = "aippocampus.episode_arc_read_model.v1"
REOPEN_PLAN_KIND = "aippocampus_episode_window_reopen_plan"
PUBLIC_GAPPY_CHAIN_REPORT_KIND = "aippocampus_episode_arc_public_gappy_chain_calibration_report"
PUBLIC_GAPPY_CHAIN_REPORT_SCHEMA_VERSION = "aippocampus.episode_arc_public_gappy_chain_calibration_report.v1"

SAFE_GAPPY_USES = ["ask", "refresh_sources"]
VISIBLE_ACTION_USES = {"block", "remind", "warn"}

_PROFILE_BY_KIND: dict[str, dict[str, Any]] = {
    "rejected_route_arc": {
        "markers": {"attempted_route", "failed_check", "tool_failure", "route_rejected", "rejected_route"},
        "required_any": (("attempted_route",), ("failed_check", "tool_failure"), ("route_rejected", "rejected_route")),
        "outcome": "route_rejected",
        "current_validity": "needs_reopen",
        "origin": "behavior_event",
    },
    "correction_arc": {
        "markers": {"user_correction", "accepted_workaround", "accepted_decision", "source_reopen"},
        "required_any": (("user_correction",), ("accepted_workaround", "accepted_decision"), ("source_reopen",)),
        "outcome": "needs_reopen",
        "current_validity": "needs_reopen",
        "origin": "clean_source",
    },
    "supersession_arc": {
        "markers": {"old_rule", "new_rule", "current_rule_selected", "superseded", "superseded_by"},
        "required_any": (("old_rule",), ("new_rule", "superseded_by"), ("current_rule_selected",)),
        "outcome": "superseded",
        "current_validity": "superseded",
        "origin": "clean_source",
    },
    "temporary_concern_arc": {
        "markers": {"temporary_concern", "later_normal_progress"},
        "required_any": (("temporary_concern",), ("later_normal_progress",)),
        "outcome": "constraint_not_current",
        "current_validity": "local_only",
        "origin": "clean_source",
    },
}

_RELATIONS = {
    ("attempted_route", "failed_check"): "failed_with",
    ("attempted_route", "tool_failure"): "failed_with",
    ("failed_check", "route_rejected"): "supported",
    ("failed_check", "rejected_route"): "supported",
    ("tool_failure", "route_rejected"): "supported",
    ("tool_failure", "rejected_route"): "supported",
    ("user_correction", "accepted_workaround"): "accepted_after",
    ("user_correction", "accepted_decision"): "accepted_after",
    ("accepted_workaround", "source_reopen"): "requires_reopen_before",
    ("accepted_decision", "source_reopen"): "requires_reopen_before",
    ("old_rule", "new_rule"): "superseded_by",
    ("new_rule", "current_rule_selected"): "supported",
    ("temporary_concern", "later_normal_progress"): "extinguished_by",
}


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _stable_id(prefix: str, *parts: Any, length: int = 18) -> str:
    raw = "\n".join(json.dumps(part, ensure_ascii=False, sort_keys=True) for part in parts)
    digest = hashlib.sha1(raw.encode("utf-8", errors="replace")).hexdigest()[:length]
    return f"{prefix}_{digest}"


def _unique_objects(items: list[Any], *, limit: int) -> list[Any]:
    seen: set[str] = set()
    out: list[Any] = []
    for item in items:
        key = json.dumps(item, ensure_ascii=False, sort_keys=True, default=str)
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
        if len(out) >= limit:
            break
    return out


def _source_ref_hash(ref: Mapping[str, Any]) -> str:
    raw = json.dumps(source_ref_key(ref), ensure_ascii=False, sort_keys=True)
    digest = hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()[:20]
    return f"sha256:{digest}"


def _compact_source_refs(row: Mapping[str, Any]) -> list[dict[str, Any]]:
    candidates = _as_list(row.get("source_refs"))
    if not candidates:
        candidates = [dict(row)]
    refs: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for candidate in candidates:
        clean = clean_source_ref(candidate)
        if not clean:
            continue
        key = source_ref_key(clean)
        if key in seen:
            continue
        seen.add(key)
        refs.append(clean)
    return refs[:8]


def _sort_key(row: Mapping[str, Any], fallback_index: int) -> tuple[int, int, int]:
    raw_index = row.get("sequence_index")
    if raw_index is None:
        raw_index = row.get("event_index")
    if raw_index is None:
        return (1, fallback_index, fallback_index)
    try:
        return (0, int(str(raw_index)), fallback_index)
    except (TypeError, ValueError):
        return (1, fallback_index, fallback_index)


def _nonzero_exit(row: Mapping[str, Any]) -> bool:
    value = row.get("exit_code")
    if value is None:
        value = row.get("exit_status")
    try:
        return int(str(value)) != 0
    except (TypeError, ValueError):
        return False


def _row_reports_failure(row: Mapping[str, Any]) -> bool:
    material = " ".join(
        str(row.get(key) or "")
        for key in ("hard_event_kind", "status", "failure_family", "result")
    ).casefold()
    return _nonzero_exit(row) or "failed" in material or "failure" in material


def _event_kind(row: Mapping[str, Any]) -> str:
    raw = str(row.get("event_kind") or row.get("event_type") or row.get("decision_kind") or "").strip()
    lowered = raw.casefold()
    command_class = str(row.get("command_class") or row.get("target_class") or "").casefold()
    operation_family = str(
        row.get("critical_operation_family")
        or row.get("operation_family")
        or row.get("event_family")
        or ""
    ).casefold()
    if _row_reports_failure(row):
        if command_class == "test" or operation_family in {"test_check_command_result", "test_result"}:
            return "failed_check"
        if lowered in {"tool_call_observed", "tool_call", "command_result"}:
            return "tool_failure"
    if lowered == "do_not_repeat":
        return "rejected_route"
    return raw


def _event_origin(row: Mapping[str, Any], event_kind: str, profile: Mapping[str, Any]) -> str:
    origin = str(row.get("origin") or row.get("source_family") or "").strip()
    if origin:
        return origin
    if event_kind in {"failed_check", "tool_failure"} or row.get("command_class") or row.get("hard_event_kind"):
        return "behavior_event"
    if row.get("decision_id") or row.get("event_type") or row.get("decision_kind"):
        return "coding_decision_event"
    return str(profile.get("origin") or "clean_source")


def _arc_origin(events: Sequence[Mapping[str, Any]], profile: Mapping[str, Any]) -> str:
    origins = [str(event.get("origin") or "") for event in events]
    if "behavior_event" in origins:
        return "behavior_event"
    if origins and all(origin == "coding_decision_event" for origin in origins):
        return "coding_decision_event"
    return str(profile.get("origin") or "clean_source")


def _normalize_event(row: Mapping[str, Any], fallback_index: int) -> dict[str, Any]:
    refs = _compact_source_refs(row)
    event_kind = _event_kind(row)
    _, profile = _profile_for([event_kind])
    event_id = str(row.get("event_id") or row.get("decision_id") or "").strip()
    if not event_id:
        event_id = _stable_id("event", event_kind, refs, fallback_index, length=16)
    return {
        "event_id": event_id,
        "event_kind": event_kind,
        "origin": _event_origin(row, event_kind, profile),
        "source_refs": refs,
        "source_ref_hash": _source_ref_hash(refs[0]) if refs else "",
        "turn_id": str(row.get("turn_id") or ""),
        "turn_index": row.get("turn_index"),
        "source_line": row.get("source_line") or row.get("line"),
        "affected_scope": _as_mapping(row.get("affected_scope")),
        "sequence_gaps": [str(item) for item in _as_list(row.get("sequence_gaps")) if str(item).strip()],
    }


def _group_rows(rows: Sequence[Mapping[str, Any]]) -> list[tuple[str, list[tuple[int, Mapping[str, Any]]]]]:
    groups: dict[str, list[tuple[int, Mapping[str, Any]]]] = {}
    fallback_group = _stable_id("episode", len(rows), rows[:1], rows[-1:] if rows else [], length=16)
    for index, row in enumerate(rows):
        episode_id = str(
            row.get("episode_id")
            or row.get("arc_id")
            or row.get("sequence_id")
            or row.get("case_id")
            or fallback_group
        )
        groups.setdefault(episode_id, []).append((index, row))
    return list(groups.items())


def _profile_for(kinds: Sequence[str]) -> tuple[str, Mapping[str, Any]]:
    kind_set = set(kinds)
    best_kind = "tacit_constraint_arc"
    best_score = 0
    for episode_kind, profile in _PROFILE_BY_KIND.items():
        score = len(kind_set & set(profile["markers"]))
        if score > best_score:
            best_kind = episode_kind
            best_score = score
    if best_kind == "tacit_constraint_arc":
        return best_kind, {"outcome": "unknown", "current_validity": "needs_reopen", "origin": "clean_source"}
    return best_kind, _PROFILE_BY_KIND[best_kind]


def _required_positions(kinds: Sequence[str], required_any: Sequence[Sequence[str]]) -> list[int | None]:
    positions: list[int | None] = []
    for options in required_any:
        found: int | None = None
        for index, event_kind in enumerate(kinds):
            if event_kind in options:
                found = index
                break
        positions.append(found)
    return positions


def _semantic_gaps(episode_kind: str, kinds: Sequence[str], profile: Mapping[str, Any]) -> list[str]:
    gaps: list[str] = []
    if len(kinds) < 2:
        return ["single_point_trap"]
    required_any = profile.get("required_any")
    if not isinstance(required_any, tuple):
        return gaps
    positions = _required_positions(kinds, required_any)
    present = [position for position in positions if position is not None]
    if 0 < len(present) < len(positions):
        gaps.append("missing_middle_event")
    if len(present) == len(positions) and present != sorted(present):
        gaps.append("event_order_semantic_mismatch")
    return gaps


def _relation_between(start_kind: str, end_kind: str) -> str:
    return _RELATIONS.get((start_kind, end_kind), "followed_by")


def _causal_edges(events: Sequence[Mapping[str, Any]]) -> list[dict[str, str]]:
    edges: list[dict[str, str]] = []
    for start, end in zip(events, events[1:], strict=False):
        edges.append(
            {
                "from": str(start.get("event_kind") or ""),
                "relation": _relation_between(str(start.get("event_kind") or ""), str(end.get("event_kind") or "")),
                "to": str(end.get("event_kind") or ""),
            }
        )
    return edges


def _merge_scope(events: Sequence[Mapping[str, Any]]) -> dict[str, list[Any]]:
    merged: dict[str, list[Any]] = {"files": [], "modules": [], "symbols": []}
    for event in events:
        scope = _as_mapping(event.get("affected_scope"))
        for field in merged:
            merged[field].extend(_as_list(scope.get(field)))
    return {field: _unique_objects(values, limit=12) for field, values in merged.items() if values}


def _turn_range(events: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    first = events[0] if events else {}
    last = events[-1] if events else {}
    return {
        "first_turn_id": first.get("turn_id") or "",
        "last_turn_id": last.get("turn_id") or "",
        "first_source_line": first.get("source_line"),
        "last_source_line": last.get("source_line"),
    }


def build_episode_arcs(event_rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Build deterministic ordered Episode/Arc read-models from event rows."""

    arcs: list[dict[str, Any]] = []
    for episode_id, grouped_rows in _group_rows(event_rows):
        ordered_rows = [row for index, row in sorted(grouped_rows, key=lambda item: _sort_key(item[1], item[0]))]
        events = [_normalize_event(row, index) for index, row in enumerate(ordered_rows)]
        events = [event for event in events if event["event_kind"]]
        if not events:
            continue
        kinds = [str(event["event_kind"]) for event in events]
        episode_kind, profile = _profile_for(kinds)
        explicit_gaps = [gap for event in events for gap in event.get("sequence_gaps", [])]
        sequence_gaps = unique_preserve(explicit_gaps + _semantic_gaps(episode_kind, kinds, profile), limit=8)
        source_refs = _unique_objects([ref for event in events for ref in event["source_refs"]], limit=16)
        source_hashes = [str(event.get("source_ref_hash") or "") for event in events if event.get("source_ref_hash")]
        arcs.append(
            {
                "schema_version": EPISODE_ARC_SCHEMA_VERSION,
                "kind": EPISODE_ARC_KIND,
                "episode_id": episode_id,
                "episode_kind": episode_kind,
                "origin": _arc_origin(events, profile),
                "source_event_ids": [str(event["event_id"]) for event in events],
                "source_refs": source_refs,
                "source_ref_hashes": source_hashes,
                "turn_range": _turn_range(events),
                "affected_scope": _merge_scope(events),
                "event_order": kinds,
                "causal_edges": _causal_edges(events),
                "outcome": str(profile.get("outcome") or "unknown"),
                "current_validity": str(profile.get("current_validity") or "needs_reopen"),
                "truth_status": sequence_packets.CHAIN_TRUTH_STATUS,
                "sequence_gaps": sequence_gaps,
                "expected_valid": not sequence_gaps,
            }
        )
    return arcs


def _source_thickness(arc: Mapping[str, Any]) -> str:
    if arc.get("sequence_gaps") or len(_as_list(arc.get("source_event_ids"))) < 2:
        return "thin"
    if str(arc.get("episode_kind") or "") == "supersession_arc" and len(_as_list(arc.get("source_event_ids"))) >= 3:
        return "strong"
    return "usable"


def _recommended_use(arc: Mapping[str, Any]) -> str:
    if _source_thickness(arc) == "thin" or arc.get("sequence_gaps"):
        return "refresh_sources"
    if str(arc.get("current_validity") or "") == "needs_reopen":
        return "refresh_sources"
    return "remind"


def _cannot_claim(arc: Mapping[str, Any]) -> list[str]:
    claims = [
        "route_handle_is_not_evidence",
        "current_validity_requires_source_reopen",
        "episode_arc_as_truth_layer",
    ]
    if arc.get("sequence_gaps"):
        claims.append("sequence_order_uncertain")
    if _source_thickness(arc) == "thin":
        claims.append("thin_source_visible_action_not_allowed")
    return claims


def render_sequence_packet(
    arc: Mapping[str, Any],
    *,
    trigger: str,
    why_relevant: str | None = None,
) -> dict[str, Any]:
    """Render the host-facing sequence packet for an Episode/Arc read-model."""

    events = _as_list(arc.get("_events"))
    if not events:
        event_ids = [str(value) for value in _as_list(arc.get("source_event_ids"))]
        event_kinds = [str(value) for value in _as_list(arc.get("event_order"))]
        hashes = [str(value) for value in _as_list(arc.get("source_ref_hashes"))]
        events = [
            {
                "event_id": event_id,
                "event_kind": event_kind,
                "source_ref_hash": hashes[index] if index < len(hashes) else "",
            }
            for index, (event_id, event_kind) in enumerate(zip(event_ids, event_kinds, strict=False))
        ]

    packet: dict[str, Any] = {
        "kind": sequence_packets.SEQUENCE_PACKET_KIND,
        "trigger": trigger,
        "why_relevant": why_relevant or str(arc.get("episode_kind") or "episode_arc"),
        "timeline": [
            {
                "event_id": str(event.get("event_id") or ""),
                "event_kind": str(event.get("event_kind") or ""),
                "source_ref_hash": str(event.get("source_ref_hash") or ""),
            }
            for event in events
        ],
        "current_assessment": {
            "source_thickness": _source_thickness(arc),
            "freshness": "needs_reopen" if str(arc.get("current_validity") or "") == "needs_reopen" else "aging",
            "proposed_use": _recommended_use(arc),
            "truth_boundary": "derived_weather_not_source_fact",
        },
        "cannot_claim": _cannot_claim(arc),
    }
    if arc.get("sequence_gaps"):
        packet["sequence_gaps"] = list(_as_list(arc.get("sequence_gaps")))
    return packet


def build_reopen_plan(arc: Mapping[str, Any]) -> dict[str, Any]:
    """Return a source-window navigation plan without treating the arc as truth."""

    source_thickness = _source_thickness(arc)
    safe_uses = SAFE_GAPPY_USES if source_thickness == "thin" or arc.get("sequence_gaps") else SAFE_GAPPY_USES + ["remind"]
    return {
        "kind": REOPEN_PLAN_KIND,
        "episode_id": str(arc.get("episode_id") or ""),
        "episode_kind": str(arc.get("episode_kind") or ""),
        "recommended_use": _recommended_use(arc),
        "safe_uses": safe_uses,
        "route": {
            "source_event_ids": [str(value) for value in _as_list(arc.get("source_event_ids"))],
            "source_refs": list(_as_list(arc.get("source_refs"))),
            "source_ref_hashes": [str(value) for value in _as_list(arc.get("source_ref_hashes"))],
            "source_window": dict(_as_mapping(arc.get("turn_range"))),
        },
        "cannot_claim": unique_preserve(_cannot_claim(arc) + ["episode_arc_is_not_current_truth"], limit=12),
    }


def _rate(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 6)


def _has_visible_action_projection(packet: Mapping[str, Any], plan: Mapping[str, Any]) -> bool:
    proposed_use = str(_as_mapping(packet.get("current_assessment")).get("proposed_use") or "")
    safe_uses = {str(value) for value in _as_list(plan.get("safe_uses"))}
    return proposed_use in VISIBLE_ACTION_USES or bool(safe_uses & VISIBLE_ACTION_USES)


def _public_case_summary(
    arc: Mapping[str, Any],
    packet: Mapping[str, Any],
    plan: Mapping[str, Any],
) -> dict[str, Any]:
    event_order = [str(value) for value in _as_list(arc.get("event_order"))]
    sequence_gaps = [str(value) for value in _as_list(arc.get("sequence_gaps"))]
    source_event_count = len(_as_list(arc.get("source_event_ids")))
    return {
        "case_id": _stable_id(
            "arc_case",
            arc.get("episode_kind"),
            event_order,
            sequence_gaps,
            source_event_count,
            length=12,
        ),
        "episode_kind": str(arc.get("episode_kind") or ""),
        "source_event_count": source_event_count,
        "source_ref_hash_count": len(_as_list(arc.get("source_ref_hashes"))),
        "event_order": event_order,
        "sequence_gaps": sequence_gaps,
        "current_validity": str(arc.get("current_validity") or ""),
        "source_thickness": str(_as_mapping(packet.get("current_assessment")).get("source_thickness") or ""),
        "proposed_use": str(_as_mapping(packet.get("current_assessment")).get("proposed_use") or ""),
        "safe_uses": [str(value) for value in _as_list(plan.get("safe_uses"))],
    }


def build_public_gappy_chain_calibration_report(event_rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Measure public gappy-chain behavior without serializing private source routes.

    This report is deliberately an aggregate/public fixture surface. It is safe
    for #663 evidence because it proves downgrade behavior for complete, gappy,
    wrong-order, and single-point chains without carrying raw text, source refs,
    event ids, thread ids, local paths, or registry paths into the output.
    """

    arcs = build_episode_arcs(event_rows)
    case_summaries: list[dict[str, Any]] = []
    gap_counts: dict[str, int] = {}
    kind_counts: dict[str, int] = {}
    complete_arc_count = 0
    gappy_arc_count = 0
    gappy_reopen_only_count = 0
    gappy_visible_action_overclaim_count = 0
    single_point_arc_count = 0
    single_point_overclaim_count = 0
    source_ref_chain_complete_count = 0
    temporary_concern_extinction_count = 0

    for arc in arcs:
        packet = render_sequence_packet(arc, trigger="public_gappy_chain_calibration")
        plan = build_reopen_plan(arc)
        summary = _public_case_summary(arc, packet, plan)
        case_summaries.append(summary)

        episode_kind = summary["episode_kind"]
        kind_counts[episode_kind] = kind_counts.get(episode_kind, 0) + 1
        sequence_gaps = [str(value) for value in _as_list(summary.get("sequence_gaps"))]
        visible_action = _has_visible_action_projection(packet, plan)
        if sequence_gaps:
            gappy_arc_count += 1
        else:
            complete_arc_count += 1
        if summary["source_event_count"] > 0 and summary["source_ref_hash_count"] >= summary["source_event_count"]:
            source_ref_chain_complete_count += 1
        if episode_kind == "temporary_concern_arc" and str(arc.get("outcome") or "") == "constraint_not_current":
            temporary_concern_extinction_count += 1

        for gap in sequence_gaps:
            gap_counts[gap] = gap_counts.get(gap, 0) + 1
        if sequence_gaps and summary["proposed_use"] in SAFE_GAPPY_USES and summary["safe_uses"] == SAFE_GAPPY_USES:
            gappy_reopen_only_count += 1
        if sequence_gaps and visible_action:
            gappy_visible_action_overclaim_count += 1
        if "single_point_trap" in sequence_gaps:
            single_point_arc_count += 1
            if visible_action:
                single_point_overclaim_count += 1

    metrics = {
        "episode_arc_count": len(arcs),
        "complete_arc_count": complete_arc_count,
        "gappy_arc_count": gappy_arc_count,
        "gappy_reopen_only_count": gappy_reopen_only_count,
        "gappy_visible_action_overclaim_count": gappy_visible_action_overclaim_count,
        "missing_middle_event_count": gap_counts.get("missing_middle_event", 0),
        "wrong_order_arc_count": gap_counts.get("event_order_semantic_mismatch", 0),
        "single_point_arc_count": single_point_arc_count,
        "temporary_concern_extinction_count": temporary_concern_extinction_count,
        "source_ref_chain_complete_count": source_ref_chain_complete_count,
        "source_ref_chain_coverage_rate": _rate(source_ref_chain_complete_count, len(arcs)),
        "single_point_overclaim_rate": _rate(single_point_overclaim_count, single_point_arc_count),
        "gappy_visible_action_overclaim_rate": _rate(gappy_visible_action_overclaim_count, gappy_arc_count),
        "needs_reopen_projection_rate": _rate(gappy_reopen_only_count, gappy_arc_count),
    }

    return {
        "schema_version": PUBLIC_GAPPY_CHAIN_REPORT_SCHEMA_VERSION,
        "kind": PUBLIC_GAPPY_CHAIN_REPORT_KIND,
        "metrics": metrics,
        "by_episode_kind": dict(sorted(kind_counts.items())),
        "sequence_gap_counts": dict(sorted(gap_counts.items())),
        "case_summaries": case_summaries,
        "can_claim": [
            "public_fixture_distinguishes_complete_gappy_wrong_order_single_point_and_temporary_arcs",
            "gappy_and_single_point_chains_project_to_ask_or_refresh_sources_only",
            "report_omits_raw_source_text_source_refs_event_ids_thread_ids_local_paths_and_registry_paths",
        ],
        "cannot_claim": [
            "github_663_episode_arc_owner_track_complete",
            "live_host_behavior_lift",
            "private_history_generality",
            "journey_instantiation_quality",
            "current_route_or_user_intent_validity_without_source_reopen",
        ],
        "issue_readouts": {
            "github_663": {
                "public_gappy_chain_fixture": "measured_public_deterministic",
                "complete_chain_count": complete_arc_count,
                "gappy_chain_count": gappy_arc_count,
                "single_point_overclaim_rate": metrics["single_point_overclaim_rate"],
                "needs_reopen_projection_rate": metrics["needs_reopen_projection_rate"],
                "gappy_visible_action_overclaim_rate": metrics["gappy_visible_action_overclaim_rate"],
                "live_host_behavior": "not_measured",
                "private_history_generality": "not_measured_by_public_fixture",
                "closeout_eligible": False,
            }
        },
    }
