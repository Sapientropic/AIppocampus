"""Shared first-recall readiness phases for foreground cards."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Mapping

EXPECTATIONS = {
    "cold_start_maintenance_required": (
        "Required source/index artifacts are missing or degraded; apply the "
        "next maintenance action before expecting private recall."
    ),
    "cold_start_no_current_thread": (
        "No current thread source is available in this cwd; open/register a "
        "thread or run registry-wide health before expecting private recall."
    ),
    "steady_state_with_live_delta": (
        "Ordinary recall can continue; refresh before relying on the latest "
        "current-thread details."
    ),
    "steady_state_latest_degraded": (
        "Ordinary recall can continue from existing artifacts; refresh before "
        "exact latest claims."
    ),
    "steady_state_available": (
        "Ordinary source-backed recall/search can continue from existing artifacts."
    ),
    "cold_start_or_maintenance_required": (
        "Required source/index artifacts are missing or degraded; apply maintenance "
        "before expecting private recall."
    ),
}


def health_readiness_fields(
    *,
    maintenance_required_before_recall: bool,
    live_delta_tolerated: bool,
    freshness_degraded: bool,
) -> dict[str, Any]:
    if maintenance_required_before_recall:
        phase = "cold_start_maintenance_required"
    elif live_delta_tolerated:
        phase = "steady_state_with_live_delta"
    elif freshness_degraded:
        phase = "steady_state_latest_degraded"
    else:
        phase = "steady_state_available"
    return {
        "first_recall_phase": phase,
        "cold_start_expected": bool(maintenance_required_before_recall),
        "first_recall_expectation": EXPECTATIONS[phase],
    }


def missing_rollout_readiness_fields() -> dict[str, Any]:
    phase = "cold_start_no_current_thread"
    return {
        "first_recall_phase": phase,
        "cold_start_expected": True,
        "first_recall_expectation": EXPECTATIONS[phase],
    }


def compact_health_first_recall_fields(
    readiness: Mapping[str, Any] | None,
    *,
    ordinary_usable: bool,
    freshness_degraded: bool,
) -> dict[str, Any]:
    phase = str((readiness or {}).get("first_recall_phase") or "")
    if not phase:
        if ordinary_usable and freshness_degraded:
            phase = "steady_state_latest_degraded"
        elif ordinary_usable:
            phase = "steady_state_available"
        else:
            phase = "cold_start_or_maintenance_required"
    cold = (
        bool(readiness.get("cold_start_expected"))
        if readiness and "cold_start_expected" in readiness
        else not ordinary_usable
    )
    return {"first_recall_phase": phase, "cold_start_expected": cold}


def maintenance_impact_readiness_fields(
    readiness: Mapping[str, Any] | None,
    *,
    fallback_phase: str,
    fallback_cold_start: bool,
) -> dict[str, Any]:
    source = readiness or {}
    phase = str(source.get("first_recall_phase") or fallback_phase)
    fields = {
        "first_recall_phase": phase,
        "cold_start_expected": bool(source.get("cold_start_expected", fallback_cold_start)),
    }
    expectation = str(source.get("first_recall_expectation") or EXPECTATIONS.get(phase) or "")
    if expectation:
        fields["first_recall_expectation"] = expectation
    return fields


def compact_start_first_recall_readiness(readiness: Mapping[str, Any]) -> dict[str, Any]:
    """Project start readiness as a foreground summary, not a diagnostic ledger.

    The start card is the CLI front door. It should tell the next agent whether
    ordinary recall is usable and what the first action is, while full/operator
    detail keeps source artifact inventories, cue-specific probes, and freshness
    diagnostics. Keep this helper small so future readiness fields do not leak
    into compact output by default.
    """

    always_keys = (
        "phase",
        "status",
        "next_action_id",
        "ordinary_first_recall_usable",
        "private_source_ready",
        "cold_start_expected",
        "progress_signal",
        "user_expectation",
        "claim_boundary",
    )
    result = {
        key: readiness[key]
        for key in always_keys
        if key in readiness and readiness[key] not in (None, "", [], {})
    }
    optional_when_present = (
        "read_only_probe_available",
        "public_demo_available",
        "freshness_degraded",
        "source_stale",
        "latest_current_thread_may_be_missing",
        "blocks_exact_latest_claims",
        "maintenance_recommended_before_exact_latest",
    )
    for key in optional_when_present:
        value = readiness.get(key)
        if value:
            result[key] = value
    if not result.get("ordinary_first_recall_usable") and "requires_user_consent_for_writes" in readiness:
        result["requires_user_consent_for_writes"] = bool(
            readiness.get("requires_user_consent_for_writes")
        )
    return result


def start_first_recall_readiness_diagnostic(
    readiness: Mapping[str, Any],
    *,
    source_state: Mapping[str, Any],
    cue_specific: Mapping[str, Any],
    cue_supplied: bool,
    actions: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Attach full start-readiness diagnostics for operator/detail output."""

    result = dict(readiness)
    result.update(
        {
            "ordinary_first_recall_usable_scope": (
                "cue_action_callable_not_previewed"
                if cue_supplied
                else "artifact_level_not_cue_specific"
            ),
            "source_artifacts_present": bool(source_state.get("exists")),
            "exact_source_search_available": bool(source_state.get("exists")),
            "compact_agent_recall_action_callable": bool(
                cue_supplied
                and any(
                    action.get("id") in {"recall_supplied_cue", "try_first_recall"}
                    and str(action.get("command") or "").startswith("aippocampus ")
                    for action in actions
                )
            ),
            "cue_specific_route_usefulness": dict(cue_specific),
            "warm_or_ambient_degraded_is_optional": True,
            "source_stale_scope": str(source_state.get("freshness_scope") or "manifest_only"),
            "manifest_stale": bool(source_state.get("manifest_stale")),
            "latest_current_thread_may_be_missing": bool(
                result.get("latest_current_thread_may_be_missing")
                or source_state.get("latest_source_may_be_missing")
            ),
            "workspace_source_maintenance_required": bool(
                source_state.get("workspace_source_maintenance_required")
            ),
            "blocks_exact_latest_claims": bool(
                result.get("blocks_exact_latest_claims")
                or source_state.get("blocks_exact_latest_claims")
            ),
            "maintenance_recommended_before_exact_latest": bool(
                result.get("maintenance_recommended_before_exact_latest")
                or source_state.get("workspace_source_maintenance_required")
            ),
        }
    )
    return result


