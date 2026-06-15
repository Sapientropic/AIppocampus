"""Foreground MemoryPacket compaction helpers."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from aippocampus_runtime import core
from aippocampus_runtime.recall import agent_facade_contract as facade


def _json_bytes(value: Mapping[str, Any]) -> int:
    return len(json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8"))


def fit_memory_packet_with_route_delta(packet: dict[str, Any]) -> dict[str, Any]:
    if _json_bytes(packet) <= facade.FOREGROUND_PACKET_BYTE_BUDGET:
        return packet
    packet.pop("route_label_specificity_score", None)
    packet.pop("label_granularity", None)
    packet.pop("scope_bucket", None)
    packet.pop("triage_rank_reason_codes", None)
    packet.pop("risk_flags", None)
    if _json_bytes(packet) <= facade.FOREGROUND_PACKET_BYTE_BUDGET:
        return packet
    hint = packet.get("selection_hint")
    if isinstance(hint, Mapping):
        packet["selection_hint"] = {
            "source": str(hint.get("source") or "")[:80],
            "why": core.compact_text(str(hint.get("why") or ""), 96),
        }
    if _json_bytes(packet) <= facade.FOREGROUND_PACKET_BYTE_BUDGET:
        return packet
    if "display_hint" in packet:
        packet["display_hint"] = core.compact_text(str(packet.get("display_hint") or ""), 96)
    if "route_label" in packet:
        packet["route_label"] = core.compact_text(str(packet.get("route_label") or ""), 96)
    if _json_bytes(packet) <= facade.FOREGROUND_PACKET_BYTE_BUDGET:
        return packet
    if packet.get("route_delta_reason_codes"):
        packet.pop("display_hint", None)
    if _json_bytes(packet) <= facade.FOREGROUND_PACKET_BYTE_BUDGET:
        return packet
    packet.pop("selection_hint", None)
    if _json_bytes(packet) <= facade.FOREGROUND_PACKET_BYTE_BUDGET:
        return packet
    if "route_label" in packet:
        packet["route_label"] = core.compact_text(str(packet.get("route_label") or ""), 64)
    if _json_bytes(packet) <= facade.FOREGROUND_PACKET_BYTE_BUDGET:
        return packet
    packet.pop("route_topic", None)
    return packet
