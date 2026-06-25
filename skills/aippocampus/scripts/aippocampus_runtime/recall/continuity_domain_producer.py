#!/usr/bin/env python3
"""Explicit producer for source-trailed continuity-domain events.

This module is the bridge from registered real history to continuity-domain
events. It is deliberately deterministic and operator-invoked: prompt hooks
consume published domain snapshots, but they must not scan private history or
author durable domain events while the user is typing.
"""

from __future__ import annotations

import hashlib
import re
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from aippocampus_runtime.core import compact_text, now_utc
from aippocampus_runtime.privacy import (
    LOCAL_PATH_REDACTION,
    SENSITIVE_VALUE_REDACTION,
    redact_private_paths,
    redact_sensitive_values,
)
from aippocampus_runtime.recall.continuity_domain_scan import (
    collect_continuity_domain_scan,
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
from aippocampus_runtime.warm_ambient.query_pattern_routes import (
    publish_registry_query_pattern_routes,
)

CONTINUITY_DOMAIN_PRODUCER_KIND = "aippocampus_continuity_domain_producer_report"
DEFAULT_CONTINUITY_DOMAIN_PREVIEW_THREAD_BUDGET = 8
DEFAULT_CONTINUITY_DOMAIN_PREVIEW_MESSAGE_BUDGET = 1000
DEFAULT_CONTINUITY_DOMAIN_PREVIEW_CANDIDATE_BUDGET = 8
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
    "candidate",
    "candidates",
    "checkpoint",
    "comment",
    "comments",
    "clean",
    "conversation",
    "conversations",
    "from",
    "generated",
    "focus",
    "health",
    "issue",
    "issues",
    "line",
    "lines",
    "main",
    "master",
    "branch",
    "commit",
    "merge",
    "pr",
    "pull",
    "repo",
    "repository",
    "source",
    "trail",
    "source trail",
    "clean source",
    "message",
    "messages",
    "normalized",
    "plugin",
    "plugins",
    "sapientropic",
    "recent",
    "rollout",
    "rollouts",
    "transcript",
    "transcripts",
    "status",
    "thread",
    "user",
    "users",
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
    "看看",
    "看下",
    "看一下",
    "最近",
    "用户",
    "角度",
    "现在试",
    "然后提",
    "实测",
    "深度实测",
    "再深度实测",
    "资深产品经理",
    "以资深产品经理",
    "不是",
    "不过",
    "刚才",
    "刚刚",
    "本机",
    "本地",
    "压缩",
}
UNTRUSTED_SINGLE_WORD_PRODUCER_TERMS = {
    "activation",
    "backstage",
    "checklist",
    "easy",
    "feel",
    "first",
    "gentle",
    "get",
    "gets",
    "got",
    "human",
    "know",
    "life",
    "like",
    "person",
    "persona",
    "sound",
    "start",
    "stays",
    "survey",
    "system",
    "visible",
    "voice",
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
    *UNTRUSTED_SINGLE_WORD_PRODUCER_TERMS,
    "a",
    "an",
    "the",
    "this",
    "that",
    "these",
    "those",
    "candidate",
    "candidates",
    "checkpoint",
    "comment",
    "comments",
    "clean",
    "conversation",
    "conversations",
    "from",
    "generated",
    "focus",
    "health",
    "issue",
    "issues",
    "line",
    "lines",
    "message",
    "messages",
    "normalized",
    "plugin",
    "plugins",
    "recent",
    "rollout",
    "rollouts",
    "transcript",
    "transcripts",
    "status",
    "user",
    "users",
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
PLAIN_LATIN_SINGLE_RE = re.compile(r"^[A-Za-z][A-Za-z']*$")
CJK_DEICTIC_ACTION_RE = re.compile(
    r"(这个|那个|这些|那些|这里|那里|这边|那边).{0,32}"
    r"(要怎么|怎么|怎样|如何|改|修改|调整|处理|做|办|弄)"
)
CJK_ACTION_PROMPT_RE = re.compile(
    r"(要怎么|怎么改|怎么办|怎么做|怎么处理|如何改|如何处理|改一下|弄一下)"
)
LINE_RANGE_TOKEN_RE = re.compile(r"^\d{1,6}[-–]\d{1,6}$")
MARKDOWN_LINK_FRAGMENT_RE = re.compile(r"\]\(\s*https?", re.IGNORECASE)
HOSTNAME_OR_DOMAIN_RE = re.compile(
    r"(?:[a-z0-9-]+\.)+[a-z]{2,}(?:/[^\s]*)?",
    re.IGNORECASE,
)


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


def _plain_latin_single_needs_trust(text: str) -> bool:
    return bool(PLAIN_LATIN_SINGLE_RE.fullmatch(text)) and text.islower()


def _low_information_producer_term(
    text: str,
    *,
    trusted_domain_label: bool = False,
) -> bool:
    low = text.casefold()
    if low in LOW_INFORMATION_PRODUCER_TERMS:
        return True
    if not trusted_domain_label and low in UNTRUSTED_SINGLE_WORD_PRODUCER_TERMS:
        return True
    latin_tokens = re.findall(r"[A-Za-z][A-Za-z'-]*", low)
    if not trusted_domain_label and latin_tokens and len(latin_tokens) <= 5:
        token_set = set(latin_tokens)
        if token_set <= ENGLISH_LOW_INFORMATION_FILLER_TERMS:
            return True
    # Raw clean-source prose produces many high-frequency single English words.
    # They are useful search tokens, but not durable continuity-domain labels
    # unless the registry or a reviewed sidecar already named them as aliases.
    if not trusted_domain_label and _plain_latin_single_needs_trust(text):
        return True
    # A deictic action prompt such as "这个要怎么改一下" is a useful recall
    # activator, but it is not a durable label or activation cue. Reject it
    # even when split_query_terms keeps a nearby project alias in the same
    # phrase, otherwise a generic follow-up can project an unrelated route.
    if _has_cjk(text) and CJK_DEICTIC_ACTION_RE.search(text):
        return True
    if _has_cjk(text) and len(text) <= 96 and ("看看" in text or "试一下" in text):
        return True
    if _has_cjk(text) and len(text) <= 32 and CJK_ACTION_PROMPT_RE.search(text):
        return True
    if _has_cjk(text) and len(text) <= 12:
        if CJK_DEICTIC_ACTION_RE.search(text):
            return True
        if CJK_ACTION_PROMPT_RE.search(text):
            return True
    return False


def _clean_candidate_term_detail(
    term: str,
    *,
    trusted_domain_label: bool = False,
) -> tuple[str, str]:
    text = re.sub(r"\s+", " ", str(term or "")).strip(" \t\r\n\"'`.,;:!?，。；：！？、")
    if not text:
        return "", ""
    if _privacy_suppressed_term(text):
        return "", "privacy"
    if MARKDOWN_LINK_FRAGMENT_RE.search(text):
        return "", "shape"
    if HOSTNAME_OR_DOMAIN_RE.fullmatch(text.casefold()):
        return "", "low_information"
    if LINE_RANGE_TOKEN_RE.fullmatch(text):
        return "", "low_information"
    if "/" in text and " " not in text and not _has_cjk(text):
        return "", "shape"
    low = text.casefold()
    if low in GENERIC_PRODUCER_TERMS:
        return "", "low_information"
    if _low_information_producer_term(text, trusted_domain_label=trusted_domain_label):
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


def _registry_terms(entry: Mapping[str, Any]) -> list[str]:
    values: list[str] = []
    for key in ("keywords", "anchor_titles", "project_tags"):
        raw = entry.get(key)
        if isinstance(raw, list):
            values.extend(str(item) for item in raw if item)
    terms: list[str] = []
    for value in values:
        terms.extend(split_query_terms([value]))
    return unique_preserve(
        [
            term
            for term in terms
            if _clean_candidate_term_detail(term, trusted_domain_label=True)[0]
        ],
        limit=64,
    )


def _signal_term_values(
    row: Mapping[str, Any],
    *,
    trusted_domain_label: bool = False,
) -> tuple[list[str], int, int]:
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
            term, reason = _clean_candidate_term_detail(
                raw,
                trusted_domain_label=trusted_domain_label,
            )
            if reason == "privacy":
                privacy_suppressed += 1
            elif reason == "low_information":
                low_information_suppressed += 1
            if term:
                terms.append(term)
    return unique_preserve(terms, limit=16), privacy_suppressed, low_information_suppressed


def _reviewed_signal_label_source(file_name: str, row: Mapping[str, Any]) -> bool:
    kind = str(row.get("kind") or "").casefold()
    status = str(row.get("status") or "").casefold()
    if status and status not in {"active", "accepted", "reviewed", "published", "ready"}:
        return False
    return file_name in {"semantic_triggers.jsonl", "query_pattern_routes.jsonl"} and (
        "semantic_trigger" in kind or "query_pattern_route" in kind
    )


def _terms_for_message(text: str, registry_terms: list[str]) -> tuple[list[str], int, int]:
    terms: list[str] = []
    privacy_suppressed = 0
    low_information_suppressed = 0
    low_text = text.casefold()
    registry_term_set = {term.casefold() for term in registry_terms}
    for raw in [*split_query_terms([text]), *registry_terms]:
        raw_low = raw.casefold()
        if raw_low not in low_text and raw_low not in registry_term_set:
            continue
        term, reason = _clean_candidate_term_detail(
            raw,
            trusted_domain_label=raw_low in registry_term_set,
        )
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
    raw_cues = [
        term,
        *[
            item
            for item, _count in co_terms.most_common(8)
            if item.casefold() != term.casefold()
        ],
    ]
    cues = unique_preserve(
        [
            cue
            for cue in raw_cues
            if _clean_candidate_term_detail(
                cue,
                trusted_domain_label=cue.casefold() in registry_term_set,
            )[0]
        ],
        limit=6,
    )
    if not cues:
        return None
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
    max_messages_per_thread: int | None = None,
    max_candidates: int = 24,
    include_local_detail: bool = False,
    refresh_query_pattern_routes: bool = False,
    broad_scan_requested: bool = False,
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
    all_threads = [
        entry for entry in registry.get("threads") or [] if isinstance(entry, Mapping)
    ]
    registered_thread_count = len(all_threads)
    effective_thread_budget = (
        max(0, int(max_threads)) if max_threads is not None else None
    )
    effective_message_budget = (
        max(0, int(max_messages_per_thread))
        if max_messages_per_thread is not None
        else None
    )
    threads = all_threads
    if max_threads is not None:
        threads = threads[: max(0, int(max_threads))]
    considered_thread_count = len(threads)
    scan_truncated_by_budget = (
        effective_thread_budget is not None
        and registered_thread_count > effective_thread_budget
    )

    scan = collect_continuity_domain_scan(
        threads=threads,
        registry_root=registry_root,
        signal_candidate_files=SIGNAL_CANDIDATE_FILES,
        max_messages_per_thread=effective_message_budget,
        entry_clean_source_dir=_entry_clean_source_dir,
        registry_terms_for_entry=_registry_terms,
        privacy_suppressed_term=_privacy_suppressed_term,
        terms_for_message=_terms_for_message,
        signal_term_values=lambda file_name, row: _signal_term_values(
            row,
            trusted_domain_label=_reviewed_signal_label_source(file_name, row),
        ),
    )

    candidates: list[tuple[float, str, str, list[dict[str, Any]], dict[str, Any]]] = []
    rejected_event_count = 0
    for (thread_key, term), refs in scan.term_refs.items():
        if len(refs) < max(1, int(min_support)):
            continue
        registry_term_set = scan.registry_terms_by_thread.get(thread_key, set())
        score = _candidate_score(term=term, refs=refs, registry_term_set=registry_term_set)
        event = _domain_event_from_term(
            thread_key=thread_key,
            term=term,
            refs=refs,
            co_terms=scan.term_co_terms[(thread_key, term)],
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
    scan_truncated_by_message_budget = scan.message_budget_truncated_thread_count > 0
    scan_partial = scan_truncated_by_budget or scan_truncated_by_message_budget
    report: dict[str, Any] = {
        "ok": True,
        "kind": CONTINUITY_DOMAIN_PRODUCER_KIND,
        "schema_version": CONTINUITY_DOMAIN_SCHEMA_VERSION,
        "generated_at": now_utc(),
        "mode": "dry_run",
        "metrics": {
            "registered_thread_count": len(registry.get("threads") or []),
            "considered_thread_count": considered_thread_count,
            "scanned_thread_count": scan.scanned_thread_count,
            "scanned_message_count": scan.scanned_message_count,
            "skipped_message_count": scan.skipped_message_count,
            "skipped_message_count_is_lower_bound": scan.skipped_message_count_is_lower_bound,
            "scan_budget_max_threads": effective_thread_budget,
            "scan_budget_max_messages_per_thread": effective_message_budget,
            "scan_truncated_by_budget": scan_truncated_by_budget,
            "scan_truncated_by_message_budget": scan_truncated_by_message_budget,
            "scan_partial": scan_partial,
            "message_budget_truncated_thread_count": scan.message_budget_truncated_thread_count,
            "message_budget_cutoff_thread_count": scan.message_budget_cutoff_thread_count,
            "unique_term_ref_key_count": len(scan.term_refs),
            "source_ref_candidate_count": scan.source_ref_candidate_count,
            "source_ref_identity_probe_count": scan.source_ref_identity_probe_count,
            "source_ref_dedup_hit_count": scan.source_ref_dedup_hit_count,
            "source_ref_dedup_list_scan_count": 0,
            "broad_scan_requested": bool(broad_scan_requested),
            "candidate_domain_count": len(selected),
            "signal_candidate_count": scan.signal_candidate_count,
            "accepted_event_count": len(candidate_events),
            "rejected_event_count": rejected_event_count,
            "missing_source_ref_count": scan.missing_source_ref_count,
            "privacy_suppressed_count": len(scan.privacy_suppressed_terms),
            "low_information_label_suppressed_count": scan.low_information_label_suppressed_count,
        },
        "top_domain_labels": label_rows,
        "source_boundary": {
            "producer_is_not_source_truth": True,
            "candidate_events_require_source_refs": True,
            "hooks_create_domains": False,
            "source_reopen_required_before_claim": True,
            "raw_source_text_serialized": False,
        },
        "scan_policy": {
            "mode": "explicit_broad_scan" if broad_scan_requested else "bounded_or_default",
            "partial": scan_partial,
            "registered_thread_count": registered_thread_count,
            "considered_thread_count": considered_thread_count,
            "scanned_thread_count": scan.scanned_thread_count,
            "scanned_message_count": scan.scanned_message_count,
            "skipped_message_count": scan.skipped_message_count,
            "skipped_message_count_is_lower_bound": scan.skipped_message_count_is_lower_bound,
            "max_threads": effective_thread_budget,
            "max_messages_per_thread": effective_message_budget,
            "message_budget_truncated_thread_count": scan.message_budget_truncated_thread_count,
            "message_budget_cutoff_thread_count": scan.message_budget_cutoff_thread_count,
            "broad_scan_explicit": bool(broad_scan_requested),
            "broad_scan_requires_explicit_flag": True,
            "broad_scan_command": "aippocampus continuity-domain preview --broad-scan --json",
        },
    }
    if include_local_detail:
        report["candidate_events"] = candidate_events
    if query_pattern_refresh is not None:
        report["query_pattern_refresh"] = query_pattern_refresh
    return redact_sensitive_values(redact_private_paths(report))
