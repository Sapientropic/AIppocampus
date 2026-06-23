"""Public-safe route-choice affordances for compact agent recall."""

from __future__ import annotations

import re
from typing import Any

from aippocampus_runtime import core
from aippocampus_runtime.contracts import (
    command_value_needs_input,
    normalize_foreground_action,
    shell_quote,
)
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
    distinctiveness = _metric_float(metrics, "packet_triage_distinctiveness")
    missing_topics = (topic_count or 0) <= 0
    repeated_topic_shape = (topic_count or 0) >= route_count and (
        distinctiveness is not None and distinctiveness <= 0.5
    )
    return (
        route_count > 1
        and floor is not None
        and floor <= 0.0
        and (missing_topics or repeated_topic_shape)
    )


def repeated_low_distinctiveness_label(
    metrics: dict[str, Any],
    packets: list[dict[str, Any]],
) -> str:
    """Return the repeated public label that makes compact choices indistinct.

    The route ranker may have valid private/source distinctions, but compact
    foreground JSON redacts those internals. When the public labels collapse to
    the same topic and the triage distinctiveness is low, defaulting to the top
    route turns the card into blind deepen. Keep the signal public-safe and use
    it only to choose the foreground action posture.
    """

    if len(packets) <= 1:
        return ""
    distinctiveness = _metric_float(metrics, "packet_triage_distinctiveness")
    if distinctiveness is None or distinctiveness > 0.5:
        return ""
    counts: dict[str, int] = {}
    labels: dict[str, str] = {}
    for packet in packets:
        raw_label = (
            packet.get("route_topic")
            or packet.get("route_label")
            or packet.get("display_hint")
            or ""
        )
        token = _safe_choice_token(raw_label)
        if not token:
            continue
        counts[token] = counts.get(token, 0) + 1
        labels[token] = str(redact_sensitive_values(redact_private_paths(str(raw_label).strip())) or "")
    if not counts:
        return ""
    token, count = max(counts.items(), key=lambda item: item[1])
    if count <= 1:
        return ""
    return core.compact_text(labels.get(token) or token, 80)


_CUE_TOKEN_RE = re.compile(r"[\u4e00-\u9fff]{2,}|[A-Za-z0-9][A-Za-z0-9_-]{3,}")
_ANCHOR_NORMALIZE_RE = re.compile(r"[^0-9A-Za-z\u4e00-\u9fff]+")
_LOW_SIGNAL_WORDS = {
    "agent",
    "about",
    "clean",
    "continuity",
    "decision",
    "handoff",
    "memory",
    "recall",
    "route",
    "safe",
    "search",
    "source",
    "source-backed",
    "sourcebacked",
    "technical",
    "work",
}


def distinctive_cue_anchor_gap(cue: str | None, packets: list[dict[str, Any]]) -> bool:
    """Return whether compact route labels fail to carry distinctive cue anchors.

    This is a foreground affordance, not a ranking layer: the underlying recall
    may still have a plausible source route, but if the compact labels do not
    echo any distinctive cue anchor, the safe default is to refine/search before
    blindly deepening a generic-looking route.
    """

    raw = str(cue or "")
    tokens = []
    seen: set[str] = set()
    for match in _CUE_TOKEN_RE.finditer(raw):
        token = _ANCHOR_NORMALIZE_RE.sub("", match.group(0).casefold())
        if token in _LOW_SIGNAL_WORDS or token in seen:
            continue
        seen.add(token)
        tokens.append(token)
    if len(tokens) < 2 or not packets:
        return False
    label_text = _ANCHOR_NORMALIZE_RE.sub(
        "",
        " ".join(
            str(packet.get(key) or "")
            for packet in packets[:3]
            for key in ("route_label", "route_topic", "display_hint", "output_mode", "route_kind")
        ).casefold(),
    )
    if not label_text:
        return False
    matched = [token for token in tokens if token in label_text]
    return len(matched) == 0


def registry_source_search_anchor_query(cue: str | None, *, max_tokens: int = 8) -> str:
    """Extract a compact registry-wide source-search query from a vague cue.

    Low-specificity recall must not ask the user to invent a better cue from
    scratch when the original wording already contains useful anchors. Keep this
    deterministic and cheap: compact recall emits the command, while the agent
    decides whether to run the registry-wide search.
    """

    raw = str(redact_sensitive_values(redact_private_paths(str(cue or "").strip())) or "")
    tokens: list[str] = []
    seen: set[str] = set()
    for match in _CUE_TOKEN_RE.finditer(raw):
        token = match.group(0)
        key = _ANCHOR_NORMALIZE_RE.sub("", token.casefold())
        if key in _LOW_SIGNAL_WORDS or key in seen:
            continue
        seen.add(key)
        tokens.append(token)
        if len(tokens) >= max_tokens:
            break
    if tokens:
        return " ".join(tokens)
    return core.compact_text(raw, 160)


