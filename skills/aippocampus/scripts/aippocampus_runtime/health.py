#!/usr/bin/env python3
"""Report health and recommended maintenance for a long Codex thread."""

from __future__ import annotations

import argparse
import importlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PureWindowsPath
from time import perf_counter
from typing import Any, Mapping

from aippocampus_runtime.artifacts.publish import (
    segment_generation_diagnostics,
)
from aippocampus_runtime.cli.errors import cli_exit_code_for_error_code
from aippocampus_runtime.command_policy import current_python_command, quote_posix_double
from aippocampus_runtime.core import (
    file_sha256,
    parse_anchor_file,
)
from aippocampus_runtime.first_recall_readiness import (
    missing_rollout_readiness_fields,
)
from aippocampus_runtime.health_actions import action, dependency_ordered_actions
from aippocampus_runtime.health_background_cognition import background_cognition_health
from aippocampus_runtime.health_freshness import rollout_visibility_stats
from aippocampus_runtime.health_host_state import codex_host_state_confounds
from aippocampus_runtime.health_recall_availability import (
    build_product_readiness,
    operator_detail_placeholder,
)
from aippocampus_runtime.health_registry import registry_health_report
from aippocampus_runtime.health_render import render_health_text, render_registry_health_text
from aippocampus_runtime.health_stages import (
    activity_class,
    age_seconds_since,
    evaluate_index_state,
    resolve_health_inputs,
)
from aippocampus_runtime.health_trajectory import attach_health_trajectory
from aippocampus_runtime.mcp.public_projection import compact_health_payload
from aippocampus_runtime.ops import log_retention
from aippocampus_runtime.ops.storage_governance_contract import human_bytes
from aippocampus_runtime.privacy import (
    LOCAL_PATH_REDACTION,
    redact_private_paths,
    redact_sensitive_values,
)
from aippocampus_runtime.question.constants import DEFAULT_DORMANT_AFTER_DAYS
from aippocampus_runtime.source.io_kernel import load_json_dict
from aippocampus_runtime.source.source_intake_health import clean_source_health_summaries

DEFAULT_JOBS_OUTPUT_NAME = "subconscious_jobs.jsonl"
STORAGE_PRESSURE_RECLAIMABLE_BYTES = 512 * 1024 * 1024
STORAGE_PRESSURE_AMPLIFICATION_RATIO = 10.0
STORAGE_PRESSURE_CANDIDATE_COUNT = 100
HEALTH_GENERATION_GC_CANDIDATE_LIMIT = 12
STORAGE_GC_BOUNDED_DETAIL_COMMAND = "aippocampus storage gc --dry-run --json --top 1 --cwd ."
STORAGE_GC_FULL_DETAIL_COMMAND = "aippocampus storage gc --dry-run --json --full --cwd ."
DEFAULT_OPERATOR_DIAGNOSTIC_TIMEOUT_MS = 5000
EXPENSIVE_OPERATOR_DIAGNOSTIC_TIMEOUT_MS = 30000
DEFAULT_SLOW_HEALTH_SECTION_MS = 250


@dataclass(frozen=True)
class HealthOptions:
    cwd: str | Path
    index_dir: str | Path | None = None
    anchors: str | Path = "thread-anchors.md"
    graphify_corpus: str | Path | None = None
    segments_dir: str | Path | None = None
    checkpoint_state: str | Path | None = None
    clean_source_dir: str | Path | None = None
    registry: str | Path | None = None
    registry_dir: str | Path | None = None
    jobs_output: str | Path | None = None
    include_question_stats: bool = False
    question_stats_details: bool = False
    question_dormant_days: int = DEFAULT_DORMANT_AFTER_DAYS
    max_stale_messages: int = 25
    max_stale_bytes: int = 5 * 1024 * 1024
    live_delta_tolerance_messages: int = 1
    max_log_bytes: int | None = None
    checkpoint_messages: int = 30
    deep_graph_messages: int = 1000
    deep_graph_bytes: int = 100 * 1024 * 1024
    segment_threshold_bytes: int = 100 * 1024 * 1024
    include_operator_diagnostics: bool = False
    include_expensive_diagnostics: bool = False
    operator_timeout_ms: int = DEFAULT_OPERATOR_DIAGNOSTIC_TIMEOUT_MS
    slow_section_threshold_ms: int = DEFAULT_SLOW_HEALTH_SECTION_MS

def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def safe_stat_size(path: Path | None, default: int = 0) -> int:
    if path is None:
        return default
    try:
        return path.stat().st_size if path.exists() else default
    except OSError:
        return default


def elapsed_ms_since(start: float) -> float:
    return round((perf_counter() - start) * 1000.0, 3)


def record_health_section(
    sections: list[dict[str, Any]],
    *,
    name: str,
    started_at: float,
    operator_diagnostic: bool = False,
    partial: bool = False,
) -> None:
    sections.append(
        {
            "name": name,
            "elapsed_ms": elapsed_ms_since(started_at),
            "operator_diagnostic": operator_diagnostic,
            "partial": partial,
        }
    )


def health_performance_diagnostics(
    sections: list[dict[str, Any]],
    *,
    slow_section_threshold_ms: int,
) -> dict[str, Any]:
    threshold = max(0, int(slow_section_threshold_ms))
    slow_sections = [
        {
            "name": str(section.get("name") or ""),
            "elapsed_ms": section.get("elapsed_ms"),
            "operator_diagnostic": bool(section.get("operator_diagnostic")),
            "partial": True if section.get("partial") else None,
        }
        for section in sections
        if float(section.get("elapsed_ms") or 0.0) >= threshold
    ]
    slow_sections.sort(key=lambda item: float(item.get("elapsed_ms") or 0.0), reverse=True)
    return {
        "sections": sections,
        "slow_section_threshold_ms": threshold,
        "slow_sections": slow_sections[:8],
        "privacy_boundary": {
            "paths_included": False,
            "raw_prompts_included": False,
            "raw_source_text_included": False,
        },
    }


def ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(float(max(0, numerator)) / float(denominator), 4)


def question_health_stats(*args: Any, **kwargs: Any) -> dict[str, Any]:
    impl = importlib.import_module("aippocampus_runtime.question.health").question_health_stats
    return impl(*args, **kwargs)


def aggregate_question_health_stats(payload: Mapping[str, Any]) -> dict[str, Any]:
    impl = importlib.import_module(
        "aippocampus_runtime.question.health"
    ).aggregate_question_health_stats
    return impl(payload)


