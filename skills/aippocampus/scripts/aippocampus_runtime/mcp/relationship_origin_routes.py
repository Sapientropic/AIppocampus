"""MCP route builder for the narrow relationship-origin recall lane."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from aippocampus_runtime.mcp.registry_source_routes import (
    route_from_registry_match,
    route_from_source_ref,
    source_ref_exists,
)
from aippocampus_runtime.registry.api import RegistryReadError
from aippocampus_runtime.source.registry_search import search_registry_sources
from aippocampus_runtime.source.relationship_origin import (
    RELATIONSHIP_ORIGIN_ROUTE_TOPIC,
    canonical_origin_doc_intent,
    relationship_origin_intent,
    relationship_origin_search_patterns,
)

CleanRef = Callable[[dict[str, Any]], dict[str, Any]]
RouteHandle = Callable[..., str]
StableId = Callable[..., str]
SafeText = Callable[[Any, int], str]

ORIGIN_SOURCE_CHAIN_REFS: tuple[dict[str, Any], ...] = (
    {
        "thread_key": "session:019e6071-5a9b-71d2-b15a-27f6ba211494",
        "message_id": "msg_ea1e9e5ea23db0e8519e",
        "line": 6726,
        "source_chain_role": "canonical_doc",
        "title": "relationship origin canonical essay handoff source",
        "summary": (
            "Source-chain route for the canonical origin essay handoff that "
            "kept the origin narrative in The Unfinished Map."
        ),
        "query_cues": (
            "未干的地图",
            "origin",
            "essay",
            "unfinished",
            "the-unfinished-map",
            "source-backed",
            "continuity",
            "初心",
            "文档",
        ),
    },
    {
        "thread_key": "session:019e5aea-a7ea-78f1-bb9c-b51df0837343",
        "message_id": "msg_b2dfe27431403cdc8ffa",
        "line": 88,
        "source_chain_role": "original_mechanical_ascension_source",
        "title": "relationship origin original mechanical-ascension source",
        "summary": "Original 2026-05-24 source-chain route for the mechanical ascension discussion.",
        "query_cues": ("机械", "飞升", "机仆", "种族", "知乎"),
    },
    {
        "thread_key": "session:019e5aea-a7ea-78f1-bb9c-b51df0837343",
        "message_id": "msg_c1d289e0359648aa0194",
        "line": 455,
        "source_chain_role": "original_external_hippocampus_design",
        "title": "relationship origin external-hippocampus design source",
        "summary": "Original source-chain route for thread-memory-index / external hippocampus design.",
        "query_cues": ("小海马体", "外置", "海马体", "thread-memory-index", "记忆"),
    },
    {
        "thread_key": "session:019e6071-5a9b-71d2-b15a-27f6ba211494",
        "message_id": "msg_770bba9190f4ab7b1281",
        "line": 6494,
        "source_chain_role": "origin_reflection",
        "title": "relationship origin user reconstruction source",
        "summary": "Source-chain route for the user's origin-story reconstruction.",
        "query_cues": ("初心", "源头", "关系", "连续", "故事"),
    },
)


def _origin_chain_priority(intent: str, row: Mapping[str, Any]) -> tuple[int, str]:
    text = intent.casefold()
    cues = [str(cue).casefold() for cue in row.get("query_cues") or []]
    cue_match_count = sum(1 for cue in cues if cue and cue in text)
    cue_hit = cue_match_count > 0
    role = str(row.get("source_chain_role") or "")
    strength = f"{999 - min(cue_match_count, 999):03d}"
    if canonical_origin_doc_intent(intent):
        if cue_hit and role == "canonical_doc":
            return (0, strength + role)
        if role == "canonical_doc":
            return (1, strength + role)
        if cue_hit:
            return (2, strength + role)
        if role.startswith("original_"):
            return (3, strength + role)
        return (4, strength + role)
    if cue_hit and role.startswith("original_"):
        return (0, strength + role)
    if cue_hit:
        return (1, strength + role)
    if role.startswith("original_"):
        return (2, strength + role)
    return (3, strength + role)


def relationship_origin_source_chain_routes(
    *,
    intent: str,
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
    rows = sorted(ORIGIN_SOURCE_CHAIN_REFS, key=lambda row: _origin_chain_priority(intent, row))
    routes: list[dict[str, Any]] = []
    for row in rows:
        ref = {
            key: row[key]
            for key in ("thread_key", "message_id", "line")
            if key in row
        }
        if not source_ref_exists(ref, clean_source_dir=source_dir, registry_dir=registry_dir):
            continue
        role = str(row.get("source_chain_role") or "relationship_origin_source")
        route = route_from_source_ref(
            ref,
            source_dir=source_dir,
            clean_ref=clean_ref,
            route_handle=route_handle,
            stable_id=stable_id,
            safe_text=safe_text,
            route_id_prefix="relationship_origin_source_chain",
            title=row.get("title") or "relationship origin source chain",
            summary=row.get("summary") or "",
            scope_labels=["relationship_continuity", "source_chain"],
            scope_bucket="relationship_continuity",
            matched_cue_family="relationship_origin",
            route_topic=RELATIONSHIP_ORIGIN_ROUTE_TOPIC,
            route_label=f"relationship_origin {role} route",
            reason_codes=[
                "relationship_origin_source_chain",
                role,
                "registry_clean_source_reopenable",
                "source_reopen_required",
            ],
            source_chain_role=role,
        )
        if route:
            route["why_this_may_matter"] = (
                "This is part of the original relationship-origin source chain; "
                "deepen it before using details."
            )
            routes.append(route)
            if len(routes) >= max_routes:
                break
    return routes


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
    except (OSError, ValueError, RegistryReadError):
        return []
    routes: list[dict[str, Any]] = []
    seen: set[str] = set()
    for match in payload.get("matches") or []:
        if not isinstance(match, Mapping):
            continue
        route = route_from_registry_match(
            match,
            source_dir=source_dir,
            registry_dir=registry_dir,
            clean_ref=clean_ref,
            route_handle=route_handle,
            stable_id=stable_id,
            safe_text=safe_text,
            route_id_prefix="relationship_origin",
            route_topic=RELATIONSHIP_ORIGIN_ROUTE_TOPIC,
            matched_cue_family="relationship_origin",
            route_label="relationship_origin recap/orientation route",
            reason_codes=[
                "relationship_origin_lane",
                "registry_clean_source_reopenable",
                "source_reopen_required",
            ],
            source_chain_role="recap_orientation",
        )
        if route is None:
            continue
        route["scope_bucket"] = "relationship_continuity"
        route["why_this_may_matter"] = (
            "This route matches the little-hippocampus / relationship-continuity "
            "origin lane; treat it as recap/orientation unless the source itself "
            "proves it is original."
        )
        ref = route["source_refs"][0]
        key = "|".join(str(ref.get(part) or "") for part in ("thread_key", "message_id", "line"))
        if key in seen:
            continue
        seen.add(key)
        routes.append(route)
        if len(routes) >= max_routes:
            break
    return routes


__all__ = [
    "relationship_origin_registry_routes",
    "relationship_origin_source_chain_routes",
]
