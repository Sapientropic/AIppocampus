#!/usr/bin/env python3
"""Public large-scale reliability gauntlet for AIppocampus.

This runner is a public-safe aggregate gate for GitHub #1102. It deliberately
keeps runtime stability, mis-recall quality, and pollution hygiene separate:
combining them into one flattering score would hide the exact-line and real
scale boundaries the evidence is meant to expose.
"""

from __future__ import annotations

import argparse
import json
import tempfile
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import _paths

_paths.ensure_paths()

import smoke_long_thread_segment_soak
import smoke_question_tracking_scale
import smoke_synthetic_scale_capacity

import benchmark_knowledge_pollution
import benchmark_semantic_robustness
from aippocampus_runtime.core import now_utc
from benchmarks.aippocampus.shared import auto_hook_pollution
from shared.report_actions import report_next_action

SCHEMA_VERSION = 1
OWNER_PATH = "benchmarks/aippocampus/benchmark_public_reliability_gauntlet.py"
HISTORICAL_SOURCE_ISSUE = "https://github.com/Sapientropic/AIppocampus/issues/1102"
HISTORICAL_OWNER_ISSUE_URL = "https://github.com/Sapientropic/AIppocampus/issues/2101"
NO_OPEN_FOLLOWUP_REASON = (
    "#2101 closed after adding owner/action routing; current claim posture is "
    "owned by docs/evidence/current-claims.md until a new scoped issue is opened."
)
LONGMEMEVAL_500_SOURCE_REPORT = "docs/evidence/benchmarks/longmemeval.md#current-published-result"
LONGMEMEVAL_500_COMMAND_REPORT = "docs/evidence/benchmarks/longmemeval.md#commands"


def _rate(numerator: int, denominator: int) -> dict[str, Any]:
    return {
        "numerator": int(numerator),
        "denominator": int(denominator),
        "rate": round(numerator / denominator, 4) if denominator else 0.0,
    }


def _unique_sorted(values: list[Any]) -> list[str]:
    return sorted({str(value) for value in values if str(value or "").strip()})


def _longmemeval_s_500_reference() -> dict[str, Any]:
    """Return the published aggregate LongMemEval-S 500Q row without raw report text.

    The raw 277 MB dataset and generated case report stay local/gitignored. This
    projection uses only the stable published aggregate, command, checksum, and
    miss taxonomy so the gauntlet can cover the 500Q runtime/mis-recall surface
    without committing public benchmark text or local machine paths.
    """

    return {
        "status": "referenced_published_aggregate",
        "source_report": LONGMEMEVAL_500_SOURCE_REPORT,
        "reproduce_commands": LONGMEMEVAL_500_COMMAND_REPORT,
        "dataset": {
            "split": "longmemeval-v1-small",
            "dataset_version": "longmemeval-cleaned 2025-09",
            "dataset_bytes": 277_383_467,
            "dataset_sha256": (
                "d6f21ea9d60a0d56f34a05b609c79c88a451d2ae03597821ea3d5a9678c3a442"
            ),
        },
        "evaluation": {
            "mode": "retrieval_only",
            "question_count": 500,
            "top_k": 10,
            "evidence_context_radius": 5,
            "runtime_seconds": 803.10,
            "warning_count": 0,
            "progress_checkpoints": "completed",
            "partial_output_behavior": "final_partial_output_completed_not_blocked",
            "raw_report_storage": "benchmark_corpus/reports local gitignored aggregate only",
        },
        "metrics": {
            "question_count": 500,
            "evidence_line_case_count": 479,
            "session_recall_at_10": _rate(479, 500),
            "evidence_line_recall_at_10": _rate(408, 479),
            "context_visible_evidence_recall_at_10": _rate(452, 479),
            "session_mrr": 0.8809,
            "evidence_line_mrr": 0.6309,
            "context_visible_evidence_mrr": 0.8086,
            "evidence_recall_ladder": {
                "r_at_1": _rate(240, 479),
                "r_at_3": _rate(349, 479),
                "r_at_5": _rate(380, 479),
                "r_at_10": _rate(408, 479),
                "r_at_20": _rate(429, 479),
                "r_at_50": _rate(450, 479),
            },
            "exact_line_miss_taxonomy": {
                "context_visible_exact_line_miss": 44,
                "session_found_below_top_k": 9,
                "same_session_wrong_line_top_k": 9,
                "gold_line_low_ranked_21_to_50": 5,
                "gold_line_below_rank_50": 3,
                "gold_line_near_miss_rank_11_to_20": 1,
            },
            "context_visible_rescue_count": 44,
            "context_visible_rescue_distance": {
                "distance_1": 29,
                "distance_2_to_context_radius": 15,
            },
        },
        "privacy_boundary": {
            "raw_text_emitted": False,
            "snippets_emitted": False,
            "case_ids_emitted": False,
            "absolute_paths_emitted": False,
            "source_report_is_aggregate": True,
        },
        "cannot_claim": [
            "longmemeval_qa_score",
            "answer_generation_quality",
            "judge_model_score",
            "longmemeval_v2_score",
            "sota_or_external_baseline_superiority",
            "exact_line_citation_quality_solved",
            "broad_memory_superiority",
        ],
    }


