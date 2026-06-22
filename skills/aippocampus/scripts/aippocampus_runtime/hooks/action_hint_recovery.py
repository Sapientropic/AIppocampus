"""Recovery cards for empty action-hint cache refreshes."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from aippocampus_runtime.contracts import foreground_shell_action


def semantic_guidance_summary() -> dict[str, Any]:
    """Summarize deterministic semantic guidance without importing the CLI frontdoor.

    `learning_loop.cli` imports action hint cache helpers, so refresh-cache must
    not call back into the CLI helper. Keep this narrow: it only decides whether
    the empty-cache recovery card should point at review/materialization rather
    than pretending no guidance surface exists.
    """

    try:
        from aippocampus_runtime.learning_loop.semantic_learning import (
            build_semantic_learning_dogfood_fixture_report,
        )

        report = build_semantic_learning_dogfood_fixture_report()
    except Exception as exc:  # pragma: no cover - defensive recovery card metadata
        return {
            "status": "unavailable",
            "semantic_action_time_guidance_count": 0,
            "error": type(exc).__name__,
        }
    metrics = report.get("metrics") if isinstance(report, Mapping) else {}
    if not isinstance(metrics, Mapping):
        metrics = {}
    count = int(metrics.get("action_time_guidance_count") or 0)
    return {
        "status": "present" if count else "not_found",
        "semantic_action_time_guidance_count": count,
        "source": "learning_loop.semantic_learning",
        "fixture_only": True,
        "not_live_cache_input": True,
    }


def empty_cache_recovery(
    *,
    result: Mapping[str, Any],
    learned_intake: Mapping[str, Any],
    ledger_intake: Mapping[str, Any],
    write_requested: bool,
) -> dict[str, Any]:
    learned_status = str(learned_intake.get("status") or "")
    ledger_status = str(ledger_intake.get("status") or "")
    semantic_summary = semantic_guidance_summary()
    semantic_count = int(semantic_summary.get("semantic_action_time_guidance_count") or 0)
    if semantic_count:
        reason = "semantic_fixture_guidance_not_live_cache_input"
    elif learned_status == "not_found" and ledger_status == "not_found":
        reason = "no_learning_or_effectiveness_inputs_found"
    elif learned_status in {"blocked", "not_found"} and ledger_intake.get("row_count"):
        reason = "effectiveness_ledger_without_guidance"
    elif learned_intake.get("finding_count") and not learned_intake.get("prepared_record_count"):
        reason = "learning_findings_filtered_or_blocked"
    elif write_requested:
        reason = "write_requested_but_no_records_to_write"
    else:
        reason = "no_action_hint_records_prepared"
    review_semantic_action = foreground_shell_action(
        action_id="review_semantic_guidance_before_cache",
        label="Review semantic guidance before cache",
        command="aippocampus learning guidance --json",
        why=(
            "Semantic action-time guidance may exist, but it must be reviewed and "
            "materialized before refresh-cache can write hot hook records."
        ),
        mutation_risk="read_only",
        claim_boundary="learning_guidance_not_source_truth",
    )
    actions = [
        review_semantic_action,
        foreground_shell_action(
            action_id="discover_learning_sources",
            label="Discover eligible learning sources",
            command="aippocampus learning discover-history --json",
            why="Find an existing sanitized or source-backed learning input before refreshing the hot cache.",
            mutation_risk="read_only",
            claim_boundary="learning_guidance_not_source_truth",
        ),
        foreground_shell_action(
            action_id="inspect_learning_guidance",
            label="Inspect learning guidance",
            command="aippocampus learning guidance --json",
            why="Check whether prepared or semantic guidance exists before writing cache files.",
            mutation_risk="read_only",
            claim_boundary="learning_guidance_not_source_truth",
        ),
        foreground_shell_action(
            action_id="activate_aippo_guidance",
            label="Use AIppo task guidance",
            command='aippocampus agent aippo --task "action-time learning guidance" --json',
            why="Use project/workflow guidance when no learned action hints are prepared yet.",
            mutation_risk="read_only",
            claim_boundary="guidance_not_source_truth",
        ),
    ]
    return {
        "empty_cache_recovery": {
            "reason": reason,
            "record_count": int((result.get("cache") or {}).get("record_count") or 0),
            "write_requested": bool(write_requested),
            "wrote_empty_cache": bool(write_requested),
            "action_hints_ready": False,
            "semantic_guidance_present_but_not_materialized": bool(semantic_count),
            "semantic_fixture_guidance_not_live_cache_input": bool(semantic_count),
            "bridge_status": (
                "needs_live_learning_input"
                if semantic_count
                else "needs_learning_input"
            ),
            "semantic_guidance": semantic_summary,
        },
        "action_hints_ready": False,
        "wrote_empty_cache": bool(write_requested),
        "foreground_action": actions[1],
        "safe_next_actions": actions,
    }
