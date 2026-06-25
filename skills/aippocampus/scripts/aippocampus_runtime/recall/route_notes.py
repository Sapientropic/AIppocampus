#!/usr/bin/env python3
"""Route-note extraction from process commentary without making it truth.

Codex commentary and action summaries often explain why an agent tried,
rejected, or deferred a route. This module keeps those notes as navigation
material only: a note is emitted only when it can join to adjacent final-answer
or behavior-event evidence, and the serialized row carries bounded reason codes
instead of raw commentary, commands, stdout, paths, or secrets.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from aippocampus_runtime.core import stable_text_id
from aippocampus_runtime.ops.route_readiness import safe_source_refs
from aippocampus_runtime.privacy import redact_private_paths

ROUTE_NOTE_KIND = "aippocampus_route_note_candidates"
ROUTE_NOTE_SCHEMA_VERSION = 1

ROUTE_NOTE_TAXONOMY = (
    "intent_before_tool",
    "decision_breadcrumb",
    "rejected_route",
    "open_question",
    "handoff_hint",
    "source_to_action_link",
)

NOTE_PRIORITIES = {
    "rejected_route": 0,
    "open_question": 1,
    "source_to_action_link": 2,
    "decision_breadcrumb": 3,
    "handoff_hint": 4,
    "intent_before_tool": 5,
}

NOTE_TITLES = {
    "intent_before_tool": "Commentary route note: intended tool route",
    "decision_breadcrumb": "Commentary route note: decision breadcrumb",
    "rejected_route": "Commentary route note: rejected route",
    "open_question": "Commentary route note: open question",
    "handoff_hint": "Commentary route note: handoff hint",
    "source_to_action_link": "Commentary route note: source-to-action link",
}

NOTE_REASON = {
    "intent_before_tool": "A process note names an intended route before a tool check.",
    "decision_breadcrumb": "A process note records a route decision that should be source-reopened before use.",
    "rejected_route": "A process note marks a rejected route and joins to adjacent evidence.",
    "open_question": "A process note marks an unresolved question and joins to adjacent evidence.",
    "handoff_hint": "A process note leaves a handoff hint joined to adjacent evidence.",
    "source_to_action_link": "A process note links source/tool evidence to a later action.",
}


def _text(value: Any) -> str:
    return str(value or "")


def _line_value(row: Mapping[str, Any]) -> Any:
    for key in ("line", "source_line", "raw_start_line"):
        value = row.get(key)
        if value not in {None, ""}:
            return value
    return None


def _message_ref(message: Mapping[str, Any]) -> dict[str, Any]:
    ref = {
        "source_id": message.get("source_id") or message.get("stable_source_id"),
        "thread_key": message.get("thread_key"),
        "message_id": message.get("message_id") or message.get("id"),
        "turn_id": message.get("turn_id"),
        "turn_index": message.get("turn_index"),
        "line": _line_value(message),
    }
    return safe_source_refs(ref)[0] if safe_source_refs(ref) else {}


def _event_ref(event: Mapping[str, Any]) -> dict[str, Any]:
    ref = {
        "source_id": event.get("source_id") or event.get("stable_source_id"),
        "thread_key": event.get("thread_key"),
        "message_id": event.get("message_id"),
        "turn_id": event.get("turn_id"),
        "turn_index": event.get("turn_index"),
        "line": _line_value(event),
    }
    refs = safe_source_refs(ref)
    return refs[0] if refs else {}


def _is_commentary(message: Mapping[str, Any]) -> bool:
    return (
        str(message.get("role") or "").casefold() == "assistant"
        and str(message.get("phase") or "").casefold() == "commentary"
    )


def _is_final(message: Mapping[str, Any]) -> bool:
    phase = str(message.get("phase") or "").casefold()
    return (
        str(message.get("role") or "").casefold() == "assistant"
        and (phase == "final_answer" or bool(message.get("is_final")))
    )


def _note_types(text: str) -> list[str]:
    lowered = text.casefold()
    hits: list[str] = []
    if any(
        token in lowered
        for token in (
            "failed",
            "failure",
            "reject",
            "rejected",
            "wrong route",
            "abandon",
            "失败",
            "不行",
            "放弃",
            "拒绝",
        )
    ):
        hits.append("rejected_route")
    if "?" in text or any(
        token in lowered
        for token in (
            "open question",
            "unresolved",
            "unclear",
            "unknown",
            "待确认",
            "未解决",
            "不确定",
        )
    ):
        hits.append("open_question")
    if any(
        token in lowered
        for token in (
            "source",
            "evidence",
            "tool result",
            "tool output",
            "changed the next action",
            "reopen",
            "来源",
            "证据",
            "工具结果",
        )
    ):
        hits.append("source_to_action_link")
    if any(
        token in lowered
        for token in (
            "switch",
            "switched",
            "decide",
            "decided",
            "decision",
            "therefore",
            "改为",
            "转向",
            "决定",
        )
    ):
        hits.append("decision_breadcrumb")
    if any(
        token in lowered
        for token in (
            "handoff",
            "next time",
            "continue from",
            "next step",
            "下次",
            "交接",
            "下一步",
            "继续从",
        )
    ):
        hits.append("handoff_hint")
    if any(
        token in lowered
        for token in (
            "before",
            "first",
            "i will",
            "i'll",
            "check",
            "read",
            "search",
            "run",
            "先",
            "准备",
            "检查",
            "读取",
            "搜索",
        )
    ):
        hits.append("intent_before_tool")
    return sorted(set(hits), key=lambda item: NOTE_PRIORITIES.get(item, 99))


def _messages_by_turn(messages: Iterable[Mapping[str, Any]]) -> dict[int, list[Mapping[str, Any]]]:
    turns: dict[int, list[Mapping[str, Any]]] = {}
    for message in messages:
        if not isinstance(message, Mapping):
            continue
        turn_index = message.get("turn_index")
        if isinstance(turn_index, int):
            turns.setdefault(turn_index, []).append(message)
    return turns


def _events_by_turn(events: Iterable[Mapping[str, Any]]) -> dict[int, list[Mapping[str, Any]]]:
    turns: dict[int, list[Mapping[str, Any]]] = {}
    for event in events:
        if not isinstance(event, Mapping):
            continue
        turn_index = event.get("turn_index")
        if isinstance(turn_index, int):
            turns.setdefault(turn_index, []).append(event)
    return turns


def _source_keyed_messages(
    messages: Iterable[Mapping[str, Any]],
    *,
    source_id: str,
    source_thread_key: str,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for message in messages:
        item = dict(message)
        item.setdefault("source_id", source_id)
        item.setdefault("thread_key", source_thread_key)
        if "source_line" not in item and "line" in item:
            item["source_line"] = item["line"]
        out.append(item)
    return out


def _joined_evidence_refs(
    *,
    turn_messages: list[Mapping[str, Any]],
    turn_events: list[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    joined: list[dict[str, Any]] = []
    source_refs: list[dict[str, Any]] = []
    for event in turn_events:
        event_ref = _event_ref(event)
        if not event_ref:
            continue
        joined.append(
            {
                "evidence_kind": "behavior_event",
                "event_id": event.get("event_id") or event.get("id"),
                "event_kind": event.get("hard_event_kind") or event.get("event_kind"),
                "status": event.get("status"),
                "command_class": event.get("command_class"),
                "command_family": event.get("command_family"),
                "target_class": event.get("target_class"),
                "failure_family": event.get("failure_family"),
                "source_ref": event_ref,
            }
        )
        source_refs.append(event_ref)
    for message in turn_messages:
        if not _is_final(message):
            continue
        message_ref = _message_ref(message)
        if not message_ref:
            continue
        joined.append(
            {
                "evidence_kind": "final_answer",
                "message_id": message.get("message_id") or message.get("id"),
                "source_ref": message_ref,
            }
        )
        source_refs.append(message_ref)
    return joined, source_refs


def _dedupe_dicts(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[tuple[tuple[str, str], ...]] = set()
    for row in rows:
        marker = tuple(sorted((str(key), str(value)) for key, value in row.items()))
        if marker in seen:
            continue
        seen.add(marker)
        out.append(row)
    return out


def _route_note_row(
    *,
    note_type: str,
    message: Mapping[str, Any],
    joined_evidence_refs: list[dict[str, Any]],
    source_refs: list[dict[str, Any]],
) -> dict[str, Any]:
    note_ref = _message_ref(message)
    route_id = stable_text_id(
        "route_note",
        note_type,
        message.get("message_id") or message.get("id"),
        message.get("source_line") or message.get("line"),
        joined_evidence_refs,
        length=20,
    )
    joined_evidence_kind = sorted(
        {str(ref.get("evidence_kind") or "unknown") for ref in joined_evidence_refs}
    )
    reason_codes = [
        "route_note",
        note_type,
        "joined_to_adjacent_evidence",
        *(f"joined_{kind}" for kind in joined_evidence_kind),
    ]
    return {
        "route_id": route_id,
        "route_id_hash": stable_text_id("route", route_id, length=20),
        "surface_kind": f"route_note:{note_type}",
        "origin": "route_note",
        "status": "ready",
        "readiness_class": "source_reopen_ready",
        "title": NOTE_TITLES[note_type],
        "why_lit": NOTE_REASON[note_type],
        "note_type": note_type,
        "output_authority": "navigation_only",
        "navigation_only": True,
        "source_reopen_required_before_claim": True,
        "source_refs": _dedupe_dicts(source_refs)[:3],
        "source_ref_count": len(_dedupe_dicts(source_refs)[:3]),
        "note_source_ref": note_ref,
        "joined_evidence_refs": joined_evidence_refs[:4],
        "freshness": "current",
        "currentness": "current",
        "reason_codes": reason_codes,
    }


def extract_route_note_candidates(
    messages: Iterable[Mapping[str, Any]],
    *,
    events: Iterable[Mapping[str, Any]] | None = None,
    max_notes: int = 12,
) -> dict[str, Any]:
    """Emit public-safe route-note candidates from adjacent process evidence."""

    turns = _messages_by_turn(messages)
    event_turns = _events_by_turn(events or [])
    rows: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []

    for turn_index in sorted(turns):
        turn_messages = turns[turn_index]
        turn_events = event_turns.get(turn_index, [])
        joined_evidence_refs, source_refs = _joined_evidence_refs(
            turn_messages=turn_messages,
            turn_events=turn_events,
        )
        for message in turn_messages:
            if not _is_commentary(message):
                continue
            note_types = _note_types(_text(message.get("text")))
            if not note_types:
                diagnostics.append(
                    {"turn_index": turn_index, "reason": "commentary_taxonomy_miss"}
                )
                continue
            if not joined_evidence_refs:
                diagnostics.append(
                    {"turn_index": turn_index, "reason": "adjacent_evidence_missing"}
                )
                continue
            rows.append(
                _route_note_row(
                    note_type=note_types[0],
                    message=message,
                    joined_evidence_refs=joined_evidence_refs,
                    source_refs=source_refs,
                )
            )

    rows = rows[: max(0, int(max_notes or 0))]
    diagnostic_count = len(diagnostics)
    joined_tool_count = sum(
        1
        for row in rows
        if any(ref.get("evidence_kind") == "behavior_event" for ref in row["joined_evidence_refs"])
    )
    payload = {
        "kind": ROUTE_NOTE_KIND,
        "schema_version": ROUTE_NOTE_SCHEMA_VERSION,
        "no_write": True,
        "navigation_only": True,
        "taxonomy": list(ROUTE_NOTE_TAXONOMY),
        "rows": rows,
        "diagnostics": diagnostics[:8],
        "metrics": {
            "candidate_count": len(rows),
            "diagnostic_only_count": diagnostic_count,
            "joined_tool_evidence_count": joined_tool_count,
            "joined_final_answer_count": sum(
                1
                for row in rows
                if any(
                    ref.get("evidence_kind") == "final_answer"
                    for ref in row["joined_evidence_refs"]
                )
            ),
            "ignored_raw_commentary_count": diagnostic_count,
        },
        "contract": {
            "commentary_is_process_evidence_not_source_truth": True,
            "clean_source_mutation_allowed": False,
            "raw_commentary_serialized": False,
            "raw_commands_serialized": False,
            "stdout_serialized": False,
            "source_reopen_required_before_claim": True,
            "external_model_calls": False,
        },
        "privacy_boundary": {
            "raw_source_text_serialized": False,
            "raw_commentary_serialized": False,
            "raw_commands_serialized": False,
            "stdout_serialized": False,
            "local_paths_serialized": False,
            "secret_values_serialized": False,
        },
        "cannot_claim": [
            "commentary_note_is_source_truth",
            "route_note_proves_memory_fact",
            "raw_commentary_reintroduced_to_clean_source",
        ],
    }
    return redact_private_paths(payload)


def extract_route_note_candidates_for_source(
    messages: Iterable[Mapping[str, Any]],
    *,
    events: Iterable[Mapping[str, Any]] | None = None,
    source_id: str,
    source_thread_key: str,
    max_notes: int = 12,
) -> dict[str, Any]:
    """Attach source join keys, then emit route-note candidates."""

    return extract_route_note_candidates(
        _source_keyed_messages(
            messages,
            source_id=source_id,
            source_thread_key=source_thread_key,
        ),
        events=events,
        max_notes=max_notes,
    )


__all__ = [
    "ROUTE_NOTE_KIND",
    "ROUTE_NOTE_SCHEMA_VERSION",
    "ROUTE_NOTE_TAXONOMY",
    "extract_route_note_candidates",
    "extract_route_note_candidates_for_source",
]
