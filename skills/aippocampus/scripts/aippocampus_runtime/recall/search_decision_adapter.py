#!/usr/bin/env python3
"""Local source-backed search-decision adapter.

The adapter helps an agent decide how old memory should influence external
search. It is deliberately not a search engine and not a web authority ranker:
it only routes before search, proposes source-ref-backed query expansion during
search, and classifies search-result residue after search. Browser/search
trails stay private until an explicit import or review path turns them into
source-backed material.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from typing import Any

from aippocampus_runtime.recall.query_policy import (
    normalize_term,
    split_query_terms,
    unique_preserve,
)

SCHEMA_VERSION = 1
SUPPORT_LEVELS = {"skip", "scent", "candidate", "evidence"}
AFTER_SEARCH_CLASSES = {"extension", "correction", "replacement", "disposable_residue"}
MAX_SOURCE_REFS = 3
MAX_QUERY_TERMS = 12

DEGRADED_CUE_MARKERS = (
    "之前",
    "上次",
    "前面",
    "刚才",
    "那个",
    "这个",
    "旧上下文",
    "旧 context",
    "继续",
    "接到",
    "remember",
    "previous",
    "earlier",
)

# These words are too broad to justify steering an external search by memory on
# their own. Keep this local to the adapter so query_policy remains a general
# retrieval helper instead of absorbing search-decision policy.
GENERIC_OVERLAP_TERMS = {
    "about",
    "browser",
    "chrome",
    "external",
    "help",
    "local",
    "memory",
    "permission",
    "permissions",
    "search",
    "source",
    "web",
    "怎么",
    "一下",
    "本地",
    "搜索",
}

BENCHMARK_LINKS = {
    "H1_pattern_completion": "degraded cue -> source-backed candidate refs or abstention",
    "H2_pattern_separation": "similar-looking prompts must not collapse into unrelated old context",
    "H5_consolidation_handoff": "after-search outcomes are review/import handoff, not automatic truth",
}

BASE_SOURCE_BOUNDARY = {
    "local_first": True,
    "does_not_replace_external_search_or_web_authority_ranking": True,
    "browser_or_search_trail_stays_private_by_default": True,
    "external_result_is_not_memory_truth": True,
}


def _clean_text(value: Any, *, chars: int = 160) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text[:chars]


def _safe_term(value: Any) -> str:
    term = normalize_term(str(value or ""))
    if not term or len(term) > 120:
        return ""
    if re.search(r"[A-Za-z]:\\|/(Users|home|tmp|var)/", term):
        return ""
    return term


def _list_strings(value: Any) -> list[str]:
    if isinstance(value, str):
        term = _safe_term(value)
        return [term] if term else []
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        term = _safe_term(item)
        if term:
            out.append(term)
    return out


def _confidence_bucket(value: Any) -> str:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        text = str(value or "").strip()
        return text if text in {"low", "medium", "high"} else "low"
    if numeric >= 0.8:
        return "high"
    if numeric >= 0.55:
        return "medium"
    return "low"


def _clean_source_ref(ref: dict[str, Any]) -> dict[str, Any]:
    allowed = (
        "source_id",
        "stable_source_id",
        "thread_key",
        "message_id",
        "turn_id",
        "turn_index",
        "source_line",
        "line",
        "phase",
    )
    clean: dict[str, Any] = {}
    for key in allowed:
        value = ref.get(key)
        if value in {None, ""}:
            continue
        out_key = "line" if key == "source_line" else key
        if out_key == "stable_source_id":
            out_key = "source_id"
        clean[out_key] = value
    return clean


def _source_refs(candidate: dict[str, Any]) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    seen: set[tuple[tuple[str, str], ...]] = set()
    raw_refs = candidate.get("source_refs") or []
    if not isinstance(raw_refs, list):
        return refs
    for raw in raw_refs:
        if not isinstance(raw, dict):
            continue
        ref = _clean_source_ref(raw)
        if not ref:
            continue
        key = tuple(sorted((str(k), str(v)) for k, v in ref.items()))
        if key in seen:
            continue
        seen.add(key)
        refs.append(ref)
        if len(refs) >= MAX_SOURCE_REFS:
            break
    return refs


def _candidate_terms(candidate: dict[str, Any]) -> list[str]:
    fields: list[str] = []
    fields.extend(_list_strings(candidate.get("title")))
    fields.extend(_list_strings(candidate.get("matched_terms")))
    fields.extend(_list_strings(candidate.get("query_aliases") or candidate.get("aliases")))
    fields.extend(_list_strings(candidate.get("keywords")))
    fields.extend(_list_strings(candidate.get("summary")))
    return unique_preserve(split_query_terms(fields), limit=48)


def _query_expansion_terms(candidate: dict[str, Any]) -> list[str]:
    fields: list[str] = []
    fields.extend(_list_strings(candidate.get("query_aliases") or candidate.get("aliases")))
    fields.extend(_list_strings(candidate.get("matched_terms")))
    fields.extend(_list_strings(candidate.get("title")))
    return unique_preserve(fields, limit=MAX_QUERY_TERMS)


def _is_specific_term(term: str) -> bool:
    low = term.casefold().strip()
    if not low or low in GENERIC_OVERLAP_TERMS:
        return False
    if re.search(r"[\u4e00-\u9fff]", term):
        return len(term) >= 2
    return len(low) >= 4


def _term_matches(left: str, right: str) -> bool:
    a = left.casefold().strip()
    b = right.casefold().strip()
    if not a or not b:
        return False
    if a == b:
        return True
    return (len(a) >= 5 and a in b) or (len(b) >= 5 and b in a)


def _matched_terms(prompt_terms: list[str], candidate_terms: list[str]) -> list[str]:
    matches: list[str] = []
    for prompt_term in prompt_terms:
        if not _is_specific_term(prompt_term):
            continue
        for candidate_term in candidate_terms:
            if not _is_specific_term(candidate_term):
                continue
            if _term_matches(prompt_term, candidate_term):
                matches.append(prompt_term if len(prompt_term) <= len(candidate_term) else candidate_term)
                break
    return unique_preserve(matches, limit=8)


def _has_degraded_cue(prompt: str) -> bool:
    low = prompt.casefold()
    return any(marker.casefold() in low for marker in DEGRADED_CUE_MARKERS)


def _support_from_candidate(candidate: dict[str, Any], *, default: str) -> str:
    support = str(candidate.get("support_level") or "").strip()
    if support == "evidence" and candidate.get("source_reopened"):
        return "evidence"
    if support in SUPPORT_LEVELS and support != "evidence":
        return support
    return default


def _candidate_projection(candidate: dict[str, Any], matched_terms: list[str]) -> dict[str, Any]:
    refs = _source_refs(candidate)
    return {
        "title": _clean_text(candidate.get("title"), chars=120),
        "support_level": _support_from_candidate(candidate, default="candidate"),
        "confidence": _confidence_bucket(candidate.get("confidence")),
        "matched_terms": matched_terms,
        "source_refs": refs,
        "source_ref_count": len(refs),
        "query_terms": _query_expansion_terms(candidate) if refs else [],
    }


def assess_before_search(prompt: str, source_candidates: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Decide whether memory should steer an external search query."""

    prompt_terms = split_query_terms([prompt])
    degraded_cue = _has_degraded_cue(prompt)
    best: dict[str, Any] | None = None
    best_matches: list[str] = []

    for candidate in source_candidates or []:
        if not isinstance(candidate, dict) or not _source_refs(candidate):
            continue
        matches = _matched_terms(prompt_terms, _candidate_terms(candidate))
        if len(matches) > len(best_matches):
            best = candidate
            best_matches = matches

    if not best or not best_matches:
        return {
            "kind": "aippocampus_search_decision_adapter",
            "schema_version": SCHEMA_VERSION,
            "phase": "before_search",
            "search_decision": "new_query",
            "support_level": "skip",
            "confidence": "low",
            "route_reason": "insufficient_source_backed_overlap",
            "matched_terms": [],
            "candidate_refs": [],
            "query_terms": [],
            "benchmark_links": dict(BENCHMARK_LINKS),
            "source_boundary": {
                **BASE_SOURCE_BOUNDARY,
                "abstained_instead_of_personalizing_search": True,
                "source_refs_are_ids_only": True,
            },
        }

    enough_for_candidate = len(best_matches) >= 2 or (degraded_cue and len(best_matches) >= 1)
    projection = _candidate_projection(best, best_matches)
    if enough_for_candidate:
        search_decision = "degraded_cue_into_old_source" if degraded_cue else "old_context_may_clarify_query"
        support_level = _support_from_candidate(best, default="candidate")
        route_reason = (
            "degraded_cue_has_source_backed_query_alias"
            if degraded_cue
            else "source_backed_overlap_can_clarify_query"
        )
    else:
        search_decision = "weak_scent_stay_quiet"
        support_level = "scent"
        route_reason = "weak_source_backed_overlap"

    return {
        "kind": "aippocampus_search_decision_adapter",
        "schema_version": SCHEMA_VERSION,
        "phase": "before_search",
        "search_decision": search_decision,
        "support_level": support_level,
        "confidence": projection["confidence"],
        "route_reason": route_reason,
        "matched_terms": projection["matched_terms"],
        "candidate_refs": projection["source_refs"],
        "query_terms": projection["query_terms"] if support_level in {"candidate", "evidence"} else [],
        "benchmark_links": dict(BENCHMARK_LINKS),
        "source_boundary": {
            **BASE_SOURCE_BOUNDARY,
            "abstained_instead_of_personalizing_search": False,
            "source_refs_are_ids_only": True,
            "source_backed_claims_require_reopen": True,
            "query_terms_are_navigation_not_facts": True,
        },
    }


