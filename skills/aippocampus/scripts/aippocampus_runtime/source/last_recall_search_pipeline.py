"""Staged exact-source search over the same-machine last recall route set."""

from __future__ import annotations

import json
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from aippocampus_runtime.contracts import (
    canonical_foreground_action_fields,
)
from aippocampus_runtime.core import compact_text, default_thread_clean_source_dir
from aippocampus_runtime.mcp.recall_navigation import RecallNavigationError, normalize_handle
from aippocampus_runtime.mcp.source_ref_registry import source_candidate_dirs_for_ref
from aippocampus_runtime.privacy import (
    LOCAL_PATH_REDACTION,
    redact_private_paths,
    redact_sensitive_values,
)
from aippocampus_runtime.recall.agent_recall_cache import (
    handle_from_last_recall_cache,
    query_from_last_recall_cache,
    read_last_recall_cache,
)
from aippocampus_runtime.recall.continuity_domains import clean_source_fingerprint
from aippocampus_runtime.source.last_recall_actions import (
    actions_for_last_recall_search as _actions_for_last_recall_search,
)
from aippocampus_runtime.source.last_recall_actions import (
    clean_recall_selector as _clean_recall_selector,
)
from aippocampus_runtime.source.last_recall_actions import (
    deepen_action_for_request as _deepen_action_for_request,
)
from aippocampus_runtime.source.last_recall_actions import (
    deepen_command_for_request as _deepen_command_for_request,
)
from aippocampus_runtime.source.last_recall_actions import (
    last_recall_source_window_command as _last_recall_source_window_command,
)
from aippocampus_runtime.source.last_recall_actions import (
    rerun_recall_action as _rerun_recall_action,
)
from aippocampus_runtime.source.last_recall_actions import (
    selector_cache_path as _selector_cache_path,
)
from aippocampus_runtime.source.last_recall_clean_search import (
    search_clean_source_dir_for_last_recall as _search_clean_source_dir,
)
from aippocampus_runtime.source.last_recall_recovery import (
    selector_recovery_payload as _selector_recovery_payload,
)
from aippocampus_runtime.source.last_recall_thread_candidate import (
    registry_source_window_command as _registry_source_window_command,
)
from aippocampus_runtime.source.last_recall_thread_candidate import (
    thread_candidate_search_refs as _thread_candidate_search_refs,
)
from aippocampus_runtime.source.registry_search_evidence import query_anchor_rank
from aippocampus_runtime.source.search_terms import search_query_terms

DEFAULT_PUBLIC_SNIPPET_CHARS = 260


@dataclass(frozen=True)
class LastRecallRouteScan:
    matches: list[dict[str, Any]]
    warnings: list[dict[str, Any]]
    searched_route_count: int
    searched_source_count: int
    unavailable_request_indices: set[int]
    thread_candidate_request_indices: set[int]
    source_ref_request_indices: set[int]


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _recovery_payload(
    *,
    code: str,
    message: str,
    cue: str | None,
    query_text: str,
    detail: dict[str, Any] | None = None,
) -> dict[str, Any]:
    action = _rerun_recall_action(cue)
    payload: dict[str, Any] = {
        "kind": "aippocampus_last_recall_source_search",
        "ok": False,
        "status": "cannot_verify",
        "search_scope": "last_recall_candidate_sources",
        "query_text": query_text,
        "error": {
            "code": code,
            "message": message,
        },
        "source_boundary": {
            "authority": "direction_only",
            "source_backed_claim_allowed": False,
            "source_reopen_required_before_claim": True,
            "last_recall_route_set_required": True,
        },
        "privacy": {
            "paths_included": False,
            "path_redaction": LOCAL_PATH_REDACTION,
            "raw_source_snippets_emitted": False,
            "capped_source_snippets_emitted": False,
            "opaque_reopen_tokens_emitted": False,
        },
    }
    if detail:
        payload["recovery_detail"] = detail
    payload.update(canonical_foreground_action_fields(action, safe_next_actions=[action]))
    return redact_sensitive_values(redact_private_paths(payload))


