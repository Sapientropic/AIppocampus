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
                command="aippocampus storage gc --apply --class rebuildable --summary-json --cwd .",
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
