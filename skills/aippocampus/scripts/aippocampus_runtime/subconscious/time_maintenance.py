#!/usr/bin/env python3
"""Opt-in time-driven maintenance lane over local registry metadata.

This lane is deliberately metadata-first. It notices due work from existing
registry and sidecar shapes, then writes bounded maintenance candidates for a
host or background worker to inspect later. It does not claim hooks wake by
themselves, does not scan raw transcripts, and does not execute heavyweight
model work from the foreground process.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aippocampus_runtime.cognitive_worker_mode import resolve_cognitive_worker_mode
from aippocampus_runtime.source.io_kernel import load_json_dict
from aippocampus_runtime.subconscious import scheduler
from aippocampus_runtime.subconscious.agent_fallback_queue import TASKS_NAME
from aippocampus_runtime.subconscious.scheduler_lock import FileLock
from aippocampus_runtime.subconscious.time_maintenance_plan import (
    CANDIDATES_FILE_NAME,
    DEFAULT_API_KEY_ENV,
    DEFAULT_COOLDOWN_SECONDS,
    DEFAULT_DORMANT_AFTER_DAYS,
    DEFAULT_LEASE_SECONDS,
    DEFAULT_STALE_ASSOCIATION_DAYS,
    DEFAULT_STALE_FRONTIER_DAYS,
    SCHEMA_VERSION,
    append_jsonl,
    build_time_maintenance_plan,
    iso_utc,
    normalize_now,
)

AGENT_FALLBACK_TASK_KIND = "agent_fallback_time_maintenance_task"


def _filtered_writable_candidates(
    candidates: Sequence[dict[str, Any]],
    state: dict[str, Any],
    *,
    now_ts: float,
    cooldown_seconds: int,
) -> tuple[list[dict[str, Any]], str | None]:
    writable: list[dict[str, Any]] = []
    leased = False
    cooldown = False
    for item in candidates:
        project_label = str(((item.get("project") or {}).get("label")) or "")
        project_state = state.setdefault("projects", {}).setdefault(project_label, {})
        if scheduler.lease_active(project_state, now_ts):
            leased = True
            continue
        last_enqueue = float(project_state.get("last_enqueue_ts") or 0.0)
        if last_enqueue and now_ts - last_enqueue < cooldown_seconds:
            cooldown = True
            continue
        writable.append(item)
    if writable:
        return writable, None
    if leased:
        return [], "leased_projects"
    if cooldown:
        return [], "enqueue_cooldown"
    return [], "no_due_projects"


def _claim_project_leases(
    candidates: Sequence[dict[str, Any]],
    state: dict[str, Any],
    registry: Mapping[str, Any],
    *,
    now_ts: float,
    lease_seconds: int,
) -> list[str]:
    stats_by_label = scheduler.project_stats_from_registry(dict(registry))
    labels = sorted({str(((item.get("project") or {}).get("label")) or "") for item in candidates})
    claimed: list[str] = []
    for label in labels:
        stats = stats_by_label.get(label)
        if not stats:
            continue
        reasons = sorted(
            {
                str(item.get("reason_code") or "")
                for item in candidates
                if ((item.get("project") or {}).get("label")) == label
            }
        )
        project_state = state.setdefault("projects", {}).setdefault(label, {})
        scheduler.claim_project_lease(
            project_state,
            stats,
            f"time_maintenance:{','.join(reasons)}",
            now_ts=now_ts,
            lease_seconds=lease_seconds,
        )
        claimed.append(label)
    return claimed


def _finish_project_state(
    labels: Iterable[str],
    state: dict[str, Any],
    *,
    now_ts: float,
    written_count: int,
    reason_codes: Sequence[str],
) -> None:
    for label in labels:
        project_state = state.setdefault("projects", {}).setdefault(label, {})
        project_state["last_enqueue_ts"] = now_ts
        project_state["last_enqueue_at"] = iso_utc(
            datetime.fromtimestamp(now_ts, tz=timezone.utc)
        )
        project_state["last_enqueue_reason"] = f"time_maintenance:{','.join(reason_codes)}"
        project_state["last_status"] = "time_maintenance_candidates_written"
        project_state["last_time_maintenance_candidate_count"] = int(written_count)
        scheduler.clear_project_lease(project_state)


def _enqueue_agent_fallback_tasks(
    *,
    root: Path,
    candidates: Sequence[dict[str, Any]],
    worker_mode: Mapping[str, Any],
    generated_at: str,
) -> int:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in candidates:
        label = str(((item.get("project") or {}).get("label")) or "")
        grouped.setdefault(label, []).append(item)
    rows: list[dict[str, Any]] = []
    for label, items in sorted(grouped.items()):
        rows.append(
            {
                "schema_version": SCHEMA_VERSION,
                "kind": AGENT_FALLBACK_TASK_KIND,
                "created_at": generated_at,
                "project_label": label,
                "provenance": "agent_fallback",
                "cognitive_worker_status": worker_mode.get("status"),
                "reason_codes": sorted({str(item.get("reason_code") or "") for item in items}),
                "candidate_ids": [str(item.get("candidate_id") or "") for item in items],
                "source_pack_contract": {
                    "input": "metadata_candidate_ids_then_clean_source_reopen",
                    "raw_rollout_allowed": False,
                    "raw_private_text_in_public_report": False,
                },
                "output_contract": {
                    "candidate_kinds": [
                        "scheduled_revisit_candidate",
                        "frontier_refresh_candidate",
                        "journey_reentry_candidate",
                        "question_reopen_candidate",
                        "association_cache_refresh_candidate",
                    ],
                    "staging_only": True,
                    "source_refs_required": True,
                    "foreground_sync_wait": False,
                },
            }
        )
    return append_jsonl(root / TASKS_NAME, rows)


def run_time_maintenance(
    *,
    registry_dir: Path | str,
    cwd: Path | str | None = None,
    project: str | None = None,
    all_projects: bool = False,
    state_file: Path | str | None = None,
    now: str | datetime | None = None,
    dry_run: bool = True,
    cooldown_seconds: int = DEFAULT_COOLDOWN_SECONDS,
    lease_seconds: int = DEFAULT_LEASE_SECONDS,
    stale_frontier_days: int = DEFAULT_STALE_FRONTIER_DAYS,
    dormant_after_days: int = DEFAULT_DORMANT_AFTER_DAYS,
    stale_association_days: int = DEFAULT_STALE_ASSOCIATION_DAYS,
    enqueue_worker: bool = False,
    api_key_env: str = DEFAULT_API_KEY_ENV,
) -> dict[str, Any]:
    root = Path(registry_dir).resolve()
    now_dt = normalize_now(now)
    now_ts = now_dt.timestamp()
    plan = build_time_maintenance_plan(
        registry_dir=root,
        cwd=cwd,
        project=project,
        all_projects=all_projects,
        now=now_dt,
        stale_frontier_days=stale_frontier_days,
        dormant_after_days=dormant_after_days,
        stale_association_days=stale_association_days,
        dry_run=dry_run,
    )
    worker_mode = resolve_cognitive_worker_mode(api_key_env=api_key_env)
    plan["cognitive_worker"] = worker_mode
    plan["written_count"] = 0
    plan["agent_fallback_task_count"] = 0
    if not plan["candidates"]:
        plan["skipped"] = "no_due_projects"
        return plan
    if dry_run:
        return plan

    state_path = scheduler.state_path(root, Path(state_file).resolve() if state_file else None)
    registry = load_json_dict(scheduler.registry_path(root)).data
    try:
        with FileLock(root / "time_maintenance_enqueue.lock"):
            state = scheduler.load_state(state_path)
            writable, skipped = _filtered_writable_candidates(
                plan["candidates"],
                state,
                now_ts=now_ts,
                cooldown_seconds=cooldown_seconds,
            )
            if not writable:
                plan["skipped"] = skipped or "no_due_projects"
                scheduler.save_state(state_path, state)
                return plan
            claimed = _claim_project_leases(
                writable,
                state,
                registry,
                now_ts=now_ts,
                lease_seconds=lease_seconds,
            )
            try:
                written = append_jsonl(root / CANDIDATES_FILE_NAME, writable)
                worker_count = 0
                if enqueue_worker and worker_mode.get("resolved_mode") == "agent_fallback":
                    worker_count = _enqueue_agent_fallback_tasks(
                        root=root,
                        candidates=writable,
                        worker_mode=worker_mode,
                        generated_at=str(plan["generated_at"]),
                    )
                _finish_project_state(
                    claimed,
                    state,
                    now_ts=now_ts,
                    written_count=written,
                    reason_codes=plan["reason_codes"],
                )
                plan["candidates"] = writable
                plan["candidate_count"] = len(writable)
                plan["written_count"] = written
                plan["agent_fallback_task_count"] = worker_count
                scheduler.save_state(state_path, state)
                return plan
            # aippocampus-debt-ok: broad-exception-boundary
            # Roll back local lease claims, persist that rollback, then re-raise
            # the original failure so operators see the real enqueue error.
            except Exception:
                for label in claimed:
                    scheduler.clear_project_lease(state.setdefault("projects", {}).setdefault(label, {}))
                scheduler.save_state(state_path, state)
                raise
    except RuntimeError as exc:
        if "already running" in str(exc):
            plan["skipped"] = "enqueue_locked"
            return plan
        raise


def public_time_maintenance_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    worker_obj = payload.get("cognitive_worker")
    worker: Mapping[str, Any] = worker_obj if isinstance(worker_obj, Mapping) else {}
    return {
        "kind": payload.get("kind"),
        "dry_run": bool(payload.get("dry_run")),
        "skipped": payload.get("skipped"),
        "project_count": int(payload.get("project_count") or 0),
        "candidate_count": int(payload.get("candidate_count") or 0),
        "reason_codes": list(payload.get("reason_codes") or []),
        "written_count": int(payload.get("written_count") or 0),
        "agent_fallback_task_count": int(payload.get("agent_fallback_task_count") or 0),
        "privacy_boundary": payload.get("privacy_boundary") or {},
        "cognitive_worker": {
            "resolved_mode": worker.get("resolved_mode"),
            "status": worker.get("status"),
        },
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry-dir")
    parser.add_argument("--state-file")
    parser.add_argument("--cwd")
    parser.add_argument("--project")
    parser.add_argument("--all-projects", action="store_true")
    parser.add_argument("--now")
    parser.add_argument("--write", action="store_true", help="Append bounded candidate artifacts.")
    parser.add_argument("--enqueue-worker", action="store_true")
    parser.add_argument("--cooldown-seconds", type=int, default=DEFAULT_COOLDOWN_SECONDS)
    parser.add_argument("--lease-seconds", type=int, default=DEFAULT_LEASE_SECONDS)
    parser.add_argument("--stale-frontier-days", type=int, default=DEFAULT_STALE_FRONTIER_DAYS)
    parser.add_argument("--dormant-after-days", type=int, default=DEFAULT_DORMANT_AFTER_DAYS)
    parser.add_argument("--stale-association-days", type=int, default=DEFAULT_STALE_ASSOCIATION_DAYS)
    parser.add_argument("--api-key-env", default=DEFAULT_API_KEY_ENV)
    parser.add_argument("--json", action="store_true", dest="json_output")
    parser.add_argument("--include-private-report", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    root = Path(args.registry_dir).resolve() if args.registry_dir else scheduler.registry_dir()
    payload = run_time_maintenance(
        registry_dir=root,
        cwd=args.cwd,
        project=args.project,
        all_projects=args.all_projects,
        state_file=args.state_file,
        now=args.now,
        dry_run=not args.write,
        cooldown_seconds=args.cooldown_seconds,
        lease_seconds=args.lease_seconds,
        stale_frontier_days=args.stale_frontier_days,
        dormant_after_days=args.dormant_after_days,
        stale_association_days=args.stale_association_days,
        enqueue_worker=args.enqueue_worker,
        api_key_env=args.api_key_env,
    )
    output = payload if args.include_private_report else public_time_maintenance_payload(payload)
    if args.json_output:
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        mode = "dry-run" if payload.get("dry_run") else "write"
        print(
            "time maintenance "
            f"{mode}: candidates={payload.get('candidate_count', 0)} "
            f"written={payload.get('written_count', 0)} "
            f"skipped={payload.get('skipped') or ''}".rstrip()
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
