"""Trace-derived concept-graph ingress candidates.

Trace and semantic-cue rows are not graph truth by themselves. This owner keeps
their admission policy fail-closed before the contribution ledger materializes
them into the read model.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from aippocampus_runtime.source.agent_trace_admission import (
    TRAINING_SIGNAL_KIND,
    behavior_training_signal_from_trace,
)

TRACE_DERIVED_GRAPH_SOURCE_FAMILY = "trace_derived_training_signal"
SEMANTIC_CUE_KIND = "aippocampus_semantic_cue"


def _semantic_cue_source_digest(row: dict[str, Any]) -> str:
    refs = [
        {
            "thread_key": str(ref.get("thread_key") or "")[:120],
            "message_id": str(ref.get("message_id") or "")[:80],
            "turn_id": str(ref.get("turn_id") or "")[:80],
            "line": ref.get("line") or ref.get("source_line"),
        }
        for ref in row.get("source_refs") or []
        if isinstance(ref, dict)
    ][:8]
    if not refs:
        return ""
    material = json.dumps(refs, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:20]


def _semantic_cue_graph_candidate(row: dict[str, Any]) -> dict[str, Any] | None:
    status_value = str(row.get("status") or "").casefold()
    source_refs = [ref for ref in row.get("source_refs") or [] if isinstance(ref, dict)]
    source_count = len(source_refs)
    admission = str(row.get("trace_admission_level") or "").casefold()
    missing_admission = not admission
    source_admitted = admission in {"reopenable_route", "bounded_evidence_after_open"}
    if status_value == "active" and source_count and source_admitted:
        status = "verified"
        active = True
        lifecycle_reason = "cue_alias_source_open_promoted"
    elif status_value == "active" and source_count:
        status = "staging"
        active = False
        lifecycle_reason = (
            "missing_trace_admission_metadata"
            if missing_admission
            else "cue_alias_waiting_trace_admission"
        )
    elif status_value == "suppressed_hard_negative":
        status = "parked"
        active = False
        lifecycle_reason = "cue_alias_hard_negative_demotion"
    elif status_value in {"parked_recheck", "expired_recheck"}:
        status = "parked"
        active = False
        lifecycle_reason = "cue_alias_waiting_recheck"
    elif source_count:
        status = "staging"
        active = False
        lifecycle_reason = "cue_alias_waiting_repeat_source_open"
    else:
        return None
    return {
        "kind": "aippocampus_trace_derived_graph_candidate",
        "source_family": TRACE_DERIVED_GRAPH_SOURCE_FAMILY,
        "signal_id": row.get("cue_id"),
        "training_role": row.get("training_role")
        or ("positive_demo" if source_admitted else "replay_sample"),
        "admission_level": admission or "operator_only",
        "missing_trace_admission": missing_admission,
        "edge_type": "cue_alias_for_route",
        "status": status,
        "active_graph_edge": active,
        "lifecycle_reason": lifecycle_reason,
        "source_ref_count": source_count,
        "source_ref_digest": _semantic_cue_source_digest(row),
        "candidate_lifecycle_state": row.get("candidate_lifecycle_state"),
        "learning_priority": row.get("learning_priority") or {},
        "claim_boundary": "cue_alias_graph_candidate_not_source_truth",
    }


def trace_derived_graph_contribution_candidates(
    rows: list[dict[str, Any]] | tuple[dict[str, Any], ...],
) -> list[dict[str, Any]]:
    """Project admitted trace/training rows into typed graph ingress candidates."""

    candidates: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if row.get("kind") == SEMANTIC_CUE_KIND:
            candidate = _semantic_cue_graph_candidate(row)
            if candidate:
                candidates.append(candidate)
            continue
        signal = (
            row
            if row.get("kind") == TRAINING_SIGNAL_KIND
            else behavior_training_signal_from_trace(row)
        )
        role = str(signal.get("training_role") or "none")
        admission = str(signal.get("admission_level") or "operator_only")
        source_count = int(signal.get("source_ref_count") or 0)
        if admission in {"ignore", "operator_only"} and role != "hard_negative":
            continue
        if role == "positive_demo":
            edge_type = "trace_positive_reopen"
            status = "verified" if source_count else "staging"
            lifecycle_reason = (
                "trace_positive_source_open"
                if source_count
                else "trace_positive_waiting_source"
            )
            active = bool(source_count)
        elif role == "hard_negative":
            edge_type = "trace_rejected_route"
            status = "parked"
            lifecycle_reason = "trace_hard_negative_demotion"
            active = False
        elif role == "process_supervision":
            edge_type = "trace_process_supervision"
            status = "staging"
            lifecycle_reason = "trace_process_waiting_quality_gate"
            active = False
        elif role == "replay_sample":
            edge_type = "trace_replay_sample"
            status = "eval_only"
            lifecycle_reason = "trace_replay_not_active_graph_evidence"
            active = False
        elif role == "hindsight_relabel":
            edge_type = "trace_hindsight_relabel"
            status = "staging"
            lifecycle_reason = "trace_hindsight_requires_verifier"
            active = False
        else:
            continue
        candidates.append(
            {
                "kind": "aippocampus_trace_derived_graph_candidate",
                "source_family": TRACE_DERIVED_GRAPH_SOURCE_FAMILY,
                "signal_id": signal.get("signal_id"),
                "training_role": role,
                "admission_level": admission,
                "edge_type": edge_type,
                "status": status,
                "active_graph_edge": active,
                "lifecycle_reason": lifecycle_reason,
                "source_ref_count": source_count,
                "source_ref_digest": signal.get("source_ref_digest") or "",
                "candidate_lifecycle_state": signal.get("candidate_lifecycle_state"),
                "learning_priority": signal.get("learning_priority") or {},
                "claim_boundary": "trace_graph_candidate_not_source_truth",
            }
        )
    return candidates