def count_messages(rollout: Path) -> tuple[int, int | None]:
    stats = rollout_visibility_stats(rollout)
    return stats.message_count, stats.last_message_line


SCRIPT_MODULES = {
    "build_index.py": "aippocampus_runtime.recall.index_builder",
    "build_clean_source.py": "aippocampus_runtime.source.clean_source",
    "checkpoint.py": "aippocampus_runtime.artifacts.checkpoint",
    "prepare_graphify_corpus.py": "aippocampus_runtime.ops.graphify_corpus",
    "build_segments.py": "aippocampus_runtime.recall.segment_builder",
}


def recommended_script_command(script_name: str, cwd: str | Path) -> str:
    module = SCRIPT_MODULES.get(script_name, Path(script_name).stem)
    if os.name == "nt":
        windows_cwd = str(PureWindowsPath(str(cwd)))
        return (
            '$env:PYTHONPATH="$env:CODEX_HOME\\skills\\aippocampus\\scripts"; '
            f"{current_python_command()} -m {module} "
            f'--cwd "{windows_cwd}"'
        )
    return (
        'PYTHONPATH="$CODEX_HOME/skills/aippocampus/scripts" '
        f"{current_python_command()} -m {module} "
        f"--cwd {quote_posix_double(cwd)}"
    )


def recommended_facade_command(action_id: str, cwd: str | Path) -> str:
    del action_id
    if os.name == "nt":
        windows_cwd = str(PureWindowsPath(str(cwd)))
        return f'aippocampus maintenance --cwd "{windows_cwd}"'
    return f"aippocampus maintenance --cwd {quote_posix_double(cwd)}"


def health_action(action_id: str, severity: str, reason: str, script_name: str, cwd: Path) -> dict[str, Any]:
    item = action(action_id, severity, reason, recommended_script_command(script_name, cwd))
    item["facade_command"] = recommended_facade_command(action_id, cwd)
    return item


def load_question_stats(
    *,
    jobs_path: Path | None,
    registry_path: Path | None,
    dormant_after_days: int = DEFAULT_DORMANT_AFTER_DAYS,
    resolve_registry_refs: bool = True,
    include_details: bool = False,
) -> dict[str, Any]:
    if jobs_path is None:
        return {"available": False, "reason": "jobs_unresolved"}
    try:
        payload = question_health_stats(
            jobs_path,
            registry_path=registry_path if resolve_registry_refs else None,
            dormant_after_days=dormant_after_days,
        )
        return payload if include_details else aggregate_question_health_stats(payload)
    except Exception as exc:
        # Health checks are operator diagnostics. Question lifecycle reporting is
        # allowed to disappear when local staging artifacts are stale or corrupt;
        # it must not block core index/clean-source maintenance advice.
        return {
            "available": False,
            "reason": "question_health_error",
            "error_type": type(exc).__name__,
            "message": str(exc)[:240],
            "jobs": str(jobs_path),
            "registry": str(registry_path) if registry_path else None,
        }


def default_question_jobs_path(registry_path: Path) -> Path:
    return registry_path.resolve().parent / DEFAULT_JOBS_OUTPUT_NAME


def registry_cache_pressure_report(cwd: Path, registry_dir: Path) -> dict[str, Any]:
    """Return a bounded generated-cache pressure card for foreground health.

    This deliberately reuses storage governance instead of inventing a second
    scanner. The report is about rebuildable generated cache only; source
    history, clean source, raw rollouts, and provenance stay protected.
    """

    try:
        from aippocampus_runtime.ops import storage_governance  # noqa: PLC0415
        from aippocampus_runtime.ops.storage_governance_contract import (  # noqa: PLC0415
            CLASS_REBUILDABLE,
        )

        plan = storage_governance.build_plan(
            cwd,
            registry_dir=registry_dir,
            class_filter=CLASS_REBUILDABLE,
            include_paths=False,
            top=3,
            fanout_budget=16,
        )
    except Exception as exc:
        return {
            "available": False,
            "status": "unavailable",
            "reason": "storage_governance_unavailable",
            "error_type": type(exc).__name__,
            "source_history_protected": True,
            "foreground_blocking": False,
        }
    metrics = dict(plan.get("metrics") or {})
    reclaimable = safe_int(metrics.get("reclaimable_rebuildable_bytes"))
    amplification = float(metrics.get("generated_index_amplification_ratio") or 0.0)
    candidate_count = safe_int(metrics.get("eviction_candidate_count"))
    reasons: list[str] = []
    if reclaimable >= STORAGE_PRESSURE_RECLAIMABLE_BYTES:
        reasons.append("reclaimable_rebuildable_cache_bytes_high")
    if amplification >= STORAGE_PRESSURE_AMPLIFICATION_RATIO:
        reasons.append("generated_index_amplification_ratio_high")
    if candidate_count >= STORAGE_PRESSURE_CANDIDATE_COUNT:
        reasons.append("rebuildable_eviction_candidate_count_high")
    status = "pressure" if reasons else "ok"
    return {
        "available": True,
        "status": status,
        "pressure": bool(reasons),
        "reasons": reasons,
        "metrics": {
            "reclaimable_rebuildable_bytes": reclaimable,
            "reclaimable_rebuildable_human": metrics.get("reclaimable_rebuildable_human"),
            "protected_source_bytes": safe_int(metrics.get("protected_source_bytes")),
            "protected_source_human": metrics.get("protected_source_human"),
            "generated_index_amplification_ratio": amplification,
            "eviction_candidate_count": candidate_count,
        },
        "dry_run_command": "aippocampus storage gc --dry-run --json --top 1 --cwd .",
        "summary_command": "aippocampus storage gc --dry-run --summary-json --cwd .",
        "repair_command": "aippocampus storage gc --apply --class rebuildable --include-active --summary-json --cwd .",
        "source_history_protected": True,
        "foreground_blocking": False,
        "privacy_boundary": {
            "paths_included": False,
            "raw_rollout_bodies_read": False,
            "clean_source_bodies_read": False,
            "rebuildable_cache_only": True,
        },
    }


