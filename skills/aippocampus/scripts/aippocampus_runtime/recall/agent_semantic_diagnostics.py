"""Optional semantic-gate sidecar for explicit agent recall."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any


def _semantic_decision(surface: Mapping[str, Any]) -> str:
    details = surface.get("details")
    if isinstance(details, Mapping) and str(details.get("decision") or "").strip():
        return str(details.get("decision") or "").strip()
    if str(surface.get("decision") or "").strip():
        return str(surface.get("decision") or "").strip()
    status = str(surface.get("status") or "").strip()
    if status in {"degraded", "unavailable", "skipped", "skip"}:
        return status
    return "not_reported"


DEGRADED_REASON_CODES = {
    "semantic_provider_timeout",
    "semantic_unavailable_missing_auth",
    "semantic_unavailable",
    "semantic_disabled_by_operator",
}


def _degraded_reason(reason_codes: list[str]) -> str | None:
    for code in reason_codes:
        if code in DEGRADED_REASON_CODES:
            return code
    return None


def _semantic_contribution(
    *,
    semantic_decision: str,
    status: str,
    degraded_reason: str | None = None,
) -> str:
    decision = semantic_decision.casefold()
    if degraded_reason == "semantic_provider_timeout":
        return "none_semantic_timeout"
    if degraded_reason:
        return "none_semantic_unavailable_or_skipped"
    if status in {"degraded", "unavailable"} or decision in {"skip", "skipped", "degraded"}:
        return "none_semantic_unavailable_or_skipped"
    if decision in {"background_only", "not_reported"}:
        return "diagnostic_only_no_selected_route_change"
    if decision in {"scent", "evidence", "surfaced"}:
        return "semantic_sidecar_returned_navigation_signal"
    return "diagnostic_only_no_selected_route_change"


def agent_semantic_gate_diagnostics(
    *,
    query: str,
    cwd: Path,
    clean_source_dir: Path,
    registry_dir: Path | None,
    max_routes: int,
    run_semantic_gate: bool,
    semantic_gate_mode: str,
    semantic_timeout: int,
) -> dict[str, Any] | None:
    mode = str(semantic_gate_mode or "off").strip().casefold()
    if mode not in {"off", "auto", "on"}:
        mode = "off"
    should_run = bool(run_semantic_gate or mode in {"auto", "on"})
    if not should_run:
        return None
    from aippocampus_runtime.recall.why_diagnostics import recall_diagnostic_report  # noqa: PLC0415

    report = recall_diagnostic_report(
        cue=query,
        mode="why-recall",
        cwd=cwd,
        clean_source_dir=clean_source_dir,
        registry_dir=registry_dir,
        max_routes=max_routes,
        run_live_semantic_gate=True,
        semantic_gate_mode=mode,
        semantic_timeout=semantic_timeout,
    )
    surfaces = [
        surface
        for surface in report.get("surface_reports") or []
        if isinstance(surface, Mapping) and surface.get("surface") == "semantic_gate"
    ]
    surface = surfaces[0] if surfaces else {}
    reason_codes = list(surface.get("reason_codes") or [])[:6]
    degraded_reason = _degraded_reason([str(code) for code in reason_codes])
    status = str(surface.get("status") or "not_run")
    semantic_decision = _semantic_decision(surface)
    if degraded_reason:
        status = "degraded"
        semantic_decision = "degraded"
    return {
        "requested": True,
        "mode": mode,
        "timeout_seconds": semantic_timeout,
        "overall_recall_diagnostic": {
            "decision": report.get("decision"),
            "reasons": list(report.get("reasons") or [])[:6],
            "next_safe_action": report.get("next_safe_action"),
        },
        "semantic_sidecar": {
            "status": status,
            "decision": semantic_decision,
            "reason_codes": reason_codes,
            "contribution": _semantic_contribution(
                semantic_decision=semantic_decision,
                status=status,
                degraded_reason=degraded_reason,
            ),
        },
        "agent_next_action": report.get("next_safe_action"),
        "semantic_surface": surface,
        "boundary": "diagnostic_sidecar_only_not_route_truth",
    }
