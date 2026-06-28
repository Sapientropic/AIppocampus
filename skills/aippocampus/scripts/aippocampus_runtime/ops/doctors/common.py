"""Shared small helpers for doctor projections."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def as_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}
