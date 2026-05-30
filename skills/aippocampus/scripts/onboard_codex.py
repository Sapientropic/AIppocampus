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
from typing import Any, Sequence

from build_cognitive_map import build_from_files as build_cognitive_map_from_files
from build_cognitive_map import default_cognitive_map_path
from build_project_timeline import (
    build_project_timeline,
    default_timeline_path,
    save_project_timeline,
)
from conversation_sources import ConversationProvider
from memory_candidate_router import default_candidates_path
from onboard_frontier import (
    filter_frontier_result_for_current_state as filter_frontier_result_for_current_state,
)
from onboard_frontier import frontier_boundary_result, frontier_maintenance_context
from onboard_frontier import onboarding_artifacts_complete as onboarding_artifacts_complete
from onboard_frontier import sample_findings_for_frontier as sample_findings_for_frontier
from onboard_frontier import stale_completed_frontier_reason as stale_completed_frontier_reason
from onboard_frontier import write_filtered_frontier_findings as write_filtered_frontier_findings
from onboard_status import clean_source_line_range as clean_source_line_range
from onboard_status import clean_source_missing_sqlite_lines as clean_source_missing_sqlite_lines
from onboard_status import infer_project_label_for_cwd as infer_project_label_for_cwd
from onboard_status import load_json_file as load_json_file
from onboard_status import maybe_float as maybe_float
from onboard_status import maybe_int as maybe_int
from onboard_status import path_exists as path_exists
from onboard_status import (
    public_registry_stats,
    registry_stats,
    resolve_frontier_project_scope,
)
from onboard_status import same_path as same_path
from onboard_status import sqlite_consistency_issues as sqlite_consistency_issues
from registry import (
    register_current_thread,
    register_rollout_thread,
    registry_paths,
    scan_session_rollouts,
)
from semantic_recall_gate import default_semantic_triggers_path
from semantic_trigger_router import (
    build_semantic_triggers,
    default_seed_triggers_path,
)
from subconscious_jobs import (
    JOB_SPECS,
    default_jobs_output_path,
)

ONBOARD_SCHEMA_VERSION = 1


def repair_missing_artifacts(
    *,
    registry_dir: Path | None = None,
    build_index: bool = True,
    max_repair: int | None = None,
    provider_name: str = "codex",
    provider: ConversationProvider | None = None,
) -> dict[str, Any]:
    stats = registry_stats(registry_dir=registry_dir)
    repaired: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    candidates = stats.get("repair_artifacts") or stats.get("missing_artifacts") or []
    if max_repair is not None:
        candidates = candidates[: max(0, int(max_repair))]
    for item in candidates:
        if not _repair_candidate_matches_provider(item, provider_name):
            skipped.append({**item, "reason": "provider_mismatch"})
            continue
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
                provider=provider,
            )
        except Exception as exc:  # pragma: no cover - exercised by real onboarding failures
            skipped.append({**item, "reason": "repair_failed", "error": str(exc)[:260]})
            continue
        repaired.append(
            {
                "thread_key": result["entry"].get("thread_key"),
                "title": result["entry"].get("title"),
                "missing_before": item.get("missing") or [],
                "stale_before": item.get("stale") or [],
                "issues_before": item.get("issues") or [],
            }
        )
    return {
        "candidate_count": len(
            stats.get("repair_artifacts") or stats.get("missing_artifacts") or []
        ),
        "attempted_count": len(candidates),
        "repaired_count": len(repaired),
        "skipped_count": len(skipped),
        "repaired": repaired[:20],
        "skipped": skipped[:20],
    }


