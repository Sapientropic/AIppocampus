#!/usr/bin/env python3
"""Explicit producer for source-trailed continuity-domain events.

This module is the bridge from registered real history to continuity-domain
events. It is deliberately deterministic and operator-invoked: prompt hooks
consume published domain snapshots, but they must not scan private history or
author durable domain events while the user is typing.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from aippocampus_runtime.core import compact_text, now_utc
from aippocampus_runtime.ops.route_readiness import safe_source_refs
from aippocampus_runtime.privacy import (
    LOCAL_PATH_REDACTION,
    SENSITIVE_VALUE_REDACTION,
    redact_private_paths,
    redact_sensitive_values,
)
from aippocampus_runtime.recall.continuity_domains import (
    CONTINUITY_DOMAIN_SCHEMA_VERSION,
    normalize_continuity_domain_event,
)
from aippocampus_runtime.recall.query_policy import (
    GENERIC_ANCHOR_TERMS,
    STOP_TERMS,
    split_query_terms,
    unique_preserve,
)
from aippocampus_runtime.registry.api import load_registry, registry_paths
from aippocampus_runtime.source.search import iter_clean_messages
from aippocampus_runtime.warm_ambient.query_pattern_routes import (
    publish_registry_query_pattern_routes,
)

CONTINUITY_DOMAIN_PRODUCER_KIND = "aippocampus_continuity_domain_producer_report"
SIGNAL_CANDIDATE_FILES = (
    "query_pattern_routes.jsonl",
    "semantic_cues.jsonl",
    "semantic_triggers.jsonl",
    "working_memory.jsonl",
    "promotion_candidates.jsonl",
    "subconscious_jobs.jsonl",
    "dream_findings.jsonl",
    "journeys.jsonl",
    "journey_tracking.jsonl",
)
SIGNAL_TEXT_KEYS = (
    "title",
    "label",
    "theme",
    "candidate_key",
    "route_label",
    "finding_kind",
    "signal_kind",
)
SIGNAL_LIST_KEYS = (
    "query_aliases",
    "aliases",
    "activation_cues",
    "matched_terms",
    "scope_labels",
    "signal_labels",
    "keywords",
    "terms",
)

PATHISH_RE = re.compile(r"([A-Za-z]:[\\/]|\\\\|/Users/|/home/|/tmp/|://)")
SECRETISH_RE = re.compile(
    r"(?i)\b(api[_ -]?key|token|access[_ -]?token|auth[_ -]?token|"
    r"refresh[_ -]?token|client[_ -]?secret|secret|password|passwd|bearer)\b|"
    r"\b(sk-[A-Za-z0-9][A-Za-z0-9._-]{8,}|ghp_[A-Za-z0-9_]{8,}|AKIA[A-Z0-9]{8,})\b"
)
REDACTION_MARKERS = (LOCAL_PATH_REDACTION, SENSITIVE_VALUE_REDACTION, "<redacted:")
GENERIC_PRODUCER_TERMS = {
    *STOP_TERMS,
    *GENERIC_ANCHOR_TERMS,
    "agent",
    "agents",
    "assistant",
    "source",
    "trail",
    "source trail",
    "clean source",
    "message",
    "thread",
    "project",
    "现在",
    "应该",
    "可以",
    "回来",
    "源头",
}
LOW_INFORMATION_PRODUCER_TERMS = {
    "it",
    "its",
    "one",
    "ones",
    "you",
    "your",
    "yours",
    "answer",
    "answers",
    "question",
    "questions",
    "trigger",
    "triggers",
    "opening",
    "thing",
    "things",
    "change",
    "changes",
    "update",
    "updates",
    "这个",
    "那个",
    "这些",
    "那些",
    "这里",
    "那里",
    "这边",
    "那边",
    "怎么",
    "怎样",
    "如何",
    "什么",
    "为啥",
    "为什么",
    "哪个",
    "一下",
    "一个",
    "一些",
}
ENGLISH_LOW_INFORMATION_CORE_TERMS = {
    "it",
    "its",
    "one",
    "ones",
    "you",
    "your",
    "yours",
    "answer",
    "answers",
    "question",
    "questions",
    "thing",
    "things",
    "change",
    "changes",
    "update",
    "updates",
}
ENGLISH_LOW_INFORMATION_FILLER_TERMS = {
    *ENGLISH_LOW_INFORMATION_CORE_TERMS,
    "a",
    "an",
    "the",
    "this",
    "that",
    "these",
    "those",
    "my",
    "our",
    "their",
    "should",
    "would",
    "could",
    "can",
    "need",
    "needs",
    "needed",
    "to",
    "be",
    "is",
    "are",
    "was",
    "were",
    "do",
    "does",
    "did",
    "please",
}
CJK_DEICTIC_ACTION_RE = re.compile(
    r"(这个|那个|这些|那些|这里|那里|这边|那边).{0,32}"
    r"(要怎么|怎么|怎样|如何|改|修改|调整|处理|做|办|弄)"
)
CJK_ACTION_PROMPT_RE = re.compile(r"(要怎么|怎么改|怎么办|怎么做|如何改|改一下|弄一下)")


def _hash(value: Any, *, prefix: str) -> str:
    digest = hashlib.sha256(
        str(value or "").encode("utf-8", errors="replace"),
    ).hexdigest()[:20]
    return f"{prefix}_{digest}"


def _has_cjk(value: str) -> bool:
    return bool(re.search(r"[\u3400-\u9fff]", value))


def _privacy_suppressed_term(term: str) -> bool:
    if PATHISH_RE.search(term) or SECRETISH_RE.search(term):
        return True
    projected = redact_sensitive_values(redact_private_paths({"label": term})).get("label")
    return any(marker in str(projected) for marker in REDACTION_MARKERS)


def _low_information_producer_term(text: str) -> bool:
    low = text.casefold()
    if low in LOW_INFORMATION_PRODUCER_TERMS:
        return True
    latin_tokens = re.findall(r"[A-Za-z][A-Za-z'-]*", low)
    if latin_tokens and len(latin_tokens) <= 5:
        token_set = set(latin_tokens)
        if token_set & ENGLISH_LOW_INFORMATION_CORE_TERMS and token_set <= ENGLISH_LOW_INFORMATION_FILLER_TERMS:
            return True
    # A deictic action prompt such as "这个要怎么改一下" is a useful recall
    # activator, but it is not a durable label or activation cue. Reject it
    # even when split_query_terms keeps a nearby project alias in the same
    # phrase, otherwise a generic follow-up can project an unrelated route.
    if _has_cjk(text) and CJK_DEICTIC_ACTION_RE.search(text):
        return True
    if _has_cjk(text) and len(text) <= 32 and CJK_ACTION_PROMPT_RE.search(text):
        return True
    if _has_cjk(text) and len(text) <= 12:
        if CJK_DEICTIC_ACTION_RE.search(text):
            return True
        if CJK_ACTION_PROMPT_RE.search(text):
            return True
    return False


def _clean_candidate_term_detail(term: str) -> tuple[str, str]:
    text = re.sub(r"\s+", " ", str(term or "")).strip(" \t\r\n\"'`.,;:!?，。；：！？、")
    if not text:
        return "", ""
    if _privacy_suppressed_term(text):
        return "", "privacy"
    low = text.casefold()
    if low in GENERIC_PRODUCER_TERMS:
        return "", "low_information"
    if _low_information_producer_term(text):
        return "", "low_information"
    if len(text) > 48:
        return "", "shape"
    if _has_cjk(text):
        if len(text) < 2:
            return "", "shape"
    elif len(text) < 3:
        return "", "shape"
    if len(text.split()) > 4:
        return "", "shape"
    return text, ""


def _clean_candidate_term(term: str) -> tuple[str, bool]:
    text, reason = _clean_candidate_term_detail(term)
    return text, reason == "privacy"


def _entry_clean_source_dir(entry: Mapping[str, Any]) -> Path | None:
    paths = entry.get("paths") if isinstance(entry.get("paths"), Mapping) else {}
    clean_dir = paths.get("clean_source_dir") if isinstance(paths, Mapping) else None
    if clean_dir:
        path = Path(str(clean_dir))
        return path if (path / "messages.jsonl").exists() else None
    messages_jsonl = paths.get("clean_source_messages_jsonl") if isinstance(paths, Mapping) else None
    if messages_jsonl:
        path = Path(str(messages_jsonl)).parent
        return path if (path / "messages.jsonl").exists() else None
    return None


def _message_source_ref(thread_key: str, message: Mapping[str, Any]) -> dict[str, Any] | None:
    if not thread_key or _privacy_suppressed_term(thread_key):
        return None
    ref = {
        "thread_key": thread_key,
        "source_id": message.get("source_id"),
        "message_id": message.get("message_id") or message.get("id"),
        "turn_id": message.get("turn_id"),
        "turn_index": message.get("turn_index"),
        "line": message.get("source_line") or message.get("line"),
        "phase": message.get("phase"),
    }
    refs = safe_source_refs(ref)
    return refs[0] if refs else None


def _remember_ref(
    known_refs: dict[str, dict[str, set[str]]],
    *,
    thread_key: str,
    message: Mapping[str, Any],
) -> None:
    bucket = known_refs[thread_key]
    for key, value in {
        "message_id": message.get("message_id") or message.get("id"),
        "turn_id": message.get("turn_id"),
        "turn_index": message.get("turn_index"),
        "line": message.get("source_line") or message.get("line"),
    }.items():
        if value not in {None, ""}:
            bucket[key].add(str(value))


def _ref_resolves(
    ref: Mapping[str, Any],
    *,
    known_refs: Mapping[str, Mapping[str, set[str]]],
) -> bool:
    thread_key = str(ref.get("thread_key") or "")
    if not thread_key:
        return False
    bucket = known_refs.get(thread_key)
    if not bucket:
        return False
    for key in ("message_id", "turn_id", "turn_index", "line"):
        value = ref.get(key)
        if value not in {None, ""} and str(value) in bucket.get(key, set()):
            return True
    return False


def _resolving_signal_refs(
    value: Any,
    *,
    known_refs: Mapping[str, Mapping[str, set[str]]],
) -> list[dict[str, Any]]:
    refs = safe_source_refs(value)
    return [ref for ref in refs if _ref_resolves(ref, known_refs=known_refs)]


def _registry_terms(entry: Mapping[str, Any]) -> list[str]:
    values: list[str] = []
    for key in ("title", "summary", "workspace_name", "project_label"):
        if entry.get(key):
            values.append(str(entry.get(key)))
    for key in ("keywords", "anchor_titles", "project_tags"):
        raw = entry.get(key)
        if isinstance(raw, list):
            values.extend(str(item) for item in raw if item)
    terms: list[str] = []
    for value in values:
        terms.extend(split_query_terms([value]))
    return unique_preserve([term for term in terms if _clean_candidate_term(term)[0]], limit=64)


def _iter_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict):
                rows.append(item)
    return rows


def _signal_term_values(row: Mapping[str, Any]) -> tuple[list[str], int, int]:
    values: list[str] = []
    for key in SIGNAL_TEXT_KEYS:
        if row.get(key):
            values.append(str(row.get(key)))
    for key in SIGNAL_LIST_KEYS:
        raw = row.get(key)
        if isinstance(raw, list):
            values.extend(str(item) for item in raw if item)
    terms: list[str] = []
    privacy_suppressed = 0
    low_information_suppressed = 0
    for value in values:
        for raw in split_query_terms([value]):
            term, reason = _clean_candidate_term_detail(raw)
            if reason == "privacy":
                privacy_suppressed += 1
            elif reason == "low_information":
                low_information_suppressed += 1
            if term:
                terms.append(term)
    return unique_preserve(terms, limit=16), privacy_suppressed, low_information_suppressed


def _refs_by_thread(refs: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    by_thread: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for ref in refs:
        thread_key = str(ref.get("thread_key") or "")
        if thread_key:
            by_thread[thread_key].append(ref)
    return by_thread


def _terms_for_message(text: str, registry_terms: list[str]) -> tuple[list[str], int, int]:
    terms: list[str] = []
    privacy_suppressed = 0
    low_information_suppressed = 0
    low_text = text.casefold()
    for raw in [*split_query_terms([text]), *registry_terms]:
        if raw.casefold() not in low_text and raw not in registry_terms:
            continue
        term, reason = _clean_candidate_term_detail(raw)
        if reason == "privacy":
            privacy_suppressed += 1
        elif reason == "low_information":
            low_information_suppressed += 1
        if term:
            terms.append(term)
    return unique_preserve(terms, limit=32), privacy_suppressed, low_information_suppressed


def _candidate_score(
    *,
    term: str,
    refs: list[dict[str, Any]],
    registry_term_set: set[str],
) -> float:
    score = len(refs) * 100.0
    if term.casefold() in registry_term_set:
        score += 40.0
    if _has_cjk(term):
        score += 8.0
    score += min(len(term), 20)
    return score


def _domain_event_from_term(
    *,
    thread_key: str,
    term: str,
    refs: list[dict[str, Any]],
    co_terms: Counter[str],
    registry_term_set: set[str],
) -> dict[str, Any] | None:
    cues = unique_preserve(
        [
            term,
            *[
                item
                for item, _count in co_terms.most_common(8)
                if item.casefold() != term.casefold()
            ],
        ],
        limit=6,
    )
    event = {
        "event_kind": "domain_created",
        "domain_id": _hash([thread_key, term], prefix="cd_reg"),
        "title": term,
        "domain_type": "recurring_question",
        "scale": "meso",
        "summary": "Deterministic registry producer found repeated source-backed continuity material.",
        "working_conclusion_short": (
            "Registered clean-source history repeatedly points to this continuity domain; "
            "reopen the listed clean-source refs before factual use."
        ),
        "activation_cues": cues,
        "scope_labels": ["registry_real_history"],
        "long_range_tendencies": [term] if term.casefold() in registry_term_set else [],
        "source_refs": refs[:6],
    }
    return normalize_continuity_domain_event(event, clean_source_dir=None)


def _public_label_row(
    *,
    term: str,
    thread_key: str,
    refs: list[dict[str, Any]],
    score: float,
    include_local_detail: bool,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "label_hash": _hash(term, prefix="label"),
        "thread_hash": _hash(thread_key, prefix="thread"),
        "support_ref_count": len(refs),
        "score": round(score, 3),
    }
    if include_local_detail:
        row["label"] = compact_text(term, 120)
        row["thread_key"] = compact_text(thread_key, 160)
    return row


def propose_continuity_domain_events_from_registry(
    *,
    registry_path: Path | str | None = None,
    registry_dir: Path | str | None = None,
    min_support: int = 2,
    max_threads: int | None = None,
    max_candidates: int = 24,
    include_local_detail: bool = False,
    refresh_query_pattern_routes: bool = False,
) -> dict[str, Any]:
    """Build source-ref-backed continuity-domain event candidates from registry history.

    The returned report is public-safe by default: domain labels are hashed and
    candidate events are omitted unless `include_local_detail=True`. Promotion
    remains a separate explicit append/publish step.
    """

    registry_path_obj = (
        Path(registry_path).resolve()
        if registry_path
        else registry_paths(Path(registry_dir).resolve() if registry_dir else None)[0]
    )
    registry = load_registry(registry_path_obj)
    registry_root = registry_path_obj.parent
    query_pattern_refresh: dict[str, Any] | None = None
    if refresh_query_pattern_routes:
        query_pattern_refresh = publish_registry_query_pattern_routes(
            registry,
            registry_dir=registry_root,
        )
    threads = [
        entry for entry in registry.get("threads") or [] if isinstance(entry, Mapping)
    ]
    if max_threads is not None:
        threads = threads[: max(0, int(max_threads))]

    term_refs: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    term_co_terms: dict[tuple[str, str], Counter[str]] = defaultdict(Counter)
    registry_terms_by_thread: dict[str, set[str]] = {}
    missing_source_ref_count = 0
    privacy_suppressed_terms: set[str] = set()
    low_information_label_suppressed_count = 0
    scanned_thread_count = 0
    signal_candidate_count = 0
    known_refs: dict[str, dict[str, set[str]]] = defaultdict(
        lambda: {
            "message_id": set(),
            "turn_id": set(),
            "turn_index": set(),
            "line": set(),
        }
    )

    for entry in threads:
        thread_key = str(entry.get("thread_key") or "").strip()
        clean_dir = _entry_clean_source_dir(entry)
        if not thread_key or clean_dir is None:
            continue
        scanned_thread_count += 1
        registry_terms = _registry_terms(entry)
        registry_terms_by_thread[thread_key] = {term.casefold() for term in registry_terms}
        for message in iter_clean_messages(clean_dir / "messages.jsonl"):
            text = str(message.get("text") or "")
            if not text:
                continue
            _remember_ref(known_refs, thread_key=thread_key, message=message)
            ref = _message_source_ref(thread_key, message)
            if ref is None:
                missing_source_ref_count += 1
                continue
            terms, suppressed_count, low_information_count = _terms_for_message(text, registry_terms)
            if suppressed_count:
                privacy_suppressed_terms.update(split_query_terms([text])[:suppressed_count])
            low_information_label_suppressed_count += low_information_count
            for term in terms:
                key = (thread_key, term)
                if not any(existing == ref for existing in term_refs[key]):
                    term_refs[key].append(ref)
                term_co_terms[key].update(other for other in terms if other != term)

    # Reviewed sidecars may propose aliases, routes, or atmosphere, but they do
    # not become evidence here. They are accepted only as label producers after
    # their refs resolve back to registered clean-source messages.
    for file_name in SIGNAL_CANDIDATE_FILES:
        for row in _iter_jsonl(registry_root / file_name):
            raw_refs = row.get("source_refs") or row.get("source_ref") or row.get("representative_sources")
            refs = _resolving_signal_refs(raw_refs, known_refs=known_refs)
            if not refs:
                if safe_source_refs(raw_refs):
                    missing_source_ref_count += 1
                continue
            terms, suppressed_count, low_information_count = _signal_term_values(row)
            privacy_suppressed_terms.update(f"signal:{file_name}:{index}" for index in range(suppressed_count))
            low_information_label_suppressed_count += low_information_count
            for thread_key, thread_refs in _refs_by_thread(refs).items():
                for term in terms:
                    key = (thread_key, term)
                    for ref in thread_refs:
                        if not any(existing == ref for existing in term_refs[key]):
                            term_refs[key].append(ref)
                    term_co_terms[key].update(other for other in terms if other != term)
                    signal_candidate_count += 1

    candidates: list[tuple[float, str, str, list[dict[str, Any]], dict[str, Any]]] = []
    rejected_event_count = 0
    for (thread_key, term), refs in term_refs.items():
        if len(refs) < max(1, int(min_support)):
            continue
        registry_term_set = registry_terms_by_thread.get(thread_key, set())
        score = _candidate_score(term=term, refs=refs, registry_term_set=registry_term_set)
        event = _domain_event_from_term(
            thread_key=thread_key,
            term=term,
            refs=refs,
            co_terms=term_co_terms[(thread_key, term)],
            registry_term_set=registry_term_set,
        )
        if event is None:
            rejected_event_count += 1
            continue
        candidates.append((score, thread_key, term, refs, event))

    candidates.sort(key=lambda item: (-item[0], item[2].casefold()))
    selected = candidates[: max(0, int(max_candidates))]
    label_rows = [
        _public_label_row(
            term=term,
            thread_key=thread_key,
            refs=refs,
            score=score,
            include_local_detail=include_local_detail,
        )
        for score, thread_key, term, refs, _event in selected[:8]
    ]
    candidate_events = [event for _score, _thread_key, _term, _refs, event in selected]
    report: dict[str, Any] = {
        "ok": True,
        "kind": CONTINUITY_DOMAIN_PRODUCER_KIND,
        "schema_version": CONTINUITY_DOMAIN_SCHEMA_VERSION,
        "generated_at": now_utc(),
        "mode": "dry_run",
        "metrics": {
            "registered_thread_count": len(registry.get("threads") or []),
            "scanned_thread_count": scanned_thread_count,
            "candidate_domain_count": len(selected),
            "signal_candidate_count": signal_candidate_count,
            "accepted_event_count": len(candidate_events),
            "rejected_event_count": rejected_event_count,
            "missing_source_ref_count": missing_source_ref_count,
            "privacy_suppressed_count": len(privacy_suppressed_terms),
            "low_information_label_suppressed_count": low_information_label_suppressed_count,
        },
        "top_domain_labels": label_rows,
        "source_boundary": {
            "producer_is_not_source_truth": True,
            "candidate_events_require_source_refs": True,
            "hooks_create_domains": False,
            "source_reopen_required_before_claim": True,
            "raw_source_text_serialized": False,
        },
    }
    if include_local_detail:
        report["candidate_events"] = candidate_events
    if query_pattern_refresh is not None:
        report["query_pattern_refresh"] = query_pattern_refresh
    return redact_sensitive_values(redact_private_paths(report))
