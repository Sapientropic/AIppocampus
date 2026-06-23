"""Profile-aware MCP result rendering.

MCP compact output is consumed by foreground agents as working context. Keep
operator proof and runtime diagnostics behind full/detail profiles here so
individual handlers do not reintroduce debug-console payloads by hand.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from aippocampus_runtime.mcp.compact_profile import compact_mcp_tool_result
from aippocampus_runtime.mcp.public_projection import detail_arg, public_payload
from aippocampus_runtime.mcp.runtime_provenance import mcp_runtime_provenance


@dataclass(frozen=True)
class RuntimeProvenanceContext:
    clean_source_dir: Path | None = None
    registry_dir: Path | None = None


PayloadProjector = Callable[[dict[str, Any]], dict[str, Any]]


def compact_profile_requested(arguments: Mapping[str, Any]) -> bool:
    return detail_arg(dict(arguments)) == "compact" and not arguments.get("include_private_paths")


def _dict_payload(payload: Any) -> dict[str, Any]:
    return dict(payload) if isinstance(payload, dict) else {"result": payload}


def _full_profile_payload(
    payload: Any,
    *,
    output_boundary: str | None = None,
    runtime_provenance_context: RuntimeProvenanceContext | None = None,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    result = _dict_payload(payload)
    result["detail"] = "full"
    if output_boundary:
        result.setdefault("output_boundary", output_boundary)
    if runtime_provenance_context is not None:
        result["runtime_provenance"] = mcp_runtime_provenance(
            arguments,
            clean_source_dir=runtime_provenance_context.clean_source_dir,
            registry_dir=runtime_provenance_context.registry_dir,
        )
    return result


def render_profiled_result(
    arguments: dict[str, Any],
    payload: Any,
    *,
    is_error: bool = False,
    compact_projector: PayloadProjector | None = None,
    full_output_boundary: str | None = None,
    runtime_provenance_context: RuntimeProvenanceContext | None = None,
) -> dict[str, Any]:
    """Render one MCP result through the selected product/detail profile."""

    if compact_profile_requested(arguments):
        projected = (
            compact_projector(_dict_payload(payload))
            if compact_projector is not None
            else _dict_payload(payload)
        )
    else:
        projected = _full_profile_payload(
            payload,
            output_boundary=full_output_boundary,
            runtime_provenance_context=runtime_provenance_context,
            arguments=arguments,
        )
    return compact_mcp_tool_result(public_payload(arguments, projected), is_error=is_error)
