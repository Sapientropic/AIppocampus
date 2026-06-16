"""Foreground personal controls for low-friction memory boundaries.

These commands are intentionally small front doors over existing ledgers and
diagnostics. They give users copyable controls without pretending that feedback
is source truth or that safe pause/forget semantics are universal deletes.
"""

from __future__ import annotations

import argparse
import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from aippocampus_runtime.contracts import foreground_shell_action
from aippocampus_runtime.coding import host_contract
from aippocampus_runtime.privacy import redact_private_paths, redact_sensitive_values
from aippocampus_runtime.recall.agent_continuity_cli_support import (
    capture_feedback,
    compact_feedback_receipt,
    feedback_lane_resolution,
)

KIND = "aippocampus_personal_control"
SCHEMA_VERSION = 1
def _json_out(payload: Mapping[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


def _public_payload(payload: Any) -> Any:
    return redact_sensitive_values(redact_private_paths(payload))


def _reason_code(value: str | None) -> str:
    raw = (value or "do_not_use_here").strip().lower()
    normalized = re.sub(r"[^a-z0-9_.-]+", "-", raw).strip("-_.")
    return (normalized or "do_not_use_here")[:80]

def _boundary() -> dict[str, Any]:
    return {
        "feedback_changes_source_truth": False,
        "source_reopen_required_for_claims": True,
        "raw_prompt_or_source_text_stored_by_default": False,
        "scope_must_stay_local_or_explicit": True,
    }


def _safe_plan_card(command: str, *, target: str = "") -> dict[str, Any]:
    if command == "pause":
        return {
            "kind": KIND,
            "schema_version": SCHEMA_VERSION,
            "mode": "pause",
            "status": "needs_scope",
            "ok": True,
            "control": "pause",
            "target": target,
            "what_it_can_do_now": [
                "pause influence for one explicit route or ticket through local low-authority feedback",
                "show the safe boundary for broader pause decisions without mutating source truth",
            ],
            "cannot_claim": [
                "ambient continuity is paused globally",
                "existing source or audit material was deleted",
            ],
            "safe_next_actions": [
                foreground_shell_action(
                    action_id="find_pause_target",
                    label="Find the route to pause here",
                    command='aippocampus agent recall "route to pause" --json',
                    why="Use recall to get a concrete route id before writing scoped feedback.",
                    mutation_risk="read_only",
                    claim_boundary="no_claim_before_reopen",
                ),
                foreground_shell_action(
                    action_id="review_control_boundary",
                    label="Review the control frontdoor",
                    command="aippocampus controls --json",
                    why="Use this when choosing between pause, forget, and do-not-use-here.",
                    mutation_risk="read_only",
                    claim_boundary="operator_diagnostic_not_source_evidence",
                ),
            ],
            "boundary": _boundary(),
        }
    return {
        "kind": KIND,
        "schema_version": SCHEMA_VERSION,
        "mode": "forget",
        "status": "needs_scope",
        "ok": True,
        "control": "forget",
        "target": target,
        "what_it_can_do_now": [
            "plan a non-destructive hide/suppress/tombstone decision",
            "route scoped quieting to do-not-use-here when the target is a route or ticket",
        ],
        "cannot_claim": [
            "raw audit history was physically deleted",
            "all copies on other devices or backups were removed",
        ],
        "safe_next_actions": [
            foreground_shell_action(
                action_id="find_forget_target",
                label="Find the route to forget here",
                command='aippocampus agent recall "route to forget here" --json',
                why="Use recall to get a concrete route id before scoped quieting.",
                mutation_risk="read_only",
                claim_boundary="no_claim_before_reopen",
            ),
                foreground_shell_action(
                    action_id="preview_export_for_review",
                    label="Review export boundary",
                    command="aippocampus export --help",
                why="Use export only when reviewing or transferring explicit local material.",
                mutation_risk="read_only",
                claim_boundary="operator_diagnostic_not_source_evidence",
            ),
        ],
        "boundary": _boundary(),
    }


def _scoped_control_payload(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    payload, code = do_not_use_here_payload(args)
    scoped = dict(payload)
    mode = str(args.command)
    scoped.update(
        {
            "mode": mode,
            "control": mode,
            "status": "scoped_control_captured"
            if payload.get("write_boundary", {}).get("wrote_event")
            else "not_quieted_yet",
            "cannot_claim": [
                "raw audit history was physically deleted",
                "all copies on other devices or backups were removed",
                "source truth changed because of this control",
            ],
            "agent_next_action": (
                "continue the task; this scoped local feedback can reduce future route pressure"
                if payload.get("write_boundary", {}).get("wrote_event")
                else "run aippocampus controls --json to choose a scoped retry path"
            ),
        }
    )
    return _public_payload(scoped), code


def _render_plan_card(payload: Mapping[str, Any]) -> str:
    lines = [
        f"AIppocampus {payload.get('mode')}: {payload.get('status')}",
        "what it can do now: " + "; ".join(str(item) for item in payload.get("what_it_can_do_now") or []),
        "cannot claim: " + "; ".join(str(item) for item in payload.get("cannot_claim") or []),
        "next:",
    ]
    for action in payload.get("safe_next_actions") or []:
        if isinstance(action, Mapping):
            lines.append("  " + str(action.get("command") or action.get("label") or ""))
    lines.append("boundary: feedback or suppression changes future activation pressure, not source truth.")
    return "\n".join(lines)


def _ticket_feedback_row(*, ticket_id: str, outcome: str, reason_code: str) -> dict[str, Any]:
    if outcome not in host_contract.FEEDBACK_OUTCOMES:
        outcome = "dismissed"
    return {
        "kind": "aippocampus_agency_ticket_feedback",
        "schema_version": SCHEMA_VERSION,
        "ticket_id": ticket_id,
        "outcome": outcome,
        "reason_code": reason_code,
        "suppression_reason_code": "recent_feedback_suppressed",
        "activation_effect": "quieter",
        "raw_feedback_text_stored": False,
        "feedback_changes_source_truth": False,
    }


def _write_jsonl(path: Path, row: Mapping[str, Any]) -> None:
    path.resolve().parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(dict(row), ensure_ascii=False, sort_keys=True) + "\n")


def _load_ticket_json(path: str | None) -> dict[str, Any] | None:
    if not path:
        return None
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return dict(payload) if isinstance(payload, Mapping) else None


def do_not_use_here_payload(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    if not args.target:
        return (
            _public_payload(
                {
                    "kind": KIND,
                    "schema_version": SCHEMA_VERSION,
                    "mode": "do-not-use-here",
                    "status": "needs_target",
                    "ok": False,
                    "agent_next_action": {
                        "id": "choose_control_target",
                        "command": 'aippocampus agent recall "route to quiet" --json',
                        "why": "Find the recall route id first, then quiet it for this workspace.",
                    },
                    "safe_next_actions": [
                        {
                            "id": "find_recall_route",
                            "command": 'aippocampus agent recall "route to quiet" --json',
                            "surface": "recall-route",
                            "mutation_risk": "read_only",
                        },
                        {
                            "id": "quiet_recall_route_here",
                            "command_template": "aippocampus do-not-use-here ROUTE_ID_FROM_RECALL --surface recall-route --json",
                            "requires": "route_id",
                            "surface": "recall-route",
                            "mutation_risk": "durable_low_authority_feedback_write",
                        },
                        {
                            "id": "quiet_coding_ticket_here",
                            "command_template": "aippocampus do-not-use-here TICKET_ID --surface coding-ticket --json",
                            "requires": "ticket_id",
                            "surface": "coding-ticket",
                            "mutation_risk": "durable_local_control_write",
                        },
                    ],
                    "boundary": _boundary(),
                }
            ),
            2,
        )
    reason_code = _reason_code(args.reason)
    lane = feedback_lane_resolution(
        args.feedback_jsonl,
        cwd=args.cwd,
        registry_dir=args.registry_dir,
    )
    path = lane["path"]
    path_source = str(lane.get("path_source") or "unknown")
    if args.surface == "recall-route":
        payload = capture_feedback(
            route_id=args.target,
            outcome=args.outcome or "wrong_route_drag",
            route_kind="active_path",
            reason=reason_code,
            feedback_path=path,
            feedback_lane=lane,
            schema_version="agent-continuity-path-v1",
            kind="aippocampus_agent_continuity_path",
        )
        receipt = compact_feedback_receipt(payload)
        wrote_event = bool(receipt.get("write_boundary", {}).get("wrote_event"))
        return (
            _public_payload(
                {
                    "kind": KIND,
                    "schema_version": SCHEMA_VERSION,
                    "mode": "do-not-use-here",
                    "status": "captured" if wrote_event else "not_durable",
                    "ok": True,
                    "surface": "recall-route",
                    "target": args.target,
                    "feedback_path_source": path_source,
                    "feedback_lane": receipt.get("feedback_lane") or lane,
                    "quieted_future_routes": wrote_event,
                    "write_boundary": receipt.get("write_boundary"),
                    "feedback": receipt,
                    "why_not_card": (
                        {
                            "status": "durable_feedback_available",
                            "reason_codes": ["negative_route_feedback"],
                            "safe_readout": (
                                "future recall can quiet this route when run with the same "
                                "feedback JSONL"
                            ),
                        }
                        if wrote_event
                        else {
                            "status": "not_quieted_yet",
                            "reason_codes": ["feedback_receipt_only"],
                            "safe_readout": "nothing durable was written; rerun with a resolvable feedback lane",
                        }
                    ),
                    "next_safe_action": (
                        "continue the task; future recall can use this JSONL as low-authority calibration"
                    if wrote_event
                    else "not quieted yet; rerun with --feedback-jsonl <path> or a writable default registry"
                ),
                    "boundary": _boundary(),
                }
            ),
            0,
        )
    row = _ticket_feedback_row(
        ticket_id=args.target,
        outcome=args.ticket_outcome or "dismissed",
        reason_code=reason_code,
    )
    wrote_event = path is not None
    if path is not None:
        _write_jsonl(path, row)
    ticket = _load_ticket_json(args.ticket_json)
    action_time_decision = {}
    activation_tuning = {}
    if ticket is not None:
        action_time_decision = host_contract.host_decision_for_ticket(
            ticket,
            recent_feedback=[row],
        )
        activation_tuning = host_contract.tune_activation_from_feedback([ticket], [row])
    consumed = "recent_feedback_suppressed" in action_time_decision.get("suppression_reasons", [])
    return (
        _public_payload(
            {
                "kind": KIND,
                "schema_version": SCHEMA_VERSION,
                "mode": "do-not-use-here",
                "status": "quieted" if consumed else ("captured" if wrote_event else "not_durable"),
                "ok": True,
                "surface": "coding-ticket",
                "target": args.target,
                "feedback_path_source": path_source,
                "feedback_lane": lane,
                "quieted_future_tickets": bool(wrote_event),
                "action_time_consumed": consumed,
                "write_boundary": {
                    "storage": "jsonl" if wrote_event else "receipt_only",
                    "wrote_event": wrote_event,
                    "will_affect_future_tickets": wrote_event,
                    "source_truth_changed_by_feedback": False,
                },
                "row": row,
                "action_time_decision": action_time_decision,
                "activation_tuning": activation_tuning,
                "why_not_card": (
                    {
                        "suppression_class": "recent_negative_feedback",
                        "reason_codes": ["recent_feedback_suppressed"],
                        "consumer": "aippocampus_runtime.coding.host_contract.host_decision_for_ticket",
                    }
                    if consumed
                    else {
                        "status": "not_quieted_yet" if not wrote_event else "not_consumed_yet",
                        "reason_codes": ["feedback_receipt_only" if not wrote_event else "feedback_not_applied_to_ticket"],
                        "safe_readout": (
                            "nothing durable was written; add --feedback-jsonl"
                            if not wrote_event
                            else "feedback was written; pass the current ticket with --ticket-json to show suppression"
                        ),
                    }
                ),
                "next_safe_action": (
                    "pass the same feedback JSONL to the host/ticket decision path; no source fact changed"
                    if wrote_event and not consumed
                    else "ticket quieted for this action-time decision; no source fact changed"
                    if consumed
                    else (
                        "rerun with --feedback-jsonl local-feedback.jsonl or a writable "
                        "default registry when you want this to quiet future ticket surfacing"
                    )
                ),
                "boundary": _boundary(),
            }
        ),
        0,
    )


def build_parser(prog: str = "aippocampus pause") -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=prog,
        usage=f"{prog} [target] [options]",
        description=(
            "Personal control card for pause, forget, and do-not-use-here. "
            "Controls tune or plan foreground behavior; they do not rewrite source truth."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Safe examples:\n"
            "  aippocampus pause --json\n"
            "  aippocampus forget --json\n"
            "  aippocampus do-not-use-here --json\n\n"
            "Boundary: feedback and quieting change future activation pressure only; reopen source before claims."
        ),
    )
    parser.add_argument("target", nargs="?")
    parser.add_argument(
        "--surface",
        choices=["recall-route", "coding-ticket"],
        default="recall-route",
        help="What kind of artifact should be quieted.",
    )
    parser.add_argument(
        "--feedback-jsonl",
        help="Optional durable local feedback JSONL. Defaults to a scoped registry lane.",
    )
    parser.add_argument("--cwd", help="Workspace scope for the default feedback lane.")
    parser.add_argument("--registry-dir", help="Registry root for the default feedback lane.")
    parser.add_argument(
        "--outcome",
        default="wrong_route_drag",
        help="Recall-route feedback signal or alias, e.g. wrong, noisy, stale.",
    )
    parser.add_argument(
        "--ticket-outcome",
        default="dismissed",
        choices=host_contract.FEEDBACK_OUTCOMES,
        help="Coding-ticket feedback outcome.",
    )
    parser.add_argument(
        "--ticket-json",
        help=(
            "Optional current coding-ticket JSON. When supplied with --surface coding-ticket, "
            "the command immediately shows the host decision/why-not suppression readout."
        ),
    )
    parser.add_argument(
        "--reason",
        "--reason-code",
        default="do_not_use_here",
        help="Short public-safe reason code; raw prose/source text is not stored.",
    )
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    raw = list(argv or [])
    command = raw.pop(0) if raw and raw[0] in {"pause", "forget", "do-not-use-here"} else "pause"
    parser = build_parser(prog=f"aippocampus {command}")
    args = parser.parse_args(raw)
    args.command = command
    if args.command in {"pause", "forget"}:
        if args.target:
            payload, code = _scoped_control_payload(args)
            if args.json:
                _json_out(payload)
            else:
                print(_render_plan_card(payload))
            return code
        payload = _public_payload(_safe_plan_card(args.command, target=""))
        if args.json:
            _json_out(payload)
        else:
            print(_render_plan_card(payload))
        return 0
    payload, code = do_not_use_here_payload(args)
    if args.json:
        _json_out(payload)
    else:
        print(f"AIppocampus do-not-use-here: {payload.get('status')}")
        print("surface: " + str(payload.get("surface") or "unknown"))
        boundary = payload.get("write_boundary") or {}
        print("storage: " + str(boundary.get("storage") or "receipt_only"))
        print("next: " + str(payload.get("next_safe_action") or payload.get("agent_next_action") or "continue"))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
