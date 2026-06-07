#!/usr/bin/env python3
"""Render AIppocampus prompt-hook decisions into Codex hook output."""

from __future__ import annotations

from typing import Any

from aippocampus_runtime.core import compact_text, sanitize_external_model_payload
from aippocampus_runtime.recall.ambient_cards import count_cards_by_field
from aippocampus_runtime.recall.prompt_context_diagnostics import (
    brief_precision_debug_summary,
    legacy_candidate_summary_suppressed,
    route_delivery_debug_summary,
)

MAX_CONTEXT_CHARS = 1800
DREAM_HYPOTHESIS_TYPE = "dream_hypothesis"


def _is_dream_hypothesis_item(item: Any) -> bool:
    return isinstance(item, dict) and item.get("candidate_type") == DREAM_HYPOTHESIS_TYPE


def _is_dream_hypothesis_card(card: Any) -> bool:
    if not isinstance(card, dict):
        return False
    if card.get("candidate_type") == DREAM_HYPOTHESIS_TYPE:
        return True
    suggested_use = str(card.get("suggested_use") or "").casefold()
    expand_if = str(card.get("expand_if") or "").casefold()
    return "dream hypothesis" in suggested_use or "dream hypothesis" in expand_if


def _limit_dream_items(items: Any, *, allow_dream: bool, max_dream_hypotheses: int) -> tuple[list[dict[str, Any]], int, int]:
    if not isinstance(items, list):
        return [], 0, 0
    kept: list[dict[str, Any]] = []
    kept_dreams = 0
    removed_dreams = 0
    limit = max(0, int(max_dream_hypotheses))
    for item in items:
        if not isinstance(item, dict):
            continue
        if _is_dream_hypothesis_item(item):
            if allow_dream and kept_dreams < limit:
                kept.append(item)
                kept_dreams += 1
            else:
                removed_dreams += 1
            continue
        kept.append(item)
    return kept, kept_dreams, removed_dreams


def _limit_dream_cards(cards: Any, *, allow_dream: bool, max_dream_hypotheses: int) -> tuple[list[dict[str, Any]], int, int]:
    if not isinstance(cards, list):
        return [], 0, 0
    kept: list[dict[str, Any]] = []
    kept_dreams = 0
    removed_dreams = 0
    limit = max(0, int(max_dream_hypotheses))
    for card in cards:
        if not isinstance(card, dict):
            continue
        if _is_dream_hypothesis_card(card):
            if allow_dream and kept_dreams < limit:
                kept.append(card)
                kept_dreams += 1
            else:
                removed_dreams += 1
            continue
        kept.append(card)
    return kept, kept_dreams, removed_dreams


def apply_dream_delivery_boundary(
    result: dict[str, Any],
    *,
    allow_dream: bool,
    max_dream_hypotheses: int = 1,
    reason: str = "",
) -> dict[str, Any]:
    """Apply the foreground contract for delivered dream A/B.

    Dream hypotheses are allowed to enter Codex `additionalContext` only for an
    explicit delivered dream treatment. Shadow, dry-run, holdback, and default
    modes still may log sanitized events, but they must not quietly turn dream
    rows into foreground context.
    """

    copy = dict(result)
    working_memory, kept_rows, removed_rows = _limit_dream_items(
        copy.get("working_memory"),
        allow_dream=allow_dream,
        max_dream_hypotheses=max_dream_hypotheses,
    )
    copy["working_memory"] = working_memory
    ambient = copy.get("ambient_recall")
    kept_cards = 0
    removed_cards = 0
    if isinstance(ambient, dict):
        ambient_copy = dict(ambient)
        cards, kept_cards, removed_cards = _limit_dream_cards(
            ambient_copy.get("cards"),
            allow_dream=allow_dream,
            max_dream_hypotheses=max_dream_hypotheses,
        )
        ambient_copy["cards"] = cards
        if not cards:
            ambient_copy["mode"] = "silent_tuning"
        copy["ambient_recall"] = ambient_copy
    removed = removed_rows + removed_cards
    kept = kept_rows + kept_cards
    if removed or kept:
        copy["dream_delivery_boundary"] = {
            "allow_dream": allow_dream,
            "kept_dream_count": kept,
            "removed_dream_count": removed,
            "reason": reason,
        }
    has_context = bool(
        copy.get("evidence")
        or copy.get("candidates")
        or copy.get("working_memory")
        or copy.get("cognitive_map")
        or (isinstance(copy.get("ambient_recall"), dict) and copy["ambient_recall"].get("cards"))
    )
    if not has_context and copy.get("decision") != "skip":
        copy["decision"] = "skip"
        copy["score"] = 0.0
        copy["confidence"] = "low"
        copy["reasons"] = [f"dream delivery boundary: {reason or 'filtered'}"]
    return copy


