"""Corpus-level CJK phrase mining for association staging."""

from __future__ import annotations

from typing import Any

from aippocampus_runtime.navigation.association_terms import (
    DURABLE_CJK_HINTS,
    source_text_is_noise,
    term_is_noise,
)
from aippocampus_runtime.registry.api import unique_preserve
from aippocampus_runtime.text import (
    CJK_DOMAIN_ANCHORS,
    iter_cjk_sequences,
    strip_cjk_deictic_prefix,
)

CJK_BAD_EDGE_CHARS = frozenset("的了和与或而但在把对给吗呢吧啊是")
CJK_MINED_SIZES = tuple(range(2, 7))


def _serializable_cjk_phrase_stat(term: str, raw: dict[str, Any]) -> dict[str, Any]:
    left = set(raw.get("left") or set())
    right = set(raw.get("right") or set())
    docs = set(raw.get("docs") or set())
    frequency = int(raw.get("frequency") or 0)
    left_av = len(left)
    right_av = len(right)
    doc_count = len(docs)
    domain_bonus = 32.0 if term in CJK_DOMAIN_ANCHORS else 0.0
    durable_bonus = 8.0 if any(hint in term for hint in DURABLE_CJK_HINTS) else 0.0
    length_bonus = 3.0 if 3 <= len(term) <= 6 else 0.0
    over_fanout_penalty = max(0, doc_count - 80) * 0.18 + max(0, frequency - 240) * 0.04
    score = (
        min(frequency, 12) * 1.0
        + min(doc_count, 8) * 1.8
        + min(left_av, 8) * 1.2
        + min(right_av, 8) * 1.2
        + domain_bonus
        + durable_bonus
        + length_bonus
        - over_fanout_penalty
    )
    return {
        "frequency": frequency,
        "document_count": doc_count,
        "left_accessor_variety": left_av,
        "right_accessor_variety": right_av,
        "score": round(score, 3),
    }


def _reject_mined_cjk_candidate(term: str) -> str | None:
    if not term or len(term) < 2 or len(term) > max(CJK_MINED_SIZES):
        return "length"
    if term in CJK_DOMAIN_ANCHORS:
        return None
    if len(term) == 2 and not any(hint in term for hint in DURABLE_CJK_HINTS):
        return "low_value"
    if term[0] in CJK_BAD_EDGE_CHARS or term[-1] in CJK_BAD_EDGE_CHARS:
        return "bad_edge"
    if term_is_noise(term):
        return "low_value"
    return None


def _is_substring_dominated(term: str, raw_stats: dict[str, dict[str, Any]]) -> bool:
    if len(term) <= 3 or term in CJK_DOMAIN_ANCHORS:
        return False
    stat = raw_stats.get(term) or {}
    frequency = int(stat.get("frequency") or 0)
    if frequency <= 0:
        return False
    left_av = len(stat.get("left") or set())
    right_av = len(stat.get("right") or set())
    doc_count = len(stat.get("docs") or set())
    if left_av > 1 or right_av > 1 or doc_count > 1:
        return False
    containing_frequency = 0
    for other, other_stat in raw_stats.items():
        if other == term or len(other) <= len(term) or term not in other:
            continue
        containing_frequency += int(other_stat.get("frequency") or 0)
        if containing_frequency >= frequency:
            return True
    return False


def _bump(diagnostics: dict[str, int] | None, key: str) -> None:
    if diagnostics is not None:
        diagnostics[key] = int(diagnostics.get(key) or 0) + 1


