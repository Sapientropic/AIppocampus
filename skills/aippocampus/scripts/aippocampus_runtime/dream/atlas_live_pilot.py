#!/usr/bin/env python3
"""Opt-in live provider pilot for deterministic Dream atlas packs."""

from __future__ import annotations

import argparse
import importlib
import json
import os
import time
from collections.abc import Callable, Iterable, Mapping
from typing import Any

from aippocampus_runtime.core import sanitize_external_model_payload, stable_json_id
from aippocampus_runtime.dream import worker as dream_worker
from aippocampus_runtime.dream.worker_contract import (
    stable_worker_contract,
    variable_run_directive,
)
from aippocampus_runtime.dream.working_memory import background_adjudicate_dream_findings
from aippocampus_runtime.model.client import (
    ChatClientConfig,
    cache_metrics_from_response,
    chat_json,
)
from aippocampus_runtime.model.routing import (
    DEFAULT_DEEPSEEK_API_KEY_ENV,
    deepseek_base_url,
    flash_model,
    is_default_deepseek_api_key_env,
    resolve_model_route,
    resolve_route_reasoning_effort,
    resolve_route_thinking,
    route_cache_contract,
    route_payload_with_effective_values,
    route_service_name,
)
from aippocampus_runtime.source.io_kernel import safe_float

LIVE_PILOT_KIND = "aippocampus_dream_atlas_live_pilot"
LIVE_WORKER_KIND = "aippocampus_dream_atlas_live_worker_run"
LIVE_DREAM_FUNCTION = "amplification"
ModelCall = Callable[[list[dict[str, str]], ChatClientConfig], dict[str, Any]]


def _atlas_pack_module() -> Any:
    """Load the deterministic atlas builder without creating an import cycle.

    `atlas_pack.py` is the CLI facade and may import this live helper on demand.
    Keeping this edge dynamic prevents same-directory cycles while preserving
    one runtime source of truth for deterministic atlas selection/reporting.
    """

    return importlib.import_module("aippocampus_runtime.dream.atlas_pack")


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _source_ref_dict(
    ref_id: str,
    *,
    pack: Mapping[str, Any],
    index: int,
) -> dict[str, Any]:
    threads = pack.get("source_thread_ids") or []
    thread_key = str(threads[index % len(threads)] if threads else f"thread_{index}")
    return {
        "thread_key": thread_key,
        "message_id": ref_id,
        "line": index + 1,
        "project_label": pack.get("project_scope") or "project:aippocampus",
        "title": pack.get("pack_id"),
    }


def _atlas_worker_pack(
    selected: list[dict[str, Any]],
    *,
    atlas: Mapping[str, Any],
) -> dict[str, Any]:
    atlas_builder = _atlas_pack_module()
    source_refs: list[dict[str, Any]] = []
    for pack in selected:
        for ref_id in pack["source_ref_ids"]:
            source_refs.append(_source_ref_dict(ref_id, pack=pack, index=len(source_refs)))
    source_thread_count = len(
        {str(ref.get("thread_key") or "") for ref in source_refs if ref.get("thread_key")}
    )
    return {
        "schema_version": 1,
        "kind": dream_worker.PACK_KIND,
        "pack_id": stable_json_id(
            "dream_atlas_live",
            *(pack["pack_id"] for pack in selected),
            length=16,
        ),
        "pack_kind": atlas_builder.ATLAS_KIND,
        "status": atlas_builder.READY_STATUS,
        "selection": {
            "atlas_kind": atlas.get("kind"),
            "selected_pack_count": len(selected),
            "source_card_count": len(atlas.get("source_cards") or []),
            "privacy_mode": atlas.get("privacy_mode"),
        },
        "objective": (
            "Run a bounded long-context Dream atlas pilot over sanitized source "
            "cards. Emit hypotheses only with cited source_ref_ids."
        ),
        "themes": sorted({pack["topic_epoch"] for pack in selected})[:12],
        "concepts": [
            "dream_atlas",
            "long_context",
            "source_cards_only",
            "cross_pack_resonance",
        ],
        "source_seed_ids": [pack["pack_id"] for pack in selected],
        "source_seed_kinds": ["dream_atlas_source_card"],
        "source_contributions": [
            {
                "seed_id": pack["pack_id"],
                "source_ref_count": len(pack["source_ref_ids"]),
                "source_thread_count": len(set(pack["source_thread_ids"])),
            }
            for pack in selected
        ],
        "source_refs": source_refs,
        "source_ref_audit": {
            "status": "clean_source_refs_present" if source_refs else "missing_clean_source_refs",
            "source_ref_count": len(source_refs),
            "source_thread_count": source_thread_count,
            "clean_source_resolution": "not_reopened_atlas_source_cards",
        },
        "eligible_dream_functions": [LIVE_DREAM_FUNCTION],
        "atlas_source_cards": atlas.get("source_cards") or [],
        "truth_boundary": "dream_atlas_source_cards_are_navigation_not_source_truth",
    }


