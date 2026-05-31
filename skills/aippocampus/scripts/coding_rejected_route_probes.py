#!/usr/bin/env python3
"""Coding rejected-route Dream probe fixture.

This adapter turns source-backed coding decision events into prospective Dream
probes for retrospective replay. It does not decide that an old rejection is
still correct; it asks what later source would justify reopening that route and
then lets the retrospective lifecycle bucket the result.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from datetime import datetime, timedelta, timezone
from typing import Any

import dream_retrospective_lifecycle
from aippocampuslib import compact_text, now_utc

PROBE_KIND = "aippocampus_dream_finding"
PROBE_FAMILY = "coding_rejected_route"
ELIGIBLE_EVENT_TYPES = {"rejected_route", "do_not_repeat", "scope_narrowing", "user_correction"}


def stable_id(*parts: object, prefix: str, length: int = 18) -> str:
    raw = "\n".join(json.dumps(part, ensure_ascii=False, sort_keys=True, default=str) for part in parts)
    return f"{prefix}_{hashlib.sha1(raw.encode('utf-8', errors='replace')).hexdigest()[:length]}"


def parse_utc(value: object) -> datetime | None:
    text = str(value or "")
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        return datetime.fromisoformat(text).astimezone(timezone.utc)
    except ValueError:
        return None


def format_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def future_utc(created_at: object, *, days: int) -> str:
    base = parse_utc(created_at) or parse_utc(now_utc()) or datetime.now(timezone.utc)
    return format_utc(base + timedelta(days=max(1, int(days))))


def source_ref_key(ref: Mapping[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(ref.get("thread_key") or ref.get("thread_id") or ""),
        str(ref.get("message_id") or ""),
        str(ref.get("turn_id") or ""),
        str(ref.get("source_id") or ref.get("source_line") or ref.get("line") or ""),
    )


def normalize_source_refs(value: object) -> list[dict[str, Any]]:
    if isinstance(value, Mapping):
        raw_items: Iterable[object] = [value]
    elif isinstance(value, Iterable) and not isinstance(value, (str, bytes)):
        raw_items = value
    else:
        raw_items = []
    refs: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for item in raw_items:
        if not isinstance(item, Mapping):
            continue
        key = source_ref_key(item)
        if not any(key) or key in seen:
            continue
        seen.add(key)
        refs.append({key: value for key, value in dict(item).items() if value not in {None, ""}})
    return refs


def rejected_route_surface(event: Mapping[str, Any]) -> str:
    for item in event.get("rejected_paths") or []:
        if isinstance(item, Mapping) and item.get("path"):
            return compact_text(str(item.get("path") or ""), 320)
    return compact_text(str(event.get("summary") or ""), 320)


def event_is_rejected_route(event: Mapping[str, Any]) -> bool:
    return str(event.get("event_type") or "") in ELIGIBLE_EVENT_TYPES and bool(event.get("rejected_paths"))


def build_rejected_route_probe(
    event: Mapping[str, Any],
    *,
    review_after_days: int = 14,
    expiry_days: int = 45,
) -> dict[str, Any]:
    if not event_is_rejected_route(event):
        raise ValueError("event is not an eligible coding rejected-route decision")
    refs = normalize_source_refs(event.get("source_refs"))
    if not refs:
        raise ValueError("coding rejected-route probe requires source refs")
    decision_id = str(event.get("decision_id") or stable_id(event, prefix="decision", length=18))
    route = rejected_route_surface(event)
    fingerprint = stable_id(decision_id, route, "coding_rejected_route_probe", prefix="dream_probe", length=20)
    created_at = str(event.get("created_at") or now_utc())
    return {
        "schema_version": 1,
        "kind": PROBE_KIND,
        "finding_kind": "dream_synthesized",
        "dream_function": "prospective",
        "candidate_kind": "rejected_route_reopening_probe",
        "probe_family": PROBE_FAMILY,
        "fingerprint": fingerprint,
        "source_decision_id": decision_id,
        "created_at": created_at,
        "review_after": future_utc(created_at, days=review_after_days),
        "expires_at": future_utc(created_at, days=expiry_days),
        "review_state": "needs_review",
        "adjudication_result": {"status": "parked", "policy": "coding_rejected_route_retrospective_probe_v1"},
        "support_level": "candidate",
        "foreground_eligible": False,
        "formal_memory_eligible": False,
        "clean_source_mutation": False,
        "human_review_required": False,
        "title": compact_text(f"Reopening probe for rejected route: {route}", 180),
        "summary": compact_text(
            f"What evidence would justify reopening this rejected route? {route}",
            520,
        ),
        "rejected_route": route,
        "counter_evidence": ["Old source only proves the route was rejected then, not that it remains rejected now."],
        "source_refs": refs,
        "bridge_claims": [
            {
                "claim": "The prospective probe is anchored to the original rejected-route source.",
                "source_refs": refs,
            }
        ],
        "source_ref_audit": {
            "status": "source_backed_coding_decision_event",
            "source_ref_count": len(refs),
            "source_thread_count": len({str(ref.get("thread_key") or ref.get("thread_id") or "") for ref in refs}),
        },
        "validation_boundary": "requires_later_explicit_source_backed_reopening_or_refutation",
        "truth_boundary": "coding_rejected_route_probe_not_current_validity_fact",
        "cannot_claim": [
            "route_is_still_rejected",
            "route_should_be_reopened",
            "predictive_validity_without_later_source",
        ],
    }


def build_rejected_route_probes(
    events: Iterable[Mapping[str, Any]],
    *,
    review_after_days: int = 14,
    expiry_days: int = 45,
) -> list[dict[str, Any]]:
    probes: list[dict[str, Any]] = []
    for event in events:
        if not isinstance(event, Mapping) or not event_is_rejected_route(event):
            continue
        try:
            probes.append(
                build_rejected_route_probe(
                    event,
                    review_after_days=review_after_days,
                    expiry_days=expiry_days,
                )
            )
        except ValueError:
            continue
    return probes


def run_rejected_route_fixture(
    events: Iterable[Mapping[str, Any]],
    later_rows: Iterable[Mapping[str, Any]],
    *,
    now: str | None = None,
    review_after_days: int = 14,
    expiry_days: int = 45,
) -> dict[str, Any]:
    generated = build_rejected_route_probes(
        events,
        review_after_days=review_after_days,
        expiry_days=expiry_days,
    )
    lifecycle = dream_retrospective_lifecycle.run_retrospective_lifecycle(
        generated,
        later_rows,
        now=now,
    )
    window_totals = {
        "ignored_before_probe": sum(int((item.get("window") or {}).get("ignored_before_probe") or 0) for item in lifecycle["items"]),
        "ignored_after_now": sum(int((item.get("window") or {}).get("ignored_after_now") or 0) for item in lifecycle["items"]),
        "term_overlap_without_target": sum(int((item.get("window") or {}).get("term_overlap_without_target") or 0) for item in lifecycle["items"]),
    }
    return {
        "schema_version": 1,
        "kind": "aippocampus_coding_rejected_route_probe_fixture",
        "created_at": now or now_utc(),
        "probes": generated,
        "lifecycle": lifecycle,
        "metrics": {
            "probe_count": len(generated),
            "status_counts": dict(lifecycle.get("counts") or {}),
            **window_totals,
        },
        "cannot_claim": [
            "predictive_validity",
            "formal_memory_promotion",
            "route_current_validity_without_separate_review",
        ],
    }


def public_fixture_summary(payload: Mapping[str, Any]) -> dict[str, Any]:
    metrics = payload.get("metrics") or {}
    return {
        "kind": "aippocampus_coding_rejected_route_probe_fixture_summary",
        "probe_count": int(metrics.get("probe_count") or 0),
        "status_counts": dict(metrics.get("status_counts") or {}),
        "ignored_before_probe": int(metrics.get("ignored_before_probe") or 0),
        "ignored_after_now": int(metrics.get("ignored_after_now") or 0),
        "term_overlap_without_target": int(metrics.get("term_overlap_without_target") or 0),
        "cannot_claim": list(payload.get("cannot_claim") or []),
    }
