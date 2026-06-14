#!/usr/bin/env python3
"""Current-completeness projection for the read-only Cognitive Observatory."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from aippocampus_runtime.ops import cognitive_observatory

COMPLETENESS_KIND = "aippocampus_cognitive_observatory_current_completeness"
COMPLETENESS_SCHEMA_VERSION = 1
EXPECTED_CURRENT_SURFACES = (
    "route_readiness",
    "activation_authority",
    "recall_diagnostic",
    "query_pattern_routes",
    "cognitive_load_calibration",
    "sleep_cycle",
    "campus_usefulness_panels",
)


def _fragment(*parts: str) -> str:
    return "".join(parts)


PUBLIC_OUTPUT_BLOCKERS = (
    _fragment("raw", "_prompt"),
    _fragment("raw", "_source", "_text"),
    _fragment("source", "_refs"),
    _fragment("thread", "_id"),
    _fragment("provider", "_payload"),
    _fragment("SECRET", "_TOKEN"),
    _fragment("api", "_key"),
    _fragment("pass", "word"),
    _fragment("bear", "er"),
    "E:\\",
    "/home/",
    "/Users/",
)


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _int(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    try:
        return max(0, int(float(value)))
    except (TypeError, ValueError):
        return 0


def _token_count(value: Any, tokens: tuple[str, ...]) -> int:
    count = 0
    if isinstance(value, Mapping):
        for raw_key, child in value.items():
            key = str(raw_key).casefold()
            if any(token in key for token in tokens) and isinstance(child, (int, float, bool)):
                count += _int(child)
            count += _token_count(child, tokens)
    elif isinstance(value, list):
        for child in value:
            count += _token_count(child, tokens)
    elif isinstance(value, str):
        text = value.casefold()
        if any(token in text for token in tokens):
            count += 1
    return count


def _surface_payload(observatory_report: Mapping[str, Any], surface: str) -> Any:
    return observatory_report.get(surface)


def _surface_included(observatory_report: Mapping[str, Any], surface: str) -> bool:
    surfaces = {str(item) for item in _as_list(observatory_report.get("surfaces"))}
    return surface in surfaces and _surface_payload(observatory_report, surface) is not None


def _surface_row(
    observatory_report: Mapping[str, Any],
    surface: str,
    *,
    fixture_mode: bool,
) -> dict[str, Any]:
    payload = _surface_payload(observatory_report, surface)
    included = _surface_included(observatory_report, surface)
    return {
        "surface": surface,
        "status": "included" if included else "missing",
        "surface_supported": True,
        "surface_present_in_this_readout": included,
        "surface_validated_by_fixture": bool(fixture_mode and included),
        "included_count": 1 if included else 0,
        "missing_count": 0 if included else 1,
        "stale_count": _token_count(payload, ("stale", "expired", "superseded")),
        "privacy_blocked_count": _token_count(
            payload,
            ("privacy", "secret", "sensitive", "blocked"),
        ),
        "suppressed_count": _token_count(payload, ("suppress", "silent")),
    }


def _projection_leak_flags(report: Mapping[str, Any]) -> list[str]:
    encoded = json.dumps(report, ensure_ascii=False, sort_keys=True)
    lowered = encoded.casefold()
    flags: list[str] = []
    for fragment in PUBLIC_OUTPUT_BLOCKERS:
        if fragment.casefold() in lowered:
            flags.append("blocked_public_fragment")
            break
    return flags


def _current_fixture_observatory_readout() -> dict[str, Any]:
    """Build a replayable current/local-style readout without private history.

    The rows intentionally include stale, privacy-blocked, suppressed, and
    attempted-control cases so the completeness projection proves gaps and
    blocked control attempts are visible without granting any control-plane
    authority.
    """

    now_unix = 1_800_000_120
    route_candidates = [
        {
            "route_id": "current-useful-route",
            "freshness": "current",
            "created_unix": 1_800_000_000,
            "ttl_seconds": 900,
            "expected_value": 5,
            "estimated_cost": 1,
            "source_refs": [{"source_id": "clean:current", "message_id": "m1"}],
        },
        {
            "route_id": "stale-route",
            "freshness": "stale",
            "created_unix": 1_799_990_000,
            "ttl_seconds": 30,
            "expected_value": 5,
            "estimated_cost": 1,
            "source_refs": [{"source_id": "clean:stale", "message_id": "m2"}],
        },
        {
            "route_id": "privacy-blocked-route",
            "freshness": "current",
            "created_unix": 1_800_000_000,
            "ttl_seconds": 900,
            "privacy_action": "hard_block",
            "privacy_reason_codes": ["secret_like"],
            "expected_value": 5,
            "estimated_cost": 1,
            "source_refs": [{"source_id": "clean:private", "message_id": "m3"}],
        },
        {
            "route_id": "missing-source-route",
            "freshness": "current",
            "created_unix": 1_800_000_000,
            "ttl_seconds": 900,
            "expected_value": 5,
            "estimated_cost": 1,
            "source_refs": [],
        },
    ]
    activation_surfaces = [
        {
            "surface_id": "current-active-lock",
            "surface_kind": "active_recall_lock",
            "conflict_key": "current-route",
            "freshness": "current",
            "source_refs": [{"source_id": "clean:current", "message_id": "m1"}],
            "source_reopen_success_count": 1,
            "recent_helpful_count": 1,
        },
        {
            "surface_id": "stale-ambient-card",
            "surface_kind": "ambient_card",
            "conflict_key": "current-route",
            "freshness": "stale",
            "pruning_action": "retire",
            "wrong_route_drag_count": 1,
            "source_refs": [{"source_id": "clean:old", "message_id": "m4"}],
        },
        {
            "surface_id": "blocked-control-attempt",
            "surface_kind": "operator_probe",
            "conflict_key": "control-boundary",
            "requested_control_action": "activate_foreground_route",
            "activate_foreground": True,
            "foreground_hook_mutation": True,
            "owner_surface_mutation": True,
        },
    ]
    recall_diagnostic = {
        "kind": "aippocampus_recall_diagnostic_report",
        "ok": True,
        "mode": "local_current_fixture",
        "metrics": {
            "route_candidate_count": 4,
            "source_reopen_required_count": 4,
            "private_payload_serialized": 0,
        },
        "contract": {
            "diagnostic_only": True,
            "source_reopen_required_before_claim": True,
        },
    }
    sleep_cycle_payload = {
        "execution_mode": "fixture",
        "no_write": True,
        "write_mode": "no_write",
        "run_ready": False,
        "counts": {
            "queue_items": 2,
            "selected_items": 0,
            "accepted": 0,
            "parked": 1,
            "rejected": 1,
            "written_findings": 0,
            "written_working_memory": 0,
        },
        "worker_statuses": {"deterministic_only": 1},
        "failure_buckets": {},
        "cache": {"hit": 0, "miss": 0},
    }
    query_pattern_routes = [
        {
            "query_aliases": ["current observatory route"],
            "source_generation_digest": "gen-current-observatory",
            "thread_key_hash": "thread_current_observatory",
            "source_refs": [{"source_id": "clean:query", "message_id": "m5"}],
            "created_unix": 1_800_000_000,
            "ttl_seconds": 900,
            "confidence": 0.9,
        },
        {
            "query_aliases": ["stale observatory route"],
            "source_generation_digest": "gen-stale-observatory",
            "thread_key_hash": "thread_stale_observatory",
            "source_refs": [{"source_id": "clean:query-old", "message_id": "m6"}],
            "created_unix": 1_799_000_000,
            "ttl_seconds": 30,
            "confidence": 0.9,
        },
        {
            "query_aliases": ["blocked route"],
            "source_generation_digest": "gen-blocked-observatory",
            "thread_key_hash": "thread_blocked_observatory",
            "source_refs": [{"source_id": "clean:query-private", "message_id": "m7"}],
            "created_unix": 1_800_000_000,
            "ttl_seconds": 900,
            "confidence": 0.9,
            "privacy_blocked": True,
        },
    ]
    cognitive_load_calibration = {
        "kind": "aippocampus_cognitive_load_private_history_calibration",
        "status": "measured_public_safe_aggregate",
        "input_surface": {
            "thread_count_scanned": 2,
            "threads_with_signal_count": 1,
            "message_rows_scanned": 8,
            "event_rows_scanned": 12,
        },
        "extraction_metrics": {
            "signal_event_count": 3,
            "message_signal_event_count": 1,
            "behavior_signal_event_count": 2,
        },
        "sidecar_metrics": {
            "entry_count": 3,
            "max_load_boost": 0.16,
            "overpersonalization_from_load_signal_count": 0,
        },
        "sidecar_projection": {
            "load_bucket_counts": {"medium": 1, "low": 2},
            "reason_code_counts": {"failed_test": 2, "user_correction": 1},
        },
        "calibration_report": {
            "issue_readouts": {
                "github_575": {
                    "private_real_history_calibration": "measured_public_safe_aggregate",
                    "host_timing_quality": "not_measured",
                    "closeout_eligible": False,
                }
            },
            "cannot_claim": ["user_visible_recall_improvement"],
        },
    }
    return cognitive_observatory.cognitive_observatory_readout(
        route_candidates=route_candidates,
        activation_surfaces=activation_surfaces,
        recall_diagnostic=recall_diagnostic,
        sleep_cycle_payload=sleep_cycle_payload,
        query_pattern_routes=query_pattern_routes,
        cognitive_load_calibration=cognitive_load_calibration,
        now_unix=now_unix,
    )


def build_current_completeness_report(
    *,
    observatory_report: Mapping[str, Any] | None = None,
    expected_surfaces: Sequence[str] = EXPECTED_CURRENT_SURFACES,
) -> dict[str, Any]:
    source_report = (
        dict(observatory_report)
        if isinstance(observatory_report, Mapping)
        else _current_fixture_observatory_readout()
    )
    fixture_mode = observatory_report is None
    surface_matrix = [
        _surface_row(source_report, surface, fixture_mode=fixture_mode)
        for surface in expected_surfaces
    ]
    included_surfaces = [
        row["surface"] for row in surface_matrix if row["surface_present_in_this_readout"]
    ]
    missing_surfaces = [
        row["surface"] for row in surface_matrix if row["missing_count"]
    ]
    blocked_or_suppressed_surfaces = [
        {
            "surface": row["surface"],
            "stale_count": row["stale_count"],
            "privacy_blocked_count": row["privacy_blocked_count"],
            "suppressed_count": row["suppressed_count"],
        }
        for row in surface_matrix
        if row["stale_count"]
        or row["privacy_blocked_count"]
        or row["suppressed_count"]
    ]
    control_audit = _as_mapping(source_report.get("control_authority_audit"))
    control_metrics = _as_mapping(control_audit.get("metrics"))
    contract = _as_mapping(source_report.get("contract"))
    mutation_allowed = _as_mapping(control_audit.get("mutation_allowed"))
    ranking_or_hook_mutation_count = 0
    if (
        contract.get("foreground_hook_mutation_allowed")
        or mutation_allowed.get("foreground_hook")
        or not contract.get("not_control_plane", True)
    ):
        ranking_or_hook_mutation_count = 1

    summary = {
        "expected_surface_count": len(tuple(expected_surfaces)),
        "included_surface_count": sum(row["included_count"] for row in surface_matrix),
        "missing_surface_count": len(missing_surfaces),
        "missing_surfaces": missing_surfaces,
        "stale_bucket_count": sum(row["stale_count"] for row in surface_matrix),
        "privacy_blocked_bucket_count": sum(
            row["privacy_blocked_count"] for row in surface_matrix
        ),
        "suppressed_bucket_count": sum(row["suppressed_count"] for row in surface_matrix),
        "control_attempts_blocked": _int(control_metrics.get("blocked_control_action_count")),
        "ranking_or_hook_mutation_count": ranking_or_hook_mutation_count,
        "raw_leak_flag_count": 0,
    }
    complete_current_surface = not missing_surfaces
    report: dict[str, Any] = {
        "schema_version": COMPLETENESS_SCHEMA_VERSION,
        "kind": COMPLETENESS_KIND,
        "mode": "local_current_fixture" if observatory_report is None else "projection_audit",
        "ok": False,
        "complete_current_surface": complete_current_surface,
        "reader_contract": {
            "included_surfaces": included_surfaces,
            "missing_optional_surfaces": missing_surfaces,
            "blocked_or_suppressed_surfaces": blocked_or_suppressed_surfaces,
            "control_plane_status": "read_only",
            "recommended_next_actions": [
                "Use included_surfaces as the read-only diagnostic checklist.",
                "Reopen source before factual claims from route-like rows.",
                "Treat missing or suppressed surfaces as opt-in repair inputs.",
            ],
        },
        "expected_surfaces": list(expected_surfaces),
        "surface_matrix": surface_matrix,
        "summary": summary,
        "control_plane_boundary": {
            "blocked_diagnostics_only": True,
            "attempted_control_action_count": _int(
                control_metrics.get("control_action_attempt_count")
            ),
            "attempted_foreground_hook_mutation_count": _int(
                control_metrics.get("foreground_hook_mutation_attempt_count")
            ),
            "control_attempts_blocked": summary["control_attempts_blocked"],
            "ranking_or_hook_mutation_count": ranking_or_hook_mutation_count,
            "live_recall_ranking_mutated": False,
            "foreground_hook_behavior_mutated": False,
        },
        "privacy_boundary": {
            "prompt_text_serialized": False,
            "source_text_serialized": False,
            "source_handle_payload_serialized": False,
            "thread_handles_serialized": False,
            "provider_details_serialized": False,
            "credential_like_values_serialized": False,
        },
        "can_claim": [
            "current_observatory_completeness_projection_exists",
            "expected_surfaces_are_explicitly_included_or_missing",
            "surface_supported_present_and_validated_states_are_separate",
            "blocked_control_attempts_are_diagnostic_only",
            "public_projection_omits_private_source_payloads",
        ],
        "cannot_claim": [
            "observatory_is_a_control_plane",
            "observatory_rows_can_change_activation_order",
            "observatory_summaries_are_source_truth",
            "live_user_visible_quality_lift",
            "private_raw_history_is_public_evidence",
            "absent_optional_surface_validated_by_fixture",
        ],
    }
    leak_flags = _projection_leak_flags(report)
    report["raw_leak_flags"] = leak_flags
    report["summary"]["raw_leak_flag_count"] = len(leak_flags)
    closeout_eligible = bool(
        complete_current_surface
        and not leak_flags
        and summary["control_attempts_blocked"] > 0
        and ranking_or_hook_mutation_count == 0
    )
    report["ok"] = closeout_eligible
    report["issue_readouts"] = {
        "github_1443": {
            "current_completeness_smoke": "measured_public_fixture",
            "expected_surfaces_all_accounted": complete_current_surface,
            "missing_surfaces": missing_surfaces,
            "control_attempts_blocked": summary["control_attempts_blocked"],
            "ranking_or_hook_mutation_count": ranking_or_hook_mutation_count,
            "raw_leak_flag_count": len(leak_flags),
            "closeout_eligible": closeout_eligible,
        }
    }
    return report
