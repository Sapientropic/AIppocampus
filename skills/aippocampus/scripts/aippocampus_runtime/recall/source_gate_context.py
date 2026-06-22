"""Attach source-anchor gate context to deepen requests."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def attach_source_gate_context_to_deepen_requests(
    *,
    source_anchor_gate: Mapping[str, Any],
    routes: list[dict[str, Any]],
    memory_packets: list[dict[str, Any]],
    deepen_requests: list[dict[str, Any]],
) -> None:
    """Carry recall source-gate posture into the deepen/open follow-through.

    The foreground packet can offer a route only when the source gate has proved
    that opening it is useful for the cue. Keep this context on the matching
    deepen request so CLI and MCP projections cannot quietly turn a diagnostic
    source into an evidence route.
    """

    if not deepen_requests or not memory_packets:
        return
    top_packet = memory_packets[0]
    route_id = str(top_packet.get("route_id") or "").strip()
    if not route_id:
        return
    source_chain_role = str(
        top_packet.get("source_chain_role")
        or (routes[0].get("source_chain_role") if routes else "")
        or ""
    ).strip()
    compact_gate = {
        key: value
        for key, value in dict(source_anchor_gate).items()
        if key
        in {
            "status",
            "reason",
            "anchor_count",
            "opened_anchor_hits",
            "required_anchor_hits",
            "target_source_matched",
            "source_chain_role",
            "artifact_role",
        }
        and value not in (None, "", [], {})
    }
    gate_status = str(compact_gate.get("status") or "")
    recommended: bool | None = None
    if gate_status in {"passed", "blocked"}:
        recommended = bool(compact_gate.get("target_source_matched")) and str(
            top_packet.get("route_choice_posture") or ""
        ) not in {"low_confidence_source_anchor_gap"}
    for request in deepen_requests:
        if str(request.get("route_id") or "").strip() != route_id:
            continue
        request["source_anchor_gate"] = compact_gate
        if gate_status in {"passed", "blocked"}:
            request["target_source_matched"] = bool(compact_gate.get("target_source_matched"))
        if recommended is not None:
            request["recommended_evidence_route"] = recommended
        if source_chain_role:
            request["source_chain_role"] = source_chain_role
        posture = str(top_packet.get("route_choice_posture") or "").strip()
        if posture:
            request["route_choice_posture"] = posture
        break
