"""Continuity-domain and pathlet route projection for MCP recall_context."""

from __future__ import annotations

import base64
import json
import time
from pathlib import Path
from typing import Any

from aippocampus_runtime.core import compact_text, sanitize_external_model_text, stable_text_id
from aippocampus_runtime.mcp.domain_handles import continuity_domain_route_handle
from aippocampus_runtime.recall.continuity_domains import (
    clean_source_fingerprint,
    load_continuity_domains_snapshot,
    match_continuity_domain_pointers,
)
from aippocampus_runtime.recall.continuity_pathlets import match_continuity_pathlet_pointers

HANDLE_PREFIX = "aippo-nav:"
HANDLE_SCHEMA_VERSION = 1
DEFAULT_TTL_SECONDS = 30 * 60
MAX_HANDLE_REFS = 3


def _safe_text(value: Any, chars: int) -> str:
    sanitized, _ = sanitize_external_model_text(str(value or ""))
    return compact_text(sanitized, chars)


def _clean_ref(item: dict[str, Any]) -> dict[str, Any]:
    clean = {
        "thread_key": item.get("thread_key"),
        "source_id": item.get("source_id"),
        "message_id": item.get("message_id") or item.get("id"),
        "turn_id": item.get("turn_id"),
        "turn_index": item.get("turn_index"),
        "line": item.get("line") or item.get("source_line"),
        "phase": item.get("phase") or "",
    }
    return {key: value for key, value in clean.items() if value not in {None, ""}}


