"""Public-safe route-choice affordances for compact agent recall."""

from __future__ import annotations

import json
from typing import Any

from aippocampus_runtime import core
from aippocampus_runtime.contracts import command_value_needs_input
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
    cue: str | None = None,
) -> dict[str, Any]:
    secondary = dict(action)
    secondary["original_action_id"] = secondary.get("action_id")
    secondary["action_id"] = "deepen_top_route_low_confidence"
    secondary["route_choice_posture"] = "labels_low_specificity"
    secondary["why"] = (
        "Source reopen is still read-only, but compact labels are not enough to "
        "make this the default route choice."
    )
    next_action = {
        "action_id": "refine_low_specificity_recall_cue",
        "tool_name": "agent_recall",
        "secondary_action": {
            key: value for key, value in secondary.items() if value not in (None, "", [])
        },
        "tighter_cue_template": {
            "arguments_template": {"query": "{tighter_cue}", "max": 3},
            "requires": ["tighter_cue"],
            "template_only": True,
            "cli_command_template": 'aippocampus agent recall "{tighter_cue}" --json',
        },
        "route_choice_posture": "labels_low_specificity",
        "route_label_specificity_floor": _metric_float(
            metrics,
            "route_label_specificity_floor",
        ),
        "topic_label_present_count": _metric_int(metrics, "topic_label_present_count"),
        "why": (
            "Route labels are not meaningfully distinguishable in compact output; "
            "use a tighter cue before choosing a route. Blind deepen remains a secondary "
            "low-confidence navigation option only."
        ),
        "claim_boundary": "no_claim_before_reopen",
    }
    clean_cue = str(redact_sensitive_values(redact_private_paths(str(cue or "").strip())) or "")
    if clean_cue and not command_value_needs_input(clean_cue):
        next_action["arguments"] = {"query": clean_cue, "max": 3}
        next_action["cli_command"] = (
            f"aippocampus agent recall {json.dumps(clean_cue, ensure_ascii=False)} --json"
        )
        next_action["same_cue_fallback"] = "low_confidence_not_a_substitute_for_tighter_cue"
    else:
        next_action.update(next_action["tighter_cue_template"])
    return {key: value for key, value in next_action.items() if value not in (None, "", [])}
