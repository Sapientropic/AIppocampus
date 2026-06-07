#!/usr/bin/env python3
"""Optional live semantic-gate benchmark for AIppocampus Track A.

The default benchmark suite keeps semantic behavior deterministic with mocked
gate decisions. This runner is the opt-in live slice: it asks the configured
DeepSeek-compatible semantic gate to classify vague continuation and explicit
evidence prompts, then checks whether the normal prompt hook guards vague model
evidence to scent while still allowing source-backed evidence for explicit
recall requests.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import tempfile
import time
from pathlib import Path
from typing import Any, Callable

import _paths

_paths.ensure_paths()

import benchmark_memory_decision_gate as gate
from aippocampus_runtime.hooks import prompt as hook
from aippocampus_runtime.recall import semantic_recall_gate as semantic

DEFAULT_LIVE_CONVERSATIONS = 5
DEFAULT_MIN_LIVE_CASES = 4
DEFAULT_MIN_SURFACE_RECALL = 0.8
DEFAULT_SEMANTIC_TIMEOUT = 12
DEFAULT_WORKERS = ("gate", "alias", "scope")
DEFAULT_CASE_WORKERS = 0
SCHEMA_VERSION = 1
HIGH_CONFIDENCE_SEMANTIC_THRESHOLD = 0.9


SemanticGateFn = Callable[..., dict[str, Any]]


def paid_semantic_hit_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Rows where model-only semantic evidence was useful but still needs source.

    These are the #201 pressure cases: the semantic path found enough to avoid
    broad manual search, but the hook correctly kept the foreground decision at
    scent until clean source can be reopened.
    """

    hits: list[dict[str, Any]] = []
    for row in rows:
        if not (
            row.get("semantic_gate_called")
            and row.get("semantic_available")
            and row.get("semantic_decision") == "evidence"
        ):
            continue
        expected = str(row.get("expected") or "")
        if expected:
            if expected == "should_scent":
                hits.append(row)
            continue
        if row.get("actual") == "scent":
            hits.append(row)
    return hits


def paid_semantic_suppression_reasons(rows: list[dict[str, Any]]) -> dict[str, int]:
    reasons: dict[str, int] = {}
    for row in rows:
        actual = row.get("actual")
        if actual not in {"scent", "evidence"}:
            reasons["semantic_hit_no_user_visible_route"] = (
                reasons.get("semantic_hit_no_user_visible_route", 0) + 1
            )
        if actual == "scent" and not row.get("source_required_reopen_plan_ready"):
            reasons["plain_scent_without_reopen_plan"] = (
                reasons.get("plain_scent_without_reopen_plan", 0) + 1
            )
        if actual == "scent" and bool(row.get("source_reopen_manual_query_expected")):
            reasons["manual_query_expected_after_reopen_route"] = (
                reasons.get("manual_query_expected_after_reopen_route", 0) + 1
            )
    return dict(sorted(reasons.items()))


def semantic_error_kind(error: Any) -> str:
    """Bucket live backend failures without emitting model/provider details."""
    text = str(error or "").casefold()
    if "timeout" in text or "timed out" in text:
        return "timeout"
    if "json" in text or "parse" in text or "decode" in text:
        return "parse_error"
    if "401" in text or "403" in text or "auth" in text or "api key" in text:
        return "auth_error"
    if "429" in text or "rate" in text:
        return "rate_limit"
    if "connect" in text or "connection" in text or "network" in text:
        return "connection_error"
    return "semantic_error"


