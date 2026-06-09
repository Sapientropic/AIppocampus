#!/usr/bin/env python3
"""Run AIppocampus subconscious consolidation jobs.

Jobs are the durable background cognition layer. They use the same bounded,
read-only perception loop as `aippocampus_runtime.subconscious.agent`, but
write job-specific staging findings instead of directly changing formal memory.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Any, Mapping

from aippocampus_runtime.core import (
    cli_error_payload,
    cli_error_payload_from_message,
    cli_exit_code_for_error_code,
    cli_public_error_object,
    compact_text,
)
from aippocampus_runtime.model.client import (
    DEEPSEEK_PREFIX_CACHE_CONTRACT,
    NO_PROVIDER_CACHE_CONTRACT,
)
from aippocampus_runtime.model.routing import (
    DEFAULT_DEEPSEEK_API_KEY_ENV,
    ModelRoute,
    resolve_model_route,
    resolve_route_reasoning_effort,
    resolve_route_thinking,
    route_artifact_source,
    route_cache_metrics,
    route_payload_with_effective_values,
    route_service_name,
)
from aippocampus_runtime.subconscious.deterministic_jobs import (
    DETERMINISTIC_RUNNERS,
    run_deterministic_job,
)
from aippocampus_runtime.subconscious.event_salience_gate import (
    filter_salient_turns,
    merge_event_salience_reports,
    public_event_salience_summary,
    write_event_salience_sidecar,
)
from aippocampus_runtime.subconscious.job_circuits import (
    JOB_SPECS,
    PROMPT_VERSION,
    job_names,
    jobs_initial_payload,
)
from aippocampus_runtime.subconscious.job_plan import (
    JobRunTask,
    plan_job_run_tasks,
    run_tasks_in_sample_waves,
    sample_count,
    worker_count,
)
from aippocampus_runtime.subconscious.job_storage import (
    append_job_findings,
    concept_findings_to_edges,
)
from aippocampus_runtime.subconscious.job_validation import (
    QUESTION_TEXT_MAX_CHARS,
    validate_findings,
)
from aippocampus_runtime.subconscious.jobs_config import (
    DEFAULT_CONCURRENCY,
    DEFAULT_JOBS_OUTPUT_NAME,
    DEFAULT_SAMPLES_PER_JOB,
    JobsRunConfig,
    default_jobs_output_path,
    jobs_run_config_from_args,
)
from aippocampus_runtime.subconscious.question_diagnostics import (
    question_axis_repair_feedback,
    question_extraction_quality_diagnostics,
    should_request_question_axis_repair,
)
from aippocampus_runtime.subconscious.question_extraction_gate import (
    filter_question_extraction_turns,
)
from aippocampus_runtime.subconscious.runtime import (
    AGENT_SYSTEM_PROMPT,
    DEFAULT_MAX_STEPS,
    DEFAULT_MIN_TOOL_STEPS,
    DEFAULT_TEMPERATURE,
    TOOL_CONTRACT_VERSION,
    AgentState,
    ChatFn,
    add_usage,
    call_chat_json,
    effective_step_budget,
    parse_action,
    run_tool,
    source_bank_from_turns,
)
from aippocampus_runtime.subconscious.tool_loop import run_tool_using_loop
from aippocampus_runtime.subconscious.validation_audit import validation_audit
from aippocampus_runtime.subconscious.worker import (
    DEFAULT_BASE_URL,
    DEFAULT_MAX_TURNS,
    DEFAULT_MODEL,
    append_staging_edges,
    load_json,
    select_timeline_turns,
)

__all__ = [
    "DEFAULT_JOBS_OUTPUT_NAME",
    "JobsRunConfig",
    "QUESTION_TEXT_MAX_CHARS",
    "default_jobs_output_path",
    "job_names",
    "jobs_run_config_from_args",
    "validation_audit",
    "validate_findings",
]


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
        "thinking": str(result.get("thinking") or "provider"),
        "reasoning_effort": str(result.get("reasoning_effort") or "provider"),
        "output_private_artifacts": bool(result.get("jobs_output") or result.get("edges_output")),
        "output_boundary": "job_details_are_local_private_artifacts",
    }
    if isinstance(result.get("event_salience_gate"), Mapping):
        payload["event_salience_gate"] = public_event_salience_summary(
            result["event_salience_gate"]
        )
    error = public_error(result.get("error"))
    if error:
        payload["error"] = error
    return payload


def response_content(response: dict[str, Any]) -> str:
    choices = response.get("choices") or []
    if not choices:
        return ""
    return str(((choices[0].get("message") or {}).get("content") or "").strip())


def parse_action_for_job(response: dict[str, Any]) -> dict[str, Any]:
    try:
        return parse_action(response)
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        return {
            "action": "parse_error",
            "error": compact_text(f"{type(exc).__name__}: {exc}", 260),
            "raw_preview": compact_text(response_content(response), 1000),
        }


def run_one_job(
    *,
    job: str,
    registry_path: Path,
    timeline_path: Path,
    concept_graph_path: Path,
    jobs_output_path: Path,
    edges_output_path: Path,
    event_salience_output_path: Path | None = None,
    project: str | None,
    objective: str,
    max_turns: int,
    max_steps: int,
    min_tool_steps: int,
    model: str,
    base_url: str,
    api_key: str | None,
    max_tokens: int | None,
    timeout: int,
    temperature: float,
    api_key_env: str = DEFAULT_DEEPSEEK_API_KEY_ENV,
    model_route: str | None = None,
    route: ModelRoute | None = None,
    chat_fn: ChatFn = call_chat_json,
    dry_run: bool = False,
    no_write: bool = False,
    defer_writes: bool = False,
    event_salience_gate: bool = False,
    sample_index: int = 1,
    sample_count: int = 1,
) -> dict[str, Any]:
    if JOB_SPECS.get(job, {}).get("runner") in DETERMINISTIC_RUNNERS:
        raise ValueError(f"{job} is a deterministic follow-up; run it through run_jobs")
    timeline = load_json(timeline_path)
    turns = select_timeline_turns(timeline, project=project, max_turns=max_turns)
    event_salience_report: dict[str, Any] = {}
    if event_salience_gate:
        turns, event_salience_report = filter_salient_turns(turns)
        if event_salience_output_path and not dry_run and not no_write and not defer_writes:
            write_event_salience_sidecar(
                event_salience_output_path,
                event_salience_report.get("sidecar_rows") or [],
            )
    question_extraction_gate: dict[str, Any] = {}
    if job == "question_extraction":
        turns, question_extraction_gate = filter_question_extraction_turns(turns)
    state = AgentState(source_bank=source_bank_from_turns(turns))
    step_budget = effective_step_budget(max_steps)
    batch_id = f"subconscious-job-{job}-{time.time_ns()}-{os.getpid()}-{sample_index}"
    sample_objective = objective
    if sample_count > 1:
        sample_objective = (
            f"{objective}\n\nDiversity sample {sample_index}/{sample_count}: "
            "use a distinct angle, search path, or cue framing while staying source-backed."
        ).strip()
    initial_payload = jobs_initial_payload(
        job, sample_objective, turns, step_budget, min_tool_steps
    )
    if dry_run:
        return {
            "ok": True,
            "dry_run": True,
            "job": job,
            "sample_index": sample_index,
            "sample_count": sample_count,
            "turn_count": len(turns),
            "effective_step_budget": step_budget,
            "tool_contract_version": TOOL_CONTRACT_VERSION,
            "prompt_preview": compact_text(initial_payload, 2600),
            "question_extraction_gate": question_extraction_gate,
            "event_salience_gate": event_salience_report,
            "event_salience_output": str(event_salience_output_path)
            if event_salience_output_path
            else "",
        }
    route = route or resolve_model_route(
        model_route,
        explicit_model=model if model != DEFAULT_MODEL and not model_route else None,
        explicit_base_url=base_url if base_url != DEFAULT_BASE_URL and not model_route else None,
        explicit_api_key_env=(
            api_key_env
            if api_key_env != DEFAULT_DEEPSEEK_API_KEY_ENV and not model_route
            else None
        ),
    )
    capabilities = route.capabilities
    resolved_model = route.model if model == DEFAULT_MODEL else model
    resolved_base_url = route.base_url if base_url == DEFAULT_BASE_URL else base_url
    resolved_api_key_env = (
        route.api_key_env
        if api_key_env == DEFAULT_DEEPSEEK_API_KEY_ENV
        else api_key_env
    )
    route_payload = route_payload_with_effective_values(
        route,
        model=resolved_model,
        base_url=resolved_base_url,
        api_key_env=resolved_api_key_env,
    )
    artifact_source = route_artifact_source(route, "subconscious_jobs")
    key_value = api_key or os.environ.get(resolved_api_key_env)
    if not key_value:
        raise RuntimeError(
            f"missing {route_service_name(route)} key; "
            f"set {resolved_api_key_env} or pass --api-key-env"
        )
    resolved_thinking = resolve_route_thinking(route)
    resolved_reasoning_effort = resolve_route_reasoning_effort(
        route,
        thinking=resolved_thinking,
    )

    system_prompt = (
        AGENT_SYSTEM_PROMPT
        + "\nFor subconscious jobs, final answers must use `findings`, not `edges`, unless the job spec says otherwise."
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": initial_payload},
    ]
    axis_repair_feedback: dict[str, Any] | None = None
    axis_repair_requested = False

    def invalid_final_feedback() -> dict[str, Any]:
        if axis_repair_feedback:
            return axis_repair_feedback
        payload: dict[str, Any] = {
            "error": "No valid source-backed findings survived validation.",
            "instruction": "Use refs from available_refs. Return action=final with findings, or empty findings only when no durable finding exists.",
            "available_refs": list(state.source_bank.keys())[:32],
        }
        if job == "semantic_scope_labeling":
            payload["semantic_scope_labeling_requirements"] = {
                "message_id": "Target exactly one clean-source message_id from a source_ref.",
                "scope_labels": "Use only canonical labels and omit weak labels.",
                "label_evidence": "Required for every scope_label, with a short source-grounded reason and confidence.",
                "source_refs": "Must include a ref that resolves to the same message_id.",
            }
        return payload

    def repair_feedback() -> dict[str, Any]:
        payload: dict[str, Any] = {
            "repair": "final_only",
            "instruction": "Use existing tool observations and available refs to produce source-backed findings. Do not call tools. Return action=final.",
            "available_refs": list(state.source_bank.keys())[:40],
        }
        if job == "semantic_scope_labeling":
            # Semantic sidecars are source-review-sensitive. Keep the repair path
            # strict so old no-evidence model habits cannot refill staging with
            # labels that the materializer must later reject.
            payload["semantic_scope_labeling_requirements"] = {
                "message_id": "Target exactly one clean-source message_id from a source_ref.",
                "label_evidence": "Every applied label needs its own source-grounded reason and confidence.",
                "omit_if_uncertain": "If a label cannot be defended from the source message itself, omit it.",
            }
        return payload

    def validate_final_for_job(action: dict[str, Any]) -> list[dict[str, Any]]:
        nonlocal axis_repair_feedback, axis_repair_requested
        axis_repair_feedback = None
        candidate_items = validate_findings(job, action, state.source_bank)
        if job == "question_extraction" and not axis_repair_requested:
            diagnostics = question_extraction_quality_diagnostics([action], candidate_items, action)
            if should_request_question_axis_repair(diagnostics):
                axis_repair_requested = True
                axis_repair_feedback = question_axis_repair_feedback(diagnostics)
                return []
        return candidate_items

    loop = run_tool_using_loop(
        messages=messages,
        step_budget=step_budget,
        min_tool_steps=min_tool_steps,
        chat_fn=chat_fn,
        api_key=str(key_value),
        model=resolved_model,
        base_url=resolved_base_url,
        max_tokens=max_tokens,
        timeout=timeout,
        temperature=temperature,
        parse_response=parse_action_for_job,
        validate_final=validate_final_for_job,
        run_tool_action=lambda tool_name, tool_args: run_tool(
            tool_name,
            tool_args,
            registry_path=registry_path,
            project=project,
            concept_graph_path=concept_graph_path,
            staging_path=edges_output_path,
            state=state,
        ),
        min_tool_feedback=lambda: {"error": "Call at least one read-only tool before finalizing."},
        invalid_final_feedback=invalid_final_feedback,
        repair_feedback=repair_feedback,
        parse_error_feedback=lambda action: {
            "error": "Previous response was not valid JSON.",
            "details": action.get("error"),
            "instruction": "Return exactly one JSON object with action=tool or action=final. Do not wrap it in Markdown.",
            "available_refs": list(state.source_bank.keys())[:32],
        },
        tool_result_instruction=(
            "Next: call another tool if needed; otherwise return action=final with source-backed findings. "
            "Do not return empty findings when observations contain useful durable structure."
        ),
        chat_kwargs={
            "service_name": route_service_name(route),
            "response_format_json": bool(
                capabilities.supports_json_response if capabilities else True
            ),
            "cache_contract": (
                DEEPSEEK_PREFIX_CACHE_CONTRACT
                if (capabilities and capabilities.cache_metrics_kind == "deepseek_prefix")
                else NO_PROVIDER_CACHE_CONTRACT
            ),
            "thinking": resolved_thinking,
            "reasoning_effort": resolved_reasoning_effort,
        }
        if chat_fn is call_chat_json
        else None,
    )
    findings = loop.final_items
    validation_diagnostics = {
        "accepted_final": validation_audit(job, loop.final_action, state.source_bank),
        "final_attempts": [
            validation_audit(job, attempt, state.source_bank)
            for attempt in loop.final_attempts
        ],
    }
    quality_diagnostics = (
        question_extraction_quality_diagnostics(loop.final_attempts, findings, loop.final_action)
        if job == "question_extraction"
        else {}
    )

    edges = concept_findings_to_edges(findings)
    edge_count = 0
    if not no_write and not defer_writes:
        append_job_findings(
            jobs_output_path,
            findings,
            model=resolved_model,
            batch_id=batch_id,
            usage=loop.usage_total,
            source=artifact_source,
            model_route=route_payload,
        )
        if edges:
            append_staging_edges(
                edges_output_path,
                edges,
                model=resolved_model,
                batch_id=batch_id,
                usage=loop.usage_total,
                prompt_version=PROMPT_VERSION,
                source=artifact_source,
                model_route=route_payload,
            )
            edge_count = len(edges)
    result = {
        "ok": True,
        "dry_run": False,
        "job": job,
        "sample_index": sample_index,
        "sample_count": sample_count,
        "model": resolved_model,
        "model_route": route_payload,
        "turn_count": len(turns),
        "finding_count": len(findings),
        "edge_count": edge_count if (not no_write and not defer_writes) else len(edges),
        "findings": findings,
        "tool_steps": loop.tool_steps,
        "final_attempts": loop.final_attempts,
        "usage": loop.usage_total,
        "cache": route_cache_metrics(route, loop.usage_total),
        "jobs_output": str(jobs_output_path),
        "edges_output": str(edges_output_path),
        "wrote": False if no_write or defer_writes else True,
        "deferred_write": bool(defer_writes and not no_write),
        "batch_id": batch_id,
        "effective_step_budget": step_budget,
        "timeout": timeout,
        "temperature": temperature,
        "thinking": resolved_thinking,
        "reasoning_effort": resolved_reasoning_effort,
        "tool_contract_version": TOOL_CONTRACT_VERSION,
        "validation_diagnostics": validation_diagnostics,
        "question_extraction_gate": question_extraction_gate,
        "event_salience_gate": event_salience_report,
        "event_salience_output": str(event_salience_output_path)
        if event_salience_output_path
        else "",
    }
    if quality_diagnostics:
        result["quality_diagnostics"] = quality_diagnostics
    return result


def run_jobs(
    *,
    jobs: list[str],
    registry_path: Path,
    timeline_path: Path,
    concept_graph_path: Path,
    jobs_output_path: Path,
    edges_output_path: Path,
    event_salience_output_path: Path | None = None,
    project: str | None,
    objective: str,
    max_turns: int,
    max_steps: int,
    min_tool_steps: int,
    model: str,
    base_url: str,
    api_key: str | None,
    max_tokens: int | None,
    timeout: int,
    temperature: float,
    api_key_env: str = DEFAULT_DEEPSEEK_API_KEY_ENV,
    model_route: str | None = None,
    dry_run: bool = False,
    no_write: bool = False,
    event_salience_gate: bool = False,
    concurrency: int = DEFAULT_CONCURRENCY,
    samples_per_job: int = DEFAULT_SAMPLES_PER_JOB,
    chat_fn: ChatFn = call_chat_json,
) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    usage_total: dict[str, Any] = {}
    sample_total = sample_count(samples_per_job)
    deterministic_jobs = [
        job
        for job in jobs
        if JOB_SPECS.get(job, {}).get("runner") in DETERMINISTIC_RUNNERS
    ]
    semantic_jobs = [
        job
        for job in jobs
        if JOB_SPECS.get(job, {}).get("runner") not in DETERMINISTIC_RUNNERS
    ]
    task_specs = plan_job_run_tasks(semantic_jobs, samples_per_job=sample_total)
    route = resolve_model_route(
        model_route,
        explicit_model=model if model != DEFAULT_MODEL and not model_route else None,
        explicit_base_url=base_url if base_url != DEFAULT_BASE_URL and not model_route else None,
        explicit_api_key_env=(
            api_key_env
            if api_key_env != DEFAULT_DEEPSEEK_API_KEY_ENV and not model_route
            else None
        ),
    )
    capabilities = route.capabilities
    resolved_model = route.model if model == DEFAULT_MODEL else model
    resolved_base_url = route.base_url if base_url == DEFAULT_BASE_URL else base_url
    resolved_api_key_env = (
        route.api_key_env
        if api_key_env == DEFAULT_DEEPSEEK_API_KEY_ENV
        else api_key_env
    )
    route_payload = route_payload_with_effective_values(
        route,
        model=resolved_model,
        base_url=resolved_base_url,
        api_key_env=resolved_api_key_env,
    )
    key_value = api_key or os.environ.get(resolved_api_key_env)
    effective_concurrency = int(concurrency)
    if route.provider != "deepseek" and capabilities:
        effective_concurrency = min(effective_concurrency, capabilities.safe_default_concurrency)

    def failed_result(job: str, sample_index: int, exc: BaseException) -> dict[str, Any]:
        return {
            "ok": False,
            "dry_run": False,
            "job": job,
            "sample_index": sample_index,
            "sample_count": sample_total,
            "model": resolved_model,
            "model_route": route_payload,
            "finding_count": 0,
            "edge_count": 0,
            "findings": [],
            "tool_steps": [],
            "final_attempts": [],
            "usage": {},
            "jobs_output": str(jobs_output_path),
            "edges_output": str(edges_output_path),
            "wrote": False,
            "deferred_write": False,
            "error": compact_text(f"{type(exc).__name__}: {exc}", 500),
        }

    def run_task(task: JobRunTask) -> dict[str, Any]:
        return run_one_job(
            job=task.job,
            registry_path=registry_path,
            timeline_path=timeline_path,
            concept_graph_path=concept_graph_path,
            jobs_output_path=jobs_output_path,
            edges_output_path=edges_output_path,
            event_salience_output_path=event_salience_output_path,
            project=project,
            objective=objective,
            max_turns=max_turns,
            max_steps=max_steps,
            min_tool_steps=min_tool_steps,
            model=resolved_model,
            base_url=resolved_base_url,
            api_key=key_value,
            max_tokens=max_tokens,
            timeout=timeout,
            temperature=temperature,
            api_key_env=resolved_api_key_env,
            model_route=model_route,
            route=route,
            chat_fn=chat_fn,
            dry_run=dry_run,
            no_write=no_write,
            defer_writes=not no_write,
            event_salience_gate=event_salience_gate,
            sample_index=task.sample_index,
            sample_count=task.sample_count,
        )

    max_workers = worker_count(concurrency=effective_concurrency, task_count=len(task_specs))
    indexed_results = run_tasks_in_sample_waves(
        task_specs,
        max_workers=max_workers,
        run_task=run_task,
        failed_task=lambda task, exc: failed_result(task.job, task.sample_index, exc),
    )
    indexed_results.sort(key=lambda item: item[0])
    results = [result for _, result in indexed_results]

    if not no_write and not dry_run:
        # DeepSeek calls can run concurrently, but staging files are append-only
        # shared artifacts. Serialize writes here so multi-sample runs do not
        # interleave JSONL rows or edge batches under parallel workers.
        for result in results:
            if result.get("ok") is False:
                continue
            append_job_findings(
                jobs_output_path,
                result.get("findings") or [],
                model=resolved_model,
                batch_id=str(result.get("batch_id") or ""),
                usage=result.get("usage") or {},
                source=route_artifact_source(route, "subconscious_jobs"),
                model_route=route_payload,
            )
            edges = concept_findings_to_edges(result.get("findings") or [])
            if edges:
                append_staging_edges(
                    edges_output_path,
                    edges,
                    model=resolved_model,
                    batch_id=str(result.get("batch_id") or ""),
                    usage=result.get("usage") or {},
                    prompt_version=PROMPT_VERSION,
                    source=route_artifact_source(route, "subconscious_jobs"),
                    model_route=route_payload,
                )
            result["wrote"] = True
            result["deferred_write"] = False
        if event_salience_gate and event_salience_output_path:
            aggregate_salience = merge_event_salience_reports(
                result.get("event_salience_gate") or {} for result in results
            )
            write_event_salience_sidecar(
                event_salience_output_path,
                aggregate_salience.get("sidecar_rows") or [],
            )
    for deterministic_job in deterministic_jobs:
        try:
            results.append(
                run_deterministic_job(
                    deterministic_job,
                    registry_path=registry_path,
                    concept_graph_path=concept_graph_path,
                    jobs_output_path=jobs_output_path,
                    edges_output_path=edges_output_path,
                    no_write=no_write,
                    dry_run=dry_run,
                )
            )
        except Exception as exc:
            results.append(failed_result(deterministic_job, 1, exc))
    for result in results:
        add_usage(usage_total, result.get("usage") or {})
    successful_count = sum(1 for result in results if result.get("ok") is not False)
    failure_count = sum(1 for result in results if result.get("ok") is False)
    semantic_job_set = set(semantic_jobs)
    semantic_successful_count = sum(
        1
        for result in results
        if result.get("ok") is not False and str(result.get("job") or "") in semantic_job_set
    )
    overall_ok = (
        semantic_successful_count > 0
        if semantic_jobs
        else successful_count > 0 or (not task_specs and not deterministic_jobs)
    )
    resolved_thinking = next(
        (result.get("thinking") for result in results if result.get("thinking")),
        None,
    )
    resolved_reasoning_effort = next(
        (result.get("reasoning_effort") for result in results if result.get("reasoning_effort")),
        None,
    )
    event_salience_report = (
        merge_event_salience_reports(result.get("event_salience_gate") or {} for result in results)
        if event_salience_gate
        else {}
    )
    return {
        "ok": overall_ok,
        "jobs": results,
        "job_count": len(results),
        "successful_job_count": successful_count,
        "failure_count": failure_count,
        "partial_failure": failure_count > 0 and successful_count > 0,
        "requested_job_count": len(jobs),
        "samples_per_job": sample_total,
        "concurrency": max_workers,
        "timeout": timeout,
        "temperature": temperature,
        "thinking": resolved_thinking,
        "reasoning_effort": resolved_reasoning_effort,
        "model_route": route_payload,
        "finding_count": sum(int(result.get("finding_count") or 0) for result in results),
        "edge_count": sum(int(result.get("edge_count") or 0) for result in results),
        "usage": usage_total,
        "cache": route_cache_metrics(route, usage_total),
        "jobs_output": str(jobs_output_path),
        "edges_output": str(edges_output_path),
        "dry_run": bool(dry_run),
        "event_salience_output": str(event_salience_output_path)
        if event_salience_output_path
        else "",
        "event_salience_gate": event_salience_report,
        "quality_diagnostics": [
            result["quality_diagnostics"]
            for result in results
            if isinstance(result.get("quality_diagnostics"), dict)
            and result.get("quality_diagnostics")
        ],
        "wrote": False if no_write or dry_run else any(bool(result.get("wrote")) for result in results),
    }


def run_jobs_with_config(
    config: JobsRunConfig, *, chat_fn: ChatFn = call_chat_json
) -> dict[str, Any]:
    return run_jobs(
        jobs=config.jobs,
        registry_path=config.registry_path,
        timeline_path=config.timeline_path,
        concept_graph_path=config.concept_graph_path,
        jobs_output_path=config.jobs_output_path,
        edges_output_path=config.edges_output_path,
        event_salience_output_path=config.event_salience_output_path,
        project=config.project,
        objective=config.objective,
        max_turns=config.max_turns,
        max_steps=config.max_steps,
        min_tool_steps=config.min_tool_steps,
        model=config.model,
        base_url=config.base_url,
        api_key=config.api_key,
        max_tokens=config.max_tokens,
        timeout=config.timeout,
        temperature=config.temperature,
        api_key_env=config.api_key_env,
        model_route=config.model_route,
        dry_run=config.dry_run,
        no_write=config.no_write,
        event_salience_gate=config.event_salience_gate,
        concurrency=config.concurrency,
        samples_per_job=config.samples_per_job,
        chat_fn=chat_fn,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry")
    parser.add_argument("--registry-dir")
    parser.add_argument("--timeline")
    parser.add_argument("--concept-graph")
    parser.add_argument("--jobs-output")
    parser.add_argument("--edges-output")
    parser.add_argument("--event-salience-output")
    parser.add_argument("--job", choices=["all", *JOB_SPECS.keys()], default="all")
    parser.add_argument("--project")
    parser.add_argument("--objective", default="")
    parser.add_argument("--max-turns", type=int, default=DEFAULT_MAX_TURNS)
    parser.add_argument("--max-steps", type=int, default=DEFAULT_MAX_STEPS)
    parser.add_argument("--min-tool-steps", type=int, default=DEFAULT_MIN_TOOL_STEPS)
    parser.add_argument("--model-route")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--api-key-env", default=DEFAULT_DEEPSEEK_API_KEY_ENV)
    parser.add_argument("--max-tokens", type=int, default=None)
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--temperature", type=float, default=DEFAULT_TEMPERATURE)
    parser.add_argument("--concurrency", type=int, default=DEFAULT_CONCURRENCY)
    parser.add_argument("--samples-per-job", type=int, default=DEFAULT_SAMPLES_PER_JOB)
    parser.add_argument("--event-salience-gate", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args()

    try:
        result = run_jobs_with_config(jobs_run_config_from_args(args))
    except Exception as exc:
        if not args.json_output:
            raise
        result = cli_error_payload(exc)
        print(json.dumps(public_jobs_payload(result), ensure_ascii=False, indent=2))
        return cli_exit_code_for_error_code(result["error"]["code"])
    if not result.get("ok") and not result.get("error"):
        first_error = next(
            (
                str(item.get("error") or "")
                for item in result.get("jobs") or []
                if item.get("error")
            ),
            "",
        )
        if first_error:
            result["error"] = cli_error_payload_from_message(first_error)["error"]
    if args.json_output:
        print(json.dumps(public_jobs_payload(result), ensure_ascii=False, indent=2))
    else:
        print(f"jobs: {result['job_count']}")
        print(f"findings: {result['finding_count']}")
        print(f"concept edges: {result['edge_count']}")
        if result.get("jobs_output"):
            print("jobs output: <local-private-artifact>")
    if result.get("ok"):
        return 0
    return cli_exit_code_for_error_code(
        str((result.get("error") or {}).get("code") or "runtime_error")
    )


if __name__ == "__main__":
    raise SystemExit(main())
