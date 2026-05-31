#!/usr/bin/env python3
"""Ambient cache and detached warming helpers for foreground prompt recall."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from aippocampus_runtime.recall.ambient_cache import (
    default_ambient_cache_path,
    read_latest_thread_cache,
    read_related_thread_cache,
    read_thread_cache,
    related_signal_fingerprints,
    topic_epoch_from_terms,
    write_thread_cache,
)
from aippocampus_runtime.recall.ambient_cards import ambient_recall_from_decision
from aippocampus_runtime.recall.ambient_policy import (
    append_policy_events,
    filter_ambient_cards,
    load_policy_events,
    surface_events_for_cards,
)
from aippocampus_runtime.warm_ambient.scheduler import (
    public_warm_schedule_status,
    schedule_warm_ambient_recall,
    warm_background_enabled,
)

__all__ = [
    "attach_ambient_recall",
    "cached_cards_for_policy",
    "current_thread_key_from_hook_thread_id",
    "warm_prompt_trace",
]


def attach_ambient_recall(
    result: dict[str, Any],
    *,
    prompt: str,
    thread_id: str | None,
    workspace: str,
    registry_path: Path,
    ambient_cache_path: Path | str | None,
    ambient_policy_path: Path | str | None,
    topic_epoch: str | None,
    use_thread_cache: bool,
    warm_background: bool | None,
    warm_job_dir: Path | str | None,
    warm_max_workers: int | None,
    warm_timeout: float | None,
    warm_quorum: int | None,
) -> dict[str, Any]:
    if not use_thread_cache or not thread_id:
        result["ambient_recall"] = ambient_recall_from_decision(result)
        return result
    epoch = topic_epoch or topic_epoch_from_terms(
        [str(term) for term in result.get("query_terms") or []]
    )
    cache_file = (
        Path(ambient_cache_path).resolve()
        if ambient_cache_path
        else default_ambient_cache_path(registry_path)
    )
    policy_file = Path(ambient_policy_path).resolve() if ambient_policy_path else None
    related_fingerprints = related_signal_fingerprints(
        candidates=result.get("candidates") or [],
        evidence=result.get("evidence") or [],
        working_memory=result.get("working_memory") or [],
        semantic_gate=result.get("semantic_gate") or None,
        query_aliases=(
            (result.get("semantic_gate") or {}).get("query_aliases")
            if isinstance(result.get("semantic_gate"), dict)
            else result.get("query_terms") or []
        ),
    )
    try:
        cached = read_thread_cache(
            cache_file,
            thread_id=thread_id,
            workspace=workspace,
            topic_epoch=epoch,
        )
        if cached.get("status") in {"miss", "expired"}:
            related = read_related_thread_cache(
                cache_file,
                thread_id=thread_id,
                workspace=workspace,
                topic_epoch=epoch,
                related_fingerprints=related_fingerprints,
            )
            if related.get("status") == "related_hit":
                cached = related
        cache_status = {
            "status": cached.get("status"),
            "topic_epoch": epoch,
            "matched_topic_epoch": cached.get("matched_topic_epoch") or None,
            "card_count": len(cached.get("cards") or []),
            "related_overlap_count": cached.get("related_overlap_count") or 0,
            "query_aliases": cached.get("query_aliases") or [],
            "topic_epoch_decision": cached.get("topic_epoch_decision") or None,
            "visibility_bias": cached.get("visibility_bias") or "",
        }
        result["ambient_recall"] = ambient_recall_from_decision(
            result,
            cached_cards=cached.get("cards") or [],
            cache_status=cache_status,
            cached_cards_first=True,
        )
        if policy_file:
            policy_events = load_policy_events(policy_file)
            policy_filter = filter_ambient_cards(
                result["ambient_recall"].get("cards") or [],
                policy_events,
                prompt=prompt,
            )
            result["ambient_recall"]["cards"] = policy_filter["cards"]
            result["ambient_recall"]["policy_filter"] = policy_filter["diagnostics"]
        cache_is_warm = cached.get("status") == "hit" and bool(cached.get("cards"))
        if result.get("decision") != "skip" and result["ambient_recall"].get("cards"):
            written = write_thread_cache(
                cache_file,
                thread_id=thread_id,
                workspace=workspace,
                topic_epoch=epoch,
                cards=result["ambient_recall"]["cards"],
                mode=str(result["ambient_recall"].get("mode") or ""),
                confidence=str(result["ambient_recall"].get("confidence") or ""),
                negative_contexts=(
                    (result.get("semantic_gate") or {}).get("negative_contexts") or []
                ),
                query_aliases=(
                    (result.get("semantic_gate") or {}).get("query_aliases")
                    or result.get("query_terms")
                    or []
                ),
                related_fingerprints=related_fingerprints,
                visibility_bias=str(result["ambient_recall"].get("mode") or ""),
            )
            result["ambient_recall"]["cache_status"] = {
                **cache_status,
                "write_status": written.get("status"),
                "written_card_count": written.get("card_count"),
            }
            if policy_file:
                try:
                    append_policy_events(
                        policy_file,
                        surface_events_for_cards(
                            result["ambient_recall"].get("cards") or [],
                            thread_id=thread_id,
                            workspace=workspace,
                        ),
                    )
                except Exception as exc:
                    result["ambient_recall"]["policy_write"] = {
                        "status": "error",
                        "error_type": type(exc).__name__,
                        "message": str(exc)[:160],
                    }
        if (
            result.get("decision") != "skip"
            and not cache_is_warm
            and warm_background_enabled(warm_background)
        ):
            current_thread_key = current_thread_key_from_hook_thread_id(thread_id)
            # The foreground hook may enqueue warming, but the 50-lane scout
            # batch must run detached. Otherwise model tail latency or rate
            # limiting would turn ambient recall from peripheral awareness into
            # a blocking path for every user prompt.
            scheduled = schedule_warm_ambient_recall(
                prompt,
                cwd=workspace,
                thread_id=thread_id,
                current_thread_key=current_thread_key,
                prompt_trace=warm_prompt_trace(prompt, current_thread_key),
                registry_path=registry_path,
                cache_path=cache_file,
                topic_epoch=epoch,
                job_dir=warm_job_dir,
                max_workers=warm_max_workers,
                timeout=warm_timeout,
                quorum=warm_quorum,
                enabled=warm_background,
                wait_all_foreground=False,
            )
            result["ambient_recall"]["warm_background"] = public_warm_schedule_status(scheduled)
    except Exception as exc:
        result["ambient_recall"] = ambient_recall_from_decision(
            result,
            cache_status={
                "status": "error",
                "topic_epoch": epoch,
                "error_type": type(exc).__name__,
                "message": str(exc)[:160],
            },
        )
    return result


def cached_cards_for_policy(
    *,
    registry_path: Path,
    ambient_cache_path: Path | str | None,
    thread_id: str | None,
    workspace: str,
) -> list[dict[str, Any]]:
    if not thread_id:
        return []
    cache_file = (
        Path(ambient_cache_path).resolve()
        if ambient_cache_path
        else default_ambient_cache_path(registry_path)
    )
    try:
        cached = read_latest_thread_cache(cache_file, thread_id=thread_id, workspace=workspace)
    except Exception:
        return []
    return [card for card in cached.get("cards") or [] if isinstance(card, dict)]


def current_thread_key_from_hook_thread_id(thread_id: str | None) -> str | None:
    """Map hook session ids to registry-style source_ref thread keys.

    The thread ambient cache can use the raw hook `thread_id` as part of its
    private cache key, but warm source-ref echo suppression compares against
    clean-source refs, whose canonical registry form is `session:<id>`. Keep
    this adapter small so later agents do not accidentally compare different
    namespaces and silently lose current-thread echo penalties.
    """

    text = str(thread_id or "").strip()
    if not text:
        return None
    if ":" in text:
        return text
    return f"session:{text}"


def warm_prompt_trace(prompt: str, current_thread_key: str | None) -> list[dict[str, Any]]:
    if not current_thread_key:
        return []
    return [
        {
            "thread_key": current_thread_key,
            "role": "user",
            "phase": "current_prompt",
            "text": str(prompt or ""),
        }
    ]