def _request_indices(
    cache: Mapping[str, Any],
    *,
    request_index: int | None,
) -> list[int]:
    indices: list[int] = []
    for request in cache.get("requests") or []:
        if not isinstance(request, Mapping):
            continue
        index = _as_int(request.get("request_index"), 0)
        if index <= 0:
            continue
        if request_index is not None and index != int(request_index):
            continue
        indices.append(index)
    return indices


def handle_source_refs(handle: Any) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    thread_candidate = _thread_candidate_search_refs(handle)
    if thread_candidate is not None:
        return thread_candidate
    normalized = normalize_handle(handle)
    expires_unix = normalized.get("expires_unix")
    if isinstance(expires_unix, (int, float)) and time.time() > float(expires_unix):
        raise RecallNavigationError(
            "stale_recall_handle",
            "The recall navigation handle has expired; rerun recall before exact route search.",
            invalidated_by=["ttl_expired"],
        )
    refs = [ref for ref in normalized.get("source_refs") or [] if isinstance(ref, dict)]
    return normalized, refs


def stale_local_source_invalidations(
    normalized: Mapping[str, Any],
    refs: list[dict[str, Any]],
    *,
    clean_source_dir: Path,
) -> list[str]:
    expected = str(normalized.get("source_fingerprint") or "").strip()
    if not expected:
        return []
    if not any(not ref.get("thread_key") for ref in refs):
        return []
    current = clean_source_fingerprint(clean_source_dir)
    return ["clean_source_fingerprint_changed"] if current != expected else []


def safe_context_path(value: Any) -> Path | None:
    text = str(value or "").strip()
    if not text:
        return None
    return Path(text).expanduser().resolve()


def _match_for_last_recall(
    *,
    request_index: int,
    route_id: str,
    recall_selector: str | None,
    source_dir: Path,
    source_ref: Mapping[str, Any],
    match: Mapping[str, Any],
    include_paths: bool,
) -> dict[str, Any]:
    selector = _clean_recall_selector(recall_selector)
    thread_key = str(source_ref.get("thread_key") or "").strip()
    query_profile = match.get("query_match_profile")
    query_profile_map: Mapping[str, Any] = (
        query_profile if isinstance(query_profile, Mapping) else {}
    )
    source_route = {
        "kind": "registry_clean_source_hit" if thread_key else "last_recall_candidate_hit",
        "request_index": request_index,
        "route_id": route_id,
        "line": match.get("source_line") or match.get("line"),
        "message_id": match.get("message_id") or match.get("id"),
        "boundary": "deepen_last_recall_route_before_quoting_or_strong_claims",
    }
    if thread_key:
        source_route["thread_key"] = thread_key
        source_route["boundary"] = "open_registry_source_window_before_quoting_or_strong_claims"
    if selector:
        source_route["recall_selector"] = selector
    source_window_command = _registry_source_window_command(source_ref, match)
    if not source_window_command:
        source_window_command = _last_recall_source_window_command(
            request_index=request_index,
            recall_selector=selector,
            match=match,
        )
    item = {
        "request_index": request_index,
        "route_id": route_id,
        "source": "last_recall_candidate_clean_source",
        "message_id": match.get("message_id") or match.get("id"),
        "turn_id": match.get("turn_id"),
        "line": match.get("source_line") or match.get("line"),
        "role": match.get("role"),
        "phase": match.get("phase") or "",
        "turn_index": match.get("turn_index"),
        "is_final": bool(match.get("is_final")),
        "scope_labels": match.get("scope_labels") or [],
        "semantic_scope_labels": match.get("semantic_scope_labels") or [],
        "score": match.get("score"),
        "snippet": compact_text(
            str(match.get("snippet") or ""),
            DEFAULT_PUBLIC_SNIPPET_CHARS,
        ),
        "search_noise": bool(match.get("search_noise")),
        "noise_reason": match.get("noise_reason"),
        "source_route": source_route,
        "_query_match_profile": dict(query_profile_map),
    }
    if source_window_command:
        item["reopen_command"] = source_window_command
        item["source_window_command"] = source_window_command
    else:
        item["deepen_command"] = _deepen_command_for_request(request_index, selector)
        item["source_open_state"] = "exact_hit_unopenable"
        item["source_open_blocker"] = "missing_message_or_line_selector"
    if include_paths:
        item["local_diagnostic"] = {
            "clean_source_messages_jsonl": str(source_dir / "messages.jsonl"),
        }
    return {key: value for key, value in item.items() if value not in (None, "", [], {})}