def start_first_recall_readiness(
    *,
    decision: str,
    source_exists: bool,
    source_stale: bool,
    action_id: str,
) -> dict[str, Any]:
    base = {
        "next_action_id": action_id,
        "source_registered": bool(source_exists),
        "source_stale": bool(source_stale),
        "requires_user_consent_for_writes": True,
        "claim_boundary": "readiness_is_operational_status_not_source_evidence",
    }
    by_decision: dict[str, dict[str, Any]] = {
        "continue_from_existing_source": {
            "phase": "steady_state_available",
            "status": "ready",
            "ordinary_first_recall_usable": True,
            "private_source_ready": True,
            "cold_start_expected": False,
            "progress_signal": "clean_source_available",
            "user_expectation": (
                "Existing source is available; start with recall/deepen and keep "
                "exact or sensitive claims source-open."
            ),
            "performance_expectation": {
                "mode": "steady_state",
                "message": "Recall should stay on the established local route; deepen may reopen source.",
            },
        },
        "continue_from_existing_source_with_search_fallback": {
            "phase": "steady_state_available",
            "status": "ready_with_low_specificity_fallback",
            "ordinary_first_recall_usable": True,
            "private_source_ready": True,
            "cold_start_expected": False,
            "progress_signal": "clean_source_available_search_fallback_first",
            "user_expectation": (
                "Existing source is available, but the supplied cue looks low-specificity; "
                "start with source search or a concrete recall command, then deepen before claims."
            ),
            "performance_expectation": {
                "mode": "steady_state",
                "message": (
                    "Source search can be more useful than compact recall for weak cues; "
                    "recall remains available after tightening the cue."
                ),
            },
        },
        "continue_from_existing_source_latest_degraded": {
            "phase": "steady_state_latest_degraded",
            "status": "ready_with_freshness_degraded",
            "ordinary_first_recall_usable": True,
            "private_source_ready": True,
            "cold_start_expected": False,
            "progress_signal": "source_exists_but_stale",
            "freshness_degraded": True,
            "latest_current_thread_may_be_missing": True,
            "blocks_exact_latest_claims": True,
            "maintenance_recommended_before_exact_latest": True,
            "user_expectation": (
                "Existing source is usable for ordinary recall, but maintenance should run "
                "before exact latest/current-thread claims."
            ),
            "performance_expectation": {
                "mode": "steady_state_latest_degraded",
                "message": (
                    "Recall can use established artifacts; refresh source/index artifacts "
                    "before relying on latest current-thread details."
                ),
            },
        },
        "try_read_only_continuity_before_setup": {
            "phase": "cold_start_probe_or_public_demo",
            "status": "probe_only_until_source_found",
            "ordinary_first_recall_usable": False,
            "private_source_ready": False,
            "read_only_probe_available": True,
            "public_demo_available": True,
            "cold_start_expected": True,
            "progress_signal": "trusted_cli_available_source_not_confirmed",
            "user_expectation": (
                "A read-only recall or public fixture demo can be tried, but private "
                "memory is not ready until local source is found or registered."
            ),
            "performance_expectation": {
                "mode": "first_run_probe",
                "message": (
                    "First setup may need registration or index preparation; future "
                    "recall is faster once source artifacts exist."
                ),
            },
        },
    }
    fallback = {
        "phase": "cold_start_setup_required",
        "status": "needs_source_registration",
        "ordinary_first_recall_usable": False,
        "private_source_ready": False,
        "cold_start_expected": True,
        "progress_signal": "no_clean_source_registered",
        "user_expectation": (
            "No local clean source is ready; preview or run an explicit registration "
            "command before expecting private recall."
        ),
        "performance_expectation": {
            "mode": "cold_start_setup",
            "message": (
                "The first useful recall may spend time building source/index artifacts; "
                "steady-state recall is faster after that setup exists."
            ),
        },
    }
    return {**base, **by_decision.get(decision, fallback)}
