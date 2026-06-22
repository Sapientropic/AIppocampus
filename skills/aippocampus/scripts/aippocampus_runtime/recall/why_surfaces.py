#!/usr/bin/env python3
"""Surface-to-reason-code projections for recall diagnostics."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from aippocampus_runtime.mcp.recall_navigation import (
    RecallNavigationError,
    clean_source_fingerprint,
    normalize_handle,
)
from aippocampus_runtime.recall.semantic_gate_response import public_semantic_gate_payload
from aippocampus_runtime.recall.why_reason_codes import safe_int, surface_report
from aippocampus_runtime.source.clean_source_resolver import resolve_clean_source_dir


def clean_source_dir_for(cwd: Path, clean_source_dir: str | Path | None = None) -> Path:
    return resolve_clean_source_dir(cwd, clean_source_dir)


def _source_ref_count_from_routes(routes: list[Any]) -> int:
    count = 0
    for route in routes:
        refs = route.get("source_refs") if isinstance(route, Mapping) else None
        if isinstance(refs, list):
            count += sum(1 for ref in refs if isinstance(ref, Mapping))
    return count


def recall_context_surface_report(payload: Mapping[str, Any]) -> dict[str, Any]:
    raw_routes = payload.get("routes")
    routes: list[Any] = raw_routes if isinstance(raw_routes, list) else []
    route_ids = [
        str(route.get("route_id") or "")
        for route in routes
        if isinstance(route, Mapping) and route.get("route_id")
    ]
    reason_codes: list[str] = []
    if routes:
        reason_codes.append("route_returned")
    if any(
        isinstance(route, Mapping)
        and (
            route.get("evidence_level") == "needs_reopen"
            or route.get("source_reopen_required")
            or (route.get("suggested_next") or {}).get("tool") == "recall_deepen"
        )
        for route in routes
    ):
        reason_codes.append("source_reopen_required")
    source_ref_count = _source_ref_count_from_routes(routes)
    if not routes or source_ref_count == 0:
        reason_codes.append("no_source_refs")
    if any(isinstance(route, Mapping) and route.get("source_thickness") == "thin" for route in routes):
        reason_codes.append("source_thickness_thin")
    return surface_report(
        "recall_context",
        status="returned" if routes else "no_routes",
        reason_codes=reason_codes,
        route_ids=route_ids,
        counts={
            "route_count": len(routes),
            "source_ref_count": source_ref_count,
            "query_term_count": len(payload.get("query_terms") or []),
        },
    )


def missing_clean_source_report() -> dict[str, Any]:
    return surface_report(
        "recall_context",
        status="missing_clean_source",
        reason_codes=["missing_clean_source"],
        counts={"route_count": 0, "source_ref_count": 0},
    )


def handle_surface_report(handle: Any, *, clean_source_dir: Path) -> dict[str, Any]:
    try:
        payload = normalize_handle(handle)
    except RecallNavigationError:
        return surface_report(
            "recall_context",
            status="malformed_handle",
            reason_codes=["no_source_refs"],
            counts={"source_ref_count": 0},
        )
    refs = [ref for ref in payload.get("source_refs") or [] if isinstance(ref, Mapping)]
    reason_codes: list[str] = []
    expected_fingerprint = payload.get("source_fingerprint")
    if expected_fingerprint:
        try:
            current_fingerprint = clean_source_fingerprint(clean_source_dir)
        except Exception:
            current_fingerprint = "source_unavailable"
        if expected_fingerprint != current_fingerprint:
            reason_codes.append("stale_handle")
    reason_codes.append("source_reopen_required" if refs else "no_source_refs")
    return surface_report(
        "recall_context",
        status="handle_diagnostic",
        reason_codes=reason_codes,
        route_ids=[str(payload.get("route_id") or "")],
        counts={"source_ref_count": len(refs)},
        details={"handle_kind": str(payload.get("kind") or "unknown")},
    )


def active_lock_surface_report(lock: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(lock, Mapping):
        return surface_report("active_lock", status="not_requested", counts={"lock_count": 0})
    state = str(lock.get("state") or "missing")
    invalidated = (lock.get("diagnostics") or {}).get("invalidated_by")
    invalidated_list = invalidated if isinstance(invalidated, list) else []
    ref_count = safe_int(lock.get("reopenable_ref_count"))
    reason_codes: list[str] = []
    if state == "missing":
        reason_codes.append("active_lock_missing")
    if state in {"expired", "superseded"} or invalidated_list:
        reason_codes.append("stale_handle")
    if state == "ready" and ref_count > 0:
        reason_codes.extend(["active_lock_ready", "source_reopen_required"])
    if state in {"ready", "pending"} and ref_count == 0:
        reason_codes.append("no_source_refs")
    conflict_flags = [str(item) for item in lock.get("conflict_flags") or []]
    if any("authority" in flag.casefold() or "privacy" in flag.casefold() for flag in conflict_flags):
        reason_codes.append("authority_level_block")
    return surface_report(
        "active_lock",
        status=state,
        reason_codes=reason_codes,
        route_ids=[str(lock.get("lock_id") or "")],
        counts={
            "lock_count": 0 if state == "missing" else 1,
            "candidate_ref_count": safe_int(lock.get("candidate_ref_count")),
            "reopenable_ref_count": ref_count,
        },
        details={
            "source_reopen_required": bool(lock.get("source_reopen_required", True)),
            "invalidated": bool(invalidated_list),
        },
    )


def ambient_cache_surface_report(cache: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(cache, Mapping):
        return surface_report("ambient_cache", status="not_requested", counts={"card_count": 0})
    status = str(cache.get("status") or "miss")
    cards = [card for card in cache.get("cards") or [] if isinstance(card, Mapping)]
    reason_codes: list[str] = []
    if status in {"hit", "related_hit"} or cards:
        reason_codes.append("ambient_cache_hit")
    elif status in {"miss", "expired"}:
        reason_codes.extend(["ambient_cache_miss", "prewarm_miss"] if status == "miss" else ["ambient_cache_miss"])
    for card in cards:
        refs = card.get("source_refs")
        ref_count = len(refs) if isinstance(refs, list) else 0
        if card.get("source_reopen_required"):
            reason_codes.append("source_reopen_required")
        if card.get("reopen_required_before_claim"):
            reason_codes.append("reopen_required_before_claim")
        if card.get("authority_state") == "bounded_evidence_ready":
            reason_codes.append("bounded_evidence_ready")
        if card.get("reopen_recommended_for_exact_quote"):
            reason_codes.append("reopen_recommended_for_exact_quote")
        if ref_count == 0:
            reason_codes.append("no_source_refs")
        if card.get("source_thickness") == "thin" or safe_int(card.get("reopenable_ref_count")) == 1 or card.get("support_level") in {"candidate", "review_required"}:
            reason_codes.append("source_thickness_thin")
        if card.get("provenance_class") in {"dream_candidate", "working_memory_candidate"}:
            reason_codes.append("dream_candidate_not_adjudicated")
    diagnostics = cache.get("suppression_diagnostics")
    if isinstance(diagnostics, Mapping):
        buckets = [str(item) for item in diagnostics.get("reason_buckets") or []]
        if "privacy_blocked" in buckets:
            reason_codes.append("privacy_partition_block")
        if "secret_or_property_risk_blocked" in buckets:
            reason_codes.append("secret_or_property_risk_blocked")
        if "external_payload_blocked" in buckets:
            reason_codes.append("external_payload_blocked")
        if "local_route_handle_only" in buckets:
            reason_codes.append("local_route_handle_only")
        if "current_thread_echo" in buckets:
            reason_codes.append("anti_nag_source_already_visible")
        if "source_validation_failed" in buckets:
            reason_codes.append("source_ref_not_found")
        if "guard_coverage_incomplete" in buckets:
            reason_codes.append("source_thickness_thin")
    return surface_report(
        "ambient_cache",
        status=status,
        reason_codes=reason_codes,
        counts={
            "card_count": len(cards),
            "source_ref_fingerprint_count": len(cache.get("source_ref_fingerprints") or []),
            "related_fingerprint_count": len(cache.get("related_fingerprints") or []),
        },
        details={
            "topic_epoch_known": bool(cache.get("topic_epoch")),
            "source_reopen_required": any(bool(card.get("source_reopen_required")) for card in cards),
            "bounded_evidence_ready": any(
                card.get("authority_state") == "bounded_evidence_ready" for card in cards
            ),
        },
    )


def semantic_gate_surface_report(
    semantic_gate: Mapping[str, Any] | None,
    *,
    semantic_gate_mode: str = "off",
) -> dict[str, Any]:
    if not isinstance(semantic_gate, Mapping):
        reason = ["semantic_disabled_by_operator"] if semantic_gate_mode == "off" else []
        return surface_report("semantic_gate", status="disabled" if reason else "not_requested", reason_codes=reason, counts={"worker_count": 0})
    public = public_semantic_gate_payload(semantic_gate)
    diagnostic = str(public.get("diagnostic") or "").casefold()
    availability = str(public.get("availability_reason") or "").casefold()
    raw_buckets = public.get("error_buckets")
    buckets: dict[Any, Any] = raw_buckets if isinstance(raw_buckets, dict) else {}
    reason_codes: list[str] = []
    if diagnostic in {"semantic_provider_read_timeout", "semantic_overall_deadline_exceeded", "semantic_timed_out_under_foreground_budget"} or availability == "semantic_worker_timeout" or buckets.get("read_timeout") or buckets.get("overall_deadline"):
        reason_codes.append("semantic_provider_timeout")
    elif not public.get("available"):
        if diagnostic == "semantic_disabled_or_auth_unavailable" and buckets.get("auth_error"):
            reason_codes.append("semantic_disabled_by_operator" if semantic_gate_mode == "off" else "semantic_unavailable_missing_auth")
        else:
            reason_codes.append("semantic_degraded")
    if public.get("available") and public.get("decision") in {"scent", "evidence"}:
        reason_codes.append("route_returned")
    if buckets.get("foreground_budget"):
        reason_codes.append("semantic_degraded")
    return surface_report(
        "semantic_gate",
        status="available" if public.get("available") else "degraded",
        reason_codes=reason_codes,
        counts={"worker_count": safe_int(public.get("worker_count")), "error_bucket_count": len(buckets)},
        details={
            "decision": public.get("decision"),
            "cached": bool(public.get("cached")),
            "cache_lookup": (public.get("cache_diagnostics") or {}).get("lookup"),
        },
    )
