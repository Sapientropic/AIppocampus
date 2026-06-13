#!/usr/bin/env python3
"""Real-history semantic scope-label smoke for Stage 2.

Default mode is observe-only: report whether dynamic semantic scope-label
sidecars already exist in the real registry, without calling an external model.

Live mode is explicit because it sends selected clean-source turns to the
configured DeepSeek-compatible backend. When `--write-sidecars` is used, the
script writes staging findings, materializes `semantic-scope-labels.jsonl`, and
refreshes `project_timeline.json`. Output stays aggregate-only.
"""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path
from typing import Any

import _paths

_paths.ensure_paths()

from benchmarks.aippocampus.shared.claim_boundary_refs import claim_boundary_ref
from smoke_life_wide_registry import coverage_ratios, dict_value, run_life_wide_registry_smoke

from aippocampus_runtime.core import (
    aippocampus_registry_dir,
    compact_text,
    deepseek_cache_metrics_from_usage,
)
from aippocampus_runtime.navigation.concept_graph import default_concept_graph_path
from aippocampus_runtime.navigation.project_timeline import (
    build_project_timeline,
    save_project_timeline,
)
from aippocampus_runtime.source.clean_source import SCOPE_LABEL_ORDER
from aippocampus_runtime.source.semantic_scope_builder import (
    build_semantic_scope_labels_for_registry,
)
from aippocampus_runtime.source.semantic_scope_evidence_diagnostics import (
    compact_label_evidence_metrics,
    public_semantic_evidence_diagnostics,
    semantic_evidence_diagnostics,
    with_semantic_evidence_diagnostics,
)
from aippocampus_runtime.subconscious.jobs import (
    DEFAULT_CONCURRENCY,
    DEFAULT_SAMPLES_PER_JOB,
    append_job_findings,
    default_jobs_output_path,
    run_jobs,
    run_one_job,
    run_tasks_in_sample_waves,
)
from aippocampus_runtime.subconscious.runtime import call_chat_json
from aippocampus_runtime.subconscious.worker import (
    DEFAULT_BASE_URL,
    DEFAULT_MODEL,
    default_project_timeline_path,
    default_staging_path,
)

DEFAULT_LIVE_CONCURRENCY = max(2, DEFAULT_CONCURRENCY)
DEFAULT_LIVE_SAMPLES_PER_JOB = max(2, DEFAULT_SAMPLES_PER_JOB)
DEFAULT_FULL_CANDIDATE_SOURCE_TURN_CAP = 5000
DEFAULT_CANDIDATE_BATCH_SIZE = 24
SEMANTIC_CANDIDATE_PROJECT_KEY = "stage2_life_wide_semantic_candidates"
SEMANTIC_CANDIDATE_PROJECT_LABEL = "Stage 2 life-wide semantic candidates"
PUBLIC_SMOKE_STATUSES = {
    "insufficient_dynamic_sidecar_rows",
    "insufficient_dynamic_sidecar_threads",
    "insufficient_timeline_semantic_turns",
    "sufficient",
    "live_model_missing_api_key",
    "live_model_failed",
    "live_model_partial_failure",
    "live_model_no_findings",
    "live_model_findings_observed",
    "materialization_empty",
    "incomplete_candidate_coverage",
}
PUBLIC_CLAIM_LEVELS = {
    "blocked_live_model",
    "diagnostic_only",
    "dynamic_semantic_sidecar_slice",
    "failed_live_model_slice",
    "fresh_live_model_findings_observed",
    "observed_dynamic_semantic_sidecar_slice",
}
PUBLIC_CANNOT_CLAIMS = (
    "full_history_refresh",
    "semantic_completeness",
    "label_correctness_without_clean_source_review",
    "fresh_live_model_run",
    "fresh_sidecar_write",
    "stage2_semantic_readiness",
)
PUBLIC_DYNAMIC_COUNT_KEYS = (
    "semantic_sidecar_threads",
    "semantic_sidecar_rows",
    "messages_with_semantic_scope_labels",
    "timeline_latest_turns_with_semantic_scope_labels",
)
PUBLIC_COVERAGE_RATIO_KEYS = (
    "labeled_message_ratio",
    "life_labeled_thread_ratio",
    "scope_labeled_thread_ratio",
    "semantic_sidecar_thread_ratio",
    "source_backed_timeline_turn_ratio",
    "semantic_timeline_turn_ratio",
)
PUBLIC_USAGE_KEYS = (
    "prompt_tokens",
    "completion_tokens",
    "total_tokens",
    "prompt_cache_hit_tokens",
    "prompt_cache_miss_tokens",
)
PUBLIC_SCOPE_LABELS = set(SCOPE_LABEL_ORDER)


def dynamic_counts(life_smoke: dict[str, Any]) -> dict[str, int]:
    artifacts = dict_value(life_smoke.get("artifact_counts"))
    timeline = dict_value(life_smoke.get("timeline_coverage"))
    return {
        "semantic_sidecar_threads": int(artifacts.get("semantic_sidecar_threads") or 0),
        "semantic_sidecar_rows": int(artifacts.get("semantic_sidecar_rows") or 0),
        "messages_with_semantic_scope_labels": int(
            artifacts.get("messages_with_semantic_scope_labels") or 0
        ),
        "timeline_latest_turns_with_semantic_scope_labels": int(
            timeline.get("latest_turns_with_semantic_scope_labels") or 0
        ),
    }


def semantic_status(
    counts: dict[str, int],
    *,
    min_sidecar_rows: int,
    min_sidecar_threads: int,
    min_timeline_turns: int,
) -> str:
    if counts.get("semantic_sidecar_rows", 0) < min_sidecar_rows:
        return "insufficient_dynamic_sidecar_rows"
    if counts.get("semantic_sidecar_threads", 0) < min_sidecar_threads:
        return "insufficient_dynamic_sidecar_threads"
    if counts.get("timeline_latest_turns_with_semantic_scope_labels", 0) < min_timeline_turns:
        return "insufficient_timeline_semantic_turns"
    return "sufficient"


