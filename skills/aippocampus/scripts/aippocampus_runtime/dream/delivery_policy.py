"""Hook-safe dream delivery policy for opt-in delivered A/B.

The prompt hook should stay glue. This module owns only the small delivery
decision wrapper: mode parsing, rollout rate normalization, hash-only event
recording, and the foreground allow/holdback flag consumed by recall rendering.
"""

from __future__ import annotations

import argparse
import os
from typing import Any, Mapping


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
    if mode == "off":
        return {
            "mode": mode,
            "event": None,
            "allow_dream": False,
            "dream_hypothesis_limit": 0,
            "reason": "delivery_disabled",
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
    return {
        "mode": mode,
        "event": event,
        "allow_dream": allow_dream,
        "dream_hypothesis_limit": 1 if allow_dream else 0,
        "reason": str(event.get("delivery_decision") or mode),
    }
