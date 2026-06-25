"""Bridge source-backed learning findings into AIppo clause seeds.

The learning loop is allowed to notice behavior patterns. AIppo owns the
working-contract lifecycle. This adapter keeps that boundary explicit: it emits
AIppo-compatible source rows and lets the existing contract/compiler decide
foreground eligibility.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from aippocampus_runtime.aippo import working_contract
from aippocampus_runtime.core import compact_text, stable_json_tuple_id
from aippocampus_runtime.hooks.action_hint_cache_records import build_action_hint_cache_report

SCHEMA_VERSION = 1
ADAPTER_REPORT_KIND = "aippocampus_learning_aippo_bridge_report"
ELIGIBLE_FINDING_KINDS = {
    "recurring_failure_finding",
    "workflow_order_finding",
    "context_reopen_candidate",
    "environment_workaround_candidate",
    "source_backed_do_not_repeat",
    "do_not_repeat",
}
SOURCE_BACKED_LESSON_KIND = "source_backed_lesson_candidate"
BLOCKED_STATUSES = {"stale", "resolved", "refuted", "retired", "superseded", "blocked"}
REOPEN_FIRST_FINDINGS = {
    "recurring_failure_finding",
    "context_reopen_candidate",
    "environment_workaround_candidate",
    "source_backed_do_not_repeat",
    "do_not_repeat",
}


def _text(value: Any, limit: int = 220) -> str:
    return compact_text(str(value or "").strip(), limit)


def _strings(value: Any, *, limit: int = 8) -> list[str]:
    if isinstance(value, str):
        values: Sequence[Any] = [value]
    elif isinstance(value, Sequence):
        values = value
    else:
        values = []
    out: list[str] = []
    seen: set[str] = set()
    for item in values:
        text = _text(item, 120)
        key = text.casefold()
        if text and key not in seen:
            seen.add(key)
            out.append(text)
        if len(out) >= limit:
            break
    return out


def _source_refs(value: Any, *, limit: int = 6) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return refs
    for item in value:
        if isinstance(item, str):
            clean = {"source_ref": _text(item, 140)}
            if clean not in refs:
                refs.append(clean)
            if len(refs) >= limit:
                break
            continue
        if not isinstance(item, Mapping):
            continue
        source_ref_record: dict[str, Any] = {
            "source_ref": _text(
                item.get("source_ref")
                or item.get("source_id")
                or item.get("message_id")
                or item.get("event_id"),
                140,
            ),
            "kind": _text(item.get("kind") or item.get("event_kind"), 80),
            "line": item.get("line") or item.get("source_line"),
        }
        source_ref_record = {key: val for key, val in source_ref_record.items() if val not in {"", None}}
        if source_ref_record and source_ref_record not in refs:
            refs.append(source_ref_record)
        if len(refs) >= limit:
            break
    return refs


def _verified_origin(row: Mapping[str, Any]) -> bool:
    """Return whether imported learning material has a verified origin.

    Absence is deliberately fail-closed. Import bundles, loose JSONL loaders,
    and hand-authored fixtures can all contain plausible source refs; only an
    explicit verified-origin stamp may promote those refs to source-supported
    authority. Local generators that really own their source trail must stamp
    this field before handing rows to the adapter.
    """

    for key in ("verified_origin", "origin_verified", "support_verified"):
        if key in row:
            return bool(row.get(key))
    for key in ("import_origin", "integrity", "origin"):
        value = row.get(key)
        if isinstance(value, Mapping) and "verified_origin" in value:
            return bool(value.get("verified_origin"))
    return False


def _first_string(value: Any, *, limit: int = 160) -> str:
    if isinstance(value, str):
        return _text(value, limit)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for item in value:
            text = _text(item, limit)
            if text:
                return text
    return _text(value, limit)


def _source_backed_lesson_to_aippo_row(
    lesson: Mapping[str, Any],
    *,
    built_at: str,
) -> dict[str, Any] | None:
    if str(lesson.get("kind") or "") != SOURCE_BACKED_LESSON_KIND:
        return None
    if str(lesson.get("status") or "").casefold() != "ripe":
        return None
    if not lesson.get("foreground_activation_allowed"):
        return None
    refs = _source_refs(lesson.get("source_refs"))
    if not refs:
        return None
    verified_origin = _verified_origin(lesson)
    raw_structured = lesson.get("structured_lesson")
    structured: Mapping[str, Any] = raw_structured if isinstance(raw_structured, Mapping) else {}
    scope_values = lesson.get("scope")
    scope_terms = _strings(scope_values, limit=6)
    source_count = int(lesson.get("source_ref_count") or len(refs))
    source_supported = verified_origin and source_count >= 1
    lesson_id = (
        _text(lesson.get("lesson_id") or lesson.get("candidate_id") or lesson.get("clause_id"), 120)
        or stable_json_tuple_id(
            "source_lesson_clause",
            lesson.get("failed_route"),
            lesson.get("proposed_lesson"),
            ensure_ascii=False,
            length=18,
        )
    )
    guidance = (
        _text(lesson.get("proposed_lesson"), 320)
        or _text(structured.get("safer_next_action"), 220)
        or "Reopen the source-backed lesson before repeating this route."
    )
    applies_when = [
        *scope_terms,
        _text(structured.get("trigger_condition"), 120),
        _text(lesson.get("failed_route"), 120),
        _text(lesson.get("candidate_kind"), 120),
    ]
    return {
        "clause_id": lesson_id,
        "lesson_id": lesson_id,
        "kind": "reopen_first_workflow_clause",
        "scope": _first_string(scope_values) or _text(structured.get("scope"), 160) or "task_family",
        "target_fingerprint": _text(lesson.get("target_fingerprint"), 160),
        "path_category_fingerprint": _text(lesson.get("path_category_fingerprint"), 160),
        "topic_epoch": _text(lesson.get("topic_epoch"), 120) or "source-backed-lessons",
        "workspace_or_environment_profile": (
            _text(structured.get("environment_profile"), 160)
            or _text(lesson.get("workspace_or_environment_profile"), 160)
            or "unknown_environment"
        ),
        "guidance": guidance,
        "next_action": "apply_source_backed_lesson_before_repeat",
        "applies_when": _strings(applies_when, limit=8),
        "does_not_apply_when": _strings(
            lesson.get("does_not_apply_when")
            or ["source_already_visible", "lesson_refuted_or_superseded"],
            limit=8,
        ),
        "allowed_without_reopen_for": ["planning", "patch_shape", "task_ordering"],
        "support_grade": "source_supported" if source_supported else "candidate_only",
        "support_verified": bool(source_supported),
        "source_refs": refs,
        "source_ref_count": source_count,
        "independent_trail_count": int(lesson.get("independent_trail_count") or min(2, source_count)),
        "support_types": ["source_backed_lesson", "reopen_first"],
        "counter_evidence_ref_count": int(lesson.get("counter_evidence_ref_count") or 0),
        "path_provenance": "complete" if source_supported else "unverified_origin",
        "status": "ripe" if source_supported else "blocked",
        "freshness": str(structured.get("freshness") or lesson.get("freshness") or "current"),
        "review_state": "reviewed",
        "built_at": built_at,
        "last_source_seen_at": _text(lesson.get("last_source_seen_at"), 40) or built_at,
        "invalidators": _strings(
            lesson.get("invalidators")
            or ["newer_source_correction", "lesson_refuted", "environment_changed"],
            limit=8,
        ),
        "learning_loop": {
            "source_backed_lesson_id": lesson_id,
            "candidate_kind": _text(lesson.get("candidate_kind"), 120),
            "navigation_only": True,
            "source_reopen_required_before_claim": True,
            "raw_tool_payload_serialized": False,
            "origin_verified": verified_origin,
            "unverified_origin_blocks_source_supported": not verified_origin,
        },
    }


def _status(row: Mapping[str, Any]) -> str:
    return _text(row.get("status") or row.get("freshness"), 60).casefold()


def _finding_kind(row: Mapping[str, Any]) -> str:
    return _text(row.get("finding_kind") or row.get("candidate_family"), 100)


def _is_local_only(row: Mapping[str, Any]) -> bool:
    scope = _text(row.get("scope"), 160).casefold()
    privacy = _text(row.get("privacy_domain") or row.get("privacy"), 80).casefold()
    profile = _text(row.get("workspace_or_environment_profile"), 160).casefold()
    return (
        privacy in {"private", "local", "restricted"}
        or scope.startswith("machine:")
        or profile.startswith("local-only")
    )


def _suppression_reason(row: Mapping[str, Any], refs: Sequence[Mapping[str, Any]]) -> str:
    kind = _finding_kind(row)
    status = _status(row)
    if kind not in ELIGIBLE_FINDING_KINDS:
        return "unsupported_learning_finding_kind"
    if row.get("expected_local_red"):
        return "expected_tdd_red_review_only"
    if _is_local_only(row):
        return "local_only_or_private_boundary"
    if status in BLOCKED_STATUSES:
        return f"{status}_finding_degraded"
    if not refs:
        return "missing_source_refs"
    if str(row.get("confidence") or "").casefold() == "low" and int(row.get("occurrence_count") or 1) < 2:
        return "low_confidence_one_off"
    return ""


def _guidance_for(row: Mapping[str, Any]) -> tuple[str, str]:
    kind = _finding_kind(row)
    workflow = _text(row.get("workflow_family") or row.get("workflow_order"), 120)
    if workflow == "cheap_preflight_before_broad_test":
        return (
            "Run the cheap preflight before the broad test route.",
            "run_preflight_before_broad_test",
        )
    if workflow == "environment_workaround_before_retry" or kind == "environment_workaround_candidate":
        return (
            "Reopen the prior environment workaround before retrying this route.",
            "reopen_environment_workaround_before_retry",
        )
    if workflow == "context_reopen_before_retry" or kind == "context_reopen_candidate":
        return (
            "Reopen the source trail that previously recovered this route before retrying.",
            "reopen_context_source_before_retry",
        )
    if kind in {"source_backed_do_not_repeat", "do_not_repeat"}:
        return (
            "Reopen the rejected route evidence before repeating this action family.",
            "reopen_rejected_route_before_repeat",
        )
    return (
        "Reopen the prior failure source trail before trying the same route again.",
        "reopen_failure_source_before_retry",
    )


def learning_findings_to_aippo_source_rows(
    findings: Iterable[Mapping[str, Any]],
    *,
    built_at: str = "2026-06-15",
) -> list[dict[str, Any]]:
    """Convert eligible learning findings into AIppo source rows."""

    rows: list[dict[str, Any]] = []
    for finding in findings:
        if not isinstance(finding, Mapping):
            continue
        lesson_row = _source_backed_lesson_to_aippo_row(finding, built_at=built_at)
        if lesson_row:
            rows.append(lesson_row)
            continue
        if str(finding.get("kind") or "") == SOURCE_BACKED_LESSON_KIND:
            continue
        refs = _source_refs(finding.get("source_refs"))
        suppression = _suppression_reason(finding, refs)
        if suppression in {
            "unsupported_learning_finding_kind",
            "expected_tdd_red_review_only",
            "local_only_or_private_boundary",
            "missing_source_refs",
            "low_confidence_one_off",
        }:
            continue
        guidance, next_action = _guidance_for(finding)
        status = "stale" if suppression.endswith("_finding_degraded") else "ripe"
        kind = _finding_kind(finding)
        source_count = int(finding.get("source_ref_count") or len(refs))
        verified_origin = _verified_origin(finding)
        source_supported = verified_origin and source_count >= 2
        row = {
            "clause_id": _text(finding.get("clause_id"), 120)
            or stable_json_tuple_id(
                "learned_clause",
                finding.get("finding_id"),
                kind,
                ensure_ascii=False,
                length=18,
            ),
            "kind": (
                "reopen_first_workflow_clause"
                if kind in REOPEN_FIRST_FINDINGS
                else "workflow_order_clause"
            ),
            "scope": _text(finding.get("scope"), 160) or "project_or_task_family",
            "target_fingerprint": _text(finding.get("target_fingerprint"), 160),
            "path_category_fingerprint": _text(finding.get("path_category_fingerprint"), 160),
            "topic_epoch": _text(finding.get("topic_epoch"), 120) or "learning-loop",
            "workspace_or_environment_profile": _text(
                finding.get("workspace_or_environment_profile"),
                160,
            )
            or "unknown_environment",
            "guidance": guidance,
            "next_action": next_action,
            "applies_when": _strings(
                [
                    finding.get("workflow_family"),
                    finding.get("candidate_family"),
                    finding.get("scope"),
                    "coding",
                    "PR_review",
                ],
                limit=8,
            ),
            "does_not_apply_when": ["unrelated_task", "source_already_visible"],
            "allowed_without_reopen_for": ["low_risk_orientation", "patch_planning"],
            "support_grade": "source_supported" if source_supported else "candidate_only",
            "support_verified": bool(source_supported),
            "source_refs": refs,
            "source_ref_count": source_count,
            "independent_trail_count": int(
                finding.get("independent_trail_count") or min(2, source_count)
            ),
            "support_types": [
                "source_backed_learning_loop",
                *(["workflow_order"] if kind == "workflow_order_finding" else []),
                *(["reopen_first"] if kind in REOPEN_FIRST_FINDINGS else []),
            ],
            "counter_evidence_ref_count": int(finding.get("counter_evidence_ref_count") or 0),
            "path_provenance": "complete" if source_supported else "unverified_origin" if not verified_origin else "gappy",
            "status": status if verified_origin else "blocked",
            "freshness": "current" if status == "ripe" and verified_origin else "stale",
            "built_at": built_at,
            "last_source_seen_at": _text(finding.get("last_source_seen_at"), 40) or built_at,
            "invalidators": _strings(
                finding.get("invalidators")
                or ["newer_source_correction", "resolved_route", "environment_changed"],
                limit=8,
            ),
            "learning_loop": {
                "finding_id": _text(finding.get("finding_id"), 120),
                "finding_kind": kind,
                "navigation_only": True,
                "source_reopen_required_before_claim": True,
                "raw_tool_payload_serialized": False,
                "origin_verified": verified_origin,
                "unverified_origin_blocks_source_supported": not verified_origin,
            },
        }
        rows.append(row)
    return rows


def build_contract_from_learning_findings(
    findings: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    contracts = working_contract.build_aippo_working_contracts(
        learning_findings_to_aippo_source_rows(findings)
    )
    return working_contract.select_aippo_working_contract(contracts)


def build_learning_aippo_bridge_report(
    findings: Iterable[Mapping[str, Any]],
    *,
    task: str = "coding patch before broad test",
    now_unix: float = 1000.0,
) -> dict[str, Any]:
    materialized = [dict(row) for row in findings if isinstance(row, Mapping)]
    rows = learning_findings_to_aippo_source_rows(materialized)
    contract = working_contract.select_aippo_working_contract(
        working_contract.build_aippo_working_contracts(rows)
    )
    activation = working_contract.activation_packet_from_working_contract(contract, task=task)
    cache_report = build_action_hint_cache_report(
        aippo_learned_clauses=contract.get("clauses") or [],
        now_unix=now_unix,
    )
    encoded = json.dumps(
        {"rows": rows, "activation": activation, "cache": cache_report},
        ensure_ascii=False,
        sort_keys=True,
    )
    red_lines = {
        "raw_stdout_stderr_leak_count": int("Traceback PRIVATE_STDOUT" in encoded),
        "raw_command_text_leak_count": int("pytest tests/private_path.py" in encoded),
        "local_path_leak_count": int("C:\\" in encoded or "/Users/" in encoded),
        "source_truth_overclaim_count": int("source_truth" in encoded),
        "raw_private_text_leak_count": int("PRIVATE_ROLLOUT_TEXT" in encoded),
    }
    provider_count = cache_report["provider_counts"].get("aippo_learned_clause", 0)
    return {
        "kind": ADAPTER_REPORT_KIND,
        "schema_version": SCHEMA_VERSION,
        "ok": bool(rows)
        and provider_count > 0
        and all(value == 0 for value in red_lines.values()),
        "source_rows": rows,
        "contract": contract,
        "activation_packet": activation,
        "prepared_cache": cache_report,
        "metrics": {
            "input_finding_count": len(materialized),
            "aippo_source_row_count": len(rows),
            "aippo_learned_clause_count": len(contract.get("clauses") or []),
            "prepared_hint_provider_count": provider_count,
            "foreground_eligible_clause_count": sum(
                1
                for clause in contract.get("clauses") or []
                if isinstance(clause, Mapping)
                and (clause.get("activation") or {}).get("foreground_eligible")
            ),
        },
        "red_lines": red_lines,
        "boundary": {
            "learning_loop_is_navigation_only": True,
            "aippo_owns_clause_lifecycle": True,
            "action_hint_cache_consumes_aippo_provider_not_raw_tool_output": True,
            "source_reopen_required_before_claim": True,
        },
    }


__all__ = [
    "build_contract_from_learning_findings",
    "build_learning_aippo_bridge_report",
    "learning_findings_to_aippo_source_rows",
]
