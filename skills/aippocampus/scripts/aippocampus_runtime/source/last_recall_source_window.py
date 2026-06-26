"""Open bounded source windows from last-recall scoped search hits."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from aippocampus_runtime.contracts import canonical_foreground_action_fields
from aippocampus_runtime.core import compact_text, default_thread_clean_source_dir
from aippocampus_runtime.mcp.recall_navigation import RecallNavigationError
from aippocampus_runtime.mcp.source_ref_registry import source_candidate_dirs_for_ref
from aippocampus_runtime.privacy import (
    LOCAL_PATH_REDACTION,
    redact_private_paths,
    redact_sensitive_values,
)
from aippocampus_runtime.recall.agent_recall_cache import (
    handle_from_last_recall_cache,
    query_from_last_recall_cache,
)
from aippocampus_runtime.source.last_recall_actions import (
    rerun_recall_action as _rerun_recall_action,
)
from aippocampus_runtime.source.last_recall_actions import (
    selector_cache_path as _selector_cache_path,
)
from aippocampus_runtime.source.last_recall_search_pipeline import (
    handle_source_refs,
    safe_context_path,
    stale_local_source_invalidations,
)
from aippocampus_runtime.source.query_match_gate import match_query_profile, query_match_gate
from aippocampus_runtime.source.search_core import iter_clean_messages

DEFAULT_SOURCE_WINDOW_CHARS = 1800


def _source_window_recovery(
    *,
    code: str,
    message: str,
    cue: str | None,
    detail: dict[str, Any] | None = None,
) -> dict[str, Any]:
    action = _rerun_recall_action(cue)
    payload: dict[str, Any] = {
        "kind": "aippocampus_last_recall_source_window",
        "ok": False,
        "status": "cannot_verify",
        "error": {"code": code, "message": message},
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
    if detail:
        payload["recovery_detail"] = detail
    payload.update(canonical_foreground_action_fields(action, safe_next_actions=[action]))
    return redact_sensitive_values(redact_private_paths(payload))


def _select_message_index(
    messages: list[dict[str, Any]],
    *,
    message_id: str | None,
    line: int | None,
) -> int:
    wanted_message = str(message_id or "").strip()
    for index, message in enumerate(messages):
        current_id = str(message.get("message_id") or message.get("id") or "")
        if wanted_message and current_id == wanted_message:
            return index
        current_line = message.get("source_line") or message.get("line")
        if line is not None and current_line is not None and str(current_line).isdigit():
            if int(str(current_line)) == int(line):
                return index
    return -1


def _source_change_warnings(
    *,
    invalidations: list[str],
    request_index: int | None,
) -> list[dict[str, Any]]:
    if not invalidations:
        return []
    return [
        {
            "code": "stale_recall_handle",
            "request_index": request_index,
            "invalidated_by": invalidations,
            "message": (
                "The recalled source changed after recall; the source window was "
                "opened from the current reachable clean source."
            ),
        }
    ]


def _source_anchor_profile(
    query_text: str,
    source_window: list[dict[str, Any]],
) -> dict[str, Any]:
    query = str(query_text or "").strip()
    if not query:
        return {
            "query_available": False,
            "exact_phrase_match": False,
            "anchor_count": 0,
            "matched_anchor_count": 0,
            "anchor_coverage": 0.0,
            "matched_anchors": [],
        }
    haystack = "\n".join(str(message.get("text") or "") for message in source_window)
    profile = match_query_profile(
        query_text=query,
        gate=query_match_gate(query),
        haystack=haystack,
    )
    matched = [str(anchor) for anchor in profile.get("matched_distinctive_anchors") or []]
    return {
        "query_available": True,
        "exact_phrase_match": bool(profile.get("exact_phrase_match")),
        "anchor_count": int(profile.get("distinctive_anchor_count") or 0),
        "matched_anchor_count": int(profile.get("matched_distinctive_anchor_count") or 0),
        "anchor_coverage": float(profile.get("distinctive_anchor_coverage") or 0.0),
        "matched_anchors": matched,
    }


def _source_window_payload(
    *,
    normalized: Mapping[str, Any],
    ref: Mapping[str, Any],
    messages: list[dict[str, Any]],
    selected_index: int,
    request_index: int,
    context_lines: int,
    searched_source_count: int,
    warnings: list[dict[str, Any]],
    include_paths: bool,
    source_dir: Path,
    query_text: str = "",
) -> dict[str, Any]:
    radius = max(0, min(8, int(context_lines or 0)))
    start = max(0, selected_index - radius)
    end = min(len(messages), selected_index + radius + 1)
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
    selected = messages[selected_index]
    source_route = {
        "kind": "last_recall_candidate_hit",
        "request_index": request_index,
        "route_id": normalized.get("route_id"),
        "message_id": selected.get("message_id") or selected.get("id"),
        "line": selected.get("source_line") or selected.get("line"),
        "boundary": "bounded_source_window_only",
    }
    thread_key = str(ref.get("thread_key") or "").strip()
    if thread_key:
        source_route["kind"] = "registry_clean_source_hit"
        source_route["thread_key"] = thread_key
    anchor_profile = _source_anchor_profile(query_text, source_window)
    payload: dict[str, Any] = {
        "kind": "aippocampus_last_recall_source_window",
        "ok": True,
        "status": "source_open",
        "source_route": {
            key: value for key, value in source_route.items() if value not in (None, "", [], {})
        },
        "source_window": source_window,
        "anchor_hits": anchor_profile["matched_anchors"],
        "source_anchor_profile": anchor_profile,
        "source_boundary": {
            "authority": "source_open",
            "source_backed_claim_allowed": True,
            "claim_scope": "returned_source_window_only",
            "source_reopen_required_before_claim": False,
            "raw_full_transcript_emitted": False,
        },
        "metrics": {
            "source_reopen_success": True,
            "window_message_count": len(source_window),
            "window_context_lines": radius,
            "searched_source_count": searched_source_count,
            "source_window_text_is_capped": True,
        },
        "warnings": warnings,
        "privacy": {
            "paths_included": include_paths,
            "path_redaction": "none" if include_paths else LOCAL_PATH_REDACTION,
            "raw_full_transcript_emitted": False,
        },
    }
    if include_paths:
        payload["local_diagnostic"] = {
            "clean_source_messages_jsonl": str(source_dir / "messages.jsonl"),
        }
    return payload if include_paths else redact_sensitive_values(redact_private_paths(payload))


def open_last_recall_source_window(
    *,
    cwd: str | Path,
    last_recall_path: str | Path | None = None,
    recall_selector: str | None = None,
    request_index: int | None = None,
    message_id: str | None = None,
    line: int | None = None,
    context_lines: int = 2,
    include_paths: bool = False,
    query_text: str | None = None,
) -> dict[str, Any]:
    if request_index is None or int(request_index or 0) <= 0:
        return _source_window_recovery(
            code="last_recall_request_required",
            message="Provide --request with --from-last-recall --open-source.",
            cue=query_from_last_recall_cache(last_recall_path),
        )
    if not str(message_id or "").strip() and line is None:
        return _source_window_recovery(
            code="source_selector_required",
            message="Provide --message-id or --line for last-recall source reopen.",
            cue=query_from_last_recall_cache(last_recall_path),
        )
    try:
        cache_path = _selector_cache_path(
            recall_selector=recall_selector,
            last_recall_path=last_recall_path,
        )
    except (OSError, ValueError) as exc:
        return _source_window_recovery(
            code="invalid_recall_selector",
            message=str(exc),
            cue=query_from_last_recall_cache(last_recall_path),
        )
    try:
        handle, context = handle_from_last_recall_cache(
            request_index=int(request_index),
            path=cache_path,
        )
        normalized, refs = handle_source_refs(handle)
    except RecallNavigationError as exc:
        return _source_window_recovery(
            code=exc.code,
            message=exc.message,
            cue=query_from_last_recall_cache(cache_path),
            detail=exc.details,
        )
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        return _source_window_recovery(
            code="last_recall_handle_unavailable",
            message=str(exc),
            cue=query_from_last_recall_cache(cache_path),
        )

    cwd_path = Path(cwd).expanduser().resolve()
    clean_source_dir = safe_context_path(context.get("clean_source_dir")) or default_thread_clean_source_dir(cwd_path)
    registry_dir = safe_context_path(context.get("registry_dir"))
    invalidations = stale_local_source_invalidations(
        normalized,
        refs,
        clean_source_dir=clean_source_dir,
    )
    warnings = _source_change_warnings(
        invalidations=invalidations,
        request_index=request_index,
    )
    anchor_query = str(query_text or query_from_last_recall_cache(cache_path) or "").strip()

    searched_source_count = 0
    for ref in refs:
        for source_dir in source_candidate_dirs_for_ref(
            ref,
            clean_source_dir=clean_source_dir,
            registry_dir=registry_dir,
        ):
            searched_source_count += 1
            messages = [dict(row) for row in iter_clean_messages(source_dir / "messages.jsonl")]
            selected_index = _select_message_index(
                messages,
                message_id=message_id,
                line=line,
            )
            if selected_index < 0:
                continue
            return _source_window_payload(
                normalized=normalized,
                ref=ref,
                messages=messages,
                selected_index=selected_index,
                request_index=int(request_index),
                context_lines=context_lines,
                searched_source_count=searched_source_count,
                warnings=warnings,
                include_paths=include_paths,
                source_dir=source_dir,
                query_text=anchor_query,
            )
    return _source_window_recovery(
        code="source_hit_not_found",
        message="The selected last-recall source hit no longer maps to clean source.",
        cue=query_from_last_recall_cache(cache_path),
        detail={"request_index": request_index, "searched_source_count": searched_source_count},
    )


def run_last_recall_source_window_cli(args: Any) -> int:
    result = open_last_recall_source_window(
        cwd=args.cwd,
        last_recall_path=args.last_recall_path,
        recall_selector=args.recall_selector,
        request_index=args.request,
        message_id=args.message_id,
        line=args.line,
        context_lines=args.context_lines,
        include_paths=bool(args.include_paths),
    )
    if args.json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        from aippocampus_runtime.source.search_output import render_human_search_result

        print(render_human_search_result(result))
    return 0 if result.get("ok") else 1


__all__ = [
    "open_last_recall_source_window",
    "run_last_recall_source_window_cli",
]
