"""Precision ranking for foreground ambient recall cards."""

from __future__ import annotations

# aippocampus-instruction-surface: ambient card ranking owner; brief precision text is local ranking policy, not a prompt.
import re
from typing import Any

from aippocampus_runtime.recall.query_profile import classify_query_profile

EVIDENCE = "evidence"
ISSUE_REF_RE = re.compile(r"#\d+\b")
BRIEF_TOKEN_RE = re.compile(r"#[0-9]+\b|[a-zA-Z][a-zA-Z0-9_-]{2,}")
RECENT_ISSUE_PROMPT_RE = re.compile(
    r"\b(just|recent|current|opened|same[- ]thread|this issue|this thread)\b|刚才|刚刚|这次|这个",
    re.IGNORECASE,
)
GENERIC_ISSUE_SUMMARY_RE = re.compile(
    r"\b(open issue summary|issue summary|open issues?|roadmap|cleanup|"
    r"created executable slices|broad|summary|public-readiness|milestone|labels?)\b",
    re.IGNORECASE,
)
RECENT_TURN_MISMATCH_WINDOW = 20


def _brief_tokens(text: str) -> set[str]:
    return {match.group(0).casefold() for match in BRIEF_TOKEN_RE.finditer(text or "")}


def _card_brief_text(card: dict[str, Any]) -> str:
    refs = card.get("source_refs") or []
    ref_text = " ".join(
        str(ref.get("title") or ref.get("thread_key") or "")
        for ref in refs
        if isinstance(ref, dict)
    )
    return " ".join(
        str(value or "")
        for value in [
            card.get("theme"),
            card.get("key_line"),
            card.get("suggested_use"),
            " ".join(str(term or "") for term in card.get("matched_terms") or []),
            ref_text,
        ]
    )


def _card_recency_hint(card: dict[str, Any]) -> tuple[int, int]:
    best_turn = -1
    best_line = -1
    for ref in card.get("source_refs") or []:
        if not isinstance(ref, dict):
            continue
        try:
            best_turn = max(best_turn, int(ref.get("turn_index") or -1))
        except (TypeError, ValueError):
            pass
        try:
            best_line = max(best_line, int(ref.get("line") or -1))
        except (TypeError, ValueError):
            pass
    return best_turn, best_line


def _action_priority(card: dict[str, Any]) -> int:
    action = str(card.get("action_grammar") or "")
    if action == "source_open":
        return 5
    if action == "bounded_evidence":
        return 4
    if action == "reopenable_route":
        return 3
    if action == "direction_with_ref":
        return 2
    if action == "direction_only":
        return 1
    return 0


def _partial_old_generic_issue_context(
    *,
    prompt_issue_refs: set[str],
    card_issue_refs: set[str],
    brief_text: str,
    issue_overlap: int,
    turn_hint: int,
    max_issue_turn_hint: int,
    recent_issue_ref_coverage: set[str],
    prompt_has_recent_issue_cue: bool,
    action_priority: int,
) -> bool:
    if len(prompt_issue_refs) < 2 or issue_overlap <= 0:
        return False
    if action_priority < 4:
        return False
    if not prompt_has_recent_issue_cue:
        return False
    if len(card_issue_refs & prompt_issue_refs) >= len(prompt_issue_refs):
        return False
    if not prompt_issue_refs.issubset(recent_issue_ref_coverage):
        return False
    if turn_hint < 0 or max_issue_turn_hint - turn_hint < RECENT_TURN_MISMATCH_WINDOW:
        return False
    return bool(GENERIC_ISSUE_SUMMARY_RE.search(brief_text))


def _query_profile_diagnostics(profile: dict[str, Any]) -> dict[str, Any]:
    return {
        "foreground_route_profile": profile.get("profile") or "normal_recall",
        "foreground_lane": profile.get("lane") or "source_text",
        "generic_prompt_term_count": int(profile.get("generic_prompt_term_count") or 0),
        "specific_prompt_term_count": int(profile.get("specific_prompt_term_count") or 0),
    }


