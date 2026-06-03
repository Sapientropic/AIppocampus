#!/usr/bin/env python3
"""Dry-run shell selection policy for subconscious scheduler runs."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

ShellDecision = Literal[
    "deterministic_only",
    "worker",
    "agent_probe",
    "agent_deep",
    "skip_due_to_backpressure",
]

VALID_DECISIONS: set[str] = {
    "deterministic_only",
    "worker",
    "agent_probe",
    "agent_deep",
    "skip_due_to_backpressure",
}

DEFAULT_TINY_CORPUS_TURNS = 3
DEFAULT_WORKER_MIN_TURNS = 3
DEFAULT_MATURE_CORPUS_TURNS = 48
DEFAULT_MATURE_CORPUS_THREADS = 3
DEFAULT_MAX_BACKLOG_ROWS = 500
DEFAULT_LOW_CONFIDENCE_PRIOR_LIMIT = 2
LOW_CONFIDENCE_PRIOR_THRESHOLD = 0.62

MANUAL_OVERRIDE_SURFACE = [
    "subconscious_worker.py --dry-run/--no-write",
    "subconscious_agent.py --dry-run/--no-write",
    "subconscious_jobs.py --dry-run --job ...",
]
# Private reports are still command output; keep reasons enumerated so local
# env var names and runtime exception text cannot leak into copied JSON/logs.
PRIVATE_REPORT_REASONS = {
    "first_run",
    "no_due_projects",
    "leased_projects",
    "enqueue_cooldown",
    "disabled_by_env",
    "missing_api_key",
}


@dataclass(frozen=True)
class ShellSelectionInput:
    project_label: str
    due_reason: str
    clean_turn_count: int
    clean_message_count: int
    thread_count: int
    staging_backlog_rows: int = 0
    low_confidence_prior_count: int = 0
    concept_graph_edge_count: int = 0


def _safe_count(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _row_mentions_project(row: dict[str, Any], project_label: str) -> bool:
    if not project_label:
        return True
    if str(row.get("project_label") or "") == project_label:
        return True
    for ref in row.get("source_refs") or []:
        if isinstance(ref, dict) and str(ref.get("project_label") or "") == project_label:
            return True
    return False


def staging_signals(root: Path, project_label: str) -> dict[str, int]:
    """Read only queue-shape signals; never expose source text or local paths."""

    backlog = 0
    low_confidence_prior = 0
    for path in (root / "subconscious_edges.jsonl", root / "subconscious_jobs.jsonl"):
        if not path.exists():
            continue
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for line in lines:
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(row, dict) or not _row_mentions_project(row, project_label):
                continue
            if row.get("status") in {None, "staging"}:
                backlog += 1
            if (
                row.get("source") == "deepseek_subconscious"
                and _safe_float(row.get("confidence")) < LOW_CONFIDENCE_PRIOR_THRESHOLD
            ):
                low_confidence_prior += 1
    return {
        "staging_backlog_rows": backlog,
        "low_confidence_prior_count": low_confidence_prior,
    }


def scheduler_project_report(
    stats: Any,
    reason: str,
    *,
    root: Path,
    override: str | None,
) -> dict[str, Any]:
    signals = staging_signals(root, str(stats.label))
    selection_input = ShellSelectionInput(
        project_label=str(stats.label),
        due_reason=reason,
        clean_turn_count=_safe_count(stats.clean_turn_count),
        clean_message_count=_safe_count(stats.clean_message_count),
        thread_count=_safe_count(stats.thread_count),
        staging_backlog_rows=signals["staging_backlog_rows"],
        low_confidence_prior_count=signals["low_confidence_prior_count"],
    )
    return {
        "label": str(stats.label),
        "reason": reason,
        "shell_selection": select_shell(selection_input, override=override),
    }


def private_scheduler_report_payload(
    result: Mapping[str, Any],
    public_payload: Mapping[str, Any],
) -> dict[str, Any]:
    payload = dict(public_payload)
    projects: list[dict[str, Any]] = []
    for project in result.get("projects") or []:
        if not isinstance(project, dict):
            continue
        row: dict[str, Any] = {
            "label": str(project.get("label") or ""),
            "reason": _private_report_reason(project.get("reason")),
        }
        selection = project.get("shell_selection")
        if isinstance(selection, dict):
            row["shell_selection"] = selection
        projects.append(row)
    if projects:
        payload["projects"] = projects
    return payload


def _private_report_reason(value: Any) -> str:
    reason = str(value or "").strip()
    if reason.startswith("new_turns:"):
        suffix = reason.removeprefix("new_turns:")
        return f"new_turns:{_safe_count(suffix)}"
    if reason.startswith("missing_"):
        return "missing_api_key"
    return reason if reason in PRIVATE_REPORT_REASONS else ("runtime_reason_redacted" if reason else "")


def _safe_float(value: Any) -> float:
    try:
        return max(0.0, float(value or 0.0))
    except (TypeError, ValueError):
        return 0.0


def select_shell(
    inputs: ShellSelectionInput,
    *,
    override: str | None = None,
) -> dict[str, Any]:
    reasons: list[str] = []
    override_value = str(override or "auto").strip()
    overridden = override_value not in {"", "auto"}
    if overridden and override_value in VALID_DECISIONS:
        decision: ShellDecision = override_value  # type: ignore[assignment]
        reasons.append("manual_override")
    else:
        if overridden:
            reasons.append("invalid_manual_override_ignored")
        if inputs.staging_backlog_rows > DEFAULT_MAX_BACKLOG_ROWS:
            decision = "skip_due_to_backpressure"
            reasons.append("staging_backlog_high")
        elif inputs.clean_turn_count < DEFAULT_TINY_CORPUS_TURNS:
            decision = "deterministic_only"
            reasons.append("tiny_corpus")
        elif inputs.low_confidence_prior_count >= DEFAULT_LOW_CONFIDENCE_PRIOR_LIMIT:
            decision = "agent_probe"
            reasons.append("low_confidence_prior_worker_output")
        elif (
            inputs.clean_turn_count >= DEFAULT_MATURE_CORPUS_TURNS
            and inputs.thread_count >= DEFAULT_MATURE_CORPUS_THREADS
        ):
            decision = "agent_probe"
            reasons.append("mature_multi_thread_corpus")
        elif inputs.clean_turn_count >= DEFAULT_WORKER_MIN_TURNS:
            decision = "worker"
            reasons.append("ordinary_due_corpus")
        else:
            decision = "deterministic_only"
            reasons.append("insufficient_semantic_source")

    if decision == "agent_deep" and not overridden:
        # Keep deep runs behind explicit operator budget until cost/quality
        # evidence exists; policy reports can recommend probes but must not
        # silently grow into expensive autonomous agents.
        decision = "agent_probe"
        reasons.append("deep_agent_requires_manual_budget")

    return {
        "decision": decision,
        "reasons": reasons,
        "overridden": overridden and override_value in VALID_DECISIONS,
        "signals": {
            "clean_turn_count": _safe_count(inputs.clean_turn_count),
            "clean_message_count": _safe_count(inputs.clean_message_count),
            "thread_count": _safe_count(inputs.thread_count),
            "staging_backlog_rows": _safe_count(inputs.staging_backlog_rows),
            "low_confidence_prior_count": _safe_count(inputs.low_confidence_prior_count),
            "concept_graph_edge_count": _safe_count(inputs.concept_graph_edge_count),
        },
        "will_start_expensive_agent": False,
        "authority_boundary": "dry_run_report_only; staging_candidates_not_formal_truth",
        "budget_boundary": "agent_probe_or_deep_requires_explicit_operator_run_before_execution",
        "manual_override_surface": MANUAL_OVERRIDE_SURFACE,
    }
