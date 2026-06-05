"""Owner-specific payload compaction for active-recall lock rows."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from typing import Any, cast

from aippocampus_runtime.core import compact_text, now_utc
from aippocampus_runtime.recall.active_recall_lock import LOCK_SCHEMA_VERSION

COMPACTION_SCHEMA_VERSION = 1
DEAD_LETTER_APPLY_MANIFEST_KIND = "aippocampus_activation_dead_letter_apply_manifest"
ACTIVE_RECALL_LOCK_COMPACTION_MANIFEST_KIND = (
    "aippocampus_active_recall_lock_payload_compaction_manifest"
)
ACTIVE_RECALL_LOCK_KIND = "aippocampus_active_recall_lock"
ACTIVE_RECALL_LOCK_SURFACE_KIND = "active_recall_lock"


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _surface_id_hash(value: Any) -> str:
    return hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()[:16]


def _entry_identity(entry_key: str, entry: Mapping[str, Any]) -> Any:
    return entry.get("lock_id") or entry.get("surface_id") or entry.get("id") or entry_key


def _entry_surface_hash(entry_key: str, entry: Mapping[str, Any]) -> str:
    return _surface_id_hash(_entry_identity(entry_key, entry))


def _source_ref_count(entry: Mapping[str, Any]) -> int:
    refs = entry.get("candidate_refs")
    return len([ref for ref in refs or [] if isinstance(ref, Mapping)]) if isinstance(refs, list) else 0


def _safe_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _dead_letter_update_safety_errors(update: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    if update.get("surface_kind") != ACTIVE_RECALL_LOCK_SURFACE_KIND:
        errors.append("not_active_recall_lock")
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
        "kind": ACTIVE_RECALL_LOCK_COMPACTION_MANIFEST_KIND,
        "ok": False,
        "status": "invalid_manifest",
        "write_mode": "no_write_invalid_manifest",
        "compacted": [],
        "skipped": [
            {
                "skip_reason": "invalid_dead_letter_manifest",
                "surface_kind": ACTIVE_RECALL_LOCK_SURFACE_KIND,
            }
        ],
        "metrics": {
            "dead_lettered_update_count": 0,
            "payload_compacted_count": 0,
            "unsafe_update_count": 0,
            "skipped_count": 1,
            "active_recall_lock_entry_count": 0,
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
                    "surface_kind": ACTIVE_RECALL_LOCK_SURFACE_KIND,
                }
            ],
            unsafe_count,
        )
    for item in manifest.get("skipped") or []:
        if isinstance(item, Mapping) and item.get("surface_kind") == ACTIVE_RECALL_LOCK_SURFACE_KIND:
            skipped.append(
                {
                    "surface_id_hash": item.get("surface_id_hash"),
                    "surface_kind": ACTIVE_RECALL_LOCK_SURFACE_KIND,
                    "skip_reason": item.get("skip_reason") or "dead_letter_manifest_skipped",
                    "protected_reference_count": item.get("protected_reference_count"),
                }
            )
    for update in manifest.get("updates") or []:
        if (
            not isinstance(update, Mapping)
            or update.get("surface_kind") != ACTIVE_RECALL_LOCK_SURFACE_KIND
        ):
            continue
        surface_id_hash = compact_text(str(update.get("surface_id_hash") or ""), 80)
        safety_errors = _dead_letter_update_safety_errors(update)
        if not surface_id_hash or safety_errors:
            unsafe_count += 1
            skipped.append(
                {
                    "surface_id_hash": surface_id_hash or None,
                    "surface_kind": ACTIVE_RECALL_LOCK_SURFACE_KIND,
                    "skip_reason": "unsafe_dead_letter_update",
                    "safety_errors": safety_errors or ["missing_surface_id_hash"],
                }
            )
            continue
        safe_updates[surface_id_hash] = update
    return safe_updates, skipped, unsafe_count


def _compacted_active_recall_lock_entry(
    entry_key: str,
    entry: Mapping[str, Any],
    update: Mapping[str, Any],
    *,
    compacted_at: str,
) -> dict[str, Any]:
    source_ref_count = max(_safe_int(update.get("source_ref_count")), _source_ref_count(entry))
    old_state = compact_text(str(entry.get("state") or "unknown"), 80)
    return {
        "schema_version": entry.get("schema_version") or LOCK_SCHEMA_VERSION,
        "kind": ACTIVE_RECALL_LOCK_KIND,
        # Keep the existing route handle so stale foreground consumers get a
        # deterministic failed state instead of silently recreating a
        # dead-lettered cue from the same route material.
        "lock_id": compact_text(str(_entry_identity(entry_key, entry)), 120),
        "lock_version": max(0, _safe_int(entry.get("lock_version"))),
        "enrichment_generation": max(0, _safe_int(entry.get("enrichment_generation"))),
        "payload_compacted": True,
        "surface_kind": ACTIVE_RECALL_LOCK_SURFACE_KIND,
        "surface_id_hash": _entry_surface_hash(entry_key, entry),
        "status": "payload_compacted",
        "state_transition": f"{old_state}->failed",
        "state": "failed",
        "support_level": "suppressed",
        "lifecycle_action": "payload_compacted",
        "dead_letter_lifecycle_action": "dead_lettered",
        "visibility": "dead_lettered_payload_compacted",
        "source_ref_count": source_ref_count,
        "source_refs_preserved": True,
        "source_reopen_required": True,
        "provenance_pointer_hash": update.get("provenance_pointer_hash"),
        "reason_codes": list(update.get("reason_codes") or []),
        "dead_lettered_at": update.get("applied_at"),
        "compacted_at": compacted_at,
        "rebuild_or_review_note": update.get("rebuild_or_review_note"),
        "consumer_metrics": _safe_dict(entry.get("consumer_metrics")),
        "roi_metrics": _safe_dict(entry.get("roi_metrics")),
        "foreground_use": {
            "default_action": "stay_silent",
            "reason": "payload_compacted_dead_lettered",
            "strong_claim_requires_source_reopen": True,
        },
        "source_boundary": {
            "navigation_only_until_source_reopened": True,
            "payload_compacted_dead_lettered": True,
            "candidate_refs_are_not_serialized": True,
        },
        "privacy_boundary": {
            "raw_activation_payload_serialized": False,
            "source_refs_serialized": False,
            "candidate_identity": "lock_id_route_handle_retained_in_owner_store",
            "public_report_identity": "surface_id_hash_only",
        },
    }


def _compaction_record(tombstone: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "surface_id_hash": tombstone["surface_id_hash"],
        "surface_kind": ACTIVE_RECALL_LOCK_SURFACE_KIND,
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


def _compact_entries(
    entries: Mapping[str, Any],
    safe_updates: Mapping[str, Mapping[str, Any]],
    *,
    compacted_at: str,
) -> tuple[dict[str, Any], list[dict[str, Any]], set[str], int]:
    next_entries: dict[str, Any] = {}
    compacted: list[dict[str, Any]] = []
    matched_hashes: set[str] = set()
    total_entries = 0
    for entry_key, entry in entries.items():
        if not isinstance(entry, Mapping):
            next_entries[entry_key] = entry
            continue
        total_entries += 1
        entry_hash = _entry_surface_hash(str(entry_key), entry)
        update = safe_updates.get(entry_hash)
        if (
            update is None
            or entry.get("kind") != ACTIVE_RECALL_LOCK_KIND
            or entry.get("payload_compacted")
        ):
            next_entries[str(entry_key)] = dict(entry)
            continue
        tombstone = _compacted_active_recall_lock_entry(
            str(entry_key),
            entry,
            update,
            compacted_at=compacted_at,
        )
        next_entries[str(entry_key)] = tombstone
        compacted.append(_compaction_record(tombstone))
        matched_hashes.add(entry_hash)
    return next_entries, compacted, matched_hashes, total_entries


def _report(
    *,
    compacted: list[dict[str, Any]],
    skipped: list[dict[str, Any]],
    safe_update_count: int,
    total_entries: int,
    unsafe_count: int,
) -> dict[str, Any]:
    return {
        "schema_version": COMPACTION_SCHEMA_VERSION,
        "kind": ACTIVE_RECALL_LOCK_COMPACTION_MANIFEST_KIND,
        "ok": True,
        "status": "compacted" if compacted else "no_changes",
        "write_mode": "owner_row_payload_compaction" if compacted else "no_write_no_safe_matches",
        "compacted": compacted,
        "skipped": skipped,
        "metrics": {
            "dead_lettered_update_count": safe_update_count,
            "payload_compacted_count": len(compacted),
            "active_recall_lock_entry_count": total_entries,
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
            "lock_id_route_handle_retained": True,
        },
        "privacy_boundary": {
            "raw_prompt_serialized": False,
            "raw_source_snippets_serialized": False,
            "raw_activation_payload_serialized": False,
            "local_paths_serialized": False,
            "source_refs_serialized": False,
            "candidate_identity": "surface_id_hash_only_in_report",
        },
    }


def compact_active_recall_lock_payloads_from_dead_letter_manifest(
    store: Mapping[str, Any],
    dead_letter_manifest: Mapping[str, Any],
    *,
    compacted_at: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Compact dead-lettered active-recall lock payloads in an owner store."""

    if not isinstance(store, Mapping) or not isinstance(dead_letter_manifest, Mapping):
        return dict(store) if isinstance(store, Mapping) else {}, _invalid_manifest()
    timestamp = compacted_at or now_utc()
    raw_entries = store.get("entries")
    entries: Mapping[str, Any] = (
        cast(Mapping[str, Any], raw_entries) if isinstance(raw_entries, Mapping) else {}
    )
    safe_updates, skipped, unsafe_count = _safe_update_map(dead_letter_manifest)
    next_entries, compacted, matched_hashes, total_entries = _compact_entries(
        entries,
        safe_updates,
        compacted_at=timestamp,
    )
    for surface_id_hash in sorted(set(safe_updates) - matched_hashes):
        skipped.append(
            {
                "surface_id_hash": surface_id_hash,
                "surface_kind": ACTIVE_RECALL_LOCK_SURFACE_KIND,
                "skip_reason": "active_recall_lock_not_found",
            }
        )
    next_store = dict(store)
    next_store["schema_version"] = store.get("schema_version") or LOCK_SCHEMA_VERSION
    next_store["entries"] = next_entries
    if compacted:
        next_store["updated_at"] = now_utc()
        next_store["payload_compaction"] = {
            "compacted_at": timestamp,
            "payload_compacted_count": len(compacted),
        }
    report = _report(
        compacted=compacted,
        skipped=skipped,
        safe_update_count=len(safe_updates),
        total_entries=total_entries,
        unsafe_count=unsafe_count,
    )
    return next_store, report


__all__ = [
    "ACTIVE_RECALL_LOCK_COMPACTION_MANIFEST_KIND",
    "compact_active_recall_lock_payloads_from_dead_letter_manifest",
]
