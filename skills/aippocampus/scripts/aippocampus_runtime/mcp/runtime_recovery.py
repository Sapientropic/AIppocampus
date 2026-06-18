"""Recovery cards for stale foreground MCP runtime failures."""

from __future__ import annotations

from typing import Any

from aippocampus_runtime.contracts import canonical_foreground_action_fields
from aippocampus_runtime.privacy import redact_private_paths


def foreground_mcp_runtime_recovery_payload(
    tool_name: str,
    exc: BaseException,
) -> dict[str, Any]:
    """Return an actionable, path-redacted card for stale MCP hosts.

    A long-lived host MCP process can keep an older module graph in memory while
    the installed package and a fresh host probe are already current. Keep this
    failure distinct from recall-quality failures so agents reload the foreground
    transport instead of treating source-backed continuity as broken.
    """

    error_summary = redact_private_paths(f"{type(exc).__name__}: {exc}")
    reload_action = {
        "id": "reload_mcp_transport",
        "label": "Reload Codex Desktop or restart the MCP transport",
        "action_type": "host_runtime_refresh",
        "mutation_risk": "host_runtime_refresh_only",
        "claim_boundary": "runtime_recovery_not_source_evidence",
        "why": "Refresh the foreground MCP process before treating this as a recall-quality failure.",
    }
    cli_fallback_action = {
        "id": "cli_recall_fallback_with_cue",
        "label": "Use CLI recall while MCP refreshes",
        "command_template": 'aippocampus agent recall "{cue}" --json',
        "requires": ["cue"],
        "template_only": True,
        "mutation_risk": "read_only",
        "claim_boundary": "no_claim_before_reopen",
        "why": "Use a concrete cue through the local CLI if the foreground MCP connection is stale.",
    }
    return {
        "kind": "aippocampus_foreground_mcp_runtime_recovery",
        "ok": False,
        "status": "foreground_mcp_runtime_mismatch",
        "tool": tool_name,
        "error": {
            "code": "foreground_mcp_runtime_mismatch",
            "message": "The current foreground MCP connection failed inside an agent-native AIppocampus tool.",
            "summary": error_summary,
        },
        "likely_cause": (
            "The foreground MCP process or plugin cache is stale even though the local "
            "runtime and fresh host probe may be current."
        ),
        **canonical_foreground_action_fields(
            reload_action,
            safe_next_actions=[reload_action, cli_fallback_action],
        ),
        "recovery_actions": [
            "reload Codex Desktop or refresh plugin tools",
            "restart the MCP transport if your host exposes that control",
            "aippocampus plugin install --codex --verify --compact-json",
            'aippocampus agent recall "{cue}" --json',
        ],
        "source_boundary": {
            "local_paths_serialized": False,
            "cli_fallback_does_not_prove_foreground_mcp_recovered": True,
        },
    }
