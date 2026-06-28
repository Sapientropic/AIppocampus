"""MCP handlers for Telepathy handoff tools."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from aippocampus_runtime.mcp.foreground_recovery import (
    missing_input_recovery_card,
)
from aippocampus_runtime.mcp.foreground_recovery import (
    template_tool_action as _template_tool_action,
)
from aippocampus_runtime.mcp.result_profile import (
    RuntimeProvenanceContext,
    render_profiled_result,
)
from aippocampus_runtime.ops import telepathy_handoff_store

RuntimeContextFn = Callable[..., RuntimeProvenanceContext]


def call_list_telepathy_handoffs(
    arguments: dict[str, Any],
    *,
    cwd_arg: Callable[[dict[str, Any]], Path],
    int_range: Callable[..., int],
    clean_source_dir_for: Callable[[dict[str, Any]], Path],
    runtime_context_for: RuntimeContextFn,
) -> dict[str, Any]:
    payload = telepathy_handoff_store.list_handoffs_payload(
        cwd=cwd_arg(arguments),
        store_path=arguments.get("store_path"),
        scope=arguments.get("scope"),
        status=str(arguments.get("status") or "active"),
        limit=int_range(arguments.get("max"), default=20, minimum=1, maximum=100),
    )
    return render_profiled_result(
        arguments,
        payload,
        runtime_provenance_context=runtime_context_for(
            arguments,
            clean_source_dir=clean_source_dir_for(arguments),
        ),
    )


def call_deepen_telepathy_handoff(
    arguments: dict[str, Any],
    *,
    cwd_arg: Callable[[dict[str, Any]], Path],
    clean_source_dir_for: Callable[[dict[str, Any]], Path],
    runtime_context_for: RuntimeContextFn,
) -> dict[str, Any]:
    card_id = str(arguments.get("card_id") or "").strip()
    if not card_id:
        return missing_input_recovery_card(
            code="missing_telepathy_handoff_card_id",
            message="deepen_telepathy_handoff requires a card_id.",
            tool_name="deepen_telepathy_handoff",
            arguments=arguments,
            required_any=["card_id"],
            safe_next_actions=[
                {
                    "tool_name": "list_telepathy_handoffs",
                    "arguments": {"status": "active", "max": 20},
                },
                _template_tool_action(
                    "deepen_telepathy_handoff",
                    {"card_id": "{card_id_from_list_telepathy_handoffs_cards}"},
                    ["card_id"],
                ),
            ],
        )
    payload = telepathy_handoff_store.deepen_handoff_payload(
        card_id=card_id,
        cwd=cwd_arg(arguments),
        store_path=arguments.get("store_path"),
    )
    return render_profiled_result(
        arguments,
        payload,
        is_error=not bool(payload.get("ok")),
        runtime_provenance_context=runtime_context_for(
            arguments,
            clean_source_dir=clean_source_dir_for(arguments),
        ),
    )
