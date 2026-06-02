#!/usr/bin/env python3
"""Deterministic knowledge-source manifest and claim-promotion checks."""

from __future__ import annotations

import re
from typing import Any, Mapping

SOURCE_SCHEMA_VERSION = "aippocampus.knowledge_source_manifest.v1"
CLAIM_SCHEMA_VERSION = "aippocampus.knowledge_claim.v1"
UPDATE_EVENT_SCHEMA_VERSION = "aippocampus.knowledge_update_event.v1"
REGISTRY_SCHEMA_VERSION = "aippocampus.knowledge_fixture_registry.v1"

INGEST_STATUSES = {
    "quarantined",
    "candidate",
    "review_required",
    "reviewed",
    "active",
    "retired",
    "retracted",
    "superseded",
    "rollback_available",
}
CLAIM_PROMOTION_STATUSES = {
    "candidate",
    "activated",
    "blocked",
    "rejected",
    "superseded",
    "uncertain",
}
CLAIM_REVIEW_STATUSES = {"unreviewed", "reviewed", "rejected"}
CLAIM_CONFLICT_STATUSES = {
    "none",
    "resolved",
    "unreviewed",
    "conflicted",
    "superseded",
    "uncertain",
}
CLAIM_CLEAR_CONFLICT_STATUSES = {"none", "resolved"}
UPDATE_DIFF_TYPES = {"added", "changed", "superseded", "retracted", "rollback"}
UPDATE_OLD_SOURCE_REQUIRED = {"changed", "superseded", "retracted", "rollback"}
UPDATE_NEW_SOURCE_REQUIRED = {"added", "changed", "superseded", "rollback"}
UPDATE_ROLLBACK_REQUIRED = {"changed", "superseded", "retracted", "rollback"}
LOW_CONFIDENCE_LEVELS = {"", "low", "unknown"}

ACTIVE_SOURCE_STATUSES = {"active", "reviewed"}
INACTIVE_SOURCE_STATUSES = {"retired", "retracted", "superseded"}
GENERATED_SOURCE_TYPES = {"model_generated_summary", "extracted_triples", "dream_finding"}
LOW_AUTHORITY_SOURCE_TYPES = {"low_quality_web_page", "raw_upload", "unreviewed_note"}
ACTIVATION_BLOCKING_TAINTS = {
    "generated",
    "untrusted",
    "copied_web",
    "missing_provenance",
}
SCOPED_SOURCE_TYPES = {"conversation_turn"}
HEX_64_RE = re.compile(r"^[a-fA-F0-9]{64}$")

SOURCE_BASE_REQUIRED = (
    "schema_version",
    "source_id",
    "source_type",
    "publisher",
    "authority_level",
    "ingest_status",
    "privacy_class",
)
SOURCE_HIGH_STAKES_REQUIRED = (
    "content_hash_sha256",
    "provenance_chain",
    "domain_scope",
    "jurisdiction_scope",
    "effective_date",
    "last_verified_at",
    "license",
    "access_policy",
)
CLAIM_BASE_REQUIRED = (
    "schema_version",
    "claim_id",
    "source_id",
    "source_anchor",
    "claim_text",
    "claim_scope",
    "authority_level",
    "jurisdiction_scope",
    "effective_date_scope",
    "review_status",
    "extraction_provenance",
    "promotion_status",
)
CLAIM_ACTIVATION_REQUIRED = (
    "reviewed_by",
    "review_signed_at",
    "confidence",
    "conflict_status",
)
UPDATE_EVENT_BASE_REQUIRED = (
    "schema_version",
    "event_id",
    "diff_type",
    "impact_scope",
    "requires_review",
    "created_at",
)
UPDATE_EVENT_ACTIVATION_REQUIRED = (
    "reviewer",
    "review_signed_at",
    "activated_at",
)


def _nonempty(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def _as_string_set(value: Any) -> set[str]:
    if not isinstance(value, list):
        return set()
    return {str(item) for item in value if str(item or "").strip()}


def _as_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item or "").strip()]


