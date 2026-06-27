"""Current-turn clean-source anchor recovery for MCP recall navigation."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from aippocampus_runtime.source.query_match_gate import match_query_profile, query_match_gate
from aippocampus_runtime.source.search import iter_clean_messages
from aippocampus_runtime.source.search_core import score_message
from aippocampus_runtime.source.search_terms import search_query_terms

RouteFromCleanHit = Callable[..., dict[str, Any]]


def _turn_route_key(message: Mapping[str, Any]) -> tuple[str, str]:
    turn_id = str(message.get("turn_id") or "").strip()
    if turn_id:
        return ("turn_id", turn_id)
    turn_index = message.get("turn_index")
    if turn_index not in (None, ""):
        return ("turn_index", str(turn_index))
    message_id = str(message.get("message_id") or message.get("id") or "").strip()
    return ("message_id", message_id)


def _selected_message(
    messages: list[dict[str, Any]],
    *,
    query_text: str,
    gate: Mapping[str, Any],
    terms: list[str],
) -> dict[str, Any]:
    def rank(message: dict[str, Any]) -> tuple[int, float, int, float]:
        profile = match_query_profile(
            query_text=query_text,
            gate=gate,
            haystack=str(message.get("text") or ""),
        )
        source_priority = 0
        if message.get("is_final") or message.get("phase") == "final_answer":
            source_priority = 2
        elif message.get("role") == "assistant":
            source_priority = 1
        return (
            int(profile.get("matched_distinctive_anchor_count") or 0),
            float(profile.get("distinctive_anchor_coverage") or 0.0),
            source_priority,
            score_message(message, terms),
        )

    return max(messages, key=rank)


def current_turn_anchor_hits(
    *,
    clean_source_dir: Path,
    intent: str,
    limit: int,
) -> list[dict[str, Any]]:
    terms = search_query_terms([intent])
    query_text = " ".join(str(term) for term in terms) or intent
    gate = query_match_gate(query_text)
    if int(gate.get("distinctive_anchor_count") or 0) < 2:
        return []

    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for message in iter_clean_messages(clean_source_dir / "messages.jsonl"):
        key = _turn_route_key(message)
        if key[1]:
            groups.setdefault(key, []).append(message)

    hits: list[dict[str, Any]] = []
    for messages in groups.values():
        joined = "\n".join(str(message.get("text") or "") for message in messages)
        profile = match_query_profile(query_text=query_text, gate=gate, haystack=joined)
        if not profile.get("accepted"):
            continue
        selected = dict(
            _selected_message(messages, query_text=query_text, gate=gate, terms=terms)
        )
        selected["query_match_profile"] = {
            **profile,
            "acceptance_reason": "same_turn_anchor_coverage",
        }
        selected["matched_cue_family"] = "clean_source_turn_anchor_hit"
        selected["turn_anchor_message_count"] = len(messages)
        selected["score"] = round(
            score_message(selected, terms)
            + int(profile.get("matched_distinctive_anchor_count") or 0) * 10
            + float(profile.get("distinctive_anchor_coverage") or 0.0) * 10,
            3,
        )
        hits.append(selected)

    def query_profile(hit: Mapping[str, Any]) -> Mapping[str, Any]:
        raw = hit.get("query_match_profile")
        return raw if isinstance(raw, Mapping) else {}

    hits.sort(
        key=lambda hit: (
            -int(query_profile(hit).get("matched_distinctive_anchor_count") or 0),
            -float(query_profile(hit).get("distinctive_anchor_coverage") or 0.0),
            -float(hit.get("score") or 0.0),
            int(hit.get("source_line") or 0),
        )
    )
    return hits[:limit]


def current_turn_anchor_routes(
    *,
    intent: str,
    source_dir: Path,
    max_routes: int,
    route_from_clean_hit: RouteFromCleanHit,
) -> list[dict[str, Any]]:
    # Only promote same-turn coverage after the same query gate accepts the
    # joined turn. This protects exact/current-source recall from falling back
    # to repo familiarity while still requiring a source reopen before claims.
    return [
        {
            **route_from_clean_hit(hit, source_dir=source_dir, intent=intent),
            "matched_cue_family": "clean_source_turn_anchor_hit",
            "route_label": "current_turn source route",
            "label_granularity": "same_turn_anchor_coverage",
            "route_label_specificity_score": 0.9,
            "triage_rank_reason_codes": [
                "same_turn_anchor_coverage",
                "current_clean_source",
                "source_reopen_required",
            ],
            "why_this_may_matter": (
                "The current clean-source turn covers the cue across adjacent "
                "messages; reopen the selected message window before claiming."
            ),
        }
        for hit in current_turn_anchor_hits(
            clean_source_dir=source_dir,
            intent=intent,
            limit=max_routes,
        )
    ]
