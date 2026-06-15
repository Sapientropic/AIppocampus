#!/usr/bin/env python3
"""Continuity-density curve diagnostics and aggregate replay measurement."""

from __future__ import annotations

import argparse
import json
from collections.abc import Iterable, Mapping
from pathlib import Path
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

PUBLIC_AGGREGATE_REPLAY_ROWS: list[dict[str, Any]] = [
    {
        "case_id": "public-cold-a",
        "source_ref_count": 0,
        "registry_route_count": 0,
        "route_handle_count": 0,
        "source_reopen_attempted_count": 1,
        "source_reopen_success_count": 0,
        "manual_search_step_count": 8,
        "route_candidate_count": 1,
        "wrong_route_count": 0,
        "noisy_route_count": 0,
        "context_token_count": 640,
        "context_budget_token_count": 4000,
    },
    {
        "case_id": "public-cold-b",
        "source_ref_count": 0,
        "registry_route_count": 0,
        "route_handle_count": 1,
        "source_reopen_attempted_count": 1,
        "source_reopen_success_count": 0,
        "manual_search_step_count": 7,
        "route_candidate_count": 1,
        "wrong_route_count": 0,
        "noisy_route_count": 0,
        "context_token_count": 780,
        "context_budget_token_count": 4000,
    },
    {
        "case_id": "public-light-a",
        "source_ref_count": 2,
        "registry_route_count": 1,
        "route_handle_count": 1,
        "source_reopen_attempted_count": 2,
        "source_reopen_success_count": 1,
        "manual_search_step_count": 5,
        "route_candidate_count": 3,
        "wrong_route_count": 0,
        "noisy_route_count": 0,
        "context_token_count": 1250,
        "context_budget_token_count": 4000,
    },
    {
        "case_id": "public-light-b",
        "source_ref_count": 3,
        "registry_route_count": 1,
        "route_handle_count": 1,
        "source_reopen_attempted_count": 2,
        "source_reopen_success_count": 1,
        "manual_search_step_count": 4,
        "route_candidate_count": 4,
        "wrong_route_count": 1,
        "noisy_route_count": 0,
        "context_token_count": 1460,
        "context_budget_token_count": 4000,
    },
    {
        "case_id": "public-medium-a",
        "source_ref_count": 5,
        "registry_route_count": 3,
        "route_handle_count": 2,
        "source_reopen_attempted_count": 3,
        "source_reopen_success_count": 2,
        "manual_search_step_count": 3,
        "route_candidate_count": 7,
        "wrong_route_count": 0,
        "noisy_route_count": 0,
        "context_token_count": 2050,
        "context_budget_token_count": 4000,
    },
    {
        "case_id": "public-medium-b",
        "source_ref_count": 6,
        "registry_route_count": 3,
        "route_handle_count": 2,
        "source_reopen_attempted_count": 3,
        "source_reopen_success_count": 3,
        "manual_search_step_count": 2,
        "route_candidate_count": 8,
        "wrong_route_count": 1,
        "noisy_route_count": 0,
        "context_token_count": 2260,
        "context_budget_token_count": 4000,
    },
    {
        "case_id": "public-heavy-a",
        "source_ref_count": 9,
        "registry_route_count": 4,
        "route_handle_count": 3,
        "source_reopen_attempted_count": 3,
        "source_reopen_success_count": 3,
        "manual_search_step_count": 2,
        "route_candidate_count": 11,
        "wrong_route_count": 1,
        "noisy_route_count": 1,
        "context_token_count": 2750,
        "context_budget_token_count": 4000,
    },
    {
        "case_id": "public-heavy-b",
        "source_ref_count": 10,
        "registry_route_count": 4,
        "route_handle_count": 3,
        "source_reopen_attempted_count": 4,
        "source_reopen_success_count": 3,
        "manual_search_step_count": 2,
        "route_candidate_count": 12,
        "wrong_route_count": 1,
        "noisy_route_count": 1,
        "context_token_count": 2920,
        "context_budget_token_count": 4000,
    },
    {
        "case_id": "public-noisy-a",
        "source_ref_count": 10,
        "registry_route_count": 5,
        "route_handle_count": 3,
        "source_reopen_attempted_count": 4,
        "source_reopen_success_count": 2,
        "manual_search_step_count": 4,
        "route_candidate_count": 17,
        "wrong_route_count": 4,
        "noisy_route_count": 7,
        "context_token_count": 4300,
        "context_budget_token_count": 4000,
    },
    {
        "case_id": "public-noisy-b",
        "source_ref_count": 11,
        "registry_route_count": 5,
        "route_handle_count": 3,
        "source_reopen_attempted_count": 4,
        "source_reopen_success_count": 3,
        "manual_search_step_count": 4,
        "route_candidate_count": 18,
        "wrong_route_count": 5,
        "noisy_route_count": 8,
        "context_token_count": 4560,
        "context_budget_token_count": 4000,
    },
]

