"""Foreground projection for reviewed background findings.

Dream/subconscious rows are useful navigation scent, but they are not source
truth. This module gives agents one small foreground card over already reviewed
working-memory rows without exposing raw model text, local paths, or source
windows. Keep it as a projection layer over the existing working-memory
substrate; do not turn Dream into a parallel recall authority.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from aippocampus_runtime import core
from aippocampus_runtime.contracts import (
    canonical_foreground_action_fields,
    foreground_recovery_card,
    foreground_shell_action,
    foreground_template_action,
)
from aippocampus_runtime.dream import working_memory_publication
from aippocampus_runtime.privacy import redact_private_paths, redact_sensitive_values
from aippocampus_runtime.recall import background_finding_actions, background_finding_projection
from aippocampus_runtime.subconscious import candidate_router

DEFAULT_BACKGROUND_FINDINGS_LIMIT = 4
BACKGROUND_FINDING_DETAIL_LEVELS = {"compact", "detail", "full", "operator"}


def _mcp_background_for_task_action() -> dict[str, Any]:
    return {
        "id": "background_for_task_cue",
        "tool_name": "agent_background",
        "command_template": 'aippocampus agent background "{task_cue}" --json',
        "arguments_template": {"task": "{task_cue}"},
        "requires": ["task_cue"],
        "template_only": True,
        "mutation_risk": "read_only",
        "claim_boundary": "background_navigation_not_source_truth",
        "label": "Ask for reviewed background findings",
        "why": "Use this for reviewed Dream/subconscious navigation relevant to the current task.",
        "cli_fallback": {
            "id": "background_for_task_cue_cli_fallback",
            "command_template": 'aippocampus agent background "{task_cue}" --json',
            "template_only": True,
            "requires": ["task_cue"],
            "mutation_risk": "read_only",
            "claim_boundary": "background_navigation_not_source_truth",
        },
    }


def _mcp_ordinary_recall_action() -> dict[str, Any]:
    return {
        "id": "ordinary_recall",
        "tool_name": "agent_recall",
        "command_template": 'aippocampus agent recall "{old_decision_or_handoff_cue}" --json',
        "arguments_template": {"query": "{old_decision_or_handoff_cue}"},
        "requires": ["old_decision_or_handoff_cue"],
        "template_only": True,
        "mutation_risk": "read_only",
        "claim_boundary": "no_claim_before_reopen",
        "label": "Ordinary source-backed recall",
        "why": "Recall is the source route when background navigation scent is not enough.",
        "cli_fallback": {
            "id": "ordinary_recall_cli_fallback",
            "command_template": 'aippocampus agent recall "{old_decision_or_handoff_cue}" --json',
            "template_only": True,
            "requires": ["old_decision_or_handoff_cue"],
            "mutation_risk": "read_only",
            "claim_boundary": "no_claim_before_reopen",
        },
    }


def _public_payload(payload: Any) -> Any:
    return redact_sensitive_values(redact_private_paths(payload))


def _registry_dir(value: str | Path | None) -> Path | None:
    if value is None or str(value).strip() == "":
        return None
    return Path(value).expanduser().resolve()


def _working_memory_path(
    *,
    registry_dir: str | Path | None = None,
    working_memory_path: str | Path | None = None,
) -> Path:
    if working_memory_path is not None and str(working_memory_path).strip():
        return Path(working_memory_path).expanduser().resolve()
    return candidate_router.default_working_memory_path(registry_dir=_registry_dir(registry_dir))


def _finding_surface(row: Mapping[str, Any]) -> str:
    return (
        "dream_working_memory"
        if row.get("candidate_type") == "dream_hypothesis"
        else "subconscious_working_memory"
    )


def _finding_boundary(row: Mapping[str, Any]) -> dict[str, Any]:
    is_dream = row.get("candidate_type") == "dream_hypothesis"
    return {
        "authority": (
            str(row.get("truth_boundary") or "adjudicated_dream_hypothesis_not_fact")
            if is_dream
            else "reviewed_working_memory_navigation_not_fact"
        ),
        "action_grammar": background_finding_actions.route_action_grammar(row),
        "navigation_only": True,
        "source_backed_claim_allowed": False,
        "source_reopen_required_before_claims": True,
    }


def _project_finding(row: Mapping[str, Any], *, cue: str, index: int) -> dict[str, Any]:
    use = row.get("dream_hypothesis_use")
    use_map = use if isinstance(use, Mapping) else {}
    projection = background_finding_projection.projection_fields(row)
    return {
        "index": index,
        "finding_id": str(row.get("candidate_key") or f"background:{index}"),
        "surface": _finding_surface(row),
        "finding_type": str(row.get("candidate_type") or "working_memory"),
        **projection,
        "why_it_may_matter_now": core.compact_text(
            str(
                row.get("route_reason")
                or use_map.get("reason")
                or "Matched reviewed background working-memory terms for this cue."
            ),
            220,
        ),
        "score": row.get("score"),
        "confidence": row.get("confidence"),
        "match_strength": row.get("match_strength"),
        "distinctive_match_count": row.get("distinctive_match_count"),
        "generic_only_match": bool(row.get("generic_only_match")),
        "route": row.get("route"),
        "ask_policy": row.get("ask_policy"),
        "project_label": row.get("project_label"),
        "review_state": row.get("review_state"),
        "dream_function": row.get("dream_function"),
        "boundary": _finding_boundary(row),
        "source": background_finding_actions.source_summary(row),
        "next_actions": background_finding_actions.finding_next_actions(row, cue=cue),
    }


def _normalize_detail(value: str | None) -> str:
    detail = str(value or "compact").strip().casefold()
    return detail if detail in BACKGROUND_FINDING_DETAIL_LEVELS else "compact"


def _read_only_actions(finding: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [
        dict(action)
        for action in finding.get("next_actions") or []
        if isinstance(action, Mapping) and action.get("mutation_risk") == "read_only"
    ]


def _compact_action(action: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in action.items()
        if key
        in {
            "id",
            "label",
            "command",
            "command_template",
            "requires",
            "template_only",
            "mutation_risk",
            "claim_boundary",
            "why",
            "tool_name",
            "arguments",
            "arguments_template",
        }
        and value not in (None, "", [], {})
    }


def _finding_summary(finding: Mapping[str, Any], *, detail_level: str = "compact") -> dict[str, Any]:
    boundary_raw = finding.get("boundary")
    boundary: Mapping[str, Any] = boundary_raw if isinstance(boundary_raw, Mapping) else {}
    source_raw = finding.get("source")
    source: Mapping[str, Any] = source_raw if isinstance(source_raw, Mapping) else {}
    if detail_level == "compact":
        pairs = {
            "index": finding.get("index"),
            "finding_id": finding.get("finding_id"),
            "finding_title": finding.get("finding_title"),
            "matched_terms": finding.get("matched_terms"),
            "match_strength": finding.get("match_strength"),
            "distinctive_match_count": finding.get("distinctive_match_count"),
            "why_it_may_matter_now": finding.get("why_it_may_matter_now"),
            "source_ref_count": source.get("source_ref_count"),
            "source_finding_count": source.get("source_finding_count"),
        }
        return {key: value for key, value in pairs.items() if value not in (None, "", [])}
    pairs = {
        "index": finding.get("index"),
        "finding_id": finding.get("finding_id"),
        "surface": finding.get("surface"),
        "finding_type": finding.get("finding_type"),
        "shape_label": finding.get("shape_label"),
        "finding_title": finding.get("finding_title"),
        "match_reason": finding.get("match_reason"),
        "matched_terms": finding.get("matched_terms"),
        "match_strength": finding.get("match_strength"),
        "distinctive_match_count": finding.get("distinctive_match_count"),
        "why_it_may_matter_now": finding.get("why_it_may_matter_now"),
        "confidence": finding.get("confidence"),
        "review_state": finding.get("review_state"),
        "source_ref_count": source.get("source_ref_count"),
        "source_finding_count": source.get("source_finding_count"),
        "use_boundary": {
            "use": "navigation_only",
            "before_claiming": "reopen_source_route",
            "action_grammar": boundary.get("action_grammar") or "reopenable_route",
        },
    }
    return {key: value for key, value in pairs.items() if value not in (None, "", [])}


def _detail_finding(finding: Mapping[str, Any]) -> dict[str, Any]:
    projected = dict(finding)
    projected["next_actions"] = _read_only_actions(finding)
    return projected


def _action_grammar_for_finding(finding: Mapping[str, Any]) -> str:
    boundary = finding.get("boundary")
    boundary_map = boundary if isinstance(boundary, Mapping) else {}
    return str(boundary_map.get("action_grammar") or "").strip()


def _reopenable_first(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        findings,
        key=lambda finding: (
            0 if _action_grammar_for_finding(finding) == "reopenable_route" else 1,
            int(finding.get("index") or 0),
        ),
    )


def background_findings_card(
    cue: str,
    *,
    registry_dir: str | Path | None = None,
    working_memory_path: str | Path | None = None,
    project: str | None = "AIppocampus",
    limit: int = DEFAULT_BACKGROUND_FINDINGS_LIMIT,
    detail: str = "compact",
    prefer_reopenable: bool = False,
) -> dict[str, Any]:
    task = str(cue or "").strip()
    if not task:
        return foreground_recovery_card(
            kind="aippocampus_background_findings_card",
            status="needs_input",
            error_code="background_cue_required",
            message="agent background needs a task cue before it can match reviewed background findings.",
            safe_next_actions=[
                _mcp_background_for_task_action(),
                _mcp_ordinary_recall_action(),
            ],
        )

    path = _working_memory_path(registry_dir=registry_dir, working_memory_path=working_memory_path)
    rows, diagnostic = working_memory_publication.load_working_memory_with_diagnostics(path)
    bounded_limit = max(1, min(int(limit or DEFAULT_BACKGROUND_FINDINGS_LIMIT), 12))
    matches = candidate_router.match_working_memory(
        task,
        rows,
        project_label=project or None,
        limit=bounded_limit,
    )
    findings = [
        _project_finding(row, cue=task, index=index)
        for index, row in enumerate(matches, start=1)
    ]
    if prefer_reopenable:
        findings = _reopenable_first(findings)
    primary_action = (
        findings[0]["next_actions"][0]
        if findings
        else foreground_shell_action(
            action_id="ordinary_recall",
            label="Ordinary source-backed recall",
            command=f"aippocampus agent recall {background_finding_actions.shell_quote(task)} --json",
            why="No reviewed background finding matched; ordinary recall/search remains the source route before claims.",
            mutation_risk="read_only",
            claim_boundary="no_claim_before_reopen",
        )
    )
    detail_level = _normalize_detail(detail)
    finding_summaries = [
        _finding_summary(finding, detail_level=detail_level) for finding in findings[:3]
    ]
    best_finding = finding_summaries[0] if finding_summaries else None
    compact_other_summaries = finding_summaries[1:] if detail_level == "compact" else finding_summaries
    action_fields = canonical_foreground_action_fields(
        primary_action,
        safe_next_actions=[primary_action],
    )
    if detail_level == "compact":
        action_fields.pop("foreground_action_contract", None)
        foreground_action = action_fields.get("foreground_action")
        if isinstance(foreground_action, Mapping):
            action_fields["foreground_action"] = _compact_action(foreground_action)
        raw_safe_next_actions = action_fields.get("safe_next_actions")
        safe_next_actions = raw_safe_next_actions if isinstance(raw_safe_next_actions, list) else []
        action_fields["safe_next_actions"] = [
            _compact_action(action)
            for action in safe_next_actions
            if isinstance(action, Mapping)
        ]
    payload = {
        "kind": "aippocampus_background_findings_card",
        "detail": detail_level,
        "ok": True,
        "status": "ok" if findings else "no_relevant_background_findings",
        "mode": "background",
        "surface": "agent_background",
        "finding_count": len(findings),
        "best_finding": best_finding,
        "finding_summaries": compact_other_summaries,
        **action_fields,
    }
    if detail_level != "compact":
        payload.update(
            {
                "cue_used": task,
                "boundary": {
                    "background_findings_are_source_truth": False,
                    "dream_findings_are_fact": False,
                    "subconscious_rows_are_fact": False,
                    "navigation_only_until_source_reopened": True,
                    "raw_private_text_emitted": False,
                    "raw_local_paths_emitted": False,
                },
                "operator_detail_command": (
                    "aippocampus agent background "
                    f"{background_finding_actions.shell_quote(task)} --json --detail full"
                ),
                "output_boundary": "detail_no_reader_or_operator_diagnostics",
            }
        )
    if detail_level == "detail":
        detail_findings = [_detail_finding(finding) for finding in findings]
        detail_summaries = [
            _finding_summary(finding, detail_level=detail_level)
            for finding in detail_findings[:3]
        ]
        payload["best_finding"] = detail_summaries[0] if detail_summaries else None
        payload["finding_summaries"] = detail_summaries
        payload["findings"] = detail_findings
        payload["output_boundary"] = "detail_no_feedback_write_actions"
    if detail_level in {"full", "operator"}:
        payload.update(
            {
                "findings": findings,
                "reader_diagnostic": {
                    "status": diagnostic.get("status"),
                    "row_count": diagnostic.get("row_count"),
                    "invalid_line_count": diagnostic.get("invalid_line_count"),
                    "writer_in_progress": diagnostic.get("writer_in_progress"),
                    "diagnostics": diagnostic.get("diagnostics") or [],
                    "path_emitted": False,
                },
                "operator_detail": {
                    "working_memory_path_label": "registry/working_memory.jsonl",
                    "full_review_sources": [
                        "skills/aippocampus/references/subconscious-jobs.md",
                        "docs/research/dream-task-design.md",
                    ],
                },
                "output_boundary": (
                    "local_operator_diagnostic_redacted"
                    if detail_level == "operator"
                    else "local_full_diagnostic_redacted"
                ),
            }
        )
    return _public_payload(payload)


def background_recovery_card(command: str) -> dict[str, Any]:
    label = "Dream" if command == "dream" else "Subconscious"
    return foreground_recovery_card(
        kind="aippocampus_background_route_recovery",
        status="use_foreground_route",
        error_code=f"{command}_is_not_a_foreground_command",
        message=(
            f"{label} output belongs in reviewed foreground background findings, "
            "not broad operator mode."
        ),
        safe_next_actions=[
            foreground_template_action(
                action_id="agent_background",
                label="Find reviewed background guidance",
                command_template='aippocampus agent background "{task_cue}" --json',
                requires=["task_cue"],
                why="Shows bounded reviewed Dream/subconscious findings relevant to a task cue.",
                mutation_risk="read_only",
                claim_boundary="background_navigation_not_source_truth",
            ),
            foreground_template_action(
                action_id="ordinary_recall",
                label="Use ordinary recall",
                command_template='aippocampus agent recall "{cue}" --json',
                requires=["cue"],
                why="Use source-backed recall when factual continuity is needed.",
                mutation_risk="read_only",
                claim_boundary="no_claim_before_reopen",
            ),
            foreground_shell_action(
                action_id="observatory_summary",
                label="Read route-readiness summary",
                command="aippocampus observatory --summary-json",
                why="Use observatory for read-only aggregate background readiness, not facts.",
                mutation_risk="read_only",
                claim_boundary="operator_diagnostic_not_source_evidence",
            ),
        ],
    )
