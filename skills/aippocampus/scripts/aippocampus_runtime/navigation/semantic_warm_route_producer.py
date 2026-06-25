"""Project background semantic warming into attention-router route material.

Semantic scouts are useful for candidate generation, aliases, topic reuse, and
route fingerprints. They are not a foreground truth source. This module keeps
that boundary explicit by turning already-materialized scout output into the
existing route-token shape, then letting the deterministic hot router consume
those tokens.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from aippocampus_runtime.core import stable_text_non_null_join_id
from aippocampus_runtime.navigation import attention_hot_router
from aippocampus_runtime.warm_ambient import scout_profiles

SEMANTIC_WARM_ROUTE_KIND = "aippocampus_semantic_warm_route_producer_fixture"
SCHEMA_VERSION = 1


def _strings(value: Any, *, limit: int = 8) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []
    result = []
    for item in value:
        text = str(item or "").strip()
        if text:
            result.append(text[:120])
        if len(result) >= limit:
            break
    return result


def _terms(*values: Any) -> list[str]:
    terms: set[str] = set()
    for value in values:
        if isinstance(value, str):
            parts = value.replace("_", " ").replace("-", " ").split()
            terms.update(part.strip(".,:;()[]{}").lower() for part in parts if part.strip())
        elif isinstance(value, (list, tuple, set)):
            terms.update(str(part).strip().lower() for part in value if str(part).strip())
    return sorted(terms)


def _source_handle_from_ref(ref: Mapping[str, Any]) -> dict[str, Any]:
    handle: dict[str, Any] = {
        "source_id": str(ref.get("source_id") or "unknown_source"),
        "segment_id": str(ref.get("segment_id") or ref.get("message_id") or "unknown_segment"),
        "reopen_required": True,
    }
    line_range = ref.get("line_range")
    if isinstance(line_range, (list, tuple)) and len(line_range) == 2:
        handle["line_range"] = [int(line_range[0]), int(line_range[1])]
    turn_range = ref.get("turn_range")
    if isinstance(turn_range, (list, tuple)) and len(turn_range) == 2:
        handle["turn_range"] = [int(turn_range[0]), int(turn_range[1])]
    return handle


def _source_handles(row: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [
        _source_handle_from_ref(ref)
        for ref in row.get("source_refs") or []
        if isinstance(ref, Mapping)
    ]


def _route_metadata(row: Mapping[str, Any]) -> dict[str, str]:
    guard_status = str(row.get("guard_status") or "clear")
    privacy = "private" if guard_status == "blocked" else str(row.get("privacy") or "public")
    return {
        "salience": str(row.get("salience") or "medium"),
        "currentness": str(row.get("currentness") or "needs_reopen"),
        "privacy": privacy,
        "conflict": str(row.get("conflict") or "none"),
    }


def _hard_masks(row: Mapping[str, Any]) -> list[str]:
    masks = {str(mask) for mask in row.get("hard_masks") or []}
    if str(row.get("guard_status") or "") == "blocked":
        masks.add("privacy_domain")
    return sorted(mask for mask in masks if mask)


def project_semantic_warm_route_tokens(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    tokens = []
    for row in rows:
        scout_family = str(row.get("scout_family") or "unknown_scout")
        scout_variant = str(row.get("scout_variant") or "direct")
        source_ref_fingerprints = _strings(row.get("source_ref_fingerprints"))
        candidate_fingerprint = str(row.get("candidate_fingerprint") or "")
        token_id = str(row.get("token_id") or "") or stable_text_non_null_join_id(
            "warmrt",
            scout_family,
            scout_variant,
            candidate_fingerprint,
            source_ref_fingerprints,
        )
        aliases = _strings(row.get("semantic_aliases"))
        source_handles = _source_handles(row)
        tokens.append(
            {
                "kind": "aippocampus_attention_route_token",
                "schema_version": "attention-route-token-v0",
                "token_id": token_id,
                "fixture_case_id": str(row.get("case_id") or token_id),
                "route_token_level": "episode_or_question_token",
                "scope": str(row.get("scope") or "project:AIppocampus"),
                "source_handles": source_handles,
                "hard_masks": _hard_masks(row),
                "route_metadata": _route_metadata(row),
                "route_label": str(row.get("route_label") or "").strip(),
                "why_may_matter": str(row.get("why_may_matter") or "").strip(),
                "risk_flags": _strings(row.get("risk_flags")),
                "triage_rank_reason_codes": _strings(row.get("triage_rank_reason_codes")),
                "route_features": {
                    "terms": _terms(
                        row.get("route_terms"),
                        aliases,
                        scout_family,
                        row.get("topic_epoch_label"),
                    ),
                    "semantic_score": float(row.get("semantic_score") or 0.0),
                    "semantic_aliases": aliases,
                    "scout_family_votes": [scout_family],
                    "source_ref_fingerprints": source_ref_fingerprints,
                    "candidate_fingerprint": candidate_fingerprint,
                    "topic_epoch_label": str(row.get("topic_epoch_label") or ""),
                    "guard_status": str(row.get("guard_status") or "clear"),
                    "cache_status": str(row.get("cache_status") or ""),
                    "source_bridge_status": "ok" if source_handles else "missing",
                },
                "action_grammar": "reopenable_route" if source_handles else "direction_only",
                "claim_permission": "no_claim_before_reopen",
                "token_contract": {
                    "semantic_warm_route_is_not_evidence": True,
                    "source_reopen_required_before_claim": True,
                    "fresh_semantic_model_call_performed": False,
                    "raw_semantic_reasoning_omitted": True,
                },
            }
        )
    return tokens


def _roi_status(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    statuses = []
    for row in rows:
        scout = str(row.get("scout") or "")
        family, _ = scout_profiles.scout_lane_parts(scout)
        lifecycle = scout_profiles.scheduler_lifecycle_status(scout, dict(row))
        router_action = "diagnostic_only" if lifecycle == "retire_candidate" else lifecycle
        statuses.append(
            {
                "scout_family": family,
                "scheduler_lifecycle_status": lifecycle,
                "router_action": router_action,
                "guard_family": family in scout_profiles.REQUIRED_GUARD_FAMILIES,
            }
        )
    return statuses


def _foreground_budget() -> dict[str, dict[str, Any]]:
    budget = {}
    for tier in ("tier0_foreground", "tier1_foreground_warm_read"):
        policy = scout_profiles.scheduler_tier_policy(tier)
        budget[tier] = {
            "fresh_model_calls_allowed": bool(policy["fresh_model_calls_allowed"]),
            "materialized_route_read_allowed": bool(policy["foreground_read_allowed"]),
        }
    return budget


def evaluate_semantic_warm_routes(
    scout_rows: Iterable[Mapping[str, Any]],
    *,
    roi_rows: Iterable[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    rows = list(scout_rows)
    route_tokens = project_semantic_warm_route_tokens(rows)
    query_state = {
        "query": "attention router semantic route",
        "query_terms": ["attention", "router", "semantic", "route"],
        "scope": "project:AIppocampus",
        "risk": "low",
        "privacy_domain": "public",
    }
    packets: list[dict[str, Any]] = attention_hot_router.route_attention(query_state, route_tokens)
    cases: list[dict[str, Any]] = [
        {"case_id": str(token.get("fixture_case_id") or token.get("token_id")), "packet": packet}
        for token, packet in zip(route_tokens, packets, strict=True)
    ]
    roi_status = _roi_status(roi_rows)
    semantic_route_used_as_truth_count = sum(
        1 for packet in packets if packet.get("claim_permission") == "bounded_claim_allowed"
    )
    hard_mask_overrode_semantic_relevance_count = sum(
        1
        for packet in packets
        if packet.get("masks_applied")
        and any(
            vote.get("head") == "semantic_head" and float(vote.get("score") or 0) > 0.9
            for vote in packet.get("head_votes") or []
        )
        and not packet.get("emitted")
    )
    masked_source_resurrection_count = sum(
        1
        for packet in packets
        if packet.get("masks_applied") and packet.get("emitted")
    )
    metrics = {
        "semantic_warm_route_token_count": len(route_tokens),
        "semantic_warm_route_packet_count": len(packets),
        "foreground_fresh_semantic_call_count": 0,
        "foreground_semantic_budget_violation_count": 0,
        "semantic_cache_hit_count": sum(1 for row in rows if row.get("cache_status") == "cache_hit"),
        "semantic_related_cache_hit_count": sum(1 for row in rows if row.get("cache_status") == "related_hit"),
        "warm_roi_keep_count": sum(1 for row in roi_status if row["router_action"] == "background_default"),
        "warm_roi_watch_count": sum(1 for row in roi_status if row["router_action"] == "watch"),
        "warm_roi_diagnostic_only_count": sum(
            1 for row in roi_status if row["router_action"] == "diagnostic_only"
        ),
        "guard_family_retired_count": sum(
            1
            for row in roi_status
            if row["guard_family"] and row["router_action"] not in {"guard_required"}
        ),
        "semantic_route_used_as_truth_count": semantic_route_used_as_truth_count,
        "hard_mask_overrode_semantic_relevance_count": hard_mask_overrode_semantic_relevance_count,
        "source_bridge_missing_for_semantic_route_count": sum(
            1
            for token in route_tokens
            if token["route_features"]["source_bridge_status"] == "missing"
        ),
        "topic_epoch_reuse_by_fingerprint_count": sum(
            1
            for row in rows
            if row.get("topic_epoch_action") == "reuse"
            and (row.get("source_ref_fingerprints") or row.get("candidate_fingerprint"))
        ),
        "raw_prompt_fuzzy_match_count": 0,
    }
    red_lines = {
        "foreground_fresh_semantic_call_count": metrics["foreground_fresh_semantic_call_count"],
        "foreground_semantic_budget_violation_count": metrics[
            "foreground_semantic_budget_violation_count"
        ],
        "semantic_route_used_as_truth_count": semantic_route_used_as_truth_count,
        "guard_family_retired_count": metrics["guard_family_retired_count"],
        "masked_source_resurrection_count": masked_source_resurrection_count,
    }
    ok = all(int(value) == 0 for value in red_lines.values())
    return {
        "kind": SEMANTIC_WARM_ROUTE_KIND,
        "schema_version": SCHEMA_VERSION,
        "ok": ok,
        "cases": cases,
        "route_tokens": route_tokens,
        "metrics": metrics,
        "red_lines": red_lines,
        "foreground_budget": _foreground_budget(),
        "roi_status": roi_status,
        "topic_epoch_policy": {
            "reuse_inputs": [
                "source_ref_fingerprints",
                "candidate_fingerprint",
                "scout_topic_decision",
                "semantic_trigger_id",
                "scope_labels",
            ],
            "raw_prompt_fuzzy_matching_allowed": False,
        },
        "privacy_boundary": {
            "raw_prompt_text_emitted": False,
            "raw_source_text_emitted": False,
            "local_paths_emitted": False,
            "private_ids_emitted": False,
            "raw_semantic_model_reasoning_emitted": False,
        },
        "cannot_claim": [
            "live_semantic_foreground_adoption",
            "semantic_output_as_evidence",
            "private_history_recall_quality",
            "multilingual_benchmark_lift",
            "full_router_quality",
        ],
    }


def fixture_semantic_warm_scout_rows() -> list[dict[str, Any]]:
    return [
        {
            "case_id": "semantic_warmed_reopenable_route",
            "scout_family": "semantic_expander",
            "scout_variant": "direct",
            "semantic_score": 0.86,
            "semantic_aliases": ["attention router", "semantic route"],
            "route_terms": ["attention", "router", "semantic", "route"],
            "source_ref_fingerprints": ["srcfp_public_attention_1"],
            "candidate_fingerprint": "cand_attention_semantic_route",
            "topic_epoch_action": "reuse",
            "topic_epoch_label": "attention-router",
            "cache_status": "cache_hit",
            "guard_status": "clear",
            "source_refs": [
                {
                    "source_id": "clean:attention-router-public",
                    "segment_id": "msg-semantic-route",
                    "line_range": [12, 18],
                    "source_text": "PRIVATE_SOURCE_SENTINEL",
                }
            ],
            "raw_prompt": "PRIVATE_PROMPT_SENTINEL",
            "raw_model_reasoning": "RAW_MODEL_REASONING_SENTINEL",
        },
        {
            "case_id": "semantic_privacy_guard_masked",
            "scout_family": "privacy_boundary_guard",
            "scout_variant": "direct",
            "semantic_score": 0.97,
            "semantic_aliases": ["attention router", "private continuity route"],
            "route_terms": ["attention", "router", "semantic", "route"],
            "source_ref_fingerprints": ["srcfp_private_masked"],
            "candidate_fingerprint": "cand_private_masked",
            "topic_epoch_label": "attention-router",
            "cache_status": "related_hit",
            "guard_status": "blocked",
            "source_refs": [
                {
                    "source_id": "clean:private-redacted",
                    "segment_id": "msg-private-redacted",
                    "line_range": [2, 4],
                    "source_text": "PRIVATE_SOURCE_SENTINEL",
                }
            ],
        },
        {
            "case_id": "semantic_missing_source_bridge_direction_only",
            "scout_family": "trajectory_matcher",
            "scout_variant": "direct",
            "semantic_score": 0.74,
            "semantic_aliases": ["attention route without bridge"],
            "route_terms": ["attention", "router", "semantic", "bridge"],
            "source_ref_fingerprints": [],
            "candidate_fingerprint": "cand_missing_source_bridge",
            "topic_epoch_label": "attention-router",
            "cache_status": "miss",
            "guard_status": "clear",
            "source_refs": [],
        },
    ]


def fixture_warm_roi_rows() -> list[dict[str, Any]]:
    quiet = {
        "classification": "watch",
        "scout_count": 12,
        "useful_result_count": 0,
        "card_candidate_count": 0,
        "accepted_card_count": 0,
        "evidence_candidate_count": 0,
        "accepted_evidence_count": 0,
    }
    return [
        {"scout": "semantic_expander:direct", **quiet},
        {"scout": "privacy_boundary_guard:direct", **quiet},
    ]


def build_semantic_warm_route_fixture_report() -> dict[str, Any]:
    return evaluate_semantic_warm_routes(
        fixture_semantic_warm_scout_rows(),
        roi_rows=fixture_warm_roi_rows(),
    )
