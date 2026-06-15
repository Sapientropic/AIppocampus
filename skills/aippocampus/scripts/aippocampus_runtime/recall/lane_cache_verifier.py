"""Cheap verifier for speculative recall lane cache proposals.

Cached lane output is a draft proposal, not memory evidence. This verifier
keeps reuse cheap while preventing stale, blocked, dismissed, or policy-mismatched
routes from silently re-entering foreground recall.
"""

from __future__ import annotations

import time
from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

SCHEMA_VERSION = 1
REPORT_KIND = "aippocampus_lane_cache_verifier_report"
ROW_KIND = "aippocampus_lane_cache_verification"
ACCEPT = "accept"
REJECT = "reject"
RERUN = "rerun"
DECISIONS = {ACCEPT, REJECT, RERUN}
BLOCKED_FEEDBACK = {
    "dismissed",
    "wrong_route",
    "blocked",
    "superseded",
    "refuted",
    "anti_nag_active",
}
BLOCKED_PRIVACY = {"private_blocked", "privacy_blocked", "blocked", "restricted"}
HIGH_COST_SCOPES = {"write", "publish", "release", "delete", "commit", "merge", "deploy"}


def _text(value: Any, *, default: str = "") -> str:
    text = str(value or "").strip()
    return text or default


def _safe_label(value: Any, *, fallback: str = "") -> str:
    text = _text(value).casefold()
    if text and len(text) <= 96 and all(char.isalnum() or char in "-_.:#" for char in text):
        return text
    return fallback


def _strings(value: Any, *, limit: int = 12) -> list[str]:
    raw_items: Sequence[Any]
    if isinstance(value, str):
        raw_items = [value]
    elif isinstance(value, Sequence):
        raw_items = value
    else:
        return []
    result: list[str] = []
    seen: set[str] = set()
    for item in raw_items:
        text = _safe_label(item)
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
        if len(result) >= limit:
            break
    return result


def _candidate_refs(proposal: Mapping[str, Any]) -> list[str]:
    refs = _strings(proposal.get("candidate_refs") or proposal.get("route_refs"), limit=16)
    if refs:
        return refs
    ref = _safe_label(proposal.get("candidate_ref") or proposal.get("route_ref"))
    return [ref] if ref else []


def _current(context: Mapping[str, Any] | None, proposal: Mapping[str, Any], key: str) -> Any:
    if isinstance(context, Mapping) and context.get(key) is not None:
        return context[key]
    return proposal.get(f"current_{key}")


def _expired(proposal: Mapping[str, Any], context: Mapping[str, Any] | None) -> bool:
    now = float(_current(context, proposal, "now_unix") or time.time())
    expires = proposal.get("expires_unix")
    if expires is None:
        return False
    try:
        return float(expires) < now
    except (TypeError, ValueError):
        return True


def _action_scope_changed_to_high_cost(
    proposal: Mapping[str, Any],
    context: Mapping[str, Any] | None,
) -> bool:
    old_scope = _safe_label(proposal.get("action_scope"))
    new_scope = _safe_label(_current(context, proposal, "action_scope"))
    return bool(old_scope and new_scope and old_scope != new_scope and new_scope in HIGH_COST_SCOPES)


def _verification_reasons(
    proposal: Mapping[str, Any],
    context: Mapping[str, Any] | None,
) -> tuple[str, list[str]]:
    reasons: list[str] = []
    lane_id = _safe_label(proposal.get("lane_id"))
    if not lane_id:
        reasons.append("missing_lane_id")
    if not _candidate_refs(proposal):
        reasons.append("missing_candidate_refs")

    source_fingerprint = _safe_label(proposal.get("source_fingerprint"))
    current_source = _safe_label(_current(context, proposal, "source_fingerprint"))
    if source_fingerprint and current_source and source_fingerprint != current_source:
        reasons.append("source_fingerprint_mismatch")

    topic_epoch = _safe_label(proposal.get("topic_epoch"))
    current_topic = _safe_label(_current(context, proposal, "topic_epoch"))
    if topic_epoch and current_topic and topic_epoch != current_topic:
        reasons.append("topic_epoch_mismatch")

    policy_version = _safe_label(proposal.get("policy_version"))
    current_policy = _safe_label(_current(context, proposal, "policy_version"))
    if policy_version and current_policy and policy_version != current_policy:
        reasons.append("policy_version_mismatch")

    if _action_scope_changed_to_high_cost(proposal, context):
        reasons.append("high_cost_action_scope_changed")
    if _expired(proposal, context):
        reasons.append("expired_lane_cache_proposal")

    feedback_state = _safe_label(
        _current(context, proposal, "feedback_state") or proposal.get("feedback_state")
    )
    if feedback_state in BLOCKED_FEEDBACK:
        reasons.append(f"feedback_{feedback_state}")

    privacy_state = _safe_label(proposal.get("privacy_state") or proposal.get("privacy"))
    boundary_flags = set(_strings(proposal.get("boundary_flags"), limit=12))
    if privacy_state in BLOCKED_PRIVACY or boundary_flags & BLOCKED_PRIVACY:
        reasons.append("privacy_or_boundary_blocked")

    reject_reasons = {
        "missing_lane_id",
        "missing_candidate_refs",
        "source_fingerprint_mismatch",
        "expired_lane_cache_proposal",
        "privacy_or_boundary_blocked",
    }
    if any(reason in reject_reasons or reason.startswith("feedback_") for reason in reasons):
        return REJECT, reasons
    rerun_reasons = {
        "topic_epoch_mismatch",
        "policy_version_mismatch",
        "high_cost_action_scope_changed",
    }
    if any(reason in rerun_reasons for reason in reasons):
        return RERUN, reasons
    return ACCEPT, ["cache_proposal_still_matches_context"]


