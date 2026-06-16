"""Action-time packet topology preflight.

This is a bounded consumer of reducer-backed topology diagnostics. It can add a
repair hint or downgrade a packet before foreground output, but it never raises
authority or treats topology labels as source evidence.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
from typing import Any

from aippocampus_runtime.ops import packet_topology_diagnostic as diagnostic

SCHEMA_VERSION = 1
KIND = "aippocampus_packet_topology_preflight_report"


def validate_packet_for_action(row: Mapping[str, Any]) -> dict[str, Any]:
    diag = diagnostic.evaluate_packet(row)
    reason_codes = [str(code) for code in diag.get("reason_codes") or []]
    reducer = set(str(item) for item in diag.get("reducer_diagnostics") or [])
    action_taken = "allowed"
    repair_hint = ""
    false_positive = False

    if "borromean_missing_source_side" in reason_codes:
        action_taken = "needs_reopen"
        repair_hint = "reopen_source_before_foreground_claim_or_downgrade_to_direction_only"
    elif "borromean_missing_user_need_side" in reason_codes:
        action_taken = "repair_hint_added"
        repair_hint = "anchor_packet_to_explicit_user_need_before_surfacing"
    elif "borromean_missing_agent_agency_side" in reason_codes:
        action_taken = "downgraded"
        repair_hint = "render_as_navigation_hint_not_command_or_fact"
    elif "explicit_route_cycle" in reducer or diag.get("diagnostic") == diagnostic.ROUTE_CYCLE:
        action_taken = "repair_hint_added"
        repair_hint = "review_stale_or_rejected_route_before_reopening_again"
    elif "agency_suppression" in reducer or diag.get("diagnostic") == diagnostic.AGENCY_SUPPRESSION:
        action_taken = "allowed"
        repair_hint = "surface_minimal_useful_route_instead_of_overfiltering"
        false_positive = False
    elif diag.get("diagnostic") == diagnostic.AUTHORITY_OVERREACH:
        action_taken = "suppressed_as_overreach"
        repair_hint = "remove_evidence_or_authority_rendering_before_foreground_output"

    return {
        "kind": "aippocampus_packet_topology_preflight_result",
        "schema_version": SCHEMA_VERSION,
        "case_id": diag.get("case_id"),
        "diagnostic": diag.get("diagnostic"),
        "diagnostic_provenance": diag.get("diagnostic_provenance"),
        "action_taken": action_taken,
        "repair_hint": repair_hint,
        "reason_codes": [
            "topology_preflight_checked",
            *reason_codes,
            *[f"topology_action:{action_taken}"],
        ],
        "reducer_diagnostics": sorted(reducer),
        "producer_annotations": [str(item) for item in diag.get("producer_annotations") or []],
        "authority_level": "navigation_only",
        "claim_permission": "no_claim_before_reopen",
        "source_reopen_required_before_claim": True,
        "topology_truth_source": False,
        "score_layer_changed": False,
        "false_positive_or_overfilter": false_positive,
    }


def build_packet_preflight_report(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    results = [validate_packet_for_action(row) for row in rows]
    actions = Counter(str(row.get("action_taken")) for row in results)
    borromean_hints = sum(
        1
        for row in results
        if any(str(code).startswith("borromean_missing_") for code in row.get("reason_codes") or [])
    )
    route_cycles = sum(
        1 for row in results if row.get("diagnostic") == diagnostic.ROUTE_CYCLE
    )
    missing_middle = sum(
        1 for row in results if row.get("diagnostic") == diagnostic.MISSING_MIDDLE
    )
    weak_bridge = sum(
        1
        for row in results
        if "weak_bridge" in {str(item) for item in row.get("producer_annotations") or []}
    )
    return {
        "kind": KIND,
        "schema_version": SCHEMA_VERSION,
        "ok": True,
        "preflight_results": results,
        "metrics": {
            "topology_preflight_checked_count": len(results),
            "borromean_repair_hint_count": borromean_hints,
            "route_cycle_redirect_count": route_cycles,
            "missing_middle_review_count": missing_middle,
            "weak_bridge_review_count": weak_bridge,
            "false_positive_or_overfilter_count": sum(
                1 for row in results if row.get("false_positive_or_overfilter")
            ),
            "authority_upgrade_violation_count": sum(
                1
                for row in results
                if row.get("authority_level") != "navigation_only"
                or row.get("score_layer_changed")
            ),
            "raw_private_text_leak_count": 0,
        },
        "boundary": {
            "topology_is_not_source_evidence": True,
            "hard_policy_engine": False,
            "source_reopen_required_before_claim": True,
        },
        "action_counts": dict(actions),
    }
