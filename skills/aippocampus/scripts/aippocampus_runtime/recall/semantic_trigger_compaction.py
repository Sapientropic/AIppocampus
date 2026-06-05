"""Owner-specific payload compaction for semantic trigger rows."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping
from typing import Any

from aippocampus_runtime.core import compact_text, now_utc

COMPACTION_SCHEMA_VERSION = 1
DEAD_LETTER_APPLY_MANIFEST_KIND = "aippocampus_activation_dead_letter_apply_manifest"
SEMANTIC_TRIGGER_COMPACTION_MANIFEST_KIND = (
    "aippocampus_semantic_trigger_payload_compaction_manifest"
)
SEMANTIC_TRIGGER_KIND = "aippocampus_semantic_trigger"
SEMANTIC_TRIGGER_SURFACE_KIND = "semantic_trigger"


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _surface_id_hash(value: Any) -> str:
    return hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()[:16]


def _row_identity(row: Mapping[str, Any]) -> Any:
    return row.get("trigger_id") or row.get("surface_id") or row.get("id")


def _row_surface_hash(row: Mapping[str, Any]) -> str:
    return _surface_id_hash(_row_identity(row))


def _source_ref_count(row: Mapping[str, Any]) -> int:
    refs = row.get("source_refs")
    return len([ref for ref in refs or [] if isinstance(ref, Mapping)]) if isinstance(refs, list) else 0


def _dead_letter_update_safety_errors(update: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    if update.get("surface_kind") != SEMANTIC_TRIGGER_SURFACE_KIND:
        errors.append("not_semantic_trigger")
    if update.get("lifecycle_action") != "dead_lettered":
        errors.append("not_dead_lettered")
    if _safe_int(update.get("source_ref_count")) <= 0:
        errors.append("missing_source_ref_count")
    if not update.get("provenance_pointer_hash"):
        errors.append("missing_provenance_pointer_hash")
    if update.get("source_refs_preserved") is not True:
        errors.append("source_refs_not_marked_preserved")
    if update.get("clean_source_mutation"):
        errors.append("clean_source_mutation_attempt")
    if update.get("truth_status_changed"):
        errors.append("truth_status_change_attempt")
    if _safe_int(update.get("protected_reference_count")) > 0:
        errors.append("protected_reference_present")
    if not update.get("reason_codes"):
        errors.append("missing_reason_codes")
    if not update.get("rebuild_or_review_note"):
        errors.append("missing_rebuild_or_review_note")
    return errors


def _invalid_manifest() -> dict[str, Any]:
    return {
        "schema_version": COMPACTION_SCHEMA_VERSION,
        "kind": SEMANTIC_TRIGGER_COMPACTION_MANIFEST_KIND,
        "ok": False,
        "status": "invalid_manifest",
        "write_mode": "no_write_invalid_manifest",
        "compacted": [],
        "skipped": [
            {
                "skip_reason": "invalid_dead_letter_manifest",
                "surface_kind": SEMANTIC_TRIGGER_SURFACE_KIND,
            }
        ],
        "metrics": {
            "dead_lettered_update_count": 0,
            "payload_compacted_count": 0,
            "unsafe_update_count": 0,
            "skipped_count": 1,
            "semantic_trigger_row_count": 0,
        },
    }


def _safe_update_map(
    manifest: Mapping[str, Any],
) -> tuple[dict[str, Mapping[str, Any]], list[dict[str, Any]], int]:
    safe_updates: dict[str, Mapping[str, Any]] = {}
    skipped: list[dict[str, Any]] = []
    unsafe_count = 0
    if manifest.get("kind") != DEAD_LETTER_APPLY_MANIFEST_KIND:
        return (
            safe_updates,
            [
                {
                    "skip_reason": "unexpected_manifest_kind",
                    "manifest_kind": compact_text(str(manifest.get("kind") or ""), 120),
                    "surface_kind": SEMANTIC_TRIGGER_SURFACE_KIND,
                }
            ],
            unsafe_count,
        )
    for item in manifest.get("skipped") or []:
        if isinstance(item, Mapping) and item.get("surface_kind") == SEMANTIC_TRIGGER_SURFACE_KIND:
            skipped.append(
                {
                    "surface_id_hash": item.get("surface_id_hash"),
                    "surface_kind": SEMANTIC_TRIGGER_SURFACE_KIND,
                    "skip_reason": item.get("skip_reason") or "dead_letter_manifest_skipped",
                    "protected_reference_count": item.get("protected_reference_count"),
                }
            )
    for update in manifest.get("updates") or []:
        if (
            not isinstance(update, Mapping)
            or update.get("surface_kind") != SEMANTIC_TRIGGER_SURFACE_KIND
        ):
            continue
        surface_id_hash = compact_text(str(update.get("surface_id_hash") or ""), 80)
        safety_errors = _dead_letter_update_safety_errors(update)
        if not surface_id_hash or safety_errors:
            unsafe_count += 1
            skipped.append(
                {
                    "surface_id_hash": surface_id_hash or None,
                    "surface_kind": SEMANTIC_TRIGGER_SURFACE_KIND,
                    "skip_reason": "unsafe_dead_letter_update",
                    "safety_errors": safety_errors or ["missing_surface_id_hash"],
                }
            )
            continue
        safe_updates[surface_id_hash] = update
    return safe_updates, skipped, unsafe_count


def _compacted_semantic_trigger_row(
    row: Mapping[str, Any],
    update: Mapping[str, Any],
    *,
    compacted_at: str,
) -> dict[str, Any]:
    source_ref_count = max(_safe_int(update.get("source_ref_count")), _source_ref_count(row))
    return {
        "schema_version": row.get("schema_version") or COMPACTION_SCHEMA_VERSION,
        "kind": SEMANTIC_TRIGGER_KIND,
        "payload_compacted": True,
        "surface_kind": SEMANTIC_TRIGGER_SURFACE_KIND,
        "surface_id_hash": _row_surface_hash(row),
        "status": "payload_compacted",
        "lifecycle_action": "payload_compacted",
        "dead_letter_lifecycle_action": "dead_lettered",
        "visibility": "dead_lettered_payload_compacted",
        "source_ref_count": source_ref_count,
        "source_refs_preserved": True,
        "provenance_pointer_hash": update.get("provenance_pointer_hash"),
        "reason_codes": list(update.get("reason_codes") or []),
        "dead_lettered_at": update.get("applied_at"),
        "compacted_at": compacted_at,
        "rebuild_or_review_note": update.get("rebuild_or_review_note"),
        "foreground_use": {
            "default_action": "stay_silent",
            "reason": "payload_compacted_dead_lettered",
            "strong_claim_requires_source_reopen": True,
        },
        "privacy_boundary": {
            "raw_activation_payload_serialized": False,
            "source_refs_serialized": False,
            "candidate_identity": "surface_id_hash_only",
        },
    }


def _compaction_record(tombstone: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "surface_id_hash": tombstone["surface_id_hash"],
        "surface_kind": SEMANTIC_TRIGGER_SURFACE_KIND,
        "lifecycle_action": "payload_compacted",
        "dead_letter_lifecycle_action": tombstone.get("dead_letter_lifecycle_action"),
        "source_ref_count": tombstone.get("source_ref_count"),
        "source_refs_preserved": True,
        "provenance_pointer_hash": tombstone.get("provenance_pointer_hash"),
        "reason_codes": tombstone.get("reason_codes") or [],
        "dead_lettered_at": tombstone.get("dead_lettered_at"),
        "compacted_at": tombstone.get("compacted_at"),
        "rebuild_or_review_note": tombstone.get("rebuild_or_review_note"),
    }


def _compact_rows(
    rows: Iterable[Mapping[str, Any]],
    safe_updates: Mapping[str, Mapping[str, Any]],
    *,
    compacted_at: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], set[str], int]:
    next_rows: list[dict[str, Any]] = []
    compacted: list[dict[str, Any]] = []
    matched_hashes: set[str] = set()
    total_rows = 0
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        total_rows += 1
        row_hash = _row_surface_hash(row)
        update = safe_updates.get(row_hash)
        if (
            update is None
            or row.get("kind") != SEMANTIC_TRIGGER_KIND
            or row.get("payload_compacted")
        ):
            next_rows.append(dict(row))
            continue
        tombstone = _compacted_semantic_trigger_row(row, update, compacted_at=compacted_at)
        next_rows.append(tombstone)
        compacted.append(_compaction_record(tombstone))
        matched_hashes.add(row_hash)
    return next_rows, compacted, matched_hashes, total_rows


def _report(
    *,
    compacted: list[dict[str, Any]],
    skipped: list[dict[str, Any]],
    safe_update_count: int,
    total_rows: int,
    unsafe_count: int,
) -> dict[str, Any]:
    return {
        "schema_version": COMPACTION_SCHEMA_VERSION,
        "kind": SEMANTIC_TRIGGER_COMPACTION_MANIFEST_KIND,
        "ok": True,
        "status": "compacted" if compacted else "no_changes",
        "write_mode": "owner_row_payload_compaction" if compacted else "no_write_no_safe_matches",
        "compacted": compacted,
        "skipped": skipped,
        "metrics": {
            "dead_lettered_update_count": safe_update_count,
            "payload_compacted_count": len(compacted),
            "semantic_trigger_row_count": total_rows,
            "unsafe_update_count": unsafe_count,
            "skipped_count": len(skipped),
        },
        "contract": {
            "owner_specific_payload_compaction": True,
            "dead_letter_manifest_required": True,
            "clean_source_mutation": False,
            "raw_rollout_mutation": False,
            "truth_status_changed": False,
            "source_refs_preserved": True,
            "foreground_hook_mutation": False,
            "protected_references_skip_apply": True,
            "row_transform_only": True,
        },
        "privacy_boundary": {
            "raw_prompt_serialized": False,
            "raw_source_snippets_serialized": False,
            "raw_activation_payload_serialized": False,
            "local_paths_serialized": False,
            "source_refs_serialized": False,
            "candidate_identity": "surface_id_hash_only",
        },
    }


def compact_semantic_trigger_payloads_from_dead_letter_manifest(
    rows: Iterable[Mapping[str, Any]],
    dead_letter_manifest: Mapping[str, Any],
    *,
    compacted_at: str | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Return transformed semantic-trigger rows plus a public-safe report.

    The generic activation audit emits hash-only lifecycle manifests. This
    owner-specific transform can match those hashes to `trigger_id` values, but
    its report never serializes raw aliases, activation cues, source refs, or
    local paths. A caller that owns `semantic_triggers.jsonl` may persist the
    returned rows during maintenance; foreground hooks must only read the
    already-compacted tombstones and skip them.
    """

    if not isinstance(dead_letter_manifest, Mapping):
        return [dict(row) for row in rows if isinstance(row, Mapping)], _invalid_manifest()
    timestamp = compacted_at or now_utc()
    safe_updates, skipped, unsafe_count = _safe_update_map(dead_letter_manifest)
    next_rows, compacted, matched_hashes, total_rows = _compact_rows(
        rows,
        safe_updates,
        compacted_at=timestamp,
    )
    for surface_id_hash in sorted(set(safe_updates) - matched_hashes):
        skipped.append(
            {
                "surface_id_hash": surface_id_hash,
                "surface_kind": SEMANTIC_TRIGGER_SURFACE_KIND,
                "skip_reason": "semantic_trigger_row_not_found",
            }
        )
    return next_rows, _report(
        compacted=compacted,
        skipped=skipped,
        safe_update_count=len(safe_updates),
        total_rows=total_rows,
        unsafe_count=unsafe_count,
    )


__all__ = [
    "SEMANTIC_TRIGGER_COMPACTION_MANIFEST_KIND",
    "compact_semantic_trigger_payloads_from_dead_letter_manifest",
]
