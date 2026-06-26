#!/usr/bin/env python3
"""Render AIppocampus prompt-hook decisions into Codex hook output."""

from __future__ import annotations

from typing import Any

from aippocampus_runtime.core import compact_text, sanitize_external_model_payload
from aippocampus_runtime.recall.ambient_cards import count_cards_by_field
from aippocampus_runtime.recall.hook_agent_affordance import (
    build_hook_agent_affordance,
    prepend_hook_agent_affordance,
)
from aippocampus_runtime.recall.prompt_context_diagnostics import (
    brief_precision_debug_summary,
    legacy_candidate_summary_suppressed,
    route_delivery_debug_summary,
)
from aippocampus_runtime.recall.prompt_context_dream import (
    apply_dream_delivery_boundary as _apply_dream_delivery_boundary,
)
from aippocampus_runtime.recall.prompt_foreground_budget import (
    ambient_cards as _ambient_cards,
)
from aippocampus_runtime.recall.prompt_foreground_budget import (
    compact_weak_scent_lines,
    foreground_context_debug_summary,
    has_direction_with_ref_card,
    is_weak_direction_only_scent,
    truncate_preserving_lines,
    weak_scent_suppressed_by_anti_nag,
)
from aippocampus_runtime.recall.prompt_recall_hot_path_debug import hot_path_debug_summary
from aippocampus_runtime.recall.semantic_gate_response import (
    public_count,
    public_error_buckets,
    public_partial_failure_reasons,
    public_semantic_budget,
)

MAX_CONTEXT_CHARS = 1800
apply_dream_delivery_boundary = _apply_dream_delivery_boundary


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
    raw_cache_diagnostic = cache_status.get("cache_read_diagnostic")
    cache_diagnostic: dict[str, Any] = (
        raw_cache_diagnostic if isinstance(raw_cache_diagnostic, dict) else {}
    )
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
            **(
                {
                    "read_diagnostic": {
                        "status": cache_diagnostic.get("status"),
                        "reason_code": cache_diagnostic.get("reason_code"),
                        "warning_count": cache_diagnostic.get("warning_count"),
                        "path_label": cache_diagnostic.get("path_label"),
                    }
                }
                if cache_diagnostic
                else {}
            ),
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

    foreground_context = context_for_hook(result) or ""
    agent_affordance = build_hook_agent_affordance(result)
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
        "foreground_context": foreground_context_debug_summary(
            result,
            context=foreground_context,
        ),
        "agent_recall_affordance": agent_affordance,
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
            "budget": public_semantic_budget(raw_semantic_gate.get("budget")),
            "error_buckets": public_error_buckets(raw_semantic_gate.get("error_buckets")),
            "worker_count": raw_semantic_gate.get("worker_count")
            or len(raw_semantic_gate.get("workers") or []),
            "successful_worker_count": public_count(
                raw_semantic_gate.get("successful_worker_count")
            ),
            "failed_worker_count": public_count(raw_semantic_gate.get("failed_worker_count")),
            "partial_success": bool(raw_semantic_gate.get("partial_success")),
            "partial_failure_reasons": public_partial_failure_reasons(
                raw_semantic_gate.get("partial_failure_reasons")
            ),
        }
    hot_path = hot_path_debug_summary(result.get("hot_path_funnel"))
    if hot_path is not None:
        payload["hot_path_funnel"] = hot_path
    route_delivery = route_delivery_debug_summary(result.get("route_delivery_diagnostic"))
    if route_delivery is not None:
        payload["route_delivery_diagnostic"] = route_delivery
    if isinstance(result.get("degraded_warnings"), list):
        payload["degraded_warnings"] = sanitize_external_model_payload(
            result.get("degraded_warnings")
        )
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


def _evidence_suppressed_by_anti_nag(result: dict[str, Any]) -> bool:
    raw_ambient = result.get("ambient_recall")
    ambient: dict[str, Any] = raw_ambient if isinstance(raw_ambient, dict) else {}
    token_values = [*(ambient.get("anti_nag_token_ids") or []), *(result.get("anti_nag_token_ids") or [])]
    if not any(str(value).strip() for value in token_values):
        return False
    raw_policy_filter = ambient.get("policy_filter")
    raw_feedback_filter = ambient.get("feedback_filter")
    policy_suppressed = isinstance(raw_policy_filter, dict) and any(
        int(raw_policy_filter.get(key) or 0) > 0 for key in ("dismissed", "frequency_capped")
    )
    feedback_suppressed = (
        isinstance(raw_feedback_filter, dict)
        and int(raw_feedback_filter.get("quieted_card_count") or 0) > 0
    )
    return bool(policy_suppressed or feedback_suppressed)


