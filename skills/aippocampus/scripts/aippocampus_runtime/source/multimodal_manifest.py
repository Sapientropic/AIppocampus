#!/usr/bin/env python3
"""Multimodal source manifest and media-origin policy validation.

This module owns the #541 contract boundary only. It validates source records,
media-origin policy, and derived-artifact provenance; it does not index media,
call providers, generate captions, or turn derived artifacts into source truth.
"""

from __future__ import annotations

import re
from typing import Any, Mapping, Sequence

from aippocampus_runtime.core import dict_or_empty, schema_block, schema_blocker_codes

REGISTRY_SCHEMA_VERSION = "aippocampus.multimodal_source_registry.v1"
SOURCE_SCHEMA_VERSION = "aippocampus.multimodal_source.v1"
DERIVED_ARTIFACT_SCHEMA_VERSION = "aippocampus.multimodal_derived_artifact.v1"

MEDIA_TYPES = {
    "image",
    "video_frame",
    "video_segment",
    "email_message",
    "chat_message",
    "receipt",
    "invoice",
    "calendar_event",
    "document_page",
}
SOURCE_TYPES = {
    "raw_image",
    "raw_video_frame",
    "raw_video_segment",
    "email_message",
    "conversation_turn",
    "receipt_image",
    "invoice_document",
    "calendar_event",
    "document_page",
}
MEDIA_ORIGIN_POLICIES = {
    "user_provided_media",
    "connected_library_media",
    "background_filesystem_media",
}
DERIVED_ARTIFACT_TYPES = {
    "asr",
    "caption",
    "entity_tag",
    "ocr",
    "perceptual_hash",
    "schema_row",
    "thumbnail",
    "visual_embedding",
}
SOURCE_REQUIRED_FIELDS = (
    "schema_version",
    "source_id",
    "source_type",
    "media_type",
    "origin_policy",
    "privacy_class",
    "source_owner",
    "access_policy",
    "license",
    "captured_at",
    "timezone",
    "content_hash_sha256",
    "source_anchor",
    "task_scoped_access",
    "provenance_chain",
)
DERIVED_REQUIRED_FIELDS = (
    "schema_version",
    "artifact_id",
    "artifact_type",
    "parent_source_id",
    "parent_anchor_id",
    "source_anchor",
    "provider_route",
    "model_id",
    "confidence",
    "created_at",
    "authority",
    "output_artifacts",
    "provenance_chain",
)
HEX_64_RE = re.compile(r"^[a-fA-F0-9]{64}$")

MEDIA_ORIGIN_POLICY = {
    "user_provided_media": {
        "current_task_access_allowed": True,
        "configured_scope_required": False,
        "default_access_denied": False,
        "hidden_durable_write_allowed": False,
        "cross_domain_reuse_allowed": False,
        "audit_event_required": True,
        "user_visible_confirmation_required": False,
    },
    "connected_library_media": {
        "current_task_access_allowed": False,
        "configured_scope_required": True,
        "default_access_denied": False,
        "hidden_durable_write_allowed": False,
        "cross_domain_reuse_allowed": False,
        "audit_event_required": True,
        "user_visible_confirmation_required": True,
    },
    "background_filesystem_media": {
        "current_task_access_allowed": False,
        "configured_scope_required": True,
        "default_access_denied": True,
        "hidden_durable_write_allowed": False,
        "cross_domain_reuse_allowed": False,
        "audit_event_required": True,
        "user_visible_confirmation_required": True,
    },
}