def _project_synthetic_scale(payload: Mapping[str, Any]) -> dict[str, Any]:
    metrics = dict(payload.get("metrics") or {})
    return {
        "status": payload.get("status"),
        "ok": bool(payload.get("ok")),
        "metrics": {
            "canonical_clean_source_bytes": metrics.get("canonical_clean_source_bytes"),
            "generated_index_bytes": metrics.get("generated_index_bytes"),
            "index_amplification_ratio": metrics.get("index_amplification_ratio"),
            "sync_policy_bytes": metrics.get("sync_policy_bytes"),
            "segment_count": metrics.get("segment_count"),
            "worst_case_sqlite_handles": metrics.get("worst_case_sqlite_handles"),
            "planned_sqlite_handles": metrics.get("planned_sqlite_handles"),
            "estimated_rebuild_work_units": metrics.get("estimated_rebuild_work_units"),
        },
        "thresholds": payload.get("thresholds") or {},
        "warnings": list(payload.get("warnings") or []),
        "blockers": list(payload.get("blockers") or []),
        "privacy_boundary": payload.get("privacy_boundary") or {},
        "cannot_claim": list(payload.get("cannot_claim") or []),
    }


def _project_question_tracking(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "status": "synthetic_scale_smoke",
        "ok": bool(payload.get("ok")),
        "metrics": {
            "candidate_count": payload.get("candidate_count"),
            "group_count": payload.get("group_count"),
            "all_pair_count": payload.get("all_pair_count"),
            "baseline_elapsed_ms": (payload.get("baseline") or {}).get("elapsed_ms"),
            "sidecar_elapsed_ms": (payload.get("sidecar") or {}).get("elapsed_ms"),
            "sidecar_pair_count": (payload.get("sidecar") or {}).get("sidecar_pair_count"),
            "source_joined_pair_count": (payload.get("sidecar") or {}).get(
                "source_joined_pair_count"
            ),
            "source_ref_key_mismatch_count": (payload.get("sidecar") or {}).get(
                "source_ref_key_mismatch_count"
            ),
            "baseline_strong_pair_coverage": (payload.get("sidecar") or {}).get(
                "baseline_strong_pair_coverage"
            ),
        },
        "warnings": list(payload.get("warnings") or []),
        "privacy_boundary": payload.get("privacy") or {},
        "cannot_claim": list(payload.get("cannot_claim") or []),
    }


def _project_segment_soak(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "status": payload.get("status"),
        "ok": bool(payload.get("ok")),
        "metrics": {
            "turn_count": (payload.get("data_boundary") or {}).get("turn_count"),
            "message_count": (payload.get("data_boundary") or {}).get("message_count"),
            "segment_count": (payload.get("capacity_metrics") or {}).get("segment_count"),
            "worst_case_sqlite_handles": (payload.get("capacity_metrics") or {}).get(
                "worst_case_sqlite_handles"
            ),
            "fanout_budget": (payload.get("capacity_metrics") or {}).get("fanout_budget"),
            "full_fanout_hit_rate": (payload.get("quality_metrics") or {}).get(
                "full_fanout_hit_rate"
            ),
            "budgeted_fanout_hit_rate": (payload.get("quality_metrics") or {}).get(
                "budgeted_fanout_hit_rate"
            ),
            "query_wall_per_case": (payload.get("timing_ms") or {}).get(
                "query_wall_per_case"
            ),
        },
        "privacy_boundary": payload.get("privacy_boundary") or {},
        "cannot_claim": list(payload.get("cannot_claim") or []),
    }


