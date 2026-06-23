"""Current-checkout repo familiarity fallback for agent recall."""

from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

from aippocampus_runtime.contracts import normalize_foreground_action
from aippocampus_runtime.mcp import agent_recall_compact_choices as recall_choices
from aippocampus_runtime.mcp import agent_recall_recovery_projection as recovery_projection
from aippocampus_runtime.navigation import repo_familiarity
from aippocampus_runtime.recall.query_policy import distinctive_cjk_query_terms
from aippocampus_runtime.source.search import search_clean_source

_ANCHOR_RE = re.compile(r"[\u4e00-\u9fff]{2,}|[A-Za-z0-9][A-Za-z0-9_-]{3,}")
_NORMALIZE_RE = re.compile(r"[^0-9A-Za-z\u4e00-\u9fff]+")
_LOW_SIGNAL_ANCHORS = {
    "agent",
    "current",
    "issue",
    "issues",
    "memory",
    "recall",
    "route",
    "source",
    "source-backed",
    "sourcebacked",
}


def _query_anchor_stats(query: str, card: Mapping[str, Any]) -> dict[str, Any]:
    tokens: list[str] = []
    seen: set[str] = set()
    for raw in distinctive_cjk_query_terms(str(query or ""), limit=8):
        token = _NORMALIZE_RE.sub("", raw.casefold())
        if not token or token in _LOW_SIGNAL_ANCHORS or token in seen:
            continue
        seen.add(token)
        tokens.append(token)
    for match in _ANCHOR_RE.finditer(str(query or "")):
        token = _NORMALIZE_RE.sub("", match.group(0).casefold())
        if not token or token in _LOW_SIGNAL_ANCHORS or token in seen:
            continue
        if re.search(r"[\u4e00-\u9fff]", match.group(0)) and token not in seen:
            continue
        seen.add(token)
        tokens.append(token)
    card_text = _NORMALIZE_RE.sub(
        "",
        " ".join(
            str(card.get(key) or "")
            for key in (
                "landmark",
                "category",
                "why_now",
                "action_delta_required",
                "first_source_to_reopen",
            )
        ).casefold(),
    )
    matched = [token for token in tokens if token in card_text]
    return {
        "query_anchor_count": len(tokens),
        "query_anchor_match_count": len(matched),
        "query_anchor_alignment": (
            "no_distinctive_query_anchors"
            if not tokens
            else "overlap"
            if matched
            else "no_overlap"
        ),
    }


def repo_familiarity_root(cwd: Path) -> Path | None:
    for path in (cwd, *cwd.parents):
        if (
            (path / "skills" / "aippocampus" / "scripts" / "aippocampus_runtime").is_dir()
            and (path / "docs" / "architecture").is_dir()
        ):
            return path
    return None


def repo_familiarity_fallback_card(query: str, cwd: Path) -> dict[str, Any] | None:
    repo_root = repo_familiarity_root(cwd)
    if repo_root is None:
        return None
    packet = repo_familiarity.select_current_checkout_packet(
        repo_root,
        task=query,
        max_cards=1,
    )
    cards = [card for card in packet.get("selected_cards") or [] if isinstance(card, Mapping)]
    if not cards:
        report = packet.get("cost_delta_report") if isinstance(packet, Mapping) else {}
        return {
            "kind": "aippocampus_repo_familiarity_fallback",
            "schema_version": repo_familiarity.SCHEMA_VERSION,
            "status": "no_current_repo_card",
            "current_checkout_checked": True,
            "rejected_card_count": len(
                [item for item in packet.get("rejected_cards") or [] if isinstance(item, Mapping)]
            ),
            "stale_fast_reject_count": (
                int(report.get("fast_reject_count") or 0) if isinstance(report, Mapping) else 0
            ),
            "irrelevant_reject_count": (
                int(report.get("irrelevant_reject_count") or 0)
                if isinstance(report, Mapping)
                else 0
            ),
            "claim_boundary": "repo_familiarity_unselected_no_source_claim",
        }
    card = cards[0]
    refs = [ref for ref in card.get("source_refs") or [] if isinstance(ref, Mapping)]
    anchor_stats = _query_anchor_stats(query, card)
    route_status = (
        "no_query_overlap"
        if anchor_stats.get("query_anchor_alignment") == "no_overlap"
        else "route_candidate"
    )
    return {
        "kind": "aippocampus_repo_familiarity_fallback",
        "schema_version": repo_familiarity.SCHEMA_VERSION,
        "status": route_status,
        "route_choice_posture": (
            "repo_familiarity_withheld_no_query_overlap"
            if route_status == "no_query_overlap"
            else "repo_familiarity_current_checkout_fallback"
        ),
        "landmark": card.get("landmark"),
        "category": card.get("category"),
        "why_now": card.get("why_now"),
        "action_delta_required": card.get("action_delta_required"),
        "first_source_to_reopen": card.get("first_source_to_reopen"),
        "source_line": (refs[0].get("line") if refs else None),
        "source_ref_count": len(refs),
        "selected_card_count": len(cards),
        "current_checkout_checked": True,
        "invalidation_present": bool(card.get("invalidation")),
        **anchor_stats,
        "source_reopen_required_before_claim": True,
        "claim_boundary": (
            "repo_familiarity_diagnostic_only_no_query_overlap"
            if route_status == "no_query_overlap"
            else "repo_familiarity_navigation_only_until_source_opened"
        ),
    }