def refresh_timeline(
    registry_path: Path, timeline_path: Path, *, max_turns_per_thread: int, max_per_life_label: int
) -> dict[str, Any]:
    timeline = build_project_timeline(
        registry_path,
        max_turns_per_thread=max_turns_per_thread,
        max_per_life_label=max_per_life_label,
    )
    save_project_timeline(timeline_path, timeline)
    life_wide = dict_value(timeline.get("life_wide"))
    return {
        "project_count": int(timeline.get("project_count") or 0),
        "life_label_count": int(life_wide.get("label_count") or 0),
        "wrote": True,
    }


def compact_job_result(result: dict[str, Any]) -> dict[str, Any]:
    jobs = [item for item in result.get("jobs") or [] if isinstance(item, dict)]
    failures = [item for item in jobs if item.get("ok") is False]
    return {
        "ok": bool(result.get("ok")),
        "job_count": int(result.get("job_count") or 0),
        "successful_job_count": int(result.get("successful_job_count") or 0),
        "failure_count": int(result.get("failure_count") or 0),
        "partial_failure": bool(result.get("partial_failure")),
        "concurrency": int(result.get("concurrency") or 0),
        "samples_per_job": int(result.get("samples_per_job") or 0),
        "finding_count": int(result.get("finding_count") or 0),
        "wrote": bool(result.get("wrote")),
        "cache": result.get("cache") or {},
        "usage": result.get("usage") or {},
        "label_evidence": compact_label_evidence_metrics(result),
        "first_error": compact_text(str((failures[0].get("error") if failures else "") or ""), 220),
    }


def compact_materialize_result(result: dict[str, Any] | None) -> dict[str, Any] | None:
    if not result:
        return None
    return {
        "ok": bool(result.get("ok")),
        "target_count": int(result.get("target_count") or 0),
        "row_count": int(result.get("row_count") or 0),
        "per_label_row_count": {
            str(label): int(count)
            for label, count in (result.get("per_label_row_count") or {}).items()
            if str(label) in PUBLIC_SCOPE_LABELS
        },
        "wrote": bool(result.get("wrote")),
        "boundary": "Semantic scope labels are navigation hints; clean source remains the source of truth.",
    }


def public_count(value: Any) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def public_float(value: Any) -> float:
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        return 0.0


def public_token(value: Any, *, allowed: set[str], fallback: str = "unknown") -> str:
    text = str(value or "").strip()
    return text if text in allowed else fallback


def public_claims(values: Any) -> list[str]:
    present = {str(value) for value in values or []}
    return [claim for claim in PUBLIC_CANNOT_CLAIMS if claim in present]


def public_dynamic_counts(counts: Any) -> dict[str, int]:
    if not isinstance(counts, dict):
        return {key: 0 for key in PUBLIC_DYNAMIC_COUNT_KEYS}
    return {key: public_count(counts.get(key)) for key in PUBLIC_DYNAMIC_COUNT_KEYS}


def public_coverage_ratios(ratios: Any) -> dict[str, Any]:
    if not isinstance(ratios, dict):
        ratios = {}
    return {
        **{key: public_float(ratios.get(key)) for key in PUBLIC_COVERAGE_RATIO_KEYS},
        "semantic_sidecar_row_count": public_count(ratios.get("semantic_sidecar_row_count")),
    }


def public_usage(usage: Any) -> dict[str, int]:
    if not isinstance(usage, dict):
        return {}
    return {key: public_count(usage.get(key)) for key in PUBLIC_USAGE_KEYS if key in usage}


def public_cache_presence(cache: Any) -> dict[str, bool]:
    return {"used": isinstance(cache, dict) and bool(cache)}


def public_label_list(values: Any) -> list[str]:
    return sorted(
        {str(value) for value in values or [] if str(value) in PUBLIC_SCOPE_LABELS}
    )


def public_label_counts(values: Any) -> dict[str, int]:
    if not isinstance(values, dict):
        return {}
    return {
        label: public_count(values.get(label))
        for label in SCOPE_LABEL_ORDER
        if label in values
    }


def public_label_evidence(metrics: Any) -> dict[str, Any]:
    if not isinstance(metrics, dict):
        return {}
    return {
        "finding_count_with_labels": public_count(metrics.get("finding_count_with_labels")),
        "accepted_label_count": public_count(metrics.get("accepted_label_count")),
        "labels_with_sufficient_evidence": public_count(
            metrics.get("labels_with_sufficient_evidence")
        ),
        "weak_or_missing_evidence_label_count": public_count(
            metrics.get("weak_or_missing_evidence_label_count")
        ),
        "label_evidence_complete": bool(metrics.get("label_evidence_complete")),
        "label_coverage": public_label_list(metrics.get("label_coverage")),
        "per_label_count": public_label_counts(metrics.get("per_label_count")),
        "per_label_sufficient_evidence_count": public_label_counts(
            metrics.get("per_label_sufficient_evidence_count")
        ),
        "per_label_weak_or_missing_evidence_count": public_label_counts(
            metrics.get("per_label_weak_or_missing_evidence_count")
        ),
    }


def public_job_result(job: Any) -> dict[str, Any] | None:
    if not isinstance(job, dict):
        return None
    return {
        "ok": bool(job.get("ok")),
        "job_count": public_count(job.get("job_count")),
        "successful_job_count": public_count(job.get("successful_job_count")),
        "failure_count": public_count(job.get("failure_count")),
        "partial_failure": bool(job.get("partial_failure")),
        "concurrency": public_count(job.get("concurrency")),
        "samples_per_job": public_count(job.get("samples_per_job")),
        "finding_count": public_count(job.get("finding_count")),
        "wrote": bool(job.get("wrote")),
        "cache": public_cache_presence(job.get("cache")),
        "usage": public_usage(job.get("usage")),
        "label_evidence": public_label_evidence(job.get("label_evidence")),
    }


