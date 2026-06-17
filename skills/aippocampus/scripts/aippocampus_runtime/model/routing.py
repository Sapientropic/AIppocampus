#!/usr/bin/env python3
"""External model routing policy for AIppocampus background work.

The public runtime is still DeepSeek-first today.  This module keeps that
compatibility while exposing provider/capability metadata so later semantic
workers can gate provider-specific request fields instead of assuming every
OpenAI-compatible endpoint behaves like DeepSeek.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from aippocampus_runtime.core import deepseek_cache_metrics_from_usage

FLASH_ROUTES = {"", "default", "fast", "flash", "cheap", "background"}
PRO_ROUTES = {"pro", "slow_adjudication", "suppressed_label_recovery", "agentic_source_review"}
DEFAULT_FLASH_MODEL = "deepseek-v4-flash"
DEFAULT_PRO_MODEL = "deepseek-v4-pro"
DEFAULT_DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEFAULT_DEEPSEEK_API_KEY_ENV = "AIPPOCAMPUS_DEEPSEEK_API_KEY"
LEGACY_DEEPSEEK_API_KEY_ENV = "DEEPSEEK_API_KEY"
DEFAULT_DEEPSEEK_THINKING = "enabled"
DEFAULT_DEEPSEEK_REASONING_EFFORT = "high"
DEEPSEEK_PREFIX_CACHE_CONTRACT = "deepseek_prefix_v1"
NO_PROVIDER_CACHE_CONTRACT = "none"
OPENAI_COMPAT_ROUTE_FALLBACKS = {"openai_compatible", "external", "custom_openai"}
EXPLICIT_OPENAI_COMPAT_ROUTE = "explicit_openai_compatible"
VALID_THINKING_MODES = {"enabled", "disabled"}
VALID_REASONING_EFFORTS = {"high", "max"}
SUPPORTED_CACHE_CONTRACT_METRIC_KINDS = {
    "deepseek_prefix": DEEPSEEK_PREFIX_CACHE_CONTRACT,
    "none": NO_PROVIDER_CACHE_CONTRACT,
}

MODEL_CALL_SITE_CACHE_CONTRACT_INVENTORY: tuple[dict[str, str], ...] = (
    {
        "call_site": "subconscious.agent",
        "path": "skills/aippocampus/scripts/aippocampus_runtime/subconscious/agent.py",
        "owner": "subconscious_agent",
        "purpose": "tool-using concept-edge proposal over clean source",
        "route_source": "DeepSeek CLI defaults",
        "cache_contract": DEEPSEEK_PREFIX_CACHE_CONTRACT,
        "usage_telemetry": "tool loop usage_total plus DeepSeek prefix cache metrics",
    },
    {
        "call_site": "subconscious.review",
        "path": "skills/aippocampus/scripts/aippocampus_runtime/subconscious/review.py",
        "owner": "subconscious_review",
        "purpose": "promotion-candidate review over staged findings",
        "route_source": "resolve_model_route",
        "cache_contract": "route_cache_contract(route)",
        "usage_telemetry": "compact usage plus route_cache_metrics",
    },
    {
        "call_site": "semantic_scope_suppressed_recovery",
        "path": (
            "skills/aippocampus/scripts/aippocampus_runtime/source/"
            "semantic_scope_suppressed_recovery.py"
        ),
        "owner": "source_semantic_scope",
        "purpose": "slow adjudication of suppressed semantic sidecar labels",
        "route_source": "resolve_model_route",
        "cache_contract": "route_cache_contract(route)",
        "usage_telemetry": "aggregate compact usage plus route_cache_metrics",
    },
    {
        "call_site": "public_semantic_sidecar_labeler",
        "path": "benchmarks/aippocampus/source_evidence/public_semantic.py",
        "owner": "benchmark_public_semantic",
        "purpose": "public semantic-sidecar candidate labeling",
        "route_source": "DeepSeek benchmark defaults",
        "cache_contract": DEEPSEEK_PREFIX_CACHE_CONTRACT,
        "usage_telemetry": "sanitized compact usage in benchmark labeler metadata",
    },
    {
        "call_site": "standard_public_line_reranker",
        "path": "benchmarks/aippocampus/source_evidence/standard_public.py",
        "owner": "benchmark_source_evidence",
        "purpose": "provider-backed public source-line reranking",
        "route_source": "semantic_line_reranker_public_contract",
        "cache_contract": "provider-derived DeepSeek prefix or none",
        "usage_telemetry": "usage, latency_ms, and provider cache summary",
    },
    {
        "call_site": "locomo_fixed_reader",
        "path": "benchmarks/aippocampus/benchmark_locomo_qa.py",
        "owner": "benchmark_locomo_qa",
        "purpose": "fixed reader answer/latency arm over bounded LoCoMo source lines",
        "route_source": "reader_config provider detection",
        "cache_contract": "provider-derived DeepSeek prefix or none",
        "usage_telemetry": "reader usage, latency_ms, cost fields, and cache summary",
    },
    {
        "call_site": "longmemeval_fixed_reader",
        "path": "benchmarks/aippocampus/benchmark_longmemeval_answer.py",
        "owner": "benchmark_longmemeval_answer",
        "purpose": "fixed reader answer/latency arm over bounded LongMemEval source lines",
        "route_source": "reader_config provider detection",
        "cache_contract": "provider-derived DeepSeek prefix or none",
        "usage_telemetry": "reader usage, latency_ms, cost fields, and cache summary",
    },
    {
        "call_site": "dream_sleep_cycle",
        "path": "skills/aippocampus/scripts/aippocampus_runtime/dream/sleep_cycle.py",
        "owner": "dream_scheduler",
        "purpose": "detached model-backed dream worker execution",
        "route_source": "resolve_model_route",
        "cache_contract": "route_cache_contract(route)",
        "usage_telemetry": "queue lifecycle usage/cache projection",
    },
    {
        "call_site": "dream_real_history_eval",
        "path": "skills/aippocampus/scripts/aippocampus_runtime/dream/real_history_eval.py",
        "owner": "dream_eval",
        "purpose": "selected real-history dream-pack model-backed evaluation",
        "route_source": "resolve_model_route",
        "cache_contract": "route_cache_contract(route)",
        "usage_telemetry": "model run usage/cache diagnostics",
    },
    {
        "call_site": "dream_live_shadow_ab",
        "path": "skills/aippocampus/scripts/aippocampus_runtime/dream/live_shadow_ab.py",
        "owner": "dream_shadow_ab",
        "purpose": "live shadow A/B semantic relevance model arm",
        "route_source": "resolve_model_route",
        "cache_contract": "route_cache_contract(route)",
        "usage_telemetry": "shadow event model metadata and usage summaries",
    },
    {
        "call_site": "question_confirmation_live",
        "path": "skills/aippocampus/scripts/aippocampus_runtime/question/confirmation_live.py",
        "owner": "question_tracking",
        "purpose": "optional live confirmation for borderline question-pair requests",
        "route_source": "resolve_model_route",
        "cache_contract": "route_cache_contract(route)",
        "usage_telemetry": "per-request route_cache_metrics summaries",
    },
)


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
    supports_reasoning_effort: bool = False
    default_thinking: str | None = None
    default_reasoning_effort: str | None = None
    reasoning_content_handling: str = "discard_without_storage"

    def as_dict(self) -> dict[str, Any]:
        return {
            "api_compatibility": self.api_compatibility,
            "supports_json_response": self.supports_json_response,
            "supports_user_id": self.supports_user_id,
            "supports_thinking": self.supports_thinking,
            "cache_metrics_kind": self.cache_metrics_kind,
            "safe_default_concurrency": self.safe_default_concurrency,
            "supports_reasoning_effort": self.supports_reasoning_effort,
            "default_thinking": self.default_thinking,
            "default_reasoning_effort": self.default_reasoning_effort,
            "reasoning_content_handling": self.reasoning_content_handling,
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


def deepseek_api_key_env(env: Mapping[str, str] | None = None) -> str:
    """Return the public env-var name to use for DeepSeek credentials.

    The canonical AIppocampus-prefixed name must be the default so diagnostics
    and hook setup do not teach users to keep provider-specific globals around.
    We keep the legacy DeepSeek name as a presence-only migration fallback for
    existing installs; do not switch this to value checks, because provider
    readiness surfaces intentionally avoid reading key material unless a model
    call is explicitly being made.
    """

    current_env = env if env is not None else os.environ
    if DEFAULT_DEEPSEEK_API_KEY_ENV in current_env:
        return DEFAULT_DEEPSEEK_API_KEY_ENV
    if LEGACY_DEEPSEEK_API_KEY_ENV in current_env:
        return LEGACY_DEEPSEEK_API_KEY_ENV
    return DEFAULT_DEEPSEEK_API_KEY_ENV


def is_default_deepseek_api_key_env(value: str | None) -> bool:
    """Return true when an api-key-env argument means "use the DeepSeek default".

    Older call sites baked `DEEPSEEK_API_KEY` in their argparse defaults before
    the public `AIPPOCAMPUS_*` prefix existed. Treat both spellings as the
    route default so model-route configuration can still supply its own key env
    and so legacy callers do not accidentally override custom routes.
    """

    raw = str(value or "").strip()
    return raw in {"", DEFAULT_DEEPSEEK_API_KEY_ENV, LEGACY_DEEPSEEK_API_KEY_ENV}


def deepseek_capabilities(tier: str) -> ModelCapabilities:
    return ModelCapabilities(
        api_compatibility="openai_chat_completions",
        supports_json_response=True,
        supports_user_id=True,
        supports_thinking=True,
        cache_metrics_kind="deepseek_prefix",
        safe_default_concurrency=1 if tier == "pro" else 4,
        supports_reasoning_effort=True,
        default_thinking=DEFAULT_DEEPSEEK_THINKING,
        default_reasoning_effort=DEFAULT_DEEPSEEK_REASONING_EFFORT,
    )


def normalize_thinking_mode(value: str | None, *, allow_provider: bool = True) -> str | None:
    raw = str(value or "").strip().casefold()
    if allow_provider and raw in {"", "auto", "provider", "default", "none"}:
        return None
    if raw not in VALID_THINKING_MODES:
        raise ValueError("thinking must be enabled, disabled, or provider/default")
    return raw


def normalize_reasoning_effort(value: str | None, *, allow_provider: bool = True) -> str | None:
    raw = str(value or "").strip().casefold()
    if allow_provider and raw in {"", "auto", "provider", "default", "none"}:
        return None
    if raw not in VALID_REASONING_EFFORTS:
        raise ValueError("reasoning_effort must be high, max, or provider/default")
    return raw


def resolve_route_thinking(route: ModelRoute, requested: str | None = "auto") -> str | None:
    capabilities = route.capabilities or deepseek_capabilities(route.tier)
    if not capabilities.supports_thinking:
        return None
    requested_value = normalize_thinking_mode(requested)
    default_value = normalize_thinking_mode(capabilities.default_thinking)
    return requested_value if requested_value is not None else default_value


def resolve_route_reasoning_effort(
    route: ModelRoute,
    requested: str | None = "auto",
    *,
    thinking: str | None,
) -> str | None:
    capabilities = route.capabilities or deepseek_capabilities(route.tier)
    if not capabilities.supports_reasoning_effort:
        return None
    if thinking == "disabled":
        return None
    requested_value = normalize_reasoning_effort(requested)
    default_value = normalize_reasoning_effort(capabilities.default_reasoning_effort)
    return requested_value if requested_value is not None else default_value


def deepseek_route(route: str, tier: str, model: str) -> ModelRoute:
    return ModelRoute(
        route=route,
        tier=tier,
        model=model,
        provider="deepseek",
        base_url=deepseek_base_url(),
        api_key_env=deepseek_api_key_env(),
        capabilities=deepseek_capabilities(tier),
    )


def conservative_openai_compatible_route(
    route: str,
    *,
    model: str,
    base_url: str,
    api_key_env: str,
    provider: str = "openai-compatible",
) -> ModelRoute:
    return ModelRoute(
        route=route,
        tier="openai_compatible",
        model=model,
        provider=provider,
        base_url=base_url,
        api_key_env=api_key_env,
        capabilities=ModelCapabilities(
            api_compatibility="openai_chat_completions",
            supports_json_response=True,
            supports_user_id=False,
            supports_thinking=False,
            cache_metrics_kind="none",
            safe_default_concurrency=1,
            reasoning_content_handling="not_supported",
        ),
    )


def route_service_name(route: ModelRoute) -> str:
    if route.provider == "deepseek":
        return "DeepSeek API"
    provider = route.provider.strip() or "OpenAI-compatible"
    return f"{provider} OpenAI-compatible API"


def route_cache_metrics(route: ModelRoute, usage: dict[str, Any]) -> dict[str, Any]:
    capabilities = route.capabilities or deepseek_capabilities(route.tier)
    kind = capabilities.cache_metrics_kind or "none"
    if kind == "deepseek_prefix":
        result = deepseek_cache_metrics_from_usage(usage)
        result["kind"] = kind
        return result
    return {"available": False, "kind": kind}


def route_cache_contract(route: ModelRoute) -> str:
    capabilities = route.capabilities or deepseek_capabilities(route.tier)
    kind = capabilities.cache_metrics_kind or "none"
    if route.provider == "deepseek" or kind == "deepseek_prefix":
        return DEEPSEEK_PREFIX_CACHE_CONTRACT
    return SUPPORTED_CACHE_CONTRACT_METRIC_KINDS.get(kind, NO_PROVIDER_CACHE_CONTRACT)


def model_call_site_cache_contract_inventory() -> tuple[dict[str, str], ...]:
    return tuple(dict(item) for item in MODEL_CALL_SITE_CACHE_CONTRACT_INVENTORY)


def route_payload_with_effective_values(
    route: ModelRoute,
    *,
    model: str,
    base_url: str,
    api_key_env: str,
) -> dict[str, Any]:
    payload = route.as_dict()
    payload["model"] = model
    payload["base_url"] = base_url
    payload["api_key_env"] = api_key_env
    payload["cache_contract"] = route_cache_contract(route)
    return payload


def route_artifact_source(route: ModelRoute, suffix: str) -> str:
    prefix = "deepseek" if route.provider == "deepseek" else "external_model"
    return f"{prefix}_{suffix}"


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
            supports_reasoning_effort=env_truthy(
                "AIPPOCAMPUS_OPENAI_COMPAT_SUPPORTS_REASONING_EFFORT", default=False
            ),
            default_thinking=normalize_thinking_mode(
                os.environ.get("AIPPOCAMPUS_OPENAI_COMPAT_DEFAULT_THINKING")
            ),
            default_reasoning_effort=normalize_reasoning_effort(
                os.environ.get("AIPPOCAMPUS_OPENAI_COMPAT_DEFAULT_REASONING_EFFORT")
            ),
            reasoning_content_handling=(
                os.environ.get("AIPPOCAMPUS_OPENAI_COMPAT_REASONING_CONTENT_HANDLING", "")
                .strip()
                or "not_supported"
            ),
        ),
    )


def resolve_model_route(
    route: str | None,
    *,
    explicit_model: str | None = None,
    explicit_base_url: str | None = None,
    explicit_api_key_env: str | None = None,
) -> ModelRoute:
    normalized = str(route or "default").strip() or "default"
    custom_base_url = str(explicit_base_url or "").strip()
    custom_api_key_env = str(explicit_api_key_env or "").strip()
    explicit_model_name = explicit_model or flash_model()
    if not route and custom_base_url and not explicit_model_name.startswith("deepseek"):
        return conservative_openai_compatible_route(
            EXPLICIT_OPENAI_COMPAT_ROUTE,
            model=explicit_model_name,
            base_url=custom_base_url or deepseek_base_url(),
            api_key_env=custom_api_key_env or deepseek_api_key_env(),
        )
    if explicit_model:
        return deepseek_route(normalized, "custom", explicit_model)
    if normalized in PRO_ROUTES:
        return deepseek_route(normalized, "pro", pro_model())
    if normalized in FLASH_ROUTES:
        return deepseek_route(normalized, "flash", flash_model())
    if normalized in configured_openai_compatible_route_names():
        return configured_openai_compatible_route(normalized)
    raise ValueError(f"unknown external model route {normalized!r}")
