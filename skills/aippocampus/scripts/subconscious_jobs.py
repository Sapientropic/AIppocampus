#!/usr/bin/env python3
"""Run AIppocampus subconscious consolidation jobs.

Jobs are the durable background cognition layer. They use the same bounded,
read-only perception loop as `subconscious_agent.py`, but write job-specific
staging findings instead of directly changing formal memory.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from aippocampuslib import (
    cli_error_payload,
    cli_error_payload_from_message,
    cli_exit_code_for_error_code,
    compact_text,
    deepseek_cache_metrics_from_usage,
    now_utc,
)
from subconscious_job_circuits import JOB_SPECS, PROMPT_VERSION, job_names, jobs_initial_payload
from subconscious_job_plan import JobRunTask, plan_job_run_tasks, sample_count, worker_count
from subconscious_job_validation import (
    QUESTION_TEXT_MAX_CHARS,
    validate_findings,
)
from subconscious_jobs_config import (
    DEFAULT_CONCURRENCY,
    DEFAULT_JOBS_OUTPUT_NAME,
    DEFAULT_SAMPLES_PER_JOB,
    JobsRunConfig,
    default_jobs_output_path,
    jobs_run_config_from_args,
)
from subconscious_runtime import (
    AGENT_SYSTEM_PROMPT,
    DEFAULT_MAX_STEPS,
    DEFAULT_MIN_TOOL_STEPS,
    DEFAULT_TEMPERATURE,
    AgentState,
    ChatFn,
    add_usage,
    call_chat_json,
    effective_step_budget,
    parse_action,
    run_tool,
    source_bank_from_turns,
)
from subconscious_tool_loop import run_tool_using_loop
from subconscious_worker import (
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
    "validate_findings",
]


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


def append_job_findings(
    path: Path, findings: list[dict[str, Any]], *, model: str, batch_id: str, usage: dict[str, Any]
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as fh:
        for finding in findings:
            payload = dict(finding)
            payload["finding_kind"] = payload.pop("kind", "")
            event = {
                "schema_version": 1,
                "kind": "aippocampus_subconscious_job_finding",
                "created_at": now_utc(),
                "prompt_version": PROMPT_VERSION,
                "model": model,
                "batch_id": batch_id,
                "status": "staging",
                "source": "deepseek_subconscious_jobs",
                "usage": usage or {},
                **payload,
            }
            fh.write(json.dumps(event, ensure_ascii=False) + "\n")


def concept_findings_to_edges(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    edges: list[dict[str, Any]] = []
    for finding in findings:
        if finding.get("job") != "concept_edges":
            continue
        edges.append(
            {
                "src": finding.get("src"),
                "dst": finding.get("dst"),
                "edge_type": finding.get("edge_type") or "related",
                "confidence": finding.get("confidence"),
                "why": finding.get("why") or finding.get("summary") or finding.get("title"),
                "source_refs": finding.get("source_refs") or [],
            }
        )
    return edges


def run_one_job(
    *,
    job: str,
    registry_path: Path,
    timeline_path: Path,
    concept_graph_path: Path,
    jobs_output_path: Path,
    edges_output_path: Path,
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
    chat_fn: ChatFn = call_chat_json,
    dry_run: bool = False,
    no_write: bool = False,
    defer_writes: bool = False,
    sample_index: int = 1,
    sample_count: int = 1,
) -> dict[str, Any]:
    timeline = load_json(timeline_path)
    turns = select_timeline_turns(timeline, project=project, max_turns=max_turns)
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
            "prompt_preview": compact_text(initial_payload, 2600),
        }
    if not api_key:
        raise RuntimeError("missing DeepSeek API key; set DEEPSEEK_API_KEY or pass --api-key-env")

    system_prompt = (
        AGENT_SYSTEM_PROMPT
        + "\nFor subconscious jobs, final answers must use `findings`, not `edges`, unless the job spec says otherwise."
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": initial_payload},
    ]

    def invalid_final_feedback() -> dict[str, Any]:
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

    loop = run_tool_using_loop(
        messages=messages,
        step_budget=step_budget,
        min_tool_steps=min_tool_steps,
        chat_fn=chat_fn,
        api_key=api_key,
        model=model,
        base_url=base_url,
        max_tokens=max_tokens,
        timeout=timeout,
        temperature=temperature,
        parse_response=parse_action_for_job,
        validate_final=lambda action: validate_findings(job, action, state.source_bank),
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
    )
    findings = loop.final_items

    edges = concept_findings_to_edges(findings)
    edge_count = 0
    if not no_write and not defer_writes:
        append_job_findings(
            jobs_output_path, findings, model=model, batch_id=batch_id, usage=loop.usage_total
        )
        if edges:
            append_staging_edges(
                edges_output_path,
                edges,
                model=model,
                batch_id=batch_id,
                usage=loop.usage_total,
                prompt_version=PROMPT_VERSION,
                source="deepseek_subconscious_jobs",
            )
            edge_count = len(edges)
    return {
        "ok": True,
        "dry_run": False,
        "job": job,
        "sample_index": sample_index,
        "sample_count": sample_count,
        "model": model,
        "turn_count": len(turns),
        "finding_count": len(findings),
        "edge_count": edge_count if (not no_write and not defer_writes) else len(edges),
        "findings": findings,
        "tool_steps": loop.tool_steps,
        "final_attempts": loop.final_attempts,
        "usage": loop.usage_total,
        "cache": deepseek_cache_metrics_from_usage(loop.usage_total),
        "jobs_output": str(jobs_output_path),
        "edges_output": str(edges_output_path),
        "wrote": False if no_write or defer_writes else True,
        "deferred_write": bool(defer_writes and not no_write),
        "batch_id": batch_id,
        "effective_step_budget": step_budget,
        "temperature": temperature,
    }


def task_sample_index(task: Any) -> int:
    if isinstance(task, dict):
        return int(task.get("sample_index") or 1)
    return int(getattr(task, "sample_index", 1) or 1)


def run_tasks_in_sample_waves(
    task_specs: list[Any],
    *,
    max_workers: int,
    run_task,
    failed_task,
) -> list[tuple[int, dict[str, Any]]]:
    """Run sample 1 before same-prefix follow-up samples.

    DeepSeek's KV cache is populated by completed requests. Launching sample 1
    and sample 2 for the same prompt prefix at the exact same time often makes
    both requests cold. Wave scheduling preserves concurrency across distinct
    jobs/batches while giving each prefix one completed warm-up before its
    diversity follow-ups start.
    """

    indexed_results: list[tuple[int, dict[str, Any]]] = []
    if not task_specs:
        return indexed_results
    sample_waves = sorted({task_sample_index(task) for task in task_specs})
    for sample_index in sample_waves:
        wave = [task for task in task_specs if task_sample_index(task) == sample_index]
        wave_workers = min(max(1, int(max_workers)), max(1, len(wave)))
        if wave_workers == 1:
            for task in wave:
                try:
                    indexed_results.append(
                        (
                            int(task["index"] if isinstance(task, dict) else task.index),
                            run_task(task),
                        )
                    )
                except Exception as exc:
                    indexed_results.append(
                        (
                            int(task["index"] if isinstance(task, dict) else task.index),
                            failed_task(task, exc),
                        )
                    )
            continue
        with ThreadPoolExecutor(max_workers=wave_workers) as executor:
            futures = {executor.submit(run_task, task): task for task in wave}
            for future in as_completed(futures):
                task = futures[future]
                task_index = int(task["index"] if isinstance(task, dict) else task.index)
                try:
                    indexed_results.append((task_index, future.result()))
                except Exception as exc:
                    indexed_results.append((task_index, failed_task(task, exc)))
    return indexed_results


def run_jobs(
    *,
    jobs: list[str],
    registry_path: Path,
    timeline_path: Path,
    concept_graph_path: Path,
    jobs_output_path: Path,
    edges_output_path: Path,
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
    dry_run: bool = False,
    no_write: bool = False,
    concurrency: int = DEFAULT_CONCURRENCY,
    samples_per_job: int = DEFAULT_SAMPLES_PER_JOB,
    chat_fn: ChatFn = call_chat_json,
) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    usage_total: dict[str, Any] = {}
    sample_total = sample_count(samples_per_job)
    task_specs = plan_job_run_tasks(jobs, samples_per_job=sample_total)

    def failed_result(job: str, sample_index: int, exc: BaseException) -> dict[str, Any]:
        return {
            "ok": False,
            "dry_run": False,
            "job": job,
            "sample_index": sample_index,
            "sample_count": sample_total,
            "model": model,
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
            project=project,
            objective=objective,
            max_turns=max_turns,
            max_steps=max_steps,
            min_tool_steps=min_tool_steps,
            model=model,
            base_url=base_url,
            api_key=api_key,
            max_tokens=max_tokens,
            timeout=timeout,
            temperature=temperature,
            chat_fn=chat_fn,
            dry_run=dry_run,
            no_write=no_write,
            defer_writes=not no_write,
            sample_index=task.sample_index,
            sample_count=task.sample_count,
        )

    max_workers = worker_count(concurrency=concurrency, task_count=len(task_specs))
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
                model=model,
                batch_id=str(result.get("batch_id") or ""),
                usage=result.get("usage") or {},
            )
            edges = concept_findings_to_edges(result.get("findings") or [])
            if edges:
                append_staging_edges(
                    edges_output_path,
                    edges,
                    model=model,
                    batch_id=str(result.get("batch_id") or ""),
                    usage=result.get("usage") or {},
                    prompt_version=PROMPT_VERSION,
                    source="deepseek_subconscious_jobs",
                )
            result["wrote"] = True
            result["deferred_write"] = False
    for result in results:
        add_usage(usage_total, result.get("usage") or {})
    successful_count = sum(1 for result in results if result.get("ok") is not False)
    failure_count = sum(1 for result in results if result.get("ok") is False)
    return {
        "ok": successful_count > 0 or not task_specs,
        "jobs": results,
        "job_count": len(results),
        "successful_job_count": successful_count,
        "failure_count": failure_count,
        "partial_failure": failure_count > 0 and successful_count > 0,
        "requested_job_count": len(jobs),
        "samples_per_job": sample_total,
        "concurrency": max_workers,
        "finding_count": sum(int(result.get("finding_count") or 0) for result in results),
        "edge_count": sum(int(result.get("edge_count") or 0) for result in results),
        "usage": usage_total,
        "cache": deepseek_cache_metrics_from_usage(usage_total),
        "jobs_output": str(jobs_output_path),
        "edges_output": str(edges_output_path),
        "wrote": False if no_write or dry_run else successful_count > 0,
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
        dry_run=config.dry_run,
        no_write=config.no_write,
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
    parser.add_argument("--job", choices=["all", *JOB_SPECS.keys()], default="all")
    parser.add_argument("--project")
    parser.add_argument("--objective", default="")
    parser.add_argument("--max-turns", type=int, default=DEFAULT_MAX_TURNS)
    parser.add_argument("--max-steps", type=int, default=DEFAULT_MAX_STEPS)
    parser.add_argument("--min-tool-steps", type=int, default=DEFAULT_MIN_TOOL_STEPS)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--api-key-env", default="DEEPSEEK_API_KEY")
    parser.add_argument("--max-tokens", type=int, default=None)
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--temperature", type=float, default=DEFAULT_TEMPERATURE)
    parser.add_argument("--concurrency", type=int, default=DEFAULT_CONCURRENCY)
    parser.add_argument("--samples-per-job", type=int, default=DEFAULT_SAMPLES_PER_JOB)
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
        print(json.dumps(result, ensure_ascii=False, indent=2))
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
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"jobs: {result['job_count']}")
        print(f"findings: {result['finding_count']}")
        print(f"concept edges: {result['edge_count']}")
        print(f"jobs output: {result['jobs_output']}")
    if result.get("ok"):
        return 0
    return cli_exit_code_for_error_code(
        str((result.get("error") or {}).get("code") or "runtime_error")
    )


if __name__ == "__main__":
    raise SystemExit(main())
