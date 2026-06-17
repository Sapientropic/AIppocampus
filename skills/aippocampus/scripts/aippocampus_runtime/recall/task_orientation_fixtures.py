"""Fixture catalogs for Task Orientation Packets.

Keep these public-safe and deterministic. They orient route selection and
benchmark smoke checks; they are not source evidence or private replay output.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from typing import Any

from aippocampus_runtime.privacy import redact_private_paths, redact_sensitive_values

SCHEMA_VERSION = "task-orientation-v1"
FOREGROUND_BYTE_BUDGET = 12000


def _public_payload(payload: Any) -> Any:
    return redact_sensitive_values(redact_private_paths(payload))


def stable_id(*parts: Any) -> str:
    raw = "\n".join(str(part or "") for part in parts)
    return "top_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def source_ref(kind: str, key: str, line: int = 1) -> dict[str, Any]:
    del line
    return {
        "source_id": f"{kind}:{key}",
    }


def build_external_source_anchors(task: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    base = [
        {
            "anchor_id": "github_issue_task_orientation",
            "source_kind": "github_issue",
            "project_role": "current_requirement_thread",
            "public_ref": "#2120-#2126",
            "entered_via": "issue_intake",
            "lifecycle_status": "current",
            "freshness": "current_until_issue_recheck",
        },
        {
            "anchor_id": "agent_native_recall_facade_doc",
            "source_kind": "documentation",
            "project_role": "implementation_boundary",
            "public_ref": "docs/architecture/recall/agent-native-recall-facade.md",
            "entered_via": "repo_doc",
            "lifecycle_status": "current",
            "freshness": "current_contract",
        },
        {
            "anchor_id": "discussion_atlas_task_orientation",
            "source_kind": "github_discussion",
            "project_role": "design_input",
            "public_ref": "docs/research/discussion-atlas.md",
            "entered_via": "discussion_atlas",
            "lifecycle_status": "current",
            "freshness": "current_navigation_index",
        },
        {
            "anchor_id": "research_reference_continuity_systems",
            "source_kind": "research_reference",
            "project_role": "background_counterpoint",
            "public_ref": stable_id("research_reference", task),
            "entered_via": "external_source_anchor",
            "lifecycle_status": "review_required",
            "freshness": "unknown_until_reopened",
        },
    ]
    suppressed = [
        {
            "anchor_id": "superseded_planning_note_example",
            "source_kind": "planning_note",
            "project_role": "historical_context_only",
            "public_ref": stable_id("superseded", task),
            "entered_via": "external_source_anchor",
            "lifecycle_status": "superseded",
            "freshness": "superseded",
        },
        {
            "anchor_id": "stale_paper_claim_example",
            "source_kind": "research_reference",
            "project_role": "do_not_claim_without_fresh_review",
            "public_ref": stable_id("stale_paper", task),
            "entered_via": "external_source_anchor",
            "lifecycle_status": "stale",
            "freshness": "stale",
        },
    ]
    for anchor in base:
        anchor.update(
            {
                "authority": "route_not_evidence",
                "safe_use": "reopen_before_claim",
                "reopen_requirement": "open_source_or_issue_before_quoting_or_closing",
                "privacy_boundary": "public_safe_ref_only",
            }
        )
    for anchor in suppressed:
        anchor.update(
            {
                "authority": "route_not_evidence",
                "safe_use": "do_not_rank_as_current_route",
                "reopen_requirement": "human_or_source_review_required_before_reuse",
                "privacy_boundary": "public_safe_ref_only",
            }
        )
    return base, suppressed


def build_learning_constraints(issue_packet: Mapping[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    active = [
        {
            "constraint_id": "aippo_working_contract_source_reopen",
            "source": "aippo_working_contract",
            "summary": "Use working guidance for planning only; reopen source before claims.",
            "authority": "navigation_only_not_fact",
            "route_status": "ready",
            "source_refs": [source_ref("runtime", "aippo.working_contract", 1)],
            "reason_codes": ["aippo_constraint", "source_reopen_before_claim"],
        },
    ]
    if issue_packet.get("should_pull"):
        active.insert(
            0,
            {
                "constraint_id": "issue_work_guard_active_pull",
                "source": "issue_work_guard",
                "summary": "Check existing route owners before broad manual scaffolding.",
                "authority": "navigation_only_not_fact",
                "route_status": "ready",
                "source_refs": [source_ref("runtime", "ops.issue_work_guard", 1)],
                "reason_codes": list(issue_packet.get("constraints") or ["issue_work_guard"]),
            },
        )
    suppressed = [
        {
            "constraint_id": "unripe_private_replay_signal",
            "source": "learning_loop",
            "summary": "Private replay aggregate can evaluate later, but is not default foreground route evidence.",
            "authority": "navigation_only_not_fact",
            "route_status": "suppressed",
            "suppression_reason": "opt_in_private_aggregate_only",
            "source_refs": [],
        }
    ]
    return active, suppressed


def compact_active_path_packet(active_path: Mapping[str, Any]) -> dict[str, Any]:
    paths: list[dict[str, Any]] = []
    for path in active_path.get("paths") or []:
        if not isinstance(path, Mapping):
            continue
        boundary = path.get("source_boundary") if isinstance(path.get("source_boundary"), Mapping) else {}
        paths.append(
            {
                "path_id": path.get("path_id"),
                "title": path.get("title"),
                "route": path.get("route"),
                "currentness": path.get("currentness"),
                "next_action": path.get("next_action"),
                "confidence": path.get("confidence"),
                "origin": path.get("origin"),
                "reason_codes": list(path.get("reason_codes") or [])[:4],
                "source_refs": list(path.get("source_refs") or [])[:2],
                "source_boundary": {
                    "navigation_not_truth": boundary.get("navigation_not_truth", True),
                    "source_reopen_required": boundary.get("source_reopen_required", False),
                    "unsafe_to_use_as_current_fact": boundary.get("unsafe_to_use_as_current_fact", False),
                },
            }
        )
    return {
        "kind": active_path.get("kind"),
        "schema_version": active_path.get("schema_version"),
        "purpose": active_path.get("purpose"),
        "paths": paths,
        "path_count": len(paths),
        "privacy": {
            "raw_source_text_serialized": False,
            "local_paths_serialized": False,
            "external_model_calls": False,
        },
        "source_boundary": {
            "navigation_not_truth": True,
            "non_evidence_paths_require_source_reopen_before_claim": True,
            "stale_or_suppressed_paths_are_boundaries": True,
        },
        "metrics": {
            "candidate_count": (active_path.get("metrics") or {}).get("candidate_count", 0),
            "selected_count": len(paths),
            "stale_or_superseded_path_count": (active_path.get("metrics") or {}).get("stale_or_superseded_path_count", 0),
        },
        "no_write": True,
    }


def route_plan_from_active_path(active_path: Mapping[str, Any]) -> dict[str, Any]:
    paths = [path for path in active_path.get("paths") or [] if isinstance(path, Mapping)]
    reopen = [path for path in paths if path.get("route") == "reopen"]
    ignored = [path for path in paths if path.get("route") == "ignore"]
    return {
        "first_sources_to_reopen": [
            {
                "path_id": path.get("path_id"),
                "title": path.get("title"),
                "why": "orientation route; reopen before relying on it",
            }
            for path in reopen[:3]
        ],
        "stop_conditions": [
            "stop if the chosen route is stale, superseded, private, or missing source",
            "stop broad search once a source-backed route answers the load-bearing unknown",
            "ask the user if no route can decide the next action",
        ],
        "suppressed_boundary_count": len(ignored),
    }


def compact_issue_work_guard(issue_packet: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "kind": issue_packet.get("kind"),
        "schema_version": issue_packet.get("schema_version"),
        "should_pull": bool(issue_packet.get("should_pull")),
        "output_mode": issue_packet.get("output_mode"),
        "suggested_agent_action": issue_packet.get("suggested_agent_action"),
        "lead_kinds": list(issue_packet.get("lead_kinds") or []),
        "existing_owner_ref_ids": list(issue_packet.get("existing_owner_ref_ids") or []),
        "owner_refs_confidence": issue_packet.get("owner_refs_confidence"),
        "constraints": list(issue_packet.get("constraints") or []),
        "claim_permission": issue_packet.get("claim_permission"),
        "not_enough_for_claim": bool(issue_packet.get("not_enough_for_claim", True)),
    }


def build_task_orientation_eval_report() -> dict[str, Any]:
    route_only = {
        "broad_manual_search_count": 2,
        "blind_deepen_count": 2,
        "repeated_wrong_route_count": 1,
        "source_truth_overclaim_count": 0,
        "field_bloat_score": 2,
        "raw_private_text_leak_count": 0,
    }
    static = {
        "broad_manual_search_count": 3,
        "blind_deepen_count": 1,
        "repeated_wrong_route_count": 1,
        "source_truth_overclaim_count": 0,
        "field_bloat_score": 1,
        "raw_private_text_leak_count": 0,
    }
    top = {
        "broad_manual_search_count": 1,
        "blind_deepen_count": 0,
        "repeated_wrong_route_count": 1,
        "source_truth_overclaim_count": 0,
        "field_bloat_score": 1,
        "raw_private_text_leak_count": 0,
    }
    top_plus = {
        "broad_manual_search_count": 1,
        "blind_deepen_count": 0,
        "repeated_wrong_route_count": 0,
        "source_truth_overclaim_count": 0,
        "field_bloat_score": 1,
        "raw_private_text_leak_count": 0,
    }
    return _public_payload(
        {
            "kind": "aippocampus_task_orientation_eval_report",
            "schema_version": SCHEMA_VERSION,
            "ok": (
                top["broad_manual_search_count"] < static["broad_manual_search_count"]
                and top["blind_deepen_count"] < static["blind_deepen_count"]
                and top_plus["repeated_wrong_route_count"]
                <= route_only["repeated_wrong_route_count"]
                and top["source_truth_overclaim_count"] == 0
                and top_plus["source_truth_overclaim_count"] == 0
                and top["raw_private_text_leak_count"] == 0
            ),
            "claim_boundary": "public_fixture_only_not_live_quality_claim",
            "condition_order": [
                "route_only_source_backed_recall",
                "static_summary_baseline",
                "task_orientation_packet",
                "task_orientation_plus_constraints",
            ],
            "conditions": {
                "route_only_source_backed_recall": route_only,
                "static_summary_baseline": static,
                "task_orientation_packet": top,
                "task_orientation_plus_constraints": top_plus,
            },
            "metrics": {
                "condition_count": 4,
                "overclaim_regression": False,
                "usability_improved_without_source_truth_regression": True,
            },
            "fixture_cases": [
                {"case_id": "complete", "expects": "first route plus boundary"},
                {"case_id": "partial", "expects": "unknowns plus ask/deepen action"},
                {"case_id": "stale_anchor", "expects": "suppress as current route"},
                {"case_id": "conflicted", "expects": "review before claim"},
                {"case_id": "missing_source", "expects": "ask or rerun recall"},
                {"case_id": "foreground_too_heavy", "expects": "fail field-bloat gate"},
            ],
            "private_replay": {
                "enabled_by_default": False,
                "aggregate_only": True,
                "opt_in_required": True,
                "raw_private_examples_serialized": False,
            },
        }
    )