def public_materialization(result: Any) -> dict[str, Any] | None:
    if not isinstance(result, dict):
        return None
    return {
        "ok": bool(result.get("ok")),
        "target_count": public_count(result.get("target_count")),
        "row_count": public_count(result.get("row_count")),
        "per_label_row_count": public_label_counts(result.get("per_label_row_count")),
        "wrote": bool(result.get("wrote")),
        "boundary": "semantic_scope_labels_are_navigation_hints_clean_source_is_truth",
    }


def public_candidate_coverage(coverage: Any) -> dict[str, Any] | None:
    if not isinstance(coverage, dict):
        return None
    return {
        "full_candidate_coverage_requested": bool(
            coverage.get("full_candidate_coverage_requested")
        ),
        "candidate_turn_count": public_count(coverage.get("candidate_turn_count")),
        "evaluated_candidate_turn_count": public_count(
            coverage.get("evaluated_candidate_turn_count")
        ),
        "unevaluated_candidate_turn_count": public_count(
            coverage.get("unevaluated_candidate_turn_count")
        ),
        "candidate_batch_size": public_count(coverage.get("candidate_batch_size")),
        "batch_count": public_count(coverage.get("batch_count")),
        "successful_batch_count": public_count(coverage.get("successful_batch_count")),
        "failed_batch_count": public_count(coverage.get("failed_batch_count")),
        "source_turn_cap": public_count(coverage.get("source_turn_cap")),
        "full_candidate_coverage_passed": bool(
            coverage.get("full_candidate_coverage_passed")
        ),
        "boundary": (
            "coverage_counts_only_selected_candidate_turns_were_sent_to_semantic_model"
        ),
    }


def public_timeline_refresh_item(item: Any) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    return {
        "wrote": bool(item.get("wrote")),
        "project_count": public_count(item.get("project_count")),
        "life_label_count": public_count(item.get("life_label_count")),
    }


def public_timeline_refresh(refresh: Any) -> dict[str, Any] | None:
    if not isinstance(refresh, dict):
        return None
    return {
        "before_live_job": public_timeline_refresh_item(refresh.get("before_live_job")),
        "after_materialization": public_timeline_refresh_item(
            refresh.get("after_materialization")
        ),
    }


def public_semantic_candidate_source(metrics: Any) -> dict[str, int]:
    if not isinstance(metrics, dict):
        return {}
    return {
        "candidate_turn_count": public_count(metrics.get("candidate_turn_count")),
        "candidate_thread_count": public_count(metrics.get("candidate_thread_count")),
        "skipped_already_semantic": public_count(metrics.get("skipped_already_semantic")),
        "skipped_without_refs": public_count(metrics.get("skipped_without_refs")),
        "limit_applied": public_count(metrics.get("limit_applied")),
    }


def public_thresholds(thresholds: Any) -> dict[str, Any]:
    if not isinstance(thresholds, dict):
        thresholds = {}
    return {
        "min_sidecar_rows": public_count(thresholds.get("min_sidecar_rows")),
        "min_sidecar_threads": public_count(thresholds.get("min_sidecar_threads")),
        "min_timeline_turns": public_count(thresholds.get("min_timeline_turns")),
        "require_labels": bool(thresholds.get("require_labels")),
        "full_candidate_coverage": bool(thresholds.get("full_candidate_coverage")),
        "candidate_batch_size": public_count(thresholds.get("candidate_batch_size")),
        "full_candidate_source_turn_cap": public_count(
            thresholds.get("full_candidate_source_turn_cap")
        ),
    }


def public_privacy_boundary(boundary: Any) -> dict[str, Any]:
    if not isinstance(boundary, dict):
        boundary = {}
    return {
        "raw_text_emitted": bool(boundary.get("raw_text_emitted")),
        "snippets_emitted": bool(boundary.get("snippets_emitted")),
        "titles_emitted": bool(boundary.get("titles_emitted")),
        "source_reference_details_emitted": bool(
            boundary.get("source_reference_details_emitted")
        ),
        "absolute_paths_emitted": bool(boundary.get("absolute_paths_emitted")),
        "external_model_call_requires_live_flag": bool(
            boundary.get("external_model_call_requires_live_flag")
        ),
        "live_mode_missing_api_key_fails": bool(
            boundary.get("live_mode_missing_api_key_fails")
        ),
        "live_mode_partial_failure_fails": bool(
            boundary.get("live_mode_partial_failure_fails")
        ),
        "output_shape": public_token(
            boundary.get("output_shape"),
            allowed={"aggregate_counts_only"},
            fallback="aggregate_counts_only",
        ),
    }


def public_smoke_result(result: dict[str, Any]) -> dict[str, Any]:
    """Project internal smoke details into the public CLI output contract.

    The internal smoke result may keep local diagnostics such as model-route
    configuration, failure text, source refs, and sidecar paths for tests and
    debugger use. The CLI is an evidence surface, so it exposes only allowlisted
    aggregate fields instead of trying to redact arbitrary semantic content.
    """

    return {
        "ok": bool(result.get("ok")),
        "stage2_semantic_sidecar_status": public_token(
            result.get("stage2_semantic_sidecar_status"),
            allowed=PUBLIC_SMOKE_STATUSES,
            fallback="unknown",
        ),
        "claim_level": public_token(
            result.get("claim_level"),
            allowed=PUBLIC_CLAIM_LEVELS,
            fallback="diagnostic_only",
        ),
        "claim_boundary_ref": claim_boundary_ref(
            "docs/evidence/readiness/stage-0-5-readiness.md"
        ),
        "cannot_claim": public_claims(result.get("cannot_claim")),
        "live_model_used": bool(result.get("live_model_used")),
        "sidecars_written": bool(result.get("sidecars_written")),
        "timeline_refreshed": bool(result.get("timeline_refreshed")),
        "privacy_boundary": public_privacy_boundary(result.get("privacy_boundary")),
        "before": public_dynamic_counts(result.get("before")),
        "after": public_dynamic_counts(result.get("after")),
        "coverage_ratios": public_coverage_ratios(result.get("coverage_ratios")),
        "job": public_job_result(result.get("job")),
        "materialization": public_materialization(result.get("materialization")),
        "candidate_coverage": public_candidate_coverage(result.get("candidate_coverage")),
        "timeline_refresh": public_timeline_refresh(result.get("timeline_refresh")),
        "semantic_candidate_source": public_semantic_candidate_source(
            result.get("semantic_candidate_source")
        ),
        "semantic_evidence_diagnostics": public_semantic_evidence_diagnostics(
            result.get("semantic_evidence_diagnostics")
            if isinstance(result.get("semantic_evidence_diagnostics"), dict)
            else semantic_evidence_diagnostics(result)
        ),
        "thresholds": public_thresholds(result.get("thresholds")),
        "output_boundary": "public_cli_json_omits_private_diagnostics",
    }


