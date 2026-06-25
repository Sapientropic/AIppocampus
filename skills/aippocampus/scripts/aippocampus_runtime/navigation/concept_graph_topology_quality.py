"""Topology quality controls for navigation-only concept graph edges.

The term-quality gate catches bad labels before materialization. This module
owns the separate failure mode where a broad project-like label becomes a
high-authority hub merely because many subconscious edges mention it. The graph
is still only navigation scent: these controls park unsafe expansion edges; they
do not judge source truth.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from aippocampus_runtime.navigation.associations import normalize_term
from aippocampus_runtime.navigation.concept_kinds import classify_concept_kind
from aippocampus_runtime.navigation.concept_lifecycle import safe_diagnostic_hash

RISKY_SUBCONSCIOUS_HUB_EDGE_TYPES = {
    "related",
    "verified_related",
    "same_decision_space",
}
GENERIC_SUBCONSCIOUS_HUB_EDGE_TYPES = {"related", "verified_related"}

SUBCONSCIOUS_HUB_COLLAPSE_MIN_FANOUT = 8
SUBCONSCIOUS_HUB_COLLAPSE_GENERIC_RATIO = 0.7
SUBCONSCIOUS_HUB_COLLAPSE_HIGH_FANOUT = 12
SUBCONSCIOUS_HUB_COLLAPSE_TARGET_KIND_DIVERSITY = 3
SUBCONSCIOUS_HUB_MAX_ACTIVE_EDGES = 6
SUBCONSCIOUS_HUB_COLLAPSE_REASON = "subconscious_hub_collapse"

PROJECT_LIKE_KINDS = {"project", "library", "tool"}


@dataclass(frozen=True)
class HubEdgeDecision:
    """Navigation-only edge override for one staged subconscious edge group."""

    status: str
    reason: str


def _bucket_count(value: int) -> str:
    count = int(value or 0)
    if count <= 0:
        return "0"
    if count <= 3:
        return "1-3"
    if count <= 7:
        return "4-7"
    if count <= 15:
        return "8-15"
    return "16+"


def _ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 4)


def _concept_kind_for(label: Any, supplied_kind: Any = None) -> str:
    classified = classify_concept_kind(
        normalize_term(str(label or "")),
        supplied_kind=supplied_kind,
        supplied_kind_status="reviewed" if supplied_kind else None,
    )
    return str(classified.get("kind") or "topic")


def _project_like(label: Any, supplied_kind: Any = None) -> bool:
    return _concept_kind_for(label, supplied_kind) in PROJECT_LIKE_KINDS


def _group_key(group: Mapping[str, Any]) -> tuple[str, str, str]:
    return (
        normalize_term(str(group.get("src") or "")),
        normalize_term(str(group.get("dst") or "")),
        str(group.get("edge_type") or "unknown"),
    )


def _thread_keys(group: Mapping[str, Any]) -> set[str]:
    return {
        str(key)
        for key in group.get("thread_keys") or []
        if str(key or "").strip()
    }


def _refs(group: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [ref for ref in group.get("refs") or [] if isinstance(ref, dict)]


def _edge_sort_key(edge: Mapping[str, Any]) -> tuple[int, int, float, str]:
    group = edge["group"]
    edge_type = str(group.get("edge_type") or "")
    specificity = 1 if edge_type not in GENERIC_SUBCONSCIOUS_HUB_EDGE_TYPES else 0
    return (
        specificity,
        len(_thread_keys(group)),
        float(group.get("confidence") or 0.0),
        normalize_term(str(edge.get("target") or "")),
    )


def _should_treat_as_collapsed(stats: Mapping[str, Any]) -> bool:
    fanout = int(stats.get("fanout") or 0)
    generic_ratio = float(stats.get("generic_relation_ratio") or 0.0)
    target_kind_count = int(stats.get("target_kind_count") or 0)
    edge_type_count = int(stats.get("edge_type_count") or 0)

    if fanout < SUBCONSCIOUS_HUB_COLLAPSE_MIN_FANOUT:
        return False
    if (
        generic_ratio >= SUBCONSCIOUS_HUB_COLLAPSE_GENERIC_RATIO
        and target_kind_count >= SUBCONSCIOUS_HUB_COLLAPSE_TARGET_KIND_DIVERSITY
    ):
        return True
    if fanout >= SUBCONSCIOUS_HUB_COLLAPSE_HIGH_FANOUT and edge_type_count <= 2:
        return True
    return False


def assess_subconscious_hub_quality(
    groups: Iterable[Mapping[str, Any]],
) -> tuple[dict[tuple[str, str, str], HubEdgeDecision], dict[str, Any]]:
    """Return edge park decisions plus privacy-safe hub quality metrics.

    The decision operates on grouped staged rows, before SQLite materialization.
    A collapsing hub is capped rather than deleted: the best few source-backed,
    relation-specific edges remain active for orientation, and the rest are
    parked so recall expansion cannot be dragged through a project-name funnel.
    """

    group_list = [group for group in groups if isinstance(group, Mapping)]
    hub_edges: dict[str, list[dict[str, Any]]] = defaultdict(list)
    hub_labels: dict[str, str] = {}

    for group in group_list:
        edge_type = str(group.get("edge_type") or "")
        if edge_type not in RISKY_SUBCONSCIOUS_HUB_EDGE_TYPES:
            continue
        endpoints = [
            ("src", group.get("src"), group.get("src_kind"), group.get("dst"), group.get("dst_kind")),
            ("dst", group.get("dst"), group.get("dst_kind"), group.get("src"), group.get("src_kind")),
        ]
        for side, label, supplied_kind, target, target_kind in endpoints:
            if not _project_like(label, supplied_kind):
                continue
            normalized = normalize_term(str(label or ""))
            if not normalized:
                continue
            hub_id = normalized.casefold()
            hub_labels[hub_id] = normalized
            hub_edges[hub_id].append(
                {
                    "group_key": _group_key(group),
                    "side": side,
                    "target": normalize_term(str(target or "")),
                    "target_kind": _concept_kind_for(target, target_kind),
                    "edge_type": edge_type,
                    "group": group,
                }
            )

    decisions: dict[tuple[str, str, str], HubEdgeDecision] = {}
    hub_degree_buckets: Counter[str] = Counter()
    edge_type_counts_by_status: dict[str, Counter[str]] = defaultdict(Counter)
    collapsed_hubs: list[dict[str, Any]] = []
    candidate_count = 0
    parked_group_keys: set[tuple[str, str, str]] = set()
    kept_capped_group_keys: set[tuple[str, str, str]] = set()

    for hub_id, edges in sorted(hub_edges.items()):
        unique_edges: dict[tuple[str, str, str], dict[str, Any]] = {}
        for edge in edges:
            unique_edges.setdefault(edge["group_key"], edge)
        fanout_edges = list(unique_edges.values())
        fanout = len(fanout_edges)
        candidate_count += 1
        hub_degree_buckets[_bucket_count(fanout)] += 1

        edge_type_counter = Counter(str(edge["edge_type"]) for edge in fanout_edges)
        generic_count = sum(
            count
            for edge_type, count in edge_type_counter.items()
            if edge_type in GENERIC_SUBCONSCIOUS_HUB_EDGE_TYPES
        )
        target_kind_counter = Counter(str(edge["target_kind"]) for edge in fanout_edges)
        thread_keys: set[str] = set()
        evidence_count = 0
        for edge in fanout_edges:
            group = edge["group"]
            thread_keys.update(_thread_keys(group))
            evidence_count += len(_refs(group))
        stats = {
            "fanout": fanout,
            "generic_relation_ratio": _ratio(generic_count, fanout),
            "target_kind_count": len(target_kind_counter),
            "edge_type_count": len(edge_type_counter),
        }
        if not _should_treat_as_collapsed(stats):
            for edge_type, count in edge_type_counter.items():
                edge_type_counts_by_status[edge_type]["active"] += count
            continue

        ranked = sorted(fanout_edges, key=_edge_sort_key, reverse=True)
        kept_keys = {
            edge["group_key"]
            for edge in ranked[:SUBCONSCIOUS_HUB_MAX_ACTIVE_EDGES]
        }
        parked_keys = {edge["group_key"] for edge in ranked} - kept_keys
        for key in parked_keys:
            decisions[key] = HubEdgeDecision(
                status="parked",
                reason=SUBCONSCIOUS_HUB_COLLAPSE_REASON,
            )
        parked_group_keys.update(parked_keys)
        kept_capped_group_keys.update(kept_keys)
        for edge in fanout_edges:
            status = "active" if edge["group_key"] in kept_keys else "parked"
            edge_type_counts_by_status[str(edge["edge_type"])][status] += 1
        collapsed_hubs.append(
            {
                "concept_hash": safe_diagnostic_hash(hub_labels.get(hub_id, hub_id)),
                "fanout_bucket": _bucket_count(fanout),
                "generic_relation_ratio": stats["generic_relation_ratio"],
                "target_kind_count": len(target_kind_counter),
                "source_thread_bucket": _bucket_count(len(thread_keys)),
                "evidence_count_bucket": _bucket_count(evidence_count),
                "active_edge_group_count": len(kept_keys),
                "parked_edge_group_count": len(parked_keys),
                "edge_type_counts": dict(sorted(edge_type_counter.items())),
                "target_kind_counts": dict(sorted(target_kind_counter.items())),
            }
        )

    payload = {
        "schema_version": "subconscious_hub_quality_v1",
        "producer": "subconscious",
        "mode": "park_edges_not_concepts",
        "risky_edge_types": sorted(RISKY_SUBCONSCIOUS_HUB_EDGE_TYPES),
        "collapse_min_fanout": SUBCONSCIOUS_HUB_COLLAPSE_MIN_FANOUT,
        "collapse_generic_ratio": SUBCONSCIOUS_HUB_COLLAPSE_GENERIC_RATIO,
        "max_active_edges_per_collapsed_hub": SUBCONSCIOUS_HUB_MAX_ACTIVE_EDGES,
        "hub_candidate_count": candidate_count,
        "collapsed_hub_count": len(collapsed_hubs),
        "parked_edge_group_count": len(parked_group_keys),
        "active_capped_edge_group_count": len(kept_capped_group_keys),
        "hub_degree_buckets": dict(sorted(hub_degree_buckets.items())),
        "edge_type_status_counts": {
            edge_type: dict(sorted(counter.items()))
            for edge_type, counter in sorted(edge_type_counts_by_status.items())
        },
        "collapsed_hub_top": collapsed_hubs[:10],
        "privacy": {
            "raw_labels_default": "omitted",
            "concept_ids_are_hashed": True,
        },
    }
    return decisions, payload


__all__ = [
    "HubEdgeDecision",
    "SUBCONSCIOUS_HUB_COLLAPSE_REASON",
    "assess_subconscious_hub_quality",
]
