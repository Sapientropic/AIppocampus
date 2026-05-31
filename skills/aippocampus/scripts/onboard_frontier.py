#!/usr/bin/env python3
"""Optional frontier extraction boundary for Codex onboarding.

This module may call external-model jobs when explicitly requested. Keep it out
of `onboard_codex.py` so first-install local maintenance stays auditable and can
run without model credentials.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from aippocampus_runtime.subconscious.worker import default_staging_path
from aippocampuslib import compact_text
from build_concept_graph import default_concept_graph_path
from subconscious_jobs import (
    DEFAULT_BASE_URL,
    DEFAULT_MODEL,
    JOB_SPECS,
    append_job_findings,
    default_jobs_output_path,
    run_jobs,
)


def sample_findings_for_frontier(result: dict[str, Any], *, limit: int = 5) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for job_result in result.get("jobs") or []:
        if not isinstance(job_result, dict):
            continue
        for finding in job_result.get("findings") or []:
            if isinstance(finding, dict):
                findings.append(finding)
                if len(findings) >= limit:
                    break
        if len(findings) >= limit:
            break

    out: list[dict[str, Any]] = []
    for finding in findings[:limit]:
        raw_refs = finding.get("source_refs")
        refs: list[Any] = raw_refs if isinstance(raw_refs, list) else []
        row = {
            "kind": compact_text(str(finding.get("kind") or ""), 40),
            "title": compact_text(str(finding.get("title") or ""), 120),
            "confidence": finding.get("confidence"),
            "source_ref_count": len(refs),
        }
        for key, chars in (
            ("question_short", 90),
            ("question_text", 180),
            ("intent_orientation", 80),
            ("phase_context", 80),
            ("frontier_type", 40),
            ("boundary_reason", 180),
        ):
            value = compact_text(str(finding.get(key) or ""), chars)
            if value:
                row[key] = value
        out.append(row)
    return out


def frontier_maintenance_context(stats: dict[str, Any], actions: dict[str, Any]) -> str:
    refresh = (
        actions.get("refresh_current") if isinstance(actions.get("refresh_current"), dict) else {}
    )
    return (
        "Current onboarding state after maintenance: "
        f"threads={stats.get('thread_count')}, "
        f"clean_source={stats.get('clean_source_count')}, "
        f"sqlite_index={stats.get('sqlite_index_count')}, "
        f"graph_json={stats.get('graph_json_count')}, "
        f"missing_clean={stats.get('missing_clean')}, "
        f"missing_sqlite={stats.get('missing_sqlite')}, "
        f"missing_graph_json={stats.get('missing_graph_json')}, "
        f"refresh_current_ok={refresh.get('ok') if refresh else None}. "
        "Treat older source claims about missing artifacts, unrefreshed injection blocks, or undone onboarding as stale "
        "when this current state contradicts them. Stale history can still be a question_candidate, but not a current frontier_marker."
    )


def onboarding_artifacts_complete(stats: dict[str, Any]) -> bool:
    return (
        int(stats.get("thread_count") or 0) > 0
        and int(stats.get("missing_clean") or 0) == 0
        and int(stats.get("missing_sqlite") or 0) == 0
        and int(stats.get("missing_graph_json") or 0) == 0
    )


def stale_completed_frontier_reason(finding: dict[str, Any], stats: dict[str, Any]) -> str:
    if str(finding.get("kind") or "") != "frontier_marker":
        return ""
    if not onboarding_artifacts_complete(stats):
        return ""
    text = " ".join(
        str(finding.get(key) or "")
        for key in ("title", "summary", "boundary_reason", "linked_question_short")
    ).casefold()
    mentions_injection_refresh = (
        "clean-source" in text or "clean source" in text or "注入" in text or "injection" in text
    ) and (
        "refresh-registered" in text
        or "refresh" in text
        or "重写" in text
        or "未刷新" in text
        or "unrefreshed" in text
    )
    if mentions_injection_refresh:
        return "current_registry_artifacts_complete"
    return ""


def filter_frontier_result_for_current_state(
    result: dict[str, Any], stats: dict[str, Any]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    filtered = dict(result)
    stale: list[dict[str, Any]] = []
    jobs: list[dict[str, Any]] = []
    for job_result in result.get("jobs") or []:
        if not isinstance(job_result, dict):
            continue
        cloned = dict(job_result)
        kept_findings = []
        for finding in job_result.get("findings") or []:
            if not isinstance(finding, dict):
                continue
            reason = stale_completed_frontier_reason(finding, stats)
            if reason:
                stale.append(
                    {
                        "title": compact_text(str(finding.get("title") or ""), 120),
                        "reason": reason,
                    }
                )
                continue
            kept_findings.append(finding)
        cloned["findings"] = kept_findings
        cloned["finding_count"] = len(kept_findings)
        jobs.append(cloned)
    filtered["jobs"] = jobs
    filtered["raw_finding_count"] = result.get("finding_count")
    filtered["finding_count"] = sum(int(job.get("finding_count") or 0) for job in jobs)
    filtered["filtered_stale_findings"] = stale
    return filtered, stale


def write_filtered_frontier_findings(
    result: dict[str, Any], jobs_output: Path, *, model: str
) -> int:
    written = 0
    for job_result in result.get("jobs") or []:
        if not isinstance(job_result, dict):
            continue
        findings = [item for item in job_result.get("findings") or [] if isinstance(item, dict)]
        if not findings:
            continue
        append_job_findings(
            jobs_output,
            findings,
            model=model,
            batch_id=str(job_result.get("batch_id") or ""),
            usage=job_result.get("usage") or {},
        )
        written += len(findings)
    return written


def frontier_boundary_result(
    *,
    mode: str,
    registry_path: Path,
    timeline_path: Path,
    registry_dir: Path | None,
    project: str | None,
    project_scope_reason: str,
    maintenance_context: str,
    maintenance_stats: dict[str, Any],
    concurrency: int,
    samples_per_job: int,
    max_turns: int,
) -> dict[str, Any]:
    available = "question_extraction" in JOB_SPECS
    if mode == "off":
        return {
            "status": "not_run",
            "question_extraction_available": available,
            "reason": "frontier extraction is explicit because it can call an external model",
            "project_scope": project,
            "project_scope_reason": project_scope_reason,
        }
    if not available:
        return {
            "status": "unavailable",
            "question_extraction_available": False,
            "project_scope": project,
            "project_scope_reason": project_scope_reason,
        }
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        status = "skipped_missing_api_key" if mode == "auto" else "blocked_missing_api_key"
        return {
            "status": status,
            "question_extraction_available": True,
            "api_key_env": "DEEPSEEK_API_KEY",
            "project_scope": project,
            "project_scope_reason": project_scope_reason,
        }
    no_write = mode in {"auto", "smoke"}
    jobs_output = default_jobs_output_path(registry_path=registry_path)
    result = run_jobs(
        jobs=["question_extraction"],
        registry_path=registry_path,
        timeline_path=timeline_path,
        concept_graph_path=default_concept_graph_path(registry_path=registry_path),
        jobs_output_path=jobs_output,
        edges_output_path=default_staging_path(
            registry_path=registry_path, registry_dir=registry_dir
        ),
        project=project,
        objective=(
            "Extract genuine recurring questions and explicit unresolved frontier markers "
            "from Codex thread history after onboarding. Use source-backed evidence only.\n\n"
            + maintenance_context
        ),
        max_turns=max_turns,
        max_steps=4,
        min_tool_steps=1,
        model=DEFAULT_MODEL,
        base_url=DEFAULT_BASE_URL,
        api_key=api_key,
        max_tokens=1800,
        timeout=60,
        temperature=0.2,
        concurrency=concurrency,
        samples_per_job=samples_per_job,
        no_write=True,
    )
    filtered_result, stale_findings = filter_frontier_result_for_current_state(
        result, maintenance_stats
    )
    written_count = 0
    if not no_write:
        written_count = write_filtered_frontier_findings(
            filtered_result, jobs_output, model=DEFAULT_MODEL
        )
    successful_count = int(filtered_result.get("successful_job_count") or 0)
    failure_count = int(filtered_result.get("failure_count") or 0)
    finding_count = int(filtered_result.get("finding_count") or 0)
    if failure_count > 0 and successful_count <= 0:
        status = "model_failed"
    elif failure_count > 0:
        status = "model_partial_failure"
    elif finding_count <= 0:
        status = "model_no_findings"
    else:
        status = "smoke_ok" if no_write else "write_ok"
    return {
        "status": status,
        "question_extraction_available": True,
        "project_scope": project,
        "project_scope_reason": project_scope_reason,
        "wrote": written_count > 0,
        "job_count": filtered_result.get("job_count"),
        "successful_job_count": filtered_result.get("successful_job_count"),
        "failure_count": filtered_result.get("failure_count"),
        "raw_finding_count": filtered_result.get("raw_finding_count"),
        "finding_count": filtered_result.get("finding_count"),
        "filtered_stale_count": len(stale_findings),
        "sample_findings": sample_findings_for_frontier(filtered_result),
        "jobs_output": str(jobs_output),
    }