def mine_corpus_cjk_phrases(
    rows: list[dict[str, Any]],
    *,
    diagnostics: dict[str, int] | None = None,
    limit: int = 1200,
    min_frequency: int = 2,
) -> dict[str, dict[str, Any]]:
    """Mine reusable CJK phrases from source windows before graph materialization.

    This is a candidate layer, not semantic authority. Static anchors can still
    bootstrap exact cues, but automatic phrasehood needs corpus support:
    frequency, source/window count, and left/right accessor variety. That keeps
    rare clause shards from winning simply because they are unusual.
    """

    raw_stats: dict[str, dict[str, Any]] = {}
    windows = 0
    for index, row in enumerate(rows):
        text = str(row.get("text") or "")
        if not text:
            continue
        doc_id = str(
            row.get("document_id")
            or row.get("source_ref")
            or row.get("thread_key")
            or index
        )
        for seq in iter_cjk_sequences(text, min_len=2, max_len=80):
            if source_text_is_noise(seq):
                continue
            windows += 1
            max_size = min(max(CJK_MINED_SIZES), len(seq))
            for size in CJK_MINED_SIZES:
                if size > max_size:
                    continue
                for offset in range(0, len(seq) - size + 1):
                    term = strip_cjk_deictic_prefix(seq[offset : offset + size])
                    reason = _reject_mined_cjk_candidate(term)
                    if reason:
                        if reason in {"bad_edge", "low_value"}:
                            _bump(diagnostics, "cjk_phrase_miner_rejected_boundary_count")
                        continue
                    stat = raw_stats.setdefault(
                        term,
                        {
                            "frequency": 0,
                            "docs": set(),
                            "left": set(),
                            "right": set(),
                        },
                    )
                    stat["frequency"] = int(stat.get("frequency") or 0) + 1
                    stat["docs"].add(doc_id)
                    stat["left"].add(seq[offset - 1] if offset > 0 else "^")
                    right_index = offset + size
                    stat["right"].add(seq[right_index] if right_index < len(seq) else "$")

    accepted: dict[str, dict[str, Any]] = {}
    rejected_substrings = 0
    for term, raw in raw_stats.items():
        stat = _serializable_cjk_phrase_stat(term, raw)
        frequency = int(stat["frequency"])
        doc_count = int(stat["document_count"])
        left_av = int(stat["left_accessor_variety"])
        right_av = int(stat["right_accessor_variety"])
        if term not in CJK_DOMAIN_ANCHORS:
            if frequency < min_frequency and doc_count < 2:
                continue
            if doc_count <= 1 and max(left_av, right_av) <= 1:
                continue
        if _is_substring_dominated(term, raw_stats):
            rejected_substrings += 1
            continue
        accepted[term] = stat

    ranked = sorted(
        accepted.items(),
        key=lambda item: (
            -float(item[1].get("score") or 0.0),
            -int(item[1].get("document_count") or 0),
            -int(item[1].get("frequency") or 0),
            item[0],
        ),
    )
    selected = dict(ranked[: max(1, int(limit))])
    if diagnostics is not None:
        diagnostics["cjk_phrase_miner_window_count"] = windows
        diagnostics["cjk_phrase_miner_candidate_count"] = len(raw_stats)
        diagnostics["cjk_phrase_miner_accepted_raw_count"] = len(accepted)
        diagnostics["cjk_phrase_miner_accepted_count"] = len(selected)
        diagnostics["cjk_phrase_miner_rejected_substring_count"] = rejected_substrings
    return selected


def corpus_cjk_terms_for_text(
    text: str,
    phrase_index: dict[str, dict[str, Any]] | None,
    *,
    limit: int = 12,
) -> list[str]:
    if not text or not phrase_index:
        return []
    found: list[str] = []
    max_size = 0
    for term in phrase_index:
        max_size = max(max_size, len(term))
    max_size = min(max_size or max(CJK_MINED_SIZES), max(CJK_MINED_SIZES))
    for seq in iter_cjk_sequences(text, min_len=2, max_len=80):
        for size in range(2, min(max_size, len(seq)) + 1):
            for offset in range(0, len(seq) - size + 1):
                term = strip_cjk_deictic_prefix(seq[offset : offset + size])
                if term in phrase_index and not term_is_noise(term):
                    found.append(term)
    ranked = sorted(
        unique_preserve(found, limit=None),
        key=lambda term: (
            -float((phrase_index.get(term) or {}).get("score") or 0.0),
            -int((phrase_index.get(term) or {}).get("document_count") or 0),
            -int((phrase_index.get(term) or {}).get("frequency") or 0),
            term,
        ),
    )
    return ranked[: max(1, int(limit))]