def _block(code: str, *, field: str, message: str) -> dict[str, str]:
    return {"code": code, "field": field, "message": message}


def _missing_blocks(payload: Mapping[str, Any], fields: tuple[str, ...]) -> list[dict[str, str]]:
    return [
        _block(f"missing_{field}", field=field, message=f"{field} is required.")
        for field in fields
        if not _nonempty(payload.get(field))
    ]


def _blocker_codes(blocks: list[dict[str, str]]) -> list[str]:
    return sorted({str(item.get("code") or "") for item in blocks if item.get("code")})


def _valid_sha256(value: Any) -> bool:
    return isinstance(value, str) and bool(HEX_64_RE.match(value))


def _source_truth_boundary(
    manifest: Mapping[str, Any],
    *,
    activation_eligible: bool,
    blockers: list[dict[str, str]],
) -> str:
    source_type = str(manifest.get("source_type") or "")
    ingest_status = str(manifest.get("ingest_status") or "")
    if ingest_status == "quarantined":
        return "quarantined"
    if ingest_status in INACTIVE_SOURCE_STATUSES or manifest.get("superseded_by"):
        return "retired_or_superseded"
    if source_type in GENERATED_SOURCE_TYPES or ingest_status in {
        "candidate",
        "review_required",
        "rollback_available",
    }:
        return "candidate_only"
    if source_type in SCOPED_SOURCE_TYPES and not any(
        item.get("code") == "source_not_active" for item in blockers
    ):
        return "scoped_source_artifact"
    if activation_eligible:
        return "active_source"
    return "candidate_only"


def validate_knowledge_source_manifest(
    manifest: Mapping[str, Any],
    *,
    high_stakes: bool = False,
) -> dict[str, Any]:
    """Validate one knowledge-source manifest and report activation eligibility.

    A quarantined or candidate source may be a valid record while still being
    ineligible to support activated high-stakes claims. That distinction keeps
    raw storage from silently becoming truth.
    """

    errors = _missing_blocks(manifest, SOURCE_BASE_REQUIRED)
    blockers: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    source_type = str(manifest.get("source_type") or "")
    ingest_status = str(manifest.get("ingest_status") or "")
    taints = _as_string_set(manifest.get("taint_labels"))

    if manifest.get("schema_version") not in {SOURCE_SCHEMA_VERSION, None, ""}:
        errors.append(
            _block(
                "unsupported_schema_version",
                field="schema_version",
                message="Unsupported knowledge source schema version.",
            )
        )
    if ingest_status and ingest_status not in INGEST_STATUSES:
        errors.append(
            _block(
                "unknown_ingest_status",
                field="ingest_status",
                message="Unknown source ingest status.",
            )
        )
    if manifest.get("content_hash_sha256") and not _valid_sha256(
        manifest.get("content_hash_sha256")
    ):
        errors.append(
            _block(
                "invalid_content_hash_sha256",
                field="content_hash_sha256",
                message="content_hash_sha256 must be a 64-character hex digest.",
            )
        )

    if high_stakes:
        for block in _missing_blocks(manifest, SOURCE_HIGH_STAKES_REQUIRED):
            blockers.append(block)
        if manifest.get("content_hash_sha256") and not _valid_sha256(
            manifest.get("content_hash_sha256")
        ):
            blockers.append(
                _block(
                    "invalid_content_hash_sha256",
                    field="content_hash_sha256",
                    message="High-stakes source manifests require a valid content hash.",
                )
            )

    if ingest_status not in ACTIVE_SOURCE_STATUSES:
        blockers.append(
            _block(
                "source_not_active",
                field="ingest_status",
                message="Only reviewed or active sources can support activated claims.",
            )
        )
    if ingest_status in INACTIVE_SOURCE_STATUSES or manifest.get("superseded_by"):
        blockers.append(
            _block(
                "source_retired_or_superseded",
                field="ingest_status",
                message="Retired, retracted, or superseded sources remain auditable but inactive.",
            )
        )
    if str(manifest.get("retracted_status") or "") not in {"", "not_retracted", "unknown"}:
        blockers.append(
            _block(
                "source_retracted",
                field="retracted_status",
                message="Retracted sources cannot support activated claims.",
            )
        )
    if source_type in GENERATED_SOURCE_TYPES:
        blockers.append(
            _block(
                "generated_source_artifact",
                field="source_type",
                message="Generated summaries or triples are navigation artifacts, not truth sources.",
            )
        )
    if source_type in LOW_AUTHORITY_SOURCE_TYPES:
        blockers.append(
            _block(
                "low_authority_source",
                field="source_type",
                message="Low-authority material must remain quarantined or candidate-only.",
            )
        )
    if taints & ACTIVATION_BLOCKING_TAINTS:
        blockers.append(
            _block(
                "tainted_source",
                field="taint_labels",
                message="Generated, untrusted, copied, or provenance-missing material is not activation eligible.",
            )
        )

    activation_eligible = not errors and not blockers
    return {
        "ok": not errors and not (
            high_stakes and ingest_status in ACTIVE_SOURCE_STATUSES and blockers
        ),
        "schema_version": SOURCE_SCHEMA_VERSION,
        "source_id": manifest.get("source_id"),
        "source_type": source_type,
        "ingest_status": ingest_status,
        "truth_boundary": _source_truth_boundary(
            manifest,
            activation_eligible=activation_eligible,
            blockers=blockers,
        ),
        "activation_eligible": activation_eligible,
        "errors": errors,
        "warnings": warnings,
        "blockers": blockers,
        "blocker_codes": _blocker_codes(blockers),
        "taint_labels": sorted(taints),
    }


