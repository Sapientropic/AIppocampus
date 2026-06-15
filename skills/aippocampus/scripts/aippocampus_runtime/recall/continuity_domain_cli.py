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
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from aippocampus_runtime.core import compact_text
from aippocampus_runtime.ops.route_readiness import safe_source_refs
from aippocampus_runtime.privacy import redact_private_paths, redact_sensitive_values
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
        "agent_next_action": (
            "Use `aippocampus agent recall` for ordinary continuity, run "
            "`aippocampus continuity-domain produce --preview --json`, or provide "
            "--clean-source-dir when manually appending source-trailed events."
        ),
        "recovery_actions": [
            "aippocampus agent recall <cue> --json",
            "aippocampus continuity-domain produce --preview --json",
        ],
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
    if payload.get("summary"):
        summary = payload["summary"]
        if isinstance(summary, dict):
            print(
                "domains: "
                f"{summary.get('domain_count', 0)} | "
                f"source refs: {summary.get('source_ref_count', 0)}"
            )
    if payload.get("agent_next_action"):
        next_action = payload["agent_next_action"]
        if isinstance(next_action, dict):
            print(f"next: {next_action.get('label') or next_action.get('command')}")
        else:
            print(f"next: {next_action}")


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


def _event_source_refs(event: MappingPayload) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for key in (
        "source_refs",
        "support_refs",
        "counter_refs",
        "correction_refs",
        "boundary_refs",
        "representative_refs",
        "ordered_source_refs",
    ):
        refs.extend(safe_source_refs(event.get(key)))
    return refs


def _require_resolvable_append_refs(event: MappingPayload, clean_source_dir: Path | None) -> None:
    refs = _event_source_refs(event)
    if not refs:
        return
    if clean_source_dir is None or not (clean_source_dir / "messages.jsonl").exists():
        raise ValueError(
            "continuity-domain append needs resolvable clean-source refs; provide "
            "--clean-source-dir or use produce --preview before appending"
        )


def append_command(args: argparse.Namespace) -> MappingPayload:
    events_path = _events_path(args)
    clean_source_dir = _clean_source_dir(args, events_path)
    event = _read_event(args)
    _require_resolvable_append_refs(event, clean_source_dir)
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


def _snapshot_summary(snapshot: MappingPayload) -> MappingPayload:
    report = continuity_domain_public_safety_report(snapshot)
    raw_metrics = report.get("metrics")
    metrics: Mapping[str, Any] = raw_metrics if isinstance(raw_metrics, Mapping) else {}
    return {
        "snapshot_id": snapshot.get("snapshot_id"),
        "generated_at": snapshot.get("generated_at"),
        "domain_count": len(snapshot.get("domains") or []),
        "event_count": metrics.get("event_count", 0),
        "source_ref_count": metrics.get("source_ref_count", 0),
        "source_reopen_required_before_claim": True,
    }


def _domain_cards(snapshot: MappingPayload, *, limit: int = 8) -> list[MappingPayload]:
    cards: list[MappingPayload] = []
    for domain in snapshot.get("domains") or []:
        if not isinstance(domain, dict):
            continue
        raw_trail = domain.get("evidence_trail")
        trail: Mapping[str, Any] = raw_trail if isinstance(raw_trail, Mapping) else {}
        source_ref_count = 0
        for refs in trail.values():
            if isinstance(refs, list):
                source_ref_count += len(refs)
        raw_lifecycle = domain.get("lifecycle")
        lifecycle: Mapping[str, Any] = (
            raw_lifecycle if isinstance(raw_lifecycle, Mapping) else {}
        )
        cards.append(
            {
                "domain_id": domain.get("domain_id"),
                "title": compact_text(str(domain.get("title") or domain.get("domain_id") or "untitled domain"), 96),
                "status": lifecycle.get("status") or "active",
                "source_ref_count": source_ref_count,
                "action_grammar": "reopenable_route",
                "source_reopen_required_before_claim": True,
            }
        )
        if len(cards) >= limit:
            break
    return redact_sensitive_values(redact_private_paths(cards))


