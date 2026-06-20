"""Dream-delivery foreground gate for prompt context rendering."""

from __future__ import annotations

from typing import Any

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
