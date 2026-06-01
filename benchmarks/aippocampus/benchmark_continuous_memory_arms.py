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
            ),
        ),
    ]


def evaluate_case(case: AttributionCase, arm: str) -> dict[str, Any]:
    spec = case.spec_for_arm(arm)
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


def run_benchmark(*, arms: Sequence[str] | None = None) -> dict[str, Any]:
    started = time.perf_counter()
    selected_arms = tuple(arms or ARM_ORDER)
    unknown = sorted(set(selected_arms) - set(ARM_ORDER))
    if unknown:
        raise ValueError(f"unknown arm(s): {', '.join(unknown)}")
    cases = fixture_cases()
    rows = [evaluate_case(case, arm) for case in cases for arm in selected_arms]
    metrics = summarize_rows(rows, case_count=len(cases))
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
        "rows": rows,
        "privacy_boundary": {
            "public_safe_synthetic_fixtures": True,
            "raw_source_snippets_in_report": False,
            "raw_private_prompts_in_report": False,
            "absolute_paths_in_report": False,
            "case_ids_are_hashed": True,
            "output_shape": "sanitized_memory_arm_attribution_report",
        },
        "interpretation_notes": [
            "memory_presence_effect isolates formatting and nearby-token effects.",
            "memory_correctness_effect isolates true source-backed memory over sham text.",
            "stale wrong arm is an adversarial diagnostic stressor, not a product mode",
            "oracle_memory is an upper-bound arm and must not leak into true-memory scoring.",
        ],
        "cannot_claim": [
            "full #378 continuous-memory superiority",
            "complete #410 cost and harm ledger",
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