def ambient_debug_summary(result: dict[str, Any]) -> dict[str, Any] | None:
    ambient = result.get("ambient_recall") if isinstance(result.get("ambient_recall"), dict) else {}
    if not ambient:
        return None
    cards = [card for card in ambient.get("cards", []) if isinstance(card, dict)]
    validation_statuses: dict[str, int] = {}
    visibility_counts: dict[str, int] = {}
    authority_counts: dict[str, int] = {}
    source_reopen_required_count = 0
    reopen_required_before_claim_count = 0
    reopen_recommended_for_exact_quote_count = 0
    for card in cards[:8]:
        visibility = str(card.get("visibility") or "")
        if visibility:
            visibility_counts[visibility] = visibility_counts.get(visibility, 0) + 1
        authority_state = str(card.get("authority_state") or "")
        if authority_state:
            authority_counts[authority_state] = authority_counts.get(authority_state, 0) + 1
        status = str((card.get("source_validation") or {}).get("status") or "")
        if status:
            validation_statuses[status] = validation_statuses.get(status, 0) + 1
        if card.get("source_reopen_required"):
            source_reopen_required_count += 1
        if card.get("reopen_required_before_claim"):
            reopen_required_before_claim_count += 1
        if card.get("reopen_recommended_for_exact_quote"):
            reopen_recommended_for_exact_quote_count += 1
    raw_cache_status = ambient.get("cache_status")
    cache_status: dict[str, Any] = raw_cache_status if isinstance(raw_cache_status, dict) else {}
    raw_brief_precision = ambient.get("brief_precision")
    brief_precision: dict[str, Any] = (
        raw_brief_precision if isinstance(raw_brief_precision, dict) else {}
    )
    raw_warm_background = ambient.get("warm_background")
    warm_background: dict[str, Any] = (
        raw_warm_background if isinstance(raw_warm_background, dict) else {}
    )
    return {
        "mode": ambient.get("mode"),
        "confidence": ambient.get("confidence"),
        "card_count": len(cards),
        "cache": {
            "status": cache_status.get("status"),
            "topic_epoch": cache_status.get("topic_epoch"),
            "card_count": cache_status.get("card_count"),
            "write_status": cache_status.get("write_status"),
        },
        "brief_precision": brief_precision_debug_summary(brief_precision),
        "warm_background": {
            "status": warm_background.get("status"),
            "spawned": warm_background.get("spawned"),
        }
        if warm_background
        else None,
        "visibility_counts": visibility_counts,
        "source_validation_statuses": validation_statuses,
        "source_reopen_required_count": source_reopen_required_count,
        "reopen_required_before_claim_count": reopen_required_before_claim_count,
        "reopen_recommended_for_exact_quote_count": reopen_recommended_for_exact_quote_count,
        "authority_counts": authority_counts,
        "trust_level_counts": count_cards_by_field(cards, "trust_level"),
        "action_grammar_counts": count_cards_by_field(cards, "action_grammar"),
        "provenance_counts": count_cards_by_field(cards, "provenance_class"),
        "support_level_counts": count_cards_by_field(cards, "support_level"),
    }


SCENT_THRESHOLD_DEBUG_REASONS = {"same_thread_decision_continuation", "semantic_reuse_hit"}
SCENT_THRESHOLD_RISK_BOUNDARIES = {
    "normal",
    "personal_continuity",
    "current_repo_fact",
    "privacy_sensitive",
}
DREAM_DELIVERY_PREFILTER_REASONS = {
    "baseline_match",
    "budget_zero",
    "eligible_but_no_candidate",
    "eligible_task_mode",
    "ineligible_task_mode",
    "recall_reminder_prompt",
    "user_disabled",
}
DREAM_DELIVERY_TASK_MODES = {
    "ambient_candidate", "coding_current_repo", "explicit_dream", "life_wide_reflection", "unknown"
}


def _debug_float(value: Any) -> float | None:
    try:
        return round(float(value), 3)
    except (TypeError, ValueError):
        return None


