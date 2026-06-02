#!/usr/bin/env python3
"""Report health and recommended maintenance for a long Codex thread."""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PureWindowsPath
from typing import Any, Mapping

from aippocampus_runtime.artifacts.publish import resolve_sqlite_index_path
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
from aippocampus_runtime.ops.storage_eviction import latest_intentional_eviction
from aippocampus_runtime.question.constants import DEFAULT_DORMANT_AFTER_DAYS
from aippocampus_runtime.registry.store import registry_paths
from aippocampus_runtime.source.rollout import iter_messages

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


def privacy_ref(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()[:12]


def question_health_stats(*args: Any, **kwargs: Any) -> dict[str, Any]:
    impl = importlib.import_module("aippocampus_runtime.question.health").question_health_stats
    return impl(*args, **kwargs)


def aggregate_question_health_stats(payload: Mapping[str, Any]) -> dict[str, Any]:
    impl = importlib.import_module(
        "aippocampus_runtime.question.health"
    ).aggregate_question_health_stats
    return impl(payload)


def count_messages(rollout: Path) -> tuple[int, int | None]:
    count = 0
    last_line = None
    for msg in iter_messages(rollout):
        count += 1
        last_line = msg["line"]
    return count, last_line


def action(action_id: str, severity: str, reason: str, command: str) -> dict[str, str]:
    return {"id": action_id, "severity": severity, "reason": reason, "command": command}


def quote_posix_double(value: str | Path) -> str:
    text = str(value)
    escaped = (
        text.replace("\\", "\\\\").replace('"', '\\"').replace("$", "\\$").replace("`", "\\`")
    )
    return f'"{escaped}"'


def recommended_script_command(script_name: str, cwd: str | Path) -> str:
    if os.name == "nt":
        windows_cwd = str(PureWindowsPath(str(cwd)))
        return (
            f'python "$env:CODEX_HOME\\skills\\aippocampus\\scripts\\{script_name}" '
            f'--cwd "{windows_cwd}"'
        )
    return (
        f'python "$CODEX_HOME/skills/aippocampus/scripts/{script_name}" '
        f"--cwd {quote_posix_double(cwd)}"
    )


def render_health_text(result: dict[str, Any]) -> None:
    status = "OK" if result["ok"] else "needs maintenance"
    rollout = result["rollout"]
    index = result["index"]
    clean_source = result["clean_source"]
    segments = result["segments"]
    checkpoint = result["checkpoint"]
    graphify = result["graphify"]
    storage = result.get("storage") or {}
    question_stats = result.get("question_stats") or {}
    actions = result["recommended_actions"]

    print(f"thread memory health: {status}")
    if storage:
        print(
            "registry: "
            f"{storage.get('active_registry')} "
            f"({storage.get('active_registry_source')})"
        )
    print(
        f"rollout: {rollout['path']} ({rollout['size']} bytes, {rollout['message_count']} messages)"
    )
    if index["stale"]:
        print("index: stale")
    elif index["message_delta"] or index["byte_delta"]:
        print(
            f"index: fresh window ({index['message_delta']} unindexed messages, {index['byte_delta']} new bytes below threshold)"
        )
    else:
        print("index: fresh")
    if index["rag"]:
        print(f"rag cache: {index['rag'].get('chunk_count', 0)} chunks")
    print(f"clean source: {'stale' if clean_source['stale'] else 'fresh'}")
    if segments["exists"]:
        print(
            f"segments: {'stale' if segments['stale'] else 'fresh'} ({segments['segment_count']} shards)"
        )
    elif segments["needed"]:
        print("segments: missing")
    else:
        print("segments: not needed yet")
    print(f"checkpoint: {'due' if checkpoint['due'] else 'not due'}")
    print(f"graphify corpus: {'stale' if graphify['stale'] else 'fresh'}")
    if question_stats.get("available"):
        print(
            "question health: "
            f"{question_stats.get('question_group_count', 0)} groups, "
            f"{question_stats.get('recurring_link_count', 0)} recurring links, "
            f"{question_stats.get('dormant_question_count', 0)} dormant, "
            f"{question_stats.get('resolved_question_count', 0)} resolved"
        )
    if actions:
        print("\nrecommended actions:")
        for item in actions:
            print(f"- {item['id']} [{item['severity']}]: {item['reason']}")


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
    """Return the runtime health payload without shelling out to the CLI.

    CLI, MCP, recall, and registry code all need the same operator health
    contract. Keeping that contract as a package API prevents frozen binaries
    and embedded hosts from accidentally re-entering the facade through
    `sys.executable script.py`.
    """
    return build_health_report(HealthOptions(cwd=Path.cwd() if cwd is None else cwd, **overrides))


def registry_health_report(
    *,
    registry_dir: str | Path | None = None,
    top: int = 10,
    include_paths: bool = False,
) -> dict[str, Any]:
    """Return a privacy-safe registry-wide health rollup.

    The aggregate view is intentionally manifest-only: it reads registry rows
    and generated health/index manifests, not raw rollout or clean-source text.
    Default output uses stable hashed refs instead of local paths or titles so
    "fleet health" does not become a new private-history disclosure surface.
    """
    registry_root_dir = (
        Path(registry_dir).resolve() if registry_dir else registry_paths(None)[0].parent
    )
    registry_path, _registry_md = registry_paths(registry_root_dir)
    registry = load_json_fail_open(registry_path)
    threads = [item for item in registry.get("threads") or [] if isinstance(item, dict)]
    action_counts: dict[str, int] = {}
    severity_counts: dict[str, int] = {}
    status_counts = {"ok": 0, "needs_maintenance": 0, "unknown": 0}
    high_risk_threads: list[dict[str, Any]] = []
    total_rollout_bytes = 0
    total_index_bytes = 0
    total_clean_source_bytes = 0

    for entry in threads:
        thread_key = str(entry.get("thread_key") or entry.get("id") or "")
        paths = entry.get("paths") or {}
        thread_store = paths.get("registry_thread_store")
        thread_dir = Path(thread_store) if thread_store else None
        if thread_dir and not thread_dir.is_absolute():
            thread_dir = registry_root_dir / thread_dir
        if thread_key and (thread_dir is None or not thread_dir.exists()):
            candidate = registry_root_dir / "threads" / (thread_key.replace(":", "-") or "")
            thread_dir = candidate if candidate.exists() else None

        index_manifest = load_json_fail_open(thread_dir / "index" / "manifest.json") if thread_dir else {}
        clean_manifest = (
            load_json_fail_open(thread_dir / "clean-source" / "manifest.json") if thread_dir else {}
        )
        segments_manifest = (
            load_json_fail_open(thread_dir / "segments" / "manifest.json") if thread_dir else {}
        )
        raw_health = entry.get("health")
        health: dict[str, Any] = raw_health if isinstance(raw_health, dict) else {}
        actions = [
            action_item
            for action_item in health.get("recommended_actions") or []
            if isinstance(action_item, dict)
        ]
        if health.get("ok") is True:
            status_counts["ok"] += 1
        elif health.get("ok") is False:
            status_counts["needs_maintenance"] += 1
        else:
            status_counts["unknown"] += 1
        for action_item in actions:
            action_id = str(action_item.get("id") or "unknown")
            severity = str(action_item.get("severity") or "unknown")
            action_counts[action_id] = action_counts.get(action_id, 0) + 1
            severity_counts[severity] = severity_counts.get(severity, 0) + 1

        rollout_size = safe_int(entry.get("rollout_size"))
        total_rollout_bytes += rollout_size
        if thread_dir:
            total_index_bytes += safe_stat_size(
                resolve_sqlite_index_path(thread_dir / "index" / "source_index.sqlite")
            )
            total_clean_source_bytes += sum(
                safe_stat_size(thread_dir / "clean-source" / filename)
                for filename in ("manifest.json", "messages.jsonl", "turns.jsonl", "events.jsonl")
            )
        message_count = safe_int(entry.get("message_count"))
        indexed_message_count = safe_int(index_manifest.get("message_count"))
        message_delta = max(0, message_count - indexed_message_count)
        stale_age = age_seconds_since(index_manifest.get("created_at"))

        risk = (
            len(actions) * 1000
            + message_delta * 10
            + safe_int(entry.get("rollout_size")) // max(1, 1024 * 1024)
            + ((stale_age or 0) // 3600)
        )
        if risk > 0:
            row: dict[str, Any] = {
                "thread_ref": privacy_ref(thread_key or str(thread_dir or "")),
                "health_ok": health.get("ok") if "ok" in health else None,
                "message_count": message_count,
                "rollout_size": rollout_size,
                "index_message_delta": message_delta,
                "index_stale_age_seconds": stale_age,
                "recommended_action_ids": [str(item.get("id") or "unknown") for item in actions],
                "has_clean_source": bool(clean_manifest),
                "has_index": bool(index_manifest),
                "has_segments": bool(segments_manifest),
                "risk_score": risk,
            }
            if include_paths:
                row["thread_key"] = thread_key
                row["thread_dir"] = str(thread_dir) if thread_dir else None
            high_risk_threads.append(row)

    high_risk_threads.sort(key=lambda item: int(item.get("risk_score") or 0), reverse=True)
    return {
        "ok": status_counts["needs_maintenance"] == 0 and status_counts["unknown"] == 0,
        "registry": str(registry_path) if include_paths else None,
        "thread_count": len(threads),
        "status_counts": status_counts,
        "recommended_action_counts": dict(sorted(action_counts.items())),
        "severity_counts": dict(sorted(severity_counts.items())),
        "storage": {
            "rollout_bytes": total_rollout_bytes,
            "clean_source_bytes": total_clean_source_bytes,
            "generated_index_bytes": total_index_bytes,
            "index_amplification_ratio": ratio(total_index_bytes, total_clean_source_bytes),
        },
        "top_threads": high_risk_threads[: max(0, top)],
        "privacy": {
            "default_identifiers": "sha256 thread refs only",
            "message_bodies_read": False,
            "paths_included": include_paths,
        },
    }


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
    jobs_path = (
        Path(options.jobs_output).resolve()
        if options.jobs_output
        else default_question_jobs_path(registry_path)
    )
    now = datetime.now(timezone.utc)
    rollout_stat = rollout.stat()
    current_message_count, last_line = count_messages(rollout)
    current_anchor_count = len(parse_anchor_file(anchors))
    current_anchor_sha = file_sha256(anchors) if anchors.exists() else None

    manifest_path = index_dir / "manifest.json"
    messages_path = index_dir / "messages.jsonl"
    stable_sqlite_path = index_dir / "source_index.sqlite"
    sqlite_path = resolve_sqlite_index_path(stable_sqlite_path)
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
    if manifest and message_delta >= options.max_stale_messages:
        index_reasons.append(f"{message_delta} new messages since last index")
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
    clean_source_message_delta = max(0, current_message_count - clean_source_message_count)
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

    deep_graph_recommended = (
        current_message_count >= options.deep_graph_messages
        or rollout_stat.st_size >= options.deep_graph_bytes
    )

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
            action(
                "consider_graphify",
                "info",
                "thread size crossed the deep graph threshold",
                f'Use $graphify on "{graphify_corpus}" when conceptual navigation is worth the cost.',
            )
        )
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
        "index": {
            "dir": str(index_dir),
            "manifest": str(manifest_path),
            "sqlite": str(sqlite_path),
            "stable_sqlite": str(stable_sqlite_path),
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
            "turn_count": safe_int(clean_manifest.get("turn_count")) if clean_manifest else 0,
            "byte_delta": clean_byte_delta,
            "unindexed_message_ratio": ratio(clean_source_message_delta, current_message_count),
            "unindexed_byte_ratio": ratio(clean_byte_delta, rollout_stat.st_size),
            "activity_class": clean_source_activity_class,
        },
        "checkpoint": {
            "state": str(checkpoint_state),
            "due": checkpoint_due,
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
        "recommended_actions": actions,
    }

    return result


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
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
    parser.add_argument("--checkpoint-messages", type=int, default=30)
    parser.add_argument("--deep-graph-messages", type=int, default=1000)
    parser.add_argument("--deep-graph-bytes", type=int, default=100 * 1024 * 1024)
    parser.add_argument("--segment-threshold-bytes", type=int, default=100 * 1024 * 1024)
    parser.add_argument("--json", action="store_true", dest="json_output")
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
            print("registry memory health: " + ("OK" if result["ok"] else "needs maintenance"))
            print(f"threads: {result['thread_count']}")
            status_counts = result.get("status_counts") or {}
            print(
                "status: "
                f"ok={status_counts.get('ok', 0)} "
                f"needs={status_counts.get('needs_maintenance', 0)} "
                f"unknown={status_counts.get('unknown', 0)}"
            )
            action_counts = result.get("recommended_action_counts") or {}
            if action_counts:
                print("recommended actions:")
                for action_id, count in action_counts.items():
                    print(f"- {action_id}: {count}")
            else:
                print("no registry recommendations recorded")
            top_threads = result.get("top_threads") or []
            if top_threads:
                print("highest-risk thread refs:")
                for item in top_threads:
                    print(
                        f"- {item['thread_ref']}: "
                        f"{', '.join(item.get('recommended_action_ids') or []) or 'no action'} "
                        f"(delta={item.get('index_message_delta', 0)})"
                    )
        if args.exit_code and not result["ok"]:
            return 2
        return 0

    result = build_health_report(options_from_args(args))
    if args.json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        render_health_text(result)

    if args.exit_code and result["recommended_actions"]:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
