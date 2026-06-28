"""Foreground recovery cards for parent and ambiguous CLI commands."""

from __future__ import annotations

from typing import Any

from aippocampus_runtime.contracts import (
    canonical_foreground_action_fields,
    foreground_chooser_card,
    foreground_shell_action,
    foreground_template_action,
)


def import_recovery_payload() -> dict[str, Any]:
    safe_actions = [
        foreground_template_action(
            action_id="preview_conversation_import",
            label="Preview a generic conversation transcript",
            command_template=(
                "aippocampus import conversation --format generic-jsonl "
                '--input "{input_path}" --dry-run --json'
            ),
            requires=["input_path"],
            why="Validate the transcript before any registry write.",
            mutation_risk="read_only_preview",
            claim_boundary="import_preview_not_source_truth",
        ),
        foreground_shell_action(
            action_id="open_import_help",
            label="Open import help",
            command="aippocampus import --help",
            why="Use help when choosing between bundle transfer and conversation transcript intake.",
            mutation_risk="read_only",
            claim_boundary="operator_import_not_source_claim",
        ),
    ]
    write_actions = [
        foreground_template_action(
            action_id="import_private_bundle",
            label="Import a private AIppocampus bundle",
            command_template='aippocampus import "{bundle_zip}" --dest "{destination_folder}"',
            requires=["bundle_zip", "destination_folder"],
            why="Use only for an explicit local AIppocampus bundle transfer.",
            mutation_risk="explicit_local_import_write",
            claim_boundary="operator_transfer_not_memory_claim",
        ),
        foreground_template_action(
            action_id="write_conversation_import_after_preview",
            label="Register the transcript after preview",
            command_template='aippocampus import conversation --format generic-jsonl --input "{input_path}"',
            requires=["input_path"],
            why="Write is explicit and should follow a reviewed dry-run preview.",
            mutation_risk="explicit_registry_write",
            claim_boundary="operator_import_not_source_claim",
        ),
    ]
    return {
        "kind": "aippocampus_import_recovery",
        "ok": True,
        "status": "choose_action",
        "surface_class": "foreground_chooser_card",
        "decision": "preview conversation import first, or explicitly choose a write path",
        "choices": [*safe_actions, *write_actions],
        "write_actions": write_actions,
        **canonical_foreground_action_fields(
            safe_actions[0],
            safe_next_actions=safe_actions,
            max_safe_next_actions=1,
            safe_next_read_only_only=True,
        ),
        "safety": {
            "no_write_happened": True,
            "preview_before_write": True,
            "explicit_input_required": True,
        },
        "write_boundary": {
            "written": False,
            "no_write_happened": True,
            "explicit_write_required": True,
        },
        "privacy_boundary": {
            "raw_local_paths_emitted": False,
            "local_path_redaction_required": True,
            "private_transcript_material_loaded": False,
        },
    }


def plugin_chooser_payload() -> dict[str, Any]:
    return foreground_chooser_card(
        kind="aippocampus_plugin_chooser",
        decision="check plugin status before choosing any install or rollback write",
        choices=[
            foreground_shell_action(
                action_id="check_codex_plugin_status",
                label="Check Codex plugin status",
                command="aippocampus plugin status --json",
                why="Read current freshness/callability without changing local plugin files.",
                mutation_risk="read_only",
                claim_boundary="host_status_not_memory_evidence",
            ),
            foreground_shell_action(
                action_id="install_or_refresh_codex_plugin",
                label="Install or refresh Codex plugin",
                command="aippocampus plugin install --codex --verify --json",
                why=(
                    "Run only after the status check or an explicit setup request; "
                    "it refreshes local Codex plugin files."
                ),
                mutation_risk="explicit_local_plugin_write",
                claim_boundary="host_setup_not_memory_evidence",
            ),
            foreground_shell_action(
                action_id="preview_codex_plugin_uninstall",
                label="Preview explicit rollback",
                command="aippocampus plugin uninstall --codex --dry-run --json",
                why="Rollback stays preview-first and should not be confused with setup.",
                mutation_risk="read_only_preview_of_delete",
                claim_boundary="host_setup_not_memory_evidence",
            ),
        ],
    )


