#!/usr/bin/env python3
"""Shared side effects after agent recall deepen opens source."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from aippocampus_runtime.recall import semantic_cue_cache
from aippocampus_runtime.recall.agent_recall_cache import (
    mark_last_recall_request_opened,
    query_from_last_recall_cache,
    read_last_recall_cache,
)
from aippocampus_runtime.recall.semantic import cue_learning as semantic_cue_learning


def _request_route_id_from_cache(
    request_index: int | None,
    path: str | Path | None,
) -> str:
    if request_index is None:
        return ""
    try:
        cache = read_last_recall_cache(path)
    except (OSError, ValueError, json.JSONDecodeError):
        return ""
    for request in cache.get("requests") or []:
        if not isinstance(request, Mapping):
            continue
        try:
            index = int(request.get("request_index") or 0)
        except (TypeError, ValueError):
            index = 0
        if index == int(request_index):
            return str(request.get("route_id") or "").strip()
    return ""


def _deepen_source_refs(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    result = payload.get("result")
    if isinstance(result, Mapping) and isinstance(result.get("source_refs"), list):
        return [dict(ref) for ref in result.get("source_refs") or [] if isinstance(ref, Mapping)]
    if isinstance(payload.get("source_refs"), list):
        return [dict(ref) for ref in payload.get("source_refs") or [] if isinstance(ref, Mapping)]
    return []


def record_successful_recall_cue_alias(
    payload: Mapping[str, Any],
    *,
    cached_context: Mapping[str, Any],
    selector_cache_path: str | Path | None,
    request_index: int | None,
    registry_dir: str | Path | None = None,
    explicit_useful: bool = False,
) -> dict[str, Any]:
    """Learn a last-recall cue only after the selected route opened source."""

    query = (
        str(cached_context.get("query") or "").strip()
        or query_from_last_recall_cache(selector_cache_path)
        or ""
    )
    refs = _deepen_source_refs(payload)
    result = payload.get("result")
    route_id = ""
    if isinstance(result, Mapping):
        route_id = str(result.get("route_id") or "").strip()
    route_id = route_id or _request_route_id_from_cache(request_index, selector_cache_path)
    registry_root = registry_dir or cached_context.get("registry_dir")
    path = semantic_cue_cache.default_semantic_cues_path(
        registry_dir=Path(registry_root) if registry_root else None
    )
    return semantic_cue_learning.promote_recall_cue_after_source_open(
        path,
        query=query,
        source_refs=refs,
        route_id=route_id,
        explicit_useful=explicit_useful,
    )


def record_source_open_recall_side_effects(
    payload: dict[str, Any],
    *,
    cached_context: Mapping[str, Any],
    selector_cache_path: str | Path | None,
    request_index: int | None,
    registry_dir: str | Path | None = None,
    detail: str = "compact",
    surface: str = "cli",
    learning_detail_modes: set[str] | None = None,
) -> None:
    if request_index is None or payload.get("status") != "ok":
        return
    try:
        mark_last_recall_request_opened(request_index, path=selector_cache_path, outcome="source_open")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        payload.setdefault("detail_warnings", []).append(_marker_warning(exc, surface=surface))
    try:
        cue_learning = record_successful_recall_cue_alias(
            payload,
            cached_context=cached_context,
            selector_cache_path=selector_cache_path,
            request_index=request_index,
            registry_dir=registry_dir,
        )
        if detail in (learning_detail_modes or {"detail", "full", "operator"}):
            payload["recall_cue_learning"] = {
                "updated_count": cue_learning.get("updated_count", 0),
                "active_count": cue_learning.get("active_count", 0),
                "output_boundary": "detail_only_counts_no_raw_prompt",
            }
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        payload.setdefault("detail_warnings", []).append(_learning_warning(exc, surface=surface))


def _marker_warning(exc: Exception, *, surface: str) -> dict[str, str]:
    if surface == "mcp":
        return {
            "code": "last_recall_open_receipt_not_marked",
            "message": "source opened, but the local selector cache receipt was not updated",
            "error_type": type(exc).__name__,
        }
    return {
        "code": "last_recall_opened_marker_unavailable",
        "error_code": type(exc).__name__,
        "recovery": "source_open_succeeded_marker_not_written",
        "claim_boundary": "detail_only_cache_diagnostic",
    }


def _learning_warning(exc: Exception, *, surface: str) -> dict[str, str]:
    if surface == "mcp":
        return {
            "code": "recall_cue_learning_unavailable",
            "message": "source opened, but the recall cue alias was not learned",
            "error_type": type(exc).__name__,
        }
    return {
        "code": "recall_cue_learning_unavailable",
        "error_code": type(exc).__name__,
        "recovery": "source_open_succeeded_alias_not_learned",
        "claim_boundary": "detail_only_learning_diagnostic",
    }
