#!/usr/bin/env python3
"""Privacy-safe conflict diagnostics for critical-operation fact rows."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

SUPPLEMENTAL_SUPERSESSION_FIELDS = (
    "supersedes",
    "superseded_by",
    "successor_event_id",
    "replacement_event_id",
)

ABSOLUTE_PATH_RE = re.compile(
    r"(?i)(?:[a-z]:[\\/]|\\\\|/(?:users|home|var|tmp|mnt|volumes)/)"
)
SECRET_SHAPED_RE = re.compile(
    r"(?i)(secret|token|api[_-]?key|password|passwd|authorization|bearer\s+[a-z0-9._-]+)"
)
SAFE_TOKEN_RE = re.compile(r"^[A-Za-z0-9_.:/#@+-]+$")
HEX_64_RE = re.compile(r"^[a-fA-F0-9]{64}$")
PLACEHOLDER_VALUES = {
    "unknown",
    "none",
    "null",
    "missing",
    "n/a",
    "na",
    "undefined",
    "todo",
    "placeholder",
}
SUCCESS_STATUSES = {
    "ok",
    "pass",
    "passed",
    "success",
    "succeeded",
    "complete",
    "completed",
}
FAILURE_STATUSES = {
    "blocked",
    "error",
    "errored",
    "fail",
    "failed",
    "failure",
}
ACTIVE_STATUSES = {"active", "current", "enforced"}
SUPERSEDED_STATUSES = {
    "canceled",
    "cancelled",
    "expired",
    "inactive",
    "replaced",
    "retired",
    "superseded",
}


def _looks_private(value: object) -> bool:
    text = str(value or "")
    return bool(ABSOLUTE_PATH_RE.search(text) or SECRET_SHAPED_RE.search(text))


def _is_placeholder(value: object) -> bool:
    text = str(value or "").strip().casefold()
    if not text:
        return True
    return text in PLACEHOLDER_VALUES or text.startswith(("unknown_", "missing_", "placeholder_"))


def _safe_scalar(value: object) -> str | int | bool | None:
    if value is None or isinstance(value, (int, bool)):
        return value
    text = str(value)
    if not text or _looks_private(text):
        return None
    if SAFE_TOKEN_RE.match(text):
        return text
    return None


def _safe_sha256(value: object) -> str | None:
    text = str(value or "")
    return text if HEX_64_RE.match(text) and not _looks_private(text) else None


def _safe_scalar_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    items: list[str] = []
    for item in value:
        safe = _safe_scalar(item)
        if isinstance(safe, str):
            items.append(safe)
    return items


def _int_or_none(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if not isinstance(value, str):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _unique_sorted_strings(values: list[object]) -> list[str]:
    return sorted(str(value) for value in values if value not in (None, "", []))


def _safe_fact_token(fact: dict[str, Any], key: str) -> str | None:
    value = fact.get(key)
    if not isinstance(value, str) or _looks_private(value) or _is_placeholder(value):
        return None
    return value if SAFE_TOKEN_RE.match(value) else None


def _safe_event_ids(facts: list[dict[str, Any]]) -> list[str]:
    event_ids = [_safe_fact_token(fact, "event_id") for fact in facts]
    return sorted({event_id for event_id in event_ids if event_id})


def _status_class(value: object) -> str | None:
    status = str(value or "").strip().casefold()
    if status in SUCCESS_STATUSES:
        return "success"
    if status in FAILURE_STATUSES:
        return "failure"
    if status in ACTIVE_STATUSES:
        return "active"
    if status in SUPERSEDED_STATUSES:
        return "superseded"
    return None


def _status_classes_conflict(status_classes: set[str]) -> bool:
    return (
        {"success", "failure"}.issubset(status_classes)
        or {"active", "superseded"}.issubset(status_classes)
    )


def _status_conflicts_for_key(
    facts: list[dict[str, Any]],
    *,
    family: str,
    key: str,
    code: str,
) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for fact in facts:
        value = _safe_fact_token(fact, key)
        if value:
            groups.setdefault(value, []).append(fact)

    conflicts: list[dict[str, Any]] = []
    for value, group in sorted(groups.items()):
        status_classes = {
            status_class
            for status_class in (_status_class(fact.get("status")) for fact in group)
            if status_class
        }
        if not _status_classes_conflict(status_classes):
            continue
        conflict: dict[str, Any] = {
            "code": code,
            "family": family,
            "field": key,
            "status_classes": sorted(status_classes),
            "statuses": _unique_sorted_strings([fact.get("status") for fact in group]),
            "event_ids": _safe_event_ids(group),
        }
        if key == "event_id":
            conflict["event_id"] = value
        elif key == "call_ref":
            conflict["call_ref"] = value
        conflicts.append(conflict)
    return conflicts


def _fact_has_supersession_marker(fact: dict[str, Any]) -> bool:
    if _status_class(fact.get("status")) == "superseded":
        return True
    return any(_safe_fact_token(fact, key) for key in SUPPLEMENTAL_SUPERSESSION_FIELDS)


def _safe_failure_family(value: object) -> str | None:
    safe = _safe_scalar(value)
    if not isinstance(safe, str) or _looks_private(safe) or not SAFE_TOKEN_RE.match(safe):
        return None
    return safe if safe == "none" or not _is_placeholder(safe) else None


def _compact_test_identity(fact: dict[str, Any]) -> tuple[object, ...] | None:
    command_family = _safe_fact_token(fact, "command_family")
    target_class = _safe_fact_token(fact, "target_class")
    if not command_family or not target_class:
        return None

    input_sha256 = _safe_sha256(fact.get("input_sha256"))
    path_fingerprints = tuple(sorted(_safe_scalar_list(fact.get("path_fingerprints"))))
    path_categories = tuple(sorted(_safe_scalar_list(fact.get("path_categories"))))
    if not input_sha256 and not path_fingerprints and not path_categories:
        return None
    return (command_family, target_class, input_sha256 or "", path_fingerprints, path_categories)


def _test_result_conflicts(facts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[object, ...], list[dict[str, Any]]] = {}
    for fact in facts:
        if _fact_has_supersession_marker(fact):
            continue
        identity = _compact_test_identity(fact)
        if identity:
            groups.setdefault(identity, []).append(fact)

    conflicts: list[dict[str, Any]] = []
    for identity, group in sorted(groups.items(), key=lambda item: str(item[0])):
        exit_statuses = sorted(
            {status for status in (_int_or_none(fact.get("exit_status")) for fact in group) if status is not None}
        )
        failure_families = sorted(
            {
                failure
                for failure in (_safe_failure_family(fact.get("failure_family")) for fact in group)
                if failure
            }
        )
        if len(exit_statuses) <= 1 and len(failure_families) <= 1:
            continue
        command_family, target_class = identity[0], identity[1]
        conflict: dict[str, Any] = {
            "code": "conflicting_test_result",
            "family": "test_check_command_result",
            "command_family": command_family,
            "target_class": target_class,
            "fields": [],
            "event_ids": _safe_event_ids(group),
        }
        if len(exit_statuses) > 1:
            conflict["fields"].append("exit_status")
            conflict["exit_statuses"] = exit_statuses
        if len(failure_families) > 1:
            conflict["fields"].append("failure_family")
            conflict["failure_families"] = failure_families
        conflicts.append(conflict)
    return conflicts


def _constraint_conflicts(facts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for fact in facts:
        constraint_kind = _safe_fact_token(fact, "constraint_kind")
        scope = _safe_fact_token(fact, "scope")
        if constraint_kind and scope:
            groups.setdefault((constraint_kind, scope), []).append(fact)

    conflicts: list[dict[str, Any]] = []
    for (constraint_kind, scope), group in sorted(groups.items()):
        status_classes = {
            status_class
            for status_class in (_status_class(fact.get("status")) for fact in group)
            if status_class
        }
        explicit_marker_present = any(
            any(_safe_fact_token(fact, key) for key in SUPPLEMENTAL_SUPERSESSION_FIELDS)
            for fact in group
        )
        if {"active", "superseded"}.issubset(status_classes) and not explicit_marker_present:
            conflicts.append(
                {
                    "code": "conflicting_constraint_status",
                    "family": "explicit_user_constraint",
                    "constraint_kind": constraint_kind,
                    "scope": scope,
                    "fields": ["status"],
                    "status_classes": sorted(status_classes),
                    "event_ids": _safe_event_ids(group),
                }
            )
    return conflicts


def _parse_iso_timestamp(value: object) -> datetime | None:
    safe = _safe_scalar(value)
    if not isinstance(safe, str):
        return None
    text = safe.strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _manifest_time_range(manifest: dict[str, Any]) -> tuple[datetime, datetime] | None:
    for key in ("event_time_range", "session_time_range", "source_session_range"):
        item = manifest.get(key)
        if not isinstance(item, dict):
            continue
        raw_start = item.get("min_timestamp") or item.get("start_timestamp") or item.get("started_at")
        raw_end = item.get("max_timestamp") or item.get("end_timestamp") or item.get("ended_at")
        start = _parse_iso_timestamp(raw_start)
        end = _parse_iso_timestamp(raw_end)
        if start and end and start <= end:
            return start, end
    return None


def _timestamp_conflicts(
    facts: list[dict[str, Any]],
    *,
    family: str,
    manifest: dict[str, Any],
) -> list[dict[str, Any]]:
    time_range = _manifest_time_range(manifest)
    conflicts: list[dict[str, Any]] = []
    for fact in facts:
        if "timestamp" not in fact:
            continue
        event_id = _safe_fact_token(fact, "event_id") or "unknown"
        parsed = _parse_iso_timestamp(fact.get("timestamp"))
        if parsed is None:
            conflicts.append(
                {
                    "code": "malformed_event_timestamp",
                    "family": family,
                    "event_id": event_id,
                    "field": "timestamp",
                }
            )
            continue
        if time_range is None:
            continue
        start, end = time_range
        if parsed < start or parsed > end:
            conflicts.append(
                {
                    "code": "timestamp_outside_session_range",
                    "family": family,
                    "event_id": event_id,
                    "field": "timestamp",
                    "range_source": "manifest",
                }
            )
    return conflicts


def detect_conflicts(
    family: str,
    facts: list[dict[str, Any]],
    manifest: dict[str, Any],
) -> list[dict[str, Any]]:
    """Return compact contradictions over projected fact rows.

    This detector consumes sanitized integrity facts only. It makes
    contradictions visible for later source/raw audit review, but it must not
    serialize raw commands, outputs, local paths, or resolve truth by voting.
    """

    conflicts: list[dict[str, Any]] = []
    conflicts.extend(
        _status_conflicts_for_key(
            facts,
            family=family,
            key="event_id",
            code="conflicting_event_status",
        )
    )
    conflicts.extend(
        _status_conflicts_for_key(
            facts,
            family=family,
            key="call_ref",
            code="conflicting_call_status",
        )
    )
    if family == "test_check_command_result":
        conflicts.extend(_test_result_conflicts(facts))
    if family == "explicit_user_constraint":
        conflicts.extend(_constraint_conflicts(facts))
    conflicts.extend(_timestamp_conflicts(facts, family=family, manifest=manifest))
    return conflicts


def conflict_gap_events(conflicts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for conflict in conflicts:
        item = {
            "code": conflict.get("code"),
            "event_id": conflict.get("event_id"),
            "call_ref": conflict.get("call_ref"),
            "event_ids": conflict.get("event_ids"),
        }
        events.append({key: value for key, value in item.items() if value not in (None, "", [])})
    return events
