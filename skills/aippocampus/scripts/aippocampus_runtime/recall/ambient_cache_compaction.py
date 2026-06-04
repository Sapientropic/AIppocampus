"""Owner-specific payload compaction for the ambient thread cache."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from aippocampus_runtime.core import compact_text, now_utc
from aippocampus_runtime.recall.ambient_cache import (
    CACHE_SCHEMA_VERSION,
    _load_cache,
    _related_fingerprint,
    _safe_int,
    _source_ref_fingerprints,
    _write_cache,
)
from aippocampus_runtime.registry.api import unique_preserve

COMPACTION_SCHEMA_VERSION = 1
DEAD_LETTER_APPLY_MANIFEST_KIND = "aippocampus_activation_dead_letter_apply_manifest"
AMBIENT_CACHE_COMPACTION_MANIFEST_KIND = "aippocampus_ambient_cache_payload_compaction_manifest"


def _surface_id_hash(value: Any) -> str:
    return hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()[:16]


def _ambient_card_related_fingerprints(card: dict[str, Any]) -> set[str]:
    values: set[str] = set(_source_ref_fingerprints([card]))
    if card.get("card_id"):
        values.add(_related_fingerprint("card", card.get("card_id")))
    return {value for value in values if value}


def _dead_letter_update_safety_errors(update: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if update.get("surface_kind") != "ambient_card":
        errors.append("not_ambient_card")
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


def _compacted_ambient_card(
    card: dict[str, Any],
    update: dict[str, Any],
    *,
    compacted_at: str,
) -> dict[str, Any]:
    source_ref_fingerprints = _source_ref_fingerprints([card])
    source_ref_count = max(_safe_int(update.get("source_ref_count")), len(source_ref_fingerprints))
    return {
        "payload_compacted": True,
        "surface_kind": "ambient_card",
        "surface_id_hash": _surface_id_hash(card.get("card_id")),
        "lifecycle_action": "payload_compacted",
        "dead_letter_lifecycle_action": "dead_lettered",
        "support_level": "suppressed",
        "visibility": "dead_lettered_payload_compacted",
        "source_ref_count": source_ref_count,
        "source_ref_fingerprint_count": len(source_ref_fingerprints),
        "source_refs_preserved": True,
        "provenance_pointer_hash": update.get("provenance_pointer_hash"),
        "reason_codes": list(update.get("reason_codes") or []),
        "dead_lettered_at": update.get("applied_at"),
        "compacted_at": compacted_at,
        "rebuild_or_review_note": update.get("rebuild_or_review_note"),
    }


def _compaction_record(*, entry_key: str, tombstone: dict[str, Any]) -> dict[str, Any]:
    return {
        "surface_id_hash": tombstone["surface_id_hash"],
        "surface_kind": "ambient_card",
        "cache_entry_key_hash": _surface_id_hash(entry_key),
        "lifecycle_action": "payload_compacted",
        "dead_letter_lifecycle_action": tombstone["dead_letter_lifecycle_action"],
        "source_ref_count": tombstone["source_ref_count"],
        "source_ref_fingerprint_count": tombstone["source_ref_fingerprint_count"],
        "source_refs_preserved": True,
        "provenance_pointer_hash": tombstone.get("provenance_pointer_hash"),
        "reason_codes": tombstone.get("reason_codes") or [],
        "dead_lettered_at": tombstone.get("dead_lettered_at"),
        "compacted_at": tombstone["compacted_at"],
        "rebuild_or_review_note": tombstone.get("rebuild_or_review_note"),
    }


def _invalid_manifest() -> dict[str, Any]:
    return {
        "schema_version": COMPACTION_SCHEMA_VERSION,
        "kind": AMBIENT_CACHE_COMPACTION_MANIFEST_KIND,
        "ok": False,
        "status": "invalid_manifest",
        "write_mode": "no_write_invalid_manifest",
        "compacted": [],
        "skipped": [{"skip_reason": "invalid_dead_letter_manifest", "surface_kind": "ambient_card"}],
        "metrics": {
            "dead_lettered_update_count": 0,
            "payload_compacted_count": 0,
            "unsafe_update_count": 0,
            "skipped_count": 1,
        },
    }


def _safe_update_map(manifest: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]], int]:
    safe_updates: dict[str, dict[str, Any]] = {}
    skipped: list[dict[str, Any]] = []
    unsafe_count = 0
    if manifest.get("kind") != DEAD_LETTER_APPLY_MANIFEST_KIND:
        return (
            safe_updates,
            [
                {
                    "skip_reason": "unexpected_manifest_kind",
                    "manifest_kind": compact_text(str(manifest.get("kind") or ""), 120),
                    "surface_kind": "ambient_card",
                }
            ],
            unsafe_count,
        )
    for item in manifest.get("skipped") or []:
        if isinstance(item, dict) and item.get("surface_kind") == "ambient_card":
            skipped.append(
                {
                    "surface_id_hash": item.get("surface_id_hash"),
                    "surface_kind": "ambient_card",
                    "skip_reason": item.get("skip_reason") or "dead_letter_manifest_skipped",
                }
            )
    for update in manifest.get("updates") or []:
        if not isinstance(update, dict) or update.get("surface_kind") != "ambient_card":
            continue
        surface_id_hash = compact_text(str(update.get("surface_id_hash") or ""), 80)
        safety_errors = _dead_letter_update_safety_errors(update)
        if not surface_id_hash or safety_errors:
            unsafe_count += 1
            skipped.append(
                {
                    "surface_id_hash": surface_id_hash or None,
                    "surface_kind": "ambient_card",
                    "skip_reason": "unsafe_dead_letter_update",
                    "safety_errors": safety_errors or ["missing_surface_id_hash"],
                }
            )
            continue
        safe_updates[surface_id_hash] = update
    return safe_updates, skipped, unsafe_count


def _compact_entries(
    entries: dict[str, Any],
    safe_updates: dict[str, dict[str, Any]],
    *,
    compacted_at: str,
) -> tuple[list[dict[str, Any]], set[str], int]:
    compacted: list[dict[str, Any]] = []
    matched_hashes: set[str] = set()
    total_entries = 0
    for entry_key, entry in entries.items():
        if not isinstance(entry, dict):
            continue
        total_entries += 1
        cards = [card for card in entry.get("cards") or [] if isinstance(card, dict)]
        changed = False
        removed_related: set[str] = set()
        next_cards: list[dict[str, Any]] = []
        for card in cards:
            card_id = card.get("card_id")
            update = safe_updates.get(_surface_id_hash(card_id)) if card_id else None
            if update is None or card.get("payload_compacted"):
                next_cards.append(card)
                continue
            removed_related.update(_ambient_card_related_fingerprints(card))
            tombstone = _compacted_ambient_card(card, update, compacted_at=compacted_at)
            next_cards.append(tombstone)
            compacted.append(_compaction_record(entry_key=entry_key, tombstone=tombstone))
            matched_hashes.add(tombstone["surface_id_hash"])
            changed = True
        if not changed:
            continue
        entry["cards"] = next_cards
        entry["source_ref_fingerprints"] = _source_ref_fingerprints(
            [card for card in next_cards if not card.get("payload_compacted")]
        )
        entry["related_fingerprints"] = unique_preserve(
            [value for value in (entry.get("related_fingerprints") or []) if value not in removed_related],
            limit=48,
        )
        entry["payload_compaction"] = {
            "compacted_at": compacted_at,
            "payload_compacted_count": sum(
                1 for card in next_cards if isinstance(card, dict) and card.get("payload_compacted")
            ),
        }
    return compacted, matched_hashes, total_entries


def compact_ambient_cache_payloads_from_dead_letter_manifest(
    cache_path: Path | str,
    dead_letter_manifest: dict[str, Any],
    *,
    compacted_at: str | None = None,
) -> dict[str, Any]:
    """Compact dead-lettered ambient-card payloads in the owner cache.

    The generic activation audit emits hash-only lifecycle manifests. This
    owner-specific writer may compare those hashes against its own card ids, but
    it writes only tombstones into the soft cache and must stay out of
    foreground hooks.
    """

    if not isinstance(dead_letter_manifest, dict):
        return _invalid_manifest()
    timestamp = compacted_at or now_utc()
    target = Path(cache_path)
    data = _load_cache(target)
    entries: dict[str, Any] = dict(data.get("entries") or {})
    safe_updates, skipped, unsafe_count = _safe_update_map(dead_letter_manifest)
    compacted, matched_hashes, total_entries = _compact_entries(
        entries,
        safe_updates,
        compacted_at=timestamp,
    )
    for surface_id_hash in sorted(set(safe_updates) - matched_hashes):
        skipped.append(
            {
                "surface_id_hash": surface_id_hash,
                "surface_kind": "ambient_card",
                "skip_reason": "ambient_card_not_found",
            }
        )
    if compacted:
        _write_cache(
            target,
            {"schema_version": CACHE_SCHEMA_VERSION, "updated_at": now_utc(), "entries": entries},
        )
    return {
        "schema_version": COMPACTION_SCHEMA_VERSION,
        "kind": AMBIENT_CACHE_COMPACTION_MANIFEST_KIND,
        "ok": True,
        "status": "compacted" if compacted else "no_changes",
        "write_mode": "owner_payload_compaction" if compacted else "no_write_no_safe_matches",
        "compacted": compacted,
        "skipped": skipped,
        "metrics": {
            "dead_lettered_update_count": len(safe_updates),
            "payload_compacted_count": len(compacted),
            "ambient_cache_entry_count": total_entries,
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
