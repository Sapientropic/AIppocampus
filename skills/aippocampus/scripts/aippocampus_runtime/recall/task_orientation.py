#!/usr/bin/env python3
"""Task Orientation Packet projection for fresh-thread agent starts.

This is a derived foreground read model, not a new memory truth store. It
combines existing route owners, issue-work guards, AIppo working constraints,
and Active Path Packets so a later agent can choose the first source route
without dumping private history or treating navigation sidecars as evidence.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from aippocampus_runtime import core
from aippocampus_runtime.contracts import (
    FOREGROUND_ACTION_CONTRACT_VERSION,
    foreground_template_action,
)
from aippocampus_runtime.ops.issue_work_guard import build_issue_active_pull_packet
from aippocampus_runtime.privacy import redact_private_paths, redact_sensitive_values
from aippocampus_runtime.recall.active_path_packet import build_active_path_packet
from aippocampus_runtime.recall.task_orientation_fixtures import (
    FOREGROUND_BYTE_BUDGET,
    build_external_source_anchors,
    build_learning_constraints,
    build_task_orientation_eval_report,
    compact_active_path_packet,
    compact_issue_work_guard,
    route_plan_from_active_path,
    source_ref,
)

KIND = "aippocampus_task_orientation_packet"
SCHEMA_VERSION = "task-orientation-v1"


def _public_payload(payload: Any) -> Any:
    return redact_sensitive_values(redact_private_paths(payload))


def _text(value: Any, limit: int = 180) -> str:
    return core.compact_text(str(value or "").strip(), limit)


def _task_value(task: str | list[str] | tuple[str, ...] | None) -> str:
    if isinstance(task, (list, tuple)):
        return _text(" ".join(str(part) for part in task), 240)
    return _text(task, 240)


def missing_task_payload(*, project: str = "AIppocampus") -> dict[str, Any]:
    action = foreground_template_action(
        action_id="provide_task_for_orientation_packet",
        label="Provide task for orientation packet",
        command_template='aippocampus agent orient "{task}" --json',
        requires=["task"],
        why="Task Orientation Packets are scoped to the task; a generic packet would become misleading.",
        claim_boundary="task_required_before_route_selection",
    )
    return _public_payload(
        {
            "kind": KIND,
            "schema_version": SCHEMA_VERSION,
            "mode": "orient",
            "status": "needs_input",
            "ok": False,
            "project": project,
            "foreground_action_contract": FOREGROUND_ACTION_CONTRACT_VERSION,
            "foreground_action": action,
            "agent_next_action": action,
            "safe_next_actions": [action],
            "source_boundary": _source_boundary(),
            "cannot_claim": ["task_scoped_orientation_without_task"],
        }
    )


def _source_boundary() -> dict[str, Any]:
    return {
        "navigation_not_truth": True,
        "clean_source_is_authority": True,
        "source_reopen_required_before_claim": True,
        "exact_or_sensitive_claims_require_deepen": True,
        "raw_source_text_serialized": False,
        "local_paths_serialized": False,
        "secret_values_serialized": False,
        "external_model_calls": False,
    }


def _route_readiness_rows(
    *,
    anchors: list[dict[str, Any]],
    suppressed_anchors: list[dict[str, Any]],
    constraints: list[dict[str, Any]],
    suppressed_constraints: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for anchor in anchors:
        rows.append(
            {
                "title": f"{anchor['source_kind']}: {anchor['project_role']}",
                "route_status": "ready",
                "currentness": "current" if anchor["lifecycle_status"] == "current" else "unknown",
                "source_refs": [source_ref(anchor["source_kind"], anchor["anchor_id"])],
                "confidence": "medium",
                "origin": "external_source_anchor",
                "reason_codes": [anchor["project_role"], "reopen_before_claim"],
            }
        )
    for constraint in constraints:
        rows.append(
            {
                "title": f"{constraint['source']}: {constraint['constraint_id']}",
                "route_status": constraint["route_status"],
                "currentness": "current",
                "source_refs": constraint["source_refs"],
                "confidence": "high",
                "origin": "learning_aippo_constraint",
                "reason_codes": constraint["reason_codes"],
            }
        )
    for anchor in suppressed_anchors:
        rows.append(
            {
                "title": f"suppressed {anchor['source_kind']}: {anchor['project_role']}",
                "route_status": "suppressed",
                "currentness": anchor["freshness"],
                "source_refs": [],
                "confidence": "low",
                "origin": "external_source_anchor",
                "suppression_reasons": [anchor["lifecycle_status"], "not_current_route"],
            }
        )
    for constraint in suppressed_constraints:
        rows.append(
            {
                "title": f"suppressed {constraint['source']}: {constraint['constraint_id']}",
                "route_status": "suppressed",
                "currentness": "unknown",
                "source_refs": [],
                "confidence": "low",
                "origin": "learning_aippo_constraint",
                "suppression_reasons": [constraint["suppression_reason"]],
            }
        )
    return rows


def _safe_next_actions(task: str) -> list[dict[str, Any]]:
    return [
        foreground_template_action(
            action_id="run_agent_recall_for_orientation",
            label="Run source-backed recall",
            command_template='aippocampus agent recall "{task}" --json',
            requires=["task"],
            why="Find real reopenable routes before factual or closeout claims.",
            claim_boundary="no_claim_before_reopen",
        ),
        foreground_template_action(
            action_id="activate_aippo_for_task",
            label="Check AIppo guidance",
            command_template='aippocampus agent aippo "{task}" --json',
            requires=["task"],
            why="Use project workflow guidance only as low-risk planning input.",
            claim_boundary="navigation_only_not_fact",
        ),
        foreground_template_action(
            action_id="deepen_selected_recall_route",
            label="Deepen selected recall route",
            command_template="aippocampus agent deepen --request {request_index} --last-recall --json",
            requires=["request_index"],
            why="Open source before quoting, closing issues, or relying on stale details.",
            claim_boundary="source_reopen_required_before_claims",
        ),
    ]


def build_task_orientation_packet(
    task: str | list[str] | tuple[str, ...] | None,
    *,
    project: str = "AIppocampus",
    max_paths: int = 3,
) -> dict[str, Any]:
    clean_task = _task_value(task)
    if not clean_task:
        return missing_task_payload(project=project)
    issue_packet = build_issue_active_pull_packet(title=clean_task)
    anchors, suppressed_anchors = build_external_source_anchors(clean_task)
    constraints, suppressed_constraints = build_learning_constraints(issue_packet)
    route_rows = _route_readiness_rows(
        anchors=anchors,
        suppressed_anchors=suppressed_anchors,
        constraints=constraints,
        suppressed_constraints=suppressed_constraints,
    )
    active_path = build_active_path_packet(
        route_readiness={"rows": route_rows},
        max_paths=max_paths,
    )
    compact_path = compact_active_path_packet(active_path)
    actions = _safe_next_actions(clean_task)
    packet = {
        "kind": KIND,
        "schema_version": SCHEMA_VERSION,
        "mode": "orient",
        "status": "ok",
        "ok": True,
        "project": project,
        "task": clean_task,
        "understanding_state_read_model": {
            "kind": "aippocampus_understanding_state_read_model",
            "schema_version": SCHEMA_VERSION,
            "authority": "navigation_only_not_fact",
            "truth_authority": "clean_source_after_reopen",
            "storage": "derived_no_new_truth_store",
            "projection_source": "active_path_packet_plus_issue_work_and_aippo",
        },
        "frontier": "choose first source route; do not start broad manual search until recall/owners are checked",
        "load_bearing_unknowns": [
            "which reopened source route is actually current",
            "whether issue comments changed acceptance criteria",
            "whether private replay aggregate is opted in for evaluation",
        ],
        "issue_work_guard": compact_issue_work_guard(issue_packet),
        "external_source_anchors": anchors,
        "suppressed_external_source_anchors": suppressed_anchors,
        "learning_and_aippo_constraints": constraints,
        "suppressed_constraints": suppressed_constraints,
        "route_plan": route_plan_from_active_path(compact_path),
        "active_path_packet": compact_path,
        "foreground_action_contract": FOREGROUND_ACTION_CONTRACT_VERSION,
        "foreground_action": actions[0],
        "agent_next_action": actions[0],
        "safe_next_actions": actions,
        "source_boundary": _source_boundary(),
        "metrics": {
            "route_readiness_row_count": len(route_rows),
            "external_source_anchor_count": len(anchors),
            "suppressed_external_source_anchor_count": len(suppressed_anchors),
            "learning_constraint_count": len(constraints),
            "suppressed_unripe_constraint_count": len(suppressed_constraints),
            "active_path_count": compact_path.get("path_count", 0),
            "external_model_calls": 0,
            "writes_performed": 0,
        },
        "red_lines": {
            "source_truth_overclaim_count": 0,
            "learning_constraint_promoted_to_fact": 0,
            "unripe_constraint_ranked_as_current": 0,
            "raw_private_text_serialized": 0,
        },
        "cannot_claim": [
            "task_orientation_packet_proves_memory_fact",
            "external_anchor_is_current_fact_without_reopen",
            "private_replay_quality_lift_without_opt_in_aggregate_eval",
        ],
    }
    foreground_bytes = len(json.dumps(packet, ensure_ascii=False, sort_keys=True).encode("utf-8"))
    packet["metrics"]["foreground_json_bytes"] = foreground_bytes
    packet["metrics"]["foreground_byte_budget"] = FOREGROUND_BYTE_BUDGET
    packet["metrics"]["foreground_too_heavy"] = foreground_bytes > FOREGROUND_BYTE_BUDGET
    packet["red_lines"]["foreground_too_heavy"] = 1 if foreground_bytes > FOREGROUND_BYTE_BUDGET else 0
    return _public_payload(packet)


def render_task_orientation_human(payload: Mapping[str, Any]) -> str:
    if payload.get("status") == "needs_input":
        action = payload.get("foreground_action") or {}
        return "\n".join(
            [
                "AIppocampus agent orient: task required",
                "next: " + str(action.get("command_template") or "aippocampus agent orient \"{task}\" --json"),
                "boundary: orientation is task-scoped navigation, not source evidence.",
            ]
        )
    paths = payload.get("active_path_packet", {}).get("path_count", 0)
    action = payload.get("foreground_action") or {}
    return "\n".join(
        [
            "AIppocampus agent orient: ok",
            "task: " + str(payload.get("task") or ""),
            "active_paths: " + str(paths),
            "next: " + str(action.get("command_template") or action.get("id")),
            "boundary: reopen source before claims or issue closeout.",
        ]
    )


def add_agent_subparser(sub: Any) -> None:
    import argparse

    orient_parser = sub.add_parser(
        "orient",
        usage='aippocampus agent orient "task to continue" --json [options]',
        description=(
            "Task Orientation Packet:\n"
            "  Use at the start of issue work or a fresh thread to choose the first source route.\n"
            "  The packet is a derived read model over existing recall, issue-work, AIppo, and "
            "Active Path Packet contracts. It is not memory evidence and does not write state.\n"
            "  Run recall/deepen before exact, stale, public, or issue-closeout claims."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    orient_parser.add_argument("task", nargs="*")
    orient_parser.add_argument("--task", dest="task_flag")
    orient_parser.add_argument("--project", default="AIppocampus")
    orient_parser.add_argument("--max", type=int, default=3)
    orient_parser.add_argument("--eval", action="store_true")
    orient_parser.add_argument("--json", action="store_true")


def run_agent_command(args: Any, json_out: Any) -> int:
    if args.eval:
        payload = build_task_orientation_eval_report()
    else:
        payload = build_task_orientation_packet(
            args.task_flag or " ".join(args.task),
            project=args.project,
            max_paths=args.max,
        )
    if args.json:
        json_out(payload)
    else:
        print(render_task_orientation_human(payload))
    return 2 if payload.get("status") == "needs_input" else 0
