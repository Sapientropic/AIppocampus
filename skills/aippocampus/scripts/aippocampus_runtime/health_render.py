#!/usr/bin/env python3
"""Text rendering helpers for AIppocampus health reports."""

from __future__ import annotations

from typing import Any


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
    logs = result.get("logs") or {}
    trajectory = result.get("health_trajectory") or {}
    actions = result["recommended_actions"]

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
    if logs:
        if logs.get("oversized"):
            print(f"logs: {logs.get('oversized_count', 0)} oversized artifact(s)")
        else:
            print("logs: within retention budget")
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
    if actions:
        print("\nrecommended actions:")
        for item in actions:
            print(f"- {item['id']} [{item['severity']}]: {item['reason']}")


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
