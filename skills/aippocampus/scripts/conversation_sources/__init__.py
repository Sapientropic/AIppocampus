"""Conversation source providers for AIppocampus ingestion."""

from __future__ import annotations

from pathlib import Path

from .base import ConversationProvider, ConversationSourceRef
from .codex import CodexConversationProvider

PROVIDER_ALIASES = {
    "auto": "codex",
    "codex": "codex",
}
PROVIDER_CHOICES = tuple(PROVIDER_ALIASES)


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
    codex_home_dir: str | Path | None = None,
) -> ConversationProvider:
    resolved = normalize_provider_name(provider)
    if resolved == "codex" and codex_home_dir is not None:
        return CodexConversationProvider(codex_home_dir)
    raise ConversationProviderUnavailable(resolved)


__all__ = [
    "CodexConversationProvider",
    "ConversationProvider",
    "ConversationProviderUnavailable",
    "ConversationSourceRef",
    "PROVIDER_CHOICES",
    "create_conversation_provider",
    "normalize_provider_name",
]
