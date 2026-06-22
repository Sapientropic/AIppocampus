#!/usr/bin/env python3
"""Search and ranking helpers for the machine-wide thread registry."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from aippocampus_runtime.core import compact_text
from aippocampus_runtime.source.rollout import is_injected_instruction_text

__all__ = [
    "RegistrySearchBudget",
    "REGISTRY_SEARCH_DEFAULT_BUDGET",
    "REGISTRY_SEARCH_DEEP_BUDGET",
    "entry_search_score",
    "search_noise_reason",
    "clean_hit_rank_score",
    "deep_search_entry_result",
    "deep_search_entry",
]


@dataclass(frozen=True)
class RegistrySearchBudget:
    candidate_limit: int
    snippet_chars: int
    context_radius: int


# Registry search feeds ambient recall and hook-safe surfaces. Keep the default
# intentionally compact; callers that are in an explicit diagnostic/deep-search
# flow can opt into the larger budget below.
REGISTRY_SEARCH_DEFAULT_BUDGET = RegistrySearchBudget(
    candidate_limit=80,
    snippet_chars=260,
    context_radius=0,
)
REGISTRY_SEARCH_DEEP_BUDGET = RegistrySearchBudget(
    candidate_limit=160,
    snippet_chars=700,
    context_radius=2,
)
PROCESS_NOISE_PREFIXES = (
    ("<subagent_notification>", "process_notification"),
    ("<tool", "tool_process"),
)


def entry_search_score(entry: dict, terms: list[str]) -> float:
    blob = "\n".join(
        [
            entry.get("title") or "",
            entry.get("workspace_name") or "",
            entry.get("project_label") or "",
            entry.get("project_key") or "",
            " ".join(entry.get("project_tags") or []),
            entry.get("summary") or "",
            " ".join(entry.get("anchor_titles") or []),
            " ".join(entry.get("keywords") or []),
            json.dumps(entry.get("session_meta") or {}, ensure_ascii=False),
        ]
    ).casefold()
    score = 0.0
    for term in terms:
        low = term.casefold()
        if not low:
            continue
        if low in (entry.get("title") or "").casefold():
            score += 8.0
        if any(low in str(keyword).casefold() for keyword in entry.get("keywords") or []):
            score += 4.0
        if low in blob:
            score += 1.5
    return score


def search_noise_reason(text: str) -> str | None:
    """Classify repeated runtime carrier text that should not dominate recall.

    This is a ranking boundary, not a deletion rule. Old indexes may already
    contain injected skill or instruction carriers, so registry search must keep
    them auditable while making real user/final-answer evidence win.
    """

    snippet = str(text or "").lstrip().casefold()
    for prefix, reason in PROCESS_NOISE_PREFIXES:
        if snippet.startswith(prefix):
            return reason
    if is_injected_instruction_text(text):
        return "injected_instruction"
    return None


def clean_hit_rank_score(message: dict, score: float) -> tuple[float, str | None]:
    text = str(message.get("text") or "")
    reason = search_noise_reason(text)
    rank_score = float(score)
    if reason:
        rank_score *= 0.05
    if message.get("role") == "assistant" and str(message.get("phase") or "") == "final_answer":
        rank_score *= 1.12
    return rank_score, reason


def _search_warning(stage: str, path: str | Path, exc: Exception) -> dict:
    return {
        "stage": stage,
        "path": str(path),
        "error_type": type(exc).__name__,
        "message": str(exc),
    }


def deep_search_entry_result(
    entry: dict,
    terms: list[str],
    max_hits: int = 3,
    *,
    search_budget: RegistrySearchBudget | None = None,
) -> dict:
    budget = search_budget or REGISTRY_SEARCH_DEFAULT_BUDGET
    paths = entry.get("paths") or {}
    warnings: list[dict] = []
    clean_messages = paths.get("clean_source_messages_jsonl")
    if clean_messages:
        try:
            from aippocampus_runtime.source.jsonl_reader import jsonl_loss_warning
            from aippocampus_runtime.source.search_core import (
                load_clean_messages_with_loss,
                score_message,
            )
            from aippocampus_runtime.source.semantic_scope_labels import (
                load_semantic_scope_labels,
                merged_scope_labels,
                semantic_labels_for_message,
            )

            clean_hits = []
            messages_path = Path(clean_messages)
            semantic_sidecar = load_semantic_scope_labels(messages_path.parent)
            messages, jsonl_loss = load_clean_messages_with_loss(messages_path)
            warning = jsonl_loss_warning(
                jsonl_loss,
                stage="clean_source",
                path_label=str(clean_messages),
            )
            if warning:
                warnings.append(warning)
            for message in messages:
                semantic_scope_labels = semantic_labels_for_message(message, semantic_sidecar)
                if semantic_scope_labels:
                    message = dict(message)
                    message["semantic_scope_labels"] = semantic_scope_labels
                    message["scope_labels"] = merged_scope_labels(
                        list(message.get("scope_labels") or []), semantic_scope_labels
                    )
                score = score_message(message, terms)
                if score <= 0:
                    continue
                rank_score, noise_reason = clean_hit_rank_score(message, score)
                clean_hits.append((rank_score, score, noise_reason, message))
            clean_hits.sort(key=lambda item: (-item[0], int(item[3].get("source_line") or 0)))
            if clean_hits:
                compact_hits = [
                    {
                        "source": "clean_source",
                        "id": message.get("message_id") or message.get("id"),
                        "message_id": message.get("message_id") or message.get("id"),
                        "turn_id": message.get("turn_id"),
                        "source_id": message.get("source_id"),
                        "clean_ordinal": message.get("clean_ordinal"),
                        "line": message.get("source_line"),
                        "role": message.get("role"),
                        "phase": message.get("phase") or "",
                        "turn_index": message.get("turn_index"),
                        "is_final": message.get("is_final"),
                        "scope_labels": [
                            label
                            for label in message.get("scope_labels", [])
                            if isinstance(label, str)
                        ],
                        "semantic_scope_labels": [
                            label
                            for label in message.get("semantic_scope_labels", [])
                            if isinstance(label, str)
                        ],
                        "score": round(score, 3),
                        "rank_score": round(rank_score, 3),
                        "search_noise": bool(noise_reason),
                        "noise_reason": noise_reason,
                        "snippet": compact_text(
                            str(message.get("text") or ""), budget.snippet_chars
                        ),
                    }
                    for rank_score, score, noise_reason, message in clean_hits[:max_hits]
                ]
                return {
                    "score": max(rank_score for rank_score, *_ in clean_hits[:max_hits]) * 0.08,
                    "hits": compact_hits,
                    "warnings": warnings,
                }
        except Exception as exc:
            warnings.append(_search_warning("clean_source", clean_messages, exc))

    sqlite_value = str(paths.get("sqlite") or "").strip()
    if not sqlite_value:
        return {"score": 0.0, "hits": [], "warnings": warnings}
    sqlite_path = Path(sqlite_value)
    if not sqlite_path.exists():
        return {"score": 0.0, "hits": [], "warnings": warnings}
    # Registry search is imported by low-level registry glue. Keep retrieval as
    # a use-site dependency so search policy can evolve without an import-time
    # cycle between catalog bookkeeping and heavier recall execution.
    from aippocampus_runtime.recall.retrieval import (
        expanded_terms_from_anchors,
        match_anchors,
        search_hybrid_index,
    )

    anchors_value = paths.get("anchors")
    anchors_path = Path(anchors_value) if anchors_value else None
    anchors = (
        match_anchors(anchors_path, terms, limit=4)
        if anchors_path and anchors_path.is_file()
        else []
    )
    expanded = expanded_terms_from_anchors(terms, anchors, limit=24)
    try:
        hits = search_hybrid_index(
            sqlite_path,
            terms,
            expanded,
            anchors,
            limit=max_hits,
            candidate_limit=budget.candidate_limit,
            snippet_chars=budget.snippet_chars,
            context_radius=budget.context_radius,
        )
    except Exception as exc:
        warnings.append(_search_warning("sqlite", sqlite_path, exc))
        return {"score": 0.0, "hits": [], "warnings": warnings}
    score = max((float(hit.get("score") or 0.0) for hit in hits), default=0.0) * 0.08
    compact_hits = []
    for hit in hits:
        item = {
            "source": "sqlite",
            "line": hit.get("line"),
            "role": hit.get("role"),
            "phase": hit.get("phase") or "",
            "turn_index": hit.get("turn_index"),
            "is_final": hit.get("is_final"),
            "score": hit.get("score"),
            "snippet": hit.get("snippet"),
        }
        if "context" in hit:
            item["context"] = hit.get("context")
        compact_hits.append(item)
    return {"score": score, "hits": compact_hits, "warnings": warnings}


def deep_search_entry(
    entry: dict,
    terms: list[str],
    max_hits: int = 3,
    *,
    search_budget: RegistrySearchBudget | None = None,
) -> tuple[float, list[dict]]:
    result = deep_search_entry_result(entry, terms, max_hits=max_hits, search_budget=search_budget)
    return float(result.get("score") or 0.0), list(result.get("hits") or [])
