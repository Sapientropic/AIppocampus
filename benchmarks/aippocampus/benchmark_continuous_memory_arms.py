#!/usr/bin/env python3
"""Deterministic attribution arms for the continuous-memory benchmark.

This runner is the first public-safe #378 attribution control for #408. It
separates correct source-backed memory from the mere presence of nearby
memory-shaped text, stale plausible memory, and an oracle upper bound. It is a
synthetic diagnostic runner, not a live-agent or superiority benchmark.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

SCHEMA_VERSION = 1
ARM_ORDER = (
    "no_memory",
    "true_aippocampus_memory",
    "sham_unrelated_memory",
    "stale_wrong_memory",
    "oracle_memory",
)
COST_COMPONENTS = (
    "foreground_tokens",
    "background_tokens",
    "background_api_calls",
    "wall_clock_latency_ms",
    "indexing_maintenance_ms",
    "storage_growth_bytes",
    "source_reopen_count",
    "retry_recovery_count",
    "human_correction_count",
    "human_correction_minutes",
)
SUCCESS_VALUE_UNIT = 10.0


@dataclass(frozen=True)
class CostProfile:
    foreground_tokens: int
    background_tokens: int = 0
    background_api_calls: int = 0
    wall_clock_latency_ms: int = 0
    indexing_maintenance_ms: int = 0
    storage_growth_bytes: int = 0
    source_reopen_count: int = 0
    retry_recovery_count: int = 0
    human_correction_count: int = 0
    human_correction_minutes: int = 0


@dataclass(frozen=True)
class HarmProfile:
    memory_false_positive: bool = False
    false_positive_severity: int = 0
    downstream_turns_affected: int = 0
    wrong_constraint_adopted: bool = False
    rejected_route_retried: bool = False
    current_project_contamination: bool = False
    risky_action_before_source_reopen: bool = False
    privacy_sensitive_recall_severity: int = 0
    rollback_rework_minutes: int = 0


@dataclass(frozen=True)
class ArmSpec:
    arm: str
    memory_packet: str
    memory_packet_shape: str
    actual_behavior: str
    success: bool
    harm_score: int
    source_reopen_required: bool
    source_reopen_attempted: bool
    source_backed_hit: bool
    cost: CostProfile
    harm: HarmProfile
    abstained_on_missing_source: bool = False

    def source_reopen_obedient(self) -> bool | None:
        if not self.source_reopen_required:
            return None
        return bool(
            self.source_reopen_attempted
            and (self.source_backed_hit or self.abstained_on_missing_source)
        )


@dataclass(frozen=True)
class AttributionCase:
    case_id: str
    case_family: str
    expected_behavior: str
    source_ref: str
    source_window: str
    specs: tuple[ArmSpec, ...]

    def spec_for_arm(self, arm: str) -> ArmSpec:
        for spec in self.specs:
            if spec.arm == arm:
                return spec
        raise KeyError(f"missing arm {arm!r} for case {self.case_id!r}")


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()


def safe_rate(numerator: int | float, denominator: int | float) -> float:
    return round(float(numerator) / float(denominator), 4) if denominator else 0.0


def round_delta(value: float) -> float:
    return round(value, 4)


def _common_specs(
    *,
    correct_packet: str,
    sham_packet: str,
    stale_packet: str,
    oracle_packet: str,
    expected_behavior: str,
    no_memory_behavior: str,
    no_memory_success: bool,
    no_memory_harm: int,
    sham_behavior: str,
    sham_success: bool,
    sham_harm: int,
    true_behavior: str | None = None,
    true_success: bool = True,
    true_harm: int = 0,
    true_source_hit: bool = True,
    true_abstained_on_missing_source: bool = False,
    stale_behavior: str | None = None,
    stale_harm: int = 4,
    stale_downstream_turns: int = 4,
    stale_wrong_constraint_adopted: bool = True,
    stale_rejected_route_retried: bool = False,
    stale_project_contamination: bool = False,
    stale_risky_action_before_reopen: bool = True,
    stale_rework_minutes: int = 18,
) -> tuple[ArmSpec, ...]:
    true_action = true_behavior or expected_behavior
    stale_action = stale_behavior or "adopt_stale_wrong_memory"
    return (
        ArmSpec(
            arm="no_memory",
            memory_packet="",
            memory_packet_shape="empty_control",
            actual_behavior=no_memory_behavior,
            success=no_memory_success,
            harm_score=no_memory_harm,
            source_reopen_required=False,
            source_reopen_attempted=False,
            source_backed_hit=False,
            cost=CostProfile(
                foreground_tokens=90,
                wall_clock_latency_ms=90,
                retry_recovery_count=0 if no_memory_success else 1,
            ),
            harm=HarmProfile(
                downstream_turns_affected=1 if no_memory_harm else 0,
                rollback_rework_minutes=5 if no_memory_harm else 0,
            ),
        ),
        ArmSpec(
            arm="true_aippocampus_memory",
            memory_packet=correct_packet,
            memory_packet_shape="source_backed_route_handle",
            actual_behavior=true_action,
            success=true_success,
            harm_score=true_harm,
            source_reopen_required=True,
            source_reopen_attempted=True,
            source_backed_hit=true_source_hit,
            cost=CostProfile(
                foreground_tokens=130,
                background_tokens=160,
                background_api_calls=1,
                wall_clock_latency_ms=170,
                indexing_maintenance_ms=55,
                storage_growth_bytes=640,
                source_reopen_count=1,
                retry_recovery_count=0 if true_source_hit else 1,
            ),
            harm=HarmProfile(
                rollback_rework_minutes=4 if not true_source_hit else 0,
            ),
            abstained_on_missing_source=true_abstained_on_missing_source,
        ),
        ArmSpec(
            arm="sham_unrelated_memory",
            memory_packet=sham_packet,
            memory_packet_shape="matched_format_unrelated_route_handle",
            actual_behavior=sham_behavior,
            success=sham_success,
            harm_score=sham_harm,
            source_reopen_required=False,
            source_reopen_attempted=False,
            source_backed_hit=False,
            cost=CostProfile(
                foreground_tokens=125,
                wall_clock_latency_ms=105,
                retry_recovery_count=0 if sham_success else 1,
            ),
            harm=HarmProfile(
                downstream_turns_affected=1 if sham_harm else 0,
                rollback_rework_minutes=5 if sham_harm else 0,
            ),
        ),
        ArmSpec(
            arm="stale_wrong_memory",
            memory_packet=stale_packet,
            memory_packet_shape="matched_format_plausible_wrong_route_handle",
            actual_behavior=stale_action,
            success=False,
            harm_score=stale_harm,
            source_reopen_required=True,
            source_reopen_attempted=False,
            source_backed_hit=False,
            cost=CostProfile(
                foreground_tokens=135,
                background_tokens=150,
                background_api_calls=1,
                wall_clock_latency_ms=160,
                indexing_maintenance_ms=55,
                storage_growth_bytes=640,
                source_reopen_count=0,
                retry_recovery_count=2,
                human_correction_count=1,
                human_correction_minutes=max(8, stale_rework_minutes // 2),
            ),
            harm=HarmProfile(
                memory_false_positive=True,
                false_positive_severity=stale_harm,
                downstream_turns_affected=stale_downstream_turns,
                wrong_constraint_adopted=stale_wrong_constraint_adopted,
                rejected_route_retried=stale_rejected_route_retried,
                current_project_contamination=stale_project_contamination,
                risky_action_before_source_reopen=stale_risky_action_before_reopen,
                rollback_rework_minutes=stale_rework_minutes,
            ),
        ),
        ArmSpec(
            arm="oracle_memory",
            memory_packet=oracle_packet,
            memory_packet_shape="minimal_source_grounded_oracle_context",
            actual_behavior=expected_behavior,
            success=True,
            harm_score=0,
            source_reopen_required=True,
            source_reopen_attempted=True,
            source_backed_hit=True,
            cost=CostProfile(
                foreground_tokens=110,
                background_tokens=40,
                wall_clock_latency_ms=110,
                source_reopen_count=1,
            ),
            harm=HarmProfile(),
        ),
    )


def fixture_cases() -> list[AttributionCase]:
    return [
        AttributionCase(
            case_id="rejected-route-after-compaction",
            case_family="post_compaction_rejected_route",
            expected_behavior="avoid_rejected_route_and_use_accepted_path",
            source_ref="synthetic://continuous-memory/rejected-route#source",
            source_window="User rejected the registry import route and accepted direct fixture replay.",
            specs=_common_specs(
                correct_packet="Route handle says rejected registry import has source support.",
                sham_packet="Route handle says a website preference thread may be nearby.",
                stale_packet="Route handle says registry import is the accepted path.",
                oracle_packet="Source says registry import was rejected; use direct fixture replay.",
                expected_behavior="avoid_rejected_route_and_use_accepted_path",
                no_memory_behavior="retry_rejected_registry_import",
                no_memory_success=False,
                no_memory_harm=2,
                sham_behavior="retry_rejected_registry_import",
                sham_success=False,
                sham_harm=2,
                stale_harm=4,
                stale_rejected_route_retried=True,
                stale_wrong_constraint_adopted=False,
                stale_rework_minutes=24,
            ),
        ),
        AttributionCase(
            case_id="scope-narrowing-after-horizon-loss",
            case_family="post_compaction_scope_constraint",
            expected_behavior="preserve_docs_only_scope",
            source_ref="synthetic://continuous-memory/docs-scope#source",
            source_window="User narrowed the slice to docs and benchmark reports only.",
            specs=_common_specs(
                correct_packet="Route handle says the active task was narrowed to docs only.",
                sham_packet="Route handle says a nutrition note had a similar date.",
                stale_packet="Route handle says code edits are in scope for this slice.",
                oracle_packet="Source says this slice is docs-only; avoid runtime code edits.",
                expected_behavior="preserve_docs_only_scope",
                no_memory_behavior="edit_runtime_module",
                no_memory_success=False,
                no_memory_harm=2,
                sham_behavior="edit_runtime_module",
                sham_success=False,
                sham_harm=2,
                stale_harm=4,
                stale_project_contamination=True,
                stale_rework_minutes=24,
            ),
        ),
        AttributionCase(
            case_id="transient-concern-expired",
            case_family="transient_concern_expiry",
            expected_behavior="do_not_preserve_expired_constraint",
            source_ref="synthetic://continuous-memory/transient-expiry#source",
            source_window="Concern was explicitly local to one run and expired at closeout.",
            specs=_common_specs(
                correct_packet="Route handle says the old concern was local-only and expired.",
                sham_packet="Route handle says an unrelated visual-review task existed.",
                stale_packet="Route handle says the old local concern is still a global rule.",
                oracle_packet="Source says the concern expired with the one-off run.",
                expected_behavior="do_not_preserve_expired_constraint",
                no_memory_behavior="do_not_preserve_expired_constraint",
                no_memory_success=True,
                no_memory_harm=0,
                sham_behavior="do_not_preserve_expired_constraint",
                sham_success=True,
                sham_harm=0,
                stale_harm=3,
                stale_downstream_turns=2,
                stale_risky_action_before_reopen=False,
                stale_rework_minutes=12,
            ),
        ),
        AttributionCase(
            case_id="incomplete-handoff-needs-reopen",
            case_family="incomplete_handoff_recovery",
            expected_behavior="recover_exact_source_before_claim",
            source_ref="synthetic://continuous-memory/incomplete-handoff#source",
            source_window="Handoff mentions a decision but omits the exact source window.",
            specs=_common_specs(
                correct_packet="Route handle names a likely decision but source reopen misses.",
                sham_packet="Route handle names an unrelated benchmark report.",
                stale_packet="Route handle fills the missing decision with an old wrong claim.",
                oracle_packet="Source gives the exact decision and its supporting window.",
                expected_behavior="recover_exact_source_before_claim",
                no_memory_behavior="guess_from_incomplete_handoff",
                no_memory_success=False,
                no_memory_harm=1,
                sham_behavior="guess_from_incomplete_handoff",
                sham_success=False,
                sham_harm=1,
                true_behavior="ask_or_abstain_until_source_reopen_succeeds",
                true_success=False,
                true_harm=0,
                true_source_hit=False,
                true_abstained_on_missing_source=True,
                stale_harm=3,
                stale_rework_minutes=18,
            ),
        ),
    ]


def evaluate_case(case: AttributionCase, arm: str) -> dict[str, Any]:
    spec = case.spec_for_arm(arm)
    cost = spec.cost
    harm = spec.harm
    return {
        "case_id_sha1": sha256_text(case.case_id)[:16],
        "case_family": case.case_family,
        "arm": arm,
        "expected_behavior": case.expected_behavior,
        "actual_behavior": spec.actual_behavior,
        "success": spec.success,
        "harm_score": spec.harm_score,
        "source_ref_sha256": sha256_text(case.source_ref)[:16],
        "source_window_sha256": sha256_text(case.source_window)[:16],
        "memory_packet_shape": spec.memory_packet_shape,
        "memory_packet_sha256": sha256_text(spec.memory_packet)[:16] if spec.memory_packet else None,
        "memory_packet_token_estimate": max(0, len(spec.memory_packet.split())),
        "source_reopen_required": spec.source_reopen_required,
        "source_reopen_attempted": spec.source_reopen_attempted,
        "source_backed_hit": spec.source_backed_hit,
        "abstained_on_missing_source": spec.abstained_on_missing_source,
        "source_reopen_obedient": spec.source_reopen_obedient(),
        "cost_components": {
            "foreground_tokens": cost.foreground_tokens,
            "background_tokens": cost.background_tokens,
            "background_api_calls": cost.background_api_calls,
            "wall_clock_latency_ms": cost.wall_clock_latency_ms,
            "indexing_maintenance_ms": cost.indexing_maintenance_ms,
            "storage_growth_bytes": cost.storage_growth_bytes,
            "source_reopen_count": cost.source_reopen_count,
            "retry_recovery_count": cost.retry_recovery_count,
            "human_correction_count": cost.human_correction_count,
            "human_correction_minutes": cost.human_correction_minutes,
        },
        "harm_components": {
            "memory_false_positive": harm.memory_false_positive,
            "false_positive_severity": harm.false_positive_severity,
            "downstream_turns_affected": harm.downstream_turns_affected,
            "wrong_constraint_adopted": harm.wrong_constraint_adopted,
            "rejected_route_retried": harm.rejected_route_retried,
            "current_project_contamination": harm.current_project_contamination,
            "risky_action_before_source_reopen": harm.risky_action_before_source_reopen,
            "privacy_sensitive_recall_severity": harm.privacy_sensitive_recall_severity,
            "rollback_rework_minutes": harm.rollback_rework_minutes,
        },
    }


def summarize_rows(rows: list[dict[str, Any]], *, case_count: int) -> dict[str, Any]:
    by_arm: dict[str, dict[str, Any]] = {}
    source_reopen_obedience_by_arm: dict[str, float | None] = {}
    for arm in ARM_ORDER:
        arm_rows = [row for row in rows if row["arm"] == arm]
        success_count = sum(1 for row in arm_rows if row["success"])
        harm_score_total = sum(int(row["harm_score"]) for row in arm_rows)
        required = [row for row in arm_rows if row["source_reopen_required"]]
        obedient = [row for row in required if row["source_reopen_obedient"]]
        source_reopen_obedience_by_arm[arm] = (
            safe_rate(len(obedient), len(required)) if required else None
        )
        by_arm[arm] = {
            "case_count": len(arm_rows),
            "success_count": success_count,
            "success_rate": safe_rate(success_count, len(arm_rows)),
            "harm_score_total": harm_score_total,
            "harm_score_avg": safe_rate(harm_score_total, len(arm_rows)),
            "source_reopen_required_count": len(required),
            "source_reopen_attempt_count": sum(
                1 for row in arm_rows if row["source_reopen_attempted"]
            ),
            "source_backed_hit_count": sum(
                1 for row in arm_rows if row["source_backed_hit"]
            ),
            "source_reopen_obedience_rate": source_reopen_obedience_by_arm[arm],
        }

    no_memory = by_arm["no_memory"]
    true_memory = by_arm["true_aippocampus_memory"]
    sham = by_arm["sham_unrelated_memory"]
    stale = by_arm["stale_wrong_memory"]
    oracle = by_arm["oracle_memory"]
    return {
        "case_count": case_count,
        "arm_count": len(ARM_ORDER),
        "row_count": len(rows),
        "by_arm": by_arm,
        "memory_presence_effect": round_delta(
            sham["success_rate"] - no_memory["success_rate"]
        ),
        "memory_correctness_effect": round_delta(
            true_memory["success_rate"] - sham["success_rate"]
        ),
        "stale_memory_harm": round_delta(
            stale["harm_score_avg"] - no_memory["harm_score_avg"]
        ),
        "oracle_headroom": round_delta(
            oracle["success_rate"] - true_memory["success_rate"]
        ),
        "source_reopen_obedience_by_arm": source_reopen_obedience_by_arm,
    }


def safe_cost_per_success(cost_units: float, success_count: int) -> float | None:
    if success_count <= 0:
        return None
    return round_delta(cost_units / success_count)


def row_foreground_cost_units(row: dict[str, Any]) -> float:
    cost = row["cost_components"]
    return (
        cost["foreground_tokens"] / 100.0
        + cost["wall_clock_latency_ms"] / 1000.0
        + cost["source_reopen_count"] * 0.25
    )


def row_background_cost_units(row: dict[str, Any]) -> float:
    cost = row["cost_components"]
    return (
        cost["background_tokens"] / 100.0
        + cost["background_api_calls"] * 2.0
        + cost["indexing_maintenance_ms"] / 1000.0
        + cost["storage_growth_bytes"] / 4096.0
    )


def row_recovery_cost_units(row: dict[str, Any]) -> float:
    cost = row["cost_components"]
    return (
        cost["retry_recovery_count"] * 1.5
        + cost["human_correction_count"] * 2.0
        + cost["human_correction_minutes"] * 0.25
    )


def harm_weighted_false_positive_cost(row: dict[str, Any]) -> float:
    harm = row["harm_components"]
    if not harm["memory_false_positive"]:
        return 0.0
    cost = float(harm["false_positive_severity"] ** 2)
    cost += harm["downstream_turns_affected"] * 1.5
    cost += 6.0 if harm["wrong_constraint_adopted"] else 0.0
    cost += 5.0 if harm["rejected_route_retried"] else 0.0
    cost += 8.0 if harm["current_project_contamination"] else 0.0
    cost += 7.0 if harm["risky_action_before_source_reopen"] else 0.0
    cost += harm["privacy_sensitive_recall_severity"] * 10.0
    cost += harm["rollback_rework_minutes"] / 3.0
    return round_delta(cost)


def summarize_cost_for_rows(arm_rows: list[dict[str, Any]]) -> dict[str, Any]:
    success_count = sum(1 for row in arm_rows if row["success"])
    foreground_cost_units = round_delta(
        sum(row_foreground_cost_units(row) for row in arm_rows)
    )
    background_cost_units = round_delta(
        sum(row_background_cost_units(row) for row in arm_rows)
    )
    recovery_cost_units = round_delta(
        sum(row_recovery_cost_units(row) for row in arm_rows)
    )
    total_cost_units = round_delta(
        foreground_cost_units + background_cost_units + recovery_cost_units
    )
    summed_cost = {
        component: sum(int(row["cost_components"][component]) for row in arm_rows)
        for component in COST_COMPONENTS
    }
    return {
        **summed_cost,
        "success_count": success_count,
        "foreground_cost_units": foreground_cost_units,
        "background_cost_units": background_cost_units,
        "recovery_cost_units": recovery_cost_units,
        "total_cost_units": total_cost_units,
        "foreground_cost_per_successful_slice": safe_cost_per_success(
            foreground_cost_units,
            success_count,
        ),
        "background_cost_per_successful_slice": safe_cost_per_success(
            background_cost_units,
            success_count,
        ),
        "amortized_cost_per_successful_slice": safe_cost_per_success(
            total_cost_units,
            success_count,
        ),
    }


def summarize_harm_for_rows(
    arm_rows: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[float]]:
    false_positive_rows = [
        row for row in arm_rows if row["harm_components"]["memory_false_positive"]
    ]
    false_positive_costs = [
        harm_weighted_false_positive_cost(row) for row in false_positive_rows
    ]
    summary = {
        "memory_false_positive_count": len(false_positive_rows),
        "memory_false_positive_rate": safe_rate(len(false_positive_rows), len(arm_rows)),
        "harm_weighted_false_positive_cost": round_delta(sum(false_positive_costs)),
        "max_downstream_turns_affected": max(
            (
                int(row["harm_components"]["downstream_turns_affected"])
                for row in arm_rows
            ),
            default=0,
        ),
        "wrong_constraint_adopted_count": sum(
            1
            for row in false_positive_rows
            if row["harm_components"]["wrong_constraint_adopted"]
        ),
        "rejected_route_retried_count": sum(
            1
            for row in false_positive_rows
            if row["harm_components"]["rejected_route_retried"]
        ),
        "current_project_contamination_count": sum(
            1
            for row in false_positive_rows
            if row["harm_components"]["current_project_contamination"]
        ),
        "risky_action_before_source_reopen_count": sum(
            1
            for row in false_positive_rows
            if row["harm_components"]["risky_action_before_source_reopen"]
        ),
        "rollback_rework_minutes": sum(
            int(row["harm_components"]["rollback_rework_minutes"])
            for row in false_positive_rows
        ),
    }
    return summary, false_positive_costs


def summarize_net_value(
    *,
    success_count: int,
    cost_summary: dict[str, Any],
    harm_summary: dict[str, Any],
) -> dict[str, float]:
    success_value_units = round_delta(success_count * SUCCESS_VALUE_UNIT)
    cost_penalty_units = cost_summary["total_cost_units"]
    harm_penalty_units = harm_summary["harm_weighted_false_positive_cost"]
    return {
        "success_value_units": success_value_units,
        "cost_penalty_units": cost_penalty_units,
        "harm_penalty_units": harm_penalty_units,
        "net_value_units": round_delta(
            success_value_units - cost_penalty_units - harm_penalty_units
        ),
    }


def build_fresh_context_spec_loop_baseline(case_count: int) -> tuple[dict[str, Any], dict[str, float]]:
    # This is a comparison baseline, not an attribution arm: it represents the
    # user-visible work of rebuilding a compact spec/source loop each slice
    # without carrying long-lived memory state. Keeping it separate prevents the
    # no-memory diagnostic arm from being misread as the fair fresh-context
    # baseline named in #410.
    cost_summary = {
        "foreground_tokens": case_count * 260,
        "background_tokens": 0,
        "background_api_calls": 0,
        "wall_clock_latency_ms": case_count * 220,
        "indexing_maintenance_ms": 0,
        "storage_growth_bytes": 0,
        "source_reopen_count": case_count,
        "retry_recovery_count": 0,
        "human_correction_count": 0,
        "human_correction_minutes": 0,
        "success_count": case_count,
    }
    foreground_units = round_delta(
        cost_summary["foreground_tokens"] / 100.0
        + cost_summary["wall_clock_latency_ms"] / 1000.0
        + cost_summary["source_reopen_count"] * 0.25
    )
    cost_summary.update(
        {
            "foreground_cost_units": foreground_units,
            "background_cost_units": 0.0,
            "recovery_cost_units": 0.0,
            "total_cost_units": foreground_units,
            "foreground_cost_per_successful_slice": safe_cost_per_success(
                foreground_units,
                case_count,
            ),
            "background_cost_per_successful_slice": 0.0,
            "amortized_cost_per_successful_slice": safe_cost_per_success(
                foreground_units,
                case_count,
            ),
            "baseline_role": "fresh_context_spec_loop",
            "modeled_from": "public synthetic source-rebuild baseline for #410",
        }
    )
    net_summary = {
        "success_value_units": round_delta(case_count * SUCCESS_VALUE_UNIT),
        "cost_penalty_units": cost_summary["total_cost_units"],
        "harm_penalty_units": 0.0,
        "net_value_units": round_delta(
            case_count * SUCCESS_VALUE_UNIT - cost_summary["total_cost_units"]
        ),
    }
    return cost_summary, net_summary


def comparable_cost_per_success(
    cost_by_arm: dict[str, dict[str, Any]],
    fresh_context_spec_loop: dict[str, Any],
) -> dict[str, float]:
    comparable = {
        arm: details["amortized_cost_per_successful_slice"]
        for arm, details in cost_by_arm.items()
        if arm != "oracle_memory"
        and details["amortized_cost_per_successful_slice"] is not None
    }
    comparable["fresh_context_spec_loop"] = fresh_context_spec_loop[
        "amortized_cost_per_successful_slice"
    ]
    return comparable


def comparable_net_values(
    net_by_arm: dict[str, dict[str, float]],
    fresh_context_spec_loop_net: dict[str, float],
) -> dict[str, dict[str, float]]:
    comparable = {
        arm: details
        for arm, details in net_by_arm.items()
        if arm != "oracle_memory"
    }
    comparable["fresh_context_spec_loop"] = fresh_context_spec_loop_net
    return comparable


def build_cost_harm_ledger(
    rows: list[dict[str, Any]],
    *,
    metrics: dict[str, Any],
) -> dict[str, Any]:
    cost_by_arm: dict[str, dict[str, Any]] = {}
    harm_by_arm: dict[str, dict[str, Any]] = {}
    net_by_arm: dict[str, dict[str, float]] = {}
    all_false_positive_costs: list[float] = []

    for arm in ARM_ORDER:
        arm_rows = [row for row in rows if row["arm"] == arm]
        cost_by_arm[arm] = summarize_cost_for_rows(arm_rows)
        harm_by_arm[arm], false_positive_costs = summarize_harm_for_rows(arm_rows)
        all_false_positive_costs.extend(false_positive_costs)
        net_by_arm[arm] = summarize_net_value(
            success_count=cost_by_arm[arm]["success_count"],
            cost_summary=cost_by_arm[arm],
            harm_summary=harm_by_arm[arm],
        )

    fresh_context_spec_loop, baseline_net = build_fresh_context_spec_loop_baseline(
        int(metrics["case_count"])
    )
    comparable_costs = comparable_cost_per_success(cost_by_arm, fresh_context_spec_loop)
    comparable_net = comparable_net_values(net_by_arm, baseline_net)
    cost_per_success_candidates = {
        arm: details["amortized_cost_per_successful_slice"]
        for arm, details in cost_by_arm.items()
        if details["amortized_cost_per_successful_slice"] is not None
    }
    max_false_positive_cost = max(all_false_positive_costs, default=0.0)
    total_false_positive_count = sum(
        details["memory_false_positive_count"] for details in harm_by_arm.values()
    )
    stale_cost = harm_by_arm["stale_wrong_memory"]["harm_weighted_false_positive_cost"]
    non_stale_cost = sum(
        details["harm_weighted_false_positive_cost"]
        for arm, details in harm_by_arm.items()
        if arm != "stale_wrong_memory"
    )
    return {
        "schema_version": 1,
        "claim_level": "public_synthetic_cost_harm_contract",
        "cost": {
            "accounting_basis": "public_synthetic_cost_units",
            "unit_formula": {
                "foreground": "foreground_tokens/100 + latency_ms/1000 + source_reopen_count*0.25",
                "background": "background_tokens/100 + api_calls*2 + indexing_ms/1000 + storage_bytes/4096",
                "recovery": "retry_count*1.5 + human_correction_count*2 + correction_minutes*0.25",
            },
            "background_jobs_counted": True,
            "unavailable_required_components": [],
            "component_status": {
                "foreground_tokens": "estimated_from_public_fixture_text",
                "background_tokens": "modeled_memory_prep_tokens",
                "background_api_calls": "modeled_optional_model_or_sidecar_calls",
                "wall_clock_latency_ms": "modeled_public_fixture_latency",
                "indexing_maintenance_ms": "modeled_clean_source_build_cost",
                "storage_growth_bytes": "modeled_sanitized_memory_artifact_growth",
                "source_reopen_count": "measured_from_fixture_source_reopen_behavior",
                "retry_recovery_count": "modeled_from_failed_or_abstained_behavior",
                "human_correction_count": "modeled_from_stale_memory_failure",
                "human_correction_minutes": "modeled_from_rework_severity",
            },
            "by_arm": cost_by_arm,
            "comparison_baselines": {
                "fresh_context_spec_loop": fresh_context_spec_loop,
            },
        },
        "harm": {
            "basis": "severity_weighted_public_synthetic_memory_false_positives",
            "overall_false_positive_count": total_false_positive_count,
            "overall_false_positive_rate": safe_rate(total_false_positive_count, len(rows)),
            "max_single_false_positive_cost": max_false_positive_cost,
            "average_false_positive_cost": round_delta(
                sum(all_false_positive_costs) / len(all_false_positive_costs)
            ) if all_false_positive_costs else 0.0,
            "severe_false_positive_dominates_score": bool(
                stale_cost > non_stale_cost
                and max_false_positive_cost
                > (sum(all_false_positive_costs) / len(all_false_positive_costs))
            ),
            "severity_weights": {
                "severity_squared": "dominant base weight",
                "downstream_turn": 1.5,
                "wrong_constraint_adopted": 6.0,
                "rejected_route_retried": 5.0,
                "current_project_contamination": 8.0,
                "risky_action_before_source_reopen": 7.0,
                "privacy_sensitive_recall_severity": 10.0,
                "rollback_rework_minutes": "minutes/3",
            },
            "by_arm": harm_by_arm,
        },
        "net_value_under_equalized_cost": {
            "decision_rule": {
                "forces_memory_arm_win": False,
                "allows_fresh_context_cost_win": True,
                "excludes_oracle_from_fair_cost_winner": True,
                "separates_success_cost_and_harm": True,
                "success_value_unit": SUCCESS_VALUE_UNIT,
            },
            "lowest_amortized_cost_per_successful_slice_arm": min(
                cost_per_success_candidates,
                key=cost_per_success_candidates.__getitem__,
            ),
            "lowest_amortized_cost_per_successful_slice_fair_strategy": min(
                comparable_costs,
                key=comparable_costs.__getitem__,
            ),
            "highest_net_value_arm": max(
                net_by_arm,
                key=lambda arm: net_by_arm[arm]["net_value_units"],
            ),
            "highest_net_value_fair_strategy": max(
                comparable_net,
                key=lambda arm: comparable_net[arm]["net_value_units"],
            ),
            "by_arm": net_by_arm,
            "comparison_baselines": {
                "fresh_context_spec_loop": baseline_net,
            },
            "source_metrics": {
                "memory_correctness_effect": metrics["memory_correctness_effect"],
                "stale_memory_harm": metrics["stale_memory_harm"],
            },
        },
    }


def run_benchmark(*, arms: Sequence[str] | None = None) -> dict[str, Any]:
    started = time.perf_counter()
    selected_arms = tuple(arms or ARM_ORDER)
    unknown = sorted(set(selected_arms) - set(ARM_ORDER))
    if unknown:
        raise ValueError(f"unknown arm(s): {', '.join(unknown)}")
    cases = fixture_cases()
    rows = [evaluate_case(case, arm) for case in cases for arm in selected_arms]
    metrics = summarize_rows(rows, case_count=len(cases))
    cost_harm_ledger = build_cost_harm_ledger(rows, metrics=metrics)
    required_arms_present = set(ARM_ORDER) <= set(selected_arms)
    attribution_controls_present = (
        metrics["memory_presence_effect"] == 0.0
        and metrics["memory_correctness_effect"] > 0.0
        and metrics["stale_memory_harm"] > 0.0
        and metrics["oracle_headroom"] > 0.0
    )
    ok = bool(required_arms_present and attribution_controls_present)
    return {
        "kind": "aippocampus_continuous_memory_arms_benchmark",
        "schema_version": SCHEMA_VERSION,
        "generated_at": now_utc(),
        "status": "diagnostic_attribution_controls" if ok else "failed",
        "ok": ok,
        "arms": list(selected_arms),
        "config": {
            "scenario_family": "continuous_agent_memory_attribution",
            "scenario_provenance": ["author_written_synthetic"],
            "uses_live_model": False,
            "uses_private_history": False,
            "uses_oracle_for_true_memory_scoring": False,
            "default_suite_member": False,
        },
        "metrics": metrics,
        "cost_harm_ledger": cost_harm_ledger,
        "rows": rows,
        "privacy_boundary": {
            "public_safe_synthetic_fixtures": True,
            "raw_source_snippets_in_report": False,
            "raw_private_prompts_in_report": False,
            "absolute_paths_in_report": False,
            "case_ids_are_hashed": True,
            "cost_harm_ledger_contains_raw_private_inputs": False,
            "output_shape": "sanitized_memory_arm_attribution_and_cost_harm_report",
        },
        "interpretation_notes": [
            "memory_presence_effect isolates formatting and nearby-token effects.",
            "memory_correctness_effect isolates true source-backed memory over sham text.",
            "stale wrong arm is an adversarial diagnostic stressor, not a product mode",
            "oracle_memory is an upper-bound arm and must not leak into true-memory scoring.",
            "cost and harm ledger uses public synthetic units, not exact billing data.",
        ],
        "cannot_claim": [
            "full #378 continuous-memory superiority",
            "exact dollar accounting for every local operation",
            "live host-native cost telemetry",
            "live host-native compaction behavior",
            "private real-history generality",
            "competitor or leaderboard superiority",
            "answer-generation model quality",
        ],
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
    }


def print_human_summary(payload: dict[str, Any]) -> None:
    metrics = payload["metrics"]
    print("AIppocampus continuous-memory attribution arms")
    print(f"status: {payload['status']}")
    print(f"cases: {metrics['case_count']} arms: {metrics['arm_count']}")
    print(
        "presence: {presence} correctness: {correctness} stale_harm: {stale} "
        "oracle_headroom: {oracle}".format(
            presence=metrics["memory_presence_effect"],
            correctness=metrics["memory_correctness_effect"],
            stale=metrics["stale_memory_harm"],
            oracle=metrics["oracle_headroom"],
        )
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arm", action="append", choices=ARM_ORDER)
    parser.add_argument("--json", action="store_true", dest="json_output")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)

    payload = run_benchmark(arms=args.arm)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    if args.json_output:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print_human_summary(payload)
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
