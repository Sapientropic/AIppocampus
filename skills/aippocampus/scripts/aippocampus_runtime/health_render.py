#!/usr/bin/env python3
"""Text rendering helpers for AIppocampus health reports."""

from __future__ import annotations

from typing import Any


def _action_command(item: dict[str, Any]) -> str:
    return str(item.get("facade_command") or item.get("command") or "").strip()


def _command_kind(command: str) -> str:
    lowered = str(command or "").casefold()
    if (
        " plan" in lowered
        or "--summary-json" in lowered
        or "--dry-run" in lowered
        or " --status" in lowered
    ):
        return "inspect"
    return "repair"


def render_health_text(result: dict[str, Any]) -> None:
    status = "OK" if result["ok"] else "needs maintenance"
    rollout = result["rollout"]
    index = result["index"]
    clean_source = result["clean_source"]
    segments = result["segments"]
    checkpoint = result["checkpoint"]
    graphify = result["graphify"]
    storage = result.get("storage") or {}
    question_stats = result.get("question_stats") or {}
    background = result.get("background_cognition") or {}
    storage_pressure = result.get("storage_pressure") or {}
    logs = result.get("logs") or {}
    trajectory = result.get("health_trajectory") or {}
    actions = result["recommended_actions"]

    readiness = result.get("product_readiness") or {}
    if readiness:
        usable = "yes" if readiness.get("ready") else "partial"
        first_action = next((item for item in actions if item.get("severity") in {"critical", "warning"}), None)
        can_continue = bool(
            readiness.get(
                "ordinary_first_recall_usable",
                readiness.get("ready") and not readiness.get("maintenance_required_before_recall"),
            )
        )
        blocks_exact_latest = bool(
            readiness.get("blocks_exact_latest_claims")
            or readiness.get("blocks_exact_latest")
            or readiness.get("freshness_degraded")
            or readiness.get("latest_current_thread_may_be_missing")
            or str(readiness.get("status") or "") == "ready_with_freshness_degraded"
        )
        print("AIppocampus health")
        print(f"readiness: {usable} ({readiness.get('status') or status})")
        print(f"can_continue_recall_now: {'yes' if can_continue else 'partial'}")
        print(f"blocks_exact_latest_claims: {'yes' if blocks_exact_latest else 'no'}")
        if can_continue and blocks_exact_latest and first_action:
            print("best next action: continue")
            print("inspect: aippocampus maintenance plan --summary-json")
        elif first_action:
            print(f"best next action: {first_action.get('id')}")
            command = _action_command(first_action)
            if command:
                print(f"{_command_kind(command)}: {command}")
        else:
            print("best next action: continue; run maintenance only when a specific check asks for it")
        works: list[str] = []
        if clean_source.get("exists"):
            works.append("clean source exists")
        if index.get("exists"):
            works.append("index exists")
        if works:
            print("works now: " + ", ".join(works))
        stale_optional: list[str] = []
        if checkpoint.get("due"):
            stale_optional.append("checkpoint due when idle")
        if graphify.get("stale"):
            stale_optional.append("graphify corpus stale")
        if background and (
            background.get("blocked_lane_count")
            or background.get("stale_lane_count")
            or background.get("due_lane_count")
        ):
            stale_optional.append("background cognition needs review")
        if stale_optional:
            print("not blocking first recall: " + ", ".join(stale_optional))
        print("")
    print(f"thread memory health: {status}")
    if storage:
        print(
            "registry: "
            f"{storage.get('active_registry')} "
            f"({storage.get('active_registry_source')})"
        )
    print(
        f"rollout: {rollout['path']} ({rollout['size']} bytes, {rollout['message_count']} messages)"
    )
    if index["stale"]:
        print("index: stale")
    elif index["message_delta"] or index["byte_delta"]:
        print(
            f"index: fresh window ({index['message_delta']} unindexed messages, {index['byte_delta']} new bytes below threshold)"
        )
    else:
        print("index: fresh")
    if index["rag"]:
        print(f"rag cache: {index['rag'].get('chunk_count', 0)} chunks")
    print(f"clean source: {'stale' if clean_source['stale'] else 'fresh'}")
    if segments["exists"]:
        print(
            f"segments: {'stale' if segments['stale'] else 'fresh'} ({segments['segment_count']} shards)"
        )
    elif segments["needed"]:
        print("segments: missing")
    else:
        print("segments: not needed yet")
    print(f"checkpoint: {'due' if checkpoint['due'] else 'not due'}")
    print(f"graphify corpus: {'stale' if graphify['stale'] else 'fresh'}")
    if storage_pressure.get("available"):
        pressure_metrics = storage_pressure.get("metrics") or {}
        if storage_pressure.get("pressure"):
            print(
                "generated cache pressure: "
                f"{pressure_metrics.get('reclaimable_rebuildable_human')} reclaimable; "
                f"{pressure_metrics.get('generated_index_amplification_ratio')}x clean-source ratio"
            )
            print(f"cache check: {storage_pressure.get('dry_run_command')}")
        else:
            print("generated cache pressure: ok")
    if logs:
        if logs.get("oversized"):
            print(f"logs: {logs.get('oversized_count', 0)} oversized artifact(s)")
        else:
            print("logs: within retention budget")
    host_confounds = result.get("host_state_confounds") or {}
    if host_confounds.get("available"):
        print(
            "codex host-state confounds: "
            f"{host_confounds.get('total_observed_human')} observed "
            f"({host_confounds.get('size_bucket')}); separate from AIppocampus cache"
        )
    if trajectory.get("preemptive_actions"):
        print(
            "preemptive freshness: "
            + ", ".join(str(item) for item in trajectory.get("preemptive_actions") or [])
        )
    if question_stats.get("available"):
        print(
            "question health: "
            f"{question_stats.get('question_group_count', 0)} groups, "
            f"{question_stats.get('recurring_link_count', 0)} recurring links, "
            f"{question_stats.get('dormant_question_count', 0)} dormant, "
            f"{question_stats.get('resolved_question_count', 0)} resolved"
        )
    if background.get("available"):
        print(
            "background cognition: "
            f"{background.get('running_lane_count', 0)} running, "
            f"{background.get('due_lane_count', 0)} due, "
            f"{background.get('blocked_lane_count', 0)} blocked, "
            f"{background.get('stale_lane_count', 0)} stale"
        )
        for name, lane in (background.get("lanes") or {}).items():
            due_state = str(lane.get("due_state") or "unknown")
            freshness_state = str(lane.get("freshness_state") or "unknown")
            if due_state in {"blocked", "due", "stale"} or freshness_state in {
                "blocked",
                "due",
                "stale",
                "no_signal",
            }:
                print(
                    f"- {name}: {due_state}; freshness={freshness_state}; next={lane.get('next_operator_action')}"
                )
    if actions:
        print("\nrecommended actions:")
        for item in actions:
            print(f"- {item['id']} [{item['severity']}]: {item['reason']}")
        runnable = [item for item in actions if item.get("command")]
        if runnable:
            print("\nNext actions:" if not result["ok"] else "\nMaintenance to inspect when idle:")
            for index, item in enumerate(runnable[:3], start=1):
                command = _action_command(item)
                command_kind = "inspect" if result["ok"] else _command_kind(command)
                print(f"{index}. {item['id']} [{command_kind}]: {command}")


def render_registry_health_text(result: dict[str, Any]) -> None:
    print("registry memory health: " + ("OK" if result["ok"] else "needs maintenance"))
    print(f"threads: {result['thread_count']}")
    status_counts = result.get("status_counts") or {}
    print(
        "status: "
        f"ok={status_counts.get('ok', 0)} "
        f"needs={status_counts.get('needs_maintenance', 0)} "
        f"unknown={status_counts.get('unknown', 0)}"
    )
    action_counts = result.get("recommended_action_counts") or {}
    if action_counts:
        print("recommended actions:")
        for action_id, count in action_counts.items():
            print(f"- {action_id}: {count}")
    else:
        print("no registry recommendations recorded")
    top_threads = result.get("top_threads") or []
    if top_threads:
        print("highest-risk thread refs:")
        for item in top_threads:
            print(
                f"- {item['thread_ref']}: "
                f"{', '.join(item.get('recommended_action_ids') or []) or 'no action'} "
                f"(delta={item.get('index_message_delta', 0)})"
            )