def _skipped_component(*, status: str, cannot_claim: list[str]) -> dict[str, Any]:
    return {
        "status": status,
        "ok": True,
        "metrics": {},
        "privacy_boundary": {
            "raw_private_text_emitted": False,
            "absolute_paths_emitted": False,
        },
        "cannot_claim": cannot_claim,
    }


def _runtime_axis(
    *,
    longmemeval_ref: Mapping[str, Any],
    run_question_tracking: bool,
    run_segment_soak: bool,
) -> dict[str, Any]:
    synthetic_scale = _project_synthetic_scale(
        smoke_synthetic_scale_capacity.build_synthetic_scale_capacity_smoke()
    )
    components: dict[str, Any] = {
        "longmemeval_s_500_reference": longmemeval_ref,
        "synthetic_scale_capacity": synthetic_scale,
    }
    if run_question_tracking:
        components["question_tracking_scale"] = _project_question_tracking(
            smoke_question_tracking_scale.run_question_tracking_scale_smoke()
        )
    else:
        components["question_tracking_scale"] = _skipped_component(
            status="skipped_by_runner_flag",
            cannot_claim=[
                "question_tracking_scale_runtime_from_this_gauntlet_run",
                "default_question_index_prefilter_is_safe",
            ],
        )
    if run_segment_soak:
        with tempfile.TemporaryDirectory(prefix="aippocampus-public-gauntlet-") as tmp:
            components["long_thread_segment_soak"] = _project_segment_soak(
                smoke_long_thread_segment_soak.run_long_thread_segment_soak(
                    workspace=Path(tmp),
                    include_monolithic=True,
                )
            )
    else:
        components["long_thread_segment_soak"] = _skipped_component(
            status="skipped_by_default_enable_with_segment_soak",
            cannot_claim=[
                "real_file_segment_soak_runtime_from_this_default_run",
                "windows_interrupted_rebuild_recovery",
            ],
        )

    component_ok = all(bool(component.get("ok", True)) for component in components.values())
    blockers = list(synthetic_scale.get("blockers") or [])
    warnings = list(synthetic_scale.get("warnings") or [])
    metrics = {
        "longmemeval_question_count": longmemeval_ref["metrics"]["question_count"],
        "longmemeval_runtime_seconds": longmemeval_ref["evaluation"]["runtime_seconds"],
        "longmemeval_warning_count": longmemeval_ref["evaluation"]["warning_count"],
        "synthetic_clean_source_bytes": synthetic_scale["metrics"][
            "canonical_clean_source_bytes"
        ],
        "synthetic_segment_count": synthetic_scale["metrics"]["segment_count"],
        "synthetic_worst_case_sqlite_handles": synthetic_scale["metrics"][
            "worst_case_sqlite_handles"
        ],
        "synthetic_planned_sqlite_handles": synthetic_scale["metrics"][
            "planned_sqlite_handles"
        ],
        "warning_count": len(warnings),
        "blocker_count": len(blockers),
        "warnings": warnings,
        "blockers": blockers,
    }
    if run_question_tracking:
        question = components["question_tracking_scale"]["metrics"]
        metrics.update(
            {
                "question_tracking_candidate_count": question.get("candidate_count"),
                "question_tracking_all_pair_count": question.get("all_pair_count"),
                "question_tracking_sidecar_pair_count": question.get("sidecar_pair_count"),
            }
        )
    if run_segment_soak:
        segment = components["long_thread_segment_soak"]["metrics"]
        metrics.update(
            {
                "segment_soak_segment_count": segment.get("segment_count"),
                "segment_soak_full_fanout_hit_rate": segment.get(
                    "full_fanout_hit_rate"
                ),
            }
        )

    return {
        "status": "passed_with_warnings" if component_ok and warnings else "passed"
        if component_ok
        else "blocked",
        "ok": component_ok and not blockers,
        "claim_boundary": (
            "Runtime axis combines a published LongMemEval-S 500Q aggregate and "
            "public-safe synthetic scale/fanout smokes. Synthetic rows are pressure "
            "models, not real GB/TB registry runtime proof."
        ),
        "metrics": metrics,
        "components": components,
        "cannot_claim": _unique_sorted(
            [claim for component in components.values() for claim in component.get("cannot_claim", [])]
            + [
                "real_gb_registry_runtime",
                "real_tb_registry_runtime",
                "private_history_runtime",
                "live_hook_write_path_quality",
            ]
        ),
    }


