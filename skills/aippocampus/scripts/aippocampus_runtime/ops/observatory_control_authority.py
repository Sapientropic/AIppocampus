#!/usr/bin/env python3
"""Control-authority audit for the read-only Cognitive Observatory."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

OBSERVATORY_SCHEMA_VERSION = 1
CONTROL_AUTHORITY_AUDIT_KIND = "aippocampus_observatory_control_authority_audit"
CONTROL_ACTION_FIELDS = (
    "requested_control_action",
    "control_action",
    "activation_command",
    "apply_action",
)


def _control_action_attempt_count(rows: list[dict[str, Any]]) -> int:
    count = 0
    for row in rows:
        if any(str(row.get(key) or "").strip() for key in CONTROL_ACTION_FIELDS):
            count += 1
        elif row.get("activate") or row.get("activate_foreground"):
            count += 1
    return count


def observatory_control_authority_audit(
    *,
    activation_surfaces: list[dict[str, Any]] | None = None,
    activation_authority: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    rows = [dict(row) for row in activation_surfaces or [] if isinstance(row, Mapping)]
    authority_metrics = (
        activation_authority.get("metrics")
        if isinstance(activation_authority, Mapping)
        else {}
    )
    metrics: Mapping[str, Any] = authority_metrics if isinstance(authority_metrics, Mapping) else {}
    control_action_attempt_count = _control_action_attempt_count(rows)
    owner_surface_mutation_attempt_count = sum(1 for row in rows if row.get("owner_surface_mutation"))
    foreground_hook_mutation_attempt_count = sum(1 for row in rows if row.get("foreground_hook_mutation"))
    clean_source_mutation_attempt_count = int(
        metrics.get("activation_clean_source_mutation_attempt_count") or 0
    )
    truth_status_mutation_attempt_count = int(
        metrics.get("activation_truth_status_mutation_attempt_count") or 0
    )
    row_level_blocked_count = sum(
        1
        for row in rows
        if any(str(row.get(key) or "").strip() for key in CONTROL_ACTION_FIELDS)
        or row.get("activate")
        or row.get("activate_foreground")
        or row.get("owner_surface_mutation")
        or row.get("foreground_hook_mutation")
        or row.get("clean_source_mutation")
        or row.get("truth_status_changed")
    )
    blocked_control_action_count = max(
        row_level_blocked_count,
        clean_source_mutation_attempt_count,
        truth_status_mutation_attempt_count,
    )
    decision = (
        "blocked_control_attempts_present"
        if blocked_control_action_count
        else "read_only_diagnostic_only"
    )
    return {
        "schema_version": OBSERVATORY_SCHEMA_VERSION,
        "kind": CONTROL_AUTHORITY_AUDIT_KIND,
        "mode": "deterministic_public_safe",
        "authority": "diagnostic_only",
        "decision": decision,
        "mutation_allowed": {
            "clean_source": False,
            "owner_surfaces": False,
            "foreground_hook": False,
            "activation_truth_status": False,
        },
        "metrics": {
            "control_action_attempt_count": control_action_attempt_count,
            "blocked_control_action_count": blocked_control_action_count,
            "owner_surface_mutation_attempt_count": owner_surface_mutation_attempt_count,
            "foreground_hook_mutation_attempt_count": foreground_hook_mutation_attempt_count,
            "activation_truth_status_mutation_attempt_count": truth_status_mutation_attempt_count,
            "activation_clean_source_mutation_attempt_count": clean_source_mutation_attempt_count,
        },
        "privacy_boundary": {
            "raw_control_payload_serialized": False,
            "raw_source_text_serialized": False,
            "local_paths_serialized": False,
        },
        "issue_readouts": {
            "github_576": {
                "control_authority": "diagnostic_only_not_control_plane",
                "control_attempts_blocked": blocked_control_action_count,
                "raw_source_leakage": "not_serialized",
                "static_view": "existing_public_safe_fixture",
                "live_host_control_plane": "not_implemented",
                "closeout_eligible": False,
            }
        },
        "cannot_claim": [
            "observatory_control_plane",
            "observatory_rows_can_mutate_control_state",
            "observatory_rows_are_source_truth",
            "live_host_observatory_ui_quality",
        ],
    }
