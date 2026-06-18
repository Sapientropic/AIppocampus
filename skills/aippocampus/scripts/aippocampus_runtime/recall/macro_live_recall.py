"""Opt-in macro orientation adapter for live agent recall.

The macro runtime already owns Yi/Three Powers interpretation. This module is
only the thin recall-facing adapter: it can widen a bounded candidate pool,
prefer the active route layer, and explain the navigation decision. It must not
turn macro state into evidence or a source-support ledger.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from aippocampus_runtime.macro import state as macro_state
from aippocampus_runtime.macro import three_powers
from aippocampus_runtime.navigation import macro_router_interface

MAX_ROUTE_LIMIT = 25


def state_from_projection(projection: Mapping[str, Any]) -> Mapping[str, Any] | None:
    state = projection.get("state")
    return state if isinstance(state, Mapping) else None


def macro_field_projection_from_projection(projection: Mapping[str, Any]) -> Mapping[str, Any] | None:
    for key in (
        "macro_field_projection",
        "macro_field_foreground_projection",
        "foreground_projection",
    ):
        candidate = projection.get(key)
        if isinstance(candidate, Mapping) and candidate.get("kind") == "macro_field_foreground_projection":
            return candidate
    return None


def context_from_projection(projection: Mapping[str, Any]) -> dict[str, Any] | None:
    entry = state_from_projection(projection)
    total = projection.get("macro_total_encoding")
    if (
        projection.get("status") == "current"
        and isinstance(total, Mapping)
        and total.get("status") in {"derived_complete", "explicit_reviewed"}
        and isinstance(total.get("macro_state_hint"), Mapping)
    ):
        context = macro_router_interface.build_macro_router_context(
            total["macro_state_hint"],
            macro_field_projection=macro_field_projection_from_projection(projection),
        )
        context["total_encoder_status"] = total.get("status")
        return context
    if projection.get("status") != "current" or entry is None:
        return None
    return macro_router_interface.build_macro_router_context(
        entry,
        macro_field_projection=macro_field_projection_from_projection(projection),
    )


def recheck_triggers(context: Mapping[str, Any] | None) -> list[str]:
    if context is None:
        return []
    effects = context.get("router_effects")
    if not isinstance(effects, Mapping):
        return []
    return [
        str(item)
        for item in effects.get("recheck_triggers") or []
        if str(item).strip()
    ]


def momentum_recheck_required(context: Mapping[str, Any] | None) -> bool:
    return any(
        trigger.startswith("momentum_") and trigger != "momentum_hibernation_review"
        for trigger in recheck_triggers(context)
    )


def fanout_bias(context: Mapping[str, Any] | None) -> str:
    if context is None:
        return "none"
    effects = context.get("router_effects")
    if not isinstance(effects, Mapping):
        return "normal"
    return str(effects.get("fanout_bias") or "normal")


def effective_route_limit(*, requested_limit: int, context: Mapping[str, Any] | None) -> int:
    """Map macro perturbation width to bounded route fanout.

    The macro state is a navigation prior, not a ranking authority. It may widen
    the candidate pool when the project signal says "look across layers", but
    the same hard cap as normal recall still applies and source reopen remains
    mandatory before factual claims.
    """

    base = max(1, min(MAX_ROUTE_LIMIT, int(requested_limit or 1)))
    bias = fanout_bias(context)
    if bias == "narrow":
        return max(base, 2)
    if bias == "wide":
        return max(base, 8)
    if bias == "reopen_source":
        return max(base, 4)
    if bias == "normal":
        return max(base, 4)
    return base


def perturbation_packet(
    *,
    context: Mapping[str, Any],
    effective_limit: int,
) -> dict[str, Any]:
    effects = context.get("router_effects")
    effects = effects if isinstance(effects, Mapping) else {}
    hexagram_state = context.get("hexagram_state")
    hexagram_state = hexagram_state if isinstance(hexagram_state, Mapping) else {}
    bias = str(effects.get("fanout_bias") or "normal")
    band = hexagram_state.get("perturbation_band") or "unknown"
    return {
        "band": band,
        "route_policy": bias,
        "fanout_hint": {
            "band": band,
            "width": bias,
            "recommended_candidate_limit": max(1, min(MAX_ROUTE_LIMIT, effective_limit)),
        },
        "stale_conflict_checks_required": bool(recheck_triggers(context)),
        "conflict_review_required": False,
    }


def reason_codes(
    *,
    context: Mapping[str, Any] | None,
    projection_status: object,
) -> list[str]:
    if context is None:
        return [
            "macro_orientation_not_applied",
            f"projection_status_{projection_status}",
        ]
    active_layer = str(context.get("active_layer") or "human")
    codes = [
        "macro_orientation_recall_prior",
        *(
            [f"macro_state_{context.get('total_encoder_status')}"]
            if context.get("total_encoder_status")
            else []
        ),
        f"macro_active_layer_{active_layer}",
        f"macro_fanout_{fanout_bias(context)}",
    ]
    if momentum_recheck_required(context):
        codes.append("macro_momentum_recheck")
    return codes


def navigation_diagnostics(
    *,
    projection: Mapping[str, Any],
    context: Mapping[str, Any] | None,
    requested_limit: int,
    effective_limit: int | None = None,
    fanout_result: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    applied = context is not None and projection.get("status") == "current"
    effective = effective_limit if effective_limit is not None else requested_limit
    diagnostics = []
    if fanout_result is not None:
        diagnostics = [
            str(item)
            for item in fanout_result.get("diagnostics") or []
            if str(item).strip()
        ]
    active_layer = str(context.get("active_layer")) if context is not None else None
    degraded_codes: list[str] = []
    total = projection.get("macro_total_encoding")
    if context is None and isinstance(total, Mapping):
        degraded_codes = [
            "macro_state_degraded",
            f"macro_total_status_{total.get('status') or 'unknown'}",
            *[str(code) for code in total.get("reason_codes") or [] if str(code).strip()],
        ]
    return {
        "kind": "macro_navigation_recall_diagnostics",
        "status": "applied" if applied else str(projection.get("status") or "not_applied"),
        "applied": applied,
        "authority_level": macro_state.AUTHORITY_LEVEL,
        "action_grammar": macro_state.ACTION_GRAMMAR,
        "claim_permission": macro_state.CLAIM_PERMISSION,
        "fact_claim_allowed": False,
        "active_layer": active_layer,
        "fanout_bias": fanout_bias(context),
        "requested_max_routes": max(1, min(MAX_ROUTE_LIMIT, int(requested_limit or 1))),
        "effective_max_routes": max(1, min(MAX_ROUTE_LIMIT, int(effective or 1))),
        "recheck_on": recheck_triggers(context),
        "reason_codes": reason_codes(
            context=context,
            projection_status=projection.get("status"),
        )
        + degraded_codes,
        "diagnostics": diagnostics[:6],
        "source_boundary": {
            "macro_context_is_navigation_prior": True,
            "not_source_backed_fact": True,
            "source_reopen_required_before_claim": True,
            "raw_origin_markers_omitted_from_foreground": True,
        },
    }


def route_source_family(route: Mapping[str, Any]) -> str:
    route_topic = str(route.get("route_topic") or "").casefold()
    route_text = " ".join(
        str(route.get(key) or "")
        for key in ("route_label", "summary", "scope_bucket", "matched_cue_family")
    ).casefold()
    combined = f"{route_topic} {route_text}"
    if any(
        cue in combined
        for cue in (
            "roadmap",
            "north star",
            "north_star",
            "thesis",
            "direction",
            "purpose",
            "long horizon",
            "product claim",
        )
    ):
        return "roadmap"
    if any(
        cue in combined
        for cue in (
            "benchmark",
            "quality gate",
            "quality_gate",
            "evidence",
            "fixture",
            "measured",
            "test",
            "readiness",
        )
    ):
        return "benchmark"
    if any(
        cue in combined
        for cue in (
            "issue",
            "backlog",
            "handoff",
            "workflow",
            "triage",
            "next action",
            "pull request",
            "pr",
            "review",
        )
    ):
        return "issue"
    kind = str(route.get("kind") or "")
    if kind in {"continuity_domain", "pathlet"}:
        return "workflow"
    if kind == "source_window":
        return "clean_source"
    return "current_task_route"


def route_label(route: Mapping[str, Any]) -> str:
    explicit = str(route.get("route_label") or "").strip()
    if explicit:
        return explicit
    kind = str(route.get("kind") or "navigation_route").strip() or "navigation_route"
    title = str(route.get("title") or "").strip()
    if title:
        return f"{kind}: {title}"
    return kind


def candidate_for_route(route: Mapping[str, Any], *, index: int) -> dict[str, Any]:
    source_refs = route.get("source_refs")
    source_ref_count = len(source_refs) if isinstance(source_refs, list) else 0
    return {
        "route_id": str(route.get("route_id") or f"route_{index}"),
        "route_label": route_label(route),
        "source_family": route_source_family(route),
        "source_handle_count": 1 if route.get("handle") else source_ref_count,
        "output_mode": "reopenable_route" if route.get("handle") else "direction_only",
    }


def append_unique_codes(
    existing: object,
    codes: list[str],
    *,
    limit: int = 4,
) -> list[str]:
    existing_codes = list(existing) if isinstance(existing, list | tuple) else []
    result: list[str] = []
    for code in [*codes, *existing_codes]:
        clean = str(code).strip()
        if clean and clean not in result:
            result.append(clean)
        if len(result) >= limit:
            break
    return result


def apply_recall_bias(
    *,
    query: str,
    routes: list[dict[str, Any]],
    context: Mapping[str, Any],
    requested_limit: int,
    effective_limit: int,
) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    candidates = [
        candidate_for_route(route, index=index)
        for index, route in enumerate(routes)
    ]
    fanout_result = three_powers.apply_three_powers_fanout(
        query,
        candidates,
        active_layer=context.get("active_layer") or "human",
        perturbation_packet=perturbation_packet(
            context=context,
            effective_limit=effective_limit,
        ),
        base_candidate_limit=effective_limit,
    )
    ranked_raw = fanout_result.get("ranked_candidates")
    ranked_candidates = ranked_raw if isinstance(ranked_raw, list) else []
    projected = {
        str(candidate.get("route_id")): candidate
        for candidate in ranked_candidates
        if isinstance(candidate, Mapping)
    }
    route_by_id = {
        str(route.get("route_id") or f"route_{index}"): dict(route)
        for index, route in enumerate(routes)
    }
    ordered_ids = [
        str(candidate.get("route_id"))
        for candidate in ranked_candidates
        if isinstance(candidate, Mapping)
    ]
    ordered_routes = [route_by_id[route_id] for route_id in ordered_ids if route_id in route_by_id]
    if len(ordered_routes) < len(routes):
        seen = {str(route.get("route_id") or "") for route in ordered_routes}
        ordered_routes.extend(
            dict(route)
            for route in routes
            if str(route.get("route_id") or "") not in seen
        )
    selected = ordered_routes[: max(1, min(MAX_ROUTE_LIMIT, effective_limit))]
    active_layer = str(context.get("active_layer") or "human")
    recheck = momentum_recheck_required(context)
    bias = fanout_bias(context)
    wrong_layer_count = 0
    enriched: list[dict[str, Any]] = []
    for route in selected:
        candidate = projected.get(str(route.get("route_id") or ""))
        facet = candidate.get("three_powers_facet") if isinstance(candidate, Mapping) else None
        facet = facet if isinstance(facet, Mapping) else {}
        facet_layer = str(facet.get("layer") or "human")
        if facet_layer != active_layer:
            wrong_layer_count += 1
        route_codes = [
            f"macro_active_layer_{active_layer}",
            f"macro_facet_{facet_layer}",
            f"macro_fanout_{bias}",
        ]
        if recheck:
            route_codes.append("macro_momentum_recheck")
        route["triage_rank_reason_codes"] = append_unique_codes(
            route.get("triage_rank_reason_codes"),
            route_codes,
        )
        route["risk_flags"] = append_unique_codes(
            route.get("risk_flags"),
            ["macro_recheck_required"] if recheck else [],
            limit=4,
        )
        route["macro_layer"] = facet_layer
        route["macro_source_family"] = str(facet.get("source_family") or "unknown")
        enriched.append(route)
    diagnostics = navigation_diagnostics(
        projection={"status": "current"},
        context=context,
        requested_limit=requested_limit,
        effective_limit=effective_limit,
        fanout_result=fanout_result,
    )
    metrics = {
        "macro_selected_route_count": len(enriched),
        "macro_wrong_layer_route_count": wrong_layer_count,
        "macro_recheck_trigger_count": len(recheck_triggers(context)),
        "macro_reason_code_count": len(diagnostics["reason_codes"]),
        "macro_layer_bias_applied": bool(fanout_result.get("layer_bias_applied")),
        "macro_layer_bias_suppressed_reason": str(
            fanout_result.get("layer_bias_suppressed_reason") or ""
        ),
    }
    return enriched, diagnostics, metrics