def registry_source_search_fallback_action(cue: str | None) -> dict[str, Any] | None:
    query = registry_source_search_anchor_query(cue)
    if not query or command_value_needs_input(query):
        return None
    return {
        "id": "search_registry_sources_for_original_cue_anchors",
        "label": "Search registered sources for cue anchors",
        "tool_name": "search_memory",
        "arguments": {"query": query, "scope": "all_registered_sources", "max": 5},
        "command": f"aippocampus search --all {shell_quote(query)} --json",
        "search_anchor_query": query,
        "mutation_risk": "read_only",
        "claim_boundary": "source_reopen_required_before_claim",
        "why": (
            "Recall could not choose a route safely from compact labels; search all registered "
            "sources for the original cue anchors before asking the user for a brand-new cue."
        ),
    }


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
    repeated_route_label: str | None = None,
) -> dict[str, Any]:
    secondary = dict(action)
    secondary["original_id"] = secondary.get("id") or secondary.get("action_id")
    secondary["id"] = "deepen_top_route_low_confidence"
    secondary["route_choice_posture"] = "labels_low_specificity"
    secondary["why"] = (
        "Source reopen is still read-only, but compact labels are not enough to "
        "make this the default route choice."
    )
    low_confidence_deepen_action = {
        key: value
        for key, value in normalize_foreground_action(secondary).items()
        if value not in (None, "", [])
    }
    next_action = {
        "id": "refine_low_specificity_recall_cue",
        "label": "Refine low-specificity recall cue",
        "tool_name": "agent_recall",
        "tighter_cue_template": {
            "arguments_template": {"query": "{tighter_cue}", "max": 3},
            "requires": ["tighter_cue"],
            "template_only": True,
            "command_template": 'aippocampus agent recall "{tighter_cue}" --json',
        },
        "route_choice_posture": "labels_low_specificity",
        "route_label_specificity_floor": _metric_float(
            metrics,
            "route_label_specificity_floor",
        ),
        "topic_label_present_count": _metric_int(metrics, "topic_label_present_count"),
        "packet_triage_distinctiveness": _metric_float(
            metrics,
            "packet_triage_distinctiveness",
        ),
        "mutation_risk": "read_only",
        "why": (
            "Route labels are not meaningfully distinguishable, or they fail to carry "
            "the distinctive cue anchors in compact output; use a tighter cue before "
            "choosing a route. Blind deepen remains a secondary low-confidence "
            "navigation option only."
        ),
        "claim_boundary": "no_claim_before_reopen",
    }
    if repeated_route_label:
        next_action["repeated_route_label"] = repeated_route_label
    clean_cue = str(redact_sensitive_values(redact_private_paths(str(cue or "").strip())) or "")
    next_action.update(next_action["tighter_cue_template"])
    if clean_cue and not command_value_needs_input(clean_cue):
        next_action["previous_low_specificity_cue"] = clean_cue
        next_action["previous_cue_role"] = "context_only_not_executable"
        next_action["same_cue_fallback"] = "low_confidence_not_a_substitute_for_tighter_cue"
    refine_action = {
        key: value
        for key, value in normalize_foreground_action(next_action).items()
        if value not in (None, "", [])
    }
    registry_fallback = registry_source_search_fallback_action(clean_cue)
    if registry_fallback:
        registry_fallback.update(
            {
                "route_choice_posture": "labels_low_specificity",
                "route_label_specificity_floor": refine_action.get("route_label_specificity_floor"),
                "topic_label_present_count": refine_action.get("topic_label_present_count"),
                "packet_triage_distinctiveness": refine_action.get("packet_triage_distinctiveness"),
                "same_cue_fallback": "registry_wide_source_search_before_new_user_cue",
                "alternative_action_ids": [
                    str(low_confidence_deepen_action.get("id") or ""),
                    str(refine_action.get("id") or ""),
                ],
            }
        )
        if repeated_route_label:
            registry_fallback["repeated_route_label"] = repeated_route_label
        primary = {
            key: value
            for key, value in normalize_foreground_action(registry_fallback).items()
            if value not in (None, "", [])
        }
        primary["_safe_next_actions"] = [low_confidence_deepen_action, refine_action]
        return primary
    refine_action["_safe_next_actions"] = [low_confidence_deepen_action]
    return refine_action
