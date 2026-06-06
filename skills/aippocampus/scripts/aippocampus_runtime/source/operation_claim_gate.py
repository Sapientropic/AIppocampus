#!/usr/bin/env python3
"""Gate strong operation claims through critical-operation integrity reports."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from aippocampus_runtime.recall.authority import with_trust_fields

SCHEMA_VERSION = 1

ALLOW_SOURCE_BACKED_CLAIM = "allow_source_backed_claim"
DOWNGRADE_TO_CANDIDATE = "downgrade_to_candidate"
REQUIRE_SOURCE_REOPEN = "require_source_reopen"
BLOCK_PUBLIC_CLAIM = "block_public_claim"
CONFLICT_REQUIRES_REVIEW = "conflict_requires_review"

STRONG_SUPPORT_LEVELS = {
    "advisory",
    "bounded_evidence",
    "evidence",
    "source_backed",
    "source_backed_claim",
}
FACT_JOIN_FIELDS = (
    "event_id",
    "source_ref",
    "call_ref",
    "source_id",
    "source_line",
    "raw_start_line",
    "raw_end_line",
    "turn_index",
)


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _family_report(report: Mapping[str, Any], family: str) -> Mapping[str, Any]:
    for item in report.get("families") or []:
        if isinstance(item, Mapping) and item.get("family") == family:
            return item
    return {}


def _claim_join_keys(
    *,
    event_id: str | None,
    source_ref: str | None,
    call_ref: str | None,
    join_keys: Mapping[str, Any] | None,
) -> dict[str, Any]:
    keys: dict[str, Any] = {}
    if event_id:
        keys["event_id"] = event_id
    if source_ref:
        keys["source_ref"] = source_ref
    if call_ref:
        keys["call_ref"] = call_ref
    for key, value in _mapping(join_keys).items():
        if key in FACT_JOIN_FIELDS and value not in (None, "", []):
            keys[str(key)] = value
    return keys


def _fact_matches(fact: Mapping[str, Any], claim_keys: Mapping[str, Any]) -> bool:
    if not claim_keys:
        return False
    # Strong operation claims must join to one concrete fact. Do not relax this
    # to any-key matching: a reused event id with a mismatched call ref would
    # otherwise be promoted to source-backed wording.
    return all(fact.get(key) == value for key, value in claim_keys.items())


def _matched_facts(
    family_report: Mapping[str, Any],
    claim_keys: Mapping[str, Any],
) -> list[Mapping[str, Any]]:
    facts = [fact for fact in family_report.get("facts") or [] if isinstance(fact, Mapping)]
    return [fact for fact in facts if _fact_matches(fact, claim_keys)]


def _fact_refs(facts: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    seen: set[tuple[tuple[str, str], ...]] = set()
    for fact in facts:
        ref = {
            key: fact.get(key)
            for key in FACT_JOIN_FIELDS
            if fact.get(key) not in (None, "", [])
        }
        if not ref:
            continue
        marker = tuple(sorted((str(key), str(value)) for key, value in ref.items()))
        if marker in seen:
            continue
        seen.add(marker)
        refs.append(ref)
    return refs


def _privacy_issue_affects_claim(
    report: Mapping[str, Any],
    *,
    claim_event_id: str | None,
    matched_facts: list[Mapping[str, Any]],
) -> bool:
    issues = _mapping(report.get("privacy")).get("issues") or []
    fact_event_ids = {
        str(fact.get("event_id"))
        for fact in matched_facts
        if fact.get("event_id") not in (None, "", [])
    }
    if claim_event_id:
        fact_event_ids.add(str(claim_event_id))
    for issue in issues:
        if not isinstance(issue, Mapping):
            continue
        event_id = issue.get("event_id")
        if event_id == "unknown" or (event_id is not None and str(event_id) in fact_event_ids):
            return True
    return False


def _conflict_affects_claim(
    report: Mapping[str, Any],
    *,
    family: str,
    claim_keys: Mapping[str, Any],
    matched_facts: list[Mapping[str, Any]],
) -> bool:
    matched_event_ids = {
        str(fact.get("event_id"))
        for fact in matched_facts
        if fact.get("event_id") not in (None, "", [])
    }
    for conflict in report.get("conflicts") or []:
        if not isinstance(conflict, Mapping) or conflict.get("family") != family:
            continue
        if not claim_keys:
            return True
        if conflict.get("event_id") and conflict.get("event_id") == claim_keys.get("event_id"):
            return True
        if conflict.get("call_ref") and conflict.get("call_ref") == claim_keys.get("call_ref"):
            return True
        conflict_event_ids = {str(item) for item in conflict.get("event_ids") or []}
        if matched_event_ids & conflict_event_ids:
            return True
    return False


def _surface_for_decision(
    *,
    decision: str,
    support_level: str,
    source_refs: list[dict[str, Any]],
    source_reopen_required: bool,
    reason_codes: list[str],
) -> dict[str, Any]:
    surface: dict[str, Any] = {
        "support_level": support_level,
        "source_refs": source_refs,
        "source_reopen_required": source_reopen_required,
    }
    if decision == ALLOW_SOURCE_BACKED_CLAIM:
        surface.update(
            {
                "evidence_level": "source_backed",
                "source_boundary": {"operation_integrity_covered": True},
            }
        )
    elif decision == REQUIRE_SOURCE_REOPEN:
        surface.update(
            {
                "route": "reopen",
                "reopen_plan": {"status": "ready" if source_refs else "blocked"},
            }
        )
    elif decision in {BLOCK_PUBLIC_CLAIM, CONFLICT_REQUIRES_REVIEW}:
        surface.update(
            {
                "route": "ignore",
                "visibility": "blocked",
                "conflict_flags": reason_codes,
            }
        )
    return with_trust_fields(surface)


def _decision_payload(
    *,
    report: Mapping[str, Any],
    family: str,
    decision: str,
    support_level: str,
    reason_codes: list[str],
    source_refs: list[dict[str, Any]],
    matched_fact_count: int,
    intended_support_level: str,
    public_claim: bool,
    source_reopen_required: bool,
) -> dict[str, Any]:
    surface = _surface_for_decision(
        decision=decision,
        support_level=support_level,
        source_refs=source_refs,
        source_reopen_required=source_reopen_required,
        reason_codes=reason_codes,
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "decision": decision,
        "family": family,
        "requested_support_level": intended_support_level,
        "public_claim": public_claim,
        "support_level": surface.get("support_level"),
        "trust_level": surface.get("trust_level"),
        "action_grammar": surface.get("action_grammar"),
        "trust_contract": surface.get("trust_contract"),
        "source_reopen_required": bool(surface.get("source_reopen_required")),
        "ordinary_recall_allowed": bool(report.get("ordinary_recall_allowed", True)),
        "matched_fact_count": matched_fact_count,
        "matched_fact_refs": source_refs,
        "reason_codes": reason_codes,
    }


def evaluate_operation_claim(
    integrity_report: Mapping[str, Any],
    *,
    family: str,
    event_id: str | None = None,
    source_ref: str | None = None,
    call_ref: str | None = None,
    join_keys: Mapping[str, Any] | None = None,
    intended_support_level: str = "evidence",
    public_claim: bool = True,
) -> dict[str, Any]:
    """Return a small machine-readable decision for a proposed operation claim."""

    report = _mapping(integrity_report)
    family_report = _family_report(report, family)
    claim_keys = _claim_join_keys(
        event_id=event_id,
        source_ref=source_ref,
        call_ref=call_ref,
        join_keys=join_keys,
    )
    matched = _matched_facts(family_report, claim_keys)
    refs = _fact_refs(matched)
    family_status = str(family_report.get("status") or "missing")
    requested = str(intended_support_level or "evidence").casefold()
    strong_claim = requested in STRONG_SUPPORT_LEVELS

    if not family_report:
        return _decision_payload(
            report=report,
            family=family,
            decision=REQUIRE_SOURCE_REOPEN,
            support_level="source_required",
            reason_codes=["family_report_missing"],
            source_refs=[],
            matched_fact_count=0,
            intended_support_level=requested,
            public_claim=public_claim,
            source_reopen_required=True,
        )

    if public_claim and strong_claim and _privacy_issue_affects_claim(
        report, claim_event_id=event_id, matched_facts=matched
    ):
        return _decision_payload(
            report=report,
            family=family,
            decision=BLOCK_PUBLIC_CLAIM,
            support_level="suppressed",
            reason_codes=["privacy_issue_affects_claim"],
            source_refs=refs,
            matched_fact_count=len(matched),
            intended_support_level=requested,
            public_claim=public_claim,
            source_reopen_required=True,
        )

    if strong_claim and _conflict_affects_claim(
        report, family=family, claim_keys=claim_keys, matched_facts=matched
    ):
        return _decision_payload(
            report=report,
            family=family,
            decision=CONFLICT_REQUIRES_REVIEW,
            support_level="suppressed",
            reason_codes=["conflict_affects_claim"],
            source_refs=refs,
            matched_fact_count=len(matched),
            intended_support_level=requested,
            public_claim=public_claim,
            source_reopen_required=True,
        )

    if family_status == "missing":
        return _decision_payload(
            report=report,
            family=family,
            decision=DOWNGRADE_TO_CANDIDATE,
            support_level="candidate",
            reason_codes=["family_missing"],
            source_refs=[],
            matched_fact_count=0,
            intended_support_level=requested,
            public_claim=public_claim,
            source_reopen_required=True,
        )
    if family_status == "partial":
        return _decision_payload(
            report=report,
            family=family,
            decision=REQUIRE_SOURCE_REOPEN,
            support_level="source_required",
            reason_codes=["family_partial"],
            source_refs=refs,
            matched_fact_count=len(matched),
            intended_support_level=requested,
            public_claim=public_claim,
            source_reopen_required=True,
        )
    if family_status == "weak_covered":
        return _decision_payload(
            report=report,
            family=family,
            decision=REQUIRE_SOURCE_REOPEN,
            support_level="source_required",
            reason_codes=["family_weak_covered"],
            source_refs=refs,
            matched_fact_count=len(matched),
            intended_support_level=requested,
            public_claim=public_claim,
            source_reopen_required=True,
        )
    if not claim_keys or not matched:
        return _decision_payload(
            report=report,
            family=family,
            decision=DOWNGRADE_TO_CANDIDATE,
            support_level="candidate",
            reason_codes=["claim_not_joined_to_fact"],
            source_refs=[],
            matched_fact_count=0,
            intended_support_level=requested,
            public_claim=public_claim,
            source_reopen_required=True,
        )
    return _decision_payload(
        report=report,
        family=family,
        decision=ALLOW_SOURCE_BACKED_CLAIM,
        support_level="evidence",
        reason_codes=["covered_fact_joined"],
        source_refs=refs,
        matched_fact_count=len(matched),
        intended_support_level=requested,
        public_claim=public_claim,
        source_reopen_required=False,
    )
