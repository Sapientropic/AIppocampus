"""Foreground cards for vault sync without owning vault writes."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from aippocampus_runtime.contracts import canonical_foreground_action_fields, foreground_shell_action
from aippocampus_runtime.privacy import redact_private_paths, redact_sensitive_values
from aippocampus_runtime.vault.utils import safe_filename


def vault_status_action() -> dict[str, object]:
    return foreground_shell_action(
        action_id="preview_vault_sync_write_set",
        label="Preview vault sync write set",
        command="aippocampus vault sync --dry-run --json",
        why="Inspect what vault sync would write before creating dashboard files or registering a thread.",
        mutation_risk="read_only",
        claim_boundary="vault_dashboard_status_not_memory_evidence",
    )


def vault_write_action() -> dict[str, object]:
    return foreground_shell_action(
        action_id="write_vault_dashboard",
        label="Write vault dashboard",
        command="aippocampus vault sync --write --json",
        why="Create or update local vault/dashboard files only after reviewing the write set.",
        mutation_risk="explicit_local_vault_write",
        claim_boundary="vault_dashboard_status_not_memory_evidence",
    )


def vault_sync_read_only_payload(
    *,
    cwd: Path,
    vault: Path,
    mode: str,
    automation_name: str | None,
    provider: str,
    include_operator_detail: bool,
) -> dict[str, object]:
    thread_slug = safe_filename(cwd.name, "thread")
    primary = vault_status_action()
    payload: dict[str, Any] = {
        "kind": "aippocampus_vault_sync",
        "ok": True,
        "mode": mode,
        "status": "read_only_preview",
        "thread": thread_slug,
        "route_value": "vault_dashboard_is_optional_human_review_surface",
        "current_uncertainty": "write_set_preview_only_health_and_registry_not_refreshed",
        **canonical_foreground_action_fields(primary, safe_next_actions=[primary]),
        "write_actions": [vault_write_action()],
        "write_preview": {
            "will_create_or_update": [
                "vault_root_if_missing",
                "thread_dashboard_notes",
                "dashboard_html_and_assets",
                "obsidian_css_snippet",
                "thread_registry_entry",
            ],
            "will_run_maintenance": False,
            "will_register_thread": False,
            "provider": provider,
            "automation_name_supplied": bool(automation_name),
        },
        "privacy_boundary": {
            "local_paths_included": False,
            "writes_performed": False,
            "raw_private_text_serialized": False,
        },
    }
    if include_operator_detail:
        payload["operator_detail"] = {
            "vault": str(vault),
            "cwd": str(cwd),
            "write_command": "aippocampus vault sync --write --json",
        }
    return redact_sensitive_values(redact_private_paths(payload))