def semantic_claim_level(status: str, *, live: bool) -> str:
    if status == "live_model_missing_api_key":
        return "blocked_live_model"
    if status in {
        "live_model_failed",
        "live_model_partial_failure",
        "live_model_no_findings",
        "materialization_empty",
    }:
        return "failed_live_model_slice"
    if status == "sufficient":
        return (
            "dynamic_semantic_sidecar_slice" if live else "observed_dynamic_semantic_sidecar_slice"
        )
    if status == "live_model_findings_observed":
        return "fresh_live_model_findings_observed"
    return "diagnostic_only"


def semantic_cannot_claim(status: str, *, live: bool, write_sidecars: bool) -> list[str]:
    claims = [
        "full_history_refresh",
        "semantic_completeness",
        "label_correctness_without_clean_source_review",
    ]
    if not live or status == "live_model_missing_api_key":
        claims.append("fresh_live_model_run")
    if live and not write_sidecars:
        claims.append("fresh_sidecar_write")
    if status != "sufficient":
        claims.append("stage2_semantic_readiness")
    return claims


def turn_identity(turn: dict[str, Any]) -> str:
    refs = [
        str(ref.get("message_id") or "")
        for ref in turn.get("source_refs") or []
        if isinstance(ref, dict) and ref.get("message_id")
    ]
    ref_part = ",".join(refs)
    return "|".join(
        [
            str(turn.get("thread_key") or ""),
            str(turn.get("turn_id") or ""),
            ref_part,
        ]
    )


def semantic_candidate_timeline_from_life_wide(
    timeline: dict[str, Any], *, max_turns: int | None
) -> dict[str, Any]:
    life_wide = dict_value(timeline.get("life_wide"))
    label_groups = dict_value(life_wide.get("labels"))
    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()
    skipped_already_semantic = 0
    skipped_without_refs = 0
    limit = None if max_turns is None or int(max_turns) <= 0 else max(1, int(max_turns))
    for group in label_groups.values():
        if not isinstance(group, dict):
            continue
        for turn in group.get("latest_turns") or []:
            if not isinstance(turn, dict):
                continue
            if turn.get("semantic_scope_labels"):
                skipped_already_semantic += 1
                continue
            if not turn.get("source_refs"):
                skipped_without_refs += 1
                continue
            identity = turn_identity(turn)
            if not identity.strip("|,") or identity in seen:
                continue
            seen.add(identity)
            item = dict(turn)
            item["project_key"] = SEMANTIC_CANDIDATE_PROJECT_KEY
            item["project_label"] = SEMANTIC_CANDIDATE_PROJECT_LABEL
            candidates.append(item)
            if limit is not None and len(candidates) >= limit:
                break
        if limit is not None and len(candidates) >= limit:
            break

    return {
        "schema_version": 1,
        "kind": "aippocampus_semantic_candidate_timeline",
        "projects": {
            SEMANTIC_CANDIDATE_PROJECT_KEY: {
                "project_key": SEMANTIC_CANDIDATE_PROJECT_KEY,
                "project_label": SEMANTIC_CANDIDATE_PROJECT_LABEL,
                "project_tags": ["stage2", "life-wide", "semantic-scope"],
                "thread_count": len(
                    {turn.get("thread_key") for turn in candidates if turn.get("thread_key")}
                ),
                "latest_turns": candidates,
            }
        },
        "candidate_metrics": {
            "candidate_turn_count": len(candidates),
            "candidate_thread_count": len(
                {turn.get("thread_key") for turn in candidates if turn.get("thread_key")}
            ),
            "skipped_already_semantic": skipped_already_semantic,
            "skipped_without_refs": skipped_without_refs,
            "limit_applied": limit,
        },
    }


def semantic_candidate_turns(candidate_timeline: dict[str, Any]) -> list[dict[str, Any]]:
    project = (candidate_timeline.get("projects") or {}).get(SEMANTIC_CANDIDATE_PROJECT_KEY)
    if not isinstance(project, dict):
        return []
    return [turn for turn in project.get("latest_turns") or [] if isinstance(turn, dict)]


def candidate_timeline_for_turns(turns: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "kind": "aippocampus_semantic_candidate_batch_timeline",
        "projects": {
            SEMANTIC_CANDIDATE_PROJECT_KEY: {
                "project_key": SEMANTIC_CANDIDATE_PROJECT_KEY,
                "project_label": SEMANTIC_CANDIDATE_PROJECT_LABEL,
                "project_tags": ["stage2", "life-wide", "semantic-scope", "candidate-batch"],
                "thread_count": len(
                    {turn.get("thread_key") for turn in turns if turn.get("thread_key")}
                ),
                "latest_turns": turns,
            }
        },
    }


def merge_usage_totals(target: dict[str, Any], usage: dict[str, Any]) -> None:
    for key, value in (usage or {}).items():
        if isinstance(value, (int, float)):
            target[key] = target.get(key, 0) + value
        elif key not in target:
            target[key] = value


