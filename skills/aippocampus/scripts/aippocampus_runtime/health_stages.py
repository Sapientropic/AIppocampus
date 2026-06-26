"""Staged helpers for building the AIppocampus health report."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aippocampus_runtime.artifacts.publish import (
    index_generation_diagnostics,
    resolve_sqlite_index_path,
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
    resolve_artifact_path,
)
from aippocampus_runtime.health_recall_availability import registry_recall_availability
from aippocampus_runtime.legacy_aliases import legacy_alias_diagnostics
from aippocampus_runtime.ops.storage_eviction import latest_intentional_eviction
from aippocampus_runtime.registry.store import registry_paths
from aippocampus_runtime.source.io_kernel import load_json_dict


@dataclass(frozen=True)
class HealthResolvedInputs:
    cwd: Path
    host_home: Path
    rollout: Path
    index_dir: Path
    anchors: Path
    graphify_corpus: Path
    segments_dir: Path
    checkpoint_state: Path
    clean_source_dir: Path
    registry_path: Path
    registry_recall: dict[str, Any]
    registry_resolution: dict[str, Any]
    legacy_aliases: dict[str, Any]


@dataclass(frozen=True)
class IndexHealthStage:
    manifest_path: Path
    sqlite_path: Path
    stable_sqlite_path: Path
    generations: dict[str, Any]
    manifest: dict[str, Any]
    intentional_eviction: dict[str, Any]
    reasons: list[str]
    stale: bool
    stale_age_seconds: int | None
    indexed_messages: int
    indexed_last_line: Any
    message_delta: int
    byte_delta: int
    activity_class: str
    rag_manifest: dict[str, Any]
    manifest_sha: str | None


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


def resolve_health_inputs(options: Any) -> HealthResolvedInputs:
    """Resolve local paths and registry state before readiness evaluation.

    This stage is deliberately IO-light: it locates the current rollout and
    resolves artifact paths, but it does not decide freshness, actions, compact
    health posture, or operator diagnostics. Keeping that boundary narrow makes
    future health splits less likely to smuggle product policy into path setup.
    """

    cwd = Path(options.cwd).resolve()
    host_home = codex_home()
    rollout = locate_rollout(cwd, host_home)
    index_dir = resolve_artifact_path(
        options.index_dir,
        cwd,
        default_thread_index_dir(cwd, rollout),
    )
    anchors = Path(options.anchors)
    if not anchors.is_absolute():
        anchors = cwd / anchors
    graphify_corpus = resolve_artifact_path(
        options.graphify_corpus,
        cwd,
        default_thread_graphify_corpus_dir(cwd, rollout),
    )
    segments_dir = resolve_artifact_path(
        options.segments_dir,
        cwd,
        default_thread_segments_dir(cwd, rollout),
    )
    checkpoint_state = resolve_artifact_path(
        options.checkpoint_state,
        cwd,
        default_thread_checkpoint_state_path(cwd, rollout),
    )
    clean_source_dir = resolve_artifact_path(
        options.clean_source_dir,
        cwd,
        default_thread_clean_source_dir(cwd, rollout),
    )
    registry_path = (
        Path(options.registry).resolve()
        if options.registry
        else registry_paths(Path(options.registry_dir).resolve() if options.registry_dir else None)[0]
    )
    registry_recall = registry_recall_availability(registry_path)
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
    return HealthResolvedInputs(
        cwd=cwd,
        host_home=host_home,
        rollout=rollout,
        index_dir=index_dir,
        anchors=anchors,
        graphify_corpus=graphify_corpus,
        segments_dir=segments_dir,
        checkpoint_state=checkpoint_state,
        clean_source_dir=clean_source_dir,
        registry_path=registry_path,
        registry_recall=registry_recall,
        registry_resolution=registry_resolution,
        legacy_aliases=legacy_aliases,
    )


def evaluate_index_state(
    *,
    index_dir: Path,
    rollout_size: int,
    current_message_count: int,
    current_anchor_sha: str | None,
    stale_message_threshold: int,
    now: datetime,
    options: Any,
) -> IndexHealthStage:
    """Evaluate source-index freshness without choosing foreground posture."""

    manifest_path = index_dir / "manifest.json"
    messages_path = index_dir / "messages.jsonl"
    stable_sqlite_path = index_dir / "source_index.sqlite"
    sqlite_path = resolve_sqlite_index_path(stable_sqlite_path)
    generations = index_generation_diagnostics(
        stable_sqlite_path,
        root=index_dir,
        include_paths=False,
    )
    manifest = load_json_dict(manifest_path).data
    intentional_eviction = {"detected": False}
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
            intentional_eviction = {"detected": False}
        else:
            intentional_eviction = candidate_eviction

    reasons: list[str] = []
    if not manifest:
        reasons.append("index manifest is missing")
    if not messages_path.exists():
        reasons.append("messages.jsonl is missing")
    if not sqlite_path.exists():
        if intentional_eviction.get("detected") and intentional_eviction.get("rebuildable"):
            reasons.append("source_index.sqlite intentionally evicted as rebuildable cache")
        else:
            reasons.append("source_index.sqlite is missing")
    indexed_messages = int(manifest.get("message_count") or 0)
    indexed_bytes = int(manifest.get("source_rollout_size") or 0)
    indexed_last_line = manifest.get("last_message_line")
    message_delta = max(0, current_message_count - indexed_messages)
    byte_delta = max(0, rollout_size - indexed_bytes)
    if manifest and message_delta >= stale_message_threshold:
        reasons.append(f"{message_delta} latest visible message(s) are newer than the index")
    if manifest and byte_delta >= options.max_stale_bytes:
        reasons.append(f"{byte_delta} new rollout bytes since last index")
    if manifest and current_anchor_sha and manifest.get("anchor_sha256") != current_anchor_sha:
        reasons.append("thread-anchors.md changed since last index")
    rag_manifest = dict(manifest.get("rag") or {})
    if manifest and not rag_manifest.get("enabled"):
        reasons.append("rag-lite chunk cache is missing from index manifest")

    stale_age_seconds = age_seconds_since(manifest.get("created_at"), now=now)
    return IndexHealthStage(
        manifest_path=manifest_path,
        sqlite_path=sqlite_path,
        stable_sqlite_path=stable_sqlite_path,
        generations=generations,
        manifest=manifest,
        intentional_eviction=intentional_eviction,
        reasons=reasons,
        stale=bool(reasons),
        stale_age_seconds=stale_age_seconds,
        indexed_messages=indexed_messages,
        indexed_last_line=indexed_last_line,
        message_delta=message_delta,
        byte_delta=byte_delta,
        activity_class=activity_class(
            message_delta=message_delta,
            byte_delta=byte_delta,
            stale_age_seconds=stale_age_seconds,
            max_stale_messages=options.max_stale_messages,
            max_stale_bytes=options.max_stale_bytes,
        ),
        rag_manifest=rag_manifest,
        manifest_sha=file_sha256(manifest_path) if manifest_path.exists() else None,
    )
