#!/usr/bin/env python3
"""Foreground projection helpers for maintenance status cards."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from aippocampus_runtime.contracts import canonical_foreground_action_fields
from aippocampus_runtime.first_recall_readiness import maintenance_impact_readiness_fields
from aippocampus_runtime.privacy import LOCAL_PATH_REDACTION

APPLY_SUMMARY_COMMAND = "aippocampus maintenance apply --summary-json"
PLAN_SUMMARY_COMMAND = "aippocampus maintenance plan --summary-json"
STATUS_SUMMARY_COMMAND = "aippocampus maintenance status --summary-json"
STATUS_COMMAND = "aippocampus maintenance status --json"
STORAGE_GC_BOUNDED_AUDIT_COMMAND = "aippocampus storage gc --dry-run --json --top 1 --cwd ."
INTERRUPTED_WRITE_CLEANUP_COMMAND = (
    "aippocampus maintenance apply --cleanup-interrupted-writes --summary-json"
)


def unique_action_ids(action_ids: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for action_id in action_ids:
        clean = str(action_id or "").strip()
        if not clean or clean in seen:
            continue
        seen.add(clean)
        result.append(clean)
    return result


def health_maintenance_status(health: dict | None) -> str:
    if not health:
        return "unavailable"
    readiness = health.get("product_readiness") or {}
    if isinstance(readiness, dict) and readiness:
        if readiness.get("maintenance_required_before_recall"):
            return "attention_needed"
        if readiness.get("maintenance_recommended"):
            return "degraded"
        if readiness.get("ordinary_first_recall_usable") or readiness.get("ready"):
            return "ok"
    status = str(health.get("status") or "").strip()
    if status:
        return status
    return "ok" if health.get("ok") else "attention_needed"


def health_maintenance_ok(health: dict | None) -> bool:
    if not health:
        return False
    readiness = health.get("product_readiness") or {}
    if isinstance(readiness, dict) and readiness:
        return bool(
            readiness.get("ordinary_first_recall_usable")
            and not readiness.get("maintenance_required_before_recall")
        )
    if not bool(health.get("ok")):
        return False
    return not any(
        item.get("severity") in {"critical", "warning"}
        for item in health.get("recommended_actions", []) or []
        if isinstance(item, dict)
    )


def public_action_command(action_id: str) -> str | None:
    if action_id == "checkpoint":
        return "aippocampus maintenance apply --append-checkpoint --summary-json"
    if action_id == "storage_gc_rebuildable_cache":
        return STORAGE_GC_BOUNDED_AUDIT_COMMAND
    if action_id == "cleanup_interrupted_writes":
        return INTERRUPTED_WRITE_CLEANUP_COMMAND
    if action_id in {
        "build_clean_source",
        "build_index",
        "build_segments",
        "build_cognitive_map",
        "prepare_graphify_corpus",
    }:
        return APPLY_SUMMARY_COMMAND
    return None


def public_recommended_action(item: dict) -> dict:
    action_id = str(item.get("id") or "")
    result = {
        "id": action_id,
        "severity": item.get("severity"),
        "reason": item.get("reason"),
    }
    command = public_action_command(action_id)
    if command:
        result["command"] = command
        if command == STORAGE_GC_BOUNDED_AUDIT_COMMAND:
            result["mutation_risk"] = "read_only"
        elif command == INTERRUPTED_WRITE_CLEANUP_COMMAND:
            result["mutation_risk"] = "explicit_local_delete_of_ai_owned_tmp_artifacts"
            result["requires_user_consent"] = True
        else:
            result["mutation_risk"] = "explicit_generated_artifact_write"
            result["requires_user_consent"] = True
    else:
        result["operator_boundary"] = "inspect the full audit before acting on this item"
    return {key: value for key, value in result.items() if value not in (None, "", [])}


def _read_only_plan_action() -> dict[str, Any]:
    return {
        "id": "review_maintenance_plan",
        "label": "Review maintenance plan",
        "kind": "shell_command",
        "command": PLAN_SUMMARY_COMMAND,
        "mutates": False,
        "mutation_risk": "read_only",
        "claim_boundary": "maintenance_plan_not_memory_evidence",
        "why": "Review generated-artifact maintenance before any write-capable apply.",
        "reason": "review generated-artifact maintenance before any write-capable apply",
    }


def _apply_with_consent_action() -> dict[str, Any]:
    return {
        "id": "apply_after_user_consent",
        "label": "Apply after user consent",
        "kind": "shell_command",
        "command": APPLY_SUMMARY_COMMAND,
        "mutates": True,
        "mutation_risk": "explicit_generated_artifact_write",
        "claim_boundary": "maintenance_action_not_memory_evidence",
        "why": "Apply only after reviewing the plan and confirming local generated-artifact writes are intended.",
        "requires_user_consent": True,
        "requires_clean_or_intentionally_dirty_worktree": True,
        "preflight_commands": ["git status --short"],
        "reason": "apply only after reviewing the plan and confirming local generated-artifact writes are intended",
    }


def _storage_gc_audit_action(command: str = STORAGE_GC_BOUNDED_AUDIT_COMMAND) -> dict[str, Any]:
    return {
        "id": "storage_gc_audit",
        "label": "Audit storage cleanup",
        "kind": "shell_command",
        "command": command,
        "mutates": False,
        "mutation_risk": "read_only",
        "claim_boundary": "storage_pressure_not_memory_evidence",
        "why": "Audit generated-cache pressure before any storage cleanup apply.",
        "reason": "audit generated-cache pressure before any storage cleanup apply",
    }


def _continue_without_maintenance_action(best: dict) -> dict[str, Any]:
    return {
        "id": "continue_without_maintenance",
        "label": "Continue without maintenance",
        "decision": "continue",
        "mutates": False,
        "mutation_risk": "read_only",
        "claim_boundary": "maintenance_status_not_memory_evidence",
        "continue_without_command": True,
        "why": str(
            best.get("reason")
            or "No blocking maintenance action is currently recommended."
        ),
        "reason": str(
            best.get("reason")
            or "No blocking maintenance action is currently recommended."
        ),
    }


def maintenance_safe_next_actions(best: dict, *, read_only: bool) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    if str(best.get("id") or "") == "continue":
        if read_only:
            actions.append(_continue_without_maintenance_action(best))
            actions.append(_read_only_plan_action())
        else:
            actions.append(
                {
                    "id": "inspect_maintenance_status",
                    "label": "Inspect maintenance status",
                    "kind": "shell_command",
                    "command": STATUS_SUMMARY_COMMAND,
                    "mutates": False,
                    "mutation_risk": "read_only",
                    "claim_boundary": "maintenance_status_not_memory_evidence",
                    "why": "Inspect the post-apply maintenance state without writing.",
                    "reason": "inspect the post-apply maintenance state without writing",
                }
            )
        return actions
    if read_only:
        actions.append(_read_only_plan_action())
        actions.append(_apply_with_consent_action())
    else:
        actions.append(
            {
                "id": "inspect_maintenance_status",
                "label": "Inspect maintenance status",
                "kind": "shell_command",
                "command": STATUS_SUMMARY_COMMAND,
                "mutates": False,
                "mutation_risk": "read_only",
                "claim_boundary": "maintenance_status_not_memory_evidence",
                "why": "Inspect the post-apply maintenance state without writing.",
                "reason": "inspect the post-apply maintenance state without writing",
            }
        )
    if best.get("id") == "storage_gc_rebuildable_cache" and best.get("command"):
        actions.append(_storage_gc_audit_action(str(best["command"])))
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for action in actions:
        action_id = str(action.get("id") or "")
        if action_id and action_id not in seen:
            seen.add(action_id)
            unique.append(action)
    return unique


def append_storage_review_action(
    actions: list[dict[str, Any]],
    recommended: list[dict],
) -> list[dict[str, Any]]:
    if not any(
        isinstance(item, dict) and item.get("id") == "storage_gc_rebuildable_cache"
        for item in recommended
    ):
        return actions
    command = next(
        (
            public_action_command(str(item.get("id") or ""))
            for item in recommended
            if isinstance(item, dict) and item.get("id") == "storage_gc_rebuildable_cache"
        ),
        STORAGE_GC_BOUNDED_AUDIT_COMMAND,
    )
    next_actions = list(actions)
    if not any(action.get("id") == "storage_gc_audit" for action in next_actions):
        next_actions.append(_storage_gc_audit_action(command or STORAGE_GC_BOUNDED_AUDIT_COMMAND))
    return next_actions


def maintenance_foreground_action(best: dict, *, read_only: bool) -> dict[str, Any]:
    action_id = str(best.get("id") or "")
    if read_only and action_id == "continue":
        return _continue_without_maintenance_action(best)
    if read_only:
        return _read_only_plan_action()
    return {
        "id": "inspect_maintenance_status",
        "label": "Inspect maintenance status",
        "kind": "shell_command",
        "command": STATUS_SUMMARY_COMMAND,
        "mutates": False,
        "mutation_risk": "read_only",
        "claim_boundary": "maintenance_status_not_memory_evidence",
        "why": "Use maintenance status/summary for a no-write card.",
        "reason": "use maintenance status/summary for a no-write card",
    }


def best_next_action(recommended: list[dict]) -> dict:
    if not recommended:
        return {
            "id": "continue",
            "decision": "continue",
            "reason": "No blocking maintenance action is currently recommended.",
        }
    severity_rank = {"critical": 0, "warning": 1, "info": 2, "suggestion": 3}
    ordered = sorted(
        recommended,
        key=lambda item: severity_rank.get(str(item.get("severity") or ""), 9),
    )
    action = public_recommended_action(ordered[0])
    action.setdefault("decision", "preview or apply the next maintenance action")
    return action


def user_impact(health: dict | None, recommended: list[dict]) -> dict:
    readiness = (health or {}).get("product_readiness") if isinstance(health, dict) else {}
    if isinstance(readiness, dict) and readiness:
        required_before_recall = bool(
            readiness.get("maintenance_required_before_recall")
            or (
                readiness.get("ready") is False
                and not readiness.get("ordinary_first_recall_usable")
            )
        )
        if required_before_recall:
            return {
                "recall_usable": "degraded",
                "can_continue_normally": False,
                "ordinary_first_recall_usable": False,
                **maintenance_impact_readiness_fields(readiness, fallback_phase="cold_start_maintenance_required", fallback_cold_start=True),
                "latest_current_thread_may_be_missing": bool(
                    readiness.get("latest_current_thread_may_be_missing")
                ),
                "maintenance_recommended": True,
                "maintenance_required_before_recall": True,
                "summary": (
                    "Source-backed recall/search may be incomplete until the required "
                    "maintenance action is applied."
                ),
            }
        if readiness.get("latest_current_thread_may_be_missing"):
            return {
                "recall_usable": "yes_latest_may_be_missing",
                "can_continue_normally": True,
                "ordinary_first_recall_usable": True,
                **maintenance_impact_readiness_fields(readiness, fallback_phase="steady_state_latest_degraded", fallback_cold_start=False),
                "latest_current_thread_may_be_missing": True,
                "maintenance_recommended": bool(readiness.get("maintenance_recommended")),
                "maintenance_required_before_recall": False,
                "summary": (
                    "Ordinary source-backed recall/search can continue; run maintenance "
                    "before relying on the latest current-thread details."
                ),
            }
        if readiness.get("maintenance_recommended"):
            return {
                "recall_usable": "yes_with_optional_maintenance",
                "can_continue_normally": True,
                "ordinary_first_recall_usable": True,
                **maintenance_impact_readiness_fields(readiness, fallback_phase="steady_state_available", fallback_cold_start=False),
                "latest_current_thread_may_be_missing": False,
                "maintenance_recommended": True,
                "maintenance_required_before_recall": False,
                "summary": "Core recall/search can continue; remaining items are optional upkeep.",
            }
        return {
            "recall_usable": "yes",
            "can_continue_normally": True,
            "ordinary_first_recall_usable": True,
            **maintenance_impact_readiness_fields(readiness, fallback_phase="steady_state_available", fallback_cold_start=False),
            "latest_current_thread_may_be_missing": False,
            "maintenance_recommended": False,
            "maintenance_required_before_recall": False,
            "summary": "Source-backed recall/search can continue normally.",
        }
    if health_maintenance_ok(health):
        return {
            "recall_usable": "yes",
            "can_continue_normally": True,
            "summary": "Source-backed recall/search can continue normally.",
        }
    blocking = [
        item
        for item in recommended
        if isinstance(item, dict) and item.get("severity") in {"critical", "warning"}
    ]
    if blocking:
        return {
            "recall_usable": "degraded",
            "can_continue_normally": False,
            "summary": (
                "Source-backed recall/search may be incomplete until the blocking "
                "maintenance action is applied."
            ),
        }
    return {
        "recall_usable": "yes_with_optional_maintenance",
        "can_continue_normally": True,
        "summary": "Core recall/search can continue; remaining items are optional upkeep.",
    }


def summary_payload(result: dict) -> dict:
    remaining = [
        public_recommended_action(item)
        for item in (result.get("remaining_recommended_actions") or [])[:8]
        if isinstance(item, dict)
    ]
    best = best_next_action(result.get("remaining_recommended_actions") or [])
    agent_action = maintenance_foreground_action(best, read_only=False)
    safe_actions = maintenance_safe_next_actions(best, read_only=False)
    return {
        "kind": "aippocampus_maintenance_summary",
        "ok": result.get("maintenance_status") in {"ok", "degraded"},
        "mode": "applied",
        "read_only": False,
        "maintenance_status": result.get("maintenance_status"),
        "cwd": LOCAL_PATH_REDACTION,
        "cwd_label": result.get("cwd_label"),
        "action_count": len(result.get("action_results") or []),
        "failure_count": len(result.get("action_failures") or []),
        "skipped_count": len(result.get("skipped_due_to_failure") or []),
        "remaining_recommended_action_count": len(result.get("remaining_recommended_actions") or []),
        "action_ids": [item.get("id") for item in (result.get("action_results") or [])[:12]],
        "failure_samples": [
            {
                "id": item.get("id"),
                "returncode": item.get("returncode"),
                "message": item.get("message"),
            }
            for item in (result.get("action_failures") or [])[:5]
        ],
        "remaining_recommended_actions": remaining,
        "interrupted_write_recovery": (result.get("health_final") or {}).get(
            "interrupted_write_recovery"
        ),
        "user_impact": user_impact(result.get("health_final"), result.get("remaining_recommended_actions") or []),
        "full_audit_available": True,
        "full_audit_flag": "--json",
        "operator_detail_available": True,
        "operator_detail_command": "aippocampus maintenance apply --json",
        "plan_first_command": STATUS_COMMAND,
        **canonical_foreground_action_fields(agent_action, safe_next_actions=safe_actions),
    }


def plan_payload(
    *,
    cwd: Path,
    health: dict | None,
    health_returncode: int,
    health_error: str = "",
    refresh_cognitive_map: bool,
    refresh_graphify: bool,
    mode: str = "plan",
) -> dict:
    recommended = list((health or {}).get("recommended_actions") or [])
    recommended_ids = unique_action_ids(
        [str(item.get("id") or "") for item in recommended if item.get("id")]
    )
    would_run_ids = list(recommended_ids)
    implicit_would_run_ids: list[str] = []
    if refresh_cognitive_map:
        would_run_ids.append("build_cognitive_map")
        if "build_cognitive_map" not in recommended_ids:
            implicit_would_run_ids.append("build_cognitive_map")
    if refresh_graphify and any(item.get("id") == "prepare_graphify_corpus" for item in recommended):
        would_run_ids.append("prepare_graphify_corpus")
    would_run_ids = unique_action_ids(would_run_ids)[:16]
    implicit_would_run_ids = unique_action_ids(implicit_would_run_ids)[:16]
    command_ok = health_returncode == 0 and health is not None
    maintenance_ok = command_ok and health_maintenance_ok(health)
    best = best_next_action(recommended)
    agent_action = maintenance_foreground_action(best, read_only=True)
    safe_actions = append_storage_review_action(
        maintenance_safe_next_actions(best, read_only=True),
        recommended,
    )
    payload = {
        "kind": (
            "aippocampus_maintenance_summary"
            if mode == "summary"
            else "aippocampus_maintenance_plan"
        ),
        "ok": maintenance_ok,
        "command_ok": command_ok,
        "plan_generated": command_ok,
        "maintenance_ok": maintenance_ok,
        "maintenance_status": health_maintenance_status(health),
        "mode": mode,
        "read_only": True,
        "cwd": LOCAL_PATH_REDACTION,
        "cwd_label": cwd.name or str(cwd),
        "recommended_action_count": len(recommended),
        "recommended_action_ids": recommended_ids[:16],
        "would_run_action_ids": would_run_ids,
        "would_run_action_count": len(would_run_ids),
        "implicit_would_run_action_ids": implicit_would_run_ids,
        "implicit_would_run_action_count": len(implicit_would_run_ids),
        "would_run_contract": {
            "would_run_action_ids_are_apply_plan_superset": True,
            "recommended_action_count_counts_health_recommendations_only": True,
            "implicit_actions_are_apply_dependencies_or_refreshes": bool(implicit_would_run_ids),
        },
        "remaining_recommended_actions": [
            public_recommended_action(item)
            for item in recommended[:8]
            if isinstance(item, dict)
        ],
        "interrupted_write_recovery": (health or {}).get("interrupted_write_recovery")
        if isinstance(health, dict)
        else None,
        "user_impact": user_impact(health, recommended),
        "apply_command": APPLY_SUMMARY_COMMAND,
        "full_audit_available": True,
        "full_audit_flag": "--json",
        "operator_detail_available": True,
        "operator_detail_command": "aippocampus maintenance plan --json",
        "health_probe": {
            "status": "compact_readiness_probe",
            "full_diagnostics_deferred": True,
            "full_diagnostics_command": "aippocampus health --detail full --json",
        },
        "full_audit_apply_command": "aippocampus maintenance apply --json",
        "privacy_boundary": {
            "local_paths_included": False,
            "writes_performed": False,
            "source_text_included": False,
        },
        **canonical_foreground_action_fields(agent_action, safe_next_actions=safe_actions),
    }
    if not command_ok and health_error:
        payload["health_probe"] = {
            "returncode": health_returncode,
            "status": "failed",
            "message": health_error[:240],
        }
    return payload
