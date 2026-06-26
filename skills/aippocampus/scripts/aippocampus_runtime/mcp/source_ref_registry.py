"""Registry lookup helpers for MCP source-ref reopen paths."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from aippocampus_runtime.recall.continuity_domains import clean_source_fingerprint
from aippocampus_runtime.registry import api as registry


def registry_clean_source_dir_for_ref(
    ref: dict[str, Any],
    *,
    registry_dir: Path | None,
) -> Path | None:
    """Return a registered clean-source dir for a thread-keyed source ref.

    This helper deliberately requires an explicit `thread_key`; registry lookup
    is a cross-thread reopen path, not a fuzzy search over every local thread.
    """

    thread_key = str(ref.get("thread_key") or "")
    if not thread_key or registry_dir is None:
        return None
    try:
        registry_path, _ = registry.registry_paths(registry_dir)
        registry_payload = registry.load_registry(registry_path)
    except (OSError, ValueError, registry.RegistryReadError):
        registry_payload = {"threads": []}
    for entry in registry_payload.get("threads") or []:
        if not isinstance(entry, dict) or str(entry.get("thread_key") or "") != thread_key:
            continue
        raw_paths = entry.get("paths")
        paths: dict[str, Any] = raw_paths if isinstance(raw_paths, dict) else {}
        candidates = []
        if paths.get("clean_source_dir"):
            candidates.append(Path(str(paths["clean_source_dir"])))
        if paths.get("clean_source_messages_jsonl"):
            candidates.append(Path(str(paths["clean_source_messages_jsonl"])).parent)
        for candidate in candidates:
            if (candidate / "messages.jsonl").exists():
                return candidate
    fallback = registry.thread_store_dir(thread_key, registry_dir) / "clean-source"
    return fallback if (fallback / "messages.jsonl").exists() else None


def registry_source_fingerprints_for_refs(
    refs: list[dict[str, Any]],
    *,
    registry_dir: Path | None,
) -> dict[str, str]:
    fingerprints: dict[str, str] = {}
    for ref in refs:
        thread_key = str(ref.get("thread_key") or "")
        if not thread_key:
            continue
        target_dir = registry_clean_source_dir_for_ref(ref, registry_dir=registry_dir)
        if target_dir is not None:
            fingerprints[thread_key] = clean_source_fingerprint(target_dir)
    return fingerprints


def registry_source_fingerprint_invalidations(
    refs: list[dict[str, Any]],
    *,
    registry_dir: Path | None,
    expected_fingerprints: dict[str, Any],
) -> list[str]:
    invalidations: list[str] = []
    for ref in refs:
        thread_key = str(ref.get("thread_key") or "")
        if not thread_key:
            continue
        target_dir = registry_clean_source_dir_for_ref(ref, registry_dir=registry_dir)
        if target_dir is None:
            continue
        expected = expected_fingerprints.get(thread_key)
        if not expected:
            invalidations.append("registry_clean_source_fingerprint_missing")
            continue
        if str(expected) != clean_source_fingerprint(target_dir):
            invalidations.append("registry_clean_source_fingerprint_changed")
    return invalidations


def source_candidate_dirs_for_ref(
    ref: dict[str, Any],
    *,
    clean_source_dir: Path,
    registry_dir: Path | None,
) -> list[Path]:
    registry_clean_source_dir = registry_clean_source_dir_for_ref(ref, registry_dir=registry_dir)
    if ref.get("thread_key"):
        return [registry_clean_source_dir] if registry_clean_source_dir is not None else []
    return [clean_source_dir]