def generation_cache_pressure_report(
    index_generations: Mapping[str, Any],
    segment_generations: Mapping[str, Any],
) -> dict[str, Any]:
    """Summarize already-loaded old generation pressure without a registry scan."""

    index_bytes = safe_int(index_generations.get("generation_gc_candidate_bytes"))
    segment_bytes = safe_int(segment_generations.get("generation_gc_candidate_bytes"))
    index_count = safe_int(index_generations.get("generation_gc_candidate_count"))
    segment_count = safe_int(segment_generations.get("generation_gc_candidate_count"))
    reclaimable = index_bytes + segment_bytes
    candidate_count = index_count + segment_count
    reasons: list[str] = []
    if reclaimable >= STORAGE_PRESSURE_RECLAIMABLE_BYTES:
        reasons.append("loaded_generation_gc_candidate_bytes_high")
    if candidate_count >= STORAGE_PRESSURE_CANDIDATE_COUNT:
        reasons.append("loaded_generation_gc_candidate_count_high")
    status = "pressure" if reasons else "ok"
    return {
        "available": True,
        "status": status,
        "pressure": bool(reasons),
        "reasons": reasons,
        "scope": "current_thread_generation_diagnostics",
        "metrics": {
            "reclaimable_rebuildable_bytes": reclaimable,
            "reclaimable_rebuildable_human": human_bytes(reclaimable),
            "index_generation_gc_candidate_bytes": index_bytes,
            "segment_generation_gc_candidate_bytes": segment_bytes,
            "eviction_candidate_count": candidate_count,
            "index_generation_gc_candidate_count": index_count,
            "segment_generation_gc_candidate_count": segment_count,
            "generated_index_amplification_ratio": 0.0,
        },
        "dry_run_command": STORAGE_GC_BOUNDED_DETAIL_COMMAND,
        "summary_command": "aippocampus storage gc --dry-run --summary-json --cwd .",
        "repair_command": "aippocampus storage gc --apply --class rebuildable --include-active --summary-json --cwd .",
        "source_history_protected": True,
        "foreground_blocking": False,
        "privacy_boundary": {
            "paths_included": False,
            "raw_rollout_bodies_read": False,
            "clean_source_bodies_read": False,
            "rebuildable_cache_only": True,
        },
        "claim_boundary": (
            "Current-thread old generation candidates are rebuildable-cache "
            "pressure only; review storage GC before any apply."
        ),
    }


def deferred_storage_pressure_report() -> dict[str, Any]:
    return {
        "available": False,
        "status": "deferred",
        "partial": True,
        "pressure": None,
        "reason": "expensive_storage_pressure_diagnostic_requires_opt_in",
        "next_operator_action": (
            "aippocampus health --detail full --json "
            f"--include-expensive-diagnostics --operator-timeout-ms {EXPENSIVE_OPERATOR_DIAGNOSTIC_TIMEOUT_MS}"
        ),
        "summary_command": "aippocampus storage gc --dry-run --summary-json --cwd .",
        "source_history_protected": True,
        "foreground_blocking": False,
        "privacy_boundary": {
            "paths_included": False,
            "raw_rollout_bodies_read": False,
            "clean_source_bodies_read": False,
            "rebuildable_cache_only": True,
        },
        "claim_boundary": (
            "Storage pressure was not assessed in the bounded full-detail pass; "
            "use next_operator_action for the explicit expensive diagnostic."
        ),
    }



def health_report(cwd: str | Path | None = None, **overrides: Any) -> dict[str, Any]:
    """Return the runtime health payload without shelling out to the CLI."""
    return build_health_report(HealthOptions(cwd=Path.cwd() if cwd is None else cwd, **overrides))


def public_health_report(payload: dict[str, Any], *, include_paths: bool = False) -> dict[str, Any]:
    public = dict(payload) if include_paths else redact_sensitive_values(redact_private_paths(payload))
    bound_health_generation_gc_candidates(public)
    if not include_paths:
        _rewrite_redacted_action_commands(public)
    privacy = dict(public.get("privacy") or {})
    privacy.update(
        {
            "paths_included": include_paths,
            "path_redaction": "none" if include_paths else LOCAL_PATH_REDACTION,
        }
    )
    public["privacy"] = privacy
    return public


def bound_health_generation_gc_candidates(payload: dict[str, Any]) -> None:
    """Keep health detail useful without turning it into a storage GC dump.

    Generation rows can number in the hundreds on real registries. Health owns
    the readiness/counts summary; storage GC owns path-level review and full
    candidate detail because apply still needs source, pointer, lease, reader
    pin, and TTL checks there.
    """

    for section in ("index", "segments"):
        section_payload = payload.get(section)
        if not isinstance(section_payload, dict):
            continue
        generations = section_payload.get("generations")
        if not isinstance(generations, dict):
            continue
        candidates = generations.get("generation_gc_candidates")
        if not isinstance(candidates, list):
            continue
        total = int(generations.get("generation_gc_candidate_count") or len(candidates))
        limit = HEALTH_GENERATION_GC_CANDIDATE_LIMIT
        if len(candidates) > limit:
            generations["generation_gc_candidates"] = candidates[:limit]
        generations["generation_gc_candidates_returned"] = min(len(candidates), limit)
        generations["generation_gc_candidate_detail_deferred"] = len(candidates) > limit
        generations["bounded_gc_detail_command"] = STORAGE_GC_BOUNDED_DETAIL_COMMAND
        generations["full_gc_detail_command"] = STORAGE_GC_FULL_DETAIL_COMMAND
        generations["generation_gc_candidate_total"] = total


def _rewrite_redacted_action_commands(payload: dict[str, Any]) -> None:
    for item in payload.get("recommended_actions") or []:
        if not isinstance(item, dict):
            continue
        command = str(item.get("command") or "")
        facade_command = str(item.get("facade_command") or "")
        needs_current_dir_facade = (
            facade_command.strip() == "aippocampus maintenance"
            or "aippocampus maintenance --cwd" in facade_command
            or (
                "aippocampus_runtime" in command
                and (
                    LOCAL_PATH_REDACTION in command
                    or LOCAL_PATH_REDACTION in facade_command
                )
            )
        )
        if needs_current_dir_facade:
            # The full report keeps the exact cwd for operator diagnostics. Once
            # paths are redacted, that same command becomes uncopyable; default
            # foreground health should give a runnable current-directory action.
            item["command"] = "aippocampus maintenance plan --summary-json"
            item["facade_command"] = "aippocampus maintenance plan --summary-json"


