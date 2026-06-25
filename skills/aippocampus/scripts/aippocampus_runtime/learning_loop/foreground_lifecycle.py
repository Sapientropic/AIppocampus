"""Foreground projections for learning guidance lifecycle cards."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from aippocampus_runtime.contracts import foreground_shell_action, shell_quote


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
    prepared_rows: Iterable[Mapping[str, Any]] | None = None,
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
    prepared_by_id: dict[str, list[dict[str, Any]]] = {}
    for row in prepared_rows or []:
        if not isinstance(row, Mapping):
            continue
        guidance_id = str(row.get("guidance_id") or row.get("record_id") or "").strip()
        if guidance_id:
            prepared_by_id.setdefault(guidance_id, []).append(dict(row))
    candidates: list[dict[str, Any]] = []
    ledger: list[dict[str, Any]] = []
    for raw in guidance_rows[:5]:
        if not isinstance(raw, Mapping):
            continue
        guidance_id = str(raw.get("guidance_id") or f"semantic-guidance-{len(candidates) + 1}")
        outcome = dict(outcome_by_id.get(guidance_id) or {})
        prepared_matches = prepared_by_id.get(guidance_id) or []
        source_refs = raw.get("source_refs")
        source_ref_count = len(source_refs) if isinstance(source_refs, list) else 0
        review_status = str(raw.get("review_status") or raw.get("review_state") or "").casefold()
        reviewed = review_status in {"reviewed", "accepted", "prepared", "machine_checked"}
        prepared_status = (
            "prepared"
            if prepared_matches
            else "prepared_unknown"
            if prepared_count and not prepared_by_id
            else "not_prepared"
        )
        lifecycle_events = [
            {
                "guidance_id": guidance_id,
                "stage": "candidate",
                "status": "candidate",
                "row_id": f"candidate:{guidance_id}",
                "navigation_only": True,
                "claim_boundary": "learning_guidance_not_source_truth",
            },
            {
                "guidance_id": guidance_id,
                "stage": "reviewed",
                "status": "reviewed" if reviewed else "review_required",
                "row_id": f"review:{guidance_id}",
                "navigation_only": True,
                "claim_boundary": "learning_guidance_not_source_truth",
            },
            {
                "guidance_id": guidance_id,
                "stage": "prepared",
                "status": prepared_status,
                "row_id": (
                    str(prepared_matches[0].get("record_id") or f"prepared:{guidance_id}")
                    if prepared_matches
                    else f"prepared:{guidance_id}"
                ),
                "navigation_only": True,
                "claim_boundary": "learning_guidance_not_source_truth",
            },
            {
                "guidance_id": guidance_id,
                "stage": "surfaced",
                "status": "eligible_unobserved",
                "row_id": f"surfaced:{guidance_id}",
                "navigation_only": True,
                "claim_boundary": "learning_guidance_not_source_truth",
            },
            {
                "guidance_id": guidance_id,
                "stage": "outcome",
                "status": outcome.get("outcome_status") or "outcome_unobserved",
                "row_id": str(outcome.get("ledger_id") or f"outcome:{guidance_id}"),
                "navigation_only": True,
                "claim_boundary": "learning_guidance_not_source_truth",
            },
        ]
        ledger.append(
            {
                "guidance_id": guidance_id,
                "prepared_record_count": len(prepared_matches),
                "events": lifecycle_events,
            }
        )
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
                    if prepared_matches or (prepared_count and not prepared_by_id)
                    else "requires_review_before_cache"
                ),
                "lifecycle_events": lifecycle_events,
                "review_action": {
                    **foreground_shell_action(
                        action_id="review_semantic_guidance_candidate",
                        label="Review semantic guidance candidate",
                        command=(
                            "aippocampus learning guidance "
                            f"--guidance-id {shell_quote(guidance_id)} --json"
                        ),
                        why=(
                            "Review this public-safe semantic candidate and source-ref count "
                            "before treating it as cache material."
                        ),
                        mutation_risk="read_only",
                        claim_boundary="learning_guidance_not_source_truth",
                    ),
                    "target": {"guidance_id": guidance_id},
                },
                "materialization_action": {
                    **foreground_shell_action(
                        action_id=(
                            "prepare_action_hint_cache_after_review"
                            if prepared_matches or (prepared_count and not prepared_by_id)
                            else "preview_action_hint_cache_bridge_after_review"
                        ),
                        label=(
                            "Prepare action-hint cache after review"
                            if prepared_matches or (prepared_count and not prepared_by_id)
                            else "Preview action-hint cache bridge after review"
                        ),
                        command=(
                            "aippocampus hooks action refresh-cache --write --json"
                            if prepared_matches or (prepared_count and not prepared_by_id)
                            else "aippocampus hooks action refresh-cache --json"
                        ),
                        why=(
                            "Write hot-cache records only after reviewed guidance has a "
                            "prepared source-backed row."
                            if prepared_matches or (prepared_count and not prepared_by_id)
                            else "Dry-run the cache bridge; this candidate is not prepared cache input yet."
                        ),
                        mutation_risk=(
                            "explicit_local_cache_write"
                            if prepared_matches or (prepared_count and not prepared_by_id)
                            else "read_only"
                        ),
                        claim_boundary="learning_guidance_not_source_truth",
                    ),
                    "blocked_until": (
                        None if prepared_count else "reviewed_guidance_has_prepared_row"
                    ),
                    "target": {"guidance_id": guidance_id},
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
        "row_lifecycle_contract": "guidance-row-lifecycle-v1",
        "status": status,
        "candidate_count": len(candidates),
        "prepared_action_hint_count": prepared_count,
        "candidate_actions": candidates,
        "guidance_lifecycle_ledger": ledger,
        "cache_bridge": preview_cache_bridge_action(),
        "claim_boundary": "semantic lifecycle rows are navigation only until source reopen/review",
    }
