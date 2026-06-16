#!/usr/bin/env python3
"""Foreground read path for source-backed question tracking."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

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
        "agent_next_action": (
            "Use questions as source-backed navigation only; reopen source before "
            "treating a question lifecycle state as evidence."
        ),
    }


def _list_payload(args: argparse.Namespace) -> dict[str, Any]:
    payload = question_health_stats(
        _default_jobs_path(args),
        registry_path=_default_registry_path(args),
        dormant_after_days=args.dormant_after_days,
    )
    rows = []
    for item in list(payload.get("lifecycle") or [])[: max(0, int(args.max or 0))]:
        if not isinstance(item, Mapping):
            continue
        rows.append(
            {
                "unit_id": item.get("unit_id"),
                "title": item.get("title"),
                "state": item.get("state"),
                "first_seen": item.get("first_seen"),
                "last_seen": item.get("last_seen"),
                "source_ref_count": item.get("source_ref_count"),
                "source_reopen_required_before_claim": True,
            }
        )
    return {
        "kind": "aippocampus_question_tracking_list",
        "ok": True,
        "mode": "list",
        "available": bool(payload.get("available")),
        "count": len(rows),
        "rows": rows,
        "empty_state": None
        if rows
        else {
            "state": "no_source_backed_question_rows",
            "agent_next_action": (
                "No question tracking rows are ready; use agent recall/search for "
                "ordinary continuity, or run background jobs explicitly."
            ),
        },
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
                print(f"- {row.get('state')}: {row.get('title')}")
    print("boundary: navigation only; reopen source before claims")
    if payload.get("agent_next_action"):
        print(f"next: {payload.get('agent_next_action')}")


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
