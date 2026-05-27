#!/usr/bin/env python3
"""Agent-native first-install onboarding for local Codex thread memory.

This command intentionally wraps the old manual sequence:

1. scan local Codex sessions,
2. register missing rollouts into the global registry,
3. build clean-source and SQLite/RAG-lite indexes,
4. repair already-registered rows that are missing artifacts,
5. refresh hook-safe navigation sidecars.

It emits one compact envelope so agents can plan, execute, and recover without
hand-assembling several scripts. Generated artifacts remain private under the
global registry by default; nothing here writes repository files.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

from aippocampuslib import compact_text
from build_cognitive_map import build_from_files as build_cognitive_map_from_files
from build_cognitive_map import default_cognitive_map_path
from build_project_timeline import build_project_timeline, default_timeline_path, save_project_timeline
from registry import (
    load_registry,
    register_current_thread,
    register_rollout_thread,
    registry_paths,
    scan_session_rollouts,
)
from subconscious_jobs import JOB_SPECS, DEFAULT_BASE_URL, DEFAULT_MODEL, append_job_findings, default_jobs_output_path, run_jobs
from subconscious_worker import default_staging_path
from build_concept_graph import default_concept_graph_path


ONBOARD_SCHEMA_VERSION = 1


def path_exists(value: Any) -> bool:
    if not value:
        return False
    try:
        return Path(str(value)).exists()
    except OSError:
        return False


def registry_stats(*, registry_dir: Path | None = None) -> dict[str, Any]:
    json_path, _ = registry_paths(registry_dir)
    registry = load_registry(json_path)
    threads = [entry for entry in registry.get("threads") or [] if isinstance(entry, dict)]
    clean_count = 0
    sqlite_count = 0
    graph_count = 0
    rollout_count = 0
    missing: list[dict[str, Any]] = []
    for entry in threads:
        paths = entry.get("paths") or {}
        missing_fields: list[str] = []
        if path_exists(paths.get("rollout")):
            rollout_count += 1
        if path_exists(paths.get("clean_source_messages_jsonl")):
            clean_count += 1
        else:
            missing_fields.append("clean_source")
        if path_exists(paths.get("sqlite")):
            sqlite_count += 1
        else:
            missing_fields.append("sqlite_index")
        if path_exists(paths.get("graph_json")):
            graph_count += 1
        else:
            missing_fields.append("graph_json")
        if missing_fields:
            missing.append(
                {
                    "thread_key": entry.get("thread_key"),
                    "title": entry.get("title"),
                    "rollout": paths.get("rollout"),
                    "workspace": paths.get("workspace"),
                    "missing": missing_fields,
                }
            )
    return {
        "registry": str(json_path),
        "thread_count": len(threads),
        "rollout_count": rollout_count,
        "clean_source_count": clean_count,
        "sqlite_index_count": sqlite_count,
        "graph_json_count": graph_count,
        "missing_clean": len([item for item in missing if "clean_source" in item["missing"]]),
        "missing_sqlite": len([item for item in missing if "sqlite_index" in item["missing"]]),
        "missing_graph_json": len([item for item in missing if "graph_json" in item["missing"]]),
        "missing_artifacts": missing,
    }


def same_path(left: str | None, right: Path) -> bool:
    if not left:
        return False
    try:
        return Path(left).resolve() == right.resolve()
    except OSError:
        return str(left).casefold() == str(right).casefold()


def infer_project_label_for_cwd(cwd: Path, registry_path: Path) -> str | None:
    registry = load_registry(registry_path)
    for entry in registry.get("threads") or []:
        if not isinstance(entry, dict):
            continue
        paths = entry.get("paths") or {}
        if same_path(paths.get("workspace"), cwd):
            return str(entry.get("project_label") or entry.get("workspace_name") or cwd.name)
    return cwd.name if cwd.name else None


def resolve_frontier_project_scope(
    *,
    cwd: Path,
    registry_path: Path,
    project: str | None,
    frontier_project: str | None,
) -> tuple[str | None, str]:
    if frontier_project:
        value = frontier_project.strip()
        if value in {"*", "all", "global"}:
            return None, "explicit_global"
        return value, "explicit_frontier_project"
    if project:
        return project, "project_arg"
    inferred = infer_project_label_for_cwd(cwd, registry_path)
    if inferred:
        return inferred, "cwd_registry_or_name"
    return None, "global_fallback"


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
        refs = finding.get("source_refs") if isinstance(finding.get("source_refs"), list) else []
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
    refresh = actions.get("refresh_current") if isinstance(actions.get("refresh_current"), dict) else {}
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
        ("clean-source" in text or "clean source" in text or "注入" in text or "injection" in text)
        and ("refresh-registered" in text or "refresh" in text or "重写" in text or "未刷新" in text or "unrefreshed" in text)
    )
    if mentions_injection_refresh:
        return "current_registry_artifacts_complete"
    return ""


def filter_frontier_result_for_current_state(result: dict[str, Any], stats: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
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


def write_filtered_frontier_findings(result: dict[str, Any], jobs_output: Path, *, model: str) -> int:
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


def repair_missing_artifacts(
    *,
    registry_dir: Path | None = None,
    build_index: bool = True,
    max_repair: int | None = None,
) -> dict[str, Any]:
    stats = registry_stats(registry_dir=registry_dir)
    repaired: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    candidates = stats.get("missing_artifacts") or []
    if max_repair is not None:
        candidates = candidates[: max(0, int(max_repair))]
    for item in candidates:
        rollout = item.get("rollout")
        if not rollout or not Path(str(rollout)).exists():
            skipped.append({**item, "reason": "missing_rollout"})
            continue
        try:
            result = register_rollout_thread(
                Path(str(rollout)),
                cwd=Path(str(item.get("workspace"))) if item.get("workspace") else None,
                registry_dir=registry_dir,
                build_index=build_index,
            )
        except Exception as exc:  # pragma: no cover - exercised by real onboarding failures
            skipped.append({**item, "reason": "repair_failed", "error": str(exc)[:260]})
            continue
        repaired.append(
            {
                "thread_key": result["entry"].get("thread_key"),
                "title": result["entry"].get("title"),
                "missing_before": item.get("missing") or [],
            }
        )
    return {
        "candidate_count": len(stats.get("missing_artifacts") or []),
        "attempted_count": len(candidates),
        "repaired_count": len(repaired),
        "skipped_count": len(skipped),
        "repaired": repaired[:20],
        "skipped": skipped[:20],
    }


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
        edges_output_path=default_staging_path(registry_path=registry_path, registry_dir=registry_dir),
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
    filtered_result, stale_findings = filter_frontier_result_for_current_state(result, maintenance_stats)
    written_count = 0
    if not no_write:
        written_count = write_filtered_frontier_findings(filtered_result, jobs_output, model=DEFAULT_MODEL)
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


def build_next_hints(*, dry_run: bool, frontier_mode: str) -> list[str]:
    hints: list[str] = []
    if dry_run:
        hints.append("python scripts/onboard_codex.py --all --format json")
    if frontier_mode == "off":
        hints.append("python scripts/onboard_codex.py --frontier-mode smoke --format json")
    return hints[:4]


def run_onboarding(
    *,
    cwd: Path,
    registry_dir: Path | None = None,
    dry_run: bool = False,
    build_index: bool = True,
    repair_indexes: bool = True,
    refresh_current: bool = True,
    refresh_registered: bool = False,
    max_count: int | None = None,
    cwd_filter: str | None = None,
    project: str | None = None,
    tags: list[str] | None = None,
    build_timeline: bool = True,
    build_cognitive_map: bool = True,
    frontier_mode: str = "off",
    frontier_project: str | None = None,
    frontier_concurrency: int = 3,
    frontier_samples_per_job: int = 2,
    frontier_max_turns: int = 180,
) -> dict[str, Any]:
    started = time.perf_counter()
    cwd = Path(cwd).resolve()
    tags = tags or []
    registry_path, _ = registry_paths(registry_dir)
    stats_before = registry_stats(registry_dir=registry_dir)
    planned_frontier_project, planned_frontier_project_reason = resolve_frontier_project_scope(
        cwd=cwd,
        registry_path=registry_path,
        project=project,
        frontier_project=frontier_project,
    )
    scan_plan = scan_session_rollouts(
        registry_dir=registry_dir,
        build_index=build_index,
        refresh=refresh_registered,
        max_count=max_count,
        cwd_filter=cwd_filter,
        project=project,
        tags=tags,
        dry_run=True,
    )
    repair_plan = repair_missing_artifacts(registry_dir=registry_dir, build_index=build_index, max_repair=0) if repair_indexes else {}
    plan = {
        "would_register_count": scan_plan.get("count", 0),
        "would_repair_count": len(stats_before.get("missing_artifacts") or []),
        "would_refresh_current": bool(refresh_current),
        "would_build_timeline": bool(build_timeline),
        "would_build_cognitive_map": bool(build_cognitive_map),
        "frontier_mode": frontier_mode,
        "frontier_project_scope": planned_frontier_project,
        "frontier_project_scope_reason": planned_frontier_project_reason,
        "sample_candidates": (scan_plan.get("planned") or [])[:10],
        "repair_preview": (stats_before.get("missing_artifacts") or [])[:10],
        "repair_probe": repair_plan,
    }
    if dry_run:
        return {
            "ok": True,
            "data": {
                "dry_run": True,
                "storage_policy": {
                    "default": "CODEX_HOME/aippocampus-registry",
                    "project_local": "explicit compatibility/export only",
                },
                "stats_before": {k: v for k, v in stats_before.items() if k != "missing_artifacts"},
                "plan": plan,
                "boundary": {
                    "search_noise": {"status": "mitigated_by_clean_source_filter_and_registry_rank_penalty"},
                    "frontier": {
                        "status": "not_run",
                        "question_extraction_available": "question_extraction" in JOB_SPECS,
                        "project_scope": planned_frontier_project,
                        "project_scope_reason": planned_frontier_project_reason,
                    },
                    "thread_anchors": {"status": "private_by_default_unless_explicit_output"},
                },
            },
            "next": build_next_hints(dry_run=True, frontier_mode=frontier_mode),
            "meta": {"schema_version": ONBOARD_SCHEMA_VERSION, "duration_ms": int((time.perf_counter() - started) * 1000)},
        }

    actions: dict[str, Any] = {}
    scan_result = scan_session_rollouts(
        registry_dir=registry_dir,
        build_index=build_index,
        refresh=refresh_registered,
        max_count=max_count,
        cwd_filter=cwd_filter,
        project=project,
        tags=tags,
        dry_run=False,
    )
    actions["scan_sessions"] = {
        "registered_count": scan_result.get("count", 0),
        "registry": scan_result.get("registry"),
    }
    if repair_indexes:
        actions["repair_missing_artifacts"] = repair_missing_artifacts(registry_dir=registry_dir, build_index=build_index)
    if refresh_current:
        try:
            current = register_current_thread(cwd, registry_dir=registry_dir, build_index=build_index)
            actions["refresh_current"] = {
                "ok": True,
                "thread_key": current["entry"].get("thread_key"),
                "registry": current.get("registry_json"),
            }
        except Exception as exc:  # pragma: no cover - depends on active Codex Desktop rollout state
            actions["refresh_current"] = {"ok": False, "error": str(exc)[:260]}

    timeline_path = default_timeline_path(registry_path)
    if build_timeline:
        timeline = build_project_timeline(registry_path)
        save_project_timeline(timeline_path, timeline)
        actions["project_timeline"] = {
            "output": str(timeline_path),
            "project_count": timeline.get("project_count"),
            "life_label_count": (timeline.get("life_wide") or {}).get("label_count"),
        }

    boundary = {
        "search_noise": {"status": "mitigated_by_clean_source_filter_and_registry_rank_penalty"},
        "thread_anchors": {
            "status": "private_by_default_unless_explicit_output",
            "reason": "registry artifacts and anchor-like generated recall surfaces are local private history unless a user explicitly exports them",
        },
    }
    if not build_timeline and frontier_mode != "off":
        timeline = build_project_timeline(registry_path)
        save_project_timeline(timeline_path, timeline)
        actions["project_timeline"] = {
            "output": str(timeline_path),
            "project_count": timeline.get("project_count"),
            "life_label_count": (timeline.get("life_wide") or {}).get("label_count"),
        }
    active_frontier_project, active_frontier_project_reason = resolve_frontier_project_scope(
        cwd=cwd,
        registry_path=registry_path,
        project=project,
        frontier_project=frontier_project,
    )
    stats_for_frontier = registry_stats(registry_dir=registry_dir)
    boundary["frontier"] = frontier_boundary_result(
        mode=frontier_mode,
        registry_path=registry_path,
        timeline_path=timeline_path,
        registry_dir=registry_dir,
        project=active_frontier_project,
        project_scope_reason=active_frontier_project_reason,
        maintenance_context=frontier_maintenance_context(stats_for_frontier, actions),
        maintenance_stats=stats_for_frontier,
        concurrency=frontier_concurrency,
        samples_per_job=frontier_samples_per_job,
        max_turns=frontier_max_turns,
    )

    if build_cognitive_map:
        jobs_path = default_jobs_output_path(registry_path=registry_path)
        output_path = default_cognitive_map_path(registry_path=registry_path)
        actions["cognitive_map"] = build_cognitive_map_from_files(
            registry_path=registry_path,
            jobs_path=jobs_path,
            output_path=output_path,
        )

    stats_after = registry_stats(registry_dir=registry_dir)
    ok: bool | str = True
    if boundary["frontier"].get("status") in {
        "blocked_missing_api_key",
        "model_failed",
        "model_partial_failure",
        "model_no_findings",
    }:
        ok = "partial"
    return {
        "ok": ok,
        "data": {
            "dry_run": False,
            "storage_policy": {
                "default": "CODEX_HOME/aippocampus-registry",
                "project_local": "explicit compatibility/export only",
            },
            "stats_before": {k: v for k, v in stats_before.items() if k != "missing_artifacts"},
            "plan": plan,
            "actions": actions,
            "stats_after": {k: v for k, v in stats_after.items() if k != "missing_artifacts"},
            "boundary": boundary,
        },
        "next": build_next_hints(dry_run=False, frontier_mode=frontier_mode),
        "meta": {"schema_version": ONBOARD_SCHEMA_VERSION, "duration_ms": int((time.perf_counter() - started) * 1000)},
    }


def print_text(result: dict[str, Any]) -> None:
    data = result.get("data") or {}
    stats = data.get("stats_after") or data.get("stats_before") or {}
    print("AIppocampus Codex onboarding")
    print(f"ok: {result.get('ok')}")
    print(f"threads: {stats.get('thread_count', 0)}")
    print(f"clean-source: {stats.get('clean_source_count', 0)}")
    print(f"sqlite indexes: {stats.get('sqlite_index_count', 0)}")
    print(f"graph.json: {stats.get('graph_json_count', 0)}")
    frontier = (data.get("boundary") or {}).get("frontier") or {}
    print(f"frontier: {frontier.get('status')}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Onboard local Codex sessions into the AIppocampus global registry.")
    parser.add_argument("--all", action="store_true", help="Scan all local Codex sessions. This is the default; the flag is kept for agent readability.")
    parser.add_argument("--cwd", default=os.getcwd(), help="Current workspace to refresh after global session onboarding.")
    parser.add_argument("--registry-dir", help="Defaults to $AIPPOCAMPUS_REGISTRY_DIR or $CODEX_HOME/aippocampus-registry.")
    parser.add_argument("--max", type=int, help="Maximum number of sessions to register, newest first.")
    parser.add_argument("--cwd-filter", help="Only include sessions whose recorded cwd contains this text.")
    parser.add_argument("--project", help="Project label to attach to newly registered sessions.")
    parser.add_argument("--tag", action="append", default=[], help="Extra tag to attach to newly registered sessions. Can be repeated.")
    parser.add_argument("--refresh-registered", action="store_true", help="Refresh sessions already in the registry.")
    parser.add_argument("--no-build-index", action="store_true", help="Build clean-source only; skip SQLite/RAG-lite index generation.")
    parser.add_argument("--no-repair", action="store_true", help="Do not repair already registered rows missing clean-source or indexes.")
    parser.add_argument("--no-refresh-current", action="store_true", help="Do not refresh the current workspace thread after global onboarding.")
    parser.add_argument("--no-timeline", action="store_true", help="Do not rebuild project_timeline.json.")
    parser.add_argument("--no-cognitive-map", action="store_true", help="Do not rebuild cognitive_map.json from existing subconscious findings.")
    parser.add_argument("--frontier-mode", choices=["off", "auto", "smoke", "write"], default="off", help="Run question/frontier extraction: off, no-write smoke, or write staging findings.")
    parser.add_argument("--frontier-project", help="Optional project label filter for frontier extraction. Defaults to the current --cwd project; use '*' for global.")
    parser.add_argument("--frontier-concurrency", type=int, default=3)
    parser.add_argument("--frontier-samples-per-job", type=int, default=2)
    parser.add_argument("--frontier-max-turns", type=int, default=180)
    parser.add_argument("--dry-run", "--preview", action="store_true", dest="dry_run")
    parser.add_argument("--format", choices=["auto", "json", "text"], default="auto")
    parser.add_argument("--json", action="store_true", dest="json_output", help="Alias for --format json.")
    args = parser.parse_args()

    registry_dir = Path(args.registry_dir).resolve() if args.registry_dir else None
    result = run_onboarding(
        cwd=Path(args.cwd),
        registry_dir=registry_dir,
        dry_run=args.dry_run,
        build_index=not args.no_build_index,
        repair_indexes=not args.no_repair,
        refresh_current=not args.no_refresh_current,
        refresh_registered=args.refresh_registered,
        max_count=args.max,
        cwd_filter=args.cwd_filter,
        project=args.project,
        tags=args.tag,
        build_timeline=not args.no_timeline,
        build_cognitive_map=not args.no_cognitive_map,
        frontier_mode=args.frontier_mode,
        frontier_project=args.frontier_project,
        frontier_concurrency=args.frontier_concurrency,
        frontier_samples_per_job=args.frontier_samples_per_job,
        frontier_max_turns=args.frontier_max_turns,
    )
    wants_json = args.json_output or args.format == "json" or (args.format == "auto" and not sys.stdout.isatty())
    if wants_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print_text(result)
    return 0 if result.get("ok") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
