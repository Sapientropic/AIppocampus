"""Generic JSONL conversation import provider."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any, Iterable

from .base import ConversationSourceRef
from .normalized import (
    load_jsonl_dicts,
    normalized_message,
    source_path,
    turn_summaries,
)

REQUIRED_ROW_FIELDS = ("session_id", "role", "text")


class GenericJsonlValidationError(ValueError):
    """Structured validation failure for the public generic JSONL schema."""

    def __init__(self, *, line: int, code: str, message: str, **details: Any) -> None:
        super().__init__(message)
        self.line = line
        self.code = code
        self.details = details

    def asdict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "line": self.line,
            "message": str(self),
            "details": self.details,
        }


def generic_import_home() -> Path:
    env = os.environ.get("AIPPOCAMPUS_GENERIC_IMPORT_DIR")
    if env:
        return Path(env)
    return Path.cwd()


def _norm_path(path: str | Path) -> str:
    return str(Path(path).resolve()).casefold()


class GenericConversationProvider:
    """Validate and read AIppocampus generic JSONL conversation exports.

    The schema is intentionally small: each line is one visible message with a
    stable session id, role, text, optional timestamp/cwd/turn_id/source_ref, and
    optional provider metadata. It refuses ambiguous rows instead of inferring
    roles from arbitrary chat logs.
    """

    name = "generic-jsonl"

    def __init__(self, home: str | Path | None = None) -> None:
        self.home = Path(home) if home is not None else generic_import_home()

    def iter_transcripts(self) -> Iterable[Path]:
        if self.home.is_file():
            yield self.home
            return
        if self.home.exists():
            yield from self.home.rglob("*.jsonl")

    def read_metadata(self, source: str | Path | ConversationSourceRef) -> dict[str, Any] | None:
        path = source_path(source)
        session_id: str | None = None
        timestamp: str | None = None
        cwd: str | None = None
        provider_label: str | None = None
        seen = False
        for _, item in load_jsonl_dicts(path):
            seen = True
            session_id = session_id or _string(item.get("session_id"))
            timestamp = timestamp or _string(item.get("timestamp"))
            cwd = cwd or _string(item.get("cwd"))
            metadata = item.get("provider_metadata")
            if isinstance(metadata, dict):
                provider_label = provider_label or _string(metadata.get("provider"))
            if session_id and timestamp and cwd:
                break
        if not seen:
            return None
        return {
            "id": session_id,
            "session_id": session_id,
            "timestamp": timestamp,
            "cwd": cwd,
            "originator": provider_label or "Generic JSONL",
            "source": "generic_jsonl",
            "thread_source": "generic_jsonl",
        }

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
        matches: list[tuple[float, ConversationSourceRef]] = []
        latest_seen: tuple[float, ConversationSourceRef] | None = None
        for source in self.discover_sessions():
            try:
                stat = source.path.stat()
            except OSError:
                continue
            if latest_seen is None or stat.st_mtime > latest_seen[0]:
                latest_seen = (stat.st_mtime, source)
            if source.cwd and _norm_path(source.cwd) == target:
                matches.append((stat.st_mtime, source))
        if matches:
            matches.sort(reverse=True, key=lambda item: item[0])
            return matches[0][1]
        if latest and latest_seen:
            return latest_seen[1]
        raise FileNotFoundError(f"no generic JSONL transcript found for cwd: {cwd}")

    def thread_key(
        self,
        source: str | Path | ConversationSourceRef,
        meta: dict[str, Any] | None = None,
    ) -> str:
        path = source_path(source)
        session_meta = meta if meta is not None else self.read_metadata(path)
        session_id = (session_meta or {}).get("id")
        if session_id:
            return f"generic-jsonl:session:{session_id}"
        digest = hashlib.sha1(str(path.resolve()).casefold().encode("utf-8")).hexdigest()[:16]
        return f"generic-jsonl:transcript:{digest}"

    def read_normalized_messages(
        self,
        source: str | Path | ConversationSourceRef,
        *,
        include_tools: bool = False,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        path = source_path(source)
        messages: list[dict[str, Any]] = []
        turn_ids: dict[str, int] = {}
        current_turn = 0
        session_id: str | None = None

        for line_no, item in load_jsonl_dicts(path):
            missing = [field for field in REQUIRED_ROW_FIELDS if not _string(item.get(field))]
            if missing:
                raise GenericJsonlValidationError(
                    line=line_no,
                    code="missing_required_fields",
                    message=f"generic JSONL row {line_no} missing required fields: {missing}",
                    missing=missing,
                )
            row_session = _string(item.get("session_id"))
            if session_id is None:
                session_id = row_session
            elif row_session != session_id:
                raise GenericJsonlValidationError(
                    line=line_no,
                    code="session_id_changed",
                    message=f"generic JSONL row {line_no} changed session_id",
                    expected_session_id=session_id,
                    actual_session_id=row_session,
                )
            role = _string(item.get("role")).casefold()
            if role == "system":
                continue
            if role not in {"user", "assistant"}:
                raise GenericJsonlValidationError(
                    line=line_no,
                    code="unsupported_role",
                    message=f"generic JSONL row {line_no} has unsupported role: {role}",
                    role=role,
                    supported=["user", "assistant", "system"],
                )
            provider_turn_id = _string(item.get("turn_id"))
            if role == "user":
                if provider_turn_id and provider_turn_id in turn_ids:
                    current_turn = turn_ids[provider_turn_id]
                else:
                    current_turn += 1
                    if provider_turn_id:
                        turn_ids[provider_turn_id] = current_turn
            else:
                if provider_turn_id:
                    if provider_turn_id not in turn_ids:
                        raise GenericJsonlValidationError(
                            line=line_no,
                            code="unknown_turn_id",
                            message=(
                                f"generic JSONL row {line_no} references unknown turn_id: "
                                f"{provider_turn_id}"
                            ),
                            turn_id=provider_turn_id,
                        )
                    current_turn = turn_ids[provider_turn_id]
                elif not current_turn:
                    raise GenericJsonlValidationError(
                        line=line_no,
                        code="orphan_assistant",
                        message=f"generic JSONL row {line_no} assistant message has no turn",
                    )
            phase = _string(item.get("phase")) or ("final_answer" if role == "assistant" else "")
            metadata = item.get("provider_metadata") if isinstance(item.get("provider_metadata"), dict) else {}
            messages.append(
                normalized_message(
                    provider=self.name,
                    session_id=session_id,
                    line=line_no,
                    role=role,
                    text=_string(item.get("text")),
                    timestamp=_string(item.get("timestamp")),
                    kind=_string(item.get("kind")) or "message",
                    phase=phase,
                    turn_index=current_turn,
                    is_final=role == "assistant" and phase == "final_answer",
                    source_ref=_string(item.get("source_ref")) or None,
                    provider_turn_id=provider_turn_id,
                    metadata=metadata,
                )
            )

        return messages, turn_summaries(messages)


def _string(value: Any) -> str:
    return str(value).strip() if value is not None else ""
