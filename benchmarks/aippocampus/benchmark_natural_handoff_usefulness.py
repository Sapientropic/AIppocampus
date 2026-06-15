#!/usr/bin/env python3
"""Public-safe natural handoff usefulness validation for #1185/#1384.

This is a bounded synthetic cohort, not a live host claim. It exercises the
default-session shapes called out in #1185 comments: actionable natural
handoff, lightly cued multilingual continuity, neutral no-help ambiguity, and
safe-but-useless regressions that should block promotion.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

import _paths

_paths.ensure_paths()

from aippocampus_runtime.recall.continuity_usefulness import continuity_usefulness_metrics

SCHEMA_VERSION = 1
KIND = "aippocampus_natural_handoff_usefulness_validation"


@dataclass(frozen=True)
class HandoffCase:
    case_id: str
    scenario_role: str
    cue_profile: str
    language: str
    expected_outcome: str
    route_available: bool
    recall_attempted: bool
    clarification_prompted: bool
    surface: Mapping[str, Any]


def _synthetic_cases() -> list[HandoffCase]:
    return [
        HandoffCase(
            case_id="natural_handoff_actionable_route_win",
            scenario_role="natural_handoff",
            cue_profile="lossy_handoff_with_reopenable_route",
            language="en",
            expected_outcome="win",
            route_available=True,
            recall_attempted=True,
            clarification_prompted=False,
            surface={
                "packet_count": 1,
                "useful_packet_count": 1,
                "packet_triage_distinctiveness": 0.92,
                "safe_route_evidence_present_count": 1,
                "copy_pasteable_deepen_target_present_count": 1,
                "action_permission_level": "actionable_route",
                "recall_to_source_reopen_attempt_count": 1,
                "recall_to_source_reopen_success_count": 1,
                "time_to_first_useful_packet_ms_proxy": 110,
                "foreground_protocol_noise_bytes": 36,
                "useful_guidance_bytes": 440,
            },
        ),
        HandoffCase(
            case_id="default_session_light_multilingual_cue_win",
            scenario_role="default_session",
            cue_profile="light_continuity_cue_multilingual",
            language="ar",
            expected_outcome="win",
            route_available=True,
            recall_attempted=True,
            clarification_prompted=False,
            surface={
                "packet_count": 1,
                "useful_packet_count": 1,
                "packet_triage_distinctiveness": 0.84,
                "safe_route_evidence_present_count": 1,
                "copy_pasteable_deepen_target_present_count": 1,
                "fresh_agent_active_pull_success_count": 1,
                "action_permission_level": "actionable_route",
                "recall_to_source_reopen_attempt_count": 1,
                "recall_to_source_reopen_success_count": 1,
                "time_to_first_useful_packet_ms_proxy": 145,
                "foreground_protocol_noise_bytes": 44,
                "useful_guidance_bytes": 360,
            },
        ),
        HandoffCase(
            case_id="pure_deictic_ambiguous_no_help",
            scenario_role="default_session",
            cue_profile="pure_deictic_ambiguous",
            language="ar",
            expected_outcome="no_help",
            route_available=False,
            recall_attempted=False,
            clarification_prompted=True,
            surface={
                "packet_count": 1,
                "useful_packet_count": 0,
                "packet_triage_distinctiveness": 1.0,
                "time_to_first_useful_packet_ms_proxy": 250,
                "foreground_protocol_noise_bytes": 12,
                "useful_guidance_bytes": 52,
            },
        ),
        HandoffCase(
            case_id="correct_but_noisy_packet_regression",
            scenario_role="natural_handoff",
            cue_profile="protocol_dump_with_valid_route",
            language="en",
            expected_outcome="regression",
            route_available=True,
            recall_attempted=True,
            clarification_prompted=False,
            surface={
                "packet_count": 1,
                "useful_packet_count": 1,
                "packet_triage_distinctiveness": 0.78,
                "safe_route_evidence_present_count": 1,
                "copy_pasteable_deepen_target_present_count": 1,
                "action_permission_level": "actionable_route",
                "time_to_first_useful_packet_ms_proxy": 170,
                "foreground_protocol_noise_bytes": 780,
                "useful_guidance_bytes": 180,
            },
        ),
        HandoffCase(
            case_id="safe_route_demoted_to_scent_regression",
            scenario_role="default_session",
            cue_profile="safe_route_collapsed_to_scent",
            language="en",
            expected_outcome="regression",
            route_available=True,
            recall_attempted=True,
            clarification_prompted=False,
            surface={
                "packet_count": 1,
                "useful_packet_count": 1,
                "packet_triage_distinctiveness": 0.76,
                "safe_route_evidence_present_count": 1,
                "copy_pasteable_deepen_target_present_count": 0,
                "action_permission_level": "scent",
                "usefulness_lost_by_demoting_to_scent_count": 1,
                "time_to_first_useful_packet_ms_proxy": 130,
                "foreground_protocol_noise_bytes": 70,
                "useful_guidance_bytes": 260,
            },
        ),
        HandoffCase(
            case_id="wrong_route_drag_before_recall_regression",
            scenario_role="natural_handoff",
            cue_profile="stale_route_drag",
            language="en",
            expected_outcome="regression",
            route_available=True,
            recall_attempted=True,
            clarification_prompted=False,
            surface={
                "packet_count": 1,
                "useful_packet_count": 1,
                "packet_triage_distinctiveness": 0.66,
                "safe_route_evidence_present_count": 1,
                "copy_pasteable_deepen_target_present_count": 1,
                "action_permission_level": "actionable_route",
                "wrong_route_drag_count": 1,
                "fresh_agent_broad_search_before_recall_count": 1,
                "time_to_first_useful_packet_ms_proxy": 310,
                "foreground_protocol_noise_bytes": 92,
                "useful_guidance_bytes": 280,
            },
        ),
    ]


def _observed_outcome(case: HandoffCase, metrics: Mapping[str, Any]) -> str:
    if metrics.get("quality_gate_ok"):
        return "win"
    if not case.route_available and case.expected_outcome == "no_help":
        return "no_help"
    return "regression"


def _rate(count: int, total: int) -> float:
    return 1.0 if total <= 0 else round(count / total, 4)


def _success_rate(rows: Iterable[Mapping[str, Any]], role: str) -> float:
    selected = [row for row in rows if row["scenario_role"] == role and row["route_available"]]
    wins = sum(1 for row in selected if row["observed_outcome"] == "win")
    return _rate(wins, len(selected))


def build_report() -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for case in _synthetic_cases():
        metrics = continuity_usefulness_metrics(case.surface)
        row = {
            "case_id": case.case_id,
            "scenario_role": case.scenario_role,
            "cue_profile": case.cue_profile,
            "language": case.language,
            "expected_outcome": case.expected_outcome,
            "observed_outcome": _observed_outcome(case, metrics),
            "route_available": case.route_available,
            "recall_attempted": case.recall_attempted,
            "clarification_prompted": case.clarification_prompted,
            "metrics": metrics,
        }
        rows.append(row)

    observed_counts = {
        outcome: sum(1 for row in rows if row["observed_outcome"] == outcome)
        for outcome in ("win", "no_help", "regression")
    }
    route_rows = [row for row in rows if row["route_available"]]
    implicit_rows = [row for row in rows if row["cue_profile"].startswith(("pure_deictic", "light_"))]
    implicit_success = sum(
        1 for row in implicit_rows if row["recall_attempted"] or row["clarification_prompted"]
    )
    blocker_counts: dict[str, int] = {}
    for row in rows:
        row_metrics: Mapping[str, Any] = row["metrics"] if isinstance(row["metrics"], Mapping) else {}
        for blocker in row_metrics.get("usefulness_blockers") or []:
            blocker_counts[blocker] = blocker_counts.get(blocker, 0) + 1

    return {
        "kind": KIND,
        "schema_version": SCHEMA_VERSION,
        "ok": True,
        "benchmark_maturity_level": "diagnostic_proxy",
        "measurement_origin": "synthetic_fixture",
        "observed_agent_behavior": False,
        "contract_gate_ok": True,
        "public_quality_gate_ok": False,
        "decision_impact": "issue_closeout_candidate",
        "decision_impact_gate_ok": False,
        "requires_human_review_before_closeout": True,
        "decision_impact_reason": (
            "bounded synthetic cohort only; useful for issue review, not an "
            "authoritative owner-status or live default-session decision"
        ),
        "issue_scope": ["#1185", "#1384"],
        "validation_scope": "bounded_public_synthetic_default_session_and_handoff_cohort",
        "case_count": len(rows),
        "cases": rows,
        "metrics": {
            "win_count": observed_counts["win"],
            "no_help_count": observed_counts["no_help"],
            "regression_count": observed_counts["regression"],
            "natural_handoff_success_rate": _success_rate(rows, "natural_handoff"),
            "default_session_continuity_success_rate": _success_rate(rows, "default_session"),
            "implicit_context_activation_success_rate": _rate(
                implicit_success, len(implicit_rows)
            ),
            "manual_search_before_recall_count": sum(
                row["metrics"]["fresh_agent_broad_search_before_recall_count"] for row in rows
            ),
            "blind_deepen_required_count": sum(
                row["metrics"]["blind_deepen_required_count"] for row in rows
            ),
            "wrong_route_drag_count": sum(row["metrics"]["wrong_route_drag_count"] for row in rows),
            "safe_route_demoted_to_scent_count": sum(
                row["metrics"]["usefulness_lost_by_demoting_to_scent_count"] for row in rows
            ),
            "route_available_case_count": len(route_rows),
            "blocker_counts": dict(sorted(blocker_counts.items())),
        },
        "promotion_readout": {
            "safety_gate_ok_on_wins": all(
                row["metrics"]["safety_gate_ok"] for row in rows if row["observed_outcome"] == "win"
            ),
            "regressions_block_promotion": observed_counts["regression"] > 0,
            "claim_level": "bounded_synthetic_validation_not_live_product_lift",
            "owner_status_note_non_authoritative": (
                "#1384 appears closeout-ready from this bounded fixture; #1185 "
                "still needs broader default-path evidence."
            ),
            "decision_impact_gate_ok": False,
            "requires_human_review_before_closeout": True,
        },
        "privacy_boundary": {
            "public_safe_synthetic_only": True,
            "raw_private_history_used": False,
            "raw_source_text_emitted": False,
            "local_paths_emitted": False,
            "provider_calls": 0,
        },
        "can_claim": [
            "bounded_public_synthetic_cohort_records_wins_no_help_and_regressions",
            "continuity_usefulness_gate_blocks_safe_but_noisy_or_demoted_route_packets",
            "multilingual_light_cue_and_natural_handoff_shapes_have_replayable_contract_cases",
        ],
        "useful_now": [
            "fixture identifies natural-handoff shapes worth preserving",
            "regression cases show where foreground output loses useful actionability",
        ],
        "agent_action": "use_as_issue_review_input_not_owner_status",
        "can_support_after_action": [
            "human-reviewed issue closeout note for bounded synthetic behavior"
        ],
        "cannot_claim": [
            "broad_default_session_product_lift",
            "private_history_user_visible_lift",
            "live_host_hook_activation_rate",
            "all_deictic_prompts_should_trigger_recall_without_clarification",
        ],
    }


def render_text(report: Mapping[str, Any]) -> str:
    metrics = report["metrics"]
    lines = [
        f"{report['kind']} ({report['validation_scope']})",
        f"cases={report['case_count']} wins={metrics['win_count']} "
        f"no_help={metrics['no_help_count']} regressions={metrics['regression_count']}",
        f"natural_handoff_success_rate={metrics['natural_handoff_success_rate']}",
        f"default_session_continuity_success_rate={metrics['default_session_continuity_success_rate']}",
        f"implicit_context_activation_success_rate={metrics['implicit_context_activation_success_rate']}",
        "cannot_claim=" + ", ".join(report["cannot_claim"]),
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Emit JSON report.")
    args = parser.parse_args()
    report = build_report()
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(render_text(report), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