def hooks_chooser_payload() -> dict[str, Any]:
    primary = foreground_shell_action(
        action_id="check_prompt_hook_readiness",
        label="Check prompt hook readiness",
        command="aippocampus hooks prompt status --last --json",
        why=(
            "Prompt hook status is the smallest useful readiness probe for whether "
            "foreground recall can run from UserPromptSubmit."
        ),
        mutation_risk="read_only",
        claim_boundary="host_setup_not_memory_evidence",
    )
    lifecycle = foreground_shell_action(
        action_id="check_lifecycle_hook_readiness",
        label="Check lifecycle hook readiness",
        command="aippocampus hooks lifecycle status --json",
        why="Use after prompt readiness when start/stop/compact maintenance is the question.",
        mutation_risk="read_only",
        claim_boundary="host_setup_not_memory_evidence",
    )
    return {
        "kind": "aippocampus_hooks_readiness",
        "ok": True,
        "status": "aggregate_probe_available",
        "surface_class": "foreground_chooser_card",
        "decision": "check aggregate hook readiness before choosing a hook family",
        "hook_readiness_contract": "hooks-readiness-v1",
        "aggregate_state": "callable_probe_available",
        "ambient_state": "callable",
        "families": ["prompt", "lifecycle", "action", "claude_code"],
        **canonical_foreground_action_fields(
            primary,
            safe_next_actions=[primary, lifecycle],
            max_safe_next_actions=1,
            safe_next_read_only_only=True,
        ),
        "detail_actions": [
            foreground_shell_action(
                action_id="check_action_hints",
                label="Check action-time hints",
                command="aippocampus hooks action status --json",
                why="Action hints are host-specific guidance; inspect after aggregate readiness.",
                mutation_risk="read_only",
                claim_boundary="host_setup_not_memory_evidence",
            ),
            foreground_shell_action(
                action_id="check_claude_code_hooks",
                label="Check Claude Code hook helper",
                command="aippocampus hooks claude-code status --json",
                why="Claude Code has a host-specific dry-run/status helper.",
                mutation_risk="read_only",
                claim_boundary="host_setup_not_memory_evidence",
            ),
        ],
        "write_boundary": {
            "written": False,
            "no_write_happened": True,
            "explicit_write_required": True,
        },
    }


def plugin_status_payload() -> dict[str, Any]:
    primary = foreground_shell_action(
        action_id="check_mcp_tool_callability",
        label="Check MCP tool callability",
        command="aippocampus mcp status --json",
        why=(
            "This is the shortest read-only probe for whether the installed "
            "AIppocampus plugin can expose callable MCP tools."
        ),
        mutation_risk="read_only",
        claim_boundary="host_status_not_memory_evidence",
    )
    return {
        "kind": "aippocampus_plugin_status_card",
        "ok": True,
        "status": "callability_probe_available",
        "surface_class": "foreground_readiness_card",
        "decision": "check MCP callability; install or refresh only after a failed probe",
        "plugin_status_contract": "plugin-callability-v1",
        "status_scope": "local_cli_and_mcp_probe",
        "plugin_installed": "unknown_without_host_probe",
        "skill_available": True,
        "mcp_tools_visible": "check_with_foreground_action",
        "mcp_tools_callable": "check_with_foreground_action",
        "callability": {
            "installed": "unknown_without_host_probe",
            "cli_callable": True,
            "mcp_tools_visible": "check_with_foreground_action",
            "mcp_tools_callable": "check_with_foreground_action",
        },
        **canonical_foreground_action_fields(
            primary,
            safe_next_actions=[],
            max_safe_next_actions=1,
            safe_next_read_only_only=True,
        ),
        "manage_command": "aippocampus plugin install --codex --verify --json",
        "operator_detail_command": "aippocampus plugin status --operator-json",
        "write_boundary": {
            "written": False,
            "no_write_happened": True,
            "explicit_write_required": True,
        },
    }


