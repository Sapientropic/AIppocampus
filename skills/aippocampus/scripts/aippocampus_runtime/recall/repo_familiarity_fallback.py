"""Current-checkout repo familiarity fallback for agent recall."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

from aippocampus_runtime.contracts import normalize_foreground_action
from aippocampus_runtime.mcp import agent_recall_compact_choices as recall_choices
from aippocampus_runtime.mcp import agent_recall_recovery_projection as recovery_projection
from aippocampus_runtime.navigation import repo_familiarity


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
    return {
        "kind": "aippocampus_repo_familiarity_fallback",
        "schema_version": repo_familiarity.SCHEMA_VERSION,
        "status": "route_candidate",
        "route_choice_posture": "repo_familiarity_current_checkout_fallback",
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
        "source_reopen_required_before_claim": True,
        "claim_boundary": "repo_familiarity_navigation_only_until_source_opened",
    }


def repo_familiarity_action_card(
    *,
    repo_familiarity_fallback: Mapping[str, Any] | None,
    previous_card: Mapping[str, Any],
    triage_metrics: Mapping[str, Any],
    memory_packets: list[dict[str, Any]],
    query: str,
) -> tuple[dict[str, Any] | None, str | None]:
    compact_card = recovery_projection.compact_repo_familiarity_fallback_card(
        repo_familiarity_fallback
    )
    repo_action = recovery_projection.repo_familiarity_fallback_action(compact_card)
    if not repo_action:
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