def _mis_recall_axis(*, longmemeval_ref: Mapping[str, Any]) -> dict[str, Any]:
    semantic = benchmark_semantic_robustness.run_semantic_robustness_benchmark(
        include_private_text=False,
        include_proxy_alignment=False,
    )
    tracks = semantic["tracks"]
    s1_metrics = tracks["s1_gate_robustness"]["metrics"]
    s2_metrics = tracks["s2_retrieval_invariance"]["metrics"]
    s3_metrics = tracks["s3_hard_negative_suppression"]["metrics"]
    components = {
        "longmemeval_s_500_reference": {
            "status": longmemeval_ref["status"],
            "source_report": longmemeval_ref["source_report"],
            "metrics": {
                "question_count": longmemeval_ref["metrics"]["question_count"],
                "session_recall_at_10": longmemeval_ref["metrics"][
                    "session_recall_at_10"
                ],
                "evidence_line_recall_at_10": longmemeval_ref["metrics"][
                    "evidence_line_recall_at_10"
                ],
                "context_visible_evidence_recall_at_10": longmemeval_ref["metrics"][
                    "context_visible_evidence_recall_at_10"
                ],
                "evidence_line_mrr": longmemeval_ref["metrics"]["evidence_line_mrr"],
                "exact_line_miss_taxonomy": longmemeval_ref["metrics"][
                    "exact_line_miss_taxonomy"
                ],
            },
            "privacy_boundary": longmemeval_ref["privacy_boundary"],
            "cannot_claim": longmemeval_ref["cannot_claim"],
        },
        "semantic_robustness_track_s": {
            "status": semantic["status"],
            "ok": bool(semantic["ok"]),
            "quality_gate_ok": bool(semantic["quality_gate_ok"]),
            "metrics": {
                "false_evidence_escalation_count": s1_metrics[
                    "false_evidence_escalation_count"
                ],
                "retrieval_invariance_top_k_survival_rate": s2_metrics[
                    "top_k_survival_rate"
                ],
                "hard_negative_suppression_rate": s3_metrics[
                    "hard_negative_suppression_rate"
                ],
                "explicit_negation_violation_count": s3_metrics[
                    "explicit_negation_violation_count"
                ],
                "source_evidence_over_escalation_count": s3_metrics[
                    "source_evidence_over_escalation_count"
                ],
                "stale_as_current_count": s3_metrics["stale_as_current_count"],
            },
            "privacy_boundary": semantic["privacy_boundary"],
            "cannot_claim": list(semantic.get("cannot_claim") or []),
        },
    }
    metrics = {
        "session_recall_at_10": longmemeval_ref["metrics"]["session_recall_at_10"],
        "evidence_line_recall_at_10": longmemeval_ref["metrics"][
            "evidence_line_recall_at_10"
        ],
        "context_visible_evidence_recall_at_10": longmemeval_ref["metrics"][
            "context_visible_evidence_recall_at_10"
        ],
        "session_mrr": longmemeval_ref["metrics"]["session_mrr"],
        "evidence_line_mrr": longmemeval_ref["metrics"]["evidence_line_mrr"],
        "context_visible_evidence_mrr": longmemeval_ref["metrics"][
            "context_visible_evidence_mrr"
        ],
        "evidence_recall_ladder": longmemeval_ref["metrics"]["evidence_recall_ladder"],
        "exact_line_miss_taxonomy": longmemeval_ref["metrics"][
            "exact_line_miss_taxonomy"
        ],
        "hard_negative_suppression": {
            "rate": s3_metrics["hard_negative_suppression_rate"],
            "source_evidence_over_escalation_count": s3_metrics[
                "source_evidence_over_escalation_count"
            ],
            "explicit_negation_violation_count": s3_metrics[
                "explicit_negation_violation_count"
            ],
        },
        "false_positive_proxy": {
            "false_evidence_escalation_count": s1_metrics[
                "false_evidence_escalation_count"
            ],
            "source_evidence_over_escalation_count": s3_metrics[
                "source_evidence_over_escalation_count"
            ],
        },
    }
    return {
        "status": "diagnostic_passed" if semantic["quality_gate_ok"] else "diagnostic_failed",
        "ok": bool(semantic["ok"]),
        "claim_boundary": (
            "Mis-recall axis distinguishes source-window routing from exact-line "
            "citation quality and pairs LongMemEval-S aggregate metrics with a "
            "public hard-negative/false-evidence suppression diagnostic."
        ),
        "metrics": metrics,
        "components": components,
        "cannot_claim": _unique_sorted(
            [
                *longmemeval_ref["cannot_claim"],
                *semantic.get("cannot_claim", []),
                "exact_line_citation_quality_solved",
                "private_history_quality",
                "live_answer_quality",
            ]
        ),
    }


