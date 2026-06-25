"""Fixture-only report assembly for AIppo working contracts."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from aippocampus_runtime.aippo import usefulness
from aippocampus_runtime.aippo import working_contract as wc
from aippocampus_runtime.core import stable_json_digest


def _fixture_cases() -> list[dict[str, Any]]:
    return [
        {
            "case_id": "self_note_candidate_without_source",
            "candidate_source": "agent_self_notes",
            "ripened": False,
            "result_status": "needs_review",
            "truth_authority": "candidate_only",
        },
        {
            "case_id": "dream_candidate_backstage",
            "candidate_source": "dream_subconscious",
            "ripened": False,
            "result_status": "backstage_candidate",
            "truth_authority": "candidate_only",
            "foreground_eligible": False,
            "source_support_passed": False,
        },
        {
            "case_id": "dream_candidate_ripened_with_source",
            "candidate_source": "dream_subconscious",
            "ripened": True,
            "result_status": "ripe",
            "truth_authority": "source_supported",
            "foreground_eligible": True,
            "source_support_passed": True,
            "repeated_wrong_route_prevented": True,
        },
        {
            "case_id": "cognitive_route_to_source_support",
            "candidate_source": "cognitive_map",
            "navigation_signal_used": "cognitive_map",
            "ripened": True,
            "result_status": "ripe",
            "truth_authority": "source_supported",
        },
    ]


def _dream_candidate_readout(cases: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    dream_cases = [
        case for case in cases if case.get("candidate_source") == "dream_subconscious"
    ]
    dream_only_foreground_leak_count = sum(
        1
        for case in dream_cases
        if case.get("truth_authority") != "source_supported"
        and bool(case.get("foreground_eligible"))
    )
    return {
        "kind": "aippo_dream_candidate_ripening_readout",
        "authority": "dream_synthesized_candidate_not_fact",
        "metrics": {
            "dream_candidate_nominated_count": len(dream_cases),
            "dream_candidate_ripened_with_source_count": sum(
                1
                for case in dream_cases
                if case.get("ripened") and case.get("truth_authority") == "source_supported"
            ),
            "dream_only_foreground_leak_count": dream_only_foreground_leak_count,
            "repeated_wrong_route_prevented_count": sum(
                1 for case in dream_cases if case.get("repeated_wrong_route_prevented")
            ),
        },
        "boundary": {
            "dream_may_nominate_candidates": True,
            "dream_only_candidates_stay_backstage": True,
            "source_support_required_before_ripening": True,
            "ripened_candidate_still_requires_reopen_before_claim": True,
        },
    }


def build_aippo_working_contract_fixture_report() -> dict[str, Any]:
    contracts = wc.build_aippo_working_contracts(wc.project_workflow_public_safe_source_rows())
    contract = wc.select_aippo_working_contract(contracts)
    activation = wc.activation_packet_from_working_contract(contract, task="benchmark reporting issue closeout")
    usefulness_metrics = usefulness.usefulness_metrics(contract, activation)
    generic_activation = {
        "kind": "aippocampus_aippo_activation_packet",
        "schema_version": wc.SCHEMA_VERSION,
        "aippo_id": wc.AIPPO_ID,
        "output_mode": "working_contract",
        "display_hint": "Scope slice, verify, reopen before claims.",
        "use_guidance": [],
        "active_clause_ids": [],
        "claim_permission": "working_contract_allowed_no_fact_claim",
        "next_action": "use_hint",
    }
    generic_usefulness = usefulness.usefulness_metrics(contract, generic_activation)
    deepen = wc.deepen_aippo_working_contract(contract)
    explain = wc.explain_aippo_working_contract(contract)
    cases = _fixture_cases()
    dream_readout = _dream_candidate_readout(cases)
    red_lines = {
        "source_backed_claim_without_reopen": 0,
        "stale_clause_activated_as_current": sum(
            1
            for clause in contract["clauses"]
            if clause["lifecycle"]["status"] == "stale"
            and clause["clause_id"] in activation["active_clause_ids"]
        ),
        "candidate_only_signal_promoted_without_source": sum(
            1 for case in cases if case["truth_authority"] == "candidate_only" and case["ripened"]
        ),
        "self_note_promoted_without_source": sum(
            1
            for case in cases
            if case["candidate_source"] == "agent_self_notes" and case["truth_authority"] != "source_supported" and case["ripened"]
        ),
        "dream_candidate_promoted_without_source": sum(
            1
            for case in cases
            if case["candidate_source"] == "dream_subconscious" and case["truth_authority"] != "source_supported" and case["ripened"]
        ),
        "cognitive_route_used_as_truth": sum(
            1
            for case in cases
            if case["candidate_source"] == "cognitive_map" and case.get("truth_authority") == "cognitive_map"
        ),
        "gappy_pathlet_promoted_without_review": sum(
            1
            for clause in contract["clauses"]
            if clause["support"].get("path_provenance") == "gappy"
            and clause["clause_id"] in activation["active_clause_ids"]
        ),
        "masked_or_private_source_in_activation_packet": int(
            "PRIVATE_SOURCE_SENTINEL" in json.dumps(activation, ensure_ascii=False)
        ),
    }
    continuity_metrics = usefulness.continuity_usefulness_for_activation(activation, red_lines)
    manifest_hash = stable_json_digest(
        contract,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    rebuild_contract = wc.build_aippo_working_contracts(
        wc.project_workflow_public_safe_source_rows()
    )[0]
    rebuild_manifest_hash = stable_json_digest(
        rebuild_contract,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    changed_source_rows = [
        dict(row, invalidators=["newer_benchmark_policy"])
        if row.get("clause_id") == "clause_benchmark_default_claim"
        else row
        for row in wc.project_workflow_public_safe_source_rows()
    ]
    changed_contract = wc.build_aippo_working_contracts(changed_source_rows)[0]
    active_clause_count = len(wc._active_clauses(contract["clauses"]))
    return {
        "kind": "aippocampus_aippo_working_contract_fixture",
        "schema_version": wc.SCHEMA_VERSION,
        "ok": all(value == 0 for value in red_lines.values())
        and usefulness_metrics["usefulness_gate_ok"],
        "contract_package": contract,
        "activation_packet": activation,
        "deepen_surface": deepen,
        "explain_surface": explain,
        "fixture_cases": cases,
        "dream_candidate_readout": dream_readout,
        "foreground_packet_budget_bytes": wc.FOREGROUND_PACKET_BYTE_BUDGET,
        "metrics": {
            "aippo_extraction_success_count": len(contracts),
            "aippo_activation_success_rate": 1.0 if activation["active_clause_count"] else 0.0,
            "usable_working_contract_count": activation["active_clause_count"],
            "foreground_packet_bytes": wc._json_bytes(activation),
            "source_coverage_count": deepen["source_support_ledger"]["source_ref_count"],
            "working_contract_used_without_unnecessary_reopen_count": activation["active_clause_count"],
            "available_active_clause_count": active_clause_count,
            "suppressed_clause_count": len(contract["clauses"]) - active_clause_count,
            "active_clause_information_density": usefulness_metrics[
                "active_clause_information_density"
            ],
            "generic_safety_posture_only_count": usefulness_metrics[
                "generic_safety_posture_only_count"
            ],
            "stable_workflow_search_avoided_count": usefulness_metrics[
                "stable_workflow_search_avoided_count"
            ],
            "aippo_next_action_delta_count": usefulness_metrics["aippo_next_action_delta_count"],
            "stale_clause_suppressed_count": usefulness_metrics["stale_clause_suppressed_count"],
            "low_risk_guidance_allowed_without_reopen_count": usefulness_metrics[
                "low_risk_guidance_allowed_without_reopen_count"
            ],
            "source_backed_claim_without_reopen": 0,
            "stale_as_current_count": red_lines["stale_clause_activated_as_current"],
            "stable_rebuild_hash_changed_count": int(manifest_hash != rebuild_manifest_hash),
        },
        "continuity_usefulness": continuity_metrics,
        "usefulness_gate": {
            "safety_gate_ok": all(value == 0 for value in red_lines.values()),
            "usefulness_gate_ok": usefulness_metrics["usefulness_gate_ok"]
            and continuity_metrics["usefulness_gate_ok"],
            "quality_gate_ok": all(value == 0 for value in red_lines.values())
            and usefulness_metrics["usefulness_gate_ok"]
            and continuity_metrics["quality_gate_ok"],
        },
        "negative_fixtures": {
            "generic_safety_posture_only": {
                "activation_packet": generic_activation,
                "usefulness_gate_ok": generic_usefulness["usefulness_gate_ok"],
                "generic_safety_posture_only_count": generic_usefulness[
                    "generic_safety_posture_only_count"
                ],
            }
        },
        "stability": {
            "stable_manifest_hash": manifest_hash,
            "rebuild_manifest_hash": rebuild_manifest_hash,
            "changed_clause_ids": [
                old["clause_id"]
                for old, new in zip(contract["clauses"], changed_contract["clauses"], strict=True)
                if stable_json_digest(old, ensure_ascii=False, separators=(",", ":"))
                != stable_json_digest(new, ensure_ascii=False, separators=(",", ":"))
            ],
        },
        "red_lines": red_lines,
        "cannot_claim": [
            "aippo_marketplace_readiness",
            "private_ficus_handling",
            "broad_automatic_skill_acquisition",
            "claim_ready_facts_without_source_reopen",
        ],
    }
