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
        "choices": {
            "bundle_import": {
                "label": "private AIppocampus bundle import",
                "command_template": 'aippocampus import "{bundle_zip}" --dest "{destination_folder}"',
                "template_only": True,
                "requires": ["bundle_zip", "destination_folder"],
                "boundary": "imports an explicit local AIppocampus bundle; paths stay redacted by default",
            },
            "conversation_import": {
                "label": "generic conversation transcript import",
                "preview_command_template": (
                    'aippocampus import conversation --format generic-jsonl --input "{input_path}" --dry-run --json'
                ),
                "write_command_template": (
                    'aippocampus import conversation --format generic-jsonl --input "{input_path}"'
                ),
                "requires": ["input_path"],
                "boundary": "preview first; the input transcript stays local operator material",
            },
        },
        "write_actions": write_actions,
        **canonical_foreground_action_fields(
            safe_actions[0],
            safe_next_actions=safe_actions,
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
    return foreground_chooser_card(
        kind="aippocampus_hooks_chooser",
        decision="choose a hook family before checking, installing, or rolling back",
        choices=[
            foreground_shell_action(
                action_id="check_prompt_hook",
                label="Check prompt hook",
                command="aippocampus hooks prompt status --last --json",
                why="Prompt hooks are the Codex UserPromptSubmit recall affordance, not the whole hook family.",
                mutation_risk="read_only",
                claim_boundary="host_setup_not_memory_evidence",
            ),
            foreground_shell_action(
                action_id="check_lifecycle_hooks",
                label="Check lifecycle hooks",
                command="aippocampus hooks lifecycle status --json",
                why="Lifecycle hooks cover bounded start/stop/compact maintenance.",
                mutation_risk="read_only",
                claim_boundary="host_setup_not_memory_evidence",
            ),
            foreground_shell_action(
                action_id="check_action_hints",
                label="Check action-time hints",
                command="aippocampus hooks action status --json",
                why=(
                    "Action-time hints are recommended trusted-Codex setup, "
                    "but remain fail-open navigation guidance."
                ),
                mutation_risk="read_only",
                claim_boundary="host_setup_not_memory_evidence",
            ),
            foreground_shell_action(
                action_id="check_claude_code_hooks",
                label="Check Claude Code hook helper",
                command="aippocampus hooks claude-code status --json",
                why="Claude Code has a host-specific status/dry-run helper rather than Codex hook installation.",
                mutation_risk="read_only",
                claim_boundary="host_setup_not_memory_evidence",
            ),
        ],
    )


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
        decision="choose dry-run preview or explicit rebuildable cleanup apply",
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
            foreground_shell_action(
                action_id="apply_rebuildable_storage_gc_after_review",
                label="Apply rebuildable cleanup after review",
                command="aippocampus storage gc --apply --class rebuildable --include-active --summary-json --cwd .",
                why="Apply is explicit and limited to candidates that pass rebuildability and safety checks.",
                mutation_risk="explicit_local_delete_of_rebuildable_cache",
                claim_boundary="operator_action_not_source_evidence",
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
