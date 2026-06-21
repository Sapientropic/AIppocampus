#!/usr/bin/env python3
"""Deterministic health stats for source-backed question tracking rows.

Question lifecycle state is a heuristic reporting layer, not a memory fact.
Only rows whose source refs still resolve are counted as facts; stale rows stay
diagnostic so a maintenance pass can repair or discard them without turning a
broken ref into a user-facing claim.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from aippocampus_runtime.core import compact_text
from aippocampus_runtime.question.constants import DEFAULT_DORMANT_AFTER_DAYS
from aippocampus_runtime.question.source_refs import (
    SourceRefIndex,
    build_source_ref_index,
    compact_source_refs,
    source_ref_key,
)
from aippocampus_runtime.question.tracking import (
    FINDING_ROW_KIND,
    FRONTIER_MARKER_KIND,
    QUESTION_CANDIDATE_KIND,
    QUESTION_LINK_KIND,
    candidate_from_row,
    frontier_from_row,
    iter_jsonl,
)
from aippocampus_runtime.question.tracking_types import (
    parse_timestamp,
    stable_digest,
)
from aippocampus_runtime.registry.api import unique_preserve

THEME_CANDIDATE_KIND = "theme_candidate"
QUESTION_RESOLUTION_KIND = "question_resolution_signal"
RESOLVED_STATES = {"resolved", "closed", "answered"}


def _now_utc() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _refs(values: Any, source_index: SourceRefIndex | None) -> tuple[dict[str, Any], ...]:
    return compact_source_refs(values, source_index=source_index)


def _date_bounds(refs: Iterable[Mapping[str, Any]]) -> tuple[str, str]:
    timestamps = [
        parsed
        for parsed in (parse_timestamp(str(ref.get("timestamp") or "")) for ref in refs)
        if parsed
    ]
    if not timestamps:
        return "", ""
    return (
        min(timestamps).isoformat().replace("+00:00", "Z"),
        max(timestamps).isoformat().replace("+00:00", "Z"),
    )


def _days_since(value: str, now: datetime) -> int | None:
    parsed = parse_timestamp(value)
    if not parsed:
        return None
    return max(0, (now - parsed).days)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _resolution_signals(row: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    raw = row.get("resolution_signal") or row.get("resolution")
    signals: list[Mapping[str, Any]] = []
    if isinstance(raw, Mapping):
        signals.append(raw)
    elif isinstance(raw, list):
        signals.extend(item for item in raw if isinstance(item, Mapping))
    state = str(
        row.get("lifecycle_state")
        or row.get("question_state")
        or row.get("resolution_status")
        or ""
    ).strip().casefold()
    if state in RESOLVED_STATES:
        signals.append(
            {
                "kind": "explicit_state",
                "resolved_at": row.get("resolved_at") or row.get("created_at"),
                "source_refs": row.get("resolution_source_refs"),
            }
        )
    return signals


def _ref_key_set(refs: Iterable[Mapping[str, Any]]) -> set[tuple[str, str, str, str]]:
    return {source_ref_key(ref) for ref in refs}


def _resolution_refs_are_independent(
    refs: Iterable[Mapping[str, Any]],
    subject_refs: Iterable[Mapping[str, Any]],
) -> bool:
    resolution_keys = _ref_key_set(refs)
    subject_keys = _ref_key_set(subject_refs)
    return bool(resolution_keys and not resolution_keys.issubset(subject_keys))


def _resolution_is_after_last_seen(
    refs: Iterable[Mapping[str, Any]],
    *,
    resolved_at: str,
    last_seen: str,
) -> bool:
    last_seen_at = parse_timestamp(last_seen)
    if not last_seen_at:
        return True
    resolved = parse_timestamp(resolved_at)
    if not resolved:
        _first, ref_last = _date_bounds(refs)
        resolved = parse_timestamp(ref_last)
    return bool(resolved and resolved > last_seen_at)


def _resolution_signal(
    row: Mapping[str, Any],
    source_index: SourceRefIndex | None,
    *,
    subject_refs: Iterable[Mapping[str, Any]] = (),
    last_seen: str = "",
) -> dict[str, Any] | None:
    for signal in _resolution_signals(row):
        refs = _refs(signal.get("source_refs") or row.get("resolution_source_refs"), source_index)
        if not refs:
            continue
        resolved_at = compact_text(
            str(signal.get("resolved_at") or row.get("resolved_at") or row.get("created_at") or ""),
            80,
        )
        if subject_refs and not _resolution_refs_are_independent(refs, subject_refs):
            continue
        if not _resolution_is_after_last_seen(refs, resolved_at=resolved_at, last_seen=last_seen):
            continue
        return {
            "kind": compact_text(str(signal.get("kind") or signal.get("type") or "resolved"), 80),
            "resolved_at": resolved_at,
            "source_ref_count": len(refs),
        }
    return None


def _string_list(values: Any, *, limit: int = 32) -> tuple[str, ...]:
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, list):
        return ()
    return tuple(unique_preserve([str(value) for value in values if str(value)], limit=limit))


def _external_resolution_signal(
    row: Mapping[str, Any], source_index: SourceRefIndex | None
) -> dict[str, Any] | None:
    refs = _refs(row.get("resolution_source_refs") or row.get("source_refs"), source_index)
    if not refs:
        return None
    return {
        "kind": compact_text(str(row.get("resolution_kind") or "explicit_user_resolution"), 80),
        "resolved_at": compact_text(str(row.get("resolved_at") or row.get("created_at") or ""), 80),
        "source_ref_count": len(refs),
        "source_ref_keys": tuple(sorted(_ref_key_set(refs))),
        "resolved_subject_id": compact_text(str(row.get("resolved_subject_id") or ""), 80),
        "resolved_question_ids": _string_list(row.get("resolved_question_ids")),
        "resolved_source_finding_ids": _string_list(row.get("resolved_source_finding_ids")),
    }


def _link_subject(
    row: Mapping[str, Any], source_index: SourceRefIndex | None
) -> dict[str, Any] | None:
    refs = _refs(row.get("source_refs"), source_index)
    if not refs:
        return None
    linked = [item for item in row.get("linked_questions") or [] if isinstance(item, Mapping)]
    source_finding_ids = unique_preserve(
        [str(value) for value in row.get("question_source_finding_ids") or [] if str(value)]
        + [
            str(item.get("source_finding_id") or "")
            for item in linked
            if item.get("source_finding_id")
        ],
        limit=32,
    )
    question_ids = unique_preserve(
        [str(item.get("question_id") or "") for item in linked if item.get("question_id")],
        limit=32,
    )
    first_seen, last_seen = (
        compact_text(str(row.get("first_seen") or ""), 80),
        compact_text(str(row.get("last_seen") or ""), 80),
    )
    if not first_seen or not last_seen:
        ref_first, ref_last = _date_bounds(refs)
        first_seen = first_seen or ref_first
        last_seen = last_seen or ref_last
    return {
        "unit_id": compact_text(
            str(row.get("question_cluster_id") or row.get("fingerprint") or "")
            or stable_digest("|".join(question_ids + source_finding_ids), prefix="qh"),
            80,
        ),
        "unit_type": "question_link",
        "title": compact_text(
            str(row.get("linked_question_short") or row.get("title") or "question link"), 140
        ),
        "link_type": compact_text(str(row.get("link_type") or "related"), 40),
        "question_ids": question_ids,
        "source_finding_ids": source_finding_ids,
        "question_count": max(1, _safe_int(row.get("question_count"), len(linked) or 1)),
        "source_refs": list(refs),
        "source_thread_count": len({ref.get("thread_key") for ref in refs if ref.get("thread_key")}),
        "phase_contexts": [
            compact_text(str(item.get("phase_context") or ""), 80)
            for item in linked[:16]
            if item.get("phase_context")
        ],
        "first_seen": first_seen,
        "last_seen": last_seen,
        "resolution_signal": _resolution_signal(
            row,
            source_index,
            subject_refs=refs,
            last_seen=last_seen,
        ),
    }


def _candidate_subject(
    row: Mapping[str, Any], source_index: SourceRefIndex | None
) -> dict[str, Any] | None:
    candidate = candidate_from_row(row, source_index=source_index)
    if not candidate:
        return None
    return {
        "unit_id": candidate.question_id,
        "unit_type": "question_candidate",
        "title": candidate.question_short or candidate.title,
        "link_type": "",
        "question_ids": [candidate.question_id],
        "source_finding_ids": [candidate.finding_id],
        "question_count": 1,
        "source_refs": list(candidate.source_refs),
        "source_thread_count": len(
            {ref.get("thread_key") for ref in candidate.source_refs if ref.get("thread_key")}
        ),
        "phase_contexts": [candidate.phase_context] if candidate.phase_context else [],
        "first_seen": candidate.first_seen,
        "last_seen": candidate.first_seen,
        "resolution_signal": _resolution_signal(
            row,
            source_index,
            subject_refs=candidate.source_refs,
            last_seen=candidate.first_seen,
        ),
    }


def _lifecycle_for(
    subject: Mapping[str, Any], *, now: datetime, dormant_after_days: int
) -> dict[str, Any]:
    resolution = subject.get("resolution_signal") if isinstance(subject.get("resolution_signal"), dict) else None
    last_seen = str(subject.get("last_seen") or "")
    days_since = _days_since(last_seen, now)
    if resolution:
        state = "resolved"
        reason = "source-backed resolution signal"
    elif days_since is not None and days_since >= dormant_after_days:
        state = "dormant"
        reason = f"no source-backed reappearance for {days_since} days"
    else:
        state = "open"
        reason = "recent or age unknown; no resolution signal"
    return {
        "unit_id": subject.get("unit_id"),
        "unit_type": subject.get("unit_type"),
        "title": subject.get("title"),
        "state": state,
        "reason": reason,
        "first_seen": subject.get("first_seen"),
        "last_seen": last_seen,
        "days_since_last_seen": days_since,
        "source_ref_count": len(subject.get("source_refs") or []),
        "source_thread_count": subject.get("source_thread_count") or 0,
        "resolution_signal": resolution,
    }


def _signal_matches_subject(signal: Mapping[str, Any], subject: Mapping[str, Any]) -> bool:
    subject_id = str(subject.get("unit_id") or "")
    if subject_id and subject_id == str(signal.get("resolved_subject_id") or ""):
        return True
    signal_question_ids = set(signal.get("resolved_question_ids") or [])
    subject_question_ids = {str(value) for value in subject.get("question_ids") or [] if str(value)}
    if signal_question_ids and signal_question_ids.intersection(subject_question_ids):
        return True
    signal_source_ids = set(signal.get("resolved_source_finding_ids") or [])
    subject_source_ids = {
        str(value) for value in subject.get("source_finding_ids") or [] if str(value)
    }
    return bool(signal_source_ids and signal_source_ids.intersection(subject_source_ids))


def _apply_external_resolution_signals(
    subjects: Iterable[dict[str, Any]], signals: Iterable[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    signal_list = list(signals)
    out: list[dict[str, Any]] = []
    for subject in subjects:
        if isinstance(subject.get("resolution_signal"), dict):
            out.append(subject)
            continue
        matched = next(
            (signal for signal in signal_list if _signal_matches_subject(signal, subject)),
            None,
        )
        if matched:
            signal_ref_keys = set(matched.get("source_ref_keys") or [])
            subject_ref_keys = _ref_key_set(subject.get("source_refs") or [])
            if signal_ref_keys and signal_ref_keys.issubset(subject_ref_keys):
                out.append(subject)
                continue
            if not _resolution_is_after_last_seen(
                [],
                resolved_at=str(matched.get("resolved_at") or ""),
                last_seen=str(subject.get("last_seen") or ""),
            ):
                out.append(subject)
                continue
            subject = dict(subject)
            subject["resolution_signal"] = {
                "kind": matched.get("kind"),
                "resolved_at": matched.get("resolved_at"),
                "source_ref_count": matched.get("source_ref_count"),
            }
        out.append(subject)
    return out


def build_question_health_stats(
    rows: Iterable[Mapping[str, Any]],
    *,
    source_index: SourceRefIndex | None = None,
    now: datetime | None = None,
    dormant_after_days: int = DEFAULT_DORMANT_AFTER_DAYS,
) -> dict[str, Any]:
    now = now or _now_utc()
    rows_list = list(rows)
    stale_or_unresolved_ref_rows = 0
    source_backed_rows = 0
    linked_source_ids: set[str] = set()
    link_subjects: list[dict[str, Any]] = []
    candidate_subjects: dict[str, dict[str, Any]] = {}
    external_resolution_signals: list[dict[str, Any]] = []
    valid_external_resolution_signal_count = 0
    recurring_link_count = 0
    frontier_counts: Counter[str] = Counter()
    active_theme_count = 0

    for row in rows_list:
        if row.get("kind") != FINDING_ROW_KIND:
            continue
        finding_kind = str(row.get("finding_kind") or "")
        if finding_kind == QUESTION_RESOLUTION_KIND:
            signal = _external_resolution_signal(row, source_index)
            if not signal:
                stale_or_unresolved_ref_rows += 1
                continue
            source_backed_rows += 1
            valid_external_resolution_signal_count += 1
            external_resolution_signals.append(signal)
            continue
        if finding_kind == QUESTION_LINK_KIND:
            subject = _link_subject(row, source_index)
            if not subject:
                stale_or_unresolved_ref_rows += 1
                continue
            source_backed_rows += 1
            link_subjects.append(subject)
            linked_source_ids.update(subject["source_finding_ids"])
            if subject["link_type"] == "recurring":
                recurring_link_count += 1
            continue
        if finding_kind == QUESTION_CANDIDATE_KIND:
            subject = _candidate_subject(row, source_index)
            if not subject:
                stale_or_unresolved_ref_rows += 1
                continue
            source_backed_rows += 1
            candidate_subjects[subject["source_finding_ids"][0]] = subject
            continue
        if finding_kind == FRONTIER_MARKER_KIND:
            frontier = frontier_from_row(row, source_index=source_index)
            if not frontier:
                stale_or_unresolved_ref_rows += 1
                continue
            source_backed_rows += 1
            frontier_counts[frontier.frontier_type or "unresolved"] += 1
            continue
        if finding_kind == THEME_CANDIDATE_KIND:
            if _refs(row.get("source_refs"), source_index):
                source_backed_rows += 1
                active_theme_count += 1
            else:
                stale_or_unresolved_ref_rows += 1

    standalone = [
        subject
        for source_id, subject in candidate_subjects.items()
        if source_id not in linked_source_ids
    ]
    subjects = _apply_external_resolution_signals(
        link_subjects + standalone,
        external_resolution_signals,
    )
    if not source_backed_rows or not subjects:
        return {
            "available": False,
            "reason": "no_source_backed_question_rows",
            "source_ref_resolution": "registry_clean_source" if source_index else "shape_only_uncertain",
            "stale_or_unresolved_ref_row_count": stale_or_unresolved_ref_rows,
        }

    lifecycle = [
        _lifecycle_for(subject, now=now, dormant_after_days=dormant_after_days)
        for subject in subjects
    ]
    resolution_signal_count = sum(
        1 for item in lifecycle if isinstance(item.get("resolution_signal"), dict)
    )
    state_counts = Counter(item["state"] for item in lifecycle)
    phase_counts: Counter[str] = Counter()
    for subject in subjects:
        phase_counts.update(str(value) for value in subject.get("phase_contexts") or [] if value)
    open_items = [item for item in lifecycle if item["state"] == "open"]
    longest_open = None
    if open_items:
        longest_open = max(
            open_items,
            key=lambda item: (
                _days_since(str(item.get("first_seen") or ""), now) or -1,
                str(item.get("unit_id") or ""),
            ),
        )
    question_ids = {
        question_id
        for subject in subjects
        for question_id in subject.get("question_ids") or []
        if question_id
    }
    return {
        "available": True,
        "source_ref_resolution": "registry_clean_source" if source_index else "shape_only_uncertain",
        "source_backed_row_count": source_backed_rows,
        "stale_or_unresolved_ref_row_count": stale_or_unresolved_ref_rows,
        "resolution_signal_count": resolution_signal_count,
        "external_resolution_signal_count": valid_external_resolution_signal_count,
        "tracked_question_count": len(question_ids) or sum(
            int(subject.get("question_count") or 1) for subject in subjects
        ),
        "question_group_count": len(subjects),
        "recurring_link_count": recurring_link_count,
        "dormant_question_count": state_counts.get("dormant", 0),
        "resolved_question_count": state_counts.get("resolved", 0),
        "open_question_count": state_counts.get("open", 0),
        "active_theme_count": active_theme_count,
        "frontier_marker_counts": dict(sorted(frontier_counts.items())),
        "phase_context_counts": dict(sorted(phase_counts.items())),
        "longest_running_open_question": longest_open,
        "lifecycle": lifecycle[:24],
        "heuristic_contract": {
            "dormant_after_days": int(dormant_after_days),
            "states": ["open", "dormant", "resolved"],
            "no_stalled_state": True,
            "truth_boundary": "question lifecycle stats are source-backed heuristics, not durable memory facts",
        },
    }


def question_health_stats(
    jobs_path: Path | str,
    *,
    registry_path: Path | str | None = None,
    now: datetime | None = None,
    dormant_after_days: int = DEFAULT_DORMANT_AFTER_DAYS,
) -> dict[str, Any]:
    path = Path(jobs_path)
    if not path.exists():
        return {"available": False, "reason": "jobs_missing", "jobs": str(path)}
    source_index = build_source_ref_index(Path(registry_path)) if registry_path else None
    payload = build_question_health_stats(
        iter_jsonl(path),
        source_index=source_index,
        now=now,
        dormant_after_days=dormant_after_days,
    )
    payload["jobs"] = str(path)
    payload["registry"] = str(registry_path) if registry_path else None
    return payload


def aggregate_question_health_stats(payload: Mapping[str, Any]) -> dict[str, Any]:
    public_keys = {
        "available",
        "reason",
        "source_ref_resolution",
        "source_backed_row_count",
        "stale_or_unresolved_ref_row_count",
        "resolution_signal_count",
        "external_resolution_signal_count",
        "tracked_question_count",
        "question_group_count",
        "recurring_link_count",
        "dormant_question_count",
        "resolved_question_count",
        "open_question_count",
        "active_theme_count",
        "frontier_marker_counts",
        "phase_context_counts",
        "heuristic_contract",
        "jobs",
        "registry",
    }
    return {key: payload[key] for key in public_keys if key in payload}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jobs", required=True)
    parser.add_argument("--registry")
    parser.add_argument("--dormant-after-days", type=int, default=DEFAULT_DORMANT_AFTER_DAYS)
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args(argv)
    payload = question_health_stats(
        args.jobs,
        registry_path=args.registry,
        dormant_after_days=args.dormant_after_days,
    )
    if args.json_output:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        if not payload.get("available"):
            print(f"question health: unavailable ({payload.get('reason')})")
        else:
            print(
                "question health: "
                f"{payload['question_group_count']} groups, "
                f"{payload['recurring_link_count']} recurring links, "
                f"{payload['dormant_question_count']} dormant, "
                f"{payload['resolved_question_count']} resolved"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
