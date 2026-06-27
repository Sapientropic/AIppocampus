"""Input coercion helpers for Cognitive Observatory tools."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from aippocampus_runtime.core import dict_or_empty


def mapping_payload(value: Any, key: str | None = None) -> dict[str, Any] | None:
    payload = value.get(key) if key and isinstance(value, Mapping) else value
    clean = dict_or_empty(payload)
    return clean or None


__all__ = ["mapping_payload"]
