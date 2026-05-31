#!/usr/bin/env python3
"""Small OpenAI-compatible JSON chat client used by live model helpers."""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from aippocampus_runtime.core import (
    deepseek_cache_metrics_from_usage,
    sanitize_external_model_payload,
    validate_private_credential_transport,
)

DEEPSEEK_PREFIX_CACHE_CONTRACT = "deepseek_prefix_v1"
NO_PROVIDER_CACHE_CONTRACT = "none"
DEEPSEEK_KV_CACHE_GUIDE_URL = "https://api-docs.deepseek.com/zh-cn/guides/kv_cache"
VALID_CACHE_CONTRACTS = {DEEPSEEK_PREFIX_CACHE_CONTRACT, NO_PROVIDER_CACHE_CONTRACT}


@dataclass(frozen=True)
class ChatClientConfig:
    api_key: str
    model: str
    base_url: str
    max_tokens: int | None = None
    timeout: float = 60.0
    temperature: float = 0.0
    service_name: str = "OpenAI-compatible chat API"
    user_id: str | None = None
    thinking: str | None = None
    response_format_json: bool = True
    cache_contract: str | None = None


def _chat_completions_url(config: ChatClientConfig) -> str:
    validate_private_credential_transport(
        config.base_url, service_name=config.service_name, credential_label="API key"
    )
    return config.base_url.rstrip("/") + "/chat/completions"


def is_deepseek_config(config: ChatClientConfig) -> bool:
    model = config.model.strip().casefold()
    service_name = config.service_name.strip().casefold()
    base_url = config.base_url.strip().casefold()
    return model.startswith("deepseek") or "deepseek" in service_name or "deepseek" in base_url


def validate_cache_contract(config: ChatClientConfig) -> str | None:
    contract = config.cache_contract.strip() if config.cache_contract else None
    if contract is not None and contract not in VALID_CACHE_CONTRACTS:
        raise ValueError(
            f"cache_contract must be one of {sorted(VALID_CACHE_CONTRACTS)!r}; got {contract!r}"
        )
    if is_deepseek_config(config) and contract != DEEPSEEK_PREFIX_CACHE_CONTRACT:
        raise ValueError(
            "DeepSeek chat calls must set "
            f"cache_contract={DEEPSEEK_PREFIX_CACHE_CONTRACT!r}. "
            "DeepSeek's KV cache is automatic, but AIppocampus prompt builders "
            "must preserve stable-prefix ordering and usage telemetry; see "
            f"{DEEPSEEK_KV_CACHE_GUIDE_URL}."
        )
    return contract


def cache_metrics_from_response(
    response: dict[str, Any], config: ChatClientConfig
) -> dict[str, Any]:
    contract = validate_cache_contract(config)
    if contract == DEEPSEEK_PREFIX_CACHE_CONTRACT:
        metrics = deepseek_cache_metrics_from_usage(response.get("usage") or {})
        metrics["kind"] = "deepseek_prefix"
        return metrics
    return {"available": False, "kind": NO_PROVIDER_CACHE_CONTRACT}


def chat_json(messages: list[dict[str, str]], config: ChatClientConfig) -> dict[str, Any]:
    validate_cache_contract(config)
    url = _chat_completions_url(config)
    thinking = ""
    if config.thinking:
        thinking = config.thinking.strip().casefold()
        if thinking not in {"enabled", "disabled"}:
            raise ValueError("thinking must be 'enabled' or 'disabled'")
    body: dict[str, Any] = {
        "model": config.model,
        "messages": sanitize_external_model_payload(messages),
    }
    if config.response_format_json:
        body["response_format"] = {"type": "json_object"}
    if thinking != "enabled":
        body["temperature"] = config.temperature
    if config.max_tokens is not None:
        body["max_tokens"] = config.max_tokens
    if thinking:
        body["thinking"] = {"type": thinking}
    if config.user_id:
        if not re.fullmatch(r"[a-zA-Z0-9\-_]{1,512}", config.user_id):
            raise ValueError("user_id must match [a-zA-Z0-9\\-_]+ and be at most 512 chars")
        body["user_id"] = config.user_id
    req = urllib.request.Request(
        url,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {config.api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=config.timeout) as resp:
            response_body = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{config.service_name} HTTP {exc.code}: {detail[:500]}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"{config.service_name} request failed: {exc}") from exc
    return json.loads(response_body)
