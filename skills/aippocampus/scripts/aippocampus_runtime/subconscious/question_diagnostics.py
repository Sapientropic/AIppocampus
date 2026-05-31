#!/usr/bin/env python3
"""Question-extraction field contracts and aggregate diagnostics."""

from __future__ import annotations

from typing import Any

QUESTION_CORE_AXIS_FIELDS = ("what_features", "where_context", "phase_context")
QUESTION_AUDIT_FIELDS = (
    "question_text",
    "question_short",
    "intent_orientation",
    *QUESTION_CORE_AXIS_FIELDS,
    "collaboration_context",
)

QUESTION_EXTRACTION_FIELD_CONTRACT: dict[str, Any] = {
    "question_candidate": {
        "expected_unless_unavailable": {
            "question_short": "stable short label for matching and review",
            "intent_orientation": (
                "the user's angle of approach, such as debugging, architecture, "
                "philosophy, writing, evaluation"
            ),
            "what_features": (
                "content objects and content kind independent of where the question appeared"
            ),
            "where_context": (
                "project, thread neighborhood, source title, concept region, or local/global scope"
            ),
            "phase_context": (
                "work/life phase such as new-project start, post-compaction, "
                "pre-closeout, architecture review, source review"
            ),
        },
        "optional_but_source_backed": {
            "collaboration_context": (
                "agent/profile/collaborator/tool context when the source itself supports it"
            ),
        },
        "recommendation": (
            "expected for actionable questions: name the quiet next consumer or follow-up use; "
            "omit only when no safe source-backed next action exists"
        ),
    },
    "frontier_marker": {
        "expected_unless_unavailable": {
            "where_context": "where the unresolved boundary appears",
            "phase_context": "the phase in which the boundary blocked or deferred work",
            "recommendation": (
                "quiet next consumer or follow-up, such as source review, external-evidence check, "
                "defer-until-resume, or ask-user-only-if-reopening"
            ),
        },
        "optional_but_source_backed": {
            "collaboration_context": "agent/profile/collaborator/tool context when relevant",
            "linked_question_short": "nearby question label when a frontier is attached to a question",
        },
    },
    "quality_gate": (
        "Before finalizing question_extraction, self-check aggregate field coverage. "
        "If you return several question_candidate findings but most lack what_features, "
        "where_context, or phase_context despite source support, revise the final answer "
        "instead of emitting a minimal schema. Do not satisfy this by generic filler; "
        "every axis must be grounded in source_refs."
    ),
}


def _field_present(row: dict[str, Any], field: str) -> bool:
    value = row.get(field)
    if isinstance(value, list):
        return any(str(item or "").strip() for item in value)
    if isinstance(value, dict):
        return bool(value)
    return bool(str(value or "").strip())


