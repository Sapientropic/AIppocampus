#!/usr/bin/env python3
"""Multimodal provider capability routing contract.

This module owns the #542 static routing boundary. It decides whether a
declared provider route is allowed for a requested modality and media-origin
policy. It does not call providers, inspect media bytes, or treat derived
artifacts as source truth.
"""

from __future__ import annotations

import hashlib
from typing import Any, Mapping, Sequence

from aippocampus_runtime.source import multimodal_manifest

PROVIDER_ROUTE_SCHEMA_VERSION = "aippocampus.multimodal_provider_routes.v1"

INPUT_MODALITIES = {"text", "image", "video", "audio", "document"}
INPUT_KINDS = {"raw_media", "derived_text"}
EXECUTION_LOCATIONS = {"local_runtime", "external_provider", "host_provided"}
OUTPUT_ARTIFACTS = multimodal_manifest.DERIVED_ARTIFACT_TYPES | {
    "entity_candidates",
    "line_item_candidates",
    "text_summary",
}
ROUTE_REQUIRED_FIELDS = (
    "route_id",
    "provider",
    "model_id",
    "input_modalities",
    "output_artifacts",
    "output_authority",
    "execution_location",
    "external_provider",
    "privacy_policy",
    "media_origin_allowances",
    "capability_contract",
)
CASE_REQUIRED_FIELDS = (
    "case_id",
    "route_id",
    "input_kind",
    "media_type",
    "origin_policy",
    "task_scoped_access",
)
MEDIA_MODALITY = {
    "image": "image",
    "video_frame": "video",
    "video_segment": "video",
    "email_message": "text",
    "chat_message": "text",
    "receipt": "image",
    "invoice": "document",
    "calendar_event": "text",
    "document_page": "document",
}


def _as_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value] if value.strip() else []
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item or "").strip()]


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _block(code: str, *, field: str, message: str) -> dict[str, str]:
    return {"code": code, "field": field, "message": message}


def _blocker_codes(blockers: Sequence[Mapping[str, str]]) -> list[str]:
    return sorted({str(item.get("code") or "") for item in blockers if item.get("code")})


def _missing_required_blocks(
    payload: Mapping[str, Any],
    fields: Sequence[str],
    *,
    prefix: str,
) -> list[dict[str, str]]:
    return [
        _block(
            f"{prefix}_missing_{field}",
            field=field,
            message=f"{field} is required for multimodal provider routing.",
        )
        for field in fields
        if payload.get(field) in (None, "", [], {})
    ]


