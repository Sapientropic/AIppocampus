#!/usr/bin/env python3
"""Foreground semantic-gate execution for prompt recall."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from prompt_cues import should_run_semantic_gate
from prompt_recall_budget import (
    POST_SEMANTIC_RESERVE_MS,
    budget_allows,
    semantic_budget_result,
    semantic_timeout_for_budget,
    semantic_worker_timeout_for_deadline,
)
from semantic_recall_gate import run_semantic_gate


def semantic_cue_cache_hit(matches: list[dict[str, Any]]) -> bool:
    return any(str(match.get("source") or "") == "semantic_cue_cache" for match in matches)


def semantic_gate_reuse_diagnostics(
    *,
    semantic_result: dict[str, Any] | None,
    semantic_cue_hit: bool,
    skipped_by_semantic_cue: bool,
) -> dict[str, Any]:
    exact_cache_hit = bool(semantic_result and semantic_result.get("cached"))
    cache_lookup = (
        str((semantic_result.get("cache_diagnostics") or {}).get("lookup") or "")
        if semantic_result
        else ""
    )
    attempted_workers = bool(
        semantic_result
        and (
            semantic_result.get("workers")
            or semantic_result.get("errors")
            or int(semantic_result.get("worker_count") or 0) > 0
        )
    )
    cold_model_call = bool(semantic_result and not exact_cache_hit and cache_lookup != "hit" and attempted_workers)
    source = "none"
    if exact_cache_hit:
        source = "exact_semantic_cache"
    elif cold_model_call:
        source = "cold_model_call"
    elif semantic_cue_hit:
        source = "semantic_cue_cache"
    return {
        "source": source,
        "exact_cache_hit": exact_cache_hit,
        "semantic_cue_hit": semantic_cue_hit,
        "cold_model_call": cold_model_call,
        "skipped_by_semantic_cue": skipped_by_semantic_cue,
        "cache_lookup": cache_lookup or None,
    }


def run_semantic_gate_for_prompt(
    *,
    prompt: str,
    cwd_path: Path,
    registry: dict[str, Any],
    registry_path: Path,
    associations: dict[str, Any],
    working_memory_rows: list[dict[str, Any]],
    semantic_triggers_file: Path,
    semantic_cache_path: Path | str | None,
    semantic_gate_mode: str | None,
    semantic_timeout: float,
    semantic_gate_fn: Callable[..., dict[str, Any]] | None,
    use_semantic_gate: bool,
    start: float,
    max_elapsed_ms: int | None,
    explicit: list[str],
    associative: list[str],
    important: list[str],
    association_matches: list[dict[str, Any]],
    working_memory_matches: list[dict[str, Any]],
    cognitive_map_matches: list[dict[str, Any]],
) -> dict[str, Any] | None:
    if (
        use_semantic_gate
        and prompt
        and should_run_semantic_gate(
            prompt,
            explicit=explicit,
            associative=associative,
            important=important,
            association_matches=association_matches,
            working_memory_matches=working_memory_matches,
            cognitive_map_matches=cognitive_map_matches,
        )
    ):
        gate = semantic_gate_fn or run_semantic_gate
        budgeted_timeout = semantic_timeout_for_budget(
            start, max_elapsed_ms, float(semantic_timeout)
        )
        if budgeted_timeout is None:
            return semantic_budget_result(
                "semantic gate skipped by prompt hook foreground budget",
                requested_timeout=float(semantic_timeout),
                effective_timeout=None,
                max_elapsed_ms=max_elapsed_ms,
            )
        effective_timeout = float(semantic_worker_timeout_for_deadline(budgeted_timeout))
        budget = {
            "requested_timeout": float(semantic_timeout),
            "effective_timeout": effective_timeout,
            "overall_deadline_seconds": float(budgeted_timeout),
            "max_elapsed_ms": max_elapsed_ms,
            "budget_clipped": float(budgeted_timeout) != float(semantic_timeout),
        }
        try:
            result = gate(
                prompt,
                cwd=cwd_path,
                registry=registry,
                registry_path=registry_path,
                associations=associations,
                working_memory=working_memory_rows,
                semantic_triggers_path=semantic_triggers_file,
                cache_path=Path(semantic_cache_path).resolve() if semantic_cache_path else None,
                mode=semantic_gate_mode,
                timeout=effective_timeout,
                deadline_seconds=budgeted_timeout,
            )
            result.setdefault("budget", budget)
            if not result.get("available"):
                buckets = result.get("error_buckets") or {}
                if buckets.get("read_timeout") and budget.get("budget_clipped"):
                    result.setdefault("availability_reason", "foreground_budget_timeout")
                    result.setdefault("diagnostic", "semantic_timed_out_under_foreground_budget")
                elif buckets.get("read_timeout"):
                    result.setdefault("availability_reason", "semantic_worker_timeout")
                    result.setdefault("diagnostic", "semantic_provider_read_timeout")
                else:
                    result.setdefault("availability_reason", "semantic_unavailable")
                    result.setdefault("diagnostic", "semantic_unavailable")
            return result
        except Exception as exc:
            return {
                "available": False,
                "decision": "skip",
                "confidence": 0.0,
                "availability_reason": "semantic_worker_error",
                "diagnostic": "semantic_worker_error",
                "query_aliases": [],
                "reasons": [f"semantic gate error: {exc}"],
                "errors": [str(exc)],
                "error_buckets": {"semantic_worker_error": 1},
                "budget": budget,
            }
    if (
        use_semantic_gate
        and max_elapsed_ms
        and not budget_allows(start, max_elapsed_ms, POST_SEMANTIC_RESERVE_MS)
    ):
        return semantic_budget_result(
            "semantic gate skipped by prompt hook foreground budget",
            requested_timeout=float(semantic_timeout),
            effective_timeout=None,
            max_elapsed_ms=max_elapsed_ms,
        )
    return None


def run_semantic_gate_for_context(
    *,
    prompt: str,
    context: Any,
    semantic_cache_path: Path | str | None,
    semantic_gate_mode: str | None,
    semantic_timeout: float,
    semantic_gate_fn: Callable[..., dict[str, Any]] | None,
    use_semantic_gate: bool,
    start: float,
    max_elapsed_ms: int | None,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    cue_hit = semantic_cue_cache_hit(context.semantic_trigger_matches)
    forced_semantic_gate = str(semantic_gate_mode or "").casefold() == "on"
    # Learned semantic cues are the foreground escape hatch for #157: after a
    # cue has accumulated source-backed hits, neighboring paraphrases should
    # stay on the local path instead of repeatedly spending the cold semantic
    # model budget. An explicit operator `semantic_gate=on` still forces a live
    # call for debugging/calibration.
    skipped = bool(cue_hit and use_semantic_gate and not forced_semantic_gate)
    result = None
    if not skipped:
        result = run_semantic_gate_for_prompt(
            prompt=prompt,
            cwd_path=context.cwd_path,
            registry=context.registry,
            registry_path=context.registry_path,
            associations=context.associations,
            working_memory_rows=context.working_memory_rows,
            semantic_triggers_file=context.semantic_triggers_path,
            semantic_cache_path=semantic_cache_path,
            semantic_gate_mode=semantic_gate_mode,
            semantic_timeout=semantic_timeout,
            semantic_gate_fn=semantic_gate_fn,
            use_semantic_gate=use_semantic_gate,
            start=start,
            max_elapsed_ms=max_elapsed_ms,
            explicit=context.pre_explicit,
            associative=context.pre_associative,
            important=context.pre_important,
            association_matches=context.association_matches,
            working_memory_matches=context.working_memory_matches,
            cognitive_map_matches=context.cognitive_map_matches,
        )
    return result, semantic_gate_reuse_diagnostics(
        semantic_result=result,
        semantic_cue_hit=cue_hit,
        skipped_by_semantic_cue=skipped,
    )
