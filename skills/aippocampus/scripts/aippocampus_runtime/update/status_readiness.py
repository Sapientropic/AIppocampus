"""Readiness grouping for update status surfaces."""

from __future__ import annotations

from typing import Any

from aippocampus_runtime.update.agent_status_summary import agent_callable_host_probe_ok

READY_SURFACE_STATUSES = {"current", "ready", "installed_package"}
CORE_SURFACES = ("cli", "skill")
MAGIC_SURFACES = ("hooks", "llm")
OPTIONAL_SURFACES = ("plugin",)
OPERATOR_SURFACES = ("mcp", "agent_callable")


def surface_ready(item: dict[str, Any]) -> bool:
    if item.get("surface") == "llm":
        return bool(item.get("ready"))
    if item.get("surface") == "agent_callable":
        return item.get("ready") is True
    return item.get("status") in READY_SURFACE_STATUSES


def surface_summary_blocker(name: str, item: dict[str, Any]) -> bool:
    if surface_ready(item):
        return False
    if name == "agent_callable" and agent_callable_host_probe_ok(item):
        return False
    return item.get("status") not in {"not_provided", "not_requested"}


def unready_surfaces(surfaces: dict[str, dict[str, Any]], names: tuple[str, ...]) -> list[str]:
    return [name for name in names if not surface_ready(surfaces.get(name) or {})]
