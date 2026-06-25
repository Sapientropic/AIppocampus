"""MCP search_memory support for registry-wide source search/open."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from aippocampus_runtime.source.registry_search import (
    open_registry_source_window,
    search_registry_sources,
)


def _int_range(value: Any, *, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, parsed))


def registry_search_memory_payload(
    arguments: dict[str, Any],
    *,
    query: str,
    cwd: Path,
    registry_dir: str | Path | None,
    limit: int,
    include_paths: bool,
) -> dict[str, Any]:
    if arguments.get("open_source") or arguments.get("hit_index"):
        return open_registry_source_window(
            registry_dir=registry_dir,
            hit_index=(
                _int_range(arguments.get("hit_index"), default=0, minimum=0, maximum=25)
                or None
            ),
            source_ref_index=(
                _int_range(
                    arguments.get("source_ref_index"),
                    default=0,
                    minimum=0,
                    maximum=100,
                )
                or None
            ),
            use_last_search=bool(arguments.get("last_search") or arguments.get("hit_index")),
            thread_key=str(arguments.get("thread_key") or "") or None,
            message_id=str(arguments.get("message_id") or "") or None,
            line=(
                _int_range(arguments.get("line"), default=0, minimum=0, maximum=10_000_000)
                or None
            ),
            context_lines=_int_range(
                arguments.get("context_lines"),
                default=2,
                minimum=0,
                maximum=8,
            ),
            include_paths=include_paths,
        )
    return search_registry_sources(
        [query],
        registry_dir=registry_dir,
        limit=limit,
        include_paths=include_paths,
        search_budget=str(arguments.get("search_budget") or "default"),
        record_last_search=False,
        cwd=cwd,
    )


__all__ = ["registry_search_memory_payload"]
