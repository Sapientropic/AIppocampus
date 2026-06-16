"""Host-integration metadata for Codex hook surfaces."""

from __future__ import annotations

from typing import Any

HOOK_HOST = "codex"
HOOK_CONFIG_SURFACE = "codex_hooks_json"
UNSUPPORTED_HOOK_HOSTS = ("claude-code", "generic-jsonl")


def host_integration_metadata() -> dict[str, Any]:
    """Return the public host boundary for current hook helpers.

    Conversation providers can be provider-aware without implying that the host
    hook installer is provider-neutral. Keep this metadata close to the Codex
    hook tools so JSON/status consumers cannot accidentally treat a
    `--provider claude-code` onboarding path as Claude Code hook support.
    """

    return {
        "host": HOOK_HOST,
        "config_surface": HOOK_CONFIG_SURFACE,
        "provider_neutral": False,
        "unsupported_hosts": list(UNSUPPORTED_HOOK_HOSTS),
    }


def add_host_integration(result: dict[str, Any]) -> dict[str, Any]:
    result["host_integration"] = host_integration_metadata()
    return result


def host_integration_text_lines() -> list[str]:
    meta = host_integration_metadata()
    return [
        f"host: {meta['host']}",
        "host scope: codex_hooks_only",
        f"config surface: {meta['config_surface']}",
        f"provider-neutral: {str(meta['provider_neutral']).lower()}",
        "other hosts: "
        + ", ".join(meta["unsupported_hosts"])
        + " use onboarding/MCP/import routes; no AIppocampus-owned hooks claimed",
        "not a failure: this installer only manages the Codex hooks.json surface",
    ]
