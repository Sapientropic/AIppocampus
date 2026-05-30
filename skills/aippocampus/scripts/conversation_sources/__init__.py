"""Conversation source providers for AIppocampus ingestion."""

from __future__ import annotations

from .base import ConversationProvider, ConversationSourceRef
from .codex import CodexConversationProvider

__all__ = [
    "CodexConversationProvider",
    "ConversationProvider",
    "ConversationSourceRef",
]
