#!/usr/bin/env python3
"""Build reopen navigation from host-facing sequence packets.

Sequence packets are compact host hints, not source truth. This helper only
turns packet timeline handles into a source-window route when the caller
provides a clean source-ref catalog; missing refs deliberately degrade to
ask/refresh navigation instead of producing a foreground warning.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping, Sequence

from aippocampus_runtime.coding import sequence_packets
from aippocampus_runtime.core import dict_or_empty, list_or_empty
from aippocampus_runtime.question.source_refs import clean_source_ref, source_ref_key
from aippocampus_runtime.registry.api import unique_preserve

SEQUENCE_PACKET_REOPEN_PLAN_KIND = "aippocampus_sequence_packet_reopen_plan"
SAFE_NAVIGATION_USES = ["ask", "refresh_sources"]


def _string_items(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if value is None:
        return []
    text = str(value).strip()
    return [text] if text else []


def _source_ref_hash(ref: Mapping[str, Any]) -> str:
    raw = json.dumps(source_ref_key(ref), ensure_ascii=False, sort_keys=True)
    digest = hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()[:20]
    return f"sha256:{digest}"


def _unique_refs(refs: list[dict[str, Any]], *, limit: int = 24) -> list[dict[str, Any]]:
    seen: set[tuple[str, str, str, str]] = set()
    out: list[dict[str, Any]] = []
    for ref in refs:
        key = source_ref_key(ref)
        if key in seen:
            continue
        seen.add(key)
        out.append(ref)
        if len(out) >= limit:
            break
    return out


def _clean_refs(row: Mapping[str, Any]) -> list[dict[str, Any]]:
    candidates: list[Any] = []
    candidates.extend(list_or_empty(row.get("source_refs")))
    if row.get("source_ref") is not None:
        candidates.append(row.get("source_ref"))
    if not candidates:
        candidates.append(dict(row))
    refs: list[dict[str, Any]] = []
    for candidate in candidates:
        clean = clean_source_ref(candidate)
        if clean:
            refs.append(clean)
    return _unique_refs(refs)


def _catalog_hashes(row: Mapping[str, Any], refs: Sequence[Mapping[str, Any]]) -> list[str]:
    hashes = (
        _string_items(row.get("source_ref_hash"))
        + _string_items(row.get("source_hash"))
        + _string_items(row.get("source_ref_hashes"))
    )
    hashes.extend(_source_ref_hash(ref) for ref in refs)
    return unique_preserve([item for item in hashes if item], limit=24)


def _catalog_event_ids(row: Mapping[str, Any]) -> list[str]:
    return unique_preserve(
        _string_items(row.get("event_id"))
        + _string_items(row.get("source_event_id"))
        + _string_items(row.get("decision_id"))
        + _string_items(row.get("source_event_ids")),
        limit=24,
    )


def _add_indexed_ref(index: dict[str, list[dict[str, Any]]], key: str, refs: Sequence[dict[str, Any]]) -> None:
    if not key or not refs:
        return
    index[key] = _unique_refs(index.get(key, []) + list(refs))


def _index_catalog(
    source_catalog: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, list[dict[str, Any]]]]:
    by_event_id: dict[str, list[dict[str, Any]]] = {}
    by_hash: dict[str, list[dict[str, Any]]] = {}
    for row in source_catalog:
        refs = _clean_refs(row)
        hashes = _catalog_hashes(row, refs)
        event_ids = _catalog_event_ids(row)

        # Episode/Arc rows often carry parallel event/hash/ref lists. Preserve
        # that narrow mapping so one event id does not resolve to the whole arc.
        if len(event_ids) > 1 and (len(refs) == len(event_ids) or len(hashes) >= len(event_ids)):
            for index, event_id in enumerate(event_ids):
                event_refs = [refs[index]] if index < len(refs) else []
                event_hashes = [hashes[index]] if index < len(hashes) else []
                if not event_refs and index < len(refs):
                    event_refs = [refs[index]]
                _add_indexed_ref(by_event_id, event_id, event_refs)
                for source_hash in event_hashes:
                    _add_indexed_ref(by_hash, source_hash, event_refs)
            continue

        for event_id in event_ids:
            _add_indexed_ref(by_event_id, event_id, refs)
        for source_hash in hashes:
            _add_indexed_ref(by_hash, source_hash, refs)
    return by_event_id, by_hash


def _timeline(packet: Mapping[str, Any]) -> list[dict[str, str]]:
    events: list[dict[str, str]] = []
    for event in list_or_empty(packet.get("timeline")):
        row = dict_or_empty(event)
        event_id = str(row.get("event_id") or "").strip()
        event_kind = str(row.get("event_kind") or "").strip()
        source_hash = str(row.get("source_ref_hash") or row.get("source_hash") or "").strip()
        if event_id or event_kind or source_hash:
            events.append(
                {
                    "event_id": event_id,
                    "event_kind": event_kind,
                    "source_ref_hash": source_hash,
                }
            )
    return events


def _resolution_status(*, packet_kind_valid: bool, timeline: Sequence[Mapping[str, str]], unresolved_count: int) -> str:
    if not packet_kind_valid or not timeline:
        return "invalid_packet"
    if unresolved_count == len(timeline):
        return "unresolved"
    if unresolved_count:
        return "partial"
    return "complete"


def _recommended_use(packet: Mapping[str, Any], status: str) -> str:
    if status != "complete" or packet.get("sequence_gaps"):
        return "refresh_sources"
    proposed = str(dict_or_empty(packet.get("current_assessment")).get("proposed_use") or "").strip()
    if proposed in {"ask", "refresh_sources", "remind"}:
        return proposed
    return "refresh_sources"


def build_sequence_packet_reopen_plan(
    packet: Mapping[str, Any],
    *,
    source_catalog: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Return source-window navigation from a sequence packet.

    The packet supplies ordered event handles; the catalog supplies source refs.
    If a handle cannot resolve, the plan is still useful as a refresh request
    but is not safe for visible reminders or action-time warnings.
    """

    packet_kind_valid = str(packet.get("kind") or "") == sequence_packets.SEQUENCE_PACKET_KIND
    timeline = _timeline(packet)
    by_event_id, by_hash = _index_catalog(source_catalog)

    resolved_refs: list[dict[str, Any]] = []
    resolved_event_ids: list[str] = []
    source_hashes: list[str] = []
    unresolved: list[dict[str, str]] = []
    for event in timeline:
        event_id = event["event_id"]
        source_hash = event["source_ref_hash"]
        refs = _unique_refs(by_event_id.get(event_id, []) + by_hash.get(source_hash, []))
        if not refs:
            unresolved.append(
                {
                    "event_id": event_id,
                    "event_kind": event["event_kind"],
                    "source_ref_hash": source_hash,
                    "reason": "source_lookup_missing",
                }
            )
            continue
        resolved_event_ids.append(event_id)
        resolved_refs.extend(refs)
        if source_hash:
            source_hashes.append(source_hash)

    status = _resolution_status(
        packet_kind_valid=packet_kind_valid,
        timeline=timeline,
        unresolved_count=len(unresolved),
    )
    recommended_use = _recommended_use(packet, status)
    safe_uses = list(SAFE_NAVIGATION_USES)
    if status == "complete" and not packet.get("sequence_gaps"):
        safe_uses.append("remind")

    cannot_claim = unique_preserve(
        _string_items(packet.get("cannot_claim"))
        + [
            "sequence_packet_is_not_evidence",
            "packet_order_is_navigation_hint_not_truth",
            "current_validity_requires_source_reopen",
        ]
        + (["source_catalog_required_for_reopen"] if status in {"partial", "unresolved", "invalid_packet"} else [])
        + (["sequence_order_uncertain"] if packet.get("sequence_gaps") else []),
        limit=16,
    )

    return {
        "kind": SEQUENCE_PACKET_REOPEN_PLAN_KIND,
        "packet_kind_valid": packet_kind_valid,
        "resolution_status": status,
        "recommended_use": recommended_use,
        "safe_uses": safe_uses,
        "route": {
            "source_event_ids": [event["event_id"] for event in timeline if event["event_id"]],
            "resolved_source_event_ids": resolved_event_ids,
            "source_refs": _unique_refs(resolved_refs),
            "source_ref_hashes": unique_preserve(source_hashes, limit=24),
            "unresolved_timeline_events": unresolved,
            "source_window": {
                "timeline_event_count": len(timeline),
                "resolved_event_count": len(resolved_event_ids),
                "unresolved_event_count": len(unresolved),
                "preserve_packet_order": True,
                "raw_source_serialized": False,
            },
        },
        "cannot_claim": cannot_claim,
        "issue_readouts": {
            "github_663": {
                "source_reopen_from_sequence_packet": status,
                "packet_as_truth": "blocked",
                "live_host_behavior": "not_measured",
                "private_history_adjudication": "not_measured",
                "closeout_eligible": False,
            }
        },
    }