def _query_anchor_sort_key(item: Mapping[str, Any]) -> tuple[int, int, float]:
    profile = item.get("_query_match_profile") or item.get("query_match_profile")
    if isinstance(profile, Mapping):
        return query_anchor_rank({"query_match_profile": profile})
    return (0, 0, 0.0)


def _strip_internal_match_fields(match: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in match.items() if not key.startswith("_")}


def _scan_last_recall_route_sources(
    *,
    indices: list[int],
    cache_path: Path,
    cwd_path: Path,
    patterns: list[str],
    recall_selector: str | None,
    per_route_limit: int,
    snippet_chars: int,
    include_paths: bool,
) -> LastRecallRouteScan | dict[str, Any]:
    matches: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    searched_route_count = 0
    searched_source_count = 0
    unavailable_request_indices: set[int] = set()
    thread_candidate_request_indices: set[int] = set()
    source_ref_request_indices: set[int] = set()
    seen_sources: set[tuple[int, str]] = set()
    query_text = " ".join(str(pattern) for pattern in patterns).strip()

    for index in indices:
        try:
            handle, context = handle_from_last_recall_cache(
                request_index=index,
                path=cache_path,
            )
            normalized, refs = handle_source_refs(handle)
        except RecallNavigationError as exc:
            if exc.code == "stale_recall_handle":
                return _recovery_payload(
                    code=exc.code,
                    message=exc.message,
                    cue=query_from_last_recall_cache(cache_path),
                    query_text=query_text,
                    detail=exc.details,
                )
            warnings.append(
                {
                    "code": exc.code,
                    "request_index": index,
                    "message": exc.message,
                }
            )
            unavailable_request_indices.add(index)
            continue
        except Exception as exc:
            warnings.append(
                {
                    "code": "last_recall_handle_unavailable",
                    "request_index": index,
                    "message": str(exc),
                }
            )
            unavailable_request_indices.add(index)
            continue

        if normalized.get("kind") == "thread_candidate":
            thread_candidate_request_indices.add(index)
        else:
            source_ref_request_indices.add(index)
        if not refs:
            warnings.append(
                {
                    "code": "last_recall_route_has_no_source_refs",
                    "request_index": index,
                    "handle_kind": normalized.get("kind"),
                    "message": "This recalled route cannot be searched exactly without source refs; deepen it instead.",
                }
            )
            unavailable_request_indices.add(index)
            continue

        clean_source_dir = safe_context_path(context.get("clean_source_dir")) or default_thread_clean_source_dir(cwd_path)
        registry_dir = safe_context_path(context.get("registry_dir"))
        invalidations = stale_local_source_invalidations(
            normalized,
            refs,
            clean_source_dir=clean_source_dir,
        )
        if invalidations:
            warnings.append(
                {
                    "code": "stale_recall_handle",
                    "request_index": index,
                    "invalidated_by": invalidations,
                    "message": (
                        "One recalled route source changed after recall; exact search "
                        "continues against the current reachable clean source."
                    ),
                }
            )

        route_id = str(normalized.get("route_id") or "").strip()
        searched_route_count += 1
        source_available_for_request = False
        for ref in refs:
            candidate_dirs = source_candidate_dirs_for_ref(
                ref,
                clean_source_dir=clean_source_dir,
                registry_dir=registry_dir,
            )
            if not candidate_dirs:
                warnings.append(
                    {
                        "code": "last_recall_source_unavailable",
                        "request_index": index,
                        "thread_key": ref.get("thread_key"),
                        "message": "A recalled route source is no longer reachable from the local registry/cache.",
                    }
                )
            for source_dir in candidate_dirs:
                source_available_for_request = True
                source_key = (index, str(source_dir.resolve()))
                if source_key in seen_sources:
                    continue
                seen_sources.add(source_key)
                searched_source_count += 1
                result = _search_clean_source_dir(
                    source_dir,
                    patterns,
                    limit=per_route_limit,
                    snippet_chars=snippet_chars,
                )
                for match in result.get("matches") or []:
                    if isinstance(match, Mapping):
                        matches.append(
                            _match_for_last_recall(
                                request_index=index,
                                route_id=route_id,
                                recall_selector=recall_selector,
                                source_dir=source_dir,
                                source_ref=ref,
                                match=match,
                                include_paths=include_paths,
                            )
                        )
                for warning in result.get("warnings") or []:
                    if isinstance(warning, Mapping):
                        warnings.append({"request_index": index, **dict(warning)})
        if not source_available_for_request:
            unavailable_request_indices.add(index)

    return LastRecallRouteScan(
        matches=matches,
        warnings=warnings,
        searched_route_count=searched_route_count,
        searched_source_count=searched_source_count,
        unavailable_request_indices=unavailable_request_indices,
        thread_candidate_request_indices=thread_candidate_request_indices,
        source_ref_request_indices=source_ref_request_indices,
    )


