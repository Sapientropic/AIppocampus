"""Shared budget contract for optional provider-backed benchmark runs."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "provider-execution-budget-v0"


@dataclass(frozen=True)
class ProviderExecutionBudget:
    benchmark_id: str
    live_mode: bool
    max_units: int
    per_case_timeout_seconds: int | None
    max_provider_calls: int | None
    max_prompt_tokens: int | None
    max_completion_tokens: int | None
    max_total_tokens: int | None
    max_estimated_cost_usd: float | None
    cost_unknown: bool
    checkpoint_path_declared: bool
    partial_output_path_declared: bool
    provider: str
    model: str
    base_url_sha1: str


def sha1_text(value: str) -> str:
    return hashlib.sha1(str(value).encode("utf-8")).hexdigest()[:16]


def path_declared(value: str | Path | None) -> bool:
    return bool(str(value or "").strip())


def build_provider_execution_budget(
    *,
    benchmark_id: str,
    live_mode: bool,
    max_units: int,
    per_case_timeout_seconds: int | None,
    max_provider_calls: int | None = None,
    max_prompt_tokens: int | None = None,
    max_completion_tokens: int | None = None,
    max_total_tokens: int | None = None,
    max_estimated_cost_usd: float | None = None,
    cost_unknown: bool = False,
    checkpoint_path: str | Path | None = None,
    partial_output_path: str | Path | None = None,
    provider: str = "unknown",
    model: str = "unknown",
    base_url: str | None = None,
    base_url_sha1: str | None = None,
) -> ProviderExecutionBudget:
    return ProviderExecutionBudget(
        benchmark_id=str(benchmark_id),
        live_mode=bool(live_mode),
        max_units=max(0, int(max_units or 0)),
        per_case_timeout_seconds=(
            None
            if per_case_timeout_seconds is None
            else max(0, int(per_case_timeout_seconds))
        ),
        max_provider_calls=(
            None if max_provider_calls is None else max(0, int(max_provider_calls))
        ),
        max_prompt_tokens=(
            None if max_prompt_tokens is None else max(0, int(max_prompt_tokens))
        ),
        max_completion_tokens=(
            None
            if max_completion_tokens is None
            else max(0, int(max_completion_tokens))
        ),
        max_total_tokens=(
            None if max_total_tokens is None else max(0, int(max_total_tokens))
        ),
        max_estimated_cost_usd=(
            None
            if max_estimated_cost_usd is None
            else max(0.0, float(max_estimated_cost_usd))
        ),
        cost_unknown=bool(cost_unknown),
        checkpoint_path_declared=path_declared(checkpoint_path),
        partial_output_path_declared=path_declared(partial_output_path),
        provider=str(provider or "unknown"),
        model=str(model or "unknown"),
        base_url_sha1=str(base_url_sha1 or sha1_text(base_url or "")),
    )


def has_token_or_cost_budget(config: ProviderExecutionBudget) -> bool:
    return bool(
        config.max_prompt_tokens is not None
        or config.max_completion_tokens is not None
        or config.max_total_tokens is not None
        or config.max_estimated_cost_usd is not None
        or config.cost_unknown
    )


def validate_provider_execution_budget(config: ProviderExecutionBudget) -> list[str]:
    if not config.live_mode:
        return []
    errors: list[str] = []
    if config.max_units <= 0:
        errors.append("missing_case_cap")
    if not config.per_case_timeout_seconds:
        errors.append("missing_per_case_timeout")
    if config.max_provider_calls is None:
        errors.append("missing_provider_call_cap")
    elif config.max_provider_calls < config.max_units:
        errors.append("provider_call_cap_below_case_cap")
    if not has_token_or_cost_budget(config):
        errors.append("missing_token_or_cost_budget")
    if not config.checkpoint_path_declared:
        errors.append("missing_checkpoint_path")
    if not config.partial_output_path_declared:
        errors.append("missing_partial_output_path")
    return errors


def usage_totals(usage: dict[str, Any] | None) -> dict[str, int]:
    usage = usage or {}
    prompt = int(usage.get("prompt_tokens") or 0)
    completion = int(usage.get("completion_tokens") or 0)
    total = int(usage.get("total_tokens") or (prompt + completion))
    return {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": total,
    }


def cache_usage_totals(cache_usage: dict[str, Any] | None) -> dict[str, Any]:
    cache_usage = cache_usage or {}
    safe: dict[str, Any] = {}
    for key, value in cache_usage.items():
        if isinstance(value, bool):
            safe[str(key)] = value
        elif isinstance(value, int):
            safe[str(key)] = int(value)
        elif isinstance(value, float):
            safe[str(key)] = round(float(value), 6)
        elif isinstance(value, str):
            safe[str(key)] = value[:120]
    return safe


def provider_execution_budget_summary(
    config: ProviderExecutionBudget,
    *,
    completed_units: int = 0,
    skipped_or_resumed_units: int = 0,
    failed_units: int = 0,
    timed_out_units: int = 0,
    elapsed_ms: float | int = 0,
    usage: dict[str, Any] | None = None,
    cache_usage: dict[str, Any] | None = None,
    estimated_cost_usd: float | None = None,
    cost_unavailable_reason: str | None = None,
    stop_reason: str = "not_started",
    validation_errors: list[str] | None = None,
) -> dict[str, Any]:
    usage_summary = usage_totals(usage)
    cost_status = (
        "estimated"
        if estimated_cost_usd is not None
        else "unknown_declared"
        if config.cost_unknown
        else "not_estimated"
    )
    if estimated_cost_usd is None and not cost_unavailable_reason:
        cost_unavailable_reason = (
            "provider_cost_unknown_declared"
            if config.cost_unknown
            else "provider_cost_not_estimated"
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "benchmark_id": config.benchmark_id,
        "live_mode": config.live_mode,
        "provider": config.provider,
        "model": config.model,
        "base_url_sha1": config.base_url_sha1,
        "declared_budget": {
            "max_units": config.max_units,
            "per_case_timeout_seconds": config.per_case_timeout_seconds,
            "max_provider_calls": config.max_provider_calls,
            "max_prompt_tokens": config.max_prompt_tokens,
            "max_completion_tokens": config.max_completion_tokens,
            "max_total_tokens": config.max_total_tokens,
            "max_estimated_cost_usd": config.max_estimated_cost_usd,
            "cost_unknown": config.cost_unknown,
            "checkpoint_path_declared": config.checkpoint_path_declared,
            "partial_output_path_declared": config.partial_output_path_declared,
        },
        "completed_units": int(completed_units),
        "skipped_or_resumed_units": int(skipped_or_resumed_units),
        "failed_units": int(failed_units),
        "timed_out_units": int(timed_out_units),
        "elapsed_ms": round(float(elapsed_ms), 2),
        "token_usage": usage_summary,
        "cache_usage": cache_usage_totals(cache_usage),
        "estimated_cost_usd": (
            None if estimated_cost_usd is None else round(float(estimated_cost_usd), 6)
        ),
        "cost_status": cost_status,
        "cost_unavailable_reason": cost_unavailable_reason,
        "stop_reason": str(stop_reason),
        "validation_errors": validation_errors or [],
        "ok_to_start": not validation_errors,
    }


def write_provider_budget_checkpoint(path: str | Path, summary: dict[str, Any]) -> None:
    """Write a sanitized reusable budget checkpoint before or after a live run."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(
            {
                "schema_version": SCHEMA_VERSION,
                "kind": "aippocampus_provider_execution_budget_checkpoint",
                "provider_execution_budget": summary,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
