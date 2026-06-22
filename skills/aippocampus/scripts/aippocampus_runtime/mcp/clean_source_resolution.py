"""MCP clean-source resolution helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from aippocampus_runtime.source.clean_source_resolver import resolve_clean_source_dir


def resolve_mcp_clean_source_dir(
    *,
    cwd: str | Path,
    clean_source_dir: str | Path | None,
    continuity_domains_snapshot: Any = None,
) -> Path:
    """Resolve MCP recall source without restoring project-local defaults.

    Ordinary MCP recall/search defaults use the provider-neutral clean-source
    resolver. The only narrow exception is an explicit continuity-domain
    snapshot, because domain handles need the clean source that was
    materialized with that snapshot to verify freshness and reopen refs.
    """

    resolved = resolve_clean_source_dir(cwd, clean_source_dir)
    if (resolved / "messages.jsonl").exists() or clean_source_dir or not continuity_domains_snapshot:
        return resolved
    try:
        snapshot_path = Path(str(continuity_domains_snapshot)).resolve()
        cwd_path = Path(cwd).resolve()
    except (OSError, ValueError):
        return resolved
    candidates: list[Path] = []
    if snapshot_path.parent.name == "continuity-domain-snapshots":
        candidates.append(snapshot_path.parent.parent / "clean-source")
    candidates.append(cwd_path / ".aippocampus" / "clean-source")
    for candidate in candidates:
        if (candidate / "messages.jsonl").exists():
            return candidate.resolve()
    return resolved


__all__ = ["resolve_mcp_clean_source_dir"]
