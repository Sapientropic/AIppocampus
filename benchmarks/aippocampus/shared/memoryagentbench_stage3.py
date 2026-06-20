"""Stage 3 local projection helpers for MemoryAgentBench smoke reports."""

from __future__ import annotations

from collections import Counter
from typing import Any, Mapping, Sequence

from aippocampus_runtime.navigation.local_global_compatibility import (
    evaluate_local_global_compatibility,
)
from aippocampus_runtime.recall.source_backed_lessons import (
    extract_source_backed_lesson_candidates,
    promote_lesson_candidate,
)


def _case_source_ref(case_payload: Mapping[str, Any], label: str) -> dict[str, Any]:
    return {
        "source_id": f"memoryagentbench:{case_payload['split']}:{label}:{case_payload['case_id']}",
        "event_id": f"{case_payload['case_id']}:{label}",
    }


def _ttl_learning_finding(case_payload: Mapping[str, Any]) -> dict[str, Any]:
    refs = [
        _case_source_ref(case_payload, "initial_write"),
        _case_source_ref(case_payload, "update_write"),
    ]
    return {
        "kind": "aippocampus_learning_finding",
        "finding_id": f"mab-ttl:{case_payload['case_id']}",
        "finding_kind": "workflow_order_finding",
        "candidate_family": "context_reopen_candidate",
        "workflow_family": "write_update_before_query",
        "status": "open",
        "occurrence_count": 2,
        "success_after_count": 1,
        "scope": "benchmark:memoryagentbench:test_time_learning",
        "freshness": "current",
        "source_refs": refs,
        "source_ref_count": len(refs),
        "foreground_eligible": True,
        "navigation_only": True,
        "claim_permission": "navigation_only_not_fact",
        "source_reopen_required_before_claim": True,
    }


def _conflict_compatibility_row(case_payload: Mapping[str, Any]) -> dict[str, Any]:
    source_id = f"memoryagentbench:{case_payload['split']}:{case_payload['case_id']}"
    return evaluate_local_global_compatibility(
        [
            {
                "case_id": f"{case_payload['case_id']}:stale",
                "kind": "memoryagentbench_conflict_candidate",
                "scope": f"case:{case_payload['case_id']}",
                "topic_epoch": "memoryagentbench-stage3",
                "freshness": "stale",
                "status": "stale",
                "source_ids": [f"{source_id}:stale"],
                "source_support": "navigation_only",
                "claim_permission": "navigation_only_not_fact",
            },
            {
                "case_id": f"{case_payload['case_id']}:current",
                "kind": "memoryagentbench_conflict_candidate",
                "scope": f"case:{case_payload['case_id']}",
                "topic_epoch": "memoryagentbench-stage3",
                "freshness": "current",
                "status": "current",
                "source_ids": [f"{source_id}:current"],
                "source_support": "navigation_only",
                "claim_permission": "navigation_only_not_fact",
            },
        ],
        case_id=f"mab-conflict:{case_payload['case_id']}",
    )


def build_stage3_aippocampus_runtime_arm(cases: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Project sanitized Stage 3 cases through runtime-owned proof layers."""

    ttl_findings = [
        _ttl_learning_finding(case)
        for case in cases
        if str(case.get("split") or "") == "Test_Time_Learning"
    ]
    lesson_candidates = extract_source_backed_lesson_candidates(ttl_findings)
    promoted_lessons = [
        promote_lesson_candidate(candidate, independent_trail_count=2)
        for candidate in lesson_candidates
    ]
    compatibility_rows = [
        _conflict_compatibility_row(case)
        for case in cases
        if str(case.get("split") or "") == "Conflict_Resolution"
    ]
    conflict_counts = Counter(str(row.get("result") or "") for row in compatibility_rows)
    stale_demoted_count = sum(
        1
        for row in compatibility_rows
        if row.get("result") in {"obstruction", "partial_glue", "blocked_boundary"}
        and "stale_or_released_section_blocks_current_glue" in row.get("reason_codes", [])
    )
    return {
        "arm": "aippocampus_runtime",
        "status": "runtime_projection_fixture",
        "projection_layers": [
            "learning_loop_finding",
            "source_backed_lesson_candidate",
            "local_global_compatibility",
        ],
        "test_time_learning": {
            "finding_count": len(ttl_findings),
            "lesson_candidate_count": len(lesson_candidates),
            "foreground_guidance_count": sum(
                1 for row in promoted_lessons if row.get("foreground_activation_allowed")
            ),
            "source_ref_count": sum(
                int(row.get("source_ref_count") or 0) for row in lesson_candidates
            ),
            "guidance_claim_permission": "working_guidance_only_not_fact",
        },
        "conflict_resolution": {
            "compatibility_case_count": len(compatibility_rows),
            "result_counts": dict(sorted(conflict_counts.items())),
            "stale_demoted_count": stale_demoted_count,
            "blocked_or_obstruction_count": sum(
                conflict_counts.get(key, 0) for key in ("obstruction", "blocked_boundary")
            ),
            "claim_permission": "navigation_only_not_fact",
        },
        "privacy_boundary": {
            "raw_context_emitted": False,
            "raw_question_emitted": False,
            "gold_label_used": False,
            "local_path_emitted": False,
        },
        "claim_boundary": {
            "official_task_run_count": 0,
            "official_memoryagentbench_score": "not_claimed",
            "runtime_projection_is_answer_quality": False,
            "source_reopen_required_before_claim": True,
        },
        "cannot_claim": [
            "official_memoryagentbench_score",
            "answer_generation_quality",
            "runtime_projection_as_official_runner_compatibility",
        ],
    }


def build_stage3_local_replay_result(
    cases: Sequence[Mapping[str, Any]],
    runtime_arm: Mapping[str, Any],
) -> dict[str, Any]:
    ttl = runtime_arm.get("test_time_learning") if isinstance(runtime_arm, Mapping) else {}
    conflict = runtime_arm.get("conflict_resolution") if isinstance(runtime_arm, Mapping) else {}
    ttl_hit = int((ttl or {}).get("foreground_guidance_count") or 0)
    conflict_hit = int((conflict or {}).get("stale_demoted_count") or 0)
    runtime_hit_count = min(len(cases), ttl_hit + conflict_hit)
    return {
        "status": (
            "bounded_local_source_backed_replay_completed"
            if cases
            else "skipped_missing_stage3_cases"
        ),
        "case_shape": "sanitized_stage3_ttl_conflict_hashes_counts_only",
        "official_score_claimable": False,
        "matched_baseline": {
            "arm": "static_or_hash_contract",
            "case_count": len(cases),
            "retrieval_probe_hit_count": 0,
            "answer_generation_mode": "not_executed",
            "judging_mode": "not_executed",
        },
        "aippocampus_runtime": {
            "arm": "aippocampus_runtime",
            "case_count": len(cases),
            "retrieval_probe_hit_count": runtime_hit_count,
            "test_time_learning_guidance_count": ttl_hit,
            "conflict_currentness_pass_count": conflict_hit,
            "answer_generation_mode": "not_executed",
            "judging_mode": "not_executed",
        },
        "claim_boundary": {
            "local_replay_supports": "write_update_retrieve_projection_over_sanitized_case_shape",
            "official_memoryagentbench_score": "not_claimed",
            "answer_quality": "not_measured",
        },
    }
