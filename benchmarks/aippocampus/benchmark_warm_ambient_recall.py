#!/usr/bin/env python3
"""Sanitized benchmark runner for warm ambient recall.

The runner has two modes:
- deterministic fixture mode for CI and regression checks
- optional live-model mode for small real calibration runs when an API key is
  present

Outputs contain hashes and aggregate metrics only. Raw prompts, prompt traces,
cards, and model text stay out of the benchmark payload so live runs can be
shared as evidence without leaking local memory content.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import _paths

_paths.ensure_paths()

import warm_ambient_recall as warm


@dataclass(frozen=True)
class WarmBenchmarkCase:
    case_id: str
    prompt: str
    prompt_trace: list[dict[str, Any]]
    current_thread_key: str | None = None
    topic_epoch: str | None = None
    expected_available: bool | None = True
    expected_min_cards: int = 1
    expected_topic_epoch_action: str | None = None


BUILTIN_CASES = (
    WarmBenchmarkCase(
        case_id="ambient_recall_design_continuity",
        prompt="那个脑内续接器现在怎么样了？",
        prompt_trace=[
            {
                "thread_key": "session:ambient-current",
                "role": "user",
                "phase": "recent_prompt",
                "text": "继续推进 ambient recall 的 10x5 scout 设计。",
            }
        ],
    ),
    WarmBenchmarkCase(
        case_id="source_ref_echo_guard",
        prompt="继续刚才 source-ref validation 和 echo penalty 的校准。",
        prompt_trace=[
            {
                "thread_key": "session:ambient-current",
                "role": "assistant",
                "phase": "final_answer",
                "text": "source-ref validation 已经落地，当前线程 echo 默认压制。",
                "source_refs": [{"thread_key": "session:ambient-current", "message_id": "m-current"}],
            }
        ],
        current_thread_key="session:ambient-current",
    ),
    WarmBenchmarkCase(
        case_id="cross_domain_style_bridge",
        prompt="这个跨界联想 scout 会不会比普通 query expansion 更像人类记忆？",
        prompt_trace=[
            {
                "thread_key": "session:ambient-current",
                "role": "user",
                "phase": "recent_prompt",
                "text": "用户在比较技术问题和人类记忆体感之间的桥接。",
            }
        ],
    ),
    WarmBenchmarkCase(
        case_id="style_preference_continuity",
        prompt="继续校准用户表达习惯和中文节奏，不要把它说成硬事实。",
        prompt_trace=[
            {
                "thread_key": "session:ambient-current",
                "role": "user",
                "phase": "recent_prompt",
                "text": "用户偏好中文、短段落、先结论后细节。",
            }
        ],
    ),
    WarmBenchmarkCase(
        case_id="trajectory_phase_match",
        prompt="现在这条 ambient recall 线应该进入后台 job 闭环了。",
        prompt_trace=[
            {
                "thread_key": "session:ambient-current",
                "role": "assistant",
                "phase": "final_answer",
                "text": "下一步是 foreground cache-first + detached wait-all warm job。",
            }
        ],
    ),
    WarmBenchmarkCase(
        case_id="dream_residue_handoff",
        prompt="这些用完即丢的 cache residue 能不能之后给 dream task 当素材？",
        prompt_trace=[
            {
                "thread_key": "session:ambient-current",
                "role": "user",
                "phase": "recent_prompt",
                "text": "cache residue should become dream seed only, not memory truth.",
            }
        ],
    ),
    WarmBenchmarkCase(
        case_id="bilingual_memory_bridge",
        prompt="这个 source-backed recall card 的 visibility bias 怎么调？",
        prompt_trace=[
            {
                "thread_key": "session:ambient-current",
                "role": "user",
                "phase": "recent_prompt",
                "text": "中文讨论里夹了 source-backed recall card 和 visibility bias。",
            }
        ],
    ),
    WarmBenchmarkCase(
        case_id="topic_epoch_rotation",
        prompt="话题从 prompt cache 转到 topic epoch rotation 了。",
        prompt_trace=[
            {
                "thread_key": "session:ambient-current",
                "role": "assistant",
                "phase": "final_answer",
                "text": "Topic epoch rotation should be judged by scouts, not hard-coded rules.",
            }
        ],
        expected_topic_epoch_action="reuse",
    ),
    WarmBenchmarkCase(
        case_id="privacy_credential_block",
        prompt="帮我回忆一下这个 api key token cookie 应该怎么处理。",
        prompt_trace=[
            {
                "thread_key": "session:ambient-current",
                "role": "user",
                "phase": "recent_prompt",
                "text": "credential-like prompt should force privacy guard block.",
            }
        ],
        expected_available=False,
        expected_min_cards=0,
    ),
    WarmBenchmarkCase(
        case_id="source_validation_guardrail",
        prompt="如果 scout 编了 source_ref，merge 层应该怎么降级？",
        prompt_trace=[
            {
                "thread_key": "session:ambient-current",
                "role": "assistant",
                "phase": "final_answer",
                "text": "Unsupported source refs must downgrade evidence to candidate.",
            }
        ],
    ),
    WarmBenchmarkCase(
        case_id="nudge_tone_crafting",
        prompt="Nudge writer 要安静一点，像旁边递一句提醒。",
        prompt_trace=[
            {
                "thread_key": "session:ambient-current",
                "role": "user",
                "phase": "recent_prompt",
                "text": "Nudge should stay private and quiet.",
            }
        ],
    ),
    WarmBenchmarkCase(
        case_id="semantic_expander_cold_path",
        prompt="Semantic expander 先服务冷路径和下一轮，不要抢 P0。",
        prompt_trace=[
            {
                "thread_key": "session:ambient-current",
                "role": "assistant",
                "phase": "final_answer",
                "text": "Semantic expander is P1 and feeds cold path aliases.",
            }
        ],
    ),
)


def load_cases_file(path: Path | str) -> tuple[WarmBenchmarkCase, ...]:
    target = Path(path)
    if target.suffix.casefold() == ".jsonl":
        raw_items = [
            json.loads(line)
            for line in target.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    else:
        raw_items = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(raw_items, list):
        raise ValueError("warm benchmark cases file must contain a JSON array or JSONL objects")
    cases: list[WarmBenchmarkCase] = []
    for idx, item in enumerate(raw_items, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"case #{idx} must be an object")
        prompt_trace = item.get("prompt_trace") or []
        if not isinstance(prompt_trace, list):
            raise ValueError(f"case #{idx} prompt_trace must be a list")
        cases.append(
            WarmBenchmarkCase(
                case_id=str(item.get("case_id") or f"case_{idx}"),
                prompt=str(item.get("prompt") or ""),
                prompt_trace=prompt_trace,
                current_thread_key=str(item.get("current_thread_key") or "") or None,
                topic_epoch=str(item.get("topic_epoch") or "") or None,
                expected_available=item.get("expected_available", True),
                expected_min_cards=int(item.get("expected_min_cards", 1) or 0),
                expected_topic_epoch_action=str(item.get("expected_topic_epoch_action") or "") or None,
            )
        )
    return tuple(cases)


def sha1_text(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]


def deterministic_scout_fn(scout: str, payload: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
    del kwargs
    family = scout.split(":", 1)[0]
    prompt = str(payload.get("prompt") or "")
    if family == "privacy_boundary_guard" and any(token in prompt.casefold() for token in ("token", "cookie", "api key")):
        return {
            "decision": "skip",
            "confidence": 0.95,
            "block": True,
            "reason": "credential-like prompt",
            "negative_contexts": ["credential-like prompt"],
        }
    if family == "intent_mode_classifier":
        return {
            "decision": "candidate",
            "confidence": 0.74,
            "themes": ["warm ambient recall calibration"],
            "query_aliases": ["ambient recall", "warm scout"],
            "topic_epoch_action": "reuse",
            "topic_epoch_label": "warm ambient recall calibration",
        }
    if family == "key_line_hunter":
        return {
            "decision": "candidate",
            "confidence": 0.82,
            "candidates": [
                {
                    "theme": "ambient recall key-line continuity",
                    "support_level": "candidate",
                    "key_line": "brain-like recall should feel like peripheral awareness",
                    "matched_terms": ["ambient recall", "continuity"],
                }
            ],
        }
    if family == "cross_domain_bridge":
        return {
            "decision": "scent",
            "confidence": 0.66,
            "themes": ["technical memory and human-like association"],
            "query_aliases": ["cross-domain bridge"],
        }
    if family == "evidence_gap_sentinel":
        return {
            "decision": "candidate",
            "confidence": 0.7,
            "negative_contexts": ["do not present resonance as source-backed fact"],
        }
    if family == "deep_theme_matcher":
        return {
            "decision": "candidate",
            "confidence": 0.78,
            "themes": ["natural ambient recall"],
            "candidates": [
                {
                    "theme": "natural ambient recall",
                    "support_level": "candidate",
                    "matched_terms": ["ambient recall"],
                }
            ],
        }
    return {"decision": "skip", "confidence": 0.1}


def summarize_case(case: WarmBenchmarkCase, result: dict[str, Any]) -> dict[str, Any]:
    validation_statuses: dict[str, int] = {}
    for card in result.get("cards") or []:
        status = str((card.get("source_validation") or {}).get("status") or "missing")
        validation_statuses[status] = validation_statuses.get(status, 0) + 1
    scout_error_kinds: dict[str, int] = {}
    for row in result.get("scouts") or []:
        if row.get("ok"):
            continue
        kind = str(row.get("error_kind") or warm.scout_error_kind(row.get("reason")))
        scout_error_kinds[kind] = scout_error_kinds.get(kind, 0) + 1
    cache = result.get("cache") or {}
    summary = {
        "case_id": case.case_id,
        "prompt_sha1": sha1_text(case.prompt),
        "available": bool(result.get("available")),
        "status": result.get("status"),
        "mode": result.get("mode"),
        "confidence": result.get("confidence"),
        "quorum_met": bool(result.get("quorum_met")),
        "configured_scout_count": int(result.get("scout_count") or 0),
        "max_workers": int(result.get("max_workers") or 0),
        "observed_scout_result_count": len(result.get("scouts") or []),
        "accepted_scout_count": int(result.get("accepted_scout_count") or 0),
        "failed_scout_count": int(result.get("failed_scout_count") or 0),
        "scout_error_kinds": scout_error_kinds,
        "card_count": len(result.get("cards") or []),
        "source_validation_statuses": validation_statuses,
        "topic_epoch_action": (result.get("topic_epoch_decision") or {}).get("action"),
        "current_thread_echo_count": int(result.get("current_thread_echo_count") or 0),
        "elapsed_ms": float(result.get("elapsed_ms") or 0.0),
        "cache": {
            "available": cache.get("available"),
            "hit_rate": cache.get("hit_rate") or cache.get("prompt_cache_hit_rate"),
            "hit_tokens": cache.get("hit_tokens") or cache.get("prompt_cache_tokens"),
            "miss_tokens": cache.get("miss_tokens") or cache.get("prompt_cache_miss_tokens"),
        },
    }
    expectation_failures: list[str] = []
    if case.expected_available is not None and summary["available"] != case.expected_available:
        expectation_failures.append("available")
    if int(summary["card_count"]) < int(case.expected_min_cards):
        expectation_failures.append("min_cards")
    if (
        case.expected_topic_epoch_action
        and summary["topic_epoch_action"] != case.expected_topic_epoch_action
    ):
        expectation_failures.append("topic_epoch_action")
    summary["expectation_passed"] = not expectation_failures
    summary["expectation_failures"] = expectation_failures
    return summary


def run_warm_ambient_recall_benchmark(
    *,
    cwd: Path | str | None = None,
    case_limit: int | None = None,
    live: bool = False,
    wait_all: bool = True,
    timeout: float = 2.4,
    quorum: int = warm.DEFAULT_QUORUM,
    max_workers: int | None = None,
    registry_path: Path | str | None = None,
    registry_dir: Path | str | None = None,
    cases_file: Path | str | None = None,
    api_key_env: str = "DEEPSEEK_API_KEY",
    user_id: str | None = None,
    min_available_rate: float = 0.65,
    min_observed_scout_rate: float = 1.0,
    min_case_pass_rate: float = 1.0,
    max_error_rate: float = 0.05,
    max_false_evidence_count: int = 0,
) -> dict[str, Any]:
    root_ctx = tempfile.TemporaryDirectory() if cwd is None else None
    try:
        workspace = Path(cwd or Path(root_ctx.name) / "workspace").resolve()
        workspace.mkdir(parents=True, exist_ok=True)
        source_cases = load_cases_file(cases_file) if cases_file else BUILTIN_CASES
        cases = list(source_cases[: case_limit or len(source_cases)])
        summaries: list[dict[str, Any]] = []
        live_key = os.environ.get(api_key_env) if live else None
        if live and not live_key:
            return {
                "kind": "aippocampus_warm_ambient_recall_benchmark",
                "schema_version": 1,
                "ok": False,
                "status": "skipped_missing_api_key",
                "live_model": True,
                "metrics": {"case_count": 0},
                "cases": [],
                "privacy_boundary": privacy_boundary(),
            }
        for case in cases:
            result = warm.run_warm_ambient_recall(
                case.prompt,
                cwd=workspace,
                thread_id=f"warm-benchmark-{case.case_id}",
                current_thread_key=case.current_thread_key,
                prompt_trace=case.prompt_trace,
                topic_epoch=case.topic_epoch,
                registry={} if not live and not registry_path and not registry_dir else None,
                registry_path=registry_path,
                registry_dir=registry_dir,
                cache_path=workspace / "ambient-thread-cache.json",
                api_key=live_key or "benchmark-key",
                user_id=user_id,
                timeout=timeout,
                quorum=quorum,
                max_workers=max_workers,
                wait_all=wait_all,
                no_write=True,
                scout_fn=warm.model_scout_fn if live else deterministic_scout_fn,
            )
            summaries.append(summarize_case(case, result))

        metrics = summarize_metrics(summaries)
        quality_gates = evaluate_quality_gates(
            summaries,
            min_available_rate=min_available_rate,
            min_observed_scout_rate=min_observed_scout_rate,
            min_case_pass_rate=min_case_pass_rate,
            max_error_rate=max_error_rate,
            max_false_evidence_count=max_false_evidence_count,
        )
        return {
            "kind": "aippocampus_warm_ambient_recall_benchmark",
            "schema_version": 1,
            "ok": bool(summaries) and bool(quality_gates.get("passed")),
            "status": "sufficient" if summaries and quality_gates.get("passed") else "insufficient" if summaries else "empty",
            "live_model": live,
            "metrics": metrics,
            "quality_gates": quality_gates,
            "cases": summaries,
            "privacy_boundary": privacy_boundary(),
            "cannot_claim": [
                "all_future_prompts_choose_the_right_memory",
                "model_quality_without_review",
            ],
        }
    finally:
        if root_ctx is not None:
            root_ctx.cleanup()


def summarize_metrics(cases: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(cases)
    total_observed = sum(int(case.get("observed_scout_result_count") or 0) for case in cases)
    total_configured = sum(int(case.get("configured_scout_count") or 0) for case in cases)
    available = sum(1 for case in cases if case.get("available"))
    cards = sum(int(case.get("card_count") or 0) for case in cases)
    total_failed = sum(int(case.get("failed_scout_count") or 0) for case in cases)
    case_passes = sum(1 for case in cases if case.get("expectation_passed"))
    false_evidence = sum(
        int((case.get("source_validation_statuses") or {}).get(status) or 0)
        for case in cases
        for status in ("unsupported", "missing_source_ref")
    )
    elapsed = [float(case.get("elapsed_ms") or 0.0) for case in cases]
    scout_error_kinds: dict[str, int] = {}
    for case in cases:
        for kind, count in (case.get("scout_error_kinds") or {}).items():
            scout_error_kinds[str(kind)] = scout_error_kinds.get(str(kind), 0) + int(count or 0)
    return {
        "case_count": total,
        "available_rate": round(available / total, 4) if total else 0.0,
        "total_scout_calls": total_observed,
        "configured_scout_calls": total_configured,
        "observed_scout_rate": round(total_observed / total_configured, 4) if total_configured else 0.0,
        "scout_error_rate": round(total_failed / total_observed, 4) if total_observed else 0.0,
        "case_pass_rate": round(case_passes / total, 4) if total else 0.0,
        "false_evidence_count": false_evidence,
        "card_count": cards,
        "avg_elapsed_ms": round(sum(elapsed) / total, 2) if total else 0.0,
        "max_elapsed_ms": round(max(elapsed), 2) if elapsed else 0.0,
        "scout_error_kinds": scout_error_kinds,
    }


def evaluate_quality_gates(
    cases: list[dict[str, Any]],
    *,
    min_available_rate: float = 0.65,
    min_observed_scout_rate: float = 1.0,
    min_case_pass_rate: float = 1.0,
    max_error_rate: float = 0.05,
    max_false_evidence_count: int = 0,
) -> dict[str, Any]:
    metrics = summarize_metrics(cases)
    failed: list[str] = []
    if float(metrics.get("available_rate") or 0.0) < min_available_rate:
        failed.append("available_rate")
    if float(metrics.get("observed_scout_rate") or 0.0) < min_observed_scout_rate:
        failed.append("observed_scout_rate")
    if float(metrics.get("case_pass_rate") or 0.0) < min_case_pass_rate:
        failed.append("case_pass_rate")
    if float(metrics.get("scout_error_rate") or 0.0) > max_error_rate:
        failed.append("scout_error_rate")
    if int(metrics.get("false_evidence_count") or 0) > max_false_evidence_count:
        failed.append("false_evidence_count")
    return {
        "passed": not failed,
        "failed": failed,
        "thresholds": {
            "min_available_rate": min_available_rate,
            "min_observed_scout_rate": min_observed_scout_rate,
            "min_case_pass_rate": min_case_pass_rate,
            "max_error_rate": max_error_rate,
            "max_false_evidence_count": max_false_evidence_count,
        },
        "failed_case_ids": [
            str(case.get("case_id") or "")
            for case in cases
            if not case.get("expectation_passed")
        ],
    }


def privacy_boundary() -> dict[str, bool]:
    return {
        "raw_prompt_emitted": False,
        "raw_prompt_trace_emitted": False,
        "raw_cards_emitted": False,
        "absolute_paths_emitted": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cwd", default=None)
    parser.add_argument("--case-limit", type=int, default=None)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--wait-all", action="store_true", dest="wait_all", default=True)
    parser.add_argument("--quorum-first", action="store_false", dest="wait_all")
    parser.add_argument("--timeout", type=float, default=2.4)
    parser.add_argument("--quorum", type=int, default=warm.DEFAULT_QUORUM)
    parser.add_argument("--max-workers", type=int, default=None)
    parser.add_argument("--registry")
    parser.add_argument("--registry-dir")
    parser.add_argument("--cases-file", help="Optional JSON/JSONL sanitized trace case file.")
    parser.add_argument("--api-key-env", default="DEEPSEEK_API_KEY")
    parser.add_argument("--user-id", help="Optional DeepSeek user_id; omit to use a stable sanitized hash.")
    parser.add_argument("--min-available-rate", type=float, default=0.65)
    parser.add_argument("--min-observed-scout-rate", type=float, default=1.0)
    parser.add_argument("--min-case-pass-rate", type=float, default=1.0)
    parser.add_argument("--max-error-rate", type=float, default=0.05)
    parser.add_argument("--max-false-evidence-count", type=int, default=0)
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args()
    payload = run_warm_ambient_recall_benchmark(
        cwd=args.cwd,
        case_limit=args.case_limit,
        live=args.live,
        wait_all=args.wait_all,
        timeout=args.timeout,
        quorum=args.quorum,
        max_workers=args.max_workers,
        registry_path=args.registry,
        registry_dir=args.registry_dir,
        cases_file=args.cases_file,
        api_key_env=args.api_key_env,
        user_id=args.user_id,
        min_available_rate=args.min_available_rate,
        min_observed_scout_rate=args.min_observed_scout_rate,
        min_case_pass_rate=args.min_case_pass_rate,
        max_error_rate=args.max_error_rate,
        max_false_evidence_count=args.max_false_evidence_count,
    )
    if args.json_output:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        metrics = payload.get("metrics") or {}
        print(
            "warm ambient recall benchmark: "
            f"cases={metrics.get('case_count', 0)} "
            f"available_rate={metrics.get('available_rate', 0)} "
            f"scout_results={metrics.get('total_scout_calls', 0)}"
        )
    return 0 if payload.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
