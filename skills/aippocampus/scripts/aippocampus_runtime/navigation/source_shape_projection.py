"""Cross-layer source-shape projection for learning-loop findings."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from aippocampus_runtime.aippo import working_contract
from aippocampus_runtime.hooks import action_hint_cache
from aippocampus_runtime.learning_loop import aippo_adapter
from aippocampus_runtime.navigation import local_global_compatibility, navigation_potential

SCHEMA_VERSION = 1
REPORT_KIND = "aippocampus_learning_source_shape_projection"
STALE_STATUSES = {"stale", "resolved", "refuted", "retired", "superseded"}


def _stable_id(prefix: str, *parts: Any) -> str:
    encoded = json.dumps(parts, ensure_ascii=False, sort_keys=True, default=str)
    return f"{prefix}_{hashlib.sha256(encoded.encode('utf-8')).hexdigest()[:16]}"


def _strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, Sequence):
        return [str(item) for item in value if str(item or "").strip()]
    return []


def _source_ids(refs: Any) -> list[str]:
    ids: list[str] = []
    if not isinstance(refs, Sequence) or isinstance(refs, (str, bytes)):
        return ids
    for ref in refs:
        if not isinstance(ref, Mapping):
            continue
        value = ref.get("source_id") or ref.get("source_ref") or ref.get("message_id")
        if value and str(value) not in ids:
            ids.append(str(value))
    return ids[:8]


def _finding_kind(row: Mapping[str, Any]) -> str:
    return str(row.get("finding_kind") or row.get("candidate_family") or "")


def _shape_for(row: Mapping[str, Any]) -> str:
    kind = _finding_kind(row)
    workflow = str(row.get("workflow_family") or "")
    if kind == "recurring_failure_finding":
        return "cycle"
    if workflow == "cheap_preflight_before_broad_test":
        return "weak_bridge"
    if workflow == "context_reopen_before_retry" or kind == "context_reopen_candidate":
        return "cut_point"
    if workflow == "environment_workaround_before_retry" or kind == "environment_workaround_candidate":
        return "weak_bridge"
    return "island"


def _macro_signal(row: Mapping[str, Any]) -> dict[str, Any]:
    kind = _finding_kind(row)
    workflow = str(row.get("workflow_family") or "")
    if kind == "recurring_failure_finding":
        pressure = "friction_counter_evidence_delta"
    elif workflow == "cheap_preflight_before_broad_test":
        pressure = "action_order_signal"
    elif workflow == "context_reopen_before_retry":
        pressure = "source_reopen_pressure"
    elif workflow == "environment_workaround_before_retry":
        pressure = "support_instability_timing_caution"
    else:
        pressure = "candidate_pressure"
    return {
        "kind": "macro_source_shape_signal",
        "pressure": pressure,
        "authority": "navigation_only",
        "source_reopen_required_before_claim": True,
    }


def _section_from_finding(row: Mapping[str, Any]) -> dict[str, Any]:
    source_ids = _source_ids(row.get("source_refs"))
    return {
        "case_id": str(row.get("finding_id") or _stable_id("learning", row)),
        "kind": "learning_loop_section",
        "scope": str(row.get("scope") or "project:AIppocampus"),
        "source_ids": source_ids,
        "topic_epoch": str(row.get("topic_epoch") or "learning-loop"),
        "freshness": str(row.get("freshness") or row.get("status") or "current"),
        "authority_level": "navigation_only",
        "claim_permission": "navigation_only_not_fact",
        "route_topic": " ".join(
            [
                _finding_kind(row),
                str(row.get("workflow_family") or ""),
                str(row.get("candidate_family") or ""),
            ]
        ),
    }


def _aippo_section(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "case_id": str(row.get("clause_id") or _stable_id("aippo", row)),
        "kind": "aippocampus_aippo_activation_packet",
        "scope": "project:AIppocampus",
        "source_ids": _source_ids(row.get("source_refs")),
        "topic_epoch": "learning-loop",
        "freshness": str(row.get("freshness") or "current"),
        "authority_level": "navigation_only",
        "claim_permission": "working_contract_allowed_no_fact_claim",
        "route_topic": str(row.get("guidance") or ""),
    }


def project_learning_findings_to_source_shape(
    findings: Iterable[Mapping[str, Any]],
    *,
    now_unix: float = 1000.0,
) -> dict[str, Any]:
    materialized = [dict(row) for row in findings if isinstance(row, Mapping)]
    active_findings = [
        row
        for row in materialized
        if str(row.get("status") or row.get("freshness") or "current").casefold()
        not in STALE_STATUSES
        and not str(row.get("scope") or "").casefold().startswith("machine:")
    ]
    aippo_rows = aippo_adapter.learning_findings_to_aippo_source_rows(active_findings)
    contract = working_contract.select_aippo_working_contract(
        working_contract.build_aippo_working_contracts(aippo_rows)
    )
    clauses = [clause for clause in contract.get("clauses") or [] if isinstance(clause, Mapping)]
    macro = [_macro_signal(row) for row in active_findings]
    topology = [
        {
            "kind": "source_shape_topology_signal",
            "shape": _shape_for(row),
            "trigger_job": "pattern_completion_learning_loop_review",
            "authority": "navigation_only",
            "source_reopen_required_before_claim": True,
        }
        for row in active_findings
    ]
    glue_rows = []
    for finding, clause_row in zip(active_findings, aippo_rows, strict=False):
        glue_rows.append(
            local_global_compatibility.evaluate_local_global_compatibility(
                [_section_from_finding(finding), _aippo_section(clause_row)],
                case_id=str(finding.get("finding_id") or "learning_aippo"),
            )
        )
    nav_projection = navigation_potential.build_navigation_potential_projection(
        cognitive_routes=[
            {
                "kind": "source_shape_learning_route",
                "route_id": str(clause.get("clause_id") or _stable_id("route", clause)),
                "status": "unresolved",
                "title": "Learned workflow route",
                "summary": clause.get("guidance") or "Learning-loop source shape route.",
                "route_cues": _strings(clause.get("applies_when")),
                "source_refs": clause.get("source_refs") or [],
                "source_thickness": "usable",
            }
            for clause in clauses
        ],
        topic_epoch="learning-loop",
    )
    cache_report = action_hint_cache.build_action_hint_cache_report(
        aippo_learned_clauses=clauses,
        now_unix=now_unix,
    )
    encoded = json.dumps(
        {
            "macro": macro,
            "topology": topology,
            "glue": glue_rows,
            "cache": cache_report,
            "nav": nav_projection,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    red_lines = {
        "authority_raised_above_navigation_only_count": int('"source_truth"' in encoded),
        "raw_private_or_local_path_leak_count": int("PRIVATE" in encoded or "C:\\" in encoded),
        "stale_or_local_only_foreground_count": 0,
    }
    return {
        "kind": REPORT_KIND,
        "schema_version": SCHEMA_VERSION,
        "ok": bool(active_findings)
        and cache_report["provider_counts"].get("aippo_learned_clause", 0) > 0
        and all(value == 0 for value in red_lines.values()),
        "source_shape_schema": {
            "carries_source_refs": True,
            "carries_scope_freshness_authority_invalidators": True,
            "provider_provenance": "learning_loop_to_aippo_to_action_hint",
        },
        "macro_signals": macro,
        "topology_signals": topology,
        "local_global_checks": glue_rows,
        "multi_pan_task_time_readout": {
            "source_ground_layer": "learning-loop source refs",
            "macro_layer": len(macro),
            "topology_layer": len(topology),
            "action_layer": len(clauses),
            "subconscious_layer": "pattern_completion_learning_loop_review",
            "task_time_compiler": "pending action selects provider match; layers do not raise authority",
        },
        "aippo_clause_seeds": aippo_rows,
        "prepared_action_hint_cache": cache_report,
        "navigation_projection": nav_projection,
        "suppressed_finding_count": len(materialized) - len(active_findings),
        "red_lines": red_lines,
        "cannot_claim": [
            "cross_layer_alignment_is_source_truth",
            "topology_shape_raises_authority",
            "local_global_glue_blocks_action",
        ],
    }


__all__ = ["project_learning_findings_to_source_shape"]