def sync_chooser_payload() -> dict[str, Any]:
    return foreground_chooser_card(
        kind="aippocampus_sync_chooser",
        decision="choose a read-only sync status before push or pull",
        choices=[
            foreground_shell_action(
                action_id="check_sync_status",
                label="Check local sync status",
                command="aippocampus sync status --json",
                why="Parent sync commands should not imply push/pull or object-store writes.",
                mutation_risk="read_only",
                claim_boundary="operator_diagnostic_not_source_evidence",
            ),
            foreground_shell_action(
                action_id="check_object_sync_status",
                label="Check object sync status",
                command="aippocampus object-sync status --json",
                why="Use this when an object-storage backend is involved.",
                mutation_risk="read_only",
                claim_boundary="operator_diagnostic_not_source_evidence",
            ),
        ],
    )


def doctor_chooser_payload() -> dict[str, Any]:
    return foreground_chooser_card(
        kind="aippocampus_doctor_chooser",
        status="needs_subcommand",
        decision="choose the local diagnostic question",
        choices=[
            foreground_shell_action(
                action_id="preflight",
                label="Check host prerequisites",
                command="aippocampus doctor preflight --json",
                why="Use first on a new or brittle host before install, sync, hooks, or recall setup.",
                mutation_risk="read_only",
                claim_boundary="host_setup_not_memory_evidence",
            ),
            foreground_shell_action(
                action_id="provider",
                label="Check optional provider visibility",
                command="aippocampus doctor provider --json",
                why="Use when model/provider key visibility or semantic-worker availability is the question.",
                mutation_risk="read_only",
                claim_boundary="operator_diagnostic_not_source_evidence",
            ),
            foreground_shell_action(
                action_id="spend",
                label="Review spend/yield diagnostics",
                command="aippocampus doctor spend --json",
                why="Use when local model spend, yield, or blocked warm work needs review.",
                mutation_risk="read_only",
                claim_boundary="operator_diagnostic_not_source_evidence",
            ),
            foreground_shell_action(
                action_id="config",
                label="Audit registered configuration",
                command="aippocampus doctor config --compact-json",
                why="Use when checking configured AIPPOCAMPUS_* knobs without printing values.",
                mutation_risk="read_only",
                claim_boundary="operator_diagnostic_not_source_evidence",
            ),
        ],
    )


def smoke_chooser_payload() -> dict[str, Any]:
    return foreground_chooser_card(
        kind="aippocampus_smoke_chooser",
        status="needs_subcommand",
        decision="choose a bounded smoke runner",
        choices=[
            foreground_template_action(
                action_id="recall_funnel",
                label="Run progressive recall funnel smoke",
                command_template='aippocampus smoke recall-funnel "{cue}" --json',
                requires=["cue"],
                why=(
                    "Use for a bounded diagnostic of recall_context -> deepen and "
                    "ordinary agent recall -> deepen usefulness."
                ),
                mutation_risk="read_only",
                claim_boundary="smoke_diagnostic_not_source_evidence",
            ),
            foreground_template_action(
                action_id="ordinary_agent_recall",
                label="Use ordinary continuity path",
                command_template='aippocampus agent recall "{cue}" --json',
                requires=["cue"],
                why="Use for normal foreground continuity work instead of a smoke diagnostic.",
                mutation_risk="read_only",
                claim_boundary="no_claim_before_reopen",
            ),
        ],
    )


