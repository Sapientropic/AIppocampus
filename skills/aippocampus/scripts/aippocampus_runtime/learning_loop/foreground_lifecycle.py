"""Foreground projections for learning guidance lifecycle cards."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from aippocampus_runtime.contracts import foreground_shell_action


def preview_cache_bridge_action() -> dict[str, Any]:
    return foreground_shell_action(
        action_id="preview_action_hint_cache_bridge",
        label="Preview action-hint cache bridge",
        command="aippocampus hooks action refresh-cache --json",
        why=(
            "Check why visible semantic guidance is not yet a prepared hot-cache hint "
            "without writing cache files."
        ),
        mutation_risk="read_only",
        claim_boundary="learning_guidance_not_source_truth",
    )


def semantic_guidance_lifecycle(
    semantic_report: Mapping[str, Any],
    *,
    prepared_count: int,
) -> dict[str, Any]:
    stage_report = semantic_report.get("stage_report")
    stage = dict(stage_report) if isinstance(stage_report, Mapping) else {}
    action_time = stage.get("action_time")
    action_time = dict(action_time) if isinstance(action_time, Mapping) else {}
    guidance_rows = action_time.get("guidance")
    if not isinstance(guidance_rows, list):
        guidance_rows = []
    outcome_report = stage.get("outcome_report")
    outcome_report = dict(outcome_report) if isinstance(outcome_report, Mapping) else {}
    outcomes = outcome_report.get("outcomes")
    if not isinstance(outcomes, list):
        outcomes = []
    outcome_by_id = {
        str(row.get("guidance_id")): row
        for row in outcomes
        if isinstance(row, Mapping) and row.get("guidance_id")
    }
    candidates: list[dict[str, Any]] = []
    for raw in guidance_rows[:5]:
        if not isinstance(raw, Mapping):
            continue
        guidance_id = str(raw.get("guidance_id") or "")
        outcome = dict(outcome_by_id.get(guidance_id) or {})
        source_refs = raw.get("source_refs")
        source_ref_count = len(source_refs) if isinstance(source_refs, list) else 0
        candidates.append(
            {
                "guidance_id": guidance_id,
                "candidate_kind": raw.get("candidate_kind") or "",
                "next_action": raw.get("next_action") or "",
                "outcome_status": outcome.get("outcome_status") or "unproven",
                "outcome": outcome.get("outcome") or "outcome_unobserved",
                "source_ref_count": source_ref_count,
                "navigation_only": True,
                "claim_boundary": "learning_guidance_not_source_truth",
                "materialization_gate": (
                    "prepared_hint_available"
                    if prepared_count
                    else "requires_review_before_cache"
                ),
                "review_action": {
                    **foreground_shell_action(
                        action_id="review_semantic_guidance_candidate",
                        label="Review semantic guidance candidate",
                        command="aippocampus learning guidance --json",
                        why=(
                            "Review the public-safe semantic candidate and source-ref count "
                            "before treating it as cache material."
                        ),
                        mutation_risk="read_only",
                        claim_boundary="learning_guidance_not_source_truth",
                    ),
                    "target": {"guidance_id": guidance_id},
                },
                "materialization_action": {
                    **foreground_shell_action(
                        action_id="prepare_action_hint_cache_after_review",
                        label="Prepare action-hint cache after review",
                        command="aippocampus hooks action refresh-cache --write --json",
                        why=(
                            "Write hot-cache records only after reviewed guidance has a "
                            "prepared source-backed row."
                        ),
                        mutation_risk="explicit_local_cache_write",
                        claim_boundary="learning_guidance_not_source_truth",
                    ),
                    "blocked_until": (
                        None if prepared_count else "reviewed_guidance_has_prepared_row"
                    ),
                },
            }
        )
    status = (
        "prepared_guidance_ready"
        if prepared_count
        else (
            "semantic_candidates_require_review_before_cache"
            if candidates
            else "no_semantic_guidance_candidates"
        )
    )
    return {
        "contract": "semantic-guidance-lifecycle-v1",
        "status": status,
        "candidate_count": len(candidates),
        "prepared_action_hint_count": prepared_count,
        "candidate_actions": candidates,
        "cache_bridge": preview_cache_bridge_action(),
        "claim_boundary": "semantic lifecycle rows are navigation only until source reopen/review",
    }
