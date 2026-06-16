#!/usr/bin/env python3
"""Deterministic calibration fixture for segmented-search merge policy.

This runner exercises the user-visible merge policy on public-safe synthetic
hits with stable source refs. It is a calibration smoke, not product-quality
evidence: real recall claims still require Track B source-evidence retrieval
and private/public corpus runs at the appropriate layer.
"""

from __future__ import annotations

import argparse
import copy
import json
import time
from dataclasses import asdict, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import _paths

_paths.ensure_paths()

from aippocampus_runtime.recall.scoring_policy import (  # noqa: E402
    SEGMENT_MERGE_POLICY,
    SegmentMergePolicy,
)
from aippocampus_runtime.recall.segment_search import merge_topk_with_diagnostics  # noqa: E402
from benchmarks.aippocampus.shared.claim_boundary_refs import claim_boundary_ref

SCHEMA_VERSION = 1
DEFAULT_FIXTURE = (
    _paths.REPO_ROOT / "benchmark_corpus" / "segmented_merge_policy" / "fixture.json"
)
REQUIRED_PATTERNS = {
    "cross_segment_diversity",
    "adjacent_turn_pairing",
    "duplicate_nearby_recap_suppression",
    "stable_source_join_dedupe",
    "stale_superseded_currentness",
}
ALTERNATE_POLICIES = {
    "no_diversity_penalties": replace(
        SEGMENT_MERGE_POLICY,
        same_segment_penalty=0.0,
        nearby_line_penalty=0.0,
    ),
    "no_final_answer_bonus": replace(SEGMENT_MERGE_POLICY, final_answer_bonus=0.0),
}
REPLAY_TOP_K = 3
REPLAY_BUDGETED_SEGMENTS = {"seg-late", "seg-final"}


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_fixture(path: Path = DEFAULT_FIXTURE) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _case_results(case: dict[str, Any]) -> list[dict[str, Any]]:
    results = copy.deepcopy(case.get("results") or [])
    for item in results:
        item.setdefault("signals", {})
        item.setdefault("kind", "message")
        item.setdefault("timestamp", "")
    return results


def _selected_source_refs(selected: list[dict[str, Any]]) -> list[str]:
    return [str(item.get("source_ref") or "") for item in selected if item.get("source_ref")]


