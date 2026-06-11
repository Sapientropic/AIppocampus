from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from aippocampus_runtime.macro import state as macro_state
from aippocampus_runtime.macro import three_powers
from aippocampus_runtime.macro.hexagram import perturbation_band
from aippocampus_runtime.navigation import attention_hot_router

AUTHORITY_LEVEL = "navigation_only"
ACTION_GRAMMAR = "direction_only"
CLAIM_PERMISSION = "no_claim_before_reopen"
SCHEMA_VERSION = 1


def _macro_entry(value: Mapping[str, Any]) -> Mapping[str, Any]:
    nested = value.get("state")
    return nested if isinstance(nested, Mapping) else value


def _project_scope(entry: Mapping[str, Any]) -> str:
    scope = entry.get("scope")
    if isinstance(scope, Mapping) and scope.get("kind") == "project":
        return f"project:{scope.get('project')}"
    return "project:unknown"


def _relation_position(entry: Mapping[str, Any]) -> Mapping[str, Any]:
    relation = entry.get("relation_position")
    return relation if isinstance(relation, Mapping) else {}


def _role_code(value: object) -> str:
    text = str(value or "")
    if text in {"世", "shi"}:
        return "shi"
    if text in {"应", "ying"}:
        return "ying"
    return text or "unknown"


def _active_layer(entry: Mapping[str, Any]) -> str:
    relation = _relation_position(entry)
    try:
        return three_powers.normalize_layer(relation.get("active_layer") or "human")
    except ValueError:
        return "human"


