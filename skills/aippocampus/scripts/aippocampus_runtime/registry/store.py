#!/usr/bin/env python3
"""Storage primitives for the machine-wide AIppocampus thread registry."""

from __future__ import annotations

import json
import re
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

from aippocampus_runtime.artifacts.publish import ArtifactLeaseBusyError, artifact_lease
from aippocampus_runtime.core import aippocampus_registry_dir, now_utc
from aippocampus_runtime.io_mtime_cache import load_json_object

REGISTRY_SCHEMA_VERSION = 1
REGISTRY_WRITER_LEASE_NAME = ".threads-registry.lock"
DEFAULT_REGISTRY_WRITER_WAIT_TIMEOUT_SECONDS = 10.0


class RegistryReadError(RuntimeError):
    """Raised when an existing registry file cannot be safely interpreted."""


class RegistryWriteBusyError(RuntimeError):
    """Raised when another local agent is updating registry metadata."""

    code = "registry_writer_busy"
    retryable = True

    def __init__(
        self,
        registry_path: Path,
        *,
        wait_timeout_seconds: float,
    ) -> None:
        self.registry_path = registry_path
        self.wait_timeout_seconds = wait_timeout_seconds
        super().__init__(
            "Registry writer lease is held by another local agent; retry after "
            f"the current writer finishes. registry={registry_path}"
        )


def default_registry_dir() -> Path:
    return aippocampus_registry_dir()


def registry_paths(registry_dir: Path | None = None) -> tuple[Path, Path]:
    root = (registry_dir or default_registry_dir()).resolve()
    return root / "threads.json", root / "threads.md"


def registry_root(registry_dir: Path | None = None) -> Path:
    return (registry_dir or default_registry_dir()).resolve()


def safe_slug(value: str, fallback: str = "thread") -> str:
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "-", value).strip()
    value = re.sub(r"\s+", "-", value)
    value = value.rstrip(".- ")
    return value[:120] or fallback