def _no_snapshot_payload() -> MappingPayload:
    return {
        "ok": True,
        "status": "empty",
        "snapshot_count": 0,
        "source_boundary": {
            "absence_is_not_absence_of_source_history": True,
            "source_reopen_required_before_claim": True,
            "local_paths_serialized": False,
        },
        "agent_next_action": {
            "id": "no_continuity_domain_snapshot",
            "label": "No continuity-domain snapshot is published for this scope; use recall or preview producer candidates.",
            "command": "aippocampus continuity-domain produce --preview --json",
        },
        "recovery_actions": [
            "aippocampus agent recall <cue> --json",
            "aippocampus continuity-domain produce --preview --json",
        ],
    }


def latest_command(args: argparse.Namespace) -> MappingPayload:
    latest_path = _snapshot_dir(args) / "latest.json"
    snapshot = load_continuity_domains_snapshot(latest_path)
    if snapshot is None:
        return _no_snapshot_payload()
    report = continuity_domain_public_safety_report(snapshot)
    return {
        "ok": True,
        "status": "ok",
        "mode": "latest",
        "snapshot_id": snapshot.get("snapshot_id"),
        "summary": _snapshot_summary(snapshot),
        "domains": _domain_cards(snapshot),
        "report": report,
        "source_boundary": report.get("contract"),
        "privacy_boundary": report.get("privacy_boundary"),
        "agent_next_action": {
            "id": "use_continuity_domain_as_route",
            "label": "Use these domains as reopenable routes only; deepen or reopen clean source before claims.",
        },
    }


def list_command(args: argparse.Namespace) -> MappingPayload:
    snapshot_dir = _snapshot_dir(args)
    summaries: list[MappingPayload] = []
    if snapshot_dir.exists():
        for path in sorted(snapshot_dir.glob("*.json"), key=lambda item: item.name):
            if path.name == "latest.json":
                continue
            snapshot = load_continuity_domains_snapshot(path)
            if snapshot is not None:
                summaries.append(_snapshot_summary(snapshot))
    if not summaries:
        return _no_snapshot_payload()
    return {
        "ok": True,
        "status": "ok",
        "mode": "list",
        "snapshot_count": len(summaries),
        "snapshots": summaries,
        "source_boundary": {
            "snapshots_are_routes_not_source_truth": True,
            "source_reopen_required_before_claim": True,
            "local_paths_serialized": False,
        },
        "agent_next_action": {
            "id": "read_latest_continuity_domain_snapshot",
            "label": "Run `aippocampus continuity-domain latest --json` for the current published route card.",
            "command": "aippocampus continuity-domain latest --json",
        },
    }


def report_command(args: argparse.Namespace) -> MappingPayload:
    snapshot_path = Path(args.snapshot).resolve() if args.snapshot else _snapshot_dir(args) / "latest.json"
    snapshot = load_continuity_domains_snapshot(snapshot_path)
    if snapshot is None:
        return _no_snapshot_payload()
    return {
        "ok": True,
        "status": "ok",
        "mode": "report",
        "snapshot_id": snapshot.get("snapshot_id"),
        "summary": _snapshot_summary(snapshot),
        "report": continuity_domain_public_safety_report(snapshot),
    }


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


def _producer_candidate_previews(payload: MappingPayload) -> list[MappingPayload]:
    previews: list[MappingPayload] = []
    for event in payload.get("candidate_events") or []:
        if not isinstance(event, dict):
            continue
        refs = event.get("source_refs") or []
        cues = [
            compact_text(str(cue), 80)
            for cue in event.get("activation_cues") or []
            if str(cue).strip()
        ][:6]
        previews.append(
            {
                "domain_handle": event.get("domain_id"),
                "title": compact_text(str(event.get("title") or "untitled domain"), 96),
                "domain_type": event.get("domain_type"),
                "scale": event.get("scale"),
                "activation_cues": cues,
                "source_ref_count": len(refs) if isinstance(refs, list) else 0,
                "source_reopen_required_before_claim": True,
            }
        )
    return previews