def build_atlas_worker_messages(
    worker_pack: Mapping[str, Any],
    *,
    atlas: Mapping[str, Any],
    deterministic_candidates: list[Mapping[str, Any]],
    max_samples: int,
) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": json.dumps(
                stable_worker_contract(dream_worker.CANDIDATE_KINDS_BY_FUNCTION),
                ensure_ascii=False,
                sort_keys=False,
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                sanitize_external_model_payload(
                    {
                        "prompt_part": "stable_atlas_source_card_payload",
                        "source_pack": dream_worker.safe_pack_payload(worker_pack),
                        "atlas": {
                            "kind": atlas.get("kind"),
                            "schema_version": atlas.get("schema_version"),
                            "cache_contract": atlas.get("cache_contract"),
                            "prompt_order": atlas.get("prompt_order"),
                            "privacy_mode": atlas.get("privacy_mode"),
                            "source_cards": atlas.get("source_cards") or [],
                            "deterministic_candidates": deterministic_candidates,
                            "truth_boundary": (
                                "atlas candidates are dream-synthesized "
                                "navigation candidates, not source facts"
                            ),
                        },
                    }
                ),
                ensure_ascii=False,
                sort_keys=False,
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                variable_run_directive(
                    LIVE_DREAM_FUNCTION,
                    max_samples=max_samples,
                    candidate_kinds_by_function=dream_worker.CANDIDATE_KINDS_BY_FUNCTION,
                ),
                ensure_ascii=False,
                sort_keys=False,
            ),
        },
    ]


def _cost_summary(
    usage: Mapping[str, Any] | None,
    *,
    input_cost_per_million: float | None,
    output_cost_per_million: float | None,
) -> dict[str, Any]:
    if not usage:
        return {
            "mode": "no_provider_usage",
            "estimated_cost_usd": None,
            "input_cost_per_million": input_cost_per_million,
            "output_cost_per_million": output_cost_per_million,
        }
    prompt_tokens = safe_float(usage.get("prompt_tokens"), 0.0)
    completion_tokens = safe_float(usage.get("completion_tokens"), 0.0)
    if input_cost_per_million is None or output_cost_per_million is None:
        return {
            "mode": "provider_pricing_not_configured",
            "estimated_cost_usd": None,
            "prompt_tokens": int(prompt_tokens),
            "completion_tokens": int(completion_tokens),
            "input_cost_per_million": input_cost_per_million,
            "output_cost_per_million": output_cost_per_million,
        }
    estimated = (
        prompt_tokens * float(input_cost_per_million)
        + completion_tokens * float(output_cost_per_million)
    ) / 1_000_000
    return {
        "mode": "user_supplied_token_prices",
        "estimated_cost_usd": round(estimated, 12),
        "prompt_tokens": int(prompt_tokens),
        "completion_tokens": int(completion_tokens),
        "input_cost_per_million": input_cost_per_million,
        "output_cost_per_million": output_cost_per_million,
        "pricing_boundary": "estimate_from_user_supplied_rates_not_provider_invoice",
    }


def _source_ref_validity_rate(findings: Iterable[Mapping[str, Any]]) -> float:
    items = list(findings)
    if not items:
        return 0.0
    missing_ref_failures = {"missing_or_unknown_source_ref_ids"}
    valid = sum(
        1
        for finding in items
        if _safe_int((finding.get("source_ref_audit") or {}).get("source_ref_count")) > 0
        and not (
            missing_ref_failures
            & set((finding.get("source_ref_audit") or {}).get("failed_checks") or [])
        )
    )
    return round(valid / len(items), 4)


