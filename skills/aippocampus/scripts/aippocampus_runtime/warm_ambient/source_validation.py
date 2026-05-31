#!/usr/bin/env python3
"""Source-ref validation helpers for warm ambient recall.

Warm scouts can propose cards, but this module owns the source-backed boundary:
fallback cards must point to clean-source refs, and citation-shaped model output
is downgraded or dropped unless local clean source supports it.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from aippocampus_runtime.recall.ambient_cards import (
    ACTIVE_GENTLE_NUDGE,
    CANDIDATE,
    EVIDENCE,
    SOURCE_BACKED_RECALL_CARD,
)
from aippocampus_runtime.recall.query_policy import split_query_terms
from aippocampus_runtime.source.search import iter_clean_messages
from aippocampuslib import compact_text, sanitize_external_model_text

PROMPT_TRACE_BASE_STOPWORDS = {
    "a",
    "an",
    "and",
    "as",
    "for",
    "in",
    "of",
    "on",
    "or",
    "the",
    "to",
    "with",
}

PROMPT_TRACE_WEAK_TERMS = PROMPT_TRACE_BASE_STOPWORDS | {
    "about",
    "also",
    "are",
    "but",
    "can",
    "could",
    "did",
    "does",
    "each",
    "error",
    "exactly",
    "file",
    "get",
    "give",
    "have",
    "how",
    "into",
    "just",
    "left",
    "me",
    "model",
    "more",
    "my",
    "not",
    "our",
    "please",
    "provide",
    "should",
    "that",
    "the",
    "these",
    "they",
    "this",
    "trying",
    "use",
    "using",
    "was",
    "were",
    "what",
    "when",
    "where",
    "will",
    "would",
    "you",
    "your",
}

PROMPT_TRACE_CONTINUATION_RE = re.compile(
    r"("
    r"继续|上[一轮文次]|刚才|前面|上一版|同样|照样|再来|"
    r"continue|where\s+you\s+left\s+off|previous|above|earlier|as\s+before|"
    r"format\s+you\s+did\s+above|this\s+works|that\s+works|it\s+works|"
    r"can\s+you\s+also|also\s+add|not\s+just|instead|"
    r"will\s+it\s+work\s+also|add\s+support\s+for"
    r")",
    re.IGNORECASE,
)


def _unique_preserve(items: list[str], limit: int | None = None) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        value = re.sub(r"\s+", " ", str(item)).strip()
        if not value or value.casefold() in seen:
            continue
        seen.add(value.casefold())
        out.append(value)
        if limit is not None and len(out) >= limit:
            break
    return out


def _stable_id(parts: list[Any]) -> str:
    raw = "\n".join(str(part or "") for part in parts)
    return "warc_" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:18]


def _is_distinctive_trace_term(term: str) -> bool:
    value = str(term or "").strip().casefold()
    return (
        len(value) >= 8
        or any(char.isdigit() for char in value)
        or any(char in value for char in ("-", "_", ".", "/", "\\"))
    )


def _safe_text(value: Any, chars: int) -> str:
    sanitized, _ = sanitize_external_model_text(str(value or ""))
    return compact_text(sanitized, chars)


def _clean_source_ref(ref: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(ref, dict):
        return {}
    line = ref.get("line", ref.get("source_line"))
    clean = {
        "thread_key": _safe_text(ref.get("thread_key"), 160),
        "title": _safe_text(ref.get("title"), 180),
        "line": line,
        "phase": _safe_text(ref.get("phase"), 80),
        "turn_index": ref.get("turn_index"),
        "message_id": _safe_text(ref.get("message_id"), 160),
    }
    return {key: value for key, value in clean.items() if value not in {None, ""}}


def source_index_from_registry(
    registry: dict[str, Any] | None, *, thread_keys: set[str] | None = None
) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for entry in (registry or {}).get("threads") or []:
        if not isinstance(entry, dict):
            continue
        thread_key = str(entry.get("thread_key") or "")
        if thread_keys is not None and thread_key not in thread_keys:
            continue
        raw_paths = entry.get("paths")
        paths = raw_paths if isinstance(raw_paths, dict) else {}
        messages_path_value = paths.get("clean_source_messages_jsonl")
        if not thread_key or not messages_path_value:
            continue
        messages = iter_clean_messages(Path(str(messages_path_value)))
        by_id: dict[str, dict[str, Any]] = {}
        by_line: dict[str, dict[str, Any]] = {}
        for message in messages:
            message_id = str(message.get("message_id") or message.get("id") or "")
            if message_id:
                by_id[message_id] = message
            for key in ("source_line", "line", "clean_ordinal"):
                value = message.get(key)
                if value is not None:
                    by_line[str(value)] = message
        index[thread_key] = {"by_id": by_id, "by_line": by_line}
    return index


def referenced_thread_keys(rows: list[dict[str, Any]]) -> set[str]:
    keys: set[str] = set()
    for row in rows:
        for card in row.get("candidates") or []:
            for ref in card.get("source_refs") or []:
                if isinstance(ref, dict) and ref.get("thread_key"):
                    keys.add(str(ref.get("thread_key")))
    return keys


def referenced_thread_keys_from_cards(cards: list[dict[str, Any]]) -> set[str]:
    keys: set[str] = set()
    for card in cards:
        for ref in card.get("source_refs") or []:
            if isinstance(ref, dict) and ref.get("thread_key"):
                keys.add(str(ref.get("thread_key")))
    return keys


def prompt_trace_fallback_cards(
    prompt: str,
    prompt_trace: list[dict[str, Any]] | None,
    *,
    limit: int = 1,
) -> list[dict[str, Any]]:
    strong_continuation = bool(PROMPT_TRACE_CONTINUATION_RE.search(str(prompt or "")))
    prompt_terms = [
        term
        for term in split_query_terms([prompt])
        if len(str(term or "").strip()) >= 3
        and term.casefold() not in PROMPT_TRACE_WEAK_TERMS
    ]
    prompt_term_set = {term.casefold() for term in prompt_terms}
    prompt_text = compact_text(str(prompt or ""), 420).casefold()
    cards: list[dict[str, Any]] = []
    for item in reversed(prompt_trace or []):
        if not isinstance(item, dict):
            continue
        text = compact_text(str(item.get("text") or item.get("prompt") or ""), 420)
        if not text or text.casefold() == prompt_text:
            continue
        if str(item.get("phase") or "").strip().casefold() == "current_prompt":
            continue
        refs = [
            clean
            for clean in (_clean_source_ref(ref) for ref in item.get("source_refs") or [])
            if clean
        ][:3]
        if not refs:
            continue
        text_source_terms = [
            term
            for term in split_query_terms([text])
            if len(str(term or "").strip()) >= 3
            and term.casefold() not in PROMPT_TRACE_WEAK_TERMS
        ]
        text_terms = {term.casefold() for term in text_source_terms}
        shared = _unique_preserve(
            [
                term
                for term in prompt_terms
                if term.casefold() in text_terms or term.casefold() in text.casefold()
            ],
            limit=6,
        )
        shared_prompt_terms = {term.casefold() for term in shared} & prompt_term_set
        if len(shared_prompt_terms) < 2 and not any(
            _is_distinctive_trace_term(term) for term in shared_prompt_terms
        ):
            if not strong_continuation:
                continue
            shared = _unique_preserve(text_source_terms, limit=6)
        if not shared:
            continue
        key_line = compact_text(text, 180)
        cards.append(
            {
                "card_id": _stable_id(
                    ["prompt_trace_fallback", key_line, json.dumps(refs, sort_keys=True)]
                ),
                "theme": compact_text("prior trace: " + ", ".join(shared[:4]), 100),
                "resonance": "medium",
                "support_level": EVIDENCE,
                "visibility": SOURCE_BACKED_RECALL_CARD,
                "suggested_use": "Use as source-backed prior context when it helps the current turn.",
                "nudge": "Prior prompt trace contains source-backed context related to this request.",
                "key_line": key_line,
                "matched_terms": shared,
                "source_refs": refs,
                "expand_if": "Open clean source before presenting exact prior wording.",
            }
        )
        if len(cards) >= limit:
            break
    return cards


def _message_for_ref(
    source_index: dict[str, dict[str, Any]], ref: dict[str, Any]
) -> dict[str, Any] | None:
    thread_key = str(ref.get("thread_key") or "")
    thread_index = source_index.get(thread_key) or {}
    message_id = str(ref.get("message_id") or ref.get("id") or "")
    if message_id and message_id in (thread_index.get("by_id") or {}):
        return thread_index["by_id"][message_id]
    line = ref.get("line", ref.get("source_line"))
    if line is not None and str(line) in (thread_index.get("by_line") or {}):
        return thread_index["by_line"][str(line)]
    return None


def _message_supports_card(message: dict[str, Any], card: dict[str, Any]) -> bool:
    text = str(message.get("text") or "").casefold()
    key_line = str(card.get("key_line") or "").strip().casefold()
    if key_line and len(key_line) >= 12 and key_line in text:
        return True
    if key_line and "..." in key_line:
        fragments = [
            fragment.strip()
            for fragment in re.split(r"\s*\.\.\.\s*", key_line)
            if len(fragment.strip()) >= 24
        ]
        if any(fragment in text for fragment in fragments):
            return True
    matched = []
    for term in card.get("matched_terms") or []:
        needle = str(term or "").strip().casefold()
        if len(needle) >= 3 and needle not in PROMPT_TRACE_WEAK_TERMS and needle in text:
            matched.append(needle)
    distinct = set(matched)
    return len(distinct) >= 2 or any(
        _is_distinctive_trace_term(item) or " " in item for item in distinct
    )


def validate_card_source_refs(
    card: dict[str, Any], source_index: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    refs = [ref for ref in card.get("source_refs") or [] if isinstance(ref, dict)]
    if not refs:
        return {"status": "missing_source_refs", "checked_ref_count": 0, "supported_ref_count": 0}
    if not source_index:
        return {
            "status": "unverified_no_source_index",
            "checked_ref_count": 0,
            "supported_ref_count": 0,
        }
    checked = 0
    supported = 0
    missing = 0
    for ref in refs:
        message = _message_for_ref(source_index, ref)
        if not message:
            missing += 1
            continue
        checked += 1
        if _message_supports_card(message, card):
            supported += 1
    if supported:
        return {
            "status": "supported",
            "checked_ref_count": checked,
            "supported_ref_count": supported,
        }
    return {
        "status": "unsupported" if checked else "missing_source_ref",
        "checked_ref_count": checked,
        "supported_ref_count": 0,
        "missing_ref_count": missing,
    }


def calibrate_cards(
    cards: list[dict[str, Any]],
    *,
    source_index: dict[str, dict[str, Any]] | None = None,
    current_thread_key: str | None = None,
    allow_current_thread_echo: bool = False,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    calibrated: list[dict[str, Any]] = []
    echo_count = 0
    for card in cards:
        refs = [ref for ref in card.get("source_refs") or [] if isinstance(ref, dict)]
        if (
            current_thread_key
            and refs
            and all(str(ref.get("thread_key") or "") == current_thread_key for ref in refs)
        ):
            echo_count += 1
            if not allow_current_thread_echo:
                continue
        clean = dict(card)
        validation = validate_card_source_refs(clean, source_index or {})
        if validation.get("status") in {"missing_source_ref", "unsupported"}:
            # Citation-shaped hallucinations are worse than source-less scents:
            # drop them so lower-ranked supported cards can still surface.
            continue
        clean["source_validation"] = validation
        if clean.get("support_level") == EVIDENCE and validation.get("status") != "supported":
            clean["support_level"] = CANDIDATE
            clean["visibility"] = ACTIVE_GENTLE_NUDGE
            clean["suggested_use"] = "Treat as provisional resonance until clean source support is verified."
        calibrated.append(clean)
    return calibrated, {"current_thread_echo_count": echo_count}