def _pattern_counts(cases: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for case in cases:
        pattern = str(case.get("pattern") or "unknown")
        counts[pattern] = counts.get(pattern, 0) + 1
    return dict(sorted(counts.items()))


def validate_fixture(fixture: dict[str, Any]) -> list[dict[str, Any]]:
    cases = fixture.get("cases")
    if not isinstance(cases, list):
        raise ValueError("fixture must contain a cases list")
    patterns = {str(case.get("pattern") or "") for case in cases}
    missing = REQUIRED_PATTERNS - patterns
    if missing:
        raise ValueError(
            "segmented merge calibration fixture must cover at least 4 required patterns; "
            f"missing: {', '.join(sorted(missing))}"
        )
    for case in cases:
        if not case.get("case_id"):
            raise ValueError("case missing case_id")
        if not isinstance(case.get("results"), list) or not case["results"]:
            raise ValueError(f"{case.get('case_id')}: case must include non-empty results")
        expect = case.get("expect")
        if not isinstance(expect, dict):
            raise ValueError(f"{case.get('case_id')}: case must include expect object")
    return cases


def evaluate_case(case: dict[str, Any], policy: SegmentMergePolicy) -> dict[str, Any]:
    top_k = int(case.get("top_k") or 3)
    selected, merge_diagnostics = merge_topk_with_diagnostics(
        _case_results(case),
        top_k,
        policy=policy,
    )
    selected_refs = _selected_source_refs(selected)
    selected_segments = [str(item.get("segment_id") or "") for item in selected]
    expect = case.get("expect") or {}
    target_refs = [str(ref) for ref in expect.get("target_source_refs") or []]
    missing_targets = [ref for ref in target_refs if ref not in selected_refs]
    unique_segment_count = len(set(selected_segments))
    min_unique_segments = int(expect.get("min_unique_segments") or 1)
    forbidden_top1_refs = set(str(ref) for ref in expect.get("forbidden_top1_source_refs") or [])
    top1_ref = selected_refs[0] if selected_refs else ""
    group_counts: dict[str, int] = {}
    for item in selected:
        group = item.get("duplicate_group")
        if group:
            group_counts[str(group)] = group_counts.get(str(group), 0) + 1
    group_violations = []
    for group, maximum in (expect.get("max_selected_from_groups") or {}).items():
        if group_counts.get(str(group), 0) > int(maximum):
            group_violations.append(str(group))
    adjacent_pair_ok = True
    if expect.get("requires_adjacent_pair"):
        adjacent_pair_ok = all(ref in selected_refs for ref in target_refs)
    stale_false_promotion = bool(top1_ref in forbidden_top1_refs)
    passed = (
        not missing_targets
        and unique_segment_count >= min_unique_segments
        and not group_violations
        and adjacent_pair_ok
        and not stale_false_promotion
    )
    return {
        "case_id": str(case.get("case_id")),
        "pattern": str(case.get("pattern")),
        "query_family": str(case.get("query_family") or "unknown"),
        "top_k": top_k,
        "passed": passed,
        "selected_source_refs": selected_refs,
        "selected_segments": selected_segments,
        "target_source_refs": target_refs,
        "missing_target_source_refs": missing_targets,
        "unique_segment_count": unique_segment_count,
        "min_unique_segments": min_unique_segments,
        "adjacent_pair_ok": adjacent_pair_ok,
        "group_violations": group_violations,
        "stale_superseded_false_promotion": stale_false_promotion,
        "source_key_dedupe_count": merge_diagnostics["source_key_dedupe_count"],
    }


def summarize_case_results(case_results: list[dict[str, Any]]) -> dict[str, Any]:
    case_count = len(case_results)
    passed_case_count = sum(1 for case in case_results if case["passed"])
    target_hits = sum(1 for case in case_results if not case["missing_target_source_refs"])
    diversity_cases = [case for case in case_results if case["min_unique_segments"] > 1]
    diversity_pass = sum(
        1 for case in diversity_cases if case["unique_segment_count"] >= case["min_unique_segments"]
    )
    adjacent_cases = [case for case in case_results if case["pattern"] == "adjacent_turn_pairing"]
    adjacent_pass = sum(1 for case in adjacent_cases if case["adjacent_pair_ok"])
    stale_false_promotions = sum(
        1 for case in case_results if case["stale_superseded_false_promotion"]
    )
    duplicate_cases = [
        case for case in case_results if case["pattern"] == "duplicate_nearby_recap_suppression"
    ]
    duplicate_pass = sum(1 for case in duplicate_cases if not case["group_violations"])
    source_key_dedupe_count = sum(case["source_key_dedupe_count"] for case in case_results)
    return {
        "case_count": case_count,
        "passed_case_count": passed_case_count,
        "target_hit_rate": round(target_hits / case_count, 6) if case_count else 0.0,
        "source_diversity_pass_rate": round(diversity_pass / len(diversity_cases), 6)
        if diversity_cases
        else 0.0,
        "adjacent_turn_pairing_success_rate": round(adjacent_pass / len(adjacent_cases), 6)
        if adjacent_cases
        else 0.0,
        "duplicate_nearby_suppression_success_rate": round(
            duplicate_pass / len(duplicate_cases),
            6,
        )
        if duplicate_cases
        else 0.0,
        "source_key_dedupe_case_count": sum(
            1 for case in case_results if case["source_key_dedupe_count"] > 0
        ),
        "source_key_dedupe_count": source_key_dedupe_count,
        "stale_superseded_false_promotion_count": stale_false_promotions,
    }


def _rate(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 6) if denominator else 0.0


def _latency_summary(values: list[float]) -> dict[str, float]:
    if not values:
        return {"p50": 0.0, "p95": 0.0}
    ordered = sorted(values)
    midpoint = len(ordered) // 2
    if len(ordered) % 2:
        p50 = ordered[midpoint]
    else:
        p50 = (ordered[midpoint - 1] + ordered[midpoint]) / 2
    p95 = ordered[min(len(ordered) - 1, int(round((len(ordered) - 1) * 0.95)))]
    return {"p50": round(p50, 3), "p95": round(p95, 3)}


def _replay_candidate(
    *,
    ref: str,
    segment_id: str,
    segment_position: str,
    score: float,
    line: int,
    role: str = "user",
    phase: str = "",
    literal_hits: int = 1,
    duplicate_group: str = "",
    stale: bool = False,
) -> dict[str, Any]:
    item: dict[str, Any] = {
        "id": line,
        "line": line,
        "score": score,
        "source_ref": ref,
        "segment_id": segment_id,
        "segment_ordinal": {"seg-early": 0, "seg-middle": 1, "seg-late": 2, "seg-final": 3}.get(
            segment_id,
            99,
        ),
        "segment_position": segment_position,
        "role": role,
        "kind": "message",
        "signals": {"literal_hits": literal_hits},
    }
    if phase:
        item["phase"] = phase
    if duplicate_group:
        item["duplicate_group"] = duplicate_group
    if stale:
        item["stale_or_superseded"] = True
    return item


def public_safe_replay_source_evidence_cases() -> list[dict[str, Any]]:
    """Tiny replay/source-evidence cohort with stable refs but no source text.

    This intentionally models source-open validation as a boolean ref check
    beside ranking metrics. Do not add raw excerpts, local paths, or generated
    index payloads here; the cohort is meant to be public-safe and replayable.
    """

    return [
        {
            "case_id": "replay-vague-cue-early",
            "pattern": "vague_cue",
            "query_family": "vague_cue",
            "segment_position": "early",
            "target_source_refs": ["replay:early:source-route"],
            "answer_source_refs": ["replay:early:source-route"],
            "results": [
                _replay_candidate(
                    ref="replay:late:recap-route",
                    segment_id="seg-late",
                    segment_position="late",
                    score=39.0,
                    line=700,
                    role="assistant",
                    phase="final_answer",
                    literal_hits=0,
                ),
                _replay_candidate(
                    ref="replay:early:source-route",
                    segment_id="seg-early",
                    segment_position="early",
                    score=35.0,
                    line=40,
                    role="user",
                ),
            ],
        },
        {
            "case_id": "replay-middle-route",
            "pattern": "middle_segment",
            "query_family": "middle",
            "segment_position": "middle",
            "target_source_refs": ["replay:middle:decision"],
            "answer_source_refs": ["replay:middle:decision"],
            "results": [
                _replay_candidate(
                    ref="replay:middle:decision",
                    segment_id="seg-middle",
                    segment_position="middle",
                    score=42.0,
                    line=360,
                ),
                _replay_candidate(
                    ref="replay:late:nearby-summary",
                    segment_id="seg-late",
                    segment_position="late",
                    score=38.0,
                    line=740,
                    role="assistant",
                    phase="final_answer",
                    literal_hits=0,
                ),
            ],
        },
        {
            "case_id": "replay-late-route",
            "pattern": "late_segment",
            "query_family": "late",
            "segment_position": "late",
            "target_source_refs": ["replay:late:handoff"],
            "answer_source_refs": ["replay:late:handoff"],
            "results": [
                _replay_candidate(
                    ref="replay:late:handoff",
                    segment_id="seg-late",
                    segment_position="late",
                    score=44.0,
                    line=780,
                    role="assistant",
                    phase="final_answer",
                ),
                _replay_candidate(
                    ref="replay:early:background",
                    segment_id="seg-early",
                    segment_position="early",
                    score=20.0,
                    line=80,
                    literal_hits=0,
                ),
            ],
        },
        {
            "case_id": "replay-cross-boundary-pair",
            "pattern": "cross_boundary",
            "query_family": "cross_boundary",
            "segment_position": "middle",
            "target_source_refs": ["replay:boundary:left", "replay:boundary:right"],
            "answer_source_refs": ["replay:boundary:left", "replay:boundary:right"],
            "requires_pairing": True,
            "results": [
                _replay_candidate(
                    ref="replay:boundary:left",
                    segment_id="seg-middle",
                    segment_position="middle",
                    score=40.0,
                    line=498,
                ),
                _replay_candidate(
                    ref="replay:boundary:right",
                    segment_id="seg-late",
                    segment_position="late",
                    score=39.0,
                    line=502,
                    role="assistant",
                    phase="final_answer",
                ),
            ],
        },
        {
            "case_id": "replay-duplicate-recap",
            "pattern": "duplicate_recap",
            "query_family": "duplicate_recap",
            "segment_position": "late",
            "target_source_refs": ["replay:duplicate:source"],
            "answer_source_refs": ["replay:duplicate:source"],
            "max_selected_from_groups": {"dup-recap": 1},
            "results": [
                _replay_candidate(
                    ref="replay:duplicate:source",
                    segment_id="seg-late",
                    segment_position="late",
                    score=43.0,
                    line=810,
                    duplicate_group="dup-recap",
                ),
                _replay_candidate(
                    ref="replay:duplicate:source",
                    segment_id="seg-final",
                    segment_position="late",
                    score=42.0,
                    line=900,
                    role="assistant",
                    phase="final_answer",
                    duplicate_group="dup-recap",
                ),
            ],
        },
        {
            "case_id": "replay-stale-superseded",
            "pattern": "stale_superseded",
            "query_family": "stale",
            "segment_position": "late",
            "target_source_refs": ["replay:current:policy"],
            "answer_source_refs": ["replay:current:policy"],
            "forbidden_top1_source_refs": ["replay:old:policy"],
            "results": [
                _replay_candidate(
                    ref="replay:current:policy",
                    segment_id="seg-late",
                    segment_position="late",
                    score=41.0,
                    line=830,
                    role="assistant",
                    phase="final_answer",
                ),
                _replay_candidate(
                    ref="replay:old:policy",
                    segment_id="seg-early",
                    segment_position="early",
                    score=38.0,
                    line=60,
                    stale=True,
                ),
            ],
        },
        {
            "case_id": "replay-final-answer-user-cue-mismatch",
            "pattern": "final_answer_user_cue_mismatch",
            "query_family": "answer_user_mismatch",
            "segment_position": "early",
            "target_source_refs": ["replay:user:cue"],
            "answer_source_refs": ["replay:user:cue"],
            "results": [
                _replay_candidate(
                    ref="replay:answer:wrong-topic",
                    segment_id="seg-final",
                    segment_position="late",
                    score=37.0,
                    line=930,
                    role="assistant",
                    phase="final_answer",
                    literal_hits=0,
                ),
                _replay_candidate(
                    ref="replay:user:cue",
                    segment_id="seg-early",
                    segment_position="early",
                    score=34.0,
                    line=95,
                    role="user",
                ),
            ],
        },
        {
            "case_id": "replay-cjk-multilingual",
            "pattern": "cjk_multilingual",
            "query_family": "cjk_multilingual",
            "segment_position": "middle",
            "target_source_refs": ["replay:cjk:cheap-plan"],
            "answer_source_refs": ["replay:cjk:cheap-plan"],
            "results": [
                _replay_candidate(
                    ref="replay:cjk:cheap-plan",
                    segment_id="seg-middle",
                    segment_position="middle",
                    score=45.0,
                    line=420,
                    role="user",
                ),
                _replay_candidate(
                    ref="replay:late:english-recap",
                    segment_id="seg-final",
                    segment_position="late",
                    score=36.0,
                    line=960,
                    role="assistant",
                    phase="final_answer",
                    literal_hits=0,
                ),
            ],
        },
    ]


def _replay_results(case: dict[str, Any], arm: str) -> list[dict[str, Any]]:
    results = copy.deepcopy(case.get("results") or [])
    if arm == "budgeted_fanout":
        return [
            item
            for item in results
            if str(item.get("segment_id") or "") in REPLAY_BUDGETED_SEGMENTS
        ]
    return results


def _select_replay_results(case: dict[str, Any], arm: str) -> list[dict[str, Any]]:
    candidates = _replay_results(case, arm)
    if arm == "monolithic":
        return sorted(
            candidates,
            key=lambda item: (-(float(item.get("score") or 0.0)), int(item.get("line") or 10**12)),
        )[:REPLAY_TOP_K]
    selected, _ = merge_topk_with_diagnostics(candidates, REPLAY_TOP_K)
    return selected


def _evaluate_replay_case(case: dict[str, Any]) -> dict[str, Any]:
    started = time.perf_counter()
    target_refs = [str(ref) for ref in case.get("target_source_refs") or []]
    forbidden_top1 = set(str(ref) for ref in case.get("forbidden_top1_source_refs") or [])
    group_limits = {str(k): int(v) for k, v in (case.get("max_selected_from_groups") or {}).items()}
    arms: dict[str, Any] = {}
    for arm in ("monolithic", "full_fanout", "budgeted_fanout"):
        selected = _select_replay_results(case, arm)
        selected_refs = _selected_source_refs(selected)
        group_counts: dict[str, int] = {}
        for item in selected:
            group = str(item.get("duplicate_group") or "")
            if group:
                group_counts[group] = group_counts.get(group, 0) + 1
        arms[arm] = {
            "selected_source_refs": selected_refs,
            "target_hit": all(ref in selected_refs for ref in target_refs),
            "missing_target_source_refs": [ref for ref in target_refs if ref not in selected_refs],
            "top1_source_ref": selected_refs[0] if selected_refs else "",
            "duplicate_group_violations": [
                group for group, maximum in group_limits.items() if group_counts.get(group, 0) > maximum
            ],
        }
    answer_refs = {str(ref) for ref in case.get("answer_source_refs") or []}
    answer_support_after_source_reopen = bool(target_refs) and set(target_refs).issubset(answer_refs)
    latency_ms = _elapsed_case_ms(started)
    return {
        "case_id": str(case.get("case_id")),
        "pattern": str(case.get("pattern")),
        "query_family": str(case.get("query_family")),
        "segment_position": str(case.get("segment_position") or "unknown"),
        "requires_pairing": bool(case.get("requires_pairing")),
        "target_source_ref_count": len(target_refs),
        "answer_support_after_source_reopen": answer_support_after_source_reopen,
        "monolithic": arms["monolithic"],
        "full_fanout": arms["full_fanout"],
        "budgeted_fanout": arms["budgeted_fanout"],
        "stale_superseded_false_promotion": bool(arms["full_fanout"]["top1_source_ref"] in forbidden_top1),
        "duplicate_recap_overpromotion": bool(arms["full_fanout"]["duplicate_group_violations"]),
        "wrong_segment_crowding": bool(
            arms["full_fanout"]["target_hit"] and not arms["budgeted_fanout"]["target_hit"]
        ),
        "latency_ms": latency_ms,
    }


def _elapsed_case_ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 3)


