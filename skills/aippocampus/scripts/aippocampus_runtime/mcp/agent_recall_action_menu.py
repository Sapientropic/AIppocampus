"""Small foreground action menu derived from compact agent recall.

Full/detail recall payloads remain operator diagnostics. This helper embeds a
compact-compatible menu in those diagnostics so a foreground agent can continue
without parsing private gate inventories or provenance.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from aippocampus_runtime import core
from aippocampus_runtime.mcp.agent_recall_projection import compact_agent_recall_payload


def foreground_action_menu(payload: Mapping[str, Any], *, query: str = "") -> dict[str, Any]:
    source = dict(payload)
    if query:
        source["query"] = query
    compact = dict(compact_agent_recall_payload(source))
    return core.strip_empty(
        {
            "kind": "aippocampus_agent_recall_foreground_action_menu",
            "detail": "foreground_action_menu",
            "status": compact.get("status"),
            "foreground_action": compact.get("foreground_action"),
            "safe_next_actions": compact.get("safe_next_actions"),
            "routes": compact.get("routes"),
            "background_recovery_card": compact.get("background_recovery_card"),
            "claim_boundary": compact.get("claim_boundary"),
            "operator_details_available": True,
        },
        drop_empty_dicts=True,
    )


__all__ = ["foreground_action_menu"]