def _candidate_mentions_cycle(finding: Mapping[str, Any]) -> bool:
    haystack = json.dumps(finding, ensure_ascii=False).casefold()
    return "cycle" in haystack or "loop" in haystack


def _live_comparison(
    *,
    deterministic_report: Mapping[str, Any],
    worker_run: Mapping[str, Any] | None,
    latency_ms: float | None,
    input_cost_per_million: float | None,
    output_cost_per_million: float | None,
) -> dict[str, Any]:
    metrics = deterministic_report.get("metrics") or {}
    source_cards = (deterministic_report.get("atlas_pack") or {}).get("source_cards", [])
    candidates = [
        item
        for item in deterministic_report.get("atlas_candidates") or []
        if isinstance(item, Mapping)
    ]
    usage = (worker_run or {}).get("usage") if worker_run else None
    usage_map: Mapping[str, Any] | None = usage if isinstance(usage, Mapping) else None
    findings = [
        item
        for item in (worker_run or {}).get("findings", [])
        if isinstance(item, Mapping)
    ]
    rejected = [
        item
        for item in (worker_run or {}).get("rejected_candidates", [])
        if isinstance(item, Mapping)
    ]
    live_counts = (worker_run or {}).get("counts") if worker_run else {}
    live_count_map: Mapping[str, Any] = live_counts if isinstance(live_counts, Mapping) else {}
    return {
        "bounded_pack": {
            "candidate_count": metrics.get("bounded_pack_candidate_count", 0),
            "bridge_detected_count": sum(
                1
                for item in source_cards
                if "weak_bridge" in (item.get("bounded_detected_shapes") or [])
            ),
            "cycle_detected_count": sum(
                1
                for item in source_cards
                if "cycle" in (item.get("bounded_detected_shapes") or [])
            ),
        },
        "atlas": {
            "candidate_count": metrics.get("atlas_candidate_count", 0),
            "bridge_detected_count": sum(
                1
                for item in candidates
                if item.get("candidate_type") == "cross_pack_bridge"
            ),
            "cycle_detected_count": sum(
                1
                for item in candidates
                if item.get("candidate_type") == "cross_pack_cycle"
            ),
            "unsupported_candidate_count": metrics.get("unsupported_candidate_count", 0),
            "source_ref_validity_rate": metrics.get("source_ref_validity_rate", 0.0),
        },
        "live_atlas": {
            "candidate_count": int(live_count_map.get("findings") or 0),
            "accepted_count": int(live_count_map.get("accepted") or 0),
            "parked_count": int(live_count_map.get("parked") or 0),
            "unsupported_candidate_count": sum(
                1
                for item in rejected
                if item.get("reason") in {"unsupported_candidate_kind", "malformed_model_output"}
            ),
            "source_ref_validity_rate": _source_ref_validity_rate(findings),
            "bridge_claim_count": sum(len(item.get("bridge_claims") or []) for item in findings),
            "cycle_detected_count": sum(1 for item in findings if _candidate_mentions_cycle(item)),
        },
        "latency_ms": round(float(latency_ms or 0.0), 3) if latency_ms is not None else None,
        "token_use": dict(usage_map or {}),
        "cost": _cost_summary(
            usage_map,
            input_cost_per_million=input_cost_per_million,
            output_cost_per_million=output_cost_per_million,
        ),
    }


