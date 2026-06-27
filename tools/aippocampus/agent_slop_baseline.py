"""Baseline lifecycle helpers for agent slop guard."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class BaselineEntry:
    fingerprint: str
    owner_issue: str
    reason: str = ""
    accepted_source: str = ""
    accepted_date: str = ""
    review_after: str = ""
    review_condition: str = ""
    expires_on: str = ""
    owner_issue_state: str = ""
    last_seen: str = ""


def load_baseline(path: Path | None) -> dict[str, str]:
    return {
        fingerprint: entry.owner_issue
        for fingerprint, entry in load_baseline_entries(path).items()
    }


def _baseline_entry_from_row(row: Mapping[str, Any]) -> BaselineEntry | None:
    raw_fingerprint = row.get("fingerprint")
    fingerprint = "" if raw_fingerprint is None else str(raw_fingerprint)
    if not fingerprint.strip():
        return None
    lifecycle = row.get("lifecycle") if isinstance(row.get("lifecycle"), Mapping) else {}
    return BaselineEntry(
        fingerprint=fingerprint,
        owner_issue=str(row.get("owner_issue") or row.get("owner") or "historical_baseline"),
        reason=str(row.get("reason") or ""),
        accepted_source=str(row.get("accepted_source") or lifecycle.get("accepted_source") or ""),
        accepted_date=str(row.get("accepted_date") or lifecycle.get("accepted_date") or ""),
        review_after=str(row.get("review_after") or lifecycle.get("review_after") or ""),
        review_condition=str(row.get("review_condition") or lifecycle.get("review_condition") or ""),
        expires_on=str(row.get("expires_on") or lifecycle.get("expires_on") or ""),
        owner_issue_state=str(row.get("owner_issue_state") or lifecycle.get("owner_issue_state") or ""),
        last_seen=str(row.get("last_seen") or lifecycle.get("last_seen") or ""),
    )


def load_baseline_entries(path: Path | None) -> dict[str, BaselineEntry]:
    if path is None or not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        rows = data
    elif isinstance(data, dict):
        rows = data.get("findings") or data.get("baseline") or []
    else:
        rows = []
    baseline: dict[str, BaselineEntry] = {}
    for row in rows:
        if isinstance(row, Mapping) and (entry := _baseline_entry_from_row(row)):
            baseline[entry.fingerprint] = entry
    return baseline


def _parse_iso_date(value: str) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _has_lifecycle_metadata(entry: BaselineEntry) -> bool:
    return bool(entry.accepted_source and entry.review_condition)


def baseline_lifecycle_summary(
    entries: Mapping[str, BaselineEntry],
    *,
    current_fingerprints: set[str],
    last_seen_scope: str = "scanned_paths_only",
    today: date | None = None,
) -> dict[str, Any]:
    current_day = today or date.today()
    values = list(entries.values())
    missing = [entry for entry in values if not _has_lifecycle_metadata(entry)]
    review_due = [
        entry
        for entry in values
        if (parsed := _parse_iso_date(entry.review_after)) is not None and parsed <= current_day
    ]
    expired = [
        entry
        for entry in values
        if (parsed := _parse_iso_date(entry.expires_on or entry.review_after)) is not None
        and parsed <= current_day
    ]
    closed_owner = [
        entry
        for entry in values
        if entry.owner_issue_state.casefold() in {"closed", "done", "resolved"}
    ]
    seen = [entry for entry in values if entry.fingerprint in current_fingerprints]
    stale = [entry for entry in values if entry.fingerprint not in current_fingerprints]
    return {
        "schema_version": 2,
        "last_seen_scope": last_seen_scope,
        "total_entry_count": len(values),
        "missing_lifecycle_metadata_count": len(missing),
        "expired_entry_count": len(expired),
        "review_due_entry_count": len(review_due),
        "closed_owner_entry_count": len(closed_owner),
        "last_seen_entry_count": len(seen),
        "stale_entry_count": len(stale),
        "missing_lifecycle_by_rule": _count_entries_by_rule(missing),
        "expired_by_rule": _count_entries_by_rule(expired),
        "review_due_by_rule": _count_entries_by_rule(review_due),
        "closed_owner_by_rule": _count_entries_by_rule(closed_owner),
        "stale_by_rule": _count_entries_by_rule(stale),
        "policy": (
            "Baseline rows without accepted_source and review_condition are legacy debt; "
            "review_due/expired/closed-owner counts are advisory until a rule-specific issue "
            "promotes them to a hard gate."
        ),
    }


def _count_entries_by_rule(entries: Sequence[BaselineEntry]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for entry in entries:
        rule_id = entry.fingerprint.split(":", 1)[0]
        counts[rule_id] = counts.get(rule_id, 0) + 1
    return dict(sorted(counts.items()))
