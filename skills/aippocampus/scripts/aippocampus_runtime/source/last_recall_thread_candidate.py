"""Thread-candidate helpers for last-recall scoped source search."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from aippocampus_runtime.mcp.recall_navigation import RecallNavigationError
from aippocampus_runtime.source.registry_source_routes import (
    registry_clean_source_route,
)
from aippocampus_runtime.source.registry_source_routes import (
    registry_source_window_command as _registry_source_window_command,
)


def _handle_mapping(handle: Any) -> dict[str, Any] | None:
    current = handle
    if isinstance(current, Mapping) and current.get("kind") == "recall_context_seed":
        current = current.get("handle")
    if isinstance(current, str):
        text = current.strip()
        if not text.startswith("{"):
            return None
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return None
        current = parsed
    return dict(current) if isinstance(current, Mapping) else None


def thread_candidate_search_refs(
    handle: Any,
) -> tuple[dict[str, Any], list[dict[str, Any]]] | None:
    """Resolve a thread-candidate hint only for scoped search.

    `thread_candidate` is deliberately not a source-open/deepen handle: a
    foreground agent cannot make claims from it and `agent deepen` rejects it.
    Last-recall exact search may still use the cached thread key to search that
    thread's registered clean source and emit a source-window command for hits.
    """

    current = _handle_mapping(handle)
    if not current or str(current.get("kind") or "") != "thread_candidate":
        return None
    thread_key = str(current.get("thread_key") or "").strip()
    if not thread_key:
        raise RecallNavigationError(
            "malformed_recall_handle",
            "thread candidate handles require thread_key.",
        )
    source_refs: list[dict[str, Any]] = [{"thread_key": thread_key}]
    normalized: dict[str, Any] = {
        "schema_version": current.get("schema_version") or 1,
        "kind": "thread_candidate",
        "route_id": current.get("route_id") or f"thread_candidate:{thread_key}",
        "thread_key": thread_key,
        "source_refs": source_refs,
        "source_search_only": True,
    }
    return normalized, source_refs


def registry_source_window_command(ref: Mapping[str, Any], match: Mapping[str, Any]) -> str:
    thread_key = str(ref.get("thread_key") or "").strip()
    if not thread_key:
        return ""
    return _registry_source_window_command(
        registry_clean_source_route(
            thread_key=thread_key,
            message_id=str(match.get("message_id") or match.get("id") or ""),
            line=match.get("source_line") or match.get("line"),
            boundary="open_registry_source_window_before_quoting_or_strong_claims",
        )
    )


__all__ = ["registry_source_window_command", "thread_candidate_search_refs"]
