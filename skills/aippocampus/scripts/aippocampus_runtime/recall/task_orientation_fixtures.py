"""Fixture catalogs for Task Orientation Packets.

Keep these public-safe and deterministic. They orient route selection and
benchmark smoke checks; they are not source evidence or private replay output.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from aippocampus_runtime.learning_loop import aippo_adapter, semantic_learning
from aippocampus_runtime.learning_loop.private_export import (
    LearningReplayInputError,
    load_behavior_event_rows,
)
from aippocampus_runtime.learning_loop.private_replay import (
    build_private_history_replay_report,
)
from aippocampus_runtime.privacy import redact_private_paths, redact_sensitive_values
from aippocampus_runtime.recall import source_backed_lessons

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


def _tiny_source_refs(value: Any, *, limit: int = 1) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    if not isinstance(value, list):
        return refs
    for item in value:
        if not isinstance(item, Mapping):
            continue
        source_id = item.get("source_id") or item.get("source_ref") or item.get("message_id")
        if not source_id:
            continue
        ref = {"source_id": str(source_id)[:160]}
        if ref not in refs:
            refs.append(ref)
        if len(refs) >= limit:
            break
    return refs


def build_external_source_anchors(task: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    base = [
        {
            "anchor_id": "github_issue_task_orientation",
            "source_kind": "github_issue",
            "project_role": "current_requirement_thread",
            "lifecycle_status": "current",
        },
        {
            "anchor_id": "agent_native_recall_facade_doc",
            "source_kind": "documentation",
            "project_role": "implementation_boundary",
            "lifecycle_status": "current",
        },
        {
            "anchor_id": "discussion_atlas_task_orientation",
            "source_kind": "github_discussion",
            "project_role": "design_input",
            "lifecycle_status": "current",
        },
        {
            "anchor_id": "research_reference_continuity_systems",
            "source_kind": "research_reference",
            "project_role": "background_counterpoint",
            "lifecycle_status": "review_required",
        },
    ]
    suppressed = [
        {
            "anchor_id": "superseded_planning_note_example",
            "source_kind": "planning_note",
            "project_role": "historical_context_only",
            "lifecycle_status": "superseded",
        },
        {
            "anchor_id": "stale_paper_claim_example",
            "source_kind": "research_reference",
            "project_role": "do_not_claim_without_fresh_review",
            "lifecycle_status": "stale",
        },
    ]
    for anchor in base:
        anchor.update(
            {
                "authority": "route_not_evidence",
                "safe_use": "reopen_before_claim",
                "privacy_boundary": "public_safe_ref_only",
            }
        )
    for anchor in suppressed:
        anchor.update(
            {
                "authority": "route_not_evidence",
                "safe_use": "do_not_rank_as_current_route",
                "privacy_boundary": "public_safe_ref_only",
            }
        )
    return base, suppressed


def _feedback_action(constraint_id: str) -> dict[str, Any]:
    del constraint_id
    return {
        "route": "learning_loop.effectiveness_ledger",
        "claim_boundary": "aggregate_or_source_ref_outcome_only",
    }


def _compact_constraint(row: Mapping[str, Any]) -> dict[str, Any]:
    constraint_id = str(row.get("constraint_id") or row.get("guidance_id") or row.get("clause_id") or "")
    return {
        "constraint_id": constraint_id[:80],
        "source": str(row.get("source") or row.get("kind") or "")[:80],
        "summary": str(row.get("summary") or row.get("guidance") or row.get("guidance_text") or "")[:110],
        "authority": "navigation_only_not_fact",
        "route_status": str(row.get("route_status") or "ready")[:40],
        "source_refs": _tiny_source_refs(row.get("source_refs"), limit=1),
        "reason_codes": [str(code)[:80] for code in list(row.get("reason_codes") or [])[:1]],
        "effectiveness_feedback": _feedback_action(constraint_id),
    }


def _compact_suppressed_constraint(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "constraint_id": str(row.get("constraint_id") or "")[:120],
        "source": str(row.get("source") or "")[:80],
        "summary": str(row.get("summary") or "")[:180],
        "authority": "navigation_only_not_fact",
        "route_status": "suppressed",
        "suppression_reason": str(row.get("suppression_reason") or "review_only")[:100],
        "source_refs": [],
    }


def _semantic_learning_constraints(task: str) -> list[dict[str, Any]]:
    promoted = [
        {
            "kind": "aippocampus_promoted_semantic_learning_guidance_candidate",
            "guidance_candidate_id": stable_id("semantic_learning", task),
            "candidate_kind": "workflow_packaging_candidate",
            "promotion_type": "source_backed_bridge_route",
            "foreground_eligible": True,
            "freshness": "current",
            "source_refs": [
                {"source_id": "learning_loop:semantic_learning", "message_id": "guidance-a"},
                {"source_id": "docs:source-backed-learning-loop", "message_id": "guidance-b"},
            ],
            "reason_codes": ["avoid_broad_search_before_bridge_route"],
        }
    ]
    projection = semantic_learning.surface_semantic_learning_guidance(
        promoted,
        query_terms=[
            "workflow_packaging_candidate",
            "source_backed_bridge_route",
            "task_orientation",
            *str(task or "").split(),
        ],
    )
    constraints: list[dict[str, Any]] = []
    for guidance in projection.get("guidance") or []:
        if not isinstance(guidance, Mapping):
            continue
        constraint_id = str(guidance.get("guidance_id") or stable_id("semantic", task))
        constraints.append(
            {
                "constraint_id": constraint_id,
                "source": "semantic_learning",
                "summary": guidance.get("guidance_text")
                or "Use promoted semantic guidance as a route cue before broad search.",
                "authority": "navigation_only_not_fact",
                "route_status": "ready",
                "source_refs": list(guidance.get("source_refs") or [])[:3],
                "reason_codes": list(guidance.get("reason_codes") or [])[:4],
                "why_it_appears": "Promoted action-time semantic guidance matched the orientation task.",
                "reopen_requirement": "reopen_semantic_guidance_sources_before_claim_or_broad_application",
                "effectiveness_feedback": _feedback_action(constraint_id),
            }
        )
    return constraints


def _source_backed_lesson_constraints(task: str) -> list[dict[str, Any]]:
    candidate = {
        "lesson_id": stable_id("source_backed_lesson", task),
        "candidate_kind": "context_reopen_candidate",
        "failed_route": "context_sensitive_route_without_reopen",
        "summary": "Reopen the source trail before retrying a context-sensitive route.",
        "source_refs": [
            {"source_id": "lesson:context-reopen", "message_id": "lesson-a"},
            {"source_id": "lesson:context-reopen", "message_id": "lesson-b"},
        ],
        "independent_trail_count": 2,
    }
    lesson = source_backed_lessons.promote_lesson_candidate(
        candidate,
        independent_trail_count=2,
    )
    if lesson.get("status") != "ripe" or not lesson.get("foreground_activation_allowed"):
        return []
    constraint_id = str(lesson.get("lesson_id") or stable_id("lesson", task))
    return [
        {
            "constraint_id": constraint_id,
            "source": "source_backed_lessons",
            "summary": lesson.get("summary")
            or "Ripe source-backed lesson should change action order.",
            "authority": "navigation_only_not_fact",
            "route_status": "ready",
            "source_refs": list(lesson.get("source_refs") or [])[:3],
            "reason_codes": ["ripe_source_backed_lesson", "source_reopen_required"],
            "why_it_appears": "The lesson is ripe and foreground-eligible, but remains guidance.",
            "reopen_requirement": "reopen_lesson_sources_before_broad_application",
            "effectiveness_feedback": _feedback_action(constraint_id),
        }
    ]


def _aippo_seed_constraints(task: str) -> list[dict[str, Any]]:
    rows = aippo_adapter.learning_findings_to_aippo_source_rows(
        [
            {
                "finding_id": stable_id("aippo_seed", task),
                "finding_kind": "workflow_order_finding",
                "workflow_family": "context_reopen_before_retry",
                "scope": "project:AIppocampus",
                "confidence": "medium",
                "source_ref_count": 2,
                "source_refs": [
                    {"source_id": "aippo-seed:workflow", "message_id": "seed-a"},
                    {"source_id": "aippo-seed:workflow", "message_id": "seed-b"},
                ],
            }
        ]
    )
    constraints: list[dict[str, Any]] = []
    for row in rows:
        constraint_id = str(row.get("clause_id") or stable_id("aippo_seed", task))
        constraints.append(
            {
                "constraint_id": constraint_id,
                "source": "learning_loop_aippo_seed",
                "summary": row.get("guidance")
                or "Eligible learning finding can seed an AIppo working clause.",
                "authority": "navigation_only_not_fact",
                "route_status": "ready" if row.get("status") == "ripe" else "review",
                "source_refs": list(row.get("source_refs") or [])[:3],
                "reason_codes": [
                    "eligible_aippo_seed_row",
                    "source_reopen_required",
                    *list(row.get("support_types") or [])[:2],
                ],
                "why_it_appears": "Learning-loop finding is eligible for AIppo clause projection.",
                "reopen_requirement": "reopen_learning_seed_sources_before_promoting_to_contract",
                "effectiveness_feedback": _feedback_action(constraint_id),
            }
        )
    return constraints


def build_learning_constraints(
    issue_packet: Mapping[str, Any],
    *,
    task: str = "",
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    active = [
        {
            "constraint_id": "aippo_working_contract_source_reopen",
            "source": "aippo_working_contract",
            "summary": "Use working guidance for planning only; reopen source before claims.",
            "authority": "navigation_only_not_fact",
            "route_status": "ready",
            "source_refs": [source_ref("runtime", "aippo.working_contract", 1)],
            "reason_codes": ["aippo_constraint", "source_reopen_before_claim"],
            "why_it_appears": "AIppo working contracts are safe for planning but not source truth.",
            "reopen_requirement": "reopen_working_contract_sources_before_claim",
            "effectiveness_feedback": _feedback_action("aippo_working_contract_source_reopen"),
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
                "why_it_appears": "Issue-like work should check existing owner routes before broad scaffolding.",
                "reopen_requirement": "reopen_issue_owner_sources_before_closeout",
                "effectiveness_feedback": _feedback_action("issue_work_guard_active_pull"),
            },
        )
    active.extend(_semantic_learning_constraints(task))
    active.extend(_source_backed_lesson_constraints(task))
    active.extend(_aippo_seed_constraints(task))
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
    return (
        [_compact_constraint(row) for row in active],
        [_compact_suppressed_constraint(row) for row in suppressed],
    )


def compact_active_path_packet(active_path: Mapping[str, Any]) -> dict[str, Any]:
    paths: list[dict[str, Any]] = []
    for path in active_path.get("paths") or []:
        if not isinstance(path, Mapping):
            continue
        raw_boundary = path.get("source_boundary")
        boundary: Mapping[str, Any] = raw_boundary if isinstance(raw_boundary, Mapping) else {}
        paths.append(
            {
                "path_id": path.get("path_id"),
                "title": path.get("title"),
                "route": path.get("route"),
                "currentness": path.get("currentness"),
                "next_action": path.get("next_action"),
                "confidence": path.get("confidence"),
                "origin": path.get("origin"),
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


def _private_replay_eval_projection(
    *,
    include_private_replay_aggregate: bool = False,
    private_replay_events: str | Path | None = None,
) -> dict[str, Any]:
    base = {
        "enabled_by_default": False,
        "aggregate_only": True,
        "opt_in_required": True,
        "raw_private_examples_serialized": False,
        "raw_event_rows_serialized": False,
        "status": "not_requested",
    }
    if not include_private_replay_aggregate and private_replay_events is None:
        return base
    try:
        events = (
            load_behavior_event_rows(Path(private_replay_events))
            if private_replay_events is not None
            else None
        )
        report = build_private_history_replay_report(
            events,
            input_origin="real_sanitized_history" if events is not None else None,
        )
    except LearningReplayInputError as exc:
        return {
            **base,
            "status": "needs_input",
            "ok": False,
            "error": {"code": exc.code, "message": str(exc)},
            "safe_next_actions": [
                {"id": "learning_status", "command": "aippocampus learning status --json"},
                {
                    "id": "discover_history",
                    "command": "aippocampus learning discover-history --json",
                },
                {
                    "id": "replay_selected_events",
                    "command_template": (
                        "aippocampus agent orient --eval "
                        "--private-replay-events {selected_sanitized_events_jsonl} --json"
                    ),
                    "requires": ["selected_sanitized_events_jsonl"],
                },
            ],
        }
    metrics = report.get("metrics") or {}
    comparable = report.get("private_dogfood_comparable_metrics") or {}
    return {
        **base,
        "status": "measured_public_safe_aggregate" if report.get("ok") else "needs_review",
        "ok": bool(report.get("ok")),
        "fixture_input": bool(report.get("fixture_input")),
        "input_origin": report.get("input_origin"),
        "aggregate_metrics": {
            "guidance_count": metrics.get("guidance_count", 0),
            "context_loss_to_reopen_source_count": metrics.get(
                "context_loss_to_reopen_source_count", 0
            ),
            "effectiveness_ledger_row_count": metrics.get("effectiveness_ledger_row_count", 0),
            "observed_guidance_outcome_count": metrics.get(
                "observed_guidance_outcome_count", 0
            ),
            "outcome_unobserved_count": metrics.get("outcome_unobserved_count", 0),
            "source_reopen_after_semantic_guidance_rate": metrics.get(
                "source_reopen_after_semantic_guidance_rate", 0.0
            ),
            "raw_private_text_leak_count": metrics.get("raw_private_text_leak_count", 0),
        },
        "comparable_metrics": {
            "repeated_failure_detection_recall": comparable.get(
                "repeated_failure_detection_recall", 0.0
            ),
            "workflow_order_detection_count": comparable.get(
                "workflow_order_detection_count", 0
            ),
            "context_reopen_before_action_rate": comparable.get(
                "context_reopen_before_action_rate", 0.0
            ),
            "false_positive_nudge_rate": comparable.get("false_positive_nudge_rate", 0.0),
            "raw_private_text_leak_count": comparable.get("raw_private_text_leak_count", 0),
        },
        "privacy_boundary": {
            "aggregate_or_redacted_public_output_only": True,
            "local_paths_serialized": False,
            "raw_rollouts_serialized": False,
            "raw_stdout_stderr_serialized": False,
        },
        "claim_boundary": "aggregate_replay_metrics_only_not_live_quality_claim",
    }


def build_task_orientation_eval_report(
    *,
    include_private_replay_aggregate: bool = False,
    private_replay_events: str | Path | None = None,
) -> dict[str, Any]:
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
    private_replay = _private_replay_eval_projection(
        include_private_replay_aggregate=include_private_replay_aggregate,
        private_replay_events=private_replay_events,
    )
    public_gate_ok = (
        top["broad_manual_search_count"] < static["broad_manual_search_count"]
        and top["blind_deepen_count"] < static["blind_deepen_count"]
        and top_plus["repeated_wrong_route_count"]
        <= route_only["repeated_wrong_route_count"]
        and top["source_truth_overclaim_count"] == 0
        and top_plus["source_truth_overclaim_count"] == 0
        and top["raw_private_text_leak_count"] == 0
    )
    private_gate_ok = private_replay.get("status") in {
        "not_requested",
        "measured_public_safe_aggregate",
    }
    return _public_payload(
        {
            "kind": "aippocampus_task_orientation_eval_report",
            "schema_version": SCHEMA_VERSION,
            "ok": public_gate_ok and private_gate_ok,
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
                "private_replay_aggregate_requested": (
                    include_private_replay_aggregate or private_replay_events is not None
                ),
            },
            "fixture_cases": [
                {"case_id": "complete", "expects": "first route plus boundary"},
                {"case_id": "partial", "expects": "unknowns plus ask/deepen action"},
                {"case_id": "stale_anchor", "expects": "suppress as current route"},
                {"case_id": "conflicted", "expects": "review before claim"},
                {"case_id": "missing_source", "expects": "ask or rerun recall"},
                {"case_id": "foreground_too_heavy", "expects": "fail field-bloat gate"},
            ],
            "private_replay": private_replay,
        }
    )
