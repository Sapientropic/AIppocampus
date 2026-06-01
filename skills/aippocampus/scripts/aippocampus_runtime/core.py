#!/usr/bin/env python3
"""Shared helpers for Codex Desktop thread-memory indexing scripts."""

from __future__ import annotations

import hashlib
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from aippocampus_runtime import anchor_graph as _anchor_graph
from aippocampus_runtime import safety as _safety
from aippocampus_runtime import text as _text
from aippocampus_runtime.cli import errors as _cli_errors
from aippocampus_runtime.source import rollout as _rollout

build_anchor_graph = _anchor_graph.build_anchor_graph
benchmark_sensitive_text_policy = _safety.benchmark_sensitive_text_policy
benchmark_text_is_sensitive = _safety.benchmark_text_is_sensitive
cli_error_class_for_error_code = _cli_errors.cli_error_class_for_error_code
cli_error_code_from_message = _cli_errors.cli_error_code_from_message
cli_error_payload = _cli_errors.cli_error_payload
cli_error_payload_from_message = _cli_errors.cli_error_payload_from_message
cli_public_error_object = _cli_errors.cli_public_error_object
cli_exit_code_for_error_code = _cli_errors.cli_exit_code_for_error_code
compact_text = _text.compact_text
deepseek_cache_metrics_from_usage = _safety.deepseek_cache_metrics_from_usage
INJECTED_INSTRUCTION_PREFIXES = _rollout.INJECTED_INSTRUCTION_PREFIXES
is_loopback_host = _safety.is_loopback_host
empty_turn = _rollout.empty_turn
extract_message = _rollout.extract_message
is_injected_instruction_text = _rollout.is_injected_instruction_text
iter_jsonl = _rollout.iter_jsonl
iter_messages = _rollout.iter_messages
message_phase = _rollout.message_phase
normalize_rollout = _rollout.normalize_rollout
parse_anchor_file = _anchor_graph.parse_anchor_file
sanitize_external_model_payload = _safety.sanitize_external_model_payload
sanitize_external_model_text = _safety.sanitize_external_model_text
tool_payload_kind = _rollout.tool_payload_kind
validate_http_endpoint_url = _safety.validate_http_endpoint_url
validate_private_credential_transport = _safety.validate_private_credential_transport


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def codex_home() -> Path:
    env = os.environ.get("CODEX_HOME")
    if env:
        return Path(env)
    return Path.home() / ".codex"


def aippocampus_home() -> Path | None:
    env = os.environ.get("AIPPOCAMPUS_HOME")
    return Path(env) if env else None


def safe_path_name(value: str, fallback: str = "item") -> str:
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "-", str(value)).strip()
    value = re.sub(r"\s+", "-", value)
    value = value.rstrip(".- ")
    return value[:120] or fallback


def aippocampus_registry_resolution(home: Path | None = None) -> dict[str, Any]:
    """Resolve generated AIppocampus registry storage without moving data.

    `AIPPOCAMPUS_REGISTRY_DIR` is the exact provider-neutral registry root.
    `AIPPOCAMPUS_HOME` is an optional broader home concept whose registry lives
    under `registry/`. Legacy Codex homes remain a fallback only, so existing
    users keep their data while new non-Codex setups can avoid `CODEX_HOME`.
    """

    env = os.environ.get("AIPPOCAMPUS_REGISTRY_DIR")
    if env:
        return {
            "path": str(Path(env)),
            "source": "AIPPOCAMPUS_REGISTRY_DIR",
            "legacy_fallback": False,
        }
    legacy_env = os.environ.get("THREAD_MEMORY_REGISTRY_DIR")
    if legacy_env:
        return {
            "path": str(Path(legacy_env)),
            "source": "THREAD_MEMORY_REGISTRY_DIR",
            "legacy_fallback": True,
        }
    aippo_home = aippocampus_home()
    if aippo_home:
        return {
            "path": str(aippo_home / "registry"),
            "source": "AIPPOCAMPUS_HOME/registry",
            "legacy_fallback": False,
        }
    legacy_home = home or codex_home()
    return {
        "path": str(legacy_home / "aippocampus-registry"),
        "source": (
            "CODEX_HOME/aippocampus-registry"
            if os.environ.get("CODEX_HOME") or home
            else "default_CODEX_HOME/aippocampus-registry"
        ),
        "legacy_fallback": True,
    }


def aippocampus_registry_dir(home: Path | None = None) -> Path:
    return Path(str(aippocampus_registry_resolution(home)["path"]))


def canonical_path(path: str | Path) -> Path:
    return Path(path).resolve()


def path_identity_key(path: str | Path) -> str:
    return str(canonical_path(path)).casefold()


def workspace_identity(workspace: str | Path) -> str:
    text = str(workspace or "")
    path = Path(text)
    # Workspace values are sometimes human/project labels rather than host
    # paths. Only absolute paths get canonicalized; resolving labels against the
    # current process cwd would make cache and policy keys drift across machines.
    if text.startswith("/") or path.is_absolute():
        return str(canonical_path(path))
    return text


def workspace_identity_key(workspace: str | Path) -> str:
    return workspace_identity(workspace).casefold()


