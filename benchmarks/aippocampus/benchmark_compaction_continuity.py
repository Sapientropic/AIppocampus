#!/usr/bin/env python3
"""Deterministic Track D compaction-continuity benchmark.

This runner uses synthetic correction/outcome events to test whether continuity
anchors would be preserved, suppressed, or rehydrated across simulated visible,
post-compaction, and horizon-lost states. It does not exercise a live Codex host,
real hooks, or live semantic adjudication.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import _paths

_paths.ensure_paths()

import correction_reconsolidation as corr

SCHEMA_VERSION = corr.SCHEMA_VERSION
HOOK_STAGES = corr.HOOK_STAGES
COMPACTION_STATES = corr.COMPACTION_STATES
ADJUDICATION_STATUSES = corr.ADJUDICATION_STATUSES
HIGH_RISK_COVERAGE_CELLS = (
    ("PostCompact", "horizon_lost", "valid_adopted"),
    ("PostCompact", "horizon_lost", "valid_ignored"),
    ("PostCompact", "horizon_lost", "refuted"),
    ("PostCompact", "horizon_lost", "superseded"),
    ("PostCompact", "horizon_lost", "uncertain"),
)
SECRET_OR_PATH_RE = re.compile(
    r"(?i)(api[_-]?key|authorization|bearer\s+[a-z0-9._-]{8,}|password|secret|token)"
    r"|([a-z]:\\[^ \n\r\t]+)"
    r"|([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})"
)


@dataclass(frozen=True)
class FixtureEvent:
    event_id: str
    event_type: str
    hook_stage: str
    source_ref: str
    text: str
    related_event_id: str | None = None

    def sanitized(self, *, include_private_text: bool) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "event_id_sha1": sha1_text(self.event_id)[:16],
            "event_type": self.event_type,
            "hook_stage": self.hook_stage,
            "source_ref_sha1": sha1_text(self.source_ref)[:16],
            "text_sha1": sha1_text(self.text)[:16],
            "related_event_id_sha1": (
                sha1_text(self.related_event_id)[:16]
                if self.related_event_id
                else None
            ),
        }
        if include_private_text:
            payload.update({"source_ref": self.source_ref, "text": self.text})
        return payload


@dataclass(frozen=True)
class TrackDCase:
    case_id: str
    thread_id: str
    case_type: str
    hook_stage: str
    compaction_state: str
    adjudication_status: str
    correction_text: str
    source_ref: str
    correction_event_id: str
    source_event_id: str
    fixture_events: tuple[FixtureEvent, ...]
    anchor_relevant: bool
    visible_context_has_source: bool
    expected_emit: bool
    expected_anchor_recall: bool = False
    anchor_already_injected: bool = False
    expects_source_fidelity: bool = True

    def expected_action(self) -> str:
        if self.expected_emit:
            return "rehydrate_anchor" if self.compaction_state == "horizon_lost" else "surface_anchor"
        if self.adjudication_status == "uncertain":
            return "confirm_when_relevant"
        return "suppress"

    def event_index(self) -> dict[str, FixtureEvent]:
        return {event.event_id: event for event in self.fixture_events}

    def event_chain_valid(self) -> bool:
        event_index = self.event_index()
        correction_event = event_index.get(self.correction_event_id)
        source_event = event_index.get(self.source_event_id)
        if not correction_event or not source_event:
            return False
        if source_event.event_id == correction_event.event_id:
            return True
        return source_event.related_event_id == correction_event.event_id

    def to_result_stub(self, *, include_private_text: bool = False) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "case_id_sha1": sha1_text(self.case_id)[:16],
            "thread_id_sha1": sha1_text(self.thread_id)[:16],
            "case_family": self.case_type,
            "case_type": self.case_type,
            "hook_stage": self.hook_stage,
            "context_state": self.compaction_state,
            "compaction_state": self.compaction_state,
            "expected_adjudication": self.adjudication_status,
            "mocked_adjudication": self.adjudication_status,
            "adjudication_status": self.adjudication_status,
            "anchor_relevant": self.anchor_relevant,
            "visible_context_has_source": self.visible_context_has_source,
            "expected_action": self.expected_action(),
            "expected_emit": self.expected_emit,
            "expected_anchor_recall": self.expected_anchor_recall,
            "prompt_sha1": sha1_text(self.correction_text)[:16],
            "anchor_sha1": sha1_text(self.source_event_id)[:16],
            "correction_event_id_sha1": sha1_text(self.correction_event_id)[:16],
            "source_event_id_sha1": sha1_text(self.source_event_id)[:16],
            "source_ref_sha1": sha1_text(self.source_ref)[:16],
            "fixture_event_count": len(self.fixture_events),
            "fixture_event_types": sorted(
                {event.event_type for event in self.fixture_events}
            ),
            "fixture_events": [
                event.sanitized(include_private_text=include_private_text)
                for event in self.fixture_events
            ],
            "anchor_already_injected": self.anchor_already_injected,
            "current_topic_epoch_sha1": sha1_text(f"{self.thread_id}:epoch:1")[:16],
        }
        if include_private_text:
            payload.update(
                {
                    "case_id": self.case_id,
                    "thread_id": self.thread_id,
                    "correction_text": self.correction_text,
                    "source_ref": self.source_ref,
                    "correction_event_id": self.correction_event_id,
                    "source_event_id": self.source_event_id,
                }
            )
        return payload


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha1_text(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8", errors="replace")).hexdigest()


def looks_sensitive(value: str) -> bool:
    return bool(SECRET_OR_PATH_RE.search(value))


def make_case(
    *,
    case_id: str,
    case_type: str,
    hook_stage: str,
    compaction_state: str,
    adjudication_status: str,
    correction_text: str,
    source_ref: str,
    anchor_relevant: bool,
    visible_context_has_source: bool,
    expected_emit: bool,
    expected_anchor_recall: bool = False,
    anchor_already_injected: bool = False,
    outcome_text: str | None = None,
) -> TrackDCase:
    thread_id = f"track-d-thread:{case_id}"
    correction_event_id = f"{case_id}:correction"
    outcome_event_id = f"{case_id}:outcome"
    correction_event = FixtureEvent(
        event_id=correction_event_id,
        event_type="correction_activation_event",
        hook_stage=hook_stage,
        source_ref=source_ref,
        text=correction_text,
    )
    outcome_event = FixtureEvent(
        event_id=outcome_event_id,
        event_type="correction_outcome_event",
        hook_stage=hook_stage,
        source_ref=f"{source_ref}:outcome",
        text=outcome_text
        or f"Mock adjudication {adjudication_status} for {case_type}.",
        related_event_id=correction_event_id,
    )
    return TrackDCase(
        case_id=case_id,
        thread_id=thread_id,
        case_type=case_type,
        hook_stage=hook_stage,
        compaction_state=compaction_state,
        adjudication_status=adjudication_status,
        correction_text=correction_text,
        source_ref=source_ref,
        correction_event_id=correction_event_id,
        source_event_id=outcome_event_id,
        fixture_events=(correction_event, outcome_event),
        anchor_relevant=anchor_relevant,
        visible_context_has_source=visible_context_has_source,
        expected_emit=expected_emit,
        expected_anchor_recall=expected_anchor_recall,
        anchor_already_injected=anchor_already_injected,
    )


def fixture_cases() -> list[TrackDCase]:
    return [
        make_case(
            case_id="track_d_user_prompt_activation",
            case_type="activation_event",
            hook_stage="UserPromptSubmit",
            compaction_state="visible",
            adjudication_status="uncertain",
            correction_text="User corrects the agent's default route before work begins.",
            source_ref="thread:track-d-demo#line:11",
            anchor_relevant=True,
            visible_context_has_source=True,
            expected_emit=False,
        ),
        make_case(
            case_id="track_d_pre_tool_unrelated",
            case_type="unrelated_pre_tool_use",
            hook_stage="PreToolUse",
            compaction_state="post_compaction",
            adjudication_status="valid_adopted",
            correction_text="Do not touch generated files during this task.",
            source_ref="thread:track-d-demo#line:20",
            anchor_relevant=False,
            visible_context_has_source=False,
            expected_emit=False,
        ),
        make_case(
            case_id="track_d_pre_tool_relevant_ignored",
            case_type="relevant_pre_tool_use",
            hook_stage="PreToolUse",
            compaction_state="horizon_lost",
            adjudication_status="valid_ignored",
            correction_text="The user narrowed scope to docs only, but a code edit is pending.",
            source_ref="thread:track-d-demo#line:31",
            anchor_relevant=True,
            visible_context_has_source=False,
            expected_emit=True,
            expected_anchor_recall=True,
        ),
        make_case(
            case_id="track_d_post_tool_evidence_capture",
            case_type="outcome_evidence_capture",
            hook_stage="PostToolUse",
            compaction_state="visible",
            adjudication_status="valid_adopted",
            correction_text="The test output confirmed the user's correction.",
            source_ref="thread:track-d-demo#line:42",
            anchor_relevant=True,
            visible_context_has_source=True,
            expected_emit=False,
        ),
        make_case(
            case_id="track_d_subagent_start_scope",
            case_type="subagent_anchor_propagation",
            hook_stage="SubagentStart",
            compaction_state="horizon_lost",
            adjudication_status="valid_adopted",
            correction_text="Delegated work must preserve the accepted docs-only scope.",
            source_ref="thread:track-d-demo#line:55",
            anchor_relevant=True,
            visible_context_has_source=False,
            expected_emit=True,
            expected_anchor_recall=True,
        ),
        make_case(
            case_id="track_d_subagent_stop_refuted",
            case_type="subagent_refuted_claim",
            hook_stage="SubagentStop",
            compaction_state="post_compaction",
            adjudication_status="refuted",
            correction_text="A delegated claim contradicted the test evidence.",
            source_ref="thread:track-d-demo#line:63",
            anchor_relevant=True,
            visible_context_has_source=False,
            expected_emit=False,
        ),
        make_case(
            case_id="track_d_stop_enqueue_local",
            case_type="stop_local_only_outcome",
            hook_stage="Stop",
            compaction_state="post_compaction",
            adjudication_status="local_only",
            correction_text="The branch-only workaround should expire with this task.",
            source_ref="thread:track-d-demo#line:78",
            anchor_relevant=True,
            visible_context_has_source=False,
            expected_emit=False,
        ),
        make_case(
            case_id="track_d_precompact_flush",
            case_type="precompact_flush",
            hook_stage="PreCompact",
            compaction_state="post_compaction",
            adjudication_status="valid_adopted",
            correction_text="Flush the accepted route correction before context rewrite.",
            source_ref="thread:track-d-demo#line:89",
            anchor_relevant=True,
            visible_context_has_source=False,
            expected_emit=False,
        ),
        make_case(
            case_id="track_d_postcompact_visible_echo",
            case_type="visible_context_echo_noise",
            hook_stage="PostCompact",
            compaction_state="visible",
            adjudication_status="valid_adopted",
            correction_text="The accepted correction is still visible; do not repeat it.",
            source_ref="thread:track-d-demo#line:101",
            anchor_relevant=True,
            visible_context_has_source=True,
            expected_emit=False,
        ),
        make_case(
            case_id="track_d_postcompact_rehydrate",
            case_type="post_compaction_anchor_recall",
            hook_stage="PostCompact",
            compaction_state="horizon_lost",
            adjudication_status="valid_adopted",
            correction_text="The accepted route correction disappeared after compaction.",
            source_ref="thread:track-d-demo#line:117",
            anchor_relevant=True,
            visible_context_has_source=False,
            expected_emit=True,
            expected_anchor_recall=True,
        ),
        make_case(
            case_id="track_d_rejected_route_after_compaction_warning",
            case_type="rejected_route_after_compaction_warning",
            hook_stage="PostCompact",
            compaction_state="horizon_lost",
            adjudication_status="valid_ignored",
            correction_text="The registry import route was rejected; warn before trying it again.",
            source_ref="thread:track-d-demo#line:121",
            anchor_relevant=True,
            visible_context_has_source=False,
            expected_emit=True,
            expected_anchor_recall=True,
        ),
        make_case(
            case_id="track_d_rejected_route_visible_silent",
            case_type="rejected_route_visible_silent",
            hook_stage="PostCompact",
            compaction_state="visible",
            adjudication_status="valid_ignored",
            correction_text="The rejected route is still visible, so repeating it would be noise.",
            source_ref="thread:track-d-demo#line:124",
            anchor_relevant=True,
            visible_context_has_source=True,
            expected_emit=False,
        ),
        make_case(
            case_id="track_d_postcompact_refuted_stale",
            case_type="refuted_stale_anchor",
            hook_stage="PostCompact",
            compaction_state="horizon_lost",
            adjudication_status="refuted",
            correction_text="The earlier correction was refuted by tests.",
            source_ref="thread:track-d-demo#line:128",
            anchor_relevant=True,
            visible_context_has_source=False,
            expected_emit=False,
        ),
        make_case(
            case_id="track_d_postcompact_superseded_stale",
            case_type="superseded_stale_anchor",
            hook_stage="PostCompact",
            compaction_state="horizon_lost",
            adjudication_status="superseded",
            correction_text="A later user correction replaced the original route.",
            source_ref="thread:track-d-demo#line:139",
            anchor_relevant=True,
            visible_context_has_source=False,
            expected_emit=False,
        ),
        make_case(
            case_id="track_d_postcompact_repeated_epoch",
            case_type="repeated_anchor_same_epoch",
            hook_stage="PostCompact",
            compaction_state="horizon_lost",
            adjudication_status="valid_adopted",
            correction_text="This anchor was already injected in the current topic epoch.",
            source_ref="thread:track-d-demo#line:145",
            anchor_relevant=True,
            visible_context_has_source=False,
            expected_emit=False,
            anchor_already_injected=True,
        ),
        make_case(
            case_id="track_d_postcompact_uncertain_confirm",
            case_type="uncertain_confirm_when_relevant",
            hook_stage="PostCompact",
            compaction_state="horizon_lost",
            adjudication_status="uncertain",
            correction_text="Evidence is conflicting, so the system should not assert the anchor.",
            source_ref="thread:track-d-demo#line:150",
            anchor_relevant=True,
            visible_context_has_source=False,
            expected_emit=False,
        ),
    ]


def should_emit_anchor(case: TrackDCase) -> bool:
    # Track D adds benchmark-only stage/actionability expectations around the
    # production anchor gate. PreCompact should flush events, not surface a
    # prompt anchor, and irrelevant corrections should remain quiet at any
    # stage even when their adjudication status is otherwise valid.
    if case.hook_stage == "PreCompact" or not case.anchor_relevant:
        return False
    candidate = {
        "kind": corr.ADJUDICATION_KIND,
        "activation_event_id": case.correction_event_id,
        "adjudication_status": case.adjudication_status,
        "route": corr.route_for_adjudication(case.adjudication_status),
    }
    already_injected = {case.correction_event_id} if case.anchor_already_injected else None
    return corr.should_surface_candidate(
        candidate,
        context_state=case.compaction_state,
        action_relevant=case.anchor_relevant,
        visible_context_has_source=case.visible_context_has_source,
        already_injected_event_ids=already_injected,
    )


def evaluate_case(case: TrackDCase, *, include_private_text: bool) -> dict[str, Any]:
    emitted_anchor = should_emit_anchor(case)
    actual_action = case.expected_action() if emitted_anchor == case.expected_emit else "unexpected"
    event_index = case.event_index()
    source_event = event_index.get(case.source_event_id)
    event_chain_valid = case.event_chain_valid()
    emitted_source_event_id = case.source_event_id if emitted_anchor else None
    anchor_recalled = bool(emitted_anchor and emitted_source_event_id and event_chain_valid)
    source_fidelity = (
        event_chain_valid
        and (
            not emitted_anchor
            or emitted_source_event_id == case.source_event_id
        )
        if case.expects_source_fidelity
        else True
    )
    stale_route_retry = emitted_anchor and case.adjudication_status in {"refuted", "superseded"}
    false_anchor = emitted_anchor and not case.expected_emit
    visible_echo_noise = emitted_anchor and case.visible_context_has_source
    lost_post_compaction = case.expected_anchor_recall and not anchor_recalled
    repeated_anchor_violation = emitted_anchor and case.anchor_already_injected
    privacy_breach = False
    if include_private_text:
        private_values = [case.correction_text, case.source_ref]
        for event in case.fixture_events:
            private_values.extend([event.text, event.source_ref])
        privacy_breach = any(looks_sensitive(value) for value in private_values)
    row = {
        **case.to_result_stub(include_private_text=include_private_text),
        "actual_action": actual_action,
        "action_correct": actual_action == case.expected_action(),
        "anchor_surface_expected": case.expected_emit,
        "anchor_surface_actual": emitted_anchor,
        "source_ref_present": bool(case.source_ref),
        "source_event_bound": source_event is not None,
        "source_event_chain_valid": event_chain_valid,
        "emitted_source_event_id_sha1": (
            sha1_text(emitted_source_event_id)[:16]
            if emitted_source_event_id
            else None
        ),
        "raw_text_emitted": bool(include_private_text),
        "emitted_anchor": emitted_anchor,
        "anchor_recalled": anchor_recalled,
        "source_fidelity": source_fidelity,
        "event_captured": event_chain_valid,
        "privacy_breach": privacy_breach,
        "false_anchor": false_anchor,
        "stale_route_retry": stale_route_retry,
        "visible_context_echo_noise": visible_echo_noise,
        "lost_post_compaction_correction": lost_post_compaction,
        "repeated_anchor_violation": repeated_anchor_violation,
        "anti_nag_correct": (not emitted_anchor) if not case.expected_emit else None,
        "correct": (
            emitted_anchor == case.expected_emit
            and anchor_recalled == case.expected_anchor_recall
            and source_fidelity
            and not privacy_breach
            and not stale_route_retry
            and not false_anchor
            and not visible_echo_noise
            and not lost_post_compaction
            and not repeated_anchor_violation
        ),
    }
    return row


def safe_rate(numerator: int | float, denominator: int | float) -> float:
    return round(float(numerator) / float(denominator), 4) if denominator else 0.0


def coverage_cell(
    hook_stage: str,
    compaction_state: str,
    adjudication_status: str,
    *,
    case_count: int | None = None,
) -> dict[str, Any]:
    cell: dict[str, Any] = {
        "hook_stage": hook_stage,
        "compaction_state": compaction_state,
        "adjudication_status": adjudication_status,
    }
    if case_count is not None:
        cell["case_count"] = case_count
    return cell


def coverage_density_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    counts: dict[tuple[str, str, str], int] = {}
    for row in rows:
        key = (
            str(row.get("hook_stage") or "unknown"),
            str(row.get("compaction_state") or row.get("context_state") or "unknown"),
            str(row.get("adjudication_status") or "unknown"),
        )
        counts[key] = counts.get(key, 0) + 1

    possible_cells = [
        (stage, state, status)
        for stage in HOOK_STAGES
        for state in COMPACTION_STATES
        for status in ADJUDICATION_STATUSES
    ]
    missing_cells = [cell for cell in possible_cells if cell not in counts]
    observed_cells = [
        coverage_cell(stage, state, status, case_count=count)
        for (stage, state, status), count in sorted(counts.items())
    ]
    singleton_cells = [cell for cell in observed_cells if cell["case_count"] == 1]
    high_risk_required = list(HIGH_RISK_COVERAGE_CELLS)
    missing_high_risk = [cell for cell in high_risk_required if cell not in counts]
    sparse_high_risk = [
        cell for cell in high_risk_required if counts.get(cell, 0) == 1
    ]
    return {
        "axes": ["hook_stage", "compaction_state", "adjudication_status"],
        "possible_cell_count": len(possible_cells),
        "observed_cell_count": len(observed_cells),
        "density": safe_rate(len(observed_cells), len(possible_cells)),
        "missing_cell_count": len(missing_cells),
        "singleton_cell_count": len(singleton_cells),
        "max_cell_count": max(counts.values(), default=0),
        "observed_cells": observed_cells,
        "sparse_cells": singleton_cells,
        "missing_cell_examples": [
            coverage_cell(stage, state, status)
            for stage, state, status in missing_cells[:24]
        ],
        "high_risk_required_cells": [
            coverage_cell(stage, state, status)
            for stage, state, status in high_risk_required
        ],
        "missing_high_risk_cells": [
            coverage_cell(stage, state, status)
            for stage, state, status in missing_high_risk
        ],
        "high_risk_sparse_cells": [
            coverage_cell(stage, state, status, case_count=counts[(stage, state, status)])
            for stage, state, status in sparse_high_risk
        ],
        "notes": [
            "Density is diagnostic only; Track D remains a synthetic runner and does not claim full cross-product coverage.",
            "High-risk cells focus on post-compaction horizon-lost stale/superseded/refuted/uncertain anchor behavior.",
        ],
    }


def summarize_results(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(rows)
    expected_silent = [row for row in rows if not row.get("expected_emit")]
    expected_recall = [row for row in rows if row.get("expected_anchor_recall")]
    source_cases = [row for row in rows if row.get("source_ref_present")]
    visible_echo_cases = [
        row
        for row in rows
        if row.get("case_type") == "visible_context_echo_noise" and not row.get("expected_emit")
    ]
    stale_anchor_cases = [
        row
        for row in rows
        if row.get("adjudication_status") in {"refuted", "superseded"}
    ]
    unrelated_pre_tool = [
        row
        for row in rows
        if row.get("hook_stage") == "PreToolUse" and not row.get("anchor_relevant")
    ]
    repeated_anchor_cases = [
        row for row in rows if row.get("anchor_already_injected")
    ]
    anti_nag_correct = sum(1 for row in expected_silent if row.get("anti_nag_correct"))
    stage_coverage: dict[str, int] = {}
    context_state_coverage: dict[str, int] = {}
    adjudication_coverage: dict[str, int] = {}
    for row in rows:
        stage = str(row.get("hook_stage") or "unknown")
        context_state = str(row.get("context_state") or row.get("compaction_state") or "unknown")
        adjudication = str(row.get("adjudication_status") or "unknown")
        stage_coverage[stage] = stage_coverage.get(stage, 0) + 1
        context_state_coverage[context_state] = context_state_coverage.get(context_state, 0) + 1
        adjudication_coverage[adjudication] = adjudication_coverage.get(adjudication, 0) + 1
    correct_count = sum(1 for row in rows if row.get("correct"))
    privacy_count = sum(1 for row in rows if row.get("privacy_breach"))
    false_anchor_count = sum(1 for row in rows if row.get("false_anchor"))
    stale_retry_count = sum(1 for row in rows if row.get("stale_route_retry"))
    repeated_anchor_violation_count = sum(
        1 for row in repeated_anchor_cases if row.get("repeated_anchor_violation")
    )
    source_fidelity_count = sum(1 for row in source_cases if row.get("source_fidelity"))
    event_chain_valid_count = sum(
        1 for row in source_cases if row.get("source_event_chain_valid")
    )
    anchor_recall_count = sum(1 for row in expected_recall if row.get("anchor_recalled"))
    unrelated_silent_count = sum(1 for row in unrelated_pre_tool if not row.get("emitted_anchor"))
    visible_echo_correct_count = sum(
        1 for row in visible_echo_cases if not row.get("visible_context_echo_noise")
    )
    uncertain_rows = [
        row for row in rows if row.get("adjudication_status") == "uncertain"
    ]
    uncertain_confirmation_count = sum(
        1 for row in uncertain_rows if row.get("expected_action") == "confirm_when_relevant"
    )
    return {
        "total_cases": total,
        "stage_coverage": stage_coverage,
        "context_state_coverage": context_state_coverage,
        "adjudication_coverage": adjudication_coverage,
        "correct_count": correct_count,
        "incorrect_count": total - correct_count,
        "all_cases_correct": correct_count == total if total else False,
        "accuracy": safe_rate(correct_count, total),
        "privacy_breach_count": privacy_count,
        "privacy_breach_rate": safe_rate(privacy_count, total),
        "raw_prompt_leakage_count": sum(1 for row in rows if row.get("raw_text_emitted")),
        "raw_prompt_leakage_rate": safe_rate(
            sum(1 for row in rows if row.get("raw_text_emitted")),
            total,
        ),
        "false_anchor_count": false_anchor_count,
        "false_anchor_rate": safe_rate(false_anchor_count, total),
        "stale_route_retry_count": stale_retry_count,
        "stale_route_retry_rate": safe_rate(
            stale_retry_count,
            max(len(stale_anchor_cases), 1),
        ),
        "anti_nag_precision": safe_rate(anti_nag_correct, len(expected_silent)),
        "repeated_anchor_case_count": len(repeated_anchor_cases),
        "repeated_anchor_count": repeated_anchor_violation_count,
        "repeated_anchor_rate": safe_rate(
            repeated_anchor_violation_count,
            len(repeated_anchor_cases),
        ),
        "repeated_anchor_suppression_rate": safe_rate(
            len(repeated_anchor_cases) - repeated_anchor_violation_count,
            len(repeated_anchor_cases),
        ),
        "event_chain_valid_count": event_chain_valid_count,
        "event_chain_valid_rate": safe_rate(event_chain_valid_count, len(source_cases)),
        "source_fidelity": safe_rate(
            source_fidelity_count,
            len(source_cases),
        ),
        "source_fidelity_count": source_fidelity_count,
        "source_fidelity_rate": safe_rate(source_fidelity_count, len(source_cases)),
        "correction_anchor_recall": safe_rate(
            anchor_recall_count,
            len(expected_recall),
        ),
        "correction_anchor_recall_count": anchor_recall_count,
        "correction_anchor_recall_rate": safe_rate(
            anchor_recall_count,
            len(expected_recall),
        ),
        "expected_anchor_recall_count": len(expected_recall),
        "lost_post_compaction_corrections": sum(
            1 for row in rows if row.get("lost_post_compaction_correction")
        ),
        "visible_context_echo_expected_silent_count": len(visible_echo_cases),
        "visibility_echo_correct_count": visible_echo_correct_count,
        "visibility_echo_correct_rate": safe_rate(
            visible_echo_correct_count,
            len(visible_echo_cases),
        ),
        "visible_context_echo_noise_count": sum(
            1 for row in visible_echo_cases if row.get("visible_context_echo_noise")
        ),
        "stale_anchor_guard_case_count": len(stale_anchor_cases),
        "unrelated_pre_tool_use_case_count": len(unrelated_pre_tool),
        "pretooluse_unrelated_intervention_count": sum(
            1 for row in unrelated_pre_tool if row.get("emitted_anchor")
        ),
        "pretooluse_unrelated_silence_rate": safe_rate(
            unrelated_silent_count,
            len(unrelated_pre_tool),
        ),
        "hook_stage_correct_count": correct_count,
        "hook_stage_correct_rate": safe_rate(correct_count, total),
        "uncertain_confirmation_count": uncertain_confirmation_count,
        "uncertain_confirmation_rate": safe_rate(
            uncertain_confirmation_count,
            len(uncertain_rows),
        ),
    }


def coverage_summary(rows: list[dict[str, Any]]) -> dict[str, list[str]]:
    return {
        "hook_stages": sorted({str(row.get("hook_stage")) for row in rows}),
        "compaction_states": sorted({str(row.get("compaction_state")) for row in rows}),
        "adjudication_statuses": sorted(
            {str(row.get("adjudication_status")) for row in rows}
        ),
    }


def run_benchmark(
    *,
    include_private_text: bool = False,
    case_limit: int | None = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    all_cases = fixture_cases()
    cases = all_cases
    if case_limit and case_limit > 0:
        cases = cases[:case_limit]
    diagnostic_subset = len(cases) < len(all_cases)
    rows = [
        evaluate_case(case, include_private_text=include_private_text)
        for case in cases
    ]
    metrics = summarize_results(rows)
    coverage = coverage_summary(rows)
    coverage_density = coverage_density_summary(rows)
    required_stage_coverage = set(HOOK_STAGES) <= set(coverage["hook_stages"])
    required_state_coverage = set(COMPACTION_STATES) <= set(coverage["compaction_states"])
    required_status_coverage = set(ADJUDICATION_STATUSES) <= set(
        coverage["adjudication_statuses"]
    )
    regression_counters_free = (
        metrics["privacy_breach_count"] == 0
        and metrics["false_anchor_count"] == 0
        and metrics["stale_route_retry_count"] == 0
        and metrics["repeated_anchor_count"] == 0
        and metrics["lost_post_compaction_corrections"] == 0
        and metrics["event_chain_valid_rate"] == 1.0
        and metrics["source_fidelity"] == 1.0
        and metrics["correction_anchor_recall"] == 1.0
        and metrics["anti_nag_precision"] == 1.0
    )
    all_cases_correct = metrics["correct_count"] == metrics["total_cases"]
    regression_free = regression_counters_free and all_cases_correct
    full_coverage = (
        required_stage_coverage
        and required_state_coverage
        and required_status_coverage
    )
    quality_gate_ok = bool(regression_free and full_coverage and not diagnostic_subset)
    ok = bool(regression_free and (full_coverage or diagnostic_subset))
    if quality_gate_ok:
        status = "sufficient"
    elif ok and diagnostic_subset:
        status = "diagnostic_subset"
    else:
        status = "track_d_regression"
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "aippocampus_compaction_continuity_benchmark",
        "generated_at": now_utc(),
        "config": {
            "case_set": "synthetic_track_d",
            "case_limit": case_limit,
            "complete_case_set": not diagnostic_subset,
            "include_private_text": include_private_text,
            "live_llm": False,
            "live_codex_host": False,
        },
        "status": status,
        "quality_gate_ok": quality_gate_ok,
        "diagnostic": {
            "is_subset": diagnostic_subset,
            "sufficient_quality_evidence": quality_gate_ok,
            "reason": "case_limit" if diagnostic_subset else None,
        },
        "metrics": metrics,
        "coverage": coverage,
        "coverage_density": coverage_density,
        "cases": rows,
        "privacy_boundary": {
            "raw_correction_text_emitted": bool(include_private_text),
            "raw_source_refs_emitted": bool(include_private_text),
            "absolute_paths_emitted": False,
            "case_ids_are_hashed": not include_private_text,
            "output_shape": "sanitized_compaction_continuity_aggregates",
        },
        "cannot_claim": [
            "live_codex_host_behavior",
            "live_hook_capture",
            "live_semantic_adjudication_quality",
            "real_history_compaction_survival",
        ],
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
        "ok": ok,
    }


def print_human_summary(payload: dict[str, Any]) -> None:
    metrics = payload["metrics"]
    print("AIppocampus Track D compaction-continuity benchmark")
    print(f"cases: {metrics['total_cases']} accuracy: {metrics['accuracy']}")
    print(
        "anchor_recall: {recall} source_fidelity: {source} anti_nag: {nag}".format(
            recall=metrics["correction_anchor_recall"],
            source=metrics["source_fidelity"],
            nag=metrics["anti_nag_precision"],
        )
    )
    print(
        "privacy_breach: {privacy} false_anchor: {false_anchor} stale_retry: {stale}".format(
            privacy=metrics["privacy_breach_count"],
            false_anchor=metrics["false_anchor_count"],
            stale=metrics["stale_route_retry_count"],
        )
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=int, default=None)
    parser.add_argument("--include-private-text", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    payload = run_benchmark(
        include_private_text=args.include_private_text,
        case_limit=args.cases,
    )
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print_human_summary(payload)
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
