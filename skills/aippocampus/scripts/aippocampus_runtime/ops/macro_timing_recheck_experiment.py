"""Public-safe macro timing recheck experiment for #1314."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from aippocampus_runtime.macro import timing


def _case(
    case_id: str,
    *,
    events: list[dict[str, Any]],
    quiet_source_event_count: int,
    project_activity_level: timing.ProjectActivityLevel = "normal",
    existing_temporal_head_covers: bool,
    existing_currentness_head_covers: bool,
    expected_distinct_signal: bool,
) -> dict[str, Any]:
    packet = timing.build_macro_timing_report(
        events,
        quiet_source_event_count=quiet_source_event_count,
        project_activity_level=project_activity_level,
    )
    return {
        "case_id": case_id,
        "packet": packet,
        "comparison": {
            "existing_temporal_head_covers": existing_temporal_head_covers,
            "existing_currentness_head_covers": existing_currentness_head_covers,
            "distinct_signal": bool(packet["distinct_signal"]) == expected_distinct_signal,
            "distinct_signal_kind": (
                "active_axis_or_cadence_recheck"
                if expected_distinct_signal
                else "covered_by_existing_heads_or_below_threshold"
            ),
        },
    }


def _fixture_cases() -> list[dict[str, Any]]:
    return [
        _case(
            "active_axis_workflow_success",
            events=[
                {
                    "event_id": "workflow-success",
                    "line": 4,
                    "route_success_delta": 0.7,
                    "support_delta": 0.2,
                    "source_epoch": 8,
                    "recency_rank": 1,
                    "currentness_status": "current",
                },
                {
                    "event_id": "roadmap-support",
                    "line": 5,
                    "support_delta": 0.2,
                    "source_epoch": 7,
                    "recency_rank": 2,
                    "currentness_status": "current",
                },
            ],
            quiet_source_event_count=2,
            existing_temporal_head_covers=False,
            existing_currentness_head_covers=False,
            expected_distinct_signal=True,
        ),
        _case(
            "stale_claim_axis_recheck",
            events=[
                {
                    "event_id": "claim-counter-evidence",
                    "line": 2,
                    "counter_evidence_delta": 0.4,
                    "staleness_delta": 0.3,
                    "source_epoch": 11,
                    "recency_rank": 1,
                    "currentness_status": "stale",
                }
            ],
            quiet_source_event_count=2,
            existing_temporal_head_covers=False,
            existing_currentness_head_covers=True,
            expected_distinct_signal=False,
        ),
        _case(
            "source_epoch_cadence_recheck",
            events=[
                {"event_id": "quiet-1", "line": 3, "source_epoch": 1},
                {"event_id": "quiet-2", "line": 3, "source_epoch": 5},
            ],
            quiet_source_event_count=5,
            existing_temporal_head_covers=False,
            existing_currentness_head_covers=False,
            expected_distinct_signal=True,
        ),
        _case(
            "slow_quiet_project_below_threshold",
            events=[
                {"event_id": "quiet-1", "line": 4, "source_epoch": 1},
            ],
            quiet_source_event_count=5,
            project_activity_level="slow_quiet",
            existing_temporal_head_covers=False,
            existing_currentness_head_covers=False,
            expected_distinct_signal=False,
        ),
    ]


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def build_macro_timing_recheck_experiment_report() -> dict[str, Any]:
    cases = _fixture_cases()
    distinct_signal_count = sum(
        int(bool(_as_mapping(case["comparison"]).get("distinct_signal")))
        for case in cases
    )
    claim_without_source_reopen_count = sum(
        int(bool(_as_mapping(case["packet"]).get("fact_claim_allowed")))
        for case in cases
    )
    currentness_mutation_count = sum(
        int(_as_mapping(_as_mapping(case["packet"]).get("active_axis")).get("currentness_status") != "unchanged")
        for case in cases
    )
    return {
        "kind": "macro_timing_recheck_experiment",
        "source_issue": "#1314",
        "ok": (
            distinct_signal_count >= 2
            and claim_without_source_reopen_count == 0
            and currentness_mutation_count == 0
        ),
        "case_count": len(cases),
        "distinct_signal_count": distinct_signal_count,
        "claim_without_source_reopen_count": claim_without_source_reopen_count,
        "currentness_mutation_count": currentness_mutation_count,
        "default_adoption_allowed": False,
        "promotion_status": "fixture_candidate_not_promoted",
        "boundary": {
            "public_safe_fixture_only": True,
            "not_live_recall_adoption": True,
            "not_classical_calendar_timing": True,
            "not_currentness_or_temporal_head_replacement": True,
        },
        "cases": cases,
    }


__all__ = ["build_macro_timing_recheck_experiment_report"]
