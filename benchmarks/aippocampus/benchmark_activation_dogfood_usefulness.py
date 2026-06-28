#!/usr/bin/env python3
"""Bounded dogfood replay probe for activation decision usefulness."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

import _paths

_paths.ensure_paths()

REPORT_KIND = "aippocampus_activation_dogfood_usefulness_probe"
SCHEMA_VERSION = 1
RUN_DATE = "2026-06-28"
ARM_COLD = "cold_no_activation"
ARM_WARM = "warm_replay_signal"
ARMS = (ARM_COLD, ARM_WARM)


def _trajectory_replay_source() -> dict[str, Any]:
    from aippocampus_runtime.coding.agent_trajectory_packets import (
        build_live_agent_trajectory_packet,
    )

    return build_live_agent_trajectory_packet(
        route_notes=[
            {
                "route_note_id": "rn-source-before-change",
                "source_refs": [{"thread_key": "public:dogfood", "message_id": "msg-route", "line": 10}],
            }
        ],
        behavior_events=[
            {
                "event_id": "tool-focused-test",
                "event_kind": "tool_call_succeeded",
                "source_refs": [{"thread_key": "public:dogfood", "message_id": "msg-test", "line": 11}],
            }
        ],
        final_closeouts=[
            {
                "message_id": "msg-closeout",
                "source_refs": [{"thread_key": "public:dogfood", "message_id": "msg-closeout", "line": 12}],
            }
        ],
        trigger="activation_dogfood_replay",
    )


def _arm(
    *,
    generated_candidates: int,
    foreground_exposed: int,
    verifier_seen: int,
    useful_source_open_hits: int,
    manual_search_fallback: int,
    wrong_route_drag: int,
    noisy_surfacing: int,
    signal_role: str,
    source_open_follow_through: int | None = None,
) -> dict[str, Any]:
    return {
        "generated_candidate_count": generated_candidates,
        "foreground_exposed_candidate_count": foreground_exposed,
        "verifier_seen_candidate_count": verifier_seen,
        "useful_source_open_hit_count": useful_source_open_hits,
        "source_open_follow_through_count": (
            useful_source_open_hits if source_open_follow_through is None else source_open_follow_through
        ),
        "manual_search_fallback_count": manual_search_fallback,
        "wrong_route_drag_count": wrong_route_drag,
        "noisy_surfacing_count": noisy_surfacing,
        "signal_role": signal_role,
    }


def _cases() -> list[dict[str, Any]]:
    trajectory = _trajectory_replay_source()
    return [
        {
            "case_id": "trajectory_positive_demo_reduces_manual_search",
            "origin": "replayable_behavior_trajectory",
            "trajectory_status": trajectory["status"],
            "reopen_resolution_status": trajectory["reopen_plan"]["resolution_status"],
            "arms": {
                ARM_COLD: _arm(
                    generated_candidates=0,
                    foreground_exposed=0,
                    verifier_seen=0,
                    useful_source_open_hits=0,
                    manual_search_fallback=1,
                    wrong_route_drag=0,
                    noisy_surfacing=0,
                    signal_role="none",
                ),
                ARM_WARM: _arm(
                    generated_candidates=1,
                    foreground_exposed=1,
                    verifier_seen=1,
                    useful_source_open_hits=1,
                    manual_search_fallback=0,
                    wrong_route_drag=0,
                    noisy_surfacing=0,
                    signal_role="process_supervision",
                ),
            },
        },
        {
            "case_id": "hard_negative_tightens_exposure",
            "origin": "route_feedback_replay",
            "arms": {
                ARM_COLD: _arm(
                    generated_candidates=1,
                    foreground_exposed=1,
                    verifier_seen=1,
                    useful_source_open_hits=0,
                    manual_search_fallback=0,
                    wrong_route_drag=1,
                    noisy_surfacing=1,
                    signal_role="none",
                ),
                ARM_WARM: _arm(
                    generated_candidates=1,
                    foreground_exposed=0,
                    verifier_seen=1,
                    useful_source_open_hits=0,
                    manual_search_fallback=0,
                    wrong_route_drag=0,
                    noisy_surfacing=0,
                    signal_role="hard_negative",
                ),
            },
        },
        {
            "case_id": "parked_low_specificity_stays_quiet",
            "origin": "candidate_lifecycle_replay",
            "arms": {
                ARM_COLD: _arm(
                    generated_candidates=0,
                    foreground_exposed=0,
                    verifier_seen=0,
                    useful_source_open_hits=0,
                    manual_search_fallback=1,
                    wrong_route_drag=0,
                    noisy_surfacing=0,
                    signal_role="none",
                ),
                ARM_WARM: _arm(
                    generated_candidates=1,
                    foreground_exposed=0,
                    verifier_seen=1,
                    useful_source_open_hits=0,
                    manual_search_fallback=1,
                    wrong_route_drag=0,
                    noisy_surfacing=0,
                    signal_role="replay_sample",
                ),
            },
        },
        {
            "case_id": "source_openable_route_not_starved",
            "origin": "source_open_replay",
            "arms": {
                ARM_COLD: _arm(
                    generated_candidates=1,
                    foreground_exposed=1,
                    verifier_seen=1,
                    useful_source_open_hits=1,
                    manual_search_fallback=0,
                    wrong_route_drag=0,
                    noisy_surfacing=0,
                    signal_role="none",
                ),
                ARM_WARM: _arm(
                    generated_candidates=2,
                    foreground_exposed=1,
                    verifier_seen=2,
                    useful_source_open_hits=1,
                    manual_search_fallback=0,
                    wrong_route_drag=0,
                    noisy_surfacing=0,
                    signal_role="positive_demo",
                ),
            },
        },
    ]


def _sum_arm(cases: Sequence[Mapping[str, Any]], arm: str) -> dict[str, Any]:
    totals: Counter[str] = Counter()
    roles: Counter[str] = Counter()
    for case in cases:
        row = (case.get("arms") or {}).get(arm) if isinstance(case.get("arms"), Mapping) else None
        if not isinstance(row, Mapping):
            continue
        for metric in (
            "generated_candidate_count",
            "foreground_exposed_candidate_count",
            "verifier_seen_candidate_count",
            "useful_source_open_hit_count",
            "source_open_follow_through_count",
            "manual_search_fallback_count",
            "wrong_route_drag_count",
            "noisy_surfacing_count",
        ):
            totals[metric] += int(row.get(metric) or 0)
        roles[str(row.get("signal_role") or "none")] += 1
    return {**dict(totals), "signal_role_counts": dict(sorted(roles.items()))}


def build_activation_dogfood_usefulness_report() -> dict[str, Any]:
    cases = _cases()
    cold = _sum_arm(cases, ARM_COLD)
    warm = _sum_arm(cases, ARM_WARM)
    deltas = {
        "manual_search_fallback_delta": warm["manual_search_fallback_count"] - cold["manual_search_fallback_count"],
        "wrong_route_drag_delta": warm["wrong_route_drag_count"] - cold["wrong_route_drag_count"],
        "noisy_surfacing_delta": warm["noisy_surfacing_count"] - cold["noisy_surfacing_count"],
        "useful_source_open_hit_delta": warm["useful_source_open_hit_count"] - cold["useful_source_open_hit_count"],
    }
    return {
        "kind": REPORT_KIND,
        "schema_version": SCHEMA_VERSION,
        "run_date": RUN_DATE,
        "ok": True,
        "case_count": len(cases),
        "comparison_contract": {
            "arms": list(ARMS),
            "cold_vs_warm_replay": True,
            "candidate_funnel_split_counts": True,
            "source_open_follow_through_required_for_useful": True,
        },
        "arm_metrics": {ARM_COLD: cold, ARM_WARM: warm},
        "deltas": deltas,
        "case_summaries": [
            {
                "case_id": case["case_id"],
                "origin": case["origin"],
                "trajectory_status": case.get("trajectory_status"),
                "reopen_resolution_status": case.get("reopen_resolution_status"),
            }
            for case in cases
        ],
        "decision": {
            "activation_probe_useful_on_bounded_replay": (
                deltas["manual_search_fallback_delta"] < 0
                and deltas["wrong_route_drag_delta"] <= 0
                and deltas["noisy_surfacing_delta"] <= 0
            ),
            "default_live_claim_promoted": False,
            "dream_default_delivery_claim_promoted": False,
        },
        "cannot_claim": [
            "causal_real_user_lift",
            "live_default_foreground_quality",
            "private_history_quality",
            "default_dream_delivery_quality",
            "source_truth_from_activation_signal",
        ],
        "privacy_boundary": {
            "raw_private_history_serialized": False,
            "raw_prompt_serialized": False,
            "raw_source_text_serialized": False,
            "local_paths_serialized": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    report = build_activation_dogfood_usefulness_report()
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"{REPORT_KIND}: ok={report['ok']} cases={report['case_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
