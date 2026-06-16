"""Source and compression fingerprint contracts for sparse provenance.

These helpers are deliberately separate from the codebook encoder so policy
checks cannot quietly become part of lookup scoring or route ranking.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

ALLOWED_LIFECYCLE_STATES = {"current", "active"}
BLOCKED_LIFECYCLE_STATES = {"deleted_no_recall", "quarantined"}
BLOCKED_PRIVACY_PARTITIONS = {"private", "quarantined", "deleted"}
SOURCE_FINGERPRINT_FIELDS = (
    "content_hash",
    "source_id",
    "privacy_partition",
    "policy_version",
    "lifecycle_state",
)
SOURCE_FINGERPRINT_OPTIONAL_FIELDS = (
    "manifest_version",
    "encoder_version",
    "retention_policy_version",
    "visibility_scope",
)
COMPRESSION_FINGERPRINT_FIELDS = (
    "template_id",
    "schema_version",
    "residual_policy_id",
    "redaction_policy_version",
    "mask_policy_version",
    "visibility_scope",
    "encoder_version",
    "codec_id",
    "codec_version",
    "dictionary_id",
    "dictionary_training_scope",
    "dictionary_privacy_partition",
    "dictionary_redaction_policy_version",
    "source_family",
)
COMPRESSION_DERIVED_ARTIFACT_FIELDS = (
    "artifact_id",
    "artifact_kind",
    "source_family",
    "privacy_partition",
    "visibility_scope",
    "lifecycle_state",
    "codec_id",
    "encoder_version",
    "dictionary_id",
    "template_id",
    "residual_policy_id",
    "redaction_policy_version",
    "mask_policy_version",
)
COMPRESSION_PUBLIC_PROJECTION_ALLOWLIST = (
    "artifact_id",
    "artifact_kind",
    "source_family",
    "privacy_partition",
    "visibility_scope",
    "lifecycle_state",
    "codec_id",
    "codec_version",
    "encoder_version",
    "dictionary_id",
    "dictionary_byte_length",
    "dictionary_training_scope",
    "dictionary_privacy_partition",
    "dictionary_redaction_policy_version",
    "template_id",
    "template_count",
    "residual_policy_id",
    "residual_bytes",
    "chunk_id_hash",
    "route_handle_hash",
    "proof_anchor_hash",
)


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _entry_allowed(entry: Mapping[str, Any]) -> bool:
    lifecycle_state = str(entry.get("lifecycle_state") or "")
    privacy_partition = str(entry.get("privacy_partition") or "")
    return (
        lifecycle_state in ALLOWED_LIFECYCLE_STATES
        and lifecycle_state not in BLOCKED_LIFECYCLE_STATES
        and privacy_partition not in BLOCKED_PRIVACY_PARTITIONS
    )


def compression_artifact_contract_report() -> dict[str, Any]:
    return {
        "kind": "aippocampus_compression_artifact_contract",
        "schema_version": "compression-artifact-contract-v1",
        "artifact_kinds": [
            "zstd_dictionary",
            "template",
            "residual_chunk",
            "route_handle",
            "chunk_id",
            "proof_anchor",
            "manifest_integrity_anchor",
        ],
        "required_metadata_fields": sorted(
            set(COMPRESSION_DERIVED_ARTIFACT_FIELDS) | set(COMPRESSION_FINGERPRINT_FIELDS)
        ),
        "public_projection_allowlist": list(COMPRESSION_PUBLIC_PROJECTION_ALLOWLIST),
        "blocked_public_fields": [
            "raw_dictionary_bytes",
            "raw_residual",
            "raw_payload",
            "raw_source_text",
            "private_handle",
            "local_path",
            "token_like_string",
            "proof_material_sufficient_to_reconstruct_masked_slots",
        ],
        "reuse_boundary": {
            "cross_privacy_partition_dictionary_reuse": "blocked",
            "cross_privacy_partition_residual_reuse": "blocked",
            "stale_redaction_policy_reuse": "blocked",
            "source_family_mismatch_reuse": "blocked",
        },
        "enforced_by": {
            "fingerprint_verifier": "#1893",
            "negative_controls": "#1894",
            "source_family_economics": "#1891/#1896",
        },
        "authority": "navigation_only_derived_artifact_not_source_truth",
    }


def verify_source_fingerprint_reuse(
    cached: Mapping[str, Any],
    current: Mapping[str, Any],
) -> dict[str, Any]:
    cached_payload = _mapping(cached.get("source_fingerprint_payload") or cached)
    current_payload = _mapping(current.get("source_fingerprint_payload") or current)
    reason_codes: list[str] = []
    for field in SOURCE_FINGERPRINT_FIELDS:
        if not cached_payload.get(field) or not current_payload.get(field):
            reason_codes.append(f"missing_{field}")
        elif cached_payload.get(field) != current_payload.get(field):
            reason_codes.append(f"{field}_mismatch")
    for field in SOURCE_FINGERPRINT_OPTIONAL_FIELDS:
        cached_value = cached_payload.get(field)
        current_value = current_payload.get(field)
        if cached_value and current_value and cached_value != current_value:
            reason_codes.append(f"{field}_mismatch")
    compression_contract_markers = tuple(
        field
        for field in COMPRESSION_FINGERPRINT_FIELDS
        if field not in {"visibility_scope", "encoder_version"}
    )
    compression_contract_present = any(
        field in cached_payload or field in current_payload for field in compression_contract_markers
    )
    if compression_contract_present:
        for field in COMPRESSION_FINGERPRINT_FIELDS:
            cached_value = cached_payload.get(field)
            current_value = current_payload.get(field)
            if not cached_value or not current_value:
                reason_codes.append(f"missing_{field}")
            elif cached_value != current_value:
                reason_codes.append(f"{field}_mismatch")
    current_state = {
        "lifecycle_state": current_payload.get("lifecycle_state"),
        "privacy_partition": current_payload.get("privacy_partition"),
    }
    blocked = not _entry_allowed(current_state)
    if blocked:
        reason_codes.append("privacy_or_lifecycle_blocked")
    if not reason_codes:
        decision = "accept_navigation_reuse"
        status = "verified_present"
    elif blocked:
        decision = "reject_cached_reuse"
        status = "verified_present_but_blocked"
    else:
        decision = "reject_cached_reuse"
        status = "cannot_verify"
    feedback_state = str(cached.get("feedback_state") or current.get("feedback_state") or "")
    feedback_refs = cached.get("feedback_source_refs") or current.get("feedback_source_refs") or []
    return {
        "kind": "aippocampus_source_fingerprint_reuse_verification",
        "status": status,
        "decision": decision,
        "reason_codes": reason_codes or ["source_fingerprint_matches_current_policy"],
        "required_fields": list(SOURCE_FINGERPRINT_FIELDS),
        "optional_fields_checked": list(SOURCE_FINGERPRINT_OPTIONAL_FIELDS),
        "compression_fields_checked": list(COMPRESSION_FINGERPRINT_FIELDS),
        "compression_contract_present": compression_contract_present,
        "deterministic_hot_path": True,
        "external_model_calls": 0,
        "action_grammar": "reopenable_route" if decision == "accept_navigation_reuse" else "direction_only",
        "cache_output_is_not_evidence": True,
        "source_reopen_required_before_claim": True,
        "feedback_state": {
            "state": feedback_state or "none",
            "authority": "source_backed" if feedback_refs else "unverified_agent_report",
            "can_raise_source_authority": bool(feedback_refs),
        },
        "red_line_counters": {
            "privacy_bypass_count": 0,
            "masked_source_resurrection_count": 0,
            "source_backed_claim_without_reopen": 0,
            "stale_as_current_count": 0,
            "fingerprint_rejected_reuse": 1 if decision != "accept_navigation_reuse" else 0,
            "verifier_timeout_or_cannot_verify": 1 if status == "cannot_verify" else 0,
        },
    }
