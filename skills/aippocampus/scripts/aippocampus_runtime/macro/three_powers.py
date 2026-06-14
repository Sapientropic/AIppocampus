from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any, Literal, TypeAlias

from aippocampus_runtime.macro import line_topology
from aippocampus_runtime.macro.hexagram import HexagramRef
from aippocampus_runtime.navigation.parallel_derivation_bundle import (
    preflattening_gate_for_route_affordance,
)

Layer: TypeAlias = Literal["earth", "human", "heaven"]

AUTHORITY_LEVEL = "navigation_only"
CLAIM_PERMISSION = "no_claim_before_reopen"
SCHEMA_VERSION = 1

_LAYERS: tuple[Layer, ...] = ("earth", "human", "heaven")
_LAYER_LABELS: dict[Layer, str] = {
    "earth": "地",
    "human": "人",
    "heaven": "天",
}
_LAYER_ALIASES: dict[str, Layer] = {
    "earth": "earth",
    "ground": "earth",
    "substrate": "earth",
    "地": "earth",
    "human": "human",
    "action": "human",
    "coordination": "human",
    "人": "human",
    "heaven": "heaven",
    "direction": "heaven",
    "thesis": "heaven",
    "天": "heaven",
}
_SOURCE_FAMILY_TO_LAYER: dict[str, Layer] = {
    "artifact": "earth",
    "benchmark": "earth",
    "benchmark_report": "earth",
    "bounded_evidence": "earth",
    "clean_source": "earth",
    "evidence": "earth",
    "implementation": "earth",
    "implementation_fact": "earth",
    "source": "earth",
    "source_span": "earth",
    "test": "earth",
    "tests": "earth",
    "agent_decision": "human",
    "current_task_route": "human",
    "github_issue": "human",
    "handoff": "human",
    "issue": "human",
    "pr": "human",
    "pull_request": "human",
    "review": "human",
    "task_route": "human",
    "workflow": "human",
    "discussion": "heaven",
    "long_horizon_purpose": "heaven",
    "north_star": "heaven",
    "product_claim": "heaven",
    "public_positioning": "heaven",
    "purpose": "heaven",
    "roadmap": "heaven",
    "thesis": "heaven",
}
_QUERY_CUES: dict[Layer, tuple[str, ...]] = {
    "earth": (
        "artifact",
        "benchmark",
        "clean source",
        "evidence",
        "fixture",
        "implementation",
        "source",
        "test",
        "证据",
        "测试",
    ),
    "human": (
        "agent",
        "current task",
        "decision",
        "handoff",
        "issue",
        "pr",
        "pull request",
        "workflow",
        "交接",
        "行动",
    ),
    "heaven": (
        "direction",
        "long horizon",
        "north star",
        "positioning",
        "product claim",
        "purpose",
        "roadmap",
        "thesis",
        "方向",
        "路线图",
    ),
}
_PRIVATE_MARKERS = ("PRIVATE_", "C:\\", "\\Users\\", "/Users/")


def _normalize_token(value: object) -> str:
    text = str(value or "").strip().casefold()
    text = re.sub(r"[\s\-]+", "_", text)
    return text


def _safe_label(value: object, fallback: str) -> str:
    label = str(value or "").strip()
    if not label:
        return fallback
    if any(marker.casefold() in label.casefold() for marker in _PRIVATE_MARKERS):
        return fallback
    return label[:120]


def normalize_layer(value: object) -> Layer:
    normalized = _normalize_token(value)
    if normalized in _LAYER_ALIASES:
        return _LAYER_ALIASES[normalized]
    raise ValueError(f"unknown Three Powers layer: {value!r}")


def infer_active_layer(
    query: str,
    *,
    explicit_layer: object | None = None,
) -> dict[str, object]:
    if explicit_layer is not None:
        layer = normalize_layer(explicit_layer)
        return {
            "active_layer": layer,
            "label": _LAYER_LABELS[layer],
            "source": "explicit",
            "scores": {item: 0 for item in _LAYERS},
            "candidate_layers": [layer],
            "score_margin": None,
            "ambiguity_status": "explicit_override",
            "reason_codes": [f"explicit_layer_{layer}"],
        }

    query_text = str(query or "").casefold()
    scores = {
        layer: sum(1 for cue in cues if cue.casefold() in query_text)
        for layer, cues in _QUERY_CUES.items()
    }
    best_score = max(scores.values())
    if best_score == 0:
        return {
            "active_layer": "human",
            "label": _LAYER_LABELS["human"],
            "source": "default",
            "scores": scores,
            "candidate_layers": ["human"],
            "score_margin": None,
            "ambiguity_status": "default",
            "reason_codes": ["default_human_current_task_route"],
        }
    winners = [layer for layer in _LAYERS if scores[layer] == best_score]
    second_score = max((score for layer, score in scores.items() if layer not in winners), default=0)
    layer = "human" if "human" in winners and len(winners) > 1 else winners[0]
    ambiguous = len(winners) > 1
    return {
        "active_layer": layer,
        "label": _LAYER_LABELS[layer],
        "source": "inferred",
        "scores": scores,
        "candidate_layers": winners,
        "score_margin": best_score - second_score,
        "ambiguity_status": "ambiguous_tie" if ambiguous else "clear",
        "reason_codes": [
            *(["ambiguous_layer_tie"] if ambiguous else []),
            *(f"query_cue_{item}" for item in winners),
        ],
    }


