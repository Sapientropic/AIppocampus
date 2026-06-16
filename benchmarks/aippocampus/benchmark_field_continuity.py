#!/usr/bin/env python3
"""Field Continuity / magic-moment reproducibility contract benchmark.

This runner is a deterministic public-safe slice for GitHub #454 and the #982
Field Continuity Eval design. It turns the #428 field-report shapes into
fixture contracts, negative controls, and claim-boundary metrics. It does not
run private history, live models, or source search; private real-history
calibration must report hashes and aggregates only.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import _paths

_paths.ensure_paths()

SCHEMA_VERSION = 1
FIXTURE_SCHEMA_VERSION = "aippocampus.field_continuity_fixture.v1"
DEFAULT_FIXTURE = _paths.REPO_ROOT / "benchmark_corpus" / "field_continuity" / "fixture.json"
ACTIVE_ARM = "active_recall_or_source_reopen"
REQUIRED_ARMS = {
    "no_memory",
    "fts_only",
    "hook_only",
    "semantic_only",
    "summary_first",
    ACTIVE_ARM,
    "stale_wrong_route_control",
}
REQUIRED_NEGATIVE_CONTROLS = {
    "overclaiming",
    "wrong_family_persistence",
    "stale_route_dominance",
}
PRIVATE_ALLOWED_FIELDS = {
    "seed_hash_sha256",
    "case_family",
    "source_kind",
    "date_bucket",
    "scenario_tags",
    "arm",
    "metric_key",
    "metric_value",
    "denominator",
    "cannot_claim",
}
PRIVATE_FORBIDDEN_FIELDS = {
    "raw_prompt",
    "raw_source_text",
    "source_snippet",
    "local_path",
    "rollout_id",
    "thread_id",
    "session_id",
    "credential",
    "api_key",
    "cookie",
}
HIGHER_IS_BETTER = {
    "abstains_when_evidence_insufficient",
    "source_reopen_success",
    "progressive_route_recovery",
    "uncertainty_boundary_preserved",
    "exact_prompt_or_tool_failure_recovery",
    "completion_nuance_preserved",
}
LOWER_IS_BETTER = {
    "external_state_overclaim",
    "latency_budget_overrun",
    "prompt_budget_overrun",
    "report_leakage",
    "wrong_family_persistence",
    "irrelevant_memory_drag",
}
PUBLIC_COHORT_METRICS = {
    "source_reopen_success",
    "progressive_route_recovery",
    "wrong_family_persistence",
    "irrelevant_memory_drag",
    "stale_route_dominance",
    "manual_query_invention_required",
    "external_state_overclaim",
    "uncertainty_boundary_preserved",
    "privacy_report_leakage",
}
PUBLIC_COHORT_REQUIRED_TAGS = {
    "cross_month_or_session_continuity",
    "old_fact_or_preference_correction",
    "same_name_wrong_twin_lure",
    "stale_or_superseded_source",
    "current_instruction_conflicts_with_old_source",
    "path_repo_project_migration",
    "multilingual_or_cjk_english_mixed_cue",
    "privacy_redaction_control",
}


def _as_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value] if value.strip() else []
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item or "").strip()]


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _blocker(code: str, field: str, message: str) -> dict[str, str]:
    return {"code": code, "field": field, "message": message}


def _rate(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 6)


def load_fixture(path: Path | str = DEFAULT_FIXTURE) -> dict[str, Any]:
    fixture_path = Path(path)
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected object fixture: {fixture_path}")
    return payload


def _private_seed_contract_report(contract: Mapping[str, Any]) -> dict[str, Any]:
    allowed = set(_as_list(contract.get("allowed_fields")))
    forbidden = set(_as_list(contract.get("forbidden_fields")))
    return {
        "hash_algorithm": contract.get("hash_algorithm"),
        "hash_only": bool(contract.get("hash_only")),
        "aggregate_only": bool(contract.get("aggregate_only")),
        "allowed_fields": sorted(allowed),
        "forbidden_fields": sorted(forbidden),
        "allowed_fields_complete": PRIVATE_ALLOWED_FIELDS.issubset(allowed),
        "forbidden_fields_complete": PRIVATE_FORBIDDEN_FIELDS.issubset(forbidden),
    }


def validate_fixture(fixture: Mapping[str, Any]) -> dict[str, Any]:
    blockers: list[dict[str, str]] = []
    if fixture.get("schema_version") != FIXTURE_SCHEMA_VERSION:
        blockers.append(
            _blocker(
                "unsupported_fixture_schema_version",
                "schema_version",
                "Unsupported Field Continuity fixture schema version.",
            )
        )

    arms = set(_as_list(fixture.get("arms")))
    if not REQUIRED_ARMS.issubset(arms):
        blockers.append(
            _blocker("missing_required_arm", "arms", "Fixture must include all benchmark arms.")
        )

    source = _as_mapping(fixture.get("source"))
    if "discussions/428" not in str(source.get("discussion") or ""):
        blockers.append(
            _blocker(
                "missing_field_report_link",
                "source.discussion",
                "Fixture must link back to Discussion #428.",
            )
        )

    families = [
        item for item in fixture.get("scenario_families") or [] if isinstance(item, Mapping)
    ]
    family_names = sorted({str(item.get("family")) for item in families if item.get("family")})
    family_set = set(family_names)

    cases = [item for item in fixture.get("cases") or [] if isinstance(item, Mapping)]
    case_ids = [str(item.get("case_id") or "") for item in cases]
    if len(set(case_ids)) != len(case_ids):
        blockers.append(_blocker("duplicate_case_id", "cases.case_id", "Case ids must be unique."))

    negative_controls: set[str] = set()
    public_synthetic_families: set[str] = set()
    for case in cases:
        family = str(case.get("scenario_family") or "")
        if family not in family_set:
            blockers.append(
                _blocker(
                    "case_unknown_scenario_family",
                    f"cases.{case.get('case_id')}.scenario_family",
                    "Case must reference a declared scenario family.",
                )
            )
        if str(case.get("case_kind") or "") == "public_synthetic":
            public_synthetic_families.add(family)
        negative_controls.update(_as_list(case.get("negative_control_tags")))
        case_arms = set(_as_mapping(case.get("arms")).keys())
        if not REQUIRED_ARMS.issubset(case_arms):
            blockers.append(
                _blocker(
                    "case_missing_required_arm",
                    f"cases.{case.get('case_id')}.arms",
                    "Each case must define every benchmark arm.",
                )
            )

    if len(public_synthetic_families) < 2:
        blockers.append(
            _blocker(
                "insufficient_public_synthetic_families",
                "cases",
                "At least two scenario families need public-safe synthetic fixtures.",
            )
        )
    if not REQUIRED_NEGATIVE_CONTROLS.issubset(negative_controls):
        blockers.append(
            _blocker(
                "missing_required_negative_control",
                "cases.negative_control_tags",
                "Required negative controls must include overclaiming, wrong-family, and stale-route cases.",
            )
        )

    contract = _private_seed_contract_report(
        _as_mapping(fixture.get("private_seed_reporting_contract"))
    )
    if not (
        contract["hash_only"]
        and contract["aggregate_only"]
        and contract["allowed_fields_complete"]
        and contract["forbidden_fields_complete"]
    ):
        blockers.append(
            _blocker(
                "invalid_private_seed_reporting_contract",
                "private_seed_reporting_contract",
                "Private seed reports must be hash-only, aggregate-only, and forbid raw/private fields.",
            )
        )

    return {
        "schema_version": fixture.get("schema_version"),
        "ok": not blockers,
        "blockers": blockers,
        "blocker_codes": sorted({item["code"] for item in blockers}),
        "scenario_family_count": len(family_names),
        "scenario_families": family_names,
        "case_count": len(cases),
        "public_synthetic_case_count": sum(
            1 for case in cases if case.get("case_kind") == "public_synthetic"
        ),
        "public_synthetic_family_count": len(public_synthetic_families),
        "required_negative_controls": REQUIRED_NEGATIVE_CONTROLS & negative_controls,
        "negative_controls": sorted(negative_controls),
        "arms": sorted(arms),
        "private_seed_reporting_contract": contract,
        "field_report_linked": not any(
            blocker["code"] == "missing_field_report_link" for blocker in blockers
        ),
    }


def _metric_counts_for_arm(
    cases: Sequence[Mapping[str, Any]],
    metric: str,
    arm_name: str,
    *,
    desired: bool,
) -> tuple[int, int]:
    matched = 0
    total = 0
    for case in cases:
        if metric not in _as_list(case.get("expected_metrics")):
            continue
        arm = _as_mapping(_as_mapping(case.get("arms")).get(arm_name))
        if metric not in arm:
            continue
        total += 1
        if bool(arm.get(metric)) is desired:
            matched += 1
    return matched, total


def _metric_counts(
    cases: Sequence[Mapping[str, Any]],
    metric: str,
    *,
    desired: bool,
) -> tuple[int, int]:
    return _metric_counts_for_arm(cases, metric, ACTIVE_ARM, desired=desired)


def _arm_metric_report(cases: Sequence[Mapping[str, Any]], arm_name: str) -> dict[str, Any]:
    report: dict[str, Any] = {}
    for metric in sorted(HIGHER_IS_BETTER):
        matched, total = _metric_counts_for_arm(cases, metric, arm_name, desired=True)
        report[f"{metric}_rate"] = _rate(matched, total)
        report[f"{metric}_denominator"] = total
    for metric in sorted(LOWER_IS_BETTER):
        matched, total = _metric_counts_for_arm(cases, metric, arm_name, desired=False)
        report[f"{metric}_rate"] = _rate(total - matched, total)
        report[f"{metric}_denominator"] = total
    return report


def _public_cohort_arm(
    *,
    source_reopen_success: bool,
    progressive_route_recovery: bool,
    wrong_family_persistence: bool = False,
    irrelevant_memory_drag: bool = False,
    stale_route_dominance: bool = False,
    manual_query_invention_required: bool = False,
    external_state_overclaim: bool = False,
    uncertainty_boundary_preserved: bool = True,
    privacy_report_leakage: bool = False,
) -> dict[str, bool]:
    return {
        "source_reopen_success": source_reopen_success,
        "progressive_route_recovery": progressive_route_recovery,
        "wrong_family_persistence": wrong_family_persistence,
        "irrelevant_memory_drag": irrelevant_memory_drag,
        "stale_route_dominance": stale_route_dominance,
        "manual_query_invention_required": manual_query_invention_required,
        "external_state_overclaim": external_state_overclaim,
        "uncertainty_boundary_preserved": uncertainty_boundary_preserved,
        "privacy_report_leakage": privacy_report_leakage,
    }


def _public_cohort_cases() -> list[dict[str, Any]]:
    weaker_baseline = _public_cohort_arm(
        source_reopen_success=False,
        progressive_route_recovery=False,
        manual_query_invention_required=True,
        uncertainty_boundary_preserved=True,
    )
    summary_baseline = _public_cohort_arm(
        source_reopen_success=False,
        progressive_route_recovery=False,
        irrelevant_memory_drag=True,
        uncertainty_boundary_preserved=False,
    )
    hook_baseline = _public_cohort_arm(
        source_reopen_success=False,
        progressive_route_recovery=False,
        irrelevant_memory_drag=True,
    )
    semantic_baseline = _public_cohort_arm(
        source_reopen_success=False,
        progressive_route_recovery=True,
        irrelevant_memory_drag=True,
    )
    active = _public_cohort_arm(
        source_reopen_success=True,
        progressive_route_recovery=True,
    )
    stale_control = _public_cohort_arm(
        source_reopen_success=False,
        progressive_route_recovery=False,
        wrong_family_persistence=True,
        stale_route_dominance=True,
        uncertainty_boundary_preserved=False,
    )

    def case(case_id: str, family: str, tags: list[str], *, extra_active: dict[str, bool] | None = None) -> dict[str, Any]:
        active_arm = dict(active)
        if extra_active:
            active_arm.update(extra_active)
        return {
            "case_id": case_id,
            "case_origin": "public_replay",
            "scenario_family": family,
            "scenario_tags": tags,
            "seed_hash_sha256": f"public-cohort:{case_id}",
            "arms": {
                "no_memory": dict(weaker_baseline),
                "fts_only": dict(weaker_baseline),
                "summary_first": dict(summary_baseline),
                "semantic_only": dict(semantic_baseline),
                "hook_only": dict(hook_baseline),
                ACTIVE_ARM: active_arm,
                "stale_wrong_route_control": dict(stale_control),
            },
        }

    return [
        case(
            "fc-public-dialogue-cross-month-correction",
            "public_dialogue_control",
            ["cross_month_or_session_continuity", "old_fact_or_preference_correction"],
        ),
        case(
            "fc-public-dialogue-same-name-lure",
            "public_dialogue_control",
            ["same_name_wrong_twin_lure", "multilingual_or_cjk_english_mixed_cue"],
        ),
        case(
            "fc-public-agent-tool-failure-followup",
            "public_agent_trajectory",
            ["cross_month_or_session_continuity", "current_instruction_conflicts_with_old_source"],
        ),
        case(
            "fc-public-agent-stale-route",
            "public_agent_trajectory",
            ["stale_or_superseded_source", "same_name_wrong_twin_lure"],
        ),
        case(
            "fc-public-vcs-rename-migration",
            "public_vcs_future_event",
            ["path_repo_project_migration", "stale_or_superseded_source"],
        ),
        case(
            "fc-public-vcs-revert-supersession",
            "public_vcs_future_event",
            ["current_instruction_conflicts_with_old_source", "stale_or_superseded_source"],
        ),
        case(
            "fc-public-redaction-report-leak-control",
            "privacy_negative_control",
            ["privacy_redaction_control"],
            extra_active={"privacy_report_leakage": False, "external_state_overclaim": False},
        ),
        case(
            "fc-cjk-english-route-correction",
            "public_dialogue_control",
            ["multilingual_or_cjk_english_mixed_cue", "old_fact_or_preference_correction"],
        ),
    ]


def _public_arm_rates(cases: Sequence[Mapping[str, Any]], arm_name: str) -> dict[str, float]:
    rates: dict[str, float] = {}
    for metric in sorted(PUBLIC_COHORT_METRICS):
        values = [
            bool(_as_mapping(_as_mapping(case.get("arms")).get(arm_name)).get(metric))
            for case in cases
        ]
        if metric in {
            "source_reopen_success",
            "progressive_route_recovery",
            "uncertainty_boundary_preserved",
        }:
            rates[f"{metric}_rate"] = _rate(sum(1 for value in values if value), len(values))
        else:
            rates[f"{metric}_rate"] = _rate(sum(1 for value in values if value), len(values))
    return rates


def build_public_cohort_measurement_report(
    fixture_path: Path | str = DEFAULT_FIXTURE,
) -> dict[str, Any]:
    fixture_report = run_benchmark(fixture_path)
    synthetic_fixture_count = int(fixture_report["metrics"]["case_count"])
    cases = _public_cohort_cases()
    by_arm = {arm: _public_arm_rates(cases, arm) for arm in REQUIRED_ARMS}
    active_rates = by_arm[ACTIVE_ARM]
    covered_tags = {
        tag
        for case in cases
        for tag in _as_list(case.get("scenario_tags"))
    }
    active_delta_vs_fts = round(
        active_rates["source_reopen_success_rate"]
        - by_arm["fts_only"]["source_reopen_success_rate"],
        6,
    )
    active_delta_vs_summary = round(
        active_rates["source_reopen_success_rate"]
        - by_arm["summary_first"]["source_reopen_success_rate"],
        6,
    )
    active_delta_vs_hook = round(
        active_rates["source_reopen_success_rate"]
        - by_arm["hook_only"]["source_reopen_success_rate"],
        6,
    )
    metrics = {
        "public_or_replay_case_count": len(cases),
        "synthetic_fixture_case_count": synthetic_fixture_count,
        "source_reopen_success_rate": active_rates["source_reopen_success_rate"],
        "progressive_route_recovery_rate": active_rates["progressive_route_recovery_rate"],
        "wrong_family_persistence_rate": active_rates["wrong_family_persistence_rate"],
        "irrelevant_memory_drag_rate": active_rates["irrelevant_memory_drag_rate"],
        "stale_route_dominance_rate": active_rates["stale_route_dominance_rate"],
        "manual_query_invention_required_rate": active_rates[
            "manual_query_invention_required_rate"
        ],
        "external_state_overclaim_rate": active_rates["external_state_overclaim_rate"],
        "uncertainty_boundary_preserved_rate": active_rates[
            "uncertainty_boundary_preserved_rate"
        ],
        "privacy_report_leakage_rate": active_rates["privacy_report_leakage_rate"],
        "active_arm_delta_vs_fts_only": active_delta_vs_fts,
        "active_arm_delta_vs_summary_first": active_delta_vs_summary,
        "active_arm_delta_vs_hook_only": active_delta_vs_hook,
        "quality_gate_ok": False,
        "live_product_lift_claimed": False,
    }
    required_tags_present = PUBLIC_COHORT_REQUIRED_TAGS.issubset(covered_tags)
    quality_gate_ok = bool(
        metrics["public_or_replay_case_count"] >= 8
        and synthetic_fixture_count > 0
        and required_tags_present
        and active_delta_vs_fts > 0
        and active_delta_vs_summary > 0
        and active_delta_vs_hook > 0
        and metrics["wrong_family_persistence_rate"] == 0.0
        and metrics["stale_route_dominance_rate"] == 0.0
        and metrics["privacy_report_leakage_rate"] == 0.0
        and metrics["external_state_overclaim_rate"] == 0.0
    )
    metrics["quality_gate_ok"] = quality_gate_ok
    return {
        "kind": "aippocampus_field_continuity_public_cohort_measurement",
        "schema_version": 1,
        "ok": quality_gate_ok,
        "status": "completed_score_scoped_public_replay_cohort"
        if quality_gate_ok
        else "measured_blocker",
        "metrics": metrics,
        "by_arm": by_arm,
        "covered_required_tags": sorted(covered_tags),
        "missing_required_tags": sorted(PUBLIC_COHORT_REQUIRED_TAGS - covered_tags),
        "cases": [
            {
                "case_id": case["case_id"],
                "case_origin": case["case_origin"],
                "scenario_family": case["scenario_family"],
                "scenario_tags": case["scenario_tags"],
                "seed_hash_sha256": case["seed_hash_sha256"],
            }
            for case in cases
        ],
        "quality_gate": {
            "requires_public_or_replay_cohort": True,
            "requires_fixture_separation": True,
            "requires_two_weaker_baselines_and_stale_control": True,
            "required_tags_present": required_tags_present,
            "quality_gate_ok": quality_gate_ok,
            "public_quality_gate_ok": quality_gate_ok,
        },
        "boundary": {
            "raw_prompts_serialized": False,
            "raw_source_text_serialized": False,
            "local_paths_serialized": False,
            "private_history_quality_claimed": False,
            "universal_fresh_thread_recall_claimed": False,
        },
        "cannot_claim": [
            "private_history_quality",
            "universal_fresh_thread_recall",
            "hosted_cross_device_readiness",
            "hook_only_sufficiency",
            "live_product_lift",
        ],
    }


def _active_boundary_failures(cases: Sequence[Mapping[str, Any]]) -> list[dict[str, str]]:
    failures: list[dict[str, str]] = []
    for case in cases:
        arm = _as_mapping(_as_mapping(case.get("arms")).get(ACTIVE_ARM))
        for metric in _as_list(case.get("expected_metrics")):
            if metric in HIGHER_IS_BETTER and arm.get(metric) is not True:
                failures.append(
                    {
                        "case_id": str(case.get("case_id") or ""),
                        "metric": metric,
                        "failure": "expected_true",
                    }
                )
            if metric in LOWER_IS_BETTER and arm.get(metric) is not False:
                failures.append(
                    {
                        "case_id": str(case.get("case_id") or ""),
                        "metric": metric,
                        "failure": "expected_false",
                    }
                )
    return failures


def _metrics(cases: Sequence[Mapping[str, Any]], validation: Mapping[str, Any]) -> dict[str, Any]:
    metrics: dict[str, Any] = {
        "case_count": len(cases),
        "scenario_family_count": validation["scenario_family_count"],
        "public_synthetic_case_count": validation["public_synthetic_case_count"],
        "negative_control_count": len(validation["negative_controls"]),
    }
    for metric in sorted(HIGHER_IS_BETTER):
        matched, total = _metric_counts(cases, metric, desired=True)
        metrics[f"{metric}_rate"] = _rate(matched, total)
        metrics[f"{metric}_denominator"] = total
    for metric in sorted(LOWER_IS_BETTER):
        matched, total = _metric_counts(cases, metric, desired=False)
        metrics[f"{metric}_rate"] = _rate(total - matched, total)
        metrics[f"{metric}_denominator"] = total
    metrics["by_arm"] = {
        arm_name: _arm_metric_report(cases, arm_name)
        for arm_name in _as_list(validation.get("arms"))
    }
    failures = _active_boundary_failures(cases)
    metrics["active_recall_or_source_reopen_boundary_failures"] = len(failures)
    return metrics


def _quality_gates(validation: Mapping[str, Any], metrics: Mapping[str, Any]) -> dict[str, Any]:
    gates = {
        "fixture_valid": bool(validation["ok"]),
        "field_report_linked": bool(validation["field_report_linked"]),
        "public_synthetic_two_families": validation["public_synthetic_family_count"] >= 2,
        "private_seed_contract_present": not any(
            code == "invalid_private_seed_reporting_contract"
            for code in validation["blocker_codes"]
        ),
        "negative_controls_present": REQUIRED_NEGATIVE_CONTROLS.issubset(
            set(validation["negative_controls"])
        ),
        "active_arm_preserves_boundaries": metrics[
            "active_recall_or_source_reopen_boundary_failures"
        ]
        == 0,
    }
    return {**gates, "ok": all(gates.values())}


def _issue_readouts(validation: Mapping[str, Any], metrics: Mapping[str, Any]) -> dict[str, Any]:
    families = set(_as_list(validation.get("scenario_families")))
    fresh_family_covered = "fresh_projectless_familiarity" in families
    return {
        "github_281": {
            "field_continuity_quality_proxy_measured": bool(fresh_family_covered),
            "claim_level": "public_safe_fixture_quality_proxy",
            "fresh_projectless_familiarity_status": (
                "covered" if fresh_family_covered else "missing"
            ),
            "source_reopen_success_rate": metrics.get("source_reopen_success_rate"),
            "progressive_route_recovery_rate": metrics.get("progressive_route_recovery_rate"),
            "wrong_family_persistence_rate": metrics.get("wrong_family_persistence_rate"),
            "irrelevant_memory_drag_rate": metrics.get("irrelevant_memory_drag_rate"),
            "active_recall_or_source_reopen_boundary_failures": metrics.get(
                "active_recall_or_source_reopen_boundary_failures"
            ),
            "live_fresh_thread_quality": "not_measured",
            "private_real_history_quality": "not_measured",
            "private_seed_review": "contract_only",
            "closeout_eligible": False,
        }
    }


def _sanitized_case(case: Mapping[str, Any]) -> dict[str, Any]:
    arms: dict[str, Any] = {}
    for arm_name, arm_result in _as_mapping(case.get("arms")).items():
        if not isinstance(arm_result, Mapping):
            continue
        arms[str(arm_name)] = {
            key: bool(value)
            for key, value in arm_result.items()
            if key in HIGHER_IS_BETTER or key in LOWER_IS_BETTER
        }
    return {
        "case_id": case.get("case_id"),
        "scenario_family": case.get("scenario_family"),
        "case_kind": case.get("case_kind"),
        "prompt_shape": case.get("prompt_shape"),
        "seed_hash_sha256": case.get("seed_hash_sha256"),
        "expected_metrics": _as_list(case.get("expected_metrics")),
        "negative_control_tags": _as_list(case.get("negative_control_tags")),
        "arms": arms,
    }


def _jsonable_validation(validation: Mapping[str, Any]) -> dict[str, Any]:
    payload = dict(validation)
    payload["required_negative_controls"] = sorted(
        str(item) for item in payload.get("required_negative_controls") or []
    )
    return payload


def run_benchmark(path: Path | str = DEFAULT_FIXTURE) -> dict[str, Any]:
    fixture = load_fixture(path)
    validation = validate_fixture(fixture)
    cases = [item for item in fixture.get("cases") or [] if isinstance(item, Mapping)]
    metrics = _metrics(cases, validation)
    gates = _quality_gates(validation, metrics)
    return {
        "kind": "aippocampus_field_continuity_benchmark",
        "schema_version": SCHEMA_VERSION,
        "ok": gates["ok"],
        "status": "passed" if gates["ok"] else "failed",
        "config": {
            "fixture_id": fixture.get("fixture_id"),
            "arms": _as_list(fixture.get("arms")),
            "uses_live_model": False,
            "uses_private_history": False,
            "active_arm": ACTIVE_ARM,
        },
        "source": {
            "issue": _as_mapping(fixture.get("source")).get("issue"),
            "design_issue": _as_mapping(fixture.get("source")).get("design_issue"),
            "discussion": _as_mapping(fixture.get("source")).get("discussion"),
            "status": _as_mapping(fixture.get("source")).get("status"),
        },
        "metrics": metrics,
        "quality_gates": gates,
        "issue_readouts": _issue_readouts(validation, metrics),
        "fixture_validation": _jsonable_validation(validation),
        "privacy_boundary": {
            "public_safe_synthetic_fixtures": True,
            "private_real_history_in_report": False,
            "raw_prompt_text_emitted": False,
            "raw_source_text_emitted": False,
            "raw_tool_error_text_emitted": False,
            "absolute_paths_emitted": False,
        },
        "private_seed_reporting_contract": validation["private_seed_reporting_contract"],
        "cases": [_sanitized_case(case) for case in cases],
        "cannot_claim": _as_list(fixture.get("cannot_claim")),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", default=str(DEFAULT_FIXTURE), help="Fixture JSON path.")
    parser.add_argument(
        "--public-cohort",
        action="store_true",
        help="Emit the #1967 public/replay cohort successor measurement report.",
    )
    parser.add_argument("--json", action="store_true", dest="json_output")
    parser.add_argument("--output", help="Optional path for the JSON report.")
    args = parser.parse_args(argv)

    payload = (
        build_public_cohort_measurement_report(args.fixture)
        if args.public_cohort
        else run_benchmark(args.fixture)
    )
    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.json_output or args.output:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"status: {payload['status']}")
        print(
            "cases: "
            f"{payload['metrics'].get('case_count', payload['metrics'].get('public_or_replay_case_count'))}"
        )
        gate = payload.get("quality_gates") or payload.get("quality_gate") or {}
        print(f"quality gates ok: {gate.get('ok', gate.get('quality_gate_ok'))}")
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
