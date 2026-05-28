#!/usr/bin/env python3
"""Source-evidence collection and hook-safe output helpers."""

from __future__ import annotations

from typing import Any

from prompt_cues import evidence_content_terms
from registry import deep_search_entry, unique_preserve


def collect_evidence(
    candidates: list[dict[str, Any]], query_terms: list[str], budget: int
) -> list[dict[str, Any]]:
    limit = max(0, budget)
    content_terms = evidence_content_terms(query_terms)
    pool: list[tuple[float, int, dict[str, Any]]] = []
    for candidate in candidates[:3]:
        if limit <= 0:
            break
        entry = candidate.get("_entry") or {}
        _, hits = deep_search_entry(entry, query_terms, max_hits=max(limit * 4, 4))
        for hit_index, hit in enumerate(hits):
            if not hit.get("line") or not hit.get("snippet"):
                continue
            snippet_low = str(hit.get("snippet") or "").casefold()
            hit_score = float(hit.get("score") or 0.0)
            clean_source_high_confidence = hit.get("source") == "clean_source" and hit_score >= 50
            if (
                content_terms
                and not clean_source_high_confidence
                and not any(term.casefold() in snippet_low for term in content_terms)
            ):
                continue
            item = {
                "thread_key": candidate.get("thread_key"),
                "title": candidate.get("title"),
                "line": hit.get("line"),
                "role": hit.get("role"),
                "phase": hit.get("phase") or "",
                "turn_index": hit.get("turn_index"),
                "score": hit.get("score"),
                "rank_score": hit.get("rank_score"),
                "source": hit.get("source"),
                "is_final": hit.get("is_final"),
                "search_noise": hit.get("search_noise"),
                "noise_reason": hit.get("noise_reason"),
                "snippet": hit.get("snippet"),
            }
            pool.append((_evidence_hit_quality(item), hit_index, item))

    if not pool:
        return []
    has_non_process_hit = any(not _evidence_hit_is_process_noise(item) for _, _, item in pool)
    selected: list[dict[str, Any]] = []
    seen: set[tuple[str, Any]] = set()
    for _, _, item in sorted(pool, key=lambda row: (-row[0], row[1])):
        if has_non_process_hit and _evidence_hit_is_process_noise(item):
            continue
        key = (str(item.get("thread_key") or ""), item.get("line"))
        if key in seen:
            continue
        seen.add(key)
        selected.append({key: value for key, value in item.items() if value not in {None, ""}})
        if len(selected) >= limit:
            break
    return selected


def _evidence_hit_is_process_noise(hit: dict[str, Any]) -> bool:
    snippet = str(hit.get("snippet") or "").lstrip().casefold()
    if hit.get("search_noise"):
        return True
    return snippet.startswith("<subagent_notification>") or snippet.startswith("<tool")


def _evidence_hit_quality(hit: dict[str, Any]) -> float:
    score = float(hit.get("rank_score") or hit.get("score") or 0.0)
    if hit.get("source") == "clean_source":
        score += 20.0
    if hit.get("phase") == "final_answer" or hit.get("is_final"):
        score += 80.0
    elif hit.get("role") == "user":
        score += 35.0
    if _evidence_hit_is_process_noise(hit):
        score -= 1000.0
    return score


def strip_private_fields(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in candidates:
        copy = dict(item)
        copy.pop("_entry", None)
        copy.pop("probe_line", None)
        copy.pop("probe_phase", None)
        copy.pop("source_refs", None)
        out.append(copy)
    return out


def strip_semantic_gate(result: dict[str, Any] | None) -> dict[str, Any] | None:
    if not result:
        return None
    workers = []
    for worker in result.get("workers") or []:
        workers.append(
            {
                "worker": worker.get("worker"),
                "decision": worker.get("decision"),
                "confidence": worker.get("confidence"),
                "query_aliases": unique_preserve(
                    [str(value) for value in worker.get("query_aliases") or []], limit=8
                ),
                "memory_scope": worker.get("memory_scope") or [],
                "anti_personalization_risk": worker.get("anti_personalization_risk"),
                "reason": worker.get("reason"),
            }
        )
    return {
        "available": bool(result.get("available")),
        "decision": result.get("decision"),
        "confidence": result.get("confidence"),
        "intent": result.get("intent"),
        "query_aliases": unique_preserve(
            [str(value) for value in result.get("query_aliases") or []], limit=12
        ),
        "memory_scope": result.get("memory_scope") or [],
        "negative_contexts": result.get("negative_contexts") or [],
        "anti_personalization_risk": result.get("anti_personalization_risk"),
        "reasons": result.get("reasons") or [],
        "cached": bool(result.get("cached")),
        "elapsed_ms": result.get("elapsed_ms"),
        "usage": result.get("usage") or {},
        "cache": result.get("cache") or {},
        "workers": workers,
        "errors": result.get("errors") or [],
    }
