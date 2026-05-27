#!/usr/bin/env python3
"""DeepSeek model routing policy for AIppocampus background work."""

from __future__ import annotations

import os
from dataclasses import dataclass

FLASH_ROUTES = {"", "default", "fast", "flash", "cheap", "background"}
PRO_ROUTES = {"pro", "slow_adjudication", "suppressed_label_recovery", "agentic_source_review"}
DEFAULT_FLASH_MODEL = "deepseek-v4-flash"
DEFAULT_PRO_MODEL = "deepseek-v4-pro"


@dataclass(frozen=True)
class ModelRoute:
    route: str
    tier: str
    model: str

    def as_dict(self) -> dict[str, str]:
        return {"route": self.route, "tier": self.tier, "model": self.model}


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


def resolve_model_route(route: str | None, *, explicit_model: str | None = None) -> ModelRoute:
    normalized = str(route or "default").strip() or "default"
    if explicit_model:
        return ModelRoute(route=normalized, tier="custom", model=explicit_model)
    if normalized in PRO_ROUTES:
        return ModelRoute(route=normalized, tier="pro", model=pro_model())
    if normalized in FLASH_ROUTES:
        return ModelRoute(route=normalized, tier="flash", model=flash_model())
    raise ValueError(f"unknown DeepSeek model route {normalized!r}")