def verify_lane_cache_proposal(
    proposal: Mapping[str, Any],
    *,
    current_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    decision, reasons = _verification_reasons(proposal, current_context)
    lane_id = _safe_label(proposal.get("lane_id"), fallback="unknown_lane")
    return {
        "kind": ROW_KIND,
        "schema_version": SCHEMA_VERSION,
        "lane_id": lane_id,
        "decision": decision,
        "reason_codes": reasons,
        "candidate_ref_count": len(_candidate_refs(proposal)),
        "action_grammar": "reopenable_route" if decision == ACCEPT else "direction_only",
        "authority_level": "navigation_only",
        "claim_permission": "no_claim_before_reopen",
        "source_reopen_required_before_claim": True,
        "cache_output_is_not_evidence": True,
        "selective_regeneration_requested": decision == RERUN,
    }


def route_token_from_accepted_lane_proposal(
    proposal: Mapping[str, Any],
    verification: Mapping[str, Any],
) -> dict[str, Any] | None:
    if verification.get("decision") != ACCEPT:
        return None
    refs = _candidate_refs(proposal)
    lane_id = str(verification.get("lane_id") or "lane")
    return {
        "kind": "aippocampus_verified_lane_cache_route_token",
        "token_id": f"lane_cache:{lane_id}",
        "lane_id": lane_id,
        "route_token_level": "episode_or_question_token",
        "candidate_refs": refs,
        "action_grammar": "reopenable_route" if refs else "direction_only",
        "authority_level": "navigation_only",
        "claim_permission": "no_claim_before_reopen",
        "source_reopen_required_before_claim": True,
        "cache_output_is_not_evidence": True,
        "route_features": {
            "terms": _strings(proposal.get("terms") or proposal.get("route_terms"), limit=16),
            "semantic_score": 0.0,
        },
    }


def build_lane_cache_verifier_report(
    proposals: Sequence[Mapping[str, Any]],
    *,
    current_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    rows = [
        verify_lane_cache_proposal(proposal, current_context=current_context)
        for proposal in proposals
    ]
    counts = Counter(row["decision"] for row in rows)
    false_accept_count = 0
    false_reject_count = 0
    for proposal, row in zip(proposals, rows, strict=True):
        expected = _safe_label(proposal.get("expected_decision"))
        if expected not in DECISIONS:
            continue
        if row["decision"] == ACCEPT and expected != ACCEPT:
            false_accept_count += 1
        if row["decision"] == REJECT and expected == ACCEPT:
            false_reject_count += 1
    return {
        "kind": REPORT_KIND,
        "schema_version": SCHEMA_VERSION,
        "ok": false_accept_count == 0,
        "case_count": len(rows),
        "verifications": rows,
        "metrics": {
            "accepted_cache_count": counts[ACCEPT],
            "rejected_cache_count": counts[REJECT],
            "rerun_count": counts[RERUN],
            "accepted_cache_avoided_lane_regeneration_count": counts[ACCEPT],
            "stale_route_revival_count": 0,
            "false_accept_count": false_accept_count,
            "false_reject_count": false_reject_count,
        },
        "boundary": {
            "cached_lane_output_is_draft_proposal": True,
            "accepted_proposals_remain_navigation_only": True,
            "source_reopen_required_before_claim": True,
            "clean_source_not_mutated": True,
        },
        "cannot_claim": [
            "cached_lane_output_as_source_truth",
            "foreground_fact_claim_without_source_reopen",
            "full_lane_regeneration_equivalence",
        ],
    }


__all__ = [
    "ACCEPT",
    "REJECT",
    "RERUN",
    "build_lane_cache_verifier_report",
    "route_token_from_accepted_lane_proposal",
    "verify_lane_cache_proposal",
]
