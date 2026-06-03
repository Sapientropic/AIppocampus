#!/usr/bin/env python3
"""Render AIppocampus prompt-hook decisions into Codex hook output."""

from __future__ import annotations

from typing import Any

from aippocampus_runtime.core import compact_text, sanitize_external_model_payload
from aippocampus_runtime.recall.ambient_cards import count_cards_by_field

MAX_CONTEXT_CHARS = 1800
DREAM_HYPOTHESIS_TYPE = "dream_hypothesis"
ROUTE_DELIVERY_FOREGROUND_PROFILES = {"ambient_hot_path", "explicit_recall"}
ROUTE_DELIVERY_REUSE_SOURCES = {
    "none",
    "exact_semantic_cache",
    "cold_model_call",
    "semantic_cue_cache",
}
ROUTE_DELIVERY_BRIDGE_DIAGNOSTICS = {"semantic_evidence_without_source_bridge"}


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


def route_delivery_debug_summary(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None

    def controlled(value: Any, allowed: set[str]) -> str | None:
        text = str(value or "")
        return text if text in allowed else None

    def count(value: Any) -> int:
        try:
            return max(0, int(value))
        except (TypeError, ValueError):
            return 0

    summary = {
        "foreground_profile": controlled(
            raw.get("foreground_profile"), ROUTE_DELIVERY_FOREGROUND_PROFILES
        )
        or "ambient_hot_path",
        "semantic_bridge_diagnostic": controlled(
            raw.get("semantic_bridge_diagnostic"), ROUTE_DELIVERY_BRIDGE_DIAGNOSTICS
        ),
        "semantic_gate_cache_hit_but_no_source_bridge": bool(
            raw.get("semantic_gate_cache_hit_but_no_source_bridge")
        ),
        "semantic_reuse_source": controlled(
            raw.get("semantic_reuse_source"), ROUTE_DELIVERY_REUSE_SOURCES
        )
        or "none",
        "semantic_waited": bool(raw.get("semantic_waited")),
        "cold_semantic_shadowed": bool(raw.get("cold_semantic_shadowed")),
        "background_scheduled": bool(raw.get("background_scheduled")),
        "hot_path_candidates_after_merge": count(
            raw.get("hot_path_candidates_after_merge")
        ),
        "final_candidate_count": count(raw.get("final_candidate_count")),
        "evidence_count": count(raw.get("evidence_count")),
    }
    return {key: value for key, value in summary.items() if value is not None}


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
    source_reopen_required_count = 0
    for card in cards[:8]:
        visibility = str(card.get("visibility") or "")
        if visibility:
            visibility_counts[visibility] = visibility_counts.get(visibility, 0) + 1
        status = str((card.get("source_validation") or {}).get("status") or "")
        if status:
            validation_statuses[status] = validation_statuses.get(status, 0) + 1
        if card.get("source_reopen_required"):
            source_reopen_required_count += 1
    raw_cache_status = ambient.get("cache_status")
    cache_status: dict[str, Any] = raw_cache_status if isinstance(raw_cache_status, dict) else {}
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
        "warm_background": {
            "status": warm_background.get("status"),
            "spawned": warm_background.get("spawned"),
        }
        if warm_background
        else None,
        "visibility_counts": visibility_counts,
        "source_validation_statuses": validation_statuses,
        "source_reopen_required_count": source_reopen_required_count,
        "provenance_counts": count_cards_by_field(cards, "provenance_class"),
        "support_level_counts": count_cards_by_field(cards, "support_level"),
    }


SCENT_THRESHOLD_DEBUG_REASONS = {
    "same_thread_decision_continuation",
    "semantic_reuse_hit",
}
SCENT_THRESHOLD_RISK_BOUNDARIES = {"normal", "current_repo_fact", "privacy_sensitive"}


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
    route_delivery = route_delivery_debug_summary(result.get("route_delivery_diagnostic"))
    if route_delivery is not None:
        payload["route_delivery_diagnostic"] = route_delivery
    return payload


def semantic_route_hint_lines(result: dict[str, Any]) -> list[str]:
    semantic_gate = result.get("semantic_gate")
    if not isinstance(semantic_gate, dict) or not semantic_gate.get("available"):
        return []
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
    lines = ["Semantic recall route (not evidence; search clean source before facts):"]
    parts: list[str] = []
    if aliases:
        parts.append("aliases: " + ", ".join(aliases))
    if scopes:
        parts.append("scope: " + ", ".join(scopes))
    if parts:
        lines.append("- " + " | ".join(parts))
    if result.get("semantic_bridge_diagnostic"):
        lines.append("- Local evidence bridge did not pass; keep this as navigation only.")
    return lines


def context_for_hook(result: dict[str, Any], *, max_chars: int = MAX_CONTEXT_CHARS) -> str | None:
    decision = result.get("decision")
    if decision == "skip":
        return None
    lines: list[str] = []
    if decision == "evidence":
        lines.append(
            "Ambient recall evidence (aippocampus). Treat as retrieved hints, not automatic truth:"
        )
        for item in result.get("evidence") or []:
            phase = f", {item.get('phase')}" if item.get("phase") else ""
            turn = f", turn {item.get('turn_index')}" if item.get("turn_index") is not None else ""
            lines.append(
                f"- {item.get('title')} line {item.get('line')}{phase}{turn}: "
                f"{compact_text(str(item.get('snippet') or ''), 240)}"
            )
        lines.append(
            "Use these only when relevant; search the source thread before relying on exact wording."
        )
    else:
        lines.append(
            "Ambient recall scent (aippocampus). Possible related old-thread memory, not evidence:"
        )
        for item in result.get("candidates") or []:
            anchors = ", ".join(item.get("anchors") or [])
            terms = ", ".join(item.get("matched_terms") or item.get("keywords") or [])
            tail = f" | terms: {terms}" if terms else ""
            lines.append(f"- {item.get('title')}: {anchors}{tail}")
        lines.extend(semantic_route_hint_lines(result))
        lines.append(
            "Use only if it helps; do not mention recalled content as fact unless backed by retrieved evidence."
        )
    if result.get("working_memory"):
        lines.append("Soft working memory candidates (source-backed staging, not formal truth):")
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
            "For source-backed working memory, search clean source before presenting exact claims as facts."
        )
    if result.get("cognitive_map"):
        lines.append("Cognitive map routes (DeepSeek subconscious navigation hints, not evidence):")
        for item in result.get("cognitive_map") or []:
            cues = ", ".join(item.get("matched_cues") or item.get("route_cues") or [])
            landmarks = ", ".join(item.get("landmark_labels") or [])
            lines.append(
                f"- {landmarks or item.get('title')}: cues {cues}; "
                f"threads {', '.join(item.get('thread_keys') or [])}"
            )
        lines.append("Treat these as wayfinding only; verify exact claims against clean source.")
    ambient = result.get("ambient_recall") or {}
    ambient_cards = ambient.get("cards") or []
    if ambient_cards:
        lines.append("Ambient recall private context (card/cache first; not user text):")
        for card in ambient_cards[:3]:
            support = str(card.get("support_level") or "scent")
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
            source_note = " source-backed refs available" if support == "evidence" else ""
            if visibility == "deep_archival_recall":
                source_note += " deep archival requested"
            lines.append(
                f"- {provenance_note} {visibility}/{support}: {theme}."
                f"{source_note} Use: {suggested_use}"
            )
        lines.append("Let these cards tune the answer; do not paste them verbatim.")
    if result.get("reasons"):
        lines.append("Why: " + "; ".join(str(reason) for reason in result.get("reasons", [])[:3]))
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
