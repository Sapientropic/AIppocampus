#!/usr/bin/env python3
"""Ambient cache and detached warming helpers for foreground prompt recall."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from aippocampus_runtime.recall.active_recall_lock import (
    DEFAULT_LOCK_NAME,
    start_or_update_recall_lock,
    summarize_lock_roi,
)
from aippocampus_runtime.recall.ambient_cache import (
    default_ambient_cache_path,
    read_latest_thread_cache,
    read_related_thread_cache,
    read_thread_cache,
    read_topic_signal_state,
    record_topic_signal,
    related_signal_fingerprints,
    signal_accumulator_path_for_cache,
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
from aippocampus_runtime.recall.ambient_source_reopen import promote_reopenable_ambient_cards
from aippocampus_runtime.warm_ambient.scheduler import (
    public_warm_schedule_status,
    schedule_warm_ambient_recall,
    warm_background_enabled,
)

__all__ = [
    "attach_ambient_recall",
    "cached_cards_for_policy",
    "current_thread_key_from_hook_thread_id",
    "prompt_topic_signal_context",
    "record_prompt_topic_signal",
    "warm_prompt_trace",
]


def _ambient_cache_file(
    *,
    ambient_cache_path: Path | str | None,
    registry_path: Path,
) -> Path:
    return (
        Path(ambient_cache_path).resolve()
        if ambient_cache_path
        else default_ambient_cache_path(registry_path)
    )


def _active_lock_roi_summary(cache_file: Path) -> dict[str, Any]:
    lock_path = cache_file.resolve().parent / DEFAULT_LOCK_NAME
    if not lock_path.exists():
        return {}
    try:
        return summarize_lock_roi(lock_path)
    except Exception:
        return {}


def prompt_topic_signal_context(
    *,
    ambient_cache_path: Path | str | None,
    registry_path: Path,
    thread_id: str | None,
    workspace: str,
    topic_epoch: str | None,
    terms: list[str],
) -> dict[str, Any]:
    """Return public-safe threshold context for same-topic route tuning.

    The accumulator is a thread-local routing aid, not a memory surface. It uses
    the same ambient-cache directory and stores only fingerprints and aggregate
    counters, so foreground threshold tuning can learn from repeated weak turns
    without persisting raw prompts or workspace paths.
    """

    epoch = topic_epoch or topic_epoch_from_terms([str(term) for term in terms])
    if not thread_id:
        return {
            "topic_epoch": epoch,
            "signal_path": None,
            "topic_signal_state": None,
            "route_roi_summary": {},
        }
    cache_file = _ambient_cache_file(
        ambient_cache_path=ambient_cache_path,
        registry_path=registry_path,
    )
    signal_path = signal_accumulator_path_for_cache(cache_file)
    return {
        "topic_epoch": epoch,
        "signal_path": signal_path,
        "topic_signal_state": read_topic_signal_state(
            signal_path,
            thread_id=thread_id,
            workspace=workspace,
            topic_epoch=epoch,
            terms=terms,
        ),
        "route_roi_summary": _active_lock_roi_summary(cache_file),
    }


def record_prompt_topic_signal(
    *,
    signal_path: Path | str | None,
    thread_id: str | None,
    workspace: str,
    topic_epoch: str,
    terms: list[str],
    decision: str,
    evidence: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    suppressed: bool,
    threshold_policy: dict[str, Any],
    reasons: list[str],
) -> dict[str, Any] | None:
    if not signal_path or not thread_id or not terms:
        return None
    if str((threshold_policy or {}).get("risk_boundary") or "") != "normal":
        return None
    outcome = ""
    if decision == "evidence" and evidence:
        outcome = "source_backed_hit"
    elif decision == "scent" and candidates:
        outcome = "candidate_backed_hit"
    elif decision == "skip" and not suppressed:
        outcome = "weak_signal"
    elif suppressed:
        outcome = "ignored_route"
    if not outcome:
        return None
    try:
        return record_topic_signal(
            signal_path,
            thread_id=thread_id,
            workspace=workspace,
            topic_epoch=topic_epoch,
            terms=terms,
            outcome=outcome,
            reason_codes=reasons,
        )
    except Exception as exc:
        return {"status": "error", "error_type": type(exc).__name__}


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
        result["ambient_recall"] = ambient_recall_from_decision(result, prompt=prompt)
        return result
    epoch = topic_epoch or topic_epoch_from_terms(
        [str(term) for term in result.get("query_terms") or []]
    )
    cache_file = _ambient_cache_file(
        ambient_cache_path=ambient_cache_path,
        registry_path=registry_path,
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
            prompt=prompt,
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
        promote_reopenable_ambient_cards(result["ambient_recall"], registry_path=registry_path)
        active_lock: dict[str, Any] | None = None
        try:
            active_lock = _attach_active_recall_lock(
                result,
                prompt=prompt,
                thread_id=thread_id,
                workspace=workspace,
                topic_epoch=epoch,
                registry_path=registry_path,
                cache_file=cache_file,
            )
        except Exception as exc:
            result["ambient_recall"]["active_recall_lock"] = {
                "state": "failed",
                "support_level": "scent",
                "source_reopen_required": True,
                "diagnostics": {
                    "error_type": type(exc).__name__,
                    "message": str(exc)[:160],
                },
            }
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
                lock_path=cache_file.resolve().parent / DEFAULT_LOCK_NAME,
                lock_id=str(active_lock.get("lock_id") or "") if active_lock else None,
                job_dir=warm_job_dir,
                max_workers=warm_max_workers,
                timeout=warm_timeout,
                quorum=warm_quorum,
                enabled=warm_background,
                wait_all_foreground=False,
            )
            warm_status = public_warm_schedule_status(scheduled)
            result["ambient_recall"]["warm_background"] = warm_status
            route_diagnostic = result.get("route_delivery_diagnostic")
            if isinstance(route_diagnostic, dict):
                route_diagnostic["background_scheduled"] = bool(
                    warm_status.get("spawned")
                    or warm_status.get("status") in {"queued", "scheduled"}
                )
    except Exception as exc:
        result["ambient_recall"] = ambient_recall_from_decision(
            result,
            cache_status={
                "status": "error",
                "topic_epoch": epoch,
                "error_type": type(exc).__name__,
                "message": str(exc)[:160],
            },
            prompt=prompt,
        )
    return result


def _lock_query_aliases(result: dict[str, Any]) -> list[str]:
    semantic_gate = result.get("semantic_gate") if isinstance(result.get("semantic_gate"), dict) else {}
    aliases = semantic_gate.get("query_aliases") if isinstance(semantic_gate, dict) else None
    values = aliases if isinstance(aliases, list) else result.get("query_terms") or []
    return [str(item) for item in values if str(item or "").strip()]


def _attach_active_recall_lock(
    result: dict[str, Any],
    *,
    prompt: str,
    thread_id: str | None,
    workspace: str,
    topic_epoch: str,
    registry_path: Path,
    cache_file: Path,
) -> dict[str, Any] | None:
    """Create a short-lived route handle without making the hook wait.

    The lock stores only fingerprints, aliases, route reasons, and source-id
    refs. It deliberately mirrors the fresh-thread boundary: foreground scent
    can prepare a route, but exact claims still require active recall reopen.
    """

    if not thread_id:
        return None
    ambient = result.get("ambient_recall")
    if not isinstance(ambient, dict):
        return None
    raw_packet = ambient.get("fresh_thread_packet")
    packet: dict[str, Any] = raw_packet if isinstance(raw_packet, dict) else {}
    support_level = str(packet.get("support_level") or "")
    if support_level in {"", "silent_scent", "suppressed"} and not ambient.get("cards"):
        return None
    lock_path = cache_file.resolve().parent / DEFAULT_LOCK_NAME
    candidate_refs = [
        ref
        for ref in packet.get("candidate_refs") or []
        if isinstance(ref, dict)
    ]
    route_reason = str(packet.get("route_reason") or "")
    lock = start_or_update_recall_lock(
        lock_path,
        prompt=prompt,
        thread_id=thread_id,
        workspace=workspace,
        topic_epoch=topic_epoch,
        registry_path=registry_path,
        candidate_refs=candidate_refs,
        cards=[card for card in ambient.get("cards") or [] if isinstance(card, dict)],
        query_aliases=_lock_query_aliases(result),
        route_reasons=[route_reason, "foreground_hook_scent"] if route_reason else ["foreground_hook_scent"],
        diagnostics={
            "cold_model_call": False,
            "fast_scout_used": bool((result.get("semantic_gate") or {}).get("cached") is False)
            if isinstance(result.get("semantic_gate"), dict)
            else False,
            "thinking_enrichment_pending": True,
        },
    )
    public = {
        "lock_id": lock.get("lock_id"),
        "state": lock.get("state"),
        "support_level": "scent",
        "candidate_ref_count": lock.get("candidate_ref_count", 0),
        "reopenable_ref_count": lock.get("reopenable_ref_count", 0),
        "source_reopen_required": True,
        "suggested_next": lock.get("suggested_next"),
        "diagnostics": lock.get("diagnostics") or {},
    }
    ambient["active_recall_lock"] = public
    if isinstance(packet, dict):
        packet["active_recall_lock"] = public
    return lock


def cached_cards_for_policy(
    *,
    registry_path: Path,
    ambient_cache_path: Path | str | None,
    thread_id: str | None,
    workspace: str,
) -> list[dict[str, Any]]:
    if not thread_id:
        return []
    cache_file = _ambient_cache_file(
        ambient_cache_path=ambient_cache_path,
        registry_path=registry_path,
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
