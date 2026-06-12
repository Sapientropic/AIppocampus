"""Project existing recall routes through the attention router.

The helper consumes routes that were already produced by source-backed recall
navigation. It may reorder candidates for a foreground agent packet, but it
must not invent source handles, answer from attention scores, or bypass the
ordinary deepen/source-reopen boundary.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from aippocampus_runtime.navigation import attention_hot_router


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _split_terms(values: Sequence[Any]) -> list[str]:
    seen: set[str] = set()
    terms: list[str] = []
    for value in values:
        for part in str(value or "").replace("_", " ").replace("-", " ").split():
            term = part.strip(".,:;()[]{}").casefold()
            if term and term not in seen:
                seen.add(term)
                terms.append(term)
    return terms


def packet_bytes(value: Mapping[str, Any]) -> int:
    return len(json.dumps(dict(value), ensure_ascii=False, sort_keys=True).encode("utf-8"))


def public_attention_packet(packet: Mapping[str, Any] | None) -> dict[str, Any]:
    if packet is None:
        return {}
    diagnostics = _as_dict(packet.get("router_diagnostics"))
    return {
        "route_id": str(packet.get("route_id") or ""),
        "output_mode": str(packet.get("output_mode") or ""),
        "action_grammar": str(packet.get("action_grammar") or ""),
        "claim_permission": str(packet.get("claim_permission") or ""),
        "emitted": bool(packet.get("emitted")),
        "route_label": str(packet.get("route_label") or ""),
        "source_handle_count": len(_as_list(packet.get("source_handles"))),
        "score": diagnostics.get("score"),
        "threshold": diagnostics.get("threshold"),
        "reason_codes": _as_list(diagnostics.get("reason_codes"))[:6],
    }


def source_handles_for_attention_route(route: Mapping[str, Any]) -> list[dict[str, Any]]:
    handles: list[dict[str, Any]] = []
    for ref in _as_list(route.get("source_refs")):
        if not isinstance(ref, Mapping):
            continue
        source_id = str(ref.get("source_id") or ref.get("thread_key") or "clean_source")
        segment_id = str(
            ref.get("message_id")
            or ref.get("turn_id")
            or ref.get("turn_index")
            or route.get("route_id")
            or "segment"
        )
        handle: dict[str, Any] = {
            "source_id": source_id,
            "segment_id": segment_id,
            "reopen_required": True,
        }
        line = ref.get("line") or ref.get("source_line")
        if line is not None:
            try:
                parsed = int(line)
            except (TypeError, ValueError):
                parsed = None
            if parsed is not None:
                handle["line_range"] = [parsed, parsed]
        handles.append(handle)
    return handles


def attention_terms_for_route(route: Mapping[str, Any]) -> list[str]:
    text = " ".join(
        str(value or "")
        for value in (
            route.get("route_label"),
            route.get("route_topic"),
            route.get("matched_cue_family"),
            route.get("scope_bucket"),
            route.get("summary"),
            " ".join(str(label) for label in route.get("scope_labels") or []),
            " ".join(str(code) for code in route.get("triage_rank_reason_codes") or []),
        )
    )
    return _split_terms([text])[:32]


def attention_token_for_route(route: Mapping[str, Any], *, index: int) -> dict[str, Any]:
    currentness = str(route.get("currentness") or "").strip() or "needs_reopen"
    source_handles = source_handles_for_attention_route(route)
    return {
        "kind": "aippocampus_attention_route_token",
        "token_id": str(route.get("route_id") or f"attention_route_{index}"),
        "route_token_level": "source_span_token" if source_handles else "episode_or_question_token",
        "source_handles": source_handles,
        "route_label": str(route.get("route_label") or ""),
        "why_may_matter": str(route.get("why_this_may_matter") or ""),
        "scope": "project:AIppocampus",
        "risk_flags": _as_list(route.get("risk_flags")),
        "triage_rank_reason_codes": _as_list(route.get("triage_rank_reason_codes")),
        "route_metadata": {
            "salience": "high" if index < 2 else "medium",
            "currentness": currentness,
            "privacy": "public",
            "conflict": str(route.get("conflict") or "none"),
        },
        "route_features": {
            "terms": attention_terms_for_route(route),
            "semantic_score": 0.45 if route.get("route_topic") else 0.25,
            "evidence_packaging_score": 0.55 if source_handles else 0.0,
        },
    }


def _token_terms(token: Mapping[str, Any]) -> set[str]:
    features = _as_dict(token.get("route_features"))
    return set(_split_terms(_as_list(features.get("terms"))))


def route_helpfulness_diagnostics(
    *,
    query: str,
    route: Mapping[str, Any] | None,
    packet: Mapping[str, Any] | None = None,
    expected_route_family: str = "",
) -> dict[str, Any]:
    """Return public-safe diagnostics for whether a selected route helps choice.

    This deliberately judges foreground guidance, not source truth. A route can
    be source-reopenable and still be too generic for a fresh agent to choose
    the right deepen call without broad manual search.
    """

    if route is None:
        return {
            "selected_query_term_overlap_count": 0,
            "selected_route_label_specificity_score": 0.0,
            "route_label_specificity_floor": 0.0,
            "route_label_expected_family_match": False,
            "explicit_bridge_reason_present": False,
            "zero_overlap_without_bridge_reason": True,
            "selected_why_may_matter_specific_enough": False,
        }

    query_terms = set(_split_terms([query]))
    route_terms = set(attention_terms_for_route(route))
    label_terms = set(_split_terms([route.get("route_label"), route.get("route_topic")]))
    expected_terms = set(_split_terms([expected_route_family.replace("_", " ")]))
    overlap_count = len(query_terms & route_terms)
    raw_specificity = _float(route.get("route_label_specificity_score"))
    if not raw_specificity and label_terms:
        raw_specificity = 0.35
    family_match = bool(expected_terms and expected_terms & label_terms)
    specificity_floor = raw_specificity
    if expected_terms and not family_match:
        specificity_floor = 0.0
    reason_codes = set(
        _split_terms(
            [
                *(_as_list(_as_dict(packet).get("reason_codes"))),
                *(_as_list(_as_dict(_as_dict(packet).get("router_diagnostics")).get("reason_codes"))),
                *(_as_list(route.get("triage_rank_reason_codes"))),
            ]
        )
    )
    bridge_reason = bool(
        overlap_count
        or family_match
        or {"action_cue_lift", "issue_id_match", "pending_path_match"} & reason_codes
    )
    why_terms = set(_split_terms([route.get("why_this_may_matter")]))
    why_specific = bool(
        specificity_floor >= 0.5
        and (bridge_reason or bool(why_terms & (query_terms | label_terms | expected_terms)))
    )
    return {
        "selected_query_term_overlap_count": overlap_count,
        "selected_route_label_specificity_score": round(raw_specificity, 3),
        "route_label_specificity_floor": round(specificity_floor, 3),
        "route_label_expected_family_match": bool(family_match) if expected_terms else True,
        "explicit_bridge_reason_present": bridge_reason,
        "zero_overlap_without_bridge_reason": overlap_count == 0 and not bridge_reason,
        "selected_why_may_matter_specific_enough": why_specific,
    }


def select_attention_packet(
    packets: Sequence[Mapping[str, Any]],
) -> tuple[int | None, dict[str, Any] | None]:
    ranked: list[tuple[float, int, Mapping[str, Any]]] = []
    for index, packet in enumerate(packets):
        if not packet.get("emitted"):
            continue
        if packet.get("output_mode") != "reopenable_route":
            continue
        score = float(_as_dict(packet.get("router_diagnostics")).get("score") or 0.0)
        ranked.append((score, index, packet))
    if not ranked:
        return None, None
    ranked.sort(key=lambda item: (-item[0], item[1]))
    _, index, packet = ranked[0]
    return index, dict(packet)


def rerank_routes_with_attention_router(
    *,
    query: str,
    routes: Sequence[Mapping[str, Any]],
    max_routes: int,
    project: str = "AIppocampus",
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Return routes reordered by attention-router packet score.

    Only already-emitted, reopenable attention route packets can move to the
    front. All original routes stay present in their original relative order
    after selected attention routes, so this cannot silently erase fallback
    routes or create a stronger evidence claim.
    """

    original_routes = [dict(route) for route in routes]
    tokens = [
        attention_token_for_route(route, index=index)
        for index, route in enumerate(original_routes)
    ]
    query_terms = set(_split_terms([query]))
    packets = attention_hot_router.route_attention(
        {
            "query": query,
            "query_terms": sorted(query_terms),
            "scope": f"project:{project}",
            "risk": "low",
            "privacy_domain": "public",
        },
        tokens,
    )
    ranked: list[tuple[float, int, int, int, Mapping[str, Any]]] = []
    for index, packet in enumerate(packets):
        if packet.get("emitted") and packet.get("output_mode") == "reopenable_route":
            token_terms = _token_terms(tokens[index]) if index < len(tokens) else set()
            query_overlap = len(query_terms & token_terms)
            ranked.append(
                (
                    float(_as_dict(packet.get("router_diagnostics")).get("score") or 0.0),
                    query_overlap,
                    len(token_terms),
                    index,
                    packet,
                )
            )
    # Router scores can saturate for multiple reopenable source routes. The
    # projection tie-break stays inside already-emitted routes and uses only
    # public term-count overlap, so it cannot invent source authority or hide a
    # fallback candidate.
    ranked.sort(key=lambda item: (-item[0], -item[1], -item[2], item[3]))
    ranked_indexes = [index for _score, _overlap, _specificity, index, _packet in ranked]
    seen: set[int] = set()
    reordered: list[dict[str, Any]] = []
    for index in ranked_indexes:
        if index in seen or index >= len(original_routes):
            continue
        route = dict(original_routes[index])
        route["attention_router_rank"] = len(reordered) + 1
        reordered.append(route)
        seen.add(index)
    for index, route in enumerate(original_routes):
        if index not in seen:
            reordered.append(dict(route))
    if ranked:
        selected_score, selected_overlap, selected_specificity, selected_index, selected_packet_raw = ranked[0]
        selected_packet = dict(selected_packet_raw)
        selected_route = (
            original_routes[selected_index]
            if selected_index is not None and selected_index < len(original_routes)
            else None
        )
    else:
        selected_score = 0.0
        selected_overlap = 0
        selected_specificity = 0
        selected_index = None
        selected_packet = None
        selected_route = None
    selected_public = public_attention_packet(selected_packet)
    selected_route_id = str(selected_public.get("route_id") or "")
    original_top = str(original_routes[0].get("route_id") or "") if original_routes else ""
    new_top = str(reordered[0].get("route_id") or "") if reordered else ""
    top_route_changed = bool(original_top and new_top and original_top != new_top)
    helpfulness = route_helpfulness_diagnostics(
        query=query,
        route=selected_route,
        packet=selected_packet,
    )
    applied_but_no_help = bool(
        ranked_indexes
        and not top_route_changed
        and (
            helpfulness["zero_overlap_without_bridge_reason"]
            or helpfulness["route_label_specificity_floor"] < 0.5
            or not helpfulness["selected_why_may_matter_specific_enough"]
        )
    )
    diagnostics = {
        "enabled": True,
        "applied": bool(ranked_indexes),
        "route_count_considered": len(original_routes),
        "ranked_route_count": len(ranked_indexes),
        "selected_route_index_before": selected_index,
        "selected_route_id": selected_route_id,
        "selected_score": selected_score,
        "selected_query_term_overlap_count": selected_overlap,
        "selected_route_term_count": selected_specificity,
        "top_route_changed": top_route_changed,
        "attention_router_applied_but_no_help": applied_but_no_help,
        **helpfulness,
        "foreground_packet_bytes": packet_bytes(selected_public) if selected_public else 0,
        "selected_packet": selected_public,
        "boundary": {
            "attention_router_reorders_existing_routes_only": True,
            "attention_score_is_not_evidence": True,
            "source_reopen_required_for_claims": True,
            "default_adoption_requires_promotion_gate": True,
        },
    }
    return reordered[:max_routes], diagnostics