def summarize_live_semantic_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    called = [row for row in results if row.get("semantic_gate_called")]
    decisions: dict[str, int] = {}
    error_kinds: dict[str, int] = {}
    availability_reasons: dict[str, int] = {}
    usage_totals = {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "prompt_cache_hit_tokens": 0,
        "prompt_cache_miss_tokens": 0,
    }
    latencies = [
        float(row.get("semantic_elapsed_ms") or 0.0)
        for row in called
        if row.get("semantic_elapsed_ms") is not None
    ]
    for row in called:
        decision = str(row.get("semantic_decision") or "none")
        decisions[decision] = decisions.get(decision, 0) + 1
        if not row.get("semantic_available"):
            reason = str(row.get("semantic_availability_reason") or "unknown")
            availability_reasons[reason] = availability_reasons.get(reason, 0) + 1
        for kind in row.get("semantic_error_kinds") or []:
            error_kinds[str(kind)] = error_kinds.get(str(kind), 0) + 1
        for key in usage_totals:
            usage_totals[key] += int(row.get(f"semantic_{key}") or 0)
    available_count = sum(1 for row in called if row.get("semantic_available"))
    guarded_to_scent = sum(
        1
        for row in called
        if row.get("semantic_decision") == "evidence" and row.get("actual") == "scent"
    )
    source_required_routes = sum(
        1
        for row in called
        if row.get("semantic_decision") == "evidence"
        and row.get("actual") == "scent"
        and row.get("source_required_reopen_plan_ready")
    )
    plain_scent = guarded_to_scent - source_required_routes
    paid_hits = paid_semantic_hit_rows(called)
    high_confidence_paid_hits = sum(
        1
        for row in paid_hits
        if float(row.get("semantic_confidence") or 0.0) >= HIGH_CONFIDENCE_SEMANTIC_THRESHOLD
    )
    manual_query_after_paid_hit = sum(
        1
        for row in paid_hits
        if row.get("actual") in {"scent", "skip"}
        and (
            not row.get("source_required_reopen_plan_ready")
            or bool(row.get("source_reopen_manual_query_expected"))
        )
    )
    source_reopen_after_semantic_hit_rate = safe_rate(source_required_routes, len(paid_hits))
    evidence_allowed = sum(
        1
        for row in called
        if row.get("semantic_decision") == "evidence" and row.get("actual") == "evidence"
    )
    return {
        "semantic_available_count": available_count,
        "semantic_unavailable_count": sum(
            1 for row in called if not row.get("semantic_available")
        ),
        "semantic_availability_rate": safe_rate(available_count, len(called)),
        "semantic_error_case_count": sum(
            1 for row in called if int(row.get("semantic_error_count") or 0) > 0
        ),
        "semantic_decision_counts": decisions,
        "semantic_availability_reason_counts": availability_reasons,
        "semantic_error_kind_counts": error_kinds,
        "semantic_usage": {
            **usage_totals,
            "cache_hit_rate": safe_rate(
                usage_totals["prompt_cache_hit_tokens"],
                usage_totals["prompt_cache_hit_tokens"]
                + usage_totals["prompt_cache_miss_tokens"],
            ),
        },
        "semantic_latency_ms": latency_summary(latencies),
        "semantic_evidence_guarded_to_scent_count": guarded_to_scent,
        "semantic_evidence_to_source_required_route_count": source_required_routes,
        "semantic_evidence_guarded_to_plain_scent_count": plain_scent,
        "paid_semantic_hit_count": len(paid_hits),
        "high_confidence_paid_semantic_hit_count": high_confidence_paid_hits,
        "paid_semantic_hit_to_source_reopen_rate": source_reopen_after_semantic_hit_rate,
        "source_reopen_after_semantic_hit_rate": source_reopen_after_semantic_hit_rate,
        "semantic_hit_user_visible_lift_rate": source_reopen_after_semantic_hit_rate,
        "paid_semantic_hit_guarded_to_plain_scent_count": plain_scent,
        "manual_query_invention_after_paid_semantic_hit_count": manual_query_after_paid_hit,
        "useful_route_suppressed_count": manual_query_after_paid_hit,
        "all_scent_collapse_rate": safe_rate(plain_scent, len(paid_hits)),
        "overconservative_suppression_reason_counts": (
            paid_semantic_suppression_reasons(paid_hits)
        ),
        "bounded_evidence_after_semantic_reopen_rate_measured": False,
        "bounded_evidence_after_semantic_reopen_rate": None,
        "semantic_evidence_allowed_count": evidence_allowed,
        "continuation_language_metrics": continuation_language_metrics(called),
    }


