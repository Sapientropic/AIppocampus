#!/usr/bin/env python3
"""Recall scoring, candidate selection, and foreground-gate policy.

This module is imported by `prompt_recall_decision.py`. Keep Codex hook
stdin/stdout glue in `aippocampus_prompt_hook.py` so the foreground hook
entrypoint stays small and auditable.
"""

from __future__ import annotations

import json
import math
import os
import sys
from pathlib import Path
from typing import Any

import prompt_cues
from registry import deep_search_entry, entry_search_score, registry_paths, unique_preserve
from retrieval import CONCEPT_TRIGGERS

# Keep these assignments as compatibility re-exports for older installed hooks.
# First-party code should import cue policy directly from `prompt_cues.py`; this
# list marks the compatibility surface so it can be removed deliberately after
# the installer/runtime migration window, not by casual cleanup.
CUE_COMPAT_EXPORTS = (
    "ASSOCIATIVE_CUES",
    "CODE_SURFACE_CUES",
    "CONCEPT_EXPANSION_MAX_TERMS",
    "DECISION_CONTINUATION_CUES",
    "EXPLICIT_RECALL_TERMS",
    "IMPORTANCE_CUES",
    "RECENCY_CUES",
    "SEMANTIC_EVIDENCE_TERMS",
    "SEMANTIC_GATE_ALIAS_DECISIONS",
    "SEMANTIC_GATE_CUE_DECISIONS",
    "WEAK_DEICTIC_TERMS",
    "association_term_is_generic",
    "concept_expansion_terms",
    "evidence_content_terms",
    "expand_query_terms",
    "explicit_recall_terms",
    "is_decision_continuation",
    "matched_life_wide_cue_terms",
    "matched_life_wide_timeline_cues",
    "matched_terms",
    "memory_boundary_context_intent",
    "natural_evidence_intent",
    "negative_evidence_intent",
    "prompt_is_code_surface",
    "prompt_is_secret_surface",
    "semantic_gate_can_request_evidence",
    "semantic_gate_is_memory_cue",
    "semantic_gate_terms",
    "should_run_semantic_gate",
    "source_evidence_intent",
    "working_memory_terms",
)
ASSOCIATIVE_CUES = prompt_cues.ASSOCIATIVE_CUES
CODE_SURFACE_CUES = prompt_cues.CODE_SURFACE_CUES
CONCEPT_EXPANSION_MAX_TERMS = prompt_cues.CONCEPT_EXPANSION_MAX_TERMS
DECISION_CONTINUATION_CUES = prompt_cues.DECISION_CONTINUATION_CUES
EXPLICIT_RECALL_TERMS = prompt_cues.EXPLICIT_RECALL_TERMS
IMPORTANCE_CUES = prompt_cues.IMPORTANCE_CUES
RECENCY_CUES = prompt_cues.RECENCY_CUES
SEMANTIC_EVIDENCE_TERMS = prompt_cues.SEMANTIC_EVIDENCE_TERMS
SEMANTIC_GATE_ALIAS_DECISIONS = prompt_cues.SEMANTIC_GATE_ALIAS_DECISIONS
SEMANTIC_GATE_CUE_DECISIONS = prompt_cues.SEMANTIC_GATE_CUE_DECISIONS
WEAK_DEICTIC_TERMS = prompt_cues.WEAK_DEICTIC_TERMS
association_term_is_generic = prompt_cues.association_term_is_generic
concept_expansion_terms = prompt_cues.concept_expansion_terms
evidence_content_terms = prompt_cues.evidence_content_terms
expand_query_terms = prompt_cues.expand_query_terms
explicit_recall_terms = prompt_cues.explicit_recall_terms
is_decision_continuation = prompt_cues.is_decision_continuation
matched_life_wide_cue_terms = prompt_cues.matched_life_wide_cue_terms
matched_life_wide_timeline_cues = prompt_cues.matched_life_wide_timeline_cues
matched_terms = prompt_cues.matched_terms
memory_boundary_context_intent = prompt_cues.memory_boundary_context_intent
natural_evidence_intent = prompt_cues.natural_evidence_intent
negative_evidence_intent = prompt_cues.negative_evidence_intent
prompt_is_code_surface = prompt_cues.prompt_is_code_surface
prompt_is_secret_surface = prompt_cues.prompt_is_secret_surface
semantic_gate_can_request_evidence = prompt_cues.semantic_gate_can_request_evidence
semantic_gate_is_memory_cue = prompt_cues.semantic_gate_is_memory_cue
semantic_gate_terms = prompt_cues.semantic_gate_terms
should_run_semantic_gate = prompt_cues.should_run_semantic_gate
source_evidence_intent = prompt_cues.source_evidence_intent
working_memory_terms = prompt_cues.working_memory_terms

