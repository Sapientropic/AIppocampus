#!/usr/bin/env python3
"""Operator CLI for explicit continuity-domain event writes.

Continuity domains are durable interpretation routes, so authoring stays an
explicit operator/agent action. Prompt hooks and ordinary MCP reads may consume
published snapshots, but they must not append domain events behind the user's
back.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from aippocampus_runtime.recall.continuity_domain_producer import (
    propose_continuity_domain_events_from_registry,
)
from aippocampus_runtime.recall.continuity_domains import (
    append_continuity_domain_event,
    continuity_domain_public_safety_report,
    default_continuity_domain_events_path,
    default_continuity_domain_snapshot_dir,
    load_continuity_domains_snapshot,
    publish_continuity_domains_snapshot,
)


def _json_error(code: str, message: str) -> dict[str, Any]:
    return {
        "ok": False,
        "error": {
            "code": code,
            "message": message,
        },
    }


def _print_payload(payload: MappingPayload, *, json_output: bool) -> None:
    if json_output:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    status = payload.get("status") or ("ok" if payload.get("ok") else "error")
    print(f"continuity-domain: {status}")
    if payload.get("event_id"):
        print(f"event: {payload['event_id']}")
    if payload.get("snapshot_id"):
        print(f"snapshot: {payload['snapshot_id']}")


MappingPayload = dict[str, Any]


def _read_event(args: argparse.Namespace) -> dict[str, Any]:
    sources = [
        bool(args.event_json),
        bool(args.event_file),
        bool(getattr(args, "stdin", False)),
    ]
    if sum(1 for item in sources if item) != 1:
        raise ValueError("append requires exactly one of --event-json, --event-file, or --stdin")
    if args.event_json:
        payload = args.event_json
    elif args.event_file:
        payload = Path(args.event_file).read_text(encoding="utf-8")
    else:
        payload = sys.stdin.read()
    event = json.loads(payload)
    if not isinstance(event, dict):
        raise ValueError("continuity-domain event payload must be a JSON object")
    return event


def _events_path(args: argparse.Namespace) -> Path:
    if args.events_path:
        return Path(args.events_path).resolve()
    return default_continuity_domain_events_path(
        Path(args.cwd).resolve(),
        registry_dir=Path(args.registry_dir).resolve() if args.registry_dir else None,
    )


def _snapshot_dir(args: argparse.Namespace) -> Path:
    if args.snapshot_dir:
        return Path(args.snapshot_dir).resolve()
    return default_continuity_domain_snapshot_dir(
        Path(args.cwd).resolve(),
        registry_dir=Path(args.registry_dir).resolve() if args.registry_dir else None,
    )


def _clean_source_dir(args: argparse.Namespace, events_path: Path) -> Path | None:
    if args.clean_source_dir:
        return Path(args.clean_source_dir).resolve()
    parent = events_path.parent
    return parent if (parent / "messages.jsonl").exists() else None


def append_command(args: argparse.Namespace) -> MappingPayload:
    events_path = _events_path(args)
    clean_source_dir = _clean_source_dir(args, events_path)
    event = _read_event(args)
    normalized = append_continuity_domain_event(
        events_path,
        event,
        clean_source_dir=clean_source_dir,
    )
    payload: MappingPayload = {
        "ok": True,
        "status": "ok",
        "event_id": normalized.get("event_id"),
        "event_kind": normalized.get("event_kind"),
        "events_path": str(events_path),
    }
    if args.publish:
        report = publish_continuity_domains_snapshot(
            events_path=events_path,
            snapshot_dir=_snapshot_dir(args),
            clean_source_dir=clean_source_dir,
        )
        payload["publish_report"] = report
        payload["snapshot_id"] = report.get("snapshot_id")
    return payload


def publish_command(args: argparse.Namespace) -> MappingPayload:
    events_path = _events_path(args)
    clean_source_dir = _clean_source_dir(args, events_path)
    report = publish_continuity_domains_snapshot(
        events_path=events_path,
        snapshot_dir=_snapshot_dir(args),
        clean_source_dir=clean_source_dir,
    )
    return {"ok": True, **report}


def report_command(args: argparse.Namespace) -> MappingPayload:
    snapshot = load_continuity_domains_snapshot(Path(args.snapshot).resolve())
    if snapshot is None:
        raise ValueError("snapshot is missing or is not a continuity-domain snapshot")
    return {"ok": True, "report": continuity_domain_public_safety_report(snapshot)}


def _strip_producer_local_detail(payload: MappingPayload) -> MappingPayload:
    clean = {key: value for key, value in payload.items() if key != "candidate_events"}
    label_rows = []
    for row in clean.get("top_domain_labels") or []:
        if isinstance(row, dict):
            label_rows.append(
                {
                    key: value
                    for key, value in row.items()
                    if key not in {"label", "thread_key"}
                }
            )
    clean["top_domain_labels"] = label_rows
    return clean


def produce_command(args: argparse.Namespace) -> MappingPayload:
    if args.dry_run and args.append:
        raise ValueError("produce accepts --dry-run or --append, not both")
    proposal = propose_continuity_domain_events_from_registry(
        registry_path=Path(args.registry).resolve() if args.registry else None,
        registry_dir=Path(args.registry_dir).resolve() if args.registry_dir else None,
        min_support=args.min_support,
        max_threads=args.max_threads,
        max_candidates=args.max_candidates,
        include_local_detail=True,
        refresh_query_pattern_routes=(
            bool(args.refresh_query_pattern_routes)
            or (bool(args.append) and not bool(args.no_refresh_query_pattern_routes))
        ),
    )
    events = list(proposal.get("candidate_events") or [])
    payload = proposal if args.include_local_detail else _strip_producer_local_detail(proposal)
    payload["mode"] = "append" if args.append else "dry_run"
    if not args.append:
        return payload

    events_path = _events_path(args)
    appended = []
    rejected = 0
    for event in events:
        try:
            appended.append(
                append_continuity_domain_event(
                    events_path,
                    event,
                    clean_source_dir=None,
                )
            )
        except ValueError:
            rejected += 1
    write_report: MappingPayload = {
        "append_requested": True,
        "appended_event_count": len(appended),
        "append_rejected_event_count": rejected,
        "events_path": str(events_path),
    }
    if args.publish:
        publish_report = publish_continuity_domains_snapshot(
            events_path=events_path,
            snapshot_dir=_snapshot_dir(args),
            clean_source_dir=None,
        )
        write_report["publish_report"] = publish_report
        payload["snapshot_id"] = publish_report.get("snapshot_id")
    payload["write_report"] = write_report
    return payload


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Append and publish explicit continuity-domain events.",
    )
    parser.add_argument("--cwd", default=".")
    parser.add_argument("--registry-dir")
    sub = parser.add_subparsers(dest="command", required=True)

    append = sub.add_parser("append")
    append.add_argument("--events-path")
    append.add_argument("--clean-source-dir")
    append.add_argument("--snapshot-dir")
    append.add_argument("--event-json")
    append.add_argument("--event-file")
    append.add_argument("--stdin", action="store_true")
    append.add_argument("--publish", action="store_true")
    append.add_argument("--json", action="store_true", dest="json_output")

    publish = sub.add_parser("publish")
    publish.add_argument("--events-path")
    publish.add_argument("--clean-source-dir")
    publish.add_argument("--snapshot-dir")
    publish.add_argument("--json", action="store_true", dest="json_output")

    report = sub.add_parser("report")
    report.add_argument("--snapshot", required=True)
    report.add_argument("--json", action="store_true", dest="json_output")

    produce = sub.add_parser("produce")
    produce.add_argument("--registry")
    produce.add_argument("--registry-dir")
    produce.add_argument("--events-path")
    produce.add_argument("--snapshot-dir")
    produce.add_argument("--dry-run", action="store_true")
    produce.add_argument("--append", action="store_true")
    produce.add_argument("--publish", action="store_true")
    produce.add_argument("--refresh-query-pattern-routes", action="store_true")
    produce.add_argument("--no-refresh-query-pattern-routes", action="store_true")
    produce.add_argument("--include-local-detail", action="store_true")
    produce.add_argument("--min-support", type=int, default=2)
    produce.add_argument("--max-threads", type=int)
    produce.add_argument("--max-candidates", type=int, default=24)
    produce.add_argument("--json", action="store_true", dest="json_output")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "append":
            payload = append_command(args)
        elif args.command == "publish":
            payload = publish_command(args)
        elif args.command == "report":
            payload = report_command(args)
        elif args.command == "produce":
            payload = produce_command(args)
        else:
            parser.error("unknown command")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        payload = _json_error("continuity_domain_cli_error", str(exc))
        _print_payload(payload, json_output=getattr(args, "json_output", False))
        return 2
    _print_payload(payload, json_output=getattr(args, "json_output", False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
