#!/usr/bin/env python3
"""Compact private ambient recall cards.

These cards are advice to the foreground agent, not user-facing text and not
formal memory. The source boundary is explicit: scent/candidate cards can guide
phrasing, while only evidence cards carry source-backed snippets.
"""

from __future__ import annotations

import hashlib
from typing import Any

from aippocampus_runtime.core import compact_text, sanitize_external_model_text
from aippocampus_runtime.recall.ambient_policy import policy_payload_for_working_memory
from aippocampus_runtime.recall.authority import with_authority_fields, with_trust_fields
from aippocampus_runtime.recall.fresh_thread_scent import fresh_thread_scent_packet_from_decision
from aippocampus_runtime.recall.nudge_policy import safe_nudge_topic

CARD_SCHEMA_VERSION = 1
MAX_CARDS = 3
MAX_BOUNDED_EVIDENCE_CHARS = 220

SILENT_TUNING = "silent_tuning"
ACTIVE_GENTLE_NUDGE = "active_gentle_nudge"
SOURCE_BACKED_RECALL_CARD = "source_backed_recall_card"
DEEP_ARCHIVAL_RECALL = "deep_archival_recall"

SCENT = "scent"
CANDIDATE = "candidate"
EVIDENCE = "evidence"

DETERMINISTIC_CUE = "deterministic_cue"
SOURCE_BACKED_REOPEN = "source_backed_reopen"
WARM_SCOUT_PROPOSAL = "warm_scout_proposal"
CACHED_WARM_CARD = "cached_warm_card"
COGNITIVE_MAP_ROUTE = "cognitive_map_route"
WORKING_MEMORY_SOURCE = "working_memory_source"
WORKING_MEMORY_MODEL = "working_memory_model"

DEFAULT_AVOID = [
    "Do not claim innate memory.",
    "Do not present scent or candidate cards as source-backed fact.",
    "Do not expose source ids unless the user asks or grounding is needed.",
]


def _stable_id(parts: list[Any]) -> str:
    raw = "\n".join(str(part or "") for part in parts)
    return "arc_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:18]


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
        "source_id": ref.get("source_id"),
        "title": ref.get("title") or fallback_title,
        "line": ref.get("line"),
        "phase": ref.get("phase") or "",
        "turn_id": ref.get("turn_id"),
        "turn_index": ref.get("turn_index"),
        "message_id": ref.get("message_id"),
    }
    return {key: value for key, value in clean.items() if value not in {None, ""}}


def _reopenable_ref_count(card: dict[str, Any]) -> int:
    return len([ref for ref in card.get("source_refs") or [] if isinstance(ref, dict)])


def with_card_provenance(
    card: dict[str, Any],
    provenance_class: str,
    *,
    cached_origin: str | None = None,
    cache_status: dict[str, Any] | None = None,
    source_reopen_required: bool = True,
) -> dict[str, Any]:
    """Attach navigation provenance without weakening source-backed semantics.

    Provenance only tells the foreground agent how a card was produced. It must
    not replace `support_level`, `visibility`, or `source_validation`; exact
    claims still need clean-source reopen unless a supported evidence path says
    otherwise.
    """

    clean = dict(card)
    clean["provenance_class"] = provenance_class
    if cached_origin:
        clean["cached_origin"] = cached_origin
    clean["source_reopen_required"] = bool(
        clean.get("source_reopen_required", source_reopen_required)
    )
    clean["reopenable_ref_count"] = _reopenable_ref_count(clean)
    if cache_status:
        clean["cache_status"] = {
            key: value
            for key, value in {
                "status": cache_status.get("status"),
                "topic_epoch": cache_status.get("topic_epoch"),
                "matched_topic_epoch": cache_status.get("matched_topic_epoch"),
                "visibility_bias": cache_status.get("visibility_bias"),
            }.items()
            if value not in {None, ""}
        }
    return with_trust_fields(clean)


def cached_card_with_provenance(
    card: dict[str, Any],
    *,
    cache_status: dict[str, Any] | None = None,
) -> dict[str, Any]:
    prior = str(
        card.get("cached_origin")
        or (
            ""
            if card.get("provenance_class") == CACHED_WARM_CARD
            else card.get("provenance_class") or ""
        )
        or "unknown"
    )
    clean = dict(card)
    clean["provenance_class"] = CACHED_WARM_CARD
    return with_card_provenance(
        clean,
        CACHED_WARM_CARD,
        cached_origin=prior,
        cache_status=cache_status,
        source_reopen_required=True,
    )


