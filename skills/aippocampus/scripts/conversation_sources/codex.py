"""Codex Desktop conversation source provider."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

from .base import ConversationSourceRef
from .normalized import stable_source_ref

ROLLOUT_DISCOVERY_DIRS = ("sessions", "archived_sessions")


def _norm_path(path: str | Path) -> str:
    return str(Path(path).resolve()).casefold()


def _source_path(source: str | Path | ConversationSourceRef) -> Path:
    if isinstance(source, ConversationSourceRef):
        return source.path
    return Path(source)


def read_codex_session_meta(path: Path) -> dict[str, Any] | None:
    try:
        with path.open("r", encoding="utf-8") as f:
            first = f.readline()
        item = json.loads(first)
    except Exception:
        return None
    if item.get("type") == "session_meta":
        payload = item.get("payload")
        return payload if isinstance(payload, dict) else {}
    return None


def public_codex_session_meta(meta: dict[str, Any] | None) -> dict[str, Any]:
    if not meta:
        return {}
    keys = [
        "id",
        "timestamp",
        "cwd",
        "originator",
        "cli_version",
        "source",
        "thread_source",
        "model_provider",
    ]
    return {key: meta[key] for key in keys if key in meta}


class CodexConversationProvider:
    """Read Codex Desktop rollout JSONL files from live and archived storage."""

    name = "codex"

    def __init__(self, home: str | Path) -> None:
        self.home = Path(home)

    def iter_rollouts(self) -> Iterable[Path]:
        """Yield Codex rollout paths from live and app-archived storage."""

        for dirname in ROLLOUT_DISCOVERY_DIRS:
            root = self.home / dirname
            if root.exists():
                yield from root.rglob("rollout-*.jsonl")

    def read_metadata(self, source: str | Path | ConversationSourceRef) -> dict[str, Any] | None:
        return read_codex_session_meta(_source_path(source))

    def discover_sessions(self) -> Iterable[ConversationSourceRef]:
        for path in self.iter_rollouts():
            meta = public_codex_session_meta(self.read_metadata(path))
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
        raise FileNotFoundError(f"no rollout found for cwd: {cwd}")

    def thread_key(
        self,
        source: str | Path | ConversationSourceRef,
        meta: dict[str, Any] | None = None,
    ) -> str:
        source_path = _source_path(source)
        session_meta = meta if meta is not None else public_codex_session_meta(
            self.read_metadata(source_path)
        )
        session_id = (session_meta or {}).get("id")
        if session_id:
            return f"session:{session_id}"
        digest = hashlib.sha1(str(source_path.resolve()).casefold().encode("utf-8")).hexdigest()[
            :16
        ]
        return f"rollout:{digest}"

    def read_normalized_messages(
        self,
        source: str | Path | ConversationSourceRef,
        *,
        include_tools: bool = False,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        # Keep Codex-specific envelope parsing under the source owner while
        # exposing the same provider-neutral shape as newer host providers.
        from aippocampus_runtime.source.rollout import normalize_rollout

        source_path = _source_path(source)
        meta = public_codex_session_meta(self.read_metadata(source_path))
        messages, turns = normalize_rollout(source_path, include_tools=include_tools)
        for message in messages:
            line_no = message.get("line")
            if isinstance(line_no, int):
                message["source_ref"] = stable_source_ref(self.name, meta.get("id"), line_no)
                message["raw_start_line"] = line_no
                message["raw_end_line"] = line_no
        return messages, turns
