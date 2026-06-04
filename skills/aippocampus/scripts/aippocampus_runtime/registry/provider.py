"""Small provider-aware helpers for registry build orchestration."""

from __future__ import annotations

import sys
from pathlib import Path

from aippocampus_runtime.core import public_session_meta, read_session_meta, workspace_thread_key

BUILD_MODULES = {
    "build_clean_source.py": "aippocampus_runtime.source.clean_source",
    "build_index.py": "aippocampus_runtime.recall.index_builder",
}


def current_thread_build_cmd(
    script_dir: Path,
    script_name: str,
    cwd: Path,
    rollout: Path | None,
    provider_name: str = "codex",
) -> list[str]:
    # Provider resolution happens at the orchestration boundary. Pass the
    # already-located source path to child builders so they do not silently
    # rediscover by cwd through the legacy Codex default.
    rollout_args = [] if rollout is None else ["--rollout", str(rollout)]
    module = BUILD_MODULES.get(script_name)
    entrypoint = ["-m", module] if module else [str(script_dir / script_name)]
    return [
        sys.executable,
        *entrypoint,
        "--cwd",
        str(cwd),
        "--provider",
        provider_name,
        *rollout_args,
        "--json",
    ]


def thread_key_for(cwd: Path, manifest: dict, rollout: Path | None) -> str:
    source_thread_key = manifest.get("source_thread_key")
    if source_thread_key:
        return str(source_thread_key)
    provider_name = str(manifest.get("source_provider") or "codex")
    session_id = (manifest.get("session_meta") or {}).get("id")
    if not session_id and rollout:
        session_id = (public_session_meta(read_session_meta(rollout)) or {}).get("id")
    if session_id:
        if provider_name and provider_name != "codex":
            return f"{provider_name}:session:{session_id}"
        return f"session:{session_id}"
    return workspace_thread_key(cwd)
