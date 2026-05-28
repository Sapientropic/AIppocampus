#!/usr/bin/env python3
"""Small OpenAI-compatible JSON chat client used by live model helpers."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from aippocampuslib import sanitize_external_model_payload, validate_private_credential_transport


@dataclass(frozen=True)
class ChatClientConfig:
    api_key: str
    model: str
    base_url: str
    max_tokens: int | None = None
    timeout: float = 60.0
    temperature: float = 0.0
    service_name: str = "OpenAI-compatible chat API"


def _chat_completions_url(config: ChatClientConfig) -> str:
    validate_private_credential_transport(
        config.base_url, service_name=config.service_name, credential_label="API key"
    )
    return config.base_url.rstrip("/") + "/chat/completions"


def chat_json(messages: list[dict[str, str]], config: ChatClientConfig) -> dict[str, Any]:
    url = _chat_completions_url(config)
    body: dict[str, Any] = {
        "model": config.model,
        "messages": sanitize_external_model_payload(messages),
        "temperature": config.temperature,
        "response_format": {"type": "json_object"},
    }
    if config.max_tokens is not None:
        body["max_tokens"] = config.max_tokens
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
