#!/usr/bin/env python3
"""Reflection-space topology and feedback MVP.

This helper builds an inspectable topology over Journey data and turns
reflection feedback into advisory ranking/confidence/visibility adjustments.
It does not rewrite clean source, mutate Journey history, or decide foreground
delivery. Later UI/AAR layers may consume the adjustments after source review.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from aippocampus_runtime.contracts import (
    canonical_foreground_action_fields,
    foreground_shell_action,
)
from aippocampus_runtime.core import compact_text, now_utc, stable_json_id
from aippocampus_runtime.source.io_kernel import (
    merge_source_refs as merge_source_ref_groups,
)
from aippocampus_runtime.source.io_kernel import (
    normalize_source_refs,
    parse_utc,
    source_ref_key_set,
)

SCHEMA_VERSION = 1
TOPOLOGY_KIND = "aippocampus_reflection_topology"
NODE_KIND = "reflection_topology_node"
EDGE_KIND = "reflection_topology_edge"
FEEDBACK_KIND = "aippocampus_reflection_feedback"
ADJUSTMENT_KIND = "aippocampus_reflection_adjustment"
FIXTURE_SMOKE_KIND = "aippocampus_reflection_space_fixture_smoke"
DREAM_HYPOTHESIS_TYPE = "dream_hypothesis"
ADJUDICATED_DREAM_STATES = {
    "accepted",
    "approved",
    "reviewed",
    "agent_adjudicated",
    "auto_adjudicated",
    "source_adjudicated",
}

ReflectionAction = Literal[
    "merge",
    "revive",
    "abandon",
    "recall_helpful",
    "recall_ignored",
    "turning_point",
    "user_correction",
]

SURFACES = {"ranking", "confidence", "visibility"}
BASE_STATUS_METRICS = {
    "traveling": {"ranking_weight": 1.0, "confidence": 0.72, "visibility_score": 0.75},
    "camped": {"ranking_weight": 0.72, "confidence": 0.64, "visibility_score": 0.48},
    "arrived": {"ranking_weight": 0.42, "confidence": 0.7, "visibility_score": 0.32},
    "abandoned": {"ranking_weight": 0.12, "confidence": 0.46, "visibility_score": 0.08},
}


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def space_source_refs(value: object) -> tuple[dict[str, Any], ...]:
    return normalize_source_refs(value, require_thread=False)


def merge_refs(*groups: object, limit: int = 12) -> tuple[dict[str, Any], ...]:
    return tuple(
        merge_source_ref_groups(
            *(space_source_refs(group) for group in groups),
            limit=limit,
            require_thread=False,
        )
    )


def journey_id_of(row: Mapping[str, Any]) -> str:
    return str(row.get("journey_id") or row.get("id") or "")


def journey_refs(row: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    waypoint_refs = [
        ref
        for waypoint in row.get("waypoints") or []
        if isinstance(waypoint, Mapping)
        for ref in space_source_refs(waypoint.get("source_refs") or [])
    ]
    return merge_refs(
        row.get("source_refs") or [],
        row.get("current_frontier_source_refs") or [],
        waypoint_refs,
    )


def action_menu(journey: Mapping[str, Any], *, journey_count: int) -> list[str]:
    status = str(journey.get("status") or "")
    actions = ["expand"]
    if journey_count > 1 and status not in {"abandoned", "arrived"}:
        actions.append("merge")
    if status not in {"abandoned", "arrived"}:
        actions.append("abandon")
    if status in {"camped", "abandoned"}:
        actions.append("revive")
    return actions


def base_metrics(status: str) -> dict[str, float]:
    return dict(BASE_STATUS_METRICS.get(status, BASE_STATUS_METRICS["camped"]))


def visibility_label(score: float) -> str:
    if score >= 0.7:
        return "foreground_candidate"
    if score >= 0.35:
        return "visible"
    return "collapsed"


def adjustment_source_refs(
    row: Mapping[str, Any],
    *,
    journey_by_id: Mapping[str, Mapping[str, Any]],
) -> tuple[dict[str, Any], ...]:
    refs = space_source_refs(row.get("source_refs") or row.get("evidence_refs") or [])
    if refs:
        return refs
    target = journey_by_id.get(str(row.get("journey_id") or row.get("target_journey_id") or ""))
    return journey_refs(target) if target else ()


def normalize_feedback_action(row: Mapping[str, Any]) -> str:
    action = str(row.get("action") or row.get("effect") or row.get("recall_effect") or "")
    aliases = {
        "helpful": "recall_helpful",
        "used": "recall_helpful",
        "ignored": "recall_ignored",
        "dismissed": "recall_ignored",
        "missed": "recall_ignored",
        "recall_helpful": "recall_helpful",
        "recall_ignored": "recall_ignored",
        "turning_point_after_recall": "turning_point",
        "turning_point": "turning_point",
        "correct": "user_correction",
        "corrected": "user_correction",
        "user_correction": "user_correction",
        "merge": "merge",
        "revive": "revive",
        "abandon": "abandon",
    }
    return aliases.get(action, "")


def make_adjustment(
    *,
    target_id: str,
    surface: str,
    delta: float,
    reason: str,
    action: str,
    source_refs: Sequence[Mapping[str, Any]],
    scope: str = "journey",
) -> dict[str, Any]:
    if surface not in SURFACES:
        raise ValueError(f"unsupported reflection adjustment surface: {surface}")
    refs = tuple(dict(ref) for ref in source_refs)
    if not refs:
        raise ValueError("reflection adjustment requires source refs")
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": ADJUSTMENT_KIND,
        "adjustment_id": stable_json_id(
            "reflection_adj",
            "reflection-space-id",
            target_id,
            surface,
            delta,
            action,
            refs,
            length=20,
        ),
        "created_at": now_utc(),
        "target_scope": scope,
        "target_id": target_id,
        "surface": surface,
        "delta": round(float(delta), 4),
        "reason": compact_text(reason, 240),
        "feedback_action": action,
        "source_refs": list(refs),
        "applies_to": ["reflection_topology", "aar_strategy"],
        "clean_source_mutation": False,
        "journey_mutation": False,
    }


def adjustments_from_feedback(
    feedback_rows: Iterable[Mapping[str, Any]],
    *,
    journey_by_id: Mapping[str, Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], int]:
    adjustments: list[dict[str, Any]] = []
    ignored = 0
    for row in feedback_rows:
        action = normalize_feedback_action(row)
        target_id = str(row.get("journey_id") or row.get("target_journey_id") or "")
        refs = adjustment_source_refs(row, journey_by_id=journey_by_id)
        if not action or not target_id or not refs:
            ignored += 1
            continue
        note = str(row.get("note") or row.get("summary") or row.get("reason") or action)
        try:
            if action == "merge":
                adjustments.append(
                    make_adjustment(
                        target_id=target_id,
                        surface="visibility",
                        delta=-0.55,
                        reason=f"Merge feedback: {note}",
                        action=action,
                        source_refs=refs,
                    )
                )
                merge_target = str(row.get("merge_target") or "")
                if merge_target:
                    adjustments.append(
                        make_adjustment(
                            target_id=merge_target,
                            surface="ranking",
                            delta=0.2,
                            reason=f"Merge target should rank higher after feedback: {note}",
                            action=action,
                            source_refs=refs,
                        )
                    )
            elif action == "abandon":
                adjustments.append(
                    make_adjustment(
                        target_id=target_id,
                        surface="visibility",
                        delta=-0.9,
                        reason=f"Abandon feedback: {note}",
                        action=action,
                        source_refs=refs,
                    )
                )
                adjustments.append(
                    make_adjustment(
                        target_id=target_id,
                        surface="ranking",
                        delta=-0.5,
                        reason=f"Abandon feedback lowers re-surface priority: {note}",
                        action=action,
                        source_refs=refs,
                    )
                )
            elif action == "revive":
                adjustments.append(
                    make_adjustment(
                        target_id=target_id,
                        surface="visibility",
                        delta=0.65,
                        reason=f"Revive feedback: {note}",
                        action=action,
                        source_refs=refs,
                    )
                )
                adjustments.append(
                    make_adjustment(
                        target_id=target_id,
                        surface="ranking",
                        delta=0.35,
                        reason=f"Revive feedback raises reentry priority: {note}",
                        action=action,
                        source_refs=refs,
                    )
                )
            elif action == "recall_helpful":
                adjustments.append(
                    make_adjustment(
                        target_id=target_id,
                        surface="ranking",
                        delta=0.25,
                        reason=f"Recall changed or supported the trajectory: {note}",
                        action=action,
                        source_refs=refs,
                    )
                )
                adjustments.append(
                    make_adjustment(
                        target_id=target_id,
                        surface="confidence",
                        delta=0.08,
                        reason=f"Recall had a positive observed effect: {note}",
                        action=action,
                        source_refs=refs,
                    )
                )
            elif action == "recall_ignored":
                adjustments.append(
                    make_adjustment(
                        target_id=target_id,
                        surface="visibility",
                        delta=-0.25,
                        reason=f"Recall was ignored or dismissed: {note}",
                        action=action,
                        source_refs=refs,
                    )
                )
            elif action == "turning_point":
                adjustments.append(
                    make_adjustment(
                        target_id=target_id,
                        surface="ranking",
                        delta=0.3,
                        reason=f"Conversation turning point was associated with this journey: {note}",
                        action=action,
                        source_refs=refs,
                    )
                )
            elif action == "user_correction":
                adjustments.append(
                    make_adjustment(
                        target_id=target_id,
                        surface="confidence",
                        delta=-0.18,
                        reason=f"User correction requires review before stronger surfacing: {note}",
                        action=action,
                        source_refs=refs,
                    )
                )
        except ValueError:
            ignored += 1
    return adjustments, ignored


def adjusted_metrics(
    journey: Mapping[str, Any],
    adjustments: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    metrics = base_metrics(str(journey.get("status") or "camped"))
    journey_id = journey_id_of(journey)
    for adjustment in adjustments:
        if str(adjustment.get("target_id") or "") != journey_id:
            continue
        surface = str(adjustment.get("surface") or "")
        delta = float(adjustment.get("delta") or 0.0)
        if surface == "ranking":
            metrics["ranking_weight"] = clamp(metrics["ranking_weight"] + delta, 0.0, 2.0)
        elif surface == "confidence":
            metrics["confidence"] = clamp(metrics["confidence"] + delta, 0.0, 1.0)
        elif surface == "visibility":
            metrics["visibility_score"] = clamp(metrics["visibility_score"] + delta, 0.0, 1.0)
    return {
        **{key: round(value, 4) for key, value in metrics.items()},
        "visibility": visibility_label(metrics["visibility_score"]),
    }


def journey_node(
    journey: Mapping[str, Any],
    *,
    journey_count: int,
    adjustments: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    refs = journey_refs(journey)
    return {
        "kind": NODE_KIND,
        "node_type": "journey",
        "node_id": f"journey:{journey_id_of(journey)}",
        "journey_id": journey_id_of(journey),
        "label": compact_text(str(journey.get("path_label") or journey.get("core_inquiry") or ""), 120),
        "status": str(journey.get("status") or "camped"),
        "current_frontier": compact_text(str(journey.get("current_frontier") or ""), 260),
        "metrics": adjusted_metrics(journey, adjustments),
        "available_actions": action_menu(journey, journey_count=journey_count),
        "source_refs": list(refs),
    }


def waypoint_nodes_and_edges(journey: Mapping[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    journey_node_id = f"journey:{journey_id_of(journey)}"
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    for index, waypoint in enumerate(journey.get("waypoints") or []):
        if not isinstance(waypoint, Mapping):
            continue
        waypoint_id = str(
            waypoint.get("waypoint_id")
            or stable_json_id("wp", "reflection-space-id", journey_node_id, index)
        )
        node_id = f"waypoint:{waypoint_id}"
        refs = space_source_refs(waypoint.get("source_refs") or [])
        nodes.append(
            {
                "kind": NODE_KIND,
                "node_type": "waypoint",
                "node_id": node_id,
                "journey_id": journey_id_of(journey),
                "waypoint_id": waypoint_id,
                "label": compact_text(str(waypoint.get("moment") or ""), 160),
                "arc": compact_text(str(waypoint.get("arc") or "unmapped"), 40),
                "timestamp": waypoint.get("timestamp"),
                "source_refs": list(refs),
            }
        )
        edges.append(
            {
                "kind": EDGE_KIND,
                "edge_type": "contains_waypoint",
                "from": journey_node_id,
                "to": node_id,
                "source_refs": list(refs),
            }
        )
    frontier = compact_text(str(journey.get("current_frontier") or ""), 260)
    frontier_refs = space_source_refs(journey.get("current_frontier_source_refs") or [])
    if frontier and frontier_refs:
        frontier_id = f"frontier:{journey_id_of(journey)}"
        nodes.append(
            {
                "kind": NODE_KIND,
                "node_type": "current_frontier",
                "node_id": frontier_id,
                "journey_id": journey_id_of(journey),
                "label": frontier,
                "source_refs": list(frontier_refs),
            }
        )
        edges.append(
            {
                "kind": EDGE_KIND,
                "edge_type": "points_to_frontier",
                "from": journey_node_id,
                "to": frontier_id,
                "source_refs": list(frontier_refs),
            }
        )
    return nodes, edges


def dream_hypothesis_block_reason(row: Mapping[str, Any], *, now: datetime | None = None) -> str:
    if row.get("candidate_type") != DREAM_HYPOTHESIS_TYPE:
        return "not_dream_hypothesis"
    if str(row.get("review_state") or "") not in ADJUDICATED_DREAM_STATES:
        return "not_adjudicated"
    if "reflection_space" not in {str(item) for item in row.get("downstream_use") or []}:
        return "reflection_not_allowed"
    if not space_source_refs(row.get("source_refs") or []):
        return "missing_source_refs"
    gate = row.get("sensitive_use_gate") or {}
    if isinstance(gate, Mapping) and gate.get("state") == "blocked":
        return "sensitive_use_blocked"
    if row.get("human_review_required"):
        return "human_review_required"
    expires_at = parse_utc(str(row.get("expires_at") or ""))
    if expires_at and expires_at <= (now or datetime.now(timezone.utc)):
        return "dream_hypothesis_expired"
    return ""


def dream_hypothesis_nodes_and_edges(
    rows: Iterable[Mapping[str, Any]],
    *,
    journeys: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int]:
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    ignored = 0
    now = datetime.now(timezone.utc)
    journey_ref_keys = {
        f"journey:{journey_id_of(journey)}": source_ref_key_set(journey_refs(journey))
        for journey in journeys
    }
    for row in rows:
        reason = dream_hypothesis_block_reason(row, now=now)
        if reason:
            ignored += 1
            continue
        refs = space_source_refs(row.get("source_refs") or [])
        node_id = "dream_hypothesis:" + str(
            row.get("candidate_key")
            or (row.get("source_finding_ids") or [""])[0]
            or stable_json_id("dream", "reflection-space-id", row.get("title") or "", refs, length=18)
        )
        nodes.append(
            {
                "kind": NODE_KIND,
                "node_type": "dream_hypothesis",
                "node_id": node_id,
                "label": compact_text(str(row.get("title") or row.get("summary") or ""), 160),
                "summary": compact_text(str(row.get("summary") or ""), 360),
                "truth_boundary": str(row.get("truth_boundary") or "adjudicated_dream_hypothesis_not_fact"),
                "dream_function": row.get("dream_function"),
                "metrics": {
                    "confidence": round(float(row.get("confidence") or 0.62), 4),
                    "ranking_weight": 0.18,
                    "visibility_score": 0.18,
                    "visibility": "collapsed",
                },
                "available_actions": ["inspect_source_refs", "compare_counter_evidence", "collapse"],
                "source_refs": list(refs),
                "source_reopen_required_for_strong_claims": True,
                "clean_source_mutation": False,
            }
        )
        bridge = row.get("journey_bridge_hypothesis")
        if isinstance(bridge, Mapping) and bridge.get("status") == "dream_bridge_not_source_fact":
            nodes[-1]["journey_bridge_hypothesis"] = {
                "status": "dream_bridge_not_source_fact",
                "bridge_kind": compact_text(str(bridge.get("bridge_kind") or ""), 80),
                "source_journey_refs": [str(item) for item in bridge.get("source_journey_refs") or []][:4],
                "shared_pattern": compact_text(str(bridge.get("shared_pattern") or ""), 220),
                "unblock_condition": compact_text(str(bridge.get("unblock_condition") or ""), 220),
            }
            nodes[-1]["available_actions"].append("inspect_journey_bridge")
        keys = source_ref_key_set(refs)
        for journey_node_id, journey_keys in journey_ref_keys.items():
            overlap = keys & journey_keys
            if not overlap:
                continue
            edges.append(
                {
                    "kind": EDGE_KIND,
                    "edge_type": "dream_hypothesis_source_overlap",
                    "from": journey_node_id,
                    "to": node_id,
                    "source_refs": list(refs),
                }
            )
    return nodes, edges, ignored


def build_reflection_topology(
    journeys: Iterable[Mapping[str, Any]],
    *,
    feedback_rows: Iterable[Mapping[str, Any]] = (),
    dream_hypotheses: Iterable[Mapping[str, Any]] = (),
    topic_epoch: str = "default",
) -> dict[str, Any]:
    journey_items = tuple(dict(row) for row in journeys if journey_id_of(row))
    journey_by_id = {journey_id_of(row): row for row in journey_items}
    adjustments, ignored_feedback_count = adjustments_from_feedback(
        feedback_rows,
        journey_by_id=journey_by_id,
    )
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    for row in journey_items:
        nodes.append(journey_node(row, journey_count=len(journey_items), adjustments=adjustments))
        waypoint_nodes, waypoint_edges = waypoint_nodes_and_edges(row)
        nodes.extend(waypoint_nodes)
        edges.extend(waypoint_edges)
    dream_nodes, dream_edges, ignored_dream_hypothesis_count = dream_hypothesis_nodes_and_edges(
        dream_hypotheses,
        journeys=journey_items,
    )
    nodes.extend(dream_nodes)
    edges.extend(dream_edges)
    aar_adjustments = [
        adjustment
        for adjustment in adjustments
        if adjustment.get("surface") in {"ranking", "confidence", "visibility"}
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": TOPOLOGY_KIND,
        "created_at": now_utc(),
        "topic_epoch": topic_epoch,
        "nodes": nodes,
        "edges": edges,
        "feedback_adjustments": adjustments,
        "aar_strategy_adjustments": aar_adjustments,
        "ignored_feedback_count": ignored_feedback_count,
        "ignored_dream_hypothesis_count": ignored_dream_hypothesis_count,
        "interaction_contract": {
            "visual_form": "inspectable_topology",
            "supported_user_actions": ["expand", "merge", "revive", "abandon"],
            "feedback_mutates_only": ["ranking", "confidence", "visibility"],
            "aar_or_host_must_apply_visibility_guard": True,
            "dream_hypotheses_are_interpretive_not_facts": True,
            "dream_hypothesis_strong_claim_requires_source_reopen": True,
            "clean_source_mutation": False,
            "journey_history_mutation": False,
            "foreground_delivery_decided_elsewhere": True,
        },
        "can_claim": [
            "small_journey_topology_with_merge_revive_abandon_feedback_adjustments",
            "feedback_adjustments_are_source_ref_carried_and_surface_only",
            "adjudicated_dream_hypotheses_can_be_reflection_nodes_with_source_reopen_boundary",
        ],
        "cannot_claim": [
            "decorative_or_polished_visualization",
            "live_user_behavior_change",
            "dream_hypothesis_is_fact",
            "scheduler_or_aar_runtime_enforcement",
            "foreground_ticket_selection_or_visible_context_suppression",
            "clean_source_rewrite",
            "journey_append_only_history_mutation",
            "agent_suggestions_are_calibrated",
        ],
    }


def fixture_journeys() -> tuple[dict[str, Any], dict[str, Any]]:
    from aippocampus_runtime.reflection.space_fixtures import (
        fixture_journeys as _fixture_journeys,
    )

    return _fixture_journeys()


def run_fixture_smoke() -> dict[str, Any]:
    from aippocampus_runtime.reflection.space_fixtures import (
        run_fixture_smoke as _run_fixture_smoke,
    )

    return _run_fixture_smoke(
        topology_builder=build_reflection_topology,
        schema_version=SCHEMA_VERSION,
        smoke_kind=FIXTURE_SMOKE_KIND,
    )


def default_reflection_space_card() -> dict[str, Any]:
    inspect_fixture = foreground_shell_action(
        action_id="run_reflection_fixture_smoke",
        label="Run reflection fixture smoke",
        command="python -m aippocampus_runtime.reflection.space --fixture-smoke --json",
        mutation_risk="read_only",
        claim_boundary="fixture_topology_is_navigation_only_not_source_truth",
        why="Use the fixture smoke when validating Reflection Space topology contracts.",
    )
    return {
        "ok": True,
        "kind": "reflection_space",
        "status": "operator_only_no_input",
        "operator_only": True,
        "fixture_only_default": True,
        "input_requirements": [
            "journey rows with source refs",
            "optional source-backed feedback rows",
            "optional adjudicated Dream hypotheses",
        ],
        "supported_entrypoints": {
            "fixture_smoke": "python -m aippocampus_runtime.reflection.space --fixture-smoke --json",
        },
        "claim_boundary": "Reflection Space is topology/navigation analysis; reopen source before claims.",
        **canonical_foreground_action_fields(inspect_fixture, safe_next_actions=[]),
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run reflection-space topology helpers. The default command is an "
            "operator-only no-input card; use --fixture-smoke for the public fixture contract."
        )
    )
    parser.add_argument("--fixture-smoke", action="store_true")
    parser.add_argument("--json", action="store_true", help="Emit compact JSON.")
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    payload = run_fixture_smoke() if args.fixture_smoke else default_reflection_space_card()
    text = json.dumps(payload, ensure_ascii=False, indent=None if args.json else 2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
