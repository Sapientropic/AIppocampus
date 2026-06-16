#!/usr/bin/env python3
"""LongMemEval-V2 official answer/latency pilot decision report.

This runner does not execute the official reader or produce a V2 score. It
records the integration decision from #1155: keep the existing V2 context
mapping pilot, and move toward a tiny official-harness answer/latency pilot
through an explicit Memory adapter contract before any full V2 run or
leaderboard/LAFS claim.
"""

from __future__ import annotations

import argparse
import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import _paths

_paths.ensure_paths()

from benchmark_longmemeval_v2_context import (  # noqa: E402
    LONGMEMEVAL_V2_DATASET_URL,
    LONGMEMEVAL_V2_LICENSE,
    LONGMEMEVAL_V2_PAPER_URL,
    LONGMEMEVAL_V2_PROJECT_URL,
    LONGMEMEVAL_V2_REPO_URL,
    now_utc,
    sha1_short,
)
from benchmarks.aippocampus.adapters import (  # noqa: E402
    longmemeval_v2_aippocampus_adapter as adapter,
)
from benchmarks.aippocampus.shared import provider_execution_budget  # noqa: E402
from benchmarks.aippocampus.shared.claim_boundary_refs import claim_boundary_ref  # noqa: E402

SCHEMA_VERSION = 1
DEFAULT_PILOT_QUESTIONS = 10
DEFAULT_MAX_PILOT_QUESTIONS = 20
DEFAULT_READER_MODEL = "Qwen/Qwen3.5-9B"
DEFAULT_READER_BASE_URL_ENV = "READER_BASE_URL"
DEFAULT_READER_API_KEY_ENV = "OPENAI_API_KEY"
DEFAULT_EVALUATOR_MODEL = "gpt-5.2"
DEFAULT_EVALUATOR_REASONING_EFFORT = "medium"
DEFAULT_MEMORY_CONTEXT_MAX_TOKENS = 200_000
DEFAULT_QUERY_LATENCY_BUDGET_SECONDS = 120.0
DEFAULT_TOTAL_COST_BUDGET_USD = 10.0
ADAPTER_MODULE = "benchmarks/aippocampus/adapters/longmemeval_v2_aippocampus_adapter.py"
ADAPTER_MEMORY_TYPE = "aippocampus_context_provider"

CANNOT_CLAIM = sorted(
    {
        "longmemeval_v2_answer_accuracy",
        "longmemeval_v2_lafs_gain",
        "longmemeval_v2_leaderboard_score",
        "longmemeval_v2_source_evidence_r_at_k_or_mrr",
        "official_v2_score_without_official_runner_outputs",
        "sota_or_external_baseline_superiority",
        "model_independent_memory_superiority",
        "private_real_history_quality",
    }
)


@dataclass(frozen=True)
class PilotConfig:
    pilot_questions: int
    max_pilot_questions: int
    reader_model: str
    reader_base_url_env: str
    reader_api_key_env: str
    evaluator_model: str
    evaluator_reasoning_effort: str
    memory_context_max_tokens: int
    query_latency_budget_seconds: float
    total_cost_budget_usd: float


def official_sources() -> dict[str, Any]:
    return {
        "paper": LONGMEMEVAL_V2_PAPER_URL,
        "repository": LONGMEMEVAL_V2_REPO_URL,
        "project_page": LONGMEMEVAL_V2_PROJECT_URL,
        "dataset": LONGMEMEVAL_V2_DATASET_URL,
        "license": LONGMEMEVAL_V2_LICENSE,
    }


def official_harness_contract(config: PilotConfig) -> dict[str, Any]:
    return {
        "upstream_repository": LONGMEMEVAL_V2_REPO_URL,
        "official_memory_api": {
            "base_class": "memory_modules.memory.Memory",
            "config_shape": {
                "memory_type": "string",
                "memory_params": "object",
            },
            "required_methods": {
                "insert": "insert(self, trajectory) receives each full trajectory object in haystack order",
                "query": "query(self, query, query_image=None) returns list[{type: text|image, value: str}]",
            },
            "optional_methods": [
                "post_query_hook(query, query_image, memory_context)",
                "_save_backend(output_dir)",
                "_load_backend(input_dir)",
            ],
        },
        "required_inputs": {
            "questions_path": "official prepared questions JSON/JSONL",
            "haystack_path": "official question-id to trajectory-id list mapping",
            "trajectories_path": "official prepared trajectories JSON/JSONL",
            "memory_config_path": "JSON config using memory_type aippocampus_context_provider",
            "output_dir": "ignored local official-run output directory",
        },
        "reader": {
            "model": config.reader_model,
            "base_url_env": config.reader_base_url_env,
            "api_key_env": config.reader_api_key_env,
            "memory_context_max_tokens": config.memory_context_max_tokens,
            "fixed_for_pilot": True,
        },
        "evaluator": {
            "model": config.evaluator_model,
            "reasoning_effort": config.evaluator_reasoning_effort,
            "fixed_for_pilot": True,
        },
        "official_outputs_expected": [
            "per_question.jsonl",
            "aggregated_metrics.json",
        ],
    }


