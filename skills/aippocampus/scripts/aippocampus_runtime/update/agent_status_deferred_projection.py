"""Deferred-field projection for compact update status."""

from __future__ import annotations

from typing import Any


def deferred_ambient_field_projection(
    state: Any,
    *,
    action_hints_stage: str,
    hooks_deferred: bool,
    provider_deferred: bool,
    provider_installed: bool,
) -> dict[str, Any]:
    """Project unchecked foreground fields without turning them into negatives."""

    not_checked_fields: dict[str, list[str]] = {}
    if hooks_deferred:
        not_checked_fields["hooks_status"] = [
            "prompt_hook_installed",
            "lifecycle_hook_installed",
            "action_hints_installed",
            "action_hints_stage",
            "action_hints_useful",
            "hot_path_active",
        ]
    if provider_deferred:
        not_checked_fields["provider"] = ["status", "degraded"]
    payload = {
        "prompt_hook_installed": None if hooks_deferred else state.prompt_installed,
        "lifecycle_hook_installed": None if hooks_deferred else state.lifecycle_installed,
        "action_hints_installed": None if hooks_deferred else state.action_hints_installed,
        "action_hints_stage": "deferred" if hooks_deferred else action_hints_stage,
        "action_hints_useful": None if hooks_deferred else state.action_hints_useful_signal,
        "hot_path_active": None if hooks_deferred else state.action_hints_hot_path_active,
        "provider": {
            "status": "deferred" if provider_deferred else state.provider_status or "not_checked",
            "degraded": None
            if provider_deferred
            else bool(state.provider_degraded and provider_installed),
            "values_redacted": True,
        },
    }
    if not_checked_fields:
        payload["not_checked_fields"] = not_checked_fields
    return payload