def _scan_public_safe_leaks(payload: Any) -> dict[str, int]:
    dumped = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    path_tokens = (":\\", "E:/", "C:/", "/Users/", "/home/")
    return {
        "raw_private_text_leak_count": int("RAW_PRIVATE_TEXT_SHOULD_NOT_EMIT" in dumped),
        "absolute_path_leak_count": sum(1 for token in path_tokens if token in dumped),
    }


def evaluate_replay_source_evidence_cohort() -> dict[str, Any]:
    cases = public_safe_replay_source_evidence_cases()
    case_results = [_evaluate_replay_case(case) for case in cases]
    case_count = len(case_results)
    monolithic_hits = sum(1 for row in case_results if row["monolithic"]["target_hit"])
    full_hits = sum(1 for row in case_results if row["full_fanout"]["target_hit"])
    budgeted_hits = sum(1 for row in case_results if row["budgeted_fanout"]["target_hit"])
    pairing_cases = [row for row in case_results if row["requires_pairing"]]
    pairing_successes = sum(1 for row in pairing_cases if row["full_fanout"]["target_hit"])
    supported = sum(1 for row in case_results if row["answer_support_after_source_reopen"])
    early_misses = sum(
        1
        for row in case_results
        if row["segment_position"] == "early" and not row["budgeted_fanout"]["target_hit"]
    )
    middle_misses = sum(
        1
        for row in case_results
        if row["segment_position"] == "middle" and not row["budgeted_fanout"]["target_hit"]
    )
    latency = _latency_summary([float(row["latency_ms"]) for row in case_results])
    metrics = {
        "long_thread_replay_case_count": case_count,
        "monolithic_target_hit_rate": _rate(monolithic_hits, case_count),
        "full_fanout_target_hit_rate": _rate(full_hits, case_count),
        "budgeted_fanout_target_hit_rate": _rate(budgeted_hits, case_count),
        "segmented_vs_monolithic_delta": round(_rate(full_hits, case_count) - _rate(monolithic_hits, case_count), 6),
        "answer_support_after_source_reopen_rate": _rate(supported, case_count),
        "early_segment_miss_count": early_misses,
        "middle_segment_miss_count": middle_misses,
        "cross_boundary_pairing_success_rate": _rate(pairing_successes, len(pairing_cases)),
        "stale_superseded_false_promotion_count": sum(
            1 for row in case_results if row["stale_superseded_false_promotion"]
        ),
        "duplicate_recap_overpromotion_count": sum(
            1 for row in case_results if row["duplicate_recap_overpromotion"]
        ),
        "wrong_segment_crowding_count": sum(1 for row in case_results if row["wrong_segment_crowding"]),
        "query_latency_p50_ms": latency["p50"],
        "query_latency_p95_ms": latency["p95"],
    }
    leak_counts = _scan_public_safe_leaks({"metrics": metrics, "cases": case_results})
    metrics.update(leak_counts)
    return {
        "case_count": case_count,
        "validation": "source_open_support_checked_separately_from_ranking",
        "metrics": metrics,
        "cases": case_results,
        "privacy_boundary": {
            "emits_raw_source_text": False,
            "emits_local_paths": False,
            "emits_generated_index_payload": False,
            "source_refs_are_public_safe_stable_ids": True,
        },
    }


