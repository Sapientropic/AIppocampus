"""Warm ambient scout error vocabulary."""

from __future__ import annotations

from typing import Any


def scout_error_kind(reason: Any) -> str:
    text = str(reason or "").casefold()
    if "429" in text or "rate limit" in text or "rate_limited" in text:
        return "rate_limited_429"
    if "503" in text or "service_unavailable" in text or "too busy" in text:
        return "service_unavailable_503"
    if "502" in text or "504" in text or "bad gateway" in text or "gateway timeout" in text:
        return "provider_5xx"
    if "timeout" in text or "timed out" in text:
        return "read_timeout"
    if "json" in text or "parse" in text or "decode" in text:
        return "invalid_json"
    if "401" in text or "403" in text or "auth" in text or "api key" in text:
        return "auth_error"
    if "connect" in text or "connection" in text or "network" in text or "urlerror" in text:
        return "connection_error"
    return "scout_error"
