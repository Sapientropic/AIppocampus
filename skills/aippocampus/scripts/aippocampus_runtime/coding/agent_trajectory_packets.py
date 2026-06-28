#!/usr/bin/env python3
"""Live agent trajectory packets built on existing sequence-packet owners.

Agent trajectories are ordered navigation handles, not source truth. This
module only joins already-clean route notes, behavior events, decisions, and
final closeouts into a `sequence_packet` plus a source catalog that
`sequence_reopen` can consume. Raw commentary, stdout, command args, and local
paths stay outside the packet.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from typing import Any

from aippocampus_runtime.coding import sequence_packets, sequence_reopen
from aippocampus_runtime.core import stable_json_id
from aippocampus_runtime.ops.route_readiness import safe_source_refs
from aippocampus_runtime.registry.api import unique_preserve

AGENT_TRAJECTORY_PACKET_KIND = "aippocampus_live_agent_trajectory_packet"
AGENT_TRAJECTORY_SCHEMA_VERSION = 1


def _source_hash(ref: Mapping[str, Any]) -> str:
    material = json.dumps(
        {
            "thread_key": ref.get("thread_key"),
            "message_id": ref.get("message_id"),
            "turn_id": ref.get("turn_id"),
            "line": ref.get("line") or ref.get("source_line"),
        },
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    )
    return "sha256:" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:20]


def _refs(row: Mapping[str, Any]) -> list[dict[str, Any]]:
    refs = safe_source_refs(row.get("source_refs"))
    if not refs and isinstance(row.get("source_ref"), Mapping):
        refs = safe_source_refs([row.get("source_ref")])
    return refs[:3]


def _line(row: Mapping[str, Any]) -> int:
    for key in ("source_line", "line", "raw_start_line"):
        value = row.get(key)
        try:
            return int(value)
        except (TypeError, ValueError):
            continue
    refs = _refs(row)
    if refs:
        try:
            return int(refs[0].get("line") or refs[0].get("source_line") or 0)
        except (TypeError, ValueError):
            return 0
    return 0


def _turn(row: Mapping[str, Any]) -> int:
    try:
        return int(row.get("turn_index") or 0)
    except (TypeError, ValueError):
        return 0


def _event_id(prefix: str, row: Mapping[str, Any], refs: list[Mapping[str, Any]]) -> str:
    for key in ("event_id", "route_note_id", "decision_id", "message_id"):
        raw = str(row.get(key) or "").strip()
        if raw:
            return raw[:160]
    return stable_json_id(prefix, row.get("kind"), row.get("event_kind"), refs, length=20)


def _route_note_event(row: Mapping[str, Any]) -> dict[str, Any] | None:
    refs = _refs(row)
    if not refs:
        refs = safe_source_refs(row.get("joined_evidence_refs"))[:3]
    if not refs:
        return None
    return {
        "event_id": _event_id("agent_route_note", row, refs),
        "event_kind": "route_note",
        "source_refs": refs,
        "sort_key": (_turn(row), _line(row), 0),
        "source_role": "route_note_joined_evidence",
    }


def _behavior_event(row: Mapping[str, Any]) -> dict[str, Any] | None:
    refs = _refs(row)
    if not refs:
        return None
    raw_kind = str(row.get("hard_event_kind") or row.get("event_kind") or "behavior_event")
    kind = raw_kind if raw_kind.startswith("tool_") or raw_kind.endswith("_event") else "behavior_event"
    return {
        "event_id": _event_id("agent_behavior", row, refs),
        "event_kind": kind,
        "source_refs": refs,
        "sort_key": (_turn(row), _line(row), 1),
        "source_role": "behavior_event",
    }


def _decision_event(row: Mapping[str, Any]) -> dict[str, Any] | None:
    refs = _refs(row)
    if not refs:
        return None
    event_type = str(row.get("event_type") or row.get("decision_type") or "decision_event")
    return {
        "event_id": _event_id("agent_decision", row, refs),
        "event_kind": event_type,
        "source_refs": refs,
        "sort_key": (_turn(row), _line(row), 2),
        "source_role": "decision_event",
    }


def _final_closeout_event(row: Mapping[str, Any]) -> dict[str, Any] | None:
    refs = _refs(row)
    if not refs:
        return None
    return {
        "event_id": _event_id("agent_final_closeout", row, refs),
        "event_kind": "final_closeout",
        "source_refs": refs,
        "sort_key": (_turn(row), _line(row), 3),
        "source_role": "final_closeout",
    }


def _with_hashes(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for event in events:
        refs = [ref for ref in event.get("source_refs") or [] if isinstance(ref, Mapping)]
        first_ref = refs[0] if refs else {}
        out.append(
            {
                **event,
                "source_ref_hash": _source_hash(first_ref) if first_ref else "",
            }
        )
    return out


def _sequence_gaps(events: list[dict[str, Any]]) -> list[str]:
    kinds = [str(event.get("event_kind") or "") for event in events]
    roles = [str(event.get("source_role") or "") for event in events]
    gaps: list[str] = []
    if "route_note_joined_evidence" not in roles:
        gaps.append("missing_route_note")
    if "behavior_event" not in roles:
        gaps.append("missing_behavior_event")
    if not ({"decision_event", "final_closeout"} & set(roles)):
        gaps.append("missing_decision_or_final_closeout")
    role_order = [role for role in roles if role in {"route_note_joined_evidence", "behavior_event", "decision_event", "final_closeout"}]
    expected_order = ["route_note_joined_evidence", "behavior_event", "decision_event", "final_closeout"]
    indexes = [expected_order.index(role) for role in role_order]
    if indexes != sorted(indexes):
        gaps.append("wrong_order")
    if len(kinds) < 3:
        gaps.append("single_point_or_thin_chain")
    return unique_preserve(gaps, limit=8)


def _source_catalog(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    catalog: list[dict[str, Any]] = []
    for event in events:
        refs = [ref for ref in event.get("source_refs") or [] if isinstance(ref, Mapping)]
        if not refs:
            continue
        catalog.append(
            {
                "event_id": event["event_id"],
                "source_ref_hash": event.get("source_ref_hash"),
                "source_refs": refs[:1],
                "source_role": event.get("source_role"),
            }
        )
    return catalog


def _packet(events: list[dict[str, Any]], *, trigger: str, gaps: list[str]) -> dict[str, Any]:
    source_thickness = "usable" if not gaps else "thin"
    return {
        "kind": sequence_packets.SEQUENCE_PACKET_KIND,
        "producer_family": "agent_trajectory",
        "trigger": trigger,
        "why_relevant": "live_agent_route_note_behavior_decision_chain",
        "timeline": [
            {
                "event_id": event["event_id"],
                "event_kind": event["event_kind"],
                "source_ref_hash": event.get("source_ref_hash") or "",
            }
            for event in events
        ],
        "current_assessment": {
            "source_thickness": source_thickness,
            "freshness": "needs_reopen",
            "proposed_use": "refresh_sources",
            "truth_boundary": "derived_weather_not_source_fact",
        },
        "sequence_gaps": gaps,
        "cannot_claim": unique_preserve(
            [
                "agent_trajectory_is_navigation_not_truth",
                "current_validity_requires_source_reopen",
                "raw_commentary_or_tool_output_serialized",
                *(["sequence_order_uncertain"] if gaps else []),
            ],
            limit=8,
        ),
        "training_signal_roles": ["process_supervision", "replay_sample"],
    }


def build_live_agent_trajectory_packet(
    *,
    route_notes: Iterable[Mapping[str, Any]] = (),
    behavior_events: Iterable[Mapping[str, Any]] = (),
    decision_events: Iterable[Mapping[str, Any]] = (),
    final_closeouts: Iterable[Mapping[str, Any]] = (),
    trigger: str = "live_agent_trace",
) -> dict[str, Any]:
    """Build a source-reopenable live agent trajectory report."""

    events: list[dict[str, Any]] = []
    for row in route_notes:
        if isinstance(row, Mapping) and (event := _route_note_event(row)):
            events.append(event)
    for row in behavior_events:
        if isinstance(row, Mapping) and (event := _behavior_event(row)):
            events.append(event)
    for row in decision_events:
        if isinstance(row, Mapping) and (event := _decision_event(row)):
            events.append(event)
    for row in final_closeouts:
        if isinstance(row, Mapping) and (event := _final_closeout_event(row)):
            events.append(event)
    events = _with_hashes(sorted(events, key=lambda event: event["sort_key"]))
    gaps = _sequence_gaps(events)
    packet = _packet(events, trigger=trigger, gaps=gaps)
    catalog = _source_catalog(events)
    reopen_plan = sequence_reopen.build_sequence_packet_reopen_plan(packet, source_catalog=catalog)
    return {
        "kind": AGENT_TRAJECTORY_PACKET_KIND,
        "schema_version": AGENT_TRAJECTORY_SCHEMA_VERSION,
        "status": "complete" if events and not gaps else "gappy" if events else "empty",
        "sequence_packet": packet,
        "source_catalog": catalog,
        "reopen_plan": reopen_plan,
        "metrics": {
            "timeline_event_count": len(events),
            "source_catalog_ref_count": len(catalog),
            "gap_count": len(gaps),
        },
        "compact_summary": {
            "status": "complete" if events and not gaps else "refresh_sources",
            "timeline_event_count": len(events),
            "gap_count": len(gaps),
            "source_reopen_required": True,
        },
        "privacy_boundary": {
            "raw_commentary_serialized": False,
            "raw_tool_output_serialized": False,
            "full_command_args_serialized": False,
            "local_paths_serialized": False,
        },
        "claim_boundary": "agent_trajectory_navigation_only_reopen_source_before_claim",
    }


__all__ = [
    "AGENT_TRAJECTORY_PACKET_KIND",
    "build_live_agent_trajectory_packet",
]
