#!/usr/bin/env python3
"""Local-only prompt-hook hot-path candidate funnel.

This module is deliberately narrow: it may produce route hints and stage
diagnostics, but it must not produce source-backed evidence. Evidence still
requires the existing source reopen/probe paths in the foreground decision
pipeline. Keep this dependency-free and reuse the existing SQLite trigram index
instead of adding another foreground search surface.
"""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any

from aippocampus_runtime.artifacts.publish import resolve_sqlite_index_path
from aippocampus_runtime.recall import prompt_cues
from aippocampus_runtime.recall.living_cue_cache import select_living_cue_packet
from aippocampus_runtime.recall.prompt_recall_core import candidate_summary, sort_candidates
from aippocampus_runtime.recall.retrieval import search_hybrid_index
from aippocampus_runtime.registry.api import unique_preserve
from aippocampus_runtime.warm_ambient.query_pattern_routes import select_query_pattern_packet

MAX_STAGE_CANDIDATES = 3


def candidate_indexes_from_registry(registry: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for entry in registry.get("threads") or []:
        if not isinstance(entry, dict):
            continue
        rows.append(
            {
                "thread_key": entry.get("thread_key"),
                "paths": entry.get("paths") or {},
                "workspace": entry.get("workspace_name") or entry.get("workspace"),
                "source_refs": [{"thread_key": entry.get("thread_key"), "line": None}],
                "thread_profile": {
                    "terms": unique_preserve(
                        [
                            str(entry.get("title") or ""),
                            str(entry.get("workspace_name") or ""),
                            str(entry.get("summary") or ""),
                            *[str(value) for value in entry.get("keywords") or []],
                            *[str(value) for value in entry.get("anchor_titles") or []],
                        ],
                        limit=16,
                    ),
                    "representative_message_ids": entry.get("representative_message_ids")
                    or [],
                },
            }
        )
    return rows


def merge_hot_path_candidates(
    candidates: list[dict[str, Any]],
    registry: dict[str, Any],
    hot_path: dict[str, Any],
    query_terms: list[str],
    *,
    scent_threshold: float,
) -> list[dict[str, Any]]:
    if hot_path.get("decision") != "scent":
        return candidates
    by_thread = {entry.get("thread_key"): entry for entry in registry.get("threads") or []}
    by_key = {item.get("thread_key"): item for item in candidates}
    candidate_reasons = hot_path.get("candidate_reasons") if isinstance(hot_path, dict) else {}
    reason_by_thread = candidate_reasons if isinstance(candidate_reasons, dict) else {}
    for thread_key in hot_path.get("candidate_ids") or []:
        entry = by_thread.get(thread_key)
        if not entry:
            continue
        hot_path_reason = str(reason_by_thread.get(thread_key) or "").strip()
        existing = by_key.get(thread_key)
        if existing:
            existing["score"] = round(
                max(float(existing.get("score") or 0.0), scent_threshold), 3
            )
            existing["hot_path_source"] = True
            if hot_path_reason:
                existing["hot_path_reason"] = hot_path_reason
            continue
        item = candidate_summary(entry, scent_threshold, query_terms)
        item["hot_path_source"] = True
        if hot_path_reason:
            item["hot_path_reason"] = hot_path_reason
        item["matched_terms"] = unique_preserve(
            list(item.get("matched_terms") or []) + query_terms,
            limit=8,
        )
        candidates.append(item)
        by_key[thread_key] = item
    return sort_candidates(candidates)


def _elapsed_ms(start: float) -> float:
    return round((time.perf_counter() - start) * 1000, 2)


def _stage(
    *,
    stage: str,
    status: str,
    candidate_count: int = 0,
    fallback_reason: str = "",
    start: float,
) -> dict[str, Any]:
    return {
        "stage": stage,
        "status": status,
        "candidate_count": max(0, int(candidate_count)),
        "fallback_reason": fallback_reason,
        "elapsed_ms": _elapsed_ms(start),
    }


def _terms_overlap(prompt: str, terms: list[str]) -> bool:
    low = prompt.casefold()
    for term in terms:
        value = str(term or "").strip()
        if len(value) < 2:
            continue
        if value.casefold() in low or low in value.casefold():
            return True
    return False


def _continuation_prompt(prompt: str) -> bool:
    low = prompt.casefold().strip()
    cues = (
        "continue",
        "resume",
        "pick up",
        "where we left",
        "继续",
        "接着",
        "上次",
        "刚才",
        "之前",
        "那个",
    )
    return any(cue in low for cue in cues)


def _candidate_id(candidate: dict[str, Any]) -> str:
    return str(candidate.get("thread_key") or candidate.get("id") or "").strip()


def _candidate_ref(candidate: dict[str, Any]) -> dict[str, Any]:
    refs = [ref for ref in candidate.get("source_refs") or [] if isinstance(ref, dict)]
    if refs:
        ref = refs[0]
        return {
            "thread_key": str(ref.get("thread_key") or _candidate_id(candidate)),
            "line": ref.get("line") or ref.get("source_line"),
        }
    return {"thread_key": _candidate_id(candidate)}


def _hit_rows(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for candidate in candidates:
        cid = _candidate_id(candidate)
        if not cid or cid in seen:
            continue
        seen.add(cid)
        rows.append(candidate)
        if len(rows) >= MAX_STAGE_CANDIDATES:
            break
    return rows


def _thread_profile_candidates(
    *,
    prompt: str,
    candidate_indexes: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not _continuation_prompt(prompt):
        return []
    hits: list[dict[str, Any]] = []
    for candidate in candidate_indexes:
        profile = candidate.get("thread_profile") if isinstance(candidate, dict) else {}
        if not isinstance(profile, dict):
            continue
        message_ids = [item for item in profile.get("representative_message_ids") or []]
        if message_ids or profile.get("current_thread"):
            item = dict(candidate)
            item["hot_path_reason"] = "thread_profile"
            hits.append(item)
    return _hit_rows(hits)


def _cue_cache_candidates(
    *,
    prompt: str,
    query_terms: list[str],
    candidate_indexes: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], str]:
    prompt_terms = unique_preserve([prompt, *query_terms], limit=16)
    hits: list[dict[str, Any]] = []
    stale = False
    for candidate in candidate_indexes:
        cache = candidate.get("cue_cache") if isinstance(candidate, dict) else {}
        if not isinstance(cache, dict):
            continue
        aliases = [str(alias) for alias in cache.get("query_aliases") or []]
        if not aliases or not any(_terms_overlap(term, aliases) for term in prompt_terms):
            continue
        item = dict(candidate)
        item["hot_path_reason"] = "cue_cache"
        if str(cache.get("state") or "").casefold() == "stale":
            stale = True
            item["hot_path_navigation_only"] = True
        hits.append(item)
    return _hit_rows(hits), "stale_navigation_only" if stale else ""


def _living_cue_candidates(
    *,
    prompt: str,
    entries: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any], str]:
    packet = select_living_cue_packet(prompt, entries)
    if packet.get("decision") != "scent":
        raw_diagnostics = packet.get("diagnostics")
        diagnostics = raw_diagnostics if isinstance(raw_diagnostics, dict) else {}
        if diagnostics.get("cache_hit_count"):
            return [], packet, "living_cue_suppressed"
        return [], packet, "no_living_cue_match"

    hits: list[dict[str, Any]] = []
    for ref in packet.get("candidate_refs") or []:
        if not isinstance(ref, dict):
            continue
        thread_key = str(ref.get("thread_key") or "").strip()
        if not thread_key:
            continue
        hits.append(
            {
                "thread_key": thread_key,
                "source_refs": [ref],
                "hot_path_reason": "living_cue_cache",
                "hot_path_navigation_only": True,
            }
        )
    return _hit_rows(hits), packet, "" if hits else "living_cue_missing_thread_ref"


def _query_pattern_route_candidates(
    *,
    prompt: str,
    routes: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any], str]:
    packet = select_query_pattern_packet(prompt, routes)
    if packet.get("decision") != "scent":
        raw_diagnostics = packet.get("diagnostics")
        diagnostics = raw_diagnostics if isinstance(raw_diagnostics, dict) else {}
        if diagnostics.get("cache_hit_count"):
            return [], packet, "query_pattern_routes_suppressed"
        return [], packet, "no_query_pattern_route_match"

    hits: list[dict[str, Any]] = []
    for ref in packet.get("candidate_refs") or []:
        if not isinstance(ref, dict):
            continue
        thread_key = str(ref.get("thread_key") or "").strip()
        if not thread_key:
            continue
        hits.append(
            {
                "thread_key": thread_key,
                "source_refs": [ref],
                "hot_path_reason": "query_pattern_routes",
                "hot_path_navigation_only": True,
            }
        )
    return _hit_rows(hits), packet, "" if hits else "query_pattern_route_missing_thread_ref"