def maybe_rerank_routes_with_attention_router(
    *,
    enabled: bool,
    query: str,
    routes: Sequence[Mapping[str, Any]],
    max_routes: int,
    project: str = "AIppocampus",
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not enabled:
        return [dict(route) for route in routes], disabled_attention_router_diagnostics()
    return rerank_routes_with_attention_router(
        query=query,
        routes=routes,
        max_routes=max_routes,
        project=project,
    )


def metrics_for_attention_navigation(diagnostics: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "attention_router_applied": bool(diagnostics.get("applied")),
        "attention_router_ranked_route_count": int(diagnostics.get("ranked_route_count") or 0),
        "attention_router_top_route_changed": bool(diagnostics.get("top_route_changed")),
        "attention_router_applied_but_no_help_count": int(
            bool(diagnostics.get("attention_router_applied_but_no_help"))
        ),
        "attention_router_zero_overlap_without_bridge_count": int(
            bool(diagnostics.get("zero_overlap_without_bridge_reason"))
        ),
        "attention_router_route_label_specificity_floor": _float(
            diagnostics.get("route_label_specificity_floor")
        ),
        "attention_router_foreground_packet_bytes": int(
            diagnostics.get("foreground_packet_bytes") or 0
        ),
    }


def disabled_attention_router_diagnostics() -> dict[str, Any]:
    return {
        "enabled": False,
        "applied": False,
        "route_count_considered": 0,
        "ranked_route_count": 0,
        "selected_route_id": "",
        "top_route_changed": False,
        "boundary": {
            "attention_router_reorders_existing_routes_only": True,
            "attention_score_is_not_evidence": True,
            "source_reopen_required_for_claims": True,
            "default_adoption_requires_promotion_gate": True,
        },
    }


__all__ = [
    "attention_terms_for_route",
    "attention_token_for_route",
    "disabled_attention_router_diagnostics",
    "maybe_rerank_routes_with_attention_router",
    "metrics_for_attention_navigation",
    "packet_bytes",
    "public_attention_packet",
    "rerank_routes_with_attention_router",
    "route_helpfulness_diagnostics",
    "select_attention_packet",
    "source_handles_for_attention_route",
]
