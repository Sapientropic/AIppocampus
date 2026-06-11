"""Foreground prompt-hook projection budgets and public-safe width metrics."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from aippocampus_runtime.core import compact_text

WEAK_SCENT_CONTEXT_MAX_CHARS = 650
WEAK_SCENT_CONTEXT_MAX_LINES = 9
DIRECTION_ONLY_BOILERPLATE_MARKERS = (
    "Use bounded_evidence within scope",
    "source_open for scoped exact wording",
    "reopenable_route by reopening source",
    "direction_with_ref as candidate-backed direction",
    "Escalate to source court",
)
DEBUG_ONLY_FOREGROUND_MARKERS = (
    "action_grammar_counts",
    "cache_hit",
    "cache miss",
    "sidecar diagnostics",
    "source-generation",
    "alias-source",
    "route id",
    "candidate-ref counts",
    "cannot_claim",
)
HIGHER_AUTHORITY_ACTIONS = {
    "bounded_evidence",
    "source_open",
    "reopenable_route",
    "direction_with_ref",
    "ignore_or_blocked",
}
MEMORY_PACKET_MAX_BYTES = 480
MEMORY_PACKET_TOTAL_MAX_BYTES = 1800
MEMORY_PACKET_MAX_HINTS = 4
PROFILE_LIKE_MARKERS = (
    "adhd",
    "anxiety",
    "identity",
    "personality",
    "profile",
    "ficus",
    "private impression",
    "dislikes",
    "hates",
)
FOREGROUND_PACKET_ALLOWED_KEYS = {
    "kind",
    "schema_version",
    "route_id",
    "output_mode",
    "display_hint",
    "route_label",
    "why_may_matter",
    "preview_permission",
    "risk_flags",
    "triage_rank_reason_codes",
    "claim_permission",
    "next_action",
    "deepen_route_id",
    "review_needed",
    "suppression_reason",
}
TRIAGE_TEXT_KEYS = (
    "display_hint",
    "route_label",
    "why_may_matter",
    "preview_permission",
)


def ambient_cards(result: dict[str, Any]) -> list[dict[str, Any]]:
    ambient = result.get("ambient_recall") if isinstance(result.get("ambient_recall"), dict) else {}
    cards = ambient.get("cards") if isinstance(ambient, dict) else []
    if not isinstance(cards, list):
        return []
    return [card for card in cards if isinstance(card, dict)]


def fresh_packet_source_required(result: dict[str, Any]) -> bool:
    ambient = result.get("ambient_recall") if isinstance(result.get("ambient_recall"), dict) else {}
    packet = ambient.get("fresh_thread_packet") if isinstance(ambient, dict) else {}
    if not isinstance(packet, dict):
        return False
    return bool(
        packet.get("support_level") == "source_required"
        and packet.get("action_grammar") == "reopenable_route"
    )


def has_direction_with_ref_card(result: dict[str, Any]) -> bool:
    return any(
        str(card.get("action_grammar") or "") == "direction_with_ref"
        for card in ambient_cards(result)
    )


def cognitive_map_rows(result: dict[str, Any]) -> list[dict[str, Any]]:
    rows = result.get("cognitive_map")
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)]


def _has_higher_authority_route(result: dict[str, Any]) -> bool:
    if result.get("evidence") or result.get("working_memory"):
        return True
    if fresh_packet_source_required(result):
        return True
    semantic_gate = result.get("semantic_gate")
    if isinstance(semantic_gate, dict) and semantic_gate.get("available"):
        return True
    for card in ambient_cards(result):
        action = str(card.get("action_grammar") or card.get("trust_level") or "").strip()
        if action in HIGHER_AUTHORITY_ACTIONS:
            return True
    return False


def _route_label(value: Any) -> str:
    return compact_text(str(value or "").strip(), 96)


def _weak_scent_card_label(card: dict[str, Any]) -> str:
    label = str(card.get("theme") or card.get("title") or "").strip()
    provenance = str(card.get("provenance_class") or "")
    if provenance == "cached_warm_card" and label:
        label = f"{label} (cached warm candidate)"
    return label


def _weak_scent_cognitive_map_label(row: dict[str, Any]) -> str:
    labels = row.get("landmark_labels")
    if isinstance(labels, list):
        label_text = ", ".join(str(label) for label in labels if str(label).strip())
    else:
        label_text = ""
    return str(row.get("title") or label_text or "").strip()


def weak_scent_route_labels(result: dict[str, Any], *, max_routes: int = 3) -> list[str]:
    labels: list[str] = []
    seen: set[str] = set()

    def add(label: Any) -> None:
        text = _route_label(label)
        key = text.casefold()
        if not text or key in seen or len(labels) >= max_routes:
            return
        seen.add(key)
        labels.append(text)

    for item in result.get("candidates") or []:
        if not isinstance(item, dict):
            continue
        add(item.get("title") or ", ".join(item.get("anchors") or []))
    for row in cognitive_map_rows(result):
        add(_weak_scent_cognitive_map_label(row))
    for card in ambient_cards(result):
        add(_weak_scent_card_label(card))
    return labels


def is_weak_direction_only_scent(result: dict[str, Any]) -> bool:
    if result.get("decision") != "scent":
        return False
    if _has_higher_authority_route(result):
        return False
    for card in ambient_cards(result):
        action = str(card.get("action_grammar") or card.get("trust_level") or "").strip()
        if action and action != "direction_only":
            return False
    return bool(
        result.get("candidates")
        or ambient_cards(result)
        or cognitive_map_rows(result)
        or result.get("reasons")
    )


def compact_weak_scent_lines(result: dict[str, Any]) -> list[str]:
    reasons = [
        str(reason).strip()
        for reason in result.get("reasons") or []
        if str(reason).strip()
    ][:2]
    why_now = compact_text("; ".join(reasons), 140) if reasons else "weak route scent"
    lines = [
        "Ambient recall scent (aippocampus compact direction_only):",
        "action: direction_only",
        f"why_now: {why_now}",
        "routes:",
    ]
    labels = weak_scent_route_labels(result, max_routes=3)
    if labels:
        lines.extend(f"- {label}" for label in labels)
    else:
        lines.append("- related prior context")
    lines.append(
        "can_use: orientation only; must_reopen_for: exact quotes, source-backed claims, "
        "public issue/comment text; next: reopen/deepen only if this changes the answer"
    )
    return lines


def line_count(context: str) -> int:
    return context.count("\n") + 1 if context else 0


def truncate_preserving_lines(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    half = max_chars // 2
    return text[:half].rstrip() + " ... " + text[-half:].lstrip()


def foreground_context_debug_summary(
    result: dict[str, Any],
    *,
    context: str,
) -> dict[str, Any]:
    candidate_count = len(result.get("candidates") or [])
    context_line_count = line_count(context)
    debug_only_field_leak_count = sum(
        1 for marker in DEBUG_ONLY_FOREGROUND_MARKERS if marker in context
    )
    boilerplate_chars = sum(
        len(marker) for marker in DIRECTION_ONLY_BOILERPLATE_MARKERS if marker in context
    )
    weak_scent = is_weak_direction_only_scent(result)
    direction_only_projection = bool(
        result.get("decision") == "scent"
        and not _has_higher_authority_route(result)
        and (
            "direction_only" in context
            or result.get("candidates")
            or ambient_cards(result)
            or cognitive_map_rows(result)
        )
    )
    budget_violation = int(
        weak_scent
        and (
            len(context) > WEAK_SCENT_CONTEXT_MAX_CHARS
            or context_line_count > WEAK_SCENT_CONTEXT_MAX_LINES
            or debug_only_field_leak_count > 0
            or boilerplate_chars > 0
        )
    )
    direction_only_budget_violation = int(
        direction_only_projection
        and (
            len(context) > WEAK_SCENT_CONTEXT_MAX_CHARS
            or context_line_count > WEAK_SCENT_CONTEXT_MAX_LINES
            or debug_only_field_leak_count > 0
            or boilerplate_chars > 0
        )
    )
    return {
        "foreground_context_chars": len(context),
        "foreground_context_line_count": context_line_count,
        "foreground_context_chars_per_candidate": round(
            len(context) / max(1, candidate_count), 2
        ),
        "direction_only_boilerplate_chars": boilerplate_chars,
        "direction_only_actionable_route_count": len(
            weak_scent_route_labels(result, max_routes=3)
        )
        if weak_scent
        else 0,
        "weak_scent_payload_budget_violation_count": budget_violation,
        "direction_only_foreground_budget_violation_count": direction_only_budget_violation,
        "debug_only_field_leak_count": debug_only_field_leak_count,
        "observatory_debug_payload_available": bool(
            result.get("ambient_recall")
            or result.get("hot_path_funnel")
            or result.get("route_delivery_diagnostic")
        ),
    }


def _packet_bytes(packet: dict[str, Any]) -> int:
    return len(json.dumps(packet, ensure_ascii=False, sort_keys=True).encode("utf-8"))


def _contains_profile_like_detail(text: str) -> bool:
    folded = text.casefold()
    return any(marker in folded for marker in PROFILE_LIKE_MARKERS)


def _packet_triage_text(packet: dict[str, Any]) -> str:
    values = [str(packet.get(key) or "") for key in TRIAGE_TEXT_KEYS]
    values.extend(str(value) for value in packet.get("risk_flags") or [])
    values.extend(str(value) for value in packet.get("triage_rank_reason_codes") or [])
    return " ".join(value for value in values if value)


def _has_selection_hint(packet: Mapping[str, Any]) -> bool:
    label = str(packet.get("route_label") or "").strip()
    hint = str(packet.get("display_hint") or "").strip()
    return bool(label) and bool(
        hint
        and hint != "A source route may matter; reopen it before using the detail."
    )


def _triage_signature(packet: Mapping[str, Any]) -> str:
    return "|".join(
        [
            str(packet.get("route_label") or "").casefold(),
            str(packet.get("display_hint") or "").casefold(),
            ",".join(str(code) for code in packet.get("triage_rank_reason_codes") or []),
        ]
    )


def _packet_triage_distinctiveness(packets: list[dict[str, Any]]) -> float:
    triage_packets = [
        packet
        for packet in packets
        if packet.get("output_mode") in {"bounded_summary_as_route", "reopenable_route"}
    ]
    if not triage_packets:
        return 0.0
    signatures = {
        _triage_signature(packet)
        for packet in triage_packets
        if _has_selection_hint(packet)
    }
    return round(len(signatures) / len(triage_packets), 3)


def _blind_deepen_required_count(packets: list[dict[str, Any]]) -> int:
    return sum(
        1
        for packet in packets
        if packet.get("output_mode") == "reopenable_route"
        and packet.get("next_action") == "reopen_source"
        and not _has_selection_hint(packet)
    )


def _allowed_packet_fields(packet: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in packet.items() if key in FOREGROUND_PACKET_ALLOWED_KEYS}


def _review_needed_packet(packet: dict[str, Any], *, reason: str) -> dict[str, Any]:
    route_id = str(packet.get("route_id") or "route:unknown")
    return {
        "kind": "aippocampus_memory_packet",
        "schema_version": str(packet.get("schema_version") or "foreground-memory-budget-v0"),
        "route_id": route_id,
        "output_mode": "direction_only",
        "display_hint": "Memory route needs review before foreground use.",
        "claim_permission": "no_claim_before_reopen",
        "next_action": "ask_light_question",
        "deepen_route_id": str(packet.get("deepen_route_id") or f"deepen:{route_id}"),
        "review_needed": True,
        "suppression_reason": reason,
    }


def _normalize_memory_packet(packet: dict[str, Any]) -> tuple[dict[str, Any], dict[str, int]]:
    metrics = {
        "profile_like_suppressed_count": 0,
        "unnecessary_reopen_prevented_count": 0,
    }
    clean = _allowed_packet_fields(packet)
    if _contains_profile_like_detail(_packet_triage_text(clean)):
        metrics["profile_like_suppressed_count"] = 1
        return _review_needed_packet(clean, reason="profile_like_detail"), metrics

    if (
        clean.get("output_mode") == "bounded_summary_as_route"
        and clean.get("claim_permission") == "no_claim_before_reopen"
        and clean.get("next_action") == "reopen_source"
    ):
        clean["next_action"] = "use_hint"
        metrics["unnecessary_reopen_prevented_count"] = 1
    return clean, metrics


def project_memory_packets_for_foreground(
    packets: list[dict[str, Any]],
    *,
    dismissed_route_ids: set[str] | None = None,
    max_hints: int = MEMORY_PACKET_MAX_HINTS,
) -> dict[str, Any]:
    """Apply #1125 foreground UX budget and anti-nag rules to memory packets.

    This projection is intentionally stricter than the lower route contracts:
    ordinary foreground output gets small hints only. Source handles, profile
    impressions, head votes, and proof ledgers stay behind deepen/explain or a
    review surface.
    """

    dismissed = dismissed_route_ids or set()
    foreground: list[dict[str, Any]] = []
    suppressed_recent = 0
    profile_suppressed = 0
    reopen_prevented = 0
    for packet in packets:
        route_id = str(packet.get("route_id") or "")
        if route_id in dismissed:
            suppressed_recent += 1
            continue
        clean, packet_metrics = _normalize_memory_packet(packet)
        profile_suppressed += packet_metrics["profile_like_suppressed_count"]
        reopen_prevented += packet_metrics["unnecessary_reopen_prevented_count"]
        if len(foreground) < max_hints:
            foreground.append(clean)

    encoded = json.dumps(foreground, ensure_ascii=False, sort_keys=True)
    packet_sizes = [_packet_bytes(packet) for packet in foreground]
    total_bytes = sum(packet_sizes)
    false_personalization_count = sum(
        1
        for packet in foreground
        if _contains_profile_like_detail(_packet_triage_text(packet))
    )
    blind_deepen_count = _blind_deepen_required_count(foreground)
    top_route_selection_hint_present_count = sum(
        1
        for packet in foreground
        if packet.get("output_mode") in {"bounded_summary_as_route", "reopenable_route"}
        and _has_selection_hint(packet)
    )
    over_cautious_abstention_count = sum(
        1
        for packet in foreground
        if packet.get("output_mode") == "bounded_summary_as_route"
        and packet.get("next_action") == "reopen_source"
    )
    source_backed_claim_without_reopen = sum(
        1
        for packet in foreground
        if packet.get("claim_permission") == "bounded_claim_allowed"
        and packet.get("output_mode") != "bounded_evidence"
    )
    metrics = {
        "foreground_hint_count": len(foreground),
        "foreground_packet_bytes": total_bytes,
        "foreground_packet_max_bytes": max(packet_sizes) if packet_sizes else 0,
        "foreground_packet_budget_violation_count": int(
            total_bytes > MEMORY_PACKET_TOTAL_MAX_BYTES
            or any(size > MEMORY_PACKET_MAX_BYTES for size in packet_sizes)
        ),
        "unnecessary_reopen_count": over_cautious_abstention_count,
        "unnecessary_reopen_prevented_count": reopen_prevented,
        "over_cautious_abstention_count": over_cautious_abstention_count,
        "false_personalization_count": false_personalization_count,
        "profile_like_suppressed_count": profile_suppressed,
        "anti_nag_suppressed_count": suppressed_recent,
        "anti_nag_violation_count": int(any(route in encoded for route in dismissed)),
        "packet_triage_distinctiveness": _packet_triage_distinctiveness(foreground),
        "blind_deepen_required_count": blind_deepen_count,
        "top_route_selection_hint_present_count": top_route_selection_hint_present_count,
        "source_backed_claim_without_reopen": source_backed_claim_without_reopen,
        "debug_or_source_field_leak_count": sum(
            1
            for marker in (
                "source_handles",
                "source_id",
                "head_votes",
                "masks_applied",
                "PRIVATE_PROFILE_SENTINEL",
            )
            if marker in encoded
        ),
    }
    red_lines = {
        "foreground_packet_budget_violation_count": metrics[
            "foreground_packet_budget_violation_count"
        ],
        "unnecessary_reopen_count": metrics["unnecessary_reopen_count"],
        "false_personalization_count": metrics["false_personalization_count"],
        "anti_nag_violation_count": metrics["anti_nag_violation_count"],
        "source_backed_claim_without_reopen": metrics["source_backed_claim_without_reopen"],
        "debug_or_source_field_leak_count": metrics["debug_or_source_field_leak_count"],
    }
    return {
        "kind": "aippocampus_foreground_memory_budget_projection",
        "schema_version": "foreground-memory-budget-v0",
        "ok": all(value == 0 for value in red_lines.values()),
        "foreground_packets": foreground,
        "metrics": metrics,
        "red_lines": red_lines,
        "budget": {
            "max_packet_bytes": MEMORY_PACKET_MAX_BYTES,
            "max_total_bytes": MEMORY_PACKET_TOTAL_MAX_BYTES,
            "max_hints": max_hints,
        },
        "privacy_boundary": {
            "ordinary_packets_include_profile_like_detail": False,
            "ordinary_packets_include_source_handles": False,
            "raw_private_text_emitted": False,
        },
    }


def foreground_memory_budget_fixture_packets() -> list[dict[str, Any]]:
    return [
        {
            "kind": "aippocampus_memory_packet",
            "schema_version": "agent-native-recall-facade-v0",
            "route_id": "route_tiny_orientation",
            "output_mode": "direction_only",
            "display_hint": "Style route: keep the patch small and source-backed.",
            "claim_permission": "no_claim_before_reopen",
            "next_action": "use_hint",
            "deepen_route_id": "deepen:route_tiny_orientation",
        },
        {
            "kind": "aippocampus_memory_packet",
            "schema_version": "agent-native-recall-facade-v0",
            "route_id": "route_bounded_summary",
            "output_mode": "bounded_summary_as_route",
            "display_hint": "Project route: use the scoped summary for planning; reopen before claims.",
            "claim_permission": "no_claim_before_reopen",
            "next_action": "reopen_source",
            "deepen_route_id": "deepen:route_bounded_summary",
        },
        {
            "kind": "aippocampus_memory_packet",
            "schema_version": "agent-native-recall-facade-v0",
            "route_id": "route_reopenable",
            "output_mode": "reopenable_route",
            "display_hint": "Old decision route may matter; reopen source before using the detail.",
            "claim_permission": "no_claim_before_reopen",
            "next_action": "reopen_source",
            "deepen_route_id": "deepen:route_reopenable",
        },
        {
            "kind": "aippocampus_memory_packet",
            "schema_version": "agent-native-recall-facade-v0",
            "route_id": "route_profile_like",
            "output_mode": "direction_only",
            "display_hint": "User profile: ADHD, hates abstractions. PRIVATE_PROFILE_SENTINEL",
            "claim_permission": "no_claim_before_reopen",
            "next_action": "use_hint",
            "deepen_route_id": "deepen:route_profile_like",
            "source_handles": [{"source_id": "src_private"}],
        },
        {
            "kind": "aippocampus_memory_packet",
            "schema_version": "agent-native-recall-facade-v0",
            "route_id": "route_recently_dismissed",
            "output_mode": "direction_only",
            "display_hint": "Dismissed route should not repeat in ordinary foreground output.",
            "claim_permission": "no_claim_before_reopen",
            "next_action": "use_hint",
            "deepen_route_id": "deepen:route_recently_dismissed",
        },
    ]


def build_foreground_memory_budget_fixture_report() -> dict[str, Any]:
    """Return the public-safe #1125 foreground memory UX budget fixture."""

    projection = project_memory_packets_for_foreground(
        foreground_memory_budget_fixture_packets(),
        dismissed_route_ids={"route_recently_dismissed"},
    )
    projection["cannot_claim"] = [
        "default_hook_adoption",
        "private_ficus_quality",
        "profile_memory_safety",
        "live_user_annoyance_rate",
        "broad_foreground_lift",
    ]
    return projection