def _candidate_source_family(candidate: Mapping[str, Any]) -> str:
    for key in ("source_family", "route_family", "candidate_type", "output_mode"):
        value = candidate.get(key)
        if value:
            return _normalize_token(value)
    return "unknown"


def route_facet_metadata(candidate: Mapping[str, Any]) -> dict[str, object]:
    source_family = _candidate_source_family(candidate)
    layer = _SOURCE_FAMILY_TO_LAYER.get(source_family, "human")
    reason_code = (
        f"source_family_{source_family}_maps_to_{layer}"
        if source_family in _SOURCE_FAMILY_TO_LAYER
        else "unknown_source_family_defaults_to_human_review"
    )
    return {
        "facet": "three_powers_route_facet",
        "layer": layer,
        "label": _LAYER_LABELS[layer],
        "source_family": source_family,
        "authority_level": AUTHORITY_LEVEL,
        "claim_permission": CLAIM_PERMISSION,
        "fact_claim_allowed": False,
        "reason_codes": [reason_code],
    }


def _source_handle_count(candidate: Mapping[str, Any]) -> int:
    explicit = candidate.get("source_handle_count")
    if type(explicit) is int:
        return explicit
    handles = candidate.get("source_handles")
    if isinstance(handles, Sequence) and not isinstance(handles, (str, bytes)):
        return len(handles)
    refs = candidate.get("source_refs")
    if isinstance(refs, Sequence) and not isinstance(refs, (str, bytes)):
        return len(refs)
    return 0


def _project_candidate(
    candidate: Mapping[str, Any],
    *,
    index: int,
    active_layer: Layer,
) -> dict[str, object]:
    route_id = str(candidate.get("route_id") or candidate.get("id") or f"route_{index}")
    facet = route_facet_metadata(candidate)
    facet_layer = str(facet["layer"])
    source_handle_count = _source_handle_count(candidate)
    score = (100 if facet_layer == active_layer else 0) + min(source_handle_count, 5)
    return {
        "route_id": route_id,
        "route_label": _safe_label(candidate.get("route_label") or candidate.get("title"), route_id),
        "source_family": facet["source_family"],
        "output_mode": str(candidate.get("output_mode") or "direction_only"),
        "action_grammar": str(candidate.get("action_grammar") or "direction_only"),
        "claim_permission": str(candidate.get("claim_permission") or CLAIM_PERMISSION),
        "authority_level": str(candidate.get("authority_level") or AUTHORITY_LEVEL),
        "source_handle_count": source_handle_count,
        "three_powers_facet": facet,
        "three_powers_rank_score": score,
        "input_order": index,
    }


def _fanout_policy(
    perturbation_packet: Mapping[str, Any] | None,
    *,
    base_candidate_limit: int,
) -> dict[str, object]:
    if perturbation_packet is None:
        return {
            "source": "default",
            "band": "none",
            "width": "layer_priority",
            "candidate_limit": base_candidate_limit,
            "stale_conflict_checks_required": False,
            "conflict_review_required": False,
        }
    hint = perturbation_packet.get("fanout_hint")
    hint = hint if isinstance(hint, Mapping) else {}
    band = str(perturbation_packet.get("band") or hint.get("band") or "unknown")
    recommended = hint.get("recommended_candidate_limit")
    limit = recommended if type(recommended) is int else base_candidate_limit
    conflict_review_required = bool(perturbation_packet.get("conflict_review_required"))
    if conflict_review_required:
        limit = 0
    elif limit <= 0:
        limit = base_candidate_limit
    return {
        "source": "perturbation_amplitude",
        "band": band,
        "width": str(hint.get("width") or "unknown"),
        "candidate_limit": limit,
        "candidate_limit_after_review": hint.get("candidate_limit_after_review"),
        "route_policy": perturbation_packet.get("route_policy"),
        "stale_conflict_checks_required": bool(
            perturbation_packet.get("stale_conflict_checks_required")
        ),
        "conflict_review_required": conflict_review_required,
    }


def _facet_counts(projected: Sequence[Mapping[str, object]]) -> dict[str, int]:
    counts: dict[str, int] = {layer: 0 for layer in _LAYERS}
    for candidate in projected:
        facet = candidate.get("three_powers_facet")
        if isinstance(facet, Mapping):
            layer = str(facet.get("layer"))
            if layer in counts:
                counts[layer] += 1
    return counts