def _source_anchor_has_span(anchor: Any) -> bool:
    if not isinstance(anchor, Mapping):
        return False
    if not _nonempty(anchor.get("section_anchor")) or not _nonempty(anchor.get("span_id")):
        return False
    start = anchor.get("char_start")
    end = anchor.get("char_end")
    return isinstance(start, int) and isinstance(end, int) and end > start >= 0


def _claim_exceeds_source_scope(claim: Mapping[str, Any], source: Mapping[str, Any]) -> bool:
    claim_scope = _as_string_set(claim.get("claim_scope"))
    source_scope = _as_string_set(source.get("domain_scope"))
    return bool(claim_scope and source_scope and not claim_scope.issubset(source_scope))


def _claim_exceeds_source_jurisdiction(
    claim: Mapping[str, Any],
    source: Mapping[str, Any],
) -> bool:
    claim_scope = _as_string_set(claim.get("jurisdiction_scope"))
    source_scope = _as_string_set(source.get("jurisdiction_scope"))
    return bool(claim_scope and source_scope and not claim_scope.issubset(source_scope))


def _claim_confidence_level(claim: Mapping[str, Any]) -> str:
    confidence = claim.get("confidence")
    if isinstance(confidence, Mapping):
        return str(confidence.get("level") or "").strip().lower()
    return str(confidence or "").strip().lower()


