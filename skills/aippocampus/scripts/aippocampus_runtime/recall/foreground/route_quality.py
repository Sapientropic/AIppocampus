"""Route-label and cue-anchor quality helpers."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from aippocampus_runtime import core
from aippocampus_runtime.privacy import redact_private_paths, redact_sensitive_values
from aippocampus_runtime.recall.query_policy import normalize_term

_TERM_SPLIT_RE = re.compile(r"[\u4e00-\u9fff]{2,}|[A-Za-z0-9][A-Za-z0-9_-]{1,}")
_TERM_KEY_RE = re.compile(r"[^0-9A-Za-z\u4e00-\u9fff]+")

LOW_SIGNAL_ANCHOR_TERMS = {
    "about",
    "agent",
    "agentnative",
    "anchor",
    "anchors",
    "apw",
    "benchmark",
    "boundary",
    "claim",
    "ci",
    "cli",
    "compact",
    "context",
    "continuity",
    "debug",
    "decision",
    "deepen",
    "detail",
    "diagnostic",
    "dogfood",
    "evidence",
    "facade",
    "feedback",
    "foreground",
    "fresh",
    "generic",
    "gate",
    "hook",
    "issue",
    "issues",
    "label",
    "labels",
    "memory",
    "meta",
    "mcp",
    "native",
    "open",
    "opened",
    "posture",
    "pr",
    "recall",
    "reopen",
    "route",
    "routes",
    "safe",
    "search",
    "semantic",
    "source",
    "sourcebacked",
    "test",
    "tests",
    "too",
    "ux",
    "vague",
    "why",
    "work",
}

LOW_SIGNAL_CJK_TERMS = {
    "之前",
    "前面",
    "刚才",
    "上次",
    "这个",
    "那个",
    "一下",
    "看看",
    "找找",
    "查查",
    "原话",
    "原文",
    "证据",
    "来源",
    "召回",
    "路线",
    "标签",
}

SHORT_MEANINGFUL_TECHNICAL_ANCHOR_TERMS = {
    "batch",
    "cache",
    "data",
    "edge",
    "graph",
    "macro",
    "node",
    "queue",
    "rust",
}

ANCHOR_QUALITY_DRIFT_SAMPLE_TERMS = (
    "rust",
    "data",
    "node",
    "edge",
    "graph",
    "queue",
    "cache",
    "batch",
    "macro",
    "ci",
    "pr",
    "ux",
    "mcp",
    "apw",
    "why",
    "too",
    "route",
    "label",
)

GENERIC_PUBLIC_LABEL_KEYS = {
    "agent native recall facade",
    "aippocampus",
    "benchmark claim posture",
    "issue backlog interpretation",
    "memory route",
    "relationship continuity route",
    "route note route",
    "semantic trigger",
    "source reopen boundary",
}


def term_key(value: Any) -> str:
    text = normalize_term(str(value or "")).casefold()
    return _TERM_KEY_RE.sub("", text)


def public_text(value: Any, *, limit: int = 96) -> str:
    text = str(redact_sensitive_values(redact_private_paths(str(value or "").strip())) or "")
    text = " ".join(text.replace("_", " ").replace("·", " ").split())
    return core.compact_text(text, limit)


def is_low_signal_anchor(value: Any) -> bool:
    key = term_key(value)
    if not key:
        return True
    if key in LOW_SIGNAL_ANCHOR_TERMS or key in LOW_SIGNAL_CJK_TERMS:
        return True
    if key in SHORT_MEANINGFUL_TECHNICAL_ANCHOR_TERMS:
        return False
    if key.isascii() and len(key) < 6:
        return True
    return False


def meaningful_terms(terms: Sequence[Any], *, limit: int = 8) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for term in term_sequence(terms):
        text = public_text(term, limit=80)
        key = term_key(text)
        if not key or key in seen or is_low_signal_anchor(text):
            continue
        seen.add(key)
        result.append(text)
        if len(result) >= limit:
            break
    return result


def _keyed_terms(terms: Sequence[Any]) -> dict[str, str]:
    keyed: dict[str, str] = {}
    for term in term_sequence(terms):
        text = public_text(term, limit=80)
        key = term_key(text)
        if key and key not in keyed:
            keyed[key] = text
    return keyed


def term_sequence(terms: Sequence[Any] | Any) -> list[Any]:
    """Return a list without splitting strings into characters."""

    if terms is None:
        return []
    if isinstance(terms, str):
        return [terms]
    if isinstance(terms, Sequence):
        return list(terms)
    return [terms]


def anchor_quality(
    *,
    matched_terms: Sequence[Any],
    anchor_terms: Sequence[Any],
) -> dict[str, Any]:
    anchors = _keyed_terms(anchor_terms)
    matched = _keyed_terms(matched_terms)
    anchor_keys = set(anchors)
    matched_keys = set(matched)
    raw_hits = sorted(anchor_keys & matched_keys)
    meaningful_anchor_keys = {
        key for key, term in anchors.items() if not is_low_signal_anchor(term)
    }
    meaningful_hit_keys = sorted(meaningful_anchor_keys & matched_keys)
    weak_hit_keys = [key for key in raw_hits if key not in meaningful_anchor_keys]
    if meaningful_hit_keys:
        status = "meaningful_anchor_match"
    elif meaningful_anchor_keys:
        status = "missing_meaningful_anchor"
    elif raw_hits:
        status = "low_signal_anchors_only"
    else:
        status = "no_anchor_hits"
    return {
        "status": status,
        "anchor_count": len(anchor_keys),
        "opened_anchor_hits": len(raw_hits),
        "meaningful_anchor_count": len(meaningful_anchor_keys),
        "meaningful_anchor_hits": len(meaningful_hit_keys),
        "weak_anchor_hits": len(weak_hit_keys),
        "meaningful_matched_terms": [matched[key] for key in meaningful_hit_keys],
        "low_signal_matched_terms": [matched[key] for key in weak_hit_keys],
    }


def split_label_terms(label: str) -> list[str]:
    return [match.group(0) for match in _TERM_SPLIT_RE.finditer(label or "")]


def label_is_generic(label: Any) -> bool:
    text = public_text(label, limit=120)
    if not text:
        return True
    if " ".join(text.casefold().split()) in GENERIC_PUBLIC_LABEL_KEYS:
        return True
    return not meaningful_terms(split_label_terms(text), limit=2)


def repaired_public_label(packet: Mapping[str, Any], fallback_label: str) -> str:
    """Return a compact label that helps choose a route, or says it cannot."""

    fallback = public_text(fallback_label, limit=90)
    if fallback and not label_is_generic(fallback):
        return fallback
    for key in (
        "public_label",
        "finding_title",
        "trajectory_title",
        "route_note_title",
        "title",
        "summary",
        "why_this_may_matter",
    ):
        candidate = public_text(packet.get(key), limit=90)
        if candidate and not label_is_generic(candidate):
            return candidate
    for key in (
        "meaningful_cue_anchors",
        "meaningful_matched_terms",
        "route_terms",
        "actual_source_matched_terms",
        "matched_cue_anchors",
    ):
        raw = packet.get(key)
        terms = meaningful_terms(raw if isinstance(raw, Sequence) and not isinstance(raw, str) else [raw])
        if terms:
            return core.compact_text("Cue: " + " / ".join(terms[:3]), 90)
    return "Low-specificity route"


def anchor_quality_drift_report(terms: Sequence[Any] | None = None) -> dict[str, Any]:
    """Classify short anchor examples for the tiny guard report."""

    raw_terms = list(terms) if terms is not None else list(ANCHOR_QUALITY_DRIFT_SAMPLE_TERMS)
    rows: list[dict[str, Any]] = []
    for term in term_sequence(raw_terms):
        text = public_text(term, limit=48)
        key = term_key(text)
        if not key:
            continue
        low_signal = is_low_signal_anchor(text)
        if key in LOW_SIGNAL_ANCHOR_TERMS or key in LOW_SIGNAL_CJK_TERMS:
            reason = "explicit_low_signal_vocabulary"
        elif key in SHORT_MEANINGFUL_TECHNICAL_ANCHOR_TERMS:
            reason = "short_meaningful_technical_allowlist"
        elif key.isascii() and len(key) < 6:
            reason = "short_ascii_needs_owner_decision"
        else:
            reason = "meaningful_by_default"
        rows.append(
            {
                "term": text,
                "key": key,
                "low_signal": low_signal,
                "reason": reason,
            }
        )
    unresolved = [
        row
        for row in rows
        if row["reason"] == "short_ascii_needs_owner_decision"
        and row["key"] not in LOW_SIGNAL_ANCHOR_TERMS
    ]
    return {
        "kind": "aippocampus_route_anchor_quality_drift_report",
        "schema_version": 1,
        "ok": not unresolved,
        "term_count": len(rows),
        "short_meaningful_allowlist": sorted(SHORT_MEANINGFUL_TECHNICAL_ANCHOR_TERMS),
        "explicit_low_signal_count": sum(
            1 for row in rows if row["reason"] == "explicit_low_signal_vocabulary"
        ),
        "unresolved_short_ascii_count": len(unresolved),
        "unresolved_short_ascii_terms": [row["term"] for row in unresolved[:12]],
        "classifications": rows,
        "privacy_boundary": {
            "raw_source_text_serialized": False,
            "terms_redacted_before_output": True,
        },
    }


__all__ = [
    "ANCHOR_QUALITY_DRIFT_SAMPLE_TERMS",
    "LOW_SIGNAL_ANCHOR_TERMS",
    "SHORT_MEANINGFUL_TECHNICAL_ANCHOR_TERMS",
    "anchor_quality_drift_report",
    "anchor_quality",
    "is_low_signal_anchor",
    "label_is_generic",
    "meaningful_terms",
    "public_text",
    "repaired_public_label",
    "term_key",
    "term_sequence",
]
