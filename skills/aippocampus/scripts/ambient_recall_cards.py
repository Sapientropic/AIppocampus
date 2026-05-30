#!/usr/bin/env python3
"""Compact private ambient recall cards.

These cards are advice to the foreground agent, not user-facing text and not
formal memory. The source boundary is explicit: scent/candidate cards can guide
phrasing, while only evidence cards carry source-backed snippets.
"""

from __future__ import annotations

import hashlib
from typing import Any

from aippocampuslib import compact_text, sanitize_external_model_text
from ambient_recall_policy import policy_payload_for_working_memory

CARD_SCHEMA_VERSION = 1
MAX_CARDS = 3

SILENT_TUNING = "silent_tuning"
ACTIVE_GENTLE_NUDGE = "active_gentle_nudge"
SOURCE_BACKED_RECALL_CARD = "source_backed_recall_card"
DEEP_ARCHIVAL_RECALL = "deep_archival_recall"

SCENT = "scent"
CANDIDATE = "candidate"
EVIDENCE = "evidence"

DEFAULT_AVOID = [
    "Do not claim innate memory.",
    "Do not present scent or candidate cards as source-backed fact.",
    "Do not expose source ids unless the user asks or grounding is needed.",
]


def _stable_id(parts: list[Any]) -> str:
    raw = "\n".join(str(part or "") for part in parts)
    return "arc_" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:18]


def _safe_text(value: Any, chars: int) -> str:
    sanitized, _ = sanitize_external_model_text(str(value or ""))
    return compact_text(sanitized, chars)


