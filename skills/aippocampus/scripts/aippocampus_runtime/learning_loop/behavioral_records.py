"""Inventory and purge local behavioral feedback records.

These records tune navigation and recall behavior. They are deliberately not
source truth, and they must remain discoverable because a quiet local feedback
lane can otherwise feel like hidden memory.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from aippocampus_runtime import core
from aippocampus_runtime.contracts import (
    canonical_foreground_action_fields,
    foreground_shell_action,
)
from aippocampus_runtime.recall.agent_continuity_cli_support import feedback_lane_resolution

TARGET_ALIASES = {
    "effectiveness-ledger": "effectiveness_ledger",
    "effectiveness_ledger": "effectiveness_ledger",
    "recall-outcome-feedback": "recall_outcome_feedback",
    "recall_outcome_feedback": "recall_outcome_feedback",
    "route-feedback": "agent_route_feedback",
    "agent-route-feedback": "agent_route_feedback",
    "agent_route_feedback": "agent_route_feedback",
    "all": "all",
}


def _jsonl_count(path: Path) -> int:
    if not path.exists() or not path.is_file():
        return 0
    try:
        with path.open("r", encoding="utf-8") as handle:
            return sum(1 for line in handle if line.strip())
    except OSError:
        return 0


def _record(record_id: str, *, label: str, path: Path, path_label: str, authority: str) -> dict[str, Any]:
    exists = path.exists()
    return {
        "id": record_id,
        "label": label,
        "status": "available" if exists else "not_found",
        "path": path,
        "path_label": path_label,
        "row_count": _jsonl_count(path),
        "authority": authority,
        "source_truth": False,
        "raw_private_text_loaded": False,
        "purge_supported": True,
    }


def behavioral_records(cwd: Path) -> list[dict[str, Any]]:
    root = cwd.resolve()
    local = root / ".aippocampus"
    lane = feedback_lane_resolution(cwd=root)
    return [
        _record(
            "effectiveness_ledger",
            label="learning effectiveness ledger",
            path=local / "learning-loop" / "effectiveness-ledger.jsonl",
            path_label="workspace/.aippocampus/learning-loop/effectiveness-ledger.jsonl",
            authority="navigation_priority_only_not_source_truth",
        ),
        _record(
            "recall_outcome_feedback",
            label="recall outcome feedback",
            path=local / "recall" / "outcome-feedback.jsonl",
            path_label="workspace/.aippocampus/recall/outcome-feedback.jsonl",
            authority="retrieval_tuning_only_not_source_truth",
        ),
        _record(
            "agent_route_feedback",
            label="agent route feedback",
            path=Path(lane["path"]),
            path_label=str(lane.get("path_label") or "registry/agent/feedback/<workspace-scope>/route-feedback.jsonl"),
            authority="route_calibration_only_not_source_truth",
        ),
    ]


def public_record(row: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if key != "path"}


def _inventory_action() -> dict[str, Any]:
    return foreground_shell_action(
        action_id="review_behavioral_records_inventory",
        label="Review behavioral records inventory",
        command="aippocampus learning behavioral-records --json",
        why="Show which local behavioral feedback records exist without reading private text or changing them.",
        mutation_risk="read_only",
        claim_boundary="behavioral_records_are_feedback_not_source_truth",
    )


def _purge_preview_action(target: str = "all") -> dict[str, Any]:
    return foreground_shell_action(
        action_id="preview_behavioral_records_purge",
        label="Preview behavioral-record purge",
        command=(
            "aippocampus learning purge-behavioral-records "
            f"--target {target} --dry-run --json"
        ),
        why="Preview exactly which local feedback files would be removed before asking for confirmation.",
        mutation_risk="read_only",
        claim_boundary="behavioral_records_are_feedback_not_source_truth",
    )


def _confirm_purge_action(target: str = "all") -> dict[str, Any]:
    action = foreground_shell_action(
        action_id="confirm_behavioral_records_purge",
        label="Confirm behavioral-record purge",
        command=(
            "aippocampus learning purge-behavioral-records "
            f"--target {target} --confirm --json"
        ),
        why="Delete selected local feedback records only after explicit user confirmation.",
        mutation_risk="explicit_local_feedback_delete",
        claim_boundary="behavioral_records_are_feedback_not_source_truth",
    )
    action["requires_explicit_user_confirmation"] = True
    return action


def inventory_payload(cwd: Path) -> dict[str, Any]:
    records = behavioral_records(cwd)
    primary_action = _inventory_action()
    return {
        "kind": "aippocampus_behavioral_records_inventory",
        "schema_version": 1,
        "ok": True,
        "status": "inventory",
        "records": [public_record(row) for row in records],
        "available_record_count": sum(1 for row in records if row["status"] == "available"),
        "privacy_boundary": {
            "raw_private_text_loaded": False,
            "local_paths_included": False,
            "source_truth": False,
        },
        **canonical_foreground_action_fields(
            primary_action,
            safe_next_actions=[primary_action, _purge_preview_action()],
        ),
        "purge_command": "aippocampus learning purge-behavioral-records --target all --dry-run --json",
    }


def _selected_records(records: Iterable[dict[str, Any]], target: str) -> list[dict[str, Any]]:
    normalized = TARGET_ALIASES.get(str(target or "all").strip().casefold(), "")
    if not normalized:
        raise ValueError(f"unknown behavioral record target: {target}")
    materialized = list(records)
    if normalized == "all":
        return materialized
    return [row for row in materialized if row["id"] == normalized]


def _is_owned_path(path: Path, *, cwd: Path) -> bool:
    resolved = path.resolve()
    roots = [
        (cwd.resolve() / ".aippocampus").resolve(),
        core.aippocampus_registry_dir().resolve(),
    ]
    return any(resolved == root or root in resolved.parents for root in roots)


def purge_payload(
    cwd: Path,
    *,
    target: str = "all",
    dry_run: bool = True,
    confirm: bool = False,
) -> dict[str, Any]:
    selected = _selected_records(behavioral_records(cwd), target)
    effective_dry_run = bool(dry_run or not confirm)
    results: list[dict[str, Any]] = []
    deleted = 0
    for row in selected:
        path = Path(row["path"])
        owned = _is_owned_path(path, cwd=cwd)
        exists = path.exists()
        action = "would_delete" if effective_dry_run and exists and owned else "skip"
        if not effective_dry_run and exists and owned:
            path.unlink()
            deleted += 1
            action = "deleted"
        reason = ""
        if not exists:
            reason = "not_found"
        elif not owned:
            reason = "path_outside_aippocampus_owned_allowlist"
        elif effective_dry_run:
            reason = "dry_run_or_missing_confirm"
        results.append(
            {
                **public_record(row),
                "action": action,
                "reason": reason,
            }
        )
    primary_action = _inventory_action()
    action_fields = canonical_foreground_action_fields(
        primary_action,
        safe_next_actions=[primary_action, _purge_preview_action(target)],
    )
    payload: dict[str, Any] = {
        "kind": "aippocampus_behavioral_records_purge",
        "schema_version": 1,
        "ok": True,
        "status": "dry_run" if effective_dry_run else "purged",
        "target": target,
        "dry_run": effective_dry_run,
        "confirm_required": not confirm,
        "deleted_count": deleted,
        "records": results,
        "privacy_boundary": {
            "raw_private_text_loaded": False,
            "local_paths_included": False,
            "source_truth": False,
        },
        **action_fields,
    }
    if effective_dry_run:
        payload["write_next_actions"] = [_confirm_purge_action(target)]
    return payload
