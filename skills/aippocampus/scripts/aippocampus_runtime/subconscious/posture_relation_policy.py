"""Promotion gate for scoped posture-relation policies."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from aippocampus_runtime.core import stable_json_lines_id

SCHEMA_VERSION = 1
KIND = "posture_relation_policy_row"


def _text(value: Any) -> str:
    return str(value or "").strip()


def promotion_gate(
    candidate: Mapping[str, Any],
    *,
    min_observed_sequence_count: int = 2,
    max_counterexample_ratio: float = 0.35,
    public_default_allowed: bool = False,
    max_lift: float = 0.12,
) -> dict[str, Any]:
    observed = int(candidate.get("observed_sequence_count") or 0)
    counter = int(candidate.get("counterexample_count") or 0)
    scope = _text(candidate.get("scope") or "project")
    refs = [ref for ref in candidate.get("source_refs") or [] if isinstance(ref, Mapping)]
    privacy = _text(candidate.get("privacy_state") or candidate.get("privacy") or "public_safe")
    ratio = (counter / observed) if observed else 1.0
    reasons: list[str] = []
    if not refs:
        reasons.append("source_refs_missing")
    if observed < min_observed_sequence_count:
        reasons.append("observed_sequence_count_below_threshold")
    if ratio > max_counterexample_ratio:
        reasons.append("counterexample_ratio_too_high")
    if privacy in {"blocked", "private_blocked"}:
        reasons.append("privacy_blocked")
    if scope in {"public", "global_public"} and not public_default_allowed:
        reasons.append("public_default_requires_separate_evidence")
    accepted = not reasons
    lift = min(max_lift, max(0.0, float(candidate.get("suggested_lift") or 0.05)))
    row = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "policy_id": stable_json_lines_id(
            "posture_policy",
            candidate.get("candidate_id"),
            candidate.get("relation"),
            scope,
            ensure_ascii=False,
            default_str=False,
        ),
        "candidate_id": _text(candidate.get("candidate_id")),
        "accepted": accepted,
        "policy_state": "active" if accepted else "rejected",
        "rejection_reasons": reasons,
        "relation": _text(candidate.get("relation")),
        "from_posture_id": _text(candidate.get("from_posture_id")),
        "to_posture_id": _text(candidate.get("to_posture_id")),
        "scope": scope,
        "observed_sequence_count": observed,
        "counterexample_count": counter,
        "counterexample_ratio": round(ratio, 6),
        "lift": lift if accepted else 0.0,
        "authority_level": "direction_only",
        "claim_permission": "none",
        "may_satisfy_glue": False,
        "may_transfer_fact": False,
        "foreground_eligible": False,
        "reviewable": True,
        "boundary": {
            "policy_is_scoped_attention_lift_only": True,
            "user_local_policy_is_not_public_default": scope not in {"public", "global_public"},
            "source_reopen_required_before_claim": True,
        },
    }
    return row


__all__ = ["promotion_gate"]
