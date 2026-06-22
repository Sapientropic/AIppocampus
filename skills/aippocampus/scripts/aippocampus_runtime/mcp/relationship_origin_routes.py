"""MCP route builder for the narrow relationship-origin recall lane."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from aippocampus_runtime.source.registry_search import search_registry_sources
from aippocampus_runtime.source.relationship_origin import (
    RELATIONSHIP_ORIGIN_ROUTE_TOPIC,
    relationship_origin_intent,
    relationship_origin_search_patterns,
)

CleanRef = Callable[[dict[str, Any]], dict[str, Any]]
RouteHandle = Callable[..., str]
StableId = Callable[..., str]
SafeText = Callable[[Any, int], str]


def _source_ref_from_registry_match(
    match: Mapping[str, Any],
    *,
    clean_ref: CleanRef,
) -> dict[str, Any]:
    raw_route = match.get("source_route")
    route = raw_route if isinstance(raw_route, Mapping) else {}
    if route.get("kind") != "registry_clean_source_hit":
        return {}
    thread = match.get("thread")
    thread_map = thread if isinstance(thread, Mapping) else {}
    ref = {
        "thread_key": route.get("thread_key") or thread_map.get("thread_key"),
        "message_id": route.get("message_id") or match.get("message_id"),
        "turn_id": match.get("turn_id"),
        "turn_index": match.get("turn_index"),
        "line": route.get("line") or match.get("line"),
        "phase": match.get("phase") or "",
    }
    clean = clean_ref({key: value for key, value in ref.items() if value not in (None, "")})
    if not clean.get("thread_key"):
        return {}
    if not any(clean.get(key) for key in ("message_id", "turn_id", "turn_index", "line")):
        return {}
    return clean


def _route_from_registry_match(
    match: Mapping[str, Any],
    *,
    source_dir: Path,
    clean_ref: CleanRef,
    route_handle: RouteHandle,
    stable_id: StableId,
    safe_text: SafeText,
) -> dict[str, Any] | None:
    source_ref = _source_ref_from_registry_match(match, clean_ref=clean_ref)
    if not source_ref:
        return None
    route_id = stable_id("relationship_origin", source_ref, match.get("hit_selector"))
    handle = route_handle(
        source_dir=source_dir,
        route_id=route_id,
        source_refs=[source_ref],
        evidence_level="needs_reopen",
    )
    scope_labels = [
        str(label)
        for label in [*(match.get("scope_labels") or []), *(match.get("semantic_scope_labels") or [])]
        if isinstance(label, str)
    ]
    thread = match.get("thread")
    thread_map = thread if isinstance(thread, Mapping) else {}
    title = thread_map.get("title") or thread_map.get("thread_key") or "relationship origin route"
    return {
        "handle": handle,
        "route_id": route_id,
        "kind": "source_window",
        "title": safe_text(title, 90),
        "summary": safe_text(match.get("snippet"), 220),
        "evidence_level": "needs_reopen",
        "support_level": "navigation",
        "source_refs": [source_ref],
        "scope_labels": list(dict.fromkeys(scope_labels))[:8],
        "scope_bucket": "relationship_continuity",
        "matched_cue_family": "relationship_origin",
        "route_topic": RELATIONSHIP_ORIGIN_ROUTE_TOPIC,
        "label_granularity": "topic_label",
        "route_label_specificity_score": 1.0,
        "route_label": "relationship_origin route",
        "triage_rank_reason_codes": [
            "relationship_origin_lane",
            "registry_clean_source_reopenable",
            "source_reopen_required",
        ],
        "reopenable": True,
        "why_this_may_matter": (
            "This route matches the little-hippocampus / relationship-continuity "
            "origin lane; reopen it before using details."
        ),
        "suggested_next": {
            "tool": "recall_deepen",
            "arguments": {"handle": handle},
        },
        "source_reopen_path": {
            "tool": "get_turn_context",
            "arguments": {
                key: source_ref[key]
                for key in ("thread_key", "message_id", "turn_id", "turn_index")
                if key in source_ref
            },
        },
    }


def relationship_origin_registry_routes(
    *,
    intent: str,
    cwd: Path,
    source_dir: Path,
    registry_dir: Path | None,
    max_routes: int,
    clean_ref: CleanRef,
    route_handle: RouteHandle,
    stable_id: StableId,
    safe_text: SafeText,
) -> list[dict[str, Any]]:
    if not relationship_origin_intent(intent) or registry_dir is None:
        return []
    try:
        payload = search_registry_sources(
            relationship_origin_search_patterns(intent),
            registry_dir=registry_dir,
            limit=max(1, min(3, max_routes)),
            per_thread_limit=2,
            cwd=cwd,
        )
    except Exception:
        return []
    routes: list[dict[str, Any]] = []
    seen: set[str] = set()
    for match in payload.get("matches") or []:
        if not isinstance(match, Mapping):
            continue
        route = _route_from_registry_match(
            match,
            source_dir=source_dir,
            clean_ref=clean_ref,
            route_handle=route_handle,
            stable_id=stable_id,
            safe_text=safe_text,
        )
        if route is None:
            continue
        ref = route["source_refs"][0]
        key = "|".join(str(ref.get(part) or "") for part in ("thread_key", "message_id", "line"))
        if key in seen:
            continue
        seen.add(key)
        routes.append(route)
        if len(routes) >= max_routes:
            break
    return routes


__all__ = ["relationship_origin_registry_routes"]
