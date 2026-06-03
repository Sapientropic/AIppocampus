#!/usr/bin/env python3
"""Field Continuity / magic-moment reproducibility contract benchmark.

This runner is a deterministic public-safe slice for GitHub #454. It turns the
#428 field-report shapes into fixture contracts, negative controls, and
claim-boundary metrics. It does not run private history, live models, or source
search; private real-history calibration must report hashes and aggregates only.
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
    "hook_only",
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
    "source_reopen_success",
    "progressive_route_recovery",
    "uncertainty_boundary_preserved",
    "exact_prompt_or_tool_failure_recovery",
    "completion_nuance_preserved",
}
LOWER_IS_BETTER = {
    "external_state_overclaim",
    "wrong_family_persistence",
    "irrelevant_memory_drag",
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
        "private_seed_reporting_contract": contract,
        "field_report_linked": not any(
            blocker["code"] == "missing_field_report_link" for blocker in blockers
        ),
    }


def _metric_counts(
    cases: Sequence[Mapping[str, Any]],
    metric: str,
    *,
    desired: bool,
) -> tuple[int, int]:
    matched = 0
    total = 0
    for case in cases:
        if metric not in _as_list(case.get("expected_metrics")):
            continue
        arm = _as_mapping(_as_mapping(case.get("arms")).get(ACTIVE_ARM))
        if metric not in arm:
            continue
        total += 1
        if bool(arm.get(metric)) is desired:
            matched += 1
    return matched, total


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
            "discussion": _as_mapping(fixture.get("source")).get("discussion"),
            "status": _as_mapping(fixture.get("source")).get("status"),
        },
        "metrics": metrics,
        "quality_gates": gates,
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
    parser.add_argument("--json", action="store_true", dest="json_output")
    parser.add_argument("--output", help="Optional path for the JSON report.")
    args = parser.parse_args(argv)

    payload = run_benchmark(args.fixture)
    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.json_output or args.output:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"status: {payload['status']}")
        print(f"cases: {payload['metrics']['case_count']}")
        print(f"quality gates ok: {payload['quality_gates']['ok']}")
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
