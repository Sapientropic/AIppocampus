#!/usr/bin/env python3
"""CLI/MCP aggregation for privacy-safe why/why-not recall diagnostics."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Mapping

from aippocampus_runtime import core
from aippocampus_runtime.mcp.recall_navigation import RecallNavigationError, recall_context_packet
from aippocampus_runtime.privacy import redact_private_paths
from aippocampus_runtime.recall import active_recall_lock, ambient_cache
from aippocampus_runtime.recall.associative_path_inputs import build_associative_path_diagnostic
from aippocampus_runtime.recall.semantic_recall_gate import run_semantic_gate
from aippocampus_runtime.recall.why_reason_codes import (
    CANNOT_CLAIM,
    DEFAULT_MAX_ROUTES,
    DIAGNOSTIC_KIND,
    REASON_CODE_CATALOG,
    REASON_CODE_CATALOG_VERSION,
    SCHEMA_VERSION,
    cue_hash,
    next_safe_action,
    overall_decision,
    safe_int,
    unique,
)
from aippocampus_runtime.recall.why_surfaces import (
    active_lock_surface_report,
    ambient_cache_surface_report,
    clean_source_dir_for,
    handle_surface_report,
    missing_clean_source_report,
    recall_context_surface_report,
    semantic_gate_surface_report,
)
from aippocampus_runtime.registry import api as registry_api


def _load_json_argument(value: str | None) -> dict[str, Any] | None:
    if not value:
        return None
    text = str(value)
    path = Path(text)
    if path.exists():
        text = path.read_text(encoding="utf-8")
    payload = json.loads(text)
    return payload if isinstance(payload, dict) else None


def _registry_path(registry_dir: Path | None, registry_path: str | Path | None) -> Path:
    return Path(registry_path).resolve() if registry_path else registry_api.registry_paths(registry_dir)[0]


def _active_lock_payload(
    *,
    cue: str,
    cwd: Path,
    registry_path: Path | None,
    registry_dir: Path | None,
    lock_id: str | None,
    lock_path: str | Path | None,
    thread_id: str | None,
    topic_epoch: str | None,
) -> dict[str, Any] | None:
    path = (
        Path(lock_path).resolve()
        if lock_path
        else active_recall_lock.default_active_recall_lock_path(
            registry_path=registry_path,
            registry_dir=registry_dir,
        )
    )
    registry_fp = (
        active_recall_lock.registry_freshness_fingerprint(registry_path)
        if registry_path
        else None
    )
    if lock_id:
        return active_recall_lock.read_recall_lock(
            path,
            lock_id,
            topic_epoch=topic_epoch,
            registry_freshness_fingerprint=registry_fp,
            record_consumer_read=False,
        )
    if not thread_id or not topic_epoch:
        return None
    return active_recall_lock.find_recall_lock(
        path,
        prompt=cue,
        thread_id=thread_id,
        workspace=cwd,
        topic_epoch=topic_epoch,
        registry_path=registry_path,
    )


def _ambient_cache_payload(
    *,
    cwd: Path,
    registry_path: Path | None,
    registry_dir: Path | None,
    cache_path: str | Path | None,
    thread_id: str | None,
    topic_epoch: str | None,
) -> dict[str, Any] | None:
    path = (
        Path(cache_path).resolve()
        if cache_path
        else ambient_cache.default_ambient_cache_path(
            registry_path=registry_path,
            registry_dir=registry_dir,
        )
    )
    if not thread_id:
        return None
    if topic_epoch:
        return ambient_cache.read_thread_cache(
            path,
            thread_id=thread_id,
            workspace=str(cwd),
            topic_epoch=topic_epoch,
        )
    return ambient_cache.read_latest_thread_cache(path, thread_id=thread_id, workspace=str(cwd))


def _semantic_gate_payload(
    *,
    cue: str,
    cwd: Path,
    registry_path: Path | None,
    semantic_result_json: str | None,
    run_live: bool,
    semantic_gate_mode: str,
    semantic_timeout: int,
) -> dict[str, Any] | None:
    injected = _load_json_argument(semantic_result_json)
    if injected is not None:
        return injected
    if not run_live:
        return None
    return run_semantic_gate(
        cue,
        cwd=cwd,
        registry_path=registry_path,
        mode=semantic_gate_mode,
        timeout=semantic_timeout,
        use_cache=True,
    )


def _recall_context_report(
    *,
    cue: str,
    cwd: Path,
    clean_dir: Path,
    registry_dir: Path | None,
    max_routes: int,
    injected: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if injected is not None:
        return recall_context_surface_report(injected)
    if not (clean_dir / "messages.jsonl").exists():
        return missing_clean_source_report()
    try:
        payload = recall_context_packet(
            intent=cue,
            cwd=cwd,
            clean_source_dir=clean_dir,
            registry_dir=registry_dir,
            max_routes=max_routes,
        )
    except RecallNavigationError:
        return missing_clean_source_report()
    return recall_context_surface_report(payload)


def _recall_context_counts(reports: list[dict[str, Any]]) -> dict[str, int]:
    for report in reports:
        if report.get("surface") == "recall_context":
            counts = report.get("counts")
            return counts if isinstance(counts, dict) else {}
    return {}


def _why_not_projection(
    *,
    mode: str,
    decision: str,
    route_ids: list[str],
    reports: list[dict[str, Any]],
    max_routes: int,
) -> dict[str, Any]:
    if mode != "why-not-recall":
        return {
            "diagnostic_class": "why_recall",
            "why_not_applicable": None,
            "route_specificity": None,
            "suggested_next": "deepen_returned_route_if_continuity_matters"
            if route_ids
            else "continue_normally_or_refine_cue",
        }
    counts = _recall_context_counts(reports)
    route_count = safe_int(counts.get("route_count"))
    source_ref_count = safe_int(counts.get("source_ref_count"))
    query_term_count = safe_int(counts.get("query_term_count"))
    low_specificity = bool(
        route_ids
        and (
            query_term_count <= 2
            or route_count >= max_routes
            or source_ref_count <= max(1, route_count)
        )
    )
    if not route_ids or decision in {"missing", "unknown"}:
        return {
            "diagnostic_class": "actually_silent",
            "why_not_applicable": False,
            "route_specificity": "none",
            "suggested_next": "inspect_reason_codes_or_run_health_if_recall_was_expected",
        }
    if low_specificity:
        return {
            "diagnostic_class": "surfaced_but_low_specificity",
            "why_not_applicable": False,
            "route_specificity": "low",
            "suggested_next": "tighten_cue_or_use_why_recall_deepen_only_if_continuity_matters",
        }
    return {
        "diagnostic_class": "surfaced_so_why_not_is_not_applicable",
        "why_not_applicable": True,
        "route_specificity": "medium",
        "suggested_next": "use_why_recall_or_deepen_the_returned_route",
    }


def _frontstage_action_card(
    *,
    mode: str,
    decision: str,
    projection: Mapping[str, Any],
    route_ids: list[str],
    reasons: list[str],
) -> dict[str, Any]:
    diagnostic = str(projection.get("diagnostic_class") or "")
    if mode == "why-not-recall":
        if diagnostic == "surfaced_but_low_specificity":
            return {
                "primary_action": "refine_cue_first",
                "what_happened": "A route surfaced, but the cue was too broad to treat as a useful answer.",
                "why": "low_specificity",
                "next_command": 'tighten cue, then run aippocampus why-recall "<more specific cue>"',
                "do_not": [
                    "do not treat low-specificity surfacing as evidence",
                    "deepen only if continuity matters",
                ],
                "claim_boundary": "diagnostic_not_source_evidence",
            }
        if not route_ids or decision in {"missing", "unknown", "suppressed", "silent"}:
            return {
                "primary_action": "refine_cue_or_check_index",
                "what_happened": "No usable recall route surfaced.",
                "why": ",".join(reasons[:3]) or "no_route",
                "next_command": 'aippocampus search "<distinctive exact phrase>" --json',
                "recovery_commands": [
                    'aippocampus why-recall "<more specific cue>" --json',
                    "aippocampus onboard --status --json",
                ],
                "do_not": ["do not claim from recall silence"],
                "claim_boundary": "diagnostic_not_source_evidence",
            }
        return {
            "primary_action": "use_why_recall_or_deepen",
            "what_happened": "A route surfaced; why-not is not the best question for this cue.",
            "why": diagnostic or "route_surfaced",
            "next_command": 'aippocampus why-recall "<cue>"',
            "do_not": ["do not treat this diagnostic as source evidence"],
            "claim_boundary": "diagnostic_not_source_evidence",
        }
    if route_ids:
        return {
            "primary_action": "deepen_selected_route",
            "what_happened": "Recall surfaced a route.",
            "why": ",".join(reasons[:3]) or "route_returned",
            "next_command": 'aippocampus agent recall "<cue>" --json; then deepen route 1',
            "do_not": ["do not quote or claim until source is reopened"],
            "claim_boundary": "diagnostic_not_source_evidence",
        }
    return {
        "primary_action": "continue_or_refine_cue",
        "what_happened": "No recall route surfaced.",
        "why": ",".join(reasons[:3]) or "no_route",
        "next_command": 'aippocampus search "<distinctive exact phrase>" --json',
        "recovery_commands": ["aippocampus onboard --status --json"],
        "do_not": ["do not claim from recall silence"],
        "claim_boundary": "diagnostic_not_source_evidence",
    }


def recall_diagnostic_report(
    *,
    cue: str,
    mode: str = "why-recall",
    cwd: str | Path | None = None,
    clean_source_dir: str | Path | None = None,
    registry_dir: str | Path | None = None,
    registry_path: str | Path | None = None,
    max_routes: int = DEFAULT_MAX_ROUTES,
    handle: Any | None = None,
    thread_id: str | None = None,
    topic_epoch: str | None = None,
    lock_id: str | None = None,
    lock_path: str | Path | None = None,
    cache_path: str | Path | None = None,
    semantic_result_json: str | None = None,
    run_live_semantic_gate: bool = False,
    semantic_gate_mode: str = "off",
    semantic_timeout: int = 12,
    recall_context_payload: Mapping[str, Any] | None = None,
    active_lock_payload: Mapping[str, Any] | None = None,
    ambient_cache_payload: Mapping[str, Any] | None = None,
    semantic_gate_payload: Mapping[str, Any] | None = None,
    include_associative_path_diagnostics: bool = False,
    associative_path_sidecar_dir: str | Path | None = None,
    associative_path_bridge_path: str | Path | None = None,
    associative_path_navigation_path: str | Path | None = None,
    associative_path_active_lock_path: str | Path | None = None,
    associative_path_feedback_path: str | Path | None = None,
    associative_path_input_pack: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_mode = str(mode or "why-recall").replace("_", "-")
    normalized_mode = normalized_mode if normalized_mode in {"why-recall", "why-not-recall"} else "why-recall"
    cwd_path = core.canonical_path(cwd or os.getcwd())
    registry_dir_path = Path(registry_dir).resolve() if registry_dir else None
    registry_path_obj = _registry_path(registry_dir_path, registry_path)
    registry_for_reads = registry_path_obj if registry_path_obj.exists() else None
    clean_dir = clean_source_dir_for(cwd_path, clean_source_dir)
    limit = max(1, min(25, safe_int(max_routes) or DEFAULT_MAX_ROUTES))
    reports = [
        _recall_context_report(
            cue=cue,
            cwd=cwd_path,
            clean_dir=clean_dir,
            registry_dir=registry_dir_path,
            max_routes=limit,
            injected=recall_context_payload,
        )
    ]
    if handle is not None:
        reports.append(handle_surface_report(handle, clean_source_dir=clean_dir))
    lock_payload = active_lock_payload if active_lock_payload is not None else _active_lock_payload(
        cue=cue,
        cwd=cwd_path,
        registry_path=registry_for_reads,
        registry_dir=registry_dir_path,
        lock_id=lock_id,
        lock_path=lock_path,
        thread_id=thread_id,
        topic_epoch=topic_epoch,
    )
    reports.append(active_lock_surface_report(lock_payload))
    ambient_payload = ambient_cache_payload if ambient_cache_payload is not None else _ambient_cache_payload(
        cwd=cwd_path,
        registry_path=registry_for_reads,
        registry_dir=registry_dir_path,
        cache_path=cache_path,
        thread_id=thread_id,
        topic_epoch=topic_epoch,
    )
    reports.append(ambient_cache_surface_report(ambient_payload))
    semantic_payload = semantic_gate_payload if semantic_gate_payload is not None else _semantic_gate_payload(
        cue=cue,
        cwd=cwd_path,
        registry_path=registry_for_reads,
        semantic_result_json=semantic_result_json,
        run_live=run_live_semantic_gate,
        semantic_gate_mode=semantic_gate_mode,
        semantic_timeout=semantic_timeout,
    )
    reports.append(
        semantic_gate_surface_report(semantic_payload, semantic_gate_mode=semantic_gate_mode)
    )
    associative_path_diagnostics: dict[str, Any] | None = None
    if include_associative_path_diagnostics:
        raw_recall_context_payload = recall_context_payload
        if raw_recall_context_payload is None and (clean_dir / "messages.jsonl").exists():
            try:
                raw_recall_context_payload = recall_context_packet(
                    intent=cue,
                    cwd=cwd_path,
                    clean_source_dir=clean_dir,
                    registry_dir=registry_dir_path,
                    max_routes=limit,
                )
            except RecallNavigationError:
                raw_recall_context_payload = None
        associative_path_diagnostics = build_associative_path_diagnostic(
            query=cue,
            cwd=cwd_path,
            sidecar_dir=associative_path_sidecar_dir,
            recall_context_payload=raw_recall_context_payload,
            active_lock_rows=[lock_payload] if isinstance(lock_payload, Mapping) else None,
            input_pack=associative_path_input_pack,
            semantic_bridge_path=associative_path_bridge_path,
            navigation_path=associative_path_navigation_path,
            active_lock_path=associative_path_active_lock_path,
            feedback_path=associative_path_feedback_path,
            max_routes=min(3, limit),
        )
    reasons = unique(
        [
            code
            for report in reports
            for code in report.get("reason_codes", [])
            if code in REASON_CODE_CATALOG
        ]
    )
    route_ids = unique(
        [
            route_id
            for report in reports
            for route_id in report.get("route_ids", [])
            if str(route_id or "").strip()
        ],
        limit=24,
    )
    decision = overall_decision(reasons)
    projection = _why_not_projection(
        mode=normalized_mode,
        decision=decision,
        route_ids=route_ids,
        reports=reports,
        max_routes=limit,
    )
    action_card = _frontstage_action_card(
        mode=normalized_mode,
        decision=decision,
        projection=projection,
        route_ids=route_ids,
        reasons=reasons,
    )
    payload = {
            "kind": DIAGNOSTIC_KIND,
            "schema_version": SCHEMA_VERSION,
            "mode": normalized_mode,
            "cue_hash": cue_hash(cue),
            "decision": decision,
            **projection,
            "searched_surfaces": [
                "recall_context",
                "active_lock",
                "ambient_cache",
                "semantic_gate",
                *(["associative_path_walker"] if associative_path_diagnostics else []),
            ],
            "surface_reports": reports,
            "reasons": reasons,
            "route_ids": route_ids,
            "action_card": action_card,
            "foreground_next_action": action_card["primary_action"],
            "next_safe_action": next_safe_action(reasons),
            "cannot_claim": list(CANNOT_CLAIM),
            "reason_code_catalog_version": REASON_CODE_CATALOG_VERSION,
            "privacy_boundary": {
                "raw_cue_emitted": False,
                "raw_source_text_emitted": False,
                "local_paths_emitted": False,
                "diagnostic_is_not_truth_source": True,
                "associative_path_walker_changed_default_ranking": False,
            },
            "observatory": {
                "issue": 576,
                "role": "low_level_why_this_route_drilldown_not_control_plane",
            },
        }
    if associative_path_diagnostics is not None:
        payload["associative_path_diagnostics"] = associative_path_diagnostics
    return redact_private_paths(payload)
