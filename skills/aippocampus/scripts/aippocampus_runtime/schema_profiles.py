#!/usr/bin/env python3
"""Small schema-profile projection helpers.

These helpers intentionally do not define a universal AIppocampus schema.
They name a few surface-specific profiles and make projection/validation
explicit so rich governance or diagnostic metadata does not accidentally become
mandatory foreground recall payload.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

PROFILE_SCHEMA_VERSION = "aippocampus.schema_profile.v1"

BASE_CANNOT_CLAIM = (
    "field_completeness_is_not_product_quality",
    "wide_metadata_does_not_replace_source_reopen",
)

FIELD_ADDITION_GOVERNANCE_REQUIRED = (
    "owner",
    "consumer",
    "lifecycle",
    "privacy_classification",
    "projection_policy",
)

FOREGROUND_ACTION_CARD_REQUIRED_FIELDS = (
    "decision",
    "why",
    "next_action",
    "claim_boundary",
)

FOREGROUND_ACTION_CARD_OPTIONAL_FIELDS = (
    "route_label",
    "route_family",
    "canonical_action",
    "callable_handle",
    "callable_handle_redacted",
    "public_safe_action",
)

FOREGROUND_ACTION_CARD_AUDIT_ONLY_KEYS = (
    "attention_router_navigation",
    "cannot_claim",
    "deepen_requests",
    "feedback_calibration",
    "macro_navigation",
    "memory_packets",
    "metrics",
    "navigation_signals",
    "policy_boundary",
    "red_lines",
    "semantic_gate_diagnostics",
)


@dataclass(frozen=True)
class SchemaProfile:
    """Profile contract for one consumer surface, not a global record schema."""

    name: str
    purpose: str
    required_fields: tuple[str, ...]
    optional_fields: tuple[str, ...] = ()
    cannot_claim: tuple[str, ...] = BASE_CANNOT_CLAIM
    unknown_field_policy: str = "ignore_unless_profile_declares_mandatory"

    @property
    def projection_fields(self) -> tuple[str, ...]:
        return self.required_fields + tuple(
            field for field in self.optional_fields if field not in self.required_fields
        )


IDENTITY_MINIMAL_FIELDS = (
    "schema_version",
    "record_id",
    "source_ref",
    "content_hash_sha256",
    "created_at",
    "updated_at",
)

PROFILES: dict[str, SchemaProfile] = {
    "identity_minimal": SchemaProfile(
        name="identity_minimal",
        purpose=(
            "Stable identity and integrity fields needed to join a record back "
            "to source without carrying governance, diagnostic, or high-risk "
            "metadata."
        ),
        required_fields=IDENTITY_MINIMAL_FIELDS,
    ),
    "retrieval_runtime": SchemaProfile(
        name="retrieval_runtime",
        purpose=(
            "Small runtime projection for candidate selection and source reopen."
        ),
        required_fields=IDENTITY_MINIMAL_FIELDS,
        optional_fields=(
            "retrieval",
            "source_refs",
            "reopen_hint",
            "modality",
            "privacy_class",
        ),
    ),
    "governance_extended": SchemaProfile(
        name="governance_extended",
        purpose=(
            "Optional governance projection for authority, review, lifecycle, "
            "privacy, conflict, supersession, and signature review surfaces."
        ),
        required_fields=IDENTITY_MINIMAL_FIELDS,
        optional_fields=(
            "authority",
            "review",
            "lifecycle",
            "privacy",
            "conflict",
            "supersession",
            "signature",
            "access_policy",
        ),
    ),
    "diagnostic_metrics": SchemaProfile(
        name="diagnostic_metrics",
        purpose=(
            "Operational or benchmark metrics projection. It is explicitly not "
            "a truth or product-quality claim surface."
        ),
        required_fields=IDENTITY_MINIMAL_FIELDS + ("diagnostics",),
        optional_fields=("metrics", "cost", "latency", "roi", "benchmark"),
    ),
    "high_risk_required": SchemaProfile(
        name="high_risk_required",
        purpose=(
            "Extra fields required only when a high-risk answer gate or similar "
            "surface is active."
        ),
        required_fields=IDENTITY_MINIMAL_FIELDS
        + (
            "authority",
            "review",
            "lifecycle",
            "privacy",
            "conflict",
            "source_reopen_policy",
        ),
        optional_fields=(
            "jurisdiction_scope",
            "effective_date_scope",
            "human_review_boundary",
            "access_policy",
        ),
    ),
    "foreground_action_card": SchemaProfile(
        name="foreground_action_card",
        purpose=(
            "Tiny agent-facing action card: one decision, one reason, one next "
            "action, and one claim boundary. Rich diagnostics stay in audit "
            "surfaces."
        ),
        required_fields=FOREGROUND_ACTION_CARD_REQUIRED_FIELDS,
        optional_fields=FOREGROUND_ACTION_CARD_OPTIONAL_FIELDS,
        cannot_claim=BASE_CANNOT_CLAIM
        + (
            "foreground_card_is_not_audit_payload",
            "action_card_does_not_support_factual_claims",
        ),
    ),
}


def profile_names() -> tuple[str, ...]:
    return tuple(PROFILES)


def get_profile(profile: str | SchemaProfile) -> SchemaProfile:
    if isinstance(profile, SchemaProfile):
        return profile
    try:
        return PROFILES[profile]
    except KeyError as exc:
        raise ValueError(f"unknown schema profile: {profile}") from exc


def _nonempty(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def project_record_for_profile(
    record: Mapping[str, Any],
    profile: str | SchemaProfile,
) -> dict[str, Any]:
    """Return only the fields named by a profile, in stable profile order."""

    resolved = get_profile(profile)
    return {
        field: record[field]
        for field in resolved.projection_fields
        if field in record
    }


def validate_profile_record(
    record: Mapping[str, Any],
    profile: str | SchemaProfile,
) -> dict[str, Any]:
    """Validate profile-required fields while ignoring unrelated extensions."""

    resolved = get_profile(profile)
    missing = [
        field for field in resolved.required_fields if not _nonempty(record.get(field))
    ]
    allowed = set(resolved.projection_fields)
    extra_fields = sorted(str(field) for field in record if field not in allowed)
    error_codes = [f"missing_{field}" for field in missing]
    return {
        "ok": not missing,
        "schema_version": PROFILE_SCHEMA_VERSION,
        "profile": resolved.name,
        "purpose": resolved.purpose,
        "required_fields": list(resolved.required_fields),
        "optional_fields": list(resolved.optional_fields),
        "missing_fields": missing,
        "error_codes": error_codes,
        "extra_fields_ignored": extra_fields,
        "unknown_field_policy": resolved.unknown_field_policy,
        "cannot_claim": list(resolved.cannot_claim),
    }


def field_addition_governance_required() -> tuple[str, ...]:
    """Return the review fields required before adding durable schema fields."""

    return FIELD_ADDITION_GOVERNANCE_REQUIRED


__all__ = [
    "BASE_CANNOT_CLAIM",
    "FIELD_ADDITION_GOVERNANCE_REQUIRED",
    "FOREGROUND_ACTION_CARD_AUDIT_ONLY_KEYS",
    "FOREGROUND_ACTION_CARD_OPTIONAL_FIELDS",
    "FOREGROUND_ACTION_CARD_REQUIRED_FIELDS",
    "IDENTITY_MINIMAL_FIELDS",
    "PROFILES",
    "PROFILE_SCHEMA_VERSION",
    "SchemaProfile",
    "field_addition_governance_required",
    "get_profile",
    "profile_names",
    "project_record_for_profile",
    "validate_profile_record",
]