def safe_rate(numerator: int | float, denominator: int | float) -> float:
    return round(float(numerator) / float(denominator), 4) if denominator else 0.0


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * pct)))
    return round(ordered[index], 2)


def latency_summary(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"count": 0, "avg": 0.0, "p50": 0.0, "p95": 0.0, "max": 0.0}
    return {
        "count": len(values),
        "avg": round(sum(values) / len(values), 2),
        "p50": percentile(values, 0.5),
        "p95": percentile(values, 0.95),
        "max": round(max(values), 2),
    }


def continuation_language(row: dict[str, Any]) -> str | None:
    case_type = str(row.get("case_type") or "")
    if "_zh_" in case_type:
        return "zh"
    if "_en_" in case_type:
        return "en"
    return None


def count_values(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        value = str(row.get(key) or "none")
        counts[value] = counts.get(value, 0) + 1
    return counts


def continuation_language_metrics(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    metrics: dict[str, dict[str, Any]] = {}
    for language in ("zh", "en"):
        lang_rows = [row for row in rows if continuation_language(row) == language]
        correct = sum(1 for row in lang_rows if row.get("correct"))
        surface_hits = sum(1 for row in lang_rows if row.get("actual") in {"scent", "evidence"})
        guarded_to_scent = sum(
            1
            for row in lang_rows
            if row.get("semantic_decision") == "evidence" and row.get("actual") == "scent"
        )
        source_required_routes = sum(
            1
            for row in lang_rows
            if row.get("semantic_decision") == "evidence"
            and row.get("actual") == "scent"
            and row.get("source_required_reopen_plan_ready")
        )
        metrics[language] = {
            "total_cases": len(lang_rows),
            "correct_count": correct,
            "accuracy": safe_rate(correct, len(lang_rows)),
            "surface_recall": safe_rate(surface_hits, len(lang_rows)),
            "semantic_available_count": sum(
                1 for row in lang_rows if row.get("semantic_available")
            ),
            "semantic_error_case_count": sum(
                1 for row in lang_rows if int(row.get("semantic_error_count") or 0) > 0
            ),
            "actual_counts": count_values(lang_rows, "actual"),
            "semantic_decision_counts": count_values(lang_rows, "semantic_decision"),
            "semantic_evidence_guarded_to_scent_count": guarded_to_scent,
            "semantic_evidence_to_source_required_route_count": source_required_routes,
            "semantic_evidence_guarded_to_plain_scent_count": (
                guarded_to_scent - source_required_routes
            ),
            "semantic_confidence_avg": round(
                sum(float(row.get("semantic_confidence") or 0.0) for row in lang_rows)
                / len(lang_rows),
                4,
            )
            if lang_rows
            else 0.0,
        }
    return metrics


def live_semantic_cases(fixture: gate.SyntheticFixture) -> list[gate.GateCase]:
    selected: list[gate.GateCase] = []
    for case in fixture.cases:
        if case.case_type == "sharegpt_coding_should_skip":
            selected.append(case)
        elif case.case_type in {
            "sharegpt_coding_semantic_positive_zh_should_scent",
            "sharegpt_coding_semantic_positive_en_should_scent",
        }:
            prompt = case.prompt
            if case.case_type == "sharegpt_coding_semantic_positive_zh_should_scent":
                cue = prompt.split("重点是 ", 1)[1] if "重点是 " in prompt else prompt
                prompt = f"能接着我们之前关于 {cue} 的那段对话继续吗？"
            selected.append(
                gate.GateCase(
                    case_id=case.case_id.replace("semantic-scent", "live-semantic"),
                    case_type=case.case_type.replace("semantic_positive", "live_semantic"),
                    expected=case.expected,
                    prompt=prompt,
                    search_budget=0,
                    use_semantic_gate=True,
                    semantic_gate_fixture="live",
                )
            )
        elif case.case_type == "sharegpt_coding_should_evidence":
            selected.append(
                gate.GateCase(
                    case_id=case.case_id.replace("evidence", "live-semantic-evidence"),
                    case_type="sharegpt_coding_live_semantic_evidence_should_evidence",
                    expected=case.expected,
                    prompt=case.prompt,
                    search_budget=case.search_budget,
                    use_semantic_gate=True,
                    semantic_gate_fixture="live",
                )
            )
    return selected


def make_live_semantic_gate(
    *,
    cache_path: Path | None,
    mode: str | None,
    timeout: int,
    workers: tuple[str, ...],
    use_cache: bool,
) -> SemanticGateFn:
    def run(prompt: str, **kwargs: Any) -> dict[str, Any]:
        return semantic.run_semantic_gate(
            prompt,
            cwd=kwargs["cwd"],
            registry=kwargs.get("registry"),
            registry_path=kwargs.get("registry_path"),
            associations=kwargs.get("associations"),
            working_memory=kwargs.get("working_memory"),
            semantic_triggers_path=kwargs.get("semantic_triggers_path"),
            cache_path=cache_path,
            mode=mode,
            timeout=timeout,
            workers=workers,
            use_cache=use_cache,
        )

    return run


def run_case(
    case: gate.GateCase,
    fixture: gate.SyntheticFixture,
    *,
    semantic_gate_fn: SemanticGateFn,
) -> dict[str, Any]:
    semantic_gate_called = False

    def semantic_gate_spy(*args: Any, **kwargs: Any) -> dict[str, Any]:
        nonlocal semantic_gate_called
        semantic_gate_called = True
        return semantic_gate_fn(*args, **kwargs)

    result = hook.assess_prompt(
        case.prompt,
        cwd=fixture.workspace,
        registry_path=fixture.registry_path,
        search_budget=case.search_budget,
        use_semantic_gate=case.use_semantic_gate,
        semantic_gate_fn=semantic_gate_spy,
    )
    row = gate.grade_case(case, result, semantic_gate_called=semantic_gate_called)
    semantic_result = result.get("semantic_gate") or {}
    semantic_errors = semantic_result.get("errors") or []
    semantic_usage = semantic_result.get("usage") or {}
    semantic_cache = semantic_result.get("cache") or {}
    row.update(
        {
            "semantic_decision": semantic_result.get("decision"),
            "semantic_available": bool(semantic_result.get("available")),
            "semantic_availability_reason": semantic_result.get("availability_reason"),
            "semantic_diagnostic": semantic_result.get("diagnostic"),
            "semantic_confidence": semantic_result.get("confidence"),
            "semantic_cached": bool(semantic_result.get("cached")),
            "semantic_elapsed_ms": semantic_result.get("elapsed_ms"),
            "semantic_worker_count": len(semantic_result.get("workers") or []),
            "semantic_error_count": len(semantic_errors),
            "semantic_error_kinds": sorted(
                {semantic_error_kind(error) for error in semantic_errors}
            ),
            "semantic_prompt_tokens": int(semantic_usage.get("prompt_tokens") or 0),
            "semantic_completion_tokens": int(
                semantic_usage.get("completion_tokens") or 0
            ),
            "semantic_total_tokens": int(semantic_usage.get("total_tokens") or 0),
            "semantic_prompt_cache_hit_tokens": int(
                semantic_usage.get("prompt_cache_hit_tokens") or 0
            ),
            "semantic_prompt_cache_miss_tokens": int(
                semantic_usage.get("prompt_cache_miss_tokens") or 0
            ),
            "semantic_cache_hit_rate": semantic_cache.get("hit_rate"),
        }
    )
    return row


def unavailable_payload(*, reason: str, started: float, config: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "aippocampus_live_semantic_gate_benchmark",
        "generated_at": gate.now_utc(),
        "status": "skipped_missing_semantic_backend",
        "ok": True,
        "quality_gate_ok": False,
        "config": config,
        "metrics": {
            "total_cases": 0,
            "correct_count": 0,
            "accuracy": 0.0,
            "semantic_model_call_count": 0,
            "semantic_model_call_rate": 0.0,
            "semantic_available_count": 0,
            "semantic_unavailable_count": 0,
            "semantic_availability_rate": 0.0,
            "semantic_error_case_count": 0,
            "semantic_decision_counts": {},
            "semantic_availability_reason_counts": {},
            "semantic_error_kind_counts": {},
            "semantic_usage": {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "prompt_cache_hit_tokens": 0,
                "prompt_cache_miss_tokens": 0,
                "cache_hit_rate": 0.0,
            },
            "semantic_latency_ms": latency_summary([]),
            "semantic_evidence_guarded_to_scent_count": 0,
            "semantic_evidence_to_source_required_route_count": 0,
            "semantic_evidence_guarded_to_plain_scent_count": 0,
            "paid_semantic_hit_count": 0,
            "high_confidence_paid_semantic_hit_count": 0,
            "paid_semantic_hit_to_source_reopen_rate": 0.0,
            "source_reopen_after_semantic_hit_rate": 0.0,
            "semantic_hit_user_visible_lift_rate": 0.0,
            "paid_semantic_hit_guarded_to_plain_scent_count": 0,
            "manual_query_invention_after_paid_semantic_hit_count": 0,
            "useful_route_suppressed_count": 0,
            "all_scent_collapse_rate": 0.0,
            "overconservative_suppression_reason_counts": {},
            "bounded_evidence_after_semantic_reopen_rate_measured": False,
            "bounded_evidence_after_semantic_reopen_rate": None,
            "semantic_evidence_allowed_count": 0,
            "continuation_language_metrics": continuation_language_metrics([]),
        },
        "cases": [],
        "issue_readouts": issue_readouts_for_metrics(
            {
                "semantic_model_call_count": 0,
                "semantic_evidence_guarded_to_scent_count": 0,
                "semantic_evidence_to_source_required_route_count": 0,
                "semantic_evidence_guarded_to_plain_scent_count": 0,
                "evidence_false_positive_count": 0,
            },
            quality_gate_ok=False,
        ),
        "skip_reason": reason,
        "privacy_boundary": privacy_boundary(case_ids_are_hashed=True),
        "cannot_claim": ["live_semantic_model_quality"],
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
    }


def privacy_boundary(*, case_ids_are_hashed: bool) -> dict[str, Any]:
    return {
        "raw_prompt_emitted": False,
        "semantic_aliases_emitted": False,
        "semantic_reasons_emitted": False,
        "snippets_emitted": False,
        "titles_emitted": False,
        "source_reference_details_emitted": False,
        "absolute_paths_emitted": False,
        "case_ids_are_hashed": case_ids_are_hashed,
        "output_shape": "sanitized_live_semantic_gate_aggregates",
    }


def status_for_metrics(metrics: dict[str, Any], *, min_cases: int, min_surface_recall: float) -> str:
    if int(metrics.get("total_cases") or 0) < min_cases:
        return "diagnostic_only"
    if int(metrics.get("semantic_model_call_count") or 0) > 0 and int(
        metrics.get("semantic_available_count") or 0
    ) == 0:
        return "insufficient_live_semantic_availability"
    if float(metrics.get("scent_or_evidence_recall") or 0.0) < min_surface_recall:
        return "insufficient_live_semantic_recall"
    if int(metrics.get("evidence_false_positive_count") or 0) > 0:
        return "insufficient_live_semantic_precision"
    return "sufficient"


def issue_readouts_for_metrics(metrics: dict[str, Any], *, quality_gate_ok: bool) -> dict[str, Any]:
    guarded_to_scent = int(metrics.get("semantic_evidence_guarded_to_scent_count") or 0)
    source_required_routes = int(
        metrics.get("semantic_evidence_to_source_required_route_count") or 0
    )
    plain_scent = int(metrics.get("semantic_evidence_guarded_to_plain_scent_count") or 0)
    paid_hits = int(metrics.get("paid_semantic_hit_count") or guarded_to_scent)
    manual_query_after_paid_hit = int(
        metrics.get("manual_query_invention_after_paid_semantic_hit_count") or 0
    )
    lift_rate = float(metrics.get("semantic_hit_user_visible_lift_rate") or 0.0)
    all_scent_collapse_rate = float(metrics.get("all_scent_collapse_rate") or 0.0)
    false_positives = int(metrics.get("evidence_false_positive_count") or 0)
    measured = bool(
        quality_gate_ok
        and int(metrics.get("semantic_model_call_count") or 0) > 0
        and guarded_to_scent > 0
    )
    live_quality = "not_measured"
    if measured:
        live_quality = (
            "source_required_reopen_route"
            if source_required_routes == guarded_to_scent and plain_scent == 0
            else "plain_scent_remains"
        )
    return {
        "github_786": {
            "live_semantic_reopen_quality_measured": measured,
            "live_semantic_reopen_quality": live_quality,
            "semantic_evidence_guarded_to_scent_count": guarded_to_scent,
            "semantic_evidence_to_source_required_route_count": source_required_routes,
            "semantic_evidence_guarded_to_plain_scent_count": plain_scent,
            "live_semantic_reopen_closeout_eligible": bool(
                measured
                and live_quality == "source_required_reopen_route"
                and false_positives == 0
            ),
        },
        "github_201": {
            "live_paid_semantic_route_actionability_measured": measured,
            "live_semantic_route_actionability": live_quality,
            "paid_semantic_hit_count": paid_hits,
            "high_confidence_paid_semantic_hit_count": int(
                metrics.get("high_confidence_paid_semantic_hit_count") or 0
            ),
            "paid_semantic_hit_to_source_reopen_rate": float(
                metrics.get("paid_semantic_hit_to_source_reopen_rate") or 0.0
            ),
            "source_reopen_after_semantic_hit_rate": float(
                metrics.get("source_reopen_after_semantic_hit_rate") or 0.0
            ),
            "semantic_hit_user_visible_lift_rate": lift_rate,
            "paid_semantic_hit_guarded_to_plain_scent_count": int(
                metrics.get("paid_semantic_hit_guarded_to_plain_scent_count") or plain_scent
            ),
            "manual_query_invention_after_paid_semantic_hit_count": (
                manual_query_after_paid_hit
            ),
            "useful_route_suppressed_count": int(
                metrics.get("useful_route_suppressed_count") or manual_query_after_paid_hit
            ),
            "all_scent_collapse_rate": all_scent_collapse_rate,
            "overconservative_suppression_reason_counts": dict(
                metrics.get("overconservative_suppression_reason_counts") or {}
            ),
            "bounded_evidence_after_semantic_reopen_rate_measured": bool(
                metrics.get("bounded_evidence_after_semantic_reopen_rate_measured")
            ),
            "bounded_evidence_after_semantic_reopen_rate": metrics.get(
                "bounded_evidence_after_semantic_reopen_rate"
            ),
            "source_boundary_preserved": false_positives == 0,
            "live_semantic_route_actionability_closeout_eligible": bool(
                measured
                and live_quality == "source_required_reopen_route"
                and manual_query_after_paid_hit == 0
                and false_positives == 0
            ),
        }
    }


def resolve_case_workers(*, sharegpt_conversations: int, case_workers: int) -> int:
    if int(case_workers) > 0:
        return int(case_workers)
    return max(1, (max(1, int(sharegpt_conversations)) + 1) // 2)


def run_cases(
    cases: list[gate.GateCase],
    fixture: gate.SyntheticFixture,
    *,
    semantic_gate_fn: SemanticGateFn,
    case_workers: int,
) -> list[dict[str, Any]]:
    workers = max(1, int(case_workers))
    if workers == 1:
        return [run_case(case, fixture, semantic_gate_fn=semantic_gate_fn) for case in cases]
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        return list(
            executor.map(
                lambda case: run_case(case, fixture, semantic_gate_fn=semantic_gate_fn),
                cases,
            )
        )


def run_live_semantic_eval(
    *,
    sharegpt_corpus_dir: str | Path | None = None,
    sharegpt_conversations: int = DEFAULT_LIVE_CONVERSATIONS,
    case_limit: int | None = None,
    min_cases: int = DEFAULT_MIN_LIVE_CASES,
    min_surface_recall: float = DEFAULT_MIN_SURFACE_RECALL,
    semantic_mode: str | None = "auto",
    semantic_timeout: int = DEFAULT_SEMANTIC_TIMEOUT,
    semantic_workers: tuple[str, ...] = DEFAULT_WORKERS,
    semantic_cache_path: str | Path | None = None,
    semantic_gate_fn: SemanticGateFn | None = None,
    case_workers: int = DEFAULT_CASE_WORKERS,
) -> dict[str, Any]:
    started = time.perf_counter()
    resolved_case_workers = resolve_case_workers(
        sharegpt_conversations=sharegpt_conversations,
        case_workers=case_workers,
    )
    semantic_result_cache_enabled = semantic_gate_fn is None and resolved_case_workers == 1
    config = {
        "case_set": "sharegpt-coding-live-semantic",
        "sharegpt_conversations": int(sharegpt_conversations),
        "case_limit": case_limit,
        "min_cases": int(min_cases),
        "min_surface_recall": float(min_surface_recall),
        "semantic_mode": semantic_mode or "auto",
        "semantic_timeout": int(semantic_timeout),
        "semantic_workers": list(semantic_workers),
        "case_workers": resolved_case_workers,
        "semantic_result_cache_enabled": semantic_result_cache_enabled,
        "semantic_result_cache_disabled_reason": None
        if semantic_result_cache_enabled
        else "parallel_or_injected_runner",
        "live_llm": semantic_gate_fn is None,
    }
    if semantic_gate_fn is None and not semantic.semantic_gate_enabled(semantic_mode):
        return unavailable_payload(
            reason="semantic gate disabled or missing api key",
            started=started,
            config=config,
        )
    cache_path = Path(semantic_cache_path).resolve() if semantic_cache_path else None
    runner = semantic_gate_fn or make_live_semantic_gate(
        cache_path=cache_path,
        mode=semantic_mode,
        timeout=semantic_timeout,
        workers=semantic_workers,
        use_cache=semantic_result_cache_enabled,
    )
    with tempfile.TemporaryDirectory(prefix="aippocampus-live-semantic-benchmark-") as tmp:
        fixture = gate.build_sharegpt_coding_fixture(
            Path(tmp),
            corpus_dir=Path(sharegpt_corpus_dir or gate.DEFAULT_SHAREGPT_CORPUS_DIR),
            max_conversations=sharegpt_conversations,
        )
        cases = gate.select_cases(live_semantic_cases(fixture), case_limit)
        results = run_cases(
            cases,
            fixture,
            semantic_gate_fn=runner,
            case_workers=resolved_case_workers,
        )
    metrics = gate.summarize_results(results)
    metrics.update(summarize_live_semantic_results(results))
    status = status_for_metrics(metrics, min_cases=min_cases, min_surface_recall=min_surface_recall)
    quality_gate_ok = status == "sufficient"
    cannot_claim = [
        "external_baseline_comparison",
        "all_future_semantic_prompts_correct",
    ]
    if not quality_gate_ok:
        cannot_claim.append("live_semantic_model_quality")
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "aippocampus_live_semantic_gate_benchmark",
        "generated_at": gate.now_utc(),
        "status": status,
        "ok": True,
        "quality_gate_ok": quality_gate_ok,
        "config": config,
        "metrics": metrics,
        "cases": results,
        "issue_readouts": issue_readouts_for_metrics(
            metrics, quality_gate_ok=quality_gate_ok
        ),
        "privacy_boundary": privacy_boundary(case_ids_are_hashed=True),
        "cannot_claim": cannot_claim,
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
    }


def print_human_summary(payload: dict[str, Any]) -> None:
    print("AIppocampus live semantic gate benchmark")
    print(f"- status: {payload['status']}")
    print(f"- quality gate ok: {payload['quality_gate_ok']}")
    metrics = payload["metrics"]
    print(
        "- cases: {cases} accuracy: {accuracy} semantic calls: {calls}".format(
            cases=metrics.get("total_cases"),
            accuracy=metrics.get("accuracy"),
            calls=metrics.get("semantic_model_call_count"),
        )
    )
    if payload.get("skip_reason"):
        print(f"- skip reason: {payload['skip_reason']}")


def parse_workers(raw: str) -> tuple[str, ...]:
    workers: list[str] = []
    invalid: list[str] = []
    for item in (raw or "").split(","):
        worker = item.strip().casefold()
        if not worker:
            continue
        if worker in {"all", "default"}:
            workers.extend(DEFAULT_WORKERS)
        elif worker in DEFAULT_WORKERS:
            workers.append(worker)
        else:
            invalid.append(worker)
    if invalid:
        raise argparse.ArgumentTypeError(
            "invalid semantic worker(s): "
            + ", ".join(invalid)
            + "; use default, all, or one of "
            + ", ".join(DEFAULT_WORKERS)
        )
    out: list[str] = []
    for worker in workers or list(DEFAULT_WORKERS):
        if worker not in out:
            out.append(worker)
    return tuple(out)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sharegpt-corpus-dir", type=Path, default=None)
    parser.add_argument("--sharegpt-conversations", type=int, default=DEFAULT_LIVE_CONVERSATIONS)
    parser.add_argument("--cases", type=int, default=None)
    parser.add_argument("--min-cases", type=int, default=DEFAULT_MIN_LIVE_CASES)
    parser.add_argument("--min-surface-recall", type=float, default=DEFAULT_MIN_SURFACE_RECALL)
    parser.add_argument("--semantic-mode", choices=["auto", "on", "off"], default="auto")
    parser.add_argument("--semantic-timeout", type=int, default=DEFAULT_SEMANTIC_TIMEOUT)
    parser.add_argument("--semantic-workers", type=parse_workers, default=DEFAULT_WORKERS)
    parser.add_argument(
        "--case-workers",
        type=int,
        default=DEFAULT_CASE_WORKERS,
        help="Case-level parallelism. 0 means auto: ceil(sharegpt-conversations / 2).",
    )
    parser.add_argument("--semantic-cache", type=Path, default=None)
    parser.add_argument("--json", action="store_true", dest="json_output")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    payload = run_live_semantic_eval(
        sharegpt_corpus_dir=args.sharegpt_corpus_dir,
        sharegpt_conversations=args.sharegpt_conversations,
        case_limit=args.cases,
        min_cases=args.min_cases,
        min_surface_recall=args.min_surface_recall,
        semantic_mode=args.semantic_mode,
        semantic_timeout=args.semantic_timeout,
        semantic_workers=args.semantic_workers,
        semantic_cache_path=args.semantic_cache,
        case_workers=args.case_workers,
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
