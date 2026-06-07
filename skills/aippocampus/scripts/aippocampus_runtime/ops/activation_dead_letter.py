"""Dead-letter candidate reporting for activation surfaces.

This module consumes already-normalized public-safe activation rows. It keeps
dead-letter selection separate from authority/conflict normalization so the
audit facade can stay small and the #582 lifecycle boundary remains explicit:
dead-lettering is activation eligibility bookkeeping, not source deletion.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import Any

DEAD_LETTER_REPORT_KIND = "aippocampus_activation_dead_letter_candidate_report"
DEAD_LETTER_APPLY_MANIFEST_KIND = "aippocampus_activation_dead_letter_apply_manifest"
DEFAULT_WRONG_ROUTE_DRAG_THRESHOLD = 3
DEFAULT_NO_SOURCE_REOPEN_THRESHOLD = 3
DEFAULT_FALSE_POSITIVE_THRESHOLD = 3
DEFAULT_REPEATED_AUDIT_INACTIVE_THRESHOLD = 3
FOREGROUND_REDUCTION_ACTIONS = {"demote", "park", "supersede", "retire"}


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _public_hash(value: Any, default: str = "unknown") -> str:
    text = str(value or default)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _dead_letter_reason_codes(
    row: Mapping[str, Any],
    *,
    wrong_route_drag_threshold: int,
    no_source_reopen_threshold: int,
    false_positive_threshold: int,
) -> list[str]:
    reasons: list[str] = []
    pruning_action = str(row.get("pruning_action") or "none")
    if pruning_action in FOREGROUND_REDUCTION_ACTIONS or row.get("authority_level") == "blocked":
        reasons.append("lifecycle_not_foreground_eligible")
    if _int(row.get("wrong_route_drag_count")) >= wrong_route_drag_threshold:
        reasons.append("wrong_route_drag_threshold")
    no_reopen_count = _int(row.get("no_source_reopen_count"))
    if no_reopen_count >= no_source_reopen_threshold:
        reasons.append("no_source_reopen_threshold")
    elif (
        _int(row.get("source_reopen_attempt_count")) >= no_source_reopen_threshold
        and _int(row.get("source_reopen_success_count")) == 0
    ):
        reasons.append("no_source_reopen_threshold")
    if _int(row.get("false_positive_count")) >= false_positive_threshold:
        reasons.append("false_positive_threshold")
    return reasons


def _inactive_after_repeated_audits(
    row: Mapping[str, Any],
    *,
    no_source_reopen_threshold: int,
) -> bool:
    return bool(
        _int(row.get("dead_letter_audit_count")) >= DEFAULT_REPEATED_AUDIT_INACTIVE_THRESHOLD
        and _int(row.get("no_source_reopen_count")) >= no_source_reopen_threshold
        and (
            str(row.get("pruning_action") or "none") in FOREGROUND_REDUCTION_ACTIONS
            or row.get("authority_level") == "blocked"
        )
    )


def _dead_letter_candidates_from_rows(
    rows: Sequence[dict[str, Any]],
    *,
    wrong_route_drag_threshold: int,
    no_source_reopen_threshold: int,
    false_positive_threshold: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    candidates: list[dict[str, Any]] = []
    protected: list[dict[str, Any]] = []
    for row in rows:
        if not row.get("activation_surface"):
            continue
        reason_codes = _dead_letter_reason_codes(
            row,
            wrong_route_drag_threshold=wrong_route_drag_threshold,
            no_source_reopen_threshold=no_source_reopen_threshold,
            false_positive_threshold=false_positive_threshold,
        )
        if "lifecycle_not_foreground_eligible" not in reason_codes or len(reason_codes) < 2:
            continue
        surface_id_hash = _public_hash(row.get("surface_id"), str(row.get("surface_kind") or "surface"))
        if _int(row.get("protected_reference_count")) > 0:
            protected.append(
                {
                    "surface_id_hash": surface_id_hash,
                    "surface_kind": row["surface_kind"],
                    "reason_codes": reason_codes,
                    "protected_reference_count": row["protected_reference_count"],
                }
            )
            continue
        inactive_after_repeated_audits = _inactive_after_repeated_audits(
            row,
            no_source_reopen_threshold=no_source_reopen_threshold,
        )
        candidates.append(
            {
                "surface_id_hash": surface_id_hash,
                "surface_kind": row["surface_kind"],
                "lifecycle_action": row["pruning_action"],
                "reason_codes": reason_codes,
                "source_ref_count": row["source_ref_count"],
                "provenance_pointer_hash": row.get("provenance_pointer_hash"),
                "source_refs_preserved": True,
                "payload_compacted": False,
                "inactive_after_repeated_audits": inactive_after_repeated_audits,
                "payload_compaction_ready": inactive_after_repeated_audits,
                "recommended_action": (
                    "dead_letter_candidate_mark_inactive"
                    if inactive_after_repeated_audits
                    else "dead_letter_candidate_no_write"
                ),
                "review_note": "No-write candidate only; apply requires owner-specific source/provenance/reference checks.",
            }
        )
    return candidates, protected


def _reason_count(candidates: Sequence[Mapping[str, Any]], reason: str) -> int:
    return sum(1 for candidate in candidates if reason in set(candidate.get("reason_codes") or []))


def activation_dead_letter_candidate_report_from_rows(
    rows: Sequence[dict[str, Any]],
    *,
    schema_version: int = 1,
    wrong_route_drag_threshold: int = DEFAULT_WRONG_ROUTE_DRAG_THRESHOLD,
    no_source_reopen_threshold: int = DEFAULT_NO_SOURCE_REOPEN_THRESHOLD,
    false_positive_threshold: int = DEFAULT_FALSE_POSITIVE_THRESHOLD,
) -> dict[str, Any]:
    candidates, protected = _dead_letter_candidates_from_rows(
        rows,
        wrong_route_drag_threshold=wrong_route_drag_threshold,
        no_source_reopen_threshold=no_source_reopen_threshold,
        false_positive_threshold=false_positive_threshold,
    )
    return {
        "schema_version": schema_version,
        "kind": DEAD_LETTER_REPORT_KIND,
        "write_mode": False,
        "thresholds": {
            "wrong_route_drag_threshold": wrong_route_drag_threshold,
            "no_source_reopen_threshold": no_source_reopen_threshold,
            "false_positive_threshold": false_positive_threshold,
        },
        "candidates": candidates,
        "protected_candidates": protected,
        "metrics": {
            "dead_letter_candidate_count": len(candidates),
            "payload_compacted_count": 0,
            "wrong_route_drag_threshold_hits": _reason_count(candidates, "wrong_route_drag_threshold"),
            "no_source_reopen_threshold_hits": _reason_count(candidates, "no_source_reopen_threshold"),
            "false_positive_threshold_hits": _reason_count(candidates, "false_positive_threshold"),
            "repeated_audit_inactive_candidate_count": sum(
                1 for candidate in candidates if candidate.get("inactive_after_repeated_audits")
            ),
            "referenced_row_protection_count": len(protected),
            "protected_surface_count": len(protected),
            "candidate_source_ref_count": sum(_int(candidate.get("source_ref_count")) for candidate in candidates),
            "activation_surface_authority_leak_count": sum(1 for row in rows if row["authority_leak"]),
        },
        "contract": {
            "no_write_report_only": True,
            "clean_source_preserved": True,
            "raw_rollout_preserved": True,
            "source_refs_preserved": True,
            "audit_provenance_preserved": True,
            "truth_status_changed": False,
            "foreground_hook_mutation": False,
            "model_judgment_deletion_authority": False,
            "apply_requires_reference_safety_checks": True,
        },
        "privacy_boundary": {
            "raw_prompt_serialized": False,
            "raw_source_snippets_serialized": False,
            "local_paths_serialized": False,
            "source_refs_serialized": False,
            "candidate_identity": "surface_id_hash_only",
        },
    }


def _candidate_update(candidate: Mapping[str, Any], *, applied_at: str) -> dict[str, Any]:
    return {
        "surface_id_hash": candidate["surface_id_hash"],
        "surface_kind": candidate["surface_kind"],
        "lifecycle_action": "dead_lettered",
        "source_ref_count": _int(candidate.get("source_ref_count")),
        "provenance_pointer_hash": candidate.get("provenance_pointer_hash"),
        "reason_codes": list(candidate.get("reason_codes") or []),
        "applied_at": applied_at,
        "append_only": True,
        "source_refs_preserved": True,
        "payload_compacted": False,
        "inactive_after_repeated_audits": bool(candidate.get("inactive_after_repeated_audits")),
        "payload_compaction_ready": bool(candidate.get("payload_compaction_ready")),
        "clean_source_mutation": False,
        "truth_status_changed": False,
        "rebuild_or_review_note": (
            "Dead-letter lifecycle patch only. Rebuild activation projections from clean source "
            "or owner manifests if this row must be reviewed or restored."
        ),
    }


def apply_dead_letter_candidate_manifest_from_rows(
    rows: Sequence[dict[str, Any]],
    *,
    schema_version: int = 1,
    applied_at: str | None = None,
    wrong_route_drag_threshold: int = DEFAULT_WRONG_ROUTE_DRAG_THRESHOLD,
    no_source_reopen_threshold: int = DEFAULT_NO_SOURCE_REOPEN_THRESHOLD,
    false_positive_threshold: int = DEFAULT_FALSE_POSITIVE_THRESHOLD,
) -> dict[str, Any]:
    timestamp = applied_at or _now_utc()
    candidates, protected = _dead_letter_candidates_from_rows(
        rows,
        wrong_route_drag_threshold=wrong_route_drag_threshold,
        no_source_reopen_threshold=no_source_reopen_threshold,
        false_positive_threshold=false_positive_threshold,
    )
    updates = [_candidate_update(candidate, applied_at=timestamp) for candidate in candidates]
    skipped = [
        {
            "surface_id_hash": item["surface_id_hash"],
            "surface_kind": item["surface_kind"],
            "reason_codes": item["reason_codes"],
            "skip_reason": "referenced_row_protected",
            "protected_reference_count": item["protected_reference_count"],
        }
        for item in protected
    ]
    return {
        "schema_version": schema_version,
        "kind": DEAD_LETTER_APPLY_MANIFEST_KIND,
        "ok": True,
        "write_mode": "append_only_manifest",
        "update_count": len(updates),
        "skipped_count": len(skipped),
        "updates": updates,
        "skipped": skipped,
        "metrics": {
            "dead_lettered_count": len(updates),
            "payload_compacted_count": 0,
            "referenced_row_protection_count": len(skipped),
            "wrong_route_drag_threshold_hits": _reason_count(updates, "wrong_route_drag_threshold"),
            "no_source_reopen_threshold_hits": _reason_count(updates, "no_source_reopen_threshold"),
            "repeated_audit_inactive_candidate_count": sum(
                1 for update in updates if update.get("inactive_after_repeated_audits")
            ),
            "activation_surface_authority_leak_count": sum(1 for row in rows if row["authority_leak"]),
        },
        "contract": {
            "append_only_lifecycle_update": True,
            "dead_lettering_changes_activation_eligibility_only": True,
            "physical_payload_compaction": False,
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


__all__ = [
    "DEAD_LETTER_APPLY_MANIFEST_KIND",
    "DEAD_LETTER_REPORT_KIND",
    "DEFAULT_FALSE_POSITIVE_THRESHOLD",
    "DEFAULT_NO_SOURCE_REOPEN_THRESHOLD",
    "DEFAULT_WRONG_ROUTE_DRAG_THRESHOLD",
    "activation_dead_letter_candidate_report_from_rows",
    "apply_dead_letter_candidate_manifest_from_rows",
]
