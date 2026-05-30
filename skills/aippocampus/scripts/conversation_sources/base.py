"""Provider contracts for host-agent conversation sources."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Protocol


@dataclass(frozen=True)
class ConversationSourceRef:
    """Portable reference to a host-agent conversation transcript."""

    provider: str
    path: Path
    session_id: str | None = None
    cwd: Path | None = None
    timestamp: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class NormalizedConversationMessage:
    """Provider-neutral visible message record for clean-source builders."""

    role: str
    text: str
    line: int
    timestamp: str | None = None
    kind: str = "message"
    phase: str = ""
    turn_index: int | None = None
    is_final: bool = False
    raw_start_line: int | None = None
    raw_end_line: int | None = None
    source_ref: str | None = None
    provider_turn_id: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def asdict(self) -> dict[str, Any]:
        return {
            "line": self.line,
            "timestamp": self.timestamp,
            "role": self.role,
            "kind": self.kind,
            "phase": self.phase,
            "turn_index": self.turn_index,
            "is_final": self.is_final,
            "raw_start_line": self.raw_start_line if self.raw_start_line is not None else self.line,
            "raw_end_line": self.raw_end_line if self.raw_end_line is not None else self.line,
            "source_ref": self.source_ref,
            "provider_turn_id": self.provider_turn_id,
            "provider_metadata": dict(self.metadata),
            "text": self.text,
        }


class ConversationProvider(Protocol):
    """Minimal ingestion boundary between host transcripts and AIppocampus core."""

    name: str

    def discover_sessions(self) -> Iterable[ConversationSourceRef]:
        """Yield known local conversation sources for this provider."""

    def locate_current(self, cwd: str | Path, *, latest: bool = False) -> ConversationSourceRef:
        """Find the source associated with a workspace cwd."""

    def read_metadata(self, source: str | Path | ConversationSourceRef) -> dict[str, Any] | None:
        """Read public session metadata from a conversation source."""

    def thread_key(
        self,
        source: str | Path | ConversationSourceRef,
        meta: dict[str, Any] | None = None,
    ) -> str:
        """Return the stable AIppocampus thread key for a source."""

    def read_normalized_messages(
        self,
        source: str | Path | ConversationSourceRef,
        *,
        include_tools: bool = False,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Return provider-normalized visible messages plus turn summaries."""