def _apply_foreground_composer(
    cards: list[dict[str, Any]],
    profile: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if profile.get("composer") != "suppress_generic_scent":
        return cards, {
            "alias_spillover_suppressed_count": 0,
            "cross_project_generic_scent_suppressed_count": 0,
            "composer_backstage_count": 0,
            "foreground_suppression_reasons": [],
        }
    kept: list[dict[str, Any]] = []
    backstage_count = 0
    for card in cards:
        support = str(card.get("support_level") or "")
        # Source-backed cards and high-action guidance remain foregroundable;
        # the generic meta profile only backstages weak scent/candidate cards.
        if support == EVIDENCE or _action_priority(card) >= 3:
            kept.append(card)
        else:
            backstage_count += 1
    reasons = ["generic_meta_terms_only"] if backstage_count else []
    return kept, {
        "alias_spillover_suppressed_count": backstage_count,
        "cross_project_generic_scent_suppressed_count": backstage_count,
        "composer_backstage_count": backstage_count,
        "foreground_suppression_reasons": reasons,
    }


def rank_cards_for_brief(
    cards: list[dict[str, Any]],
    *,
    prompt: str = "",
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Prefer precise current-brief evidence before generic source-backed clutter.

    Bounded evidence is allowed to influence the foreground agent, so its
    ordering matters more than ordinary scent ordering. Keep the signal local:
    issue refs, prompt-token overlap, and source recency only decide which
    already-authorized card gets the scarce foreground slot. They must not
    promote scent/candidate material into evidence or serialize prompt text.
    """

    profile = classify_query_profile(prompt)
    prompt_tokens = _brief_tokens(prompt)
    prompt_issue_refs = {match.group(0).casefold() for match in ISSUE_REF_RE.finditer(prompt or "")}
    cards, composer_diagnostics = _apply_foreground_composer(cards, profile)
    if not prompt_tokens and not prompt_issue_refs:
        return cards, {
            "sort_applied": False,
            "prompt_issue_ref_count": 0,
            "broad_context_intrusion_count": 0,
            "partial_issue_ref_broad_context_count": 0,
            "same_thread_recentness_mismatch_count": 0,
            "foreground_card_count": len(cards),
            **_query_profile_diagnostics(profile),
            **composer_diagnostics,
        }

    prompt_has_recent_issue_cue = bool(RECENT_ISSUE_PROMPT_RE.search(prompt or ""))
    max_issue_turn_hint = -1
    card_issue_refs_by_index: dict[int, set[str]] = {}
    turn_hints_by_index: dict[int, int] = {}
    for index, card in enumerate(cards):
        brief_text = _card_brief_text(card)
        card_issue_refs = {match.group(0).casefold() for match in ISSUE_REF_RE.finditer(brief_text)}
        issue_overlap = len(prompt_issue_refs & card_issue_refs)
        turn_hint, _ = _card_recency_hint(card)
        card_issue_refs_by_index[index] = card_issue_refs
        turn_hints_by_index[index] = turn_hint
        if issue_overlap:
            max_issue_turn_hint = max(max_issue_turn_hint, turn_hint)
    recent_issue_ref_coverage: set[str] = set()
    if max_issue_turn_hint >= 0:
        for index, card_issue_refs in card_issue_refs_by_index.items():
            turn_hint = turn_hints_by_index.get(index, -1)
            if max_issue_turn_hint - turn_hint <= RECENT_TURN_MISMATCH_WINDOW:
                recent_issue_ref_coverage.update(prompt_issue_refs & card_issue_refs)

    broad_context_intrusion_count = 0
    partial_issue_ref_broad_context_count = 0
    same_thread_recentness_mismatch_count = 0
    decorated: list[tuple[tuple[int, int, int, int, int, int], int, dict[str, Any]]] = []
    for index, card in enumerate(cards):
        brief_text = _card_brief_text(card)
        card_tokens = _brief_tokens(brief_text)
        card_issue_refs = card_issue_refs_by_index.get(index, set())
        issue_overlap = len(prompt_issue_refs & card_issue_refs)
        token_overlap = len(prompt_tokens & card_tokens)
        extra_issue_refs = max(0, len(card_issue_refs) - issue_overlap)
        if prompt_issue_refs and extra_issue_refs >= 3:
            broad_context_intrusion_count += 1
        action_priority = _action_priority(card)
        turn_hint, line_hint = _card_recency_hint(card)
        partial_old_generic = _partial_old_generic_issue_context(
            prompt_issue_refs=prompt_issue_refs,
            card_issue_refs=card_issue_refs,
            brief_text=brief_text,
            issue_overlap=issue_overlap,
            turn_hint=turn_hint,
            max_issue_turn_hint=max_issue_turn_hint,
            recent_issue_ref_coverage=recent_issue_ref_coverage,
            prompt_has_recent_issue_cue=prompt_has_recent_issue_cue,
            action_priority=action_priority,
        )
        if partial_old_generic:
            partial_issue_ref_broad_context_count += 1
            same_thread_recentness_mismatch_count += 1
            broad_context_intrusion_count += 1
        issue_precision = issue_overlap * 10 - extra_issue_refs * 4
        if partial_old_generic:
            issue_precision -= 20
        if prompt_issue_refs:
            rank_key = (
                issue_precision,
                token_overlap,
                action_priority,
                -extra_issue_refs,
                turn_hint,
                line_hint,
            )
        else:
            rank_key = (
                action_priority,
                token_overlap,
                -extra_issue_refs,
                turn_hint,
                line_hint,
                0,
            )
        decorated.append((rank_key, -index, card))
    ranked = [card for _, _, card in sorted(decorated, reverse=True)]
    return ranked, {
        "sort_applied": True,
        "prompt_issue_ref_count": len(prompt_issue_refs),
        "broad_context_intrusion_count": broad_context_intrusion_count,
        "partial_issue_ref_broad_context_count": partial_issue_ref_broad_context_count,
        "same_thread_recentness_mismatch_count": same_thread_recentness_mismatch_count,
        "foreground_card_count": len(ranked),
        **_query_profile_diagnostics(profile),
        **composer_diagnostics,
    }


__all__ = ["rank_cards_for_brief"]
