"""Central MCP protocol/version policy for the local AIppocampus server."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

MCP_SERVER_NAME = "aippocampus"
MCP_SERVER_VERSION = "0.1.0"
MCP_DEFAULT_PROTOCOL_VERSION = "2025-11-25"
MCP_SUPPORTED_PROTOCOL_VERSIONS = (MCP_DEFAULT_PROTOCOL_VERSION,)

SDK_MIGRATION_NOTE = {
    "status": "parked",
    "recommendation": (
        "Keep this deterministic stdio server as the conformance owner; evaluate "
        "an SDK migration only after initialize/tools-list/tools-call parity and "
        "compact foreground boundaries are covered by the same smoke."
    ),
    "do_not_do_now": "Do not migrate to an SDK in this MCP/typed-boundary slice.",
}


def negotiated_protocol_version(params: Mapping[str, Any]) -> str:
    """Return the protocol version this lightweight server should report.

    MCP hosts initiate with their preferred protocol version. For this local
    read-mostly server, echoing the requested value preserves host compatibility
    while the default remains the deterministic smoke baseline.
    """

    requested = str(params.get("protocolVersion") or "").strip()
    return requested or MCP_DEFAULT_PROTOCOL_VERSION


def initialize_result(params: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "protocolVersion": negotiated_protocol_version(params),
        "capabilities": {"tools": {}},
        "serverInfo": {"name": MCP_SERVER_NAME, "version": MCP_SERVER_VERSION},
    }


def protocol_policy_payload() -> dict[str, Any]:
    return {
        "server": {
            "name": MCP_SERVER_NAME,
            "version": MCP_SERVER_VERSION,
        },
        "protocol": {
            "default": MCP_DEFAULT_PROTOCOL_VERSION,
            "supported": list(MCP_SUPPORTED_PROTOCOL_VERSIONS),
            "initialize_policy": "echo_requested_or_default",
        },
        "sdk_migration": dict(SDK_MIGRATION_NOTE),
    }


__all__ = [
    "MCP_DEFAULT_PROTOCOL_VERSION",
    "MCP_SERVER_NAME",
    "MCP_SERVER_VERSION",
    "MCP_SUPPORTED_PROTOCOL_VERSIONS",
    "SDK_MIGRATION_NOTE",
    "initialize_result",
    "negotiated_protocol_version",
    "protocol_policy_payload",
]
