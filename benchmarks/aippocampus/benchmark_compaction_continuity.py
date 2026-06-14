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
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import _paths

_paths.ensure_paths()

from aippocampus_runtime.core import benchmark_text_is_sensitive
from aippocampus_runtime.reflection import reconsolidation as corr
from benchmarks.aippocampus.shared.benchmark_statistics import binomial_rate_report

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
SPEC_COMPLETE_NO_HARM_CASE_TYPES = {"spec_complete_short_task_no_harm"}
SILENT_RECORDING_STAGES = {"SubagentStop", "Stop", "PreCompact"}

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


@dataclass(frozen=True)
class TrackDSequenceCase:
    sequence_id: str
    thread_id: str
    sequence_type: str
    steps: tuple[TrackDCase, ...]

    def event_link_chain_valid(self) -> bool:
        if len(self.steps) < 2:
            return False
        return all(
            current.source_event_id == later.correction_event_id
            for current, later in zip(self.steps, self.steps[1:], strict=False)
        )


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha1_text(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8", errors="replace")).hexdigest()


def looks_sensitive(value: str) -> bool:
    return benchmark_text_is_sensitive(value)


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


def make_sequence_step(
    *,
    sequence_id: str,
    thread_id: str,
    step_name: str,
    case_type: str,
    hook_stage: str,
    compaction_state: str,
    adjudication_status: str,
    correction_event: FixtureEvent,
    source_event: FixtureEvent,
    correction_text: str,
    anchor_relevant: bool,
    visible_context_has_source: bool,
    expected_emit: bool,
    expected_anchor_recall: bool = False,
) -> TrackDCase:
    return TrackDCase(
        case_id=f"{sequence_id}:{step_name}",
        thread_id=thread_id,
        case_type=case_type,
        hook_stage=hook_stage,
        compaction_state=compaction_state,
        adjudication_status=adjudication_status,
        correction_text=correction_text,
        source_ref=source_event.source_ref,
        correction_event_id=correction_event.event_id,
        source_event_id=source_event.event_id,
        fixture_events=(correction_event, source_event),
        anchor_relevant=anchor_relevant,
        visible_context_has_source=visible_context_has_source,
        expected_emit=expected_emit,
        expected_anchor_recall=expected_anchor_recall,
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
            case_id="track_d_spec_complete_no_harm",
            case_type="spec_complete_short_task_no_harm",
            hook_stage="UserPromptSubmit",
            compaction_state="visible",
            adjudication_status="valid_adopted",
            correction_text=(
                "The current prompt already contains the complete correct spec; "
                "external memory should stay silent."
            ),
            source_ref="thread:track-d-demo#line:14",
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
        make_case(
            case_id="track_d_user_prompt_post_compaction_rehydrate",
            case_type="user_prompt_post_compaction_rehydrate",
            hook_stage="UserPromptSubmit",
            compaction_state="post_compaction",
            adjudication_status="valid_adopted",
            correction_text="The user returns after compaction and the accepted route constraint is no longer visible.",
            source_ref="thread:track-d-demo#line:161",
            anchor_relevant=True,
            visible_context_has_source=False,
            expected_emit=True,
            expected_anchor_recall=True,
        ),
        make_case(
            case_id="track_d_user_prompt_horizon_rehydrate",
            case_type="user_prompt_horizon_lost_rehydrate",
            hook_stage="UserPromptSubmit",
            compaction_state="horizon_lost",
            adjudication_status="valid_adopted",
            correction_text="The user resumes a long thread after horizon loss and the adopted correction still controls the task.",
            source_ref="thread:track-d-demo#line:165",
            anchor_relevant=True,
            visible_context_has_source=False,
            expected_emit=True,
            expected_anchor_recall=True,
        ),
        make_case(
            case_id="track_d_user_prompt_post_compaction_uncertain",
            case_type="user_prompt_uncertain_confirm",
            hook_stage="UserPromptSubmit",
            compaction_state="post_compaction",
            adjudication_status="uncertain",
            correction_text="The old correction may matter after compaction, but the source evidence is ambiguous.",
            source_ref="thread:track-d-demo#line:169",
            anchor_relevant=True,
            visible_context_has_source=False,
            expected_emit=False,
        ),
        make_case(
            case_id="track_d_user_prompt_post_compaction_local_only",
            case_type="local_only_reentry_after_compaction",
            hook_stage="UserPromptSubmit",
            compaction_state="post_compaction",
            adjudication_status="local_only",
            correction_text="A branch-local workaround becomes relevant again after compaction but should not be injected as fact.",
            source_ref="thread:track-d-demo#line:173",
            anchor_relevant=True,
            visible_context_has_source=False,
            expected_emit=False,
        ),
        make_case(
            case_id="track_d_pre_tool_visible_valid_ignored",
            case_type="pre_tool_visible_ignored_suppression",
            hook_stage="PreToolUse",
            compaction_state="visible",
            adjudication_status="valid_ignored",
            correction_text="A rejected tool route is visible in the prompt while another tool call is pending.",
            source_ref="thread:track-d-demo#line:181",
            anchor_relevant=True,
            visible_context_has_source=True,
            expected_emit=False,
        ),
        make_case(
            case_id="track_d_pre_tool_visible_valid_adopted",
            case_type="pre_tool_visible_adopted_suppression",
            hook_stage="PreToolUse",
            compaction_state="visible",
            adjudication_status="valid_adopted",
            correction_text="An adopted tool constraint is still visible and should not be echoed before the call.",
            source_ref="thread:track-d-demo#line:185",
            anchor_relevant=True,
            visible_context_has_source=True,
            expected_emit=False,
        ),
        make_case(
            case_id="track_d_pre_tool_post_compaction_relevant",
            case_type="pre_tool_post_compaction_relevant_anchor",
            hook_stage="PreToolUse",
            compaction_state="post_compaction",
            adjudication_status="valid_adopted",
            correction_text="The pending command risks violating an adopted post-compaction scope correction.",
            source_ref="thread:track-d-demo#line:189",
            anchor_relevant=True,
            visible_context_has_source=False,
            expected_emit=True,
            expected_anchor_recall=True,
        ),
        make_case(
            case_id="track_d_pre_tool_post_compaction_refuted",
            case_type="pre_tool_refuted_stale_suppression",
            hook_stage="PreToolUse",
            compaction_state="post_compaction",
            adjudication_status="refuted",
            correction_text="A stale pre-tool route was refuted by later test output.",
            source_ref="thread:track-d-demo#line:193",
            anchor_relevant=True,
            visible_context_has_source=False,
            expected_emit=False,
        ),
        make_case(
            case_id="track_d_pre_tool_horizon_refuted",
            case_type="pre_tool_horizon_refuted_suppression",
            hook_stage="PreToolUse",
            compaction_state="horizon_lost",
            adjudication_status="refuted",
            correction_text="A refuted tool-route anchor is no longer visible but must still stay suppressed.",
            source_ref="thread:track-d-demo#line:197",
            anchor_relevant=True,
            visible_context_has_source=False,
            expected_emit=False,
        ),
        make_case(
            case_id="track_d_pre_tool_horizon_superseded",
            case_type="pre_tool_horizon_superseded_suppression",
            hook_stage="PreToolUse",
            compaction_state="horizon_lost",
            adjudication_status="superseded",
            correction_text="A later user turn superseded the old tool guidance before horizon loss.",
            source_ref="thread:track-d-demo#line:201",
            anchor_relevant=True,
            visible_context_has_source=False,
            expected_emit=False,
        ),
        make_case(
            case_id="track_d_post_tool_post_compaction_adopted",
            case_type="post_tool_post_compaction_evidence_link",
            hook_stage="PostToolUse",
            compaction_state="post_compaction",
            adjudication_status="valid_adopted",
            correction_text="Sanitized tool output after compaction confirms the user's corrected route.",
            source_ref="thread:track-d-demo#line:211",
            anchor_relevant=True,
            visible_context_has_source=False,
            expected_emit=True,
            expected_anchor_recall=True,
        ),
        make_case(
            case_id="track_d_post_tool_horizon_adopted",
            case_type="post_tool_horizon_evidence_relink",
            hook_stage="PostToolUse",
            compaction_state="horizon_lost",
            adjudication_status="valid_adopted",
            correction_text="Sanitized tool output relinks an accepted correction after horizon loss.",
            source_ref="thread:track-d-demo#line:215",
            anchor_relevant=True,
            visible_context_has_source=False,
            expected_emit=True,
            expected_anchor_recall=True,
        ),
        make_case(
            case_id="track_d_post_tool_post_compaction_refuted",
            case_type="post_tool_refuted_evidence_link",
            hook_stage="PostToolUse",
            compaction_state="post_compaction",
            adjudication_status="refuted",
            correction_text="Tool output after compaction refutes a pending correction window.",
            source_ref="thread:track-d-demo#line:219",
            anchor_relevant=True,
            visible_context_has_source=False,
            expected_emit=False,
        ),
        make_case(
            case_id="track_d_post_tool_horizon_refuted",
            case_type="post_tool_horizon_refuted_evidence_link",
            hook_stage="PostToolUse",
            compaction_state="horizon_lost",
            adjudication_status="refuted",
            correction_text="Tool output after horizon loss refutes the old correction instead of reviving it.",
            source_ref="thread:track-d-demo#line:223",
            anchor_relevant=True,
            visible_context_has_source=False,
            expected_emit=False,
        ),
        make_case(
            case_id="track_d_post_tool_post_compaction_uncertain",
            case_type="semantic_disagreement_confirm",
            hook_stage="PostToolUse",
            compaction_state="post_compaction",
            adjudication_status="uncertain",
            correction_text="Deterministic evidence looks positive but mocked semantic adjudication remains uncertain.",
            source_ref="thread:track-d-demo#line:227",
            anchor_relevant=True,
            visible_context_has_source=False,
            expected_emit=False,
            outcome_text="Mock semantic adjudication disagrees with deterministic-looking tool evidence.",
        ),
        make_case(
            case_id="track_d_postcompact_valid_ignored_redundant",
            case_type="rejected_route_horizon_second_warning",
            hook_stage="PostCompact",
            compaction_state="horizon_lost",
            adjudication_status="valid_ignored",
            correction_text="A second rejected implementation path should warn before retry after horizon loss.",
            source_ref="thread:track-d-demo#line:235",
            anchor_relevant=True,
            visible_context_has_source=False,
            expected_emit=True,
            expected_anchor_recall=True,
        ),
        make_case(
            case_id="track_d_postcompact_refuted_redundant",
            case_type="refuted_clean_source_horizon_guard",
            hook_stage="PostCompact",
            compaction_state="horizon_lost",
            adjudication_status="refuted",
            correction_text="Later clean source refuted the old correction before it fell out of horizon.",
            source_ref="thread:track-d-demo#line:239",
            anchor_relevant=True,
            visible_context_has_source=False,
            expected_emit=False,
        ),
        make_case(
            case_id="track_d_postcompact_superseded_redundant",
            case_type="superseded_scope_horizon_guard",
            hook_stage="PostCompact",
            compaction_state="horizon_lost",
            adjudication_status="superseded",
            correction_text="A later scope correction replaced the previous one before horizon loss.",
            source_ref="thread:track-d-demo#line:243",
            anchor_relevant=True,
            visible_context_has_source=False,
            expected_emit=False,
        ),
        make_case(
            case_id="track_d_postcompact_uncertain_redundant",
            case_type="ambiguous_evidence_horizon_confirm",
            hook_stage="PostCompact",
            compaction_state="horizon_lost",
            adjudication_status="uncertain",
            correction_text="Horizon loss left the correction evidence ambiguous, so the agent should confirm.",
            source_ref="thread:track-d-demo#line:247",
            anchor_relevant=True,
            visible_context_has_source=False,
            expected_emit=False,
        ),
        make_case(
            case_id="track_d_postcompact_horizon_local_only",
            case_type="local_only_expiry_after_horizon_loss",
            hook_stage="PostCompact",
            compaction_state="horizon_lost",
            adjudication_status="local_only",
            correction_text="A one-off experiment correction survived in staging but should expire after horizon loss.",
            source_ref="thread:track-d-demo#line:251",
            anchor_relevant=True,
            visible_context_has_source=False,
            expected_emit=False,
        ),
        make_case(
            case_id="track_d_precompact_refuted_flush",
            case_type="precompact_refuted_flush",
            hook_stage="PreCompact",
            compaction_state="post_compaction",
            adjudication_status="refuted",
            correction_text="Flush refutation evidence before rewrite so a stale anchor cannot revive later.",
            source_ref="thread:track-d-demo#line:261",
            anchor_relevant=True,
            visible_context_has_source=False,
            expected_emit=False,
        ),
        make_case(
            case_id="track_d_precompact_superseded_flush",
            case_type="precompact_superseded_flush",
            hook_stage="PreCompact",
            compaction_state="post_compaction",
            adjudication_status="superseded",
            correction_text="Flush successor links before rewrite so the old scope remains suppressed.",
            source_ref="thread:track-d-demo#line:265",
            anchor_relevant=True,
            visible_context_has_source=False,
            expected_emit=False,
        ),
        make_case(
            case_id="track_d_precompact_uncertain_late_window",
            case_type="precompact_uncertain_late_window",
            hook_stage="PreCompact",
            compaction_state="horizon_lost",
            adjudication_status="uncertain",
            correction_text="A late pre-rewrite window keeps ambiguous source refs without injecting guidance.",
            source_ref="thread:track-d-demo#line:269",
            anchor_relevant=True,
            visible_context_has_source=False,
            expected_emit=False,
        ),
        make_case(
            case_id="track_d_stop_valid_adopted_closeout",
            case_type="stop_valid_adopted_closeout",
            hook_stage="Stop",
            compaction_state="post_compaction",
            adjudication_status="valid_adopted",
            correction_text="Closeout records that final work adopted the correction for later compaction behavior.",
            source_ref="thread:track-d-demo#line:281",
            anchor_relevant=True,
            visible_context_has_source=False,
            expected_emit=False,
        ),
        make_case(
            case_id="track_d_stop_valid_ignored_closeout",
            case_type="stop_valid_ignored_closeout",
            hook_stage="Stop",
            compaction_state="post_compaction",
            adjudication_status="valid_ignored",
            correction_text="Closeout records an ignored route without foreground prompt guidance.",
            source_ref="thread:track-d-demo#line:285",
            anchor_relevant=True,
            visible_context_has_source=False,
            expected_emit=False,
        ),
        make_case(
            case_id="track_d_stop_refuted_closeout",
            case_type="stop_refuted_closeout",
            hook_stage="Stop",
            compaction_state="post_compaction",
            adjudication_status="refuted",
            correction_text="Final verification refuted the correction and the closeout stores that result silently.",
            source_ref="thread:track-d-demo#line:289",
            anchor_relevant=True,
            visible_context_has_source=False,
            expected_emit=False,
        ),
        make_case(
            case_id="track_d_stop_superseded_closeout",
            case_type="stop_superseded_closeout",
            hook_stage="Stop",
            compaction_state="post_compaction",
            adjudication_status="superseded",
            correction_text="Closeout records that a later source superseded the earlier correction.",
            source_ref="thread:track-d-demo#line:293",
            anchor_relevant=True,
            visible_context_has_source=False,
            expected_emit=False,
        ),
        make_case(
            case_id="track_d_subagent_start_visible_adopted",
            case_type="subagent_visible_echo_suppression",
            hook_stage="SubagentStart",
            compaction_state="visible",
            adjudication_status="valid_adopted",
            correction_text="The delegated task already sees the adopted correction in visible context.",
            source_ref="thread:track-d-demo#line:301",
            anchor_relevant=True,
            visible_context_has_source=True,
            expected_emit=False,
        ),
        make_case(
            case_id="track_d_subagent_start_horizon_irrelevant",
            case_type="subagent_irrelevant_delegation_suppression",
            hook_stage="SubagentStart",
            compaction_state="horizon_lost",
            adjudication_status="valid_adopted",
            correction_text="The active anchor is real but unrelated to the delegated subtask.",
            source_ref="thread:track-d-demo#line:305",
            anchor_relevant=False,
            visible_context_has_source=False,
            expected_emit=False,
        ),
        make_case(
            case_id="track_d_subagent_start_horizon_refuted",
            case_type="subagent_refuted_propagation_suppression",
            hook_stage="SubagentStart",
            compaction_state="horizon_lost",
            adjudication_status="refuted",
            correction_text="A refuted anchor must not propagate into delegated work after horizon loss.",
            source_ref="thread:track-d-demo#line:309",
            anchor_relevant=True,
            visible_context_has_source=False,
            expected_emit=False,
        ),
        make_case(
            case_id="track_d_subagent_start_horizon_superseded",
            case_type="subagent_superseded_propagation_suppression",
            hook_stage="SubagentStart",
            compaction_state="horizon_lost",
            adjudication_status="superseded",
            correction_text="A superseded anchor must not propagate into delegated work after horizon loss.",
            source_ref="thread:track-d-demo#line:313",
            anchor_relevant=True,
            visible_context_has_source=False,
            expected_emit=False,
        ),
        make_case(
            case_id="track_d_subagent_start_post_compaction_ignored",
            case_type="subagent_rejected_route_warning_propagation",
            hook_stage="SubagentStart",
            compaction_state="post_compaction",
            adjudication_status="valid_ignored",
            correction_text="Delegated work risks repeating a route the user rejected before compaction.",
            source_ref="thread:track-d-demo#line:317",
            anchor_relevant=True,
            visible_context_has_source=False,
            expected_emit=True,
            expected_anchor_recall=True,
        ),
    ]


def sequence_cases() -> list[TrackDSequenceCase]:
    sequences: list[TrackDSequenceCase] = []
    for suffix, final_status, final_emit, final_type in (
        ("adopted", "valid_adopted", True, "subagent_sequence_adopted_rehydrate"),
        ("refuted", "refuted", False, "subagent_sequence_refuted_suppression"),
    ):
        sequence_id = f"track_d_subagent_sequence_{suffix}"
        thread_id = f"track-d-thread:{sequence_id}"
        activation = FixtureEvent(
            event_id=f"{sequence_id}:activation",
            event_type="correction_activation_event",
            hook_stage="UserPromptSubmit",
            source_ref=f"thread:track-d-sequence-{suffix}#line:10",
            text="User corrects the route before delegated work begins.",
        )
        hot_anchor = FixtureEvent(
            event_id=f"{sequence_id}:hot_anchor",
            event_type="hot_anchor_event",
            hook_stage="UserPromptSubmit",
            source_ref=f"thread:track-d-sequence-{suffix}#line:12",
            text="The accepted correction becomes a task anchor after compaction.",
            related_event_id=activation.event_id,
        )
        propagated = FixtureEvent(
            event_id=f"{sequence_id}:propagated_anchor",
            event_type="subagent_anchor_propagation_event",
            hook_stage="SubagentStart",
            source_ref=f"thread:track-d-sequence-{suffix}#line:18",
            text="The relevant active anchor is propagated into delegated work.",
            related_event_id=hot_anchor.event_id,
        )
        subagent_outcome = FixtureEvent(
            event_id=f"{sequence_id}:subagent_outcome",
            event_type="subagent_reconciliation_event",
            hook_stage="SubagentStop",
            source_ref=f"thread:track-d-sequence-{suffix}#line:26",
            text=f"The subagent returns with a {final_status} reconciliation.",
            related_event_id=propagated.event_id,
        )
        postcompact = FixtureEvent(
            event_id=f"{sequence_id}:postcompact_outcome",
            event_type="postcompact_anchor_decision_event",
            hook_stage="PostCompact",
            source_ref=f"thread:track-d-sequence-{suffix}#line:34",
            text="PostCompact either rehydrates the adopted anchor or keeps a refuted one suppressed.",
            related_event_id=subagent_outcome.event_id,
        )
        steps = (
            make_sequence_step(
                sequence_id=sequence_id,
                thread_id=thread_id,
                step_name="01_user_prompt",
                case_type="subagent_sequence_user_prompt_activation",
                hook_stage="UserPromptSubmit",
                compaction_state="post_compaction",
                adjudication_status="valid_adopted",
                correction_event=activation,
                source_event=hot_anchor,
                correction_text="User correction activates a hot anchor after compaction.",
                anchor_relevant=True,
                visible_context_has_source=False,
                expected_emit=True,
                expected_anchor_recall=True,
            ),
            make_sequence_step(
                sequence_id=sequence_id,
                thread_id=thread_id,
                step_name="02_subagent_start",
                case_type="subagent_sequence_start_propagation",
                hook_stage="SubagentStart",
                compaction_state="horizon_lost",
                adjudication_status="valid_adopted",
                correction_event=hot_anchor,
                source_event=propagated,
                correction_text="The active anchor is task-relevant for delegated work.",
                anchor_relevant=True,
                visible_context_has_source=False,
                expected_emit=True,
                expected_anchor_recall=True,
            ),
            make_sequence_step(
                sequence_id=sequence_id,
                thread_id=thread_id,
                step_name="03_subagent_stop",
                case_type="subagent_sequence_stop_reconciliation",
                hook_stage="SubagentStop",
                compaction_state="post_compaction",
                adjudication_status=final_status,
                correction_event=propagated,
                source_event=subagent_outcome,
                correction_text="SubagentStop reconciles delegated work without injecting foreground guidance.",
                anchor_relevant=True,
                visible_context_has_source=False,
                expected_emit=False,
            ),
            make_sequence_step(
                sequence_id=sequence_id,
                thread_id=thread_id,
                step_name="04_postcompact",
                case_type=final_type,
                hook_stage="PostCompact",
                compaction_state="horizon_lost",
                adjudication_status=final_status,
                correction_event=subagent_outcome,
                source_event=postcompact,
                correction_text="PostCompact applies the subagent reconciliation after horizon loss.",
                anchor_relevant=True,
                visible_context_has_source=False,
                expected_emit=final_emit,
                expected_anchor_recall=final_emit,
            ),
        )
        sequences.append(
            TrackDSequenceCase(
                sequence_id=sequence_id,
                thread_id=thread_id,
                sequence_type=final_type,
                steps=steps,
            )
        )
    return sequences


def should_emit_anchor(case: TrackDCase) -> bool:
    # Track D adds benchmark-only stage/actionability expectations around the
    # production anchor gate. Silent recording stages flush or reconcile event
    # state for later compaction handling; making them emit prompt anchors would
    # hide closeout/subagent over-propagation regressions behind a passing gate.
    # Irrelevant corrections stay quiet even when their status is otherwise
    # active, because Track D measures task continuity rather than global memory.
    if case.hook_stage in SILENT_RECORDING_STAGES or not case.anchor_relevant:
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


def evaluate_sequence_case(
    sequence: TrackDSequenceCase,
    *,
    include_private_text: bool,
) -> dict[str, Any]:
    step_rows = [
        {
            **evaluate_case(step, include_private_text=include_private_text),
            "sequence_step_index": index,
        }
        for index, step in enumerate(sequence.steps, start=1)
    ]
    final_row = step_rows[-1] if step_rows else {}
    event_link_chain_valid = sequence.event_link_chain_valid()
    step_cases_correct = all(bool(row.get("correct")) for row in step_rows)
    final_status = str(final_row.get("adjudication_status") or "")
    adopted_rehydrated = (
        final_status == "valid_adopted"
        and bool(final_row.get("emitted_anchor"))
        and bool(final_row.get("anchor_recalled"))
    )
    refuted_suppressed = final_status == "refuted" and not bool(
        final_row.get("emitted_anchor")
    )
    payload: dict[str, Any] = {
        "sequence_id_sha1": sha1_text(sequence.sequence_id)[:16],
        "thread_id_sha1": sha1_text(sequence.thread_id)[:16],
        "sequence_type": sequence.sequence_type,
        "step_count": len(step_rows),
        "covered_stages": sorted({str(row.get("hook_stage")) for row in step_rows}),
        "event_link_chain_valid": event_link_chain_valid,
        "step_cases_correct": step_cases_correct,
        "final_adjudication_status": final_status,
        "final_expected_emit": bool(final_row.get("expected_emit")),
        "final_emitted_anchor": bool(final_row.get("emitted_anchor")),
        "adopted_rehydrated": adopted_rehydrated,
        "refuted_suppressed": refuted_suppressed,
        "correct": bool(event_link_chain_valid and step_cases_correct),
        "steps": step_rows,
    }
    if include_private_text:
        payload.update(
            {
                "sequence_id": sequence.sequence_id,
                "thread_id": sequence.thread_id,
            }
        )
    return payload


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
    high_risk_counts = [counts.get(cell, 0) for cell in high_risk_required]
    return {
        "axes": ["hook_stage", "compaction_state", "adjudication_status"],
        "possible_cell_count": len(possible_cells),
        "observed_cell_count": len(observed_cells),
        "density": safe_rate(len(observed_cells), len(possible_cells)),
        "missing_cell_count": len(missing_cells),
        "singleton_cell_count": len(singleton_cells),
        "max_cell_count": max(counts.values(), default=0),
        "min_high_risk_cell_count": min(high_risk_counts, default=0),
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


def sequence_coverage_summary(sequence_rows: list[dict[str, Any]]) -> dict[str, Any]:
    covered_stages = sorted(
        {
            str(step.get("hook_stage"))
            for sequence in sequence_rows
            for step in sequence.get("steps", [])
        }
    )
    return {
        "sequence_count": len(sequence_rows),
        "covered_stages": covered_stages,
        "valid_sequence_count": sum(
            1 for sequence in sequence_rows if sequence.get("correct")
        ),
        "invalid_sequence_count": sum(
            1 for sequence in sequence_rows if not sequence.get("correct")
        ),
        "adopted_rehydration_count": sum(
            1 for sequence in sequence_rows if sequence.get("adopted_rehydrated")
        ),
        "refuted_suppression_count": sum(
            1 for sequence in sequence_rows if sequence.get("refuted_suppressed")
        ),
        "notes": [
            "Sequence diagnostics validate related-event links across stages; they remain synthetic and do not claim live subagent host wiring.",
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
    rate_estimates = {
        "accuracy": binomial_rate_report(
            "accuracy",
            numerator=correct_count,
            denominator=total,
        ),
        "event_chain_valid_rate": binomial_rate_report(
            "event_chain_valid_rate",
            numerator=event_chain_valid_count,
            denominator=len(source_cases),
        ),
        "source_fidelity": binomial_rate_report(
            "source_fidelity",
            numerator=source_fidelity_count,
            denominator=len(source_cases),
        ),
        "correction_anchor_recall": binomial_rate_report(
            "correction_anchor_recall",
            numerator=anchor_recall_count,
            denominator=len(expected_recall),
        ),
        "anti_nag_precision": binomial_rate_report(
            "anti_nag_precision",
            numerator=anti_nag_correct,
            denominator=len(expected_silent),
        ),
    }
    return {
        "total_cases": total,
        "stage_coverage": stage_coverage,
        "context_state_coverage": context_state_coverage,
        "adjudication_coverage": adjudication_coverage,
        "correct_count": correct_count,
        "incorrect_count": total - correct_count,
        "all_cases_correct": correct_count == total if total else False,
        "accuracy": safe_rate(correct_count, total),
        "rate_estimates": rate_estimates,
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


def no_harm_when_spec_complete(rows: list[dict[str, Any]]) -> dict[str, Any]:
    cases = [
        row
        for row in rows
        if str(row.get("case_type") or "") in SPEC_COMPLETE_NO_HARM_CASE_TYPES
    ]
    unwanted_memory_injection_count = sum(1 for row in cases if row.get("emitted_anchor"))
    stale_memory_false_positive_count = sum(
        1
        for row in cases
        if row.get("false_anchor")
        or row.get("stale_route_retry")
        or row.get("visible_context_echo_noise")
    )
    return {
        "case_count": len(cases),
        "unwanted_memory_injection_count": unwanted_memory_injection_count,
        "stale_memory_false_positive_count": stale_memory_false_positive_count,
        "silence_rate": safe_rate(
            len(cases) - unwanted_memory_injection_count,
            len(cases),
        ),
        "ok": bool(cases)
        and unwanted_memory_injection_count == 0
        and stale_memory_false_positive_count == 0,
        "interpretation": (
            "Complete-spec short tasks are no-harm controls: success means "
            "AIppocampus stays quiet unless memory prevents a concrete high-cost mistake."
        ),
    }


def benchmark_framing() -> dict[str, Any]:
    return {
        "primary_endpoint": {
            "name": "context_loss_or_instability",
            "applies_when": [
                "handoff_or_spec_loop_is_incomplete",
                "post_compaction_horizon_lost",
                "state_is_stale_or_superseded",
                "operation_facts_are_missing_or_costly_to_reopen",
            ],
            "core_metrics": [
                "known_bad_route_repetition_rate",
                "operation_fact_reopen_rate",
                "stale_summary_overhang_rate",
                "human_correction_count",
                "source_reopen_before_risky_action",
                "cost_per_successful_slice",
            ],
        },
        "secondary_endpoint": {
            "name": "fresh_context_spec_loop_quality",
            "interpretation": (
                "Fresh-context/spec-loop wins on cost, reliability, or safety are "
                "reported transparently and are not treated as benchmark failure."
            ),
        },
        "no_harm_endpoint": {
            "name": "no_harm_when_spec_complete",
            "metric_path": "metrics.no_harm_when_spec_complete",
            "success_condition": (
                "No memory injection or stale route revival when the current prompt "
                "already carries the full correct task context."
            ),
        },
        "baseline_arms": {
            "oracle_fresh_context_spec_loop": {
                "role": "upper_bound_no_harm_control",
                "primary_opponent": False,
                "expected_short_task_winner": "fresh_context_or_memory_silence",
            },
            "realistic_fresh_context_handoff_loop": {
                "role": "primary_reset_baseline",
                "primary_opponent": True,
                "applies_when": "handoff_or_summary_is_incomplete_lossy_or_stale",
            },
            "continuous_agent_with_aippocampus": {
                "role": "memory_layer_under_test",
                "primary_opponent": False,
            },
            "bare_continuous_no_memory": {
                "role": "context_degradation_control",
                "primary_opponent": False,
            },
        },
    }


def run_benchmark(
    *,
    include_private_text: bool = False,
    case_limit: int | None = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    all_sequences = sequence_cases()
    all_sequence_steps = [
        step for sequence in all_sequences for step in sequence.steps
    ]
    all_cases = fixture_cases() + all_sequence_steps
    cases = all_cases
    if case_limit and case_limit > 0:
        cases = cases[:case_limit]
    diagnostic_subset = len(cases) < len(all_cases)
    rows = [
        evaluate_case(case, include_private_text=include_private_text)
        for case in cases
    ]
    sequence_rows = (
        []
        if diagnostic_subset
        else [
            evaluate_sequence_case(
                sequence,
                include_private_text=include_private_text,
            )
            for sequence in all_sequences
        ]
    )
    metrics = summarize_results(rows)
    metrics["no_harm_when_spec_complete"] = no_harm_when_spec_complete(rows)
    coverage = coverage_summary(rows)
    coverage_density = coverage_density_summary(rows)
    sequence_coverage = sequence_coverage_summary(sequence_rows)
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
        and metrics["no_harm_when_spec_complete"]["ok"]
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
        "benchmark_framing": benchmark_framing(),
        "coverage": coverage,
        "coverage_density": coverage_density,
        "sequence_coverage": sequence_coverage,
        "cases": rows,
        "sequences": sequence_rows,
        "privacy_boundary": {
            "raw_correction_text_emitted": bool(include_private_text),
            "raw_source_refs_emitted": bool(include_private_text),
            "absolute_paths_emitted": False,
            "case_selection_filters_active": True,
            "case_selection_filter_policy": (
                "aippocampus_runtime.safety.benchmark_sensitive_text_policy"
            ),
            "case_selection_action": "synthetic_cases_checked_for_sensitive_debug_text",
            "include_private_text_scope": "local_debug_only",
            "case_ids_are_hashed": not include_private_text,
            "output_shape": "sanitized_compaction_continuity_aggregates",
        },
        "cannot_claim": [
            "complete_spec_fresh_context_is_not_primary_opponent",
            "live_codex_host_behavior",
            "live_hook_capture",
            "live_semantic_adjudication_quality",
            "memory_useful_when_current_prompt_contains_full_correct_context",
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
