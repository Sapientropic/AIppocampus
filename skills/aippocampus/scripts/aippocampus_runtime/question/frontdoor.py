#!/usr/bin/env python3
"""Foreground read path for source-backed question tracking."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

from aippocampus_runtime.contracts import canonical_foreground_action_fields, shell_quote
from aippocampus_runtime.question.constants import DEFAULT_DORMANT_AFTER_DAYS
from aippocampus_runtime.question.health import (
    aggregate_question_health_stats,
    question_health_stats,
)
from aippocampus_runtime.registry.api import registry_paths
from aippocampus_runtime.subconscious.jobs_config import default_jobs_output_path


def _default_jobs_path(args: argparse.Namespace) -> Path:
    if args.jobs:
        return Path(args.jobs).resolve()
    registry_path = Path(args.registry).resolve() if args.registry else None
    registry_dir = Path(args.registry_dir).resolve() if args.registry_dir else None
    return default_jobs_output_path(registry_path=registry_path, registry_dir=registry_dir)


def _default_registry_path(args: argparse.Namespace) -> Path | None:
    if args.registry:
        return Path(args.registry).resolve()
    registry_dir = Path(args.registry_dir).resolve() if args.registry_dir else None
    json_path, _ = registry_paths(registry_dir)
    return json_path


def _status_payload(args: argparse.Namespace) -> dict[str, Any]:
    payload = question_health_stats(
        _default_jobs_path(args),
        registry_path=_default_registry_path(args),
        dormant_after_days=args.dormant_after_days,
    )
    summary = aggregate_question_health_stats(payload)
    summary.pop("jobs", None)
    summary.pop("registry", None)
    open_count = _safe_int(summary.get("open_question_count"))
    if open_count:
        foreground_action: dict[str, Any] = {
            "id": "list_open_question_routes",
            "label": "List open question routes",
            "command": f"aippocampus questions list --max {int(args.max or 8)} --json",
            "mutation_risk": "read_only",
            "claim_boundary": "question_rows_are_navigation_only_reopen_source_before_claims",
            "why": "Status found open source-backed questions; list rows to get reopenable routes.",
        }
    else:
        foreground_action = {
            "id": "continue_with_ordinary_recall",
            "label": "Continue with ordinary recall",
            "command": "aippocampus agent recall --json",
            "mutation_risk": "read_only",
            "claim_boundary": "question_status_no_open_routes_not_memory_evidence",
            "why": "No open question rows were found; use ordinary source-backed recall when needed.",
        }
    safe_next_actions = [
        foreground_action,
        {
            "id": "inspect_question_status",
            "label": "Inspect question status",
            "command": "aippocampus questions status --json",
            "mutation_risk": "read_only",
            "claim_boundary": "question_lifecycle_stats_are_navigation_only",
        },
    ]
    action_fields = canonical_foreground_action_fields(
        foreground_action,
        safe_next_actions=safe_next_actions,
    )
    return {
        "kind": "aippocampus_question_tracking_status",
        "ok": True,
        "mode": "status",
        "available": bool(payload.get("available")),
        "summary": summary,
        "source_boundary": {
            "question_tracking_is_navigation_only": True,
            "source_reopen_required_before_claim": True,
            "model_job_started": False,
            "local_paths_serialized": False,
        },
        "privacy_boundary": {
            "raw_jobs_serialized": False,
            "local_paths_serialized": False,
            "raw_private_text_serialized": False,
        },
        **action_fields,
    }


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _search_command(
    title: Any,
    *,
    source_ref_count: int = 0,
    source_thread_count: int = 0,
) -> str:
    query = str(title or "question route").strip() or "question route"
    if source_ref_count > 0 or source_thread_count > 0:
        return f"aippocampus search --all {shell_quote(query)} --json"
    return f"aippocampus search {shell_quote(query)} --json"


def _row_action(
    *,
    action_id: str,
    label: str,
    command: str,
    why: str,
    claim_boundary: str = "question_rows_are_navigation_only_reopen_source_before_claims",
) -> dict[str, Any]:
    return {
        "id": action_id,
        "label": label,
        "command": command,
        "mutation_risk": "read_only",
        "claim_boundary": claim_boundary,
        "why": why,
    }


def _question_action_card(item: Mapping[str, Any]) -> dict[str, Any]:
    title = item.get("title")
    state = str(item.get("state") or "unknown")
    source_ref_count = _safe_int(item.get("source_ref_count"))
    source_thread_count = _safe_int(item.get("source_thread_count"))
    command = _search_command(
        title,
        source_ref_count=source_ref_count,
        source_thread_count=source_thread_count,
    )
    row: dict[str, Any] = {
        "unit_id": item.get("unit_id"),
        "title": title,
        "state": state,
        "first_seen": item.get("first_seen"),
        "last_seen": item.get("last_seen"),
        "source_ref_count": source_ref_count,
        "source_thread_count": source_thread_count,
        "source_reopen_required_before_claim": True,
    }
    if source_ref_count <= 0:
        row.update(
            {
                "action_grammar": "ignore_or_blocked",
                "route_state": "blocked_missing_source_refs",
                "blocked_reason": "source refs are missing or no longer resolve",
                "foreground_action": _row_action(
                    action_id="repair_question_source_refs",
                    label="Repair question source refs",
                    command="aippocampus questions status --json",
                    why=(
                        "This row has no reopenable source refs; inspect question status "
                        "before using it as a route."
                    ),
                    claim_boundary="missing_question_source_refs_block_foreground_claims",
                ),
                "source_route": None,
            }
        )
        return row

    route = {
        "kind": "clean_source_question_refs",
        "source_ref_count": source_ref_count,
        "source_thread_count": source_thread_count,
        "reopen_command": command,
        "reopen_scope": (
            "registry_wide"
            if source_ref_count > 0 or source_thread_count > 0
            else "current_thread"
        ),
        "claim_boundary": "reopen source before treating this question state as evidence",
    }
    if state == "resolved":
        row.update(
            {
                "action_grammar": "bounded_evidence",
                "route_state": "resolved_recheck_before_use",
                "foreground_action": _row_action(
                    action_id="recheck_resolved_question_source",
                    label="Recheck resolved question source",
                    command=command,
                    why="Treat this as resolved only after reopening the source route.",
                ),
                "source_route": route,
            }
        )
    elif state == "dormant":
        row.update(
            {
                "action_grammar": "reopenable_route",
                "route_state": "dormant_recheck_before_reviving",
                "foreground_action": _row_action(
                    action_id="recheck_dormant_question_source",
                    label="Recheck dormant question source",
                    command=command,
                    why="Reopen the route before reviving a dormant question.",
                ),
                "source_route": route,
            }
        )
    else:
        row.update(
            {
                "action_grammar": "reopenable_route",
                "route_state": "ready_to_reopen",
                "foreground_action": _row_action(
                    action_id="reopen_question_source",
                    label="Reopen question source",
                    command=command,
                    why="Reopen source before using this question row as continuity evidence.",
                ),
                "source_route": route,
            }
        )
    return row


def _blocked_ref_card(count: int) -> dict[str, Any]:
    return {
        "unit_id": "question_rows_with_missing_source_refs",
        "title": f"{count} question rows need source-ref repair",
        "state": "blocked",
        "source_ref_count": 0,
        "source_thread_count": 0,
        "source_reopen_required_before_claim": True,
        "action_grammar": "ignore_or_blocked",
        "route_state": "blocked_missing_source_refs",
        "blocked_reason": "some question rows had missing or unresolved source refs",
        "foreground_action": _row_action(
            action_id="repair_question_source_refs",
            label="Repair question source refs",
            command="aippocampus questions status --json",
            why=(
                "Confirm the unresolved-ref count before using blocked question rows."
            ),
            claim_boundary="missing_question_source_refs_block_foreground_claims",
        ),
        "source_route": None,
    }


def _row_action_priority(row: Mapping[str, Any], index: int) -> tuple[int, int]:
    state = str(row.get("state") or "")
    route_state = str(row.get("route_state") or "")
    if state == "open" and route_state == "ready_to_reopen":
        return (0, index)
    if route_state == "ready_to_reopen":
        return (1, index)
    if state == "dormant":
        return (2, index)
    if state == "resolved":
        return (3, index)
    if route_state.startswith("blocked"):
        return (5, index)
    return (4, index)


def _list_payload(args: argparse.Namespace) -> dict[str, Any]:
    payload = question_health_stats(
        _default_jobs_path(args),
        registry_path=_default_registry_path(args),
        dormant_after_days=args.dormant_after_days,
    )
    rows = []
    max_rows = max(0, int(args.max or 0))
    for item in list(payload.get("lifecycle") or [])[:max_rows]:
        if not isinstance(item, Mapping):
            continue
        rows.append(_question_action_card(item))
    unresolved_count = _safe_int(payload.get("stale_or_unresolved_ref_row_count"))
    if unresolved_count and len(rows) < max_rows:
        rows.append(_blocked_ref_card(unresolved_count))
    if rows:
        prioritized_rows = sorted(
            enumerate(rows),
            key=lambda pair: _row_action_priority(pair[1], pair[0]),
        )
        primary_action = next(
            (
                row["foreground_action"]
                for _, row in prioritized_rows
                if isinstance(row.get("foreground_action"), Mapping)
            ),
            {
                "id": "inspect_question_status",
                "label": "Inspect question status",
                "command": "aippocampus questions status --json",
                "mutation_risk": "read_only",
                "claim_boundary": "question_rows_are_navigation_only_reopen_source_before_claims",
                "why": "Inspect question status before using ambiguous rows.",
            },
        )
        primary_row = next(
            (
                row
                for _, row in prioritized_rows
                if row.get("foreground_action") == primary_action
            ),
            None,
        )
        primary_selection = {
            "strategy": "open_ready_routes_before_dormant",
            "row_title": primary_row.get("title") if isinstance(primary_row, Mapping) else None,
            "row_state": primary_row.get("state") if isinstance(primary_row, Mapping) else None,
            "route_state": primary_row.get("route_state") if isinstance(primary_row, Mapping) else None,
        }
        empty_state = None
    else:
        primary_action = {
            "id": "continue_with_ordinary_recall",
            "label": "Continue with ordinary recall",
            "command": "aippocampus agent recall --json",
            "mutation_risk": "read_only",
            "claim_boundary": "question_list_empty_not_memory_evidence",
            "why": "No question tracking rows are ready; use ordinary source-backed recall when needed.",
        }
        empty_state = {
            "state": "no_source_backed_question_rows",
            **canonical_foreground_action_fields(
                primary_action,
                safe_next_actions=[
                    primary_action,
                {
                    "id": "inspect_question_status",
                    "label": "Inspect question status",
                    "command": "aippocampus questions status --json",
                    "mutation_risk": "read_only",
                    "claim_boundary": "question_lifecycle_stats_are_navigation_only",
                    "why": "Check whether rows are missing, blocked, or simply absent.",
                },
                ],
            ),
        }
        primary_selection = {
            "strategy": "empty_list_ordinary_recall",
            "row_title": None,
            "row_state": None,
            "route_state": None,
        }
    action_fields = canonical_foreground_action_fields(
        primary_action,
        safe_next_actions=[
            primary_action,
            {
                "id": "inspect_question_status",
                "label": "Inspect question status",
                "command": "aippocampus questions status --json",
                "mutation_risk": "read_only",
                "claim_boundary": "question_lifecycle_stats_are_navigation_only",
                "why": "Use for aggregate question lifecycle state before row-level reopen.",
            },
        ],
    )
    return {
        "kind": "aippocampus_question_tracking_list",
        "ok": True,
        "mode": "list",
        "available": bool(payload.get("available")),
        "count": len(rows),
        "rows": rows,
        "primary_selection": {
            key: value for key, value in primary_selection.items() if value not in (None, "")
        },
        "empty_state": empty_state,
        "source_boundary": {
            "rows_are_navigation_not_source_truth": True,
            "source_reopen_required_before_claim": True,
            "model_job_started": False,
            "local_paths_serialized": False,
        },
        "privacy_boundary": {
            "raw_jobs_serialized": False,
            "local_paths_serialized": False,
            "raw_private_text_serialized": False,
        },
        **action_fields,
    }


def _print_payload(payload: Mapping[str, Any], *, json_output: bool) -> None:
    if json_output:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    print("AIppocampus question tracking")
    print(f"mode: {payload.get('mode')}")
    print(f"available: {str(bool(payload.get('available'))).lower()}")
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    if summary:
        print(f"open: {summary.get('open_question_count', 0)}")
        print(f"dormant: {summary.get('dormant_question_count', 0)}")
        print(f"resolved: {summary.get('resolved_question_count', 0)}")
    if payload.get("mode") == "list":
        print(f"rows: {payload.get('count', 0)}")
        for row in payload.get("rows") or []:
            if isinstance(row, Mapping):
                grammar = row.get("action_grammar") or "direction_only"
                print(f"- {row.get('state')} [{grammar}]: {row.get('title')}")
                if row.get("blocked_reason"):
                    print(f"  blocked: {row.get('blocked_reason')}")
                if row.get("foreground_action"):
                    action = row.get("foreground_action")
                    if isinstance(action, Mapping):
                        print(f"  next: {action.get('command') or action.get('command_template')}")
                    else:
                        print(f"  next: {action}")
    print("boundary: navigation only; reopen source before claims")
    if payload.get("foreground_action"):
        action = payload.get("foreground_action")
        if isinstance(action, Mapping):
            print(f"next: {action.get('command') or action.get('label')}")
        else:
            print(f"next: {action}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="aippocampus questions",
        usage="aippocampus questions {status,list} [--json]",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="""Read source-backed question tracking status.

This is a foreground read path only. It does not start model jobs or promote a
question lifecycle state into fact. Use rows as navigation, then reopen source
before making claims or decisions from them.""",
    )
    parser.add_argument("command", choices=["status", "list"], nargs="?", default="status")
    parser.add_argument("--jobs")
    parser.add_argument("--registry")
    parser.add_argument("--registry-dir")
    parser.add_argument("--dormant-after-days", type=int, default=DEFAULT_DORMANT_AFTER_DAYS)
    parser.add_argument("--max", type=int, default=8)
    parser.add_argument("--json", action="store_true", dest="json_output")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = _list_payload(args) if args.command == "list" else _status_payload(args)
    _print_payload(payload, json_output=bool(args.json_output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
