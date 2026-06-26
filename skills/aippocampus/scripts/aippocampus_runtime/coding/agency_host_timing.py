#!/usr/bin/env python3
"""Host-faithful replay for agency-ticket surface timing.

This helper pressure-tests when a named host surface should show, hold, or
suppress AIppocampus agency tickets. It is an evidence surface only: the host
still owns permission, priority, sequencing, safety, and execution.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from aippocampus_runtime import core
from aippocampus_runtime.coding import agency_affordance as agency

REPLAY_KIND = "aippocampus_agency_host_timing_replay"
SURFACE_EVENT_KIND = "aippocampus_agency_ticket_surface_event"
FEEDBACK_LEDGER_KIND = "aippocampus_agency_host_feedback_ledger_event"
SCHEMA_VERSION = 2
HOST_SURFACE_ID = "codex-desktop-hidden-route-lifecycle"
HOST_SURFACE_LABEL = "Codex Desktop hidden-route lifecycle"

DECISION_SHOW = "show"
DECISION_HOLD = "hold"
DECISION_SUPPRESS = "suppress"
ACTIONABLE_PHASES = {"planning", "pre_action", "before_tool", "resume"}
NEGATIVE_FEEDBACK = {"dismissed", "ignored", "corrected", "tool_failure"}
USEFULNESS_VALUES = {"unknown", "useful", "not_useful", "prevented_repeat"}
ANNOYANCE_VALUES = {"unknown", "low", "medium", "high"}


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


def codex_desktop_hidden_route_surface() -> dict[str, Any]:
    return {
        "surface_id": HOST_SURFACE_ID,
        "label": HOST_SURFACE_LABEL,
        "host": "codex-desktop",
        "timing_model": "hidden_route_lifecycle",
        "host_supplied_runtime_inputs": [
            "task_phase",
            "current_user_action",
            "visible_context_refs",
            "surface_history",
            "feedback_history",
        ],
        "actionable_phases": sorted(ACTIONABLE_PHASES),
        "held_phases": ["post_answer"],
        "claim_boundary": {
            "host_faithful_replay": True,
            "live_delivery_measured": False,
            "user_visible_usefulness_measured": False,
        },
    }


def host_duplicate_key(ticket: Mapping[str, Any]) -> str:
    source_fp = str(ticket.get("source_ref_fingerprint") or "")
    if not source_fp:
        source_fp = agency.source_ref_fingerprint(_source_refs(ticket.get("source_refs")))
    scope = core.dict_or_empty(ticket.get("scope"))
    return core.stable_json_id(
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
        "host_surface_id": HOST_SURFACE_ID,
        "host_surface_label": HOST_SURFACE_LABEL,
        "duplicate_key": host_duplicate_key(ticket),
        "source_ref_fingerprint": source_fp,
        "intervention_level": ticket.get("intervention_level"),
        "outcome": outcome,
    }


def host_feedback_ledger_event(
    ticket: Mapping[str, Any],
    *,
    host_id: str,
    topic_epoch: str,
    outcome: str,
    usefulness: str = "unknown",
    annoyance: str = "unknown",
    correction_refs: Sequence[Mapping[str, Any]] | None = None,
    operator_note: str = "",
) -> dict[str, Any]:
    """Build a public-safe feedback row for host timing calibration.

    Feedback changes later activation pressure; it must not rewrite source facts
    or store raw user/operator prose. The optional operator note exists so host
    adapters can accept richer local input while this public row keeps only
    bounded enum signals and source fingerprints.
    """

    del operator_note
    if outcome not in agency.OUTCOME_FEEDBACK:
        raise ValueError(f"outcome must be one of {', '.join(agency.OUTCOME_FEEDBACK)}")
    if usefulness not in USEFULNESS_VALUES:
        raise ValueError(f"usefulness must be one of {', '.join(sorted(USEFULNESS_VALUES))}")
    if annoyance not in ANNOYANCE_VALUES:
        raise ValueError(f"annoyance must be one of {', '.join(sorted(ANNOYANCE_VALUES))}")
    source_fp = str(ticket.get("source_ref_fingerprint") or "")
    if not source_fp:
        source_fp = agency.source_ref_fingerprint(_source_refs(ticket.get("source_refs")))
    correction_fp = agency.source_ref_fingerprint(correction_refs or [])
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": FEEDBACK_LEDGER_KIND,
        "created_at": agency.now_utc(),
        "ticket_id": ticket.get("ticket_id"),
        "affordance_id": ticket.get("affordance_id"),
        "topic_epoch": topic_epoch,
        "surface_host": host_id,
        "host_surface_id": HOST_SURFACE_ID,
        "host_surface_label": HOST_SURFACE_LABEL,
        "duplicate_key": host_duplicate_key(ticket),
        "source_ref_fingerprint": source_fp,
        "correction_source_ref_fingerprint": correction_fp,
        "outcome": outcome,
        "usefulness": usefulness,
        "annoyance": annoyance,
        "raw_feedback_text_stored": False,
        "feedback_changes_source_truth": False,
    }


def append_feedback_ledger_events(path: Path, rows: Sequence[Mapping[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("a", encoding="utf-8", newline="\n") as fh:
        for row in rows:
            if row.get("kind") != FEEDBACK_LEDGER_KIND:
                raise ValueError(f"unsupported agency host feedback row kind: {row.get('kind')}")
            fh.write(json.dumps(dict(row), ensure_ascii=False) + "\n")
            count += 1
    return count


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
        "duplicate_source_surface": "",
        "feedback_outcome": "",
        "host_surface_id": HOST_SURFACE_ID,
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
            "reason": "duplicate_surface_history",
            "duplicate_source_host": str(duplicate.get("surface_host") or ""),
            "duplicate_source_surface": str(duplicate.get("host_surface_id") or ""),
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
    return core.dict_or_empty((selection.get("foreground_tickets") or [{}])[0])


def fixture_host_timing_replay() -> dict[str, Any]:
    topic_epoch = "epoch-agency-host"
    affordance_map = fixture_affordance_map(topic_epoch=topic_epoch)
    ticket = _fixture_ticket(affordance_map, topic_epoch=topic_epoch)
    prior_event = host_surface_event(
        ticket,
        host_id="codex-desktop",
        topic_epoch=topic_epoch,
    )
    feedback_ledger = [
        host_feedback_ledger_event(
            ticket,
            host_id="codex-desktop",
            topic_epoch=topic_epoch,
            outcome="accepted",
            usefulness="useful",
            annoyance="low",
        ),
        host_feedback_ledger_event(
            ticket,
            host_id="codex-desktop",
            topic_epoch=topic_epoch,
            outcome="dismissed",
            usefulness="not_useful",
            annoyance="medium",
        ),
        host_feedback_ledger_event(
            ticket,
            host_id="codex-desktop",
            topic_epoch=topic_epoch,
            outcome="corrected",
            usefulness="prevented_repeat",
            annoyance="high",
            correction_refs=[fixture_source_ref(12, message_id="msg-later-correction")],
        ),
    ]
    dismissed = feedback_ledger[1]
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
            case_id="suppress_same_surface_duplicate",
            trigger="user_correction",
            topic_epoch=topic_epoch,
            host_id="codex-desktop",
            task_phase="pre_action",
            current_user_action="same_route_in_same_hidden_route_epoch",
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
    usefulness_counts = dict(sorted(Counter(str(row.get("usefulness") or "") for row in feedback_ledger).items()))
    annoyance_counts = dict(sorted(Counter(str(row.get("annoyance") or "") for row in feedback_ledger).items()))
    return {
        "kind": REPLAY_KIND,
        "schema_version": SCHEMA_VERSION,
        "ok": True,
        "host_surface": codex_desktop_hidden_route_surface(),
        "cases": cases,
        "cases_by_id": {str(case["case_id"]): case for case in cases},
        "feedback_ledger": {
            "kind": FEEDBACK_LEDGER_KIND,
            "storage_policy": "append_only_jsonl_or_host_native_equivalent",
            "public_safe_rows": feedback_ledger,
            "raw_feedback_text_stored": False,
            "feedback_changes_source_truth": False,
        },
        "aggregate": {
            "case_count": len(cases),
            "decision_counts": decision_counts,
            "reason_counts": reason_counts,
            "foreground_show_count": decision_counts.get(DECISION_SHOW, 0),
            "hold_count": decision_counts.get(DECISION_HOLD, 0),
            "suppress_count": decision_counts.get(DECISION_SUPPRESS, 0),
            "duplicate_suppression_count": reason_counts.get("duplicate_surface_history", 0),
            "negative_feedback_suppression_count": reason_counts.get("recent_negative_feedback", 0),
            "feedback_ledger_count": len(feedback_ledger),
            "usefulness_counts": usefulness_counts,
            "annoyance_counts": annoyance_counts,
            "correction_feedback_count": sum(1 for row in feedback_ledger if row.get("outcome") == "corrected"),
        },
        "issue_readouts": {
            "github_312": {
                "host_timing_fixture": "deterministic_replay_only",
                "live_host_timing": "not_measured",
                "annoyance_feedback_policy": "replayed",
                "multi_host_duplicate_suppression": "replayed",
                "autonomous_push_forward": "not_supported",
                "closeout_eligible": False,
            },
            "github_763": {
                "selected_host_surface": HOST_SURFACE_ID,
                "host_surface_timing": "host_faithful_replay",
                "show_hold_suppress_cases": "measured_in_fixture",
                "feedback_ledger": "contract_replay_public_safe",
                "deterministic_replay_evidence": "carried_forward_from_github_312",
                "live_host_timing": "not_measured",
                "user_visible_usefulness": "ledger_contract_only",
                "autonomous_push_forward": "not_supported",
                "closeout_eligible": True,
            },
        },
        "can_claim": [
            "one named Codex Desktop host surface is documented",
            "host-faithful replay covers show, hold, source-visible suppression, duplicate suppression, and recent negative feedback",
            "feedback ledger rows carry bounded usefulness, annoyance, dismissal, and correction signals without raw feedback text",
        ],
        "cannot_claim": [
            "live delivered host timing",
            "real user-visible usefulness or annoyance lift",
            "autonomous push-forward behavior",
            "cross-host production duplicate suppression",
            "source truth changes from feedback ledger rows",
        ],
        "evidence_layers": {
            "deterministic_replay": "github_312",
            "host_faithful_timing": "github_763",
            "user_visible_usefulness": "not_measured",
        },
        "boundary": {
            "host_owns_permission": True,
            "host_owns_priority": True,
            "host_owns_sequencing": True,
            "host_owns_safety_policy": True,
            "aippocampus_executes_actions": False,
            "no_live_host_claim": True,
            "host_faithful_replay_only": True,
            "deterministic_fixture": True,
        },
        "privacy": {
            "raw_source_text_serialized": False,
            "raw_feedback_text_serialized": False,
            "local_paths_serialized": False,
            "private_thread_ids_serialized": False,
            "credentials_serialized": False,
        },
    }


def render_text(report: Mapping[str, Any]) -> str:
    aggregate = core.dict_or_empty(report.get("aggregate"))
    surface = core.dict_or_empty(report.get("host_surface"))
    return (
        "AIppocampus agency host timing replay\n"
        f"- Host surface: {surface.get('label', HOST_SURFACE_LABEL)}\n"
        f"- OK: {str(bool(report.get('ok'))).lower()}\n"
        f"- Cases: {aggregate.get('case_count', 0)}\n"
        f"- Decisions: {json.dumps(aggregate.get('decision_counts') or {}, sort_keys=True)}\n"
        f"- Feedback ledger rows: {aggregate.get('feedback_ledger_count', 0)}\n"
        "- Boundary: host-faithful replay only; host owns permission and execution.\n"
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
