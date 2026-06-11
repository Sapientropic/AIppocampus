#!/usr/bin/env python3
"""Due-project selection diagnostics for the subconscious scheduler."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def iso_from_ts(value: float) -> str:
    return (
        datetime.fromtimestamp(value, tz=timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def project_due_diagnostic(
    stats: Any,
    project_state: dict[str, Any],
    *,
    due_reason: str | None,
    now_ts: float,
    cooldown_seconds: int,
    min_new_turns: int,
    lease_active: bool,
) -> dict[str, Any]:
    last_run = float(project_state.get("last_run_ts") or 0.0)
    last_turns = int(project_state.get("last_clean_turn_count") or 0)
    last_messages = int(project_state.get("last_clean_message_count") or 0)
    clean_turn_count = int(getattr(stats, "clean_turn_count", 0) or 0)
    clean_message_count = int(getattr(stats, "clean_message_count", 0) or 0)
    new_turns = max(0, clean_turn_count - last_turns)
    new_messages = max(0, clean_message_count - last_messages)
    cooldown_remaining = (
        max(0, int((last_run + cooldown_seconds) - now_ts)) if last_run else 0
    )
    if due_reason:
        due_state = "due"
        skip_reason = None
        next_due_at = None
    elif last_run and cooldown_remaining > 0:
        due_state = "not_due"
        skip_reason = "cooldown_not_elapsed"
        next_due_at = iso_from_ts(last_run + cooldown_seconds)
    elif not str(getattr(stats, "latest_updated_at", "") or "").strip():
        due_state = "not_due"
        skip_reason = "missing_clean_source_freshness"
        next_due_at = None
    elif last_run <= 0 and clean_turn_count < 3:
        due_state = "not_due"
        skip_reason = "source_growth_below_threshold"
        next_due_at = None
    else:
        due_state = "not_due"
        skip_reason = "source_growth_below_threshold"
        next_due_at = None
    return {
        "label": str(getattr(stats, "label", "")),
        "project_resolved": True,
        "due_state": due_state,
        "due_reason": due_reason,
        "skip_reason": skip_reason,
        "last_run_at": str(project_state.get("last_run_at") or ""),
        "new_turns_since_last_run": new_turns,
        "new_messages_since_last_run": new_messages,
        "clean_turn_count": clean_turn_count,
        "clean_message_count": clean_message_count,
        "thread_count": int(getattr(stats, "thread_count", 0) or 0),
        "min_new_turns": max(0, int(min_new_turns)),
        "cooldown_seconds": max(0, int(cooldown_seconds)),
        "cooldown_remaining_seconds": cooldown_remaining,
        "next_due_at": next_due_at,
        "lease_active": lease_active,
    }


def missing_project_diagnostic(*, label: str = "", skip_reason: str) -> dict[str, Any]:
    return {
        "label": label,
        "project_resolved": False,
        "due_state": "blocked",
        "skip_reason": skip_reason,
        "new_turns_since_last_run": 0,
        "new_messages_since_last_run": 0,
    }


ProjectForCwdFn = Callable[[dict[str, Any], Path | None], str | None]
BootstrapFn = Callable[..., None]
DueReasonFn = Callable[..., str | None]
LeaseActiveFn = Callable[[dict[str, Any], float], bool]


def choose_projects_with_diagnostics(
    *,
    root: Path,
    registry: dict[str, Any],
    stats_by_label: dict[str, Any],
    cwd: Path | None,
    project: str | None,
    all_projects: bool,
    state: dict[str, Any],
    now_ts: float,
    cooldown_seconds: int,
    min_new_turns: int,
    project_for_cwd: ProjectForCwdFn,
    bootstrap_project_state_from_staging: BootstrapFn,
    due_reason: DueReasonFn,
    lease_active: LeaseActiveFn,
) -> tuple[list[tuple[Any, str]], list[dict[str, Any]]]:
    if all_projects:
        labels = sorted(stats_by_label)
    elif project:
        if project not in stats_by_label:
            return [], [
                missing_project_diagnostic(
                    label=project,
                    skip_reason="project_name_not_resolved",
                )
            ]
        labels = [project]
    else:
        inferred = project_for_cwd(registry, cwd)
        if not inferred:
            return [], [
                missing_project_diagnostic(skip_reason="no_registered_project_for_cwd")
            ]
        labels = [inferred]

    due: list[tuple[Any, str]] = []
    diagnostics: list[dict[str, Any]] = []
    projects_state = state.setdefault("projects", {})
    for label in labels:
        stats = stats_by_label.get(label)
        if not stats:
            diagnostics.append(
                missing_project_diagnostic(
                    label=label,
                    skip_reason="project_name_not_resolved",
                )
            )
            continue
        project_state = projects_state.setdefault(label, {})
        bootstrap_project_state_from_staging(
            root,
            stats,
            project_state,
            now_ts=now_ts,
            cooldown_seconds=cooldown_seconds,
        )
        reason = due_reason(
            stats,
            project_state,
            now_ts=now_ts,
            cooldown_seconds=cooldown_seconds,
            min_new_turns=min_new_turns,
        )
        diagnostics.append(
            project_due_diagnostic(
                stats,
                project_state,
                due_reason=reason,
                now_ts=now_ts,
                cooldown_seconds=cooldown_seconds,
                min_new_turns=min_new_turns,
                lease_active=lease_active(project_state, now_ts),
            )
        )
        if reason:
            due.append((stats, reason))
    return due, diagnostics
