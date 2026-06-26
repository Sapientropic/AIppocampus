"""Cognitive-worker mode resolution for optional model-backed background work.

This module deliberately answers a small routing question only: which background
cognition lane is allowed for semantic/subconscious/Dream-adjacent work in this
process?  It does not start workers, inspect key values, or certify host agent
quality.  The first agent-fallback slice is scaffold/manual-only so a no-key
local install can queue source-backed work without smuggling model output into
source truth, foreground hooks, or "ambient useful" readiness claims.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any

from aippocampus_runtime.model.routing import (
    DEFAULT_DEEPSEEK_API_KEY_ENV,
    deepseek_api_key_env,
    is_default_deepseek_api_key_env,
)

COGNITIVE_WORKER_MODE_ENV = "AIPPOCAMPUS_COGNITIVE_WORKER_MODE"
AGENT_FALLBACK_AVAILABLE_ENV = "AIPPOCAMPUS_AGENT_FALLBACK_AVAILABLE"
BACKGROUND_MODEL_CONSENT_ENV = "AIPPOCAMPUS_BACKGROUND_MODEL_CONSENT"

VALID_MODES = {"auto", "external_model", "agent_fallback", "deterministic_only", "off"}
TRUE_VALUES = {"1", "true", "yes", "on", "available"}
FALSE_VALUES = {"0", "false", "no", "off", "unavailable", "disabled"}


def _mode_token(value: Any) -> str:
    raw = str(value or "").strip().casefold().replace("-", "_")
    if raw in {"external", "model", "provider", "provider_model"}:
        return "external_model"
    if raw in {"agent", "fallback", "agent_worker"}:
        return "agent_fallback"
    if raw in {"deterministic", "local_only", "none"}:
        return "deterministic_only"
    if raw in {"0", "false", "disabled", "no"}:
        return "off"
    if raw in {"1", "true", "enabled", "yes"}:
        return "auto"
    return raw if raw in VALID_MODES else "auto"


def _env_has_name(env: Mapping[str, str], name: str) -> bool:
    # Presence-only by design. Empty values still prove the launcher provided a
    # variable; provider-doctor separately explains that it never reads values.
    return bool(name and name in env)


def _env_bool(env: Mapping[str, str], name: str) -> bool:
    raw = str(env.get(name, "")).strip().casefold()
    if raw in TRUE_VALUES:
        return True
    if raw in FALSE_VALUES:
        return False
    return False


def resolve_cognitive_worker_mode(
    *,
    api_key_env: str = DEFAULT_DEEPSEEK_API_KEY_ENV,
    mode: str | None = None,
    provider_key_visible: bool | None = None,
    agent_fallback_available: bool | None = None,
    require_background_model_consent: bool = False,
    background_model_consent: bool | None = None,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Return a public-safe mode report for optional cognitive workers."""

    env_map: Mapping[str, str] = env if env is not None else os.environ
    requested = _mode_token(mode if mode is not None else env_map.get(COGNITIVE_WORKER_MODE_ENV, "auto"))
    resolved_api_key_env = (
        deepseek_api_key_env(env_map)
        if is_default_deepseek_api_key_env(api_key_env)
        else api_key_env
    )
    key_visible = (
        _env_has_name(env_map, resolved_api_key_env)
        if provider_key_visible is None
        else bool(provider_key_visible)
    )
    fallback_available = (
        _env_bool(env_map, AGENT_FALLBACK_AVAILABLE_ENV)
        if agent_fallback_available is None
        else bool(agent_fallback_available)
    )
    background_consent = (
        _env_bool(env_map, BACKGROUND_MODEL_CONSENT_ENV)
        if background_model_consent is None
        else bool(background_model_consent)
    )

    degraded_from = ""
    reason = ""
    if requested == "off":
        resolved = "off"
        status = "disabled_by_env"
    elif requested == "external_model":
        if key_visible and require_background_model_consent and not background_consent:
            resolved = "deterministic_only"
            status = "background_model_consent_required"
            degraded_from = "external_model"
            reason = "background_model_consent_required"
        elif key_visible:
            resolved = "external_model"
            status = "external_model_active"
        else:
            resolved = "deterministic_only"
            status = "deterministic_only_missing_provider_key"
            degraded_from = "external_model"
            reason = "provider_key_missing"
    elif requested == "agent_fallback":
        if fallback_available:
            resolved = "agent_fallback"
            status = "agent_fallback_scaffold_only"
        else:
            resolved = "deterministic_only"
            status = "deterministic_only_agent_fallback_unavailable"
            degraded_from = "agent_fallback"
            reason = "agent_fallback_unavailable"
    elif requested == "deterministic_only":
        resolved = "deterministic_only"
        status = "deterministic_only_by_env"
    elif key_visible and require_background_model_consent and not background_consent:
        resolved = "deterministic_only"
        status = "background_model_consent_required"
        degraded_from = "external_model"
        reason = "background_model_consent_required"
    elif key_visible:
        resolved = "external_model"
        status = "external_model_active"
    elif fallback_available:
        resolved = "agent_fallback"
        status = "agent_fallback_scaffold_only"
    else:
        resolved = "deterministic_only"
        status = "deterministic_only_missing_provider_and_agent"
        reason = "provider_key_and_agent_fallback_missing"

    return {
        "schema_version": 1,
        "kind": "aippocampus_cognitive_worker_mode",
        "requested_mode": requested,
        "resolved_mode": resolved,
        "status": status,
        "degraded_from": degraded_from,
        "reason": reason,
        "provider_key_visible": key_visible,
        "ambient_state": (
            "callable"
            if resolved == "agent_fallback"
            else "active"
            if resolved == "external_model"
            else "installed"
            if resolved == "deterministic_only"
            else "installed"
        ),
        "background_model_consent_required": bool(require_background_model_consent),
        "background_model_consent": bool(background_consent),
        "background_model_consent_env": BACKGROUND_MODEL_CONSENT_ENV,
        "agent_fallback_available": fallback_available,
        "agent_fallback_capability_env": AGENT_FALLBACK_AVAILABLE_ENV,
        "contracts": {
            "external_model_optional": True,
            "agent_fallback_manual_only": resolved == "agent_fallback",
            "queued_task_is_readiness_evidence": False,
            "queued_task_is_usefulness_evidence": False,
            "source_refs_required_before_promotion": True,
            "foreground_hook_waits_for_agent_fallback": False,
            "source_truth_unchanged": True,
        },
        "candidate_outputs": [
            "semantic_cue_candidate",
            "topic_epoch_candidate",
            "dream_residue_candidate",
            "cache_warmup_hint",
        ]
        if resolved == "agent_fallback"
        else [],
        "privacy": {
            "provider_key_value_checked": False,
            "provider_key_value_printed": False,
            "raw_source_text_included": False,
            "local_paths_included": False,
        },
    }
