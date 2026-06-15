"""Semantic-subregion budget classification for cognitive workers."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

SCHEMA_VERSION = 1
REPORT_KIND = "aippocampus_semantic_subregion_budget_report"


def classify_worker_boundary(spec: Mapping[str, Any]) -> dict[str, Any]:
    model_calls = int(spec.get("model_call_count") or spec.get("llm_calls") or 0)
    writes = bool(spec.get("writes") or spec.get("staging_writes") or spec.get("scheduler_effects"))
    tool_loop = bool(spec.get("tool_loop") or spec.get("multiple_tool_steps"))
    cross_worker = bool(spec.get("cross_worker_coordination"))
    strict_schema = bool(spec.get("strict_schema"))
    timeout = int(spec.get("timeout_ms") or 0)
    foreground = bool(spec.get("foreground"))
    violations: list[str] = []
    if model_calls > 1:
        violations.append("multiple_model_calls")
    if writes:
        violations.append("writes_or_scheduler_effects")
    if tool_loop:
        violations.append("tool_loop")
    if cross_worker:
        violations.append("cross_worker_coordination")
    if not strict_schema:
        violations.append("missing_strict_schema")
    if foreground and timeout <= 0:
        violations.append("foreground_missing_fail_open_timeout")
    layer = "semantic_subregion" if model_calls <= 1 and not violations else "job_circuit"
    return {
        "worker": spec.get("worker") or spec.get("name") or "unknown_worker",
        "layer": layer,
        "violations": violations,
        "routing_scent_only": True,
        "model_output_is_source_truth": False,
        "foreground_fail_open_required": foreground,
    }


def build_semantic_subregion_budget_report(
    specs: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    rows = [classify_worker_boundary(spec) for spec in specs if isinstance(spec, Mapping)]
    return {
        "kind": REPORT_KIND,
        "schema_version": SCHEMA_VERSION,
        "rows": rows,
        "semantic_subregion_count": sum(1 for row in rows if row["layer"] == "semantic_subregion"),
        "job_circuit_count": sum(1 for row in rows if row["layer"] == "job_circuit"),
        "contract": {
            "semantic_subregion_one_bounded_model_call": True,
            "job_circuit_for_writes_tools_or_multi_call": True,
            "foreground_semantic_work_requires_fail_open_timeout": True,
            "output_is_routing_scent_until_source_reopen": True,
        },
    }


__all__ = ["build_semantic_subregion_budget_report", "classify_worker_boundary"]
