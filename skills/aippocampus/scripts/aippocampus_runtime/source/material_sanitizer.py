"""Shared source-material classification for ingestion and projection edges."""

from __future__ import annotations

import hashlib
from typing import Any, Mapping

from aippocampus_runtime.source.host_internal_filter import (
    contains_host_internal_material,
)

SCHEMA_VERSION = "source-material-sanitizer-v1"


def _hash_text(value: str) -> str:
    return "ptr_" + hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()[:16]


def clean_source_material_contract() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "clean_source_policy": "visible_user_and_assistant_final_text_only",
        "host_control_envelope_policy": "audit_only_not_clean_source",
        "private_operator_detail_policy": "private_or_redacted_projection_only",
        "public_projection_policy": "metadata_counts_hashes_and_redacted_summaries",
        "source_claim_policy": "source_open_required_for_exact_claim",
        "raw_rollout_policy": "audit_source_not_default_recall_surface",
    }


def classify_source_material(
    text: str,
    *,
    source_surface: str = "unknown",
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Classify one material edge without treating wrappers as clean source.

    The contract is intentionally small and vocabulary-first. It gives import,
    clean-source, reopen, replay, and export code the same policy names, while
    still letting each surface decide how much operator detail to expose.
    """

    raw = str(text or "")
    meta = dict(metadata or {})
    host_control = contains_host_internal_material(raw)
    secret_like = any(
        marker in raw.casefold()
        for marker in ("sk-", "api_key", "secret=", "password=", "bearer ")
    )
    if host_control:
        material_class = "host_control_envelope"
        clean_policy = "exclude_from_clean_source"
        projection_policy = "redacted_metadata_only"
        claim_policy = "not_source_evidence"
    elif secret_like:
        material_class = "private_operator_detail"
        clean_policy = "exclude_from_public_projection"
        projection_policy = "hash_and_count_only"
        claim_policy = "not_source_evidence_without_private_reopen"
    else:
        material_class = "clean_source_text"
        clean_policy = "allow_if_visible_user_or_assistant_final"
        projection_policy = "allow_redacted_excerpt_with_source_scope"
        claim_policy = "source_open_required_for_exact_claim"
    return {
        "schema_version": SCHEMA_VERSION,
        "source_surface": source_surface,
        "material_class": material_class,
        "clean_source_policy": clean_policy,
        "public_projection_policy": projection_policy,
        "source_claim_policy": claim_policy,
        "metadata_policy": {
            "provider": str(meta.get("provider") or source_surface),
            "raw_local_paths_public": False,
            "raw_payload_public": False,
        },
        "public_projection": {
            "raw_text_included": False if material_class != "clean_source_text" else None,
            "material_hash": _hash_text(raw) if raw else None,
        },
    }