def logs_chooser_payload() -> dict[str, Any]:
    return foreground_chooser_card(
        kind="aippocampus_logs_chooser",
        status="needs_subcommand",
        decision="inspect log status before rotating local audit artifacts",
        choices=[
            foreground_shell_action(
                action_id="status",
                label="Inspect log retention status",
                command="aippocampus logs status --json",
                why="Read-only status never prints log contents.",
                mutation_risk="read_only",
                claim_boundary="operator_diagnostic_not_source_evidence",
            ),
            foreground_shell_action(
                action_id="rotate_dry_run",
                label="Preview bounded rotation",
                command="aippocampus logs rotate --plan --json",
                why="Use before any write to see which known artifacts would rotate.",
                mutation_risk="read_only",
                claim_boundary="operator_diagnostic_not_source_evidence",
            ),
            foreground_shell_action(
                action_id="rotate_apply",
                label="Apply bounded rotation explicitly",
                command="aippocampus logs rotate --apply --json",
                why="Write mode is explicit and should only follow a reviewed plan.",
                mutation_risk="explicit_local_log_write",
                claim_boundary="operator_diagnostic_not_source_evidence",
            ),
        ],
    )


def storage_chooser_payload() -> dict[str, Any]:
    return foreground_chooser_card(
        kind="aippocampus_storage_chooser",
        decision="choose an explicit storage action",
        choices=[
            foreground_shell_action(
                action_id="inspect_storage_gc_candidates",
                label="Preview rebuildable-cache cleanup",
                command="aippocampus storage gc --dry-run --json --top 1 --cwd .",
                why="Parent storage commands should lead to a bounded audit before any delete path.",
                mutation_risk="read_only",
                claim_boundary="operator_diagnostic_not_source_evidence",
            ),
            foreground_shell_action(
                action_id="inspect_storage_gc_summary",
                label="Preview cleanup summary",
                command="aippocampus storage gc --dry-run --summary-json --cwd .",
                why="Use the summary when deciding whether storage pressure is real for this workspace.",
                mutation_risk="read_only",
                claim_boundary="operator_diagnostic_not_source_evidence",
            ),
        ],
    )


def storage_gc_recovery_payload() -> dict[str, Any]:
    return foreground_chooser_card(
        kind="aippocampus_storage_gc_recovery",
        decision="choose a dry-run preview before any storage cleanup apply",
        choices=[
            foreground_shell_action(
                action_id="preview_bounded_storage_gc",
                label="Preview bounded cleanup candidates",
                command="aippocampus storage gc --dry-run --json --top 1 --cwd .",
                why="`storage gc --json` without --dry-run or --apply is ambiguous; preview first.",
                mutation_risk="read_only",
                claim_boundary="operator_diagnostic_not_source_evidence",
            ),
            foreground_shell_action(
                action_id="preview_storage_gc_summary",
                label="Preview cleanup summary",
                command="aippocampus storage gc --dry-run --summary-json --cwd .",
                why="Use this when a compact no-write decision card is enough.",
                mutation_risk="read_only",
                claim_boundary="operator_diagnostic_not_source_evidence",
            ),
        ],
    )


def object_sync_chooser_payload() -> dict[str, Any]:
    return foreground_chooser_card(
        kind="aippocampus_object_sync_chooser",
        decision="choose read-only object sync status before push, pull, or repair",
        choices=[
            foreground_shell_action(
                action_id="check_object_sync_status",
                label="Check object sync status",
                command="aippocampus object-sync status --json",
                why="Object-sync parent commands should lead to the object-store readiness card.",
                mutation_risk="read_only",
                claim_boundary="operator_diagnostic_not_source_evidence",
            ),
            foreground_shell_action(
                action_id="preview_object_sync_push",
                label="Preview object sync push",
                command="aippocampus object-sync push --plan --json",
                why="Preview local registry to object store before any object-store write.",
                mutation_risk="read_only",
                claim_boundary="operator_diagnostic_not_source_evidence",
            ),
            foreground_shell_action(
                action_id="preview_object_sync_pull",
                label="Preview object sync pull",
                command="aippocampus object-sync pull --plan --json",
                why="Preview object store to local registry before any local write.",
                mutation_risk="read_only",
                claim_boundary="operator_diagnostic_not_source_evidence",
            ),
        ],
    )