_DENSITY_TIER_ORDER = (
    "cold",
    "light",
    "medium",
    "heavy",
    "noisy_saturated_control",
)

_AGGREGATE_COUNT_FIELDS = (
    "source_ref_count",
    "registry_route_count",
    "route_handle_count",
    "source_reopen_attempted_count",
    "source_reopen_success_count",
    "manual_search_step_count",
    "route_candidate_count",
    "wrong_route_count",
    "noisy_route_count",
    "context_token_count",
    "context_budget_token_count",
)


def _lift(current: float, previous: float) -> float:
    return round(current - previous, 6)


def _safe_int(record: Mapping[str, Any], field: str) -> int:
    try:
        return max(0, int(record.get(field, 0) or 0))
    except (TypeError, ValueError):
        return 0


def _ratio(numerator: float, denominator: float) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 6)


def _source_unit_count(record: Mapping[str, Any]) -> int:
    return (
        _safe_int(record, "source_ref_count")
        + _safe_int(record, "registry_route_count")
        + _safe_int(record, "route_handle_count")
    )


def _context_pressure(record: Mapping[str, Any]) -> float:
    budget = _safe_int(record, "context_budget_token_count")
    if budget <= 0:
        return 0.0
    return _ratio(_safe_int(record, "context_token_count"), budget)


def _assign_replay_tier(
    *,
    source_trail_density: float,
    wrong_route_drag_rate: float,
    noisy_saturation_rate: float,
    context_pressure: float,
) -> str:
    if (
        source_trail_density >= 0.9
        and (
            wrong_route_drag_rate >= 0.18
            or noisy_saturation_rate >= 0.28
            or context_pressure >= 1.0
        )
    ):
        return "noisy_saturated_control"
    if source_trail_density < 0.2:
        return "cold"
    if source_trail_density < 0.5:
        return "light"
    if source_trail_density < 0.8:
        return "medium"
    return "heavy"


