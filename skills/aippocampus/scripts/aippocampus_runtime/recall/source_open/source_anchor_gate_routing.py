"""Source-anchor gating helpers for agent recall route ordering."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from aippocampus_runtime.recall import agent_deepen_requests
from aippocampus_runtime.recall import source_anchor_gate as recall_source_anchor_gate

MemoryPacketBuilder = Callable[[dict[str, Any]], dict[str, Any]]


def public_source_anchor_gate(gate: Mapping[str, Any]) -> dict[str, Any]:
    return {
        str(key): value
        for key, value in gate.items()
        if key != "source_ref" and value not in (None, "", [], {})
    }


def route_materials(
    routes: list[dict[str, Any]],
    *,
    memory_packet_for_route: MemoryPacketBuilder,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    memory_packets = [memory_packet_for_route(route) for route in routes]
    deepen_requests = [
        agent_deepen_requests.deepen_request_for_route(route, memory_packet, request_index=index)
        for index, (route, memory_packet) in enumerate(
            zip(routes, memory_packets, strict=True),
            start=1,
        )
        if route.get("handle") and memory_packet.get("output_mode") == "reopenable_route"
    ]
    return memory_packets, deepen_requests


def apply_source_anchor_gate_for_routes(
    *,
    query: str,
    routes: list[dict[str, Any]],
    clean_source_dir: Path,
    registry_dir: Path | None,
    memory_packet_for_route: MemoryPacketBuilder,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    memory_packets, deepen_requests = route_materials(
        routes,
        memory_packet_for_route=memory_packet_for_route,
    )
    source_anchor_gate = recall_source_anchor_gate.apply_top_route_source_anchor_gate(
        query=query,
        routes=routes,
        deepen_requests=deepen_requests,
        memory_packets=memory_packets,
        clean_source_dir=clean_source_dir,
        registry_dir=registry_dir,
    )
    return memory_packets, deepen_requests, source_anchor_gate


def rollback_attention_router_blocked_promotion(
    *,
    query: str,
    baseline_routes: list[dict[str, Any]],
    ranked_routes: list[dict[str, Any]],
    attention_navigation: dict[str, Any],
    memory_packets: list[dict[str, Any]],
    deepen_requests: list[dict[str, Any]],
    source_anchor_gate: dict[str, Any],
    clean_source_dir: Path,
    registry_dir: Path | None,
    memory_packet_for_route: MemoryPacketBuilder,
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    dict[str, Any],
    dict[str, Any],
]:
    """Restore the source-anchor-passing baseline when router promotion is blocked."""

    if (
        not baseline_routes
        or not ranked_routes
        or not attention_navigation.get("enabled")
        or not attention_navigation.get("top_route_changed")
        or source_anchor_gate.get("status") != "blocked"
    ):
        return ranked_routes, memory_packets, deepen_requests, source_anchor_gate, attention_navigation

    baseline_top_id = str(baseline_routes[0].get("route_id") or "").strip()
    promoted_top_id = str(ranked_routes[0].get("route_id") or "").strip()
    if not baseline_top_id or not promoted_top_id or baseline_top_id == promoted_top_id:
        return ranked_routes, memory_packets, deepen_requests, source_anchor_gate, attention_navigation

    _baseline_memory, _baseline_deepen, baseline_gate = apply_source_anchor_gate_for_routes(
        query=query,
        routes=[dict(route) for route in baseline_routes],
        clean_source_dir=clean_source_dir,
        registry_dir=registry_dir,
        memory_packet_for_route=memory_packet_for_route,
    )
    if baseline_gate.get("status") != "passed":
        return ranked_routes, memory_packets, deepen_requests, source_anchor_gate, attention_navigation

    blocked_promoted_gate = dict(source_anchor_gate)
    restored_routes = [
        dict(baseline_routes[0]),
        *[
            dict(route)
            for route in ranked_routes
            if str(route.get("route_id") or "").strip() != baseline_top_id
        ],
    ]
    memory_packets, deepen_requests, source_anchor_gate = apply_source_anchor_gate_for_routes(
        query=query,
        routes=restored_routes,
        clean_source_dir=clean_source_dir,
        registry_dir=registry_dir,
        memory_packet_for_route=memory_packet_for_route,
    )
    attention_navigation = dict(attention_navigation)
    attention_navigation.update(
        {
            "top_route_changed": False,
            "selected_route_id": baseline_top_id,
            "selected_route_index_before": 0,
            "post_source_anchor_rollback_applied": True,
            "router_top_changed_to_blocked_route": True,
            "promotion_blocked_source_gate_incompatible": True,
            "promotion_blocked_route_id": promoted_top_id,
            "demoted_router_route_id": promoted_top_id,
            "baseline_top_route_id": baseline_top_id,
            "blocked_promoted_source_anchor_gate": public_source_anchor_gate(
                blocked_promoted_gate
            ),
            "passing_baseline_source_anchor_gate": public_source_anchor_gate(baseline_gate),
        }
    )
    return restored_routes, memory_packets, deepen_requests, source_anchor_gate, attention_navigation
