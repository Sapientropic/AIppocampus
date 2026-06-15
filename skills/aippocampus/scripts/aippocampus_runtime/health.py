#!/usr/bin/env python3
"""Report health and recommended maintenance for a long Codex thread."""

from __future__ import annotations

import argparse
import importlib
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PureWindowsPath
from typing import Any, Mapping

from aippocampus_runtime.artifacts.publish import (
    index_generation_diagnostics,
    resolve_sqlite_index_path,
    segment_generation_diagnostics,
)
from aippocampus_runtime.core import (
    aippocampus_registry_resolution,
    codex_home,
    default_thread_checkpoint_state_path,
    default_thread_clean_source_dir,
    default_thread_graphify_corpus_dir,
    default_thread_index_dir,
    default_thread_segments_dir,
    file_sha256,
    locate_rollout,
    parse_anchor_file,
    resolve_artifact_path,
)
from aippocampus_runtime.health_actions import action, dependency_ordered_actions
from aippocampus_runtime.health_background_cognition import background_cognition_health
from aippocampus_runtime.health_freshness import rollout_visibility_stats
from aippocampus_runtime.health_registry import registry_health_report
from aippocampus_runtime.health_render import render_health_text, render_registry_health_text
from aippocampus_runtime.health_trajectory import attach_health_trajectory
from aippocampus_runtime.legacy_aliases import legacy_alias_diagnostics
from aippocampus_runtime.mcp.public_projection import compact_health_payload
from aippocampus_runtime.ops import log_retention
from aippocampus_runtime.ops.storage_eviction import latest_intentional_eviction
from aippocampus_runtime.privacy import (
    LOCAL_PATH_REDACTION,
    redact_private_paths,
    redact_sensitive_values,
)
from aippocampus_runtime.question.constants import DEFAULT_DORMANT_AFTER_DAYS
from aippocampus_runtime.registry.store import registry_paths
from aippocampus_runtime.source.source_intake_health import clean_source_health_summaries

DEFAULT_JOBS_OUTPUT_NAME = "subconscious_jobs.jsonl"


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


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def load_json_fail_open(path: Path) -> dict[str, Any]:
    try:
        data = load_json(path)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


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


def parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        text = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def age_seconds_since(value: Any, *, now: datetime | None = None) -> int | None:
    parsed = parse_timestamp(value)
    if parsed is None:
        return None
    current = now or datetime.now(timezone.utc)
    return max(0, int((current - parsed).total_seconds()))


def ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(float(max(0, numerator)) / float(denominator), 4)


def activity_class(
    *,
    message_delta: int,
    byte_delta: int,
    stale_age_seconds: int | None,
    max_stale_messages: int,
    max_stale_bytes: int,
) -> str:
    if message_delta <= 0 and byte_delta <= 0:
        return "quiet"
    if stale_age_seconds is None:
        return "unknown"
    # Activity classification is advisory. It should help operators spot fast
    # growing threads without changing the existing absolute stale thresholds.
    if stale_age_seconds <= 3600 and (
        message_delta >= max_stale_messages or byte_delta >= max_stale_bytes
    ):
        return "high_activity"
    if stale_age_seconds >= 24 * 3600 and (
        message_delta < max_stale_messages and byte_delta < max_stale_bytes
    ):
        return "quiet"
    return "normal"


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


def quote_posix_double(value: str | Path) -> str:
    text = str(value)
    escaped = (
        text.replace("\\", "\\\\").replace('"', '\\"').replace("$", "\\$").replace("`", "\\`")
    )
    return f'"{escaped}"'


def current_python_command() -> str:
    if os.name == "nt":
        return f'& "{PureWindowsPath(sys.executable)}"'
    return quote_posix_double(sys.executable)


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



def health_report(cwd: str | Path | None = None, **overrides: Any) -> dict[str, Any]:
    """Return the runtime health payload without shelling out to the CLI."""
    return build_health_report(HealthOptions(cwd=Path.cwd() if cwd is None else cwd, **overrides))


def public_health_report(payload: dict[str, Any], *, include_paths: bool = False) -> dict[str, Any]:
    public = dict(payload) if include_paths else redact_sensitive_values(redact_private_paths(payload))
    privacy = dict(public.get("privacy") or {})
    privacy.update(
        {
            "paths_included": include_paths,
            "path_redaction": "none" if include_paths else LOCAL_PATH_REDACTION,
        }
    )
    public["privacy"] = privacy
    return public