def replay_empty_metrics() -> dict[str, Any]:
    return {
        "long_thread_replay_case_count": 0,
        "monolithic_target_hit_rate": 0.0,
        "full_fanout_target_hit_rate": 0.0,
        "budgeted_fanout_target_hit_rate": 0.0,
        "segmented_vs_monolithic_delta": 0.0,
        "answer_support_after_source_reopen_rate": 0.0,
        "early_segment_miss_count": 0,
        "middle_segment_miss_count": 0,
        "cross_boundary_pairing_success_rate": 0.0,
        "stale_superseded_false_promotion_count": 0,
        "duplicate_recap_overpromotion_count": 0,
        "wrong_segment_crowding_count": 0,
        "query_latency_p50_ms": 0.0,
        "query_latency_p95_ms": 0.0,
        "raw_private_text_leak_count": 0,
        "absolute_path_leak_count": 0,
    }


def evaluate_fixture(
    fixture: dict[str, Any],
    *,
    policy: SegmentMergePolicy = SEGMENT_MERGE_POLICY,
) -> dict[str, Any]:
    cases = validate_fixture(fixture)
    case_results = [evaluate_case(case, policy) for case in cases]
    return {
        "metrics": summarize_case_results(case_results),
        "cases": case_results,
        "pattern_counts": _pattern_counts(cases),
    }


