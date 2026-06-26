"""Exact source search over the route set from the same-machine last recall."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from aippocampus_runtime.source.last_recall_search_pipeline import (
    search_last_recall_sources,
)


def render_last_recall_search_result(result: Mapping[str, Any]) -> str:
    query = str(result.get("query_text") or "").strip() or "(empty query)"
    matches = list(result.get("matches") or [])
    if matches:
        lines = [
            "Last-recall source hits",
            "Exact snippets are receipts; deepen before quoting or making strong claims.",
            f"query: {query}",
        ]
        for index, match in enumerate(matches, start=1):
            line = match.get("line") or "unknown line"
            request = match.get("request_index") or "?"
            lines.append(f"{index}. request {request} · line {line}")
            if match.get("snippet"):
                lines.append(f"   {match.get('snippet')}")
            next_command = match.get("source_window_command") or match.get("deepen_command")
            if next_command:
                lines.append(f"   next: {next_command}")
        return "\n".join(lines)
    status = str(result.get("status") or "no_matches")
    lines = [
        f"No last-recall source hit ({status}).",
        f"query: {query}",
    ]
    action = result.get("foreground_action")
    if isinstance(action, Mapping):
        command = action.get("command") or action.get("command_template")
        if command:
            lines.append(f"next: {command}")
    return "\n".join(lines)


def run_last_recall_search_cli(args: Any) -> int:
    result = search_last_recall_sources(
        list(args.patterns),
        cwd=args.cwd,
        last_recall_path=args.last_recall_path,
        recall_selector=args.recall_selector,
        request_index=args.request,
        limit=args.max,
        include_paths=bool(args.include_paths),
    )
    if args.json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(render_last_recall_search_result(result))
    if result.get("status") in {
        "cannot_verify",
        "partial_unavailable_no_matches",
        "routes_not_searchable",
    }:
        return 2
    return 0 if result.get("matches") else 1


__all__ = [
    "run_last_recall_search_cli",
    "render_last_recall_search_result",
    "search_last_recall_sources",
]