def _aggregate_replay_rows(records: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows = [dict(record) for record in records]
    max_source_units = max((_source_unit_count(row) for row in rows), default=1)
    if max_source_units <= 0:
        max_source_units = 1

    grouped: dict[str, list[dict[str, Any]]] = {tier: [] for tier in _DENSITY_TIER_ORDER}
    dropped_fields: set[str] = set()
    for row in rows:
        dropped_fields.update(str(key) for key in row if key not in _AGGREGATE_COUNT_FIELDS)
        source_units = _source_unit_count(row)
        route_candidates = _safe_int(row, "route_candidate_count")
        wrong_route_count = _safe_int(row, "wrong_route_count")
        noisy_route_count = _safe_int(row, "noisy_route_count")
        density = _ratio(source_units, max_source_units)
        wrong_drag = _ratio(wrong_route_count, max(1, route_candidates + wrong_route_count))
        noisy_rate = _ratio(noisy_route_count, max(1, route_candidates + noisy_route_count))
        pressure = _context_pressure(row)
        tier = _assign_replay_tier(
            source_trail_density=density,
            wrong_route_drag_rate=wrong_drag,
            noisy_saturation_rate=noisy_rate,
            context_pressure=pressure,
        )
        grouped[tier].append(
            {
                "source_units": source_units,
                "source_trail_density": density,
                "source_ref_count": _safe_int(row, "source_ref_count"),
                "registry_route_count": _safe_int(row, "registry_route_count"),
                "route_handle_count": _safe_int(row, "route_handle_count"),
                "source_reopen_attempted_count": _safe_int(
                    row,
                    "source_reopen_attempted_count",
                ),
                "source_reopen_success_count": _safe_int(
                    row,
                    "source_reopen_success_count",
                ),
                "manual_search_step_count": _safe_int(row, "manual_search_step_count"),
                "route_candidate_count": route_candidates,
                "wrong_route_count": wrong_route_count,
                "noisy_route_count": noisy_route_count,
                "wrong_route_drag_rate": wrong_drag,
                "noisy_saturation_rate": noisy_rate,
                "context_pressure": pressure,
            }
        )

    tiers: list[dict[str, Any]] = []
    previous_non_noisy: dict[str, Any] | None = None
    for tier in _DENSITY_TIER_ORDER:
        tier_rows = grouped[tier]
        if not tier_rows:
            continue
        case_count = len(tier_rows)
        attempted = sum(row["source_reopen_attempted_count"] for row in tier_rows)
        succeeded = sum(row["source_reopen_success_count"] for row in tier_rows)
        route_candidates = sum(row["route_candidate_count"] for row in tier_rows)
        wrong_routes = sum(row["wrong_route_count"] for row in tier_rows)
        noisy_routes = sum(row["noisy_route_count"] for row in tier_rows)
        enriched: dict[str, Any] = {
            "tier": tier,
            "case_count": case_count,
            "source_ref_count": sum(row["source_ref_count"] for row in tier_rows),
            "registry_route_count": sum(row["registry_route_count"] for row in tier_rows),
            "route_handle_count": sum(row["route_handle_count"] for row in tier_rows),
            "source_unit_count": sum(row["source_units"] for row in tier_rows),
            "source_trail_density": round(
                sum(row["source_trail_density"] for row in tier_rows) / case_count,
                6,
            ),
            "source_reopen_attempted_count": attempted,
            "source_reopen_success_count": succeeded,
            "source_reopen_success_rate": _ratio(succeeded, attempted),
            "manual_search_step_count": round(
                sum(row["manual_search_step_count"] for row in tier_rows) / case_count,
                6,
            ),
            "wrong_route_drag_rate": _ratio(
                wrong_routes,
                max(1, route_candidates + wrong_routes),
            ),
            "noisy_saturation_rate": _ratio(
                noisy_routes,
                max(1, route_candidates + noisy_routes),
            ),
            "context_pressure": round(
                sum(row["context_pressure"] for row in tier_rows) / case_count,
                6,
            ),
            "too_much_context_pressure_rate": _ratio(
                sum(1 for row in tier_rows if row["context_pressure"] >= 0.9),
                case_count,
            ),
            "enough_context_without_saturation_rate": _ratio(
                sum(
                    1
                    for row in tier_rows
                    if row["source_units"] > 0
                    and row["context_pressure"] < 0.9
                    and row["wrong_route_drag_rate"] < 0.18
                    and row["noisy_saturation_rate"] < 0.28
                ),
                case_count,
            ),
        }
        if previous_non_noisy:
            enriched["marginal_source_reopen_lift"] = _lift(
                enriched["source_reopen_success_rate"],
                previous_non_noisy["source_reopen_success_rate"],
            )
            enriched["marginal_manual_search_step_reduction"] = _lift(
                previous_non_noisy["manual_search_step_count"],
                enriched["manual_search_step_count"],
            )
        else:
            enriched["marginal_source_reopen_lift"] = 0.0
            enriched["marginal_manual_search_step_reduction"] = 0.0
        tiers.append(enriched)
        if tier != "noisy_saturated_control":
            previous_non_noisy = enriched

    for tier in tiers:
        tier["input_fields_dropped_to_preserve_public_boundary"] = sorted(dropped_fields)
    return tiers


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


def build_replay_backed_density_report(
    records: Iterable[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build the aggregate replay companion report without serializing sources.

    The replay surface intentionally accepts source/registry/route counts rather
    than text, paths, thread ids, or source refs. It is a measurement companion
    to the synthetic shape contract, not a release-quality product claim gate.
    """

    replay_rows = list(records if records is not None else PUBLIC_AGGREGATE_REPLAY_ROWS)
    tiers = _aggregate_replay_rows(replay_rows)
    tier_map = {row["tier"]: row for row in tiers}
    required_tiers = {"cold", "light", "medium", "heavy", "noisy_saturated_control"}
    missing_tiers = sorted(required_tiers.difference(tier_map))
    privacy_boundary = {
        "private_history_used": False,
        "aggregate_only": True,
        "raw_text_serialized": False,
        "local_paths_serialized": False,
        "thread_ids_serialized": False,
        "private_source_refs_serialized": False,
        "source_refs_serialized": False,
    }
    regressions: list[str] = []
    for tier in tiers:
        if tier["tier"] == "noisy_saturated_control":
            continue
        if tier["marginal_source_reopen_lift"] < 0:
            regressions.append(f"{tier['tier']}:source_reopen_regression")
        if tier["wrong_route_drag_rate"] > 0.16:
            regressions.append(f"{tier['tier']}:wrong_route_drag_high")
        if tier["too_much_context_pressure_rate"] > 0.5:
            regressions.append(f"{tier['tier']}:context_pressure_high")

    contract_gate_ok = not missing_tiers and bool(tiers)
    measured_result = {
        "medium_vs_cold_source_reopen_lift": (
            _lift(
                tier_map["medium"]["source_reopen_success_rate"],
                tier_map["cold"]["source_reopen_success_rate"],
            )
            if "medium" in tier_map and "cold" in tier_map
            else 0.0
        ),
        "medium_vs_cold_manual_search_step_reduction": (
            _lift(
                tier_map["cold"]["manual_search_step_count"],
                tier_map["medium"]["manual_search_step_count"],
            )
            if "medium" in tier_map and "cold" in tier_map
            else 0.0
        ),
        "noisy_control_wrong_route_drag_rate": tier_map.get(
            "noisy_saturated_control",
            {},
        ).get("wrong_route_drag_rate", 0.0),
        "noisy_control_context_pressure": tier_map.get(
            "noisy_saturated_control",
            {},
        ).get("context_pressure", 0.0),
        "density_tiers_computed_from_counts": True,
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "aippocampus_continuity_density_replay_measurement",
        "ok": True,
        "status": "aggregate_replay_density_measurement_complete",
        "benchmark_maturity_level": "aggregate_replay_measurement",
        "measurement_origin": "aggregate_replay_fixture",
        "observed_agent_behavior": False,
        "contract_gate_ok": contract_gate_ok,
        "public_quality_gate_ok": False,
        "quality_gate_ok": False,
        "runtime_policy_adoption_gate_ok": False,
        "decision_impact": "diagnostic_only",
        "case_count": len(replay_rows),
        "scenario_provenance": {
            "source": "public_safe_aggregate_replay_rows",
            "tuning_visible": True,
            "holdout": False,
            "private_history_used": False,
            "raw_rows_are_counts_only": True,
        },
        "tiering_rule": {
            "computed_from": [
                "source_ref_count",
                "registry_route_count",
                "route_handle_count",
                "wrong_route_count",
                "noisy_route_count",
                "context_token_count",
                "context_budget_token_count",
            ],
            "noisy_saturation_overrides_high_density": True,
        },
        "tiers": tiers,
        "measured_result": measured_result,
        "supports": [
            "aggregate_replay_density_tiers_can_be_computed_without_source_text",
            "source_reopen_success_and_manual_search_pressure_can_be_reported_together",
            "noisy_saturation_is_measured_as_a_control_not_hidden_by_density",
        ],
        "agent_action": (
            "use_as_replay_measurement_companion; keep product claims blocked until "
            "public_quality_gate_ok passes on replay-backed cohorts"
        ),
        "material_limits": [
            "public_fixture_is_aggregate_not_private_history",
            "observed_agent_behavior_not_established_by_this_fixture",
            "does_not_prove_more_context_is_always_better",
        ],
        "privacy_boundary": privacy_boundary,
        "cannot_claim": [
            "private_real_history_density_curve",
            "public_quality_lift",
            "runtime_policy_adoption",
            "innate_model_memory",
            "noise_free_saturation",
            "more_memory_is_always_better",
        ],
        "missing_tiers": missing_tiers,
        "regressions": regressions,
    }


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            payload = json.loads(stripped)
            if not isinstance(payload, dict):
                raise ValueError(f"{path}:{line_number} must be a JSON object")
            records.append(payload)
    return records


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--mode",
        choices=("synthetic", "replay"),
        default="synthetic",
        help="Choose the synthetic shape contract or aggregate replay companion.",
    )
    parser.add_argument(
        "--input-jsonl",
        type=Path,
        help="Optional aggregate-count JSONL for --mode replay.",
    )
    args = parser.parse_args(argv)
    if args.mode == "replay":
        records = _load_jsonl(args.input_jsonl) if args.input_jsonl else None
        report = build_replay_backed_density_report(records)
    else:
        report = build_density_curve_report()
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        if args.mode == "replay":
            print("continuity density replay measurement: ok")
            print("product quality gate:", report["public_quality_gate_ok"])
        else:
            print("continuity density curve: ok")
            print(
                "medium lift:",
                report["measured_result"]["medium_vs_cold_source_reopen_lift"],
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
