#!/usr/bin/env python3
"""Repo-internal prototype for capability execution contracts.

Capability contracts constrain what a skill-like path is allowed to read and
claim. They deliberately do not replace knowledge sources, claim promotion, or
the high-risk answer gate; those remain the source-of-truth layers.
"""

from __future__ import annotations

import hashlib
from typing import Any, Mapping, Sequence

from aippocampus_runtime.knowledge import answer_gate

CAPABILITY_CONTRACT_SCHEMA_VERSION = "aippocampus.capability_contract.v1"
REQUIRED_FIELDS = (
    "capability_id",
    "allowed_sources",
    "required_permissions",
    "privacy_partitions",
    "source_reopen_required",
    "human_review_required",
    "input_schema",
    "output_schema",
    "risk_level",
    "cannot_claim",
    "audit_events",
    "test_cases",
    "version",
    "superseded_by",
)
HIGH_RISK_LEVELS = {"high", "critical"}


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


def _has_required_field(contract: Mapping[str, Any], field: str) -> bool:
    if field not in contract:
        return False
    if field == "superseded_by":
        return True
    value = contract.get(field)
    if isinstance(value, bool):
        return True
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def _sha1_text(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()


def _sources_by_id(registry: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    return {
        str(item.get("source_id") or ""): item
        for item in registry.get("sources") or []
        if isinstance(item, Mapping) and item.get("source_id")
    }


def _claims_by_id(registry: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    return {
        str(item.get("claim_id") or ""): item
        for item in registry.get("claims") or []
        if isinstance(item, Mapping) and item.get("claim_id")
    }


def _unique(values: Sequence[str]) -> list[str]:
    return sorted({item for item in values if item})


def _case_report(
    *,
    contract: Mapping[str, Any],
    case: Mapping[str, Any],
    output_state: str,
    gates: Sequence[Mapping[str, str]],
    cannot_claim: Sequence[str],
    cited_boundaries: Sequence[Mapping[str, Any]] | None = None,
    questions: Sequence[Mapping[str, str]] | None = None,
) -> dict[str, Any]:
    gate_codes = _blocker_codes(gates)
    capability_id = str(contract.get("capability_id") or "")
    input_text = str(case.get("input_text") or "")
    can_emit = output_state == "answer_with_cited_bounds"
    case_risk_flags = _as_list(case.get("risk_flags")) if can_emit else []
    return {
        "case_id": case.get("case_id"),
        "family": case.get("family"),
        "capability_id": capability_id,
        "evaluation_path": "capability_contract",
        "input_sha1": _sha1_text(input_text)[:16] if input_text else None,
        "output_state": output_state,
        "can_emit_high_risk_answer": can_emit,
        "gates": [dict(item) for item in gates],
        "gate_codes": gate_codes,
        "risk_flags": case_risk_flags,
        "missing_context_questions": [dict(item) for item in (questions or [])],
        "cited_boundaries": [dict(item) for item in (cited_boundaries or [])] if can_emit else [],
        "cannot_claim": _unique(list(cannot_claim)),
        "source_boundary": {
            "evidence_required": "reopened_source_span",
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
        "audit_events": _unique(_as_list(contract.get("audit_events")) + ["capability_case_evaluated"]),
    }


def validate_capability_contract(contract: Mapping[str, Any]) -> dict[str, Any]:
    """Validate the minimal #517 capability-contract fixture shape."""

    blockers: list[dict[str, str]] = []
    for field in REQUIRED_FIELDS:
        if not _has_required_field(contract, field):
            blockers.append(
                _block(
                    f"missing_{field}",
                    field=field,
                    message=f"{field} is required for a capability contract.",
                )
            )

    schema_version = str(contract.get("schema_version") or CAPABILITY_CONTRACT_SCHEMA_VERSION)
    if schema_version != CAPABILITY_CONTRACT_SCHEMA_VERSION:
        blockers.append(
            _block(
                "unsupported_schema_version",
                field="schema_version",
                message="Unsupported capability contract schema version.",
            )
        )

    risk_level = str(contract.get("risk_level") or "")
    if risk_level in HIGH_RISK_LEVELS and contract.get("source_reopen_required") is not True:
        blockers.append(
            _block(
                "high_risk_source_reopen_required",
                field="source_reopen_required",
                message="High-risk capabilities must require reopened source spans.",
            )
        )
    if risk_level in HIGH_RISK_LEVELS and "source_reopen_required" not in _as_list(
        contract.get("required_permissions")
    ):
        blockers.append(
            _block(
                "missing_source_reopen_permission",
                field="required_permissions",
                message="High-risk capability permissions must name source reopen.",
            )
        )

    if not isinstance(contract.get("input_schema"), Mapping):
        blockers.append(
            _block(
                "invalid_input_schema",
                field="input_schema",
                message="input_schema must be an object.",
            )
        )
    if not isinstance(contract.get("output_schema"), Mapping):
        blockers.append(
            _block(
                "invalid_output_schema",
                field="output_schema",
                message="output_schema must be an object.",
            )
        )

    cannot_claim = _as_list(contract.get("cannot_claim"))
    if not cannot_claim:
        blockers.append(
            _block(
                "missing_cannot_claim",
                field="cannot_claim",
                message="Capability contracts must publish explicit cannot-claim boundaries.",
            )
        )

    return {
        "ok": not blockers,
        "schema_version": CAPABILITY_CONTRACT_SCHEMA_VERSION,
        "capability_id": contract.get("capability_id"),
        "version": contract.get("version"),
        "risk_level": risk_level,
        "allowed_sources": _as_list(contract.get("allowed_sources")),
        "allowed_source_types": _as_list(contract.get("allowed_source_types")),
        "required_permissions": _as_list(contract.get("required_permissions")),
        "privacy_partitions": _as_list(contract.get("privacy_partitions")),
        "source_reopen_required": bool(contract.get("source_reopen_required")),
        "human_review_required": _as_list(contract.get("human_review_required")),
        "cannot_claim": cannot_claim,
        "audit_events": _as_list(contract.get("audit_events")),
        "test_cases": _as_list(contract.get("test_cases")),
        "superseded_by": contract.get("superseded_by"),
        "truth_boundary": "repo_internal_prototype",
        "blockers": blockers,
        "blocker_codes": _blocker_codes(blockers),
    }


def _capability_gates(
    contract: Mapping[str, Any],
    case: Mapping[str, Any],
    registry: Mapping[str, Any],
) -> list[dict[str, str]]:
    gates: list[dict[str, str]] = []
    contract_id = str(contract.get("capability_id") or "")
    case_contract_id = str(case.get("capability_id") or "")
    if case_contract_id and case_contract_id != contract_id:
        gates.append(
            _block(
                "capability_id_mismatch",
                field="capability_id",
                message="Case capability_id does not match the active contract.",
            )
        )

    allowed_partitions = set(_as_list(contract.get("privacy_partitions")))
    privacy_partition = str(case.get("privacy_partition") or "")
    if privacy_partition not in allowed_partitions:
        gates.append(
            _block(
                "privacy_partition_not_allowed",
                field="privacy_partition",
                message="Case privacy partition is outside the capability contract.",
            )
        )

    claims = _claims_by_id(registry)
    sources = _sources_by_id(registry)
    allowed_sources = set(_as_list(contract.get("allowed_sources")))
    allowed_source_types = set(_as_list(contract.get("allowed_source_types")))
    for claim_id in _as_list(case.get("selected_claim_ids")):
        claim = claims.get(claim_id)
        if not claim:
            continue
        source_id = str(claim.get("source_id") or "")
        source = sources.get(source_id) or {}
        source_type = str(source.get("source_type") or "")
        if allowed_sources and source_id not in allowed_sources:
            gates.append(
                _block(
                    "source_not_allowed_by_capability",
                    field="source_id",
                    message="Selected claim source is not in the capability allowlist.",
                )
            )
        if allowed_source_types and source_type not in allowed_source_types:
            gates.append(
                _block(
                    "source_type_not_allowed_by_capability",
                    field="source_type",
                    message="Selected source type is not allowed by the capability contract.",
                )
            )

    context = _as_mapping(case.get("context"))
    if (
        context.get("external_model_route")
        and case.get("sensitive_input")
        and not context.get("allow_external_text")
    ):
        gates.append(
            _block(
                "external_tool_text_permission_required",
                field="external_model_route",
                message="Sensitive contract text cannot be sent to an external tool route by default.",
            )
        )
    return gates


def evaluate_capability_case(
    contract: Mapping[str, Any],
    case: Mapping[str, Any],
    registry: Mapping[str, Any],
) -> dict[str, Any]:
    """Evaluate one synthetic case through contract constraints plus answer gate."""

    contract_report = validate_capability_contract(contract)
    cannot_claim = _unique(
        _as_list(contract.get("cannot_claim")) + _as_list(case.get("cannot_claim"))
    )
    if not contract_report["ok"]:
        return _case_report(
            contract=contract,
            case=case,
            output_state="human_review_required",
            gates=contract_report["blockers"],
            cannot_claim=cannot_claim + ["capability_contract_invalid"],
        )

    gates = _capability_gates(contract, case, registry)
    if gates:
        return _case_report(
            contract=contract,
            case=case,
            output_state="human_review_required",
            gates=gates,
            cannot_claim=cannot_claim,
        )

    gate_report = answer_gate.evaluate_high_risk_answer_gate(
        registry,
        claim_ids=_as_list(case.get("selected_claim_ids")),
        evidence_items=[
            item for item in case.get("evidence_items") or [] if isinstance(item, Mapping)
        ],
        context=_as_mapping(case.get("context")),
        required_context_keys=_as_list(contract.get("required_context_keys")),
    )
    return _case_report(
        contract=contract,
        case=case,
        output_state=str(gate_report.get("output_state") or "human_review_required"),
        gates=[item for item in gate_report.get("gates") or [] if isinstance(item, Mapping)],
        cannot_claim=cannot_claim + _as_list(gate_report.get("cannot_claim")),
        cited_boundaries=[
            item for item in gate_report.get("cited_boundaries") or [] if isinstance(item, Mapping)
        ],
        questions=[item for item in gate_report.get("questions") or [] if isinstance(item, Mapping)],
    )
