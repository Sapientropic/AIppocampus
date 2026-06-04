#!/usr/bin/env python3
"""Deterministic replay for agency-ticket host timing.

This helper pressure-tests when a host should show, hold, or suppress
AIppocampus agency tickets. It is a replay/evidence surface only: the host still
owns permission, priority, sequencing, safety, and execution.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

from aippocampus_runtime.coding import agency_affordance as agency

REPLAY_KIND = "aippocampus_agency_host_timing_replay"
SURFACE_EVENT_KIND = "aippocampus_agency_ticket_surface_event"
SCHEMA_VERSION = 1

DECISION_SHOW = "show"
DECISION_HOLD = "hold"
DECISION_SUPPRESS = "suppress"
ACTIONABLE_PHASES = {"planning", "pre_action", "before_tool", "resume"}
NEGATIVE_FEEDBACK = {"dismissed", "ignored", "corrected", "tool_failure"}


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _source_refs(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    return [dict(item) for item in value if isinstance(item, Mapping)]


def fixture_source_ref(line: int, *, message_id: str | None = None) -> dict[str, Any]:
    return {
        "thread_key": "session:agency-host-timing",
        "message_id": message_id or f"msg-{line}",
        "source_line": line,
        "timestamp": "2026-06-04T00:00:00Z",
    }


def host_duplicate_key(ticket: Mapping[str, Any]) -> str:
    source_fp = str(ticket.get("source_ref_fingerprint") or "")
    if not source_fp:
        source_fp = agency.source_ref_fingerprint(_source_refs(ticket.get("source_refs")))
    scope = _as_mapping(ticket.get("scope"))
    return agency.stable_id(
        "agency_host_duplicate",
        source_fp,
        scope.get("kind"),
        scope.get("stable_id"),
        ticket.get("intervention_level"),
        length=20,
    )


def host_surface_event(
    ticket: Mapping[str, Any],
    *,
    host_id: str,
    topic_epoch: str,
    outcome: str = "shown",
) -> dict[str, Any]:
    source_fp = str(ticket.get("source_ref_fingerprint") or "")
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": SURFACE_EVENT_KIND,
        "created_at": agency.now_utc(),
        "ticket_id": ticket.get("ticket_id"),
        "affordance_id": ticket.get("affordance_id"),
        "topic_epoch": topic_epoch,
        "surface_host": host_id,
        "duplicate_key": host_duplicate_key(ticket),
        "source_ref_fingerprint": source_fp,
        "intervention_level": ticket.get("intervention_level"),
        "outcome": outcome,
    }


def _matching_duplicate_event(
    ticket: Mapping[str, Any],
    *,
    topic_epoch: str,
    surface_history: Sequence[Mapping[str, Any]],
) -> Mapping[str, Any] | None:
    duplicate_key = host_duplicate_key(ticket)
    source_fp = str(ticket.get("source_ref_fingerprint") or "")
    for event in surface_history:
        if str(event.get("topic_epoch") or "") != topic_epoch:
            continue
        if str(event.get("duplicate_key") or "") == duplicate_key:
            return event
        if source_fp and str(event.get("source_ref_fingerprint") or "") == source_fp:
            return event
    return None


def _matching_negative_feedback(
    ticket: Mapping[str, Any],
    *,
    feedback_history: Sequence[Mapping[str, Any]],
) -> Mapping[str, Any] | None:
    duplicate_key = host_duplicate_key(ticket)
    affordance_id = str(ticket.get("affordance_id") or "")
    ticket_id = str(ticket.get("ticket_id") or "")
    for row in feedback_history:
        if str(row.get("outcome") or "") not in NEGATIVE_FEEDBACK:
            continue
        if str(row.get("duplicate_key") or "") == duplicate_key:
            return row
        if affordance_id and str(row.get("affordance_id") or "") == affordance_id:
            return row
        if ticket_id and str(row.get("ticket_id") or "") == ticket_id:
            return row
    return None


def evaluate_host_timing(
    affordance_map: Mapping[str, Any],
    *,
    case_id: str,
    trigger: str,
    topic_epoch: str,
    host_id: str,
    task_phase: str,
    current_user_action: str,
    visible_context_refs: Sequence[Mapping[str, Any]] | None = None,
    surface_history: Sequence[Mapping[str, Any]] | None = None,
    feedback_history: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    selection = agency.select_agency_tickets(
        affordance_map,
        trigger=trigger,
        topic_epoch=topic_epoch,
    )
    tickets = [
        ticket
        for ticket in selection.get("foreground_tickets") or []
        if isinstance(ticket, Mapping)
    ]
    base = {
        "case_id": case_id,
        "trigger": trigger,
        "topic_epoch": topic_epoch,
        "host_id": host_id,
        "task_phase": task_phase,
        "current_user_action": current_user_action,
        "foreground_ticket_count": len(tickets),
        "selected_intervention_level": "",
        "source_ref_fingerprint": "",
        "duplicate_key": "",
        "surface_event": {},
        "duplicate_source_host": "",
        "feedback_outcome": "",
    }
    if not tickets:
        return {**base, "decision": DECISION_SUPPRESS, "reason": "selector_suppressed"}
    ticket = tickets[0]
    source_fp = str(ticket.get("source_ref_fingerprint") or "")
    duplicate_key = host_duplicate_key(ticket)
    base.update(
        {
            "selected_intervention_level": str(ticket.get("intervention_level") or ""),
            "source_ref_fingerprint": source_fp,
            "duplicate_key": duplicate_key,
        }
    )
    if task_phase not in ACTIONABLE_PHASES:
        return {**base, "decision": DECISION_HOLD, "reason": "task_phase_not_actionable"}
    visible_keys = agency.visible_ref_keys(visible_context_refs or [])
    if agency.is_visible(_source_refs(ticket.get("source_refs")), visible_context_ref_keys=visible_keys):
        return {**base, "decision": DECISION_SUPPRESS, "reason": "source_visible"}
    feedback = _matching_negative_feedback(ticket, feedback_history=feedback_history or [])
    if feedback:
        return {
            **base,
            "decision": DECISION_SUPPRESS,
            "reason": "recent_negative_feedback",
            "feedback_outcome": str(feedback.get("outcome") or ""),
        }
    duplicate = _matching_duplicate_event(
        ticket,
        topic_epoch=topic_epoch,
        surface_history=surface_history or [],
    )
    if duplicate:
        return {
            **base,
            "decision": DECISION_SUPPRESS,
            "reason": "duplicate_across_host",
            "duplicate_source_host": str(duplicate.get("surface_host") or ""),
        }
    event = host_surface_event(ticket, host_id=host_id, topic_epoch=topic_epoch)
    return {**base, "decision": DECISION_SHOW, "reason": "actionable_host_moment", "surface_event": event}


def fixture_affordance_map(*, topic_epoch: str = "epoch-agency-host") -> dict[str, Any]:
    return agency.build_agency_affordance_map(
        correction_windows=[
            {
                "kind": "correction_active_task_anchor",
                "summary": "Warn before repeating the ignored generated-file route.",
                "instruction": "Do not repeat the generated artifact edit path.",
                "adjudication_status": "valid_ignored",
                "source_refs": [
                    fixture_source_ref(10, message_id="msg-boundary"),
                    fixture_source_ref(11, message_id="msg-test-output"),
                ],
                "scope": {
                    "kind": "workspace",
                    "stable_id": "agency-host-fixture",
                    "label": "agency host timing replay fixture",
                },
                "annoyance_risk": "medium",
            }
        ],
        topic_epoch=topic_epoch,
    )


def _fixture_ticket(affordance_map: Mapping[str, Any], *, topic_epoch: str) -> Mapping[str, Any]:
    selection = agency.select_agency_tickets(
        affordance_map,
        trigger="user_correction",
        topic_epoch=topic_epoch,
    )
    return _as_mapping((selection.get("foreground_tickets") or [{}])[0])


def fixture_host_timing_replay() -> dict[str, Any]:
    topic_epoch = "epoch-agency-host"
    affordance_map = fixture_affordance_map(topic_epoch=topic_epoch)
    ticket = _fixture_ticket(affordance_map, topic_epoch=topic_epoch)
    prior_event = host_surface_event(
        ticket,
        host_id="codex-desktop",
        topic_epoch=topic_epoch,
    )
    dismissed = agency.record_ticket_feedback(ticket, outcome="dismissed")
    dismissed["duplicate_key"] = host_duplicate_key(ticket)
    cases = [
        evaluate_host_timing(
            affordance_map,
            case_id="show_compaction_warning",
            trigger="user_correction",
            topic_epoch=topic_epoch,
            host_id="codex-desktop",
            task_phase="pre_action",
            current_user_action="about_to_repeat_generated_artifact_route",
        ),
        evaluate_host_timing(
            affordance_map,
            case_id="hold_post_answer_phase",
            trigger="user_correction",
            topic_epoch=topic_epoch,
            host_id="codex-desktop",
            task_phase="post_answer",
            current_user_action="idle_after_response",
        ),
        evaluate_host_timing(
            affordance_map,
            case_id="suppress_visible_source",
            trigger="user_correction",
            topic_epoch=topic_epoch,
            host_id="codex-desktop",
            task_phase="pre_action",
            current_user_action="source_already_visible",
            visible_context_refs=_source_refs(ticket.get("source_refs")),
        ),
        evaluate_host_timing(
            affordance_map,
            case_id="suppress_cross_host_duplicate",
            trigger="user_correction",
            topic_epoch=topic_epoch,
            host_id="claude-code",
            task_phase="pre_action",
            current_user_action="same_route_in_second_host",
            surface_history=[prior_event],
        ),
        evaluate_host_timing(
            affordance_map,
            case_id="suppress_recent_dismissal",
            trigger="user_correction",
            topic_epoch=topic_epoch,
            host_id="codex-desktop",
            task_phase="pre_action",
            current_user_action="same_route_after_dismissal",
            feedback_history=[dismissed],
        ),
    ]
    decision_counts = dict(sorted(Counter(str(case.get("decision") or "") for case in cases).items()))
    reason_counts = dict(sorted(Counter(str(case.get("reason") or "") for case in cases).items()))
    return {
        "kind": REPLAY_KIND,
        "schema_version": SCHEMA_VERSION,
        "ok": True,
        "cases": cases,
        "cases_by_id": {str(case["case_id"]): case for case in cases},
        "aggregate": {
            "case_count": len(cases),
            "decision_counts": decision_counts,
            "reason_counts": reason_counts,
            "foreground_show_count": decision_counts.get(DECISION_SHOW, 0),
            "hold_count": decision_counts.get(DECISION_HOLD, 0),
            "suppress_count": decision_counts.get(DECISION_SUPPRESS, 0),
            "duplicate_suppression_count": reason_counts.get("duplicate_across_host", 0),
            "negative_feedback_suppression_count": reason_counts.get("recent_negative_feedback", 0),
        },
        "issue_readouts": {
            "github_312": {
                "host_timing_fixture": "deterministic_replay_only",
                "live_host_timing": "not_measured",
                "annoyance_feedback_policy": "replayed",
                "multi_host_duplicate_suppression": "replayed",
                "autonomous_push_forward": "not_supported",
                "closeout_eligible": False,
            }
        },
        "boundary": {
            "host_owns_permission": True,
            "host_owns_priority": True,
            "host_owns_sequencing": True,
            "host_owns_safety_policy": True,
            "aippocampus_executes_actions": False,
            "no_live_host_claim": True,
            "deterministic_replay_only": True,
        },
        "privacy": {
            "raw_source_text_serialized": False,
            "local_paths_serialized": False,
            "private_thread_ids_serialized": False,
            "credentials_serialized": False,
        },
    }


def render_text(report: Mapping[str, Any]) -> str:
    aggregate = _as_mapping(report.get("aggregate"))
    return (
        "AIppocampus agency host timing replay\n"
        f"- OK: {str(bool(report.get('ok'))).lower()}\n"
        f"- Cases: {aggregate.get('case_count', 0)}\n"
        f"- Decisions: {json.dumps(aggregate.get('decision_counts') or {}, sort_keys=True)}\n"
        "- Boundary: deterministic replay only; host owns permission and execution.\n"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run public-safe agency-ticket host timing replay fixture."
    )
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args(argv)
    report = fixture_host_timing_replay()
    if args.json_output:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render_text(report), end="")
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