def _rank_last_recall_matches(
    matches: list[dict[str, Any]],
    *,
    limit: int,
) -> list[dict[str, Any]]:
    matches.sort(
        key=lambda item: (
            1 if item.get("search_noise") else 0,
            -_query_anchor_sort_key(item)[0],
            -_query_anchor_sort_key(item)[1],
            -_query_anchor_sort_key(item)[2],
            -_as_float(item.get("score")),
            _as_int(item.get("request_index")),
            _as_int(item.get("line")),
        )
    )
    return [
        _strip_internal_match_fields(match)
        for match in matches[: max(1, int(limit or 1))]
    ]


def _finalize_last_recall_search(
    *,
    patterns: list[str],
    query_text: str,
    cache_path: Path,
    recall_selector: str | None,
    indices: list[int],
    scan: LastRecallRouteScan,
    matches: list[dict[str, Any]],
    include_paths: bool,
) -> dict[str, Any]:
    all_unavailable = bool(indices) and not matches and scan.searched_source_count == 0
    all_unavailable_thread_candidates = (
        all_unavailable
        and bool(scan.unavailable_request_indices)
        and scan.unavailable_request_indices.issubset(scan.thread_candidate_request_indices)
    )
    unavailable_source_ref_indices = scan.unavailable_request_indices.intersection(
        scan.source_ref_request_indices
    )
    partial_unavailable_no_matches = (
        bool(indices)
        and not matches
        and scan.searched_source_count > 0
        and bool(scan.unavailable_request_indices)
    )
    if all_unavailable_thread_candidates:
        actions = [_rerun_recall_action(query_from_last_recall_cache(cache_path))]
    elif all_unavailable and unavailable_source_ref_indices:
        actions = [
            _deepen_action_for_request(
                sorted(unavailable_source_ref_indices)[0],
                recall_selector,
                action_id="deepen_route_when_exact_search_not_available",
                why=(
                    "The recall route set could not be phrase-searched from local source refs; "
                    "deepen the same selector/request before falling back to a new recall."
                ),
            ),
            _rerun_recall_action(query_from_last_recall_cache(cache_path)),
        ]
    elif all_unavailable and indices:
        actions = [
            _deepen_action_for_request(
                indices[0],
                recall_selector,
                action_id="deepen_route_when_exact_search_not_available",
                why=(
                    "The recall route set could not be phrase-searched from local source refs; "
                    "deepen the same selector/request before falling back to a new recall."
                ),
            ),
            _rerun_recall_action(query_from_last_recall_cache(cache_path)),
        ]
    else:
        actions = _actions_for_last_recall_search(
            query_text=query_text,
            has_matches=bool(matches),
            first_match=matches[0] if matches else None,
            recall_selector=recall_selector,
            partial_unavailable_no_matches=partial_unavailable_no_matches,
            recall_cue=query_from_last_recall_cache(cache_path),
        )
    status = (
        "ok"
        if matches
        else "routes_not_searchable"
        if all_unavailable
        else "partial_unavailable_no_matches"
        if partial_unavailable_no_matches
        else "no_matches"
    )
    payload: dict[str, Any] = {
        "kind": "aippocampus_last_recall_source_search",
        "ok": bool(matches),
        "status": status,
        "route_state": status,
        "search_scope": "last_recall_candidate_sources",
        "scope_description": (
            "exact search over the source candidates selected by the same-machine "
            "last agent recall; a miss is not proof that no memory exists"
        ),
        "query_text": query_text,
        "query_terms": search_query_terms(patterns),
        "recall_selector": _clean_recall_selector(recall_selector) or None,
        "matches": matches,
        "match_count": len(matches),
        "searched_route_count": scan.searched_route_count,
        "searched_source_count": scan.searched_source_count,
        "unavailable_request_count": len(scan.unavailable_request_indices),
        "partial_unavailable": partial_unavailable_no_matches,
        "warnings": scan.warnings,
        "output_boundary": (
            "local_private_last_recall_source_routes_with_paths"
            if include_paths
            else "foreground_safe_last_recall_source_routes"
        ),
        "source_boundary": {
            "authority": "reopenable_route" if matches else "direction_only",
            "source_backed_claim_allowed": False,
            "source_reopen_required_before_claim": True,
            "last_recall_routes_narrowed_search": True,
            "search_miss_is_not_absence_of_memory": not bool(matches),
        },
        "privacy": {
            "paths_included": include_paths,
            "path_redaction": "none" if include_paths else LOCAL_PATH_REDACTION,
            "raw_source_snippets_emitted": False,
            "capped_source_snippets_emitted": bool(matches),
            "opaque_reopen_tokens_emitted": False,
        },
    }
    if all_unavailable:
        payload["error"] = {
            "code": "last_recall_sources_unavailable",
            "message": "The last recall route set could not be searched because its source candidates are unavailable.",
        }
    payload.update(canonical_foreground_action_fields(actions[0], safe_next_actions=actions))
    return payload if include_paths else redact_sensitive_values(redact_private_paths(payload))