def _clean_terms(values: Any, *, limit: int = 6) -> list[str]:
    if not isinstance(values, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if not text:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(_safe_text(text, 80))
        if len(out) >= limit:
            break
    return out


def _clean_source_ref(ref: dict[str, Any], *, fallback_thread: str = "", fallback_title: str = "") -> dict[str, Any]:
    clean = {
        "thread_key": ref.get("thread_key") or fallback_thread,
        "title": ref.get("title") or fallback_title,
        "line": ref.get("line"),
        "phase": ref.get("phase") or "",
        "turn_index": ref.get("turn_index"),
        "message_id": ref.get("message_id"),
    }
    return {key: value for key, value in clean.items() if value not in {None, ""}}


def _theme_from_item(item: dict[str, Any], fallback: str) -> str:
    title = str(item.get("title") or "").strip()
    terms = _clean_terms(item.get("matched_terms") or item.get("keywords") or [], limit=3)
    if title and terms:
        return _safe_text(f"{title}: {', '.join(terms)}", 140)
    if title:
        return _safe_text(title, 140)
    if terms:
        return _safe_text(", ".join(terms), 140)
    return fallback


def _evidence_card(item: dict[str, Any], *, deep_archival: bool = False) -> dict[str, Any]:
    theme = _theme_from_item(item, "source-backed prior context")
    key_line = _safe_text(item.get("snippet"), 220)
    ref = _clean_source_ref(item)
    visibility = DEEP_ARCHIVAL_RECALL if deep_archival and ref else SOURCE_BACKED_RECALL_CARD
    return {
        "card_id": _stable_id([EVIDENCE, theme, ref.get("thread_key"), ref.get("line"), key_line]),
        "theme": theme,
        "resonance": "high",
        "support_level": EVIDENCE,
        "visibility": visibility,
        "suggested_use": (
            "Open clean source before using exact wording; raw audit is only for disputed or missing clean-source details."
            if visibility == DEEP_ARCHIVAL_RECALL
            else "Use this only when the prior source changes the current answer or needs grounding."
        ),
        "nudge": "",
        "key_line": key_line,
        "matched_terms": _clean_terms(item.get("matched_terms") or []),
        "source_refs": [ref] if ref else [],
        "expand_if": (
            "Open clean source for the exact line; use raw audit only if clean source cannot settle the detail."
            if visibility == DEEP_ARCHIVAL_RECALL
            else "User asks for original wording, source details, or a disputed memory."
        ),
    }


def _candidate_card(item: dict[str, Any], *, support_level: str = SCENT) -> dict[str, Any]:
    theme = _theme_from_item(item, "related prior context")
    terms = _clean_terms(item.get("matched_terms") or item.get("keywords") or [])
    return {
        "card_id": _stable_id([support_level, theme, item.get("thread_key"), ",".join(terms)]),
        "theme": theme,
        "resonance": "medium",
        "support_level": support_level,
        "visibility": ACTIVE_GENTLE_NUDGE,
        "suggested_use": "Treat this as resonance. Lightly continue from the theme only if it helps.",
        "nudge": f"This may touch the old thread around {theme}.",
        "key_line": str((item.get("anchors") or [""])[0] or ""),
        "matched_terms": terms,
        "source_refs": [],
        "expand_if": "User asks for memory, exact context, or source-backed support.",
    }


def _working_memory_card(item: dict[str, Any]) -> dict[str, Any]:
    theme = _theme_from_item(item, "soft working memory")
    refs = [
        _clean_source_ref(ref, fallback_title=str(item.get("title") or ""))
        for ref in item.get("source_refs") or []
        if isinstance(ref, dict)
    ]
    refs = [ref for ref in refs if ref]
    is_dream = item.get("candidate_type") == "dream_hypothesis"
    card: dict[str, Any] = {
        "card_id": _stable_id([CANDIDATE, theme, item.get("route"), refs[0] if refs else ""]),
        "theme": theme,
        "resonance": "medium",
        "support_level": CANDIDATE,
        "visibility": ACTIVE_GENTLE_NUDGE
        if item.get("route") != "use_silently"
        else SILENT_TUNING,
        "suggested_use": (
            "Dream hypothesis only; use quietly and reopen source before strong claims."
            if is_dream
            else _safe_text(item.get("recommendation") or item.get("summary"), 220)
        ),
        "nudge": "",
        "key_line": _safe_text(item.get("summary"), 180),
        "matched_terms": _clean_terms(item.get("matched_terms") or []),
        "source_refs": refs[:3],
        "expand_if": (
            "Reopen clean source before presenting this dream hypothesis as a claim."
            if is_dream
            else "Search clean source before presenting exact claims as facts."
        ),
    }
    if item.get("candidate_type"):
        card["candidate_type"] = item.get("candidate_type")
    policy = policy_payload_for_working_memory(item)
    if policy:
        card["ambient_policy"] = policy
    return card


def _cognitive_map_card(item: dict[str, Any]) -> dict[str, Any]:
    labels = _clean_terms(item.get("landmark_labels") or item.get("matched_cues") or [], limit=4)
    theme = compact_text(", ".join(labels) or str(item.get("title") or "cognitive map route"), 140)
    return {
        "card_id": _stable_id([SCENT, theme, item.get("route_id")]),
        "theme": theme,
        "resonance": "medium",
        "support_level": SCENT,
        "visibility": ACTIVE_GENTLE_NUDGE,
        "suggested_use": "Use as wayfinding only; verify exact claims against clean source.",
        "nudge": f"This may follow the route around {theme}.",
        "key_line": "",
        "matched_terms": _clean_terms(item.get("matched_cues") or item.get("route_cues") or []),
        "source_refs": [],
        "expand_if": "Use clean-source search if this route would change the answer.",
    }


def _dedupe_cards(cards: list[dict[str, Any]], *, limit: int) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for card in cards:
        key = str(card.get("card_id") or "")
        if not key:
            key = _stable_id([card.get("theme"), card.get("support_level")])
            card = {**card, "card_id": key}
        if key in seen:
            continue
        seen.add(key)
        out.append(card)
        if len(out) >= limit:
            break
    return out


def _mode_for_cards(decision: str, cards: list[dict[str, Any]]) -> str:
    if not cards:
        return SILENT_TUNING
    if any(card.get("visibility") == DEEP_ARCHIVAL_RECALL for card in cards):
        return DEEP_ARCHIVAL_RECALL
    if decision == "evidence" or any(card.get("support_level") == EVIDENCE for card in cards):
        return SOURCE_BACKED_RECALL_CARD
    if any(card.get("visibility") == ACTIVE_GENTLE_NUDGE for card in cards):
        return ACTIVE_GENTLE_NUDGE
    return SILENT_TUNING


def ambient_recall_from_decision(
    result: dict[str, Any],
    *,
    cached_cards: list[dict[str, Any]] | None = None,
    cache_status: dict[str, Any] | None = None,
    cached_cards_first: bool = False,
    max_cards: int = MAX_CARDS,
) -> dict[str, Any]:
    decision = str(result.get("decision") or "skip")
    deep_archival = bool(result.get("deep_archival_requested"))
    cards: list[dict[str, Any]] = []
    if cached_cards and cached_cards_first:
        cards.extend(dict(card) for card in cached_cards if isinstance(card, dict))
    if result.get("evidence"):
        cards.extend(_evidence_card(item, deep_archival=deep_archival) for item in result.get("evidence") or [])
    if result.get("working_memory"):
        cards.extend(_working_memory_card(item) for item in result.get("working_memory") or [])
    if not cards and result.get("cognitive_map"):
        cards.extend(_cognitive_map_card(item) for item in result.get("cognitive_map") or [])
    if not cards and result.get("candidates"):
        cards.extend(_candidate_card(item) for item in result.get("candidates") or [])
    if cached_cards and not cached_cards_first:
        cards.extend(dict(card) for card in cached_cards if isinstance(card, dict))

    cards = _dedupe_cards(cards, limit=max(0, max_cards))
    mode = _mode_for_cards(decision, cards)
    return {
        "kind": "aippocampus_ambient_recall",
        "schema_version": CARD_SCHEMA_VERSION,
        "mode": mode,
        "confidence": result.get("confidence") or ("medium" if cards else "low"),
        "cards": cards,
        "avoid": list(DEFAULT_AVOID),
        "latency_ms": result.get("elapsed_ms"),
        "cache_status": cache_status or {"status": "not_used"},
        "late_update_policy": "warm_scouts_deferred",
    }
