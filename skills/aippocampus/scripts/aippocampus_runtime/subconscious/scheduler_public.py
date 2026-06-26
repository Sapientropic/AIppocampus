"""Public projection helpers for subconscious scheduler results.

The scheduler result can contain local project labels, log paths, and raw worker
details. Keep the public CLI projection separate so hook-facing JSON stays
boring and redacted even as private scheduler internals evolve.
"""

from __future__ import annotations

from typing import Any

PUBLIC_SKIP_REASONS = {
    "disabled_by_env",
    "cognitive_worker_mode_off",
    "deterministic_only_by_env",
    "agent_fallback_queued",
    "enqueue_locked",
    "no_due_projects",
    "leased_projects",
    "enqueue_cooldown",
    "cooldown_not_elapsed",
    "no_registered_project_for_cwd",
    "source_growth_below_threshold",
    "missing_clean_source_freshness",
    "lease_active_or_stale",
    "project_name_not_resolved",
}

AGENT_FALLBACK_EXECUTOR_COMMAND = (
    "python -m aippocampus_runtime.subconscious.agent_fallback_executor --json"
)
AGENT_FALLBACK_MATERIALIZER_COMMAND = (
    "python -m aippocampus_runtime.subconscious.agent_fallback_materializer --json"
)


def public_skip_reason(value: Any) -> str | None:
    reason = str(value or "").strip()
    if reason in PUBLIC_SKIP_REASONS:
        return reason
    if reason.startswith("missing_"):
        return "missing_api_key"
    return "runtime_error" if reason else None


def public_count(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def public_timestamp(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    if len(text) > 40:
        return None
    return text if all(char.isdigit() or char in "-:TZ+." for char in text) else None


def public_scheduler_diagnostic(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "project_resolved": bool(item.get("project_resolved")),
        "due_state": str(item.get("due_state") or "unknown"),
        "due_reason": _public_due_reason(item.get("due_reason")),
        "skip_reason": public_skip_reason(item.get("skip_reason")),
        "last_run_at": public_timestamp(item.get("last_run_at")),
        "new_turns_since_last_run": public_count(item.get("new_turns_since_last_run")),
        "new_messages_since_last_run": public_count(
            item.get("new_messages_since_last_run")
        ),
        "min_new_turns": public_count(item.get("min_new_turns")),
        "cooldown_remaining_seconds": public_count(item.get("cooldown_remaining_seconds")),
        "next_due_at": public_timestamp(item.get("next_due_at")),
        "lease_active": bool(item.get("lease_active")),
    }


def _public_due_reason(value: Any) -> str | None:
    reason = str(value or "").strip()
    if reason.startswith("new_turns:"):
        suffix = reason.removeprefix("new_turns:")
        return f"new_turns:{public_count(suffix)}"
    if reason == "first_run":
        return reason
    return None


def public_scheduler_payload(result: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "started": bool(result.get("started")),
        "ran": bool(result.get("ran")),
        "dry_run": bool(result.get("dry_run")),
        "skipped": public_skip_reason(result.get("skipped")),
        "pid_present": bool(result.get("pid")),
        "project_count": len(result.get("projects") or [])
        if isinstance(result.get("projects"), list)
        else 0,
        "result_count": len(result.get("results") or [])
        if isinstance(result.get("results"), list)
        else 0,
        "log_private_artifact": bool(result.get("log")),
        "output_boundary": "scheduler_project_details_are_local_private_artifacts",
    }
    if isinstance(result.get("cognitive_worker"), dict):
        worker = result["cognitive_worker"]
        contracts = worker.get("contracts") if isinstance(worker.get("contracts"), dict) else {}
        resolved_mode = worker.get("resolved_mode")
        payload["cognitive_worker"] = {
            "status": worker.get("status"),
            "resolved_mode": resolved_mode,
            "ambient_state": worker.get("ambient_state"),
            "provider_key_visible": bool(worker.get("provider_key_visible")),
            "agent_fallback_available": bool(worker.get("agent_fallback_available")),
            "foreground_hook_waits_for_agent_fallback": bool(
                contracts.get("foreground_hook_waits_for_agent_fallback")
            ),
            "queued_task_is_readiness_evidence": bool(
                contracts.get("queued_task_is_readiness_evidence")
            ),
            "queued_task_is_usefulness_evidence": bool(
                contracts.get("queued_task_is_usefulness_evidence")
            ),
        }
        if resolved_mode == "agent_fallback":
            payload["agent_fallback_follow_through"] = {
                "state": "scaffold_manual_only",
                "ambient_state": "callable",
                "queued_task_is_readiness_evidence": False,
                "queued_task_is_usefulness_evidence": False,
                "manual_operator_commands": [
                    AGENT_FALLBACK_EXECUTOR_COMMAND,
                    AGENT_FALLBACK_MATERIALIZER_COMMAND,
                ],
                "claim_boundary": (
                    "queued fallback tasks are work orders; they do not prove "
                    "reviewed findings reached recall/background surfaces"
                ),
            }
    if result.get("queued"):
        payload["queued"] = True
        payload["agent_fallback_task_count"] = int(result.get("agent_fallback_task_count") or 0)
    diagnostics = [
        public_scheduler_diagnostic(item)
        for item in result.get("scheduler_diagnostics") or []
        if isinstance(item, dict)
    ]
    if diagnostics:
        payload["scheduler_diagnostics"] = diagnostics[:8]
        payload["diagnostic_count"] = len(diagnostics)
    if result.get("error"):
        payload["error"] = {"code": "runtime_error"}
    return payload
