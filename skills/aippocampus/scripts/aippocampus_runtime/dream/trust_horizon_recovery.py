#!/usr/bin/env python3
"""Recoverable public plans for Dream trust-horizon invalidations."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def recovery_plan(
    row: Mapping[str, Any],
    *,
    action: str,
    reason: str,
    trust_status: str,
    requires_source_reopen: bool = True,
    recovery_kind: str = "source_reopen_required",
    safe_next_action: str = "reopen_source_before_use",
    hard_safety_block: bool = False,
) -> dict[str, Any]:
    return {
        "action": action,
        "reason": reason,
        "requires_source_reopen": requires_source_reopen,
        "recovery_kind": recovery_kind,
        "safe_next_action": safe_next_action,
        "hard_safety_block": hard_safety_block,
        "degraded_authority": "withheld_until_review"
        if hard_safety_block
        else "direction_only_until_source_reopen",
        "truth_boundary": row.get("truth_boundary"),
        "trust_horizon_status": trust_status,
    }


def invalidation_plan(
    row: Mapping[str, Any],
    *,
    trust_status: str,
    sensitive_blocked: bool = False,
    expired: bool = False,
    invitation_diagnostic: object = None,
    source_fingerprint_changed: bool = False,
    contradiction_visible: bool = False,
    user_correction_visible: bool = False,
    user_requested_evidence: bool = False,
    exact_or_quote_claim: bool = False,
    sensitive_claim: bool = False,
    strong_user_facing_claim: bool = False,
    review_due: bool = False,
) -> dict[str, Any] | None:
    if sensitive_blocked:
        return recovery_plan(
            row,
            action="stay_silent",
            reason="sensitive_review_required",
            trust_status=trust_status,
            recovery_kind="hard_safety_block",
            safe_next_action="ask_user_or_human_review_before_use",
            hard_safety_block=True,
        )
    if expired:
        plan = recovery_plan(
            row,
            action="reopen_source",
            reason="dream_hypothesis_expired_requires_source_reopen",
            trust_status=trust_status,
            recovery_kind="value_preserving_degradation",
            safe_next_action="reopen_source_or_use_as_direction_only",
        )
        if invitation_diagnostic:
            plan["invitation_diagnostic"] = invitation_diagnostic
            plan["safe_next_action"] = "reopen_source_or_leave_invitation_silent"
        return plan
    if source_fingerprint_changed:
        return recovery_plan(row, action="reopen_source", reason="source_fingerprint_changed", trust_status=trust_status)
    if contradiction_visible:
        return recovery_plan(
            row,
            action="reopen_source",
            reason="contradiction_visible_requires_source_reopen",
            trust_status=trust_status,
            safe_next_action="reopen_source_before_using_or_discard",
        )
    if user_correction_visible:
        return recovery_plan(
            row,
            action="ask_to_confirm",
            reason="user_correction_requires_confirmation",
            trust_status=trust_status,
            recovery_kind="user_confirmation_required",
            safe_next_action="ask_user_to_confirm_or_reopen_source",
        )
    if user_requested_evidence:
        return recovery_plan(row, action="reopen_source", reason="user_requested_evidence_requires_source_reopen", trust_status=trust_status)
    if exact_or_quote_claim or sensitive_claim:
        return recovery_plan(
            row,
            action="reopen_source",
            reason="sensitive_claim_requires_source_reopen" if sensitive_claim else "exact_or_quote_claim_requires_source_reopen",
            trust_status=trust_status,
            safe_next_action="reopen_source_before_direct_claim",
        )
    if strong_user_facing_claim:
        return recovery_plan(row, action="reopen_source", reason="strong_claim_requires_source_reopen", trust_status=trust_status)
    if review_due:
        return recovery_plan(
            row,
            action="reopen_source",
            reason="trust_horizon_review_due_requires_source_reopen",
            trust_status=trust_status,
            recovery_kind="review_due_recovery",
            safe_next_action="run_review_or_reopen_source",
        )
    return None
