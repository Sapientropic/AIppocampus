"""Foreground-safe registry-wide source search projection."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from aippocampus_runtime.contracts import (
    canonical_foreground_action_fields,
    foreground_template_action,
    shell_quote,
)
from aippocampus_runtime.core import compact_text, stable_text_fingerprint
from aippocampus_runtime.privacy import (
    LOCAL_PATH_REDACTION,
    redact_private_paths,
    redact_sensitive_values,
)
from aippocampus_runtime.source.query_match_gate import (
    match_query_profile,
    query_match_gate,
)
from aippocampus_runtime.source.registry_search_actions import registry_search_actions
from aippocampus_runtime.source.search_terms import search_query_terms

DEFAULT_PUBLIC_SNIPPET_CHARS = 260
DEFAULT_SOURCE_WINDOW_CHARS = 700
LAST_SEARCH_CACHE_NAME = "last-registry-source-search.json"
COMPACT_MATCH_DIAGNOSTIC_KEYS = {"score", "query_match_profile"}


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


def last_registry_search_cache_path(registry_dir: str | Path | None = None) -> Path:
    from aippocampus_runtime.registry.store import registry_paths

    registry_root = Path(registry_dir).resolve() if registry_dir else None
    registry_json, _ = registry_paths(registry_root)
    return registry_json.parent / LAST_SEARCH_CACHE_NAME


def _hit_selector(route: Mapping[str, Any]) -> str:
    return stable_text_fingerprint(
        json.dumps(route, ensure_ascii=False, sort_keys=True, default=str),
        namespace="registry-search-hit-selector",
        prefix="srchit",
        length=18,
    )


def _registry_entry_ref(entry: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in {
            "thread_key": entry.get("thread_key"),
            "title": compact_text(str(entry.get("title") or ""), 90),
            "workspace_name": compact_text(str(entry.get("workspace_name") or ""), 90),
            "source_provider": entry.get("source_provider"),
        }.items()
        if value not in (None, "", [])
    }


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
    match = {
        "hit_selector": _hit_selector(source_route),
        "thread": _registry_entry_ref(entry),
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
        "snippet": compact_text(str(hit.get("snippet") or ""), DEFAULT_PUBLIC_SNIPPET_CHARS),
        "search_noise": bool(hit.get("search_noise")),
        "noise_reason": hit.get("noise_reason"),
        "source_route": source_route,
    }
    if include_paths:
        match["local_diagnostic"] = {
            "workspace": paths.get("workspace"),
            "clean_source_messages_jsonl": paths.get("clean_source_messages_jsonl"),
            "sqlite": paths.get("sqlite"),
        }
    return {key: value for key, value in match.items() if value not in (None, "", [], {})}


def _match_haystack(match: Mapping[str, Any]) -> str:
    thread = match.get("thread")
    thread_map = thread if isinstance(thread, Mapping) else {}
    return " ".join(
        str(value or "")
        for value in (
            match.get("snippet"),
            thread_map.get("title"),
            thread_map.get("workspace_name"),
            match.get("source"),
        )
    )


def _compact_registry_match(match: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in match.items()
        if key not in COMPACT_MATCH_DIAGNOSTIC_KEYS
    }


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
        match["hit_index"] = index
        match["reopen_command"] = f"aippocampus search --hit {index} --last-search --json"
        match["source_window_command"] = " ".join(part for part in direct_parts if part)


def search_registry_sources(
    patterns: list[str],
    *,
    registry_dir: str | Path | None = None,
    limit: int = 10,
    per_thread_limit: int = 3,
    include_paths: bool = False,
    search_budget: str = "default",
    record_last_search: bool = False,
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
    unavailable_source_count = 0

    for entry in registry_payload.get("threads") or []:
        if not isinstance(entry, Mapping):
            continue
        searched_entry_count += 1
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
                    haystack=_match_haystack(match),
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
    matches = matches[:limit]
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
    actions = registry_search_actions(
        query=query_text,
        has_matches=bool(matches),
        first_match=matches[0] if matches else None,
    )
    no_phrase_like_matches = bool(query_gate.get("phrase_like_query")) and not matches and bool(suppressed_matches)
    diagnostic_output = include_paths or search_budget == "deep"
    output_matches = matches if diagnostic_output else [_compact_registry_match(match) for match in matches]
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
        "suppressed_low_coverage_match_count": len(suppressed_matches),
        "suppressed_low_coverage_matches": suppressed_matches[:3] if diagnostic_output else None,
        "searched_entry_count": searched_entry_count,
        "unavailable_source_count": unavailable_source_count,
        "warnings": warnings,
        "diagnostic_fields_omitted": (
            [
                "query_terms",
                "query_match_gate",
                "matches[].score",
                "matches[].query_match_profile",
                "suppressed_low_coverage_matches",
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


def write_last_registry_search_cache(
    *,
    registry_dir: str | Path | None,
    query_text: str,
    matches: Sequence[Mapping[str, Any]],
) -> Path:
    path = last_registry_search_cache_path(registry_dir)
    cache_matches = []
    for match in matches:
        raw_route = match.get("source_route")
        route: Mapping[str, Any] = raw_route if isinstance(raw_route, Mapping) else {}
        cache_matches.append(
            {
                "hit_index": match.get("hit_index"),
                "hit_selector": match.get("hit_selector"),
                "source_route": {
                    key: route.get(key)
                    for key in ("kind", "thread_key", "message_id", "line", "boundary")
                    if route.get(key) not in (None, "", [])
                },
            }
        )
    payload = {
        "kind": "aippocampus_last_registry_source_search",
        "schema_version": 1,
        "query_text": compact_text(query_text, 240),
        "match_count": len(cache_matches),
        "matches": cache_matches,
        "privacy": {
            "contains_local_paths": False,
            "contains_raw_source_text": False,
        },
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _load_registry_entry(
    *,
    registry_dir: str | Path | None,
    thread_key: str,
) -> tuple[Path, dict[str, Any] | None]:
    from aippocampus_runtime.registry.store import load_registry, registry_paths

    registry_root = Path(registry_dir).resolve() if registry_dir else None
    registry_json, _ = registry_paths(registry_root)
    payload = load_registry(registry_json)
    for entry in payload.get("threads") or []:
        if isinstance(entry, Mapping) and str(entry.get("thread_key") or "") == thread_key:
            return registry_json, dict(entry)
    return registry_json, None


def _source_open_recovery(
    *,
    code: str,
    message: str,
    thread_key: str | None = None,
) -> dict[str, Any]:
    action = foreground_template_action(
        action_id="rerun_registry_search",
        label="Rerun registry-wide source search",
        command_template='aippocampus search --all "{distinctive_phrase}" --json',
        requires=["distinctive_phrase"],
        why="The cached hit or source route is unavailable; rerun registry search for a fresh selector.",
        mutation_risk="read_only",
        claim_boundary="search_miss_is_not_absence_of_memory",
    )
    payload = {
        "kind": "aippocampus_registry_source_window",
        "ok": False,
        "status": "cannot_verify",
        "error": {"code": code, "message": message},
        "source_route": {"thread_key": thread_key} if thread_key else {},
        "metrics": {"source_reopen_success": False},
        "source_boundary": {
            "authority": "direction_only",
            "source_backed_claim_allowed": False,
            "source_reopen_required_before_claim": True,
        },
        "privacy": {
            "paths_included": False,
            "raw_full_transcript_emitted": False,
        },
    }
    payload.update(canonical_foreground_action_fields(action, safe_next_actions=[action]))
    return redact_sensitive_values(redact_private_paths(payload))


def _load_last_search_route(
    *,
    registry_dir: str | Path | None,
    hit_index: int | None,
) -> dict[str, Any] | None:
    if not hit_index or hit_index <= 0:
        return None
    path = last_registry_search_cache_path(registry_dir)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    for match in payload.get("matches") or []:
        if not isinstance(match, Mapping):
            continue
        if int(match.get("hit_index") or 0) == int(hit_index):
            route = match.get("source_route")
            return dict(route) if isinstance(route, Mapping) else None
    return None


def open_registry_source_window(
    *,
    registry_dir: str | Path | None = None,
    hit_index: int | None = None,
    use_last_search: bool = False,
    thread_key: str | None = None,
    message_id: str | None = None,
    line: int | None = None,
    context_lines: int = 2,
    include_paths: bool = False,
) -> dict[str, Any]:
    route: dict[str, Any] = {}
    if use_last_search or hit_index:
        cached = _load_last_search_route(registry_dir=registry_dir, hit_index=hit_index)
        if not cached:
            return _source_open_recovery(
                code="last_registry_search_unavailable",
                message="No matching last registry search hit is available on this machine.",
            )
        route.update(cached)
    if thread_key:
        route["thread_key"] = thread_key
    if message_id:
        route["message_id"] = message_id
    if line is not None:
        route["line"] = line
    resolved_thread_key = str(route.get("thread_key") or "").strip()
    if not resolved_thread_key:
        return _source_open_recovery(
            code="thread_key_required",
            message="A registry source window needs a thread key or a cached hit selector.",
        )
    registry_json, entry = _load_registry_entry(
        registry_dir=registry_dir,
        thread_key=resolved_thread_key,
    )
    if entry is None:
        return _source_open_recovery(
            code="registry_entry_not_found",
            message="The registry no longer contains the selected thread.",
            thread_key=resolved_thread_key,
        )
    raw_paths = entry.get("paths")
    paths: Mapping[str, Any] = raw_paths if isinstance(raw_paths, Mapping) else {}
    messages_path = Path(str(paths.get("clean_source_messages_jsonl") or ""))
    if not messages_path.is_file():
        return _source_open_recovery(
            code="clean_source_unavailable",
            message="The selected registry thread does not have a readable clean-source messages file.",
            thread_key=resolved_thread_key,
        )
    from aippocampus_runtime.source.search_core import iter_clean_messages

    messages = [dict(row) for row in iter_clean_messages(messages_path)]
    target_index = -1
    target_message_id = str(route.get("message_id") or "").strip()
    target_line = route.get("line")
    for index, message in enumerate(messages):
        current_id = str(message.get("message_id") or message.get("id") or "")
        current_line = int(message.get("source_line") or message.get("line") or -1)
        if target_message_id and current_id == target_message_id:
            target_index = index
            break
        if target_line is not None and current_line == int(target_line):
            target_index = index
            break
    if target_index < 0:
        return _source_open_recovery(
            code="source_hit_not_found",
            message="The cached hit no longer maps to a clean-source message.",
            thread_key=resolved_thread_key,
        )
    radius = max(0, min(8, int(context_lines or 0)))
    start = max(0, target_index - radius)
    end = min(len(messages), target_index + radius + 1)
    source_window = []
    for message in messages[start:end]:
        source_window.append(
            {
                "message_id": message.get("message_id") or message.get("id"),
                "turn_id": message.get("turn_id"),
                "line": message.get("source_line") or message.get("line"),
                "role": message.get("role"),
                "phase": message.get("phase") or "",
                "turn_index": message.get("turn_index"),
                "is_final": bool(message.get("is_final")),
                "text": compact_text(str(message.get("text") or ""), DEFAULT_SOURCE_WINDOW_CHARS),
            }
        )
    payload: dict[str, Any] = {
        "kind": "aippocampus_registry_source_window",
        "ok": True,
        "status": "ok",
        "registry": str(registry_json),
        "thread": _registry_entry_ref(entry),
        "source_route": {
            "kind": "registry_clean_source_hit",
            "thread_key": resolved_thread_key,
            "message_id": target_message_id
            or messages[target_index].get("message_id")
            or messages[target_index].get("id"),
            "line": messages[target_index].get("source_line") or messages[target_index].get("line"),
            "boundary": "bounded_source_window_only",
        },
        "source_window": source_window,
        "source_boundary": {
            "authority": "source_open",
            "source_backed_claim_allowed": True,
            "claim_scope": "returned_source_window_only",
            "full_thread_not_opened": True,
        },
        "metrics": {
            "source_reopen_success": True,
            "window_message_count": len(source_window),
            "context_lines": radius,
        },
        "privacy": {
            "paths_included": include_paths,
            "path_redaction": "none" if include_paths else LOCAL_PATH_REDACTION,
            "raw_full_transcript_emitted": False,
            "source_window_text_is_capped": True,
        },
    }
    if include_paths:
        payload["local_diagnostic"] = {"clean_source_messages_jsonl": str(messages_path)}
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
    )
    if args.json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(render_human_search_result(result))
    return 0 if result["matches"] else 1