def _run_atlas_worker(
    *,
    worker_pack: Mapping[str, Any],
    atlas: Mapping[str, Any],
    deterministic_candidates: list[Mapping[str, Any]],
    config: ChatClientConfig,
    model_call: ModelCall,
    max_samples: int,
) -> tuple[dict[str, Any], float]:
    atlas_builder = _atlas_pack_module()
    messages = build_atlas_worker_messages(
        worker_pack,
        atlas=atlas,
        deterministic_candidates=deterministic_candidates,
        max_samples=max_samples,
    )
    start = time.perf_counter()
    rejected: list[dict[str, Any]] = []
    response: dict[str, Any] = {}
    try:
        response = model_call(messages, config)
        parsed = dream_worker.model_response_json(response)
        findings, rejected = dream_worker.validated_findings_from_model_output(
            parsed,
            pack=worker_pack,
            dream_function=LIVE_DREAM_FUNCTION,
            max_samples=max_samples,
        )
    except (json.JSONDecodeError, ValueError) as exc:
        findings = []
        rejected = [{"reason": "malformed_model_output", "message": str(exc)[:240]}]
    latency_ms = (time.perf_counter() - start) * 1000
    adjudicated = background_adjudicate_dream_findings(
        findings,
        source_pack=worker_pack,
        adjudication_source="dream_atlas_live_pilot",
    )
    accepted_count = sum(
        1
        for item in adjudicated
        if (item.get("adjudication_result") or {}).get("status") == "accepted"
    )
    parked_count = sum(
        1
        for item in adjudicated
        if (item.get("adjudication_result") or {}).get("status") == "parked"
    )
    worker_run = {
        "schema_version": atlas_builder.SCHEMA_VERSION,
        "kind": LIVE_WORKER_KIND,
        "status": dream_worker.worker_status(
            findings=findings,
            adjudicated=adjudicated,
            rejected=rejected,
        ),
        "pack_id": worker_pack.get("pack_id"),
        "dream_function": LIVE_DREAM_FUNCTION,
        "execution_mode": "detached_background_eval",
        "foreground_eligible": False,
        "live_model_allowed_in_foreground": False,
        "cache_contract": config.cache_contract,
        "prompt_order": atlas_builder.PROMPT_ORDER,
        "findings": findings,
        "adjudicated_findings": adjudicated,
        "dream_working_memory_rows": [],
        "rejected_candidates": rejected,
        "counts": {
            "findings": len(findings),
            "accepted": accepted_count,
            "parked": parked_count,
            "rejected": len(rejected),
        },
        "usage": dict(response.get("usage") or {}) if isinstance(response, Mapping) else {},
        "cache": cache_metrics_from_response(dict(response), config)
        if isinstance(response, Mapping)
        else {},
        "no_write": True,
        "policy": {
            "foreground_model_calls_allowed": False,
            "clean_source_mutation_allowed": False,
            "requires_background_adjudication": True,
            "max_samples": max(1, int(max_samples)),
            "source_cards_only": True,
        },
    }
    return worker_run, latency_ms


def _live_report_from_base(
    *,
    base_report: Mapping[str, Any],
    worker_pack: Mapping[str, Any] | None,
    worker_run: Mapping[str, Any] | None,
    status: str,
    latency_ms: float | None = None,
    model_route: Mapping[str, Any] | None = None,
    input_cost_per_million: float | None = None,
    output_cost_per_million: float | None = None,
) -> dict[str, Any]:
    atlas_builder = _atlas_pack_module()
    usage = worker_run.get("usage") if worker_run else None
    provider_usage = usage if isinstance(usage, Mapping) and usage else None
    public_model_route = dict(model_route or {})
    if "api_key_env" in public_model_route:
        public_model_route.pop("api_key_env", None)
        public_model_route["api_key_env_omitted"] = True
    report = dict(base_report)
    report.update(
        {
            "metrics": {
                **dict(base_report["metrics"]),
                "latency_cost_mode": "provider_usage_attached"
                if provider_usage
                else "live_pilot_no_provider_usage",
            },
            "evaluation": {
                **dict(base_report["evaluation"]),
                "command": (
                    "python -m aippocampus_runtime.dream.atlas_pack "
                    "--fixture --live-pilot --json"
                ),
            },
            "cache_telemetry": atlas_builder.cache_telemetry(provider_usage),
        }
    )
    report["live_pilot"] = {
        "kind": LIVE_PILOT_KIND,
        "status": status,
        "model_route": public_model_route,
        "worker_pack_summary": None
        if worker_pack is None
        else {
            "pack_id": worker_pack.get("pack_id"),
            "source_ref_count": (worker_pack.get("source_ref_audit") or {}).get(
                "source_ref_count"
            ),
            "source_thread_count": (worker_pack.get("source_ref_audit") or {}).get(
                "source_thread_count"
            ),
            "raw_source_text_included": False,
        },
        "worker_run": worker_run,
        "comparison": _live_comparison(
            deterministic_report=base_report,
            worker_run=worker_run,
            latency_ms=latency_ms,
            input_cost_per_million=input_cost_per_million,
            output_cost_per_million=output_cost_per_million,
        ),
        "limits": [
            "small_bounded_pilot_not_broad_quality_claim",
            "model_candidates_remain_dream_synthesized_not_source_truth",
            "cost_is_unknown_without_explicit_price_inputs",
        ],
    }
    report["supports"] = [
        "live_or_skipped_eval_command_for_atlas_packs",
        "provider_usage_and_adjudicated_candidate_comparison"
        if worker_run
        else "missing_key_skip_without_fabricated_provider_metrics",
    ]
    report["cannot_claim"] = [
        item
        for item in report["cannot_claim"]
        if item != "live_deepseek_quality"
    ] + [
        "broad_live_deepseek_quality",
        "broad_long_context_candidate_quality",
    ]
    return report


