"""Hook-safe dream delivery policy for opt-in delivered A/B.

The prompt hook should stay glue. This module owns only the small delivery
decision wrapper: mode parsing, rollout rate normalization, hash-only event
recording, and the foreground allow/holdback flag consumed by recall rendering.
"""

from __future__ import annotations

import argparse
import os
from typing import Any, Mapping

from aippocampus_runtime.dream.delivery_eligibility import classify_dream_delivery_task


def add_dream_delivery_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--dream-shadow-ab", action="store_true")
    parser.add_argument("--dream-shadow-log")
    parser.add_argument("--dream-shadow-salt", default=os.environ.get("AIPPOCAMPUS_DREAM_SHADOW_AB_SALT"))
    parser.add_argument("--dream-delivery-mode")
    parser.add_argument("--dream-rollout-rate", type=float, default=None)


def _truthy_env(value: object) -> bool:
    return str(value or "").strip().casefold() in {"1", "true", "yes", "on"}


def _normalize_dream_delivery_mode(value: object) -> str:
    text = str(value or "").strip().casefold().replace("-", "_")
    if text in {"shadow", "shadow_only", "true", "1", "yes", "on"}:
        return "shadow"
    if text in {"dry_run", "dryrun", "would_deliver"}:
        return "dry_run"
    if text in {"delivered", "delivery", "treatment"}:
        return "delivered"
    return "off"


def dream_delivery_lane_card(mode: str = "off") -> dict[str, Any]:
    normalized = _normalize_dream_delivery_mode(mode)
    if normalized == "off":
        lane = "backstage_review"
        absence_reason = "delivery_disabled"
        product_meaning = "review_queue_or_operator_only"
    elif normalized in {"shadow", "dry_run"}:
        lane = "shadow_or_dry_run"
        absence_reason = "not_delivered_treatment"
        product_meaning = "measure_or_preview_without_foreground_context"
    else:
        lane = "opt_in_foreground_treatment"
        absence_reason = "not_absent_when_eligible"
        product_meaning = "deliver_one_bounded_navigation_hypothesis_when_eligible"
    return {
        "kind": "aippocampus_dream_delivery_lane_card",
        "schema_version": 1,
        "mode": normalized,
        "lane": lane,
        "foreground_absence_reason": absence_reason,
        "default_product_meaning": product_meaning,
        "foreground_fact_claim_allowed": False,
        "source_reopen_required_before_claim": True,
        "navigation_only": True,
        "operator_review_path": "dream_or_subconscious_review_queue",
    }


def _float_env_or_default(value: object, default: float) -> float:
    if not isinstance(value, (str, int, float)):
        return default
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if number != number:
        return default
    return max(0.0, min(1.0, number))


def requested_dream_delivery_mode(args: argparse.Namespace) -> str:
    raw_mode = args.dream_delivery_mode or os.environ.get("AIPPOCAMPUS_DREAM_DELIVERY_MODE")
    if raw_mode:
        return _normalize_dream_delivery_mode(raw_mode)
    if args.dream_shadow_ab or _truthy_env(os.environ.get("AIPPOCAMPUS_DREAM_SHADOW_AB")):
        return "shadow"
    return "off"


def dream_rollout_rate(args: argparse.Namespace) -> float:
    raw = (
        args.dream_rollout_rate
        if args.dream_rollout_rate is not None
        else os.environ.get("AIPPOCAMPUS_DREAM_ROLLOUT_RATE")
    )
    return _float_env_or_default(raw, 1.0)


def prepare_dream_delivery(
    *,
    prompt: str,
    hook_input: Mapping[str, Any],
    args: argparse.Namespace,
) -> dict[str, Any]:
    mode = requested_dream_delivery_mode(args)
    task = classify_dream_delivery_task(prompt)
    if mode == "off":
        return {
            "mode": mode,
            "event": None,
            "allow_dream": False,
            "dream_hypothesis_limit": 0,
            "reason": "delivery_disabled",
            "prefilter_reason": "user_disabled",
            "task_mode": task["task_mode"],
        }
    if not task["eligible"]:
        return {
            "mode": mode,
            "event": None,
            "allow_dream": False,
            "dream_hypothesis_limit": 0,
            "reason": task["reason"],
            "prefilter_reason": task["reason"],
            "task_mode": task["task_mode"],
        }

    from aippocampus_runtime.dream.live_shadow_ab import (  # noqa: PLC0415
        ASSIGNMENT_PROMPT,
        ASSIGNMENT_THREAD_TOPIC_EPOCH,
        DELIVERY_DELIVERED,
        record_prompt_shadow_from_hook_args,
    )

    args.dream_delivery_mode = mode
    args.dream_rollout_rate = dream_rollout_rate(args)
    args.dream_assignment_unit = (
        ASSIGNMENT_THREAD_TOPIC_EPOCH if mode in {"dry_run", DELIVERY_DELIVERED} else ASSIGNMENT_PROMPT
    )
    event = record_prompt_shadow_from_hook_args(prompt=prompt, hook_input=hook_input, args=args)
    allow_dream = mode == DELIVERY_DELIVERED and event.get("delivered_arm") == "dream"
    prefilter_reason = _prefilter_reason_from_event(event, allow_dream=allow_dream)
    return {
        "mode": mode,
        "event": event,
        "allow_dream": allow_dream,
        "dream_hypothesis_limit": 1 if allow_dream else 0,
        "reason": str(event.get("delivery_decision") or mode),
        "prefilter_reason": prefilter_reason,
        "task_mode": task["task_mode"],
    }


def _prefilter_reason_from_event(event: Mapping[str, Any], *, allow_dream: bool) -> str:
    if allow_dream:
        return "eligible_task_mode"
    block_reasons = {str(reason) for reason in event.get("delivery_block_reasons") or []}
    if "dream_miss" in block_reasons:
        return "eligible_but_no_candidate"
    if "recall_reminder_prompt" in block_reasons:
        return "recall_reminder_prompt"
    if "baseline_match" in block_reasons:
        return "baseline_match"
    return "budget_zero"
