"""Closeout-evidence lane for successor evidence sweeps.

Successor sweeps are inventory/report assemblers. Whether a closed successor
still provides a usable artifact or explicit deferral pointer is a closeout
policy question, so it lives here instead of being reimplemented in the main
sweep every time a new successor wave closes.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

HARD_BLOCKER_EXECUTION_PATHS: dict[int, dict[str, Any]] = {
    1929: {
        "path_kind": "open_successor_issue",
        "successor_issue": 2043,
        "blocker": "declared provider/model artifact required for AMemGym fixed-arm score",
    },
    1931: {
        "path_kind": "open_successor_issue",
        "successor_issue": 2043,
        "blocker": "declared provider/model artifact required for MemoryAgentBench generation/judge run",
    },
    1942: {
        "path_kind": "open_successor_issue",
        "successor_issue": 2044,
        "blocker": "host-faithful private compaction-survival/live trace required",
    },
    1944: {
        "path_kind": "open_successor_issue",
        "successor_issue": 2044,
        "blocker": "agency timing and annoyance require live trace evidence",
    },
    1945: {
        "path_kind": "open_successor_issue",
        "successor_issue": 2044,
        "blocker": "observed PreToolUse action-time hint behavior requires live host trace",
    },
}

BOUNDED_VALIDATION_DEFERRED_PATHS: dict[int, dict[str, Any]] = {
    1981: {
        "path_kind": "open_successor_issue",
        "successor_issue": 2045,
        "blocker": "retained private/local E2E50 case shortfall",
    }
}


def declared_successor_issue_numbers() -> list[int]:
    numbers: set[int] = set()
    for path in [
        *HARD_BLOCKER_EXECUTION_PATHS.values(),
        *BOUNDED_VALIDATION_DEFERRED_PATHS.values(),
    ]:
        number = int(path.get("successor_issue") or 0)
        if number:
            numbers.add(number)
    return sorted(numbers)


def execution_path_status(
    path: Mapping[str, Any] | None,
    *,
    live_state: Mapping[int, Mapping[str, Any]],
    github_state_checked: bool,
) -> dict[str, Any]:
    if not path:
        return {
            "path_kind": "missing",
            "ok": False,
            "status": "missing_successor_or_deferred_pointer",
        }
    result = dict(path)
    successor_issue = int(result.get("successor_issue") or 0)
    if successor_issue:
        result["successor_issue"] = successor_issue
        live_row = live_state.get(successor_issue)
        if live_row:
            successor_state = str(live_row.get("state") or "").casefold()
            pointer_kind = str(live_row.get("closeout_pointer_kind") or "none")
            result["successor_state"] = successor_state
            if live_row.get("closedAt"):
                result["successor_closed_at"] = live_row.get("closedAt")
            result["successor_closeout_pointer_kind"] = pointer_kind
            result["successor_closeout_pointer_present"] = bool(
                live_row.get("closeout_pointer_present")
            )
            if successor_state == "open":
                result["status"] = "open_successor"
                result["ok"] = True
            elif pointer_kind == "artifact_pointer":
                result["status"] = "closed_successor_artifact_pointer"
                result["ok"] = True
            elif pointer_kind == "explicit_deferral_pointer":
                result["status"] = "closed_successor_deferred_pointer"
                result["ok"] = True
            else:
                result["status"] = "closed_successor_without_artifact_pointer"
                result["ok"] = False
        elif github_state_checked and live_state and successor_issue <= max(live_state):
            result["status"] = "successor_not_seen_in_live_github_state"
            result["ok"] = False
        elif github_state_checked:
            result["status"] = "declared_successor_outside_live_fixture_range"
            result["ok"] = True
        else:
            result["status"] = "declared_successor_not_live_checked"
            result["ok"] = True
        return result
    if result.get("deferred_pointer"):
        result["status"] = "deferred_pointer_recorded"
        result["ok"] = True
        return result
    if result.get("reopened_owner"):
        result["status"] = "reopened_owner_recorded"
        result["ok"] = True
        return result
    result["status"] = "missing_successor_or_deferred_pointer"
    result["ok"] = False
    return result


__all__ = [
    "BOUNDED_VALIDATION_DEFERRED_PATHS",
    "HARD_BLOCKER_EXECUTION_PATHS",
    "declared_successor_issue_numbers",
    "execution_path_status",
]
