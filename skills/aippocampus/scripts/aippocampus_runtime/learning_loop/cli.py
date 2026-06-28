"""Task-first foreground CLI for the source-backed learning loop."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

from aippocampus_runtime.contracts import (
    canonical_foreground_action_fields,
    foreground_shell_action,
)
from aippocampus_runtime.foreground_action_lint import (
    compact_foreground_action_budget_report,
)
from aippocampus_runtime.hooks.action_hint_cache import refresh_action_hint_cache
from aippocampus_runtime.learning_loop.behavioral_records import (
    behavioral_records,
)
from aippocampus_runtime.learning_loop.behavioral_records import (
    inventory_payload as behavioral_records_inventory_payload,
)
from aippocampus_runtime.learning_loop.behavioral_records import (
    purge_payload as purge_behavioral_records_payload,
)
from aippocampus_runtime.learning_loop.foreground_lifecycle import (
    preview_cache_bridge_action,
    semantic_guidance_lifecycle,
)
from aippocampus_runtime.learning_loop.frontdoor_common import (
    KIND,
    LEARNING_OPERATOR_DETAIL_COMMAND,
    SCHEMA_VERSION,
)
from aippocampus_runtime.learning_loop.frontdoor_common import (
    privacy_boundary as _privacy_boundary,
)
from aippocampus_runtime.learning_loop.frontdoor_common import (
    public_payload as _public_payload,
)
from aippocampus_runtime.learning_loop.frontdoor_common import (
    with_boundary_detail as _with_boundary_detail,
)
from aippocampus_runtime.learning_loop.private_export import (
    LearningReplayInputError,
    export_private_replay_events,
    load_behavior_event_rows,
)
from aippocampus_runtime.learning_loop.private_replay import (
    build_private_history_replay_report,
    replay_recovery_payload,
)
from aippocampus_runtime.learning_loop.repro_package import (
    repro_package_payload,
    repro_package_recovery_payload,
    repro_package_template_payload,
)
from aippocampus_runtime.learning_loop.semantic_learning import (
    build_semantic_learning_dogfood_fixture_report,
)

COMPACT_SAFE_NEXT_ACTION_BUDGET = 1


def _json_out(payload: Mapping[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _cwd(value: str | None) -> Path:
    return Path(value or os.getcwd())


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


def _action_identity(action: Mapping[str, Any]) -> tuple[str, str, str]:
    return (
        str(action.get("id") or ""),
        str(action.get("command") or ""),
        str(action.get("command_template") or ""),
    )


def _unique_actions(*actions: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    seen: set[tuple[str, str, str]] = set()
    unique: list[dict[str, Any]] = []
    for action in actions:
        if not isinstance(action, Mapping) or not action:
            continue
        normalized = dict(action)
        identity = _action_identity(normalized)
        if identity in seen:
            continue
        seen.add(identity)
        unique.append(normalized)
    return unique


def _compact_learning_action_fields(
    primary_action: Mapping[str, Any],
    actions: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Keep learning frontdoors action-sized without losing operator routes."""

    unique_actions = _unique_actions(primary_action, *actions)
    full_action_fields = canonical_foreground_action_fields(
        primary_action,
        safe_next_actions=unique_actions,
    )
    compact_action_fields = canonical_foreground_action_fields(
        primary_action,
        safe_next_actions=unique_actions,
        max_safe_next_actions=COMPACT_SAFE_NEXT_ACTION_BUDGET,
    )
    budget = compact_foreground_action_budget_report(
        full_action_fields,
        max_safe_actions=COMPACT_SAFE_NEXT_ACTION_BUDGET,
        budget_reason="learning_frontdoor_compact_action_budget",
    )
    if budget["more_actions_available_in_detail"]:
        compact_action_fields["more_actions_available_in_detail"] = True
    operator_detail = {
        "profile": "learning_frontdoor_action_menu",
        "claim_boundary": (
            "compact learning frontdoors expose one primary action and at most "
            "one alternative; detail owns the wider action menu"
        ),
        "foreground_action_budget": budget,
        "foreground_action": full_action_fields["foreground_action"],
        "safe_next_actions": full_action_fields["safe_next_actions"],
    }
    return compact_action_fields, operator_detail


