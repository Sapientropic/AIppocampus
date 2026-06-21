"""Exact source search over the route set from the same-machine last recall."""

from __future__ import annotations

import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from aippocampus_runtime.contracts import canonical_foreground_action_fields
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
from aippocampus_runtime.source.clean_source import SCOPE_LABEL_ORDER
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
    rerun_recall_action as _rerun_recall_action,
)
from aippocampus_runtime.source.last_recall_actions import (
    selector_cache_path as _selector_cache_path,
)
from aippocampus_runtime.source.search_core import iter_clean_messages, score_message
from aippocampus_runtime.source.search_terms import search_query_terms
from aippocampus_runtime.source.semantic_scope_labels import (
    load_semantic_scope_labels,
    merged_scope_labels,
    semantic_labels_for_message,
)

PROCESS_NOISE_PREFIXES = (
    ("<subagent_notification>", "process_notification"),
    ("<tool", "tool_process"),
)
DEFAULT_PUBLIC_SNIPPET_CHARS = 260


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


def _process_noise_reason(text: str) -> str:
    snippet = str(text or "").lstrip().casefold()
    for prefix, reason in PROCESS_NOISE_PREFIXES:
        if snippet.startswith(prefix):
            return reason
    return ""


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


def _handle_source_refs(handle: Any) -> tuple[dict[str, Any], list[dict[str, Any]]]:
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


def _stale_local_source_invalidations(
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


def _safe_context_path(value: Any) -> Path | None:
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
    match: Mapping[str, Any],
    include_paths: bool,
) -> dict[str, Any]:
    selector = _clean_recall_selector(recall_selector)
    source_route = {
        "kind": "last_recall_candidate_hit",
        "request_index": request_index,
        "route_id": route_id,
        "line": match.get("source_line") or match.get("line"),
        "message_id": match.get("message_id") or match.get("id"),
        "boundary": "deepen_last_recall_route_before_quoting_or_strong_claims",
    }
    if selector:
        source_route["recall_selector"] = selector
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
        "deepen_command": _deepen_command_for_request(request_index, selector),
    }
    if include_paths:
        item["local_diagnostic"] = {
            "clean_source_messages_jsonl": str(source_dir / "messages.jsonl"),
        }
    return {key: value for key, value in item.items() if value not in (None, "", [], {})}


def _search_clean_source_dir(
    source_dir: Path,
    patterns: list[str],
    *,
    limit: int,
    snippet_chars: int,
) -> dict[str, Any]:
    semantic_sidecar = load_semantic_scope_labels(source_dir)
    terms = search_query_terms(patterns)
    known_scope_labels = set(SCOPE_LABEL_ORDER)
    matches: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    for message in iter_clean_messages(source_dir / "messages.jsonl"):
        message_text = str(message.get("text") or "")
        base_scope_labels = [
            str(label) for label in message.get("scope_labels", []) if isinstance(label, str)
        ]
        semantic_scope_labels = semantic_labels_for_message(message, semantic_sidecar)
        message_scope_labels = merged_scope_labels(base_scope_labels, semantic_scope_labels)
        for label in message_scope_labels:
            if label not in known_scope_labels:
                warnings.append(
                    {
                        "code": "unknown_scope_label",
                        "scope_label": label,
                        "message": f"Unknown scope label: {label}",
                    }
                )
        score = score_message(message, terms)
        if score <= 0:
            continue
        noise_reason = _process_noise_reason(message_text)
        match = {
            "id": message.get("message_id") or message.get("id"),
            "message_id": message.get("message_id") or message.get("id"),
            "turn_id": message.get("turn_id"),
            "source_line": message.get("source_line"),
            "role": message.get("role"),
            "phase": message.get("phase") or "",
            "turn_index": message.get("turn_index"),
            "is_final": bool(message.get("is_final")),
            "scope_labels": message_scope_labels,
            "semantic_scope_labels": semantic_scope_labels,
            "score": round(score, 3),
            "snippet": compact_text(message_text, snippet_chars) if snippet_chars else "",
            "snippet_omitted": snippet_chars == 0,
        }
        if noise_reason:
            match["search_noise"] = True
            match["noise_reason"] = noise_reason
        matches.append(match)
    matches.sort(
        key=lambda item: (
            1 if item.get("search_noise") else 0,
            -_as_float(item.get("score")),
            _as_int(item.get("source_line")),
        )
    )
    return {"matches": matches[:limit], "warnings": warnings}


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
            if match.get("deepen_command"):
                lines.append(f"   next: {match.get('deepen_command')}")
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
    cache_path = _selector_cache_path(
        recall_selector=recall_selector,
        last_recall_path=last_recall_path,
    )
    try:
        cache = read_last_recall_cache(cache_path)
    except Exception as exc:
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
    matches: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    searched_route_count = 0
    searched_source_count = 0
    unavailable_request_indices: set[int] = set()
    seen_sources: set[tuple[int, str]] = set()

    for index in indices:
        try:
            handle, context = handle_from_last_recall_cache(
                request_index=index,
                path=cache_path,
            )
            normalized, refs = _handle_source_refs(handle)
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

        clean_source_dir = _safe_context_path(context.get("clean_source_dir")) or default_thread_clean_source_dir(cwd_path)
        registry_dir = _safe_context_path(context.get("registry_dir"))
        invalidations = _stale_local_source_invalidations(
            normalized,
            refs,
            clean_source_dir=clean_source_dir,
        )
        if invalidations:
            return _recovery_payload(
                code="stale_recall_handle",
                message="The last recall source set changed; rerun recall before exact route search.",
                cue=query_from_last_recall_cache(cache_path),
                query_text=query_text,
                detail={"invalidated_by": invalidations, "request_index": index},
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
                                match=match,
                                include_paths=include_paths,
                            )
                        )
                for warning in result.get("warnings") or []:
                    if isinstance(warning, Mapping):
                        warnings.append({"request_index": index, **dict(warning)})
        if not source_available_for_request:
            unavailable_request_indices.add(index)

    matches.sort(
        key=lambda item: (
            1 if item.get("search_noise") else 0,
            -_as_float(item.get("score")),
            _as_int(item.get("request_index")),
            _as_int(item.get("line")),
        )
    )
    matches = matches[: max(1, int(limit or 1))]
    all_unavailable = bool(indices) and not matches and searched_source_count == 0
    partial_unavailable_no_matches = (
        bool(indices)
        and not matches
        and searched_source_count > 0
        and bool(unavailable_request_indices)
    )
    actions = (
        [
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
        if all_unavailable and indices
        else _actions_for_last_recall_search(
            query_text=query_text,
            has_matches=bool(matches),
            first_match=matches[0] if matches else None,
            recall_selector=recall_selector,
            partial_unavailable_no_matches=partial_unavailable_no_matches,
            recall_cue=query_from_last_recall_cache(cache_path),
        )
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
        "searched_route_count": searched_route_count,
        "searched_source_count": searched_source_count,
        "unavailable_request_count": len(unavailable_request_indices),
        "partial_unavailable": partial_unavailable_no_matches,
        "warnings": warnings,
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
        import json

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
