"""Compact agent-facing update status projection facade."""

from __future__ import annotations

from typing import Any

from aippocampus_runtime.update.agent_status_summary_core import agent_callable_host_probe_ok

__all__ = ["agent_callable_host_probe_ok", "compact_agent_status_report"]


# aippocampus-stage-map: normalize surfaces -> collect actions -> project ambient status -> render compact payload.
def compact_agent_status_report(
    report: dict[str, Any],
    *,
    schema_version: int,
) -> dict[str, Any]:
    from aippocampus_runtime.update.agent_status_summary_stages import (
        build_compact_agent_status_report,
    )

    return build_compact_agent_status_report(report, schema_version=schema_version)
