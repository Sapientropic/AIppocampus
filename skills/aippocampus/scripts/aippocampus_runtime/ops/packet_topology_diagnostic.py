#!/usr/bin/env python3
"""Post-packet relation diagnostics for route, narrative, Macro, Dream, and AIppo packets."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from aippocampus_runtime.core import stable_text_join_digest
from aippocampus_runtime.topology.borromean import borromean_relation_diagnostic
from aippocampus_runtime.topology.primitive_registry import (
    ANNOTATION_BACKED,
    REDUCER_BACKED,
    topology_primitive_registry,
)

SCHEMA_VERSION = 1
KIND = "aippocampus_packet_topology_diagnostic"
FORBIDDEN_MARKERS = (
    "PRIVATE_PACKET_TEXT",
    "raw_private_source_text",
    "source://private",
    "C:\\",
    "/Users/",
)
AUTHORITY_OVERREACH = "authority_overreach"
MISSING_MIDDLE = "missing_middle_or_cut_point"
ROUTE_CYCLE = "explicit_route_cycle"
AGENCY_SUPPRESSION = "agency_suppression_fixture"
KNOT_WITHOUT_UNLINKING = "knot_without_unlinking_move"
RELATION_PRESERVED = "relation_preserved"


def _text(value: Any) -> str:
    return str(value or "").strip()


def _safe_case_id(value: Any) -> str:
    text = _text(value)
    if (
        text
        and len(text) <= 96
        and all(char.isalnum() or char in "-_." for char in text)
    ):
        return text
    return "case_" + stable_text_join_digest(
        text, sep="\u241f", length=12, blank_falsy=False
    )


def _safe_label(value: Any, *, fallback: str = "") -> str:
    text = _text(value).casefold()
    return text if text and all(char.isalnum() or char in "-_." for char in text) else fallback


def _safe_bool(value: Any) -> bool:
    return bool(value)


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _is_navigation_only(row: Mapping[str, Any]) -> bool:
    output_mode = _safe_label(row.get("output_mode"))
    authority = _safe_label(row.get("authority_level") or row.get("authority"))
    action = _safe_label(row.get("action_grammar") or row.get("action"))
    claim = _safe_label(row.get("claim_permission"))
    return (
        output_mode in {"direction_only", "bounded_summary_as_route", "navigation_only"}
        or authority in {"navigation_only", "direction_only", "candidate_not_fact"}
        or action == "direction_only"
        or claim in {"no_claim_before_reopen", "navigation_only_not_fact"}
    )


def _packet_type(row: Mapping[str, Any]) -> str:
    return _safe_label(row.get("packet_type") or row.get("kind"), fallback="packet")


def _navigation_as_claim(row: Mapping[str, Any]) -> bool:
    return _safe_bool(row.get("rendered_as_evidence")) and _is_navigation_only(row)


def _macro_as_decision(row: Mapping[str, Any]) -> bool:
    return _packet_type(row) in {"macro_orientation", "macro_router_context"} and _safe_bool(
        row.get("rendered_as_action_instruction")
    )


def _candidate_as_authority(row: Mapping[str, Any]) -> bool:
    packet_type = _packet_type(row)
    authority = _safe_label(row.get("authority") or row.get("truth_boundary"))
    return (
        packet_type in {"dream_candidate", "aippo_candidate", "aippo_activation"}
        or authority in {"candidate_only", "candidate_not_fact", "dream_synthesized_candidate_not_fact"}
    ) and _safe_bool(row.get("rendered_as_certainty"))


def _source_handle_as_fact(row: Mapping[str, Any]) -> bool:
    return _safe_bool(row.get("source_handle_rendered_as_fact")) or (
        bool(row.get("source_handle") or row.get("source_handles"))
        and _safe_bool(row.get("rendered_as_fact"))
    )


def _missing_middle(row: Mapping[str, Any]) -> bool:
    return _safe_bool(row.get("missing_middle")) or _safe_label(
        row.get("pathlet_gap") or row.get("source_gap")
    ) in {"missing_middle", "cut_point"}


def _explicit_route_cycle(row: Mapping[str, Any]) -> bool:
    route_state = _safe_label(row.get("route_state"))
    return _safe_bool(row.get("repeated_failed_route")) or (
        _safe_int(row.get("reopen_attempt_count")) >= 3
        and route_state in {"stale", "rejected", "blocked"}
    )


def _agency_suppression(row: Mapping[str, Any]) -> bool:
    return _safe_bool(row.get("useful_navigation_available")) and _safe_bool(
        row.get("foreground_suppressed")
    )


def _knot_without_unlinking(row: Mapping[str, Any]) -> bool:
    return _safe_int(row.get("obligation_count")) >= 3 and not _safe_bool(
        row.get("unlinking_move_present")
    )


def _borromean_break_counted(row: Mapping[str, Any]) -> bool:
    return bool(borromean_relation_diagnostic(row)["break_counted"])


def _annotation_missing_middle_reason(row: Mapping[str, Any]) -> str:
    label = _safe_label(row.get("pathlet_gap") or row.get("source_gap"))
    if label == "cut_point":
        return "producer_annotated_cut_point"
    return "producer_annotated_missing_middle"


def _row_provenance(
    *,
    reducer_diagnostics: list[str],
    producer_annotations: list[str],
) -> str:
    if reducer_diagnostics:
        return REDUCER_BACKED
    if producer_annotations:
        return ANNOTATION_BACKED
    return "none"


def _row_reason_codes(
    row: Mapping[str, Any],
    *,
    borromean: Mapping[str, Any],
) -> tuple[list[str], list[str], list[str]]:
    reason_codes: list[str] = []
    reducer_diagnostics: list[str] = []
    producer_annotations: list[str] = []

    reducer_cases = (
        ("navigation_as_claim", _navigation_as_claim(row), "reducer_navigation_as_claim"),
        ("macro_as_decision", _macro_as_decision(row), "reducer_macro_as_decision"),
        ("candidate_as_authority", _candidate_as_authority(row), "reducer_candidate_as_authority"),
        ("source_handle_as_fact", _source_handle_as_fact(row), "reducer_source_handle_as_fact"),
        ("explicit_route_cycle", _explicit_route_cycle(row), "reducer_explicit_route_cycle"),
        ("agency_suppression", _agency_suppression(row), "reducer_agency_suppression"),
        ("knot_without_unlinking", _knot_without_unlinking(row), "reducer_knot_without_unlinking"),
    )
    for primitive_id, matched, reason in reducer_cases:
        if matched:
            reducer_diagnostics.append(primitive_id)
            reason_codes.append(reason)

    if borromean.get("break_counted"):
        if borromean.get("derived_break"):
            reducer_diagnostics.append("borromean_relation")
        elif borromean.get("annotation_break"):
            producer_annotations.append("borromean_relation")
        for reason in borromean.get("reason_codes") or []:
            if reason not in reason_codes:
                reason_codes.append(str(reason))

    if _missing_middle(row):
        producer_annotations.append("missing_middle_or_cut_point")
        reason_codes.append(_annotation_missing_middle_reason(row))

    if not reason_codes:
        reason_codes.append("relation_preserved")
    return (
        list(dict.fromkeys(reason_codes)),
        list(dict.fromkeys(reducer_diagnostics)),
        list(dict.fromkeys(producer_annotations)),
    )


def _diagnostic_for_row(row: Mapping[str, Any]) -> str:
    if (
        _navigation_as_claim(row)
        or _macro_as_decision(row)
        or _candidate_as_authority(row)
        or _source_handle_as_fact(row)
        or _borromean_break_counted(row)
    ):
        return AUTHORITY_OVERREACH
    if _missing_middle(row):
        return MISSING_MIDDLE
    if _explicit_route_cycle(row):
        return ROUTE_CYCLE
    if _agency_suppression(row):
        return AGENCY_SUPPRESSION
    if _knot_without_unlinking(row):
        return KNOT_WITHOUT_UNLINKING
    return RELATION_PRESERVED


def evaluate_packet(row: Mapping[str, Any]) -> dict[str, Any]:
    borromean = borromean_relation_diagnostic(row)
    diagnostic = _diagnostic_for_row(row)
    reason_codes, reducer_diagnostics, producer_annotations = _row_reason_codes(
        row,
        borromean=borromean,
    )
    boundary_crossings: list[str] = []
    if _navigation_as_claim(row):
        boundary_crossings.append("navigation_as_claim")
    if _macro_as_decision(row):
        boundary_crossings.append("macro_as_decision")
    if _candidate_as_authority(row):
        boundary_crossings.append("candidate_as_authority")
    if _source_handle_as_fact(row):
        boundary_crossings.append("source_handle_as_fact")
    if borromean["break_counted"]:
        boundary_crossings.extend(
            reason
            for reason in borromean["reason_codes"]
            if str(reason).startswith("borromean_missing_")
        )
        if borromean["annotation_break"]:
            boundary_crossings.append("producer_annotated_borromean_break")

    return {
        "kind": "aippocampus_packet_topology_row",
        "schema_version": SCHEMA_VERSION,
        "case_id": _safe_case_id(row.get("case_id")),
        "packet_type": _packet_type(row),
        "diagnostic": diagnostic,
        "diagnostic_kind": "packet_topology_diagnostic",
        "diagnostic_provenance": _row_provenance(
            reducer_diagnostics=reducer_diagnostics,
            producer_annotations=producer_annotations,
        ),
        "reason_codes": reason_codes,
        "reducer_diagnostics": reducer_diagnostics,
        "producer_annotations": producer_annotations,
        "preserved_relations": ["route_points_to_source"] if diagnostic == RELATION_PRESERVED else [],
        "boundary_crossings": boundary_crossings,
        "cycles": ["repeated_failed_route"] if _explicit_route_cycle(row) else [],
        "cut_points": ["missing_middle_or_cut_point"] if _missing_middle(row) else [],
        "knots": ["obligation_knot"] if _knot_without_unlinking(row) else [],
        "unlinking_moves": ["declared_unlinking_move"] if _safe_bool(row.get("unlinking_move_present")) else [],
        "agency_suppression_risk": _agency_suppression(row),
        "borromean_relation": borromean,
        "borromean_break_counted": bool(borromean["break_counted"]),
        "foreground_projection_tiny": True,
        "full_diagnostic_surface": "explain_debug_or_campus",
        "claim_permission": "navigation_only_not_fact",
        "source_reopen_required_before_claim": True,
        "topology_truth_source": False,
        "score_layer_changed": False,
    }


def fixture_packet_cases() -> list[dict[str, Any]]:
    return [
        {
            "case_id": "healthy_navigation_packet",
            "packet_type": "memory_packet",
            "output_mode": "reopenable_route",
            "authority_level": "navigation_only",
            "claim_permission": "no_claim_before_reopen",
            "source_ref_available": True,
        },
        {
            "case_id": "direction_only_used_as_evidence",
            "packet_type": "memory_packet",
            "output_mode": "direction_only",
            "authority_level": "navigation_only",
            "claim_permission": "no_claim_before_reopen",
            "rendered_as_evidence": True,
            "source_handle_rendered_as_fact": True,
        },
        {
            "case_id": "macro_rendered_as_action_instruction",
            "packet_type": "macro_orientation",
            "authority_level": "navigation_only",
            "action_grammar": "direction_only",
            "claim_permission": "no_claim_before_reopen",
            "rendered_as_action_instruction": True,
        },
        {
            "case_id": "dream_candidate_rendered_as_certainty",
            "packet_type": "dream_candidate",
            "authority": "dream_synthesized_candidate_not_fact",
            "rendered_as_certainty": True,
        },
        {
            "case_id": "narrative_missing_middle",
            "packet_type": "narrative_packet",
            "missing_middle": True,
            "pathlet_gap": "missing_middle",
        },
        {
            "case_id": "repeated_failed_route_cycle",
            "packet_type": "route_packet",
            "route_state": "rejected",
            "reopen_attempt_count": 3,
            "repeated_failed_route": True,
        },
        {
            "case_id": "overfiltered_useful_packet",
            "packet_type": "memory_packet",
            "useful_navigation_available": True,
            "foreground_suppressed": True,
        },
        {
            "case_id": "obligation_knot_without_unlinking",
            "packet_type": "aippo_activation",
            "authority": "candidate_not_fact",
            "obligation_count": 3,
            "unlinking_move_present": False,
        },
        {
            "case_id": "borromean_missing_source_side",
            "packet_type": "memory_packet",
            "foreground_visible": True,
            "task_anchor": "continue bounded route",
            "agent_agency_room": True,
            "authority_level": "navigation_only",
            "claim_permission": "no_claim_before_reopen",
        },
        {
            "case_id": "borromean_missing_user_need_side",
            "packet_type": "memory_packet",
            "foreground_visible": True,
            "source_refs": [{"source_id": "issue:#1548"}],
            "agent_agency_room": True,
            "authority_level": "navigation_only",
            "claim_permission": "no_claim_before_reopen",
        },
        {
            "case_id": "borromean_missing_agent_agency_side",
            "packet_type": "memory_packet",
            "action_shaping": True,
            "source_refs": [{"source_id": "issue:#1548"}],
            "task_anchor": "continue bounded route",
            "rendered_as_action_instruction": True,
            "authority_level": "navigation_only",
            "claim_permission": "no_claim_before_reopen",
        },
        {
            "case_id": "borromean_healthy_foreground_route",
            "packet_type": "memory_packet",
            "foreground_visible": True,
            "source_refs": [{"source_id": "issue:#1548"}],
            "task_anchor": "continue bounded route",
            "agent_agency_room": True,
            "authority_level": "navigation_only",
            "claim_permission": "no_claim_before_reopen",
        },
    ]


def build_packet_topology_report(
    rows: Iterable[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    row_list = list(rows) if rows is not None else fixture_packet_cases()
    diagnostics = [evaluate_packet(row) for row in row_list]
    counts: Counter[str] = Counter(item["diagnostic"] for item in diagnostics)
    boundary_counts: Counter[str] = Counter(
        crossing for item in diagnostics for crossing in item["boundary_crossings"]
    )
    provenance_counts: Counter[str] = Counter(
        item["diagnostic_provenance"] for item in diagnostics
    )
    forbidden_marker_count = sum(
        1
        for marker in FORBIDDEN_MARKERS
        if marker in json.dumps(diagnostics, ensure_ascii=False, sort_keys=True)
    )
    metrics = {
        "case_count": len(diagnostics),
        "navigation_as_claim_count": boundary_counts["navigation_as_claim"],
        "candidate_as_authority_count": boundary_counts["candidate_as_authority"],
        "macro_as_decision_count": boundary_counts["macro_as_decision"],
        "source_handle_as_fact_count": boundary_counts["source_handle_as_fact"],
        "agency_suppression_count": counts[AGENCY_SUPPRESSION],
        "knot_without_unlinking_move_count": counts[KNOT_WITHOUT_UNLINKING],
        "explicit_route_cycle_count": counts[ROUTE_CYCLE],
        "missing_middle_or_cut_point_count": counts[MISSING_MIDDLE],
        "healthy_relation_preserved_count": counts[RELATION_PRESERVED],
        "borromean_break_count": sum(
            1 for item in diagnostics if item["borromean_break_counted"]
        ),
        "reducer_derived_diagnostic_count": provenance_counts[REDUCER_BACKED],
        "producer_annotation_diagnostic_count": provenance_counts[ANNOTATION_BACKED],
    }
    red_lines = {
        "raw_private_text_emitted_count": forbidden_marker_count,
        "local_path_emitted_count": forbidden_marker_count,
        "source_handle_emitted_count": forbidden_marker_count,
        "default_foreground_full_diagnostic_count": 0,
        "topology_truth_source_count": 0,
    }
    expected = {
        AUTHORITY_OVERREACH,
        MISSING_MIDDLE,
        ROUTE_CYCLE,
        AGENCY_SUPPRESSION,
        KNOT_WITHOUT_UNLINKING,
        RELATION_PRESERVED,
    }
    contract_gate_ok = rows is not None or expected.issubset(set(counts))
    safety_gate_ok = all(value == 0 for value in red_lines.values())
    usefulness_gate_ok = metrics["agency_suppression_count"] == 0
    return {
        "kind": KIND,
        "diagnostic_kind": "packet_topology_diagnostic",
        "schema_version": SCHEMA_VERSION,
        "ok": contract_gate_ok and safety_gate_ok,
        "contract_gate_ok": contract_gate_ok,
        "safety_gate_ok": safety_gate_ok,
        "usefulness_gate_ok": usefulness_gate_ok,
        "runtime_boundary": "post_packet_explain_side",
        "every_turn_scan": False,
        "new_score_layer": False,
        "topology_is_truth_source": False,
        "default_foreground_projection": "tiny_tag_only_when_action_selection_changes",
        "diagnostics": diagnostics,
        "topology_primitive_registry": topology_primitive_registry(),
        "metrics": metrics,
        "red_lines": red_lines,
        "privacy_boundary": {
            "raw_private_text_emitted": False,
            "local_paths_emitted": False,
            "source_handles_emitted": False,
            "chain_of_thought_emitted": False,
            "forbidden_marker_count": forbidden_marker_count,
        },
        "contract": {
            "post_packet_diagnostic_only": True,
            "full_detail_belongs_to_explain_debug_or_campus": True,
            "macro_orientation_schema_not_redefined": True,
            "dream_topology_child_remains_candidate_only": True,
            "source_user_need_agent_agency_break_counted_only_when_visible": True,
            "primitive_provenance_declared": True,
            "producer_annotations_are_not_independent_discovery": True,
            "topology_names_shape_not_truth": True,
        },
        "cannot_claim": [
            "live_agent_lift",
            "broad_topology_quality",
            "automatic_ground_truth_discovery",
            "macro_orientation_correctness",
            "dream_candidate_truth",
            "sheaf_style_packet_compatibility",
        ],
    }


def load_rows(path: Path) -> list[Mapping[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return [item for item in data if isinstance(item, Mapping)]
    if isinstance(data, Mapping):
        raw_rows = data.get("cases") or data.get("rows") or data.get("packets") or []
        return [item for item in raw_rows if isinstance(item, Mapping)]
    return []


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", help="JSON file with packet rows or cases.")
    parser.add_argument("--fixture", action="store_true", help="Use the built-in fixture.")
    parser.add_argument("--json", action="store_true", help="Emit JSON report.")
    args = parser.parse_args(argv)

    rows = load_rows(Path(args.input)) if args.input else None
    report = build_packet_topology_report(rows)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print("packet topology: " + ("ok" if report["ok"] else "diagnostics_found"))
        print(f"metrics: {report['metrics']}")
    return 0 if report["safety_gate_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
