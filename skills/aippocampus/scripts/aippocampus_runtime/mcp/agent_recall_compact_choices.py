"""Public-safe route-choice affordances for compact agent recall."""

from __future__ import annotations

from typing import Any

from aippocampus_runtime import core
from aippocampus_runtime.privacy import redact_private_paths, redact_sensitive_values


def _safe_choice_token(value: Any, *, limit: int = 64) -> str:
    text = str(redact_sensitive_values(redact_private_paths(str(value or "").strip())) or "")
    text = text.casefold().replace(" ", "_")
    clean = "".join(ch for ch in text if ch.isalnum() or ch in {"_", "-", ":"})
    return clean[:limit].strip("_:-")


def _metric_float(metrics: dict[str, Any], key: str) -> float | None:
    value = metrics.get(key)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return round(float(value), 3)
    return None


def _metric_int(metrics: dict[str, Any], key: str) -> int | None:
    value = metrics.get(key)
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return None


def low_specificity_route_choices(metrics: dict[str, Any], route_count: int) -> bool:
    floor = _metric_float(metrics, "route_label_specificity_floor")
    topic_count = _metric_int(metrics, "topic_label_present_count")
    return route_count > 1 and floor is not None and floor <= 0.0 and (topic_count or 0) <= 0


def route_choice_reason(
    packet: dict[str, Any],
    *,
    index: int,
    route_count: int,
    labels_low_specificity: bool,
) -> str:
    route_family = _safe_choice_token(packet.get("route_kind") or packet.get("output_mode") or "route")
    parts = [f"rank_{index}_of_{route_count}"]
    if route_family:
        parts.append(route_family)
    route_topic = _safe_choice_token(packet.get("route_topic"))
    if route_topic:
        parts.append(f"topic_{route_topic}")
    hint = packet.get("selection_hint")
    if isinstance(hint, dict):
        source = _safe_choice_token(hint.get("source"))
        why = _safe_choice_token(hint.get("why"))
        if source:
            parts.append(f"selected_by_{source}")
        if why:
            parts.append(why)
    reason_codes = packet.get("route_delta_reason_codes") or packet.get("triage_rank_reason_codes") or []
    if isinstance(reason_codes, list):
        for code in reason_codes:
            clean = _safe_choice_token(code)
            if clean and clean not in parts:
                parts.append(clean)
            if len(parts) >= 5:
                break
    if labels_low_specificity:
        parts.append("labels_low_specificity")
        parts.append("deepen_or_tighter_cue_before_claim")
    elif index == 1:
        parts.append("top_ranked_route")
    return core.compact_text("; ".join(parts), 180)


def with_low_specificity_foreground_action(
    action: dict[str, Any],
    *,
    metrics: dict[str, Any],
) -> dict[str, Any]:
    next_action = dict(action)
    next_action["original_action_id"] = next_action.get("action_id")
    next_action["action_id"] = "deepen_top_route_blindly"
    next_action["route_choice_posture"] = "labels_low_specificity"
    next_action["route_label_specificity_floor"] = _metric_float(
        metrics, "route_label_specificity_floor"
    )
    next_action["topic_label_present_count"] = _metric_int(metrics, "topic_label_present_count")
    next_action["why"] = (
        "Route labels are not meaningfully distinguishable in compact output; "
        "deepen the top-ranked route blindly or rerun recall with a tighter cue."
    )
    next_action["claim_boundary"] = "no_claim_before_reopen"
    return {key: value for key, value in next_action.items() if value not in (None, "", [])}
