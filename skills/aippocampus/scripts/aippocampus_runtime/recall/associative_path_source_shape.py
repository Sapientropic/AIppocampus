"""APW candidate adapter for the shared source-shape guard spine.

APW can help an agent find a route after ordinary recall is weak, but its
diagnostic candidates must not jump around the source-shape privacy/freshness
guards. Keep this adapter small and boring: it copies only compact candidate
metadata into the shared descriptor and leaves source truth to deepen/reopen.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

from aippocampus_runtime import core
from aippocampus_runtime.source_shape import (
    build_source_shape_descriptor,
    project_source_shape_for_foreground,
)

PRIVATE_BUCKETS = {"private", "restricted", "personal", "user_private", "machine_private"}
STALE_STATUSES = {"stale", "superseded", "refuted", "retired", "archived", "expired"}
TEMPORAL_KEYS = (
    "source_coverage_time",
    "source_event_time",
    "materialized_at",
    "built_at",
    "valid_after",
    "valid_until",
    "review_after",
    "topic_epoch",
    "source_epoch",
    "invalidation_epoch",
    "invalidation_reasons",
)


def _text(value: Any, limit: int = 120) -> str:
    return core.compact_text(str(value or "").strip(), limit)


def _stable_id(prefix: str, *parts: Any) -> str:
    raw = json.dumps(parts, ensure_ascii=False, sort_keys=True, default=str)
    return f"{prefix}_{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:16]}"


def _scope(candidate: Mapping[str, Any]) -> str:
    for key in ("scope_bucket", "privacy_partition", "privacy_domain", "scope"):
        value = _text(candidate.get(key), 80).casefold()
        if value:
            return value
    return "public_default"


def _freshness(candidate: Mapping[str, Any]) -> str:
    for key in ("freshness", "currentness", "status"):
        value = _text(candidate.get(key), 80).casefold()
        if value:
            return value
    return "current"


def _privacy_state(candidate: Mapping[str, Any], scope: str) -> str:
    visibility = _text(candidate.get("visibility"), 80).casefold()
    if visibility == "blocked" or scope in PRIVATE_BUCKETS or candidate.get("privacy_blocked"):
        return "blocked"
    return "allowed"


def _temporal(candidate: Mapping[str, Any]) -> dict[str, Any]:
    temporal: dict[str, Any] = {}
    for key in TEMPORAL_KEYS:
        value = candidate.get(key)
        if value not in (None, "", [], {}):
            temporal[key] = value
    return temporal


def build_associative_path_source_shape(
    candidate: Mapping[str, Any],
    *,
    refs: list[dict[str, Any]],
    route_id: str | None = None,
) -> dict[str, Any]:
    """Return descriptor + compact projection for one APW candidate."""

    safe_route_id = _text(route_id or candidate.get("route_id"), 120) or _stable_id(
        "apw",
        candidate,
        refs,
    )
    scope = _scope(candidate)
    freshness = _freshness(candidate)
    privacy_state = _privacy_state(candidate, scope)
    bridge_ids = [
        _text(bridge_id, 80)
        for bridge_id in candidate.get("bridge_ids") or []
        if _text(bridge_id, 80)
    ]
    descriptor = build_source_shape_descriptor(
        producer="associative_path_walker",
        source_refs=refs,
        source_snapshot={
            "source_ids": sorted(
                {
                    _text(ref.get("source_id"), 120)
                    for ref in refs
                    if _text(ref.get("source_id"), 120)
                }
            ),
            "coverage_scope": scope,
        },
        derivation_dag={
            "producer": "associative_path_walker",
            "nodes": [
                {"id": safe_route_id, "kind": "apw_candidate", "scope": scope},
                *({"id": bridge_id, "kind": "semantic_bridge"} for bridge_id in bridge_ids),
            ],
            "edges": [],
        },
        temporal=_temporal(candidate),
        guard_inputs={
            "privacy_state": privacy_state,
            "freshness": freshness,
            "authority_level": candidate.get("authority_level") or "navigation_only",
            "claim_permission": candidate.get("claim_permission") or "no_claim_before_reopen",
            "projection_allowed": candidate.get("projection_allowed", True),
            "parallel_compatibility": candidate.get("source_shape_completeness") or "complete",
            "source_epoch": candidate.get("source_epoch"),
            "invalidation_epoch": candidate.get("invalidation_epoch"),
            "invalidation_reasons": candidate.get("invalidation_reasons"),
        },
        signals={
            "compatibility": {
                "status": "opt_in_fallback_only",
                "reason_code": "ordinary_recall_weak_or_silent",
            },
            "familiarity": {
                "status": candidate.get("source") or "associative_path_candidate",
                "posture": "navigation_only",
            },
        },
        projection_intent="foreground_recall",
        target_surfaces=("agent_recall_compact",),
        source_shape_id=_stable_id("source_shape_apw", safe_route_id, refs, scope, freshness),
    )
    return {
        "descriptor": descriptor,
        "projection": project_source_shape_for_foreground(descriptor),
        "guard_inputs": {
            "scope_bucket": scope,
            "privacy_state": privacy_state,
            "freshness": freshness,
        },
    }


__all__ = ["build_associative_path_source_shape"]
