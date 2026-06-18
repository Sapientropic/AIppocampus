#!/usr/bin/env python3
"""Background cognition freshness diagnostics for AIppocampus health."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from aippocampus_runtime.model.routing import deepseek_api_key_env
from aippocampus_runtime.recall.semantic_recall_gate import (
    semantic_gate_enabled,
    semantic_gate_mode,
)
from aippocampus_runtime.subconscious import scheduler as subconscious_scheduler
from aippocampus_runtime.subconscious.scheduler_public import public_scheduler_diagnostic
from aippocampus_runtime.warm_ambient.scheduler import (
    WARM_STATUS_COMMAND,
    warm_background_enabled,
    warm_job_activity,
)

DEFAULT_JOBS_OUTPUT_NAME = "subconscious_jobs.jsonl"
BACKGROUND_COGNITION_STALE_SECONDS = 24 * 60 * 60
BACKGROUND_COGNITION_TAIL_BYTES = 96 * 1024


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def load_json_fail_open(path: Path) -> dict[str, Any]:
    try:
        data = load_json(path)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        text = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def age_seconds_since(value: Any, *, now: datetime | None = None) -> int | None:
    parsed = parse_timestamp(value)
    if parsed is None:
        return None
    current = now or datetime.now(timezone.utc)
    return max(0, int((current - parsed).total_seconds()))

def _subconscious_hook_enabled() -> bool:
    raw = os.environ.get("AIPPOCAMPUS_SUBCONSCIOUS_HOOK")
    if raw is None:
        raw = os.environ.get("AIIPPOCAMPUS_SUBCONSCIOUS_HOOK")
    return str(raw or "").strip().casefold() in {"1", "true", "on", "yes", "enabled"}


def _dream_delivery_mode() -> str:
    raw = str(os.environ.get("AIPPOCAMPUS_DREAM_DELIVERY_MODE") or "off").strip().casefold()
    return raw if raw in {"off", "shadow", "delivered"} else "custom"


def _iso_from_mtime(path: Path) -> str | None:
    try:
        if not path.exists():
            return None
        return (
            datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z")
        )
    except OSError:
        return None


def _latest_timestamp(*values: Any) -> str | None:
    latest: datetime | None = None
    latest_text: str | None = None
    for value in values:
        parsed = parse_timestamp(value)
        if parsed is None:
            continue
        if latest is None or parsed > latest:
            latest = parsed
            latest_text = (
                parsed.replace(microsecond=0).isoformat().replace("+00:00", "Z")
            )
    return latest_text


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _nested_timestamp(payload: Mapping[str, Any], *keys: str) -> str | None:
    value: Any = payload
    for key in keys:
        value = _mapping(value).get(key)
    text = str(value or "").strip()
    return text if parse_timestamp(text) else None


def _tail_json_rows(path: Path, *, max_bytes: int = BACKGROUND_COGNITION_TAIL_BYTES):
    if not path.exists():
        return
    try:
        size = path.stat().st_size
        with path.open("rb") as fh:
            if size > max_bytes:
                fh.seek(max(0, size - max_bytes))
                fh.readline()
            for raw in fh:
                try:
                    item = json.loads(raw.decode("utf-8"))
                except Exception:
                    continue
                if isinstance(item, dict):
                    yield item
    except OSError:
        return


def _latest_jsonl_timestamp(path: Path, *, dream_only: bool = False) -> str | None:
    latest: str | None = None
    for row in _tail_json_rows(path):
        if dream_only and not _is_dream_row(row):
            continue
        timestamp = _latest_timestamp(
            row.get("completed_at"),
            row.get("updated_at"),
            row.get("created_at"),
            row.get("timestamp"),
        )
        latest = _latest_timestamp(latest, timestamp)
    return latest or _iso_from_mtime(path)


def _latest_json_file_timestamp(path: Path, *field_paths: tuple[str, ...]) -> str | None:
    payload = load_json_fail_open(path)
    timestamps = [_nested_timestamp(payload, *field_path) for field_path in field_paths]
    return _latest_timestamp(*timestamps, _iso_from_mtime(path))


def _is_dream_row(row: Mapping[str, Any]) -> bool:
    kind = str(row.get("kind") or "").casefold()
    candidate_type = str(row.get("candidate_type") or "").casefold()
    adjudication_source = str(row.get("adjudication_source") or "").casefold()
    execution_mode = str(row.get("execution_mode") or "").casefold()
    return (
        "dream" in kind
        or "dream" in candidate_type
        or "dream" in adjudication_source
        or execution_mode == "detached_background"
    )


def _artifact_summary(
    name: str,
    *,
    path: Path,
    latest_at: str | None = None,
) -> dict[str, Any]:
    return {
        "name": name,
        "exists": path.exists(),
        "latest_at": latest_at or _iso_from_mtime(path),
    }


def _lock_summary(path: Path, *, now: datetime) -> dict[str, Any]:
    exists = path.exists()
    age = None
    active = False
    stale = False
    if exists:
        mtime = _iso_from_mtime(path)
        age = age_seconds_since(mtime, now=now) if mtime else None
        active = age is not None and age <= subconscious_scheduler.DEFAULT_STALE_LOCK_SECONDS
        stale = age is not None and age > subconscious_scheduler.DEFAULT_STALE_LOCK_SECONDS
    return {"exists": exists, "active": active, "stale": stale, "age_seconds": age}


def _freshness_state(
    *,
    enabled: bool,
    due_state: str,
    currently_running: bool,
    last_observed_at: str | None,
    stale_seconds: int,
    now: datetime,
) -> str:
    if not enabled:
        return "disabled"
    if currently_running:
        return "running"
    if due_state == "blocked":
        return "blocked"
    if due_state == "due":
        return "due"
    if not last_observed_at:
        return "no_signal"
    age = age_seconds_since(last_observed_at, now=now)
    if age is None:
        return "unknown"
    return "stale" if age > stale_seconds else "fresh"


def _lane_report(
    *,
    name: str,
    enabled: bool,
    due_state: str,
    now: datetime,
    last_observed_at: str | None = None,
    last_artifact_at: str | None = None,
    due_reason: str | None = None,
    skip_reason: str | None = None,
    currently_running: bool = False,
    next_operator_action: str,
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    run_at = _latest_timestamp(last_observed_at)
    observed = run_at or _latest_timestamp(last_artifact_at)
    freshness_age_seconds = age_seconds_since(observed, now=now)
    freshness_state = _freshness_state(
        enabled=enabled,
        due_state=due_state,
        currently_running=currently_running,
        last_observed_at=observed,
        stale_seconds=BACKGROUND_COGNITION_STALE_SECONDS,
        now=now,
    )
    reported_due_state = "stale" if due_state == "not_due" and freshness_state == "stale" else due_state
    payload: dict[str, Any] = {
        "name": name,
        "enabled": enabled,
        "currently_running": currently_running,
        "due_state": reported_due_state,
        "scheduler_due_state": due_state if reported_due_state != due_state else None,
        "freshness_state": freshness_state,
        "last_run_at": run_at,
        "last_observed_at": observed,
        "last_artifact_at": last_artifact_at,
        "freshness_age_seconds": freshness_age_seconds,
        "freshness_age_hours": (
            round(float(freshness_age_seconds) / 3600.0, 2)
            if freshness_age_seconds is not None
            else None
        ),
        "due_reason": due_reason,
        "skip_reason": skip_reason,
        "next_operator_action": next_operator_action,
    }
    if extra:
        payload.update(dict(extra))
    return payload


def _subconscious_lane(
    *,
    root: Path,
    registry_path: Path,
    jobs_path: Path,
    cwd: Path,
    now: datetime,
) -> dict[str, Any]:
    enabled = _subconscious_hook_enabled()
    state_file = root / "subconscious_state.json"
    state = load_json_fail_open(state_file)
    state.setdefault("projects", {})
    # Reuse the scheduler's own due-project wrapper so health does not drift
    # from foreground hook behavior. The public projection below strips local
    # project labels and paths before the diagnostic leaves this boundary.
    del registry_path
    now_ts = now.timestamp()
    diagnostic: dict[str, Any] = {}
    try:
        _, diagnostics = subconscious_scheduler.choose_projects_with_diagnostics(
            root=root,
            cwd=cwd,
            project=None,
            all_projects=False,
            state=state,
            now_ts=now_ts,
            cooldown_seconds=subconscious_scheduler.DEFAULT_COOLDOWN_SECONDS,
            min_new_turns=subconscious_scheduler.DEFAULT_MIN_NEW_TURNS,
        )
        if diagnostics:
            diagnostic = public_scheduler_diagnostic(diagnostics[0])
    except Exception as exc:
        diagnostic = {
            "due_state": "blocked",
            "skip_reason": "runtime_error",
            "error_type": type(exc).__name__,
        }
    due_state = str(diagnostic.get("due_state") or "unknown")
    skip_reason = str(diagnostic.get("skip_reason") or "") or None
    due_reason = str(diagnostic.get("due_reason") or "") or None
    if not enabled:
        due_state = "disabled"
        skip_reason = "disabled_by_env"
    lock = _lock_summary(root / "subconscious_scheduler.lock", now=now)
    if lock["stale"] and due_state != "disabled":
        due_state = "blocked"
        skip_reason = "stale_scheduler_lock"
    last_artifact_at = _latest_timestamp(
        _latest_json_file_timestamp(state_file, ("updated_at",)),
        _latest_jsonl_timestamp(jobs_path),
        _latest_jsonl_timestamp(root / "promotion_candidates.jsonl"),
    )
    next_action = "wait_for_cooldown_or_new_source_growth"
    if due_state == "due":
        next_action = "run_subconscious_scheduler"
    elif due_state == "blocked":
        next_action = "inspect_subconscious_scheduler_state"
    elif due_state == "disabled":
        next_action = "enable_subconscious_hook_if_background_work_is_desired"
    return _lane_report(
        name="subconscious",
        enabled=enabled,
        due_state=due_state,
        now=now,
        last_observed_at=str(diagnostic.get("last_run_at") or "") or None,
        last_artifact_at=last_artifact_at,
        due_reason=due_reason,
        skip_reason=skip_reason,
        currently_running=bool(lock["active"]),
        next_operator_action=next_action,
        extra={
            "diagnostic": diagnostic,
            "lock": lock,
            "artifacts": [
                _artifact_summary("subconscious_state.json", path=state_file),
                _artifact_summary(
                    DEFAULT_JOBS_OUTPUT_NAME,
                    path=jobs_path,
                    latest_at=_latest_jsonl_timestamp(jobs_path),
                ),
                _artifact_summary(
                    "promotion_candidates.jsonl",
                    path=root / "promotion_candidates.jsonl",
                    latest_at=_latest_jsonl_timestamp(root / "promotion_candidates.jsonl"),
                ),
            ],
        },
    )


def _dream_lane(*, root: Path, now: datetime) -> dict[str, Any]:
    mode = _dream_delivery_mode()
    artifacts = [
        _artifact_summary(
            "dream_queue.jsonl",
            path=root / "dream_queue.jsonl",
            latest_at=_latest_jsonl_timestamp(root / "dream_queue.jsonl", dream_only=True),
        ),
        _artifact_summary(
            "dream_findings.jsonl",
            path=root / "dream_findings.jsonl",
            latest_at=_latest_jsonl_timestamp(root / "dream_findings.jsonl", dream_only=True),
        ),
        _artifact_summary(
            "dream_utility_events.jsonl",
            path=root / "dream_utility_events.jsonl",
            latest_at=_latest_jsonl_timestamp(root / "dream_utility_events.jsonl", dream_only=True),
        ),
        _artifact_summary(
            "working_memory.jsonl",
            path=root / "working_memory.jsonl",
            latest_at=_latest_jsonl_timestamp(root / "working_memory.jsonl", dream_only=True),
        ),
    ]
    last_artifact_at = _latest_timestamp(*(item.get("latest_at") for item in artifacts))
    enabled = mode != "off" or any(item["exists"] for item in artifacts)
    due_state = "not_due" if enabled else "disabled"
    skip_reason = None if enabled else "dream_delivery_off_and_no_artifacts"
    return _lane_report(
        name="dream",
        enabled=enabled,
        due_state=due_state,
        now=now,
        last_observed_at=last_artifact_at,
        last_artifact_at=last_artifact_at,
        skip_reason=skip_reason,
        next_operator_action=(
            "inspect_or_run_sleep_cycle_if_dream_review_is_desired"
            if enabled
            else "enable_dream_delivery_or_run_sleep_cycle_when_needed"
        ),
        extra={"delivery_mode": mode, "artifacts": artifacts},
    )


def _prompt_hook_lane(*, root: Path, now: datetime) -> dict[str, Any]:
    status_path = root / "aippocampus_prompt_hook_last_status.json"
    telemetry_path = root / "aippocampus_prompt_hook_skip_telemetry.json"
    status = load_json_fail_open(status_path)
    latest = _mapping(status.get("last_prompt_hook"))
    telemetry = load_json_fail_open(telemetry_path)
    last_prompt_hook_at = _nested_timestamp(status, "last_prompt_hook", "timestamp")
    telemetry_at = _nested_timestamp(telemetry, "updated_at")
    last_artifact_at = _latest_timestamp(
        _latest_json_file_timestamp(status_path, ("last_prompt_hook", "timestamp")),
        _latest_json_file_timestamp(telemetry_path, ("updated_at",)),
    )
    observed = bool(status_path.exists() or telemetry_path.exists())
    return _lane_report(
        name="prompt_hook_affordance",
        enabled=observed,
        due_state="not_due" if observed else "disabled",
        now=now,
        last_observed_at=_latest_timestamp(last_prompt_hook_at, telemetry_at),
        last_artifact_at=last_artifact_at,
        skip_reason=None if observed else "no_prompt_hook_status_observed",
        next_operator_action=(
            "wait_for_next_prompt_hook_run"
            if observed
            else "run_or_install_prompt_hook_to_create_status_surface"
        ),
        extra={
            "observed": observed,
            "latest": {
                "memory_surface": latest.get("memory_surface"),
                "card_count": latest.get("card_count"),
                "source_backed_count": latest.get("source_backed_count"),
                "candidate_count": latest.get("candidate_count"),
            },
            "artifacts": [
                _artifact_summary(
                    "aippocampus_prompt_hook_last_status.json",
                    path=status_path,
                    latest_at=last_prompt_hook_at,
                ),
                _artifact_summary(
                    "aippocampus_prompt_hook_skip_telemetry.json",
                    path=telemetry_path,
                    latest_at=telemetry_at,
                ),
            ],
        },
    )


def _warm_ambient_lane(*, root: Path, now: datetime) -> dict[str, Any]:
    enabled = warm_background_enabled()
    status = load_json_fail_open(root / "aippocampus_prompt_hook_last_status.json")
    warm_status = _mapping(_mapping(status.get("last_prompt_hook")).get("warm_background"))
    hook_at = _nested_timestamp(status, "last_prompt_hook", "timestamp")
    activity = warm_job_activity(root / "ambient_warm_jobs", now=now)
    last_artifact_at = _latest_timestamp(activity.get("latest_at"), hook_at)
    currently_running = bool(activity.get("worker_process_active"))
    due_state = "not_due" if enabled else "disabled"
    skip_reason = None
    if not enabled:
        skip_reason = "disabled_by_env"
    elif activity.get("pending_stale_count"):
        due_state = "blocked"
        skip_reason = "stale_warm_ambient_job"
    elif str(warm_status.get("status") or "").startswith("skipped"):
        skip_reason = str(warm_status.get("status"))
    return _lane_report(
        name="warm_ambient",
        enabled=enabled,
        due_state=due_state,
        now=now,
        last_observed_at=hook_at,
        last_artifact_at=last_artifact_at,
        skip_reason=skip_reason,
        currently_running=currently_running,
        next_operator_action=(
            WARM_STATUS_COMMAND
            if due_state == "blocked"
            else WARM_STATUS_COMMAND
            if activity.get("pending_recent_count")
            else "wait_for_next_cache_miss"
            if enabled
            else "enable_warm_background_if_budget_allows"
        ),
        extra={
            "latest_prompt_hook_status": {
                "status": warm_status.get("status"),
                "spawned": warm_status.get("spawned"),
            },
            "job_activity": activity,
            "artifacts": [
                _artifact_summary(
                    "ambient_warm_jobs",
                    path=root / "ambient_warm_jobs",
                    latest_at=activity.get("latest_at"),
                )
            ],
        },
    )


def _semantic_gate_lane(*, root: Path, now: datetime) -> dict[str, Any]:
    mode = semantic_gate_mode()
    api_key_env = deepseek_api_key_env(os.environ)
    provider_visible = api_key_env in os.environ
    enabled = semantic_gate_enabled(api_key_env=api_key_env)
    telemetry_path = root / "aippocampus_prompt_hook_skip_telemetry.json"
    telemetry = load_json_fail_open(telemetry_path)
    last_artifact_at = _latest_json_file_timestamp(telemetry_path, ("updated_at",))
    due_state = "not_due"
    skip_reason = None
    if mode == "off":
        due_state = "disabled"
        skip_reason = "semantic_disabled_by_operator"
    elif not provider_visible:
        due_state = "blocked"
        skip_reason = "semantic_unavailable_missing_auth"
    return _lane_report(
        name="semantic_gate",
        enabled=enabled,
        due_state=due_state,
        now=now,
        last_observed_at=_nested_timestamp(telemetry, "updated_at"),
        last_artifact_at=last_artifact_at,
        skip_reason=skip_reason,
        next_operator_action=(
            "provide_semantic_gate_api_key_or_set_mode_off"
            if due_state == "blocked"
            else "wait_for_prompt_recall_need"
            if enabled
            else "enable_semantic_gate_if_model_backed_recall_is_desired"
        ),
        extra={
            "mode": mode,
            "provider_key_visible": provider_visible,
            "diagnostic_counts": {
                str(key): safe_int(value)
                for key, value in (
                    _mapping(telemetry.get("semantic_diagnostic_counts")).items()
                )
            },
            "artifacts": [
                _artifact_summary(
                    "aippocampus_prompt_hook_skip_telemetry.json",
                    path=telemetry_path,
                    latest_at=_nested_timestamp(telemetry, "updated_at"),
                )
            ],
        },
    )


def background_cognition_health(
    *,
    root: Path,
    registry_path: Path,
    jobs_path: Path,
    cwd: Path,
    now: datetime,
) -> dict[str, Any]:
    lanes = [
        _subconscious_lane(
            root=root,
            registry_path=registry_path,
            jobs_path=jobs_path,
            cwd=cwd,
            now=now,
        ),
        _dream_lane(root=root, now=now),
        _warm_ambient_lane(root=root, now=now),
        _semantic_gate_lane(root=root, now=now),
        _prompt_hook_lane(root=root, now=now),
    ]
    lane_by_name = {str(lane["name"]): lane for lane in lanes}
    state_counts: dict[str, int] = {}
    freshness_state_counts: dict[str, int] = {}
    for lane in lanes:
        state = str(lane.get("due_state") or "unknown")
        state_counts[state] = state_counts.get(state, 0) + 1
        freshness_state = str(lane.get("freshness_state") or "unknown")
        freshness_state_counts[freshness_state] = freshness_state_counts.get(freshness_state, 0) + 1
    return {
        "available": True,
        "lane_count": len(lanes),
        "lanes": lane_by_name,
        "state_counts": state_counts,
        "freshness_state_counts": freshness_state_counts,
        "stale_lane_count": state_counts.get("stale", 0),
        "due_lane_count": state_counts.get("due", 0),
        "blocked_lane_count": state_counts.get("blocked", 0),
        "running_lane_count": sum(1 for lane in lanes if lane.get("currently_running")),
        "stale_after_seconds": BACKGROUND_COGNITION_STALE_SECONDS,
        "privacy_boundary": {
            "raw_prompts_included": False,
            "raw_source_text_included": False,
            "local_paths_included": False,
            "candidate_contents_included": False,
        },
    }
