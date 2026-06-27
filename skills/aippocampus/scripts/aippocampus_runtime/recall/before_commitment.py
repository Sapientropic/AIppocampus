"""Executable before-commitment attention surface map.

This is a compact report/fixture layer for #836-style commitment boundaries.
It does not add a permission system, broad foreground prose, or a new authority
taxonomy; it maps existing action grammar to small push nudges and pullable refs.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def before_commitment_surface_map() -> dict[str, Any]:
    surfaces = {
        "prompt_time_scent": {
            "owner_module": "recall.prompt_recall_hot_path",
            "allowed_output_modes": ["silent", "scent", "source_ref_shelf"],
            "max_foreground_budget": "tiny",
            "source_reopen_required": True,
            "hard_masks": ["privacy", "blocked", "source_thin"],
            "feedback_outcome_event": "ignored",
        },
        "pre_tool_action_nudge": {
            "owner_module": "recall.fresh_thread_action",
            "allowed_output_modes": ["silent", "tiny_nudge"],
            "max_foreground_budget": "tiny",
            "source_reopen_required": True,
            "hard_masks": ["privacy", "dismissed", "blocked"],
            "feedback_outcome_event": "prevented_failure",
        },
        "pre_edit_action_nudge": {
            "owner_module": "recall.agent_continuity",
            "allowed_output_modes": ["silent", "tiny_nudge"],
            "max_foreground_budget": "tiny",
            "source_reopen_required": True,
            "hard_masks": ["privacy", "scope_mismatch", "blocked"],
            "feedback_outcome_event": "prevented_failure",
        },
        "pre_commit_action_nudge": {
            "owner_module": "recall.feedback.outcome",
            "allowed_output_modes": ["silent", "tiny_nudge"],
            "max_foreground_budget": "tiny",
            "source_reopen_required": True,
            "hard_masks": ["privacy", "dismissed", "blocked"],
            "feedback_outcome_event": "source_reopen_success",
        },
        "before_final_claim_check": {
            "owner_module": "recall.source_reopen_budget",
            "allowed_output_modes": ["silent", "claim_check", "source_reopen_request"],
            "max_foreground_budget": "small",
            "source_reopen_required": True,
            "hard_masks": ["privacy", "source_thin", "blocked"],
            "feedback_outcome_event": "source_reopen_success",
        },
        "uncertainty_pull": {
            "owner_module": "recall.active_recall",
            "allowed_output_modes": ["pullable_ref_shelf", "deepen_request"],
            "max_foreground_budget": "small",
            "source_reopen_required": True,
            "hard_masks": ["privacy", "blocked"],
            "feedback_outcome_event": "deepened",
        },
        "idle_compaction_handoff": {
            "owner_module": "recall.active_path_packet",
            "allowed_output_modes": ["handoff_route_refresh"],
            "max_foreground_budget": "background",
            "source_reopen_required": True,
            "hard_masks": ["privacy", "blocked"],
            "feedback_outcome_event": "superseded",
        },
    }
    return {
        "kind": "aippocampus_before_commitment_surface_map",
        "schema_version": 1,
        "source_discussion": "#836",
        "goal": "reduce high-cost continuity failures, not more recall by default",
        "surfaces": surfaces,
        "authority_boundary": "reuse existing action grammar and claim permissions",
        "privacy_boundary": "handles_ids_reason_codes_only",
    }


def _route_ref(route: Mapping[str, Any]) -> dict[str, str]:
    return {
        key: str(route.get(key) or "")
        for key in ("route_id", "source_ref_id", "segment_id", "route_family")
        if route.get(key) not in (None, "", [])
    }


def _silent_reasons(route: Mapping[str, Any]) -> list[str]:
    reasons: list[str] = []
    if route.get("masked") or route.get("blocked"):
        reasons.append("masked_or_blocked")
    if str(route.get("currentness") or "").casefold() in {"stale", "superseded"}:
        reasons.append("stale_route_boundary")
    if str(route.get("authority") or "").casefold() in {"", "direction_only", "ignore_or_blocked"}:
        reasons.append("source_thin_or_low_authority")
    return reasons


def build_before_commitment_fixture(route_material: Mapping[str, Any]) -> dict[str, Any]:
    """Build one public-safe fixture across pull and push attention surfaces."""

    ref = _route_ref(route_material)
    reasons = _silent_reasons(route_material)
    base = {
        "kind": "aippocampus_before_commitment_fixture",
        "schema_version": 1,
        "source_discussion": "#836",
        "route_contract": {
            "authority": str(route_material.get("authority") or "direction_with_ref"),
            "currentness": str(route_material.get("currentness") or "unknown"),
            "source_reopen_required": True,
            "source_truth": False,
        },
        "pullable_ref_shelf": {
            "output_mode": "pullable_ref_shelf",
            "refs": [ref] if ref else [],
            "max_foreground_budget": "small",
        },
        "before_action_nudge": {
            "output_mode": "tiny_nudge",
            "route_id": ref.get("route_id", ""),
            "reason_codes": ["silent_constraint_route_available"],
            "source_reopen_required": True,
            "max_foreground_budget": "tiny",
        },
        "before_answer_nudge": {
            "output_mode": "claim_check",
            "route_id": ref.get("route_id", ""),
            "source_reopen_required": True,
            "max_foreground_budget": "small",
        },
        "negative_control": {
            "decision": "silent" if reasons else "not_applicable",
            "reason_codes": reasons,
        },
        "privacy_boundary": "handles_ids_reason_codes_only",
    }
    if reasons:
        base["before_action_nudge"] = {
            "output_mode": "silent",
            "route_id": ref.get("route_id", ""),
            "reason_codes": reasons,
            "source_reopen_required": True,
        }
        base["before_answer_nudge"] = {
            "output_mode": "silent",
            "route_id": ref.get("route_id", ""),
            "reason_codes": reasons,
            "source_reopen_required": True,
        }
    return base
