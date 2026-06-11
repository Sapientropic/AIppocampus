#!/usr/bin/env python3
"""Public-safe coordination-topology diagnostics for Telepathy V0."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
KIND = "aippocampus_coordination_topology_diagnostic"
FORBIDDEN_MARKERS = (
    "PRIVATE_COORDINATION_TEXT",
    "raw_private_source_text",
    "source://private",
    "C:\\",
    "/Users/",
)
DIAGNOSTIC_TO_TOPOLOGY_SHAPE = {
    "boundary_crossing": "boundary_crossing",
    "collision": "collision",
    "cut_point": "cut_point",
    "handoff_knot": "handoff_knot",
    "healthy_handoff": "healthy_handoff",
    "loop": "repeated_failed_route_cycle",
    "orphan": "orphaned_handoff",
    "overlap_without_coordination": "collision",
}
DIAGNOSTIC_TO_MAINTENANCE_HINT = {
    "boundary_crossing": "needs_review",
    "collision": "needs_review",
    "cut_point": "needs_review",
    "handoff_knot": "needs_review",
    "healthy_handoff": "keep_current",
    "loop": "suppress_until_source_changes",
    "orphan": "needs_review",
    "overlap_without_coordination": "needs_review",
}
DIAGNOSTIC_TO_OPERATOR_ACTION = {
    "boundary_crossing": "review_boundary_before_cross_agent_use",
    "collision": "open_coordination_packet_or_pause_overlap",
    "cut_point": "review_bridge_before_branch_work",
    "handoff_knot": "review_handoff_before_assignment",
    "healthy_handoff": "continue_with_visible_handoff",
    "loop": "suppress_reopen_loop_and_reopen_source",
    "orphan": "repair_owner_or_source_route",
    "overlap_without_coordination": "explain_coordination_gap",
}


def stable_hash(*parts: Any, length: int = 16) -> str:
    digest = hashlib.sha256(
        "\u241f".join(str(part) for part in parts).encode("utf-8", errors="replace")
    ).hexdigest()
    return digest[:length]


def _text(value: Any) -> str:
    return str(value or "").strip()


def _safe_case_id(value: Any) -> str:
    text = _text(value)
    if (
        text
        and len(text) <= 96
        and all(char.isalnum() or char in "-_." for char in text)
    ):
        return text
    return "case_" + stable_hash(text, length=12)


def _public_label(value: Any, *, fallback: str) -> str:
    text = _text(value).casefold()
    return text if text and all(char.isalnum() or char in "-_." for char in text) else fallback


def _strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [_text(item) for item in value if _text(item)]


def _safe_bool(value: Any) -> bool:
    return bool(value)


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _diagnostic_for_case(row: Mapping[str, Any]) -> str:
    scenario = _public_label(row.get("scenario") or row.get("diagnostic"), fallback="")
    if scenario in DIAGNOSTIC_TO_TOPOLOGY_SHAPE:
        return scenario
    agents = set(_strings(row.get("agents")) or _strings(row.get("active_agents")))
    fragile = _public_label(row.get("scope_fragility"), fallback="") == "fragile"
    handoff_visible = _safe_bool(row.get("handoff_present")) or _safe_bool(
        row.get("coordination_packet_visible")
    )
    if _safe_bool(row.get("privacy_material_crossed")):
        return "boundary_crossing"
    if len(agents) >= 2 and fragile and not handoff_visible:
        return "collision"
    if _safe_bool(row.get("adjacent_scope_overlap")) and not handoff_visible:
        return "overlap_without_coordination"
    if not _text(row.get("owner_agent") or row.get("route_owner")) or not _safe_bool(
        row.get("source_reopenable", True)
    ):
        return "orphan"
    if _safe_int(row.get("bridge_branch_count")) >= 2 and _safe_int(
        row.get("alternative_bridge_count")
    ) == 0:
        return "cut_point"
    if _safe_int(row.get("reopen_attempt_count")) >= 3 and _public_label(
        row.get("route_state"),
        fallback="",
    ) in {"stale", "rejected", "blocked"}:
        return "loop"
    if _safe_bool(row.get("ownership_conflict")) or _public_label(
        row.get("source_support_state"),
        fallback="",
    ) in {"candidate", "missing", "conflicted"}:
        return "handoff_knot"
    return "healthy_handoff"


def evaluate_coordination_case(row: Mapping[str, Any]) -> dict[str, Any]:
    diagnostic = _diagnostic_for_case(row)
    agents = _strings(row.get("agents")) or _strings(row.get("active_agents"))
    scope_ids = _strings(row.get("scope_ids"))
    privacy_crossing = diagnostic == "boundary_crossing"
    privacy_clean_useless = diagnostic == "overlap_without_coordination" and not privacy_crossing
    return {
        "kind": "aippocampus_coordination_topology_row",
        "schema_version": SCHEMA_VERSION,
        "case_id": _safe_case_id(row.get("case_id")),
        "diagnostic": diagnostic,
        "topology_shape": DIAGNOSTIC_TO_TOPOLOGY_SHAPE[diagnostic],
        "maintenance_action_hint": DIAGNOSTIC_TO_MAINTENANCE_HINT[diagnostic],
        "next_operator_action": DIAGNOSTIC_TO_OPERATOR_ACTION[diagnostic],
        "navigation_only": True,
        "assignment_created": False,
        "claim_permission": "no_claim_before_source_reopen",
        "agent_count": len(agents),
        "agent_group_hash": stable_hash(*sorted(agents)) if agents else "agent_group_empty",
        "scope_hash": stable_hash(*sorted(scope_ids)) if scope_ids else "scope_empty",
        "source_reopen_required": diagnostic != "healthy_handoff",
        "privacy_boundary_crossing_detected": privacy_crossing,
        "privacy_clean_but_coordination_useless": privacy_clean_useless,
        "reason_codes": [
            f"diagnostic:{diagnostic}",
            "telepathy_navigation_explain_only",
            "foreground_agent_judgment_retained",
        ],
    }


def fixture_coordination_cases() -> list[dict[str, Any]]:
    return [
        {
            "case_id": "healthy_handoff",
            "scenario": "healthy_handoff",
            "agents": ["codex-a", "codex-b"],
            "scope_ids": ["docs.telepathy"],
            "handoff_present": True,
            "coordination_packet_visible": True,
            "owner_agent": "codex-b",
            "source_reopenable": True,
        },
        {
            "case_id": "collision_without_handoff",
            "scenario": "collision",
            "agents": ["codex-a", "codex-b"],
            "scope_ids": ["skills.recall.fragile"],
            "scope_fragility": "fragile",
            "handoff_present": False,
            "coordination_packet_visible": False,
            "owner_agent": "codex-a",
            "source_reopenable": True,
        },
        {
            "case_id": "overlap_privacy_clean_but_useless",
            "scenario": "overlap_without_coordination",
            "agents": ["codex-a", "codex-b"],
            "scope_ids": ["docs.telepathy", "docs.agent-native"],
            "adjacent_scope_overlap": True,
            "coordination_packet_visible": False,
            "owner_agent": "codex-a",
            "source_reopenable": True,
        },
        {
            "case_id": "orphaned_route_packet",
            "scenario": "orphan",
            "agents": ["codex-a"],
            "scope_ids": ["route.orphan"],
            "owner_agent": "",
            "source_reopenable": False,
        },
        {
            "case_id": "single_bridge_cut_point",
            "scenario": "cut_point",
            "agents": ["codex-a", "codex-b"],
            "scope_ids": ["branch.alpha", "branch.beta"],
            "bridge_branch_count": 2,
            "alternative_bridge_count": 0,
            "owner_agent": "codex-a",
            "source_reopenable": True,
        },
        {
            "case_id": "private_boundary_crossing",
            "scenario": "boundary_crossing",
            "agents": ["codex-a", "codex-b"],
            "scope_ids": ["private.scope"],
            "owner_agent": "codex-a",
            "visible_to_agent": "codex-b",
            "privacy_material_crossed": True,
            "private_payload": "PRIVATE_COORDINATION_TEXT fixture sentinel",
            "source_handle": "source://private/fixture",
        },
        {
            "case_id": "stale_route_loop",
            "scenario": "loop",
            "agents": ["codex-a", "codex-b"],
            "scope_ids": ["route.stale-loop"],
            "owner_agent": "codex-a",
            "source_reopenable": True,
            "route_state": "stale",
            "reopen_attempt_count": 3,
        },
        {
            "case_id": "handoff_source_knot",
            "scenario": "handoff_knot",
            "agents": ["codex-a", "codex-b"],
            "scope_ids": ["handoff.knot"],
            "handoff_present": True,
            "ownership_conflict": True,
            "source_support_state": "candidate",
            "owner_agent": "codex-a",
            "source_reopenable": True,
        },
    ]


def build_coordination_topology_report(
    rows: Iterable[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    row_list = list(rows) if rows is not None else fixture_coordination_cases()
    diagnostics = [evaluate_coordination_case(row) for row in row_list]
    counts: Counter[str] = Counter(item["diagnostic"] for item in diagnostics)
    forbidden_marker_count = sum(
        1
        for marker in FORBIDDEN_MARKERS
        if marker in json.dumps(diagnostics, ensure_ascii=False, sort_keys=True)
    )
    work_assignment_count = sum(1 for item in diagnostics if item["assignment_created"])
    red_lines = {
        "private_payload_emitted_count": forbidden_marker_count,
        "local_path_emitted_count": forbidden_marker_count,
        "source_handle_emitted_count": forbidden_marker_count,
        "chain_of_thought_emitted_count": 0,
        "work_assignment_count": work_assignment_count,
    }
    metrics = {
        "case_count": len(diagnostics),
        "agent_collision_count": counts["collision"],
        "overlap_without_coordination_count": counts["overlap_without_coordination"],
        "orphaned_handoff_count": counts["orphan"],
        "cut_point_count": counts["cut_point"],
        "boundary_crossing_count": counts["boundary_crossing"],
        "repeated_stale_route_loop_count": counts["loop"],
        "handoff_knot_count": counts["handoff_knot"],
        "healthy_handoff_count": counts["healthy_handoff"],
        "privacy_clean_but_coordination_useless_count": sum(
            1 for item in diagnostics if item["privacy_clean_but_coordination_useless"]
        ),
    }
    expected_shapes = {
        "boundary_crossing",
        "collision",
        "cut_point",
        "handoff_knot",
        "healthy_handoff",
        "loop",
        "orphan",
        "overlap_without_coordination",
    }
    contract_gate_ok = rows is not None or expected_shapes.issubset(set(counts))
    safety_gate_ok = all(value == 0 for value in red_lines.values())
    usefulness_gate_ok = metrics["privacy_clean_but_coordination_useless_count"] == 0
    return {
        "kind": KIND,
        "schema_version": SCHEMA_VERSION,
        "ok": contract_gate_ok and safety_gate_ok,
        "contract_gate_ok": contract_gate_ok,
        "safety_gate_ok": safety_gate_ok,
        "usefulness_gate_ok": usefulness_gate_ok,
        "write_mode": "no_write_diagnostic_only",
        "authority_level": "navigation_explain_only",
        "runtime_position": "post_packet_explain_side",
        "every_turn_scan": False,
        "ranking_weight_changes": False,
        "foreground_hook_mutation": False,
        "foreground_projection": "tiny_tag_only_when_action_selection_changes",
        "diagnostics": diagnostics,
        "metrics": metrics,
        "red_lines": red_lines,
        "privacy_boundary": {
            "raw_private_text_emitted": False,
            "local_paths_emitted": False,
            "source_handles_emitted": False,
            "chain_of_thought_emitted": False,
            "forbidden_marker_count": forbidden_marker_count,
        },
        "contract": {
            "diagnostics_are_navigation_explain_only": True,
            "does_not_assign_work": True,
            "foreground_agent_judgment_retained": True,
            "post_packet_explain_side_only": True,
            "not_every_turn_scan": True,
            "full_detail_belongs_to_explain_debug_or_campus": True,
            "cross_agent_isolation_applies_before_output": True,
            "source_reopen_required_before_claim": True,
        },
        "cannot_claim": [
            "telepathy_orchestration_complete",
            "distributed_locks_implemented",
            "private_multi_agent_history_quality",
            "coordination_diagnostic_overrides_agent_judgment",
            "shared_chain_of_thought",
        ],
    }


def load_rows(path: Path) -> list[Mapping[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return [item for item in data if isinstance(item, Mapping)]
    if isinstance(data, Mapping):
        raw_rows = data.get("cases") or data.get("rows") or data.get("diagnostics") or []
        return [item for item in raw_rows if isinstance(item, Mapping)]
    return []


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", help="JSON file with coordination rows or cases.")
    parser.add_argument("--fixture", action="store_true", help="Use the built-in fixture.")
    parser.add_argument("--json", action="store_true", help="Emit JSON report.")
    args = parser.parse_args(argv)

    rows = load_rows(Path(args.input)) if args.input else None
    report = build_coordination_topology_report(rows)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(
            "coordination topology: "
            + ("ok" if report["ok"] else "diagnostics_found")
        )
        print(f"metrics: {report['metrics']}")
    return 0 if report["safety_gate_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