def scent_threshold_debug_summary(policy: Any) -> dict[str, Any] | None:
    if not isinstance(policy, dict):
        return None
    adjustments: list[dict[str, Any]] = []
    for row in policy.get("adjustments") or []:
        if not isinstance(row, dict):
            continue
        reason = str(row.get("reason") or "").strip()
        if reason not in SCENT_THRESHOLD_DEBUG_REASONS:
            continue
        delta = _debug_float(row.get("delta")) or 0.0
        adjustments.append({"reason": reason, "delta": delta})
    risk_boundary = str(policy.get("risk_boundary") or "").strip()
    if risk_boundary not in SCENT_THRESHOLD_RISK_BOUNDARIES:
        risk_boundary = "unknown"
    return {
        "base_threshold": _debug_float(policy.get("base_threshold")),
        "effective_threshold": _debug_float(policy.get("effective_threshold")),
        "adjustments": adjustments,
        "risk_boundary": risk_boundary,
    }


def dream_delivery_prefilter_debug_summary(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    reason = str(raw.get("reason") or "")
    if reason not in DREAM_DELIVERY_PREFILTER_REASONS:
        reason = "budget_zero"
    task_mode = str(raw.get("task_mode") or "")
    if task_mode not in DREAM_DELIVERY_TASK_MODES:
        task_mode = "unknown"
    return {
        "reason": reason,
        "task_mode": task_mode,
        "effective_limit": raw.get("effective_limit"),
        "candidate_dream_count": int(raw.get("candidate_dream_count") or 0),
        "prefiltered_dream_count": int(raw.get("prefiltered_dream_count") or 0),
    }


def public_hook_debug_payload(result: dict[str, Any]) -> dict[str, Any]:
    """Project hook debug JSON without leaking prompt-derived credential text.

    `assess_prompt()` keeps raw `query_terms` internally because the recall
    path needs the real prompt terms for deterministic scoring and semantic
    routing. Operator-facing JSON is different: users often paste it into
    issues, so prompt-derived debug fields must pass through the same secret
    projection used before external model calls. Do not move this redaction
    upstream into query generation; that would silently change recall behavior.
    """

    payload = {
        "decision": result.get("decision"),
        "score": result.get("score"),
        "confidence": result.get("confidence"),
        "query_terms": sanitize_external_model_payload(result.get("query_terms") or []),
        "concept_expansion_count": len(result.get("concept_expansions") or []),
        "candidate_count": len(result.get("candidates") or []),
        "evidence_count": len(result.get("evidence") or []),
        "working_memory": [],
        "working_memory_count": len(result.get("working_memory") or []),
        "ambient_recall": ambient_debug_summary(result),
        "dream_delivery_prefilter": dream_delivery_prefilter_debug_summary(
            result.get("dream_delivery_prefilter")
        ),
        "scent_threshold_policy": scent_threshold_debug_summary(
            result.get("scent_threshold_policy")
        ),
        "elapsed_ms": result.get("elapsed_ms"),
    }
    raw_semantic_gate = result.get("semantic_gate")
    if isinstance(raw_semantic_gate, dict):
        aliases = raw_semantic_gate.get("query_aliases") or raw_semantic_gate.get("aliases") or []
        payload["semantic_gate"] = {
            "available": bool(raw_semantic_gate.get("available")),
            "decision": raw_semantic_gate.get("decision"),
            "confidence": raw_semantic_gate.get("confidence"),
            "cached": bool(raw_semantic_gate.get("cached")),
            "query_aliases": sanitize_external_model_payload(aliases),
            "availability_reason": raw_semantic_gate.get("availability_reason"),
            "diagnostic": raw_semantic_gate.get("diagnostic"),
            "elapsed_ms": raw_semantic_gate.get("elapsed_ms"),
            "timeout": raw_semantic_gate.get("timeout"),
            "budget": raw_semantic_gate.get("budget"),
            "error_buckets": raw_semantic_gate.get("error_buckets") or {},
            "worker_count": raw_semantic_gate.get("worker_count")
            or len(raw_semantic_gate.get("workers") or []),
        }
    raw_hot_path = result.get("hot_path_funnel")
    if isinstance(raw_hot_path, dict):
        stages: list[dict[str, Any]] = []
        for stage in raw_hot_path.get("stages") or []:
            if not isinstance(stage, dict):
                continue
            stages.append(
                {
                    "stage": stage.get("stage"),
                    "status": stage.get("status"),
                    "candidate_count": stage.get("candidate_count"),
                    "fallback_reason": stage.get("fallback_reason") or "",
                    "elapsed_ms": stage.get("elapsed_ms"),
                }
            )
        payload["hot_path_funnel"] = {
            "decision": raw_hot_path.get("decision"),
            "candidate_count": raw_hot_path.get("candidate_count"),
            "source_reopen_promotion_count": raw_hot_path.get(
                "source_reopen_promotion_count", 0
            ),
            "local_only": bool(raw_hot_path.get("local_only")),
            "elapsed_ms": raw_hot_path.get("elapsed_ms"),
            "stages": stages[:6],
        }
        raw_living = raw_hot_path.get("living_cue_cache")
        if isinstance(raw_living, dict):
            raw_diagnostics_value = raw_living.get("diagnostics")
            raw_diagnostics = (
                raw_diagnostics_value if isinstance(raw_diagnostics_value, dict) else {}
            )
            diagnostics = {
                key: raw_diagnostics.get(key, 0)
                for key in (
                    "cache_hit_count",
                    "cache_miss_count",
                    "selected_count",
                    "stale_suppressed_count",
                    "temporary_suppressed_count",
                    "would_overpersonalize_count",
                    "low_confidence_suppressed_count",
                    "missing_source_ref_count",
                    "live_llm_call_count",
                )
            }
            payload["hot_path_funnel"]["living_cue_cache"] = {
                "decision": raw_living.get("decision"),
                "support_level": raw_living.get("support_level"),
                "selected_count": raw_living.get("selected_count", 0),
                "candidate_ref_count": len(raw_living.get("candidate_refs") or []),
                "diagnostics": diagnostics,
            }
    route_delivery = route_delivery_debug_summary(result.get("route_delivery_diagnostic"))
    if route_delivery is not None:
        payload["route_delivery_diagnostic"] = route_delivery
    return payload


def semantic_route_hint_lines(result: dict[str, Any]) -> list[str]:
    semantic_gate = result.get("semantic_gate")
    if not isinstance(semantic_gate, dict) or not semantic_gate.get("available"):
        return []
    source_required_route = _fresh_packet_source_required(result)
    aliases = [
        str(value)
        for value in sanitize_external_model_payload(
            semantic_gate.get("query_aliases") or semantic_gate.get("aliases") or []
        )
        if str(value).strip()
    ][:6]
    scopes = [
        str(value)
        for value in sanitize_external_model_payload(semantic_gate.get("memory_scope") or [])
        if str(value).strip()
    ][:4]
    if not aliases and not scopes:
        return []
    if semantic_gate.get("decision") not in {"scent", "evidence"} and not result.get(
        "semantic_bridge_diagnostic"
    ):
        return []
    route_label = (
        "source_required/reopenable_route"
        if source_required_route
        else "direction_only"
    )
    lines = [f"Semantic recall route ({route_label}; reopen clean source before facts):"]
    parts: list[str] = []
    if aliases:
        parts.append("aliases: " + ", ".join(aliases))
    if scopes:
        parts.append("scope: " + ", ".join(scopes))
    if parts:
        lines.append("- " + " | ".join(parts))
    if result.get("semantic_bridge_diagnostic"):
        lines.append("- Local evidence bridge did not pass; keep this as route material only.")
    return lines


def _fresh_packet(result: dict[str, Any]) -> dict[str, Any]:
    ambient = result.get("ambient_recall") if isinstance(result.get("ambient_recall"), dict) else {}
    packet = ambient.get("fresh_thread_packet") if isinstance(ambient, dict) else {}
    return packet if isinstance(packet, dict) else {}


def _fresh_packet_source_required(result: dict[str, Any]) -> bool:
    packet = _fresh_packet(result)
    return bool(
        packet.get("support_level") == "source_required"
        and packet.get("action_grammar") == "reopenable_route"
    )


def fresh_packet_reopen_lines(result: dict[str, Any]) -> list[str]:
    packet = _fresh_packet(result)
    if not (
        packet.get("support_level") == "source_required"
        and packet.get("action_grammar") == "reopenable_route"
    ):
        return []
    raw_plan = packet.get("reopen_plan")
    plan: dict[str, Any] = raw_plan if isinstance(raw_plan, dict) else {}
    if plan.get("status") != "ready":
        return []
    raw_arguments = plan.get("arguments")
    arguments: dict[str, Any] = raw_arguments if isinstance(raw_arguments, dict) else {}
    argument_text = ", ".join(f"{key}={value}" for key, value in arguments.items())
    if not argument_text:
        argument_text = "primary_ref"
    return [
        "Source-required recall route (reopenable_route; not evidence yet):",
        (
            f"- Use {plan.get('recommended_tool') or 'source_ref_reopen'} with "
            f"{argument_text}; candidate refs {plan.get('candidate_ref_count', 0)}, "
            "manual query invention expected: false."
        ),
    ]


def _ambient_brief_layer(action: str) -> str:
    """Map action grammar to the three foreground brief layers from #791.

    This is only a rendering grouping. It must not promote a card's authority:
    trust_level/action_grammar remain the source of truth for what the agent can
    do with the material.
    """

    if action in {"bounded_evidence", "source_open", "reopenable_route", "direction_with_ref"}:
        return "working_continuity_brief"
    if action == "ignore_or_blocked":
        return "source_court"
    return "memory_atmosphere"


def _ambient_brief_layer_heading(layer: str) -> str:
    if layer == "working_continuity_brief":
        return (
            "Working continuity brief "
            "(candidate-backed direction, reopenable routes, bounded evidence, and source-open material):"
        )
    if layer == "source_court":
        return "Source court (blocked, exact, sensitive, stale, conflict, or high-risk routes):"
    return "Memory atmosphere (direction_only orientation; no factual claim support):"


def _bounded_evidence_cards(result: dict[str, Any]) -> list[dict[str, Any]]:
    ambient = result.get("ambient_recall") if isinstance(result.get("ambient_recall"), dict) else {}
    cards = ambient.get("cards") if isinstance(ambient, dict) else []
    if not isinstance(cards, list):
        return []
    return [
        card
        for card in cards
        if isinstance(card, dict)
        and str(card.get("action_grammar") or "") in {"bounded_evidence", "source_open"}
    ]


def _has_direction_with_ref_card(result: dict[str, Any]) -> bool:
    ambient = result.get("ambient_recall") if isinstance(result.get("ambient_recall"), dict) else {}
    cards = ambient.get("cards") if isinstance(ambient, dict) else []
    if not isinstance(cards, list):
        return False
    return any(
        isinstance(card, dict) and str(card.get("action_grammar") or "") == "direction_with_ref"
        for card in cards
    )


def _evidence_boundary_line(evidence_cards: list[dict[str, Any]]) -> str:
    actions = {str(card.get("action_grammar") or "") for card in evidence_cards}
    if "source_open" in actions:
        return (
            "Do not paste long source windows verbatim. Use source_open for scoped exact wording "
            "within redaction boundaries; reopen or deepen for wider context, conflicts, sensitive "
            "or high-risk claims."
        )
    return (
        "Do not paste snippets verbatim; exact quotes or broader claims should reopen source."
    )


def _evidence_card_line(card: dict[str, Any]) -> str:
    refs = [ref for ref in card.get("source_refs") or [] if isinstance(ref, dict)]
    ref = refs[0] if refs else {}
    line = f" line {ref.get('line')}" if ref.get("line") is not None else ""
    phase = f", {ref.get('phase')}" if ref.get("phase") else ""
    turn = f", turn {ref.get('turn_index')}" if ref.get("turn_index") is not None else ""
    action = str(card.get("action_grammar") or "bounded_evidence")
    title = card.get("theme") or ref.get("title") or ref.get("thread_key") or "source-backed context"
    key_line = compact_text(str(card.get("key_line") or ""), 240)
    return f"- [{action}] {title}{line}{phase}{turn}: {key_line}"


def context_for_hook(result: dict[str, Any], *, max_chars: int = MAX_CONTEXT_CHARS) -> str | None:
    decision = result.get("decision")
    if decision == "skip":
        return None
    lines: list[str] = []
    if decision == "evidence":
        lines.append(
            "Ambient recall evidence (aippocampus). Use bounded source-backed evidence when relevant; reopen only for disputed exact wording or wider context:"
        )
        evidence_cards = _bounded_evidence_cards(result)
        if evidence_cards:
            for card in evidence_cards[:3]:
                lines.append(_evidence_card_line(card))
        else:
            for item in result.get("evidence") or []:
                phase = f", {item.get('phase')}" if item.get("phase") else ""
                turn = f", turn {item.get('turn_index')}" if item.get("turn_index") is not None else ""
                lines.append(
                    f"- {item.get('title')} line {item.get('line')}{phase}{turn}: "
                    f"{compact_text(str(item.get('snippet') or ''), 240)}"
                )
        lines.append(_evidence_boundary_line(evidence_cards))
    else:
        has_direction_with_ref = _has_direction_with_ref_card(result)
        if _fresh_packet_source_required(result):
            lines.append(
                "Ambient recall route (aippocampus source_required). Reopen source before facts:"
            )
        elif has_direction_with_ref:
            lines.append(
                "Ambient recall candidate-backed direction (aippocampus direction_with_ref). Use refs as route context, not fact:"
            )
        else:
            lines.append("Ambient recall scent (aippocampus direction_only). Related prior context:")
        visible_candidates = (
            []
            if legacy_candidate_summary_suppressed(result)
            else list(result.get("candidates") or [])
        )
        route_lines = [*fresh_packet_reopen_lines(result), *semantic_route_hint_lines(result)]
        candidate_lines: list[str] = []
        for item in visible_candidates:
            anchors = ", ".join(item.get("anchors") or [])
            terms = ", ".join(item.get("matched_terms") or item.get("keywords") or [])
            tail = f" | terms: {terms}" if terms else ""
            candidate_lines.append(f"- {item.get('title')}: {anchors}{tail}")
        if candidate_lines or route_lines or has_direction_with_ref:
            lines.extend(candidate_lines)
            lines.extend(route_lines)
            lines.append(
                "Use only if it helps; do not mention recalled content as fact unless backed by bounded_evidence, source_open, or reopened source."
            )
        else:
            lines.clear()
    if result.get("working_memory"):
        lines.append("Soft working memory candidates (working continuity; source-backed staging):")
        for item in result.get("working_memory") or []:
            terms = ", ".join(item.get("matched_terms") or [])
            refs = item.get("source_refs") or []
            ref = refs[0] if refs else {}
            source = ""
            if ref:
                source = (
                    f" | source: {ref.get('title') or ref.get('thread_key')} line {ref.get('line')}"
                )
            if item.get("candidate_type") == "dream_hypothesis":
                invitation = item.get("prospective_invitation") or {}
                artifact = item.get("constructive_artifact") or {}
                journey_bridge = item.get("journey_bridge_hypothesis") or {}
                use_plan = item.get("dream_hypothesis_use") or {}
                rendered_specific = False
                if (
                    isinstance(invitation, dict)
                    and invitation.get("suggested_opening")
                    and isinstance(use_plan, dict)
                    and use_plan.get("action") == "deliver_as_optional_question"
                ):
                    opening = compact_text(str(invitation.get("suggested_opening") or ""), 220)
                    invitation_type = str(invitation.get("invitation_type") or "light_question")
                    lines.append(
                        f"- Prospective Dream invitation, not source fact "
                        f"({invitation_type}, terms: {terms}): {opening}{source}"
                    )
                    rendered_specific = True
                if (
                    isinstance(journey_bridge, dict)
                    and journey_bridge.get("unblock_condition")
                    and isinstance(use_plan, dict)
                    and use_plan.get("action") == "deliver_as_optional_unblock_probe"
                ):
                    unblock = compact_text(str(journey_bridge.get("unblock_condition") or ""), 220)
                    bridge_kind = str(journey_bridge.get("bridge_kind") or "journey_bridge")
                    lines.append(
                        f"- Journey bridge Dream hypothesis, not source fact "
                        f"({bridge_kind}; optional unblock probe, terms: {terms}): "
                        f"{unblock}{source}"
                    )
                    rendered_specific = True
                if isinstance(artifact, dict) and artifact.get("draft_text"):
                    draft_kind = str(artifact.get("artifact_kind") or "draft_probe")
                    draft = compact_text(str(artifact.get("draft_text") or ""), 220)
                    lines.append(
                        f"- Dream draft, not source fact "
                        f"({draft_kind}; optional probe, terms: {terms}): {draft}{source}"
                    )
                    rendered_specific = True
                if not rendered_specific:
                    lines.append(
                        f"- Dream hypothesis, not source fact: {item.get('title')} "
                        f"(confidence {item.get('confidence')}, terms: {terms}): "
                        f"{compact_text(str(item.get('summary') or ''), 220)}"
                        f"{source}"
                    )
                lines.append(
                    "  Use quietly only if this changes the route; reopen source before any strong claim."
                )
                continue
            lines.append(
                f"- [{item.get('route')}] {item.get('title')} "
                f"(confidence {item.get('confidence')}, terms: {terms}): "
                f"{compact_text(str(item.get('summary') or ''), 220)}"
                f"{source}"
            )
            if item.get("route") == "confirm_when_relevant":
                lines.append(
                    "  Ask the user only if this would change the current action or sources conflict."
                )
        lines.append(
            "For working-memory exact claims, reopen clean source; bounded_evidence can guide action within its declared scope."
        )
    if result.get("cognitive_map"):
        lines.append("Cognitive map routes (DeepSeek subconscious direction_only wayfinding):")
        for item in result.get("cognitive_map") or []:
            cues = ", ".join(item.get("matched_cues") or item.get("route_cues") or [])
            landmarks = ", ".join(item.get("landmark_labels") or [])
            lines.append(
                f"- {landmarks or item.get('title')}: cues {cues}; "
                f"threads {', '.join(item.get('thread_keys') or [])}"
            )
        lines.append("Treat these as wayfinding only; verify exact or source-sensitive claims against clean source.")
    ambient = result.get("ambient_recall") or {}
    ambient_cards = ambient.get("cards") or []
    if ambient_cards:
        lines.append(
            "Ambient recall private context (agent guidance; source use follows action grammar):"
        )
        layered_cards: dict[str, list[str]] = {
            "memory_atmosphere": [],
            "working_continuity_brief": [],
            "source_court": [],
        }
        for card in ambient_cards[:3]:
            support = str(card.get("support_level") or "scent")
            trust = str(card.get("trust_level") or support)
            action = str(card.get("action_grammar") or trust)
            visibility = str(card.get("visibility") or ambient.get("mode") or "silent_tuning")
            provenance = str(card.get("provenance_class") or "")
            theme = compact_text(str(card.get("theme") or ""), 120)
            suggested_use = compact_text(str(card.get("suggested_use") or ""), 180)
            if provenance == "cached_warm_card":
                provenance_note = "cached warm candidate"
            elif provenance == "warm_scout_proposal":
                provenance_note = "warm scout proposal"
            elif provenance == "cognitive_map_route":
                provenance_note = "wayfinding route"
            elif provenance == "source_backed_reopen":
                provenance_note = "source-backed reopen candidate"
            else:
                provenance_note = "navigation hint"
            source_note = ""
            if action == "bounded_evidence":
                source_note = " source-backed refs available; bounded source-backed evidence"
            elif action == "source_open":
                source_note = " raw source open; exact wording still scope/redaction-bound"
            elif action == "reopenable_route":
                source_note = " actionable source-reopen route"
            elif action == "direction_with_ref":
                source_note = " candidate-backed refs available; route guidance only, not evidence"
            elif action == "ignore_or_blocked":
                source_note = " blocked or unsafe to use"
            if visibility == "deep_archival_recall":
                source_note += " deep archival requested"
            evidence_line = ""
            if support == "evidence" and card.get("key_line"):
                evidence_line = f" Evidence: {compact_text(str(card.get('key_line') or ''), 180)}"
            layered_cards[_ambient_brief_layer(action)].append(
                f"- {provenance_note} {visibility}/{support}/{trust}/{action}: {theme}."
                f"{source_note}{evidence_line} Use: {suggested_use}"
            )
        for layer in ("memory_atmosphere", "working_continuity_brief", "source_court"):
            rows = layered_cards[layer]
            if not rows:
                continue
            lines.append(_ambient_brief_layer_heading(layer))
            lines.extend(rows)
        lines.append(
            "Use bounded_evidence within scope, source_open for scoped exact wording, "
            "reopenable_route by reopening source, direction_with_ref as candidate-backed direction, "
            "and direction_only only as attention. "
            "Escalate to source court for exact quotes, wider context, conflicts, stale/sensitive/high-risk claims, or ignore_or_blocked routes."
        )
    if result.get("reasons"):
        if not lines:
            return None
        lines.append("Why: " + "; ".join(str(reason) for reason in result.get("reasons", [])[:3]))
    elif not lines:
        return None
    context = "\n".join(lines)
    return compact_text(context, max_chars)


def hook_stdout_payload(result: dict[str, Any]) -> dict[str, Any] | None:
    context = context_for_hook(result)
    if not context:
        return None
    return {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": context,
        }
    }