def _mapping_int(mapping: Mapping[str, object], key: str) -> int:
    value = mapping.get(key)
    return value if type(value) is int else 0


def _diagnostics(
    *,
    active_layer: Layer,
    facet_counts: Mapping[str, int],
    fanout_policy: Mapping[str, object],
) -> list[str]:
    diagnostics: list[str] = []
    if facet_counts.get("earth", 0) > 0 and facet_counts.get("heaven", 0) == 0:
        diagnostics.append("earth_supports_but_heaven_not_ready")
    if facet_counts.get("heaven", 0) > 0 and facet_counts.get("earth", 0) == 0:
        diagnostics.append("heaven_direction_clear_but_earth_evidence_missing")
    if facet_counts.get(active_layer, 0) == 0:
        diagnostics.append(f"active_layer_{active_layer}_has_no_direct_route")
    if fanout_policy.get("stale_conflict_checks_required"):
        diagnostics.append("stale_conflict_checks_required")
    if fanout_policy.get("conflict_review_required"):
        diagnostics.append("inversion_requires_source_reopen_or_conflict_review")
    return diagnostics


def apply_three_powers_fanout(
    query: str,
    route_candidates: Sequence[Mapping[str, Any]],
    *,
    active_layer: object | None = None,
    perturbation_packet: Mapping[str, Any] | None = None,
    topology_hexagram: HexagramRef | None = None,
    parallel_derivation_bundle: Mapping[str, Any] | None = None,
    base_candidate_limit: int = 1,
) -> dict[str, object]:
    layer_profile = infer_active_layer(query, explicit_layer=active_layer)
    layer = str(layer_profile["active_layer"])
    if layer not in _LAYERS:
        raise ValueError(f"unknown Three Powers layer profile: {layer!r}")
    normalized_layer = normalize_layer(layer)
    projected = [
        _project_candidate(candidate, index=index, active_layer=normalized_layer)
        for index, candidate in enumerate(route_candidates)
    ]
    ranked = sorted(
        projected,
        key=lambda item: (
            -_mapping_int(item, "three_powers_rank_score"),
            _mapping_int(item, "input_order"),
        ),
    )
    policy = _fanout_policy(
        perturbation_packet,
        base_candidate_limit=max(0, base_candidate_limit),
    )
    limit = _mapping_int(policy, "candidate_limit")
    preflattening_gate = (
        preflattening_gate_for_route_affordance(parallel_derivation_bundle)
        if parallel_derivation_bundle is not None
        else None
    )
    if preflattening_gate is not None and not preflattening_gate["flattening_allowed"]:
        narrowed_policy = dict(policy)
        original_limit = limit
        if preflattening_gate.get("status") == "tension":
            limit = min(limit, 1)
        else:
            limit = 0
        narrowed_policy["candidate_limit"] = limit
        narrowed_policy["candidate_limit_after_review"] = original_limit
        narrowed_policy["parallel_derivation_preflattening_gate"] = preflattening_gate
        policy = narrowed_policy
    selected = ranked[:limit] if limit > 0 else []
    counts = _facet_counts(projected)
    diagnostics = _diagnostics(
        active_layer=normalized_layer,
        facet_counts=counts,
        fanout_policy=policy,
    )
    topology = (
        line_topology.build_line_topology_diagnostics(topology_hexagram)
        if topology_hexagram is not None
        else None
    )
    if topology is not None:
        reason_codes = topology.get("reason_codes")
        if isinstance(reason_codes, list):
            diagnostics.extend(str(code) for code in reason_codes)
    if preflattening_gate is not None and not preflattening_gate["flattening_allowed"]:
        diagnostics.extend(
            f"parallel_derivation_{code}"
            for code in preflattening_gate.get("reason_codes") or []
        )
    return {
        "kind": "macro_three_powers_route_fanout",
        "schema_version": SCHEMA_VERSION,
        "active_layer": normalized_layer,
        "active_layer_label": _LAYER_LABELS[normalized_layer],
        "layer_profile": layer_profile,
        "ranked_candidates": ranked,
        "selected_route_ids": [str(candidate["route_id"]) for candidate in selected],
        "fanout_policy": policy,
        "parallel_derivation_preflattening_gate": preflattening_gate,
        "facet_counts": counts,
        "topology_diagnostics": topology,
        "diagnostics": diagnostics,
        "authority_level": AUTHORITY_LEVEL,
        "claim_permission": CLAIM_PERMISSION,
        "fact_claim_allowed": False,
        "source_boundary": {
            "route_facets_are_navigation_only": True,
            "source_backed_authority_unchanged": True,
            "no_claim_from_layer_label": True,
        },
    }


__all__ = [
    "AUTHORITY_LEVEL",
    "CLAIM_PERMISSION",
    "Layer",
    "apply_three_powers_fanout",
    "infer_active_layer",
    "normalize_layer",
    "route_facet_metadata",
]
