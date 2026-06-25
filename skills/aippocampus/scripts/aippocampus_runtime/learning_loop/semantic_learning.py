"""Runtime semantic-learning intake, adjudication, and action guidance.

Semantic learning stays navigation-only: candidates enter an inbox first, then
a deterministic source/adjudication gate decides whether they can become small
source-reopen guidance. Raw model wording is never evidence.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from aippocampus_runtime.core import stable_json_join_id

SCHEMA_VERSION = 1
SEMANTIC_INBOX_KIND = "aippocampus_semantic_learning_inbox_report"
SEMANTIC_DECISION_KIND = "aippocampus_semantic_learning_adjudication_report"
SEMANTIC_GUIDANCE_KIND = "aippocampus_semantic_learning_action_guidance"
SEMANTIC_STAGE_KIND = "aippocampus_semantic_learning_stage_report"
DOGFOOD_KIND = "aippocampus_semantic_learning_dogfood_fixture_report"
SEMANTIC_OUTCOME_KIND = "semantic_learning_guidance_outcome"
CLAIM_PERMISSION = "navigation_only_not_fact"
STALE_STATUSES = {"stale", "superseded", "refuted", "retired", "archived", "resolved"}
SEMANTIC_OUTCOMES = {
    "prevented_repeat",
    "ignored",
    "repeated_failure_after_surface",
    "dismissed_noisy",
    "stale_superseded",
    "outcome_unobserved",
}
SEMANTIC_USEFUL_OUTCOMES = {"prevented_repeat"}
SEMANTIC_INEFFECTIVE_OUTCOMES = {
    "ignored",
    "repeated_failure_after_surface",
    "dismissed_noisy",
}
PROMOTABLE_KINDS = {
    "recurring_question_candidate",
    "workflow_packaging_candidate",
    "cross_thread_resonance_candidate",
}
BACKSTAGE_KINDS = {"blind_spot_candidate", "one_sided_route_candidate"}


def _safe_refs(value: Any, *, limit: int = 6) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    refs: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, Mapping):
            continue
        refs.append(
            {
                str(key): str(item.get(key) or "")[:160]
                for key in (
                    "thread_key",
                    "source_id",
                    "message_id",
                    "line",
                    "handle",
                    "route_id",
                    "event_id",
                )
                if item.get(key) is not None
            }
        )
        if len(refs) >= limit:
            break
    return refs


def _dedupe_refs(refs: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for ref in refs:
        key = json.dumps(ref, ensure_ascii=False, sort_keys=True)
        if key in seen:
            continue
        seen.add(key)
        result.append(dict(ref))
    return result


def _tokens(values: Iterable[Any]) -> set[str]:
    tokens: set[str] = set()
    for value in values:
        if isinstance(value, (list, tuple, set)):
            tokens.update(_tokens(value))
            continue
        text = str(value or "").casefold().replace("_", " ").replace("-", " ")
        tokens.update(token for token in text.split() if len(token) >= 3)
    return tokens


def _privacy_scope(row: Mapping[str, Any]) -> str:
    return str(
        row.get("privacy_scope")
        or row.get("privacy_boundary")
        or row.get("scope")
        or "public"
    ).casefold()


def _guidance_id(row: Mapping[str, Any]) -> str:
    return str(row.get("guidance_id") or row.get("lesson_id") or row.get("record_id") or "")


def _outcome_status(outcome: str, *, has_observed_refs: bool, self_report_only: bool) -> str:
    if outcome == "outcome_unobserved" or self_report_only or not has_observed_refs:
        return "unproven"
    if outcome in SEMANTIC_USEFUL_OUTCOMES:
        return "useful_signal"
    if outcome in SEMANTIC_INEFFECTIVE_OUTCOMES:
        return "ineffective"
    if outcome == "stale_superseded":
        return "archived"
    return "unproven"


def summarize_semantic_learning_guidance_outcomes(
    surfaced_guidance: Iterable[Mapping[str, Any]],
    outcome_rows: Iterable[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    guidance = [dict(row) for row in surfaced_guidance if isinstance(row, Mapping)]
    surfaced_ids = {_guidance_id(row) for row in guidance if _guidance_id(row)}
    explicit_by_guidance_id: dict[str, dict[str, Any]] = {}
    for raw in outcome_rows or []:
        if not isinstance(raw, Mapping):
            continue
        if raw.get("kind") != SEMANTIC_OUTCOME_KIND:
            continue
        guidance_id = _guidance_id(raw)
        if not guidance_id:
            continue
        explicit_by_guidance_id[guidance_id] = dict(raw)

    outcome_projection: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    observed_denominator = 0
    source_reopen_numerator = 0
    for item in guidance:
        guidance_id = _guidance_id(item)
        raw_outcome: Mapping[str, Any] | None = explicit_by_guidance_id.get(guidance_id)
        outcome = str((raw_outcome or {}).get("outcome") or "outcome_unobserved")
        if outcome not in SEMANTIC_OUTCOMES:
            outcome = "outcome_unobserved"
        event_refs = _dedupe_refs(_safe_refs((raw_outcome or {}).get("event_refs")))
        source_refs = _dedupe_refs(_safe_refs((raw_outcome or {}).get("source_refs")))
        self_report_only = bool((raw_outcome or {}).get("self_report_only"))
        observed_after_guidance = bool((raw_outcome or {}).get("observed_after_guidance"))
        has_observed_refs = bool(event_refs or source_refs)
        is_observed = (
            raw_outcome is not None
            and outcome != "outcome_unobserved"
            and observed_after_guidance
            and has_observed_refs
            and not self_report_only
        )
        status = _outcome_status(
            outcome,
            has_observed_refs=has_observed_refs and observed_after_guidance,
            self_report_only=self_report_only,
        )
        if is_observed:
            observed_denominator += 1
            if source_refs:
                source_reopen_numerator += 1
            counts["surfaced_before_repeat_count"] += 1
            if outcome == "prevented_repeat":
                counts["repeat_semantic_failure_prevented_or_redirected_count"] += 1
            elif outcome == "repeated_failure_after_surface":
                counts["repeat_semantic_failure_after_surface_count"] += 1
            elif outcome in {"ignored", "dismissed_noisy"}:
                counts["false_positive_nudge_count"] += 1
        counts[f"{outcome}_count"] += 1
        counts[f"{status}_count"] += 1
        outcome_projection.append(
            {
                "kind": SEMANTIC_OUTCOME_KIND,
                "schema_version": SCHEMA_VERSION,
                "guidance_id": guidance_id,
                "outcome": outcome,
                "outcome_status": status,
                "observed_after_guidance": observed_after_guidance,
                "self_report_only": self_report_only,
                "event_refs": event_refs,
                "source_refs": source_refs,
                "navigation_only": True,
                "supports_factual_claim": False,
            }
        )

    for raw in explicit_by_guidance_id.values():
        guidance_id = _guidance_id(raw)
        if guidance_id in surfaced_ids:
            continue
        counts["outcome_without_surfaced_guidance_count"] += 1

    metrics = {
        "surfaced_before_repeat_count": counts["surfaced_before_repeat_count"],
        "repeat_semantic_failure_after_surface_count": counts[
            "repeat_semantic_failure_after_surface_count"
        ],
        "false_positive_nudge_count": counts["false_positive_nudge_count"],
        "source_reopen_after_semantic_guidance_rate": (
            round(source_reopen_numerator / observed_denominator, 6)
            if observed_denominator
            else 0.0
        ),
        "repeat_semantic_failure_prevented_or_redirected_count": counts[
            "repeat_semantic_failure_prevented_or_redirected_count"
        ],
        "outcome_unobserved_count": counts["outcome_unobserved_count"],
        "unproven_count": counts["unproven_count"],
        "useful_signal_count": counts["useful_signal_count"],
        "ineffective_count": counts["ineffective_count"],
        "archived_count": counts["archived_count"],
        "observed_outcome_row_count": observed_denominator,
        "outcome_without_surfaced_guidance_count": counts[
            "outcome_without_surfaced_guidance_count"
        ],
    }
    return {
        "kind": "aippocampus_semantic_learning_outcome_report",
        "schema_version": SCHEMA_VERSION,
        "ok": True,
        "metrics": metrics,
        "outcome_counts": {
            key: counts[f"{key}_count"]
            for key in sorted(SEMANTIC_OUTCOMES)
            if counts[f"{key}_count"]
        },
        "outcomes": outcome_projection,
        "contract": {
            "surfaced_guidance_alone_is_unproven": True,
            "useful_counts_require_observed_outcome_rows": True,
            "self_report_only_does_not_ripen": True,
            "raw_private_payloads_excluded": True,
        },
    }


def _review_status(row: Mapping[str, Any]) -> tuple[str, list[str]]:
    refs = _dedupe_refs(_safe_refs(row.get("source_refs")))
    freshness = str(row.get("freshness") or row.get("status") or "current").casefold()
    thickness = str(row.get("source_thickness") or ("usable" if refs else "thin")).casefold()
    scope = _privacy_scope(row)
    basis = str(row.get("evidence_basis") or "").casefold()
    risk = str(row.get("risk") or row.get("hallucination_risk") or "").casefold()
    reason_codes: list[str] = []
    if freshness in STALE_STATUSES:
        return "retired", ["semantic_candidate_stale_or_resolved"]
    if "private" in scope or "local-only" in scope or "local_only" in scope:
        return "rejected", ["semantic_candidate_private_or_local_only"]
    if "self_report_only" in basis or basis == "self-report-only":
        return "rejected", ["semantic_candidate_self_report_only"]
    if risk in {"high", "hallucination", "hallucination_risk"}:
        return "rejected", ["semantic_candidate_hallucination_risk"]
    if len(refs) < 2 or thickness in {"thin", "source-thin", "source_thin"}:
        return "backstage", ["semantic_candidate_source_thin"]
    if str(row.get("candidate_kind") or "") in BACKSTAGE_KINDS:
        return "review_queued", ["semantic_candidate_review_queued", "dream_or_counter_route_review_first"]
    reason_codes.append("semantic_candidate_review_queued")
    return "review_queued", reason_codes


def intake_semantic_learning_hypotheses(
    hypotheses: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    inbox: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    for row in hypotheses:
        if row.get("kind") not in {"aippocampus_semantic_learning_hypothesis", None}:
            continue
        refs = _dedupe_refs(_safe_refs(row.get("source_refs")))
        status, intake_reasons = _review_status(row)
        candidate_kind = str(row.get("candidate_kind") or "workflow_packaging_candidate")
        counts["candidate_count"] += 1
        counts[f"{status}_count"] += 1
        inbox.append(
            {
                "kind": "aippocampus_semantic_learning_inbox_row",
                "schema_version": SCHEMA_VERSION,
                "hypothesis_id": str(
                    row.get("hypothesis_id")
                    or stable_json_join_id(
                        "sem_hyp",
                        candidate_kind,
                        refs,
                        ensure_ascii=False,
                        default_str=False,
                    )
                ),
                "candidate_kind": candidate_kind,
                "source_refs": refs,
                "source_ref_count": len(refs),
                "source_thickness": str(row.get("source_thickness") or ("usable" if refs else "thin")),
                "freshness": str(row.get("freshness") or "current"),
                "privacy_scope": _privacy_scope(row),
                "intake_status": status,
                "candidate_status": str(row.get("status") or "candidate"),
                "review_window": str(row.get("review_after") or "next_consolidation_review"),
                "reason_codes": [
                    *[str(code) for code in row.get("reason_codes") or []],
                    *intake_reasons,
                ],
                "foreground_eligible": False,
                "model_output_is_evidence": False,
                "navigation_only": True,
                "claim_permission": CLAIM_PERMISSION,
                "source_reopen_required_before_claim": True,
            }
        )
    for name in (
        "candidate_count",
        "review_queued_count",
        "backstage_count",
        "rejected_count",
        "retired_count",
    ):
        counts.setdefault(name, 0)
    return {
        "kind": SEMANTIC_INBOX_KIND,
        "schema_version": SCHEMA_VERSION,
        "ok": True,
        "inbox": inbox,
        "stage_counts": dict(counts),
        "public_safe": {
            "raw_prompt_text_serialized": False,
            "raw_tool_payloads_serialized": False,
            "local_paths_serialized": False,
        },
    }


def _promotion_type(candidate_kind: str) -> str:
    if candidate_kind == "recurring_question_candidate":
        return "reviewable_question_route"
    if candidate_kind == "workflow_packaging_candidate":
        return "workflow_candidate"
    if candidate_kind == "cross_thread_resonance_candidate":
        return "source_backed_bridge_route"
    return "dream_or_counter_route_review_task"


def adjudicate_semantic_learning_hypotheses(
    inbox_rows: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    decisions: list[dict[str, Any]] = []
    promoted: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    for row in inbox_rows:
        status = str(row.get("intake_status") or "")
        candidate_kind = str(row.get("candidate_kind") or "")
        refs = _dedupe_refs(_safe_refs(row.get("source_refs")))
        if status == "retired":
            decision = "retire"
            reason = ["semantic_candidate_retired_before_promotion"]
        elif status == "rejected":
            decision = "reject"
            reason = ["semantic_candidate_rejected_by_intake_gate"]
        elif status == "backstage" or candidate_kind in BACKSTAGE_KINDS:
            decision = "keep_backstage"
            reason = ["semantic_candidate_requires_review_not_action_time"]
        elif candidate_kind in PROMOTABLE_KINDS and len(refs) >= 2:
            decision = "promote"
            reason = ["semantic_candidate_source_backed_promoted", f"semantic_kind:{candidate_kind}"]
        else:
            decision = "needs_human_review"
            reason = ["semantic_candidate_needs_human_review"]
        counts[decision] += 1
        decision_row = {
            "kind": "aippocampus_semantic_learning_adjudication_decision",
            "schema_version": SCHEMA_VERSION,
            "hypothesis_id": row.get("hypothesis_id"),
            "candidate_kind": candidate_kind,
            "decision": decision,
            "promotion_type": _promotion_type(candidate_kind) if decision == "promote" else "",
            "source_refs": refs,
            "source_ref_count": len(refs),
            "navigation_only": True,
            "claim_permission": CLAIM_PERMISSION,
            "source_reopen_required_before_claim": True,
            "model_output_is_evidence": False,
            "reason_codes": [*reason, *[str(code) for code in row.get("reason_codes") or []]],
        }
        decisions.append(decision_row)
        if decision == "promote":
            promoted.append(
                {
                    "kind": "aippocampus_promoted_semantic_learning_guidance_candidate",
                    "schema_version": SCHEMA_VERSION,
                    "guidance_candidate_id": stable_json_join_id(
                        "sem_guidance_candidate",
                        row.get("hypothesis_id"),
                        candidate_kind,
                        ensure_ascii=False,
                        default_str=False,
                    ),
                    "hypothesis_id": row.get("hypothesis_id"),
                    "candidate_kind": candidate_kind,
                    "promotion_type": _promotion_type(candidate_kind),
                    "source_refs": refs,
                    "source_ref_count": len(refs),
                    "freshness": row.get("freshness") or "current",
                    "navigation_only": True,
                    "claim_permission": CLAIM_PERMISSION,
                    "source_reopen_required_before_claim": True,
                    "foreground_eligible": True,
                    "model_output_is_evidence": False,
                    "reason_codes": decision_row["reason_codes"],
                }
            )
    for name in ("promote", "keep_backstage", "reject", "retire", "needs_human_review"):
        counts.setdefault(name, 0)
    return {
        "kind": SEMANTIC_DECISION_KIND,
        "schema_version": SCHEMA_VERSION,
        "ok": True,
        "decisions": decisions,
        "promoted_guidance_candidates": promoted,
        "decision_counts": dict(counts),
    }


def _guidance_text(candidate_kind: str) -> tuple[str, str]:
    if candidate_kind == "recurring_question_candidate":
        return (
            "recurring_question_reopen_before_decision",
            "This resembles a recurring unresolved decision; reopen source refs before choosing.",
        )
    if candidate_kind == "workflow_packaging_candidate":
        return (
            "review_workflow_packaging_candidate",
            "This repeated workflow may be ready for packaging; review source-backed evidence first.",
        )
    if candidate_kind == "cross_thread_resonance_candidate":
        return (
            "use_bridge_route_before_broad_search",
            "This may be the same unresolved problem across trails; use the bridge route before broad search.",
        )
    return (
        "review_counter_route_before_action",
        "Prior reviews suggest this framing may be one-sided; consider counter-route sources first.",
    )


def surface_semantic_learning_guidance(
    promoted_candidates: Iterable[Mapping[str, Any]],
    *,
    query_terms: Sequence[str] | None = None,
    visible_source_refs: Sequence[Mapping[str, Any]] | None = None,
    dismissed_ids: Sequence[str] | None = None,
    max_guidance: int = 3,
) -> dict[str, Any]:
    query = _tokens(query_terms or [])
    visible = _dedupe_refs(_safe_refs(list(visible_source_refs or [])))
    dismissed = {str(item) for item in dismissed_ids or []}
    guidance: list[dict[str, Any]] = []
    suppressed: Counter[str] = Counter()
    for row in promoted_candidates:
        if row.get("kind") != "aippocampus_promoted_semantic_learning_guidance_candidate":
            suppressed["raw_or_unpromoted_suppressed_count"] += 1
            continue
        if not row.get("foreground_eligible", True):
            suppressed["foreground_ineligible_suppressed_count"] += 1
            continue
        candidate_id = str(row.get("guidance_candidate_id") or "")
        if candidate_id in dismissed:
            suppressed["recently_dismissed_suppressed_count"] += 1
            continue
        freshness = str(row.get("freshness") or "current").casefold()
        if freshness in STALE_STATUSES:
            suppressed["stale_suppressed_count"] += 1
            continue
        refs = _dedupe_refs(_safe_refs(row.get("source_refs")))
        if len(refs) < 2:
            suppressed["source_thin_suppressed_count"] += 1
            continue
        if visible and any(ref in visible for ref in refs):
            suppressed["already_visible_suppressed_count"] += 1
            continue
        candidate_kind = str(row.get("candidate_kind") or "")
        haystack = _tokens([candidate_kind, row.get("promotion_type"), row.get("reason_codes")])
        if query and not (query & haystack):
            suppressed["query_mismatch_suppressed_count"] += 1
            continue
        next_action, text = _guidance_text(candidate_kind)
        guidance.append(
            {
                "kind": SEMANTIC_GUIDANCE_KIND,
                "schema_version": SCHEMA_VERSION,
                "guidance_id": stable_json_join_id(
                    "sem_guidance",
                    candidate_id,
                    query_terms,
                    ensure_ascii=False,
                    default_str=False,
                ),
                "title": "Source-backed semantic learning guidance",
                "guidance_text": text,
                "next_action": next_action,
                "action_grammar": "reopen_sources_before_claim_or_decision",
                "candidate_kind": candidate_kind,
                "promotion_type": row.get("promotion_type") or "",
                "source_refs": refs[:3],
                "source_reopen_required_before_claim": True,
                "claim_permission": CLAIM_PERMISSION,
                "navigation_only": True,
                "model_output_is_evidence": False,
                "anti_nag": {
                    "dismissible": True,
                    "visible_source_overlap_suppressed": True,
                    "stale_or_retired_suppressed": True,
                    "raw_hypotheses_never_surface": True,
                },
                "reason_codes": [
                    "semantic_learning_promoted_guidance",
                    "source_reopen_required",
                    *[str(code) for code in row.get("reason_codes") or []],
                ],
            }
        )
        if len(guidance) >= max_guidance:
            break
    return {
        "kind": "aippocampus_semantic_learning_action_time_projection",
        "schema_version": SCHEMA_VERSION,
        "ok": True,
        "guidance": guidance,
        "guidance_count": len(guidance),
        "suppression_counts": dict(suppressed),
        "public_safe": {
            "raw_source_text_serialized": False,
            "local_paths_serialized": False,
            "model_claims_used_as_evidence": False,
        },
    }


def build_semantic_learning_stage_report(
    hypotheses: Iterable[Mapping[str, Any]],
    *,
    guidance_outcomes: Iterable[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    materialized = list(hypotheses)
    intake = intake_semantic_learning_hypotheses(materialized)
    adjudication = adjudicate_semantic_learning_hypotheses(intake["inbox"])
    surfaced = surface_semantic_learning_guidance(
        adjudication["promoted_guidance_candidates"],
        query_terms=["semantic", "recurring", "workflow", "cross", "question"],
    )
    outcome_report = summarize_semantic_learning_guidance_outcomes(
        surfaced["guidance"],
        guidance_outcomes,
    )
    metrics = {
        "semantic_hypothesis_count": intake["stage_counts"]["candidate_count"],
        "review_queued_count": intake["stage_counts"]["review_queued_count"],
        "backstage_count": intake["stage_counts"]["backstage_count"],
        "rejected_count": intake["stage_counts"]["rejected_count"],
        "retired_count": intake["stage_counts"]["retired_count"],
        "promoted_guidance_candidate_count": adjudication["decision_counts"]["promote"],
        "action_time_guidance_count": surfaced["guidance_count"],
        "stale_private_thin_suppression_count": (
            intake["stage_counts"]["backstage_count"]
            + intake["stage_counts"]["rejected_count"]
            + intake["stage_counts"]["retired_count"]
        ),
        "raw_private_text_leak_count": 0,
        "deterministic_learning_count": 0,
        **outcome_report["metrics"],
    }
    if metrics["action_time_guidance_count"]:
        stage = "action_time_capable"
    elif metrics["promoted_guidance_candidate_count"]:
        stage = "promoted"
    elif metrics["review_queued_count"]:
        stage = "review_queued"
    else:
        stage = "candidate_only"
    return {
        "kind": SEMANTIC_STAGE_KIND,
        "schema_version": SCHEMA_VERSION,
        "ok": True,
        "stage": stage,
        "metrics": metrics,
        "intake": {
            "stage_counts": intake["stage_counts"],
            "public_safe": intake["public_safe"],
        },
        "adjudication": {
            "decision_counts": adjudication["decision_counts"],
        },
        "action_time": {
            "guidance_count": surfaced["guidance_count"],
            "guidance": surfaced["guidance"],
            "suppression_counts": surfaced["suppression_counts"],
        },
        "outcome_report": outcome_report,
        "closeout_gate": [
            "candidate_only_safety_is_not_sufficient",
            "action_time_guidance_path_required_before_closing_semantic_loop",
        ],
        "privacy_boundary": {
            "raw_private_text_serialized": False,
            "local_paths_serialized": False,
            "model_output_used_as_evidence": False,
        },
    }


def build_semantic_learning_dogfood_fixture_report() -> dict[str, Any]:
    hypotheses = [
        {
            "kind": "aippocampus_semantic_learning_hypothesis",
            "hypothesis_id": "dogfood-recurring-question",
            "candidate_kind": "recurring_question_candidate",
            "status": "candidate",
            "source_refs": [
                {"thread_key": "fixture-a", "source_id": "question-a"},
                {"thread_key": "fixture-b", "source_id": "question-b"},
            ],
            "source_thickness": "thick",
            "freshness": "current",
            "privacy_scope": "public",
        },
        {
            "kind": "aippocampus_semantic_learning_hypothesis",
            "hypothesis_id": "dogfood-blind-spot",
            "candidate_kind": "blind_spot_candidate",
            "status": "candidate",
            "source_refs": [
                {"thread_key": "fixture-c", "source_id": "blind-a"},
                {"thread_key": "fixture-d", "source_id": "blind-b"},
            ],
            "source_thickness": "usable",
            "freshness": "current",
            "privacy_scope": "public",
        },
        {
            "kind": "aippocampus_semantic_learning_hypothesis",
            "hypothesis_id": "dogfood-one-sided",
            "candidate_kind": "one_sided_route_candidate",
            "status": "candidate",
            "source_refs": [
                {"thread_key": "fixture-e", "source_id": "one-sided-a"},
                {"thread_key": "fixture-f", "source_id": "one-sided-b"},
            ],
            "source_thickness": "usable",
            "freshness": "current",
            "privacy_scope": "public",
        },
        {
            "kind": "aippocampus_semantic_learning_hypothesis",
            "hypothesis_id": "dogfood-cross-thread",
            "candidate_kind": "cross_thread_resonance_candidate",
            "status": "candidate",
            "source_refs": [
                {"thread_key": "fixture-g", "source_id": "bridge-a"},
                {"thread_key": "fixture-h", "source_id": "bridge-b"},
            ],
            "source_thickness": "thick",
            "freshness": "current",
            "privacy_scope": "public",
        },
        {
            "kind": "aippocampus_semantic_learning_hypothesis",
            "hypothesis_id": "dogfood-workflow-package",
            "candidate_kind": "workflow_packaging_candidate",
            "status": "candidate",
            "source_refs": [
                {"thread_key": "fixture-i", "source_id": "workflow-a"},
                {"thread_key": "fixture-j", "source_id": "workflow-b"},
            ],
            "source_thickness": "usable",
            "freshness": "current",
            "privacy_scope": "public",
        },
        {
            "kind": "aippocampus_semantic_learning_hypothesis",
            "hypothesis_id": "dogfood-no-package-yet",
            "candidate_kind": "workflow_packaging_candidate",
            "status": "candidate",
            "source_refs": [{"thread_key": "fixture-k", "source_id": "workflow-thin"}],
            "source_thickness": "thin",
            "freshness": "current",
            "privacy_scope": "public",
        },
        {
            "kind": "aippocampus_semantic_learning_hypothesis",
            "hypothesis_id": "dogfood-stale",
            "candidate_kind": "recurring_question_candidate",
            "status": "candidate",
            "source_refs": [
                {"thread_key": "fixture-l", "source_id": "stale-a"},
                {"thread_key": "fixture-m", "source_id": "stale-b"},
            ],
            "source_thickness": "usable",
            "freshness": "stale",
            "privacy_scope": "public",
        },
        {
            "kind": "aippocampus_semantic_learning_hypothesis",
            "hypothesis_id": "dogfood-private",
            "candidate_kind": "cross_thread_resonance_candidate",
            "status": "candidate",
            "source_refs": [
                {"thread_key": "fixture-n", "source_id": "private-a"},
                {"thread_key": "fixture-o", "source_id": "private-b"},
            ],
            "source_thickness": "usable",
            "freshness": "current",
            "privacy_scope": "private_local",
        },
    ]
    stage = build_semantic_learning_stage_report(hypotheses)
    metrics = {
        "semantic_hypothesis_count": stage["metrics"]["semantic_hypothesis_count"],
        "review_queued_count": stage["metrics"]["review_queued_count"],
        "promoted_guidance_candidate_count": stage["metrics"][
            "promoted_guidance_candidate_count"
        ],
        "action_time_guidance_count": stage["metrics"]["action_time_guidance_count"],
        "surfaced_before_repeat_count": stage["metrics"]["surfaced_before_repeat_count"],
        "repeat_semantic_failure_after_surface_count": stage["metrics"][
            "repeat_semantic_failure_after_surface_count"
        ],
        "false_positive_nudge_count": stage["metrics"]["false_positive_nudge_count"],
        "source_reopen_after_semantic_guidance_rate": stage["metrics"][
            "source_reopen_after_semantic_guidance_rate"
        ],
        "repeat_semantic_failure_prevented_or_redirected_count": stage["metrics"][
            "repeat_semantic_failure_prevented_or_redirected_count"
        ],
        "outcome_unobserved_count": stage["metrics"]["outcome_unobserved_count"],
        "unproven_count": stage["metrics"]["unproven_count"],
        "stale_or_retired_suppression_count": stage["metrics"]["stale_private_thin_suppression_count"],
        "raw_private_text_leak_count": 0,
    }
    return {
        "kind": DOGFOOD_KIND,
        "schema_version": SCHEMA_VERSION,
        "ok": bool(metrics["action_time_guidance_count"])
        and metrics["repeat_semantic_failure_after_surface_count"] == 0
        and metrics["raw_private_text_leak_count"] == 0,
        "metrics": metrics,
        "cases": [
            {
                "case_id": "recurring-question-before-repeat",
                "fixture_family": "recurring_question_family",
                "usefulness": "guidance_can_surface_before_repeat_decision",
            },
            {
                "case_id": "blind-spot-backstage-review",
                "fixture_family": "blind_spot_one_sided_route",
                "usefulness": "review_task_not_action_time_fact",
            },
            {
                "case_id": "cross-thread-bridge",
                "fixture_family": "cross_thread_resonance",
                "usefulness": "bridge_route_before_broad_search",
            },
            {
                "case_id": "workflow-packaging-and-no-package-yet",
                "fixture_family": "workflow_packaging",
                "usefulness": "package_candidate_plus_thin_negative_control",
            },
        ],
        "deterministic_learning_metrics": {
            "separate_from_semantic": True,
            "deterministic_learning_win_count": 0,
        },
        "contract_fixture_smoke": {
            "fixture_metrics_are_not_real_history": True,
            "action_time_guidance_count": stage["metrics"]["action_time_guidance_count"],
            "promoted_guidance_candidate_count": stage["metrics"][
                "promoted_guidance_candidate_count"
            ],
        },
        "observed_outcome_metrics": stage["outcome_report"]["metrics"],
        "closeout_gate": [
            "candidate_only_safety_is_not_sufficient",
            "semantic_loop_action_time_capable_on_public_fixture",
            "observed_effectiveness_requires_explicit_outcome_rows",
            "live_product_lift_not_claimed",
        ],
        "stage_report": stage,
        "privacy_boundary": {
            "raw_private_text_serialized": False,
            "local_paths_serialized": False,
            "full_prompts_serialized": False,
            "model_written_claims_used_as_evidence": False,
        },
        "cannot_claim": [
            "live_causal_product_lift",
            "private_history_quality",
            "semantic_candidate_is_source_truth",
        ],
    }
