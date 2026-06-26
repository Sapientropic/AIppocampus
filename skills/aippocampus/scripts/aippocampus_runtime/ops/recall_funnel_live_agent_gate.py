"""Live-agent usefulness gate for the recall funnel smoke.

This helper intentionally orchestrates the packaged agent recall/deepen path so
the smoke can catch regressions that deterministic MCP fixtures miss. Keep the
output public-safe: no cue echo, no source text, no local paths, and no raw
handles.
"""

from __future__ import annotations

import contextlib
import json
import tempfile
from io import StringIO
from pathlib import Path
from typing import Any

from aippocampus_runtime.core import dict_or_empty, list_or_empty
from aippocampus_runtime.recall import agent_continuity
from aippocampus_runtime.update import cli as update_cli


def _as_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _agent_json(argv: list[str]) -> tuple[int, dict[str, Any], dict[str, Any] | None]:
    """Run the packaged agent command in-process and keep diagnostics redacted."""

    stdout = StringIO()
    stderr = StringIO()
    code = 0
    try:
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = int(agent_continuity.main(argv) or 0)
    except SystemExit as exc:  # pragma: no cover - defensive for entrypoint drift.
        try:
            code = int(exc.code or 0)
        except (TypeError, ValueError):
            code = 1
    except Exception:
        return 1, {}, {
            "code": "agent_cli_execution_failed",
            "message": "agent continuity command failed before returning JSON.",
        }
    raw = stdout.getvalue()
    try:
        payload = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return code, {}, {
            "code": "agent_cli_json_parse_failed",
            "message": "agent continuity command did not return parseable JSON.",
        }
    return code, payload if isinstance(payload, dict) else {}, None


def _agent_recall_argv(
    cue: str,
    *,
    cwd: Path,
    clean_source_dir: str | Path | None,
    registry_dir: str | Path | None,
    max_routes: int,
    last_recall_path: Path,
) -> list[str]:
    argv = [
        "recall",
        cue,
        "--cwd",
        str(cwd),
        "--max",
        str(max_routes),
        "--last-recall-path",
        str(last_recall_path),
        "--json",
    ]
    if clean_source_dir is not None:
        argv.extend(["--clean-source-dir", str(clean_source_dir)])
    if registry_dir is not None:
        argv.extend(["--registry-dir", str(registry_dir)])
    return argv


def _agent_deepen_argv(
    action: dict[str, Any],
    *,
    cwd: Path,
    clean_source_dir: str | Path | None,
    registry_dir: str | Path | None,
    max_deepen_matches: int,
    last_recall_path: Path,
) -> list[str] | None:
    arguments = dict_or_empty(action.get("arguments"))
    request_index = _as_int(arguments.get("request_index") or action.get("request_index") or 1) or 1
    argv = [
        "deepen",
        "--request",
        str(request_index),
        "--cwd",
        str(cwd),
        "--max",
        str(max_deepen_matches),
        "--last-recall-path",
        str(last_recall_path),
        "--json",
    ]
    selector = str(arguments.get("recall_selector") or action.get("recall_selector") or "").strip()
    if selector:
        argv.extend(["--recall-selector", selector])
    elif arguments.get("last_recall") or action.get("last_recall"):
        argv.append("--last-recall")
    else:
        return None
    if clean_source_dir is not None:
        argv.extend(["--clean-source-dir", str(clean_source_dir)])
    if registry_dir is not None:
        argv.extend(["--registry-dir", str(registry_dir)])
    return argv


def _can_drive_agent_deepen(action: dict[str, Any]) -> bool:
    arguments = dict_or_empty(action.get("arguments"))
    return bool(
        arguments.get("recall_selector")
        or action.get("recall_selector")
        or arguments.get("last_recall")
        or action.get("last_recall")
    )


def _selected_agent_action(recall_payload: dict[str, Any]) -> dict[str, Any]:
    foreground = dict_or_empty(recall_payload.get("foreground_action"))
    secondary = dict_or_empty(foreground.get("secondary_action"))
    candidates: list[dict[str, Any]] = []
    if secondary:
        candidates.append(secondary)
    for route in list_or_empty(recall_payload.get("routes")):
        if not isinstance(route, dict):
            continue
        action = dict_or_empty(route.get("action"))
        if action:
            candidates.append(action)
    if dict_or_empty(foreground.get("arguments")):
        candidates.append(foreground)
    for action in candidates:
        if _can_drive_agent_deepen(action):
            return action
    return candidates[0] if candidates else {}


