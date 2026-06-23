#!/usr/bin/env python3
"""Compact private ambient recall cards.

These cards are advice to the foreground agent, not user-facing text and not
formal memory. The source boundary is explicit: scent/candidate cards can guide
phrasing, while only evidence cards carry source-backed snippets.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

from aippocampus_runtime.core import compact_text, sanitize_external_model_text
from aippocampus_runtime.recall.ambient_card_hygiene import demote_no_ref_active_cards
from aippocampus_runtime.recall.ambient_policy import policy_payload_for_working_memory
from aippocampus_runtime.recall.authority import with_authority_fields, with_trust_fields
from aippocampus_runtime.recall.continuity_domains import CONTINUITY_DOMAIN_POINTER_KIND
from aippocampus_runtime.recall.fresh_thread_scent import fresh_thread_scent_packet_from_decision
from aippocampus_runtime.recall.nudge_policy import safe_nudge_topic
from aippocampus_runtime.recall.query_profile import classify_query_profile

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
COGNITIVE_MAP_REGISTRY_OVERVIEW = "cognitive_map_registry_overview"
WORKING_MEMORY_SOURCE = "working_memory_source"
WORKING_MEMORY_MODEL = "working_memory_model"
CONTINUITY_DOMAIN_POINTER = CONTINUITY_DOMAIN_POINTER_KIND

DEFAULT_AVOID = [
    "Do not claim innate memory.",
    "Do not present scent or candidate cards as source-backed fact.",
    "Do not expose source ids unless the user asks or grounding is needed.",
]

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


def _source_ref_from_item(item: dict[str, Any]) -> dict[str, Any]:
    if not any(
        item.get(key) not in (None, "")
        for key in ("thread_key", "source_id", "message_id", "turn_id", "turn_index", "line")
    ):
        return {}
    return _clean_source_ref(
        item,
        fallback_thread=str(item.get("thread_key") or ""),
        fallback_title=str(item.get("title") or ""),
    )


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


def _rank_cards_for_brief(
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
        decorated.append(
            (
                rank_key,
                -index,
                card,
            )
        )
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
    ref = _source_ref_from_item(item)
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
        "source_refs": [ref] if ref else [],
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
    provenance = str(item.get("provenance_class") or COGNITIVE_MAP_ROUTE)
    is_overview = provenance == COGNITIVE_MAP_REGISTRY_OVERVIEW
    label_source = item.get("region_labels") if is_overview else item.get("landmark_labels")
    labels = _clean_terms(label_source or item.get("matched_cues") or [], limit=4)
    fallback = "registry overview" if is_overview else "cognitive map route"
    theme = compact_text(", ".join(labels) or str(item.get("title") or fallback), 140)
    nudge_theme = safe_nudge_topic(theme)
    suggested_use = (
        "Use as registry-derived far-view context only; reopen clean source before claims."
        if is_overview
        else "Use as wayfinding only; verify exact claims against clean source."
    )
    source_boundary = dict(item.get("source_boundary") or {})
    if is_overview:
        source_boundary.setdefault("registry_derived_navigation_only", True)
        source_boundary.setdefault("not_source_backed_route", True)
        source_boundary.setdefault("source_reopen_required_for_claims", True)
    return with_card_provenance({
        "card_id": _stable_id([SCENT, theme, item.get("route_id")]),
        "theme": theme,
        "resonance": "medium",
        "support_level": SCENT,
        "visibility": ACTIVE_GENTLE_NUDGE,
        "suggested_use": suggested_use,
        "nudge": f"This may follow the route around {nudge_theme}.",
        "key_line": "",
        "matched_terms": _clean_terms(item.get("matched_cues") or item.get("route_cues") or []),
        "source_refs": [],
        "source_boundary": source_boundary,
        "expand_if": "Use clean-source search if this route would change the answer.",
    }, provenance)


def _continuity_domain_pointer_card(item: dict[str, Any]) -> dict[str, Any]:
    domain_id = str(item.get("domain_id") or "")
    theme = compact_text(str(item.get("label") or item.get("theme") or domain_id), 140)
    nudge_theme = safe_nudge_topic(theme)
    source_boundary = dict(item.get("source_boundary") or {})
    source_boundary.setdefault("pointer_only_not_fact", True)
    source_boundary.setdefault("domain_summary_not_source", True)
    source_boundary.setdefault("source_reopen_required_for_facts", True)
    return with_card_provenance(
        {
            "card_id": _stable_id([CONTINUITY_DOMAIN_POINTER, domain_id, theme]),
            "card_kind": CONTINUITY_DOMAIN_POINTER,
            "domain_id": domain_id,
            "theme": theme,
            "resonance": "medium",
            "support_level": item.get("support_level") or "source_required",
            "visibility": ACTIVE_GENTLE_NUDGE,
            "suggested_use": _safe_text(
                item.get("suggested_use")
                or "Use as continuity pointer; reopen source before factual claims.",
                180,
            ),
            "nudge": f"This may connect to the continuity domain around {nudge_theme}.",
            "key_line": "",
            "matched_terms": _clean_terms(item.get("matched_terms") or item.get("activation_cues") or []),
            "source_refs": [
                ref
                for ref in item.get("source_refs") or item.get("representative_sources") or []
                if isinstance(ref, dict)
            ][:6],
            "reopen_plan": item.get("reopen_plan") or {},
            "pinned_boundary_conditions": item.get("pinned_boundary_conditions") or [],
            "source_boundary": source_boundary,
            "expand_if": "Run recall_deepen on the domain handle, then reopen clean source for claims.",
        },
        CONTINUITY_DOMAIN_POINTER,
    )


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
    prompt: str = "",
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
    if result.get("continuity_domains"):
        cards.extend(
            _continuity_domain_pointer_card(item)
            for item in result.get("continuity_domains") or []
            if isinstance(item, dict)
        )
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

    cards, no_ref_diagnostics = demote_no_ref_active_cards(cards, prompt=prompt)
    cards, brief_precision = _rank_cards_for_brief(cards, prompt=prompt)
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
        "brief_precision": {**brief_precision, **no_ref_diagnostics},
        "late_update_policy": "warm_scouts_deferred",
        "late_warm_handoff": {
            "default_path": "next_turn_thread_cache",
            "active_lock": "enrich_when_available",
            "explicit_continuation": "active_recall_pull",
            "current_turn_use": "not_allowed",
        },
    }
