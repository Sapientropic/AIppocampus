"""Action ordering helpers for AIppocampus health reports."""

from __future__ import annotations

from typing import Any


def action(action_id: str, severity: str, reason: str, command: str) -> dict[str, Any]:
    return {"id": action_id, "severity": severity, "reason": reason, "command": command}


def dependency_ordered_actions(actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    action_ids = {str(item.get("id")) for item in actions}
    ordered: list[dict[str, Any]] = []
    for item in actions:
        action_id = str(item.get("id") or "")
        next_item = dict(item)
        depends_on: list[str] = []
        if action_id == "build_index" and "build_clean_source" in action_ids:
            depends_on.append("build_clean_source")
            next_item["blocked_until"] = "build_clean_source_current"
        if action_id in {"build_segments", "prepare_graphify_corpus"}:
            if "build_clean_source" in action_ids:
                depends_on.append("build_clean_source")
            if "build_index" in action_ids:
                depends_on.append("build_index")
            if depends_on:
                next_item["blocked_until"] = "upstream_memory_artifacts_current"
        if depends_on:
            next_item["depends_on"] = depends_on
        ordered.append(next_item)
    priority = {
        "build_clean_source": 10,
        "build_index": 20,
        "build_segments": 30,
        "prepare_graphify_corpus": 40,
        "checkpoint": 50,
    }
    return sorted(ordered, key=lambda item: (priority.get(str(item.get("id") or ""), 100),))