def _explicit_architecture_navigation(result: dict[str, Any]) -> bool:
    intent = result.get("agent_surface_intent")
    if not isinstance(intent, dict) or not intent.get("explicit"):
        return False
    return "architecture_navigation" in [str(item) for item in intent.get("surfaces") or []]


def _architecture_navigation_only(result: dict[str, Any]) -> bool:
    if not _explicit_architecture_navigation(result):
        return False
    if result.get("decision") == "evidence":
        return False
    if _fresh_packet_source_required(result) or has_direction_with_ref_card(result):
        return False
    return not _bounded_evidence_cards(result)


def _has_foregroundable_ambient_card(result: dict[str, Any]) -> bool:
    raw_ambient = result.get("ambient_recall")
    if not isinstance(raw_ambient, dict):
        return False
    raw_cards = raw_ambient.get("cards")
    if not isinstance(raw_cards, list):
        return False
    cards = raw_cards
    raw_cache_status = raw_ambient.get("cache_status")
    cache_status: dict[str, Any] = raw_cache_status if isinstance(raw_cache_status, dict) else {}
    raw_source_reopen = raw_ambient.get("source_reopen")
    source_reopen: dict[str, Any] = raw_source_reopen if isinstance(raw_source_reopen, dict) else {}
    cache_hit = str(cache_status.get("status") or "") in {"hit", "related_hit"} and int(
        cache_status.get("card_count") or 0
    ) > 0
    reopen_success = int(source_reopen.get("success_count") or 0) > 0
    if not (cache_hit or reopen_success):
        return False
    for card in cards:
        if not isinstance(card, dict):
            continue
        action = str(card.get("action_grammar") or "")
        raw_trust = card.get("trust_contract")
        trust: dict[str, Any] = raw_trust if isinstance(raw_trust, dict) else {}
        if action and action != "ignore_or_blocked" and not trust.get("agent_should_ignore"):
            return True
    return False

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
    action = str(card.get("action_grammar") or "bounded_evidence")
    title = card.get("theme") or ref.get("title") or ref.get("thread_key") or "source-backed context"
    key_line = compact_text(str(card.get("key_line") or ""), 240)
    return f"- [{action}] {title}{line}: {key_line}"


def _needs_source_court_boundary(cards: list[dict[str, Any]]) -> bool:
    for card in cards:
        action = str(card.get("action_grammar") or card.get("trust_level") or "").strip()
        if action in {"bounded_evidence", "source_open", "reopenable_route", "direction_with_ref"}:
            return True
    return False