def query_expansion_packet(before_search_decision: dict[str, Any]) -> dict[str, Any]:
    """Build a source-ref-backed query expansion packet for external search."""

    support_level = str(before_search_decision.get("support_level") or "skip")
    query_terms = list(before_search_decision.get("query_terms") or [])
    refs = list(before_search_decision.get("candidate_refs") or [])
    can_expand = support_level in {"candidate", "evidence"} and bool(query_terms) and bool(refs)
    return {
        "kind": "aippocampus_search_query_expansion_packet",
        "schema_version": SCHEMA_VERSION,
        "phase": "during_search",
        "support_level": support_level if can_expand else "skip",
        "query_terms": _clean_query_terms(query_terms) if can_expand else [],
        "candidate_refs": refs[:MAX_SOURCE_REFS] if can_expand else [],
        "route_reason": before_search_decision.get("route_reason") or "",
        "benchmark_links": dict(BENCHMARK_LINKS),
        "source_boundary": {
            **BASE_SOURCE_BOUNDARY,
            "source_refs_are_ids_only": True,
            "expansion_terms_are_navigation_not_facts": True,
            "source_reopen_required_for_memory_claim": True,
            "abstained_instead_of_personalizing_search": not can_expand,
        },
    }


def _clean_query_terms(query_terms: list[Any]) -> list[str]:
    terms: list[str] = []
    for term in query_terms:
        clean = _safe_term(term)
        if clean:
            terms.append(clean)
    return unique_preserve(terms, limit=MAX_QUERY_TERMS)


