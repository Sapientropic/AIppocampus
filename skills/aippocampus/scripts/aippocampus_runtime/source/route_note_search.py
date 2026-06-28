"""Search joined route notes as navigation back to clean source.

Route notes are extracted from bounded agent commentary, but commentary is not
source truth. This adapter only uses filtered anchor terms and joined source
refs; foreground callers receive a reopenable clean-source route, not a raw
commentary payload or route-note inventory.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Mapping

from aippocampus_runtime.core import compact_text
from aippocampus_runtime.source.io_kernel import JsonlReadResult, load_jsonl_dict_rows

GENERIC_TERMS = {
    "agent",
    "before",
    "change",
    "changed",
    "changing",
    "check",
    "decide",
    "decided",
    "old",
    "previous",
    "route",
    "source",
}


def _low(value: Any) -> str:
    return str(value or "").casefold().strip()


def _words(value: Any) -> list[str]:
    return [item for item in re.split(r"[^0-9A-Za-z_\u4e00-\u9fff]+", str(value or "")) if item]


def _source_ref_from_joined(note: Mapping[str, Any]) -> dict[str, Any]:
    for joined in note.get("joined_evidence_refs") or []:
        if not isinstance(joined, Mapping):
            continue
        if str(joined.get("evidence_kind") or "") != "final_answer":
            continue
        ref = joined.get("source_ref")
        if isinstance(ref, Mapping) and (ref.get("message_id") or ref.get("line")):
            return dict(ref)
    for ref in note.get("source_refs") or []:
        if isinstance(ref, Mapping) and (ref.get("message_id") or ref.get("line")):
            return dict(ref)
    return {}


def _note_haystack_terms(note: Mapping[str, Any]) -> set[str]:
    haystack: set[str] = set()
    for key in ("note_type", "title", "why_lit"):
        haystack.update(_low(word) for word in _words(note.get(key)))
    for value in note.get("reason_codes") or []:
        haystack.update(_low(word) for word in _words(value))
    for value in note.get("route_anchor_terms") or []:
        haystack.add(_low(value))
        haystack.update(_low(word) for word in _words(value))
    return {item for item in haystack if item}


def _matched_terms(note: Mapping[str, Any], terms: list[str]) -> tuple[list[str], list[str]]:
    haystack = _note_haystack_terms(note)
    anchor_terms = {_low(item) for item in note.get("route_anchor_terms") or [] if _low(item)}
    matched: list[str] = []
    matched_anchor_terms: list[str] = []
    for term in terms:
        low = _low(term)
        if not low:
            continue
        if low in haystack:
            matched.append(str(term))
            if low in anchor_terms:
                matched_anchor_terms.append(str(term))
    return matched, matched_anchor_terms


def _route_note_score(note: Mapping[str, Any], terms: list[str]) -> tuple[float, list[str], list[str]]:
    matched, matched_anchor_terms = _matched_terms(note, terms)
    if not matched_anchor_terms:
        return 0.0, matched, matched_anchor_terms
    distinctive = [
        term
        for term in matched_anchor_terms
        if "_" in term or len(term) >= 8 or re.search(r"[\u4e00-\u9fff]", term)
    ]
    non_generic = [term for term in matched_anchor_terms if _low(term) not in GENERIC_TERMS]
    if not distinctive and not non_generic and len(matched) < 3:
        return 0.0, matched, matched_anchor_terms
    score = float(len(matched)) + float(len(matched_anchor_terms)) * 3.0
    score += float(len(distinctive)) * 3.0
    if str(note.get("readiness_class") or "") == "source_reopen_ready":
        score += 2.0
    if any(
        isinstance(item, Mapping) and item.get("evidence_kind") == "final_answer"
        for item in note.get("joined_evidence_refs") or []
    ):
        score += 1.0
    return score, matched, matched_anchor_terms


def _route_note_match(
    note: Mapping[str, Any],
    *,
    score: float,
    matched_terms: list[str],
    matched_anchor_terms: list[str],
    snippet_chars: int,
) -> dict[str, Any]:
    ref = _source_ref_from_joined(note)
    joined_kinds = sorted(
        {
            str(item.get("evidence_kind") or "unknown")
            for item in note.get("joined_evidence_refs") or []
            if isinstance(item, Mapping)
        }
    )
    note_type = str(note.get("note_type") or "process_route").strip()
    safe_anchors = [str(item) for item in note.get("route_anchor_terms") or [] if str(item).strip()]
    snippet = compact_text(
        (
            f"Route note: {note_type}; joined evidence: {', '.join(joined_kinds)}; "
            f"anchors: {', '.join(safe_anchors[:6])}"
        ),
        snippet_chars,
    )
    return {
        "source": "route_note",
        "id": note.get("route_id") or note.get("id"),
        "message_id": ref.get("message_id"),
        "turn_id": ref.get("turn_id"),
        "source_id": ref.get("source_id"),
        "clean_ordinal": ref.get("clean_ordinal"),
        "source_line": ref.get("line"),
        "line": ref.get("line"),
        "role": "assistant",
        "phase": "route_note",
        "turn_index": ref.get("turn_index"),
        "is_final": False,
        "material_class": "agent_trace_navigation",
        "source_claim_policy": "source_open_required_for_exact_claim",
        "scope_labels": ["route_note", "agent_trace_navigation"],
        "semantic_scope_labels": [],
        "score": round(score, 3),
        "rank_score": round(score * 0.96, 3),
        "matched_route_note_terms": matched_terms[:8],
        "query_match_profile": {
            "accepted": True,
            "acceptance_reason": "route_note_anchor_terms",
            "matched_distinctive_anchors": matched_anchor_terms[:8],
            "matched_distinctive_anchor_count": len(matched_anchor_terms),
        },
        "snippet": snippet,
    }


def search_route_notes(
    route_notes_path: str | Path,
    terms: list[str],
    *,
    limit: int = 5,
    snippet_chars: int = 260,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    path = Path(route_notes_path)
    result: JsonlReadResult = load_jsonl_dict_rows(path)
    matches: list[dict[str, Any]] = []
    for note in result.rows:
        ref = _source_ref_from_joined(note)
        if not ref:
            continue
        score, matched, matched_anchor_terms = _route_note_score(note, terms)
        if score <= 0:
            continue
        matches.append(
            _route_note_match(
                note,
                score=score,
                matched_terms=matched,
                matched_anchor_terms=matched_anchor_terms,
                snippet_chars=snippet_chars,
            )
        )
    matches.sort(key=lambda item: (-float(item.get("rank_score") or item.get("score") or 0.0), int(item.get("line") or 0)))
    return matches[:limit], result.loss


__all__ = ["search_route_notes"]
