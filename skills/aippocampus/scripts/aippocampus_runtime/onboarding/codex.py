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

from aippocampus_runtime.contracts import foreground_shell_action
from aippocampus_runtime.navigation.cognitive_map import (
    build_from_files as build_cognitive_map_from_files,
)
from aippocampus_runtime.navigation.cognitive_map import default_cognitive_map_path
from aippocampus_runtime.navigation.project_timeline import (
    build_project_timeline,
    default_timeline_path,
    save_project_timeline,
)
from aippocampus_runtime.onboarding.frontier import (
    frontier_boundary_result,
    frontier_maintenance_context,
)
from aippocampus_runtime.onboarding.status import (
    clean_source_line_range as clean_source_line_range,
)
from aippocampus_runtime.onboarding.status import (
    clean_source_missing_sqlite_lines as clean_source_missing_sqlite_lines,
)
from aippocampus_runtime.onboarding.status import (
    infer_project_label_for_cwd as infer_project_label_for_cwd,
)
from aippocampus_runtime.onboarding.status import load_json_file as load_json_file
from aippocampus_runtime.onboarding.status import maybe_float as maybe_float
from aippocampus_runtime.onboarding.status import maybe_int as maybe_int
from aippocampus_runtime.onboarding.status import path_exists as path_exists
from aippocampus_runtime.onboarding.status import (
    public_registry_stats,
    registry_stats,
    resolve_frontier_project_scope,
)
from aippocampus_runtime.onboarding.status import same_path as same_path
from aippocampus_runtime.onboarding.status import (
    sqlite_consistency_issues as sqlite_consistency_issues,
)
from aippocampus_runtime.recall.semantic_recall_gate import default_semantic_triggers_path
from aippocampus_runtime.recall.semantic_trigger_router import (
    build_semantic_triggers,
    default_seed_triggers_path,
)
from aippocampus_runtime.registry.api import (
    load_registry,
    register_current_thread,
    register_rollout_thread,
    registry_paths,
    scan_session_rollouts,
)
from aippocampus_runtime.subconscious.candidate_router import default_candidates_path
from aippocampus_runtime.subconscious.jobs import (
    JOB_SPECS,
    default_jobs_output_path,
)
from aippocampus_runtime.warm_ambient import query_pattern_routes
from conversation_sources import ConversationProvider

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
    hints: list[str] = [
        'aippocampus search "distinctive old phrase"',
        'aippocampus search "project cue or known old term"',
        'aippocampus search "recent or last month"',
    ]
    if dry_run:
        hints.append("aippocampus onboard --provider codex --all --format json")
    if frontier_mode == "off":
        hints.append("aippocampus onboard --provider codex --frontier-mode smoke --format json")
    return hints[:4]


