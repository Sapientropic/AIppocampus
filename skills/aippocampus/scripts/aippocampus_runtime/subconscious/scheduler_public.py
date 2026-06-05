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
}


def public_skip_reason(value: Any) -> str | None:
    reason = str(value or "").strip()
    if reason.startswith("missing_"):
        return "missing_api_key"
    return reason if reason in PUBLIC_SKIP_REASONS else ("runtime_error" if reason else None)


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
        payload["cognitive_worker"] = {
            "status": worker.get("status"),
            "resolved_mode": worker.get("resolved_mode"),
            "provider_key_visible": bool(worker.get("provider_key_visible")),
            "agent_fallback_available": bool(worker.get("agent_fallback_available")),
            "foreground_hook_waits_for_agent_fallback": bool(
                (worker.get("contracts") or {}).get("foreground_hook_waits_for_agent_fallback")
            ),
        }
    if result.get("queued"):
        payload["queued"] = True
        payload["agent_fallback_task_count"] = int(result.get("agent_fallback_task_count") or 0)
    if result.get("error"):
        payload["error"] = {"code": "runtime_error"}
    return payload
