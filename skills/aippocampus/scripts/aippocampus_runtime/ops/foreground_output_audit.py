"""No-write foreground output audit for agency-preserving memory packets."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

SURFACE_KINDS = ("hook", "active_recall", "aippo", "router", "bounded_summary", "macro")
SAFE_NEXT_ACTIONS = {
    "use_hint",
    "reopen_source",
    "deepen",
    "ask_light_question",
    "stay_silent",
}


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _audit_matrix(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    by_kind = {str(row.get("surface_kind")): row for row in rows}
    matrix: list[dict[str, Any]] = []
    for kind in SURFACE_KINDS:
        row = by_kind.get(kind, {})
        matrix.append(
            {
                "surface_kind": kind,
                "covered": bool(row),
                "checks": [
                    "authority_overreach",
                    "creativity_suppression",
                    "decision_language",
                    "information_density",
                    "deepen_or_explain_boundary",
                ],
                "allowed_next_actions": sorted(SAFE_NEXT_ACTIONS),
                "uses_route_material_not_decision": bool(
                    row.get("uses_route_material_not_decision", True)
                ),
            }
        )
    return matrix


def build_foreground_output_audit_report(
    *,
    surface_rows: Sequence[Mapping[str, Any]],
    fixture_cases: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    cases = [dict(case) for case in fixture_cases]
    matrix = _audit_matrix(surface_rows)
    overreach = sum(1 for case in cases if case.get("overreach_axis"))
    overfilter = sum(1 for case in cases if case.get("overfilter_axis"))
    healthy = sum(
        1
        for case in cases
        if case.get("agency_gate_ok")
        and case.get("usefulness_gate_ok")
        and case.get("candidate_material_visible_as_candidate")
    )
    red_lines = {
        # The fixture includes a bad pre-rewrite packet, but the emitted
        # remediated foreground language must be route/material language only.
        "decision_language_in_navigation_packet_count": sum(
            1
            for case in cases
            if case.get("emitted_after_remediation")
            and case.get("next_action") not in SAFE_NEXT_ACTIONS
        ),
        "raw_source_or_private_payload_leak_count": sum(
            1 for case in cases if case.get("raw_payload_leaked")
        ),
        "source_claim_without_reopen_count": sum(
            1 for case in cases if case.get("claim_ready") and not case.get("source_open")
        ),
    }
    metrics = {
        "audit_surface_count": sum(1 for row in matrix if row["covered"]),
        "authority_overreach_count": overreach,
        "creativity_suppression_count": overfilter,
        "agency_preserving_packet_count": healthy,
        "strong_material_without_forced_conclusion_count": sum(
            1 for case in cases if case.get("strong_material") and case.get("agency_gate_ok")
        ),
        "macro_recheck_pressure_without_decision_count": sum(
            1
            for case in cases
            if case.get("surface_kind") == "macro"
            and case.get("next_action") == "reopen_source"
            and not case.get("decides_user_need")
        ),
    }
    return {
        "kind": "aippocampus_foreground_output_audit",
        "schema_version": 1,
        "audit_matrix": matrix,
        "fixture_cases": cases,
        "metrics": metrics,
        "red_lines": red_lines,
        "ok": all(row["covered"] for row in matrix)
        and all(value == 0 for value in red_lines.values())
        and healthy > 0,
        "contract": {
            "memory_expands_agent_agency": True,
            "candidate_material_remains_available_without_fact_claims": True,
            "deepen_and_explain_hold_protocol_diagnostics": True,
            "audit_is_no_write": True,
        },
        "privacy_boundary": {
            "raw_prompt_serialized": False,
            "raw_source_text_serialized": False,
            "local_paths_serialized": False,
        },
    }


def build_foreground_output_audit_fixture_report() -> dict[str, Any]:
    surface_rows = [
        {"surface_kind": kind, "uses_route_material_not_decision": True}
        for kind in SURFACE_KINDS
    ]
    fixture_cases = [
        {
            "case_id": "overreaching_packet",
            "surface_kind": "router",
            "overreach_axis": True,
            "agency_gate_ok": False,
            "usefulness_gate_ok": True,
            "pre_rewrite_next_action": "decide_user_next_need",
            "next_action": "deepen",
            "emitted_after_remediation": True,
            "strong_material": True,
        },
        {
            "case_id": "overfiltered_packet",
            "surface_kind": "active_recall",
            "overfilter_axis": True,
            "agency_gate_ok": True,
            "usefulness_gate_ok": False,
            "next_action": "stay_silent",
            "candidate_material_hidden": True,
            "safety_gate_ok": True,
        },
        {
            "case_id": "healthy_navigation_packet",
            "surface_kind": "aippo",
            "agency_gate_ok": True,
            "usefulness_gate_ok": True,
            "next_action": "use_hint",
            "strong_material": True,
            "candidate_material_visible_as_candidate": True,
            "fact_claim_allowed": False,
        },
        {
            "case_id": "macro_recheck_pressure",
            "surface_kind": "macro",
            "agency_gate_ok": True,
            "usefulness_gate_ok": True,
            "next_action": "reopen_source",
            "decides_user_need": False,
            "strong_material": False,
        },
    ]
    return build_foreground_output_audit_report(
        surface_rows=surface_rows,
        fixture_cases=fixture_cases,
    )


__all__ = [
    "build_foreground_output_audit_fixture_report",
    "build_foreground_output_audit_report",
]
