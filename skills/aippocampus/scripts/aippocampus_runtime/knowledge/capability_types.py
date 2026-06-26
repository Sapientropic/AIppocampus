#!/usr/bin/env python3
"""Typed capability manifest boundaries for agent skills.

This module is the #518 typed-manifest owner. It stays deliberately narrow:
capability manifests constrain execution, permissions, source boundaries, and
evaluation protocols. They do not make source claims true, generate advice, or
replace `SKILL.md`; high-risk factual use still goes through source reopen and
the governed knowledge answer gate.
"""

from __future__ import annotations

import hashlib
from typing import Any, Mapping, Sequence

from aippocampus_runtime.core import (
    dict_or_empty,
    schema_block,
    schema_blocker_codes,
    string_list_or_empty,
)
from aippocampus_runtime.knowledge import answer_gate

CAPABILITY_MANIFEST_SCHEMA_VERSION = "aippocampus.capability_manifest.v1"
CAPABILITY_RECORD_SCHEMA_VERSION = "aippocampus.capability_record.v1"

RISK_LEVELS = {"low", "medium", "high", "critical"}
HIGH_RISK_LEVELS = {"high", "critical"}
SKILL_TYPES = {
    "declarative_knowledge",
    "procedural_operation",
    "perceptual_parsing",
    "judgment_gating",
    "interactive_communication",
    "learning_adaptation",
    "metacognitive",
    "social_relational",
    "tool_affordance",
}
RUNTIME_LAYERS = {
    "deterministic_cell",
    "microcircuit",
    "semantic_subregion",
    "job_circuit",
    "system_router",
}
SOURCE_BOUNDARIES = {"scent", "candidate", "evidence", "fact"}

MANIFEST_REQUIRED_FIELDS = (
    "schema_version",
    "capability_taxonomy",
    "capabilities",
)
CAPABILITY_REQUIRED_FIELDS = (
    "schema_version",
    "capability_id",
    "version",
    "owner",
    "risk_level",
    "domain",
    "skill_types",
    "runtime_layer",
    "intent_scope",
    "input_schema",
    "output_schema",
    "memory_policy",
    "privacy_policy",
    "source_requirements",
    "tool_permissions",
    "side_effects",
    "output_classes",
    "evaluation_protocols",
    "supersession",
    "last_reviewed_at",
)
CAPABILITY_OBJECT_FIELDS = {
    "intent_scope",
    "input_schema",
    "output_schema",
    "memory_policy",
    "privacy_policy",
    "source_requirements",
    "side_effects",
    "supersession",
}
TOOL_PERMISSION_REQUIRED_FIELDS = (
    "tool_id",
    "permission_profile",
    "allowed",
    "requires",
    "can_emit_high_risk_answer",
)


def _unique(values: Sequence[str]) -> list[str]:
    return sorted({item for item in values if item})