def batch_candidate_coverage(
    *,
    candidate_turn_count: int,
    batch_sizes: list[int],
    successful_batch_indexes: set[int],
    failed_batch_indexes: set[int],
    full_candidate_coverage: bool,
    candidate_batch_size: int,
    source_turn_cap: int,
) -> dict[str, Any]:
    evaluated = sum(
        batch_sizes[index] for index in successful_batch_indexes if 0 <= index < len(batch_sizes)
    )
    unevaluated = max(0, int(candidate_turn_count) - int(evaluated))
    return {
        "full_candidate_coverage_requested": bool(full_candidate_coverage),
        "candidate_turn_count": int(candidate_turn_count),
        "evaluated_candidate_turn_count": int(evaluated),
        "unevaluated_candidate_turn_count": int(unevaluated),
        "candidate_batch_size": int(candidate_batch_size),
        "batch_count": len(batch_sizes),
        "successful_batch_count": len(successful_batch_indexes),
        "failed_batch_count": len(failed_batch_indexes),
        "source_turn_cap": int(source_turn_cap),
        "full_candidate_coverage_passed": bool(
            full_candidate_coverage and unevaluated == 0 and not failed_batch_indexes
        ),
        "boundary": "Coverage means every selected candidate turn was sent to the semantic model; it does not mean every candidate deserved a label.",
    }


