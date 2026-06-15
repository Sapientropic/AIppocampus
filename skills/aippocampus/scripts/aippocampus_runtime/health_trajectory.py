"""Deterministic preemptive health trajectory for lifecycle hooks.

The trajectory is a small diagnostics layer over existing health facts. It is
not a second scorer: age is reported for operators, while preemptive lifecycle
work requires concrete generated-artifact or source-freshness evidence.
"""

from __future__ import annotations

from typing import Any

PREEMPTIVE_ACTION_ORDER = ("build_clean_source", "build_index")
PREEMPTIVE_ACTION_REASON_CODES = {
    "build_index": {
        "anchor_changed",
        "index_cache_evicted",
        "index_generation_lkg_fallback",
        "index_generation_stable_fallback",
        "index_missing",
        "index_pointer_dangling",
        "index_pointer_unreadable",
        "latest_visible_gap",
        "rag_cache_missing",
        "source_delta",
    },
    "build_clean_source": {
        "clean_source_contract_missing",
        "clean_source_missing",
        "clean_source_schema_drift",
        "latest_visible_gap",
        "source_delta",
    },
}
HIGH_DEGRADATION_CODES = {
    "clean_source_missing",
    "index_generation_lkg_fallback",
    "index_generation_stable_fallback",
    "index_missing",
    "index_pointer_dangling",
    "latest_visible_gap",
}


def build_health_trajectory(
    *,
    index: dict[str, Any],
    clean_source: dict[str, Any],
) -> dict[str, Any]:
    """Project health into path-free preemptive lifecycle diagnostics."""

    action_reasons = {
        "build_index": index_reason_codes(index),
        "build_clean_source": clean_source_reason_codes(clean_source),
    }
    preemptive_action_reasons = {
        action: [
            code
            for code in codes
            if code in PREEMPTIVE_ACTION_REASON_CODES.get(action, set())
        ]
        for action, codes in action_reasons.items()
    }
    preemptive_actions = [
        action
        for action in PREEMPTIVE_ACTION_ORDER
        if preemptive_action_reasons.get(action)
    ]
    reason_codes = unique_codes(
        code
        for action in preemptive_actions
        for code in preemptive_action_reasons.get(action, [])
    )
    return {
        "index_age_hours": hours_since(index.get("stale_age_seconds")),
        "clean_source_age_hours": hours_since(clean_source.get("stale_age_seconds")),
        "expected_degradation": expected_degradation(reason_codes),
        "preemptive_actions": preemptive_actions,
        "preemptive_reason_codes": reason_codes,
        "preemptive_action_reasons": {
            action: preemptive_action_reasons[action] for action in preemptive_actions
        },
        "reasons": reason_codes,
    }


def attach_health_trajectory(result: dict[str, Any]) -> None:
    result["health_trajectory"] = build_health_trajectory(
        index=result["index"],
        clean_source=result["clean_source"],
    )


def hours_since(value: Any) -> float | None:
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        return None
    if seconds < 0:
        return None
    return round(seconds / 3600.0, 2)


def expected_degradation(reason_codes: list[str]) -> str:
    if not reason_codes:
        return "low"
    if any(code in HIGH_DEGRADATION_CODES for code in reason_codes):
        return "high"
    return "medium"


def index_reason_codes(index: dict[str, Any]) -> list[str]:
    codes = [reason_code(reason, action="build_index") for reason in index.get("reasons") or []]
    generations = index.get("generations") or {}
    status = str(generations.get("status") or "")
    if status == "current_missing_last_known_good_available":
        codes.append("index_generation_lkg_fallback")
    elif status == "current_and_last_known_good_missing_stable_available":
        codes.append("index_generation_stable_fallback")
    elif status == "pointer_unreadable":
        codes.append("index_pointer_unreadable")
    elif status == "dangling_pointer":
        codes.append("index_pointer_dangling")
    return unique_codes(code for code in codes if code)


def clean_source_reason_codes(clean_source: dict[str, Any]) -> list[str]:
    codes = [
        reason_code(reason, action="build_clean_source")
        for reason in clean_source.get("reasons") or []
    ]
    return unique_codes(code for code in codes if code)


def reason_code(reason: Any, *, action: str) -> str | None:
    text = str(reason).lower()
    if "latest visible" in text or "latest clean-source" in text:
        return "latest_visible_gap"
    if "new rollout bytes" in text:
        return "source_delta"
    if "thread-anchors.md changed" in text:
        return "anchor_changed"
    if "rag-lite chunk cache is missing" in text:
        return "rag_cache_missing"
    if "intentionally evicted as rebuildable cache" in text:
        return "index_cache_evicted"
    if action == "build_index" and (
        "index manifest is missing" in text
        or "messages.jsonl is missing" in text
        or "source_index.sqlite is missing" in text
    ):
        return "index_missing"
    if action == "build_clean_source" and (
        "clean-source manifest is missing" in text
        or "clean-source messages.jsonl is missing" in text
        or "clean-source turns.jsonl is missing" in text
    ):
        return "clean_source_missing"
    if "clean-source schema is older" in text:
        return "clean_source_schema_drift"
    if "clean-source upgrade contract is missing" in text:
        return "clean_source_contract_missing"
    return None


def unique_codes(codes: Any) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for code in codes:
        text = str(code)
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out