def _repair_candidate_matches_provider(item: dict[str, Any], provider_name: str) -> bool:
    provider_name = provider_name.replace("_", "-")
    thread_key = str(item.get("thread_key") or "")
    source_provider = str(item.get("source_provider") or "").replace("_", "-")
    if provider_name == "codex":
        return not thread_key.startswith(("claude-code:", "generic-jsonl:")) and source_provider in {
            "",
            "codex",
        }
    return thread_key.startswith(f"{provider_name}:") or source_provider == provider_name


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
    provider_name: str = "codex",
    provider: ConversationProvider | None = None,
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
        provider=provider,
    )
    repair_plan = (
        repair_missing_artifacts(
            registry_dir=registry_dir,
            build_index=build_index,
            max_repair=0,
            provider_name=provider_name,
            provider=provider,
        )
        if repair_indexes
        else {}
    )
    plan = {
        "would_register_count": scan_plan.get("count", 0),
        "would_repair_count": len(
            stats_before.get("repair_artifacts") or stats_before.get("missing_artifacts") or []
        ),
        "would_refresh_current": bool(refresh_current),
        "would_build_timeline": bool(build_timeline),
        "would_build_cognitive_map": bool(build_cognitive_map),
        "frontier_mode": frontier_mode,
        "frontier_project_scope": planned_frontier_project,
        "frontier_project_scope_reason": planned_frontier_project_reason,
        "sample_candidates": (scan_plan.get("planned") or [])[:10],
        "repair_preview": (
            stats_before.get("repair_artifacts") or stats_before.get("missing_artifacts") or []
        )[:10],
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
                "stats_before": public_registry_stats(stats_before),
                "plan": plan,
                "boundary": {
                    "search_noise": {
                        "status": "mitigated_by_clean_source_filter_and_registry_rank_penalty"
                    },
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
            "meta": {
                "schema_version": ONBOARD_SCHEMA_VERSION,
                "provider": provider_name,
                "duration_ms": int((time.perf_counter() - started) * 1000),
            },
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
        provider=provider,
    )
    actions["scan_sessions"] = {
        "registered_count": scan_result.get("count", 0),
        "registry": scan_result.get("registry"),
    }
    if repair_indexes:
        actions["repair_missing_artifacts"] = repair_missing_artifacts(
            registry_dir=registry_dir,
            build_index=build_index,
            provider_name=provider_name,
            provider=provider,
        )
    if refresh_current:
        try:
            current = register_current_thread(
                cwd, registry_dir=registry_dir, build_index=build_index, provider=provider
            )
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
    actions["semantic_triggers"] = build_semantic_triggers(
        candidates_path=default_candidates_path(registry_path=registry_path),
        output_path=default_semantic_triggers_path(registry_path=registry_path),
        seed_triggers_path=default_seed_triggers_path(),
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
            "stats_before": public_registry_stats(stats_before),
            "plan": plan,
            "actions": actions,
            "stats_after": public_registry_stats(stats_after),
            "boundary": boundary,
        },
        "next": build_next_hints(dry_run=False, frontier_mode=frontier_mode),
        "meta": {
            "schema_version": ONBOARD_SCHEMA_VERSION,
            "provider": provider_name,
            "duration_ms": int((time.perf_counter() - started) * 1000),
        },
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


def main(
    argv: Sequence[str] | None = None,
    *,
    provider_name: str = "codex",
    provider: ConversationProvider | None = None,
) -> int:
    parser = argparse.ArgumentParser(
        description="Onboard local Codex sessions into the AIppocampus global registry."
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Scan all local Codex sessions. This is the default; the flag is kept for agent readability.",
    )
    parser.add_argument(
        "--cwd",
        default=os.getcwd(),
        help="Current workspace to refresh after global session onboarding.",
    )
    parser.add_argument(
        "--registry-dir",
        help="Defaults to $AIPPOCAMPUS_REGISTRY_DIR or $CODEX_HOME/aippocampus-registry.",
    )
    parser.add_argument(
        "--max", type=int, help="Maximum number of sessions to register, newest first."
    )
    parser.add_argument(
        "--cwd-filter", help="Only include sessions whose recorded cwd contains this text."
    )
    parser.add_argument("--project", help="Project label to attach to newly registered sessions.")
    parser.add_argument(
        "--tag",
        action="append",
        default=[],
        help="Extra tag to attach to newly registered sessions. Can be repeated.",
    )
    parser.add_argument(
        "--refresh-registered",
        action="store_true",
        help="Refresh sessions already in the registry.",
    )
    parser.add_argument(
        "--no-build-index",
        action="store_true",
        help="Build clean-source only; skip SQLite/RAG-lite index generation.",
    )
    parser.add_argument(
        "--no-repair",
        action="store_true",
        help="Do not repair already registered rows missing clean-source or indexes.",
    )
    parser.add_argument(
        "--no-refresh-current",
        action="store_true",
        help="Do not refresh the current workspace thread after global onboarding.",
    )
    parser.add_argument(
        "--no-timeline", action="store_true", help="Do not rebuild project_timeline.json."
    )
    parser.add_argument(
        "--no-cognitive-map",
        action="store_true",
        help="Do not rebuild cognitive_map.json from existing subconscious findings.",
    )
    parser.add_argument(
        "--frontier-mode",
        choices=["off", "auto", "smoke", "write"],
        default="off",
        help="Run question/frontier extraction: off, no-write smoke, or write staging findings.",
    )
    parser.add_argument(
        "--frontier-project",
        help="Optional project label filter for frontier extraction. Defaults to the current --cwd project; use '*' for global.",
    )
    parser.add_argument("--frontier-concurrency", type=int, default=3)
    parser.add_argument("--frontier-samples-per-job", type=int, default=2)
    parser.add_argument("--frontier-max-turns", type=int, default=180)
    parser.add_argument("--dry-run", "--preview", action="store_true", dest="dry_run")
    parser.add_argument("--format", choices=["auto", "json", "text"], default="auto")
    parser.add_argument(
        "--json", action="store_true", dest="json_output", help="Alias for --format json."
    )
    args = parser.parse_args(argv)

    registry_dir = Path(args.registry_dir).resolve() if args.registry_dir else None
    result = run_onboarding(
        cwd=Path(args.cwd),
        registry_dir=registry_dir,
        provider_name=provider_name,
        provider=provider,
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
    wants_json = (
        args.json_output
        or args.format == "json"
        or (args.format == "auto" and not sys.stdout.isatty())
    )
    if wants_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print_text(result)
    return 0 if result.get("ok") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
