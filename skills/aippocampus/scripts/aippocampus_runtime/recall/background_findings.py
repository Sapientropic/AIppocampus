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
from aippocampus_runtime.contracts import foreground_recovery_card, foreground_shell_action
from aippocampus_runtime.dream import working_memory_publication
from aippocampus_runtime.privacy import redact_private_paths, redact_sensitive_values
from aippocampus_runtime.recall import background_finding_actions, background_finding_projection
from aippocampus_runtime.subconscious import candidate_router

DEFAULT_BACKGROUND_FINDINGS_LIMIT = 4


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
        "route": row.get("route"),
        "ask_policy": row.get("ask_policy"),
        "project_label": row.get("project_label"),
        "review_state": row.get("review_state"),
        "dream_function": row.get("dream_function"),
        "boundary": _finding_boundary(row),
        "source": background_finding_actions.source_summary(row),
        "next_actions": background_finding_actions.finding_next_actions(row, cue=cue),
    }


def background_findings_card(
    cue: str,
    *,
    registry_dir: str | Path | None = None,
    working_memory_path: str | Path | None = None,
    project: str | None = "AIppocampus",
    limit: int = DEFAULT_BACKGROUND_FINDINGS_LIMIT,
) -> dict[str, Any]:
    task = str(cue or "").strip()
    if not task:
        return foreground_recovery_card(
            kind="aippocampus_background_findings_card",
            status="needs_input",
            error_code="background_cue_required",
            message="agent background needs a task cue before it can match reviewed background findings.",
            safe_next_actions=[
                foreground_shell_action(
                    action_id="background_for_task_cue",
                    label="Ask for reviewed background findings",
                    command='aippocampus agent background "task cue" --json',
                    why="Use this for reviewed Dream/subconscious navigation relevant to the current task.",
                    mutation_risk="read_only",
                    claim_boundary="background_navigation_not_source_truth",
                ),
                foreground_shell_action(
                    action_id="ordinary_recall",
                    label="Use ordinary source-backed recall",
                    command='aippocampus agent recall "old decision or handoff cue" --json',
                    why="Use recall when source routes matter more than background navigation scent.",
                    mutation_risk="read_only",
                    claim_boundary="no_claim_before_reopen",
                ),
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
    primary_action = (
        findings[0]["next_actions"][0]
        if findings
        else foreground_shell_action(
            action_id="ordinary_recall",
            label="Use ordinary source-backed recall",
            command=f"aippocampus agent recall {background_finding_actions.shell_quote(task)} --json",
            why="No reviewed background finding matched; use ordinary recall/search before claims.",
            mutation_risk="read_only",
            claim_boundary="no_claim_before_reopen",
        )
    )
    payload = {
        "kind": "aippocampus_background_findings_card",
        "ok": True,
        "status": "ok" if findings else "no_relevant_background_findings",
        "mode": "background",
        "surface": "agent_background",
        "cue_used": task,
        "finding_count": len(findings),
        "findings": findings,
        "agent_next_action": primary_action,
        "safe_next_actions": [dict(primary_action)],
        "reader_diagnostic": {
            "status": diagnostic.get("status"),
            "row_count": diagnostic.get("row_count"),
            "invalid_line_count": diagnostic.get("invalid_line_count"),
            "writer_in_progress": diagnostic.get("writer_in_progress"),
            "diagnostics": diagnostic.get("diagnostics") or [],
            "path_emitted": False,
        },
        "boundary": {
            "background_findings_are_source_truth": False,
            "dream_findings_are_fact": False,
            "subconscious_rows_are_fact": False,
            "navigation_only_until_source_reopened": True,
            "raw_private_text_emitted": False,
            "raw_local_paths_emitted": False,
        },
        "operator_detail": {
            "working_memory_path_label": "registry/working_memory.jsonl",
            "full_review_sources": [
                "skills/aippocampus/references/subconscious-jobs.md",
                "docs/research/dream-task-design.md",
            ],
        },
    }
    return _public_payload(payload)


def background_recovery_card(command: str) -> dict[str, Any]:
    label = "Dream" if command == "dream" else "Subconscious"
    return foreground_recovery_card(
        kind="aippocampus_background_route_recovery",
        status="use_foreground_route",
        error_code=f"{command}_is_not_a_foreground_command",
        message=(
            f"{label} work is surfaced through reviewed foreground background findings, "
            "not a broad operator command."
        ),
        safe_next_actions=[
            foreground_shell_action(
                action_id="agent_background",
                label="Find reviewed background guidance",
                command='aippocampus agent background "task cue" --json',
                why="Shows bounded reviewed Dream/subconscious findings relevant to a task cue.",
                mutation_risk="read_only",
                claim_boundary="background_navigation_not_source_truth",
            ),
            foreground_shell_action(
                action_id="ordinary_recall",
                label="Use ordinary recall",
                command='aippocampus agent recall "old decision or handoff cue" --json',
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
