"""Stable public facade for registry-wide source search."""

from __future__ import annotations

# aippocampus-instruction-surface: registry search CLI facade; public source-open
# output must omit local selectors and source text.
import json
from typing import Any

from aippocampus_runtime.contracts import canonical_foreground_action_fields
from aippocampus_runtime.foreground_compact_language import strip_compact_policy_vocabulary
from aippocampus_runtime.source.registry_search_pipeline import (
    search_registry_sources,
)
from aippocampus_runtime.source.registry_source_window import (
    last_registry_search_cache_path,
    open_registry_source_window,
    write_last_registry_search_cache,
)


def _public_registry_source_window_result(result: dict[str, Any]) -> dict[str, Any]:
    ok = bool(result.get("ok"))
    raw_metrics = result.get("metrics")
    metrics: dict[str, Any] = dict(raw_metrics) if isinstance(raw_metrics, dict) else {}
    action = {
        "id": "rerun_registry_search_locally",
        "label": "Rerun registry search locally",
        "command_template": 'aippocampus search --all "{query}" --json',
        "requires": ["query"],
        "mutation_risk": "read_only",
        "template_only": True,
        "why": (
            "Public source-open output omits local selectors and source text; "
            "rerun the original cue locally to reopen evidence."
        ),
    }
    payload: dict[str, Any] = {
        "kind": "aippocampus_registry_source_public_receipt",
        "ok": ok,
        "status": "source_text_omitted_public_mode" if ok else str(result.get("status") or "error"),
        "public_output": True,
        "summary": (
            "Selected source opened locally, but source text and local reopen selectors are omitted "
            "from public output."
            if ok
            else "Source window could not be opened; local selectors are omitted from public output."
        ),
        "source_text_omitted": True,
        "source_refs_omitted": True,
        "raw_source_snippets_emitted": False,
        "local_reopen_refs_emitted": False,
        "opened_source_summary": (
            {
                "message_count": int(metrics.get("window_message_count") or 0),
                "context_lines": int(metrics.get("context_lines") or 0),
            }
            if ok
            else None
        ),
    }
    payload.update(canonical_foreground_action_fields(action))
    return strip_compact_policy_vocabulary(payload)


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
        "--max-elapsed-ms",
        type=int,
        default=5000,
        help=(
            "Wall-clock budget for --all foreground search. Use 0 for an "
            "explicit unbounded local diagnostic run."
        ),
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
        if bool(getattr(args, "metadata_only", False)):
            result = _public_registry_source_window_result(result)
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
        detail=getattr(args, "detail", "compact"),
        public_output=bool(getattr(args, "metadata_only", False)),
        record_last_search=True,
        cwd=getattr(args, "cwd", None),
        max_elapsed_ms=args.max_elapsed_ms,
    )
    if args.json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(render_human_search_result(result))
    return 0 if result.get("ok") else 1


__all__ = [
    "add_registry_search_arguments",
    "last_registry_search_cache_path",
    "open_registry_source_window",
    "run_registry_search_cli",
    "search_registry_sources",
    "write_last_registry_search_cache",
]
