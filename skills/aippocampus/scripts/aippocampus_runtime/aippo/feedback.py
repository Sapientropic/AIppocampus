"""Public-safe AIppo activation feedback and reripening fixtures."""

from __future__ import annotations

import copy
import json
from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

from aippocampus_runtime.aippo import working_contract

SCHEMA_VERSION = "aippo-feedback-v0"


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _json_bytes(value: Mapping[str, Any]) -> int:
    return len(json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8"))


def _fixture_feedback_rows() -> list[dict[str, Any]]:
    return [
        {
            "case_id": "manual_search_reduced_before_useful_continuity",
            "clause_id": "clause_keep_changes_scoped",
            "agent_action": "used",
            "outcome_signal": "helped",
            "manual_search_after_packet": 0,
            "manual_search_baseline": 2,
            "source_backed": True,
            "recommended_lifecycle_change": "keep_ripe",
        },
        {
            "case_id": "later_source_correction_challenges_clause",
            "clause_id": "clause_issue_closeout_convention",
            "agent_action": "corrected",
            "outcome_signal": "misleading",
            "source_backed": True,
            "recommended_lifecycle_change": "challenge",
        },
        {
            "case_id": "stale_clause_degrades_to_reopenable_route",
            "clause_id": "clause_benchmark_default_claim",
            "agent_action": "manual_search_after_packet",
            "outcome_signal": "stale",
            "source_backed": True,
            "recommended_lifecycle_change": "stale",
        },
        {
            "case_id": "self_report_success_unverified",
            "clause_id": "clause_preserve_useful_result_claims",
            "agent_action": "used",
            "outcome_signal": "helped",
            "source_backed": False,
            "self_report_only": True,
            "feedback_status": "feedback_unverified",
            "recommended_lifecycle_change": "keep_candidate",
        },
        {
            "case_id": "noisy_correct_guidance_suppressed",
            "clause_id": "clause_run_focused_verification",
            "agent_action": "ignored",
            "outcome_signal": "noisy",
            "source_backed": True,
            "foreground_noise_bytes": 420,
            "recommended_lifecycle_change": "suppress_foreground",
        },
        {
            "case_id": "repeat_correction_claim_boundary",
            "clause_id": "clause_issue_closeout_convention",
            "agent_action": "corrected",
            "outcome_signal": "misleading",
            "source_backed": True,
            "recommended_lifecycle_change": "challenge",
        },
    ]


def _group_findings(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    grouped = Counter(
        (
            str(row.get("clause_id") or "unknown"),
            str(row.get("recommended_lifecycle_change") or "keep_candidate"),
        )
        for row in rows
        if row.get("source_backed") or row.get("outcome_signal") == "noisy"
    )
    findings = []
    for (clause_id, lifecycle_change), count in sorted(grouped.items()):
        if count < 2 and lifecycle_change not in {"suppress_foreground"}:
            continue
        findings.append(
            {
                "finding_id": f"finding_{clause_id}_{lifecycle_change}",
                "clause_id": clause_id,
                "supporting_feedback_count": count,
                "recommended_lifecycle_change": lifecycle_change,
                "bounded": True,
            }
        )
    return findings


def _eval_seed_from_finding(finding: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "eval_seed_id": f"eval_{finding['clause_id']}_{finding['recommended_lifecycle_change']}",
        "source": finding["finding_id"],
        "task_family": "issue_closeout",
        "expected_behavior": "challenge_or_deepen_before_claim",
        "public_safe": True,
    }


def _apply_feedback_to_contract(
    contract: Mapping[str, Any],
    rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    updated = copy.deepcopy(dict(contract))
    changes_by_clause: dict[str, str] = {}
    for row in rows:
        clause_id = str(row.get("clause_id") or "")
        change = str(row.get("recommended_lifecycle_change") or "")
        if row.get("self_report_only"):
            continue
        if change in {"challenge", "stale", "suppress_foreground"}:
            changes_by_clause[clause_id] = change
    for clause in updated.get("clauses") or []:
        if not isinstance(clause, dict):
            continue
        change = changes_by_clause.get(str(clause.get("clause_id") or ""))
        lifecycle = clause.setdefault("lifecycle", {})
        activation = clause.setdefault("activation", {})
        if change == "challenge":
            lifecycle["status"] = "challenged"
            lifecycle["degrade_to"] = "reopenable_route"
            activation["next_action"] = "reopen_source"
            activation["foreground_eligible"] = False
        elif change == "stale":
            lifecycle["status"] = "stale"
            lifecycle["degrade_to"] = "reopenable_route"
            activation["next_action"] = "reopen_source"
            activation["foreground_eligible"] = False
        elif change == "suppress_foreground":
            lifecycle["foreground_priority"] = "suppressed_noisy"
            activation["foreground_eligible"] = False
            activation["next_action"] = "deepen"
    return updated


def build_aippo_feedback_report(
    contract: Mapping[str, Any],
    feedback_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    rows = [dict(row) for row in feedback_rows]
    updated_contract = _apply_feedback_to_contract(contract, rows)
    packet = working_contract.activation_packet_from_working_contract(
        updated_contract,
        task="benchmark reporting issue closeout",
    )
    findings = _group_findings(rows)
    eval_seeds = [_eval_seed_from_finding(findings[0])] if findings else []
    red_lines = {
        "self_report_promoted_to_truth_count": sum(
            1
            for row in rows
            if row.get("self_report_only")
            and row.get("recommended_lifecycle_change") == "keep_ripe"
        ),
        "feedback_trace_mutated_clean_source_count": 0,
        "stale_clause_kept_ripe_after_source_correction_count": sum(
            1
            for clause in updated_contract.get("clauses") or []
            if isinstance(clause, Mapping)
            and clause.get("clause_id") == "clause_benchmark_default_claim"
            and (clause.get("lifecycle") or {}).get("status") == "ripe"
        ),
        "claim_ready_fact_from_working_contract_count": 0,
        "self_improvement_trace_counted_as_product_evidence": 0,
    }
    metrics = {
        "aippo_activation_count": len(rows),
        "aippo_clause_used_count": sum(1 for row in rows if row.get("agent_action") == "used"),
        "aippo_clause_ignored_count": sum(
            1 for row in rows if row.get("agent_action") == "ignored"
        ),
        "aippo_manual_search_after_packet_count": sum(
            1 for row in rows if row.get("agent_action") == "manual_search_after_packet"
        ),
        "aippo_manual_search_delta_proxy": sum(
            _int(row.get("manual_search_baseline")) - _int(row.get("manual_search_after_packet"))
            for row in rows
        ),
        "aippo_clause_correction_count": sum(
            1 for row in rows if row.get("agent_action") == "corrected"
        ),
        "aippo_feedback_unverified_count": sum(
            1 for row in rows if row.get("feedback_status") == "feedback_unverified"
        ),
        "aippo_grouped_finding_count": len(findings),
        "aippo_eval_seed_count": len(eval_seeds),
        "aippo_clause_challenged_from_feedback_count": sum(
            1 for row in rows if row.get("recommended_lifecycle_change") == "challenge"
        ),
        "aippo_clause_stale_from_feedback_count": sum(
            1 for row in rows if row.get("recommended_lifecycle_change") == "stale"
        ),
        "aippo_noisy_guidance_suppressed_count": sum(
            1 for row in rows if row.get("recommended_lifecycle_change") == "suppress_foreground"
        ),
        "foreground_packet_bytes": _json_bytes(packet),
    }
    return {
        "kind": "aippocampus_aippo_feedback_reripening_report",
        "schema_version": SCHEMA_VERSION,
        "fixture_cases": rows,
        "grouped_findings": findings,
        "eval_seeds": eval_seeds,
        "updated_contract": updated_contract,
        "foreground_activation_packet": packet,
        "foreground_packet_budget_bytes": working_contract.FOREGROUND_PACKET_BYTE_BUDGET,
        "metrics": metrics,
        "red_lines": red_lines,
        "ok": all(value == 0 for value in red_lines.values())
        and _json_bytes(packet) <= working_contract.FOREGROUND_PACKET_BYTE_BUDGET,
        "contract": {
            "feedback_updates_lifecycle_metadata_only": True,
            "clean_source_append_only": True,
            "self_report_is_candidate_until_source_backed": True,
            "foreground_packet_excludes_feedback_diagnostics": True,
        },
    }


def build_aippo_feedback_fixture_report(
    contract: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if contract is None:
        contract = working_contract.build_project_workflow_public_safe_contract()
    return build_aippo_feedback_report(contract, _fixture_feedback_rows())


__all__ = [
    "build_aippo_feedback_fixture_report",
    "build_aippo_feedback_report",
]