def run_candidate_batches(
    *,
    registry_path: Path,
    concept_graph_path: Path,
    jobs_output_path: Path,
    edges_output_path: Path,
    candidate_timeline: dict[str, Any],
    objective: str,
    max_steps: int,
    min_tool_steps: int,
    model: str,
    base_url: str,
    api_key: str,
    max_tokens: int | None,
    timeout: int,
    concurrency: int,
    samples_per_job: int,
    candidate_batch_size: int,
    write_sidecars: bool,
    chat_fn,
) -> dict[str, Any]:
    """Run semantic labeling across candidate batches.

    Full life-wide candidate sets can be too large for one prompt. Batching keeps
    each DeepSeek request bounded while preserving a simple audit claim: every
    selected candidate turn was actually presented to at least one successful
    model call. Writes are serialized after concurrent model calls so JSONL
    staging cannot interleave.
    """

    turns = semantic_candidate_turns(candidate_timeline)
    batch_size = max(1, int(candidate_batch_size or DEFAULT_CANDIDATE_BATCH_SIZE))
    batches = [turns[index : index + batch_size] for index in range(0, len(turns), batch_size)]
    sample_total = max(1, int(samples_per_job))
    task_specs = [
        {
            "index": batch_index * sample_total + sample_index,
            "batch_index": batch_index,
            "sample_index": sample_index + 1,
            "sample_count": sample_total,
            "turn_count": len(batch),
        }
        for batch_index, batch in enumerate(batches)
        for sample_index in range(sample_total)
    ]
    usage_total: dict[str, Any] = {}
    successful_batch_indexes: set[int] = set()
    failed_batch_indexes: set[int] = set()

    def failed_result(task: dict[str, int], exc: BaseException) -> dict[str, Any]:
        return {
            "ok": False,
            "dry_run": False,
            "job": "semantic_scope_labeling",
            "sample_index": task["sample_index"],
            "sample_count": task["sample_count"],
            "model": model,
            "turn_count": task["turn_count"],
            "finding_count": 0,
            "edge_count": 0,
            "findings": [],
            "tool_steps": [],
            "final_attempts": [],
            "usage": {},
            "jobs_output": str(jobs_output_path),
            "edges_output": str(edges_output_path),
            "wrote": False,
            "deferred_write": False,
            "batch_index": task["batch_index"],
            "candidate_turn_count": task["turn_count"],
            "error": compact_text(f"{type(exc).__name__}: {exc}", 500),
        }

    with tempfile.TemporaryDirectory(prefix="aippocampus-semantic-batches-") as tmp:
        tmp_root = Path(tmp)
        timeline_paths: list[Path] = []
        for batch_index, batch in enumerate(batches):
            path = tmp_root / f"candidate_batch_{batch_index}.json"
            path.write_text(
                json.dumps(candidate_timeline_for_turns(batch), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            timeline_paths.append(path)

        def run_task(task: dict[str, int]) -> dict[str, Any]:
            result = run_one_job(
                job="semantic_scope_labeling",
                registry_path=registry_path,
                timeline_path=timeline_paths[task["batch_index"]],
                concept_graph_path=concept_graph_path,
                jobs_output_path=jobs_output_path,
                edges_output_path=edges_output_path,
                project=None,
                objective=objective,
                max_turns=0,
                max_steps=max_steps,
                min_tool_steps=min_tool_steps,
                model=model,
                base_url=base_url,
                api_key=api_key,
                max_tokens=max_tokens,
                timeout=timeout,
                temperature=0.2,
                chat_fn=chat_fn or call_chat_json,
                no_write=False,
                defer_writes=True,
                sample_index=task["sample_index"],
                sample_count=task["sample_count"],
            )
            result["batch_index"] = task["batch_index"]
            result["candidate_turn_count"] = task["turn_count"]
            return result

        max_workers = min(max(1, int(concurrency)), max(1, len(task_specs)))
        indexed_results = run_tasks_in_sample_waves(
            task_specs,
            max_workers=max_workers,
            run_task=run_task,
            failed_task=failed_result,
        )

    indexed_results.sort(key=lambda item: item[0])
    results = [result for _, result in indexed_results]
    for result in results:
        batch_index = int(result.get("batch_index") or 0)
        if result.get("ok") is False:
            failed_batch_indexes.add(batch_index)
            continue
        successful_batch_indexes.add(batch_index)
        merge_usage_totals(usage_total, result.get("usage") or {})
        if write_sidecars:
            append_job_findings(
                jobs_output_path,
                result.get("findings") or [],
                model=model,
                batch_id=str(result.get("batch_id") or ""),
                usage=result.get("usage") or {},
            )
            result["wrote"] = True
            result["deferred_write"] = False
    failed_batch_indexes.difference_update(successful_batch_indexes)
    successful_count = sum(1 for result in results if result.get("ok") is not False)
    failure_count = sum(1 for result in results if result.get("ok") is False)
    return {
        "ok": successful_count > 0 or not task_specs,
        "jobs": results,
        "job_count": len(results),
        "successful_job_count": successful_count,
        "failure_count": failure_count,
        "partial_failure": failure_count > 0 and successful_count > 0,
        "requested_job_count": 1,
        "samples_per_job": sample_total,
        "concurrency": min(max(1, int(concurrency)), max(1, len(task_specs))),
        "finding_count": sum(int(result.get("finding_count") or 0) for result in results),
        "edge_count": 0,
        "usage": usage_total,
        "cache": deepseek_cache_metrics_from_usage(usage_total),
        "jobs_output": str(jobs_output_path),
        "edges_output": str(edges_output_path),
        "wrote": bool(write_sidecars and successful_count > 0),
        "candidate_batches": {
            "batch_sizes": [len(batch) for batch in batches],
            "successful_batch_indexes": sorted(successful_batch_indexes),
            "failed_batch_indexes": sorted(failed_batch_indexes),
        },
    }


def life_smoke_coverage_ratios(life_smoke: dict[str, Any]) -> dict[str, Any]:
    return coverage_ratios(
        {
            "artifact_counts": life_smoke.get("artifact_counts")
            if isinstance(life_smoke.get("artifact_counts"), dict)
            else {},
        },
        life_smoke.get("timeline_coverage")
        if isinstance(life_smoke.get("timeline_coverage"), dict)
        else None,
    )


def run_semantic_scope_real_history_smoke(
    *,
    registry_path: str | Path | None = None,
    timeline_path: str | Path | None = None,
    jobs_output_path: str | Path | None = None,
    edges_output_path: str | Path | None = None,
    live: bool = False,
    write_sidecars: bool = False,
    require_labels: bool = False,
    api_key_env: str = "DEEPSEEK_API_KEY",
    project: str | None = None,
    max_turns: int = 24,
    max_steps: int = 2,
    min_tool_steps: int = 0,
    max_tokens: int | None = 1800,
    timeout: int = 120,
    concurrency: int = DEFAULT_LIVE_CONCURRENCY,
    samples_per_job: int = DEFAULT_LIVE_SAMPLES_PER_JOB,
    model: str = DEFAULT_MODEL,
    base_url: str = DEFAULT_BASE_URL,
    min_sidecar_rows: int = 1,
    min_sidecar_threads: int = 1,
    min_timeline_turns: int = 1,
    full_candidate_coverage: bool = False,
    candidate_batch_size: int = 0,
    full_candidate_source_turn_cap: int = DEFAULT_FULL_CANDIDATE_SOURCE_TURN_CAP,
    chat_fn=None,
) -> dict[str, Any]:
    registry = (
        Path(registry_path).resolve()
        if registry_path
        else (aippocampus_registry_dir() / "threads.json").resolve()
    )
    timeline = (
        Path(timeline_path).resolve()
        if timeline_path
        else default_project_timeline_path(registry_path=registry)
    )
    jobs_output = (
        Path(jobs_output_path).resolve()
        if jobs_output_path
        else default_jobs_output_path(registry_path=registry)
    )
    edges_output = (
        Path(edges_output_path).resolve()
        if edges_output_path
        else default_staging_path(registry_path=registry)
    )
    concept_graph = default_concept_graph_path(registry_path=registry)

    privacy_boundary = {
        "raw_text_emitted": False,
        "snippets_emitted": False,
        "titles_emitted": False,
        "source_reference_details_emitted": False,
        "absolute_paths_emitted": False,
        "external_model_call_requires_live_flag": True,
        "live_mode_missing_api_key_fails": True,
        "live_mode_partial_failure_fails": True,
        "output_shape": "aggregate_counts_only",
    }
    if write_sidecars:
        live = True

    before_life = run_life_wide_registry_smoke(
        registry,
        compute_timeline=True,
        require_evidence=False,
        max_turns_per_thread=max_turns,
        max_per_life_label=20,
    )
    before_counts = dynamic_counts(before_life)
    status_before = semantic_status(
        before_counts,
        min_sidecar_rows=min_sidecar_rows,
        min_sidecar_threads=min_sidecar_threads,
        min_timeline_turns=min_timeline_turns,
    )
    if not live:
        return with_semantic_evidence_diagnostics({
            "ok": status_before == "sufficient" or not require_labels,
            "stage2_semantic_sidecar_status": status_before,
            "claim_level": semantic_claim_level(status_before, live=False),
            "claim_boundary_ref": claim_boundary_ref(
                "docs/evidence/readiness/stage-0-5-readiness.md"
            ),
            "cannot_claim": semantic_cannot_claim(status_before, live=False, write_sidecars=False),
            "live_model_used": False,
            "sidecars_written": False,
            "timeline_refreshed": False,
            "privacy_boundary": privacy_boundary,
            "before": before_counts,
            "after": before_counts,
            "coverage_ratios": life_smoke_coverage_ratios(before_life),
            "job": None,
            "materialization": None,
            "candidate_coverage": None,
            "thresholds": {
                "min_sidecar_rows": min_sidecar_rows,
                "min_sidecar_threads": min_sidecar_threads,
                "min_timeline_turns": min_timeline_turns,
                "require_labels": require_labels,
                "full_candidate_coverage": full_candidate_coverage,
                "candidate_batch_size": candidate_batch_size,
            },
        })

    api_key = os.environ.get(api_key_env)
    if not api_key:
        status = "live_model_missing_api_key"
        return with_semantic_evidence_diagnostics({
            "ok": False,
            "stage2_semantic_sidecar_status": status,
            "claim_level": semantic_claim_level(status, live=True),
            "claim_boundary_ref": claim_boundary_ref(
                "docs/evidence/readiness/stage-0-5-readiness.md"
            ),
            "cannot_claim": semantic_cannot_claim(status, live=True, write_sidecars=write_sidecars),
            "live_model_used": False,
            "sidecars_written": False,
            "timeline_refreshed": False,
            "privacy_boundary": privacy_boundary,
            "before": before_counts,
            "after": before_counts,
            "coverage_ratios": life_smoke_coverage_ratios(before_life),
            "job": None,
            "materialization": None,
            "candidate_coverage": None,
            "thresholds": {
                "min_sidecar_rows": min_sidecar_rows,
                "min_sidecar_threads": min_sidecar_threads,
                "min_timeline_turns": min_timeline_turns,
                "require_labels": require_labels,
                "full_candidate_coverage": full_candidate_coverage,
                "candidate_batch_size": candidate_batch_size,
            },
        })

    source_turn_cap = max(
        1, int(full_candidate_source_turn_cap if full_candidate_coverage else max_turns)
    )
    refresh_before = refresh_timeline(
        registry,
        timeline,
        max_turns_per_thread=source_turn_cap,
        max_per_life_label=max(20, source_turn_cap),
    )
    semantic_candidate_metrics = None
    candidate_coverage = None
    job_timeline_path = timeline
    candidate_temp = None
    candidate_timeline = None
    if project is None:
        candidate_timeline = semantic_candidate_timeline_from_life_wide(
            build_project_timeline(
                registry,
                max_turns_per_thread=source_turn_cap,
                max_per_life_label=max(20, source_turn_cap),
            ),
            max_turns=None if full_candidate_coverage else max_turns,
        )
        semantic_candidate_metrics = candidate_timeline.get("candidate_metrics")
        if int((semantic_candidate_metrics or {}).get("candidate_turn_count") or 0) > 0:
            candidate_temp = tempfile.TemporaryDirectory(prefix="aippocampus-semantic-candidates-")
            job_timeline_path = Path(candidate_temp.name) / "project_timeline.json"
            job_timeline_path.write_text(
                json.dumps(candidate_timeline, ensure_ascii=False, indent=2), encoding="utf-8"
            )
    objective = (
        "Label real-history clean-source turns that are semantically life-wide, casual-important, "
        "or idea-evolution material. Prefer dynamic semantic judgments over lexical keyword matches. "
        "Use only canonical scope labels and exact source-backed message refs."
    )
    try:
        use_candidate_batches = bool(
            project is None and candidate_timeline and full_candidate_coverage
        )
        if use_candidate_batches:
            assert candidate_timeline is not None
            job_result = run_candidate_batches(
                registry_path=registry,
                concept_graph_path=concept_graph,
                jobs_output_path=jobs_output,
                edges_output_path=edges_output,
                candidate_timeline=candidate_timeline,
                objective=objective,
                max_steps=max_steps,
                min_tool_steps=min_tool_steps,
                model=model,
                base_url=base_url,
                api_key=api_key,
                max_tokens=max_tokens,
                timeout=timeout,
                concurrency=concurrency,
                samples_per_job=samples_per_job,
                candidate_batch_size=candidate_batch_size or DEFAULT_CANDIDATE_BATCH_SIZE,
                write_sidecars=write_sidecars,
                chat_fn=chat_fn or call_chat_json,
            )
            batches = (
                (job_result.get("candidate_batches") or {})
                if isinstance(job_result.get("candidate_batches"), dict)
                else {}
            )
            candidate_coverage = batch_candidate_coverage(
                candidate_turn_count=int(
                    (semantic_candidate_metrics or {}).get("candidate_turn_count") or 0
                ),
                batch_sizes=[int(value) for value in batches.get("batch_sizes") or []],
                successful_batch_indexes={
                    int(value) for value in batches.get("successful_batch_indexes") or []
                },
                failed_batch_indexes={
                    int(value) for value in batches.get("failed_batch_indexes") or []
                },
                full_candidate_coverage=full_candidate_coverage,
                candidate_batch_size=candidate_batch_size or DEFAULT_CANDIDATE_BATCH_SIZE,
                source_turn_cap=source_turn_cap,
            )
        else:
            job_result = run_jobs(
                jobs=["semantic_scope_labeling"],
                registry_path=registry,
                timeline_path=job_timeline_path,
                concept_graph_path=concept_graph,
                jobs_output_path=jobs_output,
                edges_output_path=edges_output,
                project=project,
                objective=objective,
                max_turns=max_turns,
                max_steps=max_steps,
                min_tool_steps=min_tool_steps,
                model=model,
                base_url=base_url,
                api_key=api_key,
                max_tokens=max_tokens,
                timeout=timeout,
                temperature=0.2,
                concurrency=concurrency,
                samples_per_job=samples_per_job,
                dry_run=False,
                no_write=not write_sidecars,
                chat_fn=chat_fn or call_chat_json,
            )
    finally:
        if candidate_temp is not None:
            candidate_temp.cleanup()
    materialized = None
    refresh_after = None
    if write_sidecars and int(job_result.get("finding_count") or 0) > 0:
        materialized = build_semantic_scope_labels_for_registry(
            registry_path=registry,
            jobs_output_path=jobs_output,
            project=project,
            no_write=False,
        )
        refresh_after = refresh_timeline(
            registry,
            timeline,
            max_turns_per_thread=source_turn_cap,
            max_per_life_label=max(20, source_turn_cap),
        )

    after_life = run_life_wide_registry_smoke(
        registry,
        compute_timeline=True,
        require_evidence=False,
        max_turns_per_thread=max_turns,
        max_per_life_label=20,
    )
    after_counts = dynamic_counts(after_life)
    status_after = semantic_status(
        after_counts,
        min_sidecar_rows=min_sidecar_rows,
        min_sidecar_threads=min_sidecar_threads,
        min_timeline_turns=min_timeline_turns,
    )
    failure_count = int(job_result.get("failure_count") or 0)
    successful_count = int(job_result.get("successful_job_count") or 0)
    finding_count = int(job_result.get("finding_count") or 0)
    if failure_count > 0 and successful_count <= 0:
        status_after = "live_model_failed"
    elif failure_count > 0:
        status_after = "live_model_partial_failure"
    elif finding_count <= 0:
        status_after = "live_model_no_findings"
    elif write_sidecars and (not materialized or int(materialized.get("row_count") or 0) <= 0):
        status_after = "materialization_empty"
    elif not write_sidecars and status_after != "sufficient":
        status_after = "live_model_findings_observed"
    elif (
        full_candidate_coverage
        and candidate_coverage
        and int(candidate_coverage.get("unevaluated_candidate_turn_count") or 0) > 0
    ):
        status_after = "incomplete_candidate_coverage"

    if not live:
        ok = status_after == "sufficient" or not require_labels
    elif write_sidecars:
        ok = status_after == "sufficient" and (
            not full_candidate_coverage
            or bool((candidate_coverage or {}).get("full_candidate_coverage_passed"))
        )
    else:
        ok = status_after == "sufficient" or status_after == "live_model_findings_observed"

    return with_semantic_evidence_diagnostics({
        "ok": ok,
        "stage2_semantic_sidecar_status": status_after,
        "claim_level": semantic_claim_level(status_after, live=True),
        "claim_boundary_ref": claim_boundary_ref(
            "docs/evidence/readiness/stage-0-5-readiness.md"
        ),
        "cannot_claim": semantic_cannot_claim(
            status_after, live=True, write_sidecars=write_sidecars
        ),
        "live_model_used": True,
        "sidecars_written": bool(write_sidecars and materialized and materialized.get("wrote")),
        "timeline_refreshed": bool(refresh_after),
        "privacy_boundary": privacy_boundary,
        "before": before_counts,
        "after": after_counts,
        "coverage_ratios": life_smoke_coverage_ratios(after_life),
        "job": compact_job_result(job_result),
        "materialization": compact_materialize_result(materialized),
        "candidate_coverage": candidate_coverage,
        "timeline_refresh": {
            "before_live_job": refresh_before,
            "after_materialization": refresh_after,
        },
        "semantic_candidate_source": semantic_candidate_metrics,
        "thresholds": {
            "min_sidecar_rows": min_sidecar_rows,
            "min_sidecar_threads": min_sidecar_threads,
            "min_timeline_turns": min_timeline_turns,
            "require_labels": require_labels,
            "full_candidate_coverage": full_candidate_coverage,
            "candidate_batch_size": candidate_batch_size
            or (DEFAULT_CANDIDATE_BATCH_SIZE if full_candidate_coverage else 0),
            "full_candidate_source_turn_cap": source_turn_cap,
        },
    })


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry")
    parser.add_argument("--timeline")
    parser.add_argument("--jobs-output")
    parser.add_argument("--edges-output")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--write-sidecars", action="store_true")
    parser.add_argument("--require-labels", action="store_true")
    parser.add_argument("--api-key-env", default="DEEPSEEK_API_KEY")
    parser.add_argument("--project")
    parser.add_argument("--max-turns", type=int, default=24)
    parser.add_argument("--max-steps", type=int, default=2)
    parser.add_argument("--min-tool-steps", type=int, default=0)
    parser.add_argument("--max-tokens", type=int, default=1800)
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--concurrency", type=int, default=DEFAULT_LIVE_CONCURRENCY)
    parser.add_argument("--samples-per-job", type=int, default=DEFAULT_LIVE_SAMPLES_PER_JOB)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--min-sidecar-rows", type=int, default=1)
    parser.add_argument("--min-sidecar-threads", type=int, default=1)
    parser.add_argument("--min-timeline-turns", type=int, default=1)
    parser.add_argument(
        "--full-candidate-coverage",
        action="store_true",
        help="Evaluate every currently selected unlabeled life-wide candidate turn.",
    )
    parser.add_argument(
        "--candidate-batch-size",
        type=int,
        default=0,
        help="Turn count per semantic candidate batch when --full-candidate-coverage is used.",
    )
    parser.add_argument(
        "--full-candidate-source-turn-cap", type=int, default=DEFAULT_FULL_CANDIDATE_SOURCE_TURN_CAP
    )
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args()

    result = run_semantic_scope_real_history_smoke(
        registry_path=args.registry,
        timeline_path=args.timeline,
        jobs_output_path=args.jobs_output,
        edges_output_path=args.edges_output,
        live=args.live,
        write_sidecars=args.write_sidecars,
        require_labels=args.require_labels,
        api_key_env=args.api_key_env,
        project=args.project,
        max_turns=args.max_turns,
        max_steps=args.max_steps,
        min_tool_steps=args.min_tool_steps,
        max_tokens=args.max_tokens,
        timeout=args.timeout,
        concurrency=args.concurrency,
        samples_per_job=args.samples_per_job,
        model=args.model,
        base_url=args.base_url,
        min_sidecar_rows=args.min_sidecar_rows,
        min_sidecar_threads=args.min_sidecar_threads,
        min_timeline_turns=args.min_timeline_turns,
        full_candidate_coverage=args.full_candidate_coverage,
        candidate_batch_size=args.candidate_batch_size,
        full_candidate_source_turn_cap=args.full_candidate_source_turn_cap,
    )
    public_result = public_smoke_result(result)
    if args.json_output:
        print(json.dumps(public_result, ensure_ascii=False, indent=2))
    else:
        print(
            "semantic scope real-history smoke: "
            f"{public_result.get('stage2_semantic_sidecar_status')}"
        )
        print(f"ok: {public_result.get('ok')}")
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
