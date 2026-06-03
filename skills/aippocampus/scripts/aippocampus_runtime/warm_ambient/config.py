"""Typed configuration boundaries for warm ambient recall."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping

WARM_RECALL_OPERATOR_ENV_VARS = (
    "AIPPOCAMPUS_WARM_RECALL_TIMEOUT",
    "AIPPOCAMPUS_WARM_RECALL_CATALOG_LIMIT",
    "AIPPOCAMPUS_WARM_RECALL_MAX_WORKERS",
)
WARM_RECALL_PRODUCT_TUNING_ENV_VARS = (
    "AIPPOCAMPUS_WARM_RECALL_TEMPERATURE",
    "AIPPOCAMPUS_WARM_RECALL_THINKING",
    "AIPPOCAMPUS_WARM_RECALL_REASONING_EFFORT",
    "AIPPOCAMPUS_WARM_RECALL_QUORUM",
    "AIPPOCAMPUS_WARM_PREFIX_CACHE_WARMUP_SCOUTS",
    "AIPPOCAMPUS_WARM_PREFIX_CACHE_WARMUP_DELAY",
)
WARM_DETACHED_OPERATOR_ENV_VARS = (
    "AIPPOCAMPUS_DETACHED_WARM_TIMEOUT",
    "AIPPOCAMPUS_DETACHED_WARM_PREFIX_CACHE_WARMUP_SCOUTS",
    "AIPPOCAMPUS_DETACHED_WARM_PREFIX_CACHE_WARMUP_DELAY",
)


@dataclass(frozen=True)
class WarmRecallConfig:
    timeout: float = 1.8
    quorum: int = 3
    max_cards: int = 3
    max_catalog_items: int = 64
    temperature: float = 0.2
    thinking: str = "enabled"
    reasoning_effort: str | None = None
    max_workers: int | None = None
    prefix_cache_warmup_scouts: int = 0
    prefix_cache_warmup_delay: float = 0.0

    def with_overrides(
        self,
        *,
        timeout: float | None = None,
        quorum: int | None = None,
        max_cards: int | None = None,
        max_catalog_items: int | None = None,
        temperature: float | None = None,
        thinking: str | None = None,
        reasoning_effort: str | None = None,
        max_workers: int | None = None,
        prefix_cache_warmup_scouts: int | None = None,
        prefix_cache_warmup_delay: float | None = None,
    ) -> WarmRecallConfig:
        return WarmRecallConfig(
            timeout=self.timeout if timeout is None else float(timeout),
            quorum=self.quorum if quorum is None else int(quorum),
            max_cards=self.max_cards if max_cards is None else int(max_cards),
            max_catalog_items=(
                self.max_catalog_items
                if max_catalog_items is None
                else int(max_catalog_items)
            ),
            temperature=self.temperature if temperature is None else float(temperature),
            thinking=self.thinking if thinking is None else str(thinking),
            reasoning_effort=(
                self.reasoning_effort if reasoning_effort is None else str(reasoning_effort)
            ),
            max_workers=self.max_workers if max_workers is None else int(max_workers),
            prefix_cache_warmup_scouts=(
                self.prefix_cache_warmup_scouts
                if prefix_cache_warmup_scouts is None
                else int(prefix_cache_warmup_scouts)
            ),
            prefix_cache_warmup_delay=(
                self.prefix_cache_warmup_delay
                if prefix_cache_warmup_delay is None
                else float(prefix_cache_warmup_delay)
            ),
        )


@dataclass(frozen=True)
class WarmDetachedJobConfig:
    timeout: float = 45.0
    prefix_cache_warmup_scouts: int = 2
    prefix_cache_warmup_delay: float = 0.5

    def with_overrides(
        self,
        *,
        timeout: float | None = None,
        prefix_cache_warmup_scouts: int | None = None,
        prefix_cache_warmup_delay: float | None = None,
    ) -> WarmDetachedJobConfig:
        return WarmDetachedJobConfig(
            timeout=self.timeout if timeout is None else float(timeout),
            prefix_cache_warmup_scouts=(
                self.prefix_cache_warmup_scouts
                if prefix_cache_warmup_scouts is None
                else int(prefix_cache_warmup_scouts)
            ),
            prefix_cache_warmup_delay=(
                self.prefix_cache_warmup_delay
                if prefix_cache_warmup_delay is None
                else float(prefix_cache_warmup_delay)
            ),
        )


DEFAULT_WARM_RECALL_CONFIG = WarmRecallConfig()
DEFAULT_WARM_DETACHED_JOB_CONFIG = WarmDetachedJobConfig()


def _env_float(env: Mapping[str, str], name: str) -> float | None:
    raw = str(env.get(name) or "").strip()
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _env_positive_int(env: Mapping[str, str], name: str) -> int | None:
    raw = str(env.get(name) or "").strip()
    if not raw:
        return None
    try:
        value = int(raw)
    except ValueError:
        return None
    return value if value > 0 else None


def warm_recall_config_from_env(
    env: Mapping[str, str] | None = None,
    *,
    base: WarmRecallConfig = DEFAULT_WARM_RECALL_CONFIG,
) -> WarmRecallConfig:
    """Resolve only operator-facing env knobs into the typed warm config.

    Product-tuning values such as temperature, quorum, thinking mode, and
    prefix-cache warmup are deliberately excluded from this implicit env path.
    They must be passed through explicit config or CLI flags so future changes
    cannot quietly alter the source-backed warm-recall semantics.
    """

    source = os.environ if env is None else env
    return base.with_overrides(
        timeout=_env_float(source, "AIPPOCAMPUS_WARM_RECALL_TIMEOUT"),
        max_catalog_items=_env_positive_int(
            source, "AIPPOCAMPUS_WARM_RECALL_CATALOG_LIMIT"
        ),
        max_workers=_env_positive_int(source, "AIPPOCAMPUS_WARM_RECALL_MAX_WORKERS"),
    )


def warm_detached_job_config_from_env(
    env: Mapping[str, str] | None = None,
    *,
    base: WarmDetachedJobConfig = DEFAULT_WARM_DETACHED_JOB_CONFIG,
) -> WarmDetachedJobConfig:
    source = os.environ if env is None else env
    return base.with_overrides(
        timeout=_env_float(source, "AIPPOCAMPUS_DETACHED_WARM_TIMEOUT"),
        prefix_cache_warmup_scouts=_env_positive_int(
            source, "AIPPOCAMPUS_DETACHED_WARM_PREFIX_CACHE_WARMUP_SCOUTS"
        ),
        prefix_cache_warmup_delay=_env_float(
            source, "AIPPOCAMPUS_DETACHED_WARM_PREFIX_CACHE_WARMUP_DELAY"
        ),
    )