def thread_store_dir(thread_key: str, registry_dir: Path | None = None) -> Path:
    return registry_root(registry_dir) / "threads" / safe_slug(thread_key)


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def load_existing_json_object(path: Path, *, label: str) -> dict:
    if not path.exists():
        return {}
    try:
        data = load_json_object(path)
    except json.JSONDecodeError as exc:
        raise RegistryReadError(
            f"Cannot read {label} at {path}: invalid JSON at line {exc.lineno}, "
            f"column {exc.colno}: {exc.msg}"
        ) from exc
    except OSError as exc:
        raise RegistryReadError(f"Cannot read {label} at {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise RegistryReadError(f"Cannot read {label} at {path}: expected a JSON object")
    return data


def load_registry(path: Path) -> dict:
    # The registry is the machine-wide continuity map. Optional sidecar manifests
    # can fail open, but a corrupt existing registry must stop write paths instead
    # of being treated as an empty registry and overwritten.
    registry = load_existing_json_object(path, label="thread registry")
    if not registry:
        registry = {"schema_version": REGISTRY_SCHEMA_VERSION, "updated_at": None, "threads": []}
    try:
        schema_version = int(registry.get("schema_version") or REGISTRY_SCHEMA_VERSION)
    except (TypeError, ValueError) as exc:
        raise RegistryReadError(
            f"Cannot read thread registry at {path}: unsupported schema_version "
            f"{registry.get('schema_version')!r}; run aippocampus registry migrate --json "
            "or rebuild the local registry"
        ) from exc
    if schema_version != REGISTRY_SCHEMA_VERSION:
        raise RegistryReadError(
            f"Cannot read thread registry at {path}: unsupported schema_version "
            f"{schema_version}; run aippocampus registry migrate --json or rebuild the local registry"
        )
    registry["schema_version"] = REGISTRY_SCHEMA_VERSION
    registry.setdefault("threads", [])
    return registry


def upsert_thread(registry: dict, entry: dict) -> dict:
    threads = [
        item
        for item in registry.get("threads", [])
        if item.get("thread_key") != entry.get("thread_key")
    ]
    threads.append(entry)
    threads.sort(key=lambda item: item.get("updated_at") or "", reverse=True)
    registry["threads"] = threads
    registry["updated_at"] = now_utc()
    return registry


@contextmanager
def registry_writer_lease(
    json_path: Path,
    *,
    wait_timeout_seconds: float = DEFAULT_REGISTRY_WRITER_WAIT_TIMEOUT_SECONDS,
) -> Iterator[Path]:
    try:
        with artifact_lease(
            json_path.parent,
            REGISTRY_WRITER_LEASE_NAME,
            wait_timeout_seconds=wait_timeout_seconds,
        ) as lease_path:
            yield lease_path
    except ArtifactLeaseBusyError as exc:
        raise RegistryWriteBusyError(
            json_path,
            wait_timeout_seconds=float(wait_timeout_seconds),
        ) from exc


def render_registry_markdown(registry: dict) -> str:
    lines = [
        "# Thread Memory Registry",
        "",
        "Machine-wide index of local Codex thread memories. Use this as the first discovery step in a new thread.",
        "",
        f"- Updated: `{registry.get('updated_at')}`",
        f"- Threads: `{len(registry.get('threads', []))}`",
        "",
    ]
    for entry in registry.get("threads", []):
        health = entry.get("health") or {}
        caps = entry.get("capabilities") or {}
        paths = entry.get("paths") or {}
        lines.extend(
            [
                f"## {entry.get('title') or entry.get('workspace_name') or entry.get('thread_key')}",
                "",
                f"- Thread key: `{entry.get('thread_key')}`",
                f"- Updated: `{entry.get('updated_at')}`",
                f"- Project: `{entry.get('project_label') or entry.get('workspace_name')}`",
                f"- Workspace: `{paths.get('workspace')}`",
                f"- Messages: `{entry.get('message_count')}`",
                f"- Size: `{entry.get('rollout_size')}` bytes",
                f"- Anchors: `{entry.get('anchor_count')}`",
                f"- Health: `{'OK' if health.get('ok') else 'Needs maintenance'}`",
                f"- RAG-lite chunks: `{caps.get('rag_chunks')}`",
                f"- SQLite: `{paths.get('sqlite')}`",
            ]
        )
        if paths.get("dashboard_html"):
            lines.append(f"- Dashboard HTML: `{paths.get('dashboard_html')}`")
        if paths.get("vault"):
            lines.append(f"- Vault: `{paths.get('vault')}`")
        if entry.get("keywords"):
            lines.extend(["", "Keywords:", ""])
            lines.append(", ".join(f"`{keyword}`" for keyword in entry.get("keywords", [])[:20]))
        if entry.get("project_tags"):
            lines.extend(["", "Project tags:", ""])
            lines.append(", ".join(f"`{tag}`" for tag in entry.get("project_tags", [])[:20]))
        if entry.get("anchor_titles"):
            lines.extend(["", "Anchors:", ""])
            lines.extend(f"- {title}" for title in entry.get("anchor_titles", [])[:10])
        if entry.get("summary"):
            lines.extend(["", entry["summary"]])
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp-{id(text)}-{time.time_ns()}")
    tmp.write_text(text, encoding="utf-8", newline="\n")
    tmp.replace(path)


def save_registry(registry: dict, json_path: Path, md_path: Path) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    _write_text_atomic(
        json_path,
        json.dumps(registry, ensure_ascii=False, indent=2),
    )
    _write_text_atomic(md_path, render_registry_markdown(registry))


def update_registry(
    json_path: Path,
    md_path: Path,
    updater: Callable[[dict], dict],
    *,
    wait_timeout_seconds: float = DEFAULT_REGISTRY_WRITER_WAIT_TIMEOUT_SECONDS,
) -> dict:
    # Registry updates are read-modify-write operations over JSON plus Markdown.
    # Holding the same-directory lease across load/upsert/save prevents two local
    # MCP/CLI agents from both reading the old registry and publishing whichever
    # write finishes last. Read-only registry queries intentionally stay lock-free.
    with registry_writer_lease(
        json_path,
        wait_timeout_seconds=wait_timeout_seconds,
    ):
        registry = updater(load_registry(json_path))
        save_registry(registry, json_path, md_path)
        return registry
