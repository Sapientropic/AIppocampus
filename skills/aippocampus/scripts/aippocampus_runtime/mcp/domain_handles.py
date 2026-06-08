"""Short-lived MCP handles for continuity-domain routes."""

from __future__ import annotations

import base64
import json
import time
from pathlib import Path
from typing import Any

from aippocampus_runtime.mcp.source_ref_registry import registry_source_fingerprints_for_refs
from aippocampus_runtime.recall.continuity_domains import (
    clean_source_fingerprint,
    continuity_domain_snapshot_fingerprint,
)

HANDLE_PREFIX = "aippo-nav:"
HANDLE_SCHEMA_VERSION = 1
DEFAULT_TTL_SECONDS = 30 * 60
MAX_HANDLE_REFS = 3


def _encode_handle(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    encoded = base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii").rstrip("=")
    return HANDLE_PREFIX + encoded


def continuity_domain_route_handle(
    *,
    source_dir: Path,
    snapshot_path: Path | None,
    domain_id: str,
    source_refs: list[dict[str, Any]],
    registry_dir: Path | None,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
) -> str:
    now = int(time.time())
    refs = source_refs[:MAX_HANDLE_REFS]
    return _encode_handle(
        {
            "schema_version": HANDLE_SCHEMA_VERSION,
            "kind": "continuity_domain",
            "domain_id": domain_id,
            "source_refs": refs,
            "source_fingerprint": clean_source_fingerprint(source_dir),
            "snapshot_fingerprint": continuity_domain_snapshot_fingerprint(
                snapshot_path=snapshot_path,
                clean_source_dir=source_dir,
            ),
            "registry_source_fingerprints": registry_source_fingerprints_for_refs(
                refs,
                registry_dir=registry_dir,
            ),
            "issued_unix": now,
            "expires_unix": now + max(1, ttl_seconds),
        }
    )
