"""Compact foreground projection for spend doctor reports."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from aippocampus_runtime import core as runtime_core
from aippocampus_runtime.contracts import canonical_foreground_action_fields

SCHEMA_VERSION = 1


def _safe_int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _primary_spend_action(decision: Mapping[str, Any]) -> dict[str, Any]:
    action = str(decision.get("action") or "continue")
    warm_queue = (
        decision.get("warm_queue_health")
        if isinstance(decision.get("warm_queue_health"), Mapping)
        else {}
    )
    if warm_queue.get("status") == "blocked":
        return {
            "id": "inspect_warm_ambient_queue",
            "label": "Inspect blocked warm ambient queue",
            "command": str(warm_queue.get("status_command") or "aippocampus warm status --json"),
            "route": "warm_ambient",
            "queue_state": warm_queue.get("queue_state"),
            "pending_stale_count": _safe_int(warm_queue.get("pending_stale_count")),
            "why": "Warm ambient queue health is blocked or stale; inspect warm status before more optional warming.",
            "mutation_risk": "read_only",
            "claim_boundary": "operator_diagnostic_not_source_evidence",
        }
    command = str(decision.get("safe_next_command") or "aippocampus doctor spend --detail full --json")
    routes = [str(route) for route in decision.get("routes_to_pause_or_inspect") or []]
    if action == "inspect":
        lowest_yield = (
            decision.get("lowest_yield_route")
            if isinstance(decision.get("lowest_yield_route"), Mapping)
            else {}
        )
        route = routes[0] if routes else str(lowest_yield.get("route") or "unknown")
        return {
            "id": "inspect_spend_route",
            "label": "Inspect high-spend low-yield route",
            "command": command,
            "route": route,
            "why": (
                "A route crossed the spend threshold with low foreground follow-through; "
                "open the explicit operator report before launching more background work."
            ),
            "mutation_risk": "read_only",
            "claim_boundary": "operator_diagnostic_not_source_evidence",
        }
    if action == "inspect_usage":
        return {
            "id": "inspect_usage_telemetry",
            "label": "Inspect missing usage telemetry",
            "command": command,
            "routes": [str(route) for route in decision.get("usage_telemetry_gaps") or []],
            "why": "Some local artifacts do not expose usage, so spend cannot be judged from local records.",
            "mutation_risk": "read_only",
            "claim_boundary": "operator_diagnostic_not_source_evidence",
        }
    return {
        "id": "continue_with_spend_guardrails",
        "label": "Continue with current spend guardrails",
        "next_step": "continue_current_task",
        "continue_without_command": True,
        "no_command_needed": True,
        "why": str(
            decision.get("reason")
            or "No local spend/yield warning crossed the configured thresholds."
        ),
        "mutation_risk": "read_only",
        "claim_boundary": "operator_diagnostic_not_source_evidence",
    }


def compact_spend_doctor_card(report: Mapping[str, Any]) -> dict[str, Any]:
    """Project the operator spend report into the default foreground JSON card."""

    decision = report.get("decision") if isinstance(report.get("decision"), Mapping) else {}
    totals = report.get("totals") if isinstance(report.get("totals"), Mapping) else {}
    spend = totals.get("spend") if isinstance(totals.get("spend"), Mapping) else {}
    route_scan = (
        report.get("route_artifact_scan")
        if isinstance(report.get("route_artifact_scan"), Mapping)
        else {}
    )
    scan_status = str(route_scan.get("status") or "complete")
    effective_tokens_known = bool(route_scan.get("effective_tokens_known", scan_status == "complete"))
    warning_codes = [str(code) for code in report.get("warning_codes") or []]
    routes_to_inspect = [str(route) for route in decision.get("routes_to_pause_or_inspect") or []]
    primary_action = _primary_spend_action(decision)
    detail_action = {
        "id": "open_full_spend_report",
        "label": "Open full spend report",
        "command": "aippocampus doctor spend --detail full --json",
        "mutation_risk": "read_only",
        "claim_boundary": "operator_diagnostic_not_source_evidence",
        "why": "Use the operator report only when route-level telemetry or cost basis details are needed.",
    }
    payload = {
        "schema_version": SCHEMA_VERSION,
        "kind": "aippocampus_spend_doctor_card",
        "ok": bool(report.get("ok", True)),
        "status": str(report.get("status") or "ok"),
        "detail": "compact",
        "surface": "foreground_decision_card",
        "generated_at": report.get("generated_at"),
        "window": report.get("window") or {},
        "summary": {
            "effective_tokens": _safe_int(spend.get("effective_tokens")),
            "effective_tokens_known": effective_tokens_known,
            "request_count": _safe_int(spend.get("request_count")),
            "warning_count": len(warning_codes),
            "scan_status": scan_status,
        },
        "decision": {
            "action": decision.get("action"),
            "reason": decision.get("reason"),
            "safe_next_command": decision.get("safe_next_command"),
            "highest_spend_route": decision.get("highest_spend_route"),
            "lowest_yield_route": decision.get("lowest_yield_route"),
            "warm_queue_health": decision.get("warm_queue_health") or {},
            "usage_telemetry_gaps": decision.get("usage_telemetry_gaps") or [],
            "estimated_cost_supported": bool(decision.get("estimated_cost_supported")),
            "cost_basis": decision.get("cost_basis"),
            "cost_explanation": decision.get("cost_explanation"),
        },
        **canonical_foreground_action_fields(
            primary_action,
            safe_next_actions=[primary_action, detail_action],
        ),
        "routes_to_pause_or_inspect": routes_to_inspect,
        "warning_codes": warning_codes,
        "route_artifact_scan": route_scan,
        "privacy_boundary": report.get("privacy_boundary") or {},
        "reporting_boundary": report.get("reporting_boundary") or {},
        "operator_json_available": {
            "detail_full_command": "aippocampus doctor spend --detail full --json",
            "operator_json_command": "aippocampus doctor spend --operator-json",
        },
        "claim_boundary": {
            "can_use_for": "foreground spend/navigation decision",
            "must_open_operator_report_for": "route-level telemetry and billing-cost details",
            "not_source_evidence": True,
        },
    }
    return runtime_core.sanitize_external_model_payload(payload)