def sensitivity_analysis(
    fixture: dict[str, Any],
    default_results: list[dict[str, Any]],
) -> dict[str, Any]:
    default_by_id = {case["case_id"]: case for case in default_results}
    analysis: dict[str, Any] = {}
    for name, policy in ALTERNATE_POLICIES.items():
        evaluated = evaluate_fixture(fixture, policy=policy)
        regressed = [
            case["case_id"]
            for case in evaluated["cases"]
            if default_by_id.get(case["case_id"], {}).get("passed") and not case["passed"]
        ]
        improved = [
            case["case_id"]
            for case in evaluated["cases"]
            if not default_by_id.get(case["case_id"], {}).get("passed") and case["passed"]
        ]
        analysis[name] = {
            "policy": asdict(policy),
            "metrics": evaluated["metrics"],
            "regressed_case_count": len(regressed),
            "regressed_cases": regressed,
            "improved_case_count": len(improved),
            "improved_cases": improved,
        }
    return analysis


def cannot_claim() -> list[str]:
    return [
        "broad_long_thread_recall_quality",
        "generated_physical_soak_quality",
        "natural_user_query_quality",
        "private_history_segment_merge_quality",
        "real_user_recall_quality",
        "source_evidence_retrieval_quality",
        "sota_or_external_baseline_superiority",
        "turn_aware_segment_boundary_quality",
    ]