def validate_knowledge_claim(
    claim: Mapping[str, Any],
    *,
    sources: Mapping[str, Mapping[str, Any]],
    high_stakes: bool = False,
) -> dict[str, Any]:
    """Validate one claim record against source eligibility and span evidence."""

    errors = _missing_blocks(claim, CLAIM_BASE_REQUIRED)
    blockers: list[dict[str, str]] = []
    promotion_status = str(claim.get("promotion_status") or "")
    review_status = str(claim.get("review_status") or "")
    conflict_status = str(claim.get("conflict_status") or "")
    source_id = str(claim.get("source_id") or "")
    source = sources.get(source_id)

    if claim.get("schema_version") not in {CLAIM_SCHEMA_VERSION, None, ""}:
        errors.append(
            _block(
                "unsupported_schema_version",
                field="schema_version",
                message="Unsupported knowledge claim schema version.",
            )
        )
    if promotion_status and promotion_status not in CLAIM_PROMOTION_STATUSES:
        errors.append(
            _block(
                "unknown_promotion_status",
                field="promotion_status",
                message="Unknown claim promotion status.",
            )
        )
    if review_status and review_status not in CLAIM_REVIEW_STATUSES:
        errors.append(
            _block(
                "unknown_review_status",
                field="review_status",
                message="Unknown claim review status.",
            )
        )
    if conflict_status and conflict_status not in CLAIM_CONFLICT_STATUSES:
        errors.append(
            _block(
                "unknown_conflict_status",
                field="conflict_status",
                message="Unknown claim conflict status.",
            )
        )

    source_report: dict[str, Any] | None = None
    if source is None:
        blockers.append(
            _block(
                "missing_source_manifest",
                field="source_id",
                message="Claim source_id does not resolve to a manifest.",
            )
        )
    else:
        source_report = validate_knowledge_source_manifest(source, high_stakes=high_stakes)
        if promotion_status == "activated" and not source_report["activation_eligible"]:
            blockers.append(
                _block(
                    "source_not_activation_eligible",
                    field="source_id",
                    message="Activated claims require an activation-eligible source.",
                )
            )
        if _claim_exceeds_source_scope(claim, source):
            blockers.append(
                _block(
                    "claim_scope_exceeds_source_scope",
                    field="claim_scope",
                    message="Claim domain scope must stay within the source domain scope.",
                )
            )
        if _claim_exceeds_source_jurisdiction(claim, source):
            blockers.append(
                _block(
                    "claim_jurisdiction_exceeds_source_scope",
                    field="jurisdiction_scope",
                    message="Claim jurisdiction scope must stay within the source jurisdiction scope.",
                )
            )

    if promotion_status == "activated" and not _source_anchor_has_span(
        claim.get("source_anchor")
    ):
        blockers.append(
            _block(
                "missing_source_anchor_span",
                field="source_anchor",
                message="Activated claims require an assertion-level source span, not whole-document blessing.",
            )
        )
    if promotion_status == "activated":
        if high_stakes:
            blockers.extend(_missing_blocks(claim, CLAIM_ACTIVATION_REQUIRED))
        if review_status != "reviewed":
            blockers.append(
                _block(
                    "claim_not_reviewed",
                    field="review_status",
                    message="Activated claims require a reviewed status.",
                )
            )
        if conflict_status not in CLAIM_CLEAR_CONFLICT_STATUSES:
            blockers.append(
                _block(
                    "claim_conflict_not_cleared",
                    field="conflict_status",
                    message="Conflicted, uncertain, or unreviewed claims must not activate.",
                )
            )
        if claim.get("superseded_by"):
            blockers.append(
                _block(
                    "claim_superseded",
                    field="superseded_by",
                    message="Superseded claims remain auditable but cannot stay activated.",
                )
            )
        if _nonempty(claim.get("confidence")) and _claim_confidence_level(
            claim
        ) in LOW_CONFIDENCE_LEVELS:
            blockers.append(
                _block(
                    "claim_confidence_too_low",
                    field="confidence",
                    message="Activated high-stakes claims require non-low confidence.",
                )
            )

    provenance = str(claim.get("extraction_provenance") or "")
    authority = str(claim.get("authority_level") or "")
    if "model_generated" in provenance or authority == "generated_summary":
        blockers.append(
            _block(
                "generated_claim_artifact",
                field="extraction_provenance",
                message="Model-generated summaries and extracted navigation artifacts cannot activate claims.",
            )
        )

    promotion_eligible = (
        promotion_status == "activated"
        and not errors
        and not blockers
        and source_report is not None
    )
    return {
        "ok": not errors and not (promotion_status == "activated" and blockers),
        "schema_version": CLAIM_SCHEMA_VERSION,
        "claim_id": claim.get("claim_id"),
        "source_id": source_id,
        "promotion_status": promotion_status,
        "promotion_eligible": promotion_eligible,
        "truth_boundary": "activated_claim" if promotion_eligible else "candidate_or_blocked",
        "errors": errors,
        "blockers": blockers,
        "blocker_codes": _blocker_codes(blockers),
        "source_report": source_report,
    }


