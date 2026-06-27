#!/usr/bin/env python3
"""Public-safe Dream lifecycle and why-no-output status cards."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
from typing import Any

from aippocampus_runtime.dream import lifecycle as dream_lifecycle

RETENTION_LIFECYCLE_ACTIONS: dict[str, dict[str, Any]] = {
    "retain_for_review": {
        "lifecycle_state": "retained_for_review",
        "action": "keep_review_material",
        "next_action": "review_adjudicated_findings_or_project_when_accepted",
    },
    "park_for_review": {
        "lifecycle_state": "parked_pending_review",
        "action": "revisit_on_review_horizon",
        "next_action": "run_dream_retrospective_lifecycle_summary",
    },
    "drop_low_pressure": {
        "lifecycle_state": "low_pressure_compacted",
        "action": "compact_or_ignore_without_projection",
        "next_action": "leave_out_of_working_memory_unless_new_source_targets_it",
    },
}


def retention_lifecycle_action(decision: object) -> dict[str, Any]:
    return dict(
        RETENTION_LIFECYCLE_ACTIONS.get(
            str(decision or ""),
            {
                "lifecycle_state": "unknown_retention_decision",
                "action": "inspect_operator_report",
                "next_action": "inspect_full_sleep_cycle_payload",
            },
        )
    )


def retention_decision_counts(findings: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for finding in findings:
        policy = finding.get("retention_policy") or {}
        if isinstance(policy, Mapping):
            decision = str(policy.get("decision") or "")
            if decision:
                counts[decision] += 1
    return dict(sorted(counts.items()))


def _reason_buckets(payload: Mapping[str, Any], retention_counts: Mapping[str, int]) -> dict[str, int]:
    counts = payload.get("counts") or {}
    worker_statuses = payload.get("worker_statuses") or {}
    buckets: Counter[str] = Counter()
    if int(counts.get("queue_items") or 0) == 0:
        buckets["no_queue"] += 1
    if int(counts.get("selected_items") or 0) == 0 and int(counts.get("queue_items") or 0):
        buckets["no_selected_items"] += 1
    if int(counts.get("rejected") or 0) or int(worker_statuses.get("model_output_rejected") or 0):
        buckets["worker_rejection"] += int(counts.get("rejected") or 0) or int(worker_statuses.get("model_output_rejected") or 0)
    if int(counts.get("parked") or 0):
        buckets["adjudication_parked"] += int(counts.get("parked") or 0)
    if payload.get("no_write"):
        buckets["no_write_mode"] += 1
    if str(payload.get("write_mode") or "") == "staging":
        buckets["working_memory_projection_disabled"] += 1
    if int(counts.get("accepted") or 0) and not int(counts.get("written_working_memory") or 0):
        buckets["no_working_memory_projection"] += 1
    for decision, count in retention_counts.items():
        buckets[f"retention:{decision}"] += int(count)
    for reason, count in (payload.get("failure_buckets") or {}).items():
        buckets[f"worker_failure:{reason}"] += int(count)
    return dict(sorted(buckets.items()))


def dream_output_status_card(payload: Mapping[str, Any]) -> dict[str, Any]:
    counts = payload.get("counts") or {}
    retention_counts = retention_decision_counts(payload.get("adjudicated_findings") or [])
    lifecycle_report = payload.get("dream_lifecycle_report")
    if not isinstance(lifecycle_report, Mapping):
        lifecycle_report = dream_lifecycle.dream_lifecycle_report(
            payload.get("adjudicated_findings") or []
        )
    reason_buckets = _reason_buckets(payload, retention_counts)
    status = "output_available" if int(counts.get("written_working_memory") or 0) else "no_foreground_output"
    if int(counts.get("accepted") or 0) and payload.get("no_write"):
        primary_action = "rerun_with_write_or_publish_when_operator_intends_persistence"
    elif int(counts.get("parked") or 0):
        primary_action = "inspect_retention_and_review_horizon"
    elif int(counts.get("rejected") or 0) or reason_buckets.get("worker_rejection"):
        primary_action = "inspect_operator_report_for_rejected_candidate_reasons"
    elif int(counts.get("selected_items") or 0) == 0:
        primary_action = "wait_for_due_queue_or_run_ready"
    else:
        primary_action = "leave_silent"
    return {
        "kind": "aippocampus_dream_output_status_card",
        "status": status,
        "public_safe": True,
        "counts": {
            "queue_items": int(counts.get("queue_items") or 0),
            "selected_items": int(counts.get("selected_items") or 0),
            "accepted": int(counts.get("accepted") or 0),
            "parked": int(counts.get("parked") or 0),
            "rejected": int(counts.get("rejected") or 0),
            "written_findings": int(counts.get("written_findings") or 0),
            "written_working_memory": int(counts.get("written_working_memory") or 0),
        },
        "reason_buckets": reason_buckets,
        "retention_decision_counts": retention_counts,
        "dream_lifecycle_counts": dict(lifecycle_report.get("counts") or {}),
        "dream_lifecycle_examples": list(lifecycle_report.get("examples") or [])[:3],
        "retention_lifecycle_actions": {
            decision: retention_lifecycle_action(decision)
            for decision in sorted(set(retention_counts) | set(RETENTION_LIFECYCLE_ACTIONS))
        },
        "primary_next_action": primary_action,
        "safe_alternatives": [
            "inspect_operator_report",
            "run_dream_retrospective_lifecycle_summary",
            "leave_parked_without_foreground_delivery",
        ],
        "privacy": {
            "omits_raw_candidate_text": True,
            "omits_source_handles": True,
            "candidate_only_not_memory_truth": True,
        },
    }
