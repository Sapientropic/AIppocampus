"""Fixture-only reflection-space smoke helpers.

The reflection topology owner should stay focused on source-backed graph and
feedback semantics. These fixtures are deliberately split out so future demo or
regression material does not grow the production topology file.
"""

from __future__ import annotations

from collections.abc import Callable
from importlib import import_module
from typing import Any

from aippocampus_runtime.journey.tracking import (
    create_journey,
    fixture_waypoints,
    journey_to_dict,
)

_SCHEMA_VERSION = 1
_FIXTURE_SMOKE_KIND = "aippocampus_reflection_space_fixture_smoke"


def fixture_journeys() -> tuple[dict[str, Any], dict[str, Any]]:
    first = create_journey(
        path_label="continuity after change",
        core_inquiry="How can continuity survive change and compaction without false memory claims?",
        waypoint_rows=fixture_waypoints(),
        active_questions=["what survives compaction?"],
    )
    second_rows = [
        {
            **row,
            "moment": str(row["moment"]).replace("continuity", "reflection"),
            "thread_id": f"session:reflection-{idx}",
            "source_refs": [{"thread_key": f"session:reflection-{idx}", "message_id": f"msg-r{idx}"}],
        }
        for idx, row in enumerate(fixture_waypoints(), start=1)
    ]
    second = create_journey(
        path_label="reflection-space review",
        core_inquiry="How can a map room change review behavior without becoming an aggressive suggestion engine?",
        waypoint_rows=second_rows,
        active_questions=["should the map stay quiet?"],
    )
    if not first.created or first.journey is None or not second.created or second.journey is None:
        raise RuntimeError("reflection fixture journey creation failed")
    abandoned_second = second.journey.__class__(**{**second.journey.__dict__, "status": "abandoned"})
    return journey_to_dict(first.journey), journey_to_dict(abandoned_second)


def _default_topology_builder() -> Callable[..., dict[str, Any]]:
    space = import_module("aippocampus_runtime.reflection.space")
    return space.build_reflection_topology


def run_fixture_smoke(
    *,
    topology_builder: Callable[..., dict[str, Any]] | None = None,
    schema_version: int = _SCHEMA_VERSION,
    smoke_kind: str = _FIXTURE_SMOKE_KIND,
) -> dict[str, Any]:
    first, second = fixture_journeys()
    feedback = [
        {
            "action": "recall_helpful",
            "journey_id": first["journey_id"],
            "note": "A source-backed recall card changed the review direction.",
            "source_refs": first["current_frontier_source_refs"],
        },
        {
            "action": "revive",
            "journey_id": second["journey_id"],
            "note": "User chose to continue the camped map-room path.",
            "source_refs": second["source_refs"][:1],
        },
    ]
    build_topology = topology_builder or _default_topology_builder()
    topology = build_topology([first, second], feedback_rows=feedback, topic_epoch="fixture")
    has_actions = any("merge" in node.get("available_actions", []) for node in topology["nodes"])
    has_revival = any("revive" in node.get("available_actions", []) for node in topology["nodes"])
    has_adjustments = bool(topology["feedback_adjustments"])
    return {
        "schema_version": schema_version,
        "kind": smoke_kind,
        "ok": has_actions and has_revival and has_adjustments,
        "status": "sufficient" if has_actions and has_revival and has_adjustments else "insufficient",
        "metrics": {
            "node_count": len(topology["nodes"]),
            "edge_count": len(topology["edges"]),
            "feedback_adjustment_count": len(topology["feedback_adjustments"]),
        },
        "topology": topology,
    }