def _rate(count: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return round(count / total, 4)


def _finding_kind(row: dict[str, Any]) -> str:
    return str(row.get("kind") or row.get("finding_kind") or "").strip()


def final_attempt_findings(final_attempts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for attempt in final_attempts or []:
        for finding in attempt.get("findings") or []:
            if isinstance(finding, dict):
                rows.append(finding)
    return rows


def _field_count(rows: list[dict[str, Any]], field: str) -> int:
    return sum(1 for row in rows if _field_present(row, field))


def _presence_metric(rows: list[dict[str, Any]], field: str) -> dict[str, Any]:
    count = _field_count(rows, field)
    return {"count": count, "rate": _rate(count, len(rows))}


def field_presence_counts(rows: list[dict[str, Any]]) -> dict[str, Any]:
    all_rows = [row for row in rows if isinstance(row, dict)]
    question_rows = [row for row in all_rows if _finding_kind(row) == "question_candidate"]
    frontier_rows = [row for row in all_rows if _finding_kind(row) == "frontier_marker"]
    question_total = len(question_rows)
    frontier_total = len(frontier_rows)
    question_fields = {
        field: _presence_metric(question_rows, field)
        for field in QUESTION_AUDIT_FIELDS
    }
    complete_core_axes = sum(
        1
        for row in question_rows
        if all(_field_present(row, field) for field in QUESTION_CORE_AXIS_FIELDS)
    )
    any_core_axis = sum(
        1
        for row in question_rows
        if any(_field_present(row, field) for field in QUESTION_CORE_AXIS_FIELDS)
    )
    frontier_context = sum(
        1
        for row in frontier_rows
        if _field_present(row, "where_context") or _field_present(row, "phase_context")
    )
    return {
        "finding_count": len(all_rows),
        "question_candidate_count": question_total,
        "frontier_marker_count": frontier_total,
        "question_candidate_fields": question_fields,
        "complete_core_axes": {
            "count": complete_core_axes,
            "rate": _rate(complete_core_axes, question_total),
        },
        "any_core_axis": {"count": any_core_axis, "rate": _rate(any_core_axis, question_total)},
        "missing_core_axis_rate": round(1.0 - _rate(complete_core_axes, question_total), 4)
        if question_total
        else 0.0,
        "frontier_context": {
            "count": frontier_context,
            "rate": _rate(frontier_context, frontier_total),
        },
        # Keep the aggregate for backward-compatible trend charts, but make
        # per-kind rates first-class. Question recommendations and frontier
        # boundary notes have different semantics, so a mixed denominator can
        # make a healthy question_candidate run look weak.
        "recommendation": _presence_metric(all_rows, "recommendation"),
        "recommendation_by_kind": {
            "question_candidate": _presence_metric(question_rows, "recommendation"),
            "frontier_marker": _presence_metric(frontier_rows, "recommendation"),
        },
    }


def raw_to_validated_retention(
    raw_presence: dict[str, Any], validated_presence: dict[str, Any]
) -> dict[str, Any]:
    raw_questions = int(raw_presence.get("question_candidate_count") or 0)
    raw_frontiers = int(raw_presence.get("frontier_marker_count") or 0)
    validated_questions = int(validated_presence.get("question_candidate_count") or 0)
    validated_frontiers = int(validated_presence.get("frontier_marker_count") or 0)
    return {
        "question_candidate": {
            "raw_count": raw_questions,
            "validated_count": validated_questions,
            "retention_rate": _rate(validated_questions, raw_questions),
        },
        "frontier_marker": {
            "raw_count": raw_frontiers,
            "validated_count": validated_frontiers,
            "retention_rate": _rate(validated_frontiers, raw_frontiers),
        },
    }


def raw_required_field_presence(rows: list[dict[str, Any]]) -> dict[str, Any]:
    all_rows = [row for row in rows if isinstance(row, dict)]
    question_rows = [row for row in all_rows if _finding_kind(row) == "question_candidate"]
    frontier_rows = [row for row in all_rows if _finding_kind(row) == "frontier_marker"]
    return {
        "question_candidate": {
            "confidence": _presence_metric(question_rows, "confidence"),
            "source_refs": _presence_metric(question_rows, "source_refs"),
            "summary": _presence_metric(question_rows, "summary"),
            "question_text": _presence_metric(question_rows, "question_text"),
        },
        "frontier_marker": {
            "confidence": _presence_metric(frontier_rows, "confidence"),
            "source_refs": _presence_metric(frontier_rows, "source_refs"),
            "summary": _presence_metric(frontier_rows, "summary"),
            "frontier_type": _presence_metric(frontier_rows, "frontier_type"),
            "boundary_reason": _presence_metric(frontier_rows, "boundary_reason"),
        },
    }


def question_extraction_quality_diagnostics(
    final_attempts: list[dict[str, Any]],
    findings: list[dict[str, Any]],
    accepted_final_action: dict[str, Any] | None = None,
) -> dict[str, Any]:
    raw_rows = final_attempt_findings(final_attempts)
    raw_presence = field_presence_counts(raw_rows)
    accepted_rows = final_attempt_findings([accepted_final_action or {}])
    accepted_final_presence = field_presence_counts(accepted_rows)
    validated_presence = field_presence_counts(findings)
    retention = raw_to_validated_retention(accepted_final_presence, validated_presence)
    warnings: list[dict[str, Any]] = []
    question_count = int(validated_presence.get("question_candidate_count") or 0)
    frontier_count = int(validated_presence.get("frontier_marker_count") or 0)
    core_rate = float((validated_presence.get("complete_core_axes") or {}).get("rate") or 0.0)
    recommendation_by_kind = validated_presence.get("recommendation_by_kind") or {}
    question_recommendation = recommendation_by_kind.get("question_candidate") or {}
    question_recommendation_rate = float(question_recommendation.get("rate") or 0.0)
    frontier_context_rate = float((validated_presence.get("frontier_context") or {}).get("rate") or 0.0)
    if question_count >= 3 and core_rate < 0.7:
        warnings.append(
            {
                "code": "question_extraction_missing_core_axes",
                "level": "warning",
                "message": (
                    "Most validated question_candidate findings lack one or more core map axes "
                    "(what_features, where_context, phase_context)."
                ),
                "question_candidate_count": question_count,
                "complete_core_axes_rate": core_rate,
            }
        )
    if frontier_count >= 2 and frontier_context_rate < 0.5:
        warnings.append(
            {
                "code": "question_extraction_missing_frontier_context",
                "level": "warning",
                "message": "Most frontier_marker findings lack where_context and phase_context.",
                "frontier_marker_count": frontier_count,
                "frontier_context_rate": frontier_context_rate,
            }
        )
    raw_frontier_count = int((retention.get("frontier_marker") or {}).get("raw_count") or 0)
    validated_frontier_count = int(
        (retention.get("frontier_marker") or {}).get("validated_count") or 0
    )
    if raw_frontier_count >= 2 and validated_frontier_count == 0:
        warnings.append(
            {
                "code": "question_extraction_frontiers_dropped_by_validation",
                "level": "warning",
                "message": (
                    "Raw final attempts included frontier_marker rows, but none survived validation."
                ),
                "raw_frontier_marker_count": raw_frontier_count,
            }
        )
    frontier_recommendation = recommendation_by_kind.get("frontier_marker") or {}
    frontier_recommendation_rate = float(frontier_recommendation.get("rate") or 0.0)
    if question_count >= 3 and question_recommendation_rate == 0:
        warnings.append(
            {
                "code": "question_extraction_missing_recommendations",
                "level": "info",
                "message": "Question candidates produced no recommendation fields.",
                "question_candidate_count": question_count,
            }
        )
    if frontier_count >= 2 and frontier_recommendation_rate == 0:
        warnings.append(
            {
                "code": "question_extraction_missing_frontier_recommendations",
                "level": "info",
                "message": "Frontier markers produced no recommendation fields.",
                "frontier_marker_count": frontier_count,
            }
        )
    return {
        "question_extraction_field_presence": {
            "raw_final_attempts": raw_presence,
            "accepted_final": accepted_final_presence,
            "validated": validated_presence,
        },
        "raw_required_field_presence": raw_required_field_presence(raw_rows),
        "raw_required_field_presence_all_attempts": raw_required_field_presence(raw_rows),
        "accepted_final_required_field_presence": raw_required_field_presence(accepted_rows),
        "accepted_final_to_validated_retention": retention,
        "all_final_attempts_to_validated_retention": raw_to_validated_retention(
            raw_presence, validated_presence
        ),
        "warnings": warnings,
    }


def should_request_question_axis_repair(diagnostics: dict[str, Any]) -> bool:
    presence = (diagnostics.get("question_extraction_field_presence") or {}).get("validated") or {}
    question_count = int(presence.get("question_candidate_count") or 0)
    frontier_count = int(presence.get("frontier_marker_count") or 0)
    core_rate = float((presence.get("complete_core_axes") or {}).get("rate") or 0.0)
    if question_count >= 4 and core_rate < 0.6:
        return True
    recommendation_by_kind = presence.get("recommendation_by_kind") or {}
    question_recommendation_rate = float(
        ((recommendation_by_kind.get("question_candidate") or {}).get("rate")) or 0.0
    )
    frontier_recommendation_rate = float(
        ((recommendation_by_kind.get("frontier_marker") or {}).get("rate")) or 0.0
    )
    if question_count >= 4 and question_recommendation_rate == 0:
        return True
    retention = diagnostics.get("accepted_final_to_validated_retention") or {}
    frontier_retention = retention.get("frontier_marker") or {}
    if (
        int(frontier_retention.get("raw_count") or 0) >= 2
        and int(frontier_retention.get("validated_count") or 0) == 0
    ):
        return True
    return frontier_count >= 2 and frontier_recommendation_rate == 0


def question_axis_repair_feedback(diagnostics: dict[str, Any]) -> dict[str, Any]:
    presence = (diagnostics.get("question_extraction_field_presence") or {}).get("validated") or {}
    return {
        "error": "question_extraction_missing_question_map_axes",
        "instruction": (
            "Revise the same source-backed question_extraction final. For each question_candidate, "
            "include what_features, where_context, and phase_context when source_refs support them. "
            "For frontier_marker, include where_context or phase_context when source-backed, plus a "
            "quiet recommendation when the boundary implies a safe next consumer or follow-up. Every "
            "finding, including frontier_marker, must include confidence, summary, and source_refs or "
            "validation will drop it. Do not call tools; do not invent generic labels; omit an axis or "
            "recommendation only when genuinely unavailable from the source."
        ),
        "field_presence": presence,
        "accepted_final_required_field_presence": (
            diagnostics.get("accepted_final_required_field_presence") or {}
        ),
        "raw_required_field_presence_all_attempts": (
            diagnostics.get("raw_required_field_presence_all_attempts") or {}
        ),
        "accepted_final_to_validated_retention": (
            diagnostics.get("accepted_final_to_validated_retention") or {}
        ),
        "expected_core_axes": list(QUESTION_CORE_AXIS_FIELDS),
    }
