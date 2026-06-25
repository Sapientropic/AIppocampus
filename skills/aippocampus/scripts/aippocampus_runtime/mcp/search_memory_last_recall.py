"""MCP search_memory support for last-recall scoped search/open."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from aippocampus_runtime.source.last_recall_search import search_last_recall_sources
from aippocampus_runtime.source.last_recall_source_window import open_last_recall_source_window


def _int_range(value: Any, *, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, parsed))


def last_recall_search_memory_payload(
    arguments: dict[str, Any],
    *,
    query: str,
    cwd: Path,
    limit: int,
    include_paths: bool,
) -> dict[str, Any]:
    request_index = (
        _int_range(arguments.get("request_index"), default=0, minimum=0, maximum=25)
        if arguments.get("request_index") is not None
        else None
    )
    if arguments.get("open_source"):
        line_value = (
            _int_range(arguments.get("line"), default=0, minimum=0, maximum=10_000_000)
            if arguments.get("line") is not None
            else None
        )
        return open_last_recall_source_window(
            cwd=cwd,
            last_recall_path=arguments.get("last_recall_path"),
            recall_selector=arguments.get("recall_selector"),
            request_index=request_index or None,
            message_id=str(arguments.get("message_id") or "") or None,
            line=line_value or None,
            context_lines=_int_range(
                arguments.get("context_lines"),
                default=2,
                minimum=0,
                maximum=8,
            ),
            include_paths=include_paths,
            query_text=query,
        )
    return search_last_recall_sources(
        [query],
        cwd=cwd,
        last_recall_path=arguments.get("last_recall_path"),
        recall_selector=arguments.get("recall_selector"),
        request_index=request_index or None,
        limit=limit,
        include_paths=include_paths,
    )


__all__ = ["last_recall_search_memory_payload"]
