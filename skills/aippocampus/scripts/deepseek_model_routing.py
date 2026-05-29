#!/usr/bin/env python3
"""External model routing policy for AIppocampus background work.

The public runtime is still DeepSeek-first today.  This module keeps that
compatibility while exposing provider/capability metadata so later semantic
workers can gate provider-specific request fields instead of assuming every
OpenAI-compatible endpoint behaves like DeepSeek.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

FLASH_ROUTES = {"", "default", "fast", "flash", "cheap", "background"}
PRO_ROUTES = {"pro", "slow_adjudication", "suppressed_label_recovery", "agentic_source_review"}
DEFAULT_FLASH_MODEL = "deepseek-v4-flash"
DEFAULT_PRO_MODEL = "deepseek-v4-pro"
DEFAULT_DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEFAULT_DEEPSEEK_API_KEY_ENV = "DEEPSEEK_API_KEY"
OPENAI_COMPAT_ROUTE_FALLBACKS = {"openai_compatible", "external", "custom_openai"}


def env_truthy(name: str, *, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None or not value.strip():
        return default
    return value.strip().casefold() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class ModelCapabilities:
    api_compatibility: str
    supports_json_response: bool
    supports_user_id: bool
    supports_thinking: bool
    cache_metrics_kind: str
    safe_default_concurrency: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "api_compatibility": self.api_compatibility,
            "supports_json_response": self.supports_json_response,
            "supports_user_id": self.supports_user_id,
            "supports_thinking": self.supports_thinking,
            "cache_metrics_kind": self.cache_metrics_kind,
            "safe_default_concurrency": self.safe_default_concurrency,
        }


@dataclass(frozen=True)
class ModelRoute:
    route: str
    tier: str
    model: str
    provider: str = "deepseek"
    base_url: str = DEFAULT_DEEPSEEK_BASE_URL
    api_key_env: str = DEFAULT_DEEPSEEK_API_KEY_ENV
    capabilities: ModelCapabilities | None = None

    def as_dict(self) -> dict[str, Any]:
        capabilities = self.capabilities or deepseek_capabilities(self.tier)
        return {
            "route": self.route,
            "tier": self.tier,
            "model": self.model,
            "provider": self.provider,
            "base_url": self.base_url,
            "api_key_env": self.api_key_env,
            "capabilities": capabilities.as_dict(),
        }


def deepseek_base_url() -> str:
    return (
        os.environ.get("AIPPOCAMPUS_DEEPSEEK_BASE_URL")
        or os.environ.get("DEEPSEEK_BASE_URL")
        or DEFAULT_DEEPSEEK_BASE_URL
    )


def flash_model() -> str:
    return (
        os.environ.get("AIPPOCAMPUS_DEEPSEEK_FLASH_MODEL")
        or os.environ.get("DEEPSEEK_MODEL")
        or DEFAULT_FLASH_MODEL
    )


def pro_model() -> str:
    return (
        os.environ.get("AIPPOCAMPUS_DEEPSEEK_PRO_MODEL")
        or os.environ.get("DEEPSEEK_PRO_MODEL")
        or DEFAULT_PRO_MODEL
    )


def deepseek_capabilities(tier: str) -> ModelCapabilities:
    return ModelCapabilities(
        api_compatibility="openai_chat_completions",
        supports_json_response=True,
        supports_user_id=True,
        supports_thinking=True,
        cache_metrics_kind="deepseek_prefix",
        safe_default_concurrency=1 if tier == "pro" else 4,
    )


def deepseek_route(route: str, tier: str, model: str) -> ModelRoute:
    return ModelRoute(
        route=route,
        tier=tier,
        model=model,
        provider="deepseek",
        base_url=deepseek_base_url(),
        api_key_env=DEFAULT_DEEPSEEK_API_KEY_ENV,
        capabilities=deepseek_capabilities(tier),
    )


def configured_openai_compatible_route_names() -> set[str]:
    configured_route = os.environ.get("AIPPOCAMPUS_OPENAI_COMPAT_ROUTE", "").strip()
    provider = os.environ.get("AIPPOCAMPUS_OPENAI_COMPAT_PROVIDER", "").strip()
    names = set(OPENAI_COMPAT_ROUTE_FALLBACKS)
    if configured_route:
        names.add(configured_route)
    if provider:
        names.add(provider)
    return names


def configured_openai_compatible_route(route: str) -> ModelRoute:
    provider = os.environ.get("AIPPOCAMPUS_OPENAI_COMPAT_PROVIDER", "").strip()
    model = os.environ.get("AIPPOCAMPUS_OPENAI_COMPAT_MODEL", "").strip()
    base_url = os.environ.get("AIPPOCAMPUS_OPENAI_COMPAT_BASE_URL", "").strip()
    api_key_env = os.environ.get("AIPPOCAMPUS_OPENAI_COMPAT_API_KEY_ENV", "").strip()
    missing = [
        name
        for name, value in [
            ("AIPPOCAMPUS_OPENAI_COMPAT_PROVIDER", provider),
            ("AIPPOCAMPUS_OPENAI_COMPAT_MODEL", model),
            ("AIPPOCAMPUS_OPENAI_COMPAT_BASE_URL", base_url),
            ("AIPPOCAMPUS_OPENAI_COMPAT_API_KEY_ENV", api_key_env),
        ]
        if not value
    ]
    if missing:
        raise ValueError(
            f"openai-compatible route {route!r} requires {', '.join(missing)}"
        )
    concurrency_raw = os.environ.get("AIPPOCAMPUS_OPENAI_COMPAT_CONCURRENCY", "1").strip()
    try:
        safe_default_concurrency = max(1, int(concurrency_raw))
    except ValueError as exc:
        raise ValueError(
            "AIPPOCAMPUS_OPENAI_COMPAT_CONCURRENCY must be a positive integer"
        ) from exc
    return ModelRoute(
        route=route,
        tier="openai_compatible",
        model=model,
        provider=provider,
        base_url=base_url,
        api_key_env=api_key_env,
        capabilities=ModelCapabilities(
            api_compatibility="openai_chat_completions",
            supports_json_response=env_truthy(
                "AIPPOCAMPUS_OPENAI_COMPAT_SUPPORTS_JSON", default=True
            ),
            supports_user_id=env_truthy(
                "AIPPOCAMPUS_OPENAI_COMPAT_SUPPORTS_USER_ID", default=False
            ),
            supports_thinking=env_truthy(
                "AIPPOCAMPUS_OPENAI_COMPAT_SUPPORTS_THINKING", default=False
            ),
            cache_metrics_kind=os.environ.get(
                "AIPPOCAMPUS_OPENAI_COMPAT_CACHE_METRICS_KIND", "none"
            ).strip()
            or "none",
            safe_default_concurrency=safe_default_concurrency,
        ),
    )


def resolve_model_route(route: str | None, *, explicit_model: str | None = None) -> ModelRoute:
    normalized = str(route or "default").strip() or "default"
    if explicit_model:
        return deepseek_route(normalized, "custom", explicit_model)
    if normalized in PRO_ROUTES:
        return deepseek_route(normalized, "pro", pro_model())
    if normalized in FLASH_ROUTES:
        return deepseek_route(normalized, "flash", flash_model())
    if normalized in configured_openai_compatible_route_names():
        return configured_openai_compatible_route(normalized)
    raise ValueError(f"unknown external model route {normalized!r}")