def _nonempty(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def _sha1_text(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()


def _claims_by_id(registry: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    return {
        str(item.get("claim_id") or ""): item
        for item in registry.get("claims") or []
        if isinstance(item, Mapping) and item.get("claim_id")
    }


def _sources_by_id(registry: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    return {
        str(item.get("source_id") or ""): item
        for item in registry.get("sources") or []
        if isinstance(item, Mapping) and item.get("source_id")
    }


def _capabilities(manifest: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return [item for item in manifest.get("capabilities") or [] if isinstance(item, Mapping)]


def _capability_by_id(
    manifest: Mapping[str, Any],
    capability_id: str,
) -> Mapping[str, Any] | None:
    for capability in _capabilities(manifest):
        if str(capability.get("capability_id") or "") == capability_id:
            return capability
    return None


def _cases(manifest: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return [item for item in manifest.get("cases") or [] if isinstance(item, Mapping)]


def _case_by_id(manifest: Mapping[str, Any], case_id: str) -> Mapping[str, Any] | None:
    for case in _cases(manifest):
        if str(case.get("case_id") or "") == case_id:
            return case
    return None


def _missing_required_blocks(
    payload: Mapping[str, Any],
    fields: Sequence[str],
    *,
    prefix: str,
) -> list[dict[str, str]]:
    return [
        schema_block(
            f"{prefix}_missing_{field}",
            field=field,
            message=f"{field} is required for typed capability manifests.",
        )
        for field in fields
        if not _nonempty(payload.get(field))
    ]


def _validate_taxonomy(manifest: Mapping[str, Any]) -> tuple[list[str], list[dict[str, str]]]:
    taxonomy = dict_or_empty(manifest.get("capability_taxonomy"))
    blockers: list[dict[str, str]] = []
    skill_types = string_list_or_empty(taxonomy.get("skill_types"))
    missing_skill_types = sorted(SKILL_TYPES - set(skill_types))
    if missing_skill_types:
        blockers.append(
            schema_block(
                "taxonomy_missing_skill_types",
                field="capability_taxonomy.skill_types",
                message="Typed capability taxonomy must include the #518 skill-type set.",
            )
        )
    if not set(string_list_or_empty(taxonomy.get("risk_levels"))).issuperset(RISK_LEVELS):
        blockers.append(
            schema_block(
                "taxonomy_missing_risk_levels",
                field="capability_taxonomy.risk_levels",
                message="Typed capability taxonomy must include low/medium/high/critical risk.",
            )
        )
    if not set(string_list_or_empty(taxonomy.get("runtime_layers"))).issuperset(RUNTIME_LAYERS):
        blockers.append(
            schema_block(
                "taxonomy_missing_runtime_layers",
                field="capability_taxonomy.runtime_layers",
                message="Typed capability taxonomy must align to cognitive runtime layers.",
            )
        )
    if not set(string_list_or_empty(taxonomy.get("source_boundaries"))).issuperset(SOURCE_BOUNDARIES):
        blockers.append(
            schema_block(
                "taxonomy_missing_source_boundaries",
                field="capability_taxonomy.source_boundaries",
                message="Typed capability taxonomy must distinguish scent/candidate/evidence/fact.",
            )
        )
    return sorted(skill_types), blockers


def _validate_tool_permissions(
    capability: Mapping[str, Any],
) -> list[dict[str, str]]:
    blockers: list[dict[str, str]] = []
    permissions = [
        item for item in capability.get("tool_permissions") or [] if isinstance(item, Mapping)
    ]
    if not permissions:
        blockers.append(
            schema_block(
                "capability_missing_tool_permissions",
                field="tool_permissions",
                message="A typed capability must declare at least one tool permission profile.",
            )
        )
        return blockers

    risk_level = str(capability.get("risk_level") or "")
    evaluation_protocols = set(string_list_or_empty(capability.get("evaluation_protocols")))
    source_requirements = dict_or_empty(capability.get("source_requirements"))
    requires_reopen = source_requirements.get("source_reopen_required") is True
    for permission in permissions:
        blockers.extend(
            _missing_required_blocks(
                permission,
                TOOL_PERMISSION_REQUIRED_FIELDS,
                prefix="tool_permission",
            )
        )
        if not isinstance(permission.get("allowed"), bool):
            blockers.append(
                schema_block(
                    "tool_permission_invalid_allowed",
                    field="tool_permissions.allowed",
                    message="Tool permission allowed must be a boolean.",
                )
            )
        if not isinstance(permission.get("requires"), list):
            blockers.append(
                schema_block(
                    "tool_permission_invalid_requires",
                    field="tool_permissions.requires",
                    message="Tool permission requires must be a list.",
                )
            )
        if (
            permission.get("can_emit_high_risk_answer") is True
            and "high_risk_answer_gate" not in evaluation_protocols
        ):
            blockers.append(
                schema_block(
                    "tool_permission_missing_high_risk_gate",
                    field="evaluation_protocols",
                    message="High-risk answer emission requires the high-risk answer gate.",
                )
            )
        if risk_level in HIGH_RISK_LEVELS and permission.get("can_emit_high_risk_answer") is True:
            requires = set(string_list_or_empty(permission.get("requires")))
            missing_requires = {"source_reopen", "active_claim", "current_lifecycle"} - requires
            if missing_requires:
                blockers.append(
                    schema_block(
                        "tool_permission_missing_high_risk_requires",
                        field="tool_permissions.requires",
                        message="High-risk permission profiles must require reopen, active claim, and lifecycle checks.",
                    )
                )
            if not requires_reopen:
                blockers.append(
                    schema_block(
                        "high_risk_source_reopen_required",
                        field="source_requirements.source_reopen_required",
                        message="High-risk capabilities must require source reopen before answer use.",
                    )
                )
    return blockers


def _validate_capability(capability: Mapping[str, Any]) -> list[dict[str, str]]:
    blockers = _missing_required_blocks(
        capability,
        CAPABILITY_REQUIRED_FIELDS,
        prefix="capability",
    )
    if capability.get("schema_version") != CAPABILITY_RECORD_SCHEMA_VERSION:
        blockers.append(
            schema_block(
                "capability_unsupported_schema_version",
                field="schema_version",
                message="Unsupported capability record schema version.",
            )
        )

    risk_level = str(capability.get("risk_level") or "")
    if risk_level and risk_level not in RISK_LEVELS:
        blockers.append(
            schema_block(
                "capability_unknown_risk_level",
                field="risk_level",
                message="Capability risk level is outside the typed taxonomy.",
            )
        )

    skill_types = set(string_list_or_empty(capability.get("skill_types")))
    if not skill_types:
        blockers.append(
            schema_block(
                "capability_missing_skill_type",
                field="skill_types",
                message="Each capability must declare at least one typed skill type.",
            )
        )
    elif not skill_types.issubset(SKILL_TYPES):
        blockers.append(
            schema_block(
                "capability_unknown_skill_type",
                field="skill_types",
                message="Capability skill_types must come from the typed taxonomy.",
            )
        )

    runtime_layer = str(capability.get("runtime_layer") or "")
    if runtime_layer and runtime_layer not in RUNTIME_LAYERS:
        blockers.append(
            schema_block(
                "capability_unknown_runtime_layer",
                field="runtime_layer",
                message="Capability runtime_layer must align to the cognitive runtime taxonomy.",
            )
        )

    for field in CAPABILITY_OBJECT_FIELDS:
        if field in capability and not isinstance(capability.get(field), Mapping):
            blockers.append(
                schema_block(
                    f"capability_invalid_{field}",
                    field=field,
                    message=f"{field} must be an object.",
                )
            )
    for field in ("output_classes", "evaluation_protocols"):
        if field in capability and not isinstance(capability.get(field), list):
            blockers.append(
                schema_block(
                    f"capability_invalid_{field}",
                    field=field,
                    message=f"{field} must be a list.",
                )
            )

    source_requirements = dict_or_empty(capability.get("source_requirements"))
    source_boundary = str(source_requirements.get("source_boundary") or "")
    if source_boundary and source_boundary not in SOURCE_BOUNDARIES:
        blockers.append(
            schema_block(
                "capability_unknown_source_boundary",
                field="source_requirements.source_boundary",
                message="source_boundary must be scent, candidate, evidence, or fact.",
            )
        )
    if risk_level in HIGH_RISK_LEVELS and not string_list_or_empty(capability.get("cannot_claim")):
        blockers.append(
            schema_block(
                "capability_missing_cannot_claim",
                field="cannot_claim",
                message="High-risk typed capabilities must publish cannot-claim boundaries.",
            )
        )
    blockers.extend(_validate_tool_permissions(capability))
    return blockers


def validate_capability_manifest(manifest: Mapping[str, Any]) -> dict[str, Any]:
    """Validate the typed capability manifest shape without treating it as fact."""

    blockers = _missing_required_blocks(
        manifest,
        MANIFEST_REQUIRED_FIELDS,
        prefix="manifest",
    )
    if manifest.get("schema_version") != CAPABILITY_MANIFEST_SCHEMA_VERSION:
        blockers.append(
            schema_block(
                "manifest_unsupported_schema_version",
                field="schema_version",
                message="Unsupported capability manifest schema version.",
            )
        )

    skill_types, taxonomy_blockers = _validate_taxonomy(manifest)
    blockers.extend(taxonomy_blockers)

    capabilities = _capabilities(manifest)
    if not capabilities:
        blockers.append(
            schema_block(
                "manifest_missing_capabilities",
                field="capabilities",
                message="A typed capability manifest must include capability records.",
            )
        )
    capability_ids: list[str] = []
    for capability in capabilities:
        capability_id = str(capability.get("capability_id") or "")
        if capability_id:
            capability_ids.append(capability_id)
        blockers.extend(_validate_capability(capability))

    duplicate_ids = sorted({item for item in capability_ids if capability_ids.count(item) > 1})
    if duplicate_ids:
        blockers.append(
            schema_block(
                "manifest_duplicate_capability_id",
                field="capabilities.capability_id",
                message="Capability ids must be unique inside a manifest.",
            )
        )

    return {
        "ok": not blockers,
        "schema_version": CAPABILITY_MANIFEST_SCHEMA_VERSION,
        "capability_count": len(capabilities),
        "capability_ids": sorted(capability_ids),
        "skill_types": skill_types,
        "truth_boundary": "execution_boundary_not_fact_source",
        "public_api_status": "internal_architecture_prototype",
        "blockers": blockers,
        "blocker_codes": schema_blocker_codes(blockers),
    }


def tool_permission_profiles(
    manifest: Mapping[str, Any],
    tool_id: str,
) -> list[dict[str, Any]]:
    """Return sanitized permission profiles for one tool id."""

    profiles: list[dict[str, Any]] = []
    for capability in _capabilities(manifest):
        privacy_policy = dict_or_empty(capability.get("privacy_policy"))
        for permission in capability.get("tool_permissions") or []:
            if not isinstance(permission, Mapping):
                continue
            if str(permission.get("tool_id") or "") != tool_id:
                continue
            profiles.append(
                {
                    "capability_id": capability.get("capability_id"),
                    "tool_id": tool_id,
                    "permission_profile": permission.get("permission_profile"),
                    "risk_level": capability.get("risk_level"),
                    "allowed": bool(permission.get("allowed")),
                    "requires": string_list_or_empty(permission.get("requires")),
                    "can_emit_high_risk_answer": bool(
                        permission.get("can_emit_high_risk_answer")
                    ),
                    "requires_high_risk_gate": "high_risk_answer_gate"
                    in string_list_or_empty(capability.get("evaluation_protocols")),
                    "source_text_allowed_external": bool(
                        permission.get(
                            "source_text_allowed_external",
                            privacy_policy.get("source_text_allowed_external"),
                        )
                    ),
                }
            )
    return sorted(
        profiles,
        key=lambda item: (
            str(item.get("tool_id") or ""),
            str(item.get("risk_level") or ""),
            str(item.get("capability_id") or ""),
        ),
    )


def _capability_case_gates(
    capability: Mapping[str, Any],
    case: Mapping[str, Any],
    registry: Mapping[str, Any],
) -> list[dict[str, str]]:
    gates: list[dict[str, str]] = []
    capability_id = str(capability.get("capability_id") or "")
    case_capability_id = str(case.get("capability_id") or "")
    if case_capability_id and case_capability_id != capability_id:
        gates.append(
            schema_block(
                "capability_id_mismatch",
                field="capability_id",
                message="Case capability_id does not match the active typed capability.",
            )
        )

    privacy_policy = dict_or_empty(capability.get("privacy_policy"))
    allowed_partitions = set(string_list_or_empty(privacy_policy.get("allowed_partitions")))
    privacy_partition = str(case.get("privacy_partition") or "")
    if allowed_partitions and privacy_partition not in allowed_partitions:
        gates.append(
            schema_block(
                "privacy_partition_not_allowed",
                field="privacy_partition",
                message="Case privacy partition is outside the typed capability contract.",
            )
        )

    source_requirements = dict_or_empty(capability.get("source_requirements"))
    allowed_source_types = set(string_list_or_empty(source_requirements.get("allowed_source_types")))
    forbidden_source_types = set(string_list_or_empty(source_requirements.get("forbidden_source_types")))
    claims = _claims_by_id(registry)
    sources = _sources_by_id(registry)
    for claim_id in string_list_or_empty(case.get("selected_claim_ids")):
        claim = claims.get(claim_id)
        if not claim:
            continue
        source = sources.get(str(claim.get("source_id") or "")) or {}
        source_type = str(source.get("source_type") or "")
        if allowed_source_types and source_type not in allowed_source_types:
            gates.append(
                schema_block(
                    "source_type_not_allowed_by_capability",
                    field="source_type",
                    message="Selected source type is outside the typed capability allowlist.",
                )
            )
        if forbidden_source_types and source_type in forbidden_source_types:
            gates.append(
                schema_block(
                    "source_type_forbidden_by_capability",
                    field="source_type",
                    message="Selected source type is explicitly forbidden by the typed capability.",
                )
            )

    context = dict_or_empty(case.get("context"))
    if context.get("external_model_route") and not privacy_policy.get(
        "source_text_allowed_external",
        False,
    ):
        for claim_id in string_list_or_empty(case.get("selected_claim_ids")):
            claim = claims.get(claim_id) or {}
            source = sources.get(str(claim.get("source_id") or "")) or {}
            if str(source.get("privacy_class") or "") in answer_gate.PRIVATE_PRIVACY_CLASSES:
                gates.append(
                    schema_block(
                        "private_source_permission_required",
                        field="privacy_class",
                        message="Private source text needs explicit permission before external tool use.",
                    )
                )
    return gates


def _case_report(
    *,
    capability: Mapping[str, Any],
    case: Mapping[str, Any],
    output_state: str,
    gates: Sequence[Mapping[str, str]],
    cannot_claim: Sequence[str],
    cited_boundaries: Sequence[Mapping[str, Any]] | None = None,
    questions: Sequence[Mapping[str, str]] | None = None,
) -> dict[str, Any]:
    can_emit = output_state == "answer_with_cited_bounds"
    input_text = str(case.get("input_text") or "")
    side_effects = dict_or_empty(capability.get("side_effects"))
    return {
        "case_id": case.get("case_id"),
        "family": case.get("family"),
        "capability_id": capability.get("capability_id"),
        "evaluation_path": "capability_manifest",
        "input_sha1": _sha1_text(input_text)[:16] if input_text else None,
        "output_state": output_state,
        "can_emit_high_risk_answer": can_emit,
        "risk_flags": string_list_or_empty(case.get("risk_flags")) if can_emit else [],
        "gates": [dict(item) for item in gates],
        "gate_codes": schema_blocker_codes(gates),
        "missing_context_questions": [dict(item) for item in (questions or [])],
        "cited_boundaries": [dict(item) for item in (cited_boundaries or [])] if can_emit else [],
        "cannot_claim": _unique(list(cannot_claim)),
        "source_boundary": {
            "source_boundary": dict_or_empty(capability.get("source_requirements")).get(
                "source_boundary",
                "candidate",
            ),
            "evidence_required": dict_or_empty(capability.get("source_requirements")).get(
                "required_evidence",
                "reopened_source_span",
            ),
            "routing_evidence_is_navigation_only": True,
            "source_text_exported": False,
            "claim_text_exported": False,
        },
        "privacy": {
            "privacy_partition": case.get("privacy_partition"),
            "source_text_allowed_external": False,
            "source_text_exported": False,
            "raw_input_text_emitted": False,
            "raw_source_text_emitted": False,
        },
        "audit_events": _unique(
            string_list_or_empty(side_effects.get("audit_events")) + ["capability_manifest_case_evaluated"]
        ),
    }


def evaluate_manifest_case(
    manifest: Mapping[str, Any],
    registry: Mapping[str, Any],
    *,
    case_id: str,
) -> dict[str, Any]:
    """Evaluate one public-safe case through a typed capability manifest."""

    manifest_report = validate_capability_manifest(manifest)
    case = _case_by_id(manifest, case_id)
    if not case:
        return {
            "case_id": case_id,
            "output_state": "refuse_or_redirect",
            "can_emit_high_risk_answer": False,
            "gates": [
                schema_block(
                    "missing_manifest_case",
                    field="case_id",
                    message="Case id does not resolve in the capability manifest.",
                )
            ],
            "gate_codes": ["missing_manifest_case"],
            "risk_flags": [],
            "cannot_claim": ["missing_manifest_case_not_answerable"],
            "privacy": {
                "source_text_allowed_external": False,
                "source_text_exported": False,
                "raw_input_text_emitted": False,
                "raw_source_text_emitted": False,
            },
        }

    capability = _capability_by_id(manifest, str(case.get("capability_id") or ""))
    if capability is None:
        return _case_report(
            capability={},
            case=case,
            output_state="refuse_or_redirect",
            gates=[
                schema_block(
                    "missing_capability",
                    field="capability_id",
                    message="Case capability_id does not resolve in the manifest.",
                )
            ],
            cannot_claim=["missing_capability_not_answerable"],
        )

    cannot_claim = _unique(
        string_list_or_empty(capability.get("cannot_claim")) + string_list_or_empty(case.get("cannot_claim"))
    )
    if not manifest_report["ok"]:
        return _case_report(
            capability=capability,
            case=case,
            output_state="human_review_required",
            gates=manifest_report["blockers"],
            cannot_claim=cannot_claim + ["capability_manifest_invalid"],
        )

    capability_gates = _capability_case_gates(capability, case, registry)
    if capability_gates:
        return _case_report(
            capability=capability,
            case=case,
            output_state="human_review_required",
            gates=capability_gates,
            cannot_claim=cannot_claim,
        )

    gate_report = answer_gate.evaluate_high_risk_answer_gate(
        registry,
        claim_ids=string_list_or_empty(case.get("selected_claim_ids")),
        evidence_items=[
            item for item in case.get("evidence_items") or [] if isinstance(item, Mapping)
        ],
        context=dict_or_empty(case.get("context")),
        required_context_keys=string_list_or_empty(
            case.get("required_context_keys")
            or dict_or_empty(capability.get("source_requirements")).get("required_context_keys")
        ),
    )
    return _case_report(
        capability=capability,
        case=case,
        output_state=str(gate_report.get("output_state") or "human_review_required"),
        gates=[item for item in gate_report.get("gates") or [] if isinstance(item, Mapping)],
        cannot_claim=cannot_claim + string_list_or_empty(gate_report.get("cannot_claim")),
        cited_boundaries=[
            item for item in gate_report.get("cited_boundaries") or [] if isinstance(item, Mapping)
        ],
        questions=[item for item in gate_report.get("questions") or [] if isinstance(item, Mapping)],
    )


def run_manifest_smoke(
    manifest: Mapping[str, Any],
    registry: Mapping[str, Any],
) -> dict[str, Any]:
    """Run the public-safe deterministic manifest smoke over embedded cases."""

    manifest_report = validate_capability_manifest(manifest)
    cases = [
        evaluate_manifest_case(manifest, registry, case_id=str(case.get("case_id") or ""))
        for case in _cases(manifest)
        if case.get("case_id")
    ]
    expected_by_id = {
        str(case.get("case_id") or ""): str(case.get("expected_output_state") or "")
        for case in _cases(manifest)
        if case.get("case_id")
    }
    case_expectations_ok = all(
        not expected_by_id.get(str(case.get("case_id") or ""))
        or case.get("output_state") == expected_by_id.get(str(case.get("case_id") or ""))
        for case in cases
    )
    cannot_claim = sorted(
        {
            claim
            for case in cases
            for claim in string_list_or_empty(case.get("cannot_claim"))
        }
        | {
            claim
            for capability in _capabilities(manifest)
            for claim in string_list_or_empty(capability.get("cannot_claim"))
        }
    )
    return {
        "kind": "aippocampus_capability_manifest_smoke",
        "schema_version": 1,
        "ok": bool(manifest_report["ok"] and case_expectations_ok),
        "quality_gate_ok": bool(manifest_report["ok"] and case_expectations_ok),
        "manifest": manifest_report,
        "metrics": {
            "case_count": len(cases),
            "unexpected_output_state_count": sum(
                1
                for case in cases
                if expected_by_id.get(str(case.get("case_id") or ""))
                and case.get("output_state") != expected_by_id.get(str(case.get("case_id") or ""))
            ),
            "high_risk_answer_count": sum(
                1 for case in cases if case.get("output_state") == "answer_with_cited_bounds"
            ),
        },
        "cases": cases,
        "privacy_boundary": {
            "fixture_public_safe": True,
            "raw_input_text_emitted": False,
            "raw_source_text_emitted": False,
            "absolute_paths_emitted": False,
            "source_text_exported": False,
            "claim_text_exported": False,
            "output_shape": "sanitized_ids_hashes_gates_and_metrics",
        },
        "cannot_claim": cannot_claim,
    }