def public_next_actions(*, dry_run: bool, frontier_mode: str, provider: str = "codex") -> list[dict[str, Any]]:
    actions = [
        foreground_shell_action(
            action_id="try_source_backed_search",
            label="Search registered clean source",
            command='aippocampus search "distinctive old phrase" --json',
            why="Use after onboarding/status when you remember exact wording.",
            mutation_risk="read_only",
            claim_boundary="source_reopen_required_before_quoting",
        ),
        foreground_shell_action(
            action_id="try_agent_recall",
            label="Recall from a vague cue",
            command='aippocampus agent recall "old decision or handoff cue" --json',
            why="Use when the cue is fuzzy and you need route selection.",
            mutation_risk="read_only",
            claim_boundary="no_claim_before_reopen",
        ),
    ]
    if dry_run:
        actions.insert(
            0,
            foreground_shell_action(
                action_id="register_after_dry_run_review",
                label="Register after reviewing the dry-run plan",
                command=f"aippocampus onboard --provider {provider} --all --json",
                why="Dry-run found a plan; this is the explicit write step if the plan is intended.",
                mutation_risk="explicit_registration_write",
                claim_boundary="host_setup_not_memory_evidence",
            ),
        )
        actions.insert(
            1,
            foreground_shell_action(
                action_id="review_provider_status",
                label="Review provider status before writing",
                command=f"aippocampus onboard --provider {provider} --status --json",
                why="Use this if consent or provider scope is still unclear.",
                mutation_risk="read_only",
                claim_boundary="host_status_not_memory_evidence",
            ),
        )
    if frontier_mode == "off":
        actions.append(
            foreground_shell_action(
                action_id="preview_frontier_smoke",
                label="Preview frontier smoke mode",
                command=f"aippocampus onboard --provider {provider} --frontier-mode smoke --dry-run --json",
                why="Question/frontier extraction is optional and should be previewed before write paths.",
                mutation_risk="read_only",
                claim_boundary="host_setup_not_memory_evidence",
            )
        )
    return actions[:4]


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
    actions["query_pattern_routes"] = query_pattern_routes.publish_registry_query_pattern_routes(
        load_registry(registry_path), registry_dir=registry_path.parent
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
    print(f"frontier: {public_frontier_status(frontier.get('status'))}")
    print()
    print("First recall")
    print('- exact phrase: aippocampus search "distinctive old phrase"')
    print('- project cue: aippocampus search "repo, feature, object, or topic"')
    print('- time cue: aippocampus search "recent, last month, or a known date"')
    print("Boundary: project/time cues are candidate navigation until a source-backed snippet appears.")


def public_count(value: Any) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def public_frontier_status(value: Any) -> str:
    status = str(value or "").strip()
    allowed = {
        "not_run",
        "off",
        "auto",
        "smoke",
        "write",
        "blocked_missing_api_key",
        "model_failed",
        "model_partial_failure",
        "model_no_findings",
        "skipped_stale_state",
        "completed",
    }
    return status if status in allowed else "unknown"


def public_stats(stats: Any) -> dict[str, int]:
    if not isinstance(stats, dict):
        return {}
    keys = (
        "thread_count",
        "clean_source_count",
        "sqlite_index_count",
        "graph_json_count",
        "stale_sqlite",
        "missing_clean_source",
    )
    return {key: public_count(stats.get(key)) for key in keys if key in stats}


def public_plan_summary(plan: Any) -> dict[str, Any]:
    if not isinstance(plan, dict):
        return {}
    return {
        "would_register_count": public_count(plan.get("would_register_count")),
        "would_repair_count": public_count(plan.get("would_repair_count")),
        "would_refresh_current": bool(plan.get("would_refresh_current")),
        "would_build_timeline": bool(plan.get("would_build_timeline")),
        "would_build_cognitive_map": bool(plan.get("would_build_cognitive_map")),
        "frontier_mode": public_frontier_status(plan.get("frontier_mode")),
    }


def public_action_summaries(actions: Any) -> dict[str, Any]:
    if not isinstance(actions, dict):
        return {}
    summaries: dict[str, Any] = {}

    scan_sessions = actions.get("scan_sessions")
    if isinstance(scan_sessions, dict):
        summaries["scan_sessions"] = {
            "registered_count": public_count(scan_sessions.get("registered_count"))
        }

    repair_missing_artifacts = actions.get("repair_missing_artifacts")
    if isinstance(repair_missing_artifacts, dict):
        summaries["repair_missing_artifacts"] = {
            "repaired_count": public_count(repair_missing_artifacts.get("repaired_count"))
        }

    refresh_current = actions.get("refresh_current")
    if isinstance(refresh_current, dict):
        summaries["refresh_current"] = {"ok": bool(refresh_current.get("ok"))}

    project_timeline = actions.get("project_timeline")
    if isinstance(project_timeline, dict):
        summaries["project_timeline"] = {
            "project_count": public_count(project_timeline.get("project_count")),
            "life_label_count": public_count(project_timeline.get("life_label_count")),
        }

    cognitive_map = actions.get("cognitive_map")
    if isinstance(cognitive_map, dict):
        summaries["cognitive_map"] = {
            "route_count": public_count(cognitive_map.get("route_count"))
        }

    semantic_triggers = actions.get("semantic_triggers")
    if isinstance(semantic_triggers, dict):
        summaries["semantic_triggers"] = {
            "trigger_count": public_count(semantic_triggers.get("trigger_count"))
        }

    if isinstance(query_routes_report := actions.get("query_pattern_routes"), dict):
        summaries["query_pattern_routes"] = (
            query_pattern_routes.public_registry_query_pattern_routes_summary(query_routes_report)
        )

    return summaries


def public_onboarding_result(result: dict[str, Any]) -> dict[str, Any]:
    raw_data = result.get("data")
    data: dict[str, Any] = raw_data if isinstance(raw_data, dict) else {}
    raw_boundary = data.get("boundary")
    boundary: dict[str, Any] = raw_boundary if isinstance(raw_boundary, dict) else {}
    raw_frontier = boundary.get("frontier")
    frontier: dict[str, Any] = raw_frontier if isinstance(raw_frontier, dict) else {}
    if not frontier:
        raw_data_frontier = data.get("frontier")
        if isinstance(raw_data_frontier, dict):
            frontier = raw_data_frontier
    raw_meta = result.get("meta")
    meta: dict[str, Any] = raw_meta if isinstance(raw_meta, dict) else {}
    raw_actions = data.get("actions")
    actions: dict[str, Any] = raw_actions if isinstance(raw_actions, dict) else {}
    dry_run = bool(data.get("dry_run"))
    provider = str(meta.get("provider") or "codex")
    next_actions = public_next_actions(
        dry_run=dry_run,
        frontier_mode=str(frontier.get("status") or "off"),
        provider=provider,
    )
    return {
        "ok": result.get("ok"),
        "data": {
            "dry_run": dry_run,
            "stats_before": public_stats(data.get("stats_before")),
            "stats_after": public_stats(data.get("stats_after")),
            "plan": public_plan_summary(data.get("plan")),
            "actions": public_action_summaries(actions),
            "frontier_status": public_frontier_status(frontier.get("status")),
            "action_count": len(actions),
            "storage_policy": data.get("storage_policy") or {},
        },
        "next_actions": next_actions,
        "next_count": len(next_actions),
        "meta": {
            "schema_version": public_count(meta.get("schema_version")),
            "provider": provider,
            "duration_ms": public_count(meta.get("duration_ms")),
        },
        "output_boundary": "onboarding_cli_json_omits_private_artifacts_and_samples",
    }


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
        print(json.dumps(public_onboarding_result(result), ensure_ascii=False, indent=2))
    else:
        print_text(result)
    return 0 if result.get("ok") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
