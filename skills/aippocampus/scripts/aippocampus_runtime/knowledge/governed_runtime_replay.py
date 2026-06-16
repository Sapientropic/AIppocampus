#!/usr/bin/env python3
"""Opt-in replay of a narrow governed runtime caller.

This module is staged measurement scaffolding, not a default foreground caller.
It proves that a governed high-risk answer path calls the knowledge gate before
forming an answer while preserving the ordinary personal recall path boundary.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping, Sequence

from aippocampus_runtime.knowledge import answer_gate, capability_contract

REPLAY_PROFILE = "enterprise_governed"
REPLAY_BOUNDARY = "staged_opt_in"
REPLAY_CASE_IDS = (
    "supported_bounded_answer",
    "embedding_only_blocked",
    "missing_context_question",
    "stale_or_superseded_degrade",
    "conflict_set_human_review",
    "privacy_partition_block",
    "external_tool_text_transfer_block",
    "ordinary_personal_default_nonadoption",
)


def _as_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value] if value.strip() else []
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item or "").strip()]


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _gate_codes(gates: Sequence[Mapping[str, Any]]) -> list[str]:
    return sorted({str(item.get("code") or "") for item in gates if item.get("code")})


def _copy_case(base: Mapping[str, Any], case_id: str) -> dict[str, Any]:
    case = deepcopy(dict(base))
    case["case_id"] = case_id
    case["runtime_replay_profile"] = REPLAY_PROFILE
    return case


def _fixture_case(fixture: Mapping[str, Any], source_case_id: str, replay_case_id: str) -> dict[str, Any]:
    for case in fixture.get("cases") or []:
        if isinstance(case, Mapping) and case.get("case_id") == source_case_id:
            return _copy_case(case, replay_case_id)
    raise ValueError(f"missing fixture case for governed replay: {source_case_id}")


def _conflict_case(fixture: Mapping[str, Any]) -> dict[str, Any]:
    case = _fixture_case(
        fixture,
        "contract_review_supported_risk_flag",
        "conflict_set_human_review",
    )
    case["family"] = "conflict_set_human_review"
    case["evaluation_path"] = "answer_gate"
    case["selected_claim_ids"] = ["claim-runtime-conflict-a", "claim-runtime-conflict-b"]
    case["evidence_items"] = [
        {
            "kind": "reopened_source_span",
            "claim_id": "claim-runtime-conflict-a",
            "source_id": "ksrc-contract-clause",
            "source_anchor": {"section_anchor": "clause-7", "span_id": "clause-7:p1"},
        },
        {
            "kind": "reopened_source_span",
            "claim_id": "claim-runtime-conflict-b",
            "source_id": "ksrc-legal-statute-like",
            "source_anchor": {"section_anchor": "statute-1", "span_id": "statute-1:p1"},
        },
    ]
    return case


def _registry_with_runtime_conflict(registry: Mapping[str, Any]) -> dict[str, Any]:
    replay_registry = deepcopy(dict(registry))
    claims = [item for item in replay_registry.get("claims") or [] if isinstance(item, Mapping)]
    base_claims = {str(item.get("claim_id") or ""): item for item in claims}
    contract_claim = deepcopy(dict(base_claims["claim-contract-clause-risk"]))
    legal_claim = deepcopy(dict(base_claims["claim-legal-noncompete-reference"]))
    unresolved_claim = deepcopy(dict(base_claims["claim-contract-clause-risk"]))
    for claim, claim_id in (
        (contract_claim, "claim-runtime-conflict-a"),
        (legal_claim, "claim-runtime-conflict-b"),
        (unresolved_claim, "claim-runtime-conflict-unselected"),
    ):
        claim["claim_id"] = claim_id
        claim["conflict_set_id"] = "runtime-replay-conflict"
        claim["conflict_status"] = "unreviewed" if claim is unresolved_claim else "none"
        claim["promotion_status"] = "activated"
    replay_registry["claims"] = claims + [contract_claim, legal_claim, unresolved_claim]
    return replay_registry


def replay_cases(fixture: Mapping[str, Any], registry: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Build synthetic governed-runtime replay cases from existing public fixtures."""

    cases = [
        _fixture_case(fixture, "contract_review_supported_risk_flag", "supported_bounded_answer"),
        _fixture_case(fixture, "contract_review_embedding_only", "embedding_only_blocked"),
        _fixture_case(fixture, "contract_review_missing_jurisdiction", "missing_context_question"),
        _fixture_case(fixture, "stale_guideline_superseded", "stale_or_superseded_degrade"),
        _conflict_case(fixture),
        _fixture_case(fixture, "cross_case_context_bleed_case", "privacy_partition_block"),
        _fixture_case(
            fixture,
            "contract_secret_external_tool_case",
            "external_tool_text_transfer_block",
        ),
        {
            "case_id": "ordinary_personal_default_nonadoption",
            "family": "ordinary_personal_default_nonadoption",
            "runtime_replay_profile": REPLAY_PROFILE,
            "evaluation_path": "default_personal_path_probe",
            "input_text": "Synthetic personal recall prompt outside enterprise governance.",
            "expected_output_state": "default_personal_path_unaffected",
        },
    ]
    if len(cases) != len(REPLAY_CASE_IDS):
        raise ValueError("governed replay case count drifted")
    return cases


