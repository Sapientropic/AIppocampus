from __future__ import annotations

from typing import Literal, TypeAlias

from aippocampus_runtime.macro.hexagram import (
    HexagramRef,
    PerturbationBand,
    changed_lines,
    hamming_distance,
    perturbation_band,
    resolve_hexagram,
)

SignalScale: TypeAlias = Literal[
    "project",
    "project_event",
    "continuity_domain",
    "journey",
    "thread",
    "unknown",
]

AUTHORITY_LEVEL = "navigation_only"
CLAIM_PERMISSION = "no_claim_before_reopen"
_PROJECT_LEVEL_SCALES = {"project", "project_event"}

_BAND_POLICIES: dict[PerturbationBand, dict[str, object]] = {
    "none": {
        "amplitude": "no_shift",
        "route_policy": "no_extra_fanout",
        "fanout_width": "none",
        "recommended_candidate_limit": 0,
        "source_reopen_policy": "not_required_for_navigation",
        "stale_conflict_checks_required": False,
        "conflict_review_required": False,
    },
    "local": {
        "amplitude": "local_adjustment",
        "route_policy": "bounded_fanout",
        "fanout_width": "narrow",
        "recommended_candidate_limit": 2,
        "source_reopen_policy": "not_required_for_navigation",
        "stale_conflict_checks_required": False,
        "conflict_review_required": False,
    },
    "medium": {
        "amplitude": "perspective_shift",
        "route_policy": "perspective_fanout",
        "fanout_width": "medium",
        "recommended_candidate_limit": 4,
        "source_reopen_policy": "deepen_before_claim",
        "stale_conflict_checks_required": False,
        "conflict_review_required": False,
    },
    "large": {
        "amplitude": "large_shift",
        "route_policy": "broad_fanout_with_stale_conflict_checks",
        "fanout_width": "broad",
        "recommended_candidate_limit": 8,
        "source_reopen_policy": "deepen_before_action_or_claim",
        "stale_conflict_checks_required": True,
        "conflict_review_required": False,
    },
    "inversion": {
        "amplitude": "inversion",
        "route_policy": "reopen_or_conflict_review",
        "fanout_width": "conflict_review_first",
        "recommended_candidate_limit": 0,
        "candidate_limit_after_review": 8,
        "source_reopen_policy": "source_reopen_or_conflict_review_required",
        "stale_conflict_checks_required": True,
        "conflict_review_required": True,
    },
}


def _is_project_level_signal(
    *,
    signal_scale: SignalScale,
    promoted_to_project: bool,
) -> bool:
    return signal_scale in _PROJECT_LEVEL_SCALES or promoted_to_project


def _scale_guard_policy() -> dict[str, object]:
    return {
        "amplitude": "unpromoted_signal",
        "route_policy": "no_project_fanout_from_unpromoted_signal",
        "fanout_width": "none",
        "recommended_candidate_limit": 0,
        "source_reopen_policy": "promote_or_review_before_project_fanout",
        "stale_conflict_checks_required": False,
        "conflict_review_required": False,
        "candidate_limit_after_review": 0,
    }


def _policy_for_band(
    band: PerturbationBand,
    *,
    project_level_signal: bool,
) -> dict[str, object]:
    if not project_level_signal:
        return _scale_guard_policy()
    return dict(_BAND_POLICIES[band])


def build_perturbation_packet(
    previous: HexagramRef,
    current: HexagramRef,
    *,
    signal_scale: SignalScale = "project",
    promoted_to_project: bool = False,
) -> dict[str, object]:
    before = resolve_hexagram(previous)
    after = resolve_hexagram(current)
    lines = changed_lines(before, after)
    distance = hamming_distance(before, after)
    band = perturbation_band(distance)
    project_level_signal = _is_project_level_signal(
        signal_scale=signal_scale,
        promoted_to_project=promoted_to_project,
    )
    policy = _policy_for_band(band, project_level_signal=project_level_signal)

    # Scale is a boundary, not an authority upgrade. Journey/thread movement can
    # be useful input, but it must be promoted by a project/domain event or
    # explicit review before it widens project-level recall fanout.
    reason_codes = [f"perturbation_band_{band}"]
    if not project_level_signal:
        reason_codes.append("scale_not_promoted_no_project_fanout")
    if policy.get("conflict_review_required"):
        reason_codes.append("inversion_requires_source_reopen_or_conflict_review")
    if policy.get("stale_conflict_checks_required"):
        reason_codes.append("stale_conflict_checks_required")

    return {
        "kind": "macro_perturbation_amplitude",
        "schema_version": 1,
        "previous_hexagram": {"name": before.name, "number": before.number},
        "current_hexagram": {"name": after.name, "number": after.number},
        "hamming_distance": distance,
        "changed_lines": list(lines),
        "changed_line_count": len(lines),
        "band": band,
        "amplitude": policy["amplitude"],
        "route_policy": policy["route_policy"],
        "fanout_hint": {
            "band": band,
            "width": policy["fanout_width"],
            "recommended_candidate_limit": policy["recommended_candidate_limit"],
            "candidate_limit_after_review": policy.get("candidate_limit_after_review"),
        },
        "source_reopen_policy": policy["source_reopen_policy"],
        "stale_conflict_checks_required": policy["stale_conflict_checks_required"],
        "conflict_review_required": policy["conflict_review_required"],
        "project_level_signal": project_level_signal,
        "signal_scale": signal_scale,
        "promoted_to_project": promoted_to_project,
        "authority_level": AUTHORITY_LEVEL,
        "claim_permission": CLAIM_PERMISSION,
        "fact_claim_allowed": False,
        "reason_codes": reason_codes,
        "source_boundary": {
            "navigation_only_not_fact": True,
            "no_source_backed_claim_from_perturbation_alone": True,
            "scale_boundary": "project_fanout_requires_project_scope_or_promotion",
        },
    }


def _packet_int(packet: dict[str, object], key: str) -> int:
    value = packet[key]
    if type(value) is not int:
        raise ValueError(f"perturbation packet field {key!r} must be an integer")
    return value


def compact_perturbation_label(packet: dict[str, object]) -> dict[str, object]:
    distance = _packet_int(packet, "hamming_distance")
    return {
        "movement": packet["amplitude"],
        "perturbation": f"distance_{distance}",
        "changed_line_count": _packet_int(packet, "changed_line_count"),
        "route_policy": packet["route_policy"],
        "authority_level": AUTHORITY_LEVEL,
        "claim_permission": CLAIM_PERMISSION,
    }


__all__ = [
    "AUTHORITY_LEVEL",
    "CLAIM_PERMISSION",
    "SignalScale",
    "build_perturbation_packet",
    "compact_perturbation_label",
]