def build_health_report(options: HealthOptions) -> dict[str, Any]:
    """Build full health state for later compact/operator rendering.

    aippocampus-stage-map: resolve local inputs -> load manifest/cache state ->
    evaluate readiness/actions -> attach operator-only diagnostics -> return a
    full payload for renderers to compact/redact. Do not add foreground proof
    fields here; compact health projection owns frontstage shape.
    """

    section_timings: list[dict[str, Any]] = []
    core_started_at = perf_counter()
    resolved = resolve_health_inputs(options)
    cwd = resolved.cwd
    host_home = resolved.host_home
    rollout = resolved.rollout
    index_dir = resolved.index_dir
    anchors = resolved.anchors
    graphify_corpus = resolved.graphify_corpus
    segments_dir = resolved.segments_dir
    checkpoint_state = resolved.checkpoint_state
    clean_source_dir = resolved.clean_source_dir
    registry_path = resolved.registry_path
    registry_recall = resolved.registry_recall
    registry_resolution = resolved.registry_resolution
    legacy_aliases = resolved.legacy_aliases
    jobs_path = (
        Path(options.jobs_output).resolve()
        if options.jobs_output
        else default_question_jobs_path(registry_path)
    )
    now = datetime.now(timezone.utc)
    rollout_stat = rollout.stat()
    visibility = rollout_visibility_stats(rollout)
    current_message_count = visibility.message_count
    last_line = visibility.last_message_line
    current_anchor_count = len(parse_anchor_file(anchors))
    current_anchor_sha = file_sha256(anchors) if anchors.exists() else None
    live_delta_tolerance = max(0, int(options.live_delta_tolerance_messages))
    # A live foreground thread writes new rollout rows while health and
    # maintenance are running. Treat small deltas as a fresh window so the
    # readiness gate does not create a self-perpetuating maintenance loop; the
    # bulk stale threshold still protects future-thread recall quality.
    stale_message_threshold = max(
        live_delta_tolerance + 1,
        int(options.max_stale_messages),
    )
    index_stage = evaluate_index_state(
        index_dir=index_dir,
        rollout_size=rollout_stat.st_size,
        current_message_count=current_message_count,
        current_anchor_sha=current_anchor_sha,
        stale_message_threshold=stale_message_threshold,
        now=now,
        options=options,
    )
    manifest_path = index_stage.manifest_path
    manifest = index_stage.manifest
    sqlite_path = index_stage.sqlite_path
    stable_sqlite_path = index_stage.stable_sqlite_path
    index_generations = index_stage.generations
    index_intentional_eviction = index_stage.intentional_eviction
    index_reasons = index_stage.reasons
    indexed_messages = index_stage.indexed_messages
    indexed_last_line = index_stage.indexed_last_line
    message_delta = index_stage.message_delta
    byte_delta = index_stage.byte_delta
    rag_manifest = index_stage.rag_manifest
    index_stale = index_stage.stale
    index_stale_age_seconds = index_stage.stale_age_seconds
    index_activity_class = index_stage.activity_class

    clean_manifest_path = clean_source_dir / "manifest.json"
    clean_messages_path = clean_source_dir / "messages.jsonl"
    clean_turns_path = clean_source_dir / "turns.jsonl"
    clean_manifest = load_json_dict(clean_manifest_path).data
    clean_reasons: list[str] = []
    if not clean_manifest:
        clean_reasons.append("clean-source manifest is missing")
    if not clean_messages_path.exists():
        clean_reasons.append("clean-source messages.jsonl is missing")
    if not clean_turns_path.exists():
        clean_reasons.append("clean-source turns.jsonl is missing")
    try:
        clean_schema = int(clean_manifest.get("schema_version") or 0)
    except (TypeError, ValueError):
        clean_schema = 0
    if clean_manifest and clean_schema < 2:
        clean_reasons.append("clean-source schema is older than v2 upgrade contract")
    if clean_manifest and clean_schema >= 2 and not clean_manifest.get("upgrade_contract"):
        clean_reasons.append("clean-source upgrade contract is missing")
    clean_indexed_bytes = int(clean_manifest.get("source_rollout_size") or 0)
    clean_byte_delta = max(0, rollout_stat.st_size - clean_indexed_bytes)
    if clean_manifest and clean_byte_delta >= options.max_stale_bytes:
        clean_reasons.append(f"{clean_byte_delta} new rollout bytes since clean-source build")
    clean_source_stale = bool(clean_reasons)
    clean_source_stale_age_seconds = age_seconds_since(clean_manifest.get("created_at"), now=now)
    clean_source_message_count = safe_int(clean_manifest.get("message_count")) if clean_manifest else 0
    clean_source_turn_count = safe_int(clean_manifest.get("turn_count")) if clean_manifest else 0
    expected_clean_source_message_count = visibility.expected_clean_source_message_count
    expected_clean_source_turn_count = visibility.expected_clean_source_turn_count
    clean_source_message_delta = max(
        0, expected_clean_source_message_count - clean_source_message_count
    )
    clean_source_turn_delta = max(0, expected_clean_source_turn_count - clean_source_turn_count)
    if clean_manifest and clean_source_message_delta >= stale_message_threshold:
        clean_reasons.append(
            f"{clean_source_message_delta} latest visible clean-source message(s) are missing"
        )
    if clean_manifest and clean_source_turn_delta >= stale_message_threshold:
        clean_reasons.append(
            f"{clean_source_turn_delta} latest clean-source turn(s) are missing"
        )
    clean_source_stale = bool(clean_reasons)
    clean_source_activity_class = activity_class(
        message_delta=clean_source_message_delta,
        byte_delta=clean_byte_delta,
        stale_age_seconds=clean_source_stale_age_seconds,
        max_stale_messages=options.max_stale_messages,
        max_stale_bytes=options.max_stale_bytes,
    )

    corpus_manifest_path = graphify_corpus / "corpus_manifest.json"
    corpus_manifest = load_json_dict(corpus_manifest_path).data
    current_manifest_sha = index_stage.manifest_sha
    graphify_reasons: list[str] = []
    if not graphify_corpus.exists():
        graphify_reasons.append("graphify corpus is missing")
    elif not corpus_manifest:
        graphify_reasons.append("graphify corpus_manifest.json is missing")
    elif (
        current_manifest_sha
        and corpus_manifest.get("source_index_manifest_sha256") != current_manifest_sha
    ):
        graphify_reasons.append("graphify corpus was prepared from an older index manifest")
    if index_stale:
        graphify_reasons.append("index is stale, so prepared corpus may be stale too")
    graphify_stale = bool(graphify_reasons)

    segments_manifest_path = segments_dir / "manifest.json"
    segments_manifest = load_json_dict(segments_manifest_path).data
    segment_generations = segment_generation_diagnostics(
        segments_manifest_path,
        root=segments_dir,
        include_paths=False,
    )
    segments_reasons: list[str] = []
    segments_needed = rollout_stat.st_size >= options.segment_threshold_bytes
    segments_message_delta = 0
    segments_byte_delta = 0
    if segments_needed and not segments_manifest:
        segments_reasons.append("segment manifest is missing for a large rollout")
    if segments_manifest:
        segment_rollout_size = int(segments_manifest.get("source_rollout_size") or 0)
        segment_message_count = int(segments_manifest.get("message_count") or 0)
        segments_byte_delta = max(0, rollout_stat.st_size - segment_rollout_size)
        segments_message_delta = max(0, current_message_count - segment_message_count)
        # Rollout files grow during any live interaction, including the health
        # check itself. Do not mark shards stale for one fresh message or a tiny
        # tool output; use the same stale thresholds as the main index so hooks
        # do not rebuild segments on every turn.
        if segments_message_delta >= options.max_stale_messages:
            segments_reasons.append(
                f"{segments_message_delta} new messages since segmented index build"
            )
        if segments_byte_delta >= options.max_stale_bytes:
            segments_reasons.append(
                f"{segments_byte_delta} new rollout bytes since segmented index build"
            )
        if current_anchor_sha and segments_manifest.get("anchor_sha256") != current_anchor_sha:
            segments_reasons.append("thread-anchors.md changed since segmented index build")
        missing_segment_indexes = [
            item.get("id") or "unknown"
            for item in segments_manifest.get("segments") or []
            if not Path(str(item.get("sqlite") or "")).exists()
        ]
        if missing_segment_indexes:
            segments_reasons.append(
                "segment sqlite file(s) missing: " + ", ".join(missing_segment_indexes[:6])
            )
    segments_stale = bool(segments_reasons)
    segments_stale_age_seconds = age_seconds_since(segments_manifest.get("created_at"), now=now)
    segments_activity_class = activity_class(
        message_delta=segments_message_delta,
        byte_delta=segments_byte_delta,
        stale_age_seconds=segments_stale_age_seconds,
        max_stale_messages=options.max_stale_messages,
        max_stale_bytes=options.max_stale_bytes,
    )

    checkpoint = load_json_dict(checkpoint_state).data
    captured_count = int(checkpoint.get("last_captured_message_count") or 0)
    checked_count = int(checkpoint.get("last_checked_message_count") or 0)
    checkpoint_delta = current_message_count - captured_count
    checkpoint_due = captured_count == 0 or checkpoint_delta >= options.checkpoint_messages

    deep_graph_recommended = current_message_count >= options.deep_graph_messages or rollout_stat.st_size >= options.deep_graph_bytes

    actions = []
    if index_stale:
        severity = "critical" if not manifest else "warning"
        actions.append(
            health_action(
                "build_index",
                severity,
                "; ".join(index_reasons),
                "build_index.py",
                cwd,
            )
        )
    if clean_source_stale:
        actions.append(
            health_action(
                "build_clean_source",
                "warning" if clean_manifest else "critical",
                "; ".join(clean_reasons),
                "build_clean_source.py",
                cwd,
            )
        )
    if checkpoint_due:
        actions.append(
            health_action(
                "checkpoint",
                "suggestion",
                f"{checkpoint_delta} messages since the last captured checkpoint",
                "checkpoint.py",
                cwd,
            )
        )
    if graphify_stale:
        actions.append(
            health_action(
                "prepare_graphify_corpus",
                "info",
                "; ".join(graphify_reasons),
                "prepare_graphify_corpus.py",
                cwd,
            )
        )
    if segments_stale:
        severity = "warning" if segments_manifest else "info"
        actions.append(
            health_action(
                "build_segments",
                severity,
                "; ".join(segments_reasons),
                "build_segments.py",
                cwd,
            )
        )
    if deep_graph_recommended:
        actions.append(
            action("consider_graphify", "info", "thread size crossed the deep graph threshold", f'Use $graphify on "{graphify_corpus}" when conceptual navigation is worth the cost.')
        )
    record_health_section(section_timings, name="core_readiness", started_at=core_started_at)
    section_started_at = perf_counter()
    cheap_storage_pressure = generation_cache_pressure_report(
        index_generations,
        segment_generations,
    )
    if options.include_operator_diagnostics and options.include_expensive_diagnostics:
        storage_pressure = registry_cache_pressure_report(cwd, registry_path.resolve().parent)
    elif cheap_storage_pressure.get("pressure"):
        storage_pressure = cheap_storage_pressure
    elif options.include_operator_diagnostics:
        storage_pressure = deferred_storage_pressure_report()
    else:
        storage_pressure = operator_detail_placeholder(pressure=True)
    record_health_section(
        section_timings,
        name="storage_pressure",
        started_at=section_started_at,
        operator_diagnostic=options.include_operator_diagnostics,
        partial=bool(storage_pressure.get("partial")),
    )
    if storage_pressure.get("pressure"):
        metrics = storage_pressure.get("metrics") or {}
        amplification = float(metrics.get("generated_index_amplification_ratio") or 0.0)
        pressure_detail = (
            f"{metrics.get('generated_index_amplification_ratio')}x clean-source ratio"
            if amplification > 0
            else f"{metrics.get('eviction_candidate_count')} old generation candidate(s)"
        )
        actions.append(
            action(
                "storage_gc_rebuildable_cache",
                "warning",
                (
                    "Generated rebuildable cache pressure is high "
                    f"({metrics.get('reclaimable_rebuildable_human')}, {pressure_detail}). "
                    "Run the bounded dry-run audit before applying cleanup."
                ),
                storage_pressure["dry_run_command"],
            )
        )
    actions = dependency_ordered_actions(actions)
    logs = log_retention.add_health_action(actions, registry_path.resolve().parent, max_bytes=options.max_log_bytes)
    actions = dependency_ordered_actions(actions)
    section_started_at = perf_counter()
    question_stats = (
        {"available": False, "reason": "not_requested"}
        if not options.include_question_stats
        else load_question_stats(
            jobs_path=jobs_path,
            registry_path=registry_path,
            dormant_after_days=options.question_dormant_days,
            resolve_registry_refs=True,
            include_details=options.question_stats_details,
        )
    )
    record_health_section(
        section_timings,
        name="question_stats",
        started_at=section_started_at,
        operator_diagnostic=options.include_question_stats or options.question_stats_details,
        partial=bool(question_stats.get("partial")) if isinstance(question_stats, dict) else False,
    )
    raw_newer_than_index = bool(manifest and message_delta > 0)
    raw_newer_than_clean_source = bool(clean_manifest and clean_source_message_delta > 0)
    freshness = {
        "latest_visible_gap": raw_newer_than_index or raw_newer_than_clean_source,
        "raw_newer_than_index": raw_newer_than_index,
        "raw_newer_than_clean_source": raw_newer_than_clean_source,
        "index_message_delta": message_delta,
        "clean_source_message_delta": clean_source_message_delta,
        "clean_source_turn_delta": clean_source_turn_delta,
        "rollout_message_count": current_message_count,
        "rollout_last_message_line": last_line,
        "expected_clean_source_message_count": expected_clean_source_message_count,
        "expected_clean_source_turn_count": expected_clean_source_turn_count,
        "last_clean_source_line": visibility.last_clean_source_line,
        "live_delta_tolerance_messages": live_delta_tolerance,
    }
    critical_action_count = sum(
        1 for item in actions if item["severity"] == "critical"
    )
    # Warnings such as stale-but-present source indexes and rebuildable cache
    # pressure are real maintenance signals, but they should not imply that an
    # ordinary first recall/search path is unavailable. Reserve "blocking" for
    # critical missing prerequisites; keep freshness/storage pressure visible as
    # separate dimensions so agents do not turn health into a maintenance loop.
    high_severity_action_count = sum(
        1
        for item in actions
        if item["severity"] in {"critical", "warning"}
    )
    freshness_action_ids = {"build_index", "build_clean_source", "build_segments"}
    freshness_action_recommended = any(
        item.get("id") in freshness_action_ids for item in actions
    )
    live_delta_tolerated = bool(
        freshness["latest_visible_gap"]
        and critical_action_count == 0
        and not freshness_action_recommended
        and (
            0 < message_delta < stale_message_threshold
            or 0 < clean_source_message_delta < stale_message_threshold
            or 0 < clean_source_turn_delta < stale_message_threshold
        )
    )
    freshness_degraded = bool(
        freshness["latest_visible_gap"]
        or freshness_action_recommended
    )
    storage_pressure_cleanup_recommended = (
        None
        if storage_pressure.get("pressure") is None
        and storage_pressure.get("status") == "deferred"
        else bool(storage_pressure.get("pressure"))
    )
    product_readiness = build_product_readiness(
        actions=actions,
        registry_recall=registry_recall,
        clean_source_message_count=clean_source_message_count,
        critical_action_count=critical_action_count,
        high_severity_action_count=high_severity_action_count,
        live_delta_tolerated=live_delta_tolerated,
        freshness_degraded=freshness_degraded,
        storage_pressure_cleanup_recommended=storage_pressure_cleanup_recommended,
        checkpoint_due=checkpoint_due,
    )
    ordinary_first_recall_usable = bool(product_readiness["ordinary_first_recall_usable"])
    checkpoint_status = str(product_readiness["checkpoint_status"])
    product_readiness["latest_current_thread_may_be_missing"] = bool(freshness["latest_visible_gap"])
    product_readiness["live_delta_tolerated"] = live_delta_tolerated
    section_started_at = perf_counter()
    background_cognition = (
        background_cognition_health(
            root=registry_path.resolve().parent,
            registry_path=registry_path,
            jobs_path=jobs_path,
            cwd=cwd,
            now=now,
        )
        if options.include_operator_diagnostics
        else operator_detail_placeholder()
    )
    record_health_section(
        section_timings,
        name="background_cognition",
        started_at=section_started_at,
        operator_diagnostic=options.include_operator_diagnostics,
        partial=bool(background_cognition.get("partial")),
    )
    section_started_at = perf_counter()
    host_state_confounds = (
        codex_host_state_confounds(
            host_home,
            max_elapsed_ms=options.operator_timeout_ms,
        )
        if options.include_operator_diagnostics
        else operator_detail_placeholder(include_command=False)
    )
    record_health_section(
        section_timings,
        name="host_state_confounds",
        started_at=section_started_at,
        operator_diagnostic=options.include_operator_diagnostics,
        partial=bool(host_state_confounds.get("partial")),
    )

    result: dict[str, Any] = {
        "ok": ordinary_first_recall_usable,
        "cwd": str(cwd),
        "rollout": {
            "path": str(rollout),
            "size": rollout_stat.st_size,
            "message_count": current_message_count,
            "last_message_line": last_line,
        },
        "anchors": {
            "path": str(anchors),
            "exists": anchors.exists(),
            "count": current_anchor_count,
            "sha256": current_anchor_sha,
        },
        "storage": {
            "default_registry_dir": registry_resolution["path"],
            "default_registry_source": registry_resolution["source"],
            # owner #2651; removal: when legacy registry env fallback is retired;
            # default exposure: full health payload only, compact projection redacts it.
            "legacy_fallback": registry_resolution["legacy_fallback"],
            "active_registry": str(registry_path),
            "active_registry_source": (
                "--registry"
                if options.registry
                else "--registry-dir"
                if options.registry_dir
                else registry_resolution["source"]
            ),
        },
        "continuity_recall": registry_recall,
        # owner #2651; removal: when legacy alias diagnostics are no longer needed;
        # default exposure: operator/full diagnostics, with values path-redacted publicly.
        "legacy_aliases": legacy_aliases,
        "index": {
            "dir": str(index_dir),
            "manifest": str(manifest_path),
            "sqlite": str(sqlite_path),
            "stable_sqlite": str(stable_sqlite_path),
            "generations": index_generations,
            "intentional_eviction": index_intentional_eviction,
            "exists": bool(manifest),
            "stale": index_stale,
            "reasons": index_reasons,
            "last_indexed_at": manifest.get("created_at"),
            "stale_age_seconds": index_stale_age_seconds,
            "indexed_message_count": indexed_messages,
            "indexed_last_message_line": indexed_last_line,
            "current_last_message_line": last_line,
            "message_delta": message_delta,
            "byte_delta": byte_delta,
            "unindexed_message_ratio": ratio(message_delta, current_message_count),
            "unindexed_byte_ratio": ratio(byte_delta, rollout_stat.st_size),
            "activity_class": index_activity_class,
            "latest_visible_gap": raw_newer_than_index,
            "rag": rag_manifest,
        },
        "clean_source": {
            "dir": str(clean_source_dir),
            "manifest": str(clean_manifest_path),
            "exists": bool(clean_manifest),
            "stale": clean_source_stale,
            "reasons": clean_reasons,
            "last_built_at": clean_manifest.get("created_at"),
            "stale_age_seconds": clean_source_stale_age_seconds,
            "message_count": clean_source_message_count,
            "message_delta": clean_source_message_delta,
            "expected_message_count": expected_clean_source_message_count,
            "expected_message_delta": clean_source_message_delta,
            "turn_count": clean_source_turn_count,
            "expected_turn_count": expected_clean_source_turn_count,
            "expected_turn_delta": clean_source_turn_delta,
            "byte_delta": clean_byte_delta,
            "unindexed_message_ratio": ratio(
                clean_source_message_delta, expected_clean_source_message_count
            ),
            "unindexed_byte_ratio": ratio(clean_byte_delta, rollout_stat.st_size),
            "activity_class": clean_source_activity_class,
            "latest_visible_gap": raw_newer_than_clean_source,
            **clean_source_health_summaries(clean_source_dir, clean_manifest, registry_path, visibility),
        },
        "freshness": freshness,
        "checkpoint": {
            "state": str(checkpoint_state),
            "due": checkpoint_due,
            "status": checkpoint_status,
            "blocking": False,
            "last_checked_message_count": checked_count,
            "last_captured_message_count": captured_count,
            "message_delta": checkpoint_delta,
        },
        "graphify": {
            "corpus": str(graphify_corpus),
            "exists": graphify_corpus.exists(),
            "stale": graphify_stale,
            "reasons": graphify_reasons,
            "deep_graph_recommended": deep_graph_recommended,
        },
        "segments": {
            "dir": str(segments_dir),
            "manifest": str(segments_manifest_path),
            "generations": segment_generations,
            "needed": segments_needed,
            "exists": bool(segments_manifest),
            "stale": segments_stale,
            "reasons": segments_reasons,
            "last_built_at": segments_manifest.get("created_at"),
            "stale_age_seconds": segments_stale_age_seconds,
            "segment_count": int(segments_manifest.get("segment_count") or 0)
            if segments_manifest
            else 0,
            "message_delta": segments_message_delta,
            "byte_delta": segments_byte_delta,
            "unindexed_message_ratio": ratio(segments_message_delta, current_message_count),
            "unindexed_byte_ratio": ratio(segments_byte_delta, rollout_stat.st_size),
            "activity_class": segments_activity_class,
        },
        "question_stats": question_stats,
        "background_cognition": background_cognition,
        "storage_pressure": storage_pressure,
        "host_state_confounds": host_state_confounds,
        "logs": logs,
        "product_readiness": product_readiness,
        "recommended_actions": actions,
        "diagnostics": {
            "performance": health_performance_diagnostics(
                section_timings,
                slow_section_threshold_ms=options.slow_section_threshold_ms,
            )
        },
    }
    attach_health_trajectory(result)

    return result


