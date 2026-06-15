"""Deterministic navigation posture reducer for atlas sections.

Posture ids are source-reopen hints, not personality labels and not evidence.
The reducer deliberately emits `ambiguous_posture` when the source shape is thin
or competing cues would otherwise let a keyword table over-personalize routing.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any

POSTURE_IDS = {
    "closeout",
    "seed_probe",
    "verifier",
    "reviewer_gate",
    "archivist_boundary",
    "rejected_route_shadow",
    "companion_pacing",
    "ambiguous_posture",
}
AUTHORITY_LEVEL = "direction_only"
CLAIM_PERMISSION = "none"


def _text(value: Any) -> str:
    return str(value or "").strip()


def _safe_refs(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    refs: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, Mapping):
            continue
        ref = {
            str(key): item[key]
            for key in ("source_id", "message_id", "turn_ref", "issue", "url")
            if item.get(key) not in (None, "")
        }
        if ref:
            refs.append(ref)
    return refs[:6]


def _stable_id(prefix: str, *parts: Any) -> str:
    raw = "\n".join(json.dumps(part, ensure_ascii=False, sort_keys=True) for part in parts)
    digest = hashlib.sha1(raw.encode("utf-8", errors="replace")).hexdigest()[:16]
    return f"{prefix}_{digest}"


def _cue_text(row: Mapping[str, Any]) -> str:
    values: list[str] = []
    for key in (
        "posture_hint",
        "lifecycle",
        "status",
        "task_family",
        "section_kind",
        "action_delta",
        "next_action",
        "decision_shadow",
        "title",
        "summary",
        "reason_code",
    ):
        values.append(_text(row.get(key)))
    values.extend(_text(item) for item in row.get("reason_codes") or [])
    return " ".join(values).casefold()


def reduce_avatar_posture(row: Mapping[str, Any]) -> dict[str, Any]:
    text = _cue_text(row)
    refs = _safe_refs(row.get("source_refs"))
    matches: list[tuple[str, str]] = []
    if any(token in text for token in ("closeout", "release", "ship", "收口", "发布")):
        matches.append(("closeout", "closeout_or_release_cue"))
    if any(token in text for token in ("seed", "probe", "revival", "探索", "种子")):
        matches.append(("seed_probe", "seed_or_probe_cue"))
    if any(token in text for token in ("verify", "verification", "test", "validator", "验收")):
        matches.append(("verifier", "verification_cue"))
    if any(token in text for token in ("review", "gate", "audit", "lint", "审计", "评审")):
        matches.append(("reviewer_gate", "review_gate_cue"))
    if any(token in text for token in ("archive", "boundary", "source", "provenance", "归档")):
        matches.append(("archivist_boundary", "source_boundary_cue"))
    if any(token in text for token in ("rejected", "wrong_route", "shadow", "blocked", "obstruction")):
        matches.append(("rejected_route_shadow", "rejected_or_blocked_route_cue"))
    if any(token in text for token in ("companion", "pacing", "follow", "rhythm", "陪伴")):
        matches.append(("companion_pacing", "companion_or_pacing_cue"))

    unique = []
    seen: set[str] = set()
    for posture_id, reason in matches:
        if posture_id in seen:
            continue
        seen.add(posture_id)
        unique.append((posture_id, reason))
    thin = not refs and not row.get("first_source_to_reopen")
    if len(unique) != 1 or thin:
        posture_id = "ambiguous_posture"
        reason_codes = [reason for _, reason in unique] or ["no_stable_posture_cue"]
        if thin:
            reason_codes.append("thin_source_posture_ambiguous")
    else:
        posture_id = unique[0][0]
        reason_codes = [unique[0][1]]
    return {
        "kind": "avatar_posture_reduction",
        "posture_id": posture_id,
        "basis": {
            "source_ref_count": len(refs),
            "matched_posture_count": len(unique),
            "first_source_to_reopen": _text(row.get("first_source_to_reopen")),
        },
        "reason_codes": reason_codes,
        "authority_level": AUTHORITY_LEVEL,
        "claim_permission": CLAIM_PERMISSION,
        "fact_claim_allowed": False,
        "foreground_eligible": posture_id != "ambiguous_posture",
        "source_reopen_required_before_claim": True,
    }


POSTURE_RELATIONS: dict[tuple[str, str], str] = {
    ("closeout", "verifier"): "closeout_needs_verification",
    ("verifier", "closeout"): "verification_unlocks_closeout",
    ("seed_probe", "archivist_boundary"): "seed_needs_source_boundary",
    ("archivist_boundary", "seed_probe"): "source_boundary_reopens_seed",
    ("rejected_route_shadow", "reviewer_gate"): "rejected_route_needs_review_gate",
    ("reviewer_gate", "rejected_route_shadow"): "review_gate_handles_shadow",
    ("companion_pacing", "closeout"): "pacing_can_reduce_closeout_rush",
}


def posture_dependency_edge(
    source: Mapping[str, Any],
    target: Mapping[str, Any],
) -> dict[str, Any] | None:
    source_posture = _text(source.get("posture_id"))
    target_posture = _text(target.get("posture_id"))
    if (
        source_posture not in POSTURE_IDS
        or target_posture not in POSTURE_IDS
        or "ambiguous_posture" in {source_posture, target_posture}
    ):
        return None
    if source.get("privacy_state") in {"blocked", "private_blocked"}:
        return None
    if target.get("privacy_state") in {"blocked", "private_blocked"}:
        return None
    relation = POSTURE_RELATIONS.get((source_posture, target_posture))
    if not relation:
        return None
    from_id = _text(source.get("section_id") or source.get("id"))
    to_id = _text(target.get("section_id") or target.get("id"))
    return {
        "edge_id": _stable_id("posture_edge", from_id, to_id, relation),
        "edge_kind": "posture_dependency_edge",
        "from_section_id": from_id,
        "to_section_id": to_id,
        "relation": relation,
        "basis": {
            "from_posture_id": source_posture,
            "to_posture_id": target_posture,
        },
        "authority_level": AUTHORITY_LEVEL,
        "claim_permission": CLAIM_PERMISSION,
        "fact_claim_allowed": False,
        "may_satisfy_glue": False,
        "may_transfer_fact": False,
        "recommended_next": "use_as_attention_lift_then_reopen_source",
    }


__all__ = [
    "POSTURE_IDS",
    "POSTURE_RELATIONS",
    "posture_dependency_edge",
    "reduce_avatar_posture",
]
