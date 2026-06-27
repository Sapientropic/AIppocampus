"""Tier prompt-recall results into foreground decision and opt-in detail.

The prompt hook's compact result is a routing surface, not a diagnostics dump.
Keep the always-present `decision` tier small enough for foreground consumers,
and put route diagnostics or hot-path instrumentation behind explicit
detail/trace projections.
"""

from __future__ import annotations

from typing import Any, Mapping

from aippocampus_runtime.recall.prompt_recall_channels import recall_channel_envelope
from aippocampus_runtime.recall.prompt_recall_evidence import (
    strip_private_fields,
    strip_semantic_gate,
)
from aippocampus_runtime.recall.prompt_recall_projection import (
    route_delivery_diagnostic as resolve_route_delivery_diagnostic,
)
from aippocampus_runtime.subconscious.candidate_router import strip_for_hook

DIAGNOSTIC_DETAIL_LEVELS = {"detail", "trace", "full", "operator"}
TRACE_DETAIL_LEVELS = {"trace", "full", "operator"}


def normalize_detail_level(detail: str | None) -> str:
    value = str(detail or "compact").strip().casefold()
    if value in {"diagnostic", "diagnostics"}:
        return "detail"
    if value in {"operator-json", "operator_json"}:
        return "operator"
    if value in {"detail", "trace", "full", "operator"}:
        return value
    return "compact"


def include_diagnostics(detail: str | None) -> bool:
    return normalize_detail_level(detail) in DIAGNOSTIC_DETAIL_LEVELS


def include_trace(detail: str | None) -> bool:
    return normalize_detail_level(detail) in TRACE_DETAIL_LEVELS


