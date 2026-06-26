"""Public labels for reviewed background findings.

Reviewed Dream/subconscious rows often arrive with generic titles such as
"Background finding". Keep the specificity recovery here so the foreground
card can describe what kind of route an agent is seeing without turning the
background row into source truth.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from aippocampus_runtime import core
from aippocampus_runtime.subconscious import match_terms

GENERIC_BACKGROUND_TITLES = {
    "",
    "background finding",
    "reviewed finding",
    "working memory finding",
}
GENERIC_MATCH_TERMS = {
    "action",
    "actions",
    "memory",
    "project",
    "source",
    "issue",
    "issues",
    "message",
    "messages",
    "candidate",
    "finding",
    "background",
} | match_terms.LOW_INFORMATION_SINGLE_TRIGGER_TERMS
SHAPE_LABELS = {
    "hook_trigger": "action_hint_candidate",
    "concept_edge": "source_bridge",
    "project_memory": "project_memory",
    "preference_review": "preference_review",
    "contradiction_review": "review_signal",
    "dedup_review": "review_signal",
    "question_candidate": "question_signal",
    "question_link": "question_signal",
    "theme_candidate": "theme_signal",
    "frontier_marker": "frontier_signal",
    "dream_hypothesis": "dream_hypothesis",
}


def _human_label(value: str) -> str:
    text = str(value or "").replace("_", " ").strip()
    return text[:1].upper() + text[1:] if text else "Working memory finding"


def _unique_preserve(values: list[str], *, limit: int) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        key = value.casefold()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(value)
        if len(out) >= limit:
            break
    return out


def _shape_label(row: Mapping[str, Any]) -> str:
    candidate_type = str(row.get("candidate_type") or "").strip()
    if candidate_type == "dream_hypothesis":
        dream_function = str(row.get("dream_function") or "").strip()
        return f"{dream_function}_dream_hypothesis" if dream_function else "dream_hypothesis"
    return SHAPE_LABELS.get(candidate_type, "working_memory")


def _specific_matched_terms(row: Mapping[str, Any]) -> list[str]:
    raw = [
        str(term).strip()
        for term in row.get("matched_terms") or []
        if str(term).strip()
    ]
    specific = [
        term
        for term in raw
        if term.casefold() not in GENERIC_MATCH_TERMS and len(term.strip()) > 3
    ]
    return _unique_preserve(specific or raw, limit=6)


def _finding_title(row: Mapping[str, Any], *, shape_label: str) -> tuple[str, bool]:
    raw_title = core.compact_text(str(row.get("title") or ""), 140)
    if raw_title.casefold().strip() not in GENERIC_BACKGROUND_TITLES:
        return raw_title, False
    if shape_label != "working_memory":
        return _human_label(shape_label), False
    return "Reviewed background finding", True


def _match_reason(row: Mapping[str, Any], *, shape_label: str, terms: list[str]) -> str:
    if terms:
        display_terms = ", ".join(_human_label(term) for term in terms[:4])
        return f"Matched reviewed {shape_label.replace('_', ' ')} cues: {display_terms}."
    activation_cues = [
        str(cue).strip()
        for cue in row.get("activation_cues") or []
        if str(cue).strip()
    ]
    if activation_cues:
        display_terms = ", ".join(_human_label(cue) for cue in activation_cues[:4])
        return f"Reviewed {shape_label.replace('_', ' ')} has safe activation cues: {display_terms}."
    return core.compact_text(
        str(row.get("route_reason") or "Only a low-specificity reviewed background label is safe here."),
        220,
    )


def projection_fields(row: Mapping[str, Any]) -> dict[str, Any]:
    shape_label = _shape_label(row)
    matched_terms = _specific_matched_terms(row)
    finding_title, low_information_label = _finding_title(row, shape_label=shape_label)
    return {
        "shape_label": shape_label,
        "finding_title": finding_title,
        "title": finding_title,
        "low_information_label": low_information_label,
        "match_reason": _match_reason(row, shape_label=shape_label, terms=matched_terms),
        "matched_terms": matched_terms,
    }


__all__ = ["projection_fields"]