def adapter_contract() -> dict[str, Any]:
    return {
        "module": ADAPTER_MODULE,
        "memory_type": ADAPTER_MEMORY_TYPE,
        "context_types": ["text"],
        "registration_boundary": (
            "The official harness imports registered backends from its "
            "memory_modules package. For a real pilot, copy/import the adapter "
            "inside an ignored official checkout or add a tiny local import shim; "
            "do not vendor the official repository into AIppocampus."
        ),
        "config_template": {
            "memory_type": ADAPTER_MEMORY_TYPE,
            "memory_params": {
                "max_records": 5000,
                "max_context_items": 8,
                "max_context_chars": 1200,
            },
        },
        "query_metadata_policy": {
            "raw_text_emitted_in_metadata": False,
            "raw_context_text_emitted_to_official_per_question": True,
            "ai_repo_reports_must_stay_sanitized": True,
        },
    }


def metric_separation() -> dict[str, Any]:
    return {
        "memory_context_quality": {
            "owner": "official harness prompt rows and memory_context telemetry",
            "fields": [
                "memory_context_original_token_count",
                "memory_context_token_count",
                "memory_context_was_truncated",
                "memory_post_query_metadata",
            ],
            "ai_repo_claim_status": "diagnostic_only_until_official_outputs_reviewed",
        },
        "answer_accuracy": {
            "owner": "official reader/evaluator",
            "fields": [
                "overall_full_set",
                "non_abstention_by_category",
                "abstention_by_category",
                "combined_abstention_by_category",
            ],
            "ai_repo_claim_status": "not_claimed_by_this_decision_report",
        },
        "reader_evaluator_dependency": {
            "owner": "pilot config",
            "fields": [
                "reader_model",
                "reader_base_url_env",
                "evaluator_model",
                "evaluator_reasoning_effort",
            ],
            "ai_repo_claim_status": "must_be_fixed_before_any_pilot_score",
        },
        "query_latency": {
            "owner": "official harness memory_query aggregate",
            "fields": [
                "avg_seconds",
                "p50_seconds",
                "p95_seconds",
                "max_seconds",
                "total_seconds",
            ],
            "ai_repo_claim_status": "budgeted_for_tiny_pilot_only",
        },
    }


def privacy_and_artifact_policy() -> dict[str, Any]:
    return {
        "raw_official_dataset_files_committed": False,
        "raw_official_outputs_committed": False,
        "official_checkout_policy": "ignored local checkout only",
        "output_policy": "ignored local run directory; publish only sanitized aggregate decision/report notes",
        "do_not_emit_in_ai_repo_reports": [
            "raw question text",
            "gold answers",
            "trajectory goals",
            "accessibility trees",
            "actions",
            "thoughts",
            "URLs",
            "screenshots or screenshot paths",
            "local absolute paths",
            "reader/evaluator raw responses",
            "API keys or key-file paths",
        ],
    }


def pilot_plan(config: PilotConfig) -> dict[str, Any]:
    return {
        "decision": "move_to_tiny_official_answer_latency_pilot",
        "why": [
            "V2 lacks source-evidence refs for AIppocampus-owned R@K/MRR scoring.",
            "The official harness already owns Insert/Query context gathering, fixed-reader answering, answer scoring, and memory-query latency.",
            "A 5-20 question pilot can validate adapter/schema/cost/latency behavior before any full small/medium run.",
        ],
        "pilot_size": {
            "default_questions": config.pilot_questions,
            "hard_max_without_new_issue": config.max_pilot_questions,
            "domains": ["web", "enterprise"],
        },
        "budget": {
            "avg_query_latency_budget_seconds": config.query_latency_budget_seconds,
            "total_cost_budget_usd": config.total_cost_budget_usd,
            "full_run_requires_new_approval": True,
        },
        "run_order": [
            "prepare ignored official LongMemEval-V2 checkout and data root",
            "register/copy the AIppocampus context provider adapter in that checkout",
            "run one tiny domain slice with fixed reader/evaluator config",
            "review sanitized aggregate metrics and per-question privacy before citing anything",
            "only then decide whether a larger small-tier run is worth the cost",
        ],
    }


