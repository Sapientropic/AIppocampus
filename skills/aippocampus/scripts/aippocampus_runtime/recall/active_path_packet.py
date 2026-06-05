#!/usr/bin/env python3
"""Active Path Packet projection for source-backed task-start orientation.

The packet is a tiny foreground navigation surface. It does not search, write
cache, call a model, or prove memory facts; it only selects a few already-built
routes that an agent may ignore, treat as scent, reopen, or use as bounded
evidence. Clean source remains the authority for specific claims.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping
from typing import Any

from aippocampus_runtime.core import compact_text, sanitize_external_model_text
from aippocampus_runtime.ops.route_readiness import safe_source_refs
from aippocampus_runtime.question.source_refs import source_ref_key

PACKET_KIND = "aippocampus_active_path_packet"
PACKET_SCHEMA_VERSION = 1
DEFAULT_MAX_PATHS = 7
MIN_MAX_PATHS = 3

ROUTES = {"ignore", "scent", "reopen", "evidence"}
CURRENTNESS = {"current", "possibly_stale", "stale", "superseded", "unknown"}
CONFIDENCE_BUCKETS = {"low", "medium", "high"}

STALE_CURRENTNESS = {"stale", "superseded"}
STALE_MARKERS = {
    "expired",
    "possibly_stale",
    "stale",
    "superseded",
    "unknown_stale",
}
IGNORE_STATUSES = {"blocked", "expired", "failed", "suppressed"}


def _stable_id(*parts: Any) -> str:
    raw = "\n".join(str(part or "") for part in parts)
    return "app_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:18]


def _safe_text(value: Any, chars: int = 160) -> str:
    sanitized, _ = sanitize_external_model_text(str(value or ""))
    return compact_text(sanitized, chars)


def _bucket(value: Any, allowed: set[str], default: str) -> str:
    text = str(value or "").strip().casefold()
    return text if text in allowed else default


def _dedupe_refs(refs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[tuple[tuple[str, str], ...]] = set()
    for ref in refs:
        marker = tuple(sorted((str(key), str(value)) for key, value in ref.items()))
        if marker in seen:
            continue
        seen.add(marker)
        out.append(ref)
    return out


def _refs(value: Any) -> list[dict[str, Any]]:
    return _dedupe_refs(safe_source_refs(value))[:3]


def _is_reopenable_ref(ref: Mapping[str, Any]) -> bool:
    thread_key, message_id, turn_anchor, line = source_ref_key(ref)
    return bool(thread_key and (message_id or turn_anchor or line))


def _reopenable_ref_count(refs: list[dict[str, Any]]) -> int:
    return sum(1 for ref in refs if _is_reopenable_ref(ref))


def _next_reopen_action(refs: list[dict[str, Any]], recommended_tool: Any = None) -> str:
    tool = str(recommended_tool or "").strip()
    if tool == "get_turn_context":
        return "get_turn_context"
    if tool in {"source_ref_reopen", "recall_deepen"}:
        return "source_reopen"
    if any(any(key in ref for key in ("message_id", "turn_id", "turn_index")) for ref in refs):
        return "get_turn_context"
    return "source_reopen"


def _confidence(*values: Any) -> str:
    for value in values:
        bucket = _bucket(value, CONFIDENCE_BUCKETS, "")
        if bucket:
            return bucket
    return "medium"


def _currentness(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip().casefold()
        if text in {"fresh", "ready", "ok"}:
            return "current"
        if text in {"possibly_stale", "maybe_stale"}:
            return "possibly_stale"
        if text in CURRENTNESS:
            return text
        if text in STALE_MARKERS:
            return "stale"
    return "unknown"


def _privacy_boundary(*, visibility: str = "foreground") -> dict[str, Any]:
    return {
        "visibility": visibility,
        "local_first": True,
        "raw_source_text_serialized": False,
        "local_paths_serialized": False,
        "secret_values_serialized": False,
        "cloud_calls": False,
    }


def _source_boundary(
    *,
    route: str,
    currentness: str,
    source_reopen_required: bool,
) -> dict[str, Any]:
    unsafe_current = route == "ignore" or currentness in STALE_CURRENTNESS
    return {
        "navigation_not_truth": True,
        "candidate_refs_are_ids_only": True,
        "source_reopen_required": source_reopen_required,
        "source_reopen_required_before_claim": source_reopen_required,
        "unsafe_to_use_as_current_fact": unsafe_current,
        "bounded_evidence_only": route == "evidence",
    }


def _path(
    *,
    title: Any,
    why_lit: Any,
    route: str,
    currentness: str,
    source_refs: list[dict[str, Any]],
    confidence: Any,
    next_action: str,
    reason_codes: list[str],
    source_reopen_required: bool,
    origin: str,
    visibility: str = "foreground",
) -> dict[str, Any]:
    clean_route = _bucket(route, ROUTES, "scent")
    clean_currentness = _currentness(currentness)
    clean_title = _safe_text(title, 120) or "Active path"
    return {
        "path_id": _stable_id(origin, clean_route, clean_title, source_refs),
        "title": clean_title,
        "why_lit": _safe_text(why_lit, 220)
        or "A prior navigation surface may be relevant; reopen source before making claims.",
        "route": clean_route,
        "currentness": clean_currentness,
        "source_refs": source_refs,
        "confidence": _confidence(confidence),
        "privacy_boundary": _privacy_boundary(visibility=visibility),
        "next_action": next_action,
        "source_boundary": _source_boundary(
            route=clean_route,
            currentness=clean_currentness,
            source_reopen_required=source_reopen_required,
        ),
        "reason_codes": list(dict.fromkeys(reason_codes)),
        "origin": origin,
    }


def _ambient_paths(ambient_recall: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(ambient_recall, Mapping):
        return []
    paths: list[dict[str, Any]] = []
    for card in ambient_recall.get("cards") or []:
        if not isinstance(card, Mapping):
            continue
        refs = _refs(card.get("source_refs"))
        support = str(card.get("support_level") or "").casefold()
        reopen_required = bool(card.get("source_reopen_required", support != "evidence"))
        if support == "evidence":
            route = "evidence"
            next_action = "use_bounded_evidence"
            reason_codes = ["ambient_card", "bounded_evidence_ready"]
            reopen_required = False
        elif refs:
            route = "reopen"
            next_action = _next_reopen_action(refs)
            reason_codes = ["ambient_card", "candidate_source_ref_reopenable"]
        else:
            route = "scent"
            next_action = "use_as_scent"
            reason_codes = ["ambient_card", "source_refs_missing"]
        paths.append(
            _path(
                title=card.get("theme") or card.get("title") or "Ambient recall card",
                why_lit=card.get("suggested_use") or card.get("expand_if"),
                route=route,
                currentness=card.get("currentness") or card.get("freshness") or "unknown",
                source_refs=refs,
                confidence=card.get("confidence") or ambient_recall.get("confidence"),
                next_action=next_action,
                reason_codes=reason_codes,
                source_reopen_required=reopen_required,
                origin="ambient_card",
            )
        )
    packet = ambient_recall.get("fresh_thread_packet")
    if isinstance(packet, Mapping):
        paths.extend(_fresh_thread_paths(packet))
    return paths


def _fresh_thread_paths(packet: Mapping[str, Any]) -> list[dict[str, Any]]:
    support = str(packet.get("support_level") or "").casefold()
    refs = _refs(packet.get("candidate_refs"))
    currentness = _currentness(packet.get("currentness"), packet.get("freshness"))
    if support == "suppressed":
        return [
            _path(
                title="Suppressed fresh-thread route",
                why_lit="Fresh-thread signal is suppressed by privacy or staleness policy.",
                route="ignore",
                currentness=currentness,
                source_refs=[],
                confidence=packet.get("confidence"),
                next_action="ignore",
                reason_codes=["fresh_thread_packet", "suppressed"],
                source_reopen_required=False,
                origin="fresh_thread_packet",
                visibility="blocked",
            )
        ]
    if support == "source_required":
        raw_reopen_plan = packet.get("reopen_plan")
        reopen_plan: Mapping[str, Any] = (
            raw_reopen_plan if isinstance(raw_reopen_plan, Mapping) else {}
        )
        return [
            _path(
                title="Fresh-thread source route",
                why_lit=packet.get("route_reason")
                or "A fresh-thread packet found candidate refs that must reopen clean source before use.",
                route="reopen" if refs else "scent",
                currentness=currentness,
                source_refs=refs,
                confidence=packet.get("confidence"),
                next_action=_next_reopen_action(refs, reopen_plan.get("recommended_tool")),
                reason_codes=["fresh_thread_packet", "source_required"],
                source_reopen_required=True,
                origin="fresh_thread_packet",
            )
        ]
    if support in {"soft_hypothesis", "silent_scent"}:
        return [
            _path(
                title="Fresh-thread scent",
                why_lit=packet.get("route_reason") or "Fresh-thread signal is only a scent.",
                route="scent",
                currentness=currentness,
                source_refs=refs,
                confidence=packet.get("confidence"),
                next_action=str(packet.get("advisory_action") or "use_as_scent"),
                reason_codes=["fresh_thread_packet", support],
                source_reopen_required=bool(refs),
                origin="fresh_thread_packet",
            )
        ]
    return []


def _recall_context_paths(recall_context: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(recall_context, Mapping):
        return []
    paths: list[dict[str, Any]] = []
    for route_row in recall_context.get("routes") or []:
        if not isinstance(route_row, Mapping):
            continue
        refs = _refs(route_row.get("source_refs"))
        evidence_level = str(route_row.get("evidence_level") or "").casefold()
        route = "evidence" if evidence_level == "source_backed" else ("reopen" if refs else "scent")
        source_reopen_required = route != "evidence"
        paths.append(
            _path(
                title=route_row.get("title") or route_row.get("kind") or "Recall route",
                why_lit=route_row.get("why_this_may_matter")
                or "Recall navigation route may matter; reopen clean source before using exact claims.",
                route=route,
                currentness=route_row.get("currentness") or "unknown",
                source_refs=refs,
                confidence=route_row.get("confidence") or recall_context.get("confidence"),
                next_action=(
                    "use_bounded_evidence" if route == "evidence" else _next_reopen_action(refs, "recall_deepen")
                ),
                reason_codes=["recall_context", str(route_row.get("kind") or "route")],
                source_reopen_required=source_reopen_required,
                origin="recall_context",
            )
        )
    return paths


def _active_lock_title(lock: Mapping[str, Any]) -> str:
    aliases = [str(value) for value in lock.get("query_aliases") or [] if str(value or "").strip()]
    if aliases:
        return "Active recall lock: " + _safe_text(", ".join(aliases[:2]), 90)
    return "Active recall lock"


def _active_lock_paths(active_locks: Iterable[Mapping[str, Any]] | None) -> list[dict[str, Any]]:
    paths: list[dict[str, Any]] = []
    for lock in active_locks or []:
        if not isinstance(lock, Mapping):
            continue
        state = str(lock.get("state") or "pending").casefold()
        refs = _refs(lock.get("candidate_refs"))
        route = "reopen" if state == "ready" and refs else ("ignore" if state in IGNORE_STATUSES else "scent")
        next_action = _next_reopen_action(refs) if route == "reopen" else ("ignore" if route == "ignore" else "use_as_scent")
        freshness_vector = lock.get("freshness_vector") if isinstance(lock.get("freshness_vector"), Mapping) else {}
        paths.append(
            _path(
                title=_active_lock_title(lock),
                why_lit="; ".join(_safe_text(reason, 120) for reason in lock.get("route_reasons") or [])
                or "Active recall lock can guide source reopen when ready.",
                route=route,
                currentness=_currentness(state, *(freshness_vector.values() if freshness_vector else [])),
                source_refs=refs,
                confidence=lock.get("confidence") or ("high" if route == "reopen" else "medium"),
                next_action=next_action,
                reason_codes=["active_recall_lock", state],
                source_reopen_required=route == "reopen",
                origin="active_recall_lock",
            )
        )
    return paths


def _route_readiness_rows(route_readiness: Any) -> list[Mapping[str, Any]]:
    if isinstance(route_readiness, Mapping):
        rows = route_readiness.get("rows") or []
    else:
        rows = route_readiness or []
    return [row for row in rows if isinstance(row, Mapping)]


def _route_readiness_paths(route_readiness: Any) -> list[dict[str, Any]]:
    paths: list[dict[str, Any]] = []
    for row in _route_readiness_rows(route_readiness):
        refs = _refs(row.get("source_refs"))
        status = str(row.get("status") or row.get("route_status") or "").casefold()
        currentness = _currentness(
            row.get("currentness"),
            row.get("freshness"),
            row.get("freshness_state"),
            status,
        )
        suppressed = status in IGNORE_STATUSES or currentness in STALE_CURRENTNESS
        route = "ignore" if suppressed else ("reopen" if refs else "scent")
        reason_values = [
            *(row.get("reason_codes") or []),
            *(row.get("suppression_reasons") or []),
        ]
        reason_codes = ["route_readiness", *(str(value) for value in reason_values if value)]
        next_action = "ignore" if route == "ignore" else _next_reopen_action(refs)
        paths.append(
            _path(
                title=row.get("title") or row.get("surface_kind") or row.get("route_id") or "Route readiness row",
                why_lit=(
                    "Route readiness row is stale/suppressed; keep it visible only as a boundary."
                    if route == "ignore"
                    else "Route readiness says this handle may be worth reopening, not that it is a fact."
                ),
                route=route,
                currentness=currentness,
                source_refs=refs,
                confidence=row.get("confidence") or ("low" if route == "ignore" else "medium"),
                next_action=next_action,
                reason_codes=reason_codes,
                source_reopen_required=route == "reopen",
                origin="route_readiness",
                visibility="blocked" if route == "ignore" else "foreground",
            )
        )
    return paths


def _priority(path: Mapping[str, Any]) -> tuple[int, int, str]:
    route_rank = {"evidence": 0, "reopen": 1, "scent": 2, "ignore": 3}
    confidence_rank = {"high": 0, "medium": 1, "low": 2}
    reopenable_bonus = 0 if _reopenable_ref_count(list(path.get("source_refs") or [])) else 1
    return (
        route_rank.get(str(path.get("route")), 4),
        confidence_rank.get(str(path.get("confidence")), 3) + reopenable_bonus,
        str(path.get("path_id") or ""),
    )


def _dedupe_paths(paths: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for path in sorted(paths, key=_priority):
        refs = path.get("source_refs") or []
        ref_key = tuple(
            "|".join(source_ref_key(ref)) for ref in refs if isinstance(ref, Mapping)
        )
        marker = (path.get("route"), path.get("title"), ref_key or path.get("path_id"))
        if marker in seen:
            continue
        seen.add(marker)
        out.append(path)
    return out


def _trim_paths(paths: list[dict[str, Any]], max_paths: int) -> list[dict[str, Any]]:
    limit = max(1, min(DEFAULT_MAX_PATHS, int(max_paths or DEFAULT_MAX_PATHS)))
    ordered = _dedupe_paths(paths)
    if len(ordered) <= limit:
        return ordered
    kept = ordered[:limit]
    # Stale/suppressed paths are easy to drop during ranking, but issue #769
    # needs them preserved as visible "do not claim current fact" boundaries.
    if not any(path.get("route") == "ignore" for path in kept):
        ignored = next((path for path in ordered if path.get("route") == "ignore"), None)
        if ignored:
            kept[-1] = ignored
    return kept


def _metrics(paths: list[dict[str, Any]], candidate_count: int) -> dict[str, Any]:
    route_counts = {route: 0 for route in sorted(ROUTES)}
    for path in paths:
        route_counts[str(path.get("route") or "scent")] = route_counts.get(str(path.get("route")), 0) + 1
    return {
        "candidate_count": candidate_count,
        "selected_count": len(paths),
        "route_counts": route_counts,
        "reopenable_path_count": sum(
            1 for path in paths if _reopenable_ref_count(list(path.get("source_refs") or [])) > 0
        ),
        "stale_or_superseded_path_count": sum(
            1
            for path in paths
            if path.get("currentness") in STALE_CURRENTNESS
            or path.get("source_boundary", {}).get("unsafe_to_use_as_current_fact")
        ),
        "scent_path_count": route_counts.get("scent", 0),
        "evidence_path_count": route_counts.get("evidence", 0),
        "privacy_blocked_count": sum(
            1
            for path in paths
            if path.get("privacy_boundary", {}).get("visibility") == "blocked"
        ),
        "manual_query_invention_expected": False,
        "external_model_calls": 0,
        "writes_performed": 0,
    }


def build_active_path_packet(
    *,
    ambient_recall: Mapping[str, Any] | None = None,
    recall_context: Mapping[str, Any] | None = None,
    active_locks: Iterable[Mapping[str, Any]] | None = None,
    route_readiness: Any = None,
    max_paths: int = DEFAULT_MAX_PATHS,
) -> dict[str, Any]:
    """Select a few existing source-backed navigation paths for the foreground.

    This function is intentionally pure and no-write. Callers pass already
    computed recall surfaces; the selector only projects, orders, and marks the
    source boundary so a host can decide whether to ignore, reopen, or use a
    bounded evidence card.
    """

    candidates = [
        *_ambient_paths(ambient_recall),
        *_recall_context_paths(recall_context),
        *_active_lock_paths(active_locks),
        *_route_readiness_paths(route_readiness),
    ]
    selected = _trim_paths(candidates, max(max_paths, MIN_MAX_PATHS))
    return {
        "kind": PACKET_KIND,
        "schema_version": PACKET_SCHEMA_VERSION,
        "purpose": "pre_action_orientation",
        "paths": selected,
        "path_count": len(selected),
        "privacy": {
            "local_first": True,
            "raw_source_text_serialized": False,
            "local_paths_serialized": False,
            "secret_values_serialized": False,
            "cloud_calls": False,
            "external_model_calls": False,
        },
        "source_boundary": {
            "navigation_not_truth": True,
            "clean_source_is_authority": True,
            "source_reopen_required_before_claim": True,
            "scent_is_not_evidence": True,
            "stale_or_suppressed_paths_are_boundaries": True,
        },
        "cannot_claim": [
            "active_path_packet_proves_memory_fact",
            "source_reopen_required_before_claim",
            "scent_path_is_evidence",
            "stale_path_is_current_fact",
            "desktop_bootstrap_consumes_packet",
        ],
        "metrics": _metrics(selected, len(candidates)),
        "no_write": True,
    }
