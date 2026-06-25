"""Stable public facade for registry-wide source search."""

from __future__ import annotations

import json
from typing import Any

from aippocampus_runtime.source.registry_search_pipeline import (
    search_registry_sources,
)
from aippocampus_runtime.source.registry_source_window import (
    last_registry_search_cache_path,
    open_registry_source_window,
    write_last_registry_search_cache,
)


def add_registry_search_arguments(parser: Any) -> None:
    parser.add_argument(
        "--all",
        "--registry",
        action="store_true",
        dest="registry_search",
        help="Search registered clean-source/index entries across the local registry.",
    )
    parser.add_argument(
        "--registry-dir",
        default=None,
        help="Registry directory for --all. Defaults to the configured AIppocampus registry.",
    )
    parser.add_argument(
        "--search-budget",
        choices=("default", "deep"),
        default="default",
        help="Registry search budget for --all; deep is a local diagnostic mode.",
    )
    parser.add_argument(
        "--hit",
        type=int,
        help="Reopen a numbered registry-wide search hit from the same-machine last search cache.",
    )
    parser.add_argument(
        "--source-ref-index",
        type=int,
        help="With --hit --last-search, reopen a specific collapsed duplicate source ref.",
    )
    parser.add_argument(
        "--last-search",
        action="store_true",
        help="With --hit, use the same-machine last registry-wide search cache.",
    )
    parser.add_argument(
        "--open-source",
        action="store_true",
        help="Open a bounded source window for a registry-wide hit by thread/message/line.",
    )
    parser.add_argument("--thread-key", help="Thread key for --open-source.")
    parser.add_argument("--message-id", help="Message id for --open-source.")
    parser.add_argument("--line", type=int, help="Source line for --open-source.")
    parser.add_argument(
        "--context-lines",
        type=int,
        default=2,
        help="Source-window radius for --open-source.",
    )


def run_registry_search_cli(args: Any, render_human_search_result: Any) -> int:
    if getattr(args, "open_source", False) or getattr(args, "hit", None):
        result = open_registry_source_window(
            registry_dir=args.registry_dir,
            hit_index=args.hit,
            source_ref_index=args.source_ref_index,
            use_last_search=bool(args.last_search),
            thread_key=args.thread_key,
            message_id=args.message_id,
            line=args.line,
            context_lines=args.context_lines,
            include_paths=bool(args.include_paths),
        )
        if args.json_output:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(render_human_search_result(result))
        return 0 if result.get("ok") else 1
    result = search_registry_sources(
        list(args.patterns),
        registry_dir=args.registry_dir,
        limit=args.max,
        include_paths=bool(args.include_paths),
        search_budget=args.search_budget,
        record_last_search=True,
        cwd=getattr(args, "cwd", None),
    )
    if args.json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(render_human_search_result(result))
    return 0 if result["matches"] else 1


__all__ = [
    "add_registry_search_arguments",
    "last_registry_search_cache_path",
    "open_registry_source_window",
    "run_registry_search_cli",
    "search_registry_sources",
    "write_last_registry_search_cache",
]