def workspace_fingerprint(workspace: str | Path, *, prefix: str = "workspace") -> str:
    digest = hashlib.sha256(workspace_identity_key(workspace).encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{digest}"


def norm_path(path: str | Path) -> str:
    return path_identity_key(path)


ROLLOUT_DISCOVERY_DIRS = ("sessions", "archived_sessions")


def codex_provider(home: Path | None = None):
    # Keep this import lazy so partially synced hook installs that only need
    # `codex_home()` / `now_utc()` do not crash before the provider package is
    # copied. Source discovery still fails loudly when the provider is actually
    # needed, which is easier to diagnose than a prompt-hook startup failure.
    from conversation_sources import CodexConversationProvider

    return CodexConversationProvider(home or codex_home())


def iter_rollouts(home: Path) -> Iterable[Path]:
    """Yield Codex Desktop raw rollouts from live and app-archived storage.

    Codex Desktop's thread archive can move rollout JSONL files from the dated
    `sessions/` tree into the flat `archived_sessions/` directory. AIppocampus
    treats both locations as immutable audit sources; this is not the same as
    the optional cold-archive flow that writes generated gzip copies.
    """

    yield from codex_provider(home).iter_rollouts()


def read_session_meta(path: Path) -> dict | None:
    return codex_provider().read_metadata(path)


def public_session_meta(meta: dict | None) -> dict:
    if not meta:
        return {}
    keys = [
        "id",
        "timestamp",
        "cwd",
        "originator",
        "cli_version",
        "source",
        "thread_source",
        "model_provider",
    ]
    return {key: meta[key] for key in keys if key in meta}


def locate_rollout(cwd: str | Path, home: Path | None = None, latest: bool = False) -> Path:
    return codex_provider(home or codex_home()).locate_current(cwd, latest=latest).path


def thread_key_from_rollout(rollout: str | Path, meta: dict | None = None) -> str:
    rollout_path = Path(rollout)
    session_meta = (
        meta if meta is not None else public_session_meta(read_session_meta(rollout_path))
    )
    return codex_provider().thread_key(rollout_path, session_meta)


def workspace_thread_key(cwd: str | Path) -> str:
    cwd_path = canonical_path(cwd)
    # Workspace fallback keys name existing registry directories. Keep the
    # legacy suffix stable until `default_thread_store_dir` has dual lookup.
    digest = hashlib.sha1(workspace_identity_key(cwd_path).encode("utf-8")).hexdigest()[:12]
    return f"workspace:{safe_path_name(cwd_path.name, 'workspace')}:{digest}"


def default_thread_store_dir(
    cwd: str | Path,
    rollout: str | Path | None = None,
    *,
    home: Path | None = None,
    registry_dir: Path | None = None,
) -> Path:
    """Return the machine-wide artifact store for a thread.

    AIppocampus is a cross-project continuity layer, so generated recall
    artifacts should not default to the active repository. A workspace-local
    `.aippocampus` path is still valid when explicitly requested, but the
    implicit default is the provider-neutral AIppocampus registry, with legacy
    CODEX_HOME storage used only as a compatibility fallback.
    """

    cwd_path = canonical_path(cwd)
    rollout_path: Path | None = Path(rollout) if rollout else None
    if rollout_path is None:
        try:
            rollout_path = locate_rollout(cwd_path, home or codex_home())
        except Exception:
            rollout_path = None
    thread_key = (
        thread_key_from_rollout(rollout_path) if rollout_path else workspace_thread_key(cwd_path)
    )
    root = (registry_dir or aippocampus_registry_dir(home)).resolve()
    return root / "threads" / safe_path_name(thread_key, "thread")


def default_thread_index_dir(cwd: str | Path, rollout: str | Path | None = None) -> Path:
    return default_thread_store_dir(cwd, rollout) / "index"


def default_thread_clean_source_dir(cwd: str | Path, rollout: str | Path | None = None) -> Path:
    return default_thread_store_dir(cwd, rollout) / "clean-source"


def default_thread_segments_dir(cwd: str | Path, rollout: str | Path | None = None) -> Path:
    return default_thread_index_dir(cwd, rollout) / "segments"


def default_thread_graphify_corpus_dir(cwd: str | Path, rollout: str | Path | None = None) -> Path:
    return default_thread_index_dir(cwd, rollout) / "graphify-corpus"


def default_thread_checkpoint_state_path(
    cwd: str | Path, rollout: str | Path | None = None
) -> Path:
    return default_thread_index_dir(cwd, rollout) / "checkpoint_state.json"


def default_thread_retention_dir(cwd: str | Path, rollout: str | Path | None = None) -> Path:
    return default_thread_index_dir(cwd, rollout) / "retention"


def default_thread_cold_archive_dir(cwd: str | Path, rollout: str | Path | None = None) -> Path:
    return default_thread_index_dir(cwd, rollout) / "cold-archives"


def resolve_artifact_path(value: str | Path | None, cwd: str | Path, default_path: Path) -> Path:
    if value is None:
        return default_path
    path = Path(value)
    return path if path.is_absolute() else Path(cwd).resolve() / path


def file_sha256(path: Path, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest()
