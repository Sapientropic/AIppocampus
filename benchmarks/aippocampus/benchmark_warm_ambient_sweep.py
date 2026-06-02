#!/usr/bin/env python3
"""Parameter sweep runner for warm ambient recall calibration.

This runner compares benchmark settings over the same sanitized case pack. It
does not emit raw prompts, prompt traces, cards, or per-case rows. The intended
workflow is: build a private labeled trace pack in `.tmp/`, run this sweep, then
delete the pack after reviewing aggregate metrics.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Callable

import _paths

_paths.ensure_paths()

import benchmark_warm_ambient_recall as benchmark

SWEEP_SCHEMA_VERSION = 1
DEFAULT_WAIT_MODES = ("quorum_first",)
# Match the runtime's 10x5 lane design by default. Lower worker counts are
# still useful for provider/backoff diagnosis, but making them the live sweep
# default can under-sample useful scouts and falsely make Flash look weak.
DEFAULT_MAX_WORKERS = (50,)
DEFAULT_TIMEOUTS = (30.0,)
VALID_WAIT_MODES = {"quorum_first", "wait_all"}

BenchmarkFn = Callable[..., dict[str, Any]]


def sha1_text(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]


def parse_csv_items(value: str | None) -> tuple[str, ...]:
    if not value:
        return ()
    return tuple(item.strip() for item in value.split(",") if item.strip())


def parse_int_csv(value: str | None, *, default: tuple[int, ...]) -> tuple[int, ...]:
    items = parse_csv_items(value)
    if not items:
        return default
    parsed: list[int] = []
    for item in items:
        parsed.append(int(item))
    return tuple(parsed)


def parse_float_csv(value: str | None, *, default: tuple[float, ...]) -> tuple[float, ...]:
    items = parse_csv_items(value)
    if not items:
        return default
    parsed: list[float] = []
    for item in items:
        parsed.append(float(item))
    return tuple(parsed)


def normalize_wait_modes(values: tuple[str, ...] | list[str] | None) -> tuple[str, ...]:
    modes = tuple(str(item or "").strip().casefold().replace("-", "_") for item in (values or ()))
    modes = modes or DEFAULT_WAIT_MODES
    invalid = [mode for mode in modes if mode not in VALID_WAIT_MODES]
    if invalid:
        raise ValueError(f"unsupported wait mode(s): {', '.join(invalid)}")
    return tuple(dict.fromkeys(modes))


def safe_float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def compact_metrics(metrics: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "case_count",
        "available_rate",
        "configured_scout_calls",
        "prefix_cache_warmup_scout_calls",
        "trace_fallback_card_count",
        "total_scout_calls",
        "observed_scout_rate",
        "case_pass_rate",
        "false_evidence_count",
        "prompt_cache_hit_tokens",
        "prompt_cache_miss_tokens",
        "prompt_cache_hit_rate",
        "missing_source_refs_count",
        "scout_error_rate",
        "avg_elapsed_ms",
        "max_elapsed_ms",
        "card_count",
        "scout_error_kinds",
        "scout_roi_by_family",
        "scout_roi_by_lane",
        "scout_roi_classification_counts",
    )
    return {key: metrics.get(key) for key in keys if key in metrics}


def quality_summary(metrics: dict[str, Any], quality_gates: dict[str, Any]) -> dict[str, Any]:
    return {
        "gates_passed": bool(quality_gates.get("passed")),
        "case_pass_rate": safe_float(metrics.get("case_pass_rate")),
        "available_rate": safe_float(metrics.get("available_rate")),
        "false_evidence_count": safe_int(metrics.get("false_evidence_count")),
        "missing_source_refs_count": safe_int(metrics.get("missing_source_refs_count")),
        "scout_error_rate": safe_float(metrics.get("scout_error_rate")),
    }


def ranking_key(row: dict[str, Any]) -> tuple[Any, ...]:
    quality = row.get("quality") or {}
    metrics = row.get("metrics") or {}
    return (
        bool(quality.get("gates_passed")),
        bool(row.get("ok")),
        safe_float(quality.get("case_pass_rate")),
        safe_float(quality.get("available_rate")),
        -safe_int(quality.get("false_evidence_count")),
        -safe_float(quality.get("scout_error_rate")),
        -safe_int(quality.get("missing_source_refs_count")),
        -safe_float(metrics.get("avg_elapsed_ms")),
    )


def compact_quality_gates(value: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {"passed": False, "failed": ["missing_quality_gates"]}
    return {
        "passed": bool(value.get("passed")),
        "failed": [str(item) for item in value.get("failed") or []],
        "thresholds": value.get("thresholds") or {},
        "failed_case_ids": [str(item) for item in value.get("failed_case_ids") or []],
    }


def compact_run_profile(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(row, dict):
        return None
    metrics = row.get("metrics") or {}
    quality = row.get("quality") or {}
    return {
        "run_id": row.get("run_id"),
        "wait_mode": row.get("wait_mode"),
        "max_workers": row.get("max_workers"),
        "timeout": row.get("timeout"),
        "live_model": row.get("live_model"),
        "ok": row.get("ok"),
        "status": row.get("status"),
        "case_count": metrics.get("case_count"),
        "case_pass_rate": quality.get("case_pass_rate"),
        "available_rate": quality.get("available_rate"),
        "false_evidence_count": quality.get("false_evidence_count"),
        "missing_source_refs_count": quality.get("missing_source_refs_count"),
        "scout_error_rate": quality.get("scout_error_rate"),
        "observed_scout_rate": metrics.get("observed_scout_rate"),
        "avg_elapsed_ms": metrics.get("avg_elapsed_ms"),
    }


def run_row(
    payload: dict[str, Any],
    *,
    wait_mode: str,
    max_workers: int,
    timeout: float,
) -> dict[str, Any]:
    metrics = compact_metrics(payload.get("metrics") or {})
    gates = compact_quality_gates(payload.get("quality_gates") or {})
    seed = json.dumps(
        {
            "wait_mode": wait_mode,
            "max_workers": max_workers,
            "timeout": timeout,
            "live_model": bool(payload.get("live_model")),
        },
        sort_keys=True,
    )
    return {
        "run_id": "warm_sweep_" + sha1_text(seed),
        "wait_mode": wait_mode,
        "wait_all": wait_mode == "wait_all",
        "max_workers": max_workers,
        "timeout": timeout,
        "live_model": bool(payload.get("live_model")),
        "ok": bool(payload.get("ok")),
        "status": payload.get("status"),
        "metrics": metrics,
        "quality": quality_summary(metrics, gates),
        "quality_gates": gates,
    }


def accumulate_counts(target: dict[str, int], values: dict[str, Any] | list[Any] | tuple[Any, ...]) -> None:
    if isinstance(values, dict):
        items = values.items()
    else:
        items = ((item, 1) for item in values)
    for key, value in items:
        label = str(key or "").strip()
        if not label:
            continue
        target[label] = target.get(label, 0) + safe_int(value or 1)


def sweep_analysis(runs: list[dict[str, Any]], leaderboard: list[dict[str, Any]]) -> dict[str, Any]:
    successful = [row for row in leaderboard if row.get("ok") and (row.get("quality") or {}).get("gates_passed")]
    foreground = next((row for row in successful if row.get("wait_mode") == "quorum_first"), None)
    detached = next((row for row in successful if row.get("wait_mode") == "wait_all"), None)
    status_counts: dict[str, int] = {}
    failed_gate_counts: dict[str, int] = {}
    scout_error_kinds: dict[str, int] = {}
    scout_roi_classification_counts: dict[str, int] = {}
    max_missing_source_refs = 0
    max_false_evidence = 0
    for row in runs:
        status = str(row.get("status") or "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1
        accumulate_counts(failed_gate_counts, (row.get("quality_gates") or {}).get("failed") or [])
        accumulate_counts(scout_error_kinds, (row.get("metrics") or {}).get("scout_error_kinds") or {})
        accumulate_counts(
            scout_roi_classification_counts,
            (row.get("metrics") or {}).get("scout_roi_classification_counts") or {},
        )
        max_missing_source_refs = max(
            max_missing_source_refs,
            safe_int((row.get("metrics") or {}).get("missing_source_refs_count")),
        )
        max_false_evidence = max(
            max_false_evidence,
            safe_int((row.get("metrics") or {}).get("false_evidence_count")),
        )
    notes: list[str] = []
    if foreground:
        notes.append(
            "foreground candidate: "
            f"{foreground.get('wait_mode')} workers={foreground.get('max_workers')} "
            f"timeout={foreground.get('timeout')}"
        )
    else:
        notes.append("foreground candidate missing: no successful quorum_first run")
    if detached:
        notes.append(
            "detached candidate: "
            f"{detached.get('wait_mode')} workers={detached.get('max_workers')} "
            f"timeout={detached.get('timeout')}"
        )
    else:
        notes.append("detached candidate missing: no successful wait_all run")
    if scout_error_kinds:
        notes.append("scout error buckets need tuning before reading latency as quality")
    if max_false_evidence:
        notes.append("false evidence remains the highest-priority quality blocker")
    elif max_missing_source_refs:
        notes.append("missing source refs are present; tighten only for source-backed labeled packs")
    return {
        "foreground_recommendation": compact_run_profile(foreground),
        "detached_recommendation": compact_run_profile(detached),
        "failure_distribution": {
            "status_counts": status_counts,
            "failed_gate_counts": failed_gate_counts,
            "scout_error_kinds": scout_error_kinds,
        },
        "quality_pressure": {
            "max_missing_source_refs_count": max_missing_source_refs,
            "max_false_evidence_count": max_false_evidence,
        },
        "scout_roi": {
            "classification_counts": scout_roi_classification_counts,
        },
        "recommendation_notes": notes,
    }


def aggregate_privacy_boundary(runs: list[dict[str, Any]], payloads: list[dict[str, Any]]) -> dict[str, Any]:
    raw_prompt = False
    raw_prompt_trace = False
    raw_cards = False
    absolute_paths = False
    for payload in payloads:
        boundary = payload.get("privacy_boundary") or {}
        raw_prompt = raw_prompt or bool(boundary.get("raw_prompt_emitted") or boundary.get("raw_text_emitted"))
        raw_prompt_trace = raw_prompt_trace or bool(boundary.get("raw_prompt_trace_emitted"))
        raw_cards = raw_cards or bool(boundary.get("raw_cards_emitted"))
        absolute_paths = absolute_paths or bool(boundary.get("absolute_paths_emitted"))
    return {
        "raw_prompt_emitted": raw_prompt,
        "raw_prompt_trace_emitted": raw_prompt_trace,
        "raw_cards_emitted": raw_cards,
        "raw_cases_emitted": False,
        "absolute_paths_emitted": absolute_paths,
        "case_ids_are_hashed_or_private": True,
        "run_count": len(runs),
    }


def run_warm_ambient_recall_sweep(
    *,
    cwd: Path | str | None = None,
    cases_file: Path | str | None = None,
    registry_path: Path | str | None = None,
    registry_dir: Path | str | None = None,
    live: bool = False,
    wait_modes: tuple[str, ...] | list[str] | None = DEFAULT_WAIT_MODES,
    max_workers_values: tuple[int, ...] | list[int] | None = DEFAULT_MAX_WORKERS,
    timeout_values: tuple[float, ...] | list[float] | None = DEFAULT_TIMEOUTS,
    case_offset: int = 0,
    case_limit: int | None = None,
    case_workers: int | None = benchmark.DEFAULT_CASE_WORKERS,
    prefix_cache_warmup_scouts: int = benchmark.warm.DEFAULT_PREFIX_CACHE_WARMUP_SCOUTS,
    prefix_cache_warmup_delay: float = benchmark.warm.DEFAULT_PREFIX_CACHE_WARMUP_DELAY,
    quorum: int = benchmark.warm.DEFAULT_QUORUM,
    max_tokens: int | None = None,
    api_key_env: str = "DEEPSEEK_API_KEY",
    user_id: str | None = None,
    progress_dir: Path | str | None = None,
    min_available_rate: float = 0.65,
    min_observed_scout_rate: float | None = None,
    min_case_pass_rate: float = 1.0,
    max_error_rate: float = 0.05,
    max_false_evidence_count: int = 0,
    max_missing_source_refs_count: int | None = None,
    benchmark_fn: BenchmarkFn = benchmark.run_warm_ambient_recall_benchmark,
) -> dict[str, Any]:
    modes = normalize_wait_modes(wait_modes)
    workers = tuple(int(value) for value in (max_workers_values or DEFAULT_MAX_WORKERS))
    timeouts = tuple(float(value) for value in (timeout_values or DEFAULT_TIMEOUTS))
    payloads: list[dict[str, Any]] = []
    runs: list[dict[str, Any]] = []
    progress_root = Path(progress_dir) if progress_dir else None
    for wait_mode in modes:
        for max_workers in workers:
            for timeout in timeouts:
                progress_jsonl = None
                if progress_root is not None:
                    progress_jsonl = progress_root / (
                        f"{wait_mode}-case{case_offset}-limit{case_limit or 'all'}-"
                        f"workers{max_workers}-timeout{timeout:g}.jsonl"
                    )
                payload = benchmark_fn(
                    cwd=cwd,
                    case_offset=case_offset,
                    case_limit=case_limit,
                    live=live,
                    wait_all=wait_mode == "wait_all",
                    timeout=timeout,
                    quorum=quorum,
                    max_workers=max_workers,
                    case_workers=case_workers,
                    prefix_cache_warmup_scouts=prefix_cache_warmup_scouts,
                    prefix_cache_warmup_delay=prefix_cache_warmup_delay,
                    max_tokens=max_tokens,
                    registry_path=registry_path,
                    registry_dir=registry_dir,
                    cases_file=cases_file,
                    api_key_env=api_key_env,
                    user_id=user_id,
                    progress_jsonl=progress_jsonl,
                    min_available_rate=min_available_rate,
                    min_observed_scout_rate=min_observed_scout_rate,
                    min_case_pass_rate=min_case_pass_rate,
                    max_error_rate=max_error_rate,
                    max_false_evidence_count=max_false_evidence_count,
                    max_missing_source_refs_count=max_missing_source_refs_count,
                )
                payloads.append(payload)
                runs.append(
                    run_row(
                        payload,
                        wait_mode=wait_mode,
                        max_workers=max_workers,
                        timeout=timeout,
                    )
                )

    leaderboard = sorted(runs, key=ranking_key, reverse=True)
    best = leaderboard[0] if leaderboard else None
    successful = [row for row in leaderboard if row.get("ok") and (row.get("quality") or {}).get("gates_passed")]
    analysis = sweep_analysis(runs, leaderboard)
    return {
        "kind": "aippocampus_warm_ambient_recall_sweep",
        "schema_version": SWEEP_SCHEMA_VERSION,
        "ok": bool(successful),
        "status": "sufficient" if successful else "no_successful_runs" if runs else "empty",
        "live_model": live,
        "matrix": {
            "wait_modes": list(modes),
            "max_workers": list(workers),
            "timeouts": list(timeouts),
            "run_count": len(runs),
            "case_offset": case_offset,
            "case_limit": case_limit,
            "case_workers": case_workers,
            "prefix_cache_warmup_scouts": prefix_cache_warmup_scouts,
            "prefix_cache_warmup_delay": prefix_cache_warmup_delay,
            "cases_file_sha1": sha1_text(str(cases_file)) if cases_file else None,
            "registry_sha1": sha1_text(str(registry_path or registry_dir)) if (registry_path or registry_dir) else None,
            "progress_dir_enabled": bool(progress_root),
        },
        "best": best,
        "analysis": analysis,
        "runs": runs,
        "leaderboard": leaderboard,
        "privacy_boundary": aggregate_privacy_boundary(runs, payloads),
        "cannot_claim": [
            "all_future_prompts_choose_the_right_memory",
            "model_quality_without_review",
            "private_trace_labels_are_correct_without_human_review",
            "per_lane_roi_proves_public_product_quality",
            "roi_classification_should_auto_delete_scout_lanes",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cwd", default=None)
    parser.add_argument("--cases-file")
    parser.add_argument("--registry")
    parser.add_argument("--registry-dir")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--wait-modes", default="quorum_first")
    parser.add_argument("--max-workers-list", default="50")
    parser.add_argument("--timeouts", default="30")
    parser.add_argument("--case-offset", type=int, default=0)
    parser.add_argument("--case-limit", type=int, default=None)
    parser.add_argument(
        "--case-workers",
        type=int,
        default=benchmark.DEFAULT_CASE_WORKERS,
        help="Outer case concurrency passed to the warm benchmark. Use 0 for conservative auto mode.",
    )
    parser.add_argument("--prefix-cache-warmup-scouts", type=int, default=benchmark.warm.DEFAULT_PREFIX_CACHE_WARMUP_SCOUTS)
    parser.add_argument("--prefix-cache-warmup-delay", type=float, default=benchmark.warm.DEFAULT_PREFIX_CACHE_WARMUP_DELAY)
    parser.add_argument("--quorum", type=int, default=benchmark.warm.DEFAULT_QUORUM)
    parser.add_argument("--max-tokens", type=int, default=None)
    parser.add_argument("--api-key-env", default="DEEPSEEK_API_KEY")
    parser.add_argument("--user-id")
    parser.add_argument("--progress-dir", help="Optional directory for sanitized per-run case progress JSONL files.")
    parser.add_argument("--min-available-rate", type=float, default=0.65)
    parser.add_argument("--min-observed-scout-rate", type=float, default=None)
    parser.add_argument("--min-case-pass-rate", type=float, default=1.0)
    parser.add_argument("--max-error-rate", type=float, default=0.05)
    parser.add_argument("--max-false-evidence-count", type=int, default=0)
    parser.add_argument("--max-missing-source-refs-count", type=int, default=None)
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args()
    payload = run_warm_ambient_recall_sweep(
        cwd=args.cwd,
        cases_file=args.cases_file,
        registry_path=args.registry,
        registry_dir=args.registry_dir,
        live=args.live,
        wait_modes=parse_csv_items(args.wait_modes),
        max_workers_values=parse_int_csv(args.max_workers_list, default=DEFAULT_MAX_WORKERS),
        timeout_values=parse_float_csv(args.timeouts, default=DEFAULT_TIMEOUTS),
        case_offset=args.case_offset,
        case_limit=args.case_limit,
        case_workers=args.case_workers,
        prefix_cache_warmup_scouts=args.prefix_cache_warmup_scouts,
        prefix_cache_warmup_delay=args.prefix_cache_warmup_delay,
        quorum=args.quorum,
        max_tokens=args.max_tokens,
        api_key_env=args.api_key_env,
        user_id=args.user_id,
        progress_dir=args.progress_dir,
        min_available_rate=args.min_available_rate,
        min_observed_scout_rate=args.min_observed_scout_rate,
        min_case_pass_rate=args.min_case_pass_rate,
        max_error_rate=args.max_error_rate,
        max_false_evidence_count=args.max_false_evidence_count,
        max_missing_source_refs_count=args.max_missing_source_refs_count,
    )
    if args.json_output:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        best = payload.get("best") or {}
        print(
            "warm ambient recall sweep: "
            f"runs={payload.get('matrix', {}).get('run_count', 0)} "
            f"status={payload.get('status')} "
            f"best={best.get('wait_mode')} workers={best.get('max_workers')} "
            f"timeout={best.get('timeout')}"
        )
    return 0 if payload.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