def _gate_item(status: str, reason: str, **extra: Any) -> dict[str, Any]:
    result = {"status": status, "reason": reason}
    result.update({key: value for key, value in extra.items() if value not in (None, "", [])})
    return result


def _ambient_hook_readiness() -> dict[str, Any]:
    try:
        hooks = update_cli.status_hooks(update_cli.codex_home())
    except Exception:
        return {
            "status": "not_checked",
            "error": {"code": "ambient_readiness_unavailable"},
            "counts_toward_task_usefulness": False,
        }
    prompt = dict_or_empty(hooks.get("prompt_hook_status"))
    warm = dict_or_empty(hooks.get("warm_ambient"))
    warm_activity = dict_or_empty(warm.get("job_activity"))
    red_lines = _as_int(prompt.get("foreground_latency_red_line_violation_count"))
    near_timeout = _as_int(prompt.get("near_timeout_event_count"))
    prompt_latency_status = str(
        prompt.get("prompt_hook_latency_current_status")
        or prompt.get("prompt_hook_latency_risk_status")
        or ""
    )
    warm_status = str(warm.get("status") or "")
    warm_queue_state = str(warm_activity.get("queue_state") or "")
    degraded = (
        red_lines > 0
        or near_timeout > 0
        or prompt_latency_status == "near_host_timeout_risk"
        or bool(warm_activity.get("stale_queue_blocked"))
        or warm_status == "blocked"
    )
    installed = bool(prompt.get("installed") or warm.get("enabled") or hooks.get("action_hints_installed"))
    return {
        "status": "warn" if degraded else "pass" if installed else "not_installed",
        "counts_toward_task_usefulness": False,
        "prompt_hook": {
            "installed": bool(prompt.get("installed")),
            "latency_risk_status": prompt_latency_status or "unknown",
            "latency_freshness_status": str(
                prompt.get("prompt_hook_latency_freshness_status") or "unknown"
            ),
            "latency_historical_status": str(
                prompt.get("prompt_hook_latency_historical_status") or "unknown"
            ),
            "foreground_latency_red_line_violation_count": red_lines,
            "near_timeout_event_count": near_timeout,
        },
        "warm_ambient": {
            "status": warm_status or "unknown",
            "enabled": bool(warm.get("enabled")),
            "ordinary_recall_usable": bool(warm.get("ordinary_recall_usable")),
            "queue_state": warm_queue_state or "unknown",
            "pending_recent_count": _as_int(warm_activity.get("pending_recent_count")),
            "pending_stale_count": _as_int(warm_activity.get("pending_stale_count")),
            "stale_queue_blocked": bool(warm_activity.get("stale_queue_blocked")),
        },
        "diagnostic_command": "aippocampus update status --agent-json --operator-json",
    }