def context_for_hook(result: dict[str, Any], *, max_chars: int = MAX_CONTEXT_CHARS) -> str | None:
    """aippocampus-stage-map: classify decision -> render source-safe route lines -> append soft sidecars -> compact."""

    if result.get("decision") == "skip" and not _has_foregroundable_ambient_card(result):
        affordance_lines = prepend_hook_agent_affordance(result, [])
        if not affordance_lines:
            return None
        if _explicit_architecture_navigation(result):
            affordance_lines.append(
                "Architecture navigation available (aippocampus). Use agent_recall or agent_explain for topology, attention-router, macro-orientation, or local/global route diagnostics."
            )
            affordance_lines.append(
                "Ambient memory routes are suppressed here unless they are source-required or candidate-backed; run explicit recall if old conversation context becomes relevant."
            )
        return truncate_preserving_lines("\n".join(affordance_lines), max_chars)
    if is_weak_direction_only_scent(result):
        if legacy_candidate_summary_suppressed(result) and not _ambient_cards(result):
            return None
        if weak_scent_suppressed_by_anti_nag(result):
            return None
        weak_lines = prepend_hook_agent_affordance(result, compact_weak_scent_lines(result))
        return truncate_preserving_lines(
            "\n".join(weak_lines),
            max_chars,
        )
    lines: list[str] = prepend_hook_agent_affordance(result, [])
    if result.get("decision") == "evidence":
        evidence_cards = _bounded_evidence_cards(result)
        if not evidence_cards and _evidence_suppressed_by_anti_nag(result):
            return None
        lines.append(
            "Ambient recall evidence (aippocampus). Use bounded source-backed evidence when relevant; reopen only for disputed exact wording or wider context:"
        )
        if evidence_cards:
            for card in evidence_cards[:3]:
                lines.append(_evidence_card_line(card))
        else:
            for item in result.get("evidence") or []:
                lines.append(
                    f"- {item.get('title')} line {item.get('line')}: "
                    f"{compact_text(str(item.get('snippet') or ''), 240)}"
                )
        lines.append(_evidence_boundary_line(evidence_cards))
    else:
        if _architecture_navigation_only(result):
            lines.append(
                "Architecture navigation available (aippocampus). Use agent_recall or agent_explain for topology, attention-router, macro-orientation, or local/global route diagnostics."
            )
            lines.append(
                "Ambient memory routes are suppressed here unless they are source-required or candidate-backed; run explicit recall if old conversation context becomes relevant."
            )
            return truncate_preserving_lines("\n".join(lines), max_chars)
        has_direction_with_ref = has_direction_with_ref_card(result)
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
            # Keep the active-pull affordance when semantic or multilingual
            # continuity intent exists but the hook has no source-safe route to
            # print. Clearing the envelope here made the strongest vague-recall
            # cues silently disappear in foreground hosts; the agent can still
            # call recall/deepen without receiving any source content as fact.
            if lines:
                lines.append(
                    "No source route was opened in the hook; call agent_recall only if prior context would change the answer."
                )
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
        lines.append("Cognitive map routes / registry overviews (direction_only wayfinding):")
        for item in result.get("cognitive_map") or []:
            provenance = str(item.get("provenance_class") or item.get("kind") or "")
            label = (
                "registry overview"
                if provenance == "cognitive_map_registry_overview"
                else "source-backed route"
            )
            cues = ", ".join(item.get("matched_cues") or item.get("route_cues") or [])
            landmarks = ", ".join(item.get("landmark_labels") or [])
            lines.append(
                f"- [{label}] {landmarks or item.get('title')}: cues {cues}; "
                f"threads {', '.join(item.get('thread_keys') or [])}"
            )
        lines.append(
            "Treat these as wayfinding only; registry overviews are not source-backed routes, "
            "and exact or source-sensitive claims still require clean-source reopen."
        )
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
            elif provenance == "cognitive_map_registry_overview":
                provenance_note = "registry far-view overview"
            elif provenance == "source_backed_reopen":
                provenance_note = "source-backed reopen candidate"
            elif provenance == "continuity_domain_pointer":
                provenance_note = "continuity domain pointer"
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
            if provenance == "continuity_domain_pointer":
                source_note += " pointer only; domain brief is not source truth"
            if visibility == "deep_archival_recall":
                source_note += " deep archival requested"
            evidence_line = ""
            if support == "evidence" and card.get("key_line"):
                evidence_line = f" Evidence: {compact_text(str(card.get('key_line') or ''), 180)}"
            action_path = (
                f"{visibility}/{support}/{action}"
                if trust == support
                else f"{visibility}/{support}/{trust}/{action}"
            )
            layered_cards[_ambient_brief_layer(action)].append(
                f"- {action_path} {provenance_note}: {theme}."
                f"{source_note}{evidence_line} Use: {suggested_use}"
            )
        for layer in ("memory_atmosphere", "working_continuity_brief", "source_court"):
            rows = layered_cards[layer]
            if not rows:
                continue
            lines.append(_ambient_brief_layer_heading(layer))
            lines.extend(rows)
        if _needs_source_court_boundary(ambient_cards):
            lines.append(
                "Use source-backed cards only within scope; reopen or deepen for exact quotes, wider context, conflicts, or stale/sensitive claims."
            )
    if not lines:
        return None
    context = "\n".join(lines)
    return compact_text(str(sanitize_external_model_payload(context)), max_chars)


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
