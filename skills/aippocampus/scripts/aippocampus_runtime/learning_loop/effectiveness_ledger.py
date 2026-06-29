"""Append-only effectiveness ledger for surfaced learning guidance.

The ledger tracks whether a navigation hint was later useful, ignored, or
followed by the same failure. It is deliberately not a scoring layer for source
truth: rows can only adjust future navigation priority and stale/noisy review
state.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from aippocampus_runtime.core import stable_json_tuple_id
from aippocampus_runtime.source.io_kernel import load_jsonl_dict_rows

SCHEMA_VERSION = 1
LEDGER_ROW_KIND = "aippocampus_learning_guidance_effectiveness_row"
REPORT_KIND = "aippocampus_learning_guidance_effectiveness_report"

OUTCOMES = {
    "prevented_repeat",
    "ignored",
    "repeated_failure_after_surface",
    "dismissed_noisy",
    "stale_superseded",
    "unclear",
    "self_report_only",
}
USEFUL_OUTCOMES = {"prevented_repeat"}
INEFFECTIVE_OUTCOMES = {"ignored", "repeated_failure_after_surface", "dismissed_noisy"}
ARCHIVE_OUTCOMES = {"stale_superseded"}
LOADED_LEDGER_ORIGIN = {
    "verified_origin": False,
    "origin_verified": False,
    "origin_kind": "operator_selected_effectiveness_ledger_without_integrity_manifest",
    "boundary": "ledger files adjust navigation priority only; parsed JSONL is not a source-trust anchor",
}


def _text(value: Any, limit: int = 160) -> str:
    text = str(value or "").strip().replace("\\", "/")
    if len(text) > limit:
        return text[: limit - 3].rstrip() + "..."
    return text


def _refs(values: Any, *, limit: int = 6) -> list[dict[str, Any]]:
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
        return []
    refs: list[dict[str, Any]] = []
    for item in values:
        if not isinstance(item, Mapping):
            continue
        clean = {
            key: _text(item.get(key), 140)
            for key in ("source_id", "source_ref", "thread_key", "message_id", "turn_id", "event_id")
            if item.get(key) not in (None, "", [])
        }
        if clean and clean not in refs:
            refs.append(clean)
        if len(refs) >= limit:
            break
    return refs


def _lesson_id(row: Mapping[str, Any]) -> str:
    return _text(
        row.get("lesson_id")
        or row.get("finding_id")
        or row.get("guidance_id")
        or row.get("record_id")
        or row.get("hint_id"),
        160,
    )


def _outcome(row: Mapping[str, Any]) -> str:
    value = _text(row.get("outcome") or row.get("effectiveness_outcome"), 80)
    return value if value in OUTCOMES else "unclear"


def _status_for(outcome: str, source_refs: Sequence[Mapping[str, Any]], *, self_report_only: bool) -> str:
    if self_report_only or outcome == "self_report_only":
        return "unproven"
    if not source_refs:
        return "review_overdue"
    if outcome in USEFUL_OUTCOMES:
        return "useful_signal"
    if outcome in INEFFECTIVE_OUTCOMES:
        return "ineffective"
    if outcome in ARCHIVE_OUTCOMES:
        return "archived"
    return "unproven"


def _priority_delta(status: str, outcome: str) -> float:
    if status == "useful_signal":
        return 0.2
    if status == "ineffective":
        return -0.25 if outcome == "repeated_failure_after_surface" else -0.15
    if status == "archived":
        return -0.5
    return 0.0


def _safe_float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _bounded_priority_delta(rows: Sequence[Mapping[str, Any]]) -> float:
    raw = sum(_safe_float(row.get("priority_delta")) for row in rows)
    return round(max(-1.0, min(1.0, raw)), 6)


def _aggregate_status(rows: Sequence[Mapping[str, Any]], *, priority_delta: float) -> str:
    statuses = Counter(str(row.get("effectiveness_status") or "unknown") for row in rows)
    if statuses.get("archived") and priority_delta <= 0:
        return "archived"
    if priority_delta < 0:
        return "ineffective"
    if priority_delta > 0:
        return "useful_signal"
    if statuses.get("review_overdue"):
        return "review_overdue"
    return "unproven"


def _aggregate_effectiveness_rows(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Collapse append-only rows into one navigation-pressure decision.

    The ledger is an audit trail, not a latest-state table. Future agents are
    tempted to let the newest positive row overwrite repeated failures because
    it is the easiest dict assignment; keep the cumulative rule here so cache
    eligibility follows the whole same-lesson history.
    """

    materialized = [row for row in rows if isinstance(row, Mapping)]
    priority_delta = _bounded_priority_delta(materialized)
    status = _aggregate_status(materialized, priority_delta=priority_delta)
    return {
        "effectiveness_status": status,
        "priority_delta": priority_delta,
        "ledger_row_count": len(materialized),
        "status_counts": dict(
            sorted(Counter(str(row.get("effectiveness_status") or "unknown") for row in materialized).items())
        ),
        "outcome_counts": dict(
            sorted(Counter(str(row.get("outcome") or "unknown") for row in materialized).items())
        ),
        "aggregate_policy": "bounded_cumulative_navigation_pressure",
    }