def _nonempty(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def _report_key(value: Any, *, prefix: str, index: int) -> str:
    identifier = str(value or "")
    return identifier if identifier else f"<missing-{prefix}-{index}>"


def _missing_blocks(
    payload: Mapping[str, Any],
    fields: Sequence[str],
    *,
    prefix: str,
) -> list[dict[str, str]]:
    return [
        schema_block(
            f"{prefix}_missing_{field}",
            field=field,
            message=f"{field} is required.",
        )
        for field in fields
        if not _nonempty(payload.get(field))
    ]


def _valid_sha256(value: Any) -> bool:
    return isinstance(value, str) and bool(HEX_64_RE.match(value))


def _source_anchor_id(source: Mapping[str, Any]) -> str:
    return str(dict_or_empty(source.get("source_anchor")).get("anchor_id") or "")


def _source_report(source: Mapping[str, Any]) -> dict[str, Any]:
    blockers = _missing_blocks(source, SOURCE_REQUIRED_FIELDS, prefix="source")
    schema_version = str(source.get("schema_version") or "")
    source_id = str(source.get("source_id") or "")
    source_type = str(source.get("source_type") or "")
    media_type = str(source.get("media_type") or "")
    origin_policy = str(source.get("origin_policy") or "")
    access_policy = str(source.get("access_policy") or "")
    anchor = dict_or_empty(source.get("source_anchor"))
    task_access = dict_or_empty(source.get("task_scoped_access"))

    if schema_version != SOURCE_SCHEMA_VERSION:
        blockers.append(
            schema_block(
                "source_unsupported_schema_version",
                field="schema_version",
                message="Unsupported multimodal source schema version.",
            )
        )
    if source_type and source_type not in SOURCE_TYPES:
        blockers.append(
            schema_block(
                "source_unknown_source_type",
                field="source_type",
                message="Unknown multimodal source type.",
            )
        )
    if media_type and media_type not in MEDIA_TYPES:
        blockers.append(
            schema_block(
                "source_unknown_media_type",
                field="media_type",
                message="Unknown multimodal media type.",
            )
        )
    if origin_policy and origin_policy not in MEDIA_ORIGIN_POLICIES:
        blockers.append(
            schema_block(
                "source_unknown_origin_policy",
                field="origin_policy",
                message="Unknown media-origin policy.",
            )
        )
    if source.get("content_hash_sha256") and not _valid_sha256(
        source.get("content_hash_sha256")
    ):
        blockers.append(
            schema_block(
                "source_invalid_content_hash_sha256",
                field="content_hash_sha256",
                message="content_hash_sha256 must be a 64-character hex digest.",
            )
        )
    if not anchor.get("anchor_id"):
        blockers.append(
            schema_block(
                "source_missing_anchor",
                field="source_anchor.anchor_id",
                message="Original multimodal sources require a reopenable source anchor.",
            )
        )
    if not isinstance(source.get("provenance_chain"), list):
        blockers.append(
            schema_block(
                "source_invalid_provenance_chain",
                field="provenance_chain",
                message="provenance_chain must be a list.",
            )
        )

    current_task_access = task_access.get("current_task_access_allowed") is True
    configured_scope_required = task_access.get("configured_scope_required") is True
    hidden_durable_write_allowed = task_access.get("hidden_durable_write_allowed") is True
    cross_domain_reuse_allowed = task_access.get("cross_domain_reuse_allowed") is True
    audit_event_required = task_access.get("audit_event_required") is True
    origin_policy_contract = MEDIA_ORIGIN_POLICY.get(origin_policy, {})
    user_visible_confirmation_required = bool(
        origin_policy_contract.get("user_visible_confirmation_required")
    )

    if origin_policy == "user_provided_media" and not current_task_access:
        blockers.append(
            schema_block(
                "user_provided_media_current_task_not_allowed",
                field="task_scoped_access.current_task_access_allowed",
                message="User-provided media should be usable for the current task.",
            )
        )
    if origin_policy == "connected_library_media":
        if not configured_scope_required or not task_access.get("configured_scope_id"):
            blockers.append(
                schema_block(
                    "connected_media_scope_not_configured",
                    field="task_scoped_access.configured_scope_id",
                    message="Connected libraries require a configured scope before access.",
                )
            )
    if origin_policy == "background_filesystem_media":
        if current_task_access or access_policy != "denied_by_default":
            blockers.append(
                schema_block(
                    "background_media_default_access_not_denied",
                    field="task_scoped_access.current_task_access_allowed",
                    message="Unselected background media must be denied by default.",
                )
            )
    if hidden_durable_write_allowed:
        blockers.append(
            schema_block(
                "hidden_durable_write_allowed",
                field="task_scoped_access.hidden_durable_write_allowed",
                message="Task-scoped media access must not silently create durable memories.",
            )
        )
    if cross_domain_reuse_allowed:
        blockers.append(
            schema_block(
                "cross_domain_reuse_allowed",
                field="task_scoped_access.cross_domain_reuse_allowed",
                message="Task-scoped media access does not grant cross-domain reuse.",
            )
        )
    if not audit_event_required:
        blockers.append(
            schema_block(
                "source_audit_event_not_required",
                field="task_scoped_access.audit_event_required",
                message="Multimodal source access should leave an auditable policy decision.",
            )
        )

    return {
        "ok": not blockers,
        "source_id": source_id,
        "source_type": source_type,
        "media_type": media_type,
        "origin_policy": origin_policy,
        "privacy_class": source.get("privacy_class"),
        "anchor_id": anchor.get("anchor_id"),
        "truth_source": True,
        "derived_artifact_authority": "not_applicable",
        "current_task_access_allowed": current_task_access,
        "configured_scope_required": configured_scope_required,
        "hidden_durable_write_allowed": hidden_durable_write_allowed,
        "cross_domain_reuse_allowed": cross_domain_reuse_allowed,
        "audit_event_required": audit_event_required,
        "user_visible_confirmation_required": user_visible_confirmation_required,
        "blockers": blockers,
        "blocker_codes": schema_blocker_codes(blockers),
    }


def _derived_artifact_report(
    artifact: Mapping[str, Any],
    *,
    sources: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    blockers = _missing_blocks(artifact, DERIVED_REQUIRED_FIELDS, prefix="derived_artifact")
    artifact_id = str(artifact.get("artifact_id") or "")
    artifact_type = str(artifact.get("artifact_type") or "")
    parent_source_id = str(artifact.get("parent_source_id") or "")
    parent_source = sources.get(parent_source_id)
    parent_anchor_id = str(artifact.get("parent_anchor_id") or "")
    parent_source_anchor_id = _source_anchor_id(parent_source or {})
    anchor = dict_or_empty(artifact.get("source_anchor"))

    if artifact.get("schema_version") != DERIVED_ARTIFACT_SCHEMA_VERSION:
        blockers.append(
            schema_block(
                "derived_artifact_unsupported_schema_version",
                field="schema_version",
                message="Unsupported derived artifact schema version.",
            )
        )
    if artifact_type and artifact_type not in DERIVED_ARTIFACT_TYPES:
        blockers.append(
            schema_block(
                "derived_artifact_unknown_type",
                field="artifact_type",
                message="Unknown multimodal derived artifact type.",
            )
        )
    if parent_source is None:
        blockers.append(
            schema_block(
                "derived_artifact_unknown_parent_source",
                field="parent_source_id",
                message="Derived artifacts must point at a known original source.",
            )
        )
    elif not parent_source_anchor_id or parent_anchor_id != parent_source_anchor_id:
        blockers.append(
            schema_block(
                "derived_artifact_parent_anchor_mismatch",
                field="parent_anchor_id",
                message="Derived artifacts must reopen through the parent source anchor.",
            )
        )
    if not anchor.get("anchor_id"):
        blockers.append(
            schema_block(
                "derived_artifact_missing_anchor",
                field="source_anchor.anchor_id",
                message="Derived artifacts need their own artifact anchor.",
            )
        )
    if artifact.get("authority") != "navigation_only":
        blockers.append(
            schema_block(
                "derived_artifact_not_navigation_only",
                field="authority",
                message="Derived captions/OCR/tags/schema rows are route hints, not truth.",
            )
        )
    if not isinstance(artifact.get("output_artifacts"), list):
        blockers.append(
            schema_block(
                "derived_artifact_invalid_output_artifacts",
                field="output_artifacts",
                message="output_artifacts must be a list.",
            )
        )
    if not isinstance(artifact.get("provenance_chain"), list):
        blockers.append(
            schema_block(
                "derived_artifact_invalid_provenance_chain",
                field="provenance_chain",
                message="provenance_chain must be a list.",
            )
        )

    parent_anchor_resolved = parent_source is not None and parent_anchor_id == parent_source_anchor_id
    return {
        "ok": not blockers,
        "artifact_id": artifact_id,
        "artifact_type": artifact_type,
        "parent_source_id": parent_source_id,
        "parent_source_resolved": parent_source is not None,
        "parent_anchor_id": parent_anchor_id,
        "parent_anchor_resolved": parent_anchor_resolved,
        "provider_route": artifact.get("provider_route"),
        "model_id": artifact.get("model_id"),
        "authority": artifact.get("authority"),
        "truth_source": False,
        "blockers": blockers,
        "blocker_codes": schema_blocker_codes(blockers),
    }


def validate_multimodal_source_registry(registry: Mapping[str, Any]) -> dict[str, Any]:
    """Validate a multimodal source registry without indexing or reading media."""

    blockers: list[dict[str, str]] = []
    if registry.get("schema_version") != REGISTRY_SCHEMA_VERSION:
        blockers.append(
            schema_block(
                "registry_unsupported_schema_version",
                field="schema_version",
                message="Unsupported multimodal source registry schema version.",
            )
        )
    boundary = dict_or_empty(registry.get("boundary"))
    if boundary.get("derived_artifacts_are_navigation_only") is not True:
        blockers.append(
            schema_block(
                "registry_missing_navigation_boundary",
                field="boundary.derived_artifacts_are_navigation_only",
                message="Registry must declare derived artifacts as navigation only.",
            )
        )

    raw_sources = registry.get("sources") or []
    sources_list = [item for item in raw_sources if isinstance(item, Mapping)]
    source_ids = [str(item.get("source_id") or "") for item in sources_list]
    duplicates = sorted(
        {
            source_id
            for source_id in source_ids
            if source_id and source_ids.count(source_id) > 1
        }
    )
    if duplicates:
        blockers.append(
            schema_block(
                "registry_duplicate_source_id",
                field="sources.source_id",
                message="Multimodal source ids must be unique.",
            )
        )
    sources_by_id = {
        str(item.get("source_id") or ""): item
        for item in sources_list
        if item.get("source_id")
    }
    source_reports_list = [_source_report(source) for source in sources_list]
    source_reports = {
        _report_key(report.get("source_id"), prefix="source", index=index): report
        for index, report in enumerate(source_reports_list)
    }

    raw_derived_artifacts = registry.get("derived_artifacts") or []
    derived_artifacts_list = [
        item for item in raw_derived_artifacts if isinstance(item, Mapping)
    ]
    artifact_ids = [
        str(item.get("artifact_id") or "") for item in derived_artifacts_list
    ]
    duplicate_artifact_ids = sorted(
        {
            artifact_id
            for artifact_id in artifact_ids
            if artifact_id and artifact_ids.count(artifact_id) > 1
        }
    )
    if duplicate_artifact_ids:
        blockers.append(
            schema_block(
                "registry_duplicate_derived_artifact_id",
                field="derived_artifacts.artifact_id",
                message="Multimodal derived artifact ids must be unique.",
            )
        )
    derived_reports_list = [
        _derived_artifact_report(item, sources=sources_by_id)
        for item in derived_artifacts_list
    ]
    derived_reports = {
        _report_key(report.get("artifact_id"), prefix="derived-artifact", index=index): report
        for index, report in enumerate(derived_reports_list)
    }

    for report in source_reports.values():
        blockers.extend(report["blockers"])
    for report in derived_reports.values():
        blockers.extend(report["blockers"])

    return {
        "ok": not blockers,
        "schema_version": REGISTRY_SCHEMA_VERSION,
        "registry_id": registry.get("registry_id"),
        "source_count": len(source_reports),
        "derived_artifact_count": len(derived_reports),
        "source_ids": sorted(source_reports),
        "source_media_types": sorted({report["media_type"] for report in source_reports.values()}),
        "media_origin_policies": sorted(
            {report["origin_policy"] for report in source_reports.values()}
        ),
        "sources": source_reports,
        "derived_artifacts": derived_reports,
        "media_origin_policy": MEDIA_ORIGIN_POLICY,
        "truth_boundary": {
            "original_sources_are_truth_boundary": True,
            "derived_artifacts_are_navigation_only": True,
            "source_reopen_required_for_visual_or_document_claims": True,
            "task_scoped_access_is_not_durable_memory_consent": True,
        },
        "privacy_boundary": {
            "fixture_public_safe": bool(boundary.get("fixture_public_safe")),
            "raw_private_media_included": bool(boundary.get("raw_private_media_included")),
            "hidden_durable_write_allowed": False,
            "cross_domain_reuse_allowed": False,
            "background_filesystem_media_default_denied": True,
        },
        "blockers": blockers,
        "blocker_codes": schema_blocker_codes(blockers),
    }
