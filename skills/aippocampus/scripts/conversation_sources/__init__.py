"""Conversation source providers for AIppocampus ingestion."""

from __future__ import annotations

from pathlib import Path

from .base import ConversationProvider, ConversationSourceRef
from .claude_code import ClaudeCodeConversationProvider, claude_home
from .codex import CodexConversationProvider
from .generic_jsonl import (
    GenericConversationProvider,
    GenericJsonlValidationError,
    generic_import_home,
)

PROVIDER_ALIASES = {
    "auto": "codex",
    "claude": "claude-code",
    "claude-code": "claude-code",
    "codex": "codex",
    "generic": "generic-jsonl",
    "generic-jsonl": "generic-jsonl",
    "jsonl": "generic-jsonl",
}
PROVIDER_CHOICES = ("auto", "codex", "claude-code", "generic-jsonl")


class ConversationProviderUnavailable(ValueError):
    """Raised when a named host-agent provider has no implementation yet."""

    def __init__(self, provider: str) -> None:
        super().__init__(f"conversation provider is not available: {provider}")
        self.provider = provider


def normalize_provider_name(provider: str | None) -> str:
    value = (provider or "auto").strip().replace("_", "-").casefold()
    return PROVIDER_ALIASES.get(value, value)


def create_conversation_provider(
    provider: str | None = "auto",
    *,
    claude_home_dir: str | Path | None = None,
    codex_home_dir: str | Path | None = None,
) -> ConversationProvider:
    resolved = normalize_provider_name(provider)
    if resolved == "codex" and codex_home_dir is not None:
        return CodexConversationProvider(codex_home_dir)
    if resolved == "claude-code":
        return ClaudeCodeConversationProvider(claude_home_dir or claude_home())
    if resolved == "generic-jsonl":
        return GenericConversationProvider(generic_import_home())
    raise ConversationProviderUnavailable(resolved)


__all__ = [
    "ClaudeCodeConversationProvider",
    "CodexConversationProvider",
    "ConversationProvider",
    "ConversationProviderUnavailable",
    "ConversationSourceRef",
    "PROVIDER_CHOICES",
    "GenericConversationProvider",
    "GenericJsonlValidationError",
    "claude_home",
    "create_conversation_provider",
    "generic_import_home",
    "normalize_provider_name",
]
