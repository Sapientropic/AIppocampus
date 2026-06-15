"""Candidate producer for posture-relation calibration.

Subconscious/Dream may suggest posture relation patterns, but the rows emitted
here are not runtime policy and are not foreground eligible.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

SCHEMA_VERSION = 1
KIND = "posture_relation_calibration_candidate"


def _text(value: Any) -> str:
    return str(value or "").strip()


def _stable_id(prefix: str, *parts: Any) -> str:
    raw = "\n".join(json.dumps(part, ensure_ascii=False, sort_keys=True) for part in parts)
    return f"{prefix}_{hashlib.sha1(raw.encode('utf-8', errors='replace')).hexdigest()[:18]}"


def _refs(row: Mapping[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in row.get("source_refs") or []:
        if not isinstance(item, Mapping):
            continue
        ref = {
            str(key): item[key]
            for key in ("source_id", "message_id", "turn_ref", "issue", "url")
            if item.get(key) not in (None, "")
        }
        if ref:
            out.append(ref)
    return out[:6]


def posture_relation_calibration_candidates(
    observations: Sequence[Mapping[str, Any]],
    *,
    min_observed_sequence_count: int = 2,
) -> dict[str, Any]:
    rows = [row for row in observations if isinstance(row, Mapping)]
    counts: Counter[tuple[str, str, str, str]] = Counter()
    refs_by_key: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {}
    counterexamples: Counter[tuple[str, str, str, str]] = Counter()
    suppressed: Counter[str] = Counter()
    previous: Mapping[str, Any] | None = None
    for row in rows:
        posture = _text(row.get("posture_id"))
        scope = _text(row.get("scope") or row.get("project") or "project")
        privacy = _text(row.get("privacy_state") or row.get("privacy") or "public_safe")
        refs = _refs(row)
        if privacy in {"private_blocked", "blocked"}:
            suppressed["privacy_blocked"] += 1
            previous = None
            continue
        if not posture or posture == "ambiguous_posture" or not refs:
            suppressed["insufficient_source"] += 1
            previous = row
            continue
        if previous and _text(previous.get("posture_id")) and _text(previous.get("scope") or "project") == scope:
            from_posture = _text(previous.get("posture_id"))
            if from_posture != "ambiguous_posture":
                relation = f"{from_posture}_to_{posture}"
                key = (scope, from_posture, posture, relation)
                counts[key] += 1
                refs_by_key.setdefault(key, []).extend(_refs(previous))
                refs_by_key[key].extend(refs)
        previous = row

    for key in counts:
        scope, source, target, _relation = key
        reverse = (scope, target, source, f"{target}_to_{source}")
        counterexamples[key] = counts.get(reverse, 0)

    candidates: list[dict[str, Any]] = []
    for key, count in sorted(counts.items()):
        if count < min_observed_sequence_count:
            suppressed["below_observation_threshold"] += 1
            continue
        scope, source, target, relation = key
        refs = refs_by_key.get(key, [])[:10]
        if not refs:
            suppressed["insufficient_source"] += 1
            continue
        counter_count = counterexamples[key]
        candidates.append(
            {
                "schema_version": SCHEMA_VERSION,
                "kind": KIND,
                "candidate_id": _stable_id("posture_cal", scope, source, target, count, counter_count),
                "relation": relation,
                "from_posture_id": source,
                "to_posture_id": target,
                "scope": scope,
                "observed_sequence_count": count,
                "counterexample_count": counter_count,
                "source_refs": refs,
                "suggested_lift": 0.04 if counter_count else 0.08,
                "authority_level": "direction_only",
                "claim_permission": "none",
                "foreground_eligible": False,
                "policy_mutation_allowed": False,
                "fact_claim_allowed": False,
            }
        )
    return {
        "kind": "posture_relation_calibration_report",
        "schema_version": SCHEMA_VERSION,
        "candidate_count": len(candidates),
        "candidates": candidates,
        "suppressed_by_reason": dict(sorted(suppressed.items())),
        "boundary": {
            "candidates_are_not_policy": True,
            "model_confidence_is_not_evidence": True,
            "raw_private_text_serialized": False,
        },
    }


__all__ = ["posture_relation_calibration_candidates"]
