#!/usr/bin/env python3
"""Host-side consumption contract for coding continuity tickets.

AIppocampus emits source-backed coding tickets. A Codeksei-style host decides
whether a ticket becomes silence, backstage prep, a nudge, a warning, or an
offer. This helper is intentionally a simulator/contract fixture, not an
executive shell: it never grants permission, sequences work, or executes tools.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from aippocampus_runtime.source.io_kernel import load_json_dict, load_jsonl_dict_rows

SCHEMA_VERSION = 1

TICKET_KIND = "aippocampus_coding_continuity_ticket"
CONTRACT_KIND = "aippocampus_coding_ticket_host_contract"
DECISION_KIND = "aippocampus_coding_ticket_host_decision"
TUNING_KIND = "aippocampus_coding_ticket_activation_tuning"

REQUIRED_AI_FIELDS = (
    "ticket_id",
    "trigger",
    "intervention_level",
    "relevant_decisions",
    "proposed_use",
    "evidence_refs",
    "source_thickness",
    "derived_assessment",
    "expires_at",
    "annoyance_risk",
    "preconditions",
    "outcome_feedback_expected",
)
CORE_AI_FIELDS = (
    "ticket_id",
    "proposed_use",
    "evidence_refs",
    "source_thickness",
    "derived_assessment",
)
HOST_RUNTIME_INPUTS = (
    "host_present",
    "source_visible",
    "preconditions_satisfied",
    "attention_budget",
    "recent_feedback",
)
HOST_DECISION_FIELDS = (
    "visibility",
    "host_action",
    "user_visible",
    "requires_user_confirmation",
    "delivery_timing",
    "permission",
    "priority",
    "sequence",
    "safety",
)
VISIBILITIES = (
    "silent_tuning",
    "backstage_prep",
    "light_nudge",
    "warning",
    "offer_next_step",
    "stay_silent",
)
SAFE_THIN_SOURCE_USES = {"ask", "refresh_sources"}
FEEDBACK_OUTCOMES = ("accepted", "ignored", "dismissed", "corrected", "tool_success", "tool_failure")
SUPPRESSIVE_FEEDBACK_OUTCOMES = {"ignored", "dismissed", "corrected"}
DUPLICATE_DELIVERY_OUTCOMES = {"already_delivered", "delivered"}


def _list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if value in {None, ""}:
        return []
    return [value]


def _strings(value: Any, *, limit: int = 12) -> list[str]:
    return [str(item) for item in _list(value) if str(item or "").strip()][:limit]


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _source_refs(ticket: Mapping[str, Any]) -> list[dict[str, Any]]:
    derived = _mapping(ticket.get("derived_assessment"))
    raw_refs = (
        ticket.get("evidence_refs")
        or ticket.get("basis_refs")
        or derived.get("basis_refs")
        or derived.get("evidence_refs")
        or []
    )
    return [dict(ref) for ref in _list(raw_refs) if isinstance(ref, Mapping)][:12]


def _source_thickness(ticket: Mapping[str, Any], refs: Sequence[Mapping[str, Any]]) -> str:
    explicit = str(ticket.get("source_thickness") or "")
    if explicit in {"thin", "usable", "strong"}:
        return explicit
    if len(refs) >= 3:
        return "strong"
    if refs:
        return "usable"
    return "thin"


def _annoyance_risk(ticket: Mapping[str, Any]) -> str:
    explicit = str(ticket.get("annoyance_risk") or "")
    if explicit in {"low", "medium", "high"}:
        return explicit
    proposed_use = str(ticket.get("proposed_use") or "")
    return "high" if proposed_use == "warn" else "medium"


def _feedback_expectations(ticket: Mapping[str, Any]) -> list[str]:
    raw = ticket.get("outcome_feedback_expected") or ticket.get("feedback_expectations") or FEEDBACK_OUTCOMES
    values = _strings(raw, limit=12)
    return values or list(FEEDBACK_OUTCOMES)


def normalize_ticket(ticket: Mapping[str, Any]) -> dict[str, Any]:
    refs = _source_refs(ticket)
    derived = _mapping(ticket.get("derived_assessment"))
    return {
        "kind": str(ticket.get("kind") or ""),
        "ticket_id": str(ticket.get("ticket_id") or ""),
        "trigger": str(ticket.get("trigger") or ""),
        "intervention_level": str(ticket.get("intervention_level") or "backstage_only"),
        "relevant_decisions": _strings(ticket.get("relevant_decisions")),
        "proposed_use": str(ticket.get("proposed_use") or "prepare_context"),
        "evidence_refs": refs,
        "source_thickness": _source_thickness(ticket, refs),
        "derived_assessment": derived,
        "expires_at": str(ticket.get("expires_at") or "task_or_topic_epoch_end"),
        "annoyance_risk": _annoyance_risk(ticket),
        "preconditions": _strings(ticket.get("preconditions"), limit=8),
        "feedback_expectations": _feedback_expectations(ticket),
        "diagnostics": _mapping(ticket.get("diagnostics")),
        "summary": str(ticket.get("summary") or ""),
    }


def validate_ticket_contract(ticket: Mapping[str, Any]) -> dict[str, Any]:
    missing_required = []
    for field in REQUIRED_AI_FIELDS:
        if field == "outcome_feedback_expected":
            if not (ticket.get("outcome_feedback_expected") or ticket.get("feedback_expectations")):
                missing_required.append(field)
            continue
        if field == "evidence_refs":
            if not _source_refs(ticket):
                missing_required.append(field)
            continue
        value = ticket.get(field)
        if value is None or value == "" or value == () or value == []:
            missing_required.append(field)

    missing_core = [field for field in CORE_AI_FIELDS if field in missing_required]
    return {
        "ok": not missing_core,
        "missing_required_ai_fields": missing_required,
        "missing_core_ai_fields": missing_core,
        "compatible_ticket_kind": ticket.get("kind") == TICKET_KIND,
    }


def describe_host_contract(ticket: Mapping[str, Any] | None = None) -> dict[str, Any]:
    validation = validate_ticket_contract(ticket or {}) if ticket is not None else {}
    normalized = normalize_ticket(ticket or {}) if ticket is not None else {}
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": CONTRACT_KIND,
        "ai_emits": {
            "ticket_kind": TICKET_KIND,
            "required_fields": list(REQUIRED_AI_FIELDS),
            "boundary": "source_backed_proposal_not_permission_or_execution",
        },
        "host_supplies": {
            "runtime_inputs": list(HOST_RUNTIME_INPUTS),
            "source_visible": "computed by host from current context, not asserted by storage",
        },
        "host_decides": {
            "visibility_levels": list(VISIBILITIES),
            "fields": list(HOST_DECISION_FIELDS),
            "owns_permission_priority_sequence_and_safety": True,
        },
        "feedback_policy": {
            "feedback_tunes_activation": True,
            "feedback_is_not_source_truth": True,
            "forbidden_mutations": [
                "source_fact_rewrite",
                "derived_assessment_rewrite",
                "source_ref_rewrite",
            ],
        },
        "foreground_consumption": {
            "default_lane": "host_mediated_foreground_or_backstage",
            "card_kind": "coding_continuity_lane_card",
            "foreground_agent_uses": "compact lane card only; detailed diagnostics stay backstage",
            "backstage_route": "route_usable_guidance_through_action_hints_or_recall",
        },
        "validation": validation,
        "normalized_ticket": normalized,
    }


def _decision_action(proposed_use: str, level: str) -> str:
    if proposed_use == "warn" or level == "warning":
        return "warn_route"
    if proposed_use == "ask":
        return "ask_user"
    if proposed_use == "refresh_sources":
        return "refresh_sources"
    if proposed_use == "remind":
        return "nudge_with_source_summary"
    if level == "offer_next_step":
        return "offer_next_step"
    if level == "silent":
        return "tune_silently"
    return "prepare_context"


def _visibility_for(normalized: Mapping[str, Any]) -> str:
    level = str(normalized.get("intervention_level") or "")
    proposed_use = str(normalized.get("proposed_use") or "")
    thickness = str(normalized.get("source_thickness") or "thin")
    if level == "silent":
        return "silent_tuning"
    if proposed_use == "refresh_sources":
        return "backstage_prep"
    if level == "backstage_only" or proposed_use == "prepare_context":
        return "backstage_prep"
    if proposed_use == "ask":
        return "light_nudge"
    if proposed_use == "warn" or level == "warning":
        return "warning"
    if level == "offer_next_step":
        return "offer_next_step"
    if level == "light_nudge" or proposed_use == "remind":
        return "light_nudge"
    if thickness == "thin":
        return "backstage_prep"
    return "backstage_prep"


def _silent_decision(
    normalized: Mapping[str, Any],
    *,
    reasons: Sequence[str],
    safe_degradation: str = "",
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": DECISION_KIND,
        "ticket_id": normalized.get("ticket_id"),
        "visibility": "stay_silent",
        "host_action": "no_action",
        "user_visible": False,
        "requires_user_confirmation": False,
        "delivery_timing": "never_for_this_context",
        "suppression_reasons": list(reasons),
        "safe_degradation": safe_degradation,
        "host_boundary": _host_boundary(),
    }


def _host_boundary() -> dict[str, bool]:
    return {
        "aippocampus_proposes_only": True,
        "host_decides_permission": True,
        "host_decides_priority": True,
        "host_decides_sequence": True,
        "host_decides_safety": True,
    }


def _topic_epoch(value: Mapping[str, Any]) -> str:
    return str(value.get("topic_epoch") or value.get("expires_at") or "task_or_topic_epoch_end")


def _feedback_matches_ticket(normalized: Mapping[str, Any], row: Mapping[str, Any]) -> bool:
    ticket_id = str(normalized.get("ticket_id") or "")
    if not ticket_id or str(row.get("ticket_id") or "") != ticket_id:
        return False
    row_epoch = _topic_epoch(row)
    ticket_epoch = _topic_epoch(normalized)
    return row_epoch == ticket_epoch or row_epoch in {"", "task_or_topic_epoch_end"}


def _recent_feedback_suppression(
    normalized: Mapping[str, Any], recent_feedback: Sequence[Mapping[str, Any]]
) -> tuple[str, str] | None:
    for row in recent_feedback:
        if not isinstance(row, Mapping) or not _feedback_matches_ticket(normalized, row):
            continue
        outcome = str(row.get("outcome") or "").casefold()
        delivery_state = str(row.get("delivery_state") or row.get("delivery") or "").casefold()
        event = str(row.get("event") or "").casefold()
        if outcome in SUPPRESSIVE_FEEDBACK_OUTCOMES:
            return "recent_feedback_suppressed", "recent_feedback"
        if (
            outcome in DUPLICATE_DELIVERY_OUTCOMES
            or delivery_state == "delivered"
            or event == "delivered"
        ):
            return "duplicate_ticket_suppressed", "duplicate_delivery"
    return None


def host_decision_for_ticket(
    ticket: Mapping[str, Any],
    *,
    host_present: bool = True,
    source_visible: bool = False,
    preconditions_satisfied: bool = True,
    attention_budget: str = "normal",
    recent_feedback: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    normalized = normalize_ticket(ticket)
    validation = validate_ticket_contract(ticket)
    if not host_present:
        return _silent_decision(normalized, reasons=["no_host_present"], safe_degradation="no_host")
    if validation["missing_core_ai_fields"]:
        return _silent_decision(normalized, reasons=["missing_core_ai_fields"], safe_degradation="invalid_ticket")
    if source_visible:
        return _silent_decision(normalized, reasons=["source_already_visible"])
    if not preconditions_satisfied:
        return _silent_decision(normalized, reasons=["preconditions_not_satisfied"])
    if attention_budget == "none":
        return _silent_decision(normalized, reasons=["no_attention_budget"])
    feedback_suppression = _recent_feedback_suppression(normalized, recent_feedback or [])
    if feedback_suppression:
        reason, degradation = feedback_suppression
        return _silent_decision(normalized, reasons=[reason], safe_degradation=degradation)

    level = str(normalized.get("intervention_level") or "")
    proposed_use = str(normalized.get("proposed_use") or "")
    thickness = str(normalized.get("source_thickness") or "thin")
    annoyance_risk = str(normalized.get("annoyance_risk") or "medium")
    if thickness == "thin" and proposed_use not in SAFE_THIN_SOURCE_USES:
        return _silent_decision(normalized, reasons=["thin_source_unsafe_for_foreground"])
    if annoyance_risk == "high" and proposed_use != "warn":
        return _silent_decision(normalized, reasons=["annoyance_risk_high"])

    visibility = _visibility_for(normalized)
    user_visible = visibility in {"light_nudge", "warning", "offer_next_step"}
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": DECISION_KIND,
        "ticket_id": normalized.get("ticket_id"),
        "visibility": visibility,
        "host_action": _decision_action(proposed_use, level),
        "user_visible": user_visible,
        "requires_user_confirmation": bool(user_visible or proposed_use in {"ask", "warn"}),
        "delivery_timing": "host_selected",
        "suppression_reasons": [],
        "safe_degradation": "",
        "normalized_ticket": normalized,
        "contract_validation": validation,
        "host_boundary": _host_boundary(),
    }


def coding_continuity_lane_card(
    ticket: Mapping[str, Any],
    decision: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    normalized = normalize_ticket(ticket)
    host_decision = dict(decision or host_decision_for_ticket(ticket))
    visibility = str(host_decision.get("visibility") or "stay_silent")
    foreground = visibility in {"light_nudge", "warning", "offer_next_step"}
    return {
        "kind": "coding_continuity_lane_card",
        "schema_version": SCHEMA_VERSION,
        "ticket_id": normalized.get("ticket_id"),
        "lane": "foreground" if foreground else "backstage",
        "foreground_visibility": visibility,
        "user_visible": bool(host_decision.get("user_visible")),
        "next_action": host_decision.get("host_action") or "no_action",
        "agent_consumption": (
            "compact_foreground_card"
            if foreground
            else "route_usable_guidance_through_action_hints_or_recall"
        ),
        "relevant_decision_count": len(normalized.get("relevant_decisions") or []),
        "do_not_repeat": _strings(ticket.get("do_not_repeat"), limit=4),
        "source_thickness": normalized.get("source_thickness"),
        "evidence_ref_count": len(normalized.get("evidence_refs") or []),
        "source_boundary": "source_backed_proposal_not_permission_or_execution",
        "source_reopen_required_before_claim": True,
        "host_decides_permission": True,
        "host_decides_priority": True,
        "host_decides_sequence": True,
        "claim_permission": "navigation_only_not_fact",
    }


def simulate_host_consumption(
    tickets: Sequence[Mapping[str, Any]],
    *,
    host_present: bool = True,
    source_visible_ticket_ids: Sequence[str] | None = None,
    recent_feedback: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    visible_ids = {str(item) for item in source_visible_ticket_ids or []}
    decisions = [
        host_decision_for_ticket(
            ticket,
            host_present=host_present,
            source_visible=str(ticket.get("ticket_id") or "") in visible_ids,
            recent_feedback=recent_feedback,
        )
        for ticket in tickets
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "aippocampus_coding_ticket_host_simulation",
        "decision_count": len(decisions),
        "decisions": decisions,
        "contract": describe_host_contract(),
    }


def _feedback_rows_for_ticket(
    ticket_id: str,
    feedback_rows: Iterable[Mapping[str, Any]],
) -> list[Mapping[str, Any]]:
    return [row for row in feedback_rows if str(row.get("ticket_id") or "") == ticket_id]


def _activation_tuning(outcomes: Sequence[str]) -> str:
    if any(item in {"dismissed", "corrected"} for item in outcomes):
        return "quieter"
    if any(item == "tool_failure" for item in outcomes):
        return "refresh_before_surface"
    if any(item == "ignored" for item in outcomes):
        return "slightly_quieter"
    if any(item in {"accepted", "tool_success"} for item in outcomes):
        return "same_level_allowed"
    return "no_change"


def tune_activation_from_feedback(
    tickets: Sequence[Mapping[str, Any]],
    feedback_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    adjustments: list[dict[str, Any]] = []
    for ticket in tickets:
        ticket_id = str(ticket.get("ticket_id") or "")
        rows = _feedback_rows_for_ticket(ticket_id, feedback_rows)
        if not rows:
            continue
        outcomes = [str(row.get("outcome") or "") for row in rows if str(row.get("outcome") or "") in FEEDBACK_OUTCOMES]
        tuning = _activation_tuning(outcomes)
        if tuning == "no_change":
            continue
        adjustments.append(
            {
                "ticket_id": ticket_id,
                "activation_tuning": tuning,
                "outcomes": outcomes,
                # Feedback changes future activation pressure only. It must not
                # rewrite source facts or current-validity weather: a dismissal
                # can mean "too loud now", not "the old decision never happened".
                "mutates": ["future_visibility_pressure"],
                "does_not_mutate": [
                    "source_refs",
                    "decision_event",
                    "derived_assessment",
                ],
            }
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": TUNING_KIND,
        "adjustments": adjustments,
        "source_fact_mutation_allowed": False,
        "forbidden_mutations": [
            "source_fact_rewrite",
            "derived_assessment_rewrite",
            "source_ref_rewrite",
        ],
    }


def _load_contract_input(path: Path) -> Any:
    if path.suffix == ".jsonl":
        return load_jsonl_dict_rows(path).rows
    return load_json_dict(path, missing_is_loss=True).data


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", help="JSON or JSONL coding continuity tickets.")
    parser.add_argument("--contract", action="store_true", help="Print the host contract schema.")
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args()

    if args.contract:
        payload = describe_host_contract()
    elif args.input:
        raw = _load_contract_input(Path(args.input))
        tickets = raw if isinstance(raw, list) else [raw]
        payload = simulate_host_consumption([item for item in tickets if isinstance(item, Mapping)])
    else:
        payload = describe_host_contract()

    if args.json_output or args.contract or args.input:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
