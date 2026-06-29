"""Registry-search candidates from current-thread recall semantic positioning."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from aippocampus_runtime.core import compact_text
from aippocampus_runtime.source.io_kernel import load_jsonl_dict_rows
from aippocampus_runtime.source.registry_search_evidence import match_has_direct_source_open_route


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _semantic_anchor_coverage(position: Mapping[str, Any]) -> float:
    matched_count = max(0, _as_int(position.get("matched_term_count")))
    term_count = max(1, _as_int(position.get("term_count"), default=matched_count or 1))
    return round(min(1.0, matched_count / term_count), 6)


def _messages_path(entry: Mapping[str, Any]) -> Path | None:
    paths_value = entry.get("paths")
    paths: Mapping[str, Any] = paths_value if isinstance(paths_value, Mapping) else {}
    messages_value = str(paths.get("clean_source_messages_jsonl") or "").strip()
    return Path(messages_value) if messages_value else None


def _latest_navigation_message(entry: Mapping[str, Any]) -> dict[str, Any] | None:
    path = _messages_path(entry)
    if path is None:
        return None
    try:
        messages = [row for row in load_jsonl_dict_rows(path).rows if isinstance(row, Mapping)]
    except OSError:
        return None
    if not messages:
        return None
    messages.sort(
        key=lambda row: (
            str(row.get("phase") or "") == "final_answer" or bool(row.get("is_final")),
            _as_int(row.get("turn_index")),
            _as_int(row.get("source_line") or row.get("line")),
        ),
        reverse=True,
    )
    return dict(messages[0])


def _position_source_message(
    *,
    entry: Mapping[str, Any],
    position: Mapping[str, Any],
) -> dict[str, Any] | None:
    path = _messages_path(entry)
    if path is None:
        return None
    refs = [ref for ref in position.get("source_refs") or [] if isinstance(ref, Mapping)]
    if not refs:
        return _latest_navigation_message(entry)
    try:
        messages = load_jsonl_dict_rows(path).rows
    except OSError:
        messages = []
    for ref in refs:
        message_id = str(ref.get("message_id") or "").strip()
        line = _as_int(ref.get("source_line") or ref.get("line"), default=-1)
        for message in messages:
            if message_id and str(message.get("message_id") or message.get("id") or "") == message_id:
                return dict(message)
            if line >= 0 and _as_int(message.get("source_line") or message.get("line"), -2) == line:
                return dict(message)
    return _latest_navigation_message(entry)


def semantic_position_registry_candidates(
    *,
    positions: list[dict[str, Any]],
    entries: list[Mapping[str, Any]],
    include_paths: bool,
    build_match: Callable[..., dict[str, Any]],
    snippet_chars: int,
) -> list[dict[str, Any]]:
    by_thread = {
        str(entry.get("thread_key") or "").strip(): entry
        for entry in entries
        if str(entry.get("thread_key") or "").strip()
    }
    candidates: list[dict[str, Any]] = []
    for position in positions:
        entry = by_thread.get(str(position.get("thread_key") or "").strip())
        if not entry:
            continue
        message = _position_source_message(entry=entry, position=position)
        if not message:
            continue
        score = max(0.1, float(position.get("matched_term_count") or 1) * 0.1)
        match = build_match(
            entry=entry,
            hit={
                "source": "recall_semantic_position",
                "message_id": message.get("message_id") or message.get("id"),
                "turn_id": message.get("turn_id"),
                "line": message.get("source_line") or message.get("line"),
                "role": message.get("role"),
                "phase": message.get("phase") or "",
                "turn_index": message.get("turn_index"),
                "is_final": bool(message.get("is_final")),
                "score": score,
                "rank_score": score,
                "snippet": compact_text(str(message.get("text") or ""), snippet_chars),
            },
            include_paths=include_paths,
        )
        match["candidate_kind"] = "recall_semantic_positioning_candidate"
        match["claim_boundary"] = "semantic_positioning_navigation_only_no_claim"
        match["semantic_positioning"] = {
            "status": position.get("status"),
            "authority_level": "direction_only",
            "training_role": position.get("training_role") or "replay_sample",
            "candidate_lifecycle_state": position.get("candidate_lifecycle_state")
            or "draft_candidate_staging",
            "matched_term_count": position.get("matched_term_count"),
            "source_reopen_required_before_claim": True,
        }
        match["query_match_profile"] = {
            "accepted": False,
            "acceptance_reason": "",
            "suppression_reason": "semantic_positioning_navigation_only",
            "matched_distinctive_anchor_count": position.get("matched_term_count"),
            "distinctive_anchor_coverage": _semantic_anchor_coverage(position),
            "exact_phrase_match": False,
        }
        if match_has_direct_source_open_route(match):
            candidates.append(match)
    return candidates[:5]
