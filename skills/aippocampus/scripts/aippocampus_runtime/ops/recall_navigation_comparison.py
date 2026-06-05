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

from aippocampus_runtime.mcp import server as mcp_server
from aippocampus_runtime.mcp.recall_navigation import NAVIGATION_SCHEMA_VERSION

COMPARISON_KIND = "aippocampus_recall_navigation_comparison"
COMPARISON_SCHEMA_VERSION = 2
ARM_DIRECT = "direct_search"
ARM_HOOK = "hook_only"
ARM_PROGRESSIVE = "progressive_recall"
ARMS = (ARM_DIRECT, ARM_HOOK, ARM_PROGRESSIVE)


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
        result = mcp_server.call_search_memory(
            {
                "query": query,
                "cwd": str(cwd),
                "clean_source_dir": str(clean_source_dir),
                "max": max_matches,
                "include_private_paths": False,
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
    context_result = mcp_server.call_recall_context(
        {
            "intent": str(case.get("intent") or ""),
            "cwd": str(cwd),
            "clean_source_dir": str(clean_source_dir),
            "max": max_routes,
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
        }
    if after_context is not None:
        after_context()
    suggested_next = _as_dict(selected_route.get("suggested_next"))
    deepen_result = mcp_server.call_recall_deepen(
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
        "source_ref_count": len(source_refs),
        "wrong_or_stale_handle": wrong_or_stale,
        "wrong_route_drag_count": 1 if wrong_or_stale else 0,
        "scent_as_fact_violation": False,
        "error_code": error_code,
        "rejection_stage": "deepen" if deepen_error is not None else "",
        "time_to_first_useful_source_observed_ms": _elapsed_ms(start) if success else None,
        "input_token_proxy": len(str(case.get("intent") or "").split()),
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
        reopen_follow_count = sum(1 for row in rows if row.get("source_reopen_follow_through"))
        wrong_drag_count = sum(1 for row in rows if int(row.get("wrong_route_drag_count") or 0) > 0)
        scent_fact_count = sum(1 for row in rows if row.get("scent_as_fact_violation"))
        arms[arm] = {
            "case_count": total,
            "source_backed_success_count": success_count,
            "source_backed_success_rate": _ratio(success_count, total),
            "route_actionability_rate": _ratio(actionable_count, total),
            "source_reopen_attempt_count": reopen_attempt_count,
            "source_reopen_follow_through_count": reopen_follow_count,
            "source_reopen_follow_through_rate": _ratio(
                reopen_follow_count, reopen_attempt_count
            ),
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


def _issue_readouts(
    aggregate: Mapping[str, Any],
    foreground_lift: Mapping[str, Any] | None = None,
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
    return {
        "github_201": {
            "route_actionability_measured": True,
            "route_actionability_rate": progressive.get("route_actionability_rate", 0),
            "source_reopen_follow_through_measured": True,
            "source_reopen_follow_through_rate": progressive.get(
                "source_reopen_follow_through_rate", 0
            ),
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
                int(foreground_reopen.get("manual_query_invention_count") or 0)
                if foreground_reopen_measured
                else None
            ),
            "foreground_bounded_evidence_context_measured": bounded_evidence_measured,
            "foreground_bounded_evidence_card_count": bounded_evidence_card_count,
            "live_registry_quality": "not_measured",
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
                int(foreground_reopen.get("manual_query_invention_count") or 0)
                if foreground_reopen_measured
                else None
            ),
            "live_source_reopen_quality": "not_measured",
            "closeout_eligible": False,
        }
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
    report = {
        "schema_version": COMPARISON_SCHEMA_VERSION,
        "kind": COMPARISON_KIND,
        "ok": True,
        "navigation_schema_version": NAVIGATION_SCHEMA_VERSION,
        "cases": rows,
        "cases_by_id": {str(row["case_id"]): row for row in rows},
        "aggregate": aggregate,
        "foreground_lift": dict(foreground_lift or {"measured": False}),
        "issue_readouts": _issue_readouts(aggregate, foreground_lift),
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
                "Among attempted source-reopen actions from a route handle, the share that "
                "reached the expected source-backed clean-source refs."
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
        },
        "comparison_boundary": {
            "deterministic_proxy_only": True,
            "cannot_claim_live_cost_reduction": True,
            "cannot_claim_answer_quality_lift": True,
            "cannot_claim_default_foreground_lift": True,
            "cannot_claim_live_default_foreground_lift": True,
            "source_reopen_required_for_strong_claims": True,
            "hook_scent_is_not_evidence": True,
            "bounded_evidence_context_separate_from_scent_packet": True,
            "no_external_model_calls": True,
            "no_write": True,
            "no_repo_write": True,
            "temp_fixture_writes_only": True,
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
            + str(row.get("source_reopen_follow_through_rate", 0))
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
