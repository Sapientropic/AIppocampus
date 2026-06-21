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
    selector_command_template = (
        f"aippocampus agent deepen --request {request_index} "
        "--recall-selector {recall_selector} --json"
    )
    request_command = f"aippocampus agent deepen --request {request_index} --last-recall --json"
    digest = hashlib.sha256(handle_arg.encode("utf-8")).hexdigest()[:12] if handle_arg else ""
    human_next_action = selector_command_template
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
        "machine_next_command_template": selector_command_template,
        "copy_paste_command_template": selector_command_template,
        "last_recall_fallback_command": request_command,
        "last_recall_fallback_boundary": (
            "--last-recall reads a mutable same-machine cache; prefer the recall_selector "
            "emitted by the recall that produced this request."
        ),
        "private_handle_command": private_handle_command,
        "boundary": "opaque_navigation_handle_not_fact",
        "claim_boundary": "source_reopen_required_before_strong_claim",
    }


def attach_recall_selector(
    deepen_requests: list[dict[str, Any]],
    recall_selector: str | None,
) -> list[dict[str, Any]]:
    """Promote selector-safe commands after the cache snapshot has an id.

    Deepen requests are built before the selector snapshot exists. The raw
    request therefore keeps a template plus a clearly labeled mutable-cache
    fallback. Once recall writes the selector snapshot, frontstage/detail
    output should teach the stable selector command as the command to copy.
    """

    selector = str(recall_selector or "").strip()
    if not selector:
        return deepen_requests
    quoted_selector = shlex.quote(selector)
    for request in deepen_requests:
        try:
            request_index = int(request.get("request_index") or 1)
        except (TypeError, ValueError):
            request_index = 1
        command = (
            f"aippocampus agent deepen --request {request_index} "
            f"--recall-selector {quoted_selector} --json"
        )
        request["human_next_action"] = command
        request["machine_next_command"] = command
        request["copy_paste_command"] = command
        request["recall_selector"] = selector
        request["callable_selector"] = {
            "kind": "recall_selector_request_index",
            "request_index": request_index,
            "recall_selector": selector,
        }
    return deepen_requests


def attach_recall_selector_to_payload(
    payload: Mapping[str, Any] | dict[str, Any],
    recall_selector: str | None,
) -> None:
    """Promote all recall-produced frontstage deepen actions to the selector."""

    if not isinstance(payload, dict):
        return
    selector = str(recall_selector or "").strip()
    if not selector:
        return
    attach_recall_selector(payload.get("deepen_requests") or [], selector)
    card = payload.get("foreground_action_card")
    if not isinstance(card, dict) or card.get("tool_name") != "agent_deepen":
        return
    raw_arguments = card.get("arguments")
    arguments = dict(raw_arguments) if isinstance(raw_arguments, Mapping) else {}
    try:
        request_index = int(arguments.get("request_index") or 1)
    except (TypeError, ValueError):
        request_index = 1
    old_command = str(card.get("cli_command") or "").strip()
    command = (
        f"aippocampus agent deepen --request {request_index} "
        f"--recall-selector {shlex.quote(selector)} --json"
    )
    arguments.pop("last_recall", None)
    arguments["request_index"] = request_index
    arguments["recall_selector"] = selector
    card["arguments"] = arguments
    card["cli_command"] = command
    card["recall_selector"] = selector
    card.pop("cli_command_template", None)
    card.pop("template_only", None)
    card.pop("requires", None)
    if old_command:
        card["last_recall_fallback_command"] = old_command
        card["last_recall_fallback_boundary"] = (
            "--last-recall reads a mutable same-machine cache; use only when a "
            "selector emitted by the same recall is unavailable."
        )


__all__ = [
    "attach_recall_selector",
    "attach_recall_selector_to_payload",
    "deepen_request_for_route",
    "handle_preview",
]