PROMPT_HOOK_SEMANTIC_TIMEOUT = int(os.environ.get("AIPPOCAMPUS_PROMPT_SEMANTIC_TIMEOUT", "12"))
SCENT_THRESHOLD = 5.0
EVIDENCE_THRESHOLD = 10.0
DEFAULT_SEARCH_BUDGET = 3
MAX_CONTEXT_CHARS = 1800
# Probe reranking opens source indexes for candidate threads, so the foreground
# hook keeps this bounded. Deep, source-backed recall can still use explicit
# search commands outside the UserPromptSubmit timeout.
SCENT_PROBE_LIMIT = int(os.environ.get("AIPPOCAMPUS_PROMPT_PROBE_LIMIT", "8"))
SCENT_PROBE_SCORE_MULTIPLIER = 2.4
SCENT_PROBE_SCORE_CAP = 32.0
EVIDENCE_LITE_MIN_PROBE_SCORE = 6.0
LIFE_WIDE_TIMELINE_CANDIDATE_LIMIT = 3


def hook_input_from_stdin() -> dict[str, Any]:
    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    return json.loads(raw)


def registry_json_path(registry_path: Path | None = None, registry_dir: Path | None = None) -> Path:
    if registry_path:
        return registry_path
    json_path, _ = registry_paths(registry_dir)
    return json_path


def candidate_summary(
    entry: dict[str, Any], score: float, query_terms: list[str]
) -> dict[str, Any]:
    blob = "\n".join(
        [
            entry.get("title") or "",
            entry.get("workspace_name") or "",
            entry.get("summary") or "",
            " ".join(entry.get("anchor_titles") or []),
            " ".join(entry.get("keywords") or []),
        ]
    ).casefold()
    matched = [term for term in query_terms if term.casefold() in blob]
    return {
        "thread_key": entry.get("thread_key"),
        "title": entry.get("title") or entry.get("workspace_name") or entry.get("thread_key"),
        "timestamp": (entry.get("session_meta") or {}).get("timestamp")
        or entry.get("created_at")
        or entry.get("updated_at"),
        "project_label": entry.get("project_label") or entry.get("workspace_name"),
        "score": round(score, 3),
        "matched_terms": unique_preserve(matched, limit=8),
        "anchors": unique_preserve(entry.get("anchor_titles") or [], limit=3),
        "keywords": unique_preserve(entry.get("keywords") or [], limit=8),
        "_entry": entry,
    }


def sort_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates.sort(
        key=lambda item: (
            float(item.get("score") or 0.0),
            str(item.get("timestamp") or ""),
            str(item.get("title") or ""),
        ),
        reverse=True,
    )
    return candidates


def fuzzy_entry_score(entry: dict[str, Any], query_terms: list[str]) -> float:
    clues = unique_preserve(
        list(entry.get("keywords") or [])
        + list(entry.get("anchor_titles") or [])
        + [entry.get("title") or "", entry.get("summary") or ""],
        limit=80,
    )
    score = 0.0
    for term in query_terms:
        low = term.casefold().strip()
        if len(low) < 4:
            continue
        for clue in clues:
            clue_low = str(clue).casefold().strip()
            if len(clue_low) < 4:
                continue
            if low in clue_low or clue_low in low:
                score += 3.0
                break
    return min(score, 9.0)


