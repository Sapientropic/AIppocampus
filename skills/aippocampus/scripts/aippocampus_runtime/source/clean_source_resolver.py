"""Shared clean-source path resolution for foreground reopen surfaces."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from aippocampus_runtime import core

LEGACY_PROJECT_CLEAN_SOURCE_DIR = Path(".aippocampus") / "clean-source"


def _manifest_payload(clean_source_dir: Path) -> dict[str, Any]:
    try:
        payload = json.loads((clean_source_dir / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _manifest_cwd_key(payload: dict[str, Any]) -> str:
    cwd = payload.get("cwd")
    if not cwd:
        session_meta = payload.get("session_meta")
        if isinstance(session_meta, dict):
            cwd = session_meta.get("cwd")
    if not cwd:
        return ""
    try:
        return core.path_identity_key(str(cwd))
    except (OSError, ValueError):
        return str(cwd).casefold()


def _manifest_freshness(clean_source_dir: Path, payload: dict[str, Any]) -> float:
    value = payload.get("source_transcript_mtime") or payload.get("source_rollout_mtime")
    if isinstance(value, int | float):
        return float(value)
    try:
        return (clean_source_dir / "messages.jsonl").stat().st_mtime
    except OSError:
        return 0.0


def fresher_same_cwd_registry_clean_source(resolved: Path, cwd: str | Path) -> Path | None:
    """Find a fresher same-cwd registry artifact when the host locator is stale.

    Long-running hosts and CLI subprocesses can disagree about the active Codex
    thread. Registry manifests are already source-built artifacts, so the safe
    default tie-breaker is only: same cwd, newer source transcript, and still
    inside the registry `threads/*/clean-source` layout. Never use project-local
    compatibility clean source as an implicit fallback here.
    """

    manifest = _manifest_payload(resolved)
    try:
        target_cwd_key = core.path_identity_key(cwd)
    except (OSError, ValueError):
        target_cwd_key = str(cwd).casefold()
    current_cwd_key = _manifest_cwd_key(manifest)
    if current_cwd_key and current_cwd_key != target_cwd_key:
        return None
    try:
        threads_root = resolved.parent.parent.resolve()
    except OSError:
        return None
    if threads_root.name != "threads" or not threads_root.exists():
        return None
    current_freshness = _manifest_freshness(resolved, manifest)
    best: tuple[float, Path] | None = None
    try:
        thread_dirs = list(threads_root.iterdir())
    except OSError:
        return None
    for thread_dir in thread_dirs:
        candidate = thread_dir / "clean-source"
        if candidate == resolved or not (candidate / "messages.jsonl").exists():
            continue
        candidate_manifest = _manifest_payload(candidate)
        if _manifest_cwd_key(candidate_manifest) != target_cwd_key:
            continue
        freshness = _manifest_freshness(candidate, candidate_manifest)
        if freshness <= current_freshness:
            continue
        if best is None or freshness > best[0]:
            best = (freshness, candidate)
    return best[1].resolve() if best else None


def resolve_clean_source_dir(
    cwd: str | Path | None,
    clean_source_dir: str | Path | None = None,
) -> Path:
    """Resolve the clean-source directory for recall/search/reopen paths.

    The implicit default is the provider-neutral AIppocampus registry, not the
    project-local `.aippocampus/clean-source` compatibility artifact. That old
    fallback can contain stale generated material from another thread and has
    caused MCP foreground actions to open unrelated sources. Keep legacy/local
    directories usable only when the caller explicitly passes `clean_source_dir`.
    """

    root = core.canonical_path(cwd or Path.cwd())
    default_dir = core.default_thread_clean_source_dir(root)
    if clean_source_dir is not None:
        return core.resolve_artifact_path(clean_source_dir, root, default_dir).resolve()
    resolved = default_dir.resolve()
    return fresher_same_cwd_registry_clean_source(resolved, root) or resolved


__all__ = [
    "LEGACY_PROJECT_CLEAN_SOURCE_DIR",
    "fresher_same_cwd_registry_clean_source",
    "resolve_clean_source_dir",
]