def build_live_agent_usefulness_gate(
    cue: str,
    *,
    cwd: Path,
    clean_source_dir: str | Path | None,
    registry_dir: str | Path | None,
    max_routes: int,
    max_deepen_matches: int,
) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="aippo-recall-funnel-agent-") as tmp:
        last_recall_path = Path(tmp) / "last-recall.json"
        recall_code, recall_payload, recall_parse_error = _agent_json(
            _agent_recall_argv(
                cue,
                cwd=cwd,
                clean_source_dir=clean_source_dir,
                registry_dir=registry_dir,
                max_routes=max_routes,
                last_recall_path=last_recall_path,
            )
        )
        selected_action = _selected_agent_action(recall_payload)
        deepen_argv = _agent_deepen_argv(
            selected_action,
            cwd=cwd,
            clean_source_dir=clean_source_dir,
            registry_dir=registry_dir,
            max_deepen_matches=max_deepen_matches,
            last_recall_path=last_recall_path,
        )
        deepen_code = 2
        deepen_payload: dict[str, Any] = {}
        deepen_parse_error: dict[str, Any] | None = {
            "code": "no_agent_deepen_action",
            "message": "agent recall did not expose a callable deepen action.",
        }
        if deepen_argv is not None:
            deepen_code, deepen_payload, deepen_parse_error = _agent_json(deepen_argv)

    routes = [route for route in list_or_empty(recall_payload.get("routes")) if isinstance(route, dict)]
    route_count = _as_int(recall_payload.get("route_count") or len(routes))
    foreground = dict_or_empty(recall_payload.get("foreground_action"))
    foreground_action_id = str(foreground.get("id") or foreground.get("action_id") or "")
    route_choice_posture = str(
        foreground.get("route_choice_posture")
        or selected_action.get("route_choice_posture")
        or ""
    )
    action_confidence = str(selected_action.get("confidence") or "")
    labels_low_specificity = (
        foreground_action_id == "refine_low_specificity_recall_cue"
        or route_choice_posture == "labels_low_specificity"
        or action_confidence == "low_confidence_navigation"
    )
    selected_arguments = dict_or_empty(selected_action.get("arguments"))
    selected_selector_kind = (
        "recall_selector"
        if selected_arguments.get("recall_selector")
        else "last_recall"
        if selected_arguments.get("last_recall")
        else ""
    )
    deepen_summary = dict_or_empty(deepen_payload.get("source_window_summary"))
    source_opened = bool(
        deepen_payload.get("status") == "ok"
        and (
            deepen_summary.get("has_exact_source")
            or _as_int(deepen_summary.get("message_count")) > 0
            or _as_int(deepen_summary.get("source_ref_count")) > 0
        )
    )
    recall_error = recall_parse_error or (
        dict_or_empty(recall_payload.get("error")) if recall_code and recall_payload.get("error") else None
    )
    deepen_error = deepen_parse_error or (
        dict_or_empty(deepen_payload.get("error")) if deepen_code and deepen_payload.get("error") else None
    )
    route_existence = _gate_item(
        "pass" if route_count > 0 else "fail",
        "agent recall returned at least one compact route"
        if route_count > 0
        else "agent recall returned no compact routes",
        route_count=route_count,
    )
    route_specificity = _gate_item(
        "fail"
        if route_count <= 0
        else "warn"
        if labels_low_specificity
        else "pass",
        "compact route labels were low-specificity; refine before treating top route as useful"
        if labels_low_specificity
        else "compact route labels did not trigger low-specificity abstention",
        foreground_action_id=foreground_action_id,
        route_choice_posture=route_choice_posture,
        selected_action_confidence=action_confidence,
    )
    source_reopen = _gate_item(
        "pass"
        if source_opened
        else "fail"
        if selected_action
        else "not_run",
        "agent deepen reopened a source window"
        if source_opened
        else "agent deepen could not reopen the selected route",
        selected_action_id=str(selected_action.get("id") or selected_action.get("action_id") or ""),
        selected_selector_kind=selected_selector_kind,
        deepen_status=deepen_payload.get("status") or ("error" if deepen_error else "not_run"),
        source_window_message_count=_as_int(deepen_summary.get("message_count")),
        source_ref_count=_as_int(deepen_summary.get("source_ref_count")),
        error=deepen_error,
    )
    if route_existence["status"] == "fail" or source_reopen["status"] == "fail":
        task_status = "fail"
        task_reason = "live agent path did not provide a reopenable useful route"
    elif route_specificity["status"] == "warn":
        task_status = "warn"
        task_reason = "route exists and reopens, but foreground labels are too generic for confident task use"
    else:
        task_status = "pass"
        task_reason = "route exists, remains specific enough, and reopens before task use"
    return {
        "status": task_status,
        "ok": task_status != "fail",
        "surface": "agent_recall_then_agent_deepen_compact",
        "route_existence": route_existence,
        "route_specificity": route_specificity,
        "source_reopen": source_reopen,
        "task_usefulness": _gate_item(task_status, task_reason),
        "ambient_hook_readiness": _ambient_hook_readiness(),
        "recall": {
            "status": recall_payload.get("status") or ("error" if recall_error else "unknown"),
            "exit_code": recall_code,
            "parse_error": recall_parse_error,
            "error": recall_error,
            "last_recall_cache_available": bool(recall_payload.get("last_recall_cache_available")),
            "recall_selector_available": bool(recall_payload.get("recall_selector_available")),
        },
        "deepen": {
            "status": deepen_payload.get("status") or ("error" if deepen_error else "not_run"),
            "exit_code": deepen_code,
            "parse_error": deepen_parse_error,
        },
        "privacy": {
            "raw_cue_echoed": False,
            "source_window_text_included": False,
            "temporary_selector_cache_persisted": False,
            "local_paths_included": False,
        },
        "claim_boundary": {
            "gate_is_live_agent_diagnostic": True,
            "tiny_cohort_not_representative_quality_claim": True,
            "source_backed_claims_still_require_opened_source": True,
        },
    }