def _index_path(candidate: dict[str, Any]) -> Path | None:
    candidate_paths = candidate.get("paths")
    raw_paths: dict[str, Any] = candidate_paths if isinstance(candidate_paths, dict) else {}
    values = [
        candidate.get("index_path"),
        raw_paths.get("source_index_sqlite"),
        raw_paths.get("sqlite"),
        raw_paths.get("index_sqlite"),
    ]
    index_dir = raw_paths.get("index_dir")
    if index_dir:
        values.append(Path(index_dir) / "source_index.sqlite")
    workspace = raw_paths.get("workspace") or candidate.get("workspace")
    if workspace:
        values.append(Path(workspace) / ".aippocampus" / "source_index.sqlite")
    for value in values:
        if not value:
            continue
        path = Path(value)
        try:
            resolved = resolve_sqlite_index_path(path)
        except Exception:
            resolved = path
        if resolved.exists():
            return resolved
    return None


def _fts_route_intent(prompt: str) -> bool:
    """Return whether bounded FTS may wake a navigation scent.

    Trigram FTS is deliberately a hot-path fallback, not a general source
    search. Without an explicit recall/continuation/semantic-context cue, a
    plain implementation prompt that shares an entity name with old history can
    look like useful overlap and create noisy ambient memory. Keep that false
    positive out of the foreground hook; deeper source search remains available
    through explicit active recall / MCP paths.
    """

    text = str(prompt or "").strip()
    if not text:
        return False
    if (
        prompt_cues.explicit_recall_terms(text)
        or prompt_cues.natural_evidence_intent(text)
        or prompt_cues.source_evidence_intent(text)
        or prompt_cues.semantic_trigger_context_intent(text)
        or _prior_context_route_intent(text)
        or prompt_cues.matched_terms(
            text,
            prompt_cues.ASSOCIATIVE_CUES | prompt_cues.IMPORTANCE_CUES,
        )
    ):
        return True
    return False