def count_cards_by_field(cards: list[dict[str, Any]], field: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for card in cards:
        if not isinstance(card, dict):
            continue
        value = str(card.get(field) or "").strip()
        if not value:
            continue
        counts[value] = counts.get(value, 0) + 1
    return counts


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
    return with_authority_fields(
        with_card_provenance(
            {
                "card_id": _stable_id(
                    [EVIDENCE, theme, ref.get("thread_key"), ref.get("line"), key_line]
                ),
                "theme": theme,
                "resonance": "high",
                "support_level": EVIDENCE,
                "visibility": visibility,
                "suggested_use": (
                    "Use this bounded source-backed evidence when relevant; reopen clean source only for disputed exact wording or wider context."
                    if visibility == DEEP_ARCHIVAL_RECALL
                    else "Use this bounded source-backed evidence when it changes the current answer or needs grounding."
                ),
                "nudge": "",
                "key_line": key_line,
                "matched_terms": _clean_terms(item.get("matched_terms") or []),
                "source_refs": [ref] if ref else [],
                "expand_if": (
                    "Reopen clean source for disputed exact wording or missing wider context."
                    if visibility == DEEP_ARCHIVAL_RECALL
                    else "User asks for original wording, source details, or a disputed memory."
                ),
            },
            SOURCE_BACKED_REOPEN,
            source_reopen_required=False,
        )
    )


def _source_reopen_messages(payload: dict[str, Any]) -> list[dict[str, Any]]:
    window = payload.get("source_window") if isinstance(payload.get("source_window"), dict) else {}
    raw_messages = window.get("messages") if isinstance(window, dict) else None
    if raw_messages is None:
        raw_messages = payload.get("messages")
    if not isinstance(raw_messages, list):
        return []
    return [message for message in raw_messages if isinstance(message, dict)]


def _source_reopen_refs(payload: dict[str, Any]) -> list[dict[str, Any]]:
    raw_refs = payload.get("source_refs") or []
    if isinstance(raw_refs, dict):
        raw_refs = [raw_refs]
    if not isinstance(raw_refs, list):
        return []
    refs = [_clean_source_ref(ref) for ref in raw_refs if isinstance(ref, dict)]
    return [ref for ref in refs if ref][:MAX_CARDS]


def _message_as_evidence_item(message: dict[str, Any], *, fallback_ref: dict[str, Any]) -> dict[str, Any]:
    return {
        "thread_key": message.get("thread_key") or fallback_ref.get("thread_key"),
        "source_id": message.get("source_id") or fallback_ref.get("source_id"),
        "message_id": message.get("message_id") or message.get("id") or fallback_ref.get("message_id"),
        "turn_id": message.get("turn_id") or fallback_ref.get("turn_id"),
        "turn_index": message.get("turn_index") or fallback_ref.get("turn_index"),
        "line": message.get("line") or message.get("source_line") or fallback_ref.get("line"),
        "phase": message.get("phase") or fallback_ref.get("phase") or message.get("role") or "",
        "title": message.get("title")
        or fallback_ref.get("title")
        or message.get("phase")
        or message.get("role")
        or "clean-source reopen",
        "snippet": _safe_text(message.get("text") or message.get("snippet"), MAX_BOUNDED_EVIDENCE_CHARS),
    }


def _source_reopen_was_successful(payload: dict[str, Any]) -> bool:
    raw_boundary = payload.get("source_boundary")
    raw_metrics = payload.get("metrics")
    boundary: dict[str, Any] = raw_boundary if isinstance(raw_boundary, dict) else {}
    metrics: dict[str, Any] = raw_metrics if isinstance(raw_metrics, dict) else {}
    get_turn_context_shape = bool(payload.get("turn") and _source_reopen_messages(payload))
    return bool(
        not payload.get("error")
        and (
            get_turn_context_shape
            or payload.get("status") == "ok"
        )
        and (
            get_turn_context_shape
            or payload.get("support_level") == EVIDENCE
            or payload.get("evidence_level") == "source_backed"
            or boundary.get("clean_source_reopened")
            or metrics.get("source_reopen_success")
        )
    )


def bounded_evidence_context_from_source_reopen(
    payload: dict[str, Any],
    *,
    max_cards: int = MAX_CARDS,
) -> dict[str, Any]:
    """Project reopened clean source into a separate bounded evidence context.

    #707 keeps the scent packet ids-only: the packet may point at a route, but
    this context is the separate source-backed surface after a host has already
    reopened clean source. It deliberately serializes cards, not the raw
    `source_window`, so callers cannot accidentally paste an unbounded turn.
    """

    clean_payload = payload if isinstance(payload, dict) else {}
    source_refs = _source_reopen_refs(clean_payload)
    messages = _source_reopen_messages(clean_payload)
    source_reopen_success = _source_reopen_was_successful(clean_payload)
    cards: list[dict[str, Any]] = []
    if source_reopen_success:
        for index, message in enumerate(messages[: max(0, max_cards)]):
            fallback_ref = source_refs[min(index, len(source_refs) - 1)] if source_refs else {}
            item = _message_as_evidence_item(message, fallback_ref=fallback_ref)
            if not str(item.get("snippet") or "").strip():
                continue
            cards.append(_evidence_card(item))
            if len(cards) >= max(0, max_cards):
                break
    success = bool(source_reopen_success and cards)
    failure_reason_codes: list[str] = []
    if not source_reopen_success:
        failure_reason_codes.append("source_reopen_not_successful")
    if source_reopen_success and not messages:
        failure_reason_codes.append("source_window_missing")
    if source_reopen_success and messages and not cards:
        failure_reason_codes.append("bounded_evidence_empty")
    return {
        "kind": "aippocampus_bounded_evidence_context",
        "schema_version": CARD_SCHEMA_VERSION,
        "support_level": EVIDENCE if success else "none",
        "evidence_level": "source_backed" if success else "none",
        "source_reopen_success": success,
        "cards": cards,
        "card_count": len(cards),
        "source_refs": source_refs,
        "failure_reason_codes": failure_reason_codes,
        "source_boundary": {
            "separate_from_fresh_thread_packet": True,
            "fresh_thread_packet_remains_navigation_only": True,
            "clean_source_reopened": success,
            "cards_are_bounded_source_backed_context": True,
            "raw_prompt_text_serialized": False,
            "raw_source_window_serialized": False,
            "bounded_excerpt_chars": MAX_BOUNDED_EVIDENCE_CHARS,
        },
    }


def _candidate_card(item: dict[str, Any], *, support_level: str = SCENT) -> dict[str, Any]:
    theme = _theme_from_item(item, "related prior context")
    nudge_theme = safe_nudge_topic(theme)
    terms = _clean_terms(item.get("matched_terms") or item.get("keywords") or [])
    return with_card_provenance({
        "card_id": _stable_id([support_level, theme, item.get("thread_key"), ",".join(terms)]),
        "theme": theme,
        "resonance": "medium",
        "support_level": support_level,
        "visibility": ACTIVE_GENTLE_NUDGE,
        "suggested_use": "Treat this as resonance. Lightly continue from the theme only if it helps.",
        "nudge": f"This may touch the old thread around {nudge_theme}.",
        "key_line": str((item.get("anchors") or [""])[0] or ""),
        "matched_terms": terms,
        "source_refs": [],
        "expand_if": "User asks for memory, exact context, or source-backed support.",
    }, DETERMINISTIC_CUE)


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
        "route": item.get("route"),
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
    return with_card_provenance(
        card,
        WORKING_MEMORY_MODEL if is_dream else WORKING_MEMORY_SOURCE,
        source_reopen_required=True,
    )


def _cognitive_map_card(item: dict[str, Any]) -> dict[str, Any]:
    labels = _clean_terms(item.get("landmark_labels") or item.get("matched_cues") or [], limit=4)
    theme = compact_text(", ".join(labels) or str(item.get("title") or "cognitive map route"), 140)
    nudge_theme = safe_nudge_topic(theme)
    return with_card_provenance({
        "card_id": _stable_id([SCENT, theme, item.get("route_id")]),
        "theme": theme,
        "resonance": "medium",
        "support_level": SCENT,
        "visibility": ACTIVE_GENTLE_NUDGE,
        "suggested_use": "Use as wayfinding only; verify exact claims against clean source.",
        "nudge": f"This may follow the route around {nudge_theme}.",
        "key_line": "",
        "matched_terms": _clean_terms(item.get("matched_cues") or item.get("route_cues") or []),
        "source_refs": [],
        "expand_if": "Use clean-source search if this route would change the answer.",
    }, COGNITIVE_MAP_ROUTE)


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
    effective_cache_status = cache_status or ({"status": "hit"} if cached_cards else {"status": "not_used"})
    cards: list[dict[str, Any]] = []
    if cached_cards and cached_cards_first:
        cards.extend(
            cached_card_with_provenance(card, cache_status=effective_cache_status)
            for card in cached_cards
            if isinstance(card, dict)
        )
    if result.get("evidence"):
        cards.extend(_evidence_card(item, deep_archival=deep_archival) for item in result.get("evidence") or [])
    if result.get("working_memory"):
        cards.extend(_working_memory_card(item) for item in result.get("working_memory") or [])
    if not cards and result.get("cognitive_map"):
        cards.extend(_cognitive_map_card(item) for item in result.get("cognitive_map") or [])
    if not cards and result.get("candidates"):
        cards.extend(_candidate_card(item) for item in result.get("candidates") or [])
    if cached_cards and not cached_cards_first:
        cards.extend(
            cached_card_with_provenance(card, cache_status=effective_cache_status)
            for card in cached_cards
            if isinstance(card, dict)
        )

    cards = _dedupe_cards(cards, limit=max(0, max_cards))
    mode = _mode_for_cards(decision, cards)
    return {
        "kind": "aippocampus_ambient_recall",
        "schema_version": CARD_SCHEMA_VERSION,
        "mode": mode,
        "confidence": result.get("confidence") or ("medium" if cards else "low"),
        "cards": cards,
        "fresh_thread_packet": fresh_thread_scent_packet_from_decision(result),
        "avoid": list(DEFAULT_AVOID),
        "latency_ms": result.get("elapsed_ms"),
        "cache_status": effective_cache_status,
        "late_update_policy": "warm_scouts_deferred",
        "late_warm_handoff": {
            "default_path": "next_turn_thread_cache",
            "active_lock": "enrich_when_available",
            "explicit_continuation": "active_recall_pull",
            "current_turn_use": "not_allowed",
        },
    }