def _pollution_axis() -> dict[str, Any]:
    knowledge = benchmark_knowledge_pollution.run_benchmark()
    auto_hook = auto_hook_pollution.run_auto_hook_pollution_fixture_report(
        include_private_text=False
    )
    knowledge_metrics = dict(knowledge["metrics"])
    auto_metrics = dict(auto_hook["metrics"])
    components = {
        "knowledge_pollution": {
            "status": knowledge["status"],
            "ok": bool(knowledge["ok"]),
            "quality_gate_ok": bool(knowledge["quality_gate_ok"]),
            "metrics": {
                "case_count": knowledge_metrics["case_count"],
                "contamination_escape_rate": knowledge_metrics[
                    "contamination_escape_rate"
                ],
                "stale_source_harm_rate": knowledge_metrics["stale_source_harm_rate"],
                "authority_override_rate": knowledge_metrics["authority_override_rate"],
                "privacy_partition_leak_rate": knowledge_metrics[
                    "privacy_partition_leak_rate"
                ],
                "unsupported_claim_rate": knowledge_metrics["unsupported_claim_rate"],
                "source_prompt_injection_escape_rate": knowledge_metrics[
                    "source_prompt_injection_escape_rate"
                ],
                "model_summary_as_truth_rate": knowledge_metrics[
                    "model_summary_as_truth_rate"
                ],
            },
            "privacy_boundary": knowledge["privacy_boundary"],
            "cannot_claim": list(knowledge.get("cannot_claim") or []),
        },
        "auto_hook_pollution": {
            "status": "fixture_report",
            "ok": bool(auto_hook["ok"]),
            "metrics": {
                "case_count": auto_metrics["case_count"],
                "passed_count": auto_metrics["passed_count"],
                "failed_count": auto_metrics["failed_count"],
                "pollution_family_counts": auto_metrics["pollution_family_counts"],
                "durable_memory_write_count": auto_metrics[
                    "durable_memory_write_count"
                ],
                "bounded_evidence_count": auto_metrics["bounded_evidence_count"],
                "source_backed_fact_count": auto_metrics["source_backed_fact_count"],
                "recalled_echo_reextraction_count": auto_metrics[
                    "recalled_echo_reextraction_count"
                ],
                "empty_message_memory_count": auto_metrics[
                    "empty_message_memory_count"
                ],
            },
            "privacy_boundary": auto_hook["privacy_boundary"],
            "cannot_claim": list(auto_hook.get("cannot_claim") or []),
        },
    }
    ok = bool(knowledge["ok"]) and bool(auto_hook["ok"])
    metrics = {
        "contamination_escape_rate": knowledge_metrics["contamination_escape_rate"],
        "stale_source_harm_rate": knowledge_metrics["stale_source_harm_rate"],
        "authority_override_rate": knowledge_metrics["authority_override_rate"],
        "privacy_partition_leak_rate": knowledge_metrics["privacy_partition_leak_rate"],
        "unsupported_claim_rate": knowledge_metrics["unsupported_claim_rate"],
        "auto_hook_pollution_family_counts": auto_metrics["pollution_family_counts"],
        "auto_hook_durable_memory_write_count": auto_metrics[
            "durable_memory_write_count"
        ],
        "auto_hook_bounded_evidence_count": auto_metrics["bounded_evidence_count"],
        "auto_hook_source_backed_fact_count": auto_metrics["source_backed_fact_count"],
        "auto_hook_recalled_echo_reextraction_count": auto_metrics[
            "recalled_echo_reextraction_count"
        ],
        "auto_hook_empty_message_memory_count": auto_metrics[
            "empty_message_memory_count"
        ],
    }
    return {
        "status": "fixture_gates_passed" if ok else "fixture_gate_failed",
        "ok": ok,
        "claim_boundary": (
            "Pollution axis covers public synthetic knowledge contamination, privacy "
            "partitioning, source-authority, and transcript/write-path pollution. It "
            "is not a live hook-write quality or private-history pollution rate."
        ),
        "metrics": metrics,
        "components": components,
        "cannot_claim": _unique_sorted(
            [
                *(knowledge.get("cannot_claim") or []),
                *(auto_hook.get("cannot_claim") or []),
                "live_hook_write_path_quality",
                "private_history_pollution_rate",
                "competitor_superiority",
            ]
        ),
    }


