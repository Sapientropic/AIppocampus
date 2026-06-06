"""Preemptive lifecycle decision helpers.

Lifecycle hooks execute actions; this module owns the small cadence and
health-trajectory projection used to decide when SessionStart may prewarm
cheap source/index repairs before prompt-time recall.
"""

from __future__ import annotations

from typing import Any

SESSION_MIN_COOLDOWN_SECONDS = 5 * 60
SESSION_PREEMPTIVE_ACTIONS = ("build_index", "build_clean_source")


def effective_session_cooldown_seconds(
    workspace_state: dict[str, Any],
    default_cooldown_seconds: int,
    *,
    minimum_cooldown_seconds: int = SESSION_MIN_COOLDOWN_SECONDS,
) -> int:
    try:
        interval = int(float(workspace_state.get("last_session_interval_seconds") or 0))
    except (TypeError, ValueError):
        interval = 0
    if interval <= 0:
        return default_cooldown_seconds
    return max(minimum_cooldown_seconds, min(default_cooldown_seconds, interval))


def preemptive_decision_fields(health: dict[str, Any]) -> dict[str, Any]:
    return {
        "preemptive_actions": preemptive_action_ids(health),
        "preemptive_reason_codes": preemptive_reason_codes(health),
        "preemptive_action_reasons": preemptive_action_reasons(health),
    }


def preemptive_action_ids(health: dict[str, Any]) -> list[str]:
    actions = health_trajectory(health).get("preemptive_actions") or []
    return unique_items(
        [str(action) for action in actions if str(action) in SESSION_PREEMPTIVE_ACTIONS]
    )


def record_preemptive_outcome(
    decision: dict[str, Any],
    *,
    scheduled_actions: list[str],
    completed_actions: list[str],
    skipped_actions: list[dict[str, Any]],
    dry_run: bool,
) -> None:
    preemptive = set(decision.get("preemptive_actions") or [])
    decision["preemptive_action_taken"] = [
        action for action in completed_actions if action in preemptive
    ]
    decision["preemptive_action_skipped"] = [
        item for item in skipped_actions if item.get("id") in preemptive
    ]
    if decision.get("cooldown_active"):
        decision["preemptive_action_skipped"] = [
            {"id": action, "reason": "cooldown"}
            for action in decision.get("preemptive_actions") or []
        ]
    elif dry_run:
        decision["preemptive_action_skipped"] = [
            {"id": action, "reason": "dry_run"}
            for action in scheduled_actions
            if action in preemptive
        ]


def health_trajectory(health: dict[str, Any]) -> dict[str, Any]:
    value = health.get("health_trajectory")
    return value if isinstance(value, dict) else {}


def preemptive_reason_codes(health: dict[str, Any]) -> list[str]:
    codes = health_trajectory(health).get("preemptive_reason_codes") or []
    return unique_items([str(code) for code in codes if code])


def preemptive_action_reasons(health: dict[str, Any]) -> dict[str, list[str]]:
    raw = health_trajectory(health).get("preemptive_action_reasons") or {}
    if not isinstance(raw, dict):
        return {}
    result: dict[str, list[str]] = {}
    for action in SESSION_PREEMPTIVE_ACTIONS:
        codes = raw.get(action) or []
        result[action] = unique_items([str(code) for code in codes if code])
    return {action: codes for action, codes in result.items() if codes}


def unique_items(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out
