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


def extract_action_query_features(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Extract public-safe action-time query features from a pending action.

    The extractor emits normalized terms and ids only. Raw tool args and command
    text stay out of the report so synthetic fixtures can exercise action-time
    routing without becoming a tool-argument leak path.
    """

    tool_args = payload.get("tool_args")
    args = tool_args if isinstance(tool_args, Mapping) else {}
    file_paths = [str(path) for path in args.get("file_paths") or args.get("paths") or []]
    issue_ids = [str(issue).lstrip("#") for issue in args.get("issue_ids") or []]
    command_terms = _terms(args.get("command_terms") or args.get("command_family"))
    branch_terms = _terms(args.get("branch") or args.get("branch_name"))
    test_terms = _terms(args.get("test_name") or args.get("test_names"))
    path_terms = set()
    for path in file_paths:
        path_terms.update(_terms(path.replace("/", " ").replace("\\", " ")))
    issue_terms = {f"issue{issue}" for issue in issue_ids} | set(issue_ids)
    terms = (
        _terms(payload.get("prompt") or payload.get("intent"))
        | _terms(payload.get("tool_name"))
        | path_terms
        | issue_terms
        | command_terms
        | branch_terms
        | test_terms
    )
    return {
        "phase": str(payload.get("phase") or ""),
        "tool_name": str(payload.get("tool_name") or ""),
        "file_paths": file_paths[:8],
        "issue_ids": issue_ids[:8],
        "topic_epoch": str(payload.get("topic_epoch") or ""),
        "active_recall_locks": [str(lock) for lock in payload.get("active_recall_locks") or []],
        "anti_nag_token_ids": [str(token) for token in payload.get("anti_nag_token_ids") or []],
        "risk": str(payload.get("risk") or ""),
        "terms": sorted(terms),
        "privacy_boundary": {
            "raw_tool_args_emitted": False,
            "raw_command_text_emitted": False,
            "private_text_emitted": False,
        },
    }


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
    action_features = query_state.get("action_features")
    token_terms = _feature_terms(token)
    metadata = _metadata(token)
    lexical = _score_overlap(query_terms, token_terms)
    action_score = _action_score(action_features, token)
    action_reason = _action_reason_code(action_features, token) if action_score > 0 else "no_action_match"
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
        {"head": "action_head", "score": round(action_score, 3), "reason_code": action_reason},
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
        "action_head": 0.24,
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


def _action_score(action_features: Any, token: Mapping[str, Any]) -> float:
    if not isinstance(action_features, Mapping):
        return 0.0
    score = 0.0
    token_terms = _feature_terms(token)
    for path in action_features.get("file_paths") or []:
        if _terms(str(path).replace("/", " ").replace("\\", " ")) & token_terms:
            score += 0.45
            break
    for issue in action_features.get("issue_ids") or []:
        if str(issue) in token_terms or f"issue{issue}" in token_terms:
            score += 0.35
            break
    if {"test", "pytest", "ruff", "mypy"} & _terms(action_features.get("terms")) & token_terms:
        score += 0.20
    if score == 0.0 and _terms(action_features.get("terms")) & token_terms:
        score = 0.35
    return min(1.0, round(score, 3))


def _action_reason_code(action_features: Any, token: Mapping[str, Any]) -> str:
    if not isinstance(action_features, Mapping):
        return "no_action_payload"
    reasons = []
    token_terms = _feature_terms(token)
    for path in action_features.get("file_paths") or []:
        if _terms(str(path).replace("/", " ").replace("\\", " ")) & token_terms:
            reasons.append("pending_path_match")
            break
    for issue in action_features.get("issue_ids") or []:
        if str(issue) in token_terms or f"issue{issue}" in token_terms:
            reasons.append("issue_id_match")
            break
    if {"test", "pytest", "ruff", "mypy"} & _terms(action_features.get("terms")) & token_terms:
        reasons.append("command_failure_chain")
    if not reasons:
        reasons.append("pre_tool_constraint")
    return "+".join(reasons)


def route_attention(
    query_state: Mapping[str, Any],
    route_tokens: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    packets = []
    source_open_ids = set(query_state.get("source_open_token_ids") or [])
    bounded_scope_ids = set(query_state.get("bounded_scope_token_ids") or [])
    anti_nag_ids = set(query_state.get("anti_nag_token_ids") or [])
    action_features = query_state.get("action_features")
    if isinstance(action_features, Mapping):
        anti_nag_ids.update(str(token) for token in action_features.get("anti_nag_token_ids") or [])
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
        action_vote = next((vote for vote in votes if vote.get("head") == "action_head"), None)
        lexical_vote = next((vote for vote in votes if vote.get("head") == "lexical_head"), None)
        if action_vote and lexical_vote and action_vote["score"] > 0.75 and lexical_vote["score"] < 0.5:
            reason_codes.append("action_cue_lift")
        if token_id in anti_nag_ids:
            reason_codes.append("anti_nag_suppressed")
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


def build_action_head_fixture_report() -> dict[str, Any]:
    action_features = extract_action_query_features(
        {
            "prompt": "please handle the next small fix",
            "phase": "implementation",
            "tool_name": "edit",
            "tool_args": {
                "file_paths": [
                    "skills/aippocampus/scripts/aippocampus_runtime/navigation/attention_hot_router.py"
                ],
                "issue_ids": ["1109"],
                "command_family": "pytest",
                "raw_command": "PRIVATE_TOOL_ARG_SENTINEL",
            },
            "topic_epoch": "attention-router",
            "anti_nag_token_ids": ["action_repeated_hint_token"],
            "risk": "low",
        }
    )
    query_state = {
        "query": "please handle the next small fix",
        "query_terms": ["please", "handle", "small", "fix"],
        "scope": "project:AIppocampus",
        "risk": "low",
        "privacy_domain": "public",
        "action_features": action_features,
    }
    tokens = fixture_action_route_tokens()
    packets = route_attention(query_state, tokens)
    cases: list[dict[str, Any]] = [
        {"case_id": str(token.get("fixture_case_id") or token.get("token_id")), "packet": packet}
        for token, packet in zip(tokens, packets, strict=True)
    ]
    action_cue_lift_over_prompt_only_count = 0
    anti_nag_suppressed_count = 0
    masked_action_match_emission_count = 0
    for case in cases:
        packet = case["packet"]
        votes = {str(vote["head"]): vote for vote in packet["head_votes"]}
        if (
            votes.get("action_head", {}).get("score", 0) > 0.75
            and votes.get("lexical_head", {}).get("score", 1) < 0.5
            and packet["output_mode"] == "reopenable_route"
            and not packet["masks_applied"]
            and "anti_nag_suppressed" not in packet["router_diagnostics"]["reason_codes"]
        ):
            action_cue_lift_over_prompt_only_count += 1
        if "anti_nag_suppressed" in packet["router_diagnostics"]["reason_codes"]:
            anti_nag_suppressed_count += 1
        if (
            packet["masks_applied"]
            and votes.get("action_head", {}).get("score", 0) > 0.75
            and packet["emitted"]
        ):
            masked_action_match_emission_count += 1
    return {
        "kind": "aippocampus_attention_action_head_fixture",
        "schema_version": "attention-hot-router-v0",
        "ok": masked_action_match_emission_count == 0,
        "action_features": action_features,
        "cases": cases,
        "metrics": {
            "case_count": len(cases),
            "action_cue_lift_over_prompt_only_count": action_cue_lift_over_prompt_only_count,
            "anti_nag_suppressed_count": anti_nag_suppressed_count,
            "masked_action_match_emission_count": masked_action_match_emission_count,
        },
        "cannot_claim": [
            "live_hook_behavior_lift",
            "default_foreground_action_routing",
            "private_tool_argument_quality",
            "e2e50_behavior_lift",
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


def fixture_action_route_tokens() -> list[dict[str, Any]]:
    source_handle = {
        "source_id": "clean:attention-router",
        "segment_id": "msg-action",
        "reopen_required": True,
        "line_range": [10, 18],
    }
    base = {
        "kind": "aippocampus_attention_route_token",
        "route_token_level": "source_span_token",
        "scope": "project:AIppocampus",
        "source_handles": [source_handle],
        "route_metadata": {
            "salience": "high",
            "currentness": "current",
            "privacy": "public",
            "conflict": "none",
        },
    }
    action_match = {
        **base,
        "token_id": "action_path_issue_token",
        "fixture_case_id": "action_path_issue_match",
        "route_features": {
            "terms": ["attention", "hot", "router", "issue1109", "1109", "pytest"],
            "semantic_score": 0.35,
        },
    }
    private_mask = {
        **action_match,
        "token_id": "action_private_mask_token",
        "fixture_case_id": "action_matched_private_mask",
        "route_metadata": {
            "salience": "high",
            "currentness": "current",
            "privacy": "private",
            "conflict": "none",
        },
    }
    repeated = {
        **action_match,
        "token_id": "action_repeated_hint_token",
        "fixture_case_id": "action_repeated_hint_suppressed",
    }
    return [action_match, private_mask, repeated]
