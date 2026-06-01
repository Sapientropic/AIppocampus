"""Privacy and credential-transport guards for external runtime routes."""

from __future__ import annotations

import ipaddress
import re
from typing import Any
from urllib.parse import SplitResult, urlsplit

KEY_BLOCK_BOUNDARY = "-----"
GENERIC_PRIVATE_KEY_BLOCK = (
    rf"{KEY_BLOCK_BOUNDARY}BEGIN [A-Z ]*PRIVATE KEY{KEY_BLOCK_BOUNDARY}"
    rf".*?"
    rf"{KEY_BLOCK_BOUNDARY}END [A-Z ]*PRIVATE KEY{KEY_BLOCK_BOUNDARY}"
)
OPENSSH_PRIVATE_KEY_BLOCK = (
    rf"{KEY_BLOCK_BOUNDARY}BEGIN OPENSSH PRIVATE KEY{KEY_BLOCK_BOUNDARY}"
    rf".*?"
    rf"{KEY_BLOCK_BOUNDARY}END OPENSSH PRIVATE KEY{KEY_BLOCK_BOUNDARY}"
)

EXTERNAL_MODEL_HARD_SECRET_PATTERNS = [
    re.compile(pattern, re.IGNORECASE | re.DOTALL)
    for pattern in [
        GENERIC_PRIVATE_KEY_BLOCK,
        OPENSSH_PRIVATE_KEY_BLOCK,
    ]
]

EXTERNAL_MODEL_REDACTION_PATTERNS: list[tuple[str, re.Pattern[str], str]] = [
    (
        "openai_api_key",
        re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b", re.IGNORECASE),
        "<redacted:api-key>",
    ),
    (
        "bearer_token",
        re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{20,}", re.IGNORECASE),
        "Bearer <redacted:bearer-token>",
    ),
    (
        "credential_url",
        re.compile(r"\b([A-Za-z][A-Za-z0-9+.-]*://)[^@\s:/]+:[^@\s]+@"),
        r"\1<redacted:credentials>@",
    ),
    (
        "secret_assignment",
        re.compile(
            r"\b(api[_-]?key|secret|token|password|passwd|cookie|authorization)\b\s*[:=]\s*"
            r"(\"[^\"]*\"|'[^']*'|(?!(?:<redacted:))[^\s,;&]+)",
            re.IGNORECASE,
        ),
        r"\1=<redacted:secret>",
    ),
    (
        "json_escaped_windows_local_path",
        re.compile(r"(?<![\w])(?:[A-Za-z]:\\\\[^\"'\s<>]+)"),
        "<redacted:local-path>",
    ),
    (
        "windows_local_path",
        re.compile(
            r"(?<![\w])(?:[A-Za-z]:\\(?:[^\\/:*?\"<>|\r\n\t ]+\\?)+"
            r"[^\\/:*?\"<>|\r\n\t ]*)"
        ),
        "<redacted:local-path>",
    ),
    (
        "posix_local_path",
        re.compile(
            r"(?<![\w:/])/(?:Users|home|root|tmp|var|mnt|Volumes|private)/"
            r"(?:[^\s\"'<>]+)"
        ),
        "<redacted:local-path>",
    ),
]


def sanitize_external_model_text(text: str) -> tuple[str, dict[str, Any]]:
    """Redact likely secrets before automatic external-model calls.

    Clean source can include pasted credentials or machine-local paths. This
    helper is intentionally shared by all model-compatible routes so new
    workers do not accidentally bypass the prompt-hook privacy boundary.
    """

    original = str(text or "")
    hard_matches = [
        pattern.pattern
        for pattern in EXTERNAL_MODEL_HARD_SECRET_PATTERNS
        if pattern.search(original)
    ]
    if hard_matches:
        return "", {
            "redacted": True,
            "redaction_count": 0,
            "redaction_types": ["private_key_block"],
            "hard_block": True,
            "reason": "private key block detected",
        }

    sanitized = original
    redaction_types: list[str] = []
    redaction_count = 0
    for label, pattern, replacement in EXTERNAL_MODEL_REDACTION_PATTERNS:
        sanitized, count = pattern.subn(replacement, sanitized)
        if count:
            redaction_types.append(label)
            redaction_count += count

    remaining = re.sub(r"<redacted:[^>]+>", " ", sanitized)
    remaining = re.sub(r"\s+", " ", remaining).strip()
    hard_block = bool(redaction_count and len(remaining) < 12)
    return sanitized, {
        "redacted": bool(redaction_count),
        "redaction_count": redaction_count,
        "redaction_types": list(dict.fromkeys(redaction_types))[:8],
        "hard_block": hard_block,
        "reason": "prompt mostly secret/credential material after redaction" if hard_block else "",
    }


def sanitize_external_model_payload(value: Any) -> Any:
    if isinstance(value, str):
        sanitized, _ = sanitize_external_model_text(value)
        return sanitized
    if isinstance(value, list):
        return [sanitize_external_model_payload(item) for item in value]
    if isinstance(value, tuple):
        return tuple(sanitize_external_model_payload(item) for item in value)
    if isinstance(value, dict):
        return {key: sanitize_external_model_payload(item) for key, item in value.items()}
    return value


def is_loopback_host(hostname: str | None) -> bool:
    if not hostname:
        return False
    host = hostname.rstrip(".").casefold()
    if host == "localhost" or host.endswith(".localhost"):
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def validate_http_endpoint_url(endpoint_url: str, *, service_name: str) -> SplitResult:
    parsed = urlsplit(endpoint_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"{service_name} must be an http(s) URL")
    if parsed.username or parsed.password:
        raise ValueError(f"{service_name} must not include credentials")
    return parsed


def validate_private_credential_transport(
    endpoint_url: str, *, service_name: str, credential_label: str
) -> None:
    parsed = validate_http_endpoint_url(endpoint_url, service_name=service_name)
    # Local model proxies and dev object stores commonly use plain HTTP. Keep
    # that loopback path usable, but never let bearer-style credentials travel
    # over network HTTP because the receiving service may still look legitimate.
    if parsed.scheme == "http" and not is_loopback_host(parsed.hostname):
        raise ValueError(
            f"{credential_label} for {service_name} requires HTTPS unless endpoint is loopback"
        )


def deepseek_cache_metrics_from_usage(usage: dict[str, Any] | None) -> dict[str, Any]:
    usage = usage if isinstance(usage, dict) else {}
    hit = int(usage.get("prompt_cache_hit_tokens") or 0)
    miss = int(usage.get("prompt_cache_miss_tokens") or 0)
    total = hit + miss
    return {
        "available": "prompt_cache_hit_tokens" in usage or "prompt_cache_miss_tokens" in usage,
        "hit_tokens": hit,
        "miss_tokens": miss,
        "hit_rate": round(hit / total, 4) if total else 0.0,
    }
