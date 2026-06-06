#!/usr/bin/env python3
"""Deterministic topology-anchor lifecycle pressure over source-joined graph rows."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

POLICY_KIND = "aippocampus_topology_anchor_policy"
SCHEMA_VERSION = 1


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def topology_anchor_weight(row: Mapping[str, Any]) -> dict[str, Any]:
    """Classify one graph/source row as lifecycle pressure, never source truth."""

    source_refs = [ref for ref in _as_list(row.get("source_refs")) if isinstance(ref, Mapping)]
    cluster_ids = [str(item) for item in _as_list(row.get("cluster_ids")) if str(item)]
    bridge_score = _as_float(row.get("bridge_score"))
    high_degree = int(_as_float(row.get("degree")))
    unique_route_support = bool(row.get("unique_route_support"))
    supersession_edge = bool(row.get("supersession_edge") or row.get("contradiction_edge"))
    privacy_blocked = bool(row.get("privacy_blocked"))

    reasons: list[str] = []
    weight = 0.0
    diagnostic_only = False
    noisy_hub_suppressed = False

    if not source_refs:
        diagnostic_only = True
        reasons.append("missing_source_refs")
    if privacy_blocked:
        reasons.append("privacy_blocked")

    bridge_like = bool(bridge_score >= 0.65 and len(set(cluster_ids)) >= 2)
    if bridge_like:
        weight += 0.45
        reasons.append("cross_cluster_bridge")
    if unique_route_support:
        weight += 0.25
        reasons.append("unique_route_support")
    if supersession_edge:
        weight += 0.2
        reasons.append("supersession_context_preserved")
    if high_degree >= 12 and not (bridge_like or unique_route_support):
        noisy_hub_suppressed = True
        weight = min(weight, 0.1)
        reasons.append("high_degree_noisy_hub_not_protected")

    if diagnostic_only or privacy_blocked:
        classification = "diagnostic_only" if diagnostic_only else "blocked"
        decay_multiplier = 1.0
        protected = False
    elif weight >= 0.65:
        classification = "must_keep"
        decay_multiplier = 0.35
        protected = True
    elif weight >= 0.35 or supersession_edge:
        classification = "review_before_archive"
        decay_multiplier = 0.6
        protected = True
    else:
        classification = "ordinary_decay"
        decay_multiplier = 1.0
        protected = False

    return {
        "node_id": str(row.get("node_id") or row.get("source_id") or ""),
        "topology_anchor_weight": round(weight, 3),
        "classification": classification,
        "decay_multiplier": decay_multiplier,
        "protected_by_topology": protected,
        "source_ref_count": len(source_refs),
        "source_refs_available": bool(source_refs),
        "noisy_hub_suppressed": noisy_hub_suppressed,
        "stale_bridge_reopen_required": bool(supersession_edge and source_refs),
        "promoted_to_current_fact": False,
        "support_level": "navigation_lifecycle",
        "reasons": reasons,
    }


def topology_anchor_report(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    row_list = list(rows)
    nodes = [topology_anchor_weight(row) for row in row_list]
    return {
        "kind": POLICY_KIND,
        "schema_version": SCHEMA_VERSION,
        "ok": True,
        "no_write": True,
        "nodes": nodes,
        "metrics": {
            "topology_protected_anchor_count": sum(
                1 for node in nodes if node["protected_by_topology"]
            ),
            "bridge_reopen_helpful_count": sum(
                1
                for row, node in zip(row_list, nodes, strict=True)
                if bool(row.get("observed_reopen_helpful")) and node["protected_by_topology"]
            ),
            "noisy_hub_suppression_count": sum(
                1 for node in nodes if node["noisy_hub_suppressed"]
            ),
            "stale_bridge_reopen_required_count": sum(
                1 for node in nodes if node["stale_bridge_reopen_required"]
            ),
        },
        "contract": {
            "topology_is_navigation_lifecycle_pressure": True,
            "graph_centrality_is_not_truth": True,
            "source_refs_required_for_protection": True,
            "privacy_and_user_correction_override_topology": True,
            "foreground_claims_still_require_source_reopen": True,
        },
        "can_claim": [
            "bridge_anchors_can_decay_slower_than_leaf_nodes",
            "noisy_high_degree_nodes_are_not_protected_by_popularity_alone",
            "supersession_routes_preserve_context_without_promoting_stale_claims",
        ],
        "cannot_claim": [
            "old_bridge_memory_is_current_fact",
            "model_generated_topology_is_source_evidence",
            "all_high_degree_nodes_are_durable_anchors",
            "topology_policy_mutates_clean_source",
        ],
    }


def fixture_topology_anchor_report() -> dict[str, Any]:
    return topology_anchor_report(
        [
            {
                "node_id": "old-low-frequency-bridge",
                "source_refs": [{"source_id": "clean:bridge", "message_id": "m1"}],
                "cluster_ids": ["project", "life"],
                "bridge_score": 0.91,
                "degree": 4,
                "unique_route_support": True,
                "observed_reopen_helpful": True,
            },
            {
                "node_id": "popular-noisy-hub",
                "source_refs": [{"source_id": "clean:hub", "message_id": "m2"}],
                "cluster_ids": ["generic"],
                "bridge_score": 0.12,
                "degree": 80,
            },
            {
                "node_id": "superseded-bridge-context",
                "source_refs": [{"source_id": "clean:superseded", "message_id": "m3"}],
                "cluster_ids": ["old-plan", "current-plan"],
                "bridge_score": 0.58,
                "degree": 3,
                "supersession_edge": True,
            },
            {
                "node_id": "model-only-topology",
                "cluster_ids": ["model"],
                "bridge_score": 0.95,
                "degree": 2,
            },
        ]
    )
