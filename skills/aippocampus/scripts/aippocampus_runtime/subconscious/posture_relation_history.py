"""Source-backed history adapter for posture-relation calibration."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

from aippocampus_runtime.ops.route_readiness import safe_source_refs
from aippocampus_runtime.subconscious.posture_relation_calibration import (
    posture_relation_calibration_candidates,
)

SCHEMA_VERSION = 1


def _text(value: Any) -> str:
    return str(value or "").strip()


def posture_observations_from_history(
    rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    observations: list[dict[str, Any]] = []
    suppressed: Counter[str] = Counter()
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        refs = safe_source_refs(row.get("source_refs"))
        privacy = _text(row.get("privacy_state") or row.get("privacy") or "public_safe")
        freshness = _text(row.get("freshness") or row.get("currentness") or "current")
        posture = _text(row.get("posture_id") or row.get("macro_posture_id") or row.get("posture"))
        if privacy in {"blocked", "private_blocked"}:
            suppressed["privacy_blocked"] += 1
            continue
        if freshness in {"stale", "superseded", "refuted"}:
            suppressed["stale_or_refuted"] += 1
            continue
        if not refs:
            suppressed["source_refs_missing"] += 1
            continue
        if not posture or posture == "ambiguous_posture":
            suppressed["posture_missing"] += 1
            continue
        observations.append(
            {
                "posture_id": posture,
                "scope": _text(
                    row.get("scope")
                    or row.get("scope_bucket")
                    or row.get("normalized_scope")
                    or row.get("project")
                    or "project"
                ),
                "source_refs": refs,
                "privacy_state": privacy,
                "freshness": freshness,
                "authority_level": "direction_only",
                "claim_permission": "none",
                "foreground_eligible": False,
            }
        )
    return {
        "kind": "posture_relation_history_observation_report",
        "schema_version": SCHEMA_VERSION,
        "observations": observations,
        "observation_count": len(observations),
        "suppressed_by_reason": dict(sorted(suppressed.items())),
        "boundary": {
            "history_rows_are_candidate_inputs": True,
            "source_reopen_required_before_claim": True,
            "raw_history_text_serialized": False,
        },
    }


def posture_relation_calibration_from_history(
    rows: Sequence[Mapping[str, Any]],
    *,
    min_observed_sequence_count: int = 2,
) -> dict[str, Any]:
    observation_report = posture_observations_from_history(rows)
    calibration = posture_relation_calibration_candidates(
        observation_report["observations"],
        min_observed_sequence_count=min_observed_sequence_count,
    )
    return {
        "kind": "posture_relation_history_calibration_report",
        "schema_version": SCHEMA_VERSION,
        "observation_report": observation_report,
        "calibration": calibration,
        "candidate_count": calibration["candidate_count"],
        "foreground_eligible": False,
        "authority_level": "direction_only",
        "claim_permission": "none",
    }


__all__ = [
    "posture_observations_from_history",
    "posture_relation_calibration_from_history",
]
