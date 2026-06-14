#!/usr/bin/env python3
"""Adapter from subconscious salience rows to continuity-domain events.

This is the opt-in production bridge for deterministic, source-ref-backed
salience. Consent belongs at the feature-enable boundary: once enabled, the
adapter may append durable continuity-domain events quietly, while preserving
source refs, dedupe, auditable provenance, and source-reopen requirements.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from aippocampus_runtime.ops.route_readiness import safe_source_refs
from aippocampus_runtime.recall.continuity_domains import (
    append_continuity_domain_event,
    load_continuity_domain_events,
    normalize_continuity_domain_event,
    publish_continuity_domains_snapshot,
)

ADAPTER_KIND = "aippocampus_continuity_domain_salience_adapter_report"
REPORT_MODE = "report"
WRITE_WHEN_ENABLED_MODE = "write_when_enabled"
SUPPORTED_MODES = {REPORT_MODE, WRITE_WHEN_ENABLED_MODE}

FAMILY_PROFILES: dict[str, dict[str, Any]] = {
    "correction_source_added": {
        "domain_id": "cd_salience_corrections",
        "title": "Source-backed correction salience",
        "summary": "Deterministic salience found correction evidence; source_reopen_required_before_claim.",
        "scope_labels": ["salience_correction", "continuity_domain_adapter"],
    },
    "counter_source_added": {
        "domain_id": "cd_salience_counter_routes",
        "title": "Rejected route and counter-evidence salience",
        "summary": "Deterministic salience found a rejected route or failed assumption; source_reopen_required_before_claim.",
        "scope_labels": ["salience_counter", "continuity_domain_adapter"],
    },
    "boundary_pinned": {
        "domain_id": "cd_salience_boundaries",
        "title": "Pinned boundary salience",
        "summary": "Deterministic salience found a boundary, blocker, or scope constraint; source_reopen_required_before_claim.",
        "scope_labels": ["salience_boundary", "continuity_domain_adapter"],
        "effect": "require_source_reopen",
        "strength": "hard",
    },
    "domain_created": {
        "domain_id": "cd_salience_durable_preferences",
        "title": "Durable preference and style salience",
        "summary": "Repeated source refs support a cautious continuity-domain route; source_reopen_required_before_claim.",
        "scope_labels": ["salience_preference", "continuity_domain_adapter"],
    },
}

EVENT_KIND_TO_SOURCE_GROUP = {
    "correction_source_added": "correction_refs",
    "counter_source_added": "counter_refs",
    "boundary_pinned": "boundary_refs",
    "domain_created": "support_refs",
    "domain_superseded": "counter_refs",
}


def _stable_id(*parts: Any, prefix: str, length: int = 20) -> str:
    raw = "\0".join(json.dumps(part, sort_keys=True, default=str) for part in parts)
    digest = hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()[:length]
    return f"{prefix}_{digest}"


def _iter_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    if not path.exists():
        return
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict):
                yield row


def _reason_codes(row: Mapping[str, Any]) -> list[str]:
    raw = row.get("reason_codes") or []
    if not isinstance(raw, (list, tuple)):
        raw = [raw]
    return [str(item) for item in raw if str(item or "").strip()]


def _has_scope_boundary_cue(row: Mapping[str, Any]) -> bool:
    return any("scope_boundary" in item or "boundary" in item for item in _reason_codes(row))


def _target_domain_id(row: Mapping[str, Any]) -> str:
    for key in ("target_domain_id", "domain_id", "superseded_domain_id"):
        value = str(row.get(key) or "").strip()
        if value:
            return value
    return ""


def _continuity_event_kind(row: Mapping[str, Any], refs: list[dict[str, Any]]) -> tuple[str, str]:
    salience_kind = str(row.get("event_kind") or "")
    if salience_kind == "explicit_user_correction":
        return ("boundary_pinned", "") if _has_scope_boundary_cue(row) else ("correction_source_added", "")
    if salience_kind == "failed_command_or_test":
        return "correction_source_added", ""
    if salience_kind == "rejected_route_or_failed_assumption":
        return "counter_source_added", ""
    if salience_kind in {"unresolved_frontier_or_blocker", "scope_boundary_clarification"}:
        return "boundary_pinned", ""
    if salience_kind == "supersession_or_currentness":
        if _target_domain_id(row):
            return "domain_superseded", ""
        return "", "currentness_target_domain_unresolved"
    if salience_kind == "durable_preference_or_style":
        if len(refs) >= 2:
            return "domain_created", ""
        return "", "preference_requires_repeated_source_refs"
    if salience_kind in {"ordinary_context", "low_information_noise"}:
        return "", "not_selected"
    return "", "unsupported_salience_kind"


def _event_from_salience_row(row: Mapping[str, Any]) -> tuple[dict[str, Any] | None, str]:
    if row.get("candidate_action") not in {None, "", "select"}:
        return None, "not_selected"
    refs = safe_source_refs(row.get("source_refs"))
    if not refs:
        return None, "missing_source_refs"
    continuity_event_kind, deferred_reason = _continuity_event_kind(row, refs)
    if not continuity_event_kind:
        return None, deferred_reason

    salience_kind = str(row.get("event_kind") or "unknown")
    profile = dict(FAMILY_PROFILES.get(continuity_event_kind) or {})
    domain_id = _target_domain_id(row) or str(profile.get("domain_id") or "")
    if continuity_event_kind == "domain_superseded":
        domain_id = _target_domain_id(row)
        profile = {
            "domain_id": domain_id,
            "title": "Currentness and supersession salience",
            "summary": "Deterministic salience found currentness pressure; source_reopen_required_before_claim.",
            "scope_labels": ["salience_currentness", "continuity_domain_adapter"],
            "status": "superseded",
        }
    source_group_key = EVENT_KIND_TO_SOURCE_GROUP.get(continuity_event_kind, "support_refs")
    producer_event_id = str(row.get("event_id") or "")
    event_id = _stable_id(
        producer_event_id,
        salience_kind,
        continuity_event_kind,
        domain_id,
        refs,
        prefix="cde_sal",
    )
    event: dict[str, Any] = {
        "event_id": event_id,
        "event_kind": continuity_event_kind,
        "domain_id": domain_id,
        "source_refs": refs,
        source_group_key: refs,
        "title": profile.get("title") or continuity_event_kind,
        "summary": profile.get("summary") or "source_reopen_required_before_claim",
        "scope_labels": profile.get("scope_labels") or ["continuity_domain_adapter"],
        "activation_cues": [f"salience:{salience_kind}", *_reason_codes(row)[:4]],
        "producer": "subconscious_event_salience_gate",
        "producer_event_id": producer_event_id,
        "producer_event_kind": salience_kind,
        "producer_reason_codes": _reason_codes(row)[:8],
        "producer_score": row.get("salience_score"),
        "producer_authority": row.get("authority") or "navigation_intake_metadata",
        "source_reopen_policy": "required_before_claim",
        "privacy_boundary": "local_runtime_events_may_keep_navigation_handles_public_reports_stay_sanitized",
    }
    for key in ("effect", "strength", "status"):
        if profile.get(key):
            event[key] = profile[key]
    if continuity_event_kind == "boundary_pinned":
        event["boundary_kind"] = salience_kind
    if continuity_event_kind == "domain_superseded":
        event["supersedes"] = [domain_id]
    return event, ""


def salience_rows_to_continuity_domain_events(
    rows: Iterable[Mapping[str, Any]],
    *,
    clean_source_dir: Path | None = None,
) -> dict[str, Any]:
    candidate_events: list[dict[str, Any]] = []
    deferred: list[dict[str, Any]] = []
    input_count = 0
    for row in rows:
        input_count += 1
        event, reason = _event_from_salience_row(row)
        if event is None:
            deferred.append(
                {
                    "salience_event_id": str(row.get("event_id") or ""),
                    "salience_event_kind": str(row.get("event_kind") or ""),
                    "reason": reason or "not_mapped",
                }
            )
            continue
        normalized = normalize_continuity_domain_event(event, clean_source_dir=clean_source_dir)
        if normalized is None:
            deferred.append(
                {
                    "salience_event_id": str(row.get("event_id") or ""),
                    "salience_event_kind": str(row.get("event_kind") or ""),
                    "reason": "continuity_event_not_source_resolving",
                }
            )
            continue
        candidate_events.append(normalized)

    deferred_reasons = Counter(str(item.get("reason") or "unknown") for item in deferred)
    candidate_kinds = Counter(str(item.get("event_kind") or "unknown") for item in candidate_events)
    return {
        "kind": ADAPTER_KIND,
        "schema_version": 1,
        "ok": True,
        "input_row_count": input_count,
        "candidate_events": candidate_events,
        "candidate_event_kinds": dict(candidate_kinds),
        "deferred_events": deferred,
        "deferred_reason_counts": dict(deferred_reasons),
        "metrics": {
            "candidate_event_count": len(candidate_events),
            "deferred_event_count": len(deferred),
            "provider_call_count": 0,
        },
        "claim_boundary": "continuity_domain_events_are_navigation_routes_source_reopen_required_before_claim",
        "public_report_boundary": "public_reports_must_omit_raw_source_text_and_local_paths",
    }


def adapt_salience_rows_to_continuity_domains(
    rows: Iterable[Mapping[str, Any]],
    *,
    events_path: Path,
    snapshot_dir: Path,
    clean_source_dir: Path | None = None,
    mode: str = REPORT_MODE,
    enabled: bool = False,
    publish: bool = False,
) -> dict[str, Any]:
    if mode not in SUPPORTED_MODES:
        raise ValueError(f"unsupported continuity-domain salience adapter mode: {mode}")
    report = salience_rows_to_continuity_domain_events(
        rows,
        clean_source_dir=clean_source_dir,
    )
    report["mode"] = mode
    report["enabled"] = bool(enabled)
    report["events_path"] = str(events_path)
    report["snapshot_dir"] = str(snapshot_dir)
    if mode == REPORT_MODE:
        report["write_report"] = {"status": "not_requested"}
        return report
    if not enabled:
        report["write_report"] = {
            "status": "disabled_by_policy",
            "appended_event_count": 0,
            "duplicate_event_count": 0,
            "rejected_event_count": 0,
            "publish_requested": bool(publish),
        }
        return report

    existing_ids = {
        str(event.get("event_id") or "")
        for event in load_continuity_domain_events(
            Path(events_path),
            clean_source_dir=clean_source_dir,
        )
    }
    seen_ids = {item for item in existing_ids if item}
    appended: list[dict[str, Any]] = []
    duplicate_count = 0
    rejected_count = 0
    for event in report["candidate_events"]:
        event_id = str(event.get("event_id") or "")
        if event_id and event_id in seen_ids:
            duplicate_count += 1
            continue
        try:
            normalized = append_continuity_domain_event(
                Path(events_path),
                event,
                clean_source_dir=clean_source_dir,
            )
        except ValueError:
            rejected_count += 1
            continue
        appended.append(normalized)
        if event_id:
            seen_ids.add(event_id)

    write_report: dict[str, Any] = {
        "status": "completed",
        "appended_event_count": len(appended),
        "duplicate_event_count": duplicate_count,
        "rejected_event_count": rejected_count,
        "publish_requested": bool(publish),
    }
    if publish and Path(events_path).exists():
        write_report["publish_report"] = publish_continuity_domains_snapshot(
            events_path=Path(events_path),
            snapshot_dir=Path(snapshot_dir),
            clean_source_dir=clean_source_dir,
        )
    report["write_report"] = write_report
    return report


def adapt_salience_sidecar_to_continuity_domains(
    salience_path: Path,
    *,
    events_path: Path,
    snapshot_dir: Path,
    clean_source_dir: Path | None = None,
    mode: str = REPORT_MODE,
    enabled: bool = False,
    publish: bool = False,
) -> dict[str, Any]:
    return adapt_salience_rows_to_continuity_domains(
        list(_iter_jsonl(Path(salience_path))),
        events_path=events_path,
        snapshot_dir=snapshot_dir,
        clean_source_dir=clean_source_dir,
        mode=mode,
        enabled=enabled,
        publish=publish,
    )