def _dict_or_empty(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def build_result_tiers(
    *,
    outcome: str,
    score: float,
    confidence: str,
    detail: str | None = None,
    foreground_lane: str | None = None,
    foreground_route_profile: str | None = None,
    agent_surface_intent: Mapping[str, Any] | None = None,
    route_delivery_diagnostic: Mapping[str, Any] | None = None,
    hot_path_funnel: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the explicit result-tier envelope for prompt recall decisions."""

    route = _dict_or_empty(route_delivery_diagnostic)
    agent_intent = _dict_or_empty(agent_surface_intent)
    decision_tier = {
        "outcome": outcome,
        "score": round(float(score or 0.0), 3),
        "confidence": str(confidence or "low"),
        "foreground_lane": str(
            foreground_lane or route.get("foreground_lane") or "source_text"
        ),
        "agent_surface_intent": agent_intent,
    }
    if foreground_route_profile or route.get("foreground_route_profile"):
        decision_tier["foreground_route_profile"] = str(
            foreground_route_profile or route.get("foreground_route_profile")
        )
    tiers: dict[str, Any] = {"decision": decision_tier}
    if include_diagnostics(detail):
        tiers["diagnostics"] = {
            "route_delivery_diagnostic": route,
            "agent_surface_intent": agent_intent,
        }
    if include_trace(detail):
        tiers["trace"] = {
            "hot_path_funnel": _dict_or_empty(hot_path_funnel),
        }
    return tiers


def _tier(result: Mapping[str, Any], name: str) -> dict[str, Any]:
    tiers = result.get("result_tiers")
    if not isinstance(tiers, Mapping):
        return {}
    return _dict_or_empty(tiers.get(name))


def result_agent_surface_intent(result: Mapping[str, Any]) -> dict[str, Any]:
    decision = _tier(result, "decision")
    intent = _dict_or_empty(decision.get("agent_surface_intent"))
    if intent:
        return intent
    diagnostics = _tier(result, "diagnostics")
    intent = _dict_or_empty(diagnostics.get("agent_surface_intent"))
    if intent:
        return intent
    return _dict_or_empty(result.get("agent_surface_intent"))


def result_route_delivery_diagnostic(result: Mapping[str, Any]) -> dict[str, Any]:
    diagnostics = _tier(result, "diagnostics")
    route = _dict_or_empty(diagnostics.get("route_delivery_diagnostic"))
    if route:
        return route
    return _dict_or_empty(result.get("route_delivery_diagnostic"))


def update_result_route_delivery_diagnostic(
    result: dict[str, Any],
    patch: Mapping[str, Any],
) -> None:
    """Patch the opt-in diagnostics tier without recreating top-level debug fields."""

    tiers = result.get("result_tiers")
    if not isinstance(tiers, dict):
        return
    diagnostics = tiers.get("diagnostics")
    if not isinstance(diagnostics, dict):
        return
    route = diagnostics.get("route_delivery_diagnostic")
    if not isinstance(route, dict):
        route = {}
        diagnostics["route_delivery_diagnostic"] = route
    route.update(dict(patch))


def result_hot_path_funnel(result: Mapping[str, Any]) -> dict[str, Any]:
    trace = _tier(result, "trace")
    hot_path = _dict_or_empty(trace.get("hot_path_funnel"))
    if hot_path:
        return hot_path
    return _dict_or_empty(result.get("hot_path_funnel"))


def cheap_casual_skip_result(
    prompt: str,
    *,
    query_terms: list[str],
    elapsed_ms: float,
    detail: str | None = None,
) -> dict[str, Any]:
    hot_path_funnel = {
        "decision": "skip",
        "candidate_count": 0,
        "source_reopen_promotion_count": 0,
        "local_only": True,
        "elapsed_ms": elapsed_ms,
        "stages": [
            {
                "stage": "cheap_casual_skip",
                "status": "skip",
                "candidate_count": 0,
                "fallback_reason": "low_value_casual_no_memory_route_intent",
                "elapsed_ms": elapsed_ms,
            }
        ],
    }
    route_delivery_diagnostic = {
        "foreground_profile": "ambient_hot_path",
        "foreground_route_profile": "low_value_casual",
        "foreground_lane": "stay_silent",
        "generic_prompt_term_count": 0,
        "specific_prompt_term_count": 0,
        "foreground_suppression_reasons": ["low_value_casual_no_memory_route_intent"],
        "decision": "skip",
        "semantic_reuse_source": "none",
        "semantic_waited": False,
        "semantic_partial_failure": False,
        "cold_semantic_shadowed": False,
        "background_scheduled": False,
        "hot_path_candidates_after_merge": 0,
        "final_candidate_count": 0,
        "evidence_count": 0,
        "semantic_source_reopen_route": False,
        "semantic_source_reopen_candidate_count": 0,
    }
    return {
        "decision": "skip",
        "score": 0.0,
        "confidence": "low",
        "result_tiers": build_result_tiers(
            outcome="skip",
            score=0.0,
            confidence="low",
            detail=detail,
            foreground_lane="stay_silent",
            foreground_route_profile="low_value_casual",
            agent_surface_intent={},
            route_delivery_diagnostic=route_delivery_diagnostic,
            hot_path_funnel=hot_path_funnel,
        ),
        "query_terms": query_terms,
        "cognitive_map": [],
        "concept_expansions": [],
        "reasons": ["cheap skip: low-value casual prompt has no memory route intent"],
        "candidates": [],
        "evidence": [],
        "working_memory": [],
        "semantic_gate": None,
        "semantic_bridge_diagnostic": None,
        "semantic_cue_cache": None,
        "elapsed_ms": elapsed_ms,
    }


def build_prompt_result_from_state(
    *,
    state: dict[str, Any],
    context: Any,
    start: float,
    detail: str | None,
    elapsed_ms: float,
    deep_archival_requested: bool,
) -> dict[str, Any]:
    top_score = float(state["top_score"])
    working_score = float(state["working_score"])
    decision = str(state["decision"])
    score = round(max(top_score, working_score), 3)
    confidence = "high" if decision == "evidence" else "medium" if decision == "scent" else "low"
    candidates = state["candidates"]
    evidence = state["evidence"]
    semantic_result = state["semantic_result"]
    concept_expansions = state["concept_expansions"]
    hot_path_funnel = state["hot_path_funnel"]
    route_delivery_diagnostic = resolve_route_delivery_diagnostic(state=state)
    agent_surface_intent = _dict_or_empty(state.get("agent_surface_intent"))
    return {
        "decision": decision,
        "score": score,
        "confidence": confidence,
        "result_tiers": build_result_tiers(
            outcome=decision,
            score=score,
            confidence=confidence,
            detail=detail,
            agent_surface_intent=agent_surface_intent,
            route_delivery_diagnostic=route_delivery_diagnostic,
            hot_path_funnel=hot_path_funnel,
        ),
        **context.hook_path_fields(),
        "query_terms": state["query_terms"][:16],
        "cognitive_map": state["cognitive_map_matches"][:4],
        "concept_expansions": concept_expansions[:8],
        "concept_expansion_diagnostic": state["concept_expansion_diagnostic"],
        "reasons": state["reasons"] or ["no ambient recall cue"],
        "candidates": strip_private_fields(candidates[:3]),
        "evidence": evidence[: state["search_budget"]],
        "working_memory": strip_for_hook(state["working_memory_matches"][:3]),
        "ambient_policy": context.ambient_policy_diagnostics,
        "association_diagnostics": context.association_diagnostics,
        "dream_delivery_prefilter": context.dream_delivery_prefilter,
        "semantic_gate": strip_semantic_gate(semantic_result),
        "semantic_gate_reuse": state["semantic_gate_reuse"],
        "scent_threshold_policy": state["threshold_policy"],
        "topic_signal_accumulator": state["topic_signal_write"],
        "semantic_bridge_diagnostic": state["semantic_bridge_diagnostic"],
        "semantic_source_reopen_route": state["semantic_source_reopen_route"],
        "semantic_cue_cache": state["semantic_cue_cache"],
        "recall_channels": recall_channel_envelope(
            candidates=candidates,
            evidence=evidence,
            semantic_result=semantic_result,
            concept_expansions=concept_expansions,
            hot_path_funnel=hot_path_funnel,
            route_delivery_state=state,
        ),
        "elapsed_ms": elapsed_ms,
        "deep_archival_requested": deep_archival_requested,
    }


__all__ = [
    "build_result_tiers",
    "build_prompt_result_from_state",
    "cheap_casual_skip_result",
    "include_diagnostics",
    "include_trace",
    "normalize_detail_level",
    "result_agent_surface_intent",
    "result_hot_path_funnel",
    "result_route_delivery_diagnostic",
    "update_result_route_delivery_diagnostic",
]
