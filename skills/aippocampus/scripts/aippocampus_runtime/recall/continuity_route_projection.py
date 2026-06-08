"""Foreground continuity route projection for agent-initiated recall."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from aippocampus_runtime.core import compact_text, sanitize_external_model_text
from aippocampus_runtime.recall.continuity_domains import match_continuity_domain_pointers
from aippocampus_runtime.recall.continuity_pathlets import match_continuity_pathlet_pointers
from aippocampus_runtime.recall.narrative_packet import compile_narrative_packet

INACTIVE_ROUTE_STATUSES = {"blocked", "stale", "superseded", "retired"}


def _public_text(value: Any, *, chars: int) -> str:
    sanitized, _ = sanitize_external_model_text(str(value or ""))
    return compact_text(sanitized or "<redacted:sensitive-text>", chars)


def _safe_route_ref(ref: dict[str, Any]) -> dict[str, Any]:
    allowed = (
        "thread_key",
        "source_id",
        "message_id",
        "turn_id",
        "turn_index",
        "line",
        "phase",
        "title",
    )
    route: dict[str, Any] = {}
    for key in allowed:
        value = ref.get(key)
        if value in (None, "", []):
            continue
        route[key] = _public_text(value, chars=180) if isinstance(value, str) else value
    return route


def _inactive_pointer(pointer: dict[str, Any]) -> bool:
    status = str(pointer.get("status") or "active")
    action = str(pointer.get("action_grammar") or "")
    return status in INACTIVE_ROUTE_STATUSES or action == "ignore_or_blocked"


def _snapshot_status(snapshot_path: Path, snapshot: dict[str, Any] | None) -> dict[str, Any]:
    if isinstance(snapshot, dict):
        metrics = snapshot.get("metrics") if isinstance(snapshot.get("metrics"), dict) else {}
        return {
            "snapshot_status": "loaded",
            "missing_artifacts": [],
            "snapshot_has_domains": bool(metrics.get("domain_count")),
            "snapshot_has_pathlets": bool(metrics.get("pathlet_count")),
        }
    status = "missing" if not snapshot_path.exists() else "unreadable"
    return {
        "snapshot_status": status,
        "missing_artifacts": ["continuity_domains_snapshot"],
        "snapshot_has_domains": False,
        "snapshot_has_pathlets": False,
    }


def _brief(pointer: dict[str, Any], *, surface: str) -> dict[str, Any]:
    return {
        **pointer,
        "active_recall_surface": surface,
        "retrieval_role": "working_continuity_brief",
    }


def _pathlet_route_from_pointer(pointer: dict[str, Any]) -> dict[str, Any]:
    refs = [
        route
        for ref in pointer.get("ordered_source_refs") or pointer.get("source_refs") or []
        if isinstance(ref, dict) and (route := _safe_route_ref(ref))
    ]
    return {
        "kind": "pathlet",
        "pathlet_id": pointer.get("pathlet_id"),
        "title": pointer.get("label") or pointer.get("theme") or pointer.get("pathlet_id"),
        "action_grammar": pointer.get("action_grammar") or "reopenable_route",
        "source_refs": refs[:6],
        "source_reopen_required_before_claim": True,
        "recommended_tool": "get_turn_context",
        "why_this_may_matter": pointer.get("why_it_may_matter_now"),
        "source_boundary": pointer.get("source_boundary") or {},
    }


def active_continuity_route_projection(
    *,
    prompt: str,
    snapshot_path: Path,
    snapshot: dict[str, Any] | None,
    clean_source_dir: Path | None,
    max_matches: int,
) -> dict[str, Any]:
    domain_pointers = match_continuity_domain_pointers(
        prompt,
        snapshot,
        limit=max_matches,
        clean_source_dir=clean_source_dir,
        snapshot_path=snapshot_path,
    )
    blocked_domain_pointers = [
        pointer
        for pointer in match_continuity_domain_pointers(
            prompt,
            snapshot,
            limit=max_matches,
            clean_source_dir=clean_source_dir,
            snapshot_path=snapshot_path,
            include_blocked=True,
        )
        if _inactive_pointer(pointer)
    ]
    pathlet_pointers = match_continuity_pathlet_pointers(
        prompt,
        snapshot,
        limit=max_matches,
    )
    blocked_pathlet_pointers = [
        pointer
        for pointer in match_continuity_pathlet_pointers(
            prompt,
            snapshot,
            limit=max_matches,
            include_blocked=True,
        )
        if _inactive_pointer(pointer)
    ]
    narrative_inputs = [
        *domain_pointers,
        *blocked_domain_pointers,
        *pathlet_pointers,
        *blocked_pathlet_pointers,
    ]
    fresh_thread_route_packet = (
        compile_narrative_packet(
            trigger="active_recall_context",
            pathlets=[*pathlet_pointers, *blocked_pathlet_pointers],
            continuity_domain_pointers=[*domain_pointers, *blocked_domain_pointers],
            max_items=max_matches,
        )
        if narrative_inputs
        else None
    )
    route_status = {
        **_snapshot_status(snapshot_path, snapshot),
        "domain_route_count": len(domain_pointers),
        "pathlet_route_count": len(pathlet_pointers),
        "blocked_route_count": len(blocked_domain_pointers) + len(blocked_pathlet_pointers),
        "fresh_thread_route_packet": bool(fresh_thread_route_packet),
        "route_packet_action_grammar": (
            (fresh_thread_route_packet.get("use_boundary") or {}).get("action_grammar")
            if isinstance(fresh_thread_route_packet, dict)
            else None
        ),
    }
    return {
        "domain_pointers": domain_pointers,
        "pathlet_pointers": pathlet_pointers,
        "domain_brief": [_brief(pointer, surface="continuity_domain") for pointer in domain_pointers],
        "pathlet_brief": [_brief(pointer, surface="continuity_pathlet") for pointer in pathlet_pointers],
        "pathlet_source_reopen_routes": [
            route
            for pointer in pathlet_pointers
            if (route := _pathlet_route_from_pointer(pointer)).get("source_refs")
        ],
        "fresh_thread_route_packet": fresh_thread_route_packet,
        "continuity_route_status": route_status,
    }