def classify_after_search(search_result: dict[str, Any] | None, before_search_decision: dict[str, Any]) -> dict[str, Any]:
    """Classify what an external result should become after search."""

    result = search_result if isinstance(search_result, dict) else {}
    hint = str(result.get("relationship_hint") or result.get("classification") or "").strip()
    classification = hint if hint in AFTER_SEARCH_CLASSES else "disposable_residue"
    next_action = (
        "do_not_store_by_default"
        if classification == "disposable_residue"
        else "requires_explicit_import_or_review"
    )
    return {
        "kind": "aippocampus_search_result_memory_classification",
        "schema_version": SCHEMA_VERSION,
        "phase": "after_search",
        "classification": classification,
        "support_level": "candidate" if classification != "disposable_residue" else "scent",
        "prior_search_decision": before_search_decision.get("search_decision") or "unknown",
        "long_term_truth_by_default": False,
        "next_memory_action": next_action,
        "allowed_classes": sorted(AFTER_SEARCH_CLASSES),
        "benchmark_links": dict(BENCHMARK_LINKS),
        "source_boundary": {
            **BASE_SOURCE_BOUNDARY,
            "external_result_requires_import_provenance": True,
            "classification_is_not_source_claim": True,
        },
    }


def build_adapter_envelope(
    *,
    prompt: str,
    source_candidates: list[dict[str, Any]] | None = None,
    search_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    before = assess_before_search(prompt, source_candidates)
    during = query_expansion_packet(before)
    after = classify_after_search(search_result or {}, before) if search_result is not None else None
    payload: dict[str, Any] = {
        "kind": "aippocampus_search_decision_adapter",
        "schema_version": SCHEMA_VERSION,
        "before_search": before,
        "during_search": during,
        "benchmark_links": dict(BENCHMARK_LINKS),
        "source_boundary": {
            **BASE_SOURCE_BOUNDARY,
            "adapter_does_not_call_external_search": True,
            "clean_source_or_explicit_import_required_for_facts": True,
        },
    }
    if after is not None:
        payload["after_search"] = after
    return payload


def _json_arg(value: str, *, default: Any) -> Any:
    if not value:
        return default
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"invalid JSON argument: {exc}") from exc
    return parsed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prototype local search-decision memory adapter.")
    parser.add_argument("--prompt", default="", help="Current user prompt or search intent.")
    parser.add_argument(
        "--candidates-json",
        default="[]",
        help="JSON list of source-backed candidate rows with source_refs and query_aliases.",
    )
    parser.add_argument(
        "--result-json",
        default="",
        help="Optional JSON object for after-search classification.",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON envelope.")
    args = parser.parse_args(argv)

    candidates = _json_arg(args.candidates_json, default=[])
    if not isinstance(candidates, list):
        raise SystemExit("--candidates-json must be a JSON list")
    result = _json_arg(args.result_json, default=None) if args.result_json else None
    if result is not None and not isinstance(result, dict):
        raise SystemExit("--result-json must be a JSON object")

    payload = build_adapter_envelope(prompt=args.prompt, source_candidates=candidates, search_result=result)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