def _encode_handle(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    encoded = base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii").rstrip("=")
    return HANDLE_PREFIX + encoded


def _source_ref_handle(
    *,
    source_dir: Path,
    route_id: str,
    source_refs: list[dict[str, Any]],
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
) -> str:
    now = int(time.time())
    return _encode_handle(
        {
            "schema_version": HANDLE_SCHEMA_VERSION,
            "kind": "source_ref",
            "route_id": route_id,
            "evidence_level": "needs_reopen",
            "source_refs": source_refs[:MAX_HANDLE_REFS],
            "source_fingerprint": clean_source_fingerprint(source_dir),
            "issued_unix": now,
            "expires_unix": now + max(1, ttl_seconds),
        }
    )


def _boundary() -> dict[str, Any]:
    return {
        "navigation_only_not_fact": True,
        "read_only": True,
        "source_reopen_required_for_strong_claims": True,
        "clean_source_is_authority": True,
        "handles_are_short_lived": True,
        "no_raw_prompt_text": True,
        "no_raw_private_paths": True,
    }


def _domain_routes(
    *,
    intent: str,
    clean_source_dir: Path,
    snapshot_path: Path | None,
    snapshot: dict[str, Any] | None,
    registry_dir: Path | None,
    max_routes: int,
) -> list[dict[str, Any]]:
    pointers = match_continuity_domain_pointers(
        intent,
        snapshot,
        limit=max_routes,
        clean_source_dir=clean_source_dir,
        snapshot_path=snapshot_path,
    )
    routes: list[dict[str, Any]] = []
    for pointer in pointers:
        domain_id = str(pointer.get("domain_id") or "")
        source_refs = [ref for ref in pointer.get("source_refs") or [] if isinstance(ref, dict)]
        route_id = stable_text_id("route", "continuity_domain", domain_id, length=18)
        handle = continuity_domain_route_handle(
            source_dir=clean_source_dir,
            snapshot_path=snapshot_path,
            domain_id=domain_id,
            source_refs=source_refs,
            registry_dir=registry_dir,
        )
        routes.append(
            {
                "handle": handle,
                "route_id": route_id,
                "kind": "continuity_domain",
                "title": _safe_text(pointer.get("label") or domain_id, 120),
                "summary": _safe_text(pointer.get("why_it_may_matter_now"), 180),
                "evidence_level": "needs_domain_deepen",
                "support_level": "navigation",
                "action_grammar": pointer.get("action_grammar") or "reopenable_route",
                "source_refs": source_refs,
                "scope_labels": [],
                "reopenable": True,
                "why_this_may_matter": _safe_text(pointer.get("why_it_may_matter_now"), 220),
                "suggested_next": {
                    "tool": "recall_deepen",
                    "arguments": {"handle": handle},
                },
                "source_boundary": pointer.get("source_boundary") or _boundary(),
            }
        )
    return routes


def _pathlet_routes(
    *,
    intent: str,
    clean_source_dir: Path,
    snapshot: dict[str, Any] | None,
    max_routes: int,
) -> list[dict[str, Any]]:
    pointers = match_continuity_pathlet_pointers(intent, snapshot, limit=max_routes)
    routes: list[dict[str, Any]] = []
    for pointer in pointers:
        pathlet_id = str(pointer.get("pathlet_id") or "")
        source_refs = [
            _clean_ref(ref)
            for ref in pointer.get("ordered_source_refs") or pointer.get("source_refs") or []
            if isinstance(ref, dict)
        ]
        source_refs = [ref for ref in source_refs if ref]
        if not source_refs:
            continue
        route_id = stable_text_id("route", "pathlet", pathlet_id, source_refs, length=18)
        handle = _source_ref_handle(
            source_dir=clean_source_dir,
            route_id=route_id,
            source_refs=source_refs,
        )
        routes.append(
            {
                "handle": handle,
                "route_id": route_id,
                "kind": "pathlet",
                "pathlet_id": pathlet_id,
                "title": _safe_text(pointer.get("label") or pathlet_id, 120),
                "summary": _safe_text(pointer.get("why_it_may_matter_now"), 180),
                "evidence_level": "needs_reopen",
                "support_level": "navigation",
                "action_grammar": pointer.get("action_grammar") or "reopenable_route",
                "source_refs": source_refs,
                "scope_labels": [
                    str(label) for label in pointer.get("scope_labels") or [] if isinstance(label, str)
                ][:8],
                "reopenable": True,
                "why_this_may_matter": _safe_text(pointer.get("why_it_may_matter_now"), 220),
                "suggested_next": {
                    "tool": "recall_deepen",
                    "arguments": {"handle": handle},
                },
                "source_boundary": {
                    **_boundary(),
                    "pathlet_is_navigation_only": True,
                    "source_reopen_required_before_claim": True,
                },
            }
        )
    return routes


def _route_status(
    *,
    snapshot_path: Path | None,
    snapshot: dict[str, Any] | None,
    domain_routes: list[dict[str, Any]],
    pathlet_routes: list[dict[str, Any]],
) -> dict[str, Any]:
    if isinstance(snapshot, dict):
        raw_metrics = snapshot.get("metrics")
        metrics: dict[str, Any] = raw_metrics if isinstance(raw_metrics, dict) else {}
        snapshot_status = "loaded"
        missing_artifacts: list[str] = []
        snapshot_has_domains = bool(metrics.get("domain_count"))
        snapshot_has_pathlets = bool(metrics.get("pathlet_count"))
    else:
        snapshot_status = "missing" if snapshot_path is None or not snapshot_path.exists() else "unreadable"
        missing_artifacts = ["continuity_domains_snapshot"]
        snapshot_has_domains = False
        snapshot_has_pathlets = False
    return {
        "snapshot_status": snapshot_status,
        "missing_artifacts": missing_artifacts,
        "snapshot_has_domains": snapshot_has_domains,
        "snapshot_has_pathlets": snapshot_has_pathlets,
        "domain_route_count": len(domain_routes),
        "pathlet_route_count": len(pathlet_routes),
    }


def continuity_routes_for_context(
    *,
    intent: str,
    clean_source_dir: Path,
    snapshot_path: Path | None,
    registry_dir: Path | None,
    max_routes: int,
) -> dict[str, Any]:
    snapshot = load_continuity_domains_snapshot(snapshot_path)
    domain_routes = _domain_routes(
        intent=intent,
        clean_source_dir=clean_source_dir,
        snapshot_path=snapshot_path,
        snapshot=snapshot,
        registry_dir=registry_dir,
        max_routes=max_routes,
    )
    pathlet_routes = _pathlet_routes(
        intent=intent,
        clean_source_dir=clean_source_dir,
        snapshot=snapshot,
        max_routes=max_routes,
    )
    return {
        "domain_routes": domain_routes,
        "pathlet_routes": pathlet_routes,
        "continuity_route_status": _route_status(
            snapshot_path=snapshot_path,
            snapshot=snapshot,
            domain_routes=domain_routes,
            pathlet_routes=pathlet_routes,
        ),
    }
