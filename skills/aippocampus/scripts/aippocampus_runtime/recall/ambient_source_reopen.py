#!/usr/bin/env python3
"""Bounded clean-source reopen for foreground ambient recall cards."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from aippocampus_runtime.recall.ambient_cards import (
    bounded_evidence_context_from_source_reopen,
)
from aippocampus_runtime.registry.api import load_registry
from aippocampus_runtime.source.search import iter_clean_messages

MAX_AUTOMATIC_SOURCE_REOPEN_CARDS = 2
SOURCE_BACKED_VISIBILITIES = {"source_backed_recall_card", "deep_archival_recall"}


def _message_matches_ref(message: dict[str, Any], ref: dict[str, Any]) -> bool:
    message_id = str(message.get("message_id") or message.get("id") or "")
    if ref.get("message_id") and str(ref.get("message_id")) == message_id:
        return True
    turn_id = str(message.get("turn_id") or "")
    if ref.get("turn_id") and str(ref.get("turn_id")) == turn_id:
        return True
    turn_index = str(message.get("turn_index") or "")
    if ref.get("turn_index") is not None and str(ref.get("turn_index")) == turn_index:
        return True
    ref_line = ref.get("line", ref.get("source_line"))
    message_line = message.get("source_line", message.get("line"))
    return bool(ref_line is not None and str(ref_line) == str(message_line))


def _reopen_reason_for_card(card: dict[str, Any]) -> str:
    if not [ref for ref in card.get("source_refs") or [] if isinstance(ref, dict)]:
        return ""
    if card.get("candidate_type") == "dream_hypothesis":
        return ""
    provenance = str(card.get("provenance_class") or "").strip()
    if provenance == "working_memory_model":
        return ""
    if provenance == "working_memory_source":
        return "working_memory_use_with_source" if card.get("route") == "use_with_source" else ""
    cached_origin = str(card.get("cached_origin") or "").strip()
    support = str(card.get("support_level") or "").strip()
    visibility = str(card.get("visibility") or "").strip()
    raw_validation = card.get("source_validation")
    validation: dict[str, Any] = raw_validation if isinstance(raw_validation, dict) else {}
    if provenance == "cached_warm_card" and (
        cached_origin == "source_backed_reopen"
        or support == "evidence"
        or visibility in SOURCE_BACKED_VISIBILITIES
        or validation.get("status") == "supported"
    ):
        return "cached_source_backed_card"
    if provenance == "source_backed_reopen" and support == "evidence":
        return "source_backed_card"
    return ""


def _registry_threads_by_key(registry_path: Path) -> dict[str, dict[str, Any]]:
    registry = load_registry(registry_path)
    return {
        str(entry.get("thread_key") or ""): entry
        for entry in registry.get("threads") or []
        if isinstance(entry, dict) and entry.get("thread_key")
    }


def _source_ref_for_message(
    ref: dict[str, Any],
    *,
    message: dict[str, Any],
    entry: dict[str, Any],
) -> dict[str, Any]:
    clean = {
        "thread_key": ref.get("thread_key"),
        "source_id": ref.get("source_id"),
        "title": ref.get("title") or entry.get("title"),
        "line": ref.get("line", message.get("source_line", message.get("line"))),
        "phase": ref.get("phase") or message.get("phase") or message.get("role"),
        "turn_id": ref.get("turn_id") or message.get("turn_id"),
        "turn_index": ref.get("turn_index", message.get("turn_index")),
        "message_id": ref.get("message_id") or message.get("message_id") or message.get("id"),
    }
    return {key: value for key, value in clean.items() if value not in {None, ""}}


def _reopen_card_source_payload(
    card: dict[str, Any],
    *,
    threads_by_key: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    for ref in [item for item in card.get("source_refs") or [] if isinstance(item, dict)]:
        thread_key = str(ref.get("thread_key") or "")
        entry = threads_by_key.get(thread_key)
        if not entry:
            errors.append({"code": "thread_not_in_registry", "thread_key": thread_key})
            continue
        raw_paths = entry.get("paths")
        paths: dict[str, Any] = raw_paths if isinstance(raw_paths, dict) else {}
        messages_path_value = paths.get("clean_source_messages_jsonl")
        if not messages_path_value:
            errors.append({"code": "clean_source_missing", "thread_key": thread_key})
            continue
        messages = iter_clean_messages(Path(str(messages_path_value)))
        selected = next((message for message in messages if _message_matches_ref(message, ref)), None)
        if not selected:
            errors.append({"code": "source_ref_not_found", "thread_key": thread_key})
            continue
        source_ref = _source_ref_for_message(ref, message=selected, entry=entry)
        message = {
            **selected,
            "thread_key": thread_key,
            "title": ref.get("title") or entry.get("title") or selected.get("title"),
        }
        return {
            "kind": "aippocampus_recall_deepen",
            "status": "ok",
            "support_level": "evidence",
            "evidence_level": "source_backed",
            "source_refs": [source_ref],
            "source_window": {"messages": [message], "message_count": 1},
            "source_boundary": {
                "clean_source_reopened": True,
                "card_material_was_navigation_only": True,
            },
            "metrics": {"source_reopen_success": True},
        }
    return {
        "kind": "aippocampus_recall_deepen",
        "status": "error",
        "error": True,
        "errors": errors,
        "source_boundary": {"clean_source_reopened": False},
    }


def _card_dedupe_key(card: dict[str, Any]) -> str:
    refs = card.get("source_refs") or []
    if refs:
        return "refs:" + json.dumps(refs, ensure_ascii=False, sort_keys=True)
    return "card:" + str(card.get("card_id") or card.get("theme") or "")


def _prepend_promoted_cards(
    cards: list[dict[str, Any]],
    promoted: list[dict[str, Any]],
    *,
    limit: int,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for card in [*promoted, *cards]:
        key = _card_dedupe_key(card)
        if key in seen:
            continue
        seen.add(key)
        out.append(card)
        if len(out) >= limit:
            break
    return out


def promote_reopenable_ambient_cards(
    ambient: dict[str, Any],
    *,
    registry_path: Path,
    max_cards: int = MAX_AUTOMATIC_SOURCE_REOPEN_CARDS,
) -> None:
    """Promote eligible ambient cards only after deterministic clean-source reopen.

    The original ambient cards remain navigation hints. Promotion is allowed
    only for route/use_with_source working memory and cached cards that already
    came from a source-backed card. Dream hypotheses and unresolved refs stay
    candidate-level so foreground use cannot confuse a model-organized hint for
    source evidence.
    """

    cards = [card for card in ambient.get("cards") or [] if isinstance(card, dict)]
    eligible = [(card, reason) for card in cards if (reason := _reopen_reason_for_card(card))]
    if not eligible:
        return
    diagnostics: dict[str, Any] = {
        "attempted_count": 0,
        "success_count": 0,
        "failure_count": 0,
        "failure_reason_counts": {},
        "raw_source_window_serialized": False,
        "max_cards": max_cards,
    }
    promoted: list[dict[str, Any]] = []
    try:
        threads_by_key = _registry_threads_by_key(registry_path)
    except Exception as exc:
        diagnostics["attempted_count"] = min(len(eligible), max_cards)
        diagnostics["failure_count"] = diagnostics["attempted_count"]
        diagnostics["failure_reason_counts"] = {"registry_load_failed": diagnostics["failure_count"]}
        diagnostics["error_type"] = type(exc).__name__
        ambient["source_reopen"] = diagnostics
        return

    for card, reason in eligible[: max(0, max_cards)]:
        diagnostics["attempted_count"] += 1
        payload = _reopen_card_source_payload(card, threads_by_key=threads_by_key)
        evidence_context = bounded_evidence_context_from_source_reopen(payload, max_cards=1)
        if evidence_context.get("source_reopen_success"):
            diagnostics["success_count"] += 1
            for evidence_card in evidence_context.get("cards") or []:
                if not isinstance(evidence_card, dict):
                    continue
                evidence_card["source_reopen_origin"] = reason
                evidence_card["source_reopen_card_id"] = card.get("card_id")
                promoted.append(evidence_card)
            continue
        diagnostics["failure_count"] += 1
        reason_codes = evidence_context.get("failure_reason_codes") or ["source_reopen_failed"]
        counts = diagnostics["failure_reason_counts"]
        for code in reason_codes:
            key = str(code or "source_reopen_failed")
            counts[key] = counts.get(key, 0) + 1

    if diagnostics["attempted_count"]:
        ambient["source_reopen"] = diagnostics
    if promoted:
        ambient["cards"] = _prepend_promoted_cards(cards, promoted, limit=max(1, len(cards)))
        ambient["mode"] = "source_backed_recall_card"
