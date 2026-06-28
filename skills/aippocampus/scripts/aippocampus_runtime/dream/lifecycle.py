#!/usr/bin/env python3
"""Visible lifecycle projection for Dream hypotheses.

Dream findings move through several private/background shapes before they are
safe to mention to a foreground agent. This module gives status/report surfaces
one vocabulary without promoting model text into fact: examples are structural
summaries only, and every non-adjudicated surface remains navigation-only.

Lifecycle owner contract:

candidate -> adjudicate -> deliver -> age/trust-horizon check ->
compact/dead-letter -> optional rederive/review.

Only source-ref adjudicated rows may deliver as working-memory hypotheses, and
even those are route material rather than source truth. Compaction preserves
hash/provenance counts as a tombstone; it does not delete clean source, reopen
source, or keep raw hypothesis payload foreground-eligible. Review-due,
expired, corrected, evidence-requested, or exact-quote use must reopen or
confirm source before shaping claims.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
from datetime import datetime, timezone
from typing import Any

from aippocampus_runtime.source.io_kernel import parse_utc, source_ref_key

DREAM_HYPOTHESIS_TYPE = "dream_hypothesis"

LIFECYCLE_STATES = (
    "candidate",
    "parked_with_reason",
    "speculative_navigation_hypothesis",
    "adjudicated_source_ref_hypothesis",
    "expired",
    "refuted",
    "ignored",
    "payload_compacted",
)

ADJUDICATED_REVIEW_STATES = frozenset({
    "accepted",
    "approved",
    "reviewed",
    "agent_adjudicated",
    "auto_adjudicated",
    "source_adjudicated",
})

PUBLIC_AUTHORITY_SOURCE_EVIDENCE = "source_evidence"
PUBLIC_AUTHORITY_ADJUDICATED_HYPOTHESIS = "adjudicated_hypothesis"
PUBLIC_AUTHORITY_AMBIENT_HINT = "ambient_hint"
PUBLIC_AUTHORITY_DIAGNOSTIC_ONLY = "diagnostic_only"

DELIVERY_ADJUDICATED_HYPOTHESIS_ROUTE = "adjudicated_hypothesis_route"
DELIVERY_REOPENABLE_ROUTE = "reopenable_route"
DELIVERY_NEEDS_REOPEN_CHECK = "needs_reopen_check"
DELIVERY_NEEDS_CONFIRMATION = "needs_confirmation"
DELIVERY_UNRESOLVED_SOURCE = "unresolved_source"
DELIVERY_DIRECTION_ONLY = "direction_only"
DELIVERY_DIAGNOSTIC_ONLY = "diagnostic_only"

SPECULATIVE_SOURCE_AUDIT_STATUSES = {
    "model_candidate_source_ref_validated",
    "clean_source_refs_present",
    "passed",
}

FAILED_CHECK_REASONS = {
    "source_refs_present": "source refs are missing or unresolved",
    "source_ref_audit": "source-ref audit failed",
    "bridge_claims_source_refs": "bridge claims do not carry source refs",
    "source_pack_ready": "source pack is not ready for Dream review",
    "source_pack_overlap": "finding source refs do not overlap the source pack",
    "confidence_floor": "confidence floor was not met",
    "sensitive_use_gate": "sensitive or profile-like claim needs human/context review",
}


def _now(now: str | datetime | None = None) -> datetime:
    if isinstance(now, datetime):
        return now.astimezone(timezone.utc)
    return parse_utc(now) or datetime.now(timezone.utc)


def _source_refs(value: object) -> list[Mapping[str, Any]]:
    if isinstance(value, Mapping):
        raw: Iterable[object] = [value]
    elif isinstance(value, Iterable) and not isinstance(value, (str, bytes)):
        raw = value
    else:
        raw = []
    refs: list[Mapping[str, Any]] = []
    for item in raw:
        if isinstance(item, Mapping) and any(source_ref_key(item)):
            refs.append(item)
    return refs


def _source_thread_count(refs: Iterable[Mapping[str, Any]]) -> int:
    return len(
        {
            str(ref.get("thread_key") or ref.get("thread_id") or "")
            for ref in refs
            if ref.get("thread_key") or ref.get("thread_id")
        }
    )


def _bridge_claim_count(row: Mapping[str, Any]) -> int:
    return sum(1 for item in row.get("bridge_claims") or [] if isinstance(item, Mapping))


def _adjudication_result(row: Mapping[str, Any]) -> Mapping[str, Any]:
    value = row.get("adjudication_result") or {}
    return value if isinstance(value, Mapping) else {}


def _retrospective_policy(row: Mapping[str, Any]) -> Mapping[str, Any]:
    value = row.get("retrospective_policy") or {}
    return value if isinstance(value, Mapping) else {}


def _status(row: Mapping[str, Any]) -> str:
    return str(
        row.get("lifecycle_state")
        or row.get("lifecycle_status")
        or row.get("status")
        or ""
    ).strip()


def _review_state(row: Mapping[str, Any]) -> str:
    return str(row.get("review_state") or "").strip()


def is_adjudicated_review_state(value: object) -> bool:
    return str(value or "").strip() in ADJUDICATED_REVIEW_STATES


def _source_ref_audit(row: Mapping[str, Any]) -> Mapping[str, Any]:
    value = row.get("source_ref_audit") or {}
    return value if isinstance(value, Mapping) else {}


def failed_check_reason_code(failed_checks: Iterable[object]) -> str:
    reasons = [str(item) for item in failed_checks if str(item or "").strip()]
    return "+".join(reasons) if reasons else "parked_for_review"


def readable_parked_reason(failed_checks: Iterable[object]) -> str:
    reasons = [
        FAILED_CHECK_REASONS.get(str(item), str(item).replace("_", " "))
        for item in failed_checks
        if str(item or "").strip()
    ]
    if not reasons:
        return "parked pending review before any foreground use"
    return "; ".join(reasons[:3])


def next_review_or_cleanup(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "path": "review_source_refs_or_cleanup_if_unreachable",
        "review_after": row.get("review_after") or row.get("expires_or_review_after"),
        "cleanup_after": row.get("expires_at"),
        "commands": [
            "aippocampus dream status --json",
            "python -m aippocampus_runtime.dream.retrospective_lifecycle --summary --json",
        ],
    }


def _expired(row: Mapping[str, Any], *, now: str | datetime | None = None) -> bool:
    expires_at = parse_utc(row.get("expires_at"))
    return bool(expires_at and expires_at <= _now(now))


def trust_horizon_map(row: Mapping[str, Any]) -> Mapping[str, Any]:
    horizon = row.get("trust_horizon") or {}
    return horizon if isinstance(horizon, Mapping) else {}


def trust_horizon_timestamps(row: Mapping[str, Any], key: str) -> list[datetime]:
    horizon = trust_horizon_map(row)
    timestamps: list[datetime] = []
    for value in (row.get(key), horizon.get(key)):
        parsed = parse_utc(str(value or ""))
        if parsed:
            timestamps.append(parsed)
    return timestamps


def dream_hypothesis_expired(
    row: Mapping[str, Any],
    *,
    now: str | datetime | None = None,
) -> bool:
    now_dt = _now(now)
    return any(expires_at <= now_dt for expires_at in trust_horizon_timestamps(row, "expires_at"))


def trust_horizon_status(
    row: Mapping[str, Any],
    *,
    now: str | datetime | None = None,
) -> str:
    now_dt = _now(now)
    if any(expires_at <= now_dt for expires_at in trust_horizon_timestamps(row, "expires_at")):
        return "expired"
    if any(review_after <= now_dt for review_after in trust_horizon_timestamps(row, "review_after")):
        return "review_due"
    return "valid"


def _source_ref_count(row: Mapping[str, Any]) -> int:
    return len(_source_refs(row.get("source_refs")))


def public_authority_tier(row: Mapping[str, Any]) -> str:
    """Return the compact public tier a foreground agent may act on.

    This is deliberately coarser than internal review/source diagnostics. It
    answers the product question "can this shape an answer, only a route, or
    nothing yet?" without serializing source refs into compact output.
    """

    support = str(row.get("support_level") or "").casefold()
    action = str(row.get("action_grammar") or "").casefold()
    status = str(row.get("status") or "").casefold()
    if (
        support == "evidence"
        or action in {"bounded_evidence", "source_open"}
        or row.get("evidence_level") == "source_backed"
    ):
        return PUBLIC_AUTHORITY_SOURCE_EVIDENCE
    if row.get("payload_compacted") or status in {"payload_compacted", "parked", "refuted"}:
        return PUBLIC_AUTHORITY_DIAGNOSTIC_ONLY
    if str(row.get("candidate_type") or "") == DREAM_HYPOTHESIS_TYPE:
        if (
            is_adjudicated_review_state(row.get("review_state"))
            and _source_ref_count(row) > 0
            and not (row.get("sensitive_use_gate") or {}).get("state") == "blocked"
            and not row.get("human_review_required")
        ):
            return PUBLIC_AUTHORITY_ADJUDICATED_HYPOTHESIS
        return PUBLIC_AUTHORITY_DIAGNOSTIC_ONLY
    if str(row.get("route") or "") in {"use_with_source", "confirm_when_relevant"} and (
        _source_ref_count(row) > 0 or int(row.get("source_ref_count") or 0) > 0
    ):
        return PUBLIC_AUTHORITY_ADJUDICATED_HYPOTHESIS
    if action in {"ignore_or_blocked"}:
        return PUBLIC_AUTHORITY_DIAGNOSTIC_ONLY
    return PUBLIC_AUTHORITY_AMBIENT_HINT


def delivery_cues_from_prompt(prompt: str) -> dict[str, bool]:
    text = str(prompt or "").casefold()
    return {
        "user_requested_evidence": any(
            marker in text
            for marker in (
                "证据",
                "出处",
                "evidence",
                "证明",
                "依据",
                "原文",
                "source?",
                "source please",
            )
        ),
        "exact_or_quote_claim": any(
            marker in text
            for marker in (
                "原话",
                "原句",
                "逐字",
                "quote",
                "exact",
                "verbatim",
                "引用",
            )
        ),
        "user_correction_visible": any(
            marker in text
            for marker in (
                "不对",
                "错了",
                "纠正",
                "correction",
                "wrong",
            )
        ),
    }


def working_memory_delivery_posture(
    row: Mapping[str, Any],
    *,
    prompt: str = "",
    route_relevance: bool | None = None,
    source_visible: bool = False,
    exact_or_quote_claim: bool | None = None,
    user_requested_evidence: bool | None = None,
    user_correction_visible: bool | None = None,
    contradiction_visible: bool = False,
    sensitive_claim: bool = False,
    strong_user_facing_claim: bool = False,
    source_fingerprint_current: str | None = None,
    now: str | datetime | None = None,
) -> dict[str, Any]:
    """Plan compact delivery posture without reopening source in the hot path."""

    cues = delivery_cues_from_prompt(prompt)
    exact = cues["exact_or_quote_claim"] if exact_or_quote_claim is None else exact_or_quote_claim
    requested = (
        cues["user_requested_evidence"]
        if user_requested_evidence is None
        else user_requested_evidence
    )
    corrected = (
        cues["user_correction_visible"]
        if user_correction_visible is None
        else user_correction_visible
    )
    ref_count = _source_ref_count(row)
    tier = public_authority_tier(row)
    state = dream_lifecycle_state(row, now=now)
    trust_status = trust_horizon_status(row, now=now)
    if row.get("payload_compacted") or state in {"refuted", "ignored", "payload_compacted"}:
        posture = DELIVERY_DIAGNOSTIC_ONLY
        next_action = "leave_out_of_foreground_or_rederive_from_source"
        reason = "compacted_refuted_or_ignored"
    elif ref_count <= 0:
        posture = DELIVERY_UNRESOLVED_SOURCE
        next_action = "search_or_deepen_before_use"
        reason = "missing_or_unresolved_source_refs"
    elif str(row.get("candidate_type") or "") == DREAM_HYPOTHESIS_TYPE:
        if not is_adjudicated_review_state(row.get("review_state")):
            posture = DELIVERY_DIAGNOSTIC_ONLY
            next_action = "review_before_foreground_use"
            reason = "not_adjudicated"
        elif (row.get("sensitive_use_gate") or {}).get("state") == "blocked" or row.get("human_review_required"):
            posture = DELIVERY_DIAGNOSTIC_ONLY
            next_action = "human_or_user_review_before_use"
            reason = "sensitive_review_required"
        elif source_visible:
            posture = DELIVERY_DIRECTION_ONLY
            next_action = "stay_silent_source_already_visible"
            reason = "source_already_visible"
        elif corrected:
            posture = DELIVERY_NEEDS_CONFIRMATION
            next_action = "ask_user_to_confirm_or_reopen_source"
            reason = "user_correction_requires_confirmation"
        elif (
            trust_status in {"expired", "review_due"}
            or bool(source_fingerprint_current)
            and source_fingerprint_current
            != str(row.get("source_fingerprint") or trust_horizon_map(row).get("source_fingerprint") or "")
            or contradiction_visible
            or requested
            or exact
            or sensitive_claim
            or strong_user_facing_claim
        ):
            posture = DELIVERY_NEEDS_REOPEN_CHECK
            next_action = "reopen_source_before_use"
            if trust_status == "expired":
                reason = "trust_horizon_expired"
            elif trust_status == "review_due":
                reason = "trust_horizon_review_due"
            elif requested:
                reason = "user_requested_evidence"
            elif exact:
                reason = "exact_or_quote_claim"
            elif contradiction_visible:
                reason = "contradiction_visible"
            elif sensitive_claim:
                reason = "sensitive_claim"
            elif strong_user_facing_claim:
                reason = "strong_claim"
            else:
                reason = "source_fingerprint_changed"
        elif route_relevance is False:
            posture = DELIVERY_DIRECTION_ONLY
            next_action = "stay_silent_until_relevant"
            reason = "no_route_relevance"
        else:
            posture = DELIVERY_ADJUDICATED_HYPOTHESIS_ROUTE
            next_action = "use_as_route_reopen_before_claim"
            reason = "adjudicated_hypothesis_can_seed_route"
    elif str(row.get("route") or "") == "use_with_source":
        posture = DELIVERY_REOPENABLE_ROUTE
        next_action = "reopen_source_before_claim"
        reason = "source_ref_backed_working_memory_route"
    else:
        posture = DELIVERY_DIRECTION_ONLY
        next_action = "use_as_direction_only"
        reason = "ambient_or_silent_working_memory"
    return {
        "public_authority_tier": tier,
        "delivery_source_posture": posture,
        "delivery_next_action": next_action,
        "reason": reason,
        "source_ref_count": ref_count,
        "trust_horizon_status": trust_status if str(row.get("candidate_type") or "") == DREAM_HYPOTHESIS_TYPE else None,
        "raw_source_refs_emitted": False,
        "source_open_performed": False,
    }


def dream_lifecycle_state(row: Mapping[str, Any], *, now: str | datetime | None = None) -> str:
    explicit = _status(row)
    if explicit in LIFECYCLE_STATES:
        return explicit
    retrospective = str(_retrospective_policy(row).get("status") or "")
    if retrospective in {"refuted", "ignored", "expired"}:
        return retrospective
    if retrospective == "stale" or explicit in {"stale", "dropped", "drop_low_pressure"}:
        return "ignored"
    if explicit in {"refuted", "model_refuted"}:
        return "refuted"
    if _expired(row, now=now):
        return "expired"
    adjudication = _adjudication_result(row)
    adjudication_status = str(adjudication.get("status") or "")
    if adjudication_status == "parked" or explicit in {"parked", "parked_pending_review"}:
        return "parked_with_reason"
    if (
        adjudication_status == "accepted"
        or _review_state(row) in ADJUDICATED_REVIEW_STATES
        or explicit in {"accepted", "retained_for_review"}
    ):
        return "adjudicated_source_ref_hypothesis"
    audit_status = str(_source_ref_audit(row).get("status") or "")
    validation = row.get("worker_validation") or {}
    validation_status = str(validation.get("status") or "") if isinstance(validation, Mapping) else ""
    if (
        audit_status in SPECULATIVE_SOURCE_AUDIT_STATUSES
        or validation_status == "passed"
        or row.get("support_level") == "candidate"
    ) and _source_refs(row.get("source_refs")):
        return "speculative_navigation_hypothesis"
    return "candidate"


def dream_lifecycle_record(
    row: Mapping[str, Any],
    *,
    now: str | datetime | None = None,
) -> dict[str, Any]:
    state = dream_lifecycle_state(row, now=now)
    refs = _source_refs(row.get("source_refs"))
    adjudication = _adjudication_result(row)
    failed_checks = [
        *([str(item) for item in adjudication.get("failed_checks") or []]),
        *([str(item) for item in _source_ref_audit(row).get("failed_checks") or []]),
    ]
    reason_code = failed_check_reason_code(failed_checks)
    navigation_only = state != "adjudicated_source_ref_hypothesis"
    fact_claim_allowed = False
    record = {
        "state": state,
        "reason_code": reason_code if state == "parked_with_reason" else state,
        "readable_reason": readable_parked_reason(failed_checks)
        if state == "parked_with_reason"
        else _readable_state_reason(state),
        "next_review_or_cleanup": next_review_or_cleanup(row)
        if state == "parked_with_reason"
        else _next_action_for_state(state, row),
        "navigation_only": navigation_only,
        "fact_claim_allowed": fact_claim_allowed,
        "foreground_eligible": False,
        "source_ref_count": len(refs),
        "source_thread_count": _source_thread_count(refs),
        "bridge_claim_count": _bridge_claim_count(row),
        "claim_boundary": _claim_boundary_for_state(state),
    }
    return record


def _readable_state_reason(state: str) -> str:
    return {
        "candidate": "candidate is awaiting source-ref review",
        "speculative_navigation_hypothesis": "source-shaped candidate can orient navigation only",
        "adjudicated_source_ref_hypothesis": "source-ref adjudicated hypothesis may seed routes, not factual claims",
        "expired": "review or expiry horizon has passed",
        "refuted": "later targeted evidence refuted the hypothesis",
        "ignored": "low-value or stale hypothesis should stay out of foreground use",
    }.get(state, "inspect Dream lifecycle status")


def _next_action_for_state(state: str, row: Mapping[str, Any]) -> dict[str, Any]:
    if state == "adjudicated_source_ref_hypothesis":
        return {
            "path": "use_as_route_then_reopen_source_before_claim",
            "review_after": row.get("review_after"),
            "cleanup_after": row.get("expires_at"),
        }
    if state == "speculative_navigation_hypothesis":
        return {
            "path": "keep_navigation_only_until_source_adjudication",
            "review_after": row.get("review_after"),
            "cleanup_after": row.get("expires_at"),
        }
    if state in {"expired", "refuted", "ignored"}:
        return {
            "path": "leave_out_of_working_memory_or_archive",
            "review_after": row.get("review_after"),
            "cleanup_after": row.get("expires_at"),
        }
    return {
        "path": "run_background_source_ref_adjudication",
        "review_after": row.get("review_after"),
        "cleanup_after": row.get("expires_at"),
    }


def _claim_boundary_for_state(state: str) -> str:
    if state == "adjudicated_source_ref_hypothesis":
        return "adjudicated_hypothesis_not_fact_reopen_source_before_claim"
    if state == "speculative_navigation_hypothesis":
        return "navigation_only_until_source_adjudicated"
    if state == "parked_with_reason":
        return "parked_no_foreground_use_until_review"
    return "dream_candidate_not_source_truth"


def example_safe_summary(row: Mapping[str, Any], record: Mapping[str, Any]) -> str:
    function = str(row.get("dream_function") or "dream").replace("_", " ")
    candidate_kind = str(row.get("candidate_kind") or row.get("candidate_type") or "hypothesis").replace("_", " ")
    refs = int(record.get("source_ref_count") or 0)
    bridges = int(record.get("bridge_claim_count") or 0)
    state = str(record.get("state") or "candidate").replace("_", " ")
    return (
        f"{function} {candidate_kind}; {state}; {refs} source refs; "
        f"{bridges} bridge claims; reopen source before claims."
    )


def dream_lifecycle_report(
    rows: Iterable[Mapping[str, Any]],
    *,
    now: str | datetime | None = None,
    example_limit: int = 5,
) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    counts: Counter[str] = Counter({state: 0 for state in LIFECYCLE_STATES})
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        record = dream_lifecycle_record(row, now=now)
        state = str(record["state"])
        counts[state] += 1
        if len(records) < max(0, int(example_limit)):
            records.append(
                {
                    "state": state,
                    "reason_code": record.get("reason_code"),
                    "example_safe_summary": example_safe_summary(row, record),
                    "next_review_or_cleanup": record.get("next_review_or_cleanup"),
                    "claim_boundary": record.get("claim_boundary"),
                    "fact_claim_allowed": False,
                    "foreground_eligible": False,
                }
            )
    return {
        "kind": "aippocampus_dream_lifecycle_report",
        "counts": dict(counts),
        "examples": records,
        "privacy": {
            "example_summaries_omit_raw_text": True,
            "source_handles_omitted": True,
            "raw_candidate_text_omitted": True,
        },
        "claim_boundary": "dream_lifecycle_reports_are_navigation_and_status_not_source_truth",
    }


def navigation_surface_for_finding(row: Mapping[str, Any]) -> dict[str, Any]:
    record = dream_lifecycle_record(row)
    return {
        "surface_kind": "dream_navigation_hypothesis",
        "lifecycle_state": record["state"],
        "navigation_only": True,
        "fact_claim_allowed": False,
        "foreground_eligible": False,
        "claim_boundary": "navigation_only_until_source_adjudicated"
        if record["state"] == "speculative_navigation_hypothesis"
        else record["claim_boundary"],
        "example_safe_summary": example_safe_summary(row, record),
        "next_action": record["next_review_or_cleanup"]["path"],
    }
