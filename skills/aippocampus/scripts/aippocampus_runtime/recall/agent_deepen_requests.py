"""Build callable deepen requests without leaking opaque handles into prose."""

from __future__ import annotations

import hashlib
import json
import shlex
from collections.abc import Mapping
from typing import Any


def handle_preview(handle_arg: str, *, limit: int = 72) -> str:
    if len(handle_arg) <= limit:
        return handle_arg
    return f"{handle_arg[:48]}...{handle_arg[-12:]}"


def deepen_request_for_route(
    route: Mapping[str, Any],
    packet: Mapping[str, Any],
    *,
    request_index: int,
) -> dict[str, Any]:
    handle = route.get("handle")
    handle_arg = (
        json.dumps(handle, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        if isinstance(handle, Mapping)
        else str(handle)
        if handle
        else ""
    )
    private_handle_command = f"aippocampus agent deepen {shlex.quote(handle_arg)} --json" if handle_arg else None
    request_command = f"aippocampus agent deepen --request {request_index} --last-recall --json"
    digest = hashlib.sha256(handle_arg.encode("utf-8")).hexdigest()[:12] if handle_arg else ""
    human_next_action = request_command
    return {
        "request_index": request_index,
        "route_id": packet.get("route_id"),
        "deepen_route_id": packet.get("deepen_route_id"),
        "deepen_route_id_display_only": True,
        "tool": "agent deepen",
        "handle": handle,
        "callable_handle": handle,
        "callable_handle_field": "deepen_requests[].handle",
        "handle_preview": handle_preview(handle_arg) if handle_arg else "",
        "handle_sha256_12": digest,
        "human_next_action": human_next_action,
        "machine_next_command": request_command,
        "copy_paste_command": request_command,
        "private_handle_command": private_handle_command,
        "boundary": "opaque_navigation_handle_not_fact",
        "claim_boundary": "source_reopen_required_before_strong_claim",
    }


__all__ = ["deepen_request_for_route", "handle_preview"]
