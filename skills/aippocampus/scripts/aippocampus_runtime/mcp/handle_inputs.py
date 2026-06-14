#!/usr/bin/env python3
"""Normalize ergonomic MCP recall navigation inputs."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

CleanRef = Callable[[dict[str, Any]], dict[str, Any]]


def source_ref_from_reopen_arguments(
    arguments: Mapping[str, Any],
    *,
    clean_ref: CleanRef,
) -> dict[str, Any] | None:
    ref = clean_ref(dict(arguments))
    if any(ref.get(key) is not None for key in ("message_id", "turn_id", "turn_index", "line")):
        return ref
    return ref if ref.get("thread_key") else None


def nested_navigation_handle_value(
    current: Mapping[str, Any],
    *,
    clean_ref: CleanRef,
) -> Any:
    if current.get("handle"):
        return current.get("handle")
    suggested = current.get("suggested_next")
    if isinstance(suggested, Mapping):
        arguments = suggested.get("arguments")
        if isinstance(arguments, Mapping) and arguments.get("handle"):
            return arguments.get("handle")
    reopen = current.get("source_reopen_path")
    if isinstance(reopen, Mapping):
        arguments = reopen.get("arguments")
        if isinstance(arguments, Mapping):
            ref = source_ref_from_reopen_arguments(arguments, clean_ref=clean_ref)
            if ref:
                return {"kind": "source_ref", "route_id": current.get("route_id"), "source_refs": [ref]}
    ref = source_ref_from_reopen_arguments(current, clean_ref=clean_ref)
    if ref:
        return {"kind": "source_ref", "route_id": current.get("route_id"), "source_refs": [ref]}
    return None