def provider_execution_budget_boundary(config: PilotConfig) -> dict[str, Any]:
    return {
        "schema_version": provider_execution_budget.SCHEMA_VERSION,
        "benchmark_id": "longmemeval_v2_official_pilot_decision",
        "live_mode": False,
        "ok_to_start": True,
        "no_provider_budget_required_reason": "decision_report_only_no_official_reader_execution",
        "planned_live_pilot_requires_budget_before_run": True,
        "planned_budget": {
            "pilot_questions": config.pilot_questions,
            "max_pilot_questions": config.max_pilot_questions,
            "reader_model": config.reader_model,
            "evaluator_model": config.evaluator_model,
            "query_latency_budget_seconds": config.query_latency_budget_seconds,
            "total_cost_budget_usd": config.total_cost_budget_usd,
        },
    }


def build_fixture_official_harness_pilot(config: PilotConfig) -> dict[str, Any]:
    trajectory = {
        "id": "fixture-continuity-1",
        "goal": "Generic fixture text with no renewal keyword.",
        "aippocampus_continuity": {
            "route_terms": ["renewal_exception", "billing_policy"],
            "handles": ["aippo:fixture-route"],
        },
    }
    arms: list[dict[str, Any]] = []
    for arm_name, memory_config in (
        (
            "lexical_default_context",
            {"max_context_items": 4, "max_context_chars": 320},
        ),
        (
            "aippocampus_context",
            {
                "max_context_items": 4,
                "max_context_chars": 320,
                "arm_mode": "aippocampus_context",
            },
        ),
    ):
        memory = adapter.AippocampusContextProviderMemory(memory_config)
        memory.insert(trajectory)
        rows = memory.query("renewal_exception billing_policy")
        metadata = memory.post_query_hook(
            query="renewal_exception billing_policy",
            query_image=None,
            memory_context=rows,
        )
        arms.append(
            {
                "arm": arm_name,
                "memory_type": adapter.AippocampusContextProviderMemory.memory_type,
                "memory_api_insert_count": 1,
                "memory_api_query_count": 1,
                "context_item_count": len(rows),
                "returned_continuity_guidance_items": int(
                    metadata.get("returned_continuity_guidance_items") or 0
                ),
                "raw_text_emitted_in_metadata": bool(
                    metadata.get("raw_text_emitted_in_metadata")
                ),
            }
        )
    return {
        "status": "fixture_pilot_completed",
        "fixture_not_official_harness": True,
        "official_score_claimable": False,
        "pilot_questions": min(config.pilot_questions, config.max_pilot_questions),
        "arms": arms,
        "metrics_origin": "local_fixture_memory_api_only",
        "privacy_boundary": {
            "raw_official_questions_emitted": False,
            "raw_trajectories_emitted": False,
            "reader_or_evaluator_responses_emitted": False,
            "absolute_paths_emitted": False,
        },
        "cannot_claim": [
            "official_v2_score_without_official_runner_outputs",
            "longmemeval_v2_answer_accuracy",
            "longmemeval_v2_lafs_gain",
            "longmemeval_v2_leaderboard_score",
        ],
    }


def local_path_matches(text: str) -> list[str]:
    patterns = [
        r"[A-Za-z]:\\[^\s\"']+",
        r"/(?:Users|home|tmp|var|mnt)/[^\s\"']+",
    ]
    matches: list[str] = []
    for pattern in patterns:
        matches.extend(re.findall(pattern, text))
    return matches


def credential_like_matches(text: str) -> list[str]:
    patterns = [
        r"sk-[A-Za-z0-9_-]{20,}",
        r"(?:api|token|secret)[-_]?[A-Za-z0-9]{24,}",
    ]
    matches: list[str] = []
    for pattern in patterns:
        matches.extend(re.findall(pattern, text, flags=re.IGNORECASE))
    return matches


def validate_sanitized_report(payload: dict[str, Any]) -> dict[str, Any]:
    dumped = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    errors: list[dict[str, Any]] = []
    paths = local_path_matches(dumped)
    if paths:
        errors.append(
            {
                "kind": "absolute_path_leak",
                "count": len(paths),
                "examples_sha1": [sha1_short(item) for item in paths[:3]],
            }
        )
    credentials = credential_like_matches(dumped)
    if credentials:
        errors.append(
            {
                "kind": "credential_like_string",
                "count": len(credentials),
                "examples_sha1": [sha1_short(item) for item in credentials[:3]],
            }
        )
    return {
        "ok": not errors,
        "error_count": len(errors),
        "errors": errors,
        "checks": [
            "absolute_path_leak",
            "credential_like_string",
            "raw_official_data_not_in_decision_payload_by_construction",
        ],
    }