def validate_knowledge_update_event(
    event: Mapping[str, Any],
    *,
    sources: Mapping[str, Mapping[str, Any]],
    high_stakes: bool = False,
) -> dict[str, Any]:
    """Validate one append-only source lifecycle update event.

    An update event can be structurally valid while still being ineligible to
    activate a high-stakes source. That is intentional: automatic discovery may
    write candidate/review-required events, but review/signature policy decides
    whether a changed source becomes active truth.
    """

    errors = _missing_blocks(event, UPDATE_EVENT_BASE_REQUIRED)
    blockers: list[dict[str, str]] = []
    diff_type = str(event.get("diff_type") or "")
    old_source_id = str(event.get("old_source_id") or "")
    new_source_id = str(event.get("new_source_id") or "")
    rollback_source_id = str(event.get("rollback_source_id") or "")
    review_status = str(event.get("review_status") or "")
    requires_review = event.get("requires_review")

    if event.get("schema_version") not in {UPDATE_EVENT_SCHEMA_VERSION, None, ""}:
        errors.append(
            _block(
                "unsupported_schema_version",
                field="schema_version",
                message="Unsupported knowledge update event schema version.",
            )
        )
    if diff_type and diff_type not in UPDATE_DIFF_TYPES:
        errors.append(
            _block(
                "unknown_diff_type",
                field="diff_type",
                message="Unknown knowledge update diff type.",
            )
        )
    if not isinstance(requires_review, bool):
        errors.append(
            _block(
                "invalid_requires_review",
                field="requires_review",
                message="requires_review must be a boolean.",
            )
        )
    if "affected_claims" not in event:
        errors.append(
            _block(
                "missing_affected_claims",
                field="affected_claims",
                message="affected_claims is required, even when no claims are affected.",
            )
        )
    elif not isinstance(event.get("affected_claims"), list):
        errors.append(
            _block(
                "invalid_affected_claims",
                field="affected_claims",
                message="affected_claims must be a list of claim ids.",
            )
        )
    if review_status and review_status not in CLAIM_REVIEW_STATUSES:
        errors.append(
            _block(
                "unknown_review_status",
                field="review_status",
                message="Unknown update review status.",
            )
        )

    if diff_type in UPDATE_OLD_SOURCE_REQUIRED and not old_source_id:
        errors.append(
            _block(
                "missing_old_source_id",
                field="old_source_id",
                message="This update type requires old_source_id.",
            )
        )
    if diff_type in UPDATE_NEW_SOURCE_REQUIRED and not new_source_id:
        errors.append(
            _block(
                "missing_new_source_id",
                field="new_source_id",
                message="This update type requires new_source_id.",
            )
        )
    if diff_type in UPDATE_ROLLBACK_REQUIRED and not rollback_source_id:
        errors.append(
            _block(
                "missing_rollback_source_id",
                field="rollback_source_id",
                message="Lifecycle updates need an auditable rollback pointer.",
            )
        )

    for field, source_id in (
        ("old_source_id", old_source_id),
        ("new_source_id", new_source_id),
        ("rollback_source_id", rollback_source_id),
    ):
        if source_id and source_id not in sources:
            errors.append(
                _block(
                    f"unresolved_{field}",
                    field=field,
                    message="Update event source pointer does not resolve.",
                )
            )

    activation_requested = bool(event.get("activated_at")) or review_status == "reviewed"
    if high_stakes and requires_review is True and review_status != "reviewed":
        blockers.append(
            _block(
                "update_review_required",
                field="review_status",
                message="High-stakes updates may create candidates, but activation requires review.",
            )
        )
    if high_stakes and activation_requested:
        blockers.extend(_missing_blocks(event, UPDATE_EVENT_ACTIVATION_REQUIRED))

    new_source_report: dict[str, Any] | None = None
    if new_source_id and new_source_id in sources:
        new_source_report = validate_knowledge_source_manifest(
            sources[new_source_id],
            high_stakes=high_stakes,
        )
        if activation_requested and not new_source_report["activation_eligible"]:
            blockers.append(
                _block(
                    "new_source_not_activation_eligible",
                    field="new_source_id",
                    message="Reviewed update events cannot activate an ineligible source.",
                )
            )

    activation_eligible = not errors and not blockers and activation_requested
    return {
        "ok": not errors and not (activation_requested and blockers),
        "schema_version": UPDATE_EVENT_SCHEMA_VERSION,
        "event_id": event.get("event_id"),
        "diff_type": diff_type,
        "old_source_id": old_source_id or None,
        "new_source_id": new_source_id or None,
        "rollback_source_id": rollback_source_id or None,
        "requires_review": requires_review,
        "review_status": review_status,
        "activation_eligible": activation_eligible,
        "affected_claims": _as_string_list(event.get("affected_claims")),
        "impact_scope": _as_string_list(event.get("impact_scope")),
        "rollback_available": bool(rollback_source_id and rollback_source_id in sources),
        "errors": errors,
        "blockers": blockers,
        "blocker_codes": _blocker_codes(blockers),
        "new_source_report": new_source_report,
    }


