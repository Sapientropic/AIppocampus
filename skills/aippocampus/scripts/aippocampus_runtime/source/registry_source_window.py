"""Reopen bounded source windows for registry-wide search hits."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from aippocampus_runtime.contracts import (
    canonical_foreground_action_fields,
    foreground_template_action,
)
from aippocampus_runtime.core import compact_text
from aippocampus_runtime.privacy import (
    LOCAL_PATH_REDACTION,
    redact_private_paths,
    redact_sensitive_values,
)
from aippocampus_runtime.source.registry_search_evidence import match_has_direct_source_open_route
from aippocampus_runtime.source.registry_search_skips import registry_entry_ref

DEFAULT_SOURCE_WINDOW_CHARS = 700
LAST_SEARCH_CACHE_NAME = "last-registry-source-search.json"


def last_registry_search_cache_path(registry_dir: str | Path | None = None) -> Path:
    from aippocampus_runtime.registry.store import registry_paths

    registry_root = Path(registry_dir).resolve() if registry_dir else None
    registry_json, _ = registry_paths(registry_root)
    return registry_json.parent / LAST_SEARCH_CACHE_NAME


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
        direct_source_open = match_has_direct_source_open_route(match)
        duplicate_source_routes = []
        for ref in match.get("duplicate_source_refs") or []:
            if not isinstance(ref, Mapping):
                continue
            raw_ref_route = ref.get("source_route")
            ref_route: Mapping[str, Any] = (
                raw_ref_route if isinstance(raw_ref_route, Mapping) else {}
            )
            if not ref_route:
                continue
            duplicate_source_routes.append(
                {
                    "source_ref_index": ref.get("source_ref_index"),
                    "source_route": {
                        key: ref_route.get(key)
                        for key in ("kind", "thread_key", "message_id", "line", "boundary")
                        if ref_route.get(key) not in (None, "", [])
                    },
                }
            )
        cache_matches.append(
            {
                "hit_index": match.get("hit_index"),
                "hit_selector": match.get("hit_selector"),
                # The cache feeds `search --last-search --hit ... --open-source`.
                # SQLite-only rows can look line-addressable while still having
                # no matching clean-source message; caching those routes gives
                # agents a copy-paste command that is guaranteed to fail.
                "source_route": (
                    {
                        key: route.get(key)
                        for key in ("kind", "thread_key", "message_id", "line", "boundary")
                        if route.get(key) not in (None, "", [])
                    }
                    if direct_source_open
                    else {}
                ),
                "duplicate_source_routes": duplicate_source_routes,
            }
        )
    payload = {
        "kind": "aippocampus_last_registry_source_search",
        "schema_version": 2,
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
    source_ref_index: int | None = None,
) -> dict[str, Any] | None:
    if not hit_index or hit_index <= 0:
        return None
    path = last_registry_search_cache_path(registry_dir)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    for match in payload.get("matches") or []:
        if not isinstance(match, Mapping):
            continue
        if int(match.get("hit_index") or 0) == int(hit_index):
            if source_ref_index is not None and int(source_ref_index or 0) > 0:
                for ref in match.get("duplicate_source_routes") or []:
                    if not isinstance(ref, Mapping):
                        continue
                    if int(ref.get("source_ref_index") or 0) != int(source_ref_index):
                        continue
                    route = ref.get("source_route")
                    return dict(route) if isinstance(route, Mapping) else None
                return None
            route = match.get("source_route")
            return dict(route) if isinstance(route, Mapping) else None
    return None


def open_registry_source_window(
    *,
    registry_dir: str | Path | None = None,
    hit_index: int | None = None,
    source_ref_index: int | None = None,
    use_last_search: bool = False,
    thread_key: str | None = None,
    message_id: str | None = None,
    line: int | None = None,
    context_lines: int = 2,
    include_paths: bool = False,
) -> dict[str, Any]:
    route: dict[str, Any] = {}
    if use_last_search or hit_index:
        cached = _load_last_search_route(
            registry_dir=registry_dir,
            hit_index=hit_index,
            source_ref_index=source_ref_index,
        )
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
    source_window = [
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
        for message in messages[start:end]
    ]
    payload: dict[str, Any] = {
        "kind": "aippocampus_registry_source_window",
        "ok": True,
        "status": "ok",
        "registry": str(registry_json),
        "thread": registry_entry_ref(entry),
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


__all__ = [
    "last_registry_search_cache_path",
    "open_registry_source_window",
    "write_last_registry_search_cache",
]
