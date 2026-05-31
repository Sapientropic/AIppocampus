#!/usr/bin/env python3
"""Render AIppocampus prompt-hook decisions into Codex hook output."""

from __future__ import annotations

from typing import Any

from aippocampus_runtime.core import compact_text

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
    for card in cards[:8]:
        visibility = str(card.get("visibility") or "")
        if visibility:
            visibility_counts[visibility] = visibility_counts.get(visibility, 0) + 1
        status = str((card.get("source_validation") or {}).get("status") or "")
        if status:
            validation_statuses[status] = validation_statuses.get(status, 0) + 1
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
    }


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
            theme = compact_text(str(card.get("theme") or ""), 120)
            suggested_use = compact_text(str(card.get("suggested_use") or ""), 180)
            source_note = " source-backed refs available" if support == "evidence" else ""
            if visibility == "deep_archival_recall":
                source_note += " deep archival requested"
            lines.append(f"- {visibility}/{support}: {theme}.{source_note} Use: {suggested_use}")
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