def _source_effective_status(
    manifest: Mapping[str, Any],
    event_reports: Mapping[str, dict[str, Any]],
) -> str:
    source_id = str(manifest.get("source_id") or "")
    ingest_status = str(manifest.get("ingest_status") or "")
    if str(manifest.get("retracted_status") or "") not in {"", "not_retracted", "unknown"}:
        return "retracted"
    if manifest.get("superseded_by") or ingest_status == "superseded":
        return "superseded"
    if ingest_status == "retracted":
        return "retracted"
    for report in event_reports.values():
        if report.get("old_source_id") != source_id:
            continue
        if report.get("diff_type") == "retracted":
            return "retracted"
        if report.get("diff_type") == "superseded" and report.get("activation_eligible"):
            return "superseded"
    return ingest_status


def evaluate_knowledge_lifecycle(
    payload: Mapping[str, Any],
    *,
    high_stakes: bool = False,
) -> dict[str, Any]:
    """Project source/claim lifecycle effects without deleting old source rows."""

    sources = {
        str(item.get("source_id") or ""): item
        for item in payload.get("sources") or []
        if isinstance(item, Mapping) and item.get("source_id")
    }
    claims = {
        str(item.get("claim_id") or ""): item
        for item in payload.get("claims") or []
        if isinstance(item, Mapping) and item.get("claim_id")
    }
    event_reports = {
        str(event.get("event_id") or ""): validate_knowledge_update_event(
            event,
            sources=sources,
            high_stakes=high_stakes,
        )
        for event in payload.get("update_events") or []
        if isinstance(event, Mapping) and event.get("event_id")
    }
    source_lifecycle: dict[str, dict[str, Any]] = {}
    for source_id, source in sources.items():
        source_report = validate_knowledge_source_manifest(source, high_stakes=high_stakes)
        effective_status = _source_effective_status(source, event_reports)
        source_lifecycle[source_id] = {
            "source_id": source_id,
            "manifest_status": source.get("ingest_status"),
            "effective_status": effective_status,
            "activation_eligible": source_report["activation_eligible"]
            and effective_status in ACTIVE_SOURCE_STATUSES,
            "superseded_by": source.get("superseded_by"),
            "auditable": True,
        }

    affected_by_event: dict[str, list[str]] = {}
    for event_id, report in event_reports.items():
        for claim_id in report["affected_claims"]:
            affected_by_event.setdefault(claim_id, []).append(event_id)

    claim_lifecycle: dict[str, dict[str, Any]] = {}
    for claim_id, claim in claims.items():
        source_id = str(claim.get("source_id") or "")
        source_state = source_lifecycle.get(source_id, {})
        effective_status = str(source_state.get("effective_status") or "")
        promotion_status = str(claim.get("promotion_status") or "")
        effective_promotion_status = promotion_status
        reasons: list[str] = []

        if promotion_status == "activated" and effective_status == "superseded":
            effective_promotion_status = "superseded"
            reasons.append("source_superseded")
        elif promotion_status == "activated" and effective_status == "retracted":
            effective_promotion_status = "blocked"
            reasons.append("source_retracted")
        elif promotion_status == "activated" and not source_state.get(
            "activation_eligible",
            False,
        ):
            effective_promotion_status = "blocked"
            reasons.append("source_not_activation_eligible")

        if claim_id in affected_by_event:
            reasons.append("affected_by_update_event")

        claim_lifecycle[claim_id] = {
            "claim_id": claim_id,
            "source_id": source_id,
            "current_promotion_status": promotion_status,
            "effective_promotion_status": effective_promotion_status,
            "lifecycle_reasons": sorted(set(reasons)),
            "update_event_ids": affected_by_event.get(claim_id, []),
        }

    invalid_events = [
        event_id for event_id, report in event_reports.items() if not report["ok"]
    ]
    old_source_ids = [
        str(report.get("old_source_id") or "")
        for report in event_reports.values()
        if report.get("old_source_id")
    ]
    source_ids_preserved = sorted(source_id for source_id in sources if source_id)
    return {
        "ok": not invalid_events,
        "schema_version": UPDATE_EVENT_SCHEMA_VERSION,
        "update_event_count": len(event_reports),
        "events": event_reports,
        "sources": source_lifecycle,
        "claims": claim_lifecycle,
        "invalid_events": invalid_events,
        "old_sources_auditable": all(source_id in sources for source_id in old_source_ids),
        "source_ids_preserved": source_ids_preserved,
        "deleted_source_ids": [],
    }


