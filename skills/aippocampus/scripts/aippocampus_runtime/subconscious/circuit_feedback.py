"""Circuit feedback ledger and dynamic job orchestration rules."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from typing import Any

from aippocampus_runtime.core import stable_json_tuple_id

SCHEMA_VERSION = 1
LEDGER_ROW_KIND = "aippocampus_circuit_feedback_ledger_row"
REPORT_KIND = "aippocampus_circuit_feedback_report"
SAFE_OUTCOMES = {
    "validation_pass",
    "validation_fail",
    "malformed_output",
    "empty_output",
    "low_confidence",
    "source_ref_validation_failure",
    "false_positive",
    "ignored",
    "useful_routed_candidate",
    "source_reopen_follow_through",
    "cost_overrun",
    "stale_candidate",
    "anti_nag_suppressed",
}


def _source_refs(value: Any) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    if not isinstance(value, list):
        return refs
    for item in value:
        if isinstance(item, Mapping):
            clean = {
                key: str(item.get(key) or "")
                for key in ("source_id", "source_ref", "message_id", "turn_id")
                if str(item.get(key) or "")
            }
            if clean:
                refs.append(clean)
    return refs[:6]


def feedback_rows_from_reports(
    reports: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for report in reports:
        if not isinstance(report, Mapping):
            continue
        outcome = str(report.get("quality_outcome") or report.get("outcome") or "")
        if outcome not in SAFE_OUTCOMES:
            outcome = "low_confidence"
        job_id = str(report.get("job_id") or report.get("provider_job_id") or "unknown_job")
        rows.append(
            {
                "kind": LEDGER_ROW_KIND,
                "schema_version": SCHEMA_VERSION,
                "feedback_id": stable_json_tuple_id(
                    "circuit_feedback",
                    job_id,
                    outcome,
                    report.get("run_id"),
                    ensure_ascii=False,
                ),
                "provider_job_id": job_id,
                "provider_family": str(report.get("provider_family") or "subconscious_job"),
                "quality_outcome": outcome,
                "severity": int(report.get("severity") or (3 if outcome.endswith("failure") else 1)),
                "cost_proxy": int(report.get("cost_proxy") or report.get("token_proxy") or 0),
                "source_refs": _source_refs(report.get("source_refs")),
                "reason_codes": [str(item) for item in report.get("reason_codes") or [outcome]],
                "privacy_boundary": {
                    "raw_prompt_stored": False,
                    "raw_source_text_stored": False,
                    "raw_tool_output_stored": False,
                    "local_path_stored": False,
                },
                "diagnostic_only": True,
                "supports_factual_claim": False,
            }
        )
    return rows


def derive_feedback_policy(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    materialized = [row for row in rows if isinstance(row, Mapping)]
    outcome_counts = Counter(str(row.get("quality_outcome") or "") for row in materialized)
    severity_by_job: dict[str, int] = defaultdict(int)
    cost_by_job: dict[str, int] = defaultdict(int)
    for row in materialized:
        job = str(row.get("provider_job_id") or "unknown_job")
        severity_by_job[job] += int(row.get("severity") or 0)
        cost_by_job[job] += int(row.get("cost_proxy") or 0)
    tighten = outcome_counts["source_ref_validation_failure"] + outcome_counts["false_positive"]
    low_yield = outcome_counts["malformed_output"] + outcome_counts["empty_output"] + outcome_counts["low_confidence"]
    useful = outcome_counts["useful_routed_candidate"] + outcome_counts["source_reopen_follow_through"]
    return {
        "kind": "aippocampus_circuit_feedback_policy",
        "schema_version": SCHEMA_VERSION,
        "microcircuit_policy": {
            "threshold_delta": min(0.25, 0.05 * tighten),
            "top_k_delta": -1 if tighten > useful else (1 if useful > tighten else 0),
            "diversity_required": low_yield > 0,
        },
        "job_priority": {
            job: "review" if severity >= 5 else ("skip_once" if cost_by_job[job] > 1000 else "normal")
            for job, severity in sorted(severity_by_job.items())
        },
        "fallback_branches": [
            *(
                ["narrower_source_window_selection", "frontier_marker_extraction"]
                if low_yield
                else []
            ),
            *(["source_ref_review"] if outcome_counts["source_ref_validation_failure"] else []),
            *(["pattern_completion_learning_loop_review"] if useful >= 2 else []),
        ],
        "diagnostic_only": True,
        "does_not_mutate_clean_source": True,
    }


def dynamic_job_orchestration_plan(
    job_specs: Mapping[str, Mapping[str, Any]],
    feedback_rows: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    policy = derive_feedback_policy(feedback_rows)
    branches = list(dict.fromkeys(policy["fallback_branches"]))
    plan: dict[str, dict[str, Any]] = {
        job: {"depends_on": list(spec.get("depends_on") or []), "conditional_branches": []}
        for job, spec in job_specs.items()
    }
    if "question_extraction" in plan and "frontier_marker_extraction" in branches:
        plan["question_extraction"]["conditional_branches"].append("frontier_marker_extraction")
    if "theme_emergence" in plan and "narrower_source_window_selection" in branches:
        plan["theme_emergence"]["conditional_branches"].append("narrower_source_window_selection")
    if "cognitive_map" in plan and "pattern_completion_learning_loop_review" in branches:
        plan["cognitive_map"]["conditional_branches"].append("pattern_completion_learning_loop_review")
    cycle_errors = _dependency_cycle_errors(plan)
    scheduler_plan_changed_count = sum(
        len(row.get("conditional_branches") or []) for row in plan.values()
    )
    salience_decay_applied_count = sum(
        1
        for row in feedback_rows
        if str(row.get("quality_outcome") or "") in {"stale_candidate", "anti_nag_suppressed"}
    )
    return {
        "kind": "aippocampus_dynamic_job_orchestration_plan",
        "schema_version": SCHEMA_VERSION,
        "plan": plan,
        "cycle_errors": cycle_errors,
        "cycle_prevention_ok": not cycle_errors,
        "policy": policy,
        "static_depends_on_preserved": True,
        "scheduler_plan_changed_count": scheduler_plan_changed_count,
        "salience_decay_applied_count": salience_decay_applied_count,
        "runtime_consumer_count": int(bool(scheduler_plan_changed_count or salience_decay_applied_count)),
        "consumer_boundary": "feedback_changes_scheduler_plan_not_source_truth",
    }


def _dependency_cycle_errors(plan: Mapping[str, Mapping[str, Any]]) -> list[str]:
    visiting: set[str] = set()
    visited: set[str] = set()
    errors: list[str] = []

    def visit(job: str, trail: list[str]) -> None:
        if job in visited or job not in plan:
            return
        if job in visiting:
            errors.append(" -> ".join([*trail, job]))
            return
        visiting.add(job)
        for dependency in plan[job].get("depends_on") or []:
            visit(str(dependency), [*trail, job])
        visiting.remove(job)
        visited.add(job)

    for job in plan:
        visit(job, [])
    return errors


def build_circuit_feedback_report(reports: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    rows = feedback_rows_from_reports(reports)
    policy = derive_feedback_policy(rows)
    encoded = json.dumps({"rows": rows, "policy": policy}, ensure_ascii=False, sort_keys=True)
    red_lines = {
        "raw_prompt_leak_count": int("PRIVATE_PROMPT" in encoded),
        "raw_source_text_leak_count": int("PRIVATE_SOURCE_TEXT" in encoded),
        "local_path_leak_count": int("C:\\" in encoded or "/Users/" in encoded),
        "feedback_promoted_to_truth_count": sum(1 for row in rows if row["supports_factual_claim"]),
    }
    return {
        "kind": REPORT_KIND,
        "schema_version": SCHEMA_VERSION,
        "ok": all(value == 0 for value in red_lines.values()),
        "rows": rows,
        "policy": policy,
        "red_lines": red_lines,
        "contract": {
            "append_only_feedback_ledger": True,
            "feedback_is_diagnostic_navigation_metadata": True,
            "observatory_is_not_control_plane": True,
        },
    }


__all__ = [
    "build_circuit_feedback_report",
    "derive_feedback_policy",
    "dynamic_job_orchestration_plan",
    "feedback_rows_from_reports",
]
