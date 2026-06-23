"""Foreground hygiene helpers for ambient recall cards."""

from __future__ import annotations

import re
from typing import Any


def _brief_tokens(text: str) -> set[str]:
    return {token.casefold() for token in re.findall(r"[\w\u4e00-\u9fff]{2,}", text)}


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


def _has_concrete_reopen_path(card: dict[str, Any]) -> bool:
    if any(isinstance(ref, dict) for ref in card.get("source_refs") or []):
        return True
    reopen_plan = card.get("reopen_plan")
    if isinstance(reopen_plan, dict) and reopen_plan:
        return True
    return str(card.get("action_grammar") or "") in {
        "source_open",
        "bounded_evidence",
        "reopenable_route",
    }


def _looks_like_current_prompt_echo(card: dict[str, Any], prompt: str) -> bool:
    prompt_text = re.sub(r"\s+", "", str(prompt or "")).casefold()
    if not prompt_text:
        return False
    card_text = re.sub(r"\s+", "", _card_brief_text(card)).casefold()
    if not card_text:
        return False
    min_echo_len = 6 if re.search(r"[\u4e00-\u9fff]", prompt_text + card_text) else 12
    if len(card_text) >= min_echo_len and card_text in prompt_text:
        return True
    if len(prompt_text) >= min_echo_len and prompt_text in card_text:
        return True
    prompt_tokens = _brief_tokens(prompt)
    card_tokens = _brief_tokens(card_text)
    if len(prompt_tokens) < 3 or not card_tokens:
        return False
    return len(prompt_tokens & card_tokens) / max(1, len(card_tokens)) >= 0.75


def demote_no_ref_active_cards(
    cards: list[dict[str, Any]],
    *,
    prompt: str,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Keep no-source ambient self-echoes as background residue.

    A card with no source ref or reopen plan can still be useful for tuning,
    but it cannot claim the foreground "active nudge" lane. This helper keeps
    that UX boundary out of the already crowded card assembly module.
    """

    no_ref_active = 0
    no_ref_residue = 0
    self_echo_suppressed = 0
    out: list[dict[str, Any]] = []
    for card in cards:
        if (
            card.get("visibility") == "active_gentle_nudge"
            and not _has_concrete_reopen_path(card)
        ):
            no_ref_active += 1
            no_ref_residue += 1
            if _looks_like_current_prompt_echo(card, prompt):
                self_echo_suppressed += 1
            clean = dict(card)
            clean["visibility"] = "silent_tuning"
            clean["foreground_residue_reason"] = "no_source_ref_or_reopen_plan"
            clean["suggested_use"] = (
                "Keep as background resonance only; do not foreground without a source route."
            )
            out.append(clean)
            continue
        out.append(card)
    return out, {
        "no_ref_active_card_count": no_ref_active,
        "no_ref_residue_count": no_ref_residue,
        "self_echo_suppressed_count": self_echo_suppressed,
    }


__all__ = ["demote_no_ref_active_cards"]
