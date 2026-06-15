"""Suite-level status field helpers for benchmark reports."""

from __future__ import annotations

from typing import Any

CONTRACT_GATE_MEANING = (
    "bounded suite report captured; does not imply benchmark contract "
    "linter or public quality gate passed"
)


def suite_machine_summary(
    *,
    runner_ok: bool,
    contract_gate_ok: bool,
    benchmark_contract_linter_ok: bool,
    public_quality_gate_ok: bool,
    status: str,
) -> dict[str, Any]:
    """Machine-readable reading guide for suite-level status fields."""
    if public_quality_gate_ok:
        safe_interpretation = "runner_and_public_quality_gates_passed"
        agent_action = "may_use_as_public_quality_support_with_profile_boundaries"
    elif runner_ok:
        safe_interpretation = "runner_report_available_but_not_public_quality_support"
        agent_action = "read benchmark_contract_lint and cannot_claim before citing"
    else:
        safe_interpretation = "runner_baseline_not_captured"
        agent_action = "treat_as_failed_run_and_rerun_or_debug"
    return {
        "status": status,
        "safe_interpretation": safe_interpretation,
        "agent_action": agent_action,
        "runner_ok": bool(runner_ok),
        "contract_gate_ok": bool(contract_gate_ok),
        "benchmark_contract_linter_ok": bool(benchmark_contract_linter_ok),
        "public_quality_gate_ok": bool(public_quality_gate_ok),
        "linter_required_for_public_quality_gate": True,
        "ok_field_meaning": "runner_ok_baseline_report_available",
        "contract_gate_ok_meaning": CONTRACT_GATE_MEANING,
        "claim_quality_ok": bool(public_quality_gate_ok),
    }


def suite_status_fields(
    *,
    runner_ok: bool,
    contract_gate_ok: bool,
    benchmark_contract_linter_ok: bool,
    public_quality_gate_ok: bool,
    status: str,
) -> dict[str, Any]:
    return {
        "ok": runner_ok,
        "runner_ok": runner_ok,
        "contract_gate_ok": contract_gate_ok,
        "contract_gate_status": {
            "ok": contract_gate_ok,
            "meaning": CONTRACT_GATE_MEANING,
            "benchmark_contract_linter_ok": bool(benchmark_contract_linter_ok),
            "linter_required_for_public_quality_gate": True,
        },
        "quality_gate_ok": public_quality_gate_ok,
        "public_quality_gate_ok": public_quality_gate_ok,
        "claim_quality_ok": public_quality_gate_ok,
        "linter_required_for_public_quality_gate": True,
        "machine_summary": suite_machine_summary(
            runner_ok=runner_ok,
            contract_gate_ok=contract_gate_ok,
            benchmark_contract_linter_ok=benchmark_contract_linter_ok,
            public_quality_gate_ok=public_quality_gate_ok,
            status=status,
        ),
    }