def _privacy_boundary() -> dict[str, Any]:
    return {
        "public_safe_default": True,
        "raw_private_text_emitted": False,
        "raw_longmemeval_text_emitted": False,
        "raw_fixture_text_emitted": False,
        "local_absolute_paths_emitted": False,
        "absolute_paths_emitted": False,
        "secrets_or_tokens_emitted": False,
        "external_model_payloads_emitted": False,
        "output_shape": "sanitized_aggregate_axis_report",
    }


def _review_next_actions() -> list[dict[str, Any]]:
    return [
        report_next_action(
            action_id="public_reliability_gauntlet_closed_owner_record",
            label="Treat closed gauntlet owner as historical",
            status="closed_historical",
            reason=(
                "#1102 and #2101 are closed/historical; this report is bounded "
                "evidence, not an active reliability-work queue."
            ),
            doc_path="docs/evidence/current-claims.md",
            owner_path=OWNER_PATH,
            issue_url=HISTORICAL_OWNER_ISSUE_URL,
            issue_state="closed_historical",
            no_open_followup_reason=NO_OPEN_FOLLOWUP_REASON,
            claim_boundary="owner_route_not_public_reliability_claim",
        ),
        report_next_action(
            action_id="rerun_public_reliability_gauntlet_json",
            label="Rerun public reliability gauntlet JSON",
            reason=(
                "Refresh the public-safe axis report before changing claim posture "
                "or writing a review packet."
            ),
            command=(
                "python benchmarks/aippocampus/benchmark_public_reliability_gauntlet.py --json"
            ),
            owner_path=OWNER_PATH,
            issue_url=HISTORICAL_OWNER_ISSUE_URL,
            issue_state="closed_historical",
            no_open_followup_reason=NO_OPEN_FOLLOWUP_REASON,
            claim_boundary="diagnostic_rerun_not_public_reliability_claim",
        ),
    ]


def _issue_actions() -> list[dict[str, Any]]:
    return [
        report_next_action(
            action_id="public_reliability_no_open_followup",
            label="No open public reliability follow-up",
            status="closed_historical",
            reason=(
                "The gauntlet boundaries are already routed into Current Claims; "
                "open a new scoped issue only when a concrete claim expansion is needed."
            ),
            doc_path="docs/evidence/current-claims.md",
            owner_path=OWNER_PATH,
            issue_url=HISTORICAL_OWNER_ISSUE_URL,
            issue_state="closed_historical",
            no_open_followup_reason=NO_OPEN_FOLLOWUP_REASON,
            claim_boundary="issue_triage_action_not_quality_evidence",
        )
    ]