def validate_knowledge_registry(
    payload: Mapping[str, Any],
    *,
    high_stakes: bool = False,
) -> dict[str, Any]:
    """Validate a public-safe registry of knowledge sources and claims."""

    sources = {
        str(item.get("source_id") or ""): item
        for item in payload.get("sources") or []
        if isinstance(item, Mapping) and item.get("source_id")
    }
    source_reports = {
        source_id: validate_knowledge_source_manifest(source, high_stakes=high_stakes)
        for source_id, source in sources.items()
    }
    claim_reports = {
        str(claim.get("claim_id") or ""): validate_knowledge_claim(
            claim,
            sources=sources,
            high_stakes=high_stakes,
        )
        for claim in payload.get("claims") or []
        if isinstance(claim, Mapping) and claim.get("claim_id")
    }
    invalid_sources = [
        source_id for source_id, report in source_reports.items() if not report["ok"]
    ]
    invalid_claims = [
        claim_id for claim_id, report in claim_reports.items() if not report["ok"]
    ]
    lifecycle_report = evaluate_knowledge_lifecycle(payload, high_stakes=high_stakes)
    return {
        "ok": not invalid_sources
        and not invalid_claims
        and not lifecycle_report["invalid_events"],
        "schema_version": REGISTRY_SCHEMA_VERSION,
        "source_count": len(source_reports),
        "claim_count": len(claim_reports),
        "update_event_count": lifecycle_report["update_event_count"],
        "sources": source_reports,
        "claims": claim_reports,
        "lifecycle": lifecycle_report,
        "invalid_sources": invalid_sources,
        "invalid_claims": invalid_claims,
        "privacy": {
            "fixture_public_safe": True,
            "private_material_allowed": False,
            "message_bodies_required": False,
        },
    }
