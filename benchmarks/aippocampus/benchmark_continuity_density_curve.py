#!/usr/bin/env python3
"""Synthetic continuity-density compounding curve benchmark."""

from __future__ import annotations

import argparse
import json
from typing import Any

SCHEMA_VERSION = 1


SYNTHETIC_TIERS: list[dict[str, Any]] = [
    {
        "tier": "cold",
        "source_trail_density": 0.0,
        "useful_packet_rate": 0.0,
        "source_reopen_success_rate": 0.15,
        "manual_search_step_count": 7.0,
        "wrong_route_drag_rate": 0.04,
    },
    {
        "tier": "light",
        "source_trail_density": 0.35,
        "useful_packet_rate": 0.42,
        "source_reopen_success_rate": 0.48,
        "manual_search_step_count": 4.4,
        "wrong_route_drag_rate": 0.06,
    },
    {
        "tier": "medium",
        "source_trail_density": 0.68,
        "useful_packet_rate": 0.71,
        "source_reopen_success_rate": 0.72,
        "manual_search_step_count": 2.6,
        "wrong_route_drag_rate": 0.07,
    },
    {
        "tier": "heavy",
        "source_trail_density": 0.92,
        "useful_packet_rate": 0.81,
        "source_reopen_success_rate": 0.79,
        "manual_search_step_count": 2.1,
        "wrong_route_drag_rate": 0.08,
    },
    {
        "tier": "noisy_saturated_control",
        "source_trail_density": 1.0,
        "useful_packet_rate": 0.56,
        "source_reopen_success_rate": 0.62,
        "manual_search_step_count": 3.8,
        "wrong_route_drag_rate": 0.18,
    },
]


def _lift(current: float, previous: float) -> float:
    return round(current - previous, 6)


def build_density_curve_report() -> dict[str, Any]:
    tiers: list[dict[str, Any]] = []
    previous: dict[str, Any] | None = None
    regressions: list[str] = []
    for row in SYNTHETIC_TIERS:
        enriched = dict(row)
        if previous:
            enriched["marginal_source_reopen_lift"] = _lift(
                float(row["source_reopen_success_rate"]),
                float(previous["source_reopen_success_rate"]),
            )
            enriched["marginal_manual_search_step_reduction"] = _lift(
                float(previous["manual_search_step_count"]),
                float(row["manual_search_step_count"]),
            )
            if row["tier"] != "noisy_saturated_control":
                if enriched["marginal_source_reopen_lift"] < 0:
                    regressions.append(f"{row['tier']}:source_reopen_regression")
                if float(row["wrong_route_drag_rate"]) > 0.12:
                    regressions.append(f"{row['tier']}:wrong_route_drag_high")
        else:
            enriched["marginal_source_reopen_lift"] = 0.0
            enriched["marginal_manual_search_step_reduction"] = 0.0
        tiers.append(enriched)
        if row["tier"] != "noisy_saturated_control":
            previous = row
    quality_gate_ok = not regressions and len(tiers) >= 4
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "aippocampus_continuity_density_curve_benchmark",
        "ok": True,
        "status": "synthetic_density_curve_complete",
        "benchmark_maturity_level": "diagnostic_proxy",
        "measurement_origin": "deterministic_fixture",
        "observed_agent_behavior": False,
        "contract_gate_ok": True,
        "public_quality_gate_ok": False,
        "quality_gate_ok": quality_gate_ok,
        "runtime_policy_adoption_gate_ok": False,
        "decision_impact": "issue_closeout_candidate",
        "case_count": len(tiers),
        "scenario_provenance": {
            "source": "public_synthetic_density_tiers",
            "tuning_visible": True,
            "holdout": False,
            "private_history_used": False,
        },
        "prompt_family": "same vague project-continuity prompt family",
        "tiers": tiers,
        "measured_result": {
            "medium_vs_cold_source_reopen_lift": _lift(
                tiers[2]["source_reopen_success_rate"],
                tiers[0]["source_reopen_success_rate"],
            ),
            "medium_vs_cold_manual_search_step_reduction": _lift(
                tiers[0]["manual_search_step_count"],
                tiers[2]["manual_search_step_count"],
            ),
            "noisy_control_wrong_route_drag_rate": tiers[-1]["wrong_route_drag_rate"],
        },
        "supports": [
            "source_trail_density_can_be_measured_without_private_text",
            "more_source_backed_routes_reduce_manual_search_in_synthetic_fixture",
            "noisy_saturation_control_exposes_wrong_route_drag",
        ],
        "agent_action": "use_as_diagnostic_evidence; do not make public quality claims",
        "material_limits": [
            "synthetic_fixture_not_live_user_history",
            "does_not_measure_model_choice_quality",
        ],
        "privacy_boundary": {
            "private_history_used": False,
            "raw_text_serialized": False,
            "local_paths_serialized": False,
        },
        "cannot_claim": [
            "private_real_history_density_curve",
            "public_quality_lift",
            "innate_model_memory",
            "noise_free_saturation",
        ],
        "regressions": regressions,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    report = build_density_curve_report()
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print("continuity density curve: ok")
        print(
            "medium lift:",
            report["measured_result"]["medium_vs_cold_source_reopen_lift"],
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
