"""Foreground prompt-hook projection budgets and public-safe width metrics."""

from __future__ import annotations

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
