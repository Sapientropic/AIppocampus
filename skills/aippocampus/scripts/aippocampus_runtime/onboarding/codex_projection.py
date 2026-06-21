"""Public text and compact JSON projection for Codex onboarding."""

from __future__ import annotations

import shlex
from typing import Any

from aippocampus_runtime import contracts
from aippocampus_runtime.warm_ambient import query_pattern_routes

PUBLIC_FRONTIER_STATUS_LABELS = {
    key: key
    for key in (
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
    )
}
PUBLIC_PROVIDER_LABELS = {
    key: key
    for key in (
        "auto",
        "codex",
        "claude-code",
        "generic-jsonl",
    )
}


def _quote_command_arg(value: object) -> str:
    text = str(value)
    if not text:
        return '""'
    return shlex.quote(text)


def dry_run_scope_descriptor(
    *,
    cwd_filter: str | None = None,
    project: str | None = None,
    tags: list[str] | None = None,
    max_count: int | None = None,
    refresh_current: bool = True,
    refresh_registered: bool = False,
) -> dict[str, Any]:
    """Describe which preview scope the explicit write action should preserve.

    The public card must not silently broaden a scoped preview into an `--all`
    write. Local cwd values are intentionally represented as `.` because the
    foreground command should be runnable from the current project without
    publishing private filesystem paths.
    """

    args: list[str] = []
    if refresh_current:
        args.extend(["--cwd", "."])
    if cwd_filter:
        args.extend(["--cwd-filter", cwd_filter])
    if project:
        args.extend(["--project", project])
    for tag in tags or []:
        args.extend(["--tag", tag])
    if max_count is not None:
        args.extend(["--max", str(max(0, int(max_count)))])
    if refresh_registered:
        args.append("--refresh-registered")
    if args:
        return {
            "kind": "current_or_filtered_preview",
            "write_command_args": args,
            "scope_escalation": "none",
        }
    return {
        "kind": "global_scan_preview",
        "write_command_args": ["--all"],
        "scope_escalation": "explicit_all_sessions",
    }


def _scope_command_suffix(scope: dict[str, Any] | None) -> tuple[str, str]:
    if not isinstance(scope, dict):
        scope = {"write_command_args": ["--all"], "scope_escalation": "explicit_all_sessions"}
    args = [str(item) for item in scope.get("write_command_args") or [] if str(item)]
    suffix = " ".join(_quote_command_arg(arg) for arg in args)
    return suffix, str(scope.get("scope_escalation") or "unknown")


