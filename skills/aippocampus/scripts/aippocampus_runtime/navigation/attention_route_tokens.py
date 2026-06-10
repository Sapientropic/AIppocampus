"""Hierarchical route tokens for source-backed attention navigation.

Route tokens are navigation units for the future router. They preserve reopen
handles and route metadata, but they never carry raw source text or claim-ready
authority on their own.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping
from typing import Any

ROUTE_METADATA_FIELDS = ("salience", "currentness", "privacy", "conflict")
TOKEN_LEVELS = ("source_span_token", "event_token", "episode_or_question_token")


def _stable_id(*parts: Any, prefix: str = "tok") -> str:
    payload = "|".join(str(part) for part in parts if part is not None)
    return f"{prefix}_{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:16]}"


def _text(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    return text or default


def _range(value: Any) -> list[int] | None:
    if isinstance(value, (list, tuple)) and len(value) == 2:
        return [int(value[0]), int(value[1])]
    return None


def _list_of_mappings(value: Any) -> list[Mapping[str, Any]]:
    return [row for row in value or [] if isinstance(row, Mapping)]


def _route_metadata(*sources: Mapping[str, Any]) -> dict[str, str]:
    merged: dict[str, str] = {}
    for field in ROUTE_METADATA_FIELDS:
        value = ""
        for source in sources:
            metadata = source.get("route_metadata")
            if isinstance(metadata, Mapping) and metadata.get(field):
                value = str(metadata[field])
            elif source.get(field):
                value = str(source[field])
        merged[field] = value or "unknown"
    return merged


def _source_ref(ref: Mapping[str, Any]) -> dict[str, Any]:
    compact: dict[str, Any] = {}
    for key in ("source_id", "message_id", "turn_id", "line", "source_line"):
        if ref.get(key) is not None:
            compact[key] = ref[key]
    line_range = _range(ref.get("line_range"))
    if line_range:
        compact["line_range"] = line_range
    return compact


def _source_handle(
    *,
    source_id: str,
    segment_id: str,
    turn_range: Any = None,
    line_range: Any = None,
    char_range: Any = None,
) -> dict[str, Any]:
    handle: dict[str, Any] = {
        "source_id": source_id,
        "segment_id": segment_id,
        "reopen_required": True,
    }
    for key, value in (
        ("turn_range", _range(turn_range)),
        ("line_range", _range(line_range)),
        ("char_range", _range(char_range)),
    ):
        if value:
            handle[key] = value
    return handle


def _source_handles_from_refs(event: Mapping[str, Any]) -> list[dict[str, Any]]:
    handles = []
    event_source_id = _text(event.get("source_id"), "unknown_source")
    event_segment_id = _text(
        event.get("segment_id") or event.get("message_id") or event.get("turn_id"),
        "unknown_segment",
    )
    for ref in _list_of_mappings(event.get("source_refs")):
        handles.append(
            _source_handle(
                source_id=_text(ref.get("source_id"), event_source_id),
                segment_id=_text(
                    ref.get("segment_id") or ref.get("message_id") or ref.get("turn_id"),
                    event_segment_id,
                ),
                turn_range=ref.get("turn_range") or event.get("turn_range"),
                line_range=ref.get("line_range") or ref.get("line"),
            )
        )
    if handles:
        return handles
    return [
        _source_handle(
            source_id=event_source_id,
            segment_id=event_segment_id,
            turn_range=event.get("turn_range"),
        )
    ]


def project_event_route_tokens(event: Mapping[str, Any]) -> dict[str, Any]:
    event_token_id = _text(event.get("event_token_id") or event.get("event_id")) or _stable_id(
        event.get("source_id"),
        event.get("turn_id"),
        prefix="event",
    )
    source_handles = _source_handles_from_refs(event)
    source_refs = [_source_ref(ref) for ref in _list_of_mappings(event.get("source_refs"))]
    span_tokens = [
        _span_token(span, event=event, event_token_id=event_token_id)
        for span in _list_of_mappings(event.get("spans"))
    ]
    return {
        "event_token": {
            "kind": "aippocampus_attention_route_token",
            "schema_version": "attention-route-token-v0",
            "token_id": event_token_id,
            "route_token_level": "event_token",
            "role": _text(event.get("role"), "unknown"),
            "turn_id": _text(event.get("turn_id")),
            "timestamp": _text(event.get("timestamp")),
            "thread": _text(event.get("thread") or event.get("thread_id")),
            "phase": _text(event.get("phase"), "unknown"),
            "source_refs": source_refs,
            "source_handles": source_handles,
            "span_token_ids": [span["token_id"] for span in span_tokens],
            "route_metadata": _route_metadata(event),
            "action_grammar": "reopenable_route",
            "claim_permission": "no_claim_before_reopen",
            "token_contract": _token_contract(),
        },
        "source_span_tokens": span_tokens,
    }


def _span_token(
    span: Mapping[str, Any],
    *,
    event: Mapping[str, Any],
    event_token_id: str,
) -> dict[str, Any]:
    token_id = _text(span.get("span_token_id") or span.get("span_id")) or _stable_id(
        event_token_id,
        span.get("kind"),
        span.get("char_range"),
        prefix="span",
    )
    handle = _source_handle(
        source_id=_text(span.get("source_id"), _text(event.get("source_id"), "unknown_source")),
        segment_id=_text(
            span.get("segment_id") or event.get("segment_id") or event.get("turn_id"),
            "unknown_segment",
        ),
        turn_range=span.get("turn_range") or event.get("turn_range"),
        line_range=span.get("line_range"),
        char_range=span.get("char_range"),
    )
    return {
        "kind": "aippocampus_attention_route_token",
        "schema_version": "attention-route-token-v0",
        "token_id": token_id,
        "route_token_level": "source_span_token",
        "parent_event_token_id": event_token_id,
        "span_kind": _text(span.get("kind"), "span"),
        "source_refs": [_source_ref(ref) for ref in _list_of_mappings(span.get("source_refs"))],
        "source_handles": [handle],
        "route_metadata": _route_metadata(event, span),
        "action_grammar": "reopenable_route",
        "claim_permission": "no_claim_before_reopen",
        "token_contract": _token_contract(),
    }


def project_episode_or_question_token(
    group: Mapping[str, Any],
    *,
    event_tokens: Iterable[Mapping[str, Any]],
    source_span_tokens: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    event_by_id = {str(token.get("token_id")): token for token in event_tokens}
    span_by_id = {str(token.get("token_id")): token for token in source_span_tokens}
    member_event_ids = [
        token_id for token_id in group.get("member_event_token_ids") or [] if token_id in event_by_id
    ]
    member_span_ids = [
        token_id
        for token_id in group.get("member_source_span_token_ids") or []
        if token_id in span_by_id
    ]
    source_handles: list[dict[str, Any]] = []
    for token_id in [*member_event_ids, *member_span_ids]:
        token = event_by_id.get(token_id) or span_by_id.get(token_id) or {}
        source_handles.extend(token.get("source_handles") or [])
    return {
        "kind": "aippocampus_attention_route_token",
        "schema_version": "attention-route-token-v0",
        "token_id": _text(group.get("token_id") or group.get("group_id"))
        or _stable_id(member_event_ids, member_span_ids, prefix="episode"),
        "route_token_level": "episode_or_question_token",
        "group_kind": _text(group.get("group_kind"), "episode"),
        "member_event_token_ids": member_event_ids,
        "member_source_span_token_ids": member_span_ids,
        "source_handles": source_handles,
        "route_metadata": _route_metadata(group),
        "action_grammar": "direction_only",
        "claim_permission": "no_claim_before_reopen",
        "token_contract": _token_contract(),
    }


def _token_contract() -> dict[str, bool]:
    return {
        "route_token_is_not_evidence": True,
        "source_reopen_required_before_claim": True,
        "raw_source_text_omitted": True,
    }


def project_hierarchical_route_tokens(
    events: Iterable[Mapping[str, Any]],
    groups: Iterable[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    event_tokens = []
    span_tokens = []
    for event in events:
        projected = project_event_route_tokens(event)
        event_tokens.append(projected["event_token"])
        span_tokens.extend(projected["source_span_tokens"])
    group_tokens = [
        project_episode_or_question_token(
            group,
            event_tokens=event_tokens,
            source_span_tokens=span_tokens,
        )
        for group in groups
    ]
    all_tokens = [*event_tokens, *span_tokens, *group_tokens]
    token_claim_ready_without_reopen_count = sum(
        1 for token in all_tokens if token.get("claim_permission") != "no_claim_before_reopen"
    )
    return {
        "kind": "aippocampus_attention_route_token_fixture",
        "schema_version": "attention-route-token-v0",
        "ok": token_claim_ready_without_reopen_count == 0,
        "tokens": all_tokens,
        "metrics": {
            "source_span_token_count": len(span_tokens),
            "event_token_count": len(event_tokens),
            "episode_or_question_token_count": len(group_tokens),
            "token_claim_ready_without_reopen_count": token_claim_ready_without_reopen_count,
        },
        "privacy_boundary": {
            "raw_source_text_emitted": False,
            "private_text_emitted": False,
            "tokens_are_navigation_only": True,
        },
        "cannot_claim": [
            "hot_attention_router_quality",
            "source_truth_without_reopen",
            "private_history_token_quality",
            "default_router_adoption",
        ],
    }


def fixture_events() -> list[dict[str, Any]]:
    return [
        {
            "event_id": "event_public_long_turn",
            "source_id": "clean:public-thread-a",
            "segment_id": "msg-7",
            "role": "user",
            "turn_id": "turn-7",
            "timestamp": "2026-06-10T18:20:00+08:00",
            "thread": "thread:public-a",
            "phase": "implementation",
            "source_refs": [
                {"source_id": "clean:public-thread-a", "message_id": "msg-7", "line": 40}
            ],
            "route_metadata": {
                "salience": "high",
                "currentness": "current",
                "privacy": "public",
                "conflict": "none",
            },
            "spans": [
                {
                    "span_id": "span_public_long_turn_code_block",
                    "kind": "code_block",
                    "source_id": "clean:public-thread-a",
                    "segment_id": "msg-7",
                    "char_range": [128, 220],
                    "line_range": [45, 53],
                    "source_refs": [
                        {
                            "source_id": "clean:public-thread-a",
                            "message_id": "msg-7",
                            "line_range": [45, 53],
                        }
                    ],
                    "route_metadata": {"salience": "high", "privacy": "public"},
                    "text": "PRIVATE_SPAN_TEXT_SENTINEL",
                }
            ],
        }
    ]


def fixture_groups() -> list[dict[str, Any]]:
    return [
        {
            "group_id": "episode_question_frontier",
            "group_kind": "question_frontier",
            "member_event_token_ids": ["event_public_long_turn"],
            "member_source_span_token_ids": ["span_public_long_turn_code_block"],
            "route_metadata": {
                "salience": "medium",
                "currentness": "needs_reopen",
                "privacy": "public",
                "conflict": "none",
            },
        }
    ]


def build_route_token_fixture_report() -> dict[str, Any]:
    return project_hierarchical_route_tokens(fixture_events(), fixture_groups())
