"""Admission contract for trace-derived navigation rows.

Agent traces can be excellent navigation material, but they are not source
truth. This module keeps the shared vocabulary executable so future closeout,
receipt, route-note, graph, and training-signal owners do not each invent a
slightly different authority story.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from collections.abc import Iterable, Mapping
from typing import Any

from aippocampus_runtime.privacy import redact_private_paths, redact_sensitive_values

ADMISSION_LEVELS = (
    "ignore",
    "operator_only",
    "navigation_candidate",
    "reopenable_route",
    "bounded_evidence_after_open",
)
TRAINING_ROLES = (
    "none",
    "positive_demo",
    "hard_negative",
    "process_supervision",
    "replay_sample",
    "hindsight_relabel",
)

RAW_TRACE_FAMILIES = {
    "raw_stdout",
    "raw_stderr",
    "full_command_args",
    "raw_tool_output",
    "selector_cache_internal",
    "policy_gate_matrix",
}
IGNORE_FAMILIES = {"routine_commentary", "chain_of_thought_like_process"}
SOURCE_OPEN_FAMILIES = {
    "successful_source_open_receipt",
    "successful_recall_deepen_source_open",
}
CHECK_RECEIPT_FAMILIES = {"successful_test_check_event", "successful_tool_check_receipt"}
ROUTE_NOTE_FAMILIES = {"joined_route_note", "agent_trajectory"}
FINAL_CLOSEOUT_FAMILIES = {"final_answer_closeout", "assistant_final_answer_closeout"}
REPO_BREADCRUMB_FAMILIES = {"repo_breadcrumb", "safe_repo_relative_breadcrumb"}

SECRET_OR_PATH_RE = re.compile(
    r"(?i)(api[_-]?key|secret|token|password|passwd|bearer|authorization|"
    r"sk-[a-z0-9]|[a-z]:[\\/]|/(?:users|home|tmp|private|var)/)"
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _family(row: Mapping[str, Any]) -> str:
    return _text(
        row.get("trace_family")
        or row.get("family")
        or row.get("event_kind")
        or row.get("kind")
    ).casefold()


def _has_refs(row: Mapping[str, Any], key: str = "source_refs") -> bool:
    refs = row.get(key)
    return isinstance(refs, list) and any(isinstance(item, Mapping) for item in refs)


def _has_receipt(row: Mapping[str, Any]) -> bool:
    return _has_refs(row, "receipt_refs") or bool(row.get("receipt_state") == "matched")


def _success(row: Mapping[str, Any]) -> bool:
    status = _text(row.get("status") or row.get("outcome")).casefold()
    if status in {"ok", "pass", "passed", "success", "succeeded"}:
        return True
    try:
        return int(row.get("exit_code")) == 0
    except (TypeError, ValueError):
        return False


def _safe_row_blob(row: Mapping[str, Any]) -> str:
    redacted = redact_sensitive_values(redact_private_paths(dict(row)))
    return json.dumps(redacted, ensure_ascii=False, sort_keys=True, default=str)


def _contains_private_shape(row: Mapping[str, Any]) -> bool:
    return bool(SECRET_OR_PATH_RE.search(_safe_row_blob(row)))


def _candidate_lifecycle_for(admission_level: str) -> str:
    return {
        "ignore": "cannot_enter_candidate_funnel",
        "operator_only": "cannot_enter_candidate_funnel",
        "navigation_candidate": "draft_candidate_staging",
        "reopenable_route": "actionable_reopenable_route",
        "bounded_evidence_after_open": "source_open_claim_ready_within_scope",
    }[admission_level]


def _graph_projection_for(admission_level: str) -> str:
    return {
        "ignore": "never_graph",
        "operator_only": "operator_report_only",
        "navigation_candidate": "graph_staging_only",
        "reopenable_route": "typed_graph_contribution_after_owner_gate",
        "bounded_evidence_after_open": "typed_graph_contribution_after_source_open",
    }[admission_level]


def _data_card(
    *,
    admission_level: str,
    training_role: str,
    authority_join: str,
    source_state: str,
) -> dict[str, Any]:
    return {
        "intended_use": "navigation_reopen_or_training_signal",
        "not_for": "source_truth_or_issue_closeout_without_reopen",
        "freshness": "recheck_on_stale_conflict_or_negative_feedback",
        "authority_after_open": "bounded_to_opened_source_scope",
        "training_role": training_role,
        "source_state": source_state,
        "authority_join": authority_join,
        "admission_level": admission_level,
        "candidate_lifecycle_state": _candidate_lifecycle_for(admission_level),
        "graph_projection": _graph_projection_for(admission_level),
    }


def classify_trace_row(row: Mapping[str, Any]) -> dict[str, Any]:
    family = _family(row)
    admission_level = "operator_only"
    authority_join = "trace_operator_only"
    training_role = "none"
    source_state = "missing_source_or_receipt"
    reason = "default_operator_only"

    if family in IGNORE_FAMILIES:
        admission_level = "ignore"
        authority_join = "ignored_routine_trace"
        reason = "routine_or_process_prose"
    elif family in RAW_TRACE_FAMILIES or _contains_private_shape(row):
        admission_level = "operator_only"
        authority_join = "raw_or_private_trace_operator_only"
        reason = "raw_or_private_trace_material"
    elif family in FINAL_CLOSEOUT_FAMILIES:
        if _has_refs(row) and _has_receipt(row):
            admission_level = "reopenable_route"
            authority_join = "reported_and_receipted_navigation"
            training_role = "process_supervision"
            source_state = "source_refs_and_receipts"
            reason = "closeout_joined_to_receipt"
        elif _has_refs(row):
            admission_level = "navigation_candidate"
            authority_join = "agent_reported_navigation_only"
            training_role = "replay_sample"
            source_state = "source_refs_without_receipt"
            reason = "closeout_self_report_only"
    elif family in SOURCE_OPEN_FAMILIES and _has_refs(row):
        admission_level = "bounded_evidence_after_open"
        authority_join = "behavior_receipt_navigation"
        training_role = "positive_demo"
        source_state = "source_open_receipt"
        reason = "source_open_anchor_receipt"
    elif family in CHECK_RECEIPT_FAMILIES and _success(row) and _has_refs(row):
        admission_level = "reopenable_route"
        authority_join = "behavior_receipt_navigation"
        training_role = "process_supervision"
        source_state = "source_refs_and_success_receipt"
        reason = "successful_check_receipt_with_source_ref"
    elif family in ROUTE_NOTE_FAMILIES and _has_refs(row) and _has_refs(row, "joined_evidence_refs"):
        admission_level = "reopenable_route"
        authority_join = "joined_process_navigation"
        training_role = "process_supervision"
        source_state = "joined_source_refs"
        reason = "route_note_joined_to_source"
    elif family in REPO_BREADCRUMB_FAMILIES and row.get("safe_repo_relative") is True:
        admission_level = "navigation_candidate"
        authority_join = "repo_breadcrumb_navigation_only"
        training_role = "replay_sample"
        source_state = "safe_repo_relative_breadcrumb"
        reason = "safe_repo_relative_navigation"

    return {
        "trace_id": _text(row.get("trace_id") or row.get("id")),
        "trace_family": family or "unknown",
        "admission_level": admission_level,
        "authority_join": authority_join,
        "training_role": training_role,
        "source_state": source_state,
        "reason": reason,
        "candidate_lifecycle_state": _candidate_lifecycle_for(admission_level),
        "graph_projection": _graph_projection_for(admission_level),
        "micro_data_card": _data_card(
            admission_level=admission_level,
            training_role=training_role,
            authority_join=authority_join,
            source_state=source_state,
        ),
    }


def _priority(item: Mapping[str, Any]) -> int:
    return {
        "bounded_evidence_after_open": 0,
        "reopenable_route": 1,
        "navigation_candidate": 2,
        "operator_only": 3,
        "ignore": 4,
    }.get(str(item.get("admission_level") or ""), 9)


def project_trace_admission(
    rows: Iterable[Mapping[str, Any]],
    *,
    detail: str = "compact",
) -> dict[str, Any]:
    admitted = [classify_trace_row(row) for row in rows]
    counts = Counter(item["admission_level"] for item in admitted)
    training_counts = Counter(item["training_role"] for item in admitted)
    graph_counts = Counter(item["graph_projection"] for item in admitted)
    actionable = [item for item in admitted if _priority(item) <= 2]
    actionable.sort(key=_priority)

    if detail in {"detail", "full", "operator"}:
        return {
            "kind": "aippocampus_agent_trace_admission",
            "detail": detail,
            "status": "ok",
            "admission_counts": dict(counts),
            "training_role_counts": dict(training_counts),
            "graph_projection_counts": dict(graph_counts),
            "candidate_lifecycle_counts": dict(
                Counter(item["candidate_lifecycle_state"] for item in admitted)
            ),
            "operator_only_count": counts.get("operator_only", 0),
            "ignored_count": counts.get("ignore", 0),
        }

    primary = actionable[0] if actionable else None
    if not primary:
        return {
            "kind": "aippocampus_agent_trace_admission",
            "detail": "compact",
            "status": "diagnostic_only",
            "decision": "no_foreground_trace_route",
            "claim_boundary": "trace_rows_not_source_truth",
        }
    return {
        "kind": "aippocampus_agent_trace_admission",
        "detail": "compact",
        "status": "route_available",
        "decision": "use_trace_route_as_navigation_only",
        "foreground_action": {
            "id": "open_trace_route_source",
            "tool_name": "agent_deepen",
            "mutation_risk": "read_only",
            "claim_boundary": "source_reopen_required_before_claim",
            "why": "Trace material is admitted only as navigation; reopen source before using it.",
        },
        "primary_route": {
            "admission_level": primary["admission_level"],
            "authority_join": primary["authority_join"],
            "training_role": primary["training_role"],
            "candidate_lifecycle_state": primary["candidate_lifecycle_state"],
            "claim_boundary": "source_reopen_required_before_claim",
        },
        "claim_boundary": "trace_navigation_only_until_source_open",
    }


__all__ = [
    "ADMISSION_LEVELS",
    "TRAINING_ROLES",
    "classify_trace_row",
    "project_trace_admission",
]
