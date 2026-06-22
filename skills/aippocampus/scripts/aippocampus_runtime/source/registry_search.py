"""Foreground-safe registry-wide source search projection."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from aippocampus_runtime.contracts import (
    canonical_foreground_action_fields,
    shell_quote,
)
from aippocampus_runtime.core import compact_text, stable_text_fingerprint
from aippocampus_runtime.privacy import (
    LOCAL_PATH_REDACTION,
    redact_private_paths,
    redact_sensitive_values,
)
from aippocampus_runtime.source.discussion_atlas_pointer import (
    discussion_atlas_action,
    discussion_atlas_pointer_for_query,
)
from aippocampus_runtime.source.query_match_gate import (
    match_query_profile,
    query_match_gate,
)
from aippocampus_runtime.source.registry_search_actions import registry_search_actions
from aippocampus_runtime.source.registry_search_duplicates import (
    collapse_duplicate_matches,
    compact_registry_match,
    match_haystack,
    process_noise_reason,
)
from aippocampus_runtime.source.registry_search_skips import (
    registry_entry_ref,
    registry_entry_search_skip,
    skipped_maintenance_actions,
)
from aippocampus_runtime.source.registry_source_window import (
    last_registry_search_cache_path,
    open_registry_source_window,
    write_last_registry_search_cache,
)
from aippocampus_runtime.source.repo_doc_search import repo_checkout_doc_matches
from aippocampus_runtime.source.search_terms import search_query_terms

DEFAULT_PUBLIC_SNIPPET_CHARS = 260


def _without_empty(value: Mapping[str, Any]) -> dict[str, Any]:
    return {key: item for key, item in value.items() if item not in (None, "", {})}


def as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


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


def _hit_selector(route: Mapping[str, Any]) -> str:
    return stable_text_fingerprint(
        json.dumps(route, ensure_ascii=False, sort_keys=True, default=str),
        namespace="registry-search-hit-selector",
        prefix="srchit",
        length=18,
    )


def _registry_match(
    *,
    entry: Mapping[str, Any],
    hit: Mapping[str, Any],
    include_paths: bool,
) -> dict[str, Any]:
    raw_paths = entry.get("paths")
    paths: Mapping[str, Any] = raw_paths if isinstance(raw_paths, Mapping) else {}
    thread_key = str(entry.get("thread_key") or "").strip()
    source_route = {
        "kind": "registry_clean_source_hit",
        "thread_key": thread_key,
        "line": hit.get("line"),
        "message_id": hit.get("message_id") or hit.get("id"),
        "boundary": "reopen_source_before_quoting_or_strong_claims",
    }
    snippet = compact_text(str(hit.get("snippet") or ""), DEFAULT_PUBLIC_SNIPPET_CHARS)
    noise_reason = str(hit.get("noise_reason") or "") or process_noise_reason(snippet)
    match = {
        "hit_selector": _hit_selector(source_route),
        "thread": registry_entry_ref(entry),
        "source": hit.get("source"),
        "message_id": hit.get("message_id") or hit.get("id"),
        "turn_id": hit.get("turn_id"),
        "line": hit.get("line"),
        "role": hit.get("role"),
        "phase": hit.get("phase") or "",
        "turn_index": hit.get("turn_index"),
        "is_final": bool(hit.get("is_final")),
        "scope_labels": hit.get("scope_labels") or [],
        "semantic_scope_labels": hit.get("semantic_scope_labels") or [],
        "score": hit.get("rank_score") or hit.get("score"),
        "snippet": snippet,
        "search_noise": bool(hit.get("search_noise")) or bool(noise_reason),
        "noise_reason": noise_reason,
        "source_route": source_route,
    }
    if include_paths:
        match["local_diagnostic"] = {
            "workspace": paths.get("workspace"),
            "clean_source_messages_jsonl": paths.get("clean_source_messages_jsonl"),
            "sqlite": paths.get("sqlite"),
        }
    return {key: value for key, value in match.items() if value not in (None, "", [], {})}


def _annotate_last_search_reopen_commands(
    matches: list[dict[str, Any]],
    *,
    registry_dir: str | Path | None,
    include_paths: bool,
) -> None:
    registry_arg = ""
    if include_paths and registry_dir:
        registry_arg = f" --registry-dir {shell_quote(str(Path(registry_dir).resolve()))}"
    for index, match in enumerate(matches, start=1):
        raw_route = match.get("source_route")
        route: Mapping[str, Any] = raw_route if isinstance(raw_route, Mapping) else {}
        if route.get("kind") == "repo_checkout_doc_hit":
            command = str(match.get("source_window_command") or match.get("reopen_command") or "").strip()
            match["hit_index"] = index
            if command:
                match["reopen_command"] = command
                match["source_window_command"] = command
                match["last_search_reopen_command"] = command
            continue
        thread_key = str(route.get("thread_key") or "")
        message_id = str(route.get("message_id") or "")
        line = route.get("line")
        line_arg = ""
        if line is not None and str(line).isdigit():
            line_arg = f"--line {int(str(line))}"
        direct_parts = [
            "aippocampus search --open-source",
            f"--thread-key {shell_quote(thread_key)}" if thread_key else "",
            f"--message-id {shell_quote(message_id)}" if message_id else "",
            line_arg,
            registry_arg.strip(),
            "--json",
        ]
        source_window_command = " ".join(part for part in direct_parts if part)
        match["hit_index"] = index
        match["reopen_command"] = source_window_command
        match["source_window_command"] = source_window_command
        match["last_search_reopen_command"] = f"aippocampus search --hit {index} --last-search --json"


def search_registry_sources(
    patterns: list[str],
    *,
    registry_dir: str | Path | None = None,
    limit: int = 10,
    per_thread_limit: int = 3,
    include_paths: bool = False,
    search_budget: str = "default",
    record_last_search: bool = False,
    cwd: str | Path | None = None,
) -> dict[str, Any]:
    """Search registered clean-source/index entries without exposing raw paths by default."""

    from aippocampus_runtime.registry.search import (
        REGISTRY_SEARCH_DEEP_BUDGET,
        deep_search_entry_result,
    )
    from aippocampus_runtime.registry.store import load_registry, registry_paths

    registry_root = Path(registry_dir).resolve() if registry_dir else None
    registry_json, _ = registry_paths(registry_root)
    registry_payload = load_registry(registry_json)
    query_text = " ".join(str(pattern) for pattern in patterns).strip()
    terms = search_query_terms(patterns)
    query_gate = query_match_gate(query_text)
    budget = REGISTRY_SEARCH_DEEP_BUDGET if search_budget == "deep" else None
    matches: list[dict[str, Any]] = []
    suppressed_matches: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    searched_entry_count = 0
    skipped_entries: list[dict[str, Any]] = []
    skipped_reason_counts: dict[str, int] = {}
    unavailable_source_count = 0
    repo_doc_matches = repo_checkout_doc_matches(
        cwd=cwd or Path.cwd(),
        query_text=query_text,
        query_gate=query_gate,
        limit=limit,
        snippet_chars=DEFAULT_PUBLIC_SNIPPET_CHARS,
    )
    matches.extend(repo_doc_matches)

    for entry in registry_payload.get("threads") or []:
        if not isinstance(entry, Mapping):
            continue
        searched_entry_count += 1
        skip = registry_entry_search_skip(entry)
        if skip:
            skipped_entries.append(skip)
            reason = str(skip.get("reason") or "not_searchable")
            skipped_reason_counts[reason] = skipped_reason_counts.get(reason, 0) + 1
            if reason == "configured_search_sources_missing":
                unavailable_source_count += 1
            continue
        result = deep_search_entry_result(
            dict(entry),
            terms,
            max_hits=per_thread_limit,
            search_budget=budget,
        )
        entry_warnings = []
        for warning in result.get("warnings") or []:
            item = dict(warning) if isinstance(warning, Mapping) else {"message": str(warning)}
            item["thread_key"] = entry.get("thread_key")
            entry_warnings.append(item)
        if entry_warnings:
            warnings.extend(entry_warnings)
            unavailable_source_count += 1
        for hit in result.get("hits") or []:
            if isinstance(hit, Mapping):
                match = _registry_match(
                    entry=entry,
                    hit=hit,
                    include_paths=include_paths,
                )
                profile = match_query_profile(
                    query_text=query_text,
                    gate=query_gate,
                    haystack=match_haystack(match),
                )
                match["query_match_profile"] = profile
                if profile["accepted"]:
                    matches.append(match)
                else:
                    suppressed_matches.append(
                        {
                            "thread": match.get("thread"),
                            "score": match.get("score"),
                            "query_match_profile": profile,
                            "source": match.get("source"),
                            "line": match.get("line"),
                        }
                    )

    matches.sort(
        key=lambda item: (
            1 if item.get("search_noise") else 0,
            -as_float(item.get("score")),
            str((item.get("thread") or {}).get("thread_key") or ""),
            as_int(item.get("line")),
        )
    )
    matches, duplicate_metrics = collapse_duplicate_matches(matches, limit=limit)
    _annotate_last_search_reopen_commands(
        matches,
        registry_dir=registry_root,
        include_paths=include_paths,
    )
    if record_last_search:
        write_last_registry_search_cache(
            registry_dir=registry_root,
            query_text=query_text,
            matches=matches,
        )
    discussion_pointer = discussion_atlas_pointer_for_query(
        query_text,
        cwd=registry_root or Path.cwd(),
    )
    discussion_action = discussion_atlas_action(discussion_pointer, query=query_text)
    actions = registry_search_actions(
        query=query_text,
        has_matches=bool(matches),
        first_match=matches[0] if matches else None,
    )
    if discussion_action:
        actions = [discussion_action, *actions]
    no_phrase_like_matches = bool(query_gate.get("phrase_like_query")) and not matches and bool(suppressed_matches)
    diagnostic_output = include_paths or search_budget == "deep"
    output_matches = matches if diagnostic_output else [compact_registry_match(match) for match in matches]
    payload: dict[str, Any] = _without_empty({
        "kind": "aippocampus_registry_source_search",
        "ok": bool(matches),
        "status": "ok" if matches else "no_phrase_like_matches" if no_phrase_like_matches else "no_matches",
        "search_scope": "registered_clean_source_and_indexes",
        "scope_description": (
            "registered clean-source/index entries across the local registry; "
            "a miss is not proof that no memory exists"
        ),
        "registry": str(registry_json),
        "query_text": query_text,
        "query_terms": terms if diagnostic_output else None,
        "query_match_gate": query_gate if diagnostic_output else None,
        "matches": output_matches,
        "match_count": len(matches),
        "duplicate_cluster_count": duplicate_metrics["duplicate_cluster_count"],
        "duplicate_collapsed_hit_count": duplicate_metrics["duplicate_hit_count"],
        "repo_doc_match_count": len(repo_doc_matches),
        "discussion_atlas_pointer": discussion_pointer,
        "suppressed_low_coverage_match_count": len(suppressed_matches),
        "suppressed_low_coverage_matches": suppressed_matches[:3] if diagnostic_output else None,
        "searched_entry_count": searched_entry_count,
        "skipped_entry_count": len(skipped_entries),
        "skipped_reason_counts": skipped_reason_counts or None,
        "skipped_entries": skipped_entries[:20] if diagnostic_output else None,
        "maintenance_actions": skipped_maintenance_actions(skipped_entries) or None,
        "unavailable_source_count": unavailable_source_count,
        "warnings": warnings,
        "diagnostic_fields_omitted": (
            [
                "query_terms",
                "query_match_gate",
                "matches[].score",
                "matches[].query_match_profile",
                "suppressed_low_coverage_matches",
                "skipped_entries",
            ]
            if not diagnostic_output
            else None
        ),
        "diagnostic_detail_command": (
            f"aippocampus search --all {shell_quote(query_text)} --search-budget deep --json"
            if not diagnostic_output and query_text
            else None
        ),
        "output_boundary": (
            "local_private_source_routes_with_paths"
            if include_paths
            else "foreground_safe_registry_source_routes"
        ),
        "source_boundary": {
            "authority": "bounded_evidence" if matches else "direction_only",
            "registry_wide_search": True,
            "source_backed_claim_allowed": bool(matches),
            "source_reopen_required_before_claim": True,
            "search_miss_is_not_absence_of_memory": not bool(matches),
            "phrase_like_low_coverage_suppressed": no_phrase_like_matches,
        },
        "privacy": {
            "paths_included": include_paths,
            "path_redaction": "none" if include_paths else LOCAL_PATH_REDACTION,
            "raw_source_snippets_emitted": False,
            "capped_source_snippets_emitted": bool(matches),
            "full_session_metadata_emitted": False,
            "last_search_cache_contains_paths": False,
        },
    })
    if actions:
        payload.update(
            canonical_foreground_action_fields(
                actions[0],
                safe_next_actions=actions,
            )
        )
    return payload if include_paths else redact_sensitive_values(redact_private_paths(payload))


def run_registry_search_cli(args: Any, render_human_search_result: Any) -> int:
    if getattr(args, "open_source", False) or getattr(args, "hit", None):
        result = open_registry_source_window(
            registry_dir=args.registry_dir,
            hit_index=args.hit,
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
