#!/usr/bin/env python3
"""Selected source-evidence recall evaluation for life-wide prompts.

This smoke does not invent new memory. It selects source-backed life-wide turns,
builds deliberately fuzzy prompt surfaces from dynamic source terms, and checks
whether the existing clean-source search path can navigate back to the expected
message evidence. Output is aggregate and hashed so real private wording stays
inside the local registry.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

import _paths

_paths.ensure_paths()

from aippocampus_runtime.navigation.project_timeline import build_project_timeline
from aippocampus_runtime.source.clean_source import SCOPE_LABEL_ORDER
from aippocampus_runtime.source.registry_paths import resolve_registry_member_path
from aippocampus_runtime.source.search import iter_clean_messages, score_message
from aippocampus_runtime.source.semantic_scope_labels import (
    load_semantic_scope_labels,
    merged_scope_labels,
    semantic_labels_for_message,
)
from aippocampuslib import aippocampus_registry_dir
from benchmark_statistics import binomial_rate_report
from registry import deep_search_entry_result, entry_search_score, load_registry
from retrieval import GENERIC_ANCHOR_TERMS, split_query_terms, unique_preserve

PROMPT_KIND = "fuzzy_life_wide_source_evidence"
NON_TECHNICAL_LABELS = tuple(label for label in SCOPE_LABEL_ORDER if label != "technical_work")
GENERIC_TERMS = {
    *GENERIC_ANCHOR_TERMS,
    "life",
    "lately",
    "today",
    "yesterday",
    "idea",
    "question",
    "spark",
    "preference",
    "reflection",
    "continuity",
    "memory",
    "thread",
    "codex",
}


def evidence_hash(*values: Any) -> str:
    text = "\0".join(str(value or "") for value in values)
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
    return f"evidence:{digest}"


def selected_prompt_terms(
    turn: dict[str, Any],
    *,
    term_counts: dict[str, int] | None = None,
    max_term_frequency: int = 8,
    limit: int = 4,
) -> list[str]:
    terms: list[str] = []
    for term in turn.get("topic_terms") or []:
        value = str(term).strip()
        if len(value) < 3:
            continue
        if value.casefold() in GENERIC_TERMS:
            continue
        if value in SCOPE_LABEL_ORDER:
            continue
        terms.append(value)
    unique_terms = unique_preserve(terms)
    if term_counts:
        specific_terms = [
            term
            for term in unique_terms
            if int(term_counts.get(term.casefold(), 0)) <= max(1, int(max_term_frequency))
        ]
        unique_terms = sorted(
            specific_terms,
            key=lambda term: (
                int(term_counts.get(term.casefold(), 0)),
                -len(term),
                term.casefold(),
            ),
        )
    return unique_preserve(unique_terms, limit=limit)


def selected_prompt_text(terms: list[str]) -> str:
    # The generic framing is intentionally stable; the discriminating part comes
    # from source-derived terms, not a growing handcrafted fuzzy synonym table.
    cue = " ".join(terms)
    return f"之前那个偏 life-wide、像个人线索或想法火花的片段，和 {cue} 有关"


def expected_ref_for_turn(turn: dict[str, Any]) -> dict[str, Any] | None:
    refs = [ref for ref in turn.get("source_refs") or [] if isinstance(ref, dict)]
    if not refs:
        return None
    return next(
        (ref for ref in refs if ref.get("role") == "user" and ref.get("message_id")), None
    ) or next(
        (ref for ref in refs if ref.get("message_id")),
        None,
    )


def turn_has_required_semantic_label(
    turn: dict[str, Any], *, require_semantic_sidecar: bool
) -> bool:
    if not require_semantic_sidecar:
        return True
    return bool(turn.get("semantic_scope_labels"))


def dict_value(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def topic_term_counts(timeline: dict[str, Any]) -> dict[str, int]:
    life_wide = dict_value(timeline.get("life_wide"))
    labels = dict_value(life_wide.get("labels"))
    counts: dict[str, int] = {}
    seen_turn_terms: set[tuple[str, str]] = set()
    for group in labels.values():
        if not isinstance(group, dict):
            continue
        for turn in group.get("latest_turns") or []:
            if not isinstance(turn, dict):
                continue
            turn_id = "|".join(
                [
                    str(turn.get("thread_key") or ""),
                    str(turn.get("turn_id") or ""),
                    str(turn.get("turn_index") or ""),
                ]
            )
            for term in unique_preserve([str(item) for item in turn.get("topic_terms") or []]):
                key = term.casefold()
                identity = (turn_id, key)
                if identity in seen_turn_terms:
                    continue
                seen_turn_terms.add(identity)
                counts[key] = counts.get(key, 0) + 1
    return counts


def prompt_specificity_score(terms: list[str], term_counts: dict[str, int]) -> float:
    if not terms:
        return 0.0
    return (
        sum(1.0 / max(1, int(term_counts.get(term.casefold(), 1))) for term in terms)
        + len(terms) * 0.05
    )


def select_eval_cases(
    timeline: dict[str, Any],
    *,
    max_cases: int,
    require_semantic_sidecar: bool,
    max_term_frequency: int = 8,
) -> list[dict[str, Any]]:
    life_wide = dict_value(timeline.get("life_wide"))
    labels = dict_value(life_wide.get("labels"))
    term_counts = topic_term_counts(timeline)
    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()
    for label in NON_TECHNICAL_LABELS:
        group = labels.get(label)
        if not isinstance(group, dict):
            continue
        for turn in group.get("latest_turns") or []:
            if not isinstance(turn, dict) or not turn_has_required_semantic_label(
                turn, require_semantic_sidecar=require_semantic_sidecar
            ):
                continue
            ref = expected_ref_for_turn(turn)
            if not ref:
                continue
            terms = selected_prompt_terms(
                turn, term_counts=term_counts, max_term_frequency=max_term_frequency
            )
            if not terms:
                continue
            identity = "|".join(
                [
                    str(turn.get("thread_key") or ref.get("thread_key") or ""),
                    str(ref.get("message_id") or ""),
                    str(turn.get("turn_id") or ref.get("turn_id") or ""),
                ]
            )
            if identity in seen:
                continue
            seen.add(identity)
            case_id = evidence_hash(identity, label, "prompt")
            candidates.append(
                {
                    "case_id": case_id,
                    "prompt_kind": PROMPT_KIND,
                    "prompt": selected_prompt_text(terms),
                    "source_terms": terms,
                    "query_terms": split_query_terms([selected_prompt_text(terms)]),
                    "scope_labels": unique_preserve(
                        [
                            label,
                            *list(turn.get("semantic_scope_labels") or []),
                            *list(turn.get("scope_labels") or []),
                        ],
                        limit=8,
                    ),
                    "expected": {
                        "thread_key": turn.get("thread_key") or ref.get("thread_key"),
                        "message_id": ref.get("message_id"),
                        "turn_id": turn.get("turn_id") or ref.get("turn_id"),
                    },
                    "expected_evidence": evidence_hash(
                        turn.get("thread_key") or ref.get("thread_key"),
                        ref.get("message_id"),
                        turn.get("turn_id") or ref.get("turn_id"),
                    ),
                    "_specificity_score": prompt_specificity_score(terms, term_counts),
                }
            )
    candidates.sort(
        key=lambda case: (
            -float(case.get("_specificity_score") or 0.0),
            str(case.get("case_id") or ""),
        )
    )
    for case in candidates:
        case.pop("_specificity_score", None)
    return candidates[: max(1, int(max_cases))]


def hit_matches_expected(hit: dict[str, Any], expected: dict[str, Any]) -> bool:
    if expected.get("message_id") and str(hit.get("message_id") or "") == str(
        expected.get("message_id")
    ):
        return True
    if expected.get("turn_id") and str(hit.get("turn_id") or "") == str(expected.get("turn_id")):
        return True
    return False


def hit_scope_matches(hit: dict[str, Any], labels: list[str]) -> bool:
    if not labels:
        return True
    present = {str(label) for label in hit.get("scope_labels") or []}
    present.update(str(label) for label in hit.get("semantic_scope_labels") or [])
    return bool(present.intersection(labels))


def turn_key_for_row(row: dict[str, Any]) -> tuple[str, str] | None:
    message = dict_value(row.get("message"))
    thread_key = str(row.get("thread_key") or "")
    turn_id = str(message.get("turn_id") or "")
    if not thread_key or not turn_id:
        return None
    return (thread_key, turn_id)


def turn_scope_label_index(corpus: list[dict[str, Any]]) -> dict[tuple[str, str], set[str]]:
    index: dict[tuple[str, str], set[str]] = {}
    for row in corpus:
        key = turn_key_for_row(row)
        if key is None:
            continue
        message = dict_value(row.get("message"))
        labels = index.setdefault(key, set())
        labels.update(str(label) for label in message.get("scope_labels") or [])
        labels.update(str(label) for label in message.get("semantic_scope_labels") or [])
    return index


def row_or_turn_scope_matches(
    row: dict[str, Any],
    labels: list[str],
    turn_scope_labels: dict[tuple[str, str], set[str]],
) -> bool:
    if not labels:
        return True
    message = dict_value(row.get("message"))
    if hit_scope_matches(message, labels):
        return True
    key = turn_key_for_row(row)
    if key is None:
        return False
    return bool(turn_scope_labels.get(key, set()).intersection(labels))


def clean_source_corpus(
    registry: dict[str, Any], *, registry_path: Path | None = None
) -> tuple[list[dict[str, Any]], int]:
    rows: list[dict[str, Any]] = []
    warning_count = 0
    for entry in registry.get("threads") or []:
        if not isinstance(entry, dict):
            continue
        messages_path_value = (entry.get("paths") or {}).get("clean_source_messages_jsonl")
        if not messages_path_value:
            continue
        messages_path = resolve_registry_member_path(str(messages_path_value), registry_path)
        if messages_path is None:
            warning_count += 1
            continue
        try:
            semantic_sidecar = load_semantic_scope_labels(messages_path.parent)
            for message in iter_clean_messages(messages_path):
                semantic_scope_labels = semantic_labels_for_message(message, semantic_sidecar)
                if semantic_scope_labels:
                    message = dict(message)
                    message["semantic_scope_labels"] = semantic_scope_labels
                    message["scope_labels"] = merged_scope_labels(
                        list(message.get("scope_labels") or []), semantic_scope_labels
                    )
                rows.append(
                    {
                        "thread_key": entry.get("thread_key"),
                        "entry": entry,
                        "message": message,
                        "text": str(message.get("text") or ""),
                        "text_low": str(message.get("text") or "").casefold(),
                    }
                )
        except Exception:
            warning_count += 1
    return rows, warning_count


def dynamic_term_idf(corpus: list[dict[str, Any]], terms: list[str]) -> dict[str, float]:
    normalized = [term for term in unique_preserve([str(term) for term in terms]) if len(term) >= 3]
    total = max(1, len(corpus))
    out: dict[str, float] = {}
    for term in normalized:
        low = term.casefold()
        if not low:
            continue
        document_frequency = sum(1 for row in corpus if low in str(row.get("text_low") or ""))
        if document_frequency <= 0:
            continue
        out[low] = math.log((total + 1) / (document_frequency + 1)) + 1.0
    return out


def dynamic_source_score(text_low: str, terms: list[str], idf: dict[str, float]) -> float:
    score = 0.0
    for term in terms:
        low = str(term).casefold()
        if len(low) < 3 or low not in idf:
            continue
        count = text_low.count(low)
        if count <= 0:
            continue
        score += idf[low] * min(3, count)
    return score


def search_expected_evidence_registry(
    registry: dict[str, Any],
    case: dict[str, Any],
    *,
    top_k: int,
    max_hits_per_entry: int,
) -> dict[str, Any]:
    scored_hits: list[dict[str, Any]] = []
    warnings = 0
    terms = list(case.get("query_terms") or [])
    expected = case.get("expected") or {}
    labels = [str(label) for label in case.get("scope_labels") or []]
    for entry in registry.get("threads") or []:
        if not isinstance(entry, dict):
            continue
        metadata_score = entry_search_score(entry, terms)
        deep_result = deep_search_entry_result(entry, terms, max_hits=max_hits_per_entry)
        warnings += len(deep_result.get("warnings") or [])
        for hit in deep_result.get("hits") or []:
            if not isinstance(hit, dict) or not hit_scope_matches(hit, labels):
                continue
            score = (
                float(hit.get("rank_score") or hit.get("score") or 0.0)
                + float(metadata_score) * 0.02
            )
            scored_hits.append(
                {
                    "thread_key": entry.get("thread_key"),
                    "message_id": hit.get("message_id"),
                    "turn_id": hit.get("turn_id"),
                    "score": score,
                    "matched_expected": str(entry.get("thread_key") or "")
                    == str(expected.get("thread_key") or "")
                    and hit_matches_expected(hit, expected),
                }
            )
    scored_hits.sort(
        key=lambda item: (-float(item.get("score") or 0.0), str(item.get("thread_key") or ""))
    )
    for rank, hit in enumerate(scored_hits[: max(1, int(top_k))], start=1):
        if hit.get("matched_expected"):
            return {"passed": True, "rank": rank, "warning_count": warnings}
    return {"passed": False, "rank": None, "warning_count": warnings}


def candidate_space_diagnostics(
    scored_hits: list[dict[str, Any]],
    *,
    top_k: int,
) -> dict[str, Any]:
    """Summarize candidate visibility without exposing source identity.

    Candidate-space diagnostics are benchmark/debug evidence, not recall truth.
    Keep them to counts, ranks, and coarse decisions so private message ids,
    thread keys, snippets, paths, and source refs never leave the smoke report.
    """

    pool_limit = max(1, int(top_k))
    gold_raw_rank: int | None = None
    for rank, hit in enumerate(scored_hits, start=1):
        if hit.get("matched_expected"):
            gold_raw_rank = rank
            break
    gold_truncated_rank: int | None = None
    for rank, hit in enumerate(scored_hits[:pool_limit], start=1):
        if hit.get("matched_expected"):
            gold_truncated_rank = rank
            break
    gold_in_raw = gold_raw_rank is not None
    gold_in_truncated = gold_truncated_rank is not None
    if gold_in_truncated:
        gold_pruned_by = "none"
    elif gold_in_raw:
        gold_pruned_by = "top_k"
    else:
        gold_pruned_by = "unsupported"
    if not scored_hits:
        winner_support_level = "no_candidate"
    elif scored_hits[0].get("matched_expected"):
        winner_support_level = "expected_source"
    else:
        winner_support_level = "candidate_without_expected_source"
    verifier_seen_gold = gold_in_truncated
    return {
        "candidate_pool_size": len(scored_hits),
        "candidate_pool_limit": pool_limit,
        "gold_in_raw_candidate_pool": gold_in_raw,
        "gold_raw_rank": gold_raw_rank,
        "gold_in_truncated_candidate_pool": gold_in_truncated,
        "gold_truncated_rank": gold_truncated_rank,
        "gold_pruned_by": gold_pruned_by,
        "verifier_seen_gold": verifier_seen_gold,
        "verifier_decision_for_gold": "pending" if verifier_seen_gold else "not_seen",
        "winner_support_level": winner_support_level,
    }


def search_expected_evidence_dynamic_source(
    corpus: list[dict[str, Any]],
    case: dict[str, Any],
    *,
    top_k: int,
) -> dict[str, Any]:
    # `query_terms` intentionally mirrors the full fuzzy prompt. For this
    # diagnostic source-evidence ranking, prefer source-derived cue terms when
    # they are available so the stable prompt frame ("previous life-wide
    # fragment...") cannot dominate over the actual evidence discriminators.
    terms = list(case.get("source_terms") or case.get("query_terms") or [])
    labels = [str(label) for label in case.get("scope_labels") or []]
    expected = case.get("expected") or {}
    idf = dynamic_term_idf(corpus, terms)
    turn_scope_labels = turn_scope_label_index(corpus)
    scored_hits: list[dict[str, Any]] = []
    for row in corpus:
        message = dict_value(row.get("message"))
        # Clean-source can split one turn across multiple rows: a user row may
        # carry the scope label while the sibling assistant row carries the
        # source-derived query terms. Share scope only within the exact
        # thread+turn boundary; widening this to a thread-level fallback would
        # reintroduce unrelated private-context false positives.
        if not row_or_turn_scope_matches(row, labels, turn_scope_labels):
            continue
        base_score = score_message(message, terms)
        idf_score = dynamic_source_score(str(row.get("text_low") or ""), terms, idf)
        if base_score <= 0 and idf_score <= 0:
            continue
        entry = dict_value(row.get("entry"))
        score = float(base_score) + idf_score * 5.0 + entry_search_score(entry, terms) * 0.02
        scored_hits.append(
            {
                "thread_key": row.get("thread_key"),
                "message_id": message.get("message_id") or message.get("id"),
                "turn_id": message.get("turn_id"),
                "score": score,
                "source_line": message.get("source_line"),
                "matched_expected": str(row.get("thread_key") or "")
                == str(expected.get("thread_key") or "")
                and hit_matches_expected(
                    {
                        "message_id": message.get("message_id") or message.get("id"),
                        "turn_id": message.get("turn_id"),
                    },
                    expected,
                ),
            }
        )
    scored_hits.sort(
        key=lambda item: (
            -float(item.get("score") or 0.0),
            str(item.get("thread_key") or ""),
            int(item.get("source_line") or 0),
        )
    )
    candidate_space = candidate_space_diagnostics(scored_hits, top_k=top_k)
    for rank, hit in enumerate(scored_hits[: max(1, int(top_k))], start=1):
        if hit.get("matched_expected"):
            candidate_space["verifier_decision_for_gold"] = "accepted"
            return {
                "passed": True,
                "rank": rank,
                "warning_count": 0,
                "candidate_space": candidate_space,
            }
    if candidate_space["verifier_seen_gold"]:
        candidate_space["verifier_decision_for_gold"] = "rejected"
    return {
        "passed": False,
        "rank": None,
        "warning_count": 0,
        "candidate_space": candidate_space,
    }


def sanitized_case_result(case: dict[str, Any], search_result: dict[str, Any]) -> dict[str, Any]:
    out = {
        "case_id": case.get("case_id"),
        "prompt_kind": case.get("prompt_kind"),
        "scope_labels": case.get("scope_labels") or [],
        "expected_evidence": case.get("expected_evidence"),
        "passed": bool(search_result.get("passed")),
        "rank": search_result.get("rank"),
    }
    candidate_space = search_result.get("candidate_space")
    if isinstance(candidate_space, dict):
        out["candidate_space"] = candidate_space
    return out


def expected_rows_for_case(
    corpus: list[dict[str, Any]], case: dict[str, Any]
) -> list[dict[str, Any]]:
    expected = case.get("expected") or {}
    rows: list[dict[str, Any]] = []
    for row in corpus:
        message = dict_value(row.get("message"))
        if str(row.get("thread_key") or "") != str(expected.get("thread_key") or ""):
            continue
        if hit_matches_expected(
            {
                "message_id": message.get("message_id") or message.get("id"),
                "turn_id": message.get("turn_id"),
            },
            expected,
        ):
            rows.append(row)
    return rows


def query_overlap_count(row: dict[str, Any], query_terms: list[str]) -> int:
    text = str(row.get("text_low") or "")
    return sum(1 for term in query_terms if str(term).casefold() in text)


def classify_failure(
    *,
    expected_rows_found: int,
    scope_match_rows: int,
    query_overlap_rows: int,
    scope_and_query_overlap_rows: int,
    extended_rank: Any,
) -> str:
    if expected_rows_found == 0:
        return "expected_source_missing_from_corpus"
    if scope_match_rows and query_overlap_rows and not scope_and_query_overlap_rows:
        return "scope_term_split_across_expected_turn"
    if query_overlap_rows and not scope_match_rows:
        return "expected_match_missing_scope_labels"
    if scope_match_rows and not query_overlap_rows:
        return "selected_prompt_terms_not_on_expected_source"
    if scope_and_query_overlap_rows:
        return "rank_below_top_k" if extended_rank else "candidate_scored_but_too_low"
    return "no_retrievable_signal_on_expected_source"


def candidate_failure_class(
    category: str,
    candidate_space: dict[str, Any],
    *,
    result_passed: bool,
) -> str:
    if result_passed:
        return "success"
    if category == "expected_source_missing_from_corpus":
        return "source_reopen_failed"
    if not candidate_space.get("gold_in_raw_candidate_pool"):
        return "candidate_not_generated"
    if not candidate_space.get("gold_in_truncated_candidate_pool"):
        return "candidate_pruned_before_verifier"
    if candidate_space.get("verifier_seen_gold"):
        # This smoke runner's verifier is source-ref visibility/expected-ref
        # matching, not answer generation. A failed result with visible gold
        # means the diagnostic layer should treat the miss as verifier-side
        # source-evidence rejection, without claiming anything about final
        # answer quality.
        return "candidate_seen_rejected_wrongly"
    return "wrong_candidate_accepted"


def source_evidence_failure_diagnostics(
    *,
    cases: list[dict[str, Any]],
    results: list[tuple[dict[str, Any], dict[str, Any]]],
    corpus: list[dict[str, Any]],
    top_k: int,
    ranking: str,
    extended_top_k: int = 20,
) -> dict[str, Any]:
    """Return sanitized failure categories for selected source-evidence misses.

    The diagnostics intentionally count shape and ranking facts only. They do
    not include query text, snippets, message ids, thread keys, local paths, or
    raw source refs, because this smoke often runs over private real history.
    """

    failed = [
        (case, result)
        for case, result in results
        if not bool(result.get("passed"))
    ]
    categories = {
        "expected_source_missing_from_corpus": 0,
        "scope_term_split_across_expected_turn": 0,
        "expected_match_missing_scope_labels": 0,
        "selected_prompt_terms_not_on_expected_source": 0,
        "rank_below_top_k": 0,
        "candidate_scored_but_too_low": 0,
        "no_retrievable_signal_on_expected_source": 0,
        "not_diagnosed_for_ranking": 0,
    }
    failure_classes = {
        "candidate_not_generated": 0,
        "candidate_pruned_before_verifier": 0,
        "candidate_seen_rejected_correctly": 0,
        "candidate_seen_rejected_wrongly": 0,
        "wrong_candidate_accepted": 0,
        "source_reopen_failed": 0,
        "success": 0,
        "unsupported": 0,
    }
    failed_cases: list[dict[str, Any]] = []
    if ranking != "dynamic_source" or not corpus:
        categories["not_diagnosed_for_ranking"] = len(failed)
        failure_classes["unsupported"] = len(failed)
        return {
            "failed_count": len(failed),
            "top_k": int(top_k),
            "extended_top_k": int(extended_top_k),
            "categories": categories,
            "failure_classes": failure_classes,
            "failed_cases": [
                {
                    "case_id": case.get("case_id"),
                    "category": "not_diagnosed_for_ranking",
                    "failure_class": "unsupported",
                }
                for case, _ in failed
            ],
        }

    for case, result in failed:
        query_terms = [str(term) for term in case.get("query_terms") or []]
        labels = [str(label) for label in case.get("scope_labels") or []]
        expected_rows = expected_rows_for_case(corpus, case)
        row_stats = []
        for row in expected_rows:
            message = dict_value(row.get("message"))
            overlap = query_overlap_count(row, query_terms)
            row_stats.append(
                {
                    "scope_match": hit_scope_matches(message, labels),
                    "query_overlap_count": overlap,
                }
            )
        scope_match_rows = sum(1 for item in row_stats if item["scope_match"])
        query_overlap_rows = sum(1 for item in row_stats if item["query_overlap_count"] > 0)
        scope_and_query_overlap_rows = sum(
            1
            for item in row_stats
            if item["scope_match"] and item["query_overlap_count"] > 0
        )
        extended = search_expected_evidence_dynamic_source(
            corpus,
            case,
            top_k=max(int(top_k), int(extended_top_k)),
        )
        top_k_result = (
            result
            if isinstance(result.get("candidate_space"), dict)
            else search_expected_evidence_dynamic_source(corpus, case, top_k=int(top_k))
        )
        candidate_space = dict_value(top_k_result.get("candidate_space"))
        extended_rank = extended.get("rank")
        category = classify_failure(
            expected_rows_found=len(expected_rows),
            scope_match_rows=scope_match_rows,
            query_overlap_rows=query_overlap_rows,
            scope_and_query_overlap_rows=scope_and_query_overlap_rows,
            extended_rank=extended_rank,
        )
        categories[category] = categories.get(category, 0) + 1
        failure_class = candidate_failure_class(
            category,
            candidate_space,
            result_passed=bool(result.get("passed")),
        )
        if (
            failure_class == "candidate_not_generated"
            and category == "expected_match_missing_scope_labels"
        ):
            candidate_space["gold_pruned_by"] = "source_filter"
        failure_classes[failure_class] = failure_classes.get(failure_class, 0) + 1
        if failure_class == "candidate_seen_rejected_wrongly":
            candidate_space["verifier_decision_for_gold"] = "rejected"
        failed_cases.append(
            {
                "case_id": case.get("case_id"),
                "category": category,
                "failure_class": failure_class,
                "rank": result.get("rank"),
                "extended_rank": extended_rank,
                "candidate_space": candidate_space,
                "expected_rows_found": len(expected_rows),
                "expected_scope_match_rows": scope_match_rows,
                "expected_query_overlap_rows": query_overlap_rows,
                "expected_scope_and_query_overlap_rows": scope_and_query_overlap_rows,
                "expected_max_query_overlap": max(
                    [item["query_overlap_count"] for item in row_stats],
                    default=0,
                ),
            }
        )
    return {
        "failed_count": len(failed),
        "top_k": int(top_k),
        "extended_top_k": int(extended_top_k),
        "categories": categories,
        "failure_classes": failure_classes,
        "failed_cases": failed_cases,
    }


def eval_status(case_count: int, passed_count: int, *, min_cases: int, min_hit_rate: float) -> str:
    if case_count < min_cases:
        return "insufficient_selected_cases"
    hit_rate = (passed_count / case_count) if case_count else 0.0
    if hit_rate < min_hit_rate:
        return "insufficient_recall_hits"
    return "sufficient"


def cannot_claim(
    status: str,
    *,
    require_semantic_sidecar: bool = True,
    sample_gate_ok: bool | None = None,
    quality_gate_ok: bool | None = None,
) -> list[str]:
    claims = [
        "global_recall_quality",
        "semantic_completeness",
        "clean_source_truth_without_opening_evidence",
    ]
    if status != "sufficient" or not require_semantic_sidecar:
        claims.append("selected_semantic_source_evidence")
    if sample_gate_ok is False or not require_semantic_sidecar:
        claims.append("semantic_sidecar_sample_coverage")
    if quality_gate_ok is False:
        claims.append("selected_semantic_source_evidence_quality")
    if not require_semantic_sidecar:
        claims.append("deterministic_label_fallback_is_not_semantic_sidecar_evidence")
    return claims


def selection_explanation(
    *,
    require_semantic_sidecar: bool,
    case_count: int,
    min_cases: int,
    status: str,
) -> dict[str, Any]:
    sample_gap = max(0, int(min_cases) - int(case_count))
    if require_semantic_sidecar:
        next_action = (
            "Semantic sidecar-selected sample is large enough; read quality diagnostics next."
            if sample_gap == 0
            else (
                "Build or refresh semantic scope sidecars for more clean-source turns, or rerun "
                "with --allow-deterministic-labels only as a wiring baseline."
            )
        )
        return {
            "mode": "semantic_sidecar_required",
            "selected_case_count": int(case_count),
            "min_cases": int(min_cases),
            "sample_gap": sample_gap,
            "status": status,
            "selector": (
                "Selects non-technical life-wide turns only when the turn already has "
                "dynamic semantic_scope_labels from the semantic sidecar."
            ),
            "fallback_flag": "--allow-deterministic-labels",
            "fallback_meaning": (
                "The fallback widens selection to deterministic clean-source labels and "
                "topic terms; it checks recall/search wiring, not semantic-sidecar coverage."
            ),
            "claim_boundary": (
                "A sufficient result supports this selected semantic-sidecar slice only; "
                "it is not global recall quality or semantic completeness."
            ),
            "next_action": next_action,
        }
    return {
        "mode": "deterministic_label_fallback",
        "selected_case_count": int(case_count),
        "min_cases": int(min_cases),
        "sample_gap": sample_gap,
        "status": status,
        "selector": (
            "Selects the same non-technical life-wide clean-source surface without requiring "
            "dynamic semantic_scope_labels."
        ),
        "fallback_flag": "--allow-deterministic-labels",
        "fallback_meaning": (
            "This mode is useful when a machine has too few semantic sidecar rows, but a pass "
            "only proves deterministic label/search wiring."
        ),
        "claim_boundary": (
            "Do not claim selected semantic-sidecar source-evidence coverage from fallback "
            "results, even when hit-rate and sample gates pass."
        ),
        "next_action": (
            "Run again without --allow-deterministic-labels before making semantic-sidecar "
            "coverage claims."
        ),
    }


def run_source_evidence_recall_eval(
    *,
    registry_path: str | Path | None = None,
    max_cases: int = 12,
    min_cases: int = 3,
    top_k: int = 5,
    max_hits_per_entry: int = 5,
    min_hit_rate: float = 0.8,
    max_turns_per_thread: int = 5000,
    max_per_life_label: int = 5000,
    require_semantic_sidecar: bool = True,
    max_term_frequency: int = 8,
    ranking: str = "dynamic_source",
) -> dict[str, Any]:
    registry_file = (
        Path(registry_path).resolve()
        if registry_path
        else (aippocampus_registry_dir() / "threads.json").resolve()
    )
    registry = load_registry(registry_file)
    timeline = build_project_timeline(
        registry_file,
        max_turns_per_thread=max_turns_per_thread,
        max_per_life_label=max_per_life_label,
    )
    cases = select_eval_cases(
        timeline,
        max_cases=max_cases,
        require_semantic_sidecar=require_semantic_sidecar,
        max_term_frequency=max_term_frequency,
    )
    if ranking == "registry":
        corpus_warning_count = 0
        corpus: list[dict[str, Any]] = []
        results = [
            (
                case,
                search_expected_evidence_registry(
                    registry, case, top_k=top_k, max_hits_per_entry=max_hits_per_entry
                ),
            )
            for case in cases
        ]
    elif ranking == "dynamic_source":
        corpus, corpus_warning_count = clean_source_corpus(
            registry,
            registry_path=registry_file,
        )
        results = [
            (case, search_expected_evidence_dynamic_source(corpus, case, top_k=top_k))
            for case in cases
        ]
    else:
        raise ValueError("ranking must be 'dynamic_source' or 'registry'")
    passed_count = sum(1 for _, result in results if result.get("passed"))
    status = eval_status(len(cases), passed_count, min_cases=min_cases, min_hit_rate=min_hit_rate)
    labels = sorted({label for case in cases for label in case.get("scope_labels") or []})
    warning_count = corpus_warning_count + sum(
        int(result.get("warning_count") or 0) for _, result in results
    )
    hit_rate = round((passed_count / len(cases)) if cases else 0.0, 4)
    rate_estimates = {
        "top_k_hit_rate": binomial_rate_report(
            "top_k_hit_rate",
            numerator=passed_count,
            denominator=len(cases),
            threshold=min_hit_rate,
        )
    }
    sample_gate_ok = len(cases) >= min_cases
    quality_gate_ok = bool(cases) and hit_rate >= min_hit_rate
    selection_note = selection_explanation(
        require_semantic_sidecar=require_semantic_sidecar,
        case_count=len(cases),
        min_cases=min_cases,
        status=status,
    )
    return {
        "ok": status == "sufficient",
        "status": status,
        "claim_level": "selected_source_evidence_recall_eval"
        if status == "sufficient"
        else "diagnostic_only",
        "cannot_claim": cannot_claim(
            status,
            require_semantic_sidecar=require_semantic_sidecar,
            sample_gate_ok=sample_gate_ok,
            quality_gate_ok=quality_gate_ok,
        ),
        "prompt_kind": PROMPT_KIND,
        "case_count": len(cases),
        "passed_count": passed_count,
        "failed_count": max(0, len(cases) - passed_count),
        "top_k": max(1, int(top_k)),
        "top_k_hit_rate": hit_rate,
        "rate_estimates": rate_estimates,
        "min_cases": int(min_cases),
        "min_hit_rate": float(min_hit_rate),
        "sample_gate_ok": sample_gate_ok,
        "quality_gate_ok": quality_gate_ok,
        "gate_diagnostics": {
            "sample_gate_ok": sample_gate_ok,
            "quality_gate_ok": quality_gate_ok,
            "sample_status": "sufficient"
            if sample_gate_ok
            else "insufficient_selected_cases",
            "quality_status": "sufficient" if quality_gate_ok else "insufficient_recall_hits",
            "sample_gap": max(0, int(min_cases) - len(cases)),
            "selected_cases": len(cases),
            "min_cases": int(min_cases),
            "top_k_hit_rate": hit_rate,
            "min_hit_rate": float(min_hit_rate),
            "rate_estimates": rate_estimates,
        },
        "label_coverage": labels,
        "warning_count": warning_count,
        "ranking": ranking,
        "cases": [sanitized_case_result(case, result) for case, result in results],
        "failure_diagnostics": source_evidence_failure_diagnostics(
            cases=cases,
            results=results,
            corpus=corpus,
            top_k=top_k,
            ranking=ranking,
        ),
        "privacy_boundary": {
            "raw_text_emitted": False,
            "snippets_emitted": False,
            "titles_emitted": False,
            "source_reference_details_emitted": False,
            "absolute_paths_emitted": False,
            "case_ids_are_hashed": True,
            "output_shape": "sanitized_eval_aggregates",
        },
        "selection": {
            "mode": selection_note["mode"],
            "require_semantic_sidecar": bool(require_semantic_sidecar),
            "deterministic_label_fallback": not bool(require_semantic_sidecar),
            "max_cases": int(max_cases),
            "max_term_frequency": int(max_term_frequency),
            "max_turns_per_thread": int(max_turns_per_thread),
            "max_per_life_label": int(max_per_life_label),
            "boundary": (
                "Prompts and dynamic_source ranking use source-derived cue terms and corpus rarity; "
                "this is not a lexical-rule expansion path."
            ),
        },
        "selection_explanation": selection_note,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry")
    parser.add_argument("--max-cases", type=int, default=12)
    parser.add_argument("--min-cases", type=int, default=3)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--max-hits-per-entry", type=int, default=5)
    parser.add_argument("--min-hit-rate", type=float, default=0.8)
    parser.add_argument("--max-turns-per-thread", type=int, default=5000)
    parser.add_argument("--max-per-life-label", type=int, default=5000)
    parser.add_argument("--max-term-frequency", type=int, default=8)
    parser.add_argument(
        "--ranking", choices=["dynamic_source", "registry"], default="dynamic_source"
    )
    parser.add_argument(
        "--allow-deterministic-labels",
        action="store_true",
        help=(
            "Use deterministic clean-source labels as a wiring baseline when semantic-sidecar "
            "sample coverage is too small; this cannot claim semantic-sidecar coverage."
        ),
    )
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args()

    result = run_source_evidence_recall_eval(
        registry_path=args.registry,
        max_cases=args.max_cases,
        min_cases=args.min_cases,
        top_k=args.top_k,
        max_hits_per_entry=args.max_hits_per_entry,
        min_hit_rate=args.min_hit_rate,
        max_turns_per_thread=args.max_turns_per_thread,
        max_per_life_label=args.max_per_life_label,
        require_semantic_sidecar=not args.allow_deterministic_labels,
        max_term_frequency=args.max_term_frequency,
        ranking=args.ranking,
    )
    if args.json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"source-evidence recall eval: {result.get('status')}")
        print(
            f"cases: {result.get('case_count')} passed: {result.get('passed_count')} hit_rate: {result.get('top_k_hit_rate')}"
        )
        explanation = dict_value(result.get("selection_explanation"))
        if explanation:
            print(
                f"selection: {explanation.get('mode')} "
                f"selected={explanation.get('selected_case_count')} min={explanation.get('min_cases')}"
            )
            print(f"next: {explanation.get('next_action')}")
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
