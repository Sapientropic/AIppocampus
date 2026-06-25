"""Source-shaped semantic candidate context.

This reducer is the small bridge between source-shape diagnostics and semantic
recall/bridge candidates.  It keeps semantic material useful for routing while
making the claim ceiling explicit: candidate context can guide search and
reopen order, but it cannot become source evidence by itself.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from aippocampus_runtime.core import stable_json_tuple_id
from aippocampus_runtime.source_shape import (
    build_source_shape_descriptor,
    project_source_shape_for_foreground,
)

SCHEMA_VERSION = 1
CONTEXT_KIND = "aippocampus_semantic_candidate_context"
AUTHORITY = "navigation_only"
CLAIM_PERMISSION = "none"
PRIVATE_PARTITIONS = {"private", "restricted", "personal", "user_private", "machine_private"}
STALE_FRESHNESS = {"stale", "superseded", "refuted", "retired", "archived", "expired"}
SAFE_CODE_RE = re.compile(r"[^A-Za-z0-9_.:#-]+")


def _text(value: Any, *, limit: int = 120) -> str:
    text = str(value or "").strip()
    if len(text) > limit:
        text = text[:limit]
    return text


def _code(value: Any, *, fallback: str = "unknown") -> str:
    text = _text(value, limit=96).casefold().replace(" ", "_")
    text = SAFE_CODE_RE.sub("_", text).strip("_")
    return text or fallback


def _safe_strings(value: Any, *, limit: int = 8) -> list[str]:
    raw_items: Sequence[Any]
    if isinstance(value, str):
        raw_items = [value]
    elif isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        raw_items = value
    else:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in raw_items:
        text = _text(item, limit=96)
        if not text or "\\" in text or "/" in text:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(text)
        if len(out) >= limit:
            break
    return out


def _safe_refs(value: Any, *, limit: int = 6) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    seen: set[tuple[tuple[str, str], ...]] = set()
    raw_items = value if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)) else []
    for item in raw_items:
        if not isinstance(item, Mapping):
            continue
        clean = {
            str(key): item.get(key)
            for key in (
                "thread_key",
                "source_id",
                "message_id",
                "turn_id",
                "turn_index",
                "line",
                "source_line",
                "event_id",
            )
            if item.get(key) not in (None, "", [])
        }
        marker = tuple(sorted((key, str(val)) for key, val in clean.items()))
        if clean and marker not in seen:
            seen.add(marker)
            refs.append(clean)
        if len(refs) >= limit:
            break
    return refs


def _safe_mapping_strings(value: Any, *, limit: int = 6) -> dict[str, list[str]]:
    if not isinstance(value, Mapping):
        return {}
    out: dict[str, list[str]] = {}
    for key, raw in value.items():
        safe_key = _code(key, fallback="")
        if not safe_key:
            continue
        strings = _safe_strings(raw, limit=limit)
        if strings:
            out[safe_key] = strings
    return out


def _recent_outcomes(value: Any) -> dict[str, int]:
    if not isinstance(value, Mapping):
        return {}
    out: dict[str, int] = {}
    for key, raw in value.items():
        code = _code(key, fallback="")
        if not code:
            continue
        try:
            count = int(raw)
        except (TypeError, ValueError):
            continue
        if count > 0:
            out[code] = min(count, 999)
    return dict(sorted(out.items()))


def _derivation_for(row: Mapping[str, Any], refs: list[dict[str, Any]]) -> dict[str, Any]:
    nodes = ["semantic_candidate"]
    if refs:
        nodes.insert(0, "source_ref")
    producer = _code(row.get("producer") or row.get("surface") or "semantic_candidate")
    nodes.append(producer)
    return {"nodes": nodes, "edges": [["source_ref", "semantic_candidate"]] if refs else []}


def _temporal_for(row: Mapping[str, Any], invalidators: list[str]) -> dict[str, Any]:
    temporal = dict(row.get("temporal") or {}) if isinstance(row.get("temporal"), Mapping) else {}
    for key in (
        "source_coverage_time",
        "section_time_window",
        "materialized_at",
        "valid_after",
        "review_after",
        "source_epoch",
        "topic_epoch",
        "invalidation_epoch",
    ):
        if key not in temporal and row.get(key) not in (None, "", [], {}):
            temporal[key] = row.get(key)
    temporal.setdefault("source_epoch", "source-v1")
    temporal.setdefault("topic_epoch", row.get("topic_epoch") or "topic-v1")
    if invalidators:
        temporal["invalidation_reasons"] = invalidators
    return temporal


def _status_and_reasons(
    *,
    refs: list[dict[str, Any]],
    privacy_partition: str,
    freshness: str,
    invalidators: list[str],
    descriptor: Mapping[str, Any],
) -> tuple[str, list[str]]:
    reasons = ["source_shape_context_preferred"]
    if privacy_partition in PRIVATE_PARTITIONS:
        return "blocked", [*reasons, "privacy_partition_blocked"]
    if not refs:
        return "direction_only", [*reasons, "missing_source_refs_fail_open"]
    if freshness in STALE_FRESHNESS or invalidators:
        return "direction_only", [*reasons, "stale_or_invalidated_direction_only"]
    if descriptor.get("descriptor_state") != "complete":
        return "direction_only", [*reasons, "source_shape_descriptor_incomplete"]
    return "accepted", [*reasons, "source_refs_present"]


def build_semantic_candidate_context(row: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize producer-owned semantic hints into public-safe route context."""

    refs = _safe_refs(row.get("source_refs"))
    event_refs = _safe_refs(row.get("event_refs") or row.get("behavior_event_refs"))
    producer = _code(row.get("producer") or row.get("surface"), fallback="semantic_candidate")
    freshness = _code(row.get("freshness"), fallback="unknown")
    privacy_partition = _code(row.get("privacy_partition") or row.get("scope_bucket"), fallback="public_default")
    invalidators = _safe_strings(row.get("invalidators"), limit=8)
    descriptor = build_source_shape_descriptor(
        producer=producer,
        source_refs=refs,
        source_snapshot={
            "source_ids": _safe_strings(row.get("source_ids"), limit=8),
            "source_epoch": _text(row.get("source_epoch"), limit=80),
        },
        derivation_dag=row.get("derivation_dag") or _derivation_for(row, refs),
        compatibility_diagnostics=row.get("compatibility_diagnostics"),
        temporal=_temporal_for(row, invalidators),
        guard_inputs={
            "privacy_state": privacy_partition,
            "freshness": freshness,
            "parallel_compatibility": "complete" if refs else "missing",
            "projection_allowed": bool(refs),
            "claim_permission": CLAIM_PERMISSION,
            "authority_level": AUTHORITY,
        },
        signals={
            "semantic": {
                "producer": producer,
                "task_mode": _code(row.get("task_mode"), fallback="recall"),
            }
        },
        projection_intent="semantic_candidate_routing",
        target_surfaces=row.get("target_surfaces") or ("query_expansion", "semantic_trigger_router"),
    )
    status, reasons = _status_and_reasons(
        refs=refs,
        privacy_partition=privacy_partition,
        freshness=freshness,
        invalidators=invalidators,
        descriptor=descriptor,
    )
    projection = project_source_shape_for_foreground(descriptor)
    return {
        "kind": CONTEXT_KIND,
        "schema_version": SCHEMA_VERSION,
        "context_id": _text(row.get("context_id"), limit=120)
        or stable_json_tuple_id(
            "semctx",
            producer,
            refs,
            row.get("scope"),
            row.get("topic_epoch"),
            ensure_ascii=False,
            length=18,
        ),
        "producer": producer,
        "source_refs": refs,
        "source_ref_count": len(refs),
        "source_families": _safe_strings(row.get("source_families") or row.get("source_family"), limit=8),
        "scope": _text(row.get("scope") or "public_default", limit=96),
        "topic_epoch": _text(row.get("topic_epoch") or "topic-v1", limit=80),
        "freshness": freshness,
        "invalidators": invalidators,
        "task_mode": _code(row.get("task_mode"), fallback="recall"),
        "hook_stage": _code(row.get("hook_stage"), fallback="offline"),
        "behavior_event_refs": event_refs,
        "recent_outcomes": _recent_outcomes(row.get("recent_outcomes") or row.get("outcome_counts")),
        "handles": _safe_mapping_strings(row.get("handles"), limit=6),
        "privacy_partition": privacy_partition,
        "source_shape_id": descriptor.get("source_shape_id"),
        "source_shape_projection": {
            "route_posture": projection.get("route_posture"),
            "action_grammar": projection.get("action_grammar"),
            "risk_flags": projection.get("risk_flags") or [],
        },
        "authority": AUTHORITY,
        "claim_permission": CLAIM_PERMISSION,
        "reducer_status": status,
        "reason_codes": reasons,
        "navigation_only": True,
        "source_reopen_required_before_claim": True,
        "cannot_claim": ["semantic_candidate_context_is_source_truth"],
    }


def build_semantic_candidate_contexts(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [build_semantic_candidate_context(row) for row in rows if isinstance(row, Mapping)]