def score_candidates(
    prompt: str, registry: dict[str, Any], query_terms: list[str]
) -> list[dict[str, Any]]:
    explicit = explicit_recall_terms(prompt)
    associative = matched_terms(prompt, set(CONCEPT_TRIGGERS) | ASSOCIATIVE_CUES)
    important = matched_terms(prompt, IMPORTANCE_CUES)

    candidates: list[dict[str, Any]] = []
    for entry in registry.get("threads") or []:
        base = entry_search_score(entry, query_terms) + fuzzy_entry_score(entry, query_terms)
        if base <= 0:
            continue
        score = base
        if explicit:
            score += 4.0
        if associative:
            score += min(4.0, len(associative) * 1.5)
        if important:
            score += 2.5
        candidates.append(candidate_summary(entry, score, query_terms))
    return sort_candidates(candidates)


def association_document_frequency(match: dict[str, Any], total_threads: int) -> int:
    thread_count = len(
        {
            source.get("thread_key")
            for source in match.get("threads") or []
            if source.get("thread_key")
        }
    )
    hit_count = int(match.get("hit_count") or 0)
    if total_threads <= 0:
        return max(1, thread_count or hit_count or 1)
    return max(1, min(total_threads, max(thread_count, hit_count, 1)))


def association_boost(match: dict[str, Any], total_threads: int) -> float:
    confidence = float(match.get("confidence") or 0.0)
    df = association_document_frequency(match, total_threads)
    n = max(total_threads, df, 1)
    idf = math.log((n + 1.0) / (df + 1.0)) + 1.0
    status_bonus = 1.25 if match.get("status") == "verified" else 1.0
    # A matched association is enough to produce a scent, but broad terms such
    # as a project name should not drown out rare source terms. IDF keeps the
    # gate open while moving ranking authority toward more specific memories.
    return round(SCENT_THRESHOLD + min(8.0, confidence * idf * status_bonus * 2.5), 3)


def merge_association_candidates(
    candidates: list[dict[str, Any]],
    registry: dict[str, Any],
    association_matches: list[dict[str, Any]],
    query_terms: list[str],
) -> list[dict[str, Any]]:
    if not association_matches:
        return candidates
    by_thread = {entry.get("thread_key"): entry for entry in registry.get("threads") or []}
    by_key = {item.get("thread_key"): item for item in candidates}
    total_threads = len(by_thread)
    for match in association_matches:
        boost = association_boost(match, total_threads)
        seen_for_match: set[str] = set()
        for source in match.get("threads") or []:
            thread_key = source.get("thread_key")
            if not thread_key or thread_key in seen_for_match:
                continue
            seen_for_match.add(thread_key)
            entry = by_thread.get(thread_key)
            if not entry:
                continue
            existing = by_key.get(thread_key)
            if existing:
                existing["score"] = round(float(existing.get("score") or 0.0) + boost, 3)
                existing["matched_terms"] = unique_preserve(
                    list(existing.get("matched_terms") or [])
                    + list(match.get("matched_terms") or [])
                    + [match.get("term") or ""],
                    limit=8,
                )
                continue
            item = candidate_summary(entry, boost, query_terms)
            item["matched_terms"] = unique_preserve(
                list(item.get("matched_terms") or [])
                + list(match.get("matched_terms") or [])
                + [match.get("term") or ""],
                limit=8,
            )
            item["association_source"] = True
            candidates.append(item)
            by_key[thread_key] = item
    return sort_candidates(candidates)


def default_project_timeline_path(registry_path: Path) -> Path:
    return registry_path.resolve().parent / "project_timeline.json"