def _mapping(entry: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = entry.get(key)
    return value if isinstance(value, Mapping) else {}


def _int_value(value: object, default: int = 0) -> int:
    return value if type(value) is int else default


def _fanout_bias(perturbation: Mapping[str, Any]) -> str:
    route_policy = str(perturbation.get("route_policy") or "")
    movement = str(perturbation.get("movement") or "")
    if "reopen" in route_policy or movement == "inversion":
        return "reopen_source"
    if "broad" in route_policy or movement == "large_shift":
        return "wide"
    if "perspective" in route_policy:
        return "normal"
    if "bounded" in route_policy or movement == "local_adjustment":
        return "narrow"
    return "normal"


def build_macro_router_context(value: Mapping[str, Any]) -> dict[str, Any]:
    entry = _macro_entry(value)
    relation = _relation_position(entry)
    movement = _mapping(entry, "movement")
    hexagram = _mapping(entry, "hexagram")
    perturbation = _mapping(entry, "perturbation")
    momentum = _mapping(entry, "momentum")
    changing_lines = [
        _int_value(line)
        for line in entry.get("changing_lines", [])
        if type(line) is int and 1 <= line <= 6
    ]
    changed_line_count = _int_value(perturbation.get("changed_line_count"), len(changing_lines))
    band = perturbation_band(max(0, min(6, changed_line_count)))
    active_layer = _active_layer(entry)
    return {
        "kind": "macro_router_context",
        "schema_version": SCHEMA_VERSION,
        "scope": _project_scope(entry),
        "authority_level": AUTHORITY_LEVEL,
        "action_grammar": ACTION_GRAMMAR,
        "claim_permission": CLAIM_PERMISSION,
        "fact_claim_allowed": False,
        "active_layer": active_layer,
        "relation_position": {
            "situation_role": _role_code(relation.get("situation_role")),
            "current_agent_default_role": _role_code(relation.get("current_agent_default_role")),
        },
        "hexagram_state": {
            "name": hexagram.get("name"),
            "changing_lines": changing_lines,
            "toward": movement.get("toward"),
            "perturbation_band": band,
        },
        "momentum": {
            "phase": momentum.get("phase"),
            "direction": momentum.get("direction"),
        },
        "router_effects": {
            "preferred_route_layers": [active_layer],
            "fanout_bias": _fanout_bias(perturbation),
            "recheck_triggers": [str(item) for item in entry.get("recheck_on", [])],
        },
        "source_boundary": {
            "macro_context_is_navigation_prior": True,
            "hard_masks_still_run_first": True,
            "not_source_backed_fact": True,
            "hot_router_must_not_mutate_macro_state": True,
        },
    }


def _packet_layer(packet: Mapping[str, Any]) -> str:
    direct = packet.get("macro_layer") or packet.get("active_layer")
    if direct:
        try:
            return three_powers.normalize_layer(direct)
        except ValueError:
            return "human"
    facet = packet.get("three_powers_facet")
    if isinstance(facet, Mapping):
        try:
            return three_powers.normalize_layer(facet.get("layer"))
        except ValueError:
            return "human"
    metadata = packet.get("route_metadata")
    if isinstance(metadata, Mapping) and metadata.get("layer"):
        try:
            return three_powers.normalize_layer(metadata.get("layer"))
        except ValueError:
            return "human"
    return "human"


def _reason_codes(packet: Mapping[str, Any]) -> list[str]:
    diagnostics = packet.get("router_diagnostics")
    if isinstance(diagnostics, Mapping):
        raw = diagnostics.get("reason_codes")
        if isinstance(raw, list):
            return [str(code) for code in raw]
    raw = packet.get("reason_codes")
    if isinstance(raw, list):
        return [str(code) for code in raw]
    return []


def _source_handle_count(packet: Mapping[str, Any]) -> int:
    handles = packet.get("source_handles")
    return len(handles) if isinstance(handles, list) else 0


def _layer_distribution(packets: Sequence[Mapping[str, Any]]) -> dict[str, float]:
    counts = {"earth": 0, "human": 0, "heaven": 0}
    if not packets:
        return {layer: 0.0 for layer in counts}
    for packet in packets:
        counts[_packet_layer(packet)] += 1
    total = float(len(packets))
    return {layer: round(count / total, 3) for layer, count in counts.items()}


def build_router_macro_observation(
    *,
    scope: str,
    router_packets: Sequence[Mapping[str, Any]],
    source_event_refs: Sequence[str] = (),
) -> dict[str, Any]:
    total = max(1, len(router_packets))
    emitted = [packet for packet in router_packets if packet.get("emitted", True)]
    source_supported = sum(1 for packet in router_packets if _source_handle_count(packet) > 0)
    reason_codes = [code for packet in router_packets for code in _reason_codes(packet)]
    stale_conflict = sum(1 for code in reason_codes if "stale" in code or "conflict" in code)
    repeated_failures = sum(1 for code in reason_codes if "repeated_route_failure" in code)
    distribution = _layer_distribution(router_packets)
    active_layer = max(distribution, key=lambda layer: distribution[layer])
    update_reasons = ["router_observation_only"]
    if stale_conflict:
        update_reasons.append("stale_or_conflict_observed")
    if repeated_failures:
        update_reasons.append("repeated_route_failure")
    return {
        "kind": "router_macro_observation",
        "schema_version": SCHEMA_VERSION,
        "scope": scope,
        "authority_level": AUTHORITY_LEVEL,
        "action_grammar": ACTION_GRAMMAR,
        "claim_permission": CLAIM_PERMISSION,
        "fact_claim_allowed": False,
        "source_event_refs": list(source_event_refs),
        "observed_layer_distribution": distribution,
        "signals": {
            "route_success_delta": round(len(emitted) / total, 3),
            "support_delta": round(source_supported / total, 3),
            "counter_evidence_delta": round(stale_conflict / total, 3),
            "staleness_delta": round(stale_conflict / total, 3),
            "repeated_route_failure_count": repeated_failures,
            "stale_conflict_count": stale_conflict,
        },
        "candidate_macro_update": {
            "movement_state": "stalled" if stale_conflict or repeated_failures else "advanced",
            "active_layer": active_layer,
            "reason_codes": update_reasons,
            "eligible_for_macro_update": bool(source_event_refs),
        },
        "write_mode": "observation_only_no_hot_path_write",
        "macro_state_mutation_count": 0,
        "source_boundary": {
            "router_observation_is_not_macro_write": True,
            "source_refs_required_before_macro_update": True,
            "single_hot_router_result_cannot_flip_project_state": True,
        },
    }


def _first_route_id(packet: Mapping[str, Any]) -> str:
    candidates = packet.get("ranked_candidates")
    if isinstance(candidates, list) and candidates and isinstance(candidates[0], Mapping):
        return str(candidates[0].get("route_id") or "")
    return ""


def build_macro_router_interface_fixture_report() -> dict[str, Any]:
    human_state = macro_state.build_macro_orientation_state(
        project="AIppocampus",
        hexagram="乾",
        changing_lines=(1,),
        source_refs=({"source_id": "macro-router-fixture"},),
        updated_at="2026-06-11T10:00:00Z",
        active_layer="人",
        momentum={"basis": {"support_delta": 0.2}},
    )
    earth_state = macro_state.build_macro_orientation_state(
        project="AIppocampus",
        hexagram="乾",
        changing_lines=(1,),
        source_refs=({"source_id": "macro-router-fixture-earth"},),
        updated_at="2026-06-11T10:00:00Z",
        active_layer="地",
    )
    human_context = build_macro_router_context(human_state)
    earth_context = build_macro_router_context(earth_state)
    routes = [
        {"route_id": "earth_tests", "source_family": "tests"},
        {"route_id": "human_issue", "source_family": "issue"},
        {"route_id": "heaven_roadmap", "source_family": "roadmap"},
    ]
    human_fanout = three_powers.apply_three_powers_fanout(
        "macro router",
        routes,
        active_layer=human_context["active_layer"],
    )
    earth_fanout = three_powers.apply_three_powers_fanout(
        "macro router",
        routes,
        active_layer=earth_context["active_layer"],
    )
    masked = attention_hot_router.route_attention(
        {
            "query_terms": ["roadmap", "private"],
            "scope": "project:AIppocampus",
            "privacy_domain": "public",
            "macro_router_context": human_context,
        },
        [
            {
                "token_id": "private_heaven_route",
                "scope": "project:AIppocampus",
                "route_features": {"terms": ["roadmap", "private"]},
                "route_metadata": {"privacy": "private", "salience": "high", "layer": "heaven"},
                "hard_masks": ["privacy_domain"],
                "source_handles": [{"source_id": "private-fixture"}],
            }
        ],
    )[0]
    observation = build_router_macro_observation(
        scope="project:AIppocampus",
        router_packets=[
            {
                "macro_layer": "heaven",
                "emitted": True,
                "source_handles": [{"source_id": "roadmap-fixture"}],
                "router_diagnostics": {
                    "reason_codes": ["stale_or_conflicted_source_reopen"],
                },
            }
        ],
        source_event_refs=("issue:#1243",),
    )
    human_first = _first_route_id(human_fanout)
    earth_first = _first_route_id(earth_fanout)
    metrics = {
        "macro_context_claim_ready_count": int(human_context["fact_claim_allowed"]),
        "masked_macro_bias_emission_count": int(bool(masked.get("emitted"))),
        "hot_path_macro_state_write_count": int(observation["macro_state_mutation_count"]),
        "active_layer_changed_route_order_count": int(human_first != earth_first),
        "router_observation_source_ref_count": len(observation["source_event_refs"]),
    }
    return {
        "kind": "macro_router_interface_fixture_report",
        "schema_version": SCHEMA_VERSION,
        "ok": (
            metrics["macro_context_claim_ready_count"] == 0
            and metrics["masked_macro_bias_emission_count"] == 0
            and metrics["hot_path_macro_state_write_count"] == 0
            and metrics["active_layer_changed_route_order_count"] == 1
            and metrics["router_observation_source_ref_count"] >= 1
        ),
        "macro_context": human_context,
        "human_fanout_first_route": human_first,
        "earth_fanout_first_route": earth_first,
        "masked_packet": masked,
        "router_observation": observation,
        "metrics": metrics,
        "authority_level": AUTHORITY_LEVEL,
        "claim_permission": CLAIM_PERMISSION,
        "cannot_claim": [
            "macro_context_as_evidence",
            "router_observation_as_macro_write",
            "hard_mask_override_from_macro_bias",
        ],
    }


__all__ = [
    "ACTION_GRAMMAR",
    "AUTHORITY_LEVEL",
    "CLAIM_PERMISSION",
    "SCHEMA_VERSION",
    "build_macro_router_context",
    "build_macro_router_interface_fixture_report",
    "build_router_macro_observation",
]
