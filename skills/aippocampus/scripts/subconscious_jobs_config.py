#!/usr/bin/env python3
"""Configuration and default paths for subconscious job runs."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from build_concept_graph import default_concept_graph_path
from deepseek_model_routing import DEFAULT_DEEPSEEK_API_KEY_ENV, resolve_model_route
from registry import registry_paths
from subconscious_job_circuits import job_names
from subconscious_worker import (
    DEFAULT_BASE_URL,
    DEFAULT_MODEL,
    default_project_timeline_path,
    default_staging_path,
)

DEFAULT_JOBS_OUTPUT_NAME = "subconscious_jobs.jsonl"
DEFAULT_CONCURRENCY = int(os.environ.get("AIPPOCAMPUS_SUBCONSCIOUS_CONCURRENCY", "4"))
DEFAULT_SAMPLES_PER_JOB = int(os.environ.get("AIPPOCAMPUS_SUBCONSCIOUS_SAMPLES_PER_JOB", "2"))


@dataclass(frozen=True)
class JobsRunConfig:
    jobs: list[str]
    registry_path: Path
    timeline_path: Path
    concept_graph_path: Path
    jobs_output_path: Path
    edges_output_path: Path
    project: str | None
    objective: str
    max_turns: int
    max_steps: int
    min_tool_steps: int
    model: str
    base_url: str
    api_key: str | None
    max_tokens: int | None
    timeout: int
    temperature: float
    api_key_env: str = DEFAULT_DEEPSEEK_API_KEY_ENV
    model_route: str | None = None
    concurrency: int = DEFAULT_CONCURRENCY
    samples_per_job: int = DEFAULT_SAMPLES_PER_JOB
    dry_run: bool = False
    no_write: bool = False


def default_jobs_output_path(
    registry_path: Path | None = None, registry_dir: Path | None = None
) -> Path:
    if registry_path:
        return registry_path.resolve().parent / DEFAULT_JOBS_OUTPUT_NAME
    json_path, _ = registry_paths(registry_dir)
    return json_path.resolve().parent / DEFAULT_JOBS_OUTPUT_NAME


def jobs_run_config_from_args(args: Any) -> JobsRunConfig:
    model_route = getattr(args, "model_route", None)
    arg_api_key_env = str(getattr(args, "api_key_env", DEFAULT_DEEPSEEK_API_KEY_ENV) or DEFAULT_DEEPSEEK_API_KEY_ENV)
    model = str(getattr(args, "model", DEFAULT_MODEL) or DEFAULT_MODEL)
    base_url = str(getattr(args, "base_url", DEFAULT_BASE_URL) or DEFAULT_BASE_URL)
    route = resolve_model_route(
        model_route,
        explicit_model=model if model != DEFAULT_MODEL and not model_route else None,
        explicit_base_url=base_url if base_url != DEFAULT_BASE_URL and not model_route else None,
        explicit_api_key_env=(
            arg_api_key_env
            if arg_api_key_env != DEFAULT_DEEPSEEK_API_KEY_ENV and not model_route
            else None
        ),
    )
    api_key_env = (
        route.api_key_env
        if arg_api_key_env == DEFAULT_DEEPSEEK_API_KEY_ENV
        else arg_api_key_env
    )
    registry_path = (
        Path(args.registry).resolve()
        if args.registry
        else registry_paths(Path(args.registry_dir).resolve() if args.registry_dir else None)[0]
    )
    timeline_path = (
        Path(args.timeline).resolve()
        if args.timeline
        else default_project_timeline_path(registry_path=registry_path)
    )
    concept_graph_path = (
        Path(args.concept_graph).resolve()
        if args.concept_graph
        else default_concept_graph_path(registry_path=registry_path)
    )
    jobs_output_path = (
        Path(args.jobs_output).resolve()
        if args.jobs_output
        else default_jobs_output_path(registry_path=registry_path)
    )
    edges_output_path = (
        Path(args.edges_output).resolve()
        if args.edges_output
        else default_staging_path(registry_path=registry_path)
    )
    return JobsRunConfig(
        jobs=job_names(args.job),
        registry_path=registry_path,
        timeline_path=timeline_path,
        concept_graph_path=concept_graph_path,
        jobs_output_path=jobs_output_path,
        edges_output_path=edges_output_path,
        project=args.project,
        objective=args.objective,
        max_turns=args.max_turns,
        max_steps=args.max_steps,
        min_tool_steps=args.min_tool_steps,
        model=model,
        base_url=base_url,
        api_key=os.environ.get(api_key_env),
        api_key_env=api_key_env,
        model_route=model_route,
        max_tokens=args.max_tokens,
        timeout=args.timeout,
        temperature=args.temperature,
        concurrency=args.concurrency,
        samples_per_job=args.samples_per_job,
        dry_run=args.dry_run,
        no_write=args.no_write,
    )
