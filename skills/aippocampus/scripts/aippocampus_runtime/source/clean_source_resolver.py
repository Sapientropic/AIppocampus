"""Shared clean-source path resolution for foreground reopen surfaces."""

from __future__ import annotations

from pathlib import Path

from aippocampus_runtime import core

LEGACY_PROJECT_CLEAN_SOURCE_DIR = Path(".aippocampus") / "clean-source"


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
    return default_dir.resolve()


__all__ = ["LEGACY_PROJECT_CLEAN_SOURCE_DIR", "resolve_clean_source_dir"]