def privacy_boundary() -> dict[str, Any]:
    return {
        "raw_snippets_emitted": False,
        "absolute_paths_emitted": False,
        "private_text_emitted": False,
        "source_refs_are_synthetic": True,
        "replay_source_refs_are_public_safe": True,
        "output_shape": "sanitized_segmented_merge_policy_metrics",
    }


def run_segmented_merge_policy_benchmark(
    *,
    fixture_path: Path = DEFAULT_FIXTURE,
    include_replay_cohort: bool = False,
) -> dict[str, Any]:
    started = time.perf_counter()
    fixture = load_fixture(fixture_path)
    evaluated = evaluate_fixture(fixture)
    metrics = evaluated["metrics"]
    replay = evaluate_replay_source_evidence_cohort() if include_replay_cohort else None
    replay_metrics = replay["metrics"] if replay else replay_empty_metrics()
    metrics = {
        **metrics,
        "synthetic_policy_fixture_case_count": int(metrics["case_count"]),
        "generated_soak_case_count": 0,
        **replay_metrics,
        "stale_superseded_false_promotion_count": int(
            metrics["stale_superseded_false_promotion_count"]
        )
        + int(replay_metrics["stale_superseded_false_promotion_count"]),
    }
    default_policy_acceptable = (
        metrics["passed_case_count"] == metrics["case_count"]
        and metrics["case_count"] >= len(REQUIRED_PATTERNS)
    )
    status = "policy_acceptance_passed" if default_policy_acceptable else "policy_diagnostic"
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "aippocampus_segmented_merge_policy_benchmark",
        "generated_at": now_utc(),
        "status": status,
        "ok": default_policy_acceptable,
        "fixture": {
            "path": "benchmark_corpus/segmented_merge_policy/fixture.json",
            "name": fixture.get("name"),
            "schema_version": fixture.get("schema_version"),
            "pattern_counts": evaluated["pattern_counts"],
        },
        "policy": {
            "default_policy": asdict(SEGMENT_MERGE_POLICY),
            "policy_owner": "skills/aippocampus/scripts/aippocampus_runtime/recall/scoring_policy.py",
            "merge_owner": "skills/aippocampus/scripts/aippocampus_runtime/recall/segment_search.py",
        },
        "decision": {
            "default_policy_acceptable": default_policy_acceptable,
            "weight_change_made": False,
            "interpretation": (
                "Default weights pass the public-safe calibration fixture and "
                "remain diagnostic policy. Replay/source-evidence ranking and "
                "source-open support are reported separately when enabled."
            ),
        },
        "metrics": metrics,
        "cases": evaluated["cases"],
        "evidence_cohorts": {
            "synthetic_policy_fixture": {
                "case_count": int(evaluated["metrics"]["case_count"]),
                "validation": "synthetic_fixture_merge_policy_only",
            },
            "generated_physical_soak": {
                "case_count": 0,
                "validation": "not_run_by_this_runner",
            },
            **({"replay_source_evidence": replay} if replay else {}),
        },
        "sensitivity": sensitivity_analysis(fixture, evaluated["cases"]),
        "privacy_boundary": privacy_boundary(),
        "claim_boundary_ref": claim_boundary_ref(
            "docs/evidence/benchmarks/segmented-merge-policy-fixture-report.md"
        ),
        "cannot_claim": cannot_claim(),
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
    }


