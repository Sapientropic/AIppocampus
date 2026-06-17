"""Foreground recovery cards for parent and ambiguous CLI commands."""

from __future__ import annotations

from typing import Any

from aippocampus_runtime.contracts import (
    foreground_chooser_card,
    foreground_shell_action,
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