def current_source_anchor_probe(
    query: str,
    cwd: Path,
    *,
    clean_source_dir: str | Path | None = None,
) -> dict[str, Any]:
    anchor_query = recall_choices.registry_source_search_anchor_query(query)
    if not anchor_query:
        return {
            "status": "skipped",
            "reason": "no_distinctive_anchor_query",
            "match_count": 0,
        }
    try:
        result = search_clean_source(
            cwd,
            [anchor_query],
            clean_source_dir=clean_source_dir,
            limit=1,
            snippet_chars=0,
        )
    except Exception as exc:  # pragma: no cover - defensive diagnostic path
        return {
            "status": "unavailable",
            "reason": type(exc).__name__,
            "match_count": 0,
            "anchor_query": anchor_query,
        }
    raw_matches = [match for match in result.get("matches") or [] if isinstance(match, Mapping)]
    matches = [
        match
        for match in raw_matches
        if not match.get("search_noise")
        and (
            bool(match.get("is_final"))
            or str(match.get("phase") or "") == "final_answer"
            or str(match.get("role") or "") == "user"
        )
    ]
    return {
        "status": "matched" if matches else "no_match",
        "match_count": len(matches),
        "raw_match_count": len(raw_matches),
        "anchor_query": anchor_query,
        "search_scope": result.get("search_scope"),
        "top_match_message_id": matches[0].get("message_id") if matches else None,
        "claim_boundary": "current_source_anchor_probe_only_blocks_unrelated_repo_fallback",
    }


def repo_familiarity_action_card(
    *,
    repo_familiarity_fallback: Mapping[str, Any] | None,
    previous_card: Mapping[str, Any],
    triage_metrics: Mapping[str, Any],
    memory_packets: list[dict[str, Any]],
    query: str,
    current_source_probe: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any] | None, str | None]:
    compact_card = recovery_projection.compact_repo_familiarity_fallback_card(
        repo_familiarity_fallback
    )
    repo_action = recovery_projection.repo_familiarity_fallback_action(compact_card)
    if not repo_action:
        return None, None

    if recovery_projection.repo_familiarity_query_anchor_alignment(compact_card) == "no_overlap":
        return None, None

    if current_source_probe and int(current_source_probe.get("match_count") or 0) > 0:
        return None, None

    if any(packet.get("already_opened") for packet in memory_packets):
        return None, None

    route_count = len(memory_packets)
    metrics = dict(triage_metrics)
    labels_low_specificity = (
        recall_choices.low_specificity_route_choices(metrics, route_count)
        or bool(recall_choices.repeated_low_distinctiveness_label(metrics, memory_packets))
        or recall_choices.distinctive_cue_anchor_gap(query, memory_packets)
    )
    raw_previous_action = previous_card.get("canonical_action")
    previous_action: Mapping[str, object] = (
        cast(Mapping[str, object], raw_previous_action)
        if isinstance(raw_previous_action, Mapping)
        else {}
    )
    normalized_previous = normalize_foreground_action(previous_action)
    if not (
        labels_low_specificity
        or recovery_projection.repo_familiarity_should_replace_foreground_action(
            normalized_previous
        )
    ):
        return None, None

    canonical_action = {
        "action_id": repo_action.get("id"),
        "tool_name": repo_action.get("tool_name"),
        "arguments": repo_action.get("arguments") or {},
        "cli_command": repo_action.get("command"),
        "why": "Open current-checkout source before claims.",
        "mutation_risk": repo_action.get("mutation_risk") or "read_only",
        "claim_boundary": repo_action.get("claim_boundary"),
    }
    canonical_action = {
        key: value
        for key, value in canonical_action.items()
        if value not in (None, "", [], {})
    }
    return (
        {
            "decision": "use_repo_familiarity_fallback",
            "why": "Current-checkout source is a safer primary than low-specificity recall routes.",
            "next_action": "open_repo_familiarity_source",
            "claim_boundary": "repo_familiarity_navigation_only_until_source_opened",
            "canonical_action": canonical_action,
        },
        str(repo_action.get("command") or "") or None,
    )


__all__ = [
    "repo_familiarity_action_card",
    "repo_familiarity_fallback_card",
]