def _prior_context_route_intent(prompt: str) -> bool:
    if not any(pattern.search(prompt) for pattern in prompt_cues.PRIOR_HISTORY_MARKER_PATTERNS):
        return False
    return bool(
        re.search(
            r"[?？吗]|(继续|接着|找|查|回忆|想起|remember|recall|continue|resume)",
            prompt,
            flags=re.IGNORECASE,
        )
    )


def _fts_candidates(
    *,
    prompt: str,
    query_terms: list[str],
    candidate_indexes: list[dict[str, Any]],
    candidate_cap: int,
) -> list[dict[str, Any]]:
    if not query_terms or not _fts_route_intent(prompt):
        return []
    hits: list[dict[str, Any]] = []
    for candidate in candidate_indexes[: max(1, candidate_cap)]:
        index = _index_path(candidate)
        if not index:
            continue
        rows = search_hybrid_index(
            index,
            query_terms,
            unique_preserve(query_terms, limit=12),
            [],
            limit=2,
            candidate_limit=24,
            snippet_chars=180,
            context_radius=0,
            use_rag_chunks=True,
        )
        if not rows:
            continue
        item = dict(candidate)
        item["hot_path_reason"] = "bounded_trigram_fts"
        item["hot_path_hit_count"] = len(rows)
        item["hot_path_top_score"] = max(float(row.get("score") or 0.0) for row in rows)
        hits.append(item)
    return _hit_rows(hits)