def run_public_reliability_gauntlet(
    *,
    run_question_tracking: bool = True,
    run_segment_soak: bool = False,
) -> dict[str, Any]:
    started = time.perf_counter()
    longmemeval_ref = _longmemeval_s_500_reference()
    axes = {
        "runtime_stability": _runtime_axis(
            longmemeval_ref=longmemeval_ref,
            run_question_tracking=run_question_tracking,
            run_segment_soak=run_segment_soak,
        ),
        "mis_recall_quality": _mis_recall_axis(longmemeval_ref=longmemeval_ref),
        "pollution_hygiene": _pollution_axis(),
    }
    ok = all(bool(axis.get("ok")) for axis in axes.values())
    cannot_claim = _unique_sorted(
        [
            claim
            for axis in axes.values()
            for claim in list(axis.get("cannot_claim") or [])
        ]
        + [
            "single_aggregate_reliability_score",
            "private_history_quality",
            "real_gb_registry_runtime",
            "real_tb_registry_runtime",
            "longmemeval_qa_score",
            "exact_line_citation_quality_solved",
            "live_hook_write_path_quality",
            "competitor_superiority",
        ]
    )
    review_next_actions = _review_next_actions()
    issue_actions = _issue_actions()
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "aippocampus_public_reliability_gauntlet",
        "generated_at": now_utc(),
        "benchmark_maturity_level": "diagnostic_aggregate",
        "measurement_origin": "scripted_proxy",
        "observed_agent_behavior": False,
        "contract_gate_ok": ok,
        "public_quality_gate_ok": False,
        "quality_gate_ok": False,
        "decision_impact": "diagnostic_only",
        "decision_impact_gate_ok": False,
        "decision_impact_reason": (
            "public-safe aggregate axes are review input only; they do not close "
            "public reliability, private-history, or live-hook quality questions"
        ),
        "case_count": int(longmemeval_ref["metrics"]["question_count"]),
        "source_issue": HISTORICAL_SOURCE_ISSUE,
        "historical_source_issue": HISTORICAL_SOURCE_ISSUE,
        "historical_owner_issue_url": HISTORICAL_OWNER_ISSUE_URL,
        "owner_issue_state": "closed_historical",
        "no_open_followup_reason": NO_OPEN_FOLLOWUP_REASON,
        "owner_path": OWNER_PATH,
        "issue_refs": [
            {
                "issue_url": HISTORICAL_SOURCE_ISSUE,
                "issue_state": "closed_historical",
                "role": "historical_source",
            },
            {
                "issue_url": HISTORICAL_OWNER_ISSUE_URL,
                "issue_state": "closed_historical",
                "role": "historical_owner_action_route",
            },
        ],
        "status": "public_safe_gauntlet_passed_with_boundaries" if ok else "axis_failed",
        "ok": ok,
        "axis_names": list(axes),
        "axes": axes,
        "metrics": {
            "axis_count": len(axes),
            "longmemeval_question_count": longmemeval_ref["metrics"]["question_count"],
            "runtime_warning_count": axes["runtime_stability"]["metrics"][
                "warning_count"
            ],
            "runtime_blocker_count": axes["runtime_stability"]["metrics"][
                "blocker_count"
            ],
            "cannot_claim_count": len(cannot_claim),
        },
        "privacy_boundary": _privacy_boundary(),
        "claim_boundary": (
            "A public-safe reliability gate exists for runtime pressure, mis-recall "
            "diagnostics, and pollution hygiene. The axes are intentionally not "
            "collapsed into a single score."
        ),
        "supports": [
            "public-safe runtime, mis-recall, and pollution axes are reported separately",
            "closed historical source and owner issues are paired with an explicit no-open-followup reason",
        ],
        "useful_now": [
            "use as bounded evidence for Current Claims review",
            "keep aggregate reliability and private-history quality unclaimed",
        ],
        "agent_action": "open_current_claims_before_using_gauntlet_for_review",
        "can_claim": [
            "public_safe_gauntlet_axes_are_available",
            "axis_report_keeps_runtime_mis_recall_and_pollution_boundaries_separate",
        ],
        "material_limits": [
            "no single aggregate reliability score",
            "no private-history quality measurement",
            "no real GB/TB registry runtime proof",
        ],
        "review_next_actions": review_next_actions,
        "issue_actions": issue_actions,
        "cannot_claim": cannot_claim,
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
    }


def print_human_summary(payload: Mapping[str, Any]) -> None:
    print("AIppocampus public reliability gauntlet")
    print(f"- status: {payload['status']} ok: {payload['ok']}")
    for axis_name, axis in payload["axes"].items():
        print(f"- {axis_name}: {axis['status']}")
    print("- boundary: axes are separate; no aggregate reliability score")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", dest="json_output")
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--skip-question-tracking",
        action="store_true",
        help="Skip the synthetic question-tracking scale smoke for faster local checks.",
    )
    parser.add_argument(
        "--segment-soak",
        action="store_true",
        help="Also run the public-safe long-thread segmented-search physical-file soak.",
    )
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    payload = run_public_reliability_gauntlet(
        run_question_tracking=not args.skip_question_tracking,
        run_segment_soak=bool(args.segment_soak),
    )
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    if args.json_output:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print_human_summary(payload)
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
