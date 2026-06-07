"""Metadata scanners for opt-in time-driven maintenance candidates."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aippocampus_runtime.core import compact_text, stable_text_fingerprint
from aippocampus_runtime.journey import tracking as journey_tracking
from aippocampus_runtime.question import health as question_health
from aippocampus_runtime.question.constants import DEFAULT_DORMANT_AFTER_DAYS
from aippocampus_runtime.subconscious import scheduler

SCHEMA_VERSION = 1
PLAN_KIND = "aippocampus_time_driven_maintenance_plan"
CANDIDATE_KIND = "aippocampus_time_driven_maintenance_candidate"
CANDIDATES_FILE_NAME = "time_maintenance_candidates.jsonl"

DEFAULT_COOLDOWN_SECONDS = scheduler.DEFAULT_ENQUEUE_COOLDOWN_SECONDS
DEFAULT_LEASE_SECONDS = scheduler.DEFAULT_PROJECT_LEASE_SECONDS
DEFAULT_STALE_FRONTIER_DAYS = 21
DEFAULT_STALE_ASSOCIATION_DAYS = 14
DEFAULT_API_KEY_ENV = scheduler.DEFAULT_API_KEY_ENV

REASON_CODES = {
    "scheduled_revisit",
    "stale_frontier",
    "camped_journey_due",
    "dormant_question_due",
    "stale_association_cache",
    "health_preemptive_due",
}

ACTION_BY_REASON = {
    "scheduled_revisit": "prepare_scheduled_revisit_candidate",
    "stale_frontier": "prepare_frontier_refresh_candidate",
    "camped_journey_due": "prepare_journey_reentry_candidate",
    "dormant_question_due": "prepare_question_reopen_candidate",
    "stale_association_cache": "refresh_association_cache",
    "health_preemptive_due": "run_threshold_maintenance_action",
}

SCHEDULED_REVISIT_FILES = (
    "scheduled_revisits.jsonl",
    "agency_tickets.jsonl",
    "agency_affordance_tickets.jsonl",
)
JOURNEY_FILES = ("journeys.jsonl", "journey_tracking.jsonl")
ASSOCIATION_CACHE_FILES = ("associations.json", "semantic_cues.jsonl", "semantic_triggers.jsonl")


def parse_time(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text or text == "topic_epoch_end":
        return None
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).replace(microsecond=0)


def normalize_now(value: str | datetime | None) -> datetime:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).replace(microsecond=0)
    return parse_time(value) or datetime.now(timezone.utc).replace(microsecond=0)


def iso_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def append_jsonl(path: Path, rows: Sequence[Mapping[str, Any]]) -> int:
    if not rows:
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as fh:
        for row in rows:
            fh.write(json.dumps(dict(row), ensure_ascii=False, sort_keys=True))
            fh.write("\n")
    return len(rows)


def _iter_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    if not path.exists():
        return
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict):
                yield item


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _project_hash(label: str) -> str:
    return stable_text_fingerprint(label, namespace="time-maintenance-project", prefix="project", length=16)


def _subject_hash(*parts: Any) -> str:
    text = json.dumps(parts, ensure_ascii=False, sort_keys=True, default=str)
    return stable_text_fingerprint(text, namespace="time-maintenance-subject", prefix="subject", length=18)


def _candidate_id(*parts: Any) -> str:
    text = json.dumps(parts, ensure_ascii=False, sort_keys=True, default=str)
    return stable_text_fingerprint(text, namespace="time-maintenance-candidate", prefix="tmc", length=20)


def _source_ref_count(value: Any) -> int:
    if isinstance(value, list | tuple):
        return sum(1 for item in value if isinstance(item, Mapping))
    if isinstance(value, Mapping):
        return 1
    return 0


def _first_time(row: Mapping[str, Any], fields: Sequence[str]) -> datetime | None:
    for field in fields:
        parsed = parse_time(row.get(field))
        if parsed:
            return parsed
    return None


def _row_trigger(row: Mapping[str, Any]) -> str:
    why_now = row.get("why_now")
    if isinstance(why_now, Mapping):
        trigger = why_now.get("trigger")
        if trigger:
            return str(trigger)
    return str(row.get("trigger") or row.get("why_now_trigger") or "")


def _row_project_label(row: Mapping[str, Any]) -> str:
    scope = row.get("scope")
    scope_label = scope.get("label") if isinstance(scope, Mapping) else ""
    return str(row.get("project_label") or row.get("project") or scope_label or "")


def _matches_project(row: Mapping[str, Any], stats: scheduler.ProjectStats) -> bool:
    label = _row_project_label(row)
    return not label or label == stats.label


def _candidate(
    *,
    stats: scheduler.ProjectStats,
    reason_code: str,
    subject_kind: str,
    subject_id: str,
    due_at: datetime | None,
    source_ref_count: int = 0,
    generated_at: str,
) -> dict[str, Any]:
    safe_subject = compact_text(str(subject_id or ""), 100) or _subject_hash(subject_kind, reason_code)
    cid = _candidate_id(stats.label, reason_code, subject_kind, safe_subject, iso_utc(due_at) if due_at else "")
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": CANDIDATE_KIND,
        "candidate_id": cid,
        "created_at": generated_at,
        "project": {
            "label": stats.label,
            "label_hash": _project_hash(stats.label),
        },
        "reason_code": reason_code,
        "maintenance_action": {
            "verb": ACTION_BY_REASON[reason_code],
            "bounded": True,
            "write_scope": "staging_candidate_only",
        },
        "subject": {
            "kind": subject_kind,
            "id": safe_subject,
        },
        "due_at": iso_utc(due_at) if due_at else "",
        "source_ref_count": int(source_ref_count),
        "source_pack_contract": {
            "input": "registry_metadata_and_sidecar_refs_only",
            "raw_prompt_text_default": False,
            "raw_rollout_allowed": False,
        },
        "output_contract": {
            "candidate_only": True,
            "source_refs_required_before_promotion": True,
            "foreground_hook_wait": False,
        },
        "privacy_boundary": {
            "raw_text_included": False,
            "local_paths_included": False,
            "public_reason_code": reason_code,
        },
    }


def _scheduled_revisit_candidates(
    root: Path,
    stats: scheduler.ProjectStats,
    *,
    now_dt: datetime,
    generated_at: str,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for name in SCHEDULED_REVISIT_FILES:
        for row in _iter_jsonl(root / name):
            if not _matches_project(row, stats):
                continue
            if _row_trigger(row) != "scheduled_revisit":
                continue
            due_at = _first_time(
                row,
                ("due_at", "scheduled_for", "revisit_after", "next_revisit_at", "review_after"),
            )
            if not due_at or due_at > now_dt:
                continue
            expires_at = parse_time(row.get("expires_at"))
            if expires_at and expires_at < now_dt:
                continue
            subject_id = str(
                row.get("ticket_id")
                or row.get("affordance_id")
                or row.get("scheduled_revisit_id")
                or _subject_hash(name, row.get("scope"), due_at.isoformat())
            )
            candidates.append(
                _candidate(
                    stats=stats,
                    reason_code="scheduled_revisit",
                    subject_kind="agency_ticket",
                    subject_id=subject_id,
                    due_at=due_at,
                    source_ref_count=_source_ref_count(row.get("source_refs") or row.get("evidence_refs")),
                    generated_at=generated_at,
                )
            )
    return candidates


def _journey_candidates(
    root: Path,
    stats: scheduler.ProjectStats,
    *,
    now_dt: datetime,
    generated_at: str,
    stale_frontier_days: int,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    stale_delta_days = max(0, int(stale_frontier_days))
    for name in JOURNEY_FILES:
        for row in _iter_jsonl(root / name):
            if row.get("kind") != journey_tracking.JOURNEY_KIND or not _matches_project(row, stats):
                continue
            status = str(row.get("status") or "")
            if status in {"arrived", "abandoned"}:
                continue
            last_seen = parse_time(row.get("last_seen"))
            subject_id = str(row.get("journey_id") or _subject_hash(name, row.get("path_label")))
            source_count = _source_ref_count(
                row.get("current_frontier_source_refs") or row.get("source_refs")
            )
            if status == "camped":
                candidates.append(
                    _candidate(
                        stats=stats,
                        reason_code="camped_journey_due",
                        subject_kind="journey",
                        subject_id=subject_id,
                        due_at=last_seen,
                        source_ref_count=source_count,
                        generated_at=generated_at,
                    )
                )
            elif last_seen and (now_dt - last_seen).days >= stale_delta_days:
                candidates.append(
                    _candidate(
                        stats=stats,
                        reason_code="stale_frontier",
                        subject_kind="journey_frontier",
                        subject_id=subject_id,
                        due_at=last_seen,
                        source_ref_count=source_count,
                        generated_at=generated_at,
                    )
                )
    return candidates


def _frontier_marker_candidates(
    root: Path,
    stats: scheduler.ProjectStats,
    *,
    now_dt: datetime,
    generated_at: str,
    stale_frontier_days: int,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for row in _iter_jsonl(root / "subconscious_jobs.jsonl"):
        if row.get("finding_kind") != "frontier_marker" or not _matches_project(row, stats):
            continue
        created = parse_time(row.get("created_at"))
        if not created or (now_dt - created).days < max(0, int(stale_frontier_days)):
            continue
        subject_id = str(row.get("fingerprint") or row.get("finding_id") or _subject_hash("frontier", row))
        candidates.append(
            _candidate(
                stats=stats,
                reason_code="stale_frontier",
                subject_kind="frontier_marker",
                subject_id=subject_id,
                due_at=created,
                source_ref_count=_source_ref_count(row.get("source_refs")),
                generated_at=generated_at,
            )
        )
    return candidates


def _question_candidates(
    root: Path,
    stats: scheduler.ProjectStats,
    *,
    now_dt: datetime,
    generated_at: str,
    dormant_after_days: int,
) -> list[dict[str, Any]]:
    jobs_path = root / "subconscious_jobs.jsonl"
    if not jobs_path.exists():
        return []
    try:
        payload = question_health.question_health_stats(
            jobs_path,
            now=now_dt,
            dormant_after_days=dormant_after_days,
        )
    except Exception:
        return []
    candidates: list[dict[str, Any]] = []
    for item in payload.get("lifecycle") or []:
        if not isinstance(item, Mapping) or item.get("state") != "dormant":
            continue
        subject_id = str(item.get("unit_id") or _subject_hash("question", item.get("first_seen")))
        due_at = parse_time(item.get("last_seen"))
        candidates.append(
            _candidate(
                stats=stats,
                reason_code="dormant_question_due",
                subject_kind=str(item.get("unit_type") or "question"),
                subject_id=subject_id,
                due_at=due_at,
                source_ref_count=int(item.get("source_ref_count") or 0),
                generated_at=generated_at,
            )
        )
    return candidates


def _latest_jsonl_time(path: Path) -> datetime | None:
    latest: datetime | None = None
    for row in _iter_jsonl(path):
        parsed = _first_time(row, ("updated_at", "created_at", "timestamp"))
        if parsed and (latest is None or parsed > latest):
            latest = parsed
    if latest:
        return latest
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).replace(microsecond=0)
    except OSError:
        return None


def _association_candidates(
    root: Path,
    stats: scheduler.ProjectStats,
    *,
    now_dt: datetime,
    generated_at: str,
    stale_association_days: int,
) -> list[dict[str, Any]]:
    stale_after = max(0, int(stale_association_days))
    candidates: list[dict[str, Any]] = []
    for name in ASSOCIATION_CACHE_FILES:
        path = root / name
        if not path.exists():
            continue
        updated = parse_time(_load_json(path).get("updated_at")) if path.suffix == ".json" else _latest_jsonl_time(path)
        if not updated or (now_dt - updated).days < stale_after:
            continue
        candidates.append(
            _candidate(
                stats=stats,
                reason_code="stale_association_cache",
                subject_kind="association_cache",
                subject_id=path.stem,
                due_at=updated,
                source_ref_count=0,
                generated_at=generated_at,
            )
        )
    return candidates


def _action_rows_from_health(entry: Mapping[str, Any]) -> Iterable[Mapping[str, Any]]:
    health = entry.get("health") if isinstance(entry.get("health"), Mapping) else {}
    for key in ("recommended_actions", "preemptive_actions"):
        rows = health.get(key) if isinstance(health, Mapping) else []
        if isinstance(rows, list):
            yield from (row for row in rows if isinstance(row, Mapping))
    trajectory = health.get("health_trajectory") if isinstance(health, Mapping) else {}
    rows = trajectory.get("preemptive_actions") if isinstance(trajectory, Mapping) else []
    if isinstance(rows, list):
        yield from (row for row in rows if isinstance(row, Mapping))


def _health_candidates(
    registry: Mapping[str, Any],
    stats: scheduler.ProjectStats,
    *,
    generated_at: str,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for entry in registry.get("threads") or []:
        if not isinstance(entry, Mapping):
            continue
        if scheduler.thread_project_label(dict(entry)) != stats.label:
            continue
        for action in _action_rows_from_health(entry):
            action_id = compact_text(str(action.get("id") or action.get("action") or ""), 80)
            if not action_id:
                continue
            candidates.append(
                _candidate(
                    stats=stats,
                    reason_code="health_preemptive_due",
                    subject_kind="health_action",
                    subject_id=action_id,
                    due_at=None,
                    source_ref_count=0,
                    generated_at=generated_at,
                )
            )
    return candidates


def _selected_projects(
    registry: Mapping[str, Any],
    *,
    cwd: Path | None,
    project: str | None,
    all_projects: bool,
) -> list[scheduler.ProjectStats]:
    stats_by_label = scheduler.project_stats_from_registry(dict(registry))
    if all_projects:
        labels = sorted(stats_by_label)
    elif project:
        labels = [project]
    else:
        inferred = scheduler.project_for_cwd(dict(registry), cwd)
        labels = [inferred] if inferred else []
    return [stats_by_label[label] for label in labels if label in stats_by_label]


def _dedupe_candidates(candidates: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for item in candidates:
        cid = str(item.get("candidate_id") or "")
        if not cid or cid in seen:
            continue
        seen.add(cid)
        out.append(item)
    out.sort(
        key=lambda item: (
            str(item.get("reason_code") or ""),
            str((item.get("subject") or {}).get("kind") or ""),
            str((item.get("subject") or {}).get("id") or ""),
        )
    )
    return out


def build_time_maintenance_plan(
    *,
    registry_dir: Path | str,
    cwd: Path | str | None = None,
    project: str | None = None,
    all_projects: bool = False,
    now: str | datetime | None = None,
    stale_frontier_days: int = DEFAULT_STALE_FRONTIER_DAYS,
    dormant_after_days: int = DEFAULT_DORMANT_AFTER_DAYS,
    stale_association_days: int = DEFAULT_STALE_ASSOCIATION_DAYS,
    dry_run: bool = True,
) -> dict[str, Any]:
    root = Path(registry_dir).resolve()
    now_dt = normalize_now(now)
    generated_at = iso_utc(now_dt)
    registry = scheduler.load_json(scheduler.registry_path(root))
    projects = _selected_projects(
        registry,
        cwd=Path(cwd).resolve() if cwd else None,
        project=project,
        all_projects=all_projects,
    )
    candidates: list[dict[str, Any]] = []
    for stats in projects:
        candidates.extend(
            _scheduled_revisit_candidates(root, stats, now_dt=now_dt, generated_at=generated_at)
        )
        candidates.extend(
            _journey_candidates(
                root,
                stats,
                now_dt=now_dt,
                generated_at=generated_at,
                stale_frontier_days=stale_frontier_days,
            )
        )
        candidates.extend(
            _frontier_marker_candidates(
                root,
                stats,
                now_dt=now_dt,
                generated_at=generated_at,
                stale_frontier_days=stale_frontier_days,
            )
        )
        candidates.extend(
            _question_candidates(
                root,
                stats,
                now_dt=now_dt,
                generated_at=generated_at,
                dormant_after_days=dormant_after_days,
            )
        )
        candidates.extend(
            _association_candidates(
                root,
                stats,
                now_dt=now_dt,
                generated_at=generated_at,
                stale_association_days=stale_association_days,
            )
        )
        candidates.extend(_health_candidates(registry, stats, generated_at=generated_at))
    candidates = _dedupe_candidates(candidates)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": PLAN_KIND,
        "mode": "dry_run" if dry_run else "write",
        "dry_run": bool(dry_run),
        "generated_at": generated_at,
        "project_count": len(projects),
        "candidate_count": len(candidates),
        "reason_codes": sorted({str(item.get("reason_code") or "") for item in candidates}),
        "candidates": candidates,
        "privacy_boundary": {
            "registry_metadata_first": True,
            "raw_prompt_text_included": False,
            "local_paths_included": False,
            "provider_backed_work_optional": True,
        },
    }
