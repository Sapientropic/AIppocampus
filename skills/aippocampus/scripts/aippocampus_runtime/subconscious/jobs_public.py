"""Public-safe projections for subconscious job runs."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Mapping

from aippocampus_runtime.core import cli_public_error_object
from aippocampus_runtime.subconscious.continuity_domain_salience import (
    public_continuity_domain_salience_summary,
)
from aippocampus_runtime.subconscious.event_salience_gate import (
    public_event_salience_summary,
)


def public_count(value: Any) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def public_float(value: Any) -> float:
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        return 0.0


def public_model_route(route: Any) -> dict[str, str]:
    if not isinstance(route, Mapping):
        return {}
    provider = str(route.get("provider") or "").strip()
    safe = "".join(char for char in provider[:48] if char.isalnum() or char in {"_", "-", "."})
    return {"provider": safe or "unknown"}


def public_cache(cache: Any) -> dict[str, Any]:
    if not isinstance(cache, Mapping):
        return {}
    result: dict[str, Any] = {"available": bool(cache.get("available"))}
    for key in ("hit_tokens", "miss_tokens"):
        if key in cache:
            result[key] = public_count(cache.get(key))
    if "hit_rate" in cache:
        result["hit_rate"] = public_float(cache.get("hit_rate"))
    return result


def public_usage(usage: Any) -> dict[str, int]:
    if not isinstance(usage, Mapping):
        return {}
    keys = ("prompt_tokens", "completion_tokens", "total_tokens")
    return {key: public_count(usage.get(key)) for key in keys if key in usage}


def public_error(error: Any) -> dict[str, str] | None:
    if not isinstance(error, Mapping):
        return None
    return cli_public_error_object(error)


def public_jobs_payload(result: Mapping[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "ok": bool(result.get("ok")),
        "job_count": public_count(result.get("job_count")),
        "successful_job_count": public_count(result.get("successful_job_count")),
        "failure_count": public_count(result.get("failure_count")),
        "partial_failure": bool(result.get("partial_failure")),
        "requested_job_count": public_count(result.get("requested_job_count")),
        "samples_per_job": public_count(result.get("samples_per_job")),
        "concurrency": public_count(result.get("concurrency")),
        "finding_count": public_count(result.get("finding_count")),
        "edge_count": public_count(result.get("edge_count")),
        "wrote": bool(result.get("wrote")),
        "dry_run": bool(result.get("dry_run")),
        "cache": public_cache(result.get("cache")),
        "usage": public_usage(result.get("usage")),
        "model_route": public_model_route(result.get("model_route")),
        "semantic_worker_available": result.get("semantic_worker_available"),
        "semantic_worker_unavailable": bool(result.get("semantic_worker_unavailable")),
        "semantic_worker_unavailable_reason": str(
            result.get("semantic_worker_unavailable_reason") or ""
        ),
        "semantic_worker_mode": str(result.get("semantic_worker_mode") or ""),
        "thinking": str(result.get("thinking") or "provider"),
        "reasoning_effort": str(result.get("reasoning_effort") or "provider"),
        "output_private_artifacts": bool(result.get("jobs_output") or result.get("edges_output")),
        "output_boundary": "job_details_are_local_private_artifacts",
    }
    if isinstance(result.get("event_salience_gate"), Mapping):
        payload["event_salience_gate"] = public_event_salience_summary(result["event_salience_gate"])
    if isinstance(result.get("continuity_domain_salience_adapter"), Mapping):
        payload["continuity_domain_salience_adapter"] = public_continuity_domain_salience_summary(
            result["continuity_domain_salience_adapter"]
        )
    if isinstance(result.get("cognitive_runtime_feedback"), Mapping):
        payload["cognitive_runtime_feedback"] = {
            "ok": bool(result["cognitive_runtime_feedback"].get("ok")),
            "row_count": len(result["cognitive_runtime_feedback"].get("rows") or []),
            "diagnostic_only": True,
        }
    if isinstance(result.get("dynamic_job_orchestration"), Mapping):
        payload["dynamic_job_orchestration"] = {
            "cycle_prevention_ok": bool(
                result["dynamic_job_orchestration"].get("cycle_prevention_ok")
            ),
            "static_depends_on_preserved": bool(
                result["dynamic_job_orchestration"].get("static_depends_on_preserved")
            ),
            "diagnostic_only": True,
        }
    if isinstance(result.get("semantic_subregion_budget"), Mapping):
        payload["semantic_subregion_budget"] = {
            "semantic_subregion_count": public_count(
                result["semantic_subregion_budget"].get("semantic_subregion_count")
            ),
            "job_circuit_count": public_count(
                result["semantic_subregion_budget"].get("job_circuit_count")
            ),
            "diagnostic_only": True,
        }
    error = public_error(result.get("error"))
    if error:
        payload["error"] = error
    return payload


def worker_specs_from_job_specs(specs: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for name, spec in specs.items():
        deterministic = bool(spec.get("runner"))
        rows.append(
            {
                "worker": name,
                "model_call_count": 0 if deterministic else 1,
                "tool_loop": not deterministic,
                "staging_writes": True,
                "strict_schema": True,
                "foreground": False,
                "timeout_ms": 120000,
            }
        )
    return rows


def feedback_inputs_from_job_results(results: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for result in results:
        job = str(result.get("job") or "unknown_job")
        ok = result.get("ok") is not False
        finding_count = public_count(result.get("finding_count"))
        if result.get("semantic_worker_unavailable"):
            outcome = "semantic_worker_unavailable"
            severity = 2
        elif not ok:
            outcome = "validation_fail"
            severity = 3
        elif finding_count == 0:
            outcome = "empty_output"
            severity = 1
        else:
            outcome = "useful_routed_candidate"
            severity = 1
        raw_usage = result.get("usage")
        usage: Mapping[str, Any] = raw_usage if isinstance(raw_usage, Mapping) else {}
        rows.append(
            {
                "job_id": job,
                "quality_outcome": outcome,
                "severity": severity,
                "cost_proxy": public_count(usage.get("total_tokens")),
                "reason_codes": [outcome],
            }
        )
    return rows
