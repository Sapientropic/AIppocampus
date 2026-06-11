#!/usr/bin/env python3
"""Deterministic maintenance planner for cold navigation-map lifecycle rows."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from aippocampus_runtime.core import now_utc

SCHEMA_VERSION = 1
VALID_ACTIONS = {
    "dead_letter_compact",
    "keep_current",
    "needs_review",
    "prune_or_decay",
    "refresh_source",
    "suppress_until_source_changes",
}
NON_CURRENT_STATES = {
    "stale",
    "challenged",
    "quarantined",
    "superseded",
    "missing_middle",
    "deleted_no_recall",
    "dead_letter",
    "repeated_wrong",
}
TOPOLOGY_REVIEW_SHAPES = {
    "boundary_crossing",
    "collision",
    "coordination_loop",
    "cut_point",
    "handoff_collision",
    "orphan_route",
    "orphaned_handoff",
}
TOPOLOGY_REFRESH_SHAPES = {
    "stale_knot",
}
TOPOLOGY_SUPPRESS_SHAPES = {
    "failed_route_cycle",
    "repeated_failed_route_cycle",
}
HARD_RED_LINE_KEYS = (
    "deleted_no_recall_emit_count",
    "masked_source_resurrection_count",
    "quarantined_route_emit_count",
    "stale_as_current_count",
    "superseded_route_emit_count",
    "wrong_route_revival_count",
)


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _safe_bool(value: Any) -> bool:
    return bool(value)


def _public_case_id(value: Any) -> str:
    text = str(value or "").strip()
    if (
        text
        and len(text) <= 96
        and all(char.isalnum() or char in "-_." for char in text)
    ):
        return text
    digest = hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()[:12]
    return f"case_{digest}"


def _public_label(value: Any, *, fallback: str) -> str:
    text = str(value or "").strip().casefold()
    return text if text and all(char.isalnum() or char in "-_." for char in text) else fallback


def hard_red_lines_for_row(row: Mapping[str, Any]) -> dict[str, int]:
    state = _public_label(row.get("lifecycle_state"), fallback="unknown")
    emitted = _safe_bool(row.get("emitted_route"))
    eligible = _safe_bool(row.get("eligible_for_current_navigation"))
    masked = _safe_bool(row.get("masked")) or state in {"quarantined", "deleted_no_recall"}
    return {
        "deleted_no_recall_emit_count": int(emitted and state == "deleted_no_recall"),
        "masked_source_resurrection_count": int(emitted and masked),
        "quarantined_route_emit_count": int(emitted and state == "quarantined"),
        "stale_as_current_count": int(
            emitted and not eligible and state in {"stale", "challenged", "superseded"}
        ),
        "superseded_route_emit_count": int(emitted and state == "superseded"),
        "wrong_route_revival_count": int(
            emitted and _safe_bool(row.get("repeated_wrong_route"))
        ),
    }


def action_for_row(row: Mapping[str, Any]) -> tuple[str, list[str]]:
    state = _public_label(row.get("lifecycle_state"), fallback="unknown")
    next_action = _public_label(row.get("next_action"), fallback="")
    topology_shape = _public_label(
        row.get("topology_shape") or row.get("diagnostic_shape") or row.get("shape"),
        fallback="",
    )
    reasons = [f"lifecycle_state:{state}"]
    if topology_shape:
        reasons.append(f"topology_shape:{topology_shape}")
    if state == "dead_letter" or _safe_bool(row.get("dead_lettered")):
        return "dead_letter_compact", reasons + ["dead_lettered_artifact"]
    if state == "deleted_no_recall":
        return "prune_or_decay", reasons + ["deleted_no_recall_not_for_hot_surface"]
    if topology_shape in TOPOLOGY_SUPPRESS_SHAPES:
        return "suppress_until_source_changes", reasons + ["topology_route_cycle"]
    if topology_shape in TOPOLOGY_REVIEW_SHAPES:
        return "needs_review", reasons + ["topology_source_route_repair_required"]
    if topology_shape in TOPOLOGY_REFRESH_SHAPES:
        return "refresh_source", reasons + ["topology_stale_knot_requires_source_refresh"]
    if state == "current" and _safe_bool(row.get("eligible_for_current_navigation")):
        return "keep_current", reasons + ["current_route_eligible"]
    if state in {"challenged", "missing_middle"} or _safe_bool(
        row.get("review_needed")
    ) or _safe_bool(row.get("missing_middle_warning")):
        return "needs_review", reasons + ["source_or_human_adjudication_required"]
    if state in {"quarantined", "repeated_wrong"} or _safe_bool(
        row.get("masked")
    ) or _safe_bool(row.get("repeated_wrong_route")):
        return "suppress_until_source_changes", reasons + ["unsafe_for_current_navigation"]
    if state in {"stale", "superseded"} or next_action in {
        "refresh_source",
        "use_successor_after_reopen",
        "review_or_refresh",
    }:
        return "refresh_source", reasons + ["source_currentness_check_required"]
    if _safe_bool(row.get("prunable_or_decay_candidate")):
        return "prune_or_decay", reasons + ["inactive_hot_surface_candidate"]
    if _safe_bool(row.get("eligible_for_current_navigation")) and _safe_bool(
        row.get("emitted_route")
    ):
        return "keep_current", reasons + ["eligible_route_emitted"]
    return "needs_review", reasons + ["unknown_lifecycle_state_requires_review"]


def maintenance_action_for_row(row: Mapping[str, Any]) -> dict[str, Any]:
    action, reasons = action_for_row(row)
    age_days = _safe_int(row.get("age_days"))
    state = _public_label(row.get("lifecycle_state"), fallback="unknown")
    object_kind = _public_label(row.get("object_kind"), fallback="object")
    topology_shape = _public_label(
        row.get("topology_shape") or row.get("diagnostic_shape") or row.get("shape"),
        fallback="",
    )
    remove_from_hot_surface = action != "keep_current"
    payload = {
        "case_id": _public_case_id(row.get("case_id")),
        "object_kind": object_kind,
        "lifecycle_state": state,
        "age_days": age_days,
        "action": action,
        "maintenance_action": {
            "verb": action,
            "write_scope": "no_write_plan_only",
            "source_boundary": "follow_existing_source_refs_before_any_cleanup",
        },
        "reason_codes": reasons,
        "remove_from_hot_surface": remove_from_hot_surface,
        "review_queue": action == "needs_review",
        "reactivation_after_source_refresh": action == "refresh_source",
        "source_reopen_required": action in {"refresh_source", "needs_review"},
        "dead_letter_cleanup": action == "dead_letter_compact",
        "eligible_for_current_navigation": _safe_bool(
            row.get("eligible_for_current_navigation")
        ),
        "emitted_route": _safe_bool(row.get("emitted_route")),
    }
    if topology_shape:
        payload["topology_shape"] = topology_shape
    return payload


def plan_map_rot_maintenance(
    rows: Iterable[Mapping[str, Any]],
    *,
    run_at: str | None = None,
) -> dict[str, Any]:
    row_list = list(rows)
    actions = [maintenance_action_for_row(row) for row in row_list]
    hard_red_lines: Counter[str] = Counter()
    for row in row_list:
        hard_red_lines.update(hard_red_lines_for_row(row))
    action_counts = Counter(str(item["action"]) for item in actions)
    challenged_ages = [
        int(item["age_days"])
        for item in actions
        if item.get("lifecycle_state") == "challenged"
    ]
    metrics = {
        "case_count": len(actions),
        "action_counts": {name: action_counts.get(name, 0) for name in sorted(VALID_ACTIONS)},
        "hot_surface_removal_count": sum(
            1 for item in actions if item["remove_from_hot_surface"]
        ),
        "review_queue_count": sum(1 for item in actions if item["review_queue"]),
        "reactivation_after_source_refresh_count": sum(
            1 for item in actions if item["reactivation_after_source_refresh"]
        ),
        "dead_letter_cleanup_count": sum(1 for item in actions if item["dead_letter_cleanup"]),
        "oldest_challenged_age_days": max(challenged_ages) if challenged_ages else 0,
    }
    red_lines = {name: int(hard_red_lines.get(name, 0)) for name in HARD_RED_LINE_KEYS}
    return {
        "kind": "aippocampus_map_rot_maintenance_plan",
        "schema_version": SCHEMA_VERSION,
        "run_at": run_at or now_utc(),
        "ok": all(value == 0 for value in red_lines.values()),
        "actions": actions,
        "metrics": metrics,
        "hard_red_lines": red_lines,
        "bounded_maintenance_actions": sorted(VALID_ACTIONS),
        "write_mode": "no_write_plan_only",
        "privacy_boundary": {
            "raw_source_text_emitted": False,
            "private_text_emitted": False,
            "local_paths_emitted": False,
            "private_thread_ids_emitted": False,
            "raw_case_payloads_emitted": False,
        },
        "cannot_claim": [
            "source_deleted",
            "audit_history_deleted",
            "conflict_auto_resolved",
            "foreground_hook_cleanup",
            "forgetting_completed",
        ],
    }


def load_rows(path: Path) -> list[Mapping[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return [item for item in data if isinstance(item, Mapping)]
    if isinstance(data, Mapping):
        raw_rows = data.get("cases") or data.get("rows") or data.get("actions") or []
        return [item for item in raw_rows if isinstance(item, Mapping)]
    return []


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="JSON file with lifecycle rows or cases.")
    parser.add_argument("--json", action="store_true", help="Emit JSON report.")
    args = parser.parse_args(argv)

    report = plan_map_rot_maintenance(load_rows(Path(args.input)))
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print("map-rot maintenance status: " + ("ok" if report["ok"] else "blocked"))
        print(f"actions: {report['metrics']['action_counts']}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