def build_health_report(options: HealthOptions) -> dict[str, Any]:
    cwd = Path(options.cwd).resolve()
    rollout = locate_rollout(cwd, codex_home())
    index_dir = resolve_artifact_path(options.index_dir, cwd, default_thread_index_dir(cwd, rollout))
    anchors = Path(options.anchors)
    if not anchors.is_absolute():
        anchors = cwd / anchors
    graphify_corpus = resolve_artifact_path(
        options.graphify_corpus, cwd, default_thread_graphify_corpus_dir(cwd, rollout)
    )
    segments_dir = resolve_artifact_path(
        options.segments_dir, cwd, default_thread_segments_dir(cwd, rollout)
    )
    checkpoint_state = resolve_artifact_path(
        options.checkpoint_state, cwd, default_thread_checkpoint_state_path(cwd, rollout)
    )
    clean_source_dir = resolve_artifact_path(
        options.clean_source_dir, cwd, default_thread_clean_source_dir(cwd, rollout)
    )
    registry_path = (
        Path(options.registry).resolve()
        if options.registry
        else registry_paths(Path(options.registry_dir).resolve() if options.registry_dir else None)[0]
    )
    registry_resolution = aippocampus_registry_resolution()
    legacy_aliases = legacy_alias_diagnostics(
        registry_resolution=registry_resolution,
        workspace=cwd,
        project_local_paths={
            "index": index_dir,
            "clean_source": clean_source_dir,
            "graphify": graphify_corpus,
            "segments": segments_dir,
            "checkpoint": checkpoint_state,
        },
    )
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

    manifest_path = index_dir / "manifest.json"
    messages_path = index_dir / "messages.jsonl"
    stable_sqlite_path = index_dir / "source_index.sqlite"
    sqlite_path = resolve_sqlite_index_path(stable_sqlite_path)
    index_generations = index_generation_diagnostics(
        stable_sqlite_path,
        root=index_dir,
        include_paths=False,
    )
    manifest = load_json(manifest_path)
    index_intentional_eviction = {"detected": False}
    if not sqlite_path.exists():
        candidate_eviction = latest_intentional_eviction(index_dir, "source_index.sqlite")
        eviction_time = parse_timestamp(candidate_eviction.get("evicted_at"))
        manifest_time = parse_timestamp(manifest.get("created_at"))
        if (
            candidate_eviction.get("detected")
            and eviction_time is not None
            and manifest_time is not None
            and manifest_time > eviction_time
        ):
            index_intentional_eviction = {"detected": False}
        else:
            index_intentional_eviction = candidate_eviction

    index_reasons: list[str] = []
    if not manifest:
        index_reasons.append("index manifest is missing")
    if not messages_path.exists():
        index_reasons.append("messages.jsonl is missing")
    if not sqlite_path.exists():
        if index_intentional_eviction.get("detected") and index_intentional_eviction.get(
            "rebuildable"
        ):
            index_reasons.append("source_index.sqlite intentionally evicted as rebuildable cache")
        else:
            index_reasons.append("source_index.sqlite is missing")
    indexed_messages = int(manifest.get("message_count") or 0)
    indexed_bytes = int(manifest.get("source_rollout_size") or 0)
    indexed_last_line = manifest.get("last_message_line")
    message_delta = max(0, current_message_count - indexed_messages)
    byte_delta = max(0, rollout_stat.st_size - indexed_bytes)
    live_delta_tolerance = max(0, int(options.live_delta_tolerance_messages))
    if manifest and message_delta > live_delta_tolerance:
        index_reasons.append(
            f"{message_delta} latest visible message(s) are newer than the index"
        )
    if manifest and byte_delta >= options.max_stale_bytes:
        index_reasons.append(f"{byte_delta} new rollout bytes since last index")
    if manifest and current_anchor_sha and manifest.get("anchor_sha256") != current_anchor_sha:
        index_reasons.append("thread-anchors.md changed since last index")
    rag_manifest = manifest.get("rag") or {}
    if manifest and not rag_manifest.get("enabled"):
        index_reasons.append("rag-lite chunk cache is missing from index manifest")

    index_stale = bool(index_reasons)
    index_stale_age_seconds = age_seconds_since(manifest.get("created_at"), now=now)
    index_activity_class = activity_class(
        message_delta=message_delta,
        byte_delta=byte_delta,
        stale_age_seconds=index_stale_age_seconds,
        max_stale_messages=options.max_stale_messages,
        max_stale_bytes=options.max_stale_bytes,
    )

    clean_manifest_path = clean_source_dir / "manifest.json"
    clean_messages_path = clean_source_dir / "messages.jsonl"
    clean_turns_path = clean_source_dir / "turns.jsonl"
    clean_manifest = load_json(clean_manifest_path)
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
    if clean_manifest and clean_source_message_delta > live_delta_tolerance:
        clean_reasons.append(
            f"{clean_source_message_delta} latest visible clean-source message(s) are missing"
        )
    if clean_manifest and clean_source_turn_delta > live_delta_tolerance:
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
    corpus_manifest = load_json(corpus_manifest_path)
    current_manifest_sha = file_sha256(manifest_path) if manifest_path.exists() else None
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
    segments_manifest = load_json(segments_manifest_path)
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

    checkpoint = load_json(checkpoint_state)
    captured_count = int(checkpoint.get("last_captured_message_count") or 0)
    checked_count = int(checkpoint.get("last_checked_message_count") or 0)
    checkpoint_delta = current_message_count - captured_count
    checkpoint_due = captured_count == 0 or checkpoint_delta >= options.checkpoint_messages

    deep_graph_recommended = current_message_count >= options.deep_graph_messages or rollout_stat.st_size >= options.deep_graph_bytes

    actions = []
    if index_stale:
        severity = "critical" if not manifest else "warning"
        actions.append(
            action(
                "build_index",
                severity,
                "; ".join(index_reasons),
                recommended_script_command("build_index.py", cwd),
            )
        )
    if clean_source_stale:
        actions.append(
            action(
                "build_clean_source",
                "warning" if clean_manifest else "critical",
                "; ".join(clean_reasons),
                recommended_script_command("build_clean_source.py", cwd),
            )
        )
    if checkpoint_due:
        actions.append(
            action(
                "checkpoint",
                "suggestion",
                f"{checkpoint_delta} messages since the last captured checkpoint",
                recommended_script_command("checkpoint.py", cwd),
            )
        )
    if graphify_stale:
        actions.append(
            action(
                "prepare_graphify_corpus",
                "info",
                "; ".join(graphify_reasons),
                recommended_script_command("prepare_graphify_corpus.py", cwd),
            )
        )
    if segments_stale:
        severity = "warning" if segments_manifest else "info"
        actions.append(
            action(
                "build_segments",
                severity,
                "; ".join(segments_reasons),
                recommended_script_command("build_segments.py", cwd),
            )
        )
    if deep_graph_recommended:
        actions.append(
            action("consider_graphify", "info", "thread size crossed the deep graph threshold", f'Use $graphify on "{graphify_corpus}" when conceptual navigation is worth the cost.')
        )
    actions = dependency_ordered_actions(actions)
    logs = log_retention.add_health_action(actions, registry_path.resolve().parent, max_bytes=options.max_log_bytes)
    actions = dependency_ordered_actions(actions)
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
    blocking_action_count = sum(
        1 for item in actions if item["severity"] in {"critical", "warning"}
    )
    live_delta_tolerated = bool(
        freshness["latest_visible_gap"]
        and blocking_action_count == 0
        and (
            0 < message_delta <= live_delta_tolerance
            or 0 < clean_source_message_delta <= live_delta_tolerance
            or 0 < clean_source_turn_delta <= live_delta_tolerance
        )
    )
    checkpoint_status = "due_when_idle" if checkpoint_due else "current"
    product_readiness = {
        "status": (
            "needs_maintenance"
            if blocking_action_count
            else ("ready_with_live_delta" if live_delta_tolerated else "ready")
        ),
        "ready": blocking_action_count == 0,
        "blocking_action_count": blocking_action_count,
        "live_delta_tolerated": live_delta_tolerated,
        "checkpoint_status": checkpoint_status,
        "next_best_action": (
            "run_checkpoint_when_idle" if checkpoint_due else "continue"
        ),
    }

    result: dict[str, Any] = {
        "ok": not any(a["severity"] in {"critical", "warning"} for a in actions),
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
        "background_cognition": background_cognition_health(root=registry_path.resolve().parent, registry_path=registry_path, jobs_path=jobs_path, cwd=cwd, now=now),
        "logs": logs,
        "product_readiness": product_readiness,
        "recommended_actions": actions,
    }
    attach_health_trajectory(result)

    return result


def build_arg_parser() -> argparse.ArgumentParser:
    # Python 3.14 changed argparse's default prog to reflect how __main__ was
    # executed. Keep the public compatibility-shim identity stable for direct
    # installed-script help, facade dispatch, and cross-platform smoke tests.
    parser = argparse.ArgumentParser(prog="aippocampus health")
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
        "--exit-code", action="store_true", help="Exit 2 when maintenance is recommended."
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
    )


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
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
        if args.json_output:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            render_registry_health_text(result)
        if args.exit_code and not result["ok"]:
            return 2
        return 0

    result = build_health_report(options_from_args(args))
    public_result = public_health_report(result, include_paths=bool(args.include_paths))
    if args.agent_json:
        print(json.dumps(compact_health_payload(public_result), ensure_ascii=False, indent=2))
    elif args.json_output:
        print(json.dumps(public_result, ensure_ascii=False, indent=2))
    else:
        render_health_text(public_result)

    if args.exit_code and result["recommended_actions"]:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