def run_hot_path_funnel(
    *,
    prompt: str,
    query_terms: list[str],
    candidate_indexes: list[dict[str, Any]],
    living_cue_entries: list[dict[str, Any]] | None = None,
    query_pattern_routes: list[dict[str, Any]] | None = None,
    candidate_cap: int = 8,
) -> dict[str, Any]:
    """Return local route candidates plus stage diagnostics.

    The result intentionally carries `evidence=[]`: local profiles, cue caches,
    and trigram hits are route material. They can make a prompt-hook decision
    emit scent, but source-backed evidence remains owned by `collect_evidence`.
    """

    overall_start = time.perf_counter()
    stages: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []
    living_cue_packet: dict[str, Any] | None = None
    query_pattern_packet: dict[str, Any] | None = None

    stage_start = time.perf_counter()
    candidates = _thread_profile_candidates(prompt=prompt, candidate_indexes=candidate_indexes)
    stages.append(
        _stage(
            stage="thread_profile",
            status="hit" if candidates else "skip",
            candidate_count=len(candidates),
            fallback_reason="" if candidates else "no_thread_profile_match",
            start=stage_start,
        )
    )

    stage_start = time.perf_counter()
    if candidates:
        stages.append(
            _stage(
                stage="living_cue_cache",
                status="skip",
                candidate_count=0,
                fallback_reason="already_hit",
                start=stage_start,
            )
        )
    else:
        candidates, living_cue_packet, living_reason = _living_cue_candidates(
            prompt=prompt,
            entries=living_cue_entries or [],
        )
        stages.append(
            _stage(
                stage="living_cue_cache",
                status="hit" if candidates else "skip",
                candidate_count=len(candidates),
                fallback_reason=living_reason or ("" if candidates else "no_living_cue_match"),
                start=stage_start,
            )
        )

    stage_start = time.perf_counter()
    if candidates:
        stages.append(
            _stage(
                stage="query_pattern_routes",
                status="skip",
                candidate_count=0,
                fallback_reason="already_hit",
                start=stage_start,
            )
        )
    else:
        candidates, query_pattern_packet, query_pattern_reason = _query_pattern_route_candidates(
            prompt=prompt,
            routes=query_pattern_routes or [],
        )
        stages.append(
            _stage(
                stage="query_pattern_routes",
                status="hit" if candidates else "skip",
                candidate_count=len(candidates),
                fallback_reason=query_pattern_reason
                or ("" if candidates else "no_query_pattern_route_match"),
                start=stage_start,
            )
        )

    stage_start = time.perf_counter()
    if candidates:
        stages.append(
            _stage(
                stage="cue_cache",
                status="skip",
                candidate_count=0,
                fallback_reason="already_hit",
                start=stage_start,
            )
        )
    else:
        candidates, cache_reason = _cue_cache_candidates(
            prompt=prompt,
            query_terms=query_terms,
            candidate_indexes=candidate_indexes,
        )
        stages.append(
            _stage(
                stage="cue_cache",
                status="hit" if candidates else "skip",
                candidate_count=len(candidates),
                fallback_reason=cache_reason or ("" if candidates else "no_cue_cache_match"),
                start=stage_start,
            )
        )

    stage_start = time.perf_counter()
    if candidates:
        stages.append(
            _stage(
                stage="bounded_trigram_fts",
                status="skip",
                candidate_count=0,
                fallback_reason="already_hit",
                start=stage_start,
            )
        )
    else:
        candidates = _fts_candidates(
            prompt=prompt,
            query_terms=query_terms,
            candidate_indexes=candidate_indexes,
            candidate_cap=candidate_cap,
        )
        stages.append(
            _stage(
                stage="bounded_trigram_fts",
                status="hit" if candidates else "skip",
                candidate_count=len(candidates),
                fallback_reason=(
                    ""
                    if candidates
                    else "no_fts_match"
                    if _fts_route_intent(prompt)
                    else "prompt_lacks_memory_route_intent"
                ),
                start=stage_start,
            )
        )

    if not candidates:
        stage_start = time.perf_counter()
        stages.append(
            _stage(
                stage="no_op",
                status="skip",
                candidate_count=0,
                fallback_reason="no_local_candidate",
                start=stage_start,
            )
        )

    candidate_ids = [_candidate_id(candidate) for candidate in candidates if _candidate_id(candidate)]
    candidate_reasons = {
        _candidate_id(candidate): str(candidate.get("hot_path_reason") or "")
        for candidate in candidates
        if _candidate_id(candidate) and candidate.get("hot_path_reason")
    }
    return {
        "decision": "scent" if candidate_ids else "skip",
        "candidate_count": len(candidate_ids),
        "candidate_ids": candidate_ids,
        "candidate_reasons": candidate_reasons,
        "candidate_refs": [_candidate_ref(candidate) for candidate in candidates],
        "stages": stages,
        "evidence": [],
        "living_cue_cache": living_cue_packet,
        "query_pattern_routes": query_pattern_packet,
        "source_reopen_promotion_count": 0,
        "local_only": True,
        "elapsed_ms": _elapsed_ms(overall_start),
    }
