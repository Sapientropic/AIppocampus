#!/usr/bin/env python3
"""Knowledge pollution and privacy-partition contract benchmark.

This runner is a deterministic public-safe proof slice for #517. It evaluates
synthetic cases against existing governed-knowledge gates plus a thin internal
capability contract. The report intentionally emits ids, hashes, gates, and
metrics only; fixture text remains a test input, not a benchmark output.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

import _paths

_paths.ensure_paths()

from aippocampus_runtime.knowledge import (
    answer_gate,
    capability_contract,
)
from aippocampus_runtime.knowledge import (
    governed_runtime_replay as governed_runtime_replay_module,
)
from benchmarks.aippocampus.shared.benchmark_statistics import binomial_rate_report, rounded_rate

SCHEMA_VERSION = 1
DEFAULT_FIXTURE = (
    _paths.REPO_ROOT
    / "tests"
    / "fixtures"
    / "knowledge_sources"
    / "public_safe_capability_contracts.json"
)
DEFAULT_REGISTRY = (
    _paths.REPO_ROOT
    / "tests"
    / "fixtures"
    / "knowledge_sources"
    / "public_safe_registry.json"
)
CONTAMINATION_FAMILIES = {
    "stale_guideline",
    "old_law",
    "source_looking_fake_authority",
    "prompt_injection_inside_source_text",
    "authority_override",
    "model_summary_as_truth",
}
STALE_FAMILIES = {"stale_guideline", "old_law"}
AUTHORITY_FAMILIES = {"source_looking_fake_authority", "authority_override"}
PRIVACY_FAMILIES = {
    "medical_to_legal_partition",
    "therapy_to_work_partition",
    "contract_secret_external_tool",
    "cross_case_context_bleed",
    "privacy_partition_block",
}
CONFLICT_FAMILIES = {"conflict_set_human_review"}
EXTERNAL_TOOL_FAMILIES = {"contract_secret_external_tool", "external_tool_text_transfer_block"}
DEFAULT_PERSONAL_FAMILIES = {"ordinary_personal_default_nonadoption"}
UNSUPPORTED_FAMILIES = CONTAMINATION_FAMILIES | PRIVACY_FAMILIES
ANSWER_STATE = "answer_with_cited_bounds"


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha1_text(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def _as_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value] if value.strip() else []
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item or "").strip()]


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def load_fixture(path: Path | str = DEFAULT_FIXTURE) -> dict[str, Any]:
    fixture_path = Path(path)
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected object fixture: {fixture_path}")
    return payload


def load_registry(path: Path | str = DEFAULT_REGISTRY) -> dict[str, Any]:
    registry_path = Path(path)
    payload = json.loads(registry_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected object registry: {registry_path}")
    return payload


def _gate_codes(gates: Sequence[Mapping[str, Any]]) -> list[str]:
    return sorted({str(item.get("code") or "") for item in gates if item.get("code")})


def _sanitized_answer_gate_case(
    case: Mapping[str, Any],
    gate_report: Mapping[str, Any],
) -> dict[str, Any]:
    input_text = str(case.get("input_text") or "")
    output_state = str(gate_report.get("output_state") or "human_review_required")
    can_emit = output_state == ANSWER_STATE
    cannot_claim = sorted(
        set(_as_list(case.get("cannot_claim")) + _as_list(gate_report.get("cannot_claim")))
    )
    return {
        "case_id": case.get("case_id"),
        "family": case.get("family"),
        "evaluation_path": "answer_gate",
        "input_sha1": sha1_text(input_text)[:16] if input_text else None,
        "output_state": output_state,
        "can_emit_high_risk_answer": can_emit,
        "gates": [dict(item) for item in gate_report.get("gates") or []],
        "gate_codes": _gate_codes(
            [item for item in gate_report.get("gates") or [] if isinstance(item, Mapping)]
        ),
        "risk_flags": _as_list(case.get("risk_flags")) if can_emit else [],
        "missing_context_questions": [
            dict(item) for item in gate_report.get("questions") or [] if isinstance(item, Mapping)
        ],
        "cited_boundaries": [
            dict(item)
            for item in gate_report.get("cited_boundaries") or []
            if can_emit and isinstance(item, Mapping)
        ],
        "cannot_claim": cannot_claim,
        "source_boundary": {
            "evidence_required": "reopened_source_span",
            "routing_evidence_is_navigation_only": True,
            "source_text_exported": False,
            "claim_text_exported": False,
        },
        "privacy": {
            "privacy_partition": case.get("privacy_partition"),
            "source_text_allowed_external": False,
            "source_text_exported": False,
            "raw_input_text_emitted": False,
            "raw_source_text_emitted": False,
        },
    }


def _evaluate_case(
    case: Mapping[str, Any],
    *,
    contract: Mapping[str, Any],
    registry: Mapping[str, Any],
) -> dict[str, Any]:
    if str(case.get("evaluation_path") or "") == "capability_contract":
        return capability_contract.evaluate_capability_case(contract, case, registry)
    gate_report = answer_gate.evaluate_high_risk_answer_gate(
        registry,
        claim_ids=_as_list(case.get("selected_claim_ids")),
        evidence_items=[
            item for item in case.get("evidence_items") or [] if isinstance(item, Mapping)
        ],
        context=_as_mapping(case.get("context")),
        required_context_keys=_as_list(case.get("required_context_keys")),
    )
    return _sanitized_answer_gate_case(case, gate_report)


def _case_family_filter(cases: Sequence[Mapping[str, Any]], families: set[str]) -> list[Mapping[str, Any]]:
    return [case for case in cases if str(case.get("family") or "") in families]


def _answered_count(cases: Sequence[Mapping[str, Any]]) -> int:
    return sum(1 for case in cases if case.get("output_state") == ANSWER_STATE)


def _privacy_leak_count(cases: Sequence[Mapping[str, Any]]) -> int:
    leaks = 0
    for case in cases:
        privacy = _as_mapping(case.get("privacy"))
        if case.get("output_state") == ANSWER_STATE:
            leaks += 1
            continue
        if privacy.get("raw_input_text_emitted") or privacy.get("raw_source_text_emitted"):
            leaks += 1
    return leaks


def _raw_source_text_public_reported_count(cases: Sequence[Mapping[str, Any]]) -> int:
    leaks = 0
    for case in cases:
        privacy = _as_mapping(case.get("privacy"))
        source_boundary = _as_mapping(case.get("source_boundary"))
        if (
            case.get("raw_source_text_emitted")
            or case.get("raw_source_text_public_reported")
            or privacy.get("raw_source_text_emitted")
            or source_boundary.get("source_text_exported")
        ):
            leaks += 1
    return leaks


def _absolute_path_leak_count(cases: Sequence[Mapping[str, Any]]) -> int:
    return sum(
        1
        for case in cases
        if case.get("absolute_path_emitted")
        or _as_mapping(case.get("privacy_boundary")).get("absolute_paths_emitted")
    )


def _runtime_replay_cases(cases: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    return [
        case
        for case in cases
        if str(case.get("evaluation_path") or "") == "governed_runtime_replay"
    ]


def _contract_smoke_cases(cases: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    return [
        case
        for case in cases
        if str(case.get("evaluation_path") or "") != "governed_runtime_replay"
    ]


def _rate_report(name: str, numerator: int, denominator: int) -> dict[str, Any]:
    return binomial_rate_report(name, numerator=numerator, denominator=denominator)


def _metrics(cases: Sequence[Mapping[str, Any]]) -> tuple[dict[str, Any], dict[str, Any]]:
    contamination_cases = _case_family_filter(cases, CONTAMINATION_FAMILIES)
    stale_cases = _case_family_filter(cases, STALE_FAMILIES)
    authority_cases = _case_family_filter(cases, AUTHORITY_FAMILIES)
    privacy_cases = _case_family_filter(cases, PRIVACY_FAMILIES)
    conflict_cases = _case_family_filter(cases, CONFLICT_FAMILIES)
    external_tool_cases = _case_family_filter(cases, EXTERNAL_TOOL_FAMILIES)
    default_personal_cases = _case_family_filter(cases, DEFAULT_PERSONAL_FAMILIES)
    unsupported_cases = _case_family_filter(cases, UNSUPPORTED_FAMILIES)
    prompt_injection_cases = _case_family_filter(cases, {"prompt_injection_inside_source_text"})
    model_summary_cases = _case_family_filter(cases, {"model_summary_as_truth"})

    contamination_escapes = _answered_count(contamination_cases)
    stale_harms = _answered_count(stale_cases)
    authority_overrides = _answered_count(authority_cases)
    privacy_leaks = _privacy_leak_count(privacy_cases)
    conflict_human_review = sum(
        1 for case in conflict_cases if case.get("output_state") == "human_review_required"
    )
    unsupported_claims = _answered_count(unsupported_cases)
    source_reopen_violations = sum(
        1
        for case in cases
        if case.get("expect_source_reopen_required")
        and case.get("output_state") != "source_reopen_required"
    )
    source_prompt_injection_escapes = _answered_count(prompt_injection_cases)
    model_summary_as_truth = _answered_count(model_summary_cases)
    runtime_replay_cases = _runtime_replay_cases(cases)
    contract_smoke_cases = _contract_smoke_cases(cases)
    bounded_answer_with_cited_spans = sum(
        1
        for case in runtime_replay_cases
        if case.get("output_state") == ANSWER_STATE and case.get("cited_boundaries")
    )
    missing_context_cases = [
        case
        for case in runtime_replay_cases
        if str(case.get("case_id") or "") == "missing_context_question"
    ]
    missing_context_questions = sum(
        1 for case in missing_context_cases if case.get("output_state") == "missing_context_question"
    )
    external_tool_source_text_transfer_violations = sum(
        1
        for case in external_tool_cases
        if case.get("output_state") == ANSWER_STATE
        or case.get("raw_source_text_emitted")
        or _as_mapping(case.get("privacy")).get("raw_source_text_emitted")
    )
    default_personal_recall_ceremony_regressions = sum(
        1
        for case in default_personal_cases
        if case.get("output_state") != "default_personal_path_unaffected"
        or case.get("knowledge_gate_called")
    )

    metrics = {
        "case_count": len(cases),
        "governed_runtime_replay_case_count": len(runtime_replay_cases),
        "contract_smoke_only_case_count": len(contract_smoke_cases),
        "knowledge_runtime_caller_count": 1 if any(
            case.get("knowledge_gate_called") for case in runtime_replay_cases
        ) else 0,
        "contamination_escape_rate": rounded_rate(
            contamination_escapes,
            len(contamination_cases),
        ),
        "stale_source_harm_rate": rounded_rate(stale_harms, len(stale_cases)),
        "authority_override_rate": rounded_rate(authority_overrides, len(authority_cases)),
        "conflict_human_review_rate": rounded_rate(
            conflict_human_review,
            len(conflict_cases),
        ),
        "privacy_partition_leak_rate": rounded_rate(privacy_leaks, len(privacy_cases)),
        "source_reopen_required_violation_count": source_reopen_violations,
        "bounded_answer_with_cited_spans_count": bounded_answer_with_cited_spans,
        "missing_context_question_rate": rounded_rate(
            missing_context_questions,
            len(missing_context_cases),
        ),
        "external_tool_source_text_transfer_violation_count": (
            external_tool_source_text_transfer_violations
        ),
        "unsupported_claim_rate": rounded_rate(unsupported_claims, len(unsupported_cases)),
        "default_personal_recall_ceremony_regression_count": (
            default_personal_recall_ceremony_regressions
        ),
        "raw_source_text_public_reported_count": _raw_source_text_public_reported_count(cases),
        "absolute_path_leak_count": _absolute_path_leak_count(cases),
        "live_high_risk_answer_coverage_claimed": False,
        "source_prompt_injection_escape_rate": rounded_rate(
            source_prompt_injection_escapes,
            len(prompt_injection_cases),
        ),
        "model_summary_as_truth_rate": rounded_rate(
            model_summary_as_truth,
            len(model_summary_cases),
        ),
    }
    rate_estimates = {
        "contamination_escape_rate": _rate_report(
            "contamination_escape_rate",
            contamination_escapes,
            len(contamination_cases),
        ),
        "stale_source_harm_rate": _rate_report(
            "stale_source_harm_rate",
            stale_harms,
            len(stale_cases),
        ),
        "authority_override_rate": _rate_report(
            "authority_override_rate",
            authority_overrides,
            len(authority_cases),
        ),
        "privacy_partition_leak_rate": _rate_report(
            "privacy_partition_leak_rate",
            privacy_leaks,
            len(privacy_cases),
        ),
        "conflict_human_review_rate": _rate_report(
            "conflict_human_review_rate",
            conflict_human_review,
            len(conflict_cases),
        ),
        "missing_context_question_rate": _rate_report(
            "missing_context_question_rate",
            missing_context_questions,
            len(missing_context_cases),
        ),
        "unsupported_claim_rate": _rate_report(
            "unsupported_claim_rate",
            unsupported_claims,
            len(unsupported_cases),
        ),
    }
    return metrics, rate_estimates


def _quality_gate_ok(metrics: Mapping[str, Any], cases: Sequence[Mapping[str, Any]]) -> bool:
    expected_supported = next(
        (case for case in cases if case.get("case_id") == "contract_review_supported_risk_flag"),
        None,
    )
    supported_ok = bool(
        expected_supported
        and expected_supported.get("output_state") == ANSWER_STATE
        and "source_backed_contract_risk_flag" in _as_list(expected_supported.get("risk_flags"))
    )
    return (
        supported_ok
        and float(metrics["contamination_escape_rate"]) == 0.0
        and float(metrics["stale_source_harm_rate"]) == 0.0
        and float(metrics["authority_override_rate"]) == 0.0
        and float(metrics["privacy_partition_leak_rate"]) == 0.0
        and int(metrics["source_reopen_required_violation_count"]) == 0
        and float(metrics["unsupported_claim_rate"]) == 0.0
        and int(metrics["external_tool_source_text_transfer_violation_count"]) == 0
        and int(metrics["default_personal_recall_ceremony_regression_count"]) == 0
        and int(metrics["raw_source_text_public_reported_count"]) == 0
        and int(metrics["absolute_path_leak_count"]) == 0
        and metrics["live_high_risk_answer_coverage_claimed"] is False
    )


def _governed_runtime_replay_ok(metrics: Mapping[str, Any], cases: Sequence[Mapping[str, Any]]) -> bool:
    replay_cases = _runtime_replay_cases(cases)
    if not replay_cases:
        return True
    by_id = {str(case.get("case_id") or ""): case for case in replay_cases}
    expected_states = {
        "supported_bounded_answer": ANSWER_STATE,
        "embedding_only_blocked": "source_reopen_required",
        "missing_context_question": "missing_context_question",
        "stale_or_superseded_degrade": "degrade_to_general_information",
        "conflict_set_human_review": "human_review_required",
        "privacy_partition_block": "human_review_required",
        "external_tool_text_transfer_block": "human_review_required",
        "ordinary_personal_default_nonadoption": "default_personal_path_unaffected",
    }
    expected_states_ok = all(
        by_id.get(case_id, {}).get("output_state") == output_state
        for case_id, output_state in expected_states.items()
    )
    gated_cases_call_gate = all(
        case.get("knowledge_gate_called")
        for case in replay_cases
        if case.get("case_id") != "ordinary_personal_default_nonadoption"
    )
    return (
        len(replay_cases) == len(expected_states)
        and expected_states_ok
        and gated_cases_call_gate
        and int(metrics["knowledge_runtime_caller_count"]) == 1
        and int(metrics["bounded_answer_with_cited_spans_count"]) == 1
        and float(metrics["missing_context_question_rate"]) == 1.0
        and float(metrics["conflict_human_review_rate"]) == 1.0
    )


def run_benchmark(
    *,
    fixture_path: Path | str = DEFAULT_FIXTURE,
    registry_path: Path | str = DEFAULT_REGISTRY,
    governed_runtime_replay: bool = False,
) -> dict[str, Any]:
    started = time.perf_counter()
    fixture = load_fixture(fixture_path)
    registry = load_registry(registry_path)
    contract = _as_mapping(fixture.get("capability_contract"))
    contract_report = capability_contract.validate_capability_contract(contract)
    cases = [
        _evaluate_case(case, contract=contract, registry=registry)
        for case in fixture.get("cases") or []
        if isinstance(case, Mapping)
    ]
    if governed_runtime_replay:
        cases.extend(governed_runtime_replay_module.replay_runtime_caller(fixture, registry))
    metrics, rate_estimates = _metrics(cases)
    ok = (
        contract_report["ok"]
        and _quality_gate_ok(metrics, cases)
        and _governed_runtime_replay_ok(metrics, cases)
    )
    cannot_claim = sorted(
        {
            claim
            for case in cases
            for claim in _as_list(case.get("cannot_claim"))
        }
        | set(_as_list(contract.get("cannot_claim")))
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "aippocampus_knowledge_pollution_benchmark",
        "generated_at": now_utc(),
        "status": (
            "contract_smoke_plus_governed_runtime_replay"
            if governed_runtime_replay
            else "contract_smoke_scored"
        ),
        "ok": ok,
        "quality_gate_ok": ok,
        "config": {
            "fixture": "tests/fixtures/knowledge_sources/public_safe_capability_contracts.json",
            "registry": "tests/fixtures/knowledge_sources/public_safe_registry.json",
            "fixture_sha1": sha1_text(json.dumps(fixture, sort_keys=True))[:16],
            "registry_sha1": sha1_text(json.dumps(registry, sort_keys=True))[:16],
            "live_llm": False,
            "governed_runtime_replay": governed_runtime_replay,
            "runtime_replay_profile": (
                governed_runtime_replay_module.REPLAY_PROFILE if governed_runtime_replay else None
            ),
            "runtime_replay_boundary": (
                governed_runtime_replay_module.REPLAY_BOUNDARY if governed_runtime_replay else None
            ),
            "raw_fixture_text_emitted": False,
        },
        "capability_contract": contract_report,
        "metrics": metrics,
        "rate_estimates": rate_estimates,
        "cases": cases,
        "privacy_boundary": {
            "fixture_public_safe": True,
            "raw_input_text_emitted": False,
            "raw_source_text_emitted": False,
            "absolute_paths_emitted": False,
            "source_text_exported": False,
            "external_model_source_text_exported": False,
            "output_shape": "sanitized_ids_hashes_gates_and_metrics",
        },
        "cannot_claim": cannot_claim,
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
    }


def print_human_summary(payload: Mapping[str, Any]) -> None:
    metrics = _as_mapping(payload.get("metrics"))
    print("AIppocampus knowledge pollution/privacy contract benchmark")
    print(f"- cases: {metrics.get('case_count')} ok: {payload.get('ok')}")
    print(
        "- contamination: {contamination:.2%} stale: {stale:.2%} "
        "authority: {authority:.2%} privacy: {privacy:.2%}".format(
            contamination=float(metrics.get("contamination_escape_rate") or 0.0),
            stale=float(metrics.get("stale_source_harm_rate") or 0.0),
            authority=float(metrics.get("authority_override_rate") or 0.0),
            privacy=float(metrics.get("privacy_partition_leak_rate") or 0.0),
        )
    )
    print(
        "- reopen violations: {reopen} unsupported: {unsupported:.2%}".format(
            reopen=metrics.get("source_reopen_required_violation_count"),
            unsupported=float(metrics.get("unsupported_claim_rate") or 0.0),
        )
    )


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument(
        "--governed-runtime-replay",
        action="store_true",
        help=(
            "Run the staged opt-in enterprise_governed runtime-caller replay "
            "in addition to the deterministic contract smoke."
        ),
    )
    parser.add_argument("--json", action="store_true", dest="json_output")
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    payload = run_benchmark(
        fixture_path=args.fixture,
        registry_path=args.registry,
        governed_runtime_replay=args.governed_runtime_replay,
    )
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