def _producer_agent_preview(payload: MappingPayload) -> MappingPayload:
    clean = _strip_producer_local_detail(payload)
    previews = _producer_candidate_previews(payload)
    clean["detail"] = "agent_preview"
    clean["candidate_previews"] = previews
    clean["preview_boundary"] = {
        "candidate_events_emitted": False,
        "raw_source_refs_emitted": False,
        "local_paths_emitted": False,
        "preview_is_not_source_truth": True,
    }
    if previews:
        clean["agent_next_action"] = {
            "id": "review_then_append_continuity_domains",
            "label": "Review candidate_previews, then append/publish if they match the intended continuity domains.",
            "command": "aippocampus continuity-domain produce --append --publish --json",
            "requires_operator_review": True,
        }
    else:
        clean["agent_next_action"] = {
            "id": "no_continuity_domain_candidates",
            "label": "No supported continuity-domain candidates were found; keep the public dry-run report as evidence.",
            "requires_operator_review": False,
        }
    return redact_sensitive_values(redact_private_paths(clean))


def produce_command(args: argparse.Namespace) -> MappingPayload:
    if args.dry_run and args.append:
        raise ValueError("produce accepts --dry-run or --append, not both")
    if args.preview and args.append:
        raise ValueError("produce --preview is dry-run only; use --append after review")
    if args.preview and args.include_local_detail:
        raise ValueError("produce accepts --preview or --include-local-detail, not both")
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
    if args.preview:
        payload = _producer_agent_preview(proposal)
    elif args.include_local_detail:
        payload = proposal
    else:
        payload = _strip_producer_local_detail(proposal)
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
        prog="aippocampus continuity-domain",
        description=(
            "Inspect or backfill source-trailed continuity domains. Ordinary "
            "foreground use goes through agent recall/deepen; manual append and "
            "publish are operator/debug/backfill paths."
        ),
        epilog=(
            "Ordinary path: use `aippocampus agent recall` and deepen source "
            "routes before claims. Use `produce --dry-run` to preview deterministic "
            "domain candidates; use append/publish only for explicit backfill."
        ),
    )
    parser.add_argument("--cwd", default=".")
    parser.add_argument("--registry-dir")
    sub = parser.add_subparsers(dest="command", required=True)

    append = sub.add_parser("append", help="operator/debug manual event append")
    append.add_argument("--events-path")
    append.add_argument("--clean-source-dir")
    append.add_argument("--snapshot-dir")
    append.add_argument("--event-json")
    append.add_argument("--event-file")
    append.add_argument("--stdin", action="store_true")
    append.add_argument("--publish", action="store_true")
    append.add_argument("--json", action="store_true", dest="json_output")

    publish = sub.add_parser("publish", help="operator/debug snapshot rebuild")
    publish.add_argument("--events-path")
    publish.add_argument("--clean-source-dir")
    publish.add_argument("--snapshot-dir")
    publish.add_argument("--json", action="store_true", dest="json_output")

    latest = sub.add_parser("latest", help="read the latest public-safe snapshot card")
    latest.add_argument("--snapshot-dir")
    latest.add_argument("--json", action="store_true", dest="json_output")

    list_parser = sub.add_parser("list", help="list public-safe continuity-domain snapshots")
    list_parser.add_argument("--snapshot-dir")
    list_parser.add_argument("--json", action="store_true", dest="json_output")

    report = sub.add_parser("report", help="read an existing public-safe snapshot report")
    report.add_argument("--snapshot")
    report.add_argument("--snapshot-dir")
    report.add_argument("--json", action="store_true", dest="json_output")

    produce = sub.add_parser("produce", help="preview/backfill deterministic producer candidates")
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
    produce.add_argument("--preview", action="store_true")
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
        elif args.command == "latest":
            payload = latest_command(args)
        elif args.command == "list":
            payload = list_command(args)
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
