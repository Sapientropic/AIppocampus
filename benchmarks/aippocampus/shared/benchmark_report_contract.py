"""Shared benchmark report fields for claim-safe audit surfaces."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

MEASUREMENT_LIVE_AGENT_OBSERVED = "live_agent_observed"
MEASUREMENT_MODEL_JUDGED = "model_judged"
MEASUREMENT_DERIVED_FROM_ARM = "derived_from_arm"
MEASUREMENT_SCRIPTED_PROXY = "scripted_proxy"
MEASUREMENT_DETERMINISTIC_CONTRACT = "deterministic_contract"

POSITIVE_SUPPORT_FIELDS = (
    "measured_result",
    "supports",
    "useful_now",
    "agent_action",
    "can_support_after_action",
    "material_limits",
)

DECISION_IMPACT_FIELDS = (
    "decision_impact",
    "decision_impact_gate_ok",
    "runtime_policy_adoption_gate_ok",
    "decision_impact_not_applicable",
)


def measurement_origin_metadata(
    *,
    measurement_origin: str,
    observed_agent_behavior: bool,
    eligible_for_runtime_policy_adoption: bool = False,
    eligible_for_public_quality_claim: bool = False,
    evidence_note: str = "",
) -> dict[str, Any]:
    return {
        "measurement_origin": str(measurement_origin),
        "observed_agent_behavior": bool(observed_agent_behavior),
        "eligible_for_runtime_policy_adoption": bool(
            eligible_for_runtime_policy_adoption
        ),
        "eligible_for_public_quality_claim": bool(eligible_for_public_quality_claim),
        "evidence_note": str(evidence_note),
    }


def proxy_aliases(metrics: Mapping[str, Any], aliases: Mapping[str, str]) -> dict[str, Any]:
    """Return explicit proxy-prefixed aliases without removing legacy keys."""

    return {
        str(alias): metrics[source]
        for source, alias in aliases.items()
        if source in metrics
    }


def _field_value(report: Mapping[str, Any], field: str) -> Any:
    value = report.get(field)
    if value not in (None, "", [], {}):
        return value
    maturity = report.get("benchmark_maturity")
    if isinstance(maturity, Mapping):
        value = maturity.get(field)
        if value not in (None, "", [], {}):
            return value
    return None


def _has_any_field(report: Mapping[str, Any], fields: tuple[str, ...]) -> bool:
    return any(_field_value(report, field) is not None for field in fields)


def benchmark_report_contract_lint(report: Mapping[str, Any]) -> dict[str, Any]:
    """Lint benchmark reports for claim-safe, action-useful machine metadata.

    The linter deliberately checks both sides of the AIppocampus contract:
    benchmark outputs need maturity/origin/decision-impact metadata so they do
    not overclaim, and they also need a positive usefulness/support projection
    so they do not teach agents that every bounded route is merely unusable.
    """

    missing_fields: list[str] = []
    if _field_value(report, "benchmark_maturity_level") is None:
        missing_fields.append("benchmark_maturity_level")
    if _field_value(report, "measurement_origin") is None:
        missing_fields.append("measurement_origin")
    if _field_value(report, "observed_agent_behavior") is None:
        missing_fields.append("observed_agent_behavior")
    if _field_value(report, "contract_gate_ok") is None:
        missing_fields.append("contract_gate_ok")
    if not _has_any_field(report, ("public_quality_gate_ok", "quality_gate_ok")):
        missing_fields.append("public_quality_gate_ok_or_quality_gate_ok")
    if not _has_any_field(report, DECISION_IMPACT_FIELDS):
        missing_fields.append("decision_impact_or_not_applicable")
    if _field_value(report, "cannot_claim") is None:
        missing_fields.append("cannot_claim")
    if _field_value(report, "privacy_boundary") is None:
        missing_fields.append("privacy_boundary")
    sample_size = (
        _field_value(report, "case_count")
        or _field_value(report, "sample_size")
        or _field_value(report, "coverage")
    )
    if sample_size is None:
        missing_fields.append("case_count_or_sample_size")

    positive_support_present = _has_any_field(report, POSITIVE_SUPPORT_FIELDS)
    cannot_claim_present = _field_value(report, "cannot_claim") is not None
    boundary_only_projection = bool(cannot_claim_present and not positive_support_present)
    findings: list[str] = []
    if missing_fields:
        findings.append("missing_contract_metadata")
    if boundary_only_projection:
        findings.append("boundary_only_projection_without_positive_support")

    synthetic_or_proxy = str(_field_value(report, "measurement_origin") or "") in {
        MEASUREMENT_DETERMINISTIC_CONTRACT,
        MEASUREMENT_SCRIPTED_PROXY,
        "synthetic_fixture",
        "deterministic_fixture",
    }
    decision_impact = str(_field_value(report, "decision_impact") or "")
    decision_gate = _field_value(report, "decision_impact_gate_ok")
    requires_review = bool(_field_value(report, "requires_human_review_before_closeout"))
    risky_decision_signal = (
        synthetic_or_proxy
        and decision_impact
        and decision_impact
        not in {"diagnostic_only", "docs_only", "not_applicable"}
        and bool(decision_gate)
        and not requires_review
    )
    if risky_decision_signal:
        findings.append("synthetic_decision_impact_without_human_review_gate")

    return {
        "ok": not findings,
        "findings": findings,
        "missing_fields": missing_fields,
        "positive_support_fields": [
            field for field in POSITIVE_SUPPORT_FIELDS if _field_value(report, field) is not None
        ],
        "positive_support_present": positive_support_present,
        "boundary_only_projection": boundary_only_projection,
        "decision_impact": decision_impact or "not_declared",
        "decision_impact_gate_ok": bool(decision_gate) if decision_gate is not None else None,
        "requires_human_review_before_closeout": requires_review,
    }


def benchmark_cli_summary(
    *,
    kind: str,
    schema_version: int | str,
    report: Mapping[str, Any],
    status: str | None = None,
    full_report_available: bool = True,
    full_report_flag: str = "--output",
    full_report_route: str | None = None,
    summary_boundary: str = "summary_only_use_output_for_sanitized_full_report",
) -> dict[str, Any]:
    maturity = report.get("benchmark_maturity")
    if not isinstance(maturity, Mapping):
        maturity = {}
    coverage = report.get("coverage")
    if not isinstance(coverage, Mapping):
        coverage = {}
    metrics = report.get("metrics")
    if not isinstance(metrics, Mapping):
        metrics = {}
    sample_size = (
        report.get("sample_size")
        or report.get("case_count")
        or coverage.get("case_count")
        or metrics.get("case_count")
    )
    return {
        "kind": kind,
        "schema_version": schema_version,
        "status": status or str(report.get("status") or "summary_only"),
        "stdout_boundary": summary_boundary,
        "ok": bool(report.get("ok")),
        "contract_gate_ok": bool(
            report.get("contract_gate_ok", report.get("ok", False))
        ),
        "quality_gate_ok": bool(report.get("quality_gate_ok", False)),
        "public_quality_gate_ok": bool(
            report.get(
                "public_quality_gate_ok",
                maturity.get("public_quality_gate_ok", report.get("quality_gate_ok", False)),
            )
        ),
        "benchmark_maturity_level": (
            report.get("benchmark_maturity_level")
            or maturity.get("benchmark_maturity_level")
            or "unknown"
        ),
        "case_count": int(report.get("case_count") or coverage.get("case_count") or 0),
        "sample_size": int(sample_size or 0),
        "cannot_claim_count": len(report.get("cannot_claim") or []),
        "cannot_claim": list(report.get("cannot_claim") or []),
        "contract_lint": benchmark_report_contract_lint(report),
        "full_report_available": bool(full_report_available),
        "full_report_flag": full_report_flag,
        "full_report_route": full_report_route or full_report_flag,
    }