def public_next_actions(
    *,
    dry_run: bool,
    frontier_mode: str,
    provider: str = "codex",
    dry_run_scope: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    provider = public_provider_name(provider)
    actions = [
        contracts.foreground_shell_action(
            action_id="try_source_backed_search",
            label="Search registered clean source",
            command='aippocampus search "distinctive old phrase" --json',
            why="Use after onboarding/status when you remember exact wording.",
            mutation_risk="read_only",
            claim_boundary="source_reopen_required_before_quoting",
        ),
        contracts.foreground_shell_action(
            action_id="try_agent_recall",
            label="Recall from a vague cue",
            command='aippocampus agent recall "old decision or handoff cue" --json',
            why="Use when the cue is fuzzy and you need route selection.",
            mutation_risk="read_only",
            claim_boundary="no_claim_before_reopen",
        ),
    ]
    if dry_run:
        scope_suffix, scope_escalation = _scope_command_suffix(dry_run_scope)
        write_command = f"aippocampus onboard --provider {provider}"
        if scope_suffix:
            write_command = f"{write_command} {scope_suffix}"
        write_command = f"{write_command} --json"
        write_action = contracts.foreground_shell_action(
            action_id="register_after_dry_run_review",
            label="Register after reviewing the dry-run plan",
            command=write_command,
            why="Dry-run found a plan; this explicit write step preserves the preview scope.",
            mutation_risk="explicit_registration_write",
            claim_boundary="host_setup_not_memory_evidence",
        )
        write_action["scope"] = "same_as_dry_run_preview"
        write_action["scope_escalation"] = scope_escalation
        actions.insert(
            0,
            write_action,
        )
        actions.insert(
            1,
            contracts.foreground_shell_action(
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
            contracts.foreground_shell_action(
                action_id="preview_frontier_smoke",
                label="Preview frontier smoke mode",
                command=f"aippocampus onboard --provider {provider} --frontier-mode smoke --dry-run --json",
                why="Question/frontier extraction is optional and should be previewed before write paths.",
                mutation_risk="read_only",
                claim_boundary="host_setup_not_memory_evidence",
            )
        )
    return actions[:4]

def print_text(result: dict[str, Any]) -> None:
    raw_data = result.get("data")
    data: dict[str, Any] = raw_data if isinstance(raw_data, dict) else {}
    stats = public_stats(data.get("stats_after") or data.get("stats_before"))
    print("AIppocampus Codex onboarding")
    print(f"ok: {result.get('ok')}")
    print(f"threads: {stats.get('thread_count', 0)}")
    print(f"clean-source: {stats.get('clean_source_count', 0)}")
    print(f"sqlite indexes: {stats.get('sqlite_index_count', 0)}")
    print(f"graph.json: {stats.get('graph_json_count', 0)}")
    raw_boundary = data.get("boundary")
    boundary: dict[str, Any] = raw_boundary if isinstance(raw_boundary, dict) else {}
    raw_frontier = boundary.get("frontier")
    frontier: dict[str, Any] = raw_frontier if isinstance(raw_frontier, dict) else {}
    frontier_status = public_frontier_status(frontier.get("status"))
    print(f"frontier: {frontier_status}")
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
    return PUBLIC_FRONTIER_STATUS_LABELS.get(status, "unknown")


def public_provider_name(value: Any) -> str:
    provider = str(value or "codex").strip().lower().replace("_", "-")
    return PUBLIC_PROVIDER_LABELS.get(provider, "auto")


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
    summary: dict[str, Any] = {
        "would_register_count": public_count(plan.get("would_register_count")),
        "would_repair_count": public_count(plan.get("would_repair_count")),
        "would_refresh_current": bool(plan.get("would_refresh_current")),
        "would_build_timeline": bool(plan.get("would_build_timeline")),
        "would_build_cognitive_map": bool(plan.get("would_build_cognitive_map")),
        "frontier_mode": public_frontier_status(plan.get("frontier_mode")),
    }
    dry_run_scope = plan.get("dry_run_scope")
    if isinstance(dry_run_scope, dict):
        summary["dry_run_scope"] = {
            "kind": str(dry_run_scope.get("kind") or "unknown"),
            "write_command_args": [
                str(item)
                for item in dry_run_scope.get("write_command_args") or []
                if str(item)
            ],
            "scope_escalation": str(dry_run_scope.get("scope_escalation") or "unknown"),
        }
    return summary


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
    provider = public_provider_name(meta.get("provider"))
    plan_summary = public_plan_summary(data.get("plan"))
    next_actions = public_next_actions(
        dry_run=dry_run,
        frontier_mode=str(frontier.get("status") or "off"),
        provider=provider,
        dry_run_scope=plan_summary.get("dry_run_scope"),
    )
    primary_action = next_actions[0] if next_actions else {
        "id": "continue_after_onboarding_status",
        "message": "No onboarding action is needed from this compact card.",
        "mutation_risk": "read_only",
        "claim_boundary": "host_setup_not_memory_evidence",
    }
    action_fields = contracts.canonical_foreground_action_fields(primary_action, safe_next_actions=next_actions or [primary_action])
    return {
        "kind": "aippocampus_onboard_result",
        "status": "dry_run_preview" if dry_run else "completed",
        "ok": result.get("ok"),
        **action_fields,
        "data": {
            "dry_run": dry_run,
            "stats_before": public_stats(data.get("stats_before")),
            "stats_after": public_stats(data.get("stats_after")),
            "plan": plan_summary,
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
