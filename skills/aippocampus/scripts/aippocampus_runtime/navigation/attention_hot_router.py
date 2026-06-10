"""Deterministic V0 attention router over source-backed route tokens.

This is an auditable prototype for route selection. It is deliberately not a
learned model, not a default foreground hook, and not an answer authority.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from aippocampus_runtime.navigation import attention_route_tokens, attention_router_contract


def _terms(value: Any) -> set[str]:
    if isinstance(value, str):
        raw = value.replace("_", " ").replace("-", " ").split()
        return {part.strip(".,:;()[]{}").lower() for part in raw if part.strip()}
    if isinstance(value, (list, tuple, set)):
        return {str(part).strip().lower() for part in value if str(part).strip()}
    return set()


def _metadata(token: Mapping[str, Any]) -> Mapping[str, Any]:
    metadata = token.get("route_metadata")
    return metadata if isinstance(metadata, Mapping) else {}


def _feature_terms(token: Mapping[str, Any]) -> set[str]:
    features = token.get("route_features")
    if isinstance(features, Mapping):
        terms = _terms(features.get("terms"))
        if terms:
            return terms
    return _terms(
        [
            token.get("token_id"),
            token.get("route_token_level"),
            token.get("group_kind"),
            token.get("span_kind"),
            _metadata(token).get("salience"),
            _metadata(token).get("currentness"),
        ]
    )


def _source_handles(token: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [dict(handle) for handle in token.get("source_handles") or [] if isinstance(handle, Mapping)]


def _score_overlap(query_terms: set[str], token_terms: set[str]) -> float:
    if not query_terms or not token_terms:
        return 0.0
    return len(query_terms & token_terms) / len(query_terms)


def _level_score(value: Any, table: Mapping[str, float], default: float) -> float:
    return table.get(str(value or "").lower(), default)


def _hard_masks(query_state: Mapping[str, Any], token: Mapping[str, Any]) -> list[str]:
    metadata = _metadata(token)
    masks = [str(mask) for mask in token.get("hard_masks") or []]
    if metadata.get("privacy") == "private" and query_state.get("privacy_domain") != "private":
        masks.append("privacy_domain")
    if query_state.get("risk") == "high" and not _source_handles(token):
        masks.append("high_risk_no_source")
    if metadata.get("currentness") == "stale" and not _source_handles(token):
        masks.append("stale_handle_invalid")
    return sorted(set(mask for mask in masks if mask in attention_router_contract.HARD_MASKS))


def _adaptive_threshold(query_state: Mapping[str, Any], token: Mapping[str, Any]) -> float:
    metadata = _metadata(token)
    threshold = 0.55
    if query_state.get("risk") == "high":
        threshold += 0.12
    if metadata.get("conflict") not in {None, "", "none", "unknown"}:
        threshold += 0.10
    if metadata.get("currentness") in {"stale", "needs_reopen"}:
        threshold += 0.05
    if metadata.get("salience") == "high":
        threshold -= 0.05
    if token.get("scope") and token.get("scope") == query_state.get("scope"):
        threshold -= 0.04
    return max(0.2, min(0.9, round(threshold, 3)))


def _head_votes(query_state: Mapping[str, Any], token: Mapping[str, Any]) -> list[dict[str, Any]]:
    query_terms = _terms(query_state.get("query_terms") or query_state.get("query"))
    token_terms = _feature_terms(token)
    metadata = _metadata(token)
    lexical = _score_overlap(query_terms, token_terms)
    semantic = float((token.get("route_features") or {}).get("semantic_score") or 0.0)
    scope = 1.0 if token.get("scope") and token.get("scope") == query_state.get("scope") else 0.4
    salience = _level_score(metadata.get("salience"), {"high": 0.9, "medium": 0.6, "low": 0.3}, 0.45)
    currentness = _level_score(
        metadata.get("currentness"),
        {"current": 0.85, "needs_reopen": 0.55, "stale": 0.25},
        0.45,
    )
    conflict = 0.85 if metadata.get("conflict") in {None, "", "none", "unknown"} else 0.35
    risk = 0.8 if query_state.get("risk") != "high" else 0.45
    abstention = 1.0 - max(lexical, semantic, salience)
    return [
        {"head": "lexical_head", "score": round(lexical, 3), "reason_code": "term_overlap"},
        {"head": "semantic_head", "score": round(semantic, 3), "reason_code": "provided_sidecar_score"},
        {"head": "scope_head", "score": round(scope, 3), "reason_code": "scope_match"},
        {"head": "salience_head", "score": round(salience, 3), "reason_code": "token_salience"},
        {"head": "currentness_head", "score": round(currentness, 3), "reason_code": "token_currentness"},
        {"head": "conflict_head", "score": round(conflict, 3), "reason_code": "conflict_penalty"},
        {"head": "risk_head", "score": round(risk, 3), "reason_code": "query_risk"},
        {"head": "abstention_head", "score": round(abstention, 3), "reason_code": "weak_best_head"},
    ]


def _combined_score(votes: Iterable[Mapping[str, Any]]) -> float:
    weights = {
        "lexical_head": 0.24,
        "semantic_head": 0.18,
        "scope_head": 0.12,
        "salience_head": 0.14,
        "currentness_head": 0.12,
        "conflict_head": 0.10,
        "risk_head": 0.06,
        "abstention_head": -0.08,
    }
    total = 0.0
    for vote in votes:
        total += weights.get(str(vote.get("head")), 0.0) * float(vote.get("score") or 0.0)
    return max(0.0, min(1.0, round(total, 3)))


def route_attention(
    query_state: Mapping[str, Any],
    route_tokens: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    packets = []
    source_open_ids = set(query_state.get("source_open_token_ids") or [])
    bounded_scope_ids = set(query_state.get("bounded_scope_token_ids") or [])
    for token in route_tokens:
        token_id = str(token.get("token_id") or "")
        masks = _hard_masks(query_state, token)
        votes = _head_votes(query_state, token)
        score = _combined_score(votes)
        threshold = _adaptive_threshold(query_state, token)
        handles = _source_handles(token)
        reason_codes = ["adaptive_threshold"]
        if masks:
            reason_codes.append("hard_mask_applied")
        if score < threshold:
            reason_codes.append("below_adaptive_threshold")
            handles = []
        metadata = _metadata(token)
        if metadata.get("currentness") in {"stale", "needs_reopen"} or metadata.get("conflict") not in {
            None,
            "",
            "none",
            "unknown",
        }:
            reason_codes.append("stale_or_conflicted_source_reopen")
        packet = attention_router_contract.build_route_packet(
            {
                "case_id": token_id,
                "route_id": token_id,
                "hard_masks": masks,
                "head_votes": votes,
                "source_handles": handles,
                "source_open": token_id in source_open_ids,
                "bounded_scope": token_id in bounded_scope_ids,
            }
        )
        packet["router_diagnostics"] = {
            "score": score,
            "threshold": threshold,
            "adaptive_threshold": threshold,
            "reason_codes": sorted(set(reason_codes)),
        }
        packets.append(packet)
    return packets


def build_hot_router_fixture_report() -> dict[str, Any]:
    query_state = {
        "query": "router code block route",
        "scope": "project:AIppocampus",
        "risk": "low",
        "privacy_domain": "public",
    }
    tokens = fixture_route_tokens()
    packets = route_attention(query_state, tokens)
    cases: list[dict[str, Any]] = [
        {"case_id": str(token.get("fixture_case_id") or token.get("token_id")), "packet": packet}
        for token, packet in zip(tokens, packets, strict=True)
    ]
    masked_high_score_emission_count = 0
    claim_ready_without_source_open_count = 0
    for case in cases:
        packet = case["packet"]
        if (
            packet["masks_applied"]
            and packet["router_diagnostics"]["score"] > 0.8
            and packet["emitted"]
        ):
            masked_high_score_emission_count += 1
        if packet["claim_permission"] == "bounded_claim_allowed":
            claim_ready_without_source_open_count += 1
    return {
        "kind": "aippocampus_attention_hot_router_fixture",
        "schema_version": "attention-hot-router-v0",
        "ok": masked_high_score_emission_count == 0 and claim_ready_without_source_open_count == 0,
        "cases": cases,
        "metrics": {
            "case_count": len(cases),
            "masked_high_score_emission_count": masked_high_score_emission_count,
            "claim_ready_without_source_open_count": claim_ready_without_source_open_count,
        },
        "cannot_claim": [
            "default_foreground_router_adoption",
            "private_history_router_quality",
            "learned_attention_quality",
            "score_fusion_calibration",
        ],
    }


def fixture_route_tokens() -> list[dict[str, Any]]:
    base = attention_route_tokens.build_route_token_fixture_report()["tokens"]
    positive = dict(base[1])
    positive.update(
        {
            "fixture_case_id": "positive_source_span_route",
            "scope": "project:AIppocampus",
            "route_features": {
                "terms": ["router", "code", "block", "route"],
                "semantic_score": 0.72,
            },
        }
    )
    masked = dict(positive)
    masked.update(
        {
            "token_id": "masked_private_route_token",
            "fixture_case_id": "masked_high_relevance_private_route",
            "route_metadata": {
                "salience": "high",
                "currentness": "current",
                "privacy": "private",
                "conflict": "none",
            },
            "route_features": {
                "terms": ["router", "code", "block", "route"],
                "semantic_score": 0.95,
            },
        }
    )
    stale = dict(positive)
    stale.update(
        {
            "token_id": "stale_conflict_route_token",
            "fixture_case_id": "stale_conflict_reopen_route",
            "route_metadata": {
                "salience": "high",
                "currentness": "needs_reopen",
                "privacy": "public",
                "conflict": "conflicting_update",
            },
            "route_features": {
                "terms": ["router", "route", "stale", "conflict"],
                "semantic_score": 0.70,
            },
        }
    )
    abstain = {
        "kind": "aippocampus_attention_route_token",
        "token_id": "abstention_route_token",
        "fixture_case_id": "abstention_direction_only",
        "route_token_level": "episode_or_question_token",
        "source_handles": [],
        "route_metadata": {
            "salience": "low",
            "currentness": "unknown",
            "privacy": "public",
            "conflict": "none",
        },
        "route_features": {"terms": ["unrelated"], "semantic_score": 0.0},
    }
    return [positive, masked, stale, abstain]