def run_live_atlas_pilot(
    rows: Iterable[Mapping[str, Any]] | None = None,
    *,
    config: ChatClientConfig | None = None,
    model_call: ModelCall = chat_json,
    max_samples: int = 2,
    input_cost_per_million: float | None = None,
    output_cost_per_million: float | None = None,
    model_route: Mapping[str, Any] | None = None,
    skip_reason: str | None = None,
) -> dict[str, Any]:
    atlas_builder = _atlas_pack_module()
    row_list = list(rows) if rows is not None else atlas_builder.fixture_pack_rows()
    selected, _rejected = atlas_builder.select_ready_packs(row_list)
    base_report = atlas_builder.build_dream_atlas_report(row_list)
    worker_pack = _atlas_worker_pack(selected, atlas=base_report["atlas_pack"])
    if skip_reason:
        return _live_report_from_base(
            base_report=base_report,
            worker_pack=worker_pack,
            worker_run=None,
            status=skip_reason,
            model_route=model_route,
            input_cost_per_million=input_cost_per_million,
            output_cost_per_million=output_cost_per_million,
        )
    if config is None:
        raise RuntimeError("run_live_atlas_pilot requires a ChatClientConfig unless skipped")
    worker_run, latency_ms = _run_atlas_worker(
        worker_pack=worker_pack,
        atlas=base_report["atlas_pack"],
        deterministic_candidates=[
            item
            for item in base_report["atlas_candidates"]
            if isinstance(item, Mapping)
        ],
        config=config,
        model_call=model_call,
        max_samples=max_samples,
    )
    return _live_report_from_base(
        base_report=base_report,
        worker_pack=worker_pack,
        worker_run=worker_run,
        status="live_provider_completed",
        latency_ms=latency_ms,
        model_route=model_route,
        input_cost_per_million=input_cost_per_million,
        output_cost_per_million=output_cost_per_million,
    )


def config_from_args(args: argparse.Namespace) -> tuple[ChatClientConfig | None, dict[str, Any], str | None]:
    api_key_env_arg = str(args.api_key_env or DEFAULT_DEEPSEEK_API_KEY_ENV)
    route = resolve_model_route(
        args.model_route,
        explicit_model=args.model if args.model != flash_model() and not args.model_route else None,
        explicit_base_url=args.base_url if args.base_url != deepseek_base_url() and not args.model_route else None,
        explicit_api_key_env=(
            api_key_env_arg
            if not is_default_deepseek_api_key_env(api_key_env_arg) and not args.model_route
            else None
        ),
    )
    model = route.model if args.model == flash_model() else args.model
    base_url = route.base_url if args.base_url == deepseek_base_url() else args.base_url
    api_key_env = (
        route.api_key_env
        if is_default_deepseek_api_key_env(api_key_env_arg)
        else api_key_env_arg
    )
    model_route = route_payload_with_effective_values(
        route,
        model=model,
        base_url=base_url,
        api_key_env=api_key_env,
    )
    api_key = os.environ.get(api_key_env, "")
    if not api_key:
        if args.skip_if_missing_key:
            return None, model_route, "skipped_missing_api_key"
        raise RuntimeError(
            f"missing {route_service_name(route)} key; set {api_key_env} or pass --api-key-env"
        )
    thinking = resolve_route_thinking(route, args.dream_model_thinking)
    reasoning_effort = resolve_route_reasoning_effort(
        route,
        args.dream_model_reasoning_effort,
        thinking=thinking,
    )
    config = ChatClientConfig(
        api_key=api_key,
        model=model,
        base_url=base_url,
        max_tokens=args.max_tokens,
        timeout=args.timeout,
        temperature=args.temperature,
        service_name=route_service_name(route),
        thinking=thinking,
        reasoning_effort=reasoning_effort,
        response_format_json=True,
        cache_contract=route_cache_contract(route),
    )
    return config, model_route, None
