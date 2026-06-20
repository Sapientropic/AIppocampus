#!/usr/bin/env python3
"""Codex rollout envelope parsing for clean-source and recall tools."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterable

from aippocampus_runtime.source.normalization_loss import (
    count_provider_loss,
    empty_provider_normalization_loss,
    finalize_provider_normalization_loss,
)
from aippocampus_runtime.source.turns import empty_turn, message_digest

INJECTED_INSTRUCTION_PREFIXES = (
    "# AGENTS.md instructions",
    "<skill>",
    "<permissions instructions>",
    "<environment_context>",
    "<collaboration_mode>",
    "<skills_instructions>",
    "<plugins_instructions>",
    "<app-context>",
    "WECHAT SESSION INSTRUCTIONS",
    "WECHAT THREAD CONTINUITY REFRESH",
    "WECHAT SESSION INSTRUCTIONS REFRESH",
)


def iter_jsonl(
    path: Path,
    *,
    normalization_loss: dict[str, Any] | None = None,
) -> Iterable[tuple[int, dict[str, Any]]]:
    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                if normalization_loss is not None:
                    count_provider_loss(normalization_loss, "invalid_json_line_count")
                continue
            if isinstance(item, dict):
                yield line_no, item
            elif normalization_loss is not None:
                count_provider_loss(normalization_loss, "non_object_line_count")


def message_phase(payload: dict[str, Any]) -> str:
    phase = payload.get("phase")
    return str(phase or "")


def extract_message(item: dict[str, Any], include_tools: bool = False) -> dict[str, Any] | None:
    payload = item.get("payload") or {}
    typ = item.get("type")

    if typ == "event_msg":
        ptype = payload.get("type")
        if ptype == "user_message":
            return {
                "role": "user",
                "kind": "user_message",
                "phase": message_phase(payload),
                "text": payload.get("message") or "",
            }
        if ptype == "agent_message":
            return {
                "role": "assistant",
                "kind": "agent_message",
                "phase": message_phase(payload),
                "text": payload.get("message") or "",
            }
        if include_tools:
            return {
                "role": "event",
                "kind": ptype or "event_msg",
                "phase": message_phase(payload),
                "text": json.dumps(payload, ensure_ascii=False),
            }

    if typ == "response_item":
        ptype = payload.get("type")
        if ptype == "message":
            role = payload.get("role") or "message"
            if role not in {"user", "assistant"}:
                return None
            texts = []
            for part in payload.get("content") or []:
                if isinstance(part, dict):
                    texts.append(part.get("text") or "")
                    texts.append(part.get("input_text") or "")
                    texts.append(part.get("output_text") or "")
            text = "\n".join(t for t in texts if t)
            return {"role": role, "kind": "message", "phase": message_phase(payload), "text": text}
        if include_tools and ptype in {"function_call", "function_call_output", "web_search_call"}:
            return {
                "role": "tool",
                "kind": ptype,
                "phase": "tool",
                "text": json.dumps(payload, ensure_ascii=False),
            }

    return None


def tool_payload_kind(item: dict[str, Any]) -> str | None:
    if item.get("type") != "response_item":
        return None
    payload = item.get("payload") or {}
    ptype = payload.get("type")
    if ptype in {"function_call", "function_call_output", "web_search_call"}:
        return str(ptype)
    return None


def _row_drop_reason(item: dict[str, Any], *, include_tools: bool) -> str | None:
    typ = item.get("type")
    payload = item.get("payload") or {}
    if typ == "session_meta":
        return None
    if typ == "event_msg":
        ptype = payload.get("type")
        if ptype in {"user_message", "agent_message"}:
            return "empty_text_policy_drop_count"
        return "unsupported_event_count"
    if typ == "response_item":
        ptype = payload.get("type")
        if ptype == "message":
            role = payload.get("role") or "message"
            if role not in {"user", "assistant"}:
                return "role_policy_drop_count"
            return "empty_text_policy_drop_count"
        if ptype in {"function_call", "function_call_output", "web_search_call"}:
            return None if include_tools else "tool_payload_policy_drop_count"
        return "unsupported_event_count"
    return "unsupported_event_count"


def is_injected_instruction_text(text: str) -> bool:
    """Return True for known runtime carrier blocks, not topical user prose.

    Full-machine onboarding makes repeated carrier text show up hundreds of
    times. This guard is intentionally structural: it recognizes envelope
    prefixes injected by host/runtime plumbing so those blocks do not outrank
    user evidence. Do not turn this into a semantic topic filter or a static
    vocabulary for judging what a user "really meant".
    """

    stripped = str(text or "").lstrip()
    if any(stripped.startswith(prefix) for prefix in INJECTED_INSTRUCTION_PREFIXES):
        return True
    if re.match(r"^<developer(?:\s|>)", stripped, flags=re.IGNORECASE):
        return True
    return False


def normalize_rollout_with_loss(
    rollout: Path,
    include_tools: bool = False,
) -> tuple[list[dict], list[dict], dict[str, Any]]:
    """Return deduped visible messages plus turn summaries.

    Codex Desktop writes a user request as a stream of raw events: commentary,
    tool calls/outputs, and finally a final_answer. Long-term recall should
    prefer the user request plus final_answer, while audit/provenance tools can
    still inspect raw tool lines. For that reason this normalizer records tool
    counts and raw line spans in turns, but it does not put tool payload text in
    the default message index unless include_tools is explicitly requested.
    """

    seen: set[str] = set()
    messages: list[dict] = []
    turns: dict[int, dict] = {}
    current_turn = 0
    normalization_loss = empty_provider_normalization_loss("codex")

    for line_no, item in iter_jsonl(rollout, normalization_loss=normalization_loss):
        timestamp = item.get("timestamp")
        tool_kind = tool_payload_kind(item)
        if current_turn and current_turn in turns:
            turns[current_turn]["end_line"] = line_no
            if tool_kind == "function_call":
                turns[current_turn]["tool_call_count"] += 1
            elif tool_kind in {"function_call_output", "web_search_call"}:
                turns[current_turn]["tool_output_count"] += 1

        msg = extract_message(item, include_tools=include_tools)
        if not msg:
            reason = _row_drop_reason(item, include_tools=include_tools)
            if reason:
                count_provider_loss(normalization_loss, reason)
            continue
        if not msg.get("text"):
            count_provider_loss(normalization_loss, "empty_text_policy_drop_count")
            continue
        text = msg["text"].lstrip()
        if msg["role"] == "user" and is_injected_instruction_text(text):
            count_provider_loss(normalization_loss, "injected_instruction_policy_drop_count")
            continue

        phase = str(msg.get("phase") or "")
        digest = message_digest(msg["role"], phase, msg["text"])
        if digest in seen:
            count_provider_loss(normalization_loss, "duplicate_message_drop_count")
            continue
        seen.add(digest)

        if msg["role"] == "user":
            current_turn += 1
            turns[current_turn] = empty_turn(current_turn, line_no, timestamp)
        elif current_turn and current_turn in turns:
            turns[current_turn]["end_line"] = line_no

        turn_index = current_turn if current_turn else None
        is_final = msg["role"] == "assistant" and phase == "final_answer"

        if turn_index and turn_index in turns and msg["role"] == "assistant":
            turns[turn_index]["fallback_assistant_line"] = line_no
            turns[turn_index]["fallback_assistant_timestamp"] = timestamp
            if phase == "commentary":
                turns[turn_index]["commentary_count"] += 1
            if is_final:
                turns[turn_index]["final_line"] = line_no
                turns[turn_index]["final_timestamp"] = timestamp

        messages.append(
            {
                "line": line_no,
                "timestamp": timestamp,
                "role": msg["role"],
                "kind": msg["kind"],
                "phase": phase,
                "turn_index": turn_index,
                "is_final": is_final,
                "sha1": digest,
                "text": msg["text"],
            }
        )

    return messages, list(turns.values()), finalize_provider_normalization_loss(normalization_loss)


def normalize_rollout(rollout: Path, include_tools: bool = False) -> tuple[list[dict], list[dict]]:
    messages, turns, _normalization_loss = normalize_rollout_with_loss(
        rollout,
        include_tools=include_tools,
    )
    return messages, turns


def iter_messages(rollout: Path, include_tools: bool = False) -> Iterable[dict]:
    messages, _ = normalize_rollout(rollout, include_tools=include_tools)
    yield from messages


__all__ = [
    "INJECTED_INSTRUCTION_PREFIXES",
    "empty_turn",
    "extract_message",
    "is_injected_instruction_text",
    "iter_jsonl",
    "iter_messages",
    "message_phase",
    "normalize_rollout",
    "normalize_rollout_with_loss",
    "tool_payload_kind",
]
