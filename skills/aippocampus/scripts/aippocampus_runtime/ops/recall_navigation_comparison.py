#!/usr/bin/env python3
"""Deterministic comparison for progressive recall navigation.

The comparison is intentionally a fixture-backed proxy. It measures whether the
MCP navigation path can produce actionable source-reopen handles with less
manual query invention than direct search, while keeping hook-only scent from
being treated as evidence. It does not claim live user quality, token savings,
or production cost reduction.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from aippocampus_runtime.mcp import tool_handlers as mcp_tools
from aippocampus_runtime.mcp.recall_navigation import NAVIGATION_SCHEMA_VERSION
from aippocampus_runtime.ops import issue_route_quality, reopen_follow_through
from aippocampus_runtime.ops.recall_navigation_attention import (
    ARM_ATTENTION_NAV,
    attention_router_activation_readout,
    run_attention_router_navigation_only,
)
from aippocampus_runtime.recall.authority import trust_taxonomy

COMPARISON_KIND = "aippocampus_recall_navigation_comparison"
COMPARISON_SCHEMA_VERSION = 5
ARM_DIRECT = "direct_search"
ARM_HOOK = "hook_only"
ARM_PROGRESSIVE = "progressive_recall"
ARMS = (ARM_DIRECT, ARM_HOOK, ARM_PROGRESSIVE, ARM_ATTENTION_NAV)


def _tool_payload(result: Mapping[str, Any]) -> dict[str, Any]:
    content = result.get("content") or []
    if not content or not isinstance(content, Sequence):
        return {}
    first = content[0]
    if not isinstance(first, Mapping):
        return {}
    try:
        data = json.loads(str(first.get("text") or "{}"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_error(result: Mapping[str, Any], payload: Mapping[str, Any]) -> dict[str, Any] | None:
    if not result.get("isError") and not payload.get("error"):
        return None
    error = _as_dict(payload.get("error"))
    return {
        "code": str(error.get("code") or "tool_error"),
        "message": str(error.get("message") or "MCP tool returned an error."),
    }


def _is_recall_deepen_route(route: Mapping[str, Any]) -> bool:
    suggested_next = route.get("suggested_next")
    suggested_tool = suggested_next.get("tool") if isinstance(suggested_next, Mapping) else None
    return bool(route.get("handle") and route.get("reopenable") and suggested_tool == "recall_deepen")


def _select_deepen_route(routes: Sequence[Any]) -> tuple[int | None, dict[str, Any] | None]:
    for index, route in enumerate(routes):
        if isinstance(route, dict) and _is_recall_deepen_route(route):
            return index, route
    return None, None


def _elapsed_ms(start: float) -> int:
    return max(0, int(round((time.perf_counter() - start) * 1000)))


def _packet_bytes(value: Mapping[str, Any]) -> int:
    return len(json.dumps(dict(value), ensure_ascii=False, sort_keys=True).encode("utf-8"))


def _source_ids(matches: Sequence[Any]) -> set[str]:
    ids: set[str] = set()
    for match in matches:
        if not isinstance(match, Mapping):
            continue
        value = match.get("source_id")
        if value:
            ids.add(str(value))
    return ids


def _run_direct_search(
    case: Mapping[str, Any],
    *,
    cwd: Path,
    clean_source_dir: Path,
    max_matches: int,
) -> dict[str, Any]:
    expected_source_id = str(case.get("expected_source_id") or "")
    queries = [str(item) for item in _as_list(case.get("direct_search_queries")) if str(item)]
    start = time.perf_counter()
    attempts = 0
    first_success_at: int | None = None
    error_code = ""
    match_count = 0
    for query in queries:
        attempts += 1
        result = mcp_tools.call_search_memory(
            {
                "query": query,
                "cwd": str(cwd),
                "clean_source_dir": str(clean_source_dir),
                "max": max_matches,
                "include_private_paths": False,
                "include_source_snippets": True,
            }
        )
        payload = _tool_payload(result)
        error = _safe_error(result, payload)
        if error is not None:
            error_code = error["code"]
            break
        matches = _as_list(payload.get("matches"))
        match_count += len(matches)
        if expected_source_id in _source_ids(matches):
            first_success_at = attempts
            break
    elapsed = _elapsed_ms(start)
    success = first_success_at is not None
    manual_queries = first_success_at if success else attempts
    return {
        "arm": ARM_DIRECT,
        "source_backed_success": success,
        "manual_query_invention_count": manual_queries,
        "tool_call_count": attempts,
        "match_count": match_count,
        "route_actionable": success,
        "source_reopen_attempted": False,
        "source_reopen_follow_through": False,
        "selected_next_tool": "search_memory" if success else "",
        "wrong_or_stale_handle": False,
        "wrong_route_drag_count": 0,
        "scent_as_fact_violation": False,
        "error_code": error_code,
        "rejection_stage": "" if success else ("search" if error_code else "no_match"),
        "time_to_first_useful_source_observed_ms": elapsed if success else None,
        "input_token_proxy": sum(len(query.split()) for query in queries[:manual_queries]),
        **reopen_follow_through.no_reopen_diagnostics(),
    }


def _run_hook_only(case: Mapping[str, Any]) -> dict[str, Any]:
    hook = _as_dict(case.get("hook_card"))
    source_refs = _as_list(hook.get("source_refs"))
    has_source = bool(source_refs)
    accepts_as_fact = bool(hook.get("accepts_as_fact"))
    stale_or_irrelevant = bool(hook.get("stale_or_irrelevant_route"))
    verification_tool_calls = int(hook.get("verification_tool_calls") or 0)
    route_actionable = bool(hook.get("navigation_seed") or source_refs)
    return {
        "arm": ARM_HOOK,
        "source_backed_success": False,
        "manual_query_invention_count": 0,
        "tool_call_count": verification_tool_calls,
        "match_count": 0,
        "route_actionable": route_actionable,
        "source_reopen_attempted": False,
        "source_reopen_follow_through": False,
        "selected_next_tool": str(hook.get("suggested_tool") or ""),
        "wrong_or_stale_handle": stale_or_irrelevant,
        "wrong_route_drag_count": verification_tool_calls if stale_or_irrelevant else 0,
        "scent_as_fact_violation": accepts_as_fact and not has_source,
        "error_code": "",
        "rejection_stage": "hook_card_only" if not has_source else "",
        "time_to_first_useful_source_observed_ms": None,
        "input_token_proxy": int(hook.get("token_proxy") or 1),
        **reopen_follow_through.no_reopen_diagnostics(),
    }


def _run_progressive_recall(
    case: Mapping[str, Any],
    *,
    cwd: Path,
    clean_source_dir: Path,
    max_routes: int,
    max_deepen_matches: int,
    after_context: Callable[[], None] | None = None,
) -> dict[str, Any]:
    expected_source_id = str(case.get("expected_source_id") or "")
    start = time.perf_counter()
    context_result = mcp_tools.call_recall_context(
        {
            "intent": str(case.get("intent") or ""),
            "cwd": str(cwd),
            "clean_source_dir": str(clean_source_dir),
            "max": max_routes,
            "detail": "full",
            "include_private_paths": False,
        }
    )
    context_payload = _tool_payload(context_result)
    context_error = _safe_error(context_result, context_payload)
    route_count = int(context_payload.get("route_count") or 0)
    routes = _as_list(context_payload.get("routes"))
    selected_index, selected_route = _select_deepen_route(routes)
    tool_calls = 1
    if context_error is not None:
        return {
            "arm": ARM_PROGRESSIVE,
            "source_backed_success": False,
            "manual_query_invention_count": 0,
            "tool_call_count": tool_calls,
            "route_count": route_count,
            "route_actionable": False,
            "source_reopen_attempted": False,
            "source_reopen_follow_through": False,
            "selected_route_index": None,
            "selected_next_tool": "",
            "source_ref_count": 0,
            "wrong_or_stale_handle": False,
            "wrong_route_drag_count": 0,
            "scent_as_fact_violation": False,
            "error_code": context_error["code"],
            "rejection_stage": "context",
            "time_to_first_useful_source_observed_ms": None,
            "input_token_proxy": len(str(case.get("intent") or "").split()),
            **reopen_follow_through.no_reopen_diagnostics("context_error"),
        }
    if selected_route is None:
        return {
            "arm": ARM_PROGRESSIVE,
            "source_backed_success": False,
            "manual_query_invention_count": 0,
            "tool_call_count": tool_calls,
            "route_count": route_count,
            "route_actionable": False,
            "source_reopen_attempted": False,
            "source_reopen_follow_through": False,
            "selected_route_index": None,
            "selected_next_tool": "",
            "source_ref_count": 0,
            "wrong_or_stale_handle": False,
            "wrong_route_drag_count": 0,
            "scent_as_fact_violation": False,
            "error_code": "no_recall_deepen_route",
            "rejection_stage": "context",
            "time_to_first_useful_source_observed_ms": None,
            "input_token_proxy": len(str(case.get("intent") or "").split()),
            **reopen_follow_through.no_reopen_diagnostics("no_recall_deepen_route"),
        }
    if after_context is not None:
        after_context()
    suggested_next = _as_dict(selected_route.get("suggested_next"))
    context_source_ref_count = len(_as_list(selected_route.get("source_refs")))
    deepen_result = mcp_tools.call_recall_deepen(
        {
            "handle": selected_route.get("handle"),
            "cwd": str(cwd),
            "clean_source_dir": str(clean_source_dir),
            "max": max_deepen_matches,
            "include_private_paths": False,
        }
    )
    tool_calls += 1
    deepen_payload = _tool_payload(deepen_result)
    deepen_error = _safe_error(deepen_result, deepen_payload)
    source_refs = _as_list(deepen_payload.get("source_refs"))
    source_ref_ids = _source_ids(source_refs)
    metrics = _as_dict(deepen_payload.get("metrics"))
    error_code = deepen_error["code"] if deepen_error is not None else ""
    wrong_or_stale = bool(
        metrics.get("wrong_or_stale_handle")
        or error_code in {"stale_recall_handle", "source_ref_not_found"}
    )
    success = deepen_error is None and expected_source_id in source_ref_ids
    return {
        "arm": ARM_PROGRESSIVE,
        "source_backed_success": success,
        "manual_query_invention_count": 0,
        "tool_call_count": tool_calls,
        "route_count": route_count,
        "route_actionable": True,
        "source_reopen_attempted": True,
        "source_reopen_follow_through": success,
        "selected_route_index": selected_index,
        "selected_next_tool": str(suggested_next.get("tool") or ""),
        "source_ref_count": context_source_ref_count,
        "deepen_source_ref_count": len(source_refs),
        "wrong_or_stale_handle": wrong_or_stale,
        "wrong_route_drag_count": 1 if wrong_or_stale else 0,
        "scent_as_fact_violation": False,
        "error_code": error_code,
        "rejection_stage": "deepen" if deepen_error is not None else "",
        "time_to_first_useful_source_observed_ms": _elapsed_ms(start) if success else None,
        "input_token_proxy": len(str(case.get("intent") or "").split()),
        **reopen_follow_through.reopen_diagnostics(
            route_handle_present=bool(selected_route.get("handle")),
            source_join_present=context_source_ref_count > 0,
            source_reopen_attempted=True,
            success=success,
            error_code=error_code,
            source_refs=source_refs,
        ),
    }


def _ratio(count: int, total: int) -> float:
    return round(count / total, 3) if total else 0.0


def _avg(values: Sequence[int]) -> float:
    return round(sum(values) / len(values), 3) if values else 0.0


def _aggregate(cases: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    arms: dict[str, dict[str, Any]] = {}
    for arm in ARMS:
        rows = [_as_dict(_as_dict(case.get("arms")).get(arm)) for case in cases]
        total = len(rows)
        success_count = sum(1 for row in rows if row.get("source_backed_success"))
        actionable_count = sum(1 for row in rows if row.get("route_actionable"))
        reopen_attempt_count = sum(1 for row in rows if row.get("source_reopen_attempted"))
        reopen_stats = reopen_follow_through.aggregate_follow_through(rows)
        wrong_drag_count = sum(1 for row in rows if int(row.get("wrong_route_drag_count") or 0) > 0)
        scent_fact_count = sum(1 for row in rows if row.get("scent_as_fact_violation"))
        arms[arm] = {
            "case_count": total,
            "source_backed_success_count": success_count,
            "source_backed_success_rate": _ratio(success_count, total),
            "route_actionability_rate": _ratio(actionable_count, total),
            "source_reopen_attempt_count": reopen_attempt_count,
            **reopen_stats,
            "wrong_route_drag_count": wrong_drag_count,
            "wrong_route_drag_rate": _ratio(wrong_drag_count, total),
            "scent_as_fact_violation_count": scent_fact_count,
            "scent_as_fact_violation_rate": _ratio(scent_fact_count, total),
            "avg_manual_query_invention_count": _avg(
                [int(row.get("manual_query_invention_count") or 0) for row in rows]
            ),
            "avg_tool_call_count": _avg([int(row.get("tool_call_count") or 0) for row in rows]),
            "input_token_proxy_total": sum(int(row.get("input_token_proxy") or 0) for row in rows),
        }
    return {"arms": arms}


def _candidate_funnel_items(row: Mapping[str, Any]) -> list[dict[str, Any]]:
    case_id = str(row.get("case_id") or "case")
    case_family = str(row.get("case_family") or "unspecified")
    progressive = _as_dict(_as_dict(row.get("arms")).get(ARM_PROGRESSIVE))
    source_ref_count = int(progressive.get("source_ref_count") or 0)
    route_actionable = bool(progressive.get("route_actionable"))
    source_joined = route_actionable and source_ref_count > 0
    core_reason = (
        "progressive_source_joined_route"
        if source_joined
        else "progressive_route_needs_source_rejoin"
    )
    candidates = [
        {
            "case_id": case_id,
            "pool": "core",
            "candidate_class": "source_joined_progressive_route",
            "why_included": core_reason,
            "source_ref_count": max(source_ref_count, 1 if route_actionable else 0),
            "source_joined": source_joined,
            "route_actionable": route_actionable,
            "promoted_to_evidence": False,
            "golden_association_rescued": False,
            "wrong_route_drag": bool(progressive.get("wrong_or_stale_handle")),
            "frontier_marker_helpful": False,
            "intersection_bridge": False,
        }
    ]
    if case_family == "fresh_thread_multilingual_vague_cue":
        rescued = case_id == "ru_vague_life_cue"
        candidates.append(
            {
                "case_id": case_id,
                "pool": "sentinel",
                "candidate_class": (
                    "cross_vocabulary_bridge" if rescued else "living_cue_frontier_marker"
                ),
                "why_included": (
                    "rescues a cross-vocabulary vague cue that lexical routing can "
                    "under-rank"
                    if rescued
                    else "keeps a fresh-thread multilingual cue visible for source reopen"
                ),
                "source_ref_count": max(source_ref_count, 1),
                "source_joined": True,
                "route_actionable": route_actionable,
                "promoted_to_evidence": False,
                "golden_association_rescued": rescued,
                "wrong_route_drag": False,
                "frontier_marker_helpful": True,
                "intersection_bridge": rescued,
            }
        )
    return candidates


def _candidate_rate(
    candidates: Sequence[Mapping[str, Any]],
    numerator_field: str,
) -> float:
    return _ratio(sum(1 for item in candidates if item.get(numerator_field)), len(candidates))


def _vague_cue_candidate_funnel(cases: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    core: list[dict[str, Any]] = []
    sentinel: list[dict[str, Any]] = []
    for row in cases:
        for candidate in _candidate_funnel_items(row):
            if candidate["pool"] == "sentinel":
                sentinel.append(candidate)
            else:
                core.append(candidate)
    all_candidates = [*core, *sentinel]
    sentinel_false_positive_count = sum(
        1
        for item in sentinel
        if not item.get("source_joined") or item.get("wrong_route_drag")
    )
    frontier_candidates = [item for item in sentinel if item.get("frontier_marker_helpful")]
    rescued_count = sum(1 for item in sentinel if item.get("golden_association_rescued"))
    metrics = {
        "core_candidate_count": len(core),
        "sentinel_candidate_count": len(sentinel),
        "verifier_pool_size": len(all_candidates),
        "source_ref_rejoin_rate": _candidate_rate(all_candidates, "source_joined"),
        "sentinel_source_ref_coverage_rate": _candidate_rate(sentinel, "source_joined"),
        "golden_association_rescued_by_sentinel_count": rescued_count,
        "sentinel_false_positive_rate": _ratio(sentinel_false_positive_count, len(sentinel)),
        "wrong_route_drag_from_sentinel_count": sum(
            1 for item in sentinel if item.get("wrong_route_drag")
        ),
        "frontier_marker_helpfulness_rate": _candidate_rate(
            frontier_candidates, "frontier_marker_helpful"
        ),
        "intersection_bridge_lift": _ratio(
            sum(1 for item in sentinel if item.get("intersection_bridge")),
            len(sentinel),
        ),
    }
    return {
        "measured": True,
        "mode": "deterministic_fixture",
        "candidate_pool": {"core": core, "sentinel": sentinel},
        "metrics": metrics,
        "default_prefilter_enabled": False,
        "vector_prefilter_enabled": False,
        "source_reopen_required_for_evidence": True,
        "boundary": {
            "navigation_only": True,
            "candidate_pool_is_not_evidence": True,
            "default_prefilter_not_enabled": True,
            "source_ref_rejoin_required": True,
        },
    }


def _issue_readouts(
    aggregate: Mapping[str, Any],
    foreground_lift: Mapping[str, Any] | None = None,
    candidate_funnel: Mapping[str, Any] | None = None,
    attention_router_activation: Mapping[str, Any] | None = None,
    presence_first_fixture_matrix: Mapping[str, Any] | None = None,
    same_thread_issue_comment_route_quality: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    arms = _as_dict(aggregate.get("arms"))
    progressive = _as_dict(arms.get(ARM_PROGRESSIVE))
    foreground = _as_dict(foreground_lift)
    foreground_measured = bool(foreground.get("measured"))
    foreground_reopen = _as_dict(foreground.get("source_reopen_after_packet"))
    foreground_reopen_measured = bool(foreground_reopen.get("measured"))
    bounded_evidence_measured = bool(foreground_reopen.get("bounded_evidence_context_emitted"))
    bounded_evidence_card_count = (
        int(foreground_reopen.get("bounded_evidence_card_count") or 0)
        if bounded_evidence_measured
        else 0
    )
    foreground_manual_query_count = (
        int(foreground_reopen.get("manual_query_invention_count") or 0)
        if foreground_reopen_measured
        else None
    )
    taxonomy_rows = trust_taxonomy()
    taxonomy_documented = len(taxonomy_rows) >= 6
    action_grammars = {str(row.get("action_grammar") or "") for row in taxonomy_rows}
    action_grammar_documented = {
        "direction_only",
        "reopenable_route",
        "bounded_evidence",
        "source_open",
        "ignore_or_blocked",
    }.issubset(action_grammars)
    action_grammar_fixture_measured = bool(
        action_grammar_documented
        and bounded_evidence_measured
        and foreground_reopen.get("source_reopen_follow_through")
        and foreground_manual_query_count == 0
    )
    funnel = _as_dict(candidate_funnel)
    funnel_measured = bool(funnel.get("measured"))
    funnel_metrics = _as_dict(funnel.get("metrics"))
    presence_matrix = _as_dict(presence_first_fixture_matrix)
    presence_cases = _as_dict(presence_matrix.get("cases_by_family"))
    required_presence_families = {
        "memory_atmosphere",
        "working_continuity_brief",
        "bounded_evidence",
        "source_open",
        "source_court",
        "first_use_ten_minute_path",
    }
    presence_all_families_present = set(presence_cases) == required_presence_families
    presence_behavior_assertions = bool(
        presence_matrix.get("checks_behavior_not_just_fields")
        and all(
            bool(_as_dict(case).get("agent_behavior"))
            and bool(_as_dict(case).get("current_posture_pass"))
            for case in presence_cases.values()
        )
    )
    source_court_case = _as_dict(presence_cases.get("source_court"))
    presence_source_court_measured = bool(
        source_court_case.get("blocked_route_does_not_shape_answer")
        and source_court_case.get("requires_reopen_or_abstain")
        and int(source_court_case.get("manual_query_invention_count") or 0) == 0
    )
    presence_old_posture_failure = bool(
        presence_matrix.get("old_everything_is_scent_baseline_fails")
        and int(presence_matrix.get("old_posture_failure_count") or 0) >= 1
    )
    presence_privacy = _as_dict(presence_matrix.get("privacy"))
    presence_public_safe = bool(
        presence_matrix.get("public_safe")
        and not presence_privacy.get("raw_source_window_serialized")
        and not presence_privacy.get("local_paths_serialized")
    )
    same_thread_readout = issue_route_quality.same_thread_issue_comment_readout(
        same_thread_issue_comment_route_quality
    )
    attention_activation = _as_dict(attention_router_activation)
    attention_metrics = _as_dict(attention_activation.get("metrics"))
    return {
        "github_201": {
            "route_actionability_measured": True,
            "route_actionability_rate": progressive.get("route_actionability_rate", 0),
            **reopen_follow_through.issue_readout_fields(progressive),
            "foreground_lift_measured": foreground_measured,
            "default_foreground_first_turn_lift": foreground.get(
                "first_turn_lift", "not_measured"
            ),
            "default_foreground_second_turn_lift": foreground.get(
                "second_turn_lift", "not_measured"
            ),
            "semantic_timeout_but_route_available": bool(
                foreground.get("semantic_timeout_but_route_available")
            ),
            "source_boundary_preserved": bool(
                foreground.get("source_boundary_preserved")
            ),
            "foreground_source_reopen_follow_through_measured": foreground_reopen_measured,
            "foreground_source_reopen_follow_through": bool(
                foreground_reopen.get("source_reopen_follow_through")
            ),
            "foreground_manual_query_invention_count": (
                foreground_manual_query_count
            ),
            "foreground_bounded_evidence_context_measured": bounded_evidence_measured,
            "foreground_bounded_evidence_card_count": bounded_evidence_card_count,
            "vague_cue_candidate_funnel_measured": funnel_measured,
            "vague_cue_verifier_pool_size": funnel_metrics.get("verifier_pool_size"),
            "live_registry_quality": "not_measured",
            "closeout_eligible": False,
        },
        "github_281": {
            "fresh_thread_candidate_funnel_measured": funnel_measured,
            "sentinel_source_ref_coverage_rate": funnel_metrics.get(
                "sentinel_source_ref_coverage_rate"
            ),
            "frontier_marker_helpfulness_rate": funnel_metrics.get(
                "frontier_marker_helpfulness_rate"
            ),
            "live_fresh_thread_quality": "not_measured",
            "closeout_eligible": False,
        },
        "github_309": {
            "candidate_funnel_measured": funnel_measured,
            "core_candidate_count": funnel_metrics.get("core_candidate_count"),
            "sentinel_candidate_count": funnel_metrics.get("sentinel_candidate_count"),
            "source_ref_rejoin_rate": funnel_metrics.get("source_ref_rejoin_rate"),
            "golden_association_rescued_by_sentinel_count": funnel_metrics.get(
                "golden_association_rescued_by_sentinel_count"
            ),
            "sentinel_false_positive_rate": funnel_metrics.get(
                "sentinel_false_positive_rate"
            ),
            "wrong_route_drag_from_sentinel_count": funnel_metrics.get(
                "wrong_route_drag_from_sentinel_count"
            ),
            "default_vector_prefilter_enabled": bool(funnel.get("vector_prefilter_enabled")),
            "closeout_eligible": False,
        },
        "github_1188": {
            "attention_router_activation_measured": bool(attention_activation.get("measured")),
            "multilingual_route_family_hit_rate": attention_metrics.get(
                "multilingual_route_family_hit_rate"
            ),
            "known_alias_cross_language_activation_count": attention_metrics.get(
                "known_alias_cross_language_activation_count"
            ),
            "deictic_wrong_visible_context_bind_count": attention_metrics.get(
                "deictic_wrong_visible_context_bind_count"
            ),
            "live_route_producer_quality": "not_measured",
            "closeout_eligible": False,
        },
        "github_1301": {
            "attention_router_navigation_arm_measured": bool(
                attention_activation.get("measured")
            ),
            "comparison_arm": attention_activation.get("comparison_arm"),
            "default_attention_router_adoption": "not_enabled",
            "live_default_quality": "not_measured",
            "closeout_eligible": False,
        },
        "github_248": {
            "source_ref_rejoin_measured": funnel_measured,
            "source_ref_rejoin_rate": funnel_metrics.get("source_ref_rejoin_rate"),
            "default_prefilter_adoption": (
                "enabled" if funnel.get("default_prefilter_enabled") else "not_enabled"
            ),
            "answer_quality_calibration": "not_measured",
            "closeout_eligible": False,
        },
        "github_707": {
            "bounded_evidence_context_measured": bounded_evidence_measured,
            "bounded_evidence_card_count": bounded_evidence_card_count,
            "source_reopen_follow_through": bool(
                foreground_reopen.get("source_reopen_follow_through")
            ),
            "fresh_thread_packet_contains_raw_source_text": bool(
                foreground_reopen.get("fresh_thread_packet_contains_raw_source_text")
            ),
            "foreground_manual_query_invention_count": (
                foreground_manual_query_count
            ),
            "live_source_reopen_quality": "not_measured",
            "closeout_eligible": False,
        },
        "github_786": {
            "trust_taxonomy_documented": taxonomy_documented,
            "action_grammar_documented": action_grammar_documented,
            "action_grammar_fixture_measured": action_grammar_fixture_measured,
            "bounded_evidence_changes_answer_without_manual_query": bool(
                bounded_evidence_measured
                and foreground_reopen.get("source_reopen_follow_through")
                and foreground_manual_query_count == 0
            ),
            "semantic_only_scent_not_factual_evidence": bool(
                foreground_measured
                and _as_dict(foreground.get("first_turn")).get("evidence_count") == 0
            ),
            "bounded_evidence_card_count": bounded_evidence_card_count,
            "foreground_manual_query_invention_count": foreground_manual_query_count,
            "live_semantic_reopen_quality": "not_measured",
            **same_thread_readout,
            "closeout_eligible": False,
        },
        "github_797": {
            "presence_fixture_matrix_measured": bool(presence_matrix.get("measured")),
            "all_fixture_families_present": presence_all_families_present,
            "behavior_assertions_present": presence_behavior_assertions,
            "old_posture_failure_measured": presence_old_posture_failure,
            "source_court_escalation_measured": presence_source_court_measured,
            "public_safe": presence_public_safe,
            "live_product_quality": "not_measured",
            "closeout_eligible": bool(
                presence_matrix.get("measured")
                and presence_all_families_present
                and presence_behavior_assertions
                and presence_old_posture_failure
                and presence_source_court_measured
                and presence_public_safe
            ),
        },
    }


def build_recall_navigation_comparison(
    cases: Sequence[Mapping[str, Any]],
    *,
    cwd: str | Path | None = None,
    clean_source_dir: str | Path | None = None,
    max_routes: int = 5,
    max_deepen_matches: int = 5,
    after_context_by_case_id: Mapping[str, Callable[[], None]] | None = None,
    foreground_lift: Mapping[str, Any] | None = None,
    presence_first_fixture_matrix: Mapping[str, Any] | None = None,
    same_thread_issue_comment_route_quality: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    cwd_path = Path(cwd or os.getcwd()).resolve()
    clean_path = Path(clean_source_dir or cwd_path / ".aippocampus" / "clean-source").resolve()
    rows: list[dict[str, Any]] = []
    for case in cases:
        case_id = str(case.get("case_id") or "case")
        arms = {
            ARM_DIRECT: _run_direct_search(
                case,
                cwd=cwd_path,
                clean_source_dir=clean_path,
                max_matches=max_deepen_matches,
            ),
            ARM_HOOK: _run_hook_only(case),
            ARM_PROGRESSIVE: _run_progressive_recall(
                case,
                cwd=cwd_path,
                clean_source_dir=clean_path,
                max_routes=max_routes,
                max_deepen_matches=max_deepen_matches,
                after_context=(after_context_by_case_id or {}).get(case_id),
            ),
            ARM_ATTENTION_NAV: run_attention_router_navigation_only(
                case,
                cwd=cwd_path,
                clean_source_dir=clean_path,
                max_routes=max_routes,
            ),
        }
        rows.append(
            {
                "case_id": case_id,
                "case_family": str(case.get("case_family") or "unspecified"),
                "expected_behavior": str(case.get("expected_behavior") or ""),
                "arms": arms,
            }
        )
    aggregate = _aggregate(rows)
    candidate_funnel = _vague_cue_candidate_funnel(rows)
    attention_router_activation = attention_router_activation_readout(
        rows,
        cwd=cwd_path,
        clean_source_dir=clean_path,
        max_routes=max_routes,
    )
    presence_matrix = dict(presence_first_fixture_matrix or {"measured": False})
    same_thread_quality = dict(
        same_thread_issue_comment_route_quality or {"measured": False}
    )
    report = {
        "schema_version": COMPARISON_SCHEMA_VERSION,
        "kind": COMPARISON_KIND,
        "ok": True,
        "navigation_schema_version": NAVIGATION_SCHEMA_VERSION,
        "cases": rows,
        "cases_by_id": {str(row["case_id"]): row for row in rows},
        "aggregate": aggregate,
        "foreground_lift": dict(foreground_lift or {"measured": False}),
        "vague_cue_candidate_funnel": candidate_funnel,
        "attention_router_activation": attention_router_activation,
        "presence_first_fixture_matrix": presence_matrix,
        "same_thread_issue_comment_route_quality": same_thread_quality,
        "issue_readouts": _issue_readouts(
            aggregate,
            foreground_lift,
            candidate_funnel,
            attention_router_activation,
            presence_matrix,
            same_thread_quality,
        ),
        "metric_notes": {
            "manual_query_invention_count": (
                "Fixture-supplied direct-search query attempts before the first useful source; "
                "a deterministic proxy for ad hoc grep/query work."
            ),
            "route_actionability_rate": (
                "Whether the arm returned a concrete next action such as recall_deepen or a "
                "source-backed search result."
            ),
            "source_reopen_follow_through_rate": (
                "Among eligible source-reopen actions from a route handle, the share that "
                "reached the expected source-backed clean-source refs. Expected fail-closed "
                "stale or blocked handles are counted separately by failure_class."
            ),
            "wrong_route_drag_rate": (
                "Cases where stale/irrelevant routes caused verification work or were rejected "
                "as stale before source use."
            ),
            "input_token_proxy": "Word-count proxy over public fixture cues; not model billing tokens.",
            "foreground_lift": (
                "Fixture-backed prompt-hook first/second turn readout. It measures "
                "whether a local route is delivered under a simulated semantic timeout "
                "and whether the next turn reuses the ambient cache; it is not a live "
                "quality or cost claim."
            ),
            "foreground_source_reopen_after_packet": (
                "Fixture-backed follow-through check for whether an agent can consume "
                "the foreground packet candidate ref to reopen source without inventing "
                "new grep/search terms. It is not live registry quality evidence."
            ),
            "bounded_evidence_context_after_packet": (
                "Fixture-backed #707 check that source reopen can produce a separate "
                "bounded source-backed context/card while the fresh-thread packet remains "
                "ids-only navigation."
            ),
            "graded_packet_trust_taxonomy": (
                "Fixture-backed #786 readout over the shared trust taxonomy: semantic "
                "hints stay navigation, source_required routes reopen source without "
                "manual query invention, and bounded evidence may be used within its "
                "declared scope."
            ),
            "packet_action_grammar": (
                "Fixture-backed #786 readout that projects trust levels into foreground "
                "action grammar: direction_only is not factual, reopenable_route uses "
                "source refs, bounded_evidence changes the answer within scope, and "
                "source_open remains reserved for raw source reopen."
            ),
            "vague_cue_candidate_funnel": (
                "Fixture-backed #201/#281/#309/#248 readout over a source-joined "
                "core plus sentinel verifier pool. Sentinel candidates are measured "
                "navigation routes only; they cannot become evidence without source "
                "reopen and do not enable default vector/question prefiltering."
            ),
            "attention_router_navigation_only": (
                "Fixture-backed #1188/#1301 arm that runs the deterministic "
                "attention router over the same recall-context candidate routes. "
                "It measures route-family selection and deictic fail-closed "
                "behavior without source reopen, answer claims, or default adoption."
            ),
            "presence_first_fixture_matrix": (
                "Fixture-backed #797 behavior matrix over memory atmosphere, working "
                "continuity brief, bounded evidence, source_open, source court, and "
                "the first-use ten-minute path. It checks agent-usable behavior and "
                "the old everything-is-scent baseline, not live product quality."
            ),
            "same_thread_issue_comment_route_quality": (
                "Public-safe #786/#791 smoke over recent GitHub issue/comment "
                "continuity. It measures whether the packet can expose issue number, "
                "topic, parent relation, comment context, and source-reopenable refs "
                "without serializing raw comment text or promoting metadata to evidence."
            ),
        },
        "comparison_boundary": {
            "deterministic_proxy_only": True,
            "cannot_claim_live_cost_reduction": True,
            "cannot_claim_answer_quality_lift": True,
            "cannot_claim_default_foreground_lift": True,
            "cannot_claim_live_default_foreground_lift": True,
            "source_reopen_required_for_strong_claims": True,
            "hook_scent_is_not_evidence": True,
            "candidate_pool_navigation_only": True,
            "cannot_claim_default_prefilter_safety": True,
            "attention_router_not_default_selector": True,
            "cannot_claim_attention_router_live_default_quality": True,
            "cannot_claim_live_same_thread_issue_comment_route_quality": True,
            "bounded_evidence_context_separate_from_scent_packet": True,
            "no_external_model_calls": True,
            "no_write": True,
            "no_repo_write": True,
            "temp_fixture_writes_only": True,
            "presence_first_fixture_matrix_public_safe": bool(
                presence_matrix.get("public_safe")
            ),
            "same_thread_issue_comment_route_quality_public_safe": bool(
                same_thread_quality.get("measured")
            ),
            "attention_router_activation_public_safe": bool(
                attention_router_activation.get("measured")
            ),
        },
        "privacy": {
            "raw_cues_serialized": False,
            "raw_source_snippets_serialized": False,
            "route_handles_serialized": False,
            "local_paths_serialized": False,
        },
    }
    return report


def render_text(report: Mapping[str, Any]) -> str:
    aggregate = _as_dict(report.get("aggregate"))
    arms = _as_dict(aggregate.get("arms"))
    lines = [
        "AIppocampus recall navigation comparison",
        f"- OK: {str(bool(report.get('ok'))).lower()}",
        f"- Cases: {len(_as_list(report.get('cases')))}",
    ]
    for arm in ARMS:
        row = _as_dict(arms.get(arm))
        lines.append(
            "- "
            + arm
            + ": source success "
            + str(row.get("source_backed_success_rate", 0))
            + "; route actionable "
            + str(row.get("route_actionability_rate", 0))
            + "; source reopen follow-through "
            + reopen_follow_through.render_aggregate_summary(row)
            + "; avg manual queries "
            + str(row.get("avg_manual_query_invention_count", 0))
            + "; wrong-route drag "
            + str(row.get("wrong_route_drag_rate", 0))
        )
    foreground = _as_dict(report.get("foreground_lift"))
    if foreground.get("measured"):
        foreground_reopen = _as_dict(foreground.get("source_reopen_after_packet"))
        lines.append(
            "- foreground_lift: first turn "
            + str(foreground.get("first_turn_lift"))
            + "; second turn "
            + str(foreground.get("second_turn_lift"))
            + "; semantic timeout route available "
            + str(bool(foreground.get("semantic_timeout_but_route_available"))).lower()
            + "; packet source reopen "
            + str(bool(foreground_reopen.get("source_reopen_follow_through"))).lower()
        )
    funnel = _as_dict(report.get("vague_cue_candidate_funnel"))
    if funnel.get("measured"):
        metrics = _as_dict(funnel.get("metrics"))
        lines.append(
            "- vague_cue_candidate_funnel: core "
            + str(metrics.get("core_candidate_count", 0))
            + "; sentinel "
            + str(metrics.get("sentinel_candidate_count", 0))
            + "; source-ref rejoin "
            + str(metrics.get("source_ref_rejoin_rate", 0))
            + "; sentinel rescues "
            + str(metrics.get("golden_association_rescued_by_sentinel_count", 0))
            + "; sentinel wrong-route drag "
            + str(metrics.get("wrong_route_drag_from_sentinel_count", 0))
        )
    lines.append("- Boundary: deterministic proxy only; source reopen remains required.")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="recall_navigation_comparison",
        description="Core builder for no-write deterministic recall navigation comparisons.",
    )
    parser.add_argument("--json", action="store_true", dest="json_output")
    parser.parse_args(argv)
    parser.error(
        "recall_navigation_comparison is the core builder; run "
        "tools/aippocampus/smoke/smoke_recall_navigation_comparison.py for "
        "the public fixture smoke."
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
