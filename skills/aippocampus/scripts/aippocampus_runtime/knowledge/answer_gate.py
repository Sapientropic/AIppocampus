#!/usr/bin/env python3
"""Deterministic high-risk answer gate over governed knowledge claims."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from aippocampus_runtime.core import dict_or_empty, string_list_or_empty
from aippocampus_runtime.knowledge import schema

POLICY_VERSION = "aippocampus.high_risk_answer_gate.v1"

OUTPUT_STATES = {
    "source_reopen_required",
    "missing_context_question",
    "human_review_required",
    "degrade_to_general_information",
    "refuse_or_redirect",
    "answer_with_cited_bounds",
}
REOPENED_EVIDENCE_KINDS = {"reopened_source_span", "source_ref_reopened"}
ROUTING_ONLY_EVIDENCE_KINDS = {
    "embedding_hit",
    "semantic_match",
    "vector_neighbor",
    "model_generated_summary",
}
CLEAR_CONFLICT_STATUSES = {"", "none", "resolved"}
INACTIVE_EFFECTIVE_SOURCE_STATUSES = {
    "quarantined",
    "candidate",
    "review_required",
    "retired",
    "retracted",
    "superseded",
    "rollback_available",
}
PRIVATE_PRIVACY_CLASSES = {"personal_private", "org_private", "regulated_private"}
BASE_CANNOT_CLAIM = [
    "professional_certification_not_claimed",
    "source_text_not_exported_by_gate",
]


def _as_set(value: Any) -> set[str]:
    return set(string_list_or_empty(value))


def _critical_variables(context: Mapping[str, Any]) -> Mapping[str, Any]:
    return dict_or_empty(context.get("critical_variables"))


def _add_gate(
    gates: list[dict[str, str]],
    code: str,
    *,
    field: str,
    message: str,
) -> None:
    gates.append({"code": code, "field": field, "message": message})


def _gate_codes(gates: list[dict[str, str]]) -> list[str]:
    return sorted({item["code"] for item in gates})


def _selected_claims(
    claims: Mapping[str, Mapping[str, Any]],
    claim_ids: Sequence[str],
) -> tuple[list[Mapping[str, Any]], list[str]]:
    selected: list[Mapping[str, Any]] = []
    missing: list[str] = []
    for claim_id in claim_ids:
        claim = claims.get(claim_id)
        if claim is None:
            missing.append(claim_id)
        else:
            selected.append(claim)
    return selected, missing


def _reopened_claim_ids(evidence_items: list[Mapping[str, Any]]) -> set[str]:
    reopened: set[str] = set()
    for item in evidence_items:
        if str(item.get("kind") or "") not in REOPENED_EVIDENCE_KINDS:
            continue
        claim_id = str(item.get("claim_id") or "")
        source_id = str(item.get("source_id") or "")
        anchor = item.get("source_anchor")
        if claim_id and source_id and isinstance(anchor, Mapping):
            reopened.add(claim_id)
    return reopened


def _routing_only_kinds(evidence_items: list[Mapping[str, Any]]) -> set[str]:
    return {
        str(item.get("kind") or "")
        for item in evidence_items
        if str(item.get("kind") or "") in ROUTING_ONLY_EVIDENCE_KINDS
    }


def _missing_context_gates(
    context: Mapping[str, Any],
    required_context_keys: list[str],
) -> list[dict[str, str]]:
    gates: list[dict[str, str]] = []
    for field in ("domain_scope", "jurisdiction_scope", "as_of_date"):
        value = context.get(field)
        if not value:
            _add_gate(
                gates,
                f"missing_{field}",
                field=field,
                message=f"{field} is required before high-risk answer formation.",
            )
    variables = _critical_variables(context)
    for key in required_context_keys:
        if not variables.get(key):
            _add_gate(
                gates,
                f"missing_critical_variable:{key}",
                field="critical_variables",
                message=f"Critical context variable {key} is missing.",
            )
    return gates


def _applicability_gates(
    claim: Mapping[str, Any],
    context: Mapping[str, Any],
) -> list[dict[str, str]]:
    gates: list[dict[str, str]] = []
    request_domains = _as_set(context.get("domain_scope"))
    request_jurisdictions = _as_set(context.get("jurisdiction_scope"))
    claim_domains = _as_set(claim.get("claim_scope"))
    claim_jurisdictions = _as_set(claim.get("jurisdiction_scope"))

    if claim_domains and request_domains and not claim_domains.issubset(request_domains):
        _add_gate(
            gates,
            "claim_domain_not_applicable",
            field="claim_scope",
            message="Claim domain scope does not fit the requested domain.",
        )
    if (
        claim_jurisdictions
        and request_jurisdictions
        and not claim_jurisdictions.issubset(request_jurisdictions)
    ):
        _add_gate(
            gates,
            "claim_jurisdiction_not_applicable",
            field="jurisdiction_scope",
            message="Claim jurisdiction scope does not fit the request.",
        )

    date_scope = claim.get("effective_date_scope")
    if isinstance(date_scope, Mapping):
        as_of = str(context.get("as_of_date") or "")
        valid_from = str(date_scope.get("valid_from") or "")
        valid_to = str(date_scope.get("valid_to") or "")
        if valid_from and as_of and as_of < valid_from:
            _add_gate(
                gates,
                "claim_not_effective_yet",
                field="effective_date_scope",
                message="Claim is not effective at the requested date.",
            )
        if valid_to and as_of and as_of > valid_to:
            _add_gate(
                gates,
                "claim_effective_date_expired",
                field="effective_date_scope",
                message="Claim is expired at the requested date.",
            )
    return gates


def _private_permission_gates(
    selected_claims: list[Mapping[str, Any]],
    sources: Mapping[str, Mapping[str, Any]],
    context: Mapping[str, Any],
) -> list[dict[str, str]]:
    if not context.get("external_model_route") or context.get("allow_private_sources"):
        return []
    gates: list[dict[str, str]] = []
    for claim in selected_claims:
        source = sources.get(str(claim.get("source_id") or ""))
        privacy_class = str((source or {}).get("privacy_class") or "")
        if privacy_class in PRIVATE_PRIVACY_CLASSES:
            _add_gate(
                gates,
                "private_source_permission_required",
                field="privacy_class",
                message="Private source evidence needs explicit permission before external-model use.",
            )
    return gates


def _claim_validity_gates(
    selected_claims: list[Mapping[str, Any]],
    sources: Mapping[str, Mapping[str, Any]],
    lifecycle: Mapping[str, Any],
) -> list[dict[str, str]]:
    gates: list[dict[str, str]] = []
    lifecycle_claims = lifecycle.get("claims") if isinstance(lifecycle, Mapping) else {}
    lifecycle_sources = lifecycle.get("sources") if isinstance(lifecycle, Mapping) else {}
    for claim in selected_claims:
        report = schema.validate_knowledge_claim(claim, sources=sources, high_stakes=True)
        claim_id = str(claim.get("claim_id") or "")
        source_id = str(claim.get("source_id") or "")
        claim_state = (lifecycle_claims or {}).get(claim_id) or {}
        source_state = (lifecycle_sources or {}).get(source_id) or {}
        effective_promotion = str(claim_state.get("effective_promotion_status") or "")
        effective_source = str(source_state.get("effective_status") or "")
        if not report["promotion_eligible"]:
            _add_gate(
                gates,
                "claim_not_promotion_eligible",
                field="claim_id",
                message="Selected high-risk claim is not promotion eligible.",
            )
        for blocker_code in string_list_or_empty(report.get("blocker_codes")):
            _add_gate(
                gates,
                f"claim_blocker:{blocker_code}",
                field="claim_id",
                message="Knowledge-claim schema blocker prevents high-risk answer use.",
            )
        source_report = report.get("source_report")
        if isinstance(source_report, Mapping):
            for blocker_code in string_list_or_empty(source_report.get("blocker_codes")):
                _add_gate(
                    gates,
                    f"source_blocker:{blocker_code}",
                    field="source_id",
                    message="Knowledge-source schema blocker prevents high-risk answer use.",
                )
        if effective_promotion and effective_promotion != "activated":
            _add_gate(
                gates,
                f"claim_effective_status:{effective_promotion}",
                field="promotion_status",
                message="Lifecycle state prevents this claim from supporting an answer.",
            )
        if effective_source in INACTIVE_EFFECTIVE_SOURCE_STATUSES:
            _add_gate(
                gates,
                f"source_effective_status:{effective_source}",
                field="source_id",
                message="Lifecycle state prevents this source from supporting an answer.",
            )
    return gates


def _conflict_sets(
    selected_claims: list[Mapping[str, Any]],
    all_claims: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    selected_sets = {
        str(claim.get("conflict_set_id") or "")
        for claim in selected_claims
        if claim.get("conflict_set_id")
    }
    conflicts: list[dict[str, Any]] = []
    for conflict_set_id in sorted(selected_sets):
        members = [
            claim
            for claim in all_claims.values()
            if str(claim.get("conflict_set_id") or "") == conflict_set_id
        ]
        uncleared = [
            claim
            for claim in members
            if str(claim.get("conflict_status") or "") not in CLEAR_CONFLICT_STATUSES
            or str(claim.get("promotion_status") or "") in {"uncertain", "blocked"}
        ]
        if not uncleared:
            continue
        conflicts.append(
            {
                "conflict_set_id": conflict_set_id,
                "claim_ids": sorted(str(claim.get("claim_id") or "") for claim in members),
                "source_ids": sorted(str(claim.get("source_id") or "") for claim in members),
                "domain_scopes": sorted(
                    {
                        scope
                        for claim in members
                        for scope in string_list_or_empty(claim.get("claim_scope"))
                    }
                ),
                "jurisdiction_scopes": sorted(
                    {
                        scope
                        for claim in members
                        for scope in string_list_or_empty(claim.get("jurisdiction_scope"))
                    }
                ),
                "resolution": "human_review_required",
            }
        )
    return conflicts


def _cited_boundaries(
    selected_claims: list[Mapping[str, Any]],
    sources: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    boundaries: list[dict[str, Any]] = []
    for claim in selected_claims:
        source = sources.get(str(claim.get("source_id") or "")) or {}
        boundaries.append(
            {
                "claim_id": claim.get("claim_id"),
                "source_id": claim.get("source_id"),
                "source_anchor": claim.get("source_anchor"),
                "authority_level": claim.get("authority_level"),
                "evidence_grade": source.get("evidence_grade"),
                "domain_scope": string_list_or_empty(claim.get("claim_scope")),
                "jurisdiction_scope": string_list_or_empty(claim.get("jurisdiction_scope")),
                "effective_date_scope": claim.get("effective_date_scope"),
                "conflict_status": claim.get("conflict_status"),
                "uncertainty_notes": claim.get("uncertainty_notes"),
            }
        )
    return boundaries


def _questions_for_gates(gates: list[dict[str, str]]) -> list[dict[str, str]]:
    questions: list[dict[str, str]] = []
    for gate in gates:
        if not gate["code"].startswith("missing_"):
            continue
        questions.append(
            {
                "field": gate["field"],
                "question": f"Provide {gate['field']} before high-risk answer formation.",
            }
        )
    return questions


def _report(
    *,
    output_state: str,
    gates: list[dict[str, str]],
    selected_claims: list[Mapping[str, Any]],
    sources: Mapping[str, Mapping[str, Any]],
    cannot_claim: list[str],
    conflict_sets: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    can_emit = output_state == "answer_with_cited_bounds"
    unique_cannot_claim = sorted(set(BASE_CANNOT_CLAIM + cannot_claim))
    return {
        "ok": output_state in OUTPUT_STATES,
        "policy_version": POLICY_VERSION,
        "output_state": output_state,
        "can_emit_high_risk_answer": can_emit,
        "gates": gates,
        "gate_codes": _gate_codes(gates),
        "questions": _questions_for_gates(gates),
        "conflict_sets": conflict_sets or [],
        "cited_boundaries": _cited_boundaries(selected_claims, sources) if can_emit else [],
        "cannot_claim": unique_cannot_claim,
        "source_boundary": {
            "evidence_required": "reopened_source_span",
            "routing_evidence_is_navigation_only": True,
            "source_text_exported": False,
            "claim_text_exported": False,
        },
        "privacy": {
            "source_text_allowed_external": False,
            "source_text_exported": False,
        },
    }


def evaluate_high_risk_answer_gate(
    payload: Mapping[str, Any],
    *,
    claim_ids: Sequence[str],
    evidence_items: Sequence[Mapping[str, Any]] | None = None,
    context: Mapping[str, Any] | None = None,
    required_context_keys: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Evaluate whether selected knowledge claims may support a high-risk answer.

    The gate treats embeddings, semantic matches, and generated summaries as
    routing evidence only. High-risk answer formation requires reopened source
    spans, applicable context, active lifecycle state, cleared conflicts, and a
    privacy boundary that does not export source text by default.
    """

    evidence_items = list(evidence_items or [])
    context = context or {}
    required_context_keys = list(required_context_keys or [])
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
    selected, missing_claim_ids = _selected_claims(claims, claim_ids)
    gates: list[dict[str, str]] = []
    cannot_claim: list[str] = []

    if missing_claim_ids:
        for claim_id in missing_claim_ids:
            _add_gate(
                gates,
                "missing_claim",
                field="claim_id",
                message=f"Claim {claim_id} does not resolve in the registry.",
            )
        return _report(
            output_state="refuse_or_redirect",
            gates=gates,
            selected_claims=selected,
            sources=sources,
            cannot_claim=["missing_claim_not_answerable"],
        )

    context_gates = _missing_context_gates(context, required_context_keys)
    if context_gates:
        return _report(
            output_state="missing_context_question",
            gates=context_gates,
            selected_claims=selected,
            sources=sources,
            cannot_claim=["missing_context_not_answerable"],
        )

    reopened_claim_ids = _reopened_claim_ids(evidence_items)
    missing_reopen = [
        str(claim.get("claim_id") or "")
        for claim in selected
        if str(claim.get("claim_id") or "") not in reopened_claim_ids
    ]
    if missing_reopen:
        _add_gate(
            gates,
            "source_reopen_required",
            field="evidence_items",
            message="High-risk claims require reopened source spans before answer emission.",
        )
        if _routing_only_kinds(evidence_items):
            cannot_claim.append("embedding_hit_is_navigation_only")
        return _report(
            output_state="source_reopen_required",
            gates=gates,
            selected_claims=selected,
            sources=sources,
            cannot_claim=cannot_claim,
        )

    applicability_gates: list[dict[str, str]] = []
    for claim in selected:
        applicability_gates.extend(_applicability_gates(claim, context))
    if applicability_gates:
        return _report(
            output_state="degrade_to_general_information",
            gates=applicability_gates,
            selected_claims=selected,
            sources=sources,
            cannot_claim=["claim_scope_not_applicable"],
        )

    privacy_gates = _private_permission_gates(selected, sources, context)
    if privacy_gates:
        return _report(
            output_state="human_review_required",
            gates=privacy_gates,
            selected_claims=selected,
            sources=sources,
            cannot_claim=["private_source_not_exportable_without_permission"],
        )

    lifecycle = schema.evaluate_knowledge_lifecycle(payload, high_stakes=True)
    validity_gates = _claim_validity_gates(selected, sources, lifecycle)
    if validity_gates:
        return _report(
            output_state="human_review_required",
            gates=validity_gates,
            selected_claims=selected,
            sources=sources,
            cannot_claim=["inactive_or_unpromoted_claim_not_answerable"],
        )

    conflicts = _conflict_sets(selected, claims)
    if conflicts:
        _add_gate(
            gates,
            "conflict_set_uncleared",
            field="conflict_set_id",
            message="Conflicting sources must remain visible and require review.",
        )
        return _report(
            output_state="human_review_required",
            gates=gates,
            selected_claims=selected,
            sources=sources,
            conflict_sets=conflicts,
            cannot_claim=["conflicting_sources_not_averaged"],
        )

    return _report(
        output_state="answer_with_cited_bounds",
        gates=[],
        selected_claims=selected,
        sources=sources,
        cannot_claim=[],
    )