def load_project_timeline(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def project_matches_prompt(project: dict[str, Any], prompt: str, cwd: Path) -> bool:
    low = prompt.casefold()
    labels = unique_preserve(
        [
            project.get("project_label") or "",
            project.get("project_key") or "",
            *list(project.get("project_tags") or []),
        ],
        limit=24,
    )
    if any(label and label.casefold() in low for label in labels):
        return True
    cwd_low = str(cwd).casefold()
    return any(label and label.casefold() in cwd_low for label in labels)


def merge_life_wide_timeline_candidates(
    candidates: list[dict[str, Any]],
    registry: dict[str, Any],
    timeline: dict[str, Any],
    prompt: str,
    query_terms: list[str],
) -> list[dict[str, Any]]:
    labels, cue_terms = matched_life_wide_timeline_cues(prompt)
    if not labels:
        return candidates
    life_wide = timeline.get("life_wide") or {}
    label_groups = life_wide.get("labels") or {}
    if not isinstance(label_groups, dict):
        return candidates

    by_thread = {entry.get("thread_key"): entry for entry in registry.get("threads") or []}
    by_key = {item.get("thread_key"): item for item in candidates}
    added_threads: set[str] = set()
    recency_terms = matched_terms(prompt, RECENCY_CUES)
    for label in labels:
        group = label_groups.get(label) or {}
        if not isinstance(group, dict):
            continue
        for turn in group.get("latest_turns") or []:
            if not isinstance(turn, dict):
                continue
            thread_key = turn.get("thread_key")
            if not thread_key:
                continue
            entry = by_thread.get(thread_key)
            if not entry:
                continue
            scope_labels = [
                str(value) for value in turn.get("scope_labels") or [] if isinstance(value, str)
            ]
            source_refs = [ref for ref in turn.get("source_refs") or [] if isinstance(ref, dict)]
            source_ref_count = len(source_refs)
            matched = unique_preserve(
                recency_terms
                + cue_terms
                + [label]
                + [str(value) for value in (turn.get("topic_terms") or [])[:3]],
                limit=8,
            )
            boost = SCENT_THRESHOLD + 4.0
            existing = by_key.get(thread_key)
            if existing:
                existing["score"] = round(float(existing.get("score") or 0.0) + boost, 3)
                existing["matched_terms"] = unique_preserve(
                    list(existing.get("matched_terms") or []) + matched, limit=8
                )
                existing["timeline_source"] = True
                existing["life_wide_timeline_source"] = True
                existing["scope_labels"] = unique_preserve(
                    list(existing.get("scope_labels") or []) + scope_labels, limit=8
                )
                if source_ref_count:
                    existing["source_ref_count"] = max(
                        int(existing.get("source_ref_count") or 0), source_ref_count
                    )
                if source_refs and not existing.get("source_refs"):
                    existing["source_refs"] = source_refs[:3]
                if turn.get("turn_id") and not existing.get("timeline_turn_id"):
                    existing["timeline_turn_id"] = turn.get("turn_id")
            else:
                item = candidate_summary(entry, boost, query_terms)
                item["matched_terms"] = unique_preserve(
                    list(item.get("matched_terms") or []) + matched, limit=8
                )
                item["timeline_source"] = True
                item["life_wide_timeline_source"] = True
                item["scope_labels"] = scope_labels
                item["source_refs"] = source_refs[:3]
                item["source_ref_count"] = source_ref_count
                item["timeline_turn_id"] = turn.get("turn_id")
                candidates.append(item)
                by_key[thread_key] = item
            added_threads.add(str(thread_key))
            if len(added_threads) >= LIFE_WIDE_TIMELINE_CANDIDATE_LIMIT:
                return sort_candidates(candidates)
            break
    return sort_candidates(candidates)


def merge_timeline_candidates(
    candidates: list[dict[str, Any]],
    registry: dict[str, Any],
    timeline: dict[str, Any],
    prompt: str,
    cwd: Path,
    query_terms: list[str],
) -> list[dict[str, Any]]:
    if not timeline or not matched_terms(prompt, RECENCY_CUES):
        return candidates
    by_thread = {entry.get("thread_key"): entry for entry in registry.get("threads") or []}
    by_key = {item.get("thread_key"): item for item in candidates}
    for project in (timeline.get("projects") or {}).values():
        if not isinstance(project, dict) or not project_matches_prompt(project, prompt, cwd):
            continue
        latest_turns = project.get("latest_turns") or []
        if not latest_turns:
            continue
        latest = latest_turns[0]
        thread_key = latest.get("thread_key")
        entry = by_thread.get(thread_key)
        if not entry:
            continue
        boost = EVIDENCE_THRESHOLD + 2.0
        existing = by_key.get(thread_key)
        if existing:
            existing["score"] = round(float(existing.get("score") or 0.0) + boost, 3)
            existing["matched_terms"] = unique_preserve(
                list(existing.get("matched_terms") or [])
                + matched_terms(prompt, RECENCY_CUES)
                + [project.get("project_label") or ""],
                limit=8,
            )
            existing["timeline_source"] = True
            continue
        item = candidate_summary(entry, boost, query_terms)
        item["matched_terms"] = unique_preserve(
            list(item.get("matched_terms") or [])
            + matched_terms(prompt, RECENCY_CUES)
            + [project.get("project_label") or ""],
            limit=8,
        )
        item["timeline_source"] = True
        candidates.append(item)
        by_key[thread_key] = item
    candidates = merge_life_wide_timeline_candidates(
        candidates, registry, timeline, prompt, query_terms
    )
    return sort_candidates(candidates)


def cognitive_map_terms(matches: list[dict[str, Any]]) -> list[str]:
    terms: list[str] = []
    for match in matches:
        terms.extend(str(value) for value in match.get("matched_cues") or [])
        terms.extend(str(value) for value in match.get("query_terms") or [])
        terms.extend(str(value) for value in match.get("landmark_labels") or [])
    return unique_preserve([term for term in terms if term.strip()], limit=24)


def cognitive_map_boost(match: dict[str, Any]) -> float:
    confidence = float(match.get("confidence") or 0.0)
    score = float(match.get("score") or 0.0)
    return round(SCENT_THRESHOLD + min(12.0, confidence * 7.0 + score * 0.35), 3)


def merge_cognitive_map_candidates(
    candidates: list[dict[str, Any]],
    registry: dict[str, Any],
    cognitive_map_matches: list[dict[str, Any]],
    query_terms: list[str],
) -> list[dict[str, Any]]:
    if not cognitive_map_matches:
        return candidates
    by_thread = {entry.get("thread_key"): entry for entry in registry.get("threads") or []}
    by_key = {item.get("thread_key"): item for item in candidates}
    for match in cognitive_map_matches:
        boost = cognitive_map_boost(match)
        matched_terms = unique_preserve(
            list(match.get("matched_cues") or [])
            + list(match.get("query_terms") or [])
            + list(match.get("landmark_labels") or []),
            limit=8,
        )
        for thread_key in match.get("thread_keys") or []:
            entry = by_thread.get(thread_key)
            if not entry:
                continue
            existing = by_key.get(thread_key)
            if existing:
                existing["score"] = round(float(existing.get("score") or 0.0) + boost, 3)
                existing["matched_terms"] = unique_preserve(
                    list(existing.get("matched_terms") or []) + matched_terms, limit=8
                )
                existing["cognitive_map_source"] = True
                continue
            item = candidate_summary(entry, boost, query_terms)
            item["matched_terms"] = unique_preserve(
                list(item.get("matched_terms") or []) + matched_terms, limit=8
            )
            item["cognitive_map_source"] = True
            candidates.append(item)
            by_key[thread_key] = item
    return sort_candidates(candidates)


def rerank_candidates_with_probe(
    candidates: list[dict[str, Any]],
    query_terms: list[str],
    *,
    limit: int = SCENT_PROBE_LIMIT,
) -> list[dict[str, Any]]:
    if not candidates or not query_terms:
        return candidates
    for candidate in candidates[: max(0, limit)]:
        entry = candidate.get("_entry") or {}
        probe_score, hits = deep_search_entry(entry, query_terms, max_hits=1)
        if probe_score <= 0:
            continue
        candidate["probe_score"] = round(probe_score, 3)
        if hits:
            hit = hits[0]
            candidate["probe_line"] = hit.get("line")
            candidate["probe_phase"] = hit.get("phase") or ""
        candidate["score"] = round(
            float(candidate.get("score") or 0.0)
            + min(SCENT_PROBE_SCORE_CAP, probe_score * SCENT_PROBE_SCORE_MULTIPLIER),
            3,
        )
    return sort_candidates(candidates)


def fallback_search_candidates(
    registry: dict[str, Any], query_terms: list[str], limit: int = 5
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for entry in registry.get("threads") or []:
        paths = entry.get("paths") or {}
        sqlite_value = paths.get("sqlite")
        if not sqlite_value:
            continue
        sqlite_path = Path(str(sqlite_value))
        if not sqlite_path.exists() or not sqlite_path.is_file():
            continue
        item = candidate_summary(entry, SCENT_THRESHOLD, query_terms)
        item["fallback"] = True
        candidates.append(item)
        if len(candidates) >= limit:
            break
    return candidates


def should_suppress(
    prompt: str,
    explicit: list[str],
    associative: list[str],
    candidates: list[dict[str, Any]],
    working_memory_matches: list[dict[str, Any]] | None = None,
    *,
    cognitive_map_cue: bool = False,
    semantic_memory_cue: bool = False,
    source_evidence_cue: bool = False,
) -> bool:
    if prompt_is_secret_surface(prompt) and not memory_boundary_context_intent(prompt):
        # Secret-adjacent surfaces are intentionally stricter than ordinary
        # code prompts. They often contain harmless placeholders in tests, but
        # the next paste can contain a real cookie/header/key; do not let
        # semantic aliases or registry overlap turn that into foreground recall.
        return True
    if explicit:
        return False
    if source_evidence_cue and candidates:
        # Source-backed requests such as "Can you cite..." may mention codey
        # nouns (dashboard/project/API) because the old source itself is about
        # software. Once the user has asked for evidence and local search found
        # candidates, do not let the generic code-surface brake hide it.
        return False
    if associative and candidates:
        return False
    if semantic_memory_cue and candidates:
        # Semantic recall is allowed to replace brittle cue lists, but only
        # after the semantic gate has already run its anti-personalization
        # check. The local source search still has to find a candidate before
        # anything is surfaced.
        return False
    if working_memory_matches:
        # Working-memory routes already passed project scope and concrete-term
        # checks, so let them surface for relevant implementation work. This is
        # the ADHD-friendly path: use source-backed soft memory without turning
        # every coding prompt into a broad personal-memory prompt.
        return False
    if cognitive_map_cue and candidates:
        # Cognitive-map routes come from the slower subconscious layer. The
        # foreground hook may use them as navigation scent, but not as evidence.
        return False
    if prompt_is_code_surface(prompt):
        # Global prompt hooks are expensive socially, not computationally: a
        # normal "fix the button" task should not suddenly summon old personal
        # or philosophical memories unless the user also gave a memory cue.
        return True
    return False


def current_project_label(registry: dict[str, Any], cwd: Path) -> str | None:
    target = str(cwd.resolve()).casefold()
    sep = os.sep.casefold()
    best: tuple[int, str] | None = None
    for entry in registry.get("threads") or []:
        paths = entry.get("paths") or {}
        workspace = str(
            paths.get("workspace") or (entry.get("session_meta") or {}).get("cwd") or ""
        )
        if not workspace:
            continue
        try:
            workspace_low = str(Path(workspace).resolve()).casefold()
        except Exception:
            workspace_low = workspace.casefold()
        if workspace_low == target:
            score = 3
        elif target.startswith(workspace_low + sep) or workspace_low.startswith(target + sep):
            score = 2
        else:
            continue
        label = str(entry.get("project_label") or entry.get("workspace_name") or "")
        if label and (best is None or score > best[0]):
            best = (score, label)
    return best[1] if best else None
