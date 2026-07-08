from __future__ import annotations

from aippocampus_runtime.macro.hexagram import (
    HexagramRef,
    PerturbationBand,
    changed_lines,
    hamming_distance,
    perturbation_band,
    resolve_hexagram,
)
from aippocampus_runtime.macro.signal_scales import (
    SignalScale,
    is_project_level_signal,
    normalize_signal_scale,
    signal_scale_diagnostic,
)

AUTHORITY_LEVEL = "navigation_only"
CLAIM_PERMISSION = "no_claim_before_reopen"

LINE_LAYER_BY_POSITION = {
    1: "earth",
    2: "earth",
    3: "human",
    4: "human",
    5: "heaven",
    6: "heaven",
}

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
    return is_project_level_signal(
        signal_scale,
        promoted_to_project=promoted_to_project,
    )


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


def changed_line_layer_diagnostics(lines: tuple[int, ...]) -> dict[str, object]:
    layers = [{"line": position, "layer": LINE_LAYER_BY_POSITION[position]} for position in lines]
    counts = {
        "earth": sum(1 for item in layers if item["layer"] == "earth"),
        "human": sum(1 for item in layers if item["layer"] == "human"),
        "heaven": sum(1 for item in layers if item["layer"] == "heaven"),
    }
    active_layers = [layer for layer, count in counts.items() if count > 0]
    if not active_layers:
        dominant = "none"
    else:
        max_count = max(counts.values())
        leaders = [layer for layer, count in counts.items() if count == max_count and count > 0]
        dominant = leaders[0] if len(leaders) == 1 else "multi_layer"
    reason_codes = [f"perturbation_layer_{layer}" for layer in active_layers]
    if len(active_layers) > 1:
        reason_codes.append("perturbation_layer_multi")
    return {
        "changed_line_layers": layers,
        "changed_layer_counts": counts,
        "dominant_changed_layer": dominant,
        "reason_codes": reason_codes,
    }


def build_perturbation_packet(
    previous: HexagramRef,
    current: HexagramRef,
    *,
    signal_scale: str = "project_event",
    promoted_to_project: bool = False,
) -> dict[str, object]:
    normalized_scale = normalize_signal_scale(signal_scale)
    before = resolve_hexagram(previous)
    after = resolve_hexagram(current)
    lines = changed_lines(before, after)
    distance = hamming_distance(before, after)
    band = perturbation_band(distance)
    layer_diagnostics = changed_line_layer_diagnostics(lines)
    project_level_signal = _is_project_level_signal(
        signal_scale=normalized_scale,
        promoted_to_project=promoted_to_project,
    )
    policy = _policy_for_band(band, project_level_signal=project_level_signal)

    # Scale is a boundary, not an authority upgrade. Journey/thread movement can
    # be useful input, but it must be promoted by a project/domain event or
    # explicit review before it widens project-level recall fanout.
    reason_codes = [f"perturbation_band_{band}"]
    diagnostic = signal_scale_diagnostic(
        normalized_scale,
        promoted_to_project=promoted_to_project,
    )
    if diagnostic:
        reason_codes.append(diagnostic)
    if not project_level_signal:
        reason_codes.append("scale_not_promoted_no_project_fanout")
    if policy.get("conflict_review_required"):
        reason_codes.append("inversion_requires_source_reopen_or_conflict_review")
    if policy.get("stale_conflict_checks_required"):
        reason_codes.append("stale_conflict_checks_required")
    raw_layer_reasons = layer_diagnostics.get("reason_codes")
    layer_reasons = raw_layer_reasons if isinstance(raw_layer_reasons, list) else []
    for reason in layer_reasons:
        if reason not in reason_codes:
            reason_codes.append(str(reason))

    return {
        "kind": "macro_perturbation_amplitude",
        "schema_version": 1,
        "previous_hexagram": {"name": before.name, "number": before.number},
        "current_hexagram": {"name": after.name, "number": after.number},
        "hamming_distance": distance,
        "changed_lines": list(lines),
        "changed_line_count": len(lines),
        "changed_line_layers": layer_diagnostics["changed_line_layers"],
        "changed_layer_counts": layer_diagnostics["changed_layer_counts"],
        "dominant_changed_layer": layer_diagnostics["dominant_changed_layer"],
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
        "signal_scale": normalized_scale,
        "promoted_to_project": promoted_to_project,
        "signal_scale_schema": {
            "canonical": normalized_scale,
            "project_level": project_level_signal,
            "diagnostic": diagnostic,
        },
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
    "changed_line_layer_diagnostics",
    "compact_perturbation_label",
]
