"""Low-authority APW follow-through feedback events.

These events calibrate future navigation only. They never prove source truth and
they deliberately use the existing APW feedback row shape so the walker keeps
one damping/reinforcement policy.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from aippocampus_runtime import core
from aippocampus_runtime.mcp import recall_navigation

POSITIVE_OUTCOMES = {"source_reopened", "source_helped_task", "task_advanced"}
NEGATIVE_OUTCOMES = {
    "action_ignored",
    "source_not_useful",
    "wrong_hop",
    "irrelevant_drag",
    "stale_route",
    "superseded_route",
    "private_or_wrong_scope",
    "manual_search_needed_first",
}
OUTCOME_TO_SIGNAL = {
    "source_reopened": "source_reopen_success",
    "source_helped_task": "user_confirmed",
    "task_advanced": "user_confirmed",
    "action_ignored": "ignored",
    "source_not_useful": "wrong_route_drag",
    "wrong_hop": "wrong_route_drag",
    "irrelevant_drag": "wrong_route_drag",
    "stale_route": "superseded",
    "superseded_route": "superseded",
    "private_or_wrong_scope": "blocked",
    "manual_search_needed_first": "wrong_route_drag",
}


def _text(value: Any, limit: int = 120) -> str:
    return core.compact_text(str(value or "").strip(), limit)


def _clean_refs(refs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    clean: list[dict[str, Any]] = []
    for ref in refs:
        row = recall_navigation._clean_ref(ref)  # noqa: SLF001 - shared source-ref normalizer.
        if row:
            clean.append(row)
    return clean[:4]


def build_followthrough_event(
    *,
    route_id: str,
    outcome: str,
    scope_bucket: str,
    source_refs: list[dict[str, Any]] | None = None,
    occurred_at: str | None = None,
    freshness: str = "current",
    note: str = "",
) -> dict[str, Any]:
    safe_outcome = _text(outcome, 80)
    if safe_outcome not in OUTCOME_TO_SIGNAL:
        raise ValueError(f"unknown APW follow-through outcome: {safe_outcome}")
    signal = OUTCOME_TO_SIGNAL[safe_outcome]
    event = {
        "kind": "aippocampus_apw_followthrough_feedback",
        "schema_version": 1,
        "route_id": _text(route_id, 160),
        "candidate_id": _text(route_id, 160),
        "outcome": safe_outcome,
        "signal": signal,
        "scope_bucket": _text(scope_bucket, 80) or "public_default",
        "freshness": _text(freshness, 80) or "current",
        "occurred_at": occurred_at or core.now_utc(),
        "positive": safe_outcome in POSITIVE_OUTCOMES,
        "negative": safe_outcome in NEGATIVE_OUTCOMES,
        "source_refs": _clean_refs(source_refs or []),
        "authority": "navigation_calibration_only",
        "claim_boundary": "feedback_is_not_source_truth",
        "note": _text(note, 120),
    }
    return {key: value for key, value in event.items() if value not in ("", [], None)}


def append_followthrough_event(path: str | Path, event: dict[str, Any]) -> dict[str, Any]:
    target = Path(path).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
    return {
        "ok": True,
        "kind": "aippocampus_apw_followthrough_feedback_receipt",
        "wrote": True,
        "path_written": False,
        "route_id": event.get("route_id"),
        "outcome": event.get("outcome"),
        "signal": event.get("signal"),
        "claim_boundary": "feedback_is_not_source_truth",
    }


__all__ = ["append_followthrough_event", "build_followthrough_event"]