def ledger_rows_from_guidance_outcomes(
    surfaced_guidance: Iterable[Mapping[str, Any]],
    outcomes: Iterable[Mapping[str, Any]],
    *,
    surface: str = "replay",
) -> list[dict[str, Any]]:
    guidance_by_id = {
        _lesson_id(row): dict(row)
        for row in surfaced_guidance
        if isinstance(row, Mapping) and _lesson_id(row)
    }
    rows: list[dict[str, Any]] = []
    for outcome_row in outcomes:
        if not isinstance(outcome_row, Mapping):
            continue
        lesson_id = _lesson_id(outcome_row)
        guidance = guidance_by_id.get(lesson_id, {})
        outcome = _outcome(outcome_row)
        source_refs = _refs(outcome_row.get("source_refs") or guidance.get("source_refs"))
        event_refs = _refs(outcome_row.get("event_refs") or guidance.get("event_refs"))
        self_report_only = bool(outcome_row.get("self_report_only"))
        status = _status_for(outcome, source_refs, self_report_only=self_report_only)
        rows.append(
            {
                "kind": LEDGER_ROW_KIND,
                "schema_version": SCHEMA_VERSION,
                "ledger_id": stable_json_tuple_id(
                    "learn_eff",
                    lesson_id,
                    surface,
                    outcome,
                    source_refs,
                    event_refs,
                    ensure_ascii=False,
                    length=18,
                ),
                "lesson_id": lesson_id,
                "finding_id": _text(guidance.get("finding_id") or outcome_row.get("finding_id"), 160),
                "record_id": _text(guidance.get("record_id") or guidance.get("guidance_id") or lesson_id, 160),
                "surface": _text(outcome_row.get("surface") or surface, 80),
                "surface_event_refs": event_refs,
                "outcome": outcome,
                "source_refs": source_refs,
                "event_refs": event_refs,
                "effectiveness_status": status,
                "priority_delta": _priority_delta(status, outcome),
                "negative_counter": int(outcome == "repeated_failure_after_surface"),
                "privacy_boundary": {
                    "raw_command_text_stored": False,
                    "raw_stdout_stderr_stored": False,
                    "raw_source_snippet_stored": False,
                    "local_paths_stored": False,
                    "self_report_not_enough_to_ripen": True,
                },
                "navigation_only": True,
                "supports_factual_claim": False,
            }
        )
    return rows


def summarize_effectiveness_ledger(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    materialized = [dict(row) for row in rows if isinstance(row, Mapping)]
    status_counts = Counter(str(row.get("effectiveness_status") or "unknown") for row in materialized)
    outcome_counts = Counter(str(row.get("outcome") or "unknown") for row in materialized)
    negative_count = sum(int(row.get("negative_counter") or 0) for row in materialized)
    return {
        "kind": REPORT_KIND,
        "schema_version": SCHEMA_VERSION,
        "ok": True,
        "row_count": len(materialized),
        "status_counts": dict(sorted(status_counts.items())),
        "outcome_counts": dict(sorted(outcome_counts.items())),
        "repeat_failure_after_hint_count": negative_count,
        "navigation_priority_delta_total": round(
            sum(float(row.get("priority_delta") or 0.0) for row in materialized),
            6,
        ),
        "contract": {
            "effectiveness_is_navigation_priority_not_truth": True,
            "append_only_rows": True,
            "self_report_only_does_not_ripen": True,
            "raw_private_payloads_excluded": True,
        },
        "cannot_claim": [
            "causal_live_behavior_lift",
            "guidance_is_source_truth",
            "private_history_generalization",
        ],
    }


def apply_effectiveness_to_guidance(
    guidance: Iterable[Mapping[str, Any]],
    ledger_rows: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    rows_by_lesson: dict[str, list[Mapping[str, Any]]] = {}
    for row in ledger_rows:
        if not isinstance(row, Mapping):
            continue
        lesson = _lesson_id(row)
        if lesson:
            rows_by_lesson.setdefault(lesson, []).append(row)
    aggregates = {
        lesson: _aggregate_effectiveness_rows(rows)
        for lesson, rows in rows_by_lesson.items()
    }
    projected: list[dict[str, Any]] = []
    for item in guidance:
        if not isinstance(item, Mapping):
            continue
        row = dict(item)
        lesson = _lesson_id(row)
        ledger = aggregates.get(lesson)
        if ledger:
            row["effectiveness_status"] = ledger.get("effectiveness_status")
            row["navigation_priority_delta"] = ledger.get("priority_delta")
            row["effectiveness_ledger_row_count"] = ledger.get("ledger_row_count")
            row["effectiveness_aggregate_policy"] = ledger.get("aggregate_policy")
            if ledger.get("effectiveness_status") in {"ineffective", "archived"}:
                row["freshness"] = "stale"
                row["status"] = "archived" if ledger.get("effectiveness_status") == "archived" else "review"
        projected.append(row)
    return projected


def append_ledger_rows(path: Path, rows: Iterable[Mapping[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("a", encoding="utf-8", newline="\n") as fh:
        for row in rows:
            if row.get("kind") != LEDGER_ROW_KIND:
                raise ValueError(f"unsupported learning effectiveness row kind: {row.get('kind')}")
            payload = dict(row)
            payload.setdefault("verified_origin", True)
            payload.setdefault(
                "origin",
                {
                    "verified_origin": True,
                    "origin_kind": "local_effectiveness_ledger_append",
                    "boundary": "local append is authorized for navigation priority, not source truth",
                },
            )
            fh.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
            count += 1
    return count


def load_ledger_rows(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    for payload in load_jsonl_dict_rows(path).rows:
        if payload.get("kind") == LEDGER_ROW_KIND:
            row = dict(payload)
            row["verified_origin"] = False
            row["origin_verified"] = False
            row["origin"] = dict(LOADED_LEDGER_ORIGIN)
            rows.append(row)
    return rows


__all__ = [
    "LEDGER_ROW_KIND",
    "REPORT_KIND",
    "append_ledger_rows",
    "apply_effectiveness_to_guidance",
    "ledger_rows_from_guidance_outcomes",
    "load_ledger_rows",
    "summarize_effectiveness_ledger",
]
