#!/usr/bin/env python3
"""Public-safe Cognitive Observatory projection for cognitive-load reports."""

from __future__ import annotations

import re
from typing import Any, Mapping

SUMMARY_KIND = "aippocampus_observatory_cognitive_load_calibration_summary"
SAFE_TOKEN_RE = re.compile(r"^[A-Za-z0-9_.-]{1,96}$")


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _as_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _as_float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _safe_token_or_none(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text if SAFE_TOKEN_RE.fullmatch(text) else None


def _safe_token(value: Any, *, default: str) -> str:
    return _safe_token_or_none(value) or default


def _first_safe_token(*values: Any, default: str) -> str:
    for value in values:
        token = _safe_token_or_none(value)
        if token is not None:
            return token
    return default


def _safe_count_mapping(value: Any) -> dict[str, int]:
    counts: dict[str, int] = {}
    if not isinstance(value, Mapping):
        return counts
    for key, raw_count in value.items():
        safe_key = _safe_token_or_none(key) or "unsafe_or_unknown"
        counts[safe_key] = counts.get(safe_key, 0) + _as_int(raw_count)
    return counts


def _cannot_claim(payload: Mapping[str, Any], report: Mapping[str, Any]) -> list[str]:
    values = {
        "cognitive_load_summary_is_source_truth",
        "cognitive_load_summary_proves_user_visible_lift",
        "cognitive_load_summary_is_host_timing_quality",
        *[
            token
            for item in _as_list(payload.get("cannot_claim"))
            if (token := _safe_token_or_none(item))
        ],
        *[
            token
            for item in _as_list(report.get("cannot_claim"))
            if (token := _safe_token_or_none(item))
        ],
    }
    return sorted(item for item in values if item)


def cognitive_load_calibration_summary(payload: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """Return the Observatory-safe subset of a cognitive-load calibration.

    The private calibration report may include source-ref hash samples or local
    operator diagnostics that are fine for a private `.tmp` run but unnecessary
    in the Observatory. This projection keeps only counts, rates, status, and
    cannot-claim boundaries.
    """

    if not isinstance(payload, Mapping):
        return None
    payload_metrics = _as_mapping(payload.get("metrics"))
    report = _as_mapping(payload.get("calibration_report") or payload)
    input_surface = _as_mapping(payload.get("input_surface"))
    extraction = _as_mapping(payload.get("extraction_metrics"))
    report_metrics = _as_mapping(report.get("metrics"))
    sidecar_metrics = {
        **report_metrics,
        **_as_mapping(payload.get("sidecar_metrics")),
        **payload_metrics,
    }
    sidecar_projection = _as_mapping(payload.get("sidecar_projection"))
    report_issue_readouts = _as_mapping(report.get("issue_readouts"))
    payload_issue_readouts = _as_mapping(payload.get("issue_readouts"))
    issue_readouts = {**report_issue_readouts, **payload_issue_readouts}
    report_github_575 = _as_mapping(_as_mapping(report_issue_readouts.get("github_575")))
    payload_github_575 = _as_mapping(_as_mapping(payload_issue_readouts.get("github_575")))
    github_575 = _as_mapping(issue_readouts.get("github_575"))
    status = _first_safe_token(
        payload.get("status"),
        github_575.get("public_behavior_trace_feedback"),
        github_575.get("private_real_history_calibration"),
        default="unknown",
    )
    reason_counts = _safe_count_mapping(sidecar_projection.get("reason_code_counts"))
    bucket_counts = _safe_count_mapping(sidecar_projection.get("load_bucket_counts"))

    return {
        "kind": SUMMARY_KIND,
        "source_kind": _first_safe_token(payload.get("kind"), report.get("kind"), default="unknown"),
        "status": status,
        "authority": "diagnostic_only",
        "no_write": True,
        "navigation_only": True,
        "projection_boundary": "routing_caution_not_affect_or_personality_truth",
        "metrics": {
            "thread_count_scanned": _as_int(input_surface.get("thread_count_scanned")),
            "threads_with_signal_count": _as_int(input_surface.get("threads_with_signal_count")),
            "message_rows_scanned": _as_int(input_surface.get("message_rows_scanned")),
            "event_rows_scanned": _as_int(input_surface.get("event_rows_scanned")),
            "signal_event_count": _as_int(extraction.get("signal_event_count")),
            "message_signal_event_count": _as_int(
                extraction.get("message_signal_event_count")
            ),
            "behavior_signal_event_count": _as_int(
                extraction.get("behavior_signal_event_count")
            ),
            "sidecar_entry_count": _as_int(sidecar_metrics.get("entry_count")),
            "max_load_boost": _as_float_or_none(sidecar_metrics.get("max_load_boost")),
            "load_weight_decay_coverage": _as_float_or_none(
                sidecar_metrics.get("load_weight_decay_coverage")
            ),
            "load_weight_false_positive_rate": _as_float_or_none(
                sidecar_metrics.get("load_weight_false_positive_rate")
            ),
            "caution_hint_useful_rate": _as_float_or_none(
                sidecar_metrics.get("caution_hint_useful_rate")
            ),
            "public_behavior_trace_case_count": _as_int(
                sidecar_metrics.get("public_behavior_trace_case_count")
            ),
            "reviewed_feedback_case_count": _as_int(
                sidecar_metrics.get("reviewed_feedback_case_count")
            ),
            "helpful_caution_hint_count": _as_int(
                sidecar_metrics.get("helpful_caution_hint_count")
            ),
            "irrelevant_load_drag_count": _as_int(
                sidecar_metrics.get("irrelevant_load_drag_count")
            ),
            "irrelevant_load_drag_rate": _as_float_or_none(
                sidecar_metrics.get("irrelevant_load_drag_rate")
            ),
            "overpersonalization_from_load_signal_count": _as_int(
                sidecar_metrics.get("overpersonalization_from_load_signal_count")
            ),
        },
        "load_bucket_counts": bucket_counts,
        "reason_code_counts": reason_counts,
        "issue_readouts": {
            "github_575": {
                "public_behavior_trace_feedback": _safe_token(
                    github_575.get("public_behavior_trace_feedback"),
                    default="not_measured",
                ),
                "false_positive_rate": _as_float_or_none(
                    github_575.get("false_positive_rate")
                ),
                "caution_hint_useful_rate": _as_float_or_none(
                    github_575.get("caution_hint_useful_rate")
                ),
                "irrelevant_load_drag_rate": _as_float_or_none(
                    github_575.get("irrelevant_load_drag_rate")
                ),
                "private_real_history_calibration": _first_safe_token(
                    payload_github_575.get("private_real_history_calibration"),
                    report_github_575.get("private_real_history_calibration"),
                    status,
                    default=status,
                ),
                "live_hook_capture": _safe_token(
                    github_575.get("live_hook_capture"),
                    default="not_run",
                ),
                "host_timing_quality": _safe_token(
                    github_575.get("host_timing_quality"),
                    default="not_measured",
                ),
                "closeout_eligible": bool(github_575.get("closeout_eligible")),
            }
        },
        "privacy_boundary": {
            "raw_private_text_serialized": False,
            "raw_source_handles_serialized": False,
            "raw_command_text_serialized": False,
            "local_paths_serialized": False,
            "thread_ids_serialized": False,
            "message_ids_serialized": False,
        },
        "contract": {
            "read_only_report": True,
            "not_control_plane": True,
            "load_is_routing_metadata_only": True,
            "source_truth_unchanged": True,
            "affect_or_personality_truth_blocked": True,
        },
        "cannot_claim": _cannot_claim(payload, report),
    }