def _compact_semantic_lifecycle(
    lifecycle: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Keep status/guidance scan-friendly while preserving audit ledgers.

    Lifecycle events are useful for debugging materialization, but they drown
    the foreground question: what guidance exists and what should the agent do
    next? The compact projection keeps candidate action cards; full row ledgers
    move to operator_detail so a future maintainer does not accidentally make
    the first screen ledger-first again.
    """

    compact = dict(lifecycle)
    ledger = compact.pop("guidance_lifecycle_ledger", [])
    raw_candidates = compact.get("candidate_actions")
    compact_candidates: list[dict[str, Any]] = []
    if isinstance(raw_candidates, list):
        for raw in raw_candidates:
            if not isinstance(raw, Mapping):
                continue
            candidate = dict(raw)
            candidate.pop("lifecycle_events", None)
            compact_candidates.append(candidate)
    compact["candidate_actions"] = compact_candidates
    operator_detail = {
        "profile": "learning_lifecycle_operator_detail",
        "detail_command": LEARNING_OPERATOR_DETAIL_COMMAND,
        "guidance_lifecycle_ledger": list(ledger) if isinstance(ledger, list) else [],
        "claim_boundary": "operator lifecycle rows explain candidate state; they are not source truth",
    }
    return compact, operator_detail


def _current_guidance_rows(lifecycle: Mapping[str, Any], *, limit: int = 3) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    candidates = lifecycle.get("candidate_actions")
    if not isinstance(candidates, list):
        return rows
    for raw in candidates:
        if not isinstance(raw, Mapping):
            continue
        review_action = raw.get("review_action")
        row = {
            "guidance_id": raw.get("guidance_id"),
            "candidate_kind": raw.get("candidate_kind"),
            "next_action": raw.get("next_action"),
            "source_ref_count": raw.get("source_ref_count", 0),
            "materialization_gate": raw.get("materialization_gate"),
            "outcome_status": raw.get("outcome_status"),
            "claim_boundary": raw.get("claim_boundary") or "learning_guidance_not_source_truth",
        }
        if isinstance(review_action, Mapping):
            row["review_action"] = dict(review_action)
        materialization_action = raw.get("materialization_action")
        if isinstance(materialization_action, Mapping):
            row["materialization_action"] = dict(materialization_action)
        rows.append(row)
        if len(rows) >= limit:
            break
    return rows


def _review_current_guidance_action(current_guidance: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not current_guidance:
        return None
    review_action = current_guidance[0].get("review_action")
    if not isinstance(review_action, Mapping):
        return None
    action = dict(review_action)
    action["why"] = (
        "Review the top visible semantic guidance candidate before exporting history "
        "or writing any action-time cache."
    )
    return action


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
    for row in behavioral_records(root):
        candidates.append(
            {
                "id": row["id"],
                "label": row["label"],
                "status": row["status"],
                "path_label": row["path_label"],
                "row_count": row["row_count"],
                "authority": row["authority"],
                "source_truth": False,
                "raw_private_text_loaded": False,
                "purge_command": (
                    "aippocampus learning purge-behavioral-records "
                    f"--target {row['id']} --dry-run --json"
                ),
            }
        )
    setup_actions = _learning_setup_actions()
    primary_action = {
        **setup_actions[1],
        "why": "If no candidate is available yet, inspect guidance before exporting or replaying anything.",
    }
    action_fields = canonical_foreground_action_fields(
        primary_action,
        safe_next_actions=_unique_actions(primary_action, *setup_actions),
        max_safe_next_actions=COMPACT_SAFE_NEXT_ACTION_BUDGET,
    )
    return _public_payload(
        _with_boundary_detail(
            {
            "kind": KIND,
            "schema_version": SCHEMA_VERSION,
            "mode": "discover-history",
            "ok": True,
            "status": "source_selection",
            "candidate_count": len(candidates),
            "available_candidate_count": sum(1 for row in candidates if row["status"] == "available"),
            "candidates": candidates,
            **action_fields,
            "privacy_boundary": _privacy_boundary(),
            },
            cannot_claim=[
                "private_history_scanned_by_default",
                "learned_guidance_as_source_truth",
            ],
        )
    )


def status_payload(
    *,
    cwd: Path,
    no_default_learning: bool = False,
    include_operator_detail: bool = False,
    guidance_id: str | None = None,
) -> dict[str, Any]:
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
    semantic_report = build_semantic_learning_dogfood_fixture_report()
    semantic_metrics = dict(semantic_report.get("metrics") or {})
    semantic_stage = dict((semantic_report.get("stage_report") or {}).get("metrics") or {})
    semantic_lifecycle = semantic_guidance_lifecycle(
        semantic_report,
        prepared_count=prepared_count,
        prepared_rows=(report.get("cache") or {}).get("records") or [],
    )
    compact_lifecycle, operator_detail = _compact_semantic_lifecycle(semantic_lifecycle)
    requested_guidance_id = str(guidance_id or "").strip()
    current_guidance = _current_guidance_rows(
        compact_lifecycle,
        limit=5 if requested_guidance_id else 3 if include_operator_detail else 1,
    )
    if requested_guidance_id:
        current_guidance = [
            row for row in current_guidance if str(row.get("guidance_id") or "") == requested_guidance_id
        ]
    semantic_count = int(semantic_metrics.get("action_time_guidance_count") or 0)
    summary_metrics = {
        "default_learning_status": intake.get("status"),
        "finding_count": intake.get("finding_count", 0),
        "included_count": intake.get("included_count", 0),
        "prepared_action_hint_count": prepared_count,
        "effectiveness_ledger_row_count": ledger_intake.get("row_count", 0),
        "semantic_loop_stage": (semantic_report.get("stage_report") or {}).get("stage"),
        "semantic_action_time_guidance_count": semantic_count,
        "cache_write_requested": False,
    }
    primary_action = (
        foreground_shell_action(
            action_id="refresh_action_hint_cache",
            label="Prepare action-time cache",
            command=cache_command,
            why="Prepared guidance exists and can be materialized into the local action-hint cache.",
            mutation_risk="explicit_local_cache_write",
            claim_boundary="learning_guidance_not_source_truth",
        )
        if prepared_count
        else (_review_current_guidance_action(current_guidance) or _learning_discovery_action())
    )
    followup_actions = (
        _unique_actions(primary_action, *_learning_setup_actions())
        if prepared_count
        else _unique_actions(
            primary_action,
            preview_cache_bridge_action() if current_guidance else None,
            *_learning_setup_actions(),
        )
    )
    action_fields, frontdoor_operator_detail = _compact_learning_action_fields(
        primary_action,
        followup_actions,
    )
    next_actions = cast(list[dict[str, object]], action_fields["safe_next_actions"])
    payload: dict[str, Any] = {
        "kind": KIND,
        "schema_version": SCHEMA_VERSION,
        "mode": "status",
        "ok": True,
        "route_value": "current_learning_guidance_is_navigation_for_next_action",
        "current_uncertainty": (
            "prepared_guidance_ready_for_explicit_cache_write"
            if prepared_count
            else (
                "semantic_guidance_requires_review_before_cache"
                if current_guidance
                else "no_current_guidance_source_selected"
            )
        ),
        **action_fields,
        "next_actions": next_actions,
        "current_guidance": current_guidance,
        "summary_metrics": summary_metrics,
        "summary": summary_metrics,
        "lanes": lanes,
        "current_guidance_summary": {
            "selected_count": len(current_guidance),
            "available_action_time_guidance_count": semantic_count,
            "boundary": "guidance is navigation, not source truth; reopen source before claims.",
        },
        "operator_detail_command": LEARNING_OPERATOR_DETAIL_COMMAND,
        "privacy_boundary": _privacy_boundary(),
    }
    if include_operator_detail:
        operator_detail = {
            **operator_detail,
            "learning_frontdoor_actions": frontdoor_operator_detail,
        }
        payload["semantic_loop"] = {
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
        }
        payload["semantic_guidance_lifecycle"] = compact_lifecycle
        payload["operator_detail"] = operator_detail
    return _public_payload(
        _with_boundary_detail(
            payload,
            cannot_claim=(
                [
                    "causal_live_behavior_lift",
                    "learned_guidance_as_source_truth",
                    "private_history_scanned_by_default",
                ]
                if include_operator_detail
                else []
            ),
        )
    )


def guidance_payload(
    *,
    cwd: Path,
    no_default_learning: bool = False,
    include_operator_detail: bool = False,
    guidance_id: str | None = None,
) -> dict[str, Any]:
    payload = status_payload(
        cwd=cwd,
        no_default_learning=no_default_learning,
        include_operator_detail=include_operator_detail,
        guidance_id=guidance_id,
    )
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
        next_action = preview_cache_bridge_action()
        materialization_status = "semantic_guidance_requires_review_before_cache"
    else:
        next_action = _learning_discovery_action()
        materialization_status = "needs_learning_input"
    lifecycle = dict(payload.get("semantic_guidance_lifecycle") or {})
    current_guidance = list(payload.get("current_guidance") or [])
    review_action = _review_current_guidance_action(
        [row for row in current_guidance if isinstance(row, dict)]
    )
    safe_next_actions = (
        _unique_actions(next_action, review_action, *_learning_setup_actions())
        if semantic_count
        else _unique_actions(next_action, *_learning_setup_actions())
    )
    action_fields, frontdoor_operator_detail = _compact_learning_action_fields(
        next_action,
        safe_next_actions,
    )
    semantic_guidance = {
        "guidance_count": semantic_count,
        "materialization_status": materialization_status,
        "cache_materialization_command": "aippocampus hooks action refresh-cache --json",
        "operator_detail_command": LEARNING_OPERATOR_DETAIL_COMMAND,
    }
    if include_operator_detail:
        semantic_guidance["lifecycle"] = lifecycle
        operator_detail = dict(payload.get("operator_detail") or {})
        operator_detail["learning_frontdoor_actions"] = frontdoor_operator_detail
        payload["operator_detail"] = operator_detail
    if not include_operator_detail:
        payload.pop("semantic_guidance_lifecycle", None)
        payload.pop("operator_detail", None)
    return _public_payload(
        {
            **payload,
            "mode": "guidance",
            **action_fields,
            "cache_command": "aippocampus hooks action refresh-cache --write --json",
            "semantic_guidance": semantic_guidance,
        }
    )


def replay_needs_source_payload() -> dict[str, Any]:
    primary_action = _learning_discovery_action()
    action_fields = canonical_foreground_action_fields(
        primary_action,
        safe_next_actions=_unique_actions(primary_action, *_learning_setup_actions()),
    )
    return _public_payload(
        _with_boundary_detail(
            {
            "kind": KIND,
            "schema_version": SCHEMA_VERSION,
            "mode": "replay",
            "ok": False,
            "status": "needs_source_selection",
            "fixture_input": False,
            **action_fields,
            "metrics_boundary": {
                "fixture_metrics_are_not_real_history": True,
                "real_history_replay_requires_sanitized_events": True,
            },
            "privacy_boundary": _privacy_boundary(),
            },
            cannot_claim=[
                "causal_live_behavior_lift",
                "private_history_scanned_by_default",
                "guidance_as_source_truth",
            ],
            include_cannot_claim=False,
        )
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
        _with_boundary_detail(
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
            "next_step_hint": (
                replay_next_actions[0]["command"]
                if replay_next_actions
                else "inspect replay metrics and append an effectiveness ledger only after review"
            ),
            "next_actions": replay_next_actions,
            },
            cannot_claim=report.get("cannot_claim") or [],
        )
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
    elif payload.get("next_step_hint"):
        lines.append("next: " + str(payload["next_step_hint"]))
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
    parser.add_argument("--operator-json", action="store_true")
    parser.add_argument("--detail", choices=["compact", "full"], default="compact")
    status = sub.add_parser("status")
    status.add_argument("--cwd")
    status.add_argument("--no-default-learning", action="store_true")
    status.add_argument("--json", action="store_true")
    status.add_argument("--operator-json", action="store_true")
    status.add_argument("--detail", choices=["compact", "full"], default="compact")

    guidance = sub.add_parser("guidance")
    guidance.add_argument("--cwd")
    guidance.add_argument("--no-default-learning", action="store_true")
    guidance.add_argument("--guidance-id")
    guidance.add_argument("--json", action="store_true")
    guidance.add_argument("--operator-json", action="store_true")
    guidance.add_argument("--detail", choices=["compact", "full"], default="compact")

    replay = sub.add_parser("replay")
    replay.add_argument("--events", type=Path)
    replay.add_argument("--clean-source-events", type=Path)
    replay.add_argument("--rollout", type=Path)
    replay.add_argument("--export-output", type=Path)
    replay.add_argument("--json", action="store_true")

    discover = sub.add_parser("discover-history")
    discover.add_argument("--cwd")
    discover.add_argument("--json", action="store_true")

    behavior = sub.add_parser("behavioral-records")
    behavior.add_argument("--cwd")
    behavior.add_argument("--json", action="store_true")

    purge_behavior = sub.add_parser("purge-behavioral-records")
    purge_behavior.add_argument("--cwd")
    purge_behavior.add_argument(
        "--target",
        default="all",
        choices=[
            "all",
            "effectiveness-ledger",
            "effectiveness_ledger",
            "recall-outcome-feedback",
            "recall_outcome_feedback",
            "route-feedback",
            "agent-route-feedback",
            "agent_route_feedback",
        ],
    )
    purge_behavior.add_argument("--dry-run", action="store_true")
    purge_behavior.add_argument("--confirm", action="store_true")
    purge_behavior.add_argument("--json", action="store_true")

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
    args_list = list(sys.argv[1:] if argv is None else argv)
    if not args_list:
        args_list = ["status"]
    parser = build_parser()
    args = parser.parse_args(args_list)
    if args.command == "replay":
        try:
            payload = replay_payload(args)
        except LearningReplayInputError as exc:
            payload = replay_recovery_payload(exc)
        except ValueError as exc:
            parser.error(str(exc))
    elif args.command == "discover-history":
        payload = discover_history_payload(cwd=_cwd(args.cwd))
    elif args.command == "behavioral-records":
        payload = behavioral_records_inventory_payload(cwd=_cwd(args.cwd))
    elif args.command == "purge-behavioral-records":
        payload = purge_behavioral_records_payload(
            cwd=_cwd(args.cwd),
            target=args.target,
            dry_run=bool(args.dry_run),
            confirm=bool(args.confirm),
        )
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
        payload = guidance_payload(
            cwd=_cwd(args.cwd),
            no_default_learning=args.no_default_learning,
            include_operator_detail=bool(args.operator_json or args.detail == "full"),
            guidance_id=args.guidance_id,
        )
    else:
        payload = status_payload(
            cwd=_cwd(args.cwd),
            no_default_learning=args.no_default_learning,
            include_operator_detail=bool(args.operator_json or args.detail == "full"),
        )
    if getattr(args, "json", False):
        _json_out(payload)
    else:
        print(render_human(payload))
    return 0 if payload.get("ok", True) else 2


if __name__ == "__main__":
    raise SystemExit(main())
