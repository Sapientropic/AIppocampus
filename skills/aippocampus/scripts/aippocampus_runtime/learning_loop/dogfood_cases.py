"""Public-safe second-user dogfood cases for learning/action-time hints."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
REPORT_KIND = "aippocampus_learning_loop_second_user_dogfood_report"


def load_second_user_cases(path: Path) -> list[dict[str, Any]]:
    return [
        dict(json.loads(line))
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _phase_cases(rows: Iterable[Mapping[str, Any]]) -> dict[str, dict[str, Mapping[str, Any]]]:
    cases: dict[str, dict[str, Mapping[str, Any]]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        case_id = str(row.get("case_id") or "")
        phase = str(row.get("phase") or "")
        if case_id and phase:
            cases.setdefault(case_id, {})[phase] = row
    return cases


def _flag(row: Mapping[str, Any] | None, key: str) -> bool:
    return bool((row or {}).get(key))


def build_second_user_dogfood_report(
    rows: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    materialized = [dict(row) for row in rows if isinstance(row, Mapping)]
    cases = _phase_cases(materialized)
    case_reports: list[dict[str, Any]] = []
    for case_id, phases in sorted(cases.items()):
        before = phases.get("without_hint")
        after = phases.get("with_hint")
        case_reports.append(
            {
                "case_id": case_id,
                "category": str((after or before or {}).get("category") or ""),
                "first_wrong_action_avoided": _flag(before, "first_wrong_action_taken")
                and not _flag(after, "first_wrong_action_taken"),
                "broad_search_avoided": _flag(before, "broad_search_taken")
                and not _flag(after, "broad_search_taken"),
                "source_reopen_before_claim": _flag(after, "source_reopened_before_claim"),
                "hint_ignored_or_dismissed": _flag(after, "hint_ignored")
                or _flag(after, "hint_dismissed"),
                "repeat_failure_after_hint": _flag(after, "repeat_failure_after_hint"),
                "stale_warning_suppressed": _flag(before, "stale_warning_emitted")
                and not _flag(after, "stale_warning_emitted"),
                "current_thread_visibility_boundary_preserved": _flag(
                    after,
                    "current_thread_visibility_boundary_preserved",
                ),
            }
        )
    metrics = {
        "first_wrong_action_avoided": sum(1 for row in case_reports if row["first_wrong_action_avoided"]),
        "broad_search_avoided": sum(1 for row in case_reports if row["broad_search_avoided"]),
        "source_reopen_before_claim": sum(1 for row in case_reports if row["source_reopen_before_claim"]),
        "hint_ignored_or_dismissed": sum(1 for row in case_reports if row["hint_ignored_or_dismissed"]),
        "repeat_failure_after_hint": sum(1 for row in case_reports if row["repeat_failure_after_hint"]),
        "stale_warning_suppressed": sum(1 for row in case_reports if row["stale_warning_suppressed"]),
        "current_thread_visibility_boundary_preserved": sum(
            1 for row in case_reports if row["current_thread_visibility_boundary_preserved"]
        ),
    }
    encoded = json.dumps({"cases": case_reports, "metrics": metrics}, ensure_ascii=False, sort_keys=True)
    red_lines = {
        "raw_private_text_leak_count": int("PRIVATE_" in encoded),
        "local_path_leak_count": int("C:/" in encoded or "E:/" in encoded or "\\Users\\" in encoded),
        "source_truth_overclaim_count": int("source_truth" in encoded),
    }
    return {
        "kind": REPORT_KIND,
        "schema_version": SCHEMA_VERSION,
        "ok": bool(case_reports) and all(value == 0 for value in red_lines.values()),
        "case_count": len(case_reports),
        "metrics": metrics,
        "cases": case_reports,
        "red_lines": red_lines,
        "privacy_boundary": {
            "public_safe_or_private_sanitized_cases_only": True,
            "raw_private_text_serialized": False,
            "local_paths_serialized": False,
            "navigation_only": True,
        },
        "cannot_claim": [
            "causal_live_behavior_lift",
            "all_second_user_feedback_resolved",
            "source_truth_from_hint",
        ],
    }


__all__ = ["build_second_user_dogfood_report", "load_second_user_cases"]
