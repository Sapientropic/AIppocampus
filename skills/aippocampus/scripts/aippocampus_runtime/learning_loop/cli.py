"""Task-first foreground CLI for the source-backed learning loop."""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from aippocampus_runtime.hooks.action_hint_cache import refresh_action_hint_cache
from aippocampus_runtime.learning_loop.private_export import (
    export_private_replay_events,
    load_behavior_event_rows,
)
from aippocampus_runtime.learning_loop.private_replay import build_private_history_replay_report
from aippocampus_runtime.privacy import redact_private_paths, redact_sensitive_values

KIND = "aippocampus_learning_frontdoor"
SCHEMA_VERSION = 1


def _json_out(payload: Mapping[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


def _public_payload(payload: Any) -> Any:
    return redact_sensitive_values(redact_private_paths(payload))


def _cwd(value: str | None) -> Path:
    return Path(value or os.getcwd())


def _privacy_boundary() -> dict[str, Any]:
    return {
        "raw_rollout_scan_default": False,
        "raw_rollouts_serialized": False,
        "raw_prompt_or_stdout_serialized": False,
        "learning_guidance_is_source_truth": False,
        "source_reopen_required_for_claims": True,
        "default_output_redacts_local_paths": True,
    }


def status_payload(*, cwd: Path, no_default_learning: bool = False) -> dict[str, Any]:
    report = refresh_action_hint_cache(
        cwd=cwd,
        write=False,
        include_default_learning=not no_default_learning,
    )
    intake = dict(report.get("learned_provider_intake") or {})
    prepared_count = int(intake.get("prepared_record_count") or 0)
    cache_command = (
        "aippocampus hooks action refresh-cache "
        "--cache-jsonl <local-cache.jsonl> --write --json"
    )
    replay_command = "aippocampus learning replay --events <sanitized-events.jsonl> --json"
    benchmark_command = "python benchmarks/aippocampus/benchmark_learning_loop_public_companion.py --json"
    lanes = {
        "prepared_guidance": {
            "status": "available" if prepared_count else "not_found",
            "prepared_action_hint_count": prepared_count,
            "next_action": cache_command if prepared_count else "skip_until_guidance_exists",
        },
        "sanitized_replay": {
            "status": "available_on_request",
            "command": replay_command,
            "input_boundary": "sanitized_behavior_events_not_raw_rollout",
        },
        "operator_diagnostics": {
            "status": "operator_only",
            "command": benchmark_command,
            "default_frontdoor": False,
        },
    }
    next_actions = []
    if prepared_count:
        next_actions.append(
            {
                "label": "prepare action-time cache",
                "command": cache_command,
            }
        )
    else:
        next_actions.append(
            {
                "label": "run fixture or sanitized replay",
                "command": replay_command,
            }
        )
    next_actions.append(
        {
            "label": "inspect public companion benchmark",
            "command": benchmark_command,
        }
    )
    return _public_payload(
        {
            "kind": KIND,
            "schema_version": SCHEMA_VERSION,
            "mode": "status",
            "ok": True,
            "summary": {
                "default_learning_status": intake.get("status"),
                "finding_count": intake.get("finding_count", 0),
                "included_count": intake.get("included_count", 0),
                "prepared_action_hint_count": prepared_count,
                "cache_write_requested": False,
            },
            "lanes": lanes,
            "agent_next_action": cache_command if prepared_count else replay_command,
            "next_actions": next_actions,
            "cannot_claim": [
                "causal_live_behavior_lift",
                "learned_guidance_as_source_truth",
                "private_history_scanned_by_default",
            ],
            "privacy_boundary": _privacy_boundary(),
        }
    )


def guidance_payload(*, cwd: Path, no_default_learning: bool = False) -> dict[str, Any]:
    payload = status_payload(cwd=cwd, no_default_learning=no_default_learning)
    summary = dict(payload.get("summary") or {})
    return _public_payload(
        {
            **payload,
            "mode": "guidance",
            "agent_next_action": (
                "write a local action-hint cache only after choosing a cache path"
                if summary.get("prepared_action_hint_count")
                else "produce or provide sanitized learning findings before expecting action-time hints"
            ),
            "cache_command": (
                "aippocampus hooks action refresh-cache "
                "--cache-jsonl <local-cache.jsonl> --write --json"
            ),
        }
    )


def intervention_report_from_replay(report: Mapping[str, Any]) -> dict[str, Any]:
    metrics = report.get("metrics") if isinstance(report.get("metrics"), Mapping) else {}
    ledger = (
        report.get("effectiveness_ledger")
        if isinstance(report.get("effectiveness_ledger"), Mapping)
        else {}
    )
    guidance_count = int(metrics.get("guidance_count") or 0)
    false_positive_rate = float(metrics.get("false_positive_nudge_rate") or 0.0)
    return {
        "kind": "aippocampus_learning_intervention_report",
        "status": "diagnostic_behavior_signal",
        "eligible_intervention_case_count": guidance_count,
        "baseline": {
            "arm": "no_hint",
            "eligible_case_count": guidance_count,
            "source_reopen_before_action_count": 0,
            "hint_surface_count": 0,
        },
        "hint_arm": {
            "arm": "action_time_hint",
            "eligible_case_count": guidance_count,
            "hint_surface_count": guidance_count,
            "broad_wrong_route_avoided_count": int(
                metrics.get("source_backed_guidance_changed_action_order_count") or 0
            ),
            "repeat_failure_after_hint_count": int(
                ledger.get("repeat_failure_after_hint_count") or 0
            ),
            "over_nudge_count": int(round(false_positive_rate * max(1, guidance_count))),
            "source_reopen_before_action_count": int(
                metrics.get("context_loss_to_reopen_source_count") or 0
            ),
        },
        "cannot_claim": [
            "causal_live_behavior_lift",
            "production_default_adoption",
            "guidance_as_source_truth",
        ],
    }


def replay_payload(args: argparse.Namespace) -> dict[str, Any]:
    events = None
    input_origin = None
    export_summary = None
    if args.events:
        events = load_behavior_event_rows(args.events)
        input_origin = "sanitized_behavior_events"
    if args.clean_source_events or args.rollout:
        if not args.export_output:
            raise ValueError("--clean-source-events/--rollout requires --export-output")
        export_summary = export_private_replay_events(
            clean_source_events=args.clean_source_events,
            rollout=args.rollout,
            output=args.export_output,
        )
        events = load_behavior_event_rows(args.export_output)
        input_origin = str(export_summary.get("input_origin") or "real_sanitized_history")
    report = build_private_history_replay_report(
        events,
        input_origin=input_origin,
        sanitized_export_summary=export_summary,
    )
    return _public_payload(
        {
            "kind": KIND,
            "schema_version": SCHEMA_VERSION,
            "mode": "replay",
            "ok": bool(report.get("ok")),
            "fixture_input": bool(report.get("fixture_input")),
            "input_origin": report.get("input_origin"),
            "metrics": report.get("metrics") or {},
            "intervention_report": intervention_report_from_replay(report),
            "guidance_authority": report.get("guidance_authority") or {},
            "privacy_boundary": report.get("privacy_boundary") or _privacy_boundary(),
            "cannot_claim": report.get("cannot_claim") or [],
        }
    )


def render_human(payload: Mapping[str, Any]) -> str:
    mode = str(payload.get("mode") or "status")
    lines = [f"AIppocampus learning {mode}: {'ok' if payload.get('ok') else 'needs-review'}"]
    summary = payload.get("summary")
    if isinstance(summary, Mapping):
        lines.append(
            "findings: "
            + str(summary.get("finding_count", 0))
            + ", prepared hints: "
            + str(summary.get("prepared_action_hint_count", 0))
        )
    lanes = payload.get("lanes")
    if isinstance(lanes, Mapping):
        prepared = lanes.get("prepared_guidance")
        replay = lanes.get("sanitized_replay")
        if isinstance(prepared, Mapping):
            lines.append("prepared guidance: " + str(prepared.get("status") or "unknown"))
        if isinstance(replay, Mapping) and not (
            isinstance(prepared, Mapping) and prepared.get("status") == "available"
        ):
            lines.append("replay: " + str(replay.get("status") or "available_on_request"))
    metrics = payload.get("metrics")
    if isinstance(metrics, Mapping):
        lines.append("guidance: " + str(metrics.get("guidance_count", 0)))
    actions = [row for row in payload.get("next_actions") or [] if isinstance(row, Mapping)]
    if actions:
        lines.append("next: " + str(actions[0].get("command") or "continue"))
    elif payload.get("agent_next_action"):
        lines.append("next: " + str(payload["agent_next_action"]))
    lines.append("boundary: learning guidance is navigation only; reopen source before claims.")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="aippocampus learning",
        description=(
            "Foreground source-backed learning loop card: status, sanitized replay, "
            "and action-time guidance readiness."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Useful paths:\n"
            "  aippocampus learning status --json\n"
            "  aippocampus learning replay --json\n"
            "  aippocampus learning replay --events <sanitized-events.jsonl> --json\n"
            "  aippocampus learning guidance --json\n\n"
            "Raw private rollouts are never scanned by default; use --rollout only with --export-output."
        ),
    )
    sub = parser.add_subparsers(dest="command")
    status = sub.add_parser("status")
    status.add_argument("--cwd")
    status.add_argument("--no-default-learning", action="store_true")
    status.add_argument("--json", action="store_true")

    guidance = sub.add_parser("guidance")
    guidance.add_argument("--cwd")
    guidance.add_argument("--no-default-learning", action="store_true")
    guidance.add_argument("--json", action="store_true")

    replay = sub.add_parser("replay")
    replay.add_argument("--events", type=Path)
    replay.add_argument("--clean-source-events", type=Path)
    replay.add_argument("--rollout", type=Path)
    replay.add_argument("--export-output", type=Path)
    replay.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args_list = list(argv or [])
    if not args_list:
        args_list = ["status"]
    parser = build_parser()
    args = parser.parse_args(args_list)
    if args.command == "replay":
        try:
            payload = replay_payload(args)
        except ValueError as exc:
            parser.error(str(exc))
    elif args.command == "guidance":
        payload = guidance_payload(cwd=_cwd(args.cwd), no_default_learning=args.no_default_learning)
    else:
        payload = status_payload(cwd=_cwd(args.cwd), no_default_learning=args.no_default_learning)
    if getattr(args, "json", False):
        _json_out(payload)
    else:
        print(render_human(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
