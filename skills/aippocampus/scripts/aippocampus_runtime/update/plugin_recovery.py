"""Public-safe recovery cards for plugin install failures."""

from __future__ import annotations

from typing import Any


def plugin_failure_code(exc: Exception) -> str:
    if isinstance(exc, PermissionError):
        return "plugin_package_write_denied"
    if isinstance(exc, FileExistsError):
        return "plugin_package_locked"
    if isinstance(exc, OSError):
        text = str(exc).casefold()
        if "being used by another process" in text or "lock" in text:
            return "plugin_package_locked"
        if "permission" in text or "access" in text or "拒绝访问" in text:
            return "plugin_package_write_denied"
        return "plugin_package_write_failed"
    return "plugin_command_failed"


def plugin_install_recovery(exc: Exception, *, operator: bool = False) -> dict[str, Any]:
    code = plugin_failure_code(exc)
    if operator:
        return {
            "kind": "aippocampus_plugin_install_operator_failure",
            "ok": False,
            "error": {
                "code": code,
                "message": "Plugin install failed; operator diagnostics include local paths.",
            },
            "operator_error": {
                "exception_type": type(exc).__name__,
                "message": f"{type(exc).__name__}: {exc}",
            },
            "next_actions": [
                {
                    "label": "retry after clearing file lock or permission issue",
                    "command": "aippocampus plugin install --codex --verify --json",
                    "mutates": True,
                },
                {
                    "label": "check status",
                    "command": "aippocampus plugin status --agent-json",
                    "mutates": False,
                },
            ],
            "privacy_boundary": {
                "operator_json_requested": True,
                "local_paths_may_be_serialized": True,
                "no_private_memory_copied": True,
            },
        }
    return {
        "kind": "aippocampus_plugin_install_recovery",
        "ok": False,
        "error": {
            "code": code,
            "message": (
                "Plugin package install/verify could not write or refresh a local plugin "
                "artifact. Close the host or clear the file lock, then retry."
            ),
            "path": "redacted_local_plugin_package_path",
            "write_boundary": "plugin_package_or_host_cache_only",
        },
        "next_actions": [
            {
                "label": "retry after closing host or clearing lock",
                "command": "aippocampus plugin install --codex --verify --json",
                "mutates": True,
            },
            {
                "label": "inspect plugin status",
                "command": "aippocampus plugin status --agent-json",
                "mutates": False,
            },
            {
                "label": "operator diagnostics with local path detail",
                "command": "aippocampus plugin install --codex --verify --operator-json",
                "mutates": True,
            },
            {
                "label": "rebuild plugin package",
                "command": "python plugins/aippocampus/build_plugin_package.py --repo-root . --json",
                "mutates": True,
            },
        ],
        "rollback_hint": "aippocampus plugin uninstall --codex --dry-run --json",
        "privacy_boundary": {
            "local_paths_serialized": False,
            "python_exception_serialized": False,
            "operator_json_required_for_raw_paths": True,
            "no_private_memory_copied": True,
            "install_write_boundary": "plugin_package_and_codex_plugin_cache_only",
        },
        "claim_boundary": "This recovery card describes local install state, not recall quality or memory contents.",
    }
