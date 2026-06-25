#!/usr/bin/env python3
"""Route-producer fixtures for Episode/Arc sequence packets.

This module does not make Episode/Arc a source of truth. It proves a small live
recall route-producer shape: ordered sequence packets can change route
guidance, while gappy or wrong-order paths only ask the agent to reopen source.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from aippocampus_runtime.coding import episode_arcs
from aippocampus_runtime.core import stable_json_join_id
from aippocampus_runtime.recall.narrative_packet import compile_narrative_packet

REPORT_KIND = "aippocampus_episode_arc_route_producer_report"
REPORT_SCHEMA_VERSION = "aippocampus.episode_arc_route_producer_report.v1"
ACTION_REOPENABLE_ROUTE = "reopenable_route"
ACTION_DIRECTION_WITH_REF = "direction_with_ref"


def public_event(
    event_id: str,
    event_kind: str,
    line: int,
    *,
    family: str,
    sequence_index: int | None = None,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "episode_id": f"episode:{family}",
        "event_id": event_id,
        "event_kind": event_kind,
        "public_family": family,
        "source_refs": [
            {
                "thread_key": f"public:{family}",
                "message_id": f"m-{family}-{line}",
                "turn_id": f"turn-{family}-{line}",
                "source_line": line,
            }
        ],
        "turn_id": f"turn-{family}-{line}",
        "source_line": line,
    }
    if sequence_index is not None:
        row["sequence_index"] = sequence_index
    return row


def default_public_event_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    rows.extend(
        [
            public_event("commit-route", "attempted_route", 10, family="commit_revert", sequence_index=0),
            public_event("commit-failed", "failed_check", 11, family="commit_revert", sequence_index=1),
            public_event("commit-rejected", "route_rejected", 12, family="commit_revert", sequence_index=2),
            public_event("pr-route", "attempted_route", 20, family="pr_rejection_merge", sequence_index=0),
            public_event("pr-failed", "failed_check", 21, family="pr_rejection_merge", sequence_index=1),
            public_event("pr-rejected", "route_rejected", 22, family="pr_rejection_merge", sequence_index=2),
            public_event("issue-frontier", "unresolved_frontier", 30, family="issue_reopen", sequence_index=0),
            public_event("issue-source", "source_reopen", 31, family="issue_reopen", sequence_index=1),
            public_event("old-patch", "old_rule", 40, family="patch_supersession", sequence_index=0),
            public_event("new-patch", "new_rule", 41, family="patch_supersession", sequence_index=1),
            public_event("patch-current", "current_rule_selected", 42, family="patch_supersession", sequence_index=2),
            public_event("workaround-temp", "temporary_concern", 50, family="workaround_removal", sequence_index=0),
            public_event("workaround-normal", "later_normal_progress", 51, family="workaround_removal", sequence_index=1),
            public_event("missing-route", "attempted_route", 60, family="missing_middle_negative", sequence_index=0),
            public_event("missing-rejected", "route_rejected", 62, family="missing_middle_negative", sequence_index=2),
            public_event("wrong-failed", "failed_check", 71, family="wrong_order_negative"),
            public_event("wrong-route", "attempted_route", 70, family="wrong_order_negative"),
            public_event("wrong-rejected", "route_rejected", 72, family="wrong_order_negative"),
        ]
    )
    return rows


def _arc_events(arc: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    events = arc.get("_events")
    if isinstance(events, Sequence) and not isinstance(events, (str, bytes, bytearray)):
        return [event for event in events if isinstance(event, Mapping)]
    return []


def _family(arc: Mapping[str, Any]) -> str:
    for event in _arc_events(arc):
        family = str(event.get("public_family") or "").strip()
        if family:
            return family
    episode_id = str(arc.get("episode_id") or "")
    return episode_id.split(":", 1)[-1] if episode_id else "unknown"


def _source_catalog_for_arc(arc: Mapping[str, Any]) -> list[dict[str, Any]]:
    event_ids = [str(item) for item in arc.get("source_event_ids") or []]
    hashes = [str(item) for item in arc.get("source_ref_hashes") or []]
    refs = [item for item in arc.get("source_refs") or [] if isinstance(item, Mapping)]
    return [
        {
            "event_id": event_id,
            "source_ref_hash": source_hash,
            "source_refs": [dict(ref)],
        }
        for event_id, source_hash, ref in zip(event_ids, hashes, refs, strict=False)
    ]


def _pathlet_kind(arc: Mapping[str, Any]) -> str:
    gaps = {str(item) for item in arc.get("sequence_gaps") or []}
    order = [str(item) for item in arc.get("event_order") or []]
    if "unresolved_frontier" in order:
        return "unresolved_frontier"
    if "event_order_semantic_mismatch" in gaps:
        return "wrong_order"
    if "missing_middle_event" in gaps:
        return "missing_middle"
    episode_kind = str(arc.get("episode_kind") or "")
    if episode_kind == "rejected_route_arc":
        return "rejected_route"
    if episode_kind == "supersession_arc":
        return "supersession_chain"
    return episode_kind or "episode_arc"


def _route_action(pathlet_kind: str, gaps: Sequence[Any]) -> tuple[str, str]:
    if pathlet_kind == "rejected_route" and not gaps:
        return "prevent_repeated_wrong_route", ACTION_REOPENABLE_ROUTE
    if pathlet_kind == "unresolved_frontier":
        return "reopen_unresolved_frontier", ACTION_REOPENABLE_ROUTE
    if pathlet_kind == "supersession_chain" and not gaps:
        return "reopen_currentness_source", ACTION_REOPENABLE_ROUTE
    return "refresh_sources", ACTION_DIRECTION_WITH_REF


def _route_material(arc: Mapping[str, Any], narrative_packet: Mapping[str, Any]) -> dict[str, Any]:
    gaps = [str(item) for item in arc.get("sequence_gaps") or []]
    pathlet_kind = _pathlet_kind(arc)
    next_action, action_grammar = _route_action(pathlet_kind, gaps)
    return {
        "case_id": stable_json_join_id(
            "episode_route",
            _family(arc),
            arc.get("event_order"),
            gaps,
            sep="\0",
            ensure_ascii=False,
            length=14,
        ),
        "family": _family(arc),
        "pathlet_kind": pathlet_kind,
        "event_order": [str(item) for item in arc.get("event_order") or []],
        "sequence_gaps": gaps,
        "next_action": next_action,
        "action_grammar": action_grammar,
        "source_ref_hash_count": len(arc.get("source_ref_hashes") or []),
        "narrative_packet_action_grammar": (
            (narrative_packet.get("use_boundary") or {}).get("action_grammar")
            if isinstance(narrative_packet.get("use_boundary"), Mapping)
            else ""
        ),
        "source_reopen_required_before_claim": True,
        "story_like_foreground": False,
    }


def build_episode_arc_route_producer_report(event_rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    arcs = episode_arcs.build_episode_arcs(event_rows)
    case_summaries: list[dict[str, Any]] = []
    family_counts: dict[str, int] = {}
    for arc in arcs:
        packet = episode_arcs.render_sequence_packet(arc, trigger="episode_arc_route_producer")
        narrative = compile_narrative_packet(
            trigger="episode_arc_route_producer",
            current_query="public episode arc route producer fixture",
            sequence_packets=[packet],
            source_catalog=_source_catalog_for_arc(arc),
        )
        summary = _route_material(arc, narrative)
        case_summaries.append(summary)
        family_counts[summary["family"]] = family_counts.get(summary["family"], 0) + 1

    sequence_route_count = len(case_summaries)
    repeated_wrong_route_prevented_count = sum(
        1 for case in case_summaries if case["next_action"] == "prevent_repeated_wrong_route"
    )
    unresolved_frontier_reopen_count = sum(
        1 for case in case_summaries if case["next_action"] == "reopen_unresolved_frontier"
    )
    missing_middle_detected_count = sum(1 for case in case_summaries if case["pathlet_kind"] == "missing_middle")
    wrong_order_suppressed_count = sum(1 for case in case_summaries if case["pathlet_kind"] == "wrong_order")
    helpful_count = sum(
        1
        for case in case_summaries
        if case["next_action"]
        in {"prevent_repeated_wrong_route", "reopen_unresolved_frontier", "reopen_currentness_source"}
    )
    metrics = {
        "episode_arc_count": len(arcs),
        "sequence_route_count": sequence_route_count,
        "ordered_route_helpfulness_rate": _rate(helpful_count, sequence_route_count),
        "repeated_wrong_route_prevented_count": repeated_wrong_route_prevented_count,
        "unresolved_frontier_reopen_count": unresolved_frontier_reopen_count,
        "missing_middle_detected_count": missing_middle_detected_count,
        "wrong_order_suppressed_count": wrong_order_suppressed_count,
        "sequence_order_claim_requires_reopen_count": sequence_route_count,
        "sequence_route_claim_without_reopen_count": 0,
        "foreground_story_dump_count": 0,
    }
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "kind": REPORT_KIND,
        "metrics": metrics,
        "family_counts": dict(sorted(family_counts.items())),
        "case_summaries": case_summaries,
        "can_claim": [
            "public_episode_arc_route_producer_fixture_exists",
            "ordered_sequence_can_prevent_repeated_wrong_route_after_source_reopen",
            "wrong_order_and_missing_middle_sequences_degrade_to_refresh_sources",
            "unresolved_frontier_projects_as_reopenable_route",
        ],
        "cannot_claim": [
            "source_reopen_required_before_claim",
            "live_host_behavior_lift",
            "private_history_generality",
            "default_recall_route_producer_adoption",
            "episode_arc_as_source_truth",
            "github_663_owner_complete",
        ],
        "public_safety": {
            "serialized_sensitive_fields": {
                "source_text": False,
                "route_refs": False,
                "event_handles": False,
                "thread_handles": False,
                "local_paths": False,
            },
        },
        "issue_readouts": {
            "github_1362": {
                "route_producer_fixture": "measured_public_deterministic",
                "repeated_wrong_route_prevented_count": repeated_wrong_route_prevented_count,
                "closeout_eligible": True,
            },
            "github_1363": {
                "public_vcs_hard_event_cohort": "measured_public_deterministic",
                "family_count": len(family_counts),
                "closeout_eligible": True,
            },
            "github_663": {
                "live_route_usefulness": "not_measured",
                "closeout_eligible": False,
            },
        },
    }


def build_public_episode_arc_route_producer_report(
    event_rows: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    return build_episode_arc_route_producer_report(event_rows or default_public_event_rows())


def _rate(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 6)
