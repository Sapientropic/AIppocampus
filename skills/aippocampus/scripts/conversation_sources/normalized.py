"""Shared helpers for provider-normalized visible transcript records."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from aippocampus_runtime.source.turns import empty_turn, message_digest

from .base import ConversationSourceRef, NormalizedConversationMessage

VISIBLE_ROLES = {"user", "assistant"}


def source_path(source: str | Path | ConversationSourceRef) -> Path:
    if isinstance(source, ConversationSourceRef):
        return source.path
    return Path(source)


def stable_source_ref(provider: str, session_id: str | None, line: int) -> str:
    if session_id:
        return f"{provider}:session:{session_id}#L{line}"
    return f"{provider}:source#L{line}"


def visible_text_from_content(content: Any) -> str:
    """Extract only visible conversational text from common host content shapes."""

    if isinstance(content, str):
        return content
    if isinstance(content, list):
        texts: list[str] = []
        for block in content:
            if isinstance(block, str):
                texts.append(block)
                continue
            if not isinstance(block, dict):
                continue
            block_type = str(block.get("type") or "").casefold()
            if block_type in {"text", "input_text", "output_text"}:
                value = block.get("text") or block.get("input_text") or block.get("output_text")
                if value:
                    texts.append(str(value))
        return "\n".join(text for text in texts if text)
    return ""


def normalized_message(
    *,
    provider: str,
    session_id: str | None,
    line: int,
    role: str,
    text: str,
    timestamp: str | None = None,
    kind: str = "message",
    phase: str = "",
    turn_index: int | None = None,
    is_final: bool = False,
    source_ref: str | None = None,
    provider_turn_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    item = NormalizedConversationMessage(
        role=role,
        text=text,
        line=line,
        timestamp=timestamp,
        kind=kind,
        phase=phase,
        turn_index=turn_index,
        is_final=is_final,
        source_ref=source_ref or stable_source_ref(provider, session_id, line),
        provider_turn_id=provider_turn_id,
        metadata=metadata or {},
    ).asdict()
    item["sha1"] = message_digest(role, phase, text)
    return item


def turn_summaries(messages: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build Codex-compatible turn summaries from provider-normalized messages."""

    turns: dict[int, dict[str, Any]] = {}
    for message in messages:
        turn_index = message.get("turn_index")
        if not isinstance(turn_index, int):
            continue
        line_no = message.get("line")
        timestamp = message.get("timestamp")
        turn = turns.setdefault(turn_index, empty_turn(turn_index, line_no, timestamp))
        if isinstance(line_no, int):
            start = turn.get("start_line")
            end = turn.get("end_line")
            turn["start_line"] = line_no if start is None else min(int(start), line_no)
            turn["end_line"] = line_no if end is None else max(int(end), line_no)
        if message.get("role") == "user" and turn.get("user_line") is None:
            turn["user_line"] = line_no
            turn["user_timestamp"] = timestamp
        if message.get("role") != "assistant":
            continue
        turn["fallback_assistant_line"] = line_no
        turn["fallback_assistant_timestamp"] = timestamp
        if message.get("phase") == "commentary":
            turn["commentary_count"] += 1
        if message.get("is_final"):
            turn["final_line"] = line_no
            turn["final_timestamp"] = timestamp
    return [turns[key] for key in sorted(turns)]


def load_jsonl_dicts(path: Path) -> Iterable[tuple[int, dict[str, Any]]]:
    if not path.is_file():
        return
    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict):
                yield line_no, item
