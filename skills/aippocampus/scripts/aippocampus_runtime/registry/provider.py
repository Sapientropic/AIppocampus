"""Small provider-aware helpers for registry build orchestration."""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

from aippocampuslib import public_session_meta, read_session_meta

from .store import safe_slug


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
    return [
        sys.executable,
        str(script_dir / script_name),
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
    digest = hashlib.sha1(str(cwd).casefold().encode("utf-8")).hexdigest()[:12]
    return f"workspace:{safe_slug(cwd.name)}:{digest}"