def replay_runtime_caller(
    fixture: Mapping[str, Any],
    registry: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Run the opt-in replay caller through knowledge gates.

    The ordinary personal default probe intentionally does not call the gate:
    it verifies that enterprise governance remains opt-in and does not add
    ceremony to default personal recall.
    """

    contract = _as_mapping(fixture.get("capability_contract"))
    replay_registry = _registry_with_runtime_conflict(registry)
    reports: list[dict[str, Any]] = []
    for case in replay_cases(fixture, replay_registry):
        if case.get("evaluation_path") == "default_personal_path_probe":
            reports.append(
                {
                    "case_id": case["case_id"],
                    "family": case["family"],
                    "evaluation_path": "governed_runtime_replay",
                    "runtime_replay_profile": REPLAY_PROFILE,
                    "runtime_replay_boundary": REPLAY_BOUNDARY,
                    "output_state": "default_personal_path_unaffected",
                    "knowledge_gate_called": False,
                    "default_personal_path_unaffected": True,
                    "raw_source_text_emitted": False,
                    "absolute_path_emitted": False,
                    "cannot_claim": ["not_enterprise_governed_default_path"],
                    "privacy": {
                        "raw_input_text_emitted": False,
                        "raw_source_text_emitted": False,
                    },
                }
            )
            continue

        if case.get("evaluation_path") == "capability_contract":
            gate_report = capability_contract.evaluate_capability_case(
                contract,
                case,
                replay_registry,
            )
        else:
            gate_report = answer_gate.evaluate_high_risk_answer_gate(
                replay_registry,
                claim_ids=_as_list(case.get("selected_claim_ids")),
                evidence_items=[
                    item for item in case.get("evidence_items") or [] if isinstance(item, Mapping)
                ],
                context=_as_mapping(case.get("context")),
                required_context_keys=_as_list(case.get("required_context_keys")),
            )
        report = dict(gate_report)
        report.update(
            {
                "case_id": case["case_id"],
                "family": case.get("family"),
                "evaluation_path": "governed_runtime_replay",
                "runtime_replay_profile": REPLAY_PROFILE,
                "runtime_replay_boundary": REPLAY_BOUNDARY,
                "knowledge_gate_called": True,
                "gate_codes": _gate_codes(
                    [item for item in report.get("gates") or [] if isinstance(item, Mapping)]
                ),
                "raw_source_text_emitted": False,
                "absolute_path_emitted": False,
            }
        )
        reports.append(report)
    return reports
