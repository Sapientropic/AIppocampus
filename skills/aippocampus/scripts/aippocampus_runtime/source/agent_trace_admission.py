"""Admission contract for trace-derived navigation rows.

Agent traces can be excellent navigation material, but they are not source
truth. This module keeps the shared vocabulary executable so future closeout,
receipt, route-note, graph, and training-signal owners do not each invent a
slightly different authority story.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable, Mapping
from typing import Any

from aippocampus_runtime.core import stable_json_join_id
from aippocampus_runtime.recall.feedback.vocabulary import (
    feedback_signal_is_negative,
    feedback_signal_is_positive,
    normalize_feedback_signal,
)
from aippocampus_runtime.source import agent_trace_families
from aippocampus_runtime.source.agent_trace_receipts import (
    ACCEPTED_RECEIPT_FIELDS,
    RECEIPT_FIELD_CONTRACT,
    adapt_trace_row,
    adapt_trace_rows_with_receipts,
)

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
TRAINING_SIGNAL_KIND = "aippocampus_behavior_training_signal"
SPECULATIVE_CANDIDATE_KIND = "aippocampus_speculative_navigation_candidate"
LEDGER_SCHEMA_VERSION = 1
CANDIDATE_SCHEMA_VERSION = 1

VERIFIER_OUTCOMES = (
    "source_open_hit",
    "actionable_reopenable_route",
    "wrong_route",
    "dismissed",
    "manual_search_after_route",
    "privacy_blocked",
    "stale",
    "duplicate",
    "needs_refine",
    "missed_opportunity",
)

TRACE_POSITIVE_OUTCOMES = {
    "source_open_hit",
    "actionable_reopenable_route",
    "useful_final_action",
}
TRACE_NEGATIVE_OUTCOMES = {
    "unrelated_repo_familiarity",
}
REPLAY_OUTCOMES = {"missed_opportunity", "manual_recovered", "replay_sample"}
HINDSIGHT_OUTCOMES = {"hindsight_relabel", "narrower_route_found", "failed_but_relabelable"}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _has_refs(row: Mapping[str, Any], key: str = "source_refs") -> bool:
    refs = row.get(key)
    return isinstance(refs, list) and any(isinstance(item, Mapping) for item in refs)


def _has_receipt(row: Mapping[str, Any]) -> bool:
    return _has_refs(row, "receipt_refs") or bool(row.get("receipt_state") == "matched")


def _success(row: Mapping[str, Any]) -> bool:
    status = _text(row.get("status") or row.get("outcome")).casefold()
    if status in {"ok", "pass", "passed", "success", "succeeded"}:
        return True
    exit_code = row.get("exit_code")
    if isinstance(exit_code, int):
        return exit_code == 0
    if isinstance(exit_code, str):
        try:
            return int(exit_code) == 0
        except ValueError:
            return False
    return False


def _cue_hash(cue: Any = None, row: Mapping[str, Any] | None = None) -> str:
    row = row or {}
    explicit = _text(row.get("cue_hash") or row.get("prompt_hash") or row.get("query_hash"))
    if explicit:
        return explicit[:80]
    cue_text = _text(cue or row.get("cue") or row.get("query") or row.get("prompt"))
    if not cue_text:
        return ""
    return stable_json_join_id(
        "cue",
        re.sub(r"\s+", " ", cue_text),
        ensure_ascii=False,
        default_str=False,
        length=20,
    )


def _source_ref_count(row: Mapping[str, Any]) -> int:
    refs = row.get("source_refs")
    if not isinstance(refs, list):
        return 0
    return sum(1 for ref in refs if isinstance(ref, Mapping))


def _source_ref_digest(row: Mapping[str, Any]) -> str:
    refs = row.get("source_refs")
    if not isinstance(refs, list) or not refs:
        return ""
    safe_refs = []
    for ref in refs[:8]:
        if not isinstance(ref, Mapping):
            continue
        safe_refs.append(
            {
                "message_id": _text(ref.get("message_id"))[:80],
                "turn_id": _text(ref.get("turn_id"))[:80],
                "thread_key": _text(ref.get("thread_key"))[:120],
                "line": ref.get("line") or ref.get("source_line"),
            }
        )
    return (
        stable_json_join_id("src", safe_refs, ensure_ascii=False, default_str=False, length=20)
        if safe_refs
        else ""
    )


def _training_role_from_outcome(outcome: str, fallback: str) -> str:
    folded = outcome.casefold()
    normalized = normalize_feedback_signal(folded, default=folded)
    if normalized in TRACE_POSITIVE_OUTCOMES or feedback_signal_is_positive(normalized):
        return "positive_demo"
    if normalized in TRACE_NEGATIVE_OUTCOMES or feedback_signal_is_negative(normalized):
        return "hard_negative"
    if normalized in REPLAY_OUTCOMES:
        return "replay_sample"
    if normalized in HINDSIGHT_OUTCOMES:
        return "hindsight_relabel"
    return fallback if fallback in TRAINING_ROLES else "none"


def _priority_bucket(score: int) -> str:
    if score >= 4:
        return "high_information"
    if score >= 2:
        return "medium"
    return "low"


def learning_priority_for_signal(row: Mapping[str, Any]) -> dict[str, Any]:
    """Return a public-safe replay/promotion priority for a training row.

    This is a queueing hint, not foreground ranking magic. It helps rare,
    previously missed, source-opened, multilingual, or manual-recovered cues
    get replayed before generic successes.
    """

    score = 0
    reasons: list[str] = []
    if _source_ref_count(row) or row.get("source_ref_count"):
        score += 1
        reasons.append("has_source_or_reopen_ref")
    if row.get("opened_anchor_hits") or row.get("source_open_anchor_hits"):
        score += 1
        reasons.append("source_anchor_hits")
    if row.get("previously_missed") or row.get("low_confidence_before") or row.get("manual_recovered"):
        score += 1
        reasons.append("previously_missed_or_manual_recovered")
    if row.get("multilingual") or row.get("alias_like") or row.get("non_obvious_alias"):
        score += 1
        reasons.append("multilingual_or_non_obvious_alias")
    if row.get("manual_search_reduced") or row.get("wrong_route_drag_reduced"):
        score += 1
        reasons.append("reduced_manual_or_wrong_route_drag")
    try:
        frequency = int(row.get("cue_frequency") or row.get("hit_count") or 0)
    except (TypeError, ValueError):
        frequency = 0
    if 0 < frequency <= 2:
        score += 1
        reasons.append("rare_or_low_frequency")
    if frequency > 8:
        score -= 1
        reasons.append("generic_high_frequency")
    return {
        "score": max(0, score),
        "bucket": _priority_bucket(score),
        "reason_codes": reasons[:8],
        "policy": "promotion_replay_priority_not_foreground_ranking",
    }


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
    row = adapt_trace_row(row)
    family = agent_trace_families.normalized_family(row)
    producer_family = agent_trace_families.raw_family(row)
    unknown_family = agent_trace_families.unknown_family(row)
    admission_level = "operator_only"
    authority_join = "trace_operator_only"
    training_role = "none"
    source_state = "missing_source_or_receipt"
    reason = "default_operator_only"

    if family in agent_trace_families.IGNORE_FAMILIES:
        admission_level = "ignore"
        authority_join = "ignored_routine_trace"
        reason = "routine_or_process_prose"
    elif family in agent_trace_families.RAW_TRACE_FAMILIES or (
        agent_trace_families.contains_private_shape(row)
    ):
        admission_level = "operator_only"
        authority_join = "raw_or_private_trace_operator_only"
        reason = "raw_or_private_trace_material"
    elif family in agent_trace_families.FINAL_CLOSEOUT_FAMILIES:
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
    elif family in agent_trace_families.SOURCE_OPEN_FAMILIES and _has_refs(row):
        admission_level = "bounded_evidence_after_open"
        authority_join = "behavior_receipt_navigation"
        training_role = "positive_demo"
        source_state = "source_open_receipt"
        reason = "source_open_anchor_receipt"
    elif (
        family in agent_trace_families.CHECK_RECEIPT_FAMILIES
        and _success(row)
        and _has_refs(row)
    ):
        admission_level = "reopenable_route"
        authority_join = "behavior_receipt_navigation"
        training_role = "process_supervision"
        source_state = "source_refs_and_success_receipt"
        reason = "successful_check_receipt_with_source_ref"
    elif (
        family in agent_trace_families.ROUTE_NOTE_FAMILIES
        and _has_refs(row)
        and _has_refs(row, "joined_evidence_refs")
    ):
        admission_level = "reopenable_route"
        authority_join = "joined_process_navigation"
        training_role = "process_supervision"
        source_state = "joined_source_refs"
        reason = "route_note_joined_to_source"
    elif (
        family in agent_trace_families.REPO_BREADCRUMB_FAMILIES
        and row.get("safe_repo_relative") is True
    ):
        admission_level = "navigation_candidate"
        authority_join = "repo_breadcrumb_navigation_only"
        training_role = "replay_sample"
        source_state = "safe_repo_relative_breadcrumb"
        reason = "safe_repo_relative_navigation"

    return {
        "trace_id": _text(row.get("trace_id") or row.get("id")),
        "trace_family": family or "unknown",
        "producer_trace_family": producer_family or "",
        "family_alias_applied": bool(producer_family and producer_family != family),
        "unknown_trace_family": unknown_family,
        "admission_level": admission_level,
        "authority_join": authority_join,
        "training_role": training_role,
        "source_state": source_state,
        "source_ref_count": _source_ref_count(row),
        "source_ref_digest": _source_ref_digest(row),
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


def behavior_training_signal_from_trace(
    row: Mapping[str, Any],
    *,
    cue: Any = None,
    outcome: str | None = None,
) -> dict[str, Any]:
    """Project one trace/feedback row into the shared training-signal ledger."""

    classification = classify_trace_row(row)
    raw_outcome = _text(
        outcome
        or row.get("outcome")
        or row.get("signal")
        or row.get("verifier_outcome")
        or row.get("status")
    ).casefold()
    normalized_outcome = normalize_feedback_signal(raw_outcome, default=raw_outcome)
    role = _training_role_from_outcome(normalized_outcome, classification["training_role"])
    if role == "positive_demo" and classification["admission_level"] == "operator_only":
        role = "none"
    if role == "none" and classification["admission_level"] == "reopenable_route":
        role = "process_supervision"
    signal_id = stable_json_join_id(
        "bts",
        classification["trace_family"],
        classification["admission_level"],
        role,
        _cue_hash(cue, row),
        agent_trace_families.safe_optional_token(
            row.get("route_id") or row.get("candidate_id"),
            prefix="route",
        ),
        classification.get("source_ref_digest"),
        ensure_ascii=False,
        default_str=False,
        length=20,
    )
    signal: dict[str, Any] = {
        "schema_version": LEDGER_SCHEMA_VERSION,
        "kind": TRAINING_SIGNAL_KIND,
        "signal_id": signal_id,
        "trace_id": classification["trace_id"],
        "trace_family": classification["trace_family"],
        "admission_level": classification["admission_level"],
        "training_role": role,
        "authority_join": classification["authority_join"],
        "candidate_lifecycle_state": classification["candidate_lifecycle_state"],
        "graph_projection": classification["graph_projection"],
        "cue_hash": _cue_hash(cue, row),
        "route_id": agent_trace_families.safe_optional_token(
            row.get("route_id") or row.get("candidate_id"),
            prefix="route",
        ),
        "preferred_route_id": agent_trace_families.safe_optional_token(
            row.get("preferred_route_id"),
            prefix="route",
        ),
        "rejected_route_ids": [
            token
            for value in row.get("rejected_route_ids") or []
            if (token := agent_trace_families.safe_optional_token(value, prefix="route"))
        ][:8],
        "outcome": normalized_outcome,
        "source_ref_count": int(classification.get("source_ref_count") or 0),
        "source_ref_digest": classification.get("source_ref_digest") or "",
        "opened_anchor_hits": int(row.get("opened_anchor_hits") or row.get("source_open_anchor_hits") or 0),
        "micro_data_card": classification["micro_data_card"],
        "privacy_boundary": {
            "stores_raw_prompt_text": False,
            "stores_raw_tool_output": False,
            "stores_full_command_args": False,
            "stores_local_path": False,
            "stores_private_source_excerpt": False,
        },
        "policy_boundary": {
            "training_signal_not_source_truth": True,
            "source_reopen_required_for_claims": True,
            "priority_not_foreground_ranking_magic": True,
        },
    }
    signal["learning_priority"] = learning_priority_for_signal({**dict(row), **signal})
    if signal["preferred_route_id"] and signal["rejected_route_ids"]:
        signal["contrastive_pair"] = {
            "cue_hash": signal["cue_hash"],
            "preferred_route_id": signal["preferred_route_id"],
            "rejected_route_ids": signal["rejected_route_ids"],
            "scope": agent_trace_families.safe_optional_token(
                row.get("scope") or row.get("scope_key"),
                prefix="scope",
            ),
            "freshness": _text(row.get("freshness") or "recheck_on_new_feedback"),
        }
    return signal


def project_behavior_training_ledger(
    rows: Iterable[Mapping[str, Any]],
    *,
    detail: str = "compact",
) -> dict[str, Any]:
    row_items = [row for row in rows if isinstance(row, Mapping)]
    adapted_rows = adapt_trace_rows_with_receipts(row_items)
    signals = [
        dict(row)
        if row.get("kind") == TRAINING_SIGNAL_KIND
        else behavior_training_signal_from_trace(row)
        for row in adapted_rows
    ]
    role_counts = Counter(str(row.get("training_role") or "none") for row in signals)
    admission_counts = Counter(str(row.get("admission_level") or "operator_only") for row in signals)
    priority_counts = Counter(
        str((row.get("learning_priority") or {}).get("bucket") or "low")
        for row in signals
    )
    if detail in {"detail", "full", "operator"}:
        samples = []
        for row in signals[:8]:
            samples.append(
                {
                    "signal_id": row.get("signal_id"),
                    "training_role": row.get("training_role"),
                    "admission_level": row.get("admission_level"),
                    "candidate_lifecycle_state": row.get("candidate_lifecycle_state"),
                    "learning_priority": row.get("learning_priority"),
                    "has_contrastive_pair": bool(row.get("contrastive_pair")),
                    "source_ref_count": row.get("source_ref_count"),
                }
            )
        return {
            "kind": "aippocampus_behavior_training_signal_ledger",
            "schema_version": LEDGER_SCHEMA_VERSION,
            "detail": detail,
            "status": "ok",
            "signal_count": len(signals),
            "training_role_counts": dict(sorted(role_counts.items())),
            "admission_counts": dict(sorted(admission_counts.items())),
            "learning_priority_counts": dict(sorted(priority_counts.items())),
            "contrastive_pair_count": sum(1 for row in signals if row.get("contrastive_pair")),
            "sample_rows": samples,
            "privacy_boundary": {
                "sample_rows_omit_raw_prompts_tools_paths_and_source_text": True,
            },
        }
    active_count = sum(
        1
        for row in signals
        if row.get("training_role") in {"positive_demo", "process_supervision", "hard_negative"}
    )
    return {
        "kind": "aippocampus_behavior_training_signal_ledger",
        "schema_version": LEDGER_SCHEMA_VERSION,
        "detail": "compact",
        "status": "has_training_signals" if active_count else "diagnostic_only",
        "decision": "use_training_signals_as_navigation_calibration_only",
        "signal_count": len(signals),
        "active_signal_count": active_count,
        "claim_boundary": "behavior_training_signals_are_not_source_truth",
    }


def draft_navigation_candidate_from_signal(
    signal: Mapping[str, Any],
    *,
    producer_family: str = "behavior_training_signal",
) -> dict[str, Any]:
    cue_hash = _text(signal.get("cue_hash"))
    route_id = agent_trace_families.safe_optional_token(signal.get("route_id"), prefix="route")
    dedupe_key = stable_json_join_id(
        "navcand",
        producer_family,
        cue_hash,
        route_id,
        signal.get("training_role"),
        signal.get("source_ref_digest"),
        ensure_ascii=False,
        default_str=False,
        length=20,
    )
    return {
        "schema_version": CANDIDATE_SCHEMA_VERSION,
        "kind": SPECULATIVE_CANDIDATE_KIND,
        "candidate_id": dedupe_key,
        "dedupe_key": dedupe_key,
        "producer_family": producer_family,
        "signal_id": signal.get("signal_id"),
        "cue_hash": cue_hash,
        "route_id": route_id,
        "training_role": signal.get("training_role") or "none",
        "admission_level": signal.get("admission_level") or "operator_only",
        "lifecycle_state": "draft_candidate",
        "intended_use": "source_reopen_navigation",
        "claim_boundary": "candidate_requires_verifier_or_source_open_before_claim",
        "learning_priority": signal.get("learning_priority") or {},
        "source_ref_count": int(signal.get("source_ref_count") or 0),
        "source_ref_digest": signal.get("source_ref_digest") or "",
    }


def verify_navigation_candidate(
    candidate: Mapping[str, Any],
    *,
    outcome: str,
    reason: str = "",
) -> dict[str, Any]:
    normalized = _text(outcome).casefold()
    if normalized not in VERIFIER_OUTCOMES:
        normalized = "needs_refine"
    next_state = {
        "source_open_hit": "source_open_claim_ready",
        "actionable_reopenable_route": "actionable_reopenable_route",
        "wrong_route": "rejected_hard_negative",
        "dismissed": "rejected_hard_negative",
        "manual_search_after_route": "rejected_hard_negative",
        "privacy_blocked": "parked_privacy_blocked",
        "stale": "parked_stale_recheck",
        "duplicate": "deduped_duplicate",
        "needs_refine": "staging_needs_refine",
        "missed_opportunity": "replay_only_missed_opportunity",
    }[normalized]
    role = str(candidate.get("training_role") or "none")
    if next_state == "rejected_hard_negative":
        role = "hard_negative"
    elif next_state == "replay_only_missed_opportunity" and role == "none":
        role = "replay_sample"
    verified = dict(candidate)
    verified["verifier_outcome"] = normalized
    verified["lifecycle_state"] = next_state
    verified["training_role"] = role
    verified["verified_reason"] = (
        agent_trace_families.safe_optional_token(reason, prefix="reason") if reason else ""
    )
    verified["foreground_eligible"] = next_state in {
        "actionable_reopenable_route",
        "source_open_claim_ready",
    }
    verified["claim_boundary"] = (
        "bounded_to_opened_source_scope"
        if next_state == "source_open_claim_ready"
        else "source_reopen_required_before_claim"
    )
    return verified


def dedupe_navigation_candidates(candidates: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    by_key: dict[str, dict[str, Any]] = {}
    for candidate in candidates:
        if not isinstance(candidate, Mapping):
            continue
        key = _text(candidate.get("dedupe_key") or candidate.get("candidate_id"))
        if not key:
            continue
        existing = by_key.get(key)
        current = dict(candidate)
        if not existing:
            by_key[key] = current
            continue
        existing_priority = int((existing.get("learning_priority") or {}).get("score") or 0)
        current_priority = int((current.get("learning_priority") or {}).get("score") or 0)
        existing_foreground = bool(existing.get("foreground_eligible"))
        current_foreground = bool(current.get("foreground_eligible"))
        if (current_foreground, current_priority) > (existing_foreground, existing_priority):
            by_key[key] = current
    return sorted(
        by_key.values(),
        key=lambda row: (
            not bool(row.get("foreground_eligible")),
            -int((row.get("learning_priority") or {}).get("score") or 0),
            str(row.get("candidate_id") or ""),
        ),
    )


def project_candidate_funnel(
    candidates: Iterable[Mapping[str, Any]],
    *,
    detail: str = "compact",
) -> dict[str, Any]:
    deduped = dedupe_navigation_candidates(candidates)
    lifecycle_counts = Counter(str(row.get("lifecycle_state") or "unknown") for row in deduped)
    producer_counts = Counter(str(row.get("producer_family") or "unknown") for row in deduped)
    role_counts = Counter(str(row.get("training_role") or "none") for row in deduped)
    foreground = [row for row in deduped if row.get("foreground_eligible")]
    if detail in {"detail", "full", "operator"}:
        return {
            "kind": "aippocampus_speculative_navigation_candidate_funnel",
            "schema_version": CANDIDATE_SCHEMA_VERSION,
            "detail": detail,
            "status": "ok",
            "candidate_count": len(deduped),
            "foreground_exposed_count": len(foreground),
            "lifecycle_counts": dict(sorted(lifecycle_counts.items())),
            "producer_counts": dict(sorted(producer_counts.items())),
            "training_role_counts": dict(sorted(role_counts.items())),
            "privacy_boundary": {
                "candidate_inventory_omits_raw_prompts_tools_paths_and_source_text": True,
            },
        }
    if not foreground:
        return {
            "kind": "aippocampus_speculative_navigation_candidate_funnel",
            "schema_version": CANDIDATE_SCHEMA_VERSION,
            "detail": "compact",
            "status": "diagnostic_only",
            "decision": "no_candidate_reaches_foreground",
            "claim_boundary": "candidate_funnel_not_source_truth",
        }
    first = foreground[0]
    return {
        "kind": "aippocampus_speculative_navigation_candidate_funnel",
        "schema_version": CANDIDATE_SCHEMA_VERSION,
        "detail": "compact",
        "status": "foreground_route_available",
        "decision": "open_verified_candidate_source",
        "foreground_action": {
            "id": "open_candidate_source",
            "tool_name": "agent_deepen",
            "mutation_risk": "read_only",
            "claim_boundary": first.get("claim_boundary") or "source_reopen_required_before_claim",
        },
        "primary_candidate": {
            "producer_family": first.get("producer_family"),
            "lifecycle_state": first.get("lifecycle_state"),
            "training_role": first.get("training_role"),
            "claim_boundary": first.get("claim_boundary"),
        },
        "claim_boundary": "candidate_navigation_only_until_source_open",
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
    admitted = [classify_trace_row(row) for row in adapt_trace_rows_with_receipts(rows)]
    counts = Counter(item["admission_level"] for item in admitted)
    training_counts = Counter(item["training_role"] for item in admitted)
    graph_counts = Counter(item["graph_projection"] for item in admitted)
    unknown_families = Counter(
        item["unknown_trace_family"] for item in admitted if item.get("unknown_trace_family")
    )
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
            "unknown_family_count": sum(unknown_families.values()),
            "unknown_trace_families": [
                {"family": family, "count": count}
                for family, count in sorted(unknown_families.items())[:8]
            ],
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
    "ACCEPTED_RECEIPT_FIELDS",
    "CANDIDATE_SCHEMA_VERSION",
    "LEDGER_SCHEMA_VERSION",
    "RECEIPT_FIELD_CONTRACT",
    "SPECULATIVE_CANDIDATE_KIND",
    "TRAINING_SIGNAL_KIND",
    "TRAINING_ROLES",
    "VERIFIER_OUTCOMES",
    "adapt_trace_rows_with_receipts",
    "behavior_training_signal_from_trace",
    "classify_trace_row",
    "dedupe_navigation_candidates",
    "draft_navigation_candidate_from_signal",
    "learning_priority_for_signal",
    "project_behavior_training_ledger",
    "project_candidate_funnel",
    "project_trace_admission",
    "verify_navigation_candidate",
]
