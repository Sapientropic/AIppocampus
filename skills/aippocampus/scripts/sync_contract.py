#!/usr/bin/env python3
"""Shared manifest, transport, and privacy contract for sync routes."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from aippocampuslib import now_utc

SYNC_BUNDLE_KIND = "aippocampus_sync_bundle"
SYNC_SCHEMA_VERSION = 1
SYNC_MANIFEST_NAME = "aippocampus-sync-manifest.json"
LOCAL_FOLDER_BACKEND = "local_folder"
RAW_ROLLOUT_DEFAULT = "excluded"
RAW_ROLLOUT_INCLUDE_FLAG = "--include-raw"


def sync_privacy_boundary(*, include_raw: bool) -> dict[str, Any]:
    return {
        "clean_source_is_private": True,
        "raw_rollout_default": RAW_ROLLOUT_DEFAULT,
        "raw_rollout_included_only_with": RAW_ROLLOUT_INCLUDE_FLAG,
        "raw_rollout_included": bool(include_raw),
    }


def sync_transport_metadata(
    *,
    kind: str,
    manifest_object: str | Path | None = None,
) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "kind": kind,
        "raw_rollout_default": RAW_ROLLOUT_DEFAULT,
    }
    if manifest_object is not None:
        metadata["manifest_object"] = str(manifest_object).replace("\\", "/")
    return metadata


def build_sync_manifest(
    *,
    backend: str,
    clean_source_delta: dict[str, Any],
    files: list[dict[str, Any]],
    include_raw: bool,
    transport: dict[str, Any] | None = None,
) -> dict[str, Any]:
    manifest: dict[str, Any] = {
        "schema_version": SYNC_SCHEMA_VERSION,
        "kind": SYNC_BUNDLE_KIND,
        "created_at": now_utc(),
        "backend": backend,
        "raw_rollout_included": include_raw,
        "clean_source_delta": clean_source_delta,
        "files": files,
        "file_count": len(files),
        "privacy_boundary": sync_privacy_boundary(include_raw=include_raw),
    }
    if transport is not None:
        manifest["transport"] = transport
    return manifest