def missing_rollout_health_report(cwd: str | Path, exc: FileNotFoundError) -> dict[str, Any]:
    resolved_cwd = Path(cwd).resolve()
    return {
        "ok": False,
        "status": "no_rollout_for_cwd",
        "cwd": str(resolved_cwd),
        "error": {
            "code": "no_rollout_for_cwd",
            "class": "missing_prerequisite",
            "message": "No current Codex rollout was found for this cwd.",
            "detail": str(exc),
        },
        "product_readiness": {
            "status": "no_current_thread",
            "ready": False,
            "ordinary_first_recall_usable": False,
            **missing_rollout_readiness_fields(),
            "freshness_degraded": False,
            "latest_current_thread_may_be_missing": True,
            "maintenance_recommended": True,
            "maintenance_required_before_recall": True,
            "storage_pressure_cleanup_recommended": False,
            "blocking_action_count": 1,
            "high_severity_action_count": 1,
            "advisory_action_count": 0,
            "next_best_action": "open_or_register_thread",
        },
        "recommended_actions": [
            {
                "kind": "open_current_thread_or_run_registry_wide_health",
                "severity": "warning",
                "message": (
                    "Run health inside an active Codex thread, or use registry-wide "
                    "health when you only need aggregate local readiness."
                ),
                "command": "aippocampus health --registry-wide --agent-json",
                "facade_command": "aippocampus health --registry-wide --agent-json",
            },
            {
                "kind": "first_recall_without_health",
                "severity": "info",
                "message": "Health is diagnostic; source-backed search/recall can still be tried directly.",
                "command": 'aippocampus agent recall "old cue" --json',
                "facade_command": 'aippocampus agent recall "old cue" --json',
            },
        ],
        "cannot_claim": [
            "current_thread_readiness",
            "current_rollout_index_freshness",
        ],
    }


