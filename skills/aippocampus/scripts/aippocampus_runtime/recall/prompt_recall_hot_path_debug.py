#!/usr/bin/env python3
"""Public-safe debug projection for hot-path foreground route packets."""

from __future__ import annotations

from typing import Any

LIVING_CUE_DIAGNOSTIC_KEYS = (
    "cache_hit_count",
    "cache_miss_count",
    "selected_count",
    "stale_suppressed_count",
    "temporary_suppressed_count",
    "would_overpersonalize_count",
    "low_confidence_suppressed_count",
    "missing_source_ref_count",
    "live_llm_call_count",
)

QUERY_PATTERN_DIAGNOSTIC_KEYS = (
    "route_seen_count",
    "cache_hit_count",
    "cache_miss_count",
    "selected_count",
    "cache_hit_count_by_alias_source",
    "selected_count_by_alias_source",
    "registry_alias_hit_rate",
    "generated_alias_hit_rate",
    "registry_to_generated_alias_lift",
    "multilingual_alias_route_hit_count",
    "nickname_miss_count",
    "stale_suppressed_count",
    "privacy_suppressed_count",
    "low_confidence_suppressed_count",
    "missing_source_ref_count",
    "live_llm_call_count",
    "alias_text_publicly_serialized",
)


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _stage_rows(raw_hot_path: dict[str, Any]) -> list[dict[str, Any]]:
    stages: list[dict[str, Any]] = []
    for stage in raw_hot_path.get("stages") or []:
        if not isinstance(stage, dict):
            continue
        stages.append(
            {
                "stage": stage.get("stage"),
                "status": stage.get("status"),
                "candidate_count": stage.get("candidate_count"),
                "fallback_reason": stage.get("fallback_reason") or "",
                "elapsed_ms": stage.get("elapsed_ms"),
            }
        )
    return stages


def _packet_summary(packet: dict[str, Any], diagnostic_keys: tuple[str, ...]) -> dict[str, Any]:
    diagnostics = _dict(packet.get("diagnostics"))
    return {
        "decision": packet.get("decision"),
        "support_level": packet.get("support_level"),
        "selected_count": packet.get("selected_count", 0),
        "candidate_ref_count": len(packet.get("candidate_refs") or []),
        "diagnostics": {key: diagnostics.get(key, 0) for key in diagnostic_keys},
    }


def hot_path_debug_summary(raw_hot_path: Any) -> dict[str, Any] | None:
    if not isinstance(raw_hot_path, dict):
        return None
    payload = {
        "decision": raw_hot_path.get("decision"),
        "candidate_count": raw_hot_path.get("candidate_count"),
        "source_reopen_promotion_count": raw_hot_path.get(
            "source_reopen_promotion_count", 0
        ),
        "local_only": bool(raw_hot_path.get("local_only")),
        "elapsed_ms": raw_hot_path.get("elapsed_ms"),
        "stages": _stage_rows(raw_hot_path)[:6],
    }
    living = _dict(raw_hot_path.get("living_cue_cache"))
    if living:
        payload["living_cue_cache"] = _packet_summary(living, LIVING_CUE_DIAGNOSTIC_KEYS)
    query_patterns = _dict(raw_hot_path.get("query_pattern_routes"))
    if query_patterns:
        payload["query_pattern_routes"] = _packet_summary(
            query_patterns,
            QUERY_PATTERN_DIAGNOSTIC_KEYS,
        )
    return payload