def search_last_recall_sources(
    patterns: list[str],
    *,
    cwd: str | Path,
    last_recall_path: str | Path | None = None,
    recall_selector: str | None = None,
    request_index: int | None = None,
    limit: int = 10,
    per_route_limit: int = 3,
    snippet_chars: int = 700,
    include_paths: bool = False,
) -> dict[str, Any]:
    query_text = " ".join(str(pattern) for pattern in patterns).strip()
    try:
        raw_cache_path = _selector_cache_path(
            recall_selector=recall_selector,
            last_recall_path=last_recall_path,
        )
        if raw_cache_path is None:
            raise ValueError("last recall cache path could not be resolved")
        cache_path = Path(raw_cache_path)
    except (OSError, ValueError) as exc:
        return _selector_recovery_payload(
            code="invalid_recall_selector",
            message=str(exc),
            cue=query_from_last_recall_cache(last_recall_path),
            query_text=query_text,
        )
    try:
        cache = read_last_recall_cache(cache_path)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        return _recovery_payload(
            code="last_recall_unavailable",
            message=str(exc),
            cue=query_from_last_recall_cache(last_recall_path),
            query_text=query_text,
        )

    indices = _request_indices(cache, request_index=request_index)
    if not indices:
        return _recovery_payload(
            code="last_recall_request_not_found",
            message="The last recall cache does not contain the requested route.",
            cue=query_from_last_recall_cache(cache_path),
            query_text=query_text,
            detail={"request_index": request_index},
        )

    cwd_path = Path(cwd).expanduser().resolve()
    scan = _scan_last_recall_route_sources(
        indices=indices,
        cache_path=cache_path,
        cwd_path=cwd_path,
        patterns=patterns,
        recall_selector=recall_selector,
        per_route_limit=per_route_limit,
        snippet_chars=snippet_chars,
        include_paths=include_paths,
    )
    if isinstance(scan, dict):
        return scan
    matches = _rank_last_recall_matches(scan.matches, limit=limit)
    return _finalize_last_recall_search(
        patterns=patterns,
        query_text=query_text,
        cache_path=cache_path,
        recall_selector=recall_selector,
        indices=indices,
        scan=scan,
        matches=matches,
        include_paths=include_paths,
    )