def build_report(config: PilotConfig, *, include_fixture_pilot: bool = False) -> dict[str, Any]:
    started = time.perf_counter()
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": "aippocampus_longmemeval_v2_official_pilot_decision",
        "generated_at": now_utc(),
        "status": "official_pilot_plan_ready",
        "ok": True,
        "official_score_claimable": False,
        "decision": pilot_plan(config),
        "official_sources": official_sources(),
        "official_harness_contract": official_harness_contract(config),
        "adapter_contract": adapter_contract(),
        "metric_separation": metric_separation(),
        "provider_execution_budget": provider_execution_budget_boundary(config),
        "privacy_and_artifact_policy": privacy_and_artifact_policy(),
        "claim_boundary_ref": claim_boundary_ref(
            "docs/evidence/benchmarks/design/benchmark-priority-map.md"
        ),
        "cannot_claim": CANNOT_CLAIM,
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
    }
    if include_fixture_pilot:
        payload["fixture_official_harness_pilot"] = build_fixture_official_harness_pilot(config)
    validation = validate_sanitized_report(payload)
    payload["sanitized_report_validation"] = validation
    payload["ok"] = validation["ok"]
    if not validation["ok"]:
        payload["status"] = "sanitized_report_validation_failed"
    return payload


def write_json_payload(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


CLI_STDOUT_BOUNDARY = {
    "kind": "aippocampus_longmemeval_v2_official_pilot_cli",
    "stdout_boundary": "static_only",
    "full_report": "use --output for the sanitized JSON decision report",
}


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "LongMemEval-V2 official pilot decision report.\n"
            "Question answered: should AIppocampus proceed toward a tiny official-harness "
            "answer/latency pilot, and with which adapter boundary?\n"
            "Can claim: integration readiness, budget shape, and decision status.\n"
            "Important limits: this is not a V2 score, not a leaderboard/LAFS claim, and "
            "does not execute the official reader.\n"
            "Best next benchmark: run the tiny official-harness pilot only after the "
            "Memory adapter contract is ready."
        ),
        epilog=(
            "Default stdout is a static boundary card. Use --output for the sanitized JSON "
            "decision report; use --json only for the stdout-boundary contract."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--pilot-questions", type=int, default=DEFAULT_PILOT_QUESTIONS)
    parser.add_argument("--max-pilot-questions", type=int, default=DEFAULT_MAX_PILOT_QUESTIONS)
    parser.add_argument("--reader-model", default=DEFAULT_READER_MODEL)
    parser.add_argument("--reader-base-url-env", default=DEFAULT_READER_BASE_URL_ENV)
    parser.add_argument("--reader-api-key-env", default=DEFAULT_READER_API_KEY_ENV)
    parser.add_argument("--evaluator-model", default=DEFAULT_EVALUATOR_MODEL)
    parser.add_argument(
        "--evaluator-reasoning-effort",
        default=DEFAULT_EVALUATOR_REASONING_EFFORT,
    )
    parser.add_argument(
        "--memory-context-max-tokens",
        type=int,
        default=DEFAULT_MEMORY_CONTEXT_MAX_TOKENS,
    )
    parser.add_argument(
        "--query-latency-budget-seconds",
        type=float,
        default=DEFAULT_QUERY_LATENCY_BUDGET_SECONDS,
    )
    parser.add_argument(
        "--total-cost-budget-usd",
        type=float,
        default=DEFAULT_TOTAL_COST_BUDGET_USD,
    )
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument(
        "--include-fixture-pilot",
        action="store_true",
        help="Embed the deterministic local Memory-API fixture pilot; not an official score.",
    )
    parser.add_argument("--json", action="store_true", dest="json_output")
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    config = PilotConfig(
        pilot_questions=args.pilot_questions,
        max_pilot_questions=args.max_pilot_questions,
        reader_model=args.reader_model,
        reader_base_url_env=args.reader_base_url_env,
        reader_api_key_env=args.reader_api_key_env,
        evaluator_model=args.evaluator_model,
        evaluator_reasoning_effort=args.evaluator_reasoning_effort,
        memory_context_max_tokens=args.memory_context_max_tokens,
        query_latency_budget_seconds=args.query_latency_budget_seconds,
        total_cost_budget_usd=args.total_cost_budget_usd,
    )
    payload = build_report(config, include_fixture_pilot=args.include_fixture_pilot)
    if args.output:
        write_json_payload(args.output, payload)
    if args.json_output:
        print(json.dumps(CLI_STDOUT_BOUNDARY, ensure_ascii=False, indent=2))
    else:
        print("AIppocampus LongMemEval-V2 official pilot decision")
        print("- stdout: static boundary only")
        print("- full report: use --output for sanitized JSON")
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