def print_human_summary(payload: dict[str, Any]) -> None:
    metrics = payload.get("metrics") or {}
    print("AIppocampus segmented merge policy calibration")
    print(f"- status: {payload.get('status')}")
    print(f"- cases: {metrics.get('passed_case_count', 0)}/{metrics.get('case_count', 0)} passed")
    print(f"- target hit rate: {metrics.get('target_hit_rate', 0.0):.2%}")
    if metrics.get("long_thread_replay_case_count", 0):
        print(
            "- replay/source-evidence hit rate: "
            f"monolithic {metrics.get('monolithic_target_hit_rate', 0.0):.2%} / "
            f"full {metrics.get('full_fanout_target_hit_rate', 0.0):.2%} / "
            f"budgeted {metrics.get('budgeted_fanout_target_hit_rate', 0.0):.2%}"
        )
        print(
            "- source reopen support rate: "
            f"{metrics.get('answer_support_after_source_reopen_rate', 0.0):.2%}"
        )
    print(f"- diversity pass rate: {metrics.get('source_diversity_pass_rate', 0.0):.2%}")
    print(f"- stale false promotions: {metrics.get('stale_superseded_false_promotion_count', 0)}")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument(
        "--replay-cohort",
        action="store_true",
        help="Include the public-safe replay/source-evidence cohort.",
    )
    parser.add_argument("--json", action="store_true", dest="json_output")
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    payload = run_segmented_merge_policy_benchmark(
        fixture_path=args.fixture,
        include_replay_cohort=args.replay_cohort,
    )
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    if args.json_output:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print_human_summary(payload)
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
