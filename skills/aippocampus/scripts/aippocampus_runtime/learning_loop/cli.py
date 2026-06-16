"""Task-first foreground CLI for the source-backed learning loop."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from aippocampus_runtime.contracts import foreground_shell_action
from aippocampus_runtime.hooks.action_hint_cache import refresh_action_hint_cache
from aippocampus_runtime.learning_loop.dogfood_cases import build_sanitized_repro_package
from aippocampus_runtime.learning_loop.private_export import (
    export_private_replay_events,
    load_behavior_event_rows,
)
from aippocampus_runtime.learning_loop.private_replay import build_private_history_replay_report
from aippocampus_runtime.learning_loop.semantic_learning import (
    build_semantic_learning_dogfood_fixture_report,
)
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


def _learning_discovery_action() -> dict[str, Any]:
    return foreground_shell_action(
        action_id="discover_eligible_learning_sources",
        label="Discover eligible learning sources",
        command="aippocampus learning discover-history --json",
        why="Choose an existing sanitized or clean-source learning input before replaying.",
        mutation_risk="read_only",
        claim_boundary="learning_guidance_not_source_truth",
    )


def _learning_setup_actions() -> list[dict[str, Any]]:
    return [
        _learning_discovery_action(),
        foreground_shell_action(
            action_id="inspect_learning_guidance",
            label="Inspect learning guidance",
            command="aippocampus learning guidance --json",
            why="Show prepared and semantic learning guidance without writing a cache.",
            mutation_risk="read_only",
            claim_boundary="learning_guidance_not_source_truth",
        ),
        foreground_shell_action(
            action_id="refresh_action_hint_cache",
            label="Refresh action-hint cache",
            command="aippocampus hooks action refresh-cache --json",
            why="Preview action-time hint materialization before using --write.",
            mutation_risk="read_only",
            claim_boundary="learning_guidance_not_source_truth",
        ),
    ]


def discover_history_payload(*, cwd: Path) -> dict[str, Any]:
    root = cwd.resolve()
    candidates: list[dict[str, Any]] = []
    known = [
        (
            "clean_source_events",
            root / ".aippocampus" / "clean-source" / "behavior-events.jsonl",
            "clean-source behavior events",
        ),
        (
            "sanitized_replay_events",
            root / ".aippocampus" / "learning-loop" / "sanitized-events.jsonl",
            "sanitized learning replay events",
        ),
        (
            "learning_findings",
            root / ".aippocampus" / "learning-loop" / "findings.jsonl",
            "source-backed learning findings",
        ),
        (
            "effectiveness_ledger",
            root / ".aippocampus" / "learning-loop" / "effectiveness-ledger.jsonl",
            "learning effectiveness ledger",
        ),
    ]
    for candidate_id, path, label in known:
        candidates.append(
            {
                "id": candidate_id,
                "label": label,
                "status": "available" if path.exists() else "not_found",
                "path_label": f"workspace/.aippocampus/learning-loop/{path.name}"
                if "learning-loop" in path.parts
                else "workspace/.aippocampus/clean-source/behavior-events.jsonl",
                "raw_private_text_loaded": False,
            }
        )
    return _public_payload(
        {
            "kind": KIND,
            "schema_version": SCHEMA_VERSION,
            "mode": "discover-history",
            "ok": True,
            "status": "source_selection",
            "candidate_count": len(candidates),
            "available_candidate_count": sum(1 for row in candidates if row["status"] == "available"),
            "candidates": candidates,
            "agent_next_action": {
                **_learning_setup_actions()[1],
                "why": "If no candidate is available yet, inspect guidance before exporting or replaying anything.",
            },
            "safe_next_actions": _learning_setup_actions(),
            "privacy_boundary": _privacy_boundary(),
            "cannot_claim": [
                "private_history_scanned_by_default",
                "learned_guidance_as_source_truth",
            ],
        }
    )


def status_payload(*, cwd: Path, no_default_learning: bool = False) -> dict[str, Any]:
    report = refresh_action_hint_cache(
        cwd=cwd,
        write=False,
        include_default_learning=not no_default_learning,
    )
    intake = dict(report.get("learned_provider_intake") or {})
    ledger_intake = dict(report.get("effectiveness_ledger_intake") or {})
    prepared_count = int(intake.get("prepared_record_count") or 0)
    cache_command = "aippocampus hooks action refresh-cache --write --json"
    replay_command = "aippocampus learning discover-history --json"
    current_history_command = "aippocampus learning discover-history --json"
    benchmark_command = "python benchmarks/aippocampus/benchmark_learning_loop_public_companion.py --json"
    lanes = {
        "prepared_guidance": {
            "status": "available" if prepared_count else "not_found",
            "prepared_action_hint_count": prepared_count,
            "next_action": cache_command if prepared_count else "skip_until_guidance_exists",
        },
        "current_history_extraction": {
            "status": "available_after_explicit_source_choice",
            "command": current_history_command,
            "export_command_template": (
                "aippocampus learning replay --clean-source-events selected-events.jsonl "
                "--export-output sanitized-events.jsonl --json"
            ),
            "requires_explicit_source": True,
            "raw_private_rollouts_scanned_by_default": False,
            "input_boundary": "operator-selected clean-source behavior events or rollout exported to sanitized events first",
        },
        "sanitized_replay": {
            "status": "available_on_request",
            "command": replay_command,
            "replay_command_template": (
                "aippocampus learning replay --events sanitized-events.jsonl --json"
            ),
            "input_boundary": "sanitized_behavior_events_not_raw_rollout",
        },
        "effectiveness_ledger": {
            "status": ledger_intake.get("status") or "not_found",
            "row_count": ledger_intake.get("row_count", 0),
            "applied_to_guidance_before_cache": bool(
                ledger_intake.get("applied_to_guidance_before_cache")
            ),
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
                "label": "export and replay current eligible history",
                "command": current_history_command,
            }
        )
    semantic_report = build_semantic_learning_dogfood_fixture_report()
    semantic_metrics = dict(semantic_report.get("metrics") or {})
    semantic_stage = dict((semantic_report.get("stage_report") or {}).get("metrics") or {})
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
                "effectiveness_ledger_row_count": ledger_intake.get("row_count", 0),
                "semantic_loop_stage": (semantic_report.get("stage_report") or {}).get("stage"),
                "semantic_action_time_guidance_count": semantic_metrics.get(
                    "action_time_guidance_count", 0
                ),
                "cache_write_requested": False,
            },
            "lanes": lanes,
            "semantic_loop": {
                "stage": (semantic_report.get("stage_report") or {}).get("stage"),
                "stage_counts": {
                    "semantic_hypothesis_count": semantic_metrics.get(
                        "semantic_hypothesis_count", 0
                    ),
                    "review_queued_count": semantic_metrics.get("review_queued_count", 0),
                    "promoted_guidance_candidate_count": semantic_metrics.get(
                        "promoted_guidance_candidate_count", 0
                    ),
                    "action_time_guidance_count": semantic_metrics.get(
                        "action_time_guidance_count", 0
                    ),
                    "stale_private_thin_suppression_count": semantic_stage.get(
                        "stale_private_thin_suppression_count", 0
                    ),
                    "raw_private_text_leak_count": semantic_metrics.get(
                        "raw_private_text_leak_count", 0
                    ),
                },
                "closeout_gate": semantic_report.get("closeout_gate") or [],
                "deterministic_learning_metrics_separate": bool(
                    (semantic_report.get("deterministic_learning_metrics") or {}).get(
                        "separate_from_semantic"
                    )
                ),
            },
            "agent_next_action": (
                foreground_shell_action(
                    action_id="refresh_action_hint_cache",
                    label="Prepare action-time cache",
                    command=cache_command,
                    why="Prepared guidance exists and can be materialized into the local action-hint cache.",
                    mutation_risk="explicit_local_cache_write",
                    claim_boundary="learning_guidance_not_source_truth",
                )
                if prepared_count
                else _learning_discovery_action()
            ),
            "next_actions": next_actions,
            "safe_next_actions": _learning_setup_actions(),
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
    semantic_count = int(summary.get("semantic_action_time_guidance_count") or 0)
    if summary.get("prepared_action_hint_count"):
        next_action: Any = foreground_shell_action(
            action_id="refresh_action_hint_cache",
            label="Prepare action-time cache",
            command="aippocampus hooks action refresh-cache --write --json",
            why="Prepared guidance exists and can be written into the local action-hint cache.",
            mutation_risk="explicit_local_cache_write",
            claim_boundary="learning_guidance_not_source_truth",
        )
        materialization_status = "prepared_guidance_ready"
    elif semantic_count:
        next_action = foreground_shell_action(
            action_id="review_semantic_guidance_before_cache",
            label="Review semantic guidance candidates",
            command="aippocampus learning guidance --json",
            why="Semantic action-time guidance exists, but source-backed materialization still needs review.",
            mutation_risk="read_only",
            claim_boundary="learning_guidance_not_source_truth",
        )
        materialization_status = "semantic_guidance_requires_review_before_cache"
    else:
        next_action = _learning_discovery_action()
        materialization_status = "needs_learning_input"
    return _public_payload(
        {
            **payload,
            "mode": "guidance",
            "agent_next_action": next_action,
            "cache_command": "aippocampus hooks action refresh-cache --write --json",
            "semantic_guidance": {
                "guidance_count": semantic_count,
                "materialization_status": materialization_status,
                "cache_materialization_command": "aippocampus hooks action refresh-cache --json",
            },
        }
    )


def replay_needs_source_payload() -> dict[str, Any]:
    return _public_payload(
        {
            "kind": KIND,
            "schema_version": SCHEMA_VERSION,
            "mode": "replay",
            "ok": False,
            "status": "needs_source_selection",
            "fixture_input": False,
            "agent_next_action": _learning_discovery_action(),
            "safe_next_actions": _learning_setup_actions(),
            "metrics_boundary": {
                "fixture_metrics_are_not_real_history": True,
                "real_history_replay_requires_sanitized_events": True,
            },
            "privacy_boundary": _privacy_boundary(),
            "cannot_claim": [
                "causal_live_behavior_lift",
                "private_history_scanned_by_default",
                "guidance_as_source_truth",
            ],
        }
    )


def intervention_report_from_replay(report: Mapping[str, Any]) -> dict[str, Any]:
    metrics_raw = report.get("metrics")
    metrics = dict(metrics_raw) if isinstance(metrics_raw, Mapping) else {}
    ledger_raw = report.get("effectiveness_ledger")
    ledger = dict(ledger_raw) if isinstance(ledger_raw, Mapping) else {}
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
    if events is None:
        return replay_needs_source_payload()
    report = build_private_history_replay_report(
        events,
        input_origin=input_origin,
        sanitized_export_summary=export_summary,
    )
    fixture_input = bool(report.get("fixture_input"))
    replay_next_actions = []
    if fixture_input:
        replay_next_actions.append(
            {
                "label": "run real sanitized replay",
                "command": "aippocampus learning discover-history --json",
            }
        )
        replay_next_actions.append(
            {
                "label": "export private history to sanitized events first",
                "command": (
                    "aippocampus learning discover-history --json"
                ),
            }
        )
    return _public_payload(
        {
            "kind": KIND,
            "schema_version": SCHEMA_VERSION,
            "mode": "replay",
            "ok": bool(report.get("ok")),
            "fixture_input": fixture_input,
            "input_origin": report.get("input_origin"),
            "evidence_origin": report.get("evidence_origin") or {},
            "metrics_boundary": {
                "fixture_metrics_are_not_real_history": fixture_input,
                "real_history_replay_requires_sanitized_events": True,
            },
            "metrics": report.get("metrics") or {},
            "intervention_report": intervention_report_from_replay(report),
            "guidance_authority": report.get("guidance_authority") or {},
            "privacy_boundary": report.get("privacy_boundary") or _privacy_boundary(),
            "cannot_claim": report.get("cannot_claim") or [],
            "agent_next_action": (
                replay_next_actions[0]["command"]
                if replay_next_actions
                else "inspect replay metrics and append an effectiveness ledger only after review"
            ),
            "next_actions": replay_next_actions,
        }
    )


def _runtime_version() -> str:
    try:
        return importlib.metadata.version("aippocampus")
    except importlib.metadata.PackageNotFoundError:
        return "unknown"


def _load_repro_package_input(args: argparse.Namespace) -> Any:
    if args.input_json and args.stdin:
        raise ValueError("choose only one of --input-json or --stdin")
    if args.stdin:
        return json.loads(sys.stdin.read())
    return json.loads(args.input_json.read_text(encoding="utf-8"))


def repro_package_payload(args: argparse.Namespace) -> dict[str, Any]:
    payload = _load_repro_package_input(args)
    if not isinstance(payload, Mapping):
        raise ValueError("--input-json must contain a JSON object")
    missing = [
        field
        for field in ("command", "expected", "actual")
        if not str(payload.get(field) or "").strip()
    ]
    if missing:
        raise ValueError("missing required repro fields: " + ", ".join(missing))
    if not (payload.get("output") is not None or payload.get("stdout") is not None or payload.get("output_ref")):
        raise ValueError("missing one of output, stdout, or output_ref")
    package = build_sanitized_repro_package(
        payload,
        version=args.version or _runtime_version(),
        commit=args.commit or "unknown",
        plugin_manifest_version=args.plugin_manifest_version or "unknown",
    )
    return _public_payload(
        {
            "kind": KIND,
            "schema_version": SCHEMA_VERSION,
            "mode": "repro_package",
            "ok": bool(package.get("ok")),
            "repro_package": package,
            "agent_next_action": "paste repro_package into a public issue after human review",
            "privacy_boundary": package.get("privacy_boundary") or _privacy_boundary(),
            "cannot_claim": [
                "source_truth_from_repro_package",
                "official_benchmark_score_from_repro_package",
                "private_history_quality",
            ],
        }
    )


def repro_package_template_payload() -> dict[str, Any]:
    schema = repro_package_input_schema()
    template = schema["redacted_example"]
    template_json = json.dumps(template, ensure_ascii=False, indent=2, sort_keys=True)
    primary = foreground_shell_action(
        action_id="package_repro_input_file",
        label="Package a saved repro input JSON file",
        command="aippocampus repro package --input-json repro-input.json --json",
        why="Use this after writing the template JSON to repro-input.json and filling expected/actual.",
        mutation_risk="read_only",
        claim_boundary="repro_package_not_source_truth",
    )
    return _public_payload(
        {
            "kind": KIND,
            "schema_version": SCHEMA_VERSION,
            "mode": "repro_package_template",
            "ok": True,
            "template": template,
            "template_json": template_json,
            "stdin_payload": template_json,
            "expected_input_schema": schema,
            "agent_next_action": {
                "id": "choose_repro_packaging_path",
                "primary": primary,
                "no_file_payload_field": "stdin_payload",
            },
            "primary_next_action": primary,
            "safe_next_actions": [
                primary,
                foreground_shell_action(
                    action_id="package_repro_stdin",
                    label="Package repro JSON through stdin",
                    command="cat repro-input.json | aippocampus repro package --stdin --json",
                    why="Portable Unix stdin path when a pipe is preferred.",
                    mutation_risk="read_only",
                    claim_boundary="repro_package_not_source_truth",
                ),
                foreground_shell_action(
                    action_id="validate_repro_input_json",
                    label="Validate repro input JSON",
                    command="python -m json.tool repro-input.json",
                    why="Check JSON syntax before packaging.",
                    mutation_risk="read_only",
                    claim_boundary="syntax_check_not_source_evidence",
                ),
            ],
            "next_actions": [
                {
                    "label": str(action.get("label") or action.get("id")),
                    "command": str(action["command"]),
                    "mutates": False,
                }
                for action in [
                    primary,
                    foreground_shell_action(
                        action_id="package_repro_stdin_legacy_list",
                        label="Package repro JSON through stdin",
                        command="cat repro-input.json | aippocampus repro package --stdin --json",
                        mutation_risk="read_only",
                        claim_boundary="repro_package_not_source_truth",
                    ),
                ]
            ],
            "privacy_boundary": _privacy_boundary(),
        }
    )


def repro_package_input_schema() -> dict[str, Any]:
    return {
        "required": ["command", "expected", "actual"],
        "one_of": ["output", "output_ref"],
        "optional": ["surface", "source_refs", "privacy_boundary"],
        "redacted_example": {
            "surface": "agent_recall",
            "command": "aippocampus agent recall \"old decision or handoff cue\" --json",
            "output_ref": "saved-output://local/redacted-command-output.json",
            "expected": "source-backed route appears with reopen boundary",
            "actual": "route was missing or degraded",
            "source_refs": [{"source_id": "public-fixture-source", "message_id": "msg_public_001"}],
            "privacy_boundary": "no raw private stdout or prompt text",
        },
    }


def repro_package_recovery_payload(*, malformed_error: str | None = None) -> dict[str, Any]:
    code = "learning_repro_input_malformed" if malformed_error else "learning_repro_input_required"
    return _public_payload(
        {
            "kind": KIND,
            "schema_version": SCHEMA_VERSION,
            "mode": "repro_package_recovery",
            "ok": False,
            "error": {
                "code": code,
                "message": (
                    "repro-package needs a saved JSON object with command plus output or "
                    "output_ref and expected/actual fields; no private stdout or prompt text "
                    "was read."
                ),
                "malformed_error": malformed_error or "",
                "next_command": (
                    "aippocampus repro package --template --json"
                ),
            },
            "expected_input_schema": repro_package_input_schema(),
            "recovery_paths": [
                {
                    "label": "from sanitized replay or guidance output",
                    "steps": [
                        "run `aippocampus learning guidance --json` or sanitized replay",
                        "save the relevant command outcome as the expected input schema",
                        "run `aippocampus repro package --input-json command-output.json --json`",
                    ],
                    "copyable_validate_command": (
                        "python -m json.tool command-output.json"
                    ),
                    "copyable_package_command": (
                        "aippocampus repro package --input-json command-output.json --json"
                    ),
                    "mutates": False,
                },
                {
                    "label": "fresh command/output capture template",
                    "steps": [
                        "run the foreground command manually",
                        "record only redacted output or an output_ref",
                        "fill command/expected/actual/source_refs before packaging",
                    ],
                    "template": repro_package_input_schema()["redacted_example"],
                    "copyable_template_command": "aippocampus repro package --template --json",
                    "copyable_stdin_command": (
                        "cat command-output.json | aippocampus repro package --stdin --json"
                    ),
                    "mutates": False,
                },
            ],
            "next_actions": [
                {
                    "label": "inspect learning guidance first",
                    "command": "aippocampus learning guidance --json",
                    "mutates": False,
                }
            ],
            "privacy_boundary": _privacy_boundary(),
            "cannot_claim": [
                "source_truth_from_repro_package",
                "private_history_quality",
            ],
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
    origin = payload.get("evidence_origin")
    if isinstance(origin, Mapping):
        if origin.get("fixture_metrics_are_not_real_history"):
            lines.append("origin: synthetic fixture, not real-history evidence")
        elif origin.get("kind"):
            lines.append("origin: " + str(origin.get("kind")))
    if payload.get("status") == "needs_source_selection":
        lines.append("status: needs source selection")
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
    parser.add_argument("--cwd")
    parser.add_argument("--no-default-learning", action="store_true")
    parser.add_argument("--json", action="store_true")
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

    discover = sub.add_parser("discover-history")
    discover.add_argument("--cwd")
    discover.add_argument("--json", action="store_true")

    repro = sub.add_parser(
        "repro-package",
        help="Create a public-safe dogfood repro package from a saved command/output JSON object.",
    )
    repro.add_argument("--input-json", type=Path)
    repro.add_argument("--stdin", action="store_true")
    repro.add_argument("--template", action="store_true")
    repro.add_argument("--version")
    repro.add_argument("--commit")
    repro.add_argument("--plugin-manifest-version")
    repro.add_argument("--json", action="store_true")
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
    elif args.command == "discover-history":
        payload = discover_history_payload(cwd=_cwd(args.cwd))
    elif args.command == "repro-package":
        if args.template:
            payload = repro_package_template_payload()
        elif not args.input_json and not args.stdin:
            payload = repro_package_recovery_payload()
        else:
            try:
                payload = repro_package_payload(args)
            except ValueError as exc:
                payload = repro_package_recovery_payload(malformed_error=str(exc))
            except (OSError, json.JSONDecodeError) as exc:
                payload = repro_package_recovery_payload(
                    malformed_error=f"{exc.__class__.__name__}: invalid or unreadable JSON"
                )
    elif args.command == "guidance":
        payload = guidance_payload(cwd=_cwd(args.cwd), no_default_learning=args.no_default_learning)
    else:
        payload = status_payload(cwd=_cwd(args.cwd), no_default_learning=args.no_default_learning)
    if getattr(args, "json", False):
        _json_out(payload)
    else:
        print(render_human(payload))
    return 0 if payload.get("ok", True) else 2


if __name__ == "__main__":
    raise SystemExit(main())
