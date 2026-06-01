"""Claude Code conversation source provider."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import replace
from pathlib import Path
from typing import Any, Iterable

from .base import ConversationSourceRef
from .normalized import (
    load_jsonl_dicts,
    normalized_message,
    source_path,
    turn_summaries,
    visible_text_from_content,
)


def claude_home() -> Path:
    env = os.environ.get("CLAUDE_HOME")
    if env:
        return Path(env)
    return Path.home() / ".claude"


def _norm_path(path: str | Path) -> str:
    return str(Path(path).resolve()).casefold()


def _source_path(source: str | Path | ConversationSourceRef) -> Path:
    if isinstance(source, ConversationSourceRef):
        return source.path
    return Path(source)


def _public_claude_metadata(item: dict[str, Any], meta: dict[str, Any]) -> None:
    session_id = item.get("sessionId")
    if session_id and not meta.get("id"):
        meta["id"] = session_id
        meta["session_id"] = session_id
    timestamp = item.get("timestamp")
    if timestamp and not meta.get("timestamp"):
        meta["timestamp"] = timestamp
    cwd = item.get("cwd")
    if cwd and not meta.get("cwd"):
        meta["cwd"] = cwd
    for key in ("version", "gitBranch", "entrypoint", "userType"):
        value = item.get(key)
        if value and key not in meta:
            meta[key] = value
    if item.get("type") == "ai-title" and item.get("aiTitle") and not meta.get("title"):
        meta["title"] = item["aiTitle"]


def read_claude_session_meta(path: Path, *, max_lines: int = 400) -> dict[str, Any] | None:
    meta: dict[str, Any] = {
        "originator": "Claude Code",
        "source": "claude_code",
        "thread_source": "claude_code",
        "model_provider": "anthropic",
    }
    seen = False
    try:
        with path.open("r", encoding="utf-8") as f:
            for line_no, line in enumerate(f, start=1):
                if line_no > max_lines:
                    break
                try:
                    item = json.loads(line)
                except Exception:
                    continue
                if not isinstance(item, dict):
                    continue
                seen = True
                _public_claude_metadata(item, meta)
                if meta.get("id") and meta.get("cwd") and meta.get("timestamp"):
                    break
    except OSError:
        return None
    return meta if seen else None


def transcript_contains_cwd(path: Path, target: str) -> bool:
    try:
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                try:
                    item = json.loads(line)
                except Exception:
                    continue
                cwd = item.get("cwd") if isinstance(item, dict) else None
                if cwd and _norm_path(cwd) == target:
                    return True
    except OSError:
        return False
    return False


class ClaudeCodeConversationProvider:
    """Read Claude Code JSONL transcripts from the local projects store."""

    name = "claude-code"

    def __init__(self, home: str | Path | None = None) -> None:
        self.home = Path(home) if home is not None else claude_home()

    def iter_transcripts(self) -> Iterable[Path]:
        root = self.home / "projects"
        if root.exists():
            yield from root.rglob("*.jsonl")

    def read_metadata(self, source: str | Path | ConversationSourceRef) -> dict[str, Any] | None:
        return read_claude_session_meta(_source_path(source))

    def discover_sessions(self) -> Iterable[ConversationSourceRef]:
        for path in self.iter_transcripts():
            meta = self.read_metadata(path) or {}
            cwd_value = meta.get("cwd")
            yield ConversationSourceRef(
                provider=self.name,
                path=path,
                session_id=meta.get("id"),
                cwd=Path(cwd_value) if cwd_value else None,
                timestamp=meta.get("timestamp"),
                metadata=meta,
            )

    def locate_current(self, cwd: str | Path, *, latest: bool = False) -> ConversationSourceRef:
        target = _norm_path(cwd)
        cwd_path = Path(cwd).resolve()
        matches: list[tuple[float, ConversationSourceRef]] = []
        latest_seen: tuple[float, ConversationSourceRef] | None = None

        for source in self.discover_sessions():
            try:
                stat = source.path.stat()
            except OSError:
                continue
            if latest_seen is None or stat.st_mtime > latest_seen[0]:
                latest_seen = (stat.st_mtime, source)
            if (source.cwd and _norm_path(source.cwd) == target) or transcript_contains_cwd(
                source.path, target
            ):
                metadata = dict(source.metadata)
                metadata["cwd"] = str(cwd_path)
                matches.append((stat.st_mtime, replace(source, cwd=cwd_path, metadata=metadata)))

        if matches:
            matches.sort(reverse=True, key=lambda item: item[0])
            return matches[0][1]
        if latest and latest_seen:
            return latest_seen[1]
        raise FileNotFoundError(f"no Claude Code transcript found for cwd: {cwd}")

    def thread_key(
        self,
        source: str | Path | ConversationSourceRef,
        meta: dict[str, Any] | None = None,
    ) -> str:
        source_path = _source_path(source)
        session_meta = meta if meta is not None else self.read_metadata(source_path)
        session_id = (session_meta or {}).get("id")
        if session_id:
            return f"claude-code:session:{session_id}"
        # Fallback thread keys are source-backed registry ids. Changing this
        # digest in place would orphan previously registered transcripts.
        digest = hashlib.sha1(str(source_path.resolve()).casefold().encode("utf-8")).hexdigest()[
            :16
        ]
        return f"claude-code:transcript:{digest}"

    def read_normalized_messages(
        self,
        source: str | Path | ConversationSourceRef,
        *,
        include_tools: bool = False,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Parse Claude Code JSONL into visible provider-neutral messages.

        Thinking, tool-use/result blocks, attachments, and other non-message rows
        stay in the raw transcript audit path. Clean source only receives text a
        normal user or assistant would see in the conversation.
        """

        path = source_path(source)
        meta = self.read_metadata(path) or {}
        session_id = meta.get("id")
        messages: list[dict[str, Any]] = []
        current_turn = 0
        seen: set[tuple[str, str, str, str]] = set()

        for line_no, item in load_jsonl_dicts(path):
            row_type = str(item.get("type") or "").casefold()
            if row_type not in {"user", "assistant"}:
                continue
            raw_payload = item.get("message")
            payload: dict[str, Any] = raw_payload if isinstance(raw_payload, dict) else {}
            role = str(payload.get("role") or row_type).casefold()
            if role not in {"user", "assistant"}:
                continue
            text = visible_text_from_content(payload.get("content"))
            if not text:
                continue
            phase = "final_answer" if role == "assistant" else ""
            digest_key = (role, phase, text, str(item.get("uuid") or line_no))
            if digest_key in seen:
                continue
            seen.add(digest_key)
            if role == "user":
                current_turn += 1
            elif not current_turn:
                continue
            messages.append(
                normalized_message(
                    provider=self.name,
                    session_id=session_id,
                    line=line_no,
                    role=role,
                    text=text,
                    timestamp=item.get("timestamp"),
                    kind="message",
                    phase=phase,
                    turn_index=current_turn,
                    is_final=role == "assistant",
                    provider_turn_id=item.get("parentUuid") or item.get("uuid"),
                    metadata={
                        key: item[key]
                        for key in ("uuid", "parentUuid", "cwd")
                        if item.get(key) is not None
                    },
                )
            )

        return messages, turn_summaries(messages)
