"""Staging queue for agent-backed subconscious fallback work.

The queue is intentionally boring: it records that a later host agent may build
source-ref-backed candidates from clean source.  It does not call an agent,
write clean source, or promote model/agent synthesis into memory.  Keeping this
owner separate prevents the hook-safe scheduler from growing into a background
cognition implementation.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from aippocampus_runtime.core import now_utc

TASKS_NAME = "agent_fallback_tasks.jsonl"


def _append_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True))
            fh.write("\n")


def _lease_active(project_state: dict[str, Any], now_ts: float) -> bool:
    lease_until = float(project_state.get("lease_until_ts") or 0.0)
    return lease_until > now_ts


def _task_row(stats: Any, reason: str, worker_mode: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "kind": "agent_fallback_subconscious_task",
        "created_at": now_utc(),
        "project_label": stats.label,
        "reason": reason,
        "provenance": "agent_fallback",
        "cognitive_worker_status": worker_mode.get("status"),
        "counts": {
            "clean_turn_count": stats.clean_turn_count,
            "clean_message_count": stats.clean_message_count,
            "thread_count": stats.thread_count,
        },
        "source_pack_contract": {
            "input": "clean_source_and_source_refs_only",
            "raw_rollout_allowed": False,
            "raw_private_text_in_public_report": False,
        },
        "output_contract": {
            "candidate_kinds": [
                "semantic_cue_candidate",
                "topic_epoch_candidate",
                "dream_residue_candidate",
                "cache_warmup_hint",
            ],
            "staging_only": True,
            "source_refs_required": True,
            "foreground_sync_wait": False,
            "cannot_claim": [
                "agent_fallback_output_is_not_source_truth",
                "source_refs_required_before_promotion",
            ],
        },
    }


def enqueue_due_tasks(
    *,
    root: Path,
    state: dict[str, Any],
    due: list[tuple[Any, str]],
    worker_mode: dict[str, Any],
    now_ts: float,
    enqueue_cooldown_seconds: int,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    leased: list[dict[str, str]] = []
    for stats, reason in due:
        project_state = state.setdefault("projects", {}).setdefault(stats.label, {})
        if _lease_active(project_state, now_ts):
            leased.append({"label": stats.label, "reason": reason})
            continue
        last_enqueue = float(project_state.get("last_enqueue_ts") or 0.0)
        if last_enqueue and now_ts - last_enqueue < enqueue_cooldown_seconds:
            continue
        project_state["last_enqueue_ts"] = now_ts
        project_state["last_enqueue_at"] = now_utc()
        project_state["last_enqueue_reason"] = f"agent_fallback:{reason}"
        project_state["last_status"] = "agent_fallback_queued"
        project_state["last_clean_turn_count"] = stats.clean_turn_count
        project_state["last_clean_message_count"] = stats.clean_message_count
        project_state["last_thread_count"] = stats.thread_count
        rows.append(_task_row(stats, reason, worker_mode))

    _append_jsonl(root / TASKS_NAME, rows)
    if rows:
        return {
            "queued": True,
            "skipped": "agent_fallback_queued",
            "agent_fallback_task_count": len(rows),
        }
    if leased:
        return {"queued": False, "skipped": "leased_projects", "leased_projects": leased}
    return {"queued": False, "skipped": "enqueue_cooldown", "agent_fallback_task_count": 0}
