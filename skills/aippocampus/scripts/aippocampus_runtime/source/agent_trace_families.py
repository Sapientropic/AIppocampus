"""Trace-family normalization and public-safe trace tokens."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any

from aippocampus_runtime.core import stable_json_join_id
from aippocampus_runtime.privacy import redact_private_paths, redact_sensitive_values
from aippocampus_runtime.recall.feedback.vocabulary import (
    POSITIVE_FEEDBACK_SIGNALS,
    normalize_feedback_signal,
)

RAW_TRACE_FAMILIES = {
    "raw_stdout",
    "raw_stderr",
    "full_command_args",
    "raw_tool_output",
    "selector_cache_internal",
    "policy_gate_matrix",
}
IGNORE_FAMILIES = {"routine_commentary", "chain_of_thought_like_process"}
SOURCE_OPEN_FAMILIES = {
    "successful_source_open_receipt",
    "successful_recall_deepen_source_open",
}
CHECK_RECEIPT_FAMILIES = {"successful_test_check_event", "successful_tool_check_receipt"}
ROUTE_NOTE_FAMILIES = {"joined_route_note", "agent_trajectory"}
FINAL_CLOSEOUT_FAMILIES = {"final_answer_closeout", "assistant_final_answer_closeout"}
REPO_BREADCRUMB_FAMILIES = {"repo_breadcrumb", "safe_repo_relative_breadcrumb"}
ASSISTANT_FINAL_PRODUCER_FAMILY = "assistant_final"
TOOL_CALL_SUCCEEDED_PRODUCER_FAMILY = "tool_call_succeeded"
TEST_CHECK_SUCCEEDED_PRODUCER_FAMILY = "test_check_succeeded"
FAMILY_ALIASES = {
    ASSISTANT_FINAL_PRODUCER_FAMILY: "final_answer_closeout",
    "assistant_final_answer": "assistant_final_answer_closeout",
    "final_closeout": "final_answer_closeout",
    TOOL_CALL_SUCCEEDED_PRODUCER_FAMILY: "successful_tool_check_receipt",
    TEST_CHECK_SUCCEEDED_PRODUCER_FAMILY: "successful_test_check_event",
}
TRACE_FAMILY_PRODUCER_CONTRACT = {
    "rollout_search.final_assistant_payload": ASSISTANT_FINAL_PRODUCER_FAMILY,
    "behavior_events.successful_tool_call": TOOL_CALL_SUCCEEDED_PRODUCER_FAMILY,
}
TRACE_FAMILY_RUNTIME_PRODUCER_SITES = {
    ASSISTANT_FINAL_PRODUCER_FAMILY: (
        "skills/aippocampus/scripts/aippocampus_runtime/recall/rollout_search.py",
        "ASSISTANT_FINAL_PRODUCER_FAMILY",
    ),
    TOOL_CALL_SUCCEEDED_PRODUCER_FAMILY: (
        "skills/aippocampus/scripts/aippocampus_runtime/source/behavior_events.py",
        "TOOL_CALL_SUCCEEDED_PRODUCER_FAMILY",
    ),
}
TRACE_FAMILY_NON_RUNTIME_PRODUCER_CONTRACT = {
    "test_check.successful_check": {
        "family": TEST_CHECK_SUCCEEDED_PRODUCER_FAMILY,
        "category": "external_or_future_or_test_only",
        "reason": (
            "Admitted as a known receipt family, but no AIppocampus runtime "
            "producer currently emits this token."
        ),
    }
}
KNOWN_TRACE_FAMILIES = (
    RAW_TRACE_FAMILIES
    | IGNORE_FAMILIES
    | SOURCE_OPEN_FAMILIES
    | CHECK_RECEIPT_FAMILIES
    | ROUTE_NOTE_FAMILIES
    | FINAL_CLOSEOUT_FAMILIES
    | REPO_BREADCRUMB_FAMILIES
)
POSITIVE_SOURCE_OPEN_OUTCOMES = POSITIVE_FEEDBACK_SIGNALS | {
    "source_open_hit",
    "actionable_reopenable_route",
}

SECRET_OR_PATH_RE = re.compile(
    r"(?i)(api[_-]?key|secret|token|password|passwd|bearer|authorization|"
    r"sk-[a-z0-9]|[a-z]:[\\/]|/(?:users|home|tmp|private|var)/)"
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def declared_trace_family_producer_values() -> frozenset[str]:
    """Return runtime-owned producer family tokens that must stay admitted.

    Tests read this owner contract instead of mirroring producer values in a
    second hand-written set. Producers should reference the constants above so
    a future token change updates the producer and consumer boundary together.
    """

    return frozenset(TRACE_FAMILY_PRODUCER_CONTRACT.values())


def declared_non_runtime_trace_family_producer_values() -> frozenset[str]:
    """Return admitted producer tokens that are not runtime coverage claims."""

    return frozenset(
        str(item.get("family") or "")
        for item in TRACE_FAMILY_NON_RUNTIME_PRODUCER_CONTRACT.values()
        if item.get("family")
    )


def _safe_family_id(value: Any) -> str:
    text = _text(value).casefold()
    if not text:
        return ""
    redacted = redact_sensitive_values(redact_private_paths(text))
    if redacted != text or SECRET_OR_PATH_RE.search(redacted):
        return stable_json_join_id(
            "family",
            redacted,
            ensure_ascii=False,
            default_str=False,
            length=20,
        )
    return re.sub(r"[^a-z0-9_.:-]+", "_", redacted).strip("_")[:80]


def raw_family(row: Mapping[str, Any]) -> str:
    explicit = _text(row.get("trace_family") or row.get("family")).casefold()
    if explicit:
        return explicit
    hard_event_kind = _text(row.get("hard_event_kind")).casefold()
    if hard_event_kind in FAMILY_ALIASES or hard_event_kind in KNOWN_TRACE_FAMILIES:
        return hard_event_kind
    event_kind = _text(row.get("event_kind")).casefold()
    if event_kind:
        return event_kind
    signal = normalize_feedback_signal(
        _text(row.get("signal") or row.get("outcome")).casefold()
    )
    if signal in POSITIVE_SOURCE_OPEN_OUTCOMES:
        return "successful_recall_deepen_source_open"
    return _text(row.get("kind")).casefold()


def normalized_family(row: Mapping[str, Any]) -> str:
    raw = raw_family(row)
    return FAMILY_ALIASES.get(raw, raw)


def unknown_family(row: Mapping[str, Any]) -> str:
    raw = raw_family(row)
    if not raw:
        return ""
    family = FAMILY_ALIASES.get(raw, raw)
    if family in KNOWN_TRACE_FAMILIES:
        return ""
    return _safe_family_id(raw)


def safe_optional_token(value: Any, *, prefix: str) -> str:
    text = _text(value)
    if not text:
        return ""
    redacted = redact_sensitive_values(redact_private_paths(text))
    if redacted != text or SECRET_OR_PATH_RE.search(redacted):
        return stable_json_join_id(
            prefix,
            redacted,
            ensure_ascii=False,
            default_str=False,
            length=20,
        )
    return redacted[:160]


def contains_private_shape(row: Mapping[str, Any]) -> bool:
    redacted = redact_sensitive_values(redact_private_paths(dict(row)))
    blob = json.dumps(redacted, ensure_ascii=False, sort_keys=True, default=str)
    return bool(SECRET_OR_PATH_RE.search(blob))
