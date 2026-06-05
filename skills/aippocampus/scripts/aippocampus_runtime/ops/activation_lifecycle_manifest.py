"""Append-only lifecycle manifests for activation surfaces."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

LIFECYCLE_STATE_BY_ACTION = {
    "demote": "demoted",
    "park": "parked",
    "supersede": "superseded",
    "retire": "retired",
}


def apply_activation_lifecycle_manifest_from_rows(
    rows: Sequence[dict[str, Any]],
    *,
    schema_version: int = 1,
) -> dict[str, Any]:
    updates: list[dict[str, Any]] = []
    for row in rows:
        action = str(row.get("pruning_action") or "none")
        if not row["activation_surface"] or action not in LIFECYCLE_STATE_BY_ACTION:
            continue
        updates.append(
            {
                "surface_id": row["surface_id"],
                "surface_kind": row["surface_kind"],
                "conflict_key": row["conflict_key"],
                "action": action,
                "lifecycle_state_after": LIFECYCLE_STATE_BY_ACTION[action],
                "activation_eligible_after": action == "demote",
                "foreground_eligible_after": False,
                "source_refs": row["source_refs"],
                "source_refs_preserved": True,
                "append_only": True,
                "clean_source_mutation": False,
                "truth_status_changed": False,
            }
        )

    return {
        "schema_version": schema_version,
        "kind": "aippocampus_activation_lifecycle_apply_manifest",
        "ok": True,
        "update_count": len(updates),
        "updates": updates,
        "contract": {
            "append_only_lifecycle_update": True,
            "clean_source_mutation": False,
            "truth_status_changed": False,
            "source_refs_preserved": True,
            "source_rows_are_not_pruned": True,
            "raw_prompts_or_snippets_serialized": False,
        },
        "privacy_boundary": {
            "raw_prompt_serialized": False,
            "raw_source_snippets_serialized": False,
            "local_paths_serialized": False,
            "source_refs_are_id_only": True,
        },
    }


__all__ = [
    "LIFECYCLE_STATE_BY_ACTION",
    "apply_activation_lifecycle_manifest_from_rows",
]
