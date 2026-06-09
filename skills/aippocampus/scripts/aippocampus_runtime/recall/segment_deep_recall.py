"""Explicit bounded multi-hop helpers for segmented recall."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any, Sequence

from aippocampus_runtime.recall.query_policy import split_query_terms, unique_preserve


def now_seconds() -> float:
    return time.monotonic()


def elapsed_ms(started_at: float) -> int:
    return max(0, int((time.monotonic() - started_at) * 1000))


def source_keys(results: Sequence[dict], source_key_fn: Callable[[dict], str]) -> list[str]:
    return unique_preserve(
        [key for item in results if (key := source_key_fn(item))],
    )


def disabled_diagnostics() -> dict[str, Any]:
    return {
        "enabled": False,
        "mode": "single_pass",
        "completed_hops": 0,
        "stop_reason": "not_requested",
        "hops": [],
        "skipped_expansions": [],
        "source_boundary": "single-pass segmented recall; source claims still require source reopen or bounded evidence",
    }


def initial_diagnostics(*, max_hops: int, candidate_budget: int | None) -> dict[str, Any]:
    return {
        "enabled": True,
        "mode": "explicit_deep_recall",
        "max_hops": max(0, int(max_hops)),
        "candidate_budget": candidate_budget,
        "completed_hops": 0,
        "stop_reason": "",
        "hops": [],
        "skipped_expansions": [],
        "source_boundary": (
            "explicit deep recall reruns bounded lexical search from source-joined "
            "anchors; generated expansion terms are navigation only"
        ),
    }


def unavailable_diagnostics(options: Any) -> dict[str, Any]:
    if not getattr(options, "deep", False):
        return disabled_diagnostics()
    diagnostics = initial_diagnostics(
        max_hops=getattr(options, "deep_max_hops", 1),
        candidate_budget=getattr(options, "deep_candidate_budget", None),
    )
    diagnostics["stop_reason"] = "segments_unavailable"
    return diagnostics


def hop_diagnostic(
    *,
    hop: int,
    query_terms: Sequence[str],
    results: Sequence[dict],
    source_key_fn: Callable[[dict], str],
    previous_source_keys: set[str],
) -> dict[str, Any]:
    keys = source_keys(results, source_key_fn)
    added = [key for key in keys if key not in previous_source_keys]
    return {
        "hop": hop,
        "query_terms": list(query_terms),
        "result_count": len(results),
        "source_keys": keys,
        "source_key_count": len(keys),
        "added_source_keys": added,
        "added_source_key_count": len(added),
    }


def extraction_terms(
    *,
    original_terms: Sequence[str],
    previous_terms: Sequence[str],
    results: Sequence[dict],
    source_key_fn: Callable[[dict], str],
    limit: int,
) -> list[str]:
    """Extract bounded navigation terms from source-joined hit snippets.

    The expansion source is deliberately narrow: already source-joined results.
    These terms can route another search pass, but they are not aliases or
    factual claims until a caller reopens source or receives bounded evidence.
    """

    blocked = {str(term).casefold() for term in original_terms}
    blocked.update(str(term).casefold() for term in previous_terms)
    candidates: list[str] = []
    for item in results:
        if not source_key_fn(item):
            continue
        snippet = str(item.get("snippet") or "")
        context = " ".join(str(ctx.get("snippet") or "") for ctx in item.get("context") or [])
        for term in split_query_terms([snippet, context]):
            normalized = term.casefold()
            if not normalized or normalized in blocked:
                continue
            candidates.append(normalized)
    return unique_preserve(candidates, limit=max(0, int(limit)))


def _stop_before_expansion(
    diagnostics: dict[str, Any],
    *,
    reason: str,
    next_hop: int,
    **fields: Any,
) -> None:
    diagnostics["stop_reason"] = reason
    entry = {"hop": next_hop, "reason": reason}
    entry.update(fields)
    diagnostics["skipped_expansions"].append(entry)


def _empty_deep_pass(diagnostics: dict[str, Any]) -> dict[str, Any]:
    return {
        "diagnostics": diagnostics,
        "raw_results": [],
        "segment_errors": [],
        "rag_context": [],
        "searched_segment_count": 0,
        "missing_index_count": 0,
    }


def run_explicit_deep_recall(
    *,
    options: Any,
    query_terms: list[str],
    planned_segments: list[tuple[int, dict]],
    boundary_contexts: dict[str, dict],
    temporal_cue: dict[str, Any] | None,
    initial_results: list[dict],
    initial_source_keys: list[str],
    started_at: float,
    search_pass: Callable[..., dict[str, Any]],
    source_key_fn: Callable[[dict], str],
) -> dict[str, Any]:
    diagnostics = initial_diagnostics(
        max_hops=options.deep_max_hops,
        candidate_budget=options.deep_candidate_budget,
    )
    seen_source_keys = set(initial_source_keys)
    diagnostics["hops"].append(
        hop_diagnostic(
            hop=0,
            query_terms=query_terms,
            results=initial_results,
            source_key_fn=source_key_fn,
            previous_source_keys=set(),
        )
    )
    max_hops = max(0, int(options.deep_max_hops))
    if max_hops <= 0:
        diagnostics["stop_reason"] = "max_hops"
        return _empty_deep_pass(diagnostics)

    candidate_budget = options.deep_candidate_budget
    if candidate_budget is not None and len(seen_source_keys) >= max(0, int(candidate_budget)):
        _stop_before_expansion(
            diagnostics,
            reason="candidate_budget",
            next_hop=1,
            source_key_count=len(seen_source_keys),
            budget=max(0, int(candidate_budget)),
        )
        return _empty_deep_pass(diagnostics)

    elapsed_budget = options.deep_elapsed_budget_ms
    if elapsed_budget is not None and elapsed_ms(started_at) >= max(0, int(elapsed_budget)):
        _stop_before_expansion(
            diagnostics,
            reason="elapsed_budget",
            next_hop=1,
            elapsed_ms=elapsed_ms(started_at),
            budget_ms=max(0, int(elapsed_budget)),
        )
        return _empty_deep_pass(diagnostics)

    all_raw_results: list[dict] = []
    all_segment_errors: list[dict] = []
    all_rag_context: list[dict] = []
    searched_segment_count = 0
    missing_index_count = 0
    current_results = initial_results
    previous_terms = list(query_terms)
    for hop in range(1, max_hops + 1):
        deep_terms = extraction_terms(
            original_terms=query_terms,
            previous_terms=previous_terms,
            results=current_results,
            source_key_fn=source_key_fn,
            limit=options.deep_terms_per_hop,
        )
        if not deep_terms:
            _stop_before_expansion(
                diagnostics,
                reason="no_expansion_terms",
                next_hop=hop,
            )
            break
        pass_payload = search_pass(
            options=options,
            patterns=deep_terms,
            query_terms=deep_terms,
            expanded_terms=deep_terms,
            anchors=[],
            planned_segments=planned_segments,
            boundary_contexts=boundary_contexts,
            temporal_cue=temporal_cue,
            recall_hop=hop,
            include_rag_context=False,
        )
        hop_results = pass_payload["raw_results"]
        all_raw_results.extend(hop_results)
        all_segment_errors.extend(pass_payload["segment_errors"])
        all_rag_context.extend(pass_payload["rag_context"])
        searched_segment_count += int(pass_payload["searched_segment_count"])
        missing_index_count += int(pass_payload["missing_index_count"])
        hop_entry = hop_diagnostic(
            hop=hop,
            query_terms=deep_terms,
            results=hop_results,
            source_key_fn=source_key_fn,
            previous_source_keys=seen_source_keys,
        )
        diagnostics["hops"].append(hop_entry)
        diagnostics["completed_hops"] = hop
        added_source_keys = list(hop_entry["added_source_keys"])
        if not added_source_keys:
            diagnostics["stop_reason"] = "no_new_source_keys"
            break
        seen_source_keys.update(added_source_keys)
        current_results = hop_results
        previous_terms.extend(deep_terms)
        if hop >= max_hops:
            diagnostics["stop_reason"] = "max_hops"
            break
        if candidate_budget is not None and len(seen_source_keys) >= max(0, int(candidate_budget)):
            _stop_before_expansion(
                diagnostics,
                reason="candidate_budget",
                next_hop=hop + 1,
                source_key_count=len(seen_source_keys),
                budget=max(0, int(candidate_budget)),
            )
            break
        if elapsed_budget is not None and elapsed_ms(started_at) >= max(0, int(elapsed_budget)):
            _stop_before_expansion(
                diagnostics,
                reason="elapsed_budget",
                next_hop=hop + 1,
                elapsed_ms=elapsed_ms(started_at),
                budget_ms=max(0, int(elapsed_budget)),
            )
            break
    if not diagnostics["stop_reason"]:
        diagnostics["stop_reason"] = "completed"
    return {
        "diagnostics": diagnostics,
        "raw_results": all_raw_results,
        "segment_errors": all_segment_errors,
        "rag_context": all_rag_context,
        "searched_segment_count": searched_segment_count,
        "missing_index_count": missing_index_count,
    }
