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
        "output_shape": "sanitized_segmented_merge_policy_metrics",
    }


def run_segmented_merge_policy_benchmark(
    *,
    fixture_path: Path = DEFAULT_FIXTURE,
) -> dict[str, Any]:
    started = time.perf_counter()
    fixture = load_fixture(fixture_path)
    evaluated = evaluate_fixture(fixture)
    metrics = evaluated["metrics"]
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
                "remain diagnostic policy, not product-quality proof."
            ),
        },
        "metrics": metrics,
        "cases": evaluated["cases"],
        "sensitivity": sensitivity_analysis(fixture, evaluated["cases"]),
        "privacy_boundary": privacy_boundary(),
        "cannot_claim": cannot_claim(),
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
    }


def print_human_summary(payload: dict[str, Any]) -> None:
    metrics = payload.get("metrics") or {}
    print("AIppocampus segmented merge policy calibration")
    print(f"- status: {payload.get('status')}")
    print(f"- cases: {metrics.get('passed_case_count', 0)}/{metrics.get('case_count', 0)} passed")
    print(f"- target hit rate: {metrics.get('target_hit_rate', 0.0):.2%}")
    print(f"- diversity pass rate: {metrics.get('source_diversity_pass_rate', 0.0):.2%}")
    print(f"- stale false promotions: {metrics.get('stale_superseded_false_promotion_count', 0)}")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--json", action="store_true", dest="json_output")
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    payload = run_segmented_merge_policy_benchmark(fixture_path=args.fixture)
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
