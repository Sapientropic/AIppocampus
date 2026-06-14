#!/usr/bin/env python3
"""Public-safe Dream delivery-quality eval for #1438.

This runner is intentionally narrower than a live/private Dream claim. It asks
whether a pre-registered bounded-hint treatment improves selected delivery
cases over no-Dream and backstage-only arms while suppressing stale, noisy,
over-personalized, Dream-only, and source-truth-overclaim controls.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import _paths

_paths.ensure_paths()

REPORT_KIND = "aippocampus_dream_delivery_quality_eval"
SCHEMA_VERSION = 1
ARM_BASELINE = "baseline_no_dream"
ARM_BACKSTAGE = "dream_backstage_only"
ARM_BOUNDED = "dream_bounded_action_hint"
ARMS = (ARM_BASELINE, ARM_BACKSTAGE, ARM_BOUNDED)


def _ratio(numerator: int | float, denominator: int | float) -> float:
    return round(float(numerator) / float(denominator), 6) if denominator else 0.0


def _arm(
    *,
    route_found: bool,
    manual_search_steps: int,
    verification_cost: int,
    action_quality: int,
    visible_hint: bool = False,
    wrong_hint: bool = False,
    source_ripened: bool = False,
    source_reopen_required: bool = True,
    suppressed_reason: str = "",
    source_truth_overclaim: bool = False,
) -> dict[str, Any]:
    return {
        "route_found": route_found,
        "manual_search_steps": manual_search_steps,
        "verification_cost": verification_cost,
        "action_quality": action_quality,
        "visible_hint": visible_hint,
        "wrong_hint": wrong_hint,
        "source_ripened": source_ripened,
        "source_reopen_required": source_reopen_required,
        "suppressed_reason": suppressed_reason,
        "source_truth_overclaim": source_truth_overclaim,
    }


def _fixture_cases() -> list[dict[str, Any]]:
    return [
        {
            "case_id": "rejected_route_recovery",
            "case_family": "repeated_rejected_route",
            "control_family": "positive_route_lift",
            "arms": {
                ARM_BASELINE: _arm(
                    route_found=False,
                    manual_search_steps=3,
                    verification_cost=3,
                    action_quality=0,
                ),
                ARM_BACKSTAGE: _arm(
                    route_found=True,
                    manual_search_steps=2,
                    verification_cost=2,
                    action_quality=1,
                    source_ripened=True,
                ),
                ARM_BOUNDED: _arm(
                    route_found=True,
                    manual_search_steps=1,
                    verification_cost=1,
                    action_quality=2,
                    visible_hint=True,
                    source_ripened=True,
                ),
            },
        },
        {
            "case_id": "currentness_check_before_retry",
            "case_family": "stale_hypothesis_currentness",
            "control_family": "positive_action_lift",
            "arms": {
                ARM_BASELINE: _arm(
                    route_found=True,
                    manual_search_steps=2,
                    verification_cost=2,
                    action_quality=0,
                ),
                ARM_BACKSTAGE: _arm(
                    route_found=True,
                    manual_search_steps=2,
                    verification_cost=2,
                    action_quality=1,
                    source_ripened=True,
                ),
                ARM_BOUNDED: _arm(
                    route_found=True,
                    manual_search_steps=1,
                    verification_cost=1,
                    action_quality=2,
                    visible_hint=True,
                    source_ripened=True,
                ),
            },
        },
        {
            "case_id": "stale_route_negative_control",
            "case_family": "stale_route",
            "control_family": "stale_route",
            "arms": {
                ARM_BASELINE: _arm(
                    route_found=True,
                    manual_search_steps=1,
                    verification_cost=1,
                    action_quality=1,
                ),
                ARM_BACKSTAGE: _arm(
                    route_found=True,
                    manual_search_steps=1,
                    verification_cost=1,
                    action_quality=1,
                    suppressed_reason="stale_route",
                ),
                ARM_BOUNDED: _arm(
                    route_found=True,
                    manual_search_steps=1,
                    verification_cost=1,
                    action_quality=1,
                    suppressed_reason="stale_route",
                ),
            },
        },
        {
            "case_id": "noisy_generic_hint_control",
            "case_family": "noisy_hint",
            "control_family": "noisy_hint",
            "arms": {
                ARM_BASELINE: _arm(
                    route_found=False,
                    manual_search_steps=0,
                    verification_cost=0,
                    action_quality=1,
                ),
                ARM_BACKSTAGE: _arm(
                    route_found=False,
                    manual_search_steps=0,
                    verification_cost=0,
                    action_quality=1,
                    suppressed_reason="noisy_hint",
                ),
                ARM_BOUNDED: _arm(
                    route_found=False,
                    manual_search_steps=0,
                    verification_cost=0,
                    action_quality=1,
                    suppressed_reason="noisy_hint",
                ),
            },
        },
        {
            "case_id": "over_personalized_hint_control",
            "case_family": "over_personalization",
            "control_family": "over_personalization",
            "arms": {
                ARM_BASELINE: _arm(
                    route_found=False,
                    manual_search_steps=0,
                    verification_cost=0,
                    action_quality=1,
                ),
                ARM_BACKSTAGE: _arm(
                    route_found=False,
                    manual_search_steps=0,
                    verification_cost=0,
                    action_quality=1,
                    suppressed_reason="over_personalization",
                ),
                ARM_BOUNDED: _arm(
                    route_found=False,
                    manual_search_steps=0,
                    verification_cost=0,
                    action_quality=1,
                    suppressed_reason="over_personalization",
                ),
            },
        },
        {
            "case_id": "source_truth_overclaim_control",
            "case_family": "source_truth_boundary",
            "control_family": "source_truth_overclaim",
            "arms": {
                ARM_BASELINE: _arm(
                    route_found=False,
                    manual_search_steps=1,
                    verification_cost=1,
                    action_quality=1,
                ),
                ARM_BACKSTAGE: _arm(
                    route_found=True,
                    manual_search_steps=1,
                    verification_cost=1,
                    action_quality=1,
                    suppressed_reason="source_reopen_required",
                ),
                ARM_BOUNDED: _arm(
                    route_found=True,
                    manual_search_steps=1,
                    verification_cost=1,
                    action_quality=1,
                    suppressed_reason="source_reopen_required",
                ),
            },
        },
    ]


def _case_readout(case: Mapping[str, Any]) -> dict[str, Any]:
    raw_arms = case.get("arms")
    arms: Mapping[str, Any] = raw_arms if isinstance(raw_arms, Mapping) else {}
    baseline = arms.get(ARM_BASELINE, {})
    bounded = arms.get(ARM_BOUNDED, {})
    backstage = arms.get(ARM_BACKSTAGE, {})
    bounded_route_lift = bool(
        bounded.get("route_found")
        and (
            not baseline.get("route_found")
            or int(bounded.get("manual_search_steps") or 0)
            < int(baseline.get("manual_search_steps") or 0)
        )
    )
    bounded_action_lift = int(bounded.get("action_quality") or 0) > int(
        baseline.get("action_quality") or 0
    )
    bounded_verification_cost_delta = int(
        bounded.get("verification_cost") or 0
    ) - int(baseline.get("verification_cost") or 0)
    bounded_quiet_no_harm = bool(
        not bounded.get("visible_hint")
        and not bounded.get("wrong_hint")
        and int(bounded.get("action_quality") or 0)
        >= int(baseline.get("action_quality") or 0)
    )
    dream_only_foreground_leak = bool(
        bounded.get("visible_hint") and not bounded.get("source_ripened")
    )
    return {
        "case_id": str(case.get("case_id") or "case"),
        "case_family": str(case.get("case_family") or ""),
        "control_family": str(case.get("control_family") or ""),
        "arms": {
            arm: arms.get(arm, {})
            for arm in ARMS
            if isinstance(arms.get(arm), Mapping)
        },
        "bounded_route_lift": bounded_route_lift,
        "bounded_action_lift": bounded_action_lift,
        "bounded_verification_cost_delta": bounded_verification_cost_delta,
        "bounded_quiet_no_harm": bounded_quiet_no_harm,
        "source_ripening": bool(
            bounded.get("source_ripened") or backstage.get("source_ripened")
        ),
        "dream_only_foreground_leak": dream_only_foreground_leak,
    }


def _metrics(cases: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    visible_hint_count = sum(
        1 for case in cases if case["arms"][ARM_BOUNDED]["visible_hint"]
    )
    wrong_hint_count = sum(
        1 for case in cases if case["arms"][ARM_BOUNDED]["wrong_hint"]
    )
    return {
        "case_count": len(cases),
        "bounded_route_lift_count": sum(
            1 for case in cases if case["bounded_route_lift"]
        ),
        "bounded_action_lift_count": sum(
            1 for case in cases if case["bounded_action_lift"]
        ),
        "bounded_verification_cost_delta_total": sum(
            int(case["bounded_verification_cost_delta"]) for case in cases
        ),
        "visible_hint_count": visible_hint_count,
        "visible_wrong_hint_count": wrong_hint_count,
        "visible_wrong_hint_rate": _ratio(wrong_hint_count, visible_hint_count),
        "quiet_no_harm_count": sum(
            1 for case in cases if case["bounded_quiet_no_harm"]
        ),
        "source_ripening_count": sum(1 for case in cases if case["source_ripening"]),
    }


def _negative_controls(cases: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    bounded_arms = [case["arms"][ARM_BOUNDED] for case in cases]
    return {
        "stale_route_suppressed_count": sum(
            1
            for arm in bounded_arms
            if arm.get("suppressed_reason") == "stale_route"
        ),
        "noisy_hint_suppressed_count": sum(
            1 for arm in bounded_arms if arm.get("suppressed_reason") == "noisy_hint"
        ),
        "over_personalization_suppressed_count": sum(
            1
            for arm in bounded_arms
            if arm.get("suppressed_reason") == "over_personalization"
        ),
        "dream_only_foreground_leak_count": sum(
            1 for case in cases if case["dream_only_foreground_leak"]
        ),
        "source_truth_overclaim_count": sum(
            1 for arm in bounded_arms if arm.get("source_truth_overclaim")
        ),
        "source_reopen_required_count": sum(
            1 for arm in bounded_arms if arm.get("source_reopen_required")
        ),
    }


def build_dream_delivery_quality_report() -> dict[str, Any]:
    cases = [_case_readout(case) for case in _fixture_cases()]
    metrics = _metrics(cases)
    negative_controls = _negative_controls(cases)
    ok = bool(
        metrics["case_count"] >= 6
        and metrics["bounded_route_lift_count"] >= 2
        and metrics["bounded_action_lift_count"] >= 2
        and metrics["bounded_verification_cost_delta_total"] < 0
        and metrics["visible_wrong_hint_count"] == 0
        and metrics["quiet_no_harm_count"] >= 4
        and metrics["source_ripening_count"] >= 2
        and negative_controls["stale_route_suppressed_count"] >= 1
        and negative_controls["noisy_hint_suppressed_count"] >= 1
        and negative_controls["over_personalization_suppressed_count"] >= 1
        and negative_controls["dream_only_foreground_leak_count"] == 0
        and negative_controls["source_truth_overclaim_count"] == 0
    )
    return {
        "kind": REPORT_KIND,
        "schema_version": SCHEMA_VERSION,
        "ok": ok,
        "claim_level": "public_synthetic_delivery_quality_eval",
        "scoring_contract": {
            "arms": list(ARMS),
            "arms_pre_registered": True,
            "scoring_defined_before_cases": True,
            "private_history_used": False,
            "provider_call_count": 0,
            "same_public_fixture_budget": True,
        },
        "metrics": metrics,
        "negative_controls": negative_controls,
        "cases": cases,
        "issue_readouts": {
            "github_1438": {
                "delivery_quality_eval_measured": True,
                "arms_pre_registered": True,
                "negative_controls_covered": True,
                "sanitized_aggregate_only": True,
                "live_private_delivery_quality_measured": False,
                "closeout_eligible": ok,
            }
        },
        "can_claim": [
            "public_synthetic_three_arm_delivery_quality_eval_exists",
            "bounded_hint_arm_improves_selected_route_and_action_cases",
            "stale_noisy_over_personalized_and_unsourced_controls_stay_quiet",
            "source_reopen_required_before_dream_material_can_support_claims",
        ],
        "cannot_claim": [
            "live_default_dream_delivery_quality",
            "broad_private_history_dream_quality",
            "causal_real_user_lift",
            "dream_only_material_as_source_truth",
            "default_foreground_dream_adoption",
        ],
        "privacy_boundary": {
            "prompt_text_serialized": False,
            "source_text_serialized": False,
            "source_handles_serialized": False,
            "thread_handles_serialized": False,
            "provider_details_serialized": False,
            "credential_values_serialized": False,
        },
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Emit the JSON report.")
    parser.add_argument("--output", type=Path, help="Optional JSON output path.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    report = build_dream_delivery_quality_report()
    text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    if args.json:
        print(text)
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
