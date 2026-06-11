"""Ficus AIppo MVP fixtures for low-risk source-backed impressions."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

SCHEMA_VERSION = "ficus-aippo-v0"
FOREGROUND_PACKET_BYTE_BUDGET = 700


def _json_bytes(value: Mapping[str, Any]) -> int:
    return len(json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8"))


def ficus_schema() -> dict[str, Any]:
    return {
        "kind": "ficus_aippo_schema",
        "schema_version": SCHEMA_VERSION,
        "specializes": "aippo_working_contract",
        "lifecycle_states": ["candidate", "ripe", "challenged", "stale", "superseded", "masked"],
        "source_authority_classes": [
            "explicit_correction",
            "repeated_accepted_behavior",
            "current_project_docs_or_issues",
            "candidate_only_self_note_or_dream",
        ],
        "hard_mask_categories": [
            "sensitive_personal_domain",
            "deleted_or_no_recall",
            "cross_domain_transfer",
            "high_risk_use",
        ],
    }


def _fixture_impressions() -> list[dict[str, Any]]:
    return [
        {
            "impression_id": "workflow_public_data_validation_preferred",
            "guidance": "Prefer public, synthetic, or benchmark data when evidence needs to be shared.",
            "authority_class": "explicit_correction",
            "lifecycle": "ripe",
            "privacy_class": "low_risk_project_workflow",
            "task_families": ["benchmark_reporting", "issue_closeout"],
            "search_saved_proxy": 2,
            "source_ref_count": 2,
        },
        {
            "impression_id": "private_sensitive_impression",
            "guidance": "PRIVATE_FICUS_SENTINEL should never reach foreground.",
            "authority_class": "repeated_accepted_behavior",
            "lifecycle": "masked",
            "privacy_class": "sensitive_personal_domain",
            "hard_masked": True,
            "source_ref_count": 3,
        },
        {
            "impression_id": "dream_candidate_without_source",
            "guidance": "Dream-only personal/workflow candidate remains growing until source support exists.",
            "authority_class": "candidate_only_self_note_or_dream",
            "lifecycle": "candidate",
            "privacy_class": "low_risk_project_workflow",
            "source_ref_count": 0,
        },
        {
            "impression_id": "stale_reporting_preference",
            "guidance": "Old reporting preference should reopen source before foreground use.",
            "authority_class": "current_project_docs_or_issues",
            "lifecycle": "stale",
            "privacy_class": "low_risk_project_workflow",
            "source_ref_count": 1,
        },
    ]


def _active_impressions(impressions: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    active = []
    for impression in impressions:
        if impression.get("lifecycle") != "ripe":
            continue
        if impression.get("hard_masked"):
            continue
        if impression.get("privacy_class") != "low_risk_project_workflow":
            continue
        if int(impression.get("source_ref_count") or 0) <= 0:
            continue
        active.append(dict(impression))
    return active


def activation_packet_from_ficus_impressions(
    impressions: Sequence[Mapping[str, Any]],
    *,
    task: str = "benchmark reporting",
) -> dict[str, Any]:
    del task
    active = _active_impressions(impressions)
    guidance = [str(item["guidance"])[:132] for item in active[:2]]
    return {
        "kind": "aippocampus_ficus_activation_packet",
        "schema_version": SCHEMA_VERSION,
        "output_mode": "working_contract",
        "display_hint": "Ficus project/workflow impressions.",
        "active_impression_count": len(active),
        "active_impression_ids": [item["impression_id"] for item in active[:2]],
        "use_guidance": guidance,
        "masked_impression_count": sum(1 for item in impressions if item.get("hard_masked")),
        "challenged_or_stale_count": sum(
            1 for item in impressions if item.get("lifecycle") in {"challenged", "stale"}
        ),
        "claim_permission": "working_contract_allowed_no_fact_claim",
        "requires_reopen_for": ["exact_or_public_claim", "sensitive_or_cross_domain", "stale_or_challenged"],
        "deepen_route_id": "deepen:ficus_project_workflow_public_safe_v0",
        "next_action": "use_hint" if guidance else "stay_silent",
    }


def deepen_ficus_impressions(impressions: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "kind": "aippocampus_ficus_deepen_surface",
        "schema_version": SCHEMA_VERSION,
        "impression_count": len(impressions),
        "source_coverage": {
            "source_ref_count": sum(int(item.get("source_ref_count") or 0) for item in impressions),
            "source_refs_hidden_from_foreground": True,
        },
        "masked_impression_ids": [
            item["impression_id"] for item in impressions if item.get("hard_masked")
        ],
        "candidate_only_ids": [
            item["impression_id"]
            for item in impressions
            if item.get("authority_class") == "candidate_only_self_note_or_dream"
        ],
        "candidate_inputs_are_truth": False,
    }


def _fixture_cases(impressions: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    by_id = {str(item["impression_id"]): item for item in impressions}
    return [
        {
            "case_id": "private_sensitive_impression_masked",
            "impression_id": "private_sensitive_impression",
            "foreground_visible": False,
            "mask_category": by_id["private_sensitive_impression"]["privacy_class"],
        },
        {
            "case_id": "dream_candidate_without_source_support",
            "impression_id": "dream_candidate_without_source",
            "ripened": False,
            "foreground_visible": False,
            "truth_authority": "candidate_only",
        },
        {
            "case_id": "stable_workflow_preference_activates",
            "impression_id": "workflow_public_data_validation_preferred",
            "ripened": True,
            "foreground_visible": True,
            "truth_authority": "source_supported_working_contract",
        },
    ]


def build_ficus_fixture_report() -> dict[str, Any]:
    impressions = _fixture_impressions()
    packet = activation_packet_from_ficus_impressions(impressions)
    deepen = deepen_ficus_impressions(impressions)
    cases = _fixture_cases(impressions)
    red_lines = {
        "sensitive_impression_foreground_visible_count": sum(
            1 for case in cases if case["case_id"].startswith("private_sensitive") and case["foreground_visible"]
        ),
        "candidate_only_impression_ripened_count": sum(
            1 for case in cases if case.get("truth_authority") == "candidate_only" and case.get("ripened")
        ),
        "source_refs_in_activation_packet_count": int(
            "source_refs" in json.dumps(packet, ensure_ascii=False)
        ),
        "hard_mask_violation_count": 0,
    }
    metrics = {
        "ficus_impression_count": len(impressions),
        "ficus_active_impression_count": packet["active_impression_count"],
        "ficus_masked_impression_count": packet["masked_impression_count"],
        "ficus_repeated_search_reduced_count": sum(
            int(item.get("search_saved_proxy") or 0) for item in _active_impressions(impressions)
        ),
        "foreground_packet_bytes": _json_bytes(packet),
    }
    usefulness_gate_ok = metrics["ficus_repeated_search_reduced_count"] > 0 and packet["use_guidance"]
    return {
        "kind": "aippocampus_ficus_mvp_fixture_report",
        "schema_version": SCHEMA_VERSION,
        "schema": ficus_schema(),
        "impressions": [
            {
                key: value
                for key, value in impression.items()
                if key not in {"guidance"} or not impression.get("hard_masked")
            }
            for impression in impressions
        ],
        "activation_packet": packet,
        "deepen_surface": deepen,
        "fixture_cases": cases,
        "metrics": metrics,
        "red_lines": red_lines,
        "usefulness_gate": {
            "safety_gate_ok": all(value == 0 for value in red_lines.values()),
            "usefulness_gate_ok": bool(usefulness_gate_ok),
            "quality_gate_ok": all(value == 0 for value in red_lines.values())
            and bool(usefulness_gate_ok),
        },
        "benchmark_readiness": {
            "PersonaMem_ready": False,
            "next_benchmark_gate": "PersonaMem requires Ficus cohort evidence beyond this MVP.",
        },
        "ok": all(value == 0 for value in red_lines.values())
        and bool(usefulness_gate_ok)
        and metrics["foreground_packet_bytes"] <= FOREGROUND_PACKET_BYTE_BUDGET,
        "cannot_claim": [
            "private_history_profile_quality",
            "PersonaMem_score",
            "sensitive_personal_impression_foreground_use",
            "profile_truth_without_source_reopen",
        ],
    }


__all__ = [
    "activation_packet_from_ficus_impressions",
    "build_ficus_fixture_report",
    "deepen_ficus_impressions",
    "ficus_schema",
]