def build_arg_parser() -> argparse.ArgumentParser:
    # Python 3.14 changed argparse's default prog to reflect how __main__ was
    # executed. Keep the public compatibility-shim identity stable for direct
    # installed-script help, facade dispatch, and cross-platform smoke tests.
    parser = argparse.ArgumentParser(
        prog="aippocampus health",
        description=(
            "Task-first health card:\n"
            "  aippocampus health              # one-screen readiness and next action\n"
            "  aippocampus health --agent-json # compact foreground JSON\n"
            "  aippocampus health --json       # compact automation JSON\n"
            "  aippocampus health --operator-json  # full local diagnostic JSON\n\n"
            "Use path and threshold flags only when repairing local artifacts or "
            "investigating a maintainer diagnostic."
        ),
        epilog=(
            "Boundary: health is read-only. Compact JSON hides local paths by default; "
            "--operator-json/--full emit full JSON diagnostics but still redact paths "
            "unless --include-paths is explicit."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--cwd", default=os.getcwd())
    parser.add_argument(
        "--registry-wide",
        action="store_true",
        help="Report privacy-safe aggregate health for every registry thread.",
    )
    parser.add_argument(
        "--registry-wide-top",
        type=int,
        default=10,
        help="Number of high-risk registry thread refs to include.",
    )
    parser.add_argument(
        "--include-paths",
        action="store_true",
        help="Local maintainer diagnostic: include registry paths and thread keys.",
    )
    parser.add_argument(
        "--index-dir",
        default=None,
        help="Defaults to the AIppocampus registry thread store.",
    )
    parser.add_argument("--anchors", default="thread-anchors.md")
    parser.add_argument(
        "--graphify-corpus",
        default=None,
        help="Defaults to the global thread store's graphify-corpus.",
    )
    parser.add_argument(
        "--segments-dir",
        default=None,
        help="Defaults to the global thread store's segments directory.",
    )
    parser.add_argument(
        "--checkpoint-state",
        default=None,
        help="Defaults to the global thread store's checkpoint state.",
    )
    parser.add_argument(
        "--clean-source-dir",
        default=None,
        help="Defaults to the global thread store's clean-source directory.",
    )
    parser.add_argument("--registry", default=None)
    parser.add_argument("--registry-dir", default=None)
    parser.add_argument(
        "--jobs-output",
        default=None,
        help="Defaults to the registry-local subconscious_jobs.jsonl.",
    )
    parser.add_argument(
        "--question-stats",
        action="store_true",
        help="Include derived aggregate question lifecycle/reporting stats.",
    )
    parser.add_argument(
        "--question-stats-resolve-refs",
        action="store_true",
        help="Compatibility flag; question stats resolve refs against registry clean source by default.",
    )
    parser.add_argument(
        "--question-stats-details",
        action="store_true",
        help="Include source-derived question lifecycle details in JSON; local diagnostics only.",
    )
    parser.add_argument(
        "--question-dormant-days",
        type=int,
        default=DEFAULT_DORMANT_AFTER_DAYS,
        help="Days without a source-backed reappearance before a question is reported dormant.",
    )
    parser.add_argument("--max-stale-messages", type=int, default=25)
    parser.add_argument("--max-stale-bytes", type=int, default=5 * 1024 * 1024)
    parser.add_argument("--live-delta-tolerance-messages", type=int, default=1)
    parser.add_argument("--max-log-bytes", type=int, default=None)
    parser.add_argument("--checkpoint-messages", type=int, default=30)
    parser.add_argument("--deep-graph-messages", type=int, default=1000)
    parser.add_argument("--deep-graph-bytes", type=int, default=100 * 1024 * 1024)
    parser.add_argument("--segment-threshold-bytes", type=int, default=100 * 1024 * 1024)
    parser.add_argument("--json", action="store_true", dest="json_output")
    parser.add_argument(
        "--agent-json",
        action="store_true",
        help="Emit compact agent-facing JSON with next actions instead of operator detail.",
    )
    parser.add_argument(
        "--detail",
        choices=["compact", "full"],
        default="compact",
        help="JSON detail level. Default --json emits the compact foreground card; --detail full emits operator diagnostics.",
    )
    parser.add_argument(
        "--operator-json",
        action="store_true",
        help="Emit the full local operator audit JSON; implies JSON output.",
    )
    parser.add_argument(
        "--operator-timeout-ms",
        type=int,
        default=DEFAULT_OPERATOR_DIAGNOSTIC_TIMEOUT_MS,
        help=(
            "Time budget for expensive operator diagnostics such as host-state scans; "
            "timed-out lanes return partial summaries with next commands."
        ),
    )
    parser.add_argument(
        "--include-expensive-diagnostics",
        action="store_true",
        help=(
            "Opt into expensive full-detail lanes such as rebuildable-cache "
            "storage pressure scans."
        ),
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Alias for --operator-json on the thread health surface; implies JSON output.",
    )
    parser.add_argument(
        "--exit-code",
        action="store_true",
        help="Exit 2 only when ordinary first recall is blocked; advisory maintenance stays exit 0.",
    )
    return parser


def options_from_args(args: argparse.Namespace) -> HealthOptions:
    return HealthOptions(
        cwd=args.cwd,
        index_dir=args.index_dir,
        anchors=args.anchors,
        graphify_corpus=args.graphify_corpus,
        segments_dir=args.segments_dir,
        checkpoint_state=args.checkpoint_state,
        clean_source_dir=args.clean_source_dir,
        registry=args.registry,
        registry_dir=args.registry_dir,
        jobs_output=args.jobs_output,
        include_question_stats=args.question_stats,
        question_stats_details=args.question_stats_details,
        question_dormant_days=args.question_dormant_days,
        max_stale_messages=args.max_stale_messages,
        max_stale_bytes=args.max_stale_bytes,
        live_delta_tolerance_messages=args.live_delta_tolerance_messages,
        max_log_bytes=args.max_log_bytes,
        checkpoint_messages=args.checkpoint_messages,
        deep_graph_messages=args.deep_graph_messages,
        deep_graph_bytes=args.deep_graph_bytes,
        segment_threshold_bytes=args.segment_threshold_bytes,
        include_expensive_diagnostics=args.include_expensive_diagnostics,
        operator_timeout_ms=args.operator_timeout_ms,
        include_operator_diagnostics=bool(
            args.operator_json
            or args.full
            or args.detail == "full"
            or args.include_paths
            or args.question_stats
            or args.question_stats_details
        ),
    )


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    json_requested = bool(args.json_output or args.agent_json or args.operator_json or args.full)
    if args.registry_wide:
        registry_wide_dir = (
            Path(args.registry).resolve().parent
            if args.registry and not args.registry_dir
            else args.registry_dir
        )
        result = registry_health_report(
            registry_dir=registry_wide_dir,
            top=args.registry_wide_top,
            include_paths=args.include_paths,
        )
        if json_requested:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            render_registry_health_text(result)
        if args.exit_code and not result["ok"]:
            return 2
        return 0

    try:
        result = build_health_report(options_from_args(args))
    except FileNotFoundError as exc:
        result = missing_rollout_health_report(args.cwd, exc)
    public_result = public_health_report(result, include_paths=bool(args.include_paths))
    full_detail_json = bool(args.operator_json or args.full or args.detail == "full")
    compact_json = bool(args.agent_json or (args.json_output and not full_detail_json))
    if compact_json:
        print(json.dumps(compact_health_payload(public_result), ensure_ascii=False, indent=2))
    elif json_requested:
        print(json.dumps(public_result, ensure_ascii=False, indent=2))
    else:
        render_health_text(public_result)

    readiness = result.get("product_readiness") if isinstance(result, dict) else {}
    readiness_exit_requested = bool(args.exit_code or compact_json or not json_requested)
    if (
        readiness_exit_requested
        and isinstance(readiness, dict)
        and "ordinary_first_recall_usable" in readiness
    ):
        return (
            0
            if readiness.get("ordinary_first_recall_usable")
            else cli_exit_code_for_error_code("missing_prerequisite")
        )
    if args.exit_code and not result.get("ok"):
        return cli_exit_code_for_error_code("missing_prerequisite")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
