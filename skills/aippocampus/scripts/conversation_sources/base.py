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