def _routes(manifest: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return [item for item in manifest.get("routes") or [] if isinstance(item, Mapping)]


def _cases(manifest: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return [item for item in manifest.get("cases") or [] if isinstance(item, Mapping)]


def _route_by_id(manifest: Mapping[str, Any], route_id: str) -> Mapping[str, Any] | None:
    for route in _routes(manifest):
        if str(route.get("route_id") or "") == route_id:
            return route
    return None


def _case_by_id(manifest: Mapping[str, Any], case_id: str) -> Mapping[str, Any] | None:
    for case in _cases(manifest):
        if str(case.get("case_id") or "") == case_id:
            return case
    return None


def _required_modality(case: Mapping[str, Any]) -> str:
    if str(case.get("input_kind") or "") == "derived_text":
        return "text"
    return MEDIA_MODALITY.get(str(case.get("media_type") or ""), "")


def _sha1_text(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:16]


def _validate_route(route: Mapping[str, Any]) -> list[dict[str, str]]:
    blockers = _missing_required_blocks(route, ROUTE_REQUIRED_FIELDS, prefix="route")
    input_modalities = set(_as_list(route.get("input_modalities")))
    output_artifacts = set(_as_list(route.get("output_artifacts")))
    if input_modalities and not input_modalities.issubset(INPUT_MODALITIES):
        blockers.append(
            _block(
                "route_unknown_input_modality",
                field="input_modalities",
                message="Provider route input modalities must come from the #542 taxonomy.",
            )
        )
    if output_artifacts and not output_artifacts.issubset(OUTPUT_ARTIFACTS):
        blockers.append(
            _block(
                "route_unknown_output_artifact",
                field="output_artifacts",
                message="Provider route output artifacts must be declared navigation artifacts.",
            )
        )
    if route.get("output_authority") != "navigation_only":
        blockers.append(
            _block(
                "route_output_not_navigation_only",
                field="output_authority",
                message="OCR/caption/tag/schema outputs are navigation artifacts, not source truth.",
            )
        )
    if str(route.get("execution_location") or "") not in EXECUTION_LOCATIONS:
        blockers.append(
            _block(
                "route_unknown_execution_location",
                field="execution_location",
                message="Provider route execution_location is outside the #542 taxonomy.",
            )
        )
    if not isinstance(route.get("external_provider"), bool):
        blockers.append(
            _block(
                "route_invalid_external_provider",
                field="external_provider",
                message="external_provider must be a boolean.",
            )
        )
    privacy = _as_mapping(route.get("privacy_policy"))
    if privacy.get("local_path_export_allowed") is True:
        blockers.append(
            _block(
                "route_allows_local_path_export",
                field="privacy_policy.local_path_export_allowed",
                message="Provider route reports must not export local paths.",
            )
        )
    allowances = _as_mapping(route.get("media_origin_allowances"))
    for origin_policy in multimodal_manifest.MEDIA_ORIGIN_POLICIES:
        if origin_policy not in allowances:
            blockers.append(
                _block(
                    "route_missing_media_origin_policy",
                    field=f"media_origin_allowances.{origin_policy}",
                    message="Provider routes must make every media-origin decision explicit.",
                )
            )
    return blockers


def validate_provider_route_manifest(manifest: Mapping[str, Any]) -> dict[str, Any]:
    """Validate route declarations without selecting or calling a provider."""

    blockers: list[dict[str, str]] = []
    if manifest.get("schema_version") != PROVIDER_ROUTE_SCHEMA_VERSION:
        blockers.append(
            _block(
                "manifest_unsupported_schema_version",
                field="schema_version",
                message="Unsupported multimodal provider route schema version.",
            )
        )
    routes = _routes(manifest)
    route_ids = [str(route.get("route_id") or "") for route in routes]
    duplicate_route_ids = sorted(
        {route_id for route_id in route_ids if route_id and route_ids.count(route_id) > 1}
    )
    if duplicate_route_ids:
        blockers.append(
            _block(
                "manifest_duplicate_route_id",
                field="routes.route_id",
                message="Provider route ids must be unique.",
            )
        )
    for route in routes:
        blockers.extend(_validate_route(route))
    return {
        "ok": not blockers,
        "schema_version": PROVIDER_ROUTE_SCHEMA_VERSION,
        "route_count": len(routes),
        "route_ids": sorted(route_id for route_id in route_ids if route_id),
        "input_modalities": sorted(
            {modality for route in routes for modality in _as_list(route.get("input_modalities"))}
        ),
        "output_artifacts": sorted(
            {artifact for route in routes for artifact in _as_list(route.get("output_artifacts"))}
        ),
        "truth_boundary": {
            "derived_outputs_are_navigation_only": True,
            "raw_media_routes_do_not_create_source_truth": True,
            "provider_route_contract_is_not_live_provider_quality": True,
        },
        "blockers": blockers,
        "blocker_codes": _blocker_codes(blockers),
    }


def _case_policy_blocks(
    *,
    route: Mapping[str, Any],
    case: Mapping[str, Any],
) -> list[dict[str, str]]:
    blockers = _missing_required_blocks(case, CASE_REQUIRED_FIELDS, prefix="case")
    input_kind = str(case.get("input_kind") or "")
    media_type = str(case.get("media_type") or "")
    origin_policy = str(case.get("origin_policy") or "")
    task_access = _as_mapping(case.get("task_scoped_access"))
    route_modalities = set(_as_list(route.get("input_modalities")))
    required_modality = _required_modality(case)
    allowances = _as_mapping(route.get("media_origin_allowances"))
    allowance = _as_mapping(allowances.get(origin_policy))

    if input_kind and input_kind not in INPUT_KINDS:
        blockers.append(
            _block(
                "case_unknown_input_kind",
                field="input_kind",
                message="Provider route cases must use raw_media or derived_text.",
            )
        )
    if media_type and media_type not in multimodal_manifest.MEDIA_TYPES:
        blockers.append(
            _block(
                "case_unknown_media_type",
                field="media_type",
                message="Provider route case media_type must be a multimodal source media type.",
            )
        )
    if required_modality and required_modality not in route_modalities:
        blockers.append(
            _block(
                "provider_route_missing_required_modality",
                field="input_modalities",
                message="Selected provider route lacks the required input modality.",
            )
        )
    if origin_policy and origin_policy not in multimodal_manifest.MEDIA_ORIGIN_POLICIES:
        blockers.append(
            _block(
                "case_unknown_origin_policy",
                field="origin_policy",
                message="Provider route case uses an unknown media-origin policy.",
            )
        )
    if not allowance:
        blockers.append(
            _block(
                "media_origin_policy_not_allowed",
                field="media_origin_allowances",
                message="Selected route has no policy allowance for this media origin.",
            )
        )
    if input_kind == "raw_media" and not allowance.get("raw_media_allowed"):
        blockers.append(
            _block(
                "raw_media_not_allowed_by_route",
                field="media_origin_allowances.raw_media_allowed",
                message="Selected route may not consume raw media for this origin.",
            )
        )
    if input_kind == "derived_text" and not allowance.get("derived_text_allowed"):
        blockers.append(
            _block(
                "derived_text_not_allowed_by_route",
                field="media_origin_allowances.derived_text_allowed",
                message="Selected route may not consume derived text for this origin.",
            )
        )
    if origin_policy == "user_provided_media" and not task_access.get(
        "current_task_access_allowed"
    ):
        blockers.append(
            _block(
                "user_media_current_task_not_allowed",
                field="task_scoped_access.current_task_access_allowed",
                message="User-provided media must be selected for the current task.",
            )
        )
    if origin_policy == "connected_library_media" and allowance.get(
        "configured_scope_required"
    ) and not task_access.get("configured_scope_id"):
        blockers.append(
            _block(
                "connected_media_scope_not_configured",
                field="task_scoped_access.configured_scope_id",
                message="Connected media needs an explicit configured scope.",
            )
        )
    if origin_policy == "background_filesystem_media" and allowance.get(
        "denied_by_default",
        True,
    ):
        blockers.append(
            _block(
                "background_media_denied_by_default",
                field="origin_policy",
                message="Background filesystem media is denied until explicitly selected.",
            )
        )
    for field, code in (
        ("hidden_durable_write_allowed", "hidden_durable_write_allowed"),
        ("cross_domain_reuse_allowed", "cross_domain_reuse_allowed"),
    ):
        if task_access.get(field) is True:
            blockers.append(
                _block(
                    code,
                    field=f"task_scoped_access.{field}",
                    message="Task-scoped media routing must not broaden future memory use.",
                )
            )
    return blockers


def evaluate_provider_route_case(
    manifest: Mapping[str, Any],
    *,
    case_id: str,
) -> dict[str, Any]:
    """Evaluate one public-safe provider route case and return a sanitized report."""

    manifest_report = validate_provider_route_manifest(manifest)
    case = _case_by_id(manifest, case_id)
    if case is None:
        blockers = [
            _block(
                "missing_provider_route_case",
                field="case_id",
                message="Provider route case id does not exist.",
            )
        ]
        route: Mapping[str, Any] = {}
    else:
        route = _route_by_id(manifest, str(case.get("route_id") or "")) or {}
        blockers = [] if route else [
            _block(
                "provider_route_missing",
                field="route_id",
                message="Provider route id does not exist.",
            )
        ]
        if route:
            blockers.extend(_case_policy_blocks(route=route, case=case))
    if not manifest_report["ok"]:
        blockers.extend(manifest_report["blockers"])

    input_kind = str((case or {}).get("input_kind") or "")
    task_access = _as_mapping((case or {}).get("task_scoped_access"))
    raw_prompt = str((case or {}).get("raw_prompt_text") or "")
    derived_text = input_kind == "derived_text"
    allowed = not blockers
    cannot_claim = _as_list((case or {}).get("cannot_claim"))
    if derived_text:
        cannot_claim.append("derived_text_is_navigation_only")
    if str(route.get("output_authority") or "") == "navigation_only":
        cannot_claim.append("provider_output_is_navigation_only")
    return {
        "case_id": case_id,
        "route_id": route.get("route_id") or (case or {}).get("route_id"),
        "provider_id": route.get("provider"),
        "model_id_sha1": _sha1_text(str(route.get("model_id") or ""))
        if route.get("model_id")
        else None,
        "input_kind": input_kind,
        "media_type": (case or {}).get("media_type"),
        "required_modality": _required_modality(case or {}),
        "origin_policy": (case or {}).get("origin_policy"),
        "current_task_access_allowed": task_access.get("current_task_access_allowed") is True,
        "hidden_durable_write_allowed": task_access.get("hidden_durable_write_allowed") is True,
        "cross_domain_reuse_allowed": task_access.get("cross_domain_reuse_allowed") is True,
        "allowed": allowed,
        "can_claim_source_truth": False,
        "output_artifacts": _as_list(route.get("output_artifacts")),
        "output_authority": route.get("output_authority"),
        "blockers": blockers,
        "blocker_codes": _blocker_codes(blockers),
        "cannot_claim": sorted(set(cannot_claim)),
        "raw_media_bytes_exported": False,
        "raw_prompt_text_exported": False,
        "input_sha1": _sha1_text(raw_prompt) if raw_prompt else None,
        "policy_decision": "allow" if allowed else "block",
    }


def run_provider_route_smoke(manifest: Mapping[str, Any]) -> dict[str, Any]:
    """Run all embedded public-safe provider route cases."""

    manifest_report = validate_provider_route_manifest(manifest)
    cases = [
        evaluate_provider_route_case(manifest, case_id=str(case.get("case_id") or ""))
        for case in _cases(manifest)
        if case.get("case_id")
    ]
    expected = {
        str(case.get("case_id") or ""): bool(case.get("expected_allowed"))
        for case in _cases(manifest)
        if case.get("case_id")
    }
    expectation_failures = [
        case
        for case in cases
        if str(case.get("case_id") or "") in expected
        and bool(case.get("allowed")) is not expected[str(case.get("case_id") or "")]
    ]
    return {
        "kind": "aippocampus_multimodal_provider_route_smoke",
        "schema_version": 1,
        "ok": bool(manifest_report["ok"] and not expectation_failures),
        "manifest": manifest_report,
        "metrics": {
            "case_count": len(cases),
            "allowed_case_count": sum(1 for case in cases if case.get("allowed")),
            "blocked_case_count": sum(1 for case in cases if not case.get("allowed")),
            "unexpected_decision_count": len(expectation_failures),
        },
        "cases": cases,
        "privacy_boundary": {
            "fixture_public_safe": True,
            "raw_media_bytes_emitted": False,
            "raw_prompt_text_emitted": False,
            "absolute_paths_emitted": False,
            "provider_secret_values_emitted": False,
            "output_shape": "sanitized_ids_hashes_policy_decisions_and_blocker_codes",
        },
        "cannot_claim": sorted(
            {
                claim
                for case in cases
                for claim in _as_list(case.get("cannot_claim"))
            }
            | {
                "live_provider_vision_quality",
                "raw_media_processed_by_live_provider",
                "derived_artifacts_are_source_truth",
            }
        ),
    }
