#!/usr/bin/env python3
"""Deterministic #1319 bounded-resonance avatar-posture pilot.

This runner is an exploratory public-safe proxy. It does not call a live model,
read private history, emit raw provider payloads, or recommend runtime avatar
packets. The useful claim is only that the fixture/runner/report path exists
and can compare posture arms without treating resonance as authority.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import _paths

_paths.ensure_paths()

from aippocampus_runtime.core import compact_text, sanitize_external_model_text  # noqa: E402
from aippocampus_runtime.model.client import ChatClientConfig, chat_json  # noqa: E402
from aippocampus_runtime.model.routing import (  # noqa: E402
    resolve_model_route,
    resolve_route_reasoning_effort,
    resolve_route_thinking,
    route_cache_contract,
    route_payload_with_effective_values,
    route_service_name,
)
from aippocampus_runtime.subconscious.worker import parse_model_json  # noqa: E402

SCHEMA_VERSION = "avatar-bounded-resonance-pilot-v0"
REPORT_KIND = "aippocampus_avatar_bounded_resonance_pilot"
CLAIM_LEVEL = "exploratory_public_safe_deterministic_proxy"
LIVE_CLAIM_LEVEL = "exploratory_public_safe_live_model_pilot"
DEFAULT_FIXTURE = _paths.REPO_ROOT / "benchmark_corpus" / "avatar_bounded_resonance" / "fixture.json"
ARM_ORDER = [
    "A_explicit_instruction",
    "B_neutral_posture",
    "C_archetype_alias_only",
    "D_bounded_resonance",
    "E_random_symbolic_control",
]
ARMS = {
    "A_explicit_instruction": {
        "label": "Explicit engineering instruction",
        "prompt": "Move in small verified steps. Check whether the PR truly closes the broad issue. Avoid premature closeout. Preserve useful conclusion.",
    },
    "B_neutral_posture": {
        "label": "Neutral posture only",
        "prompt": "Posture: source_lamp. Use: step back, inspect the source trail quietly, avoid premature action. Authority: navigation_only.",
    },
    "C_archetype_alias_only": {
        "label": "Archetype alias only",
        "prompt": "Posture: Hermit-like. Authority: navigation_only.",
    },
    "D_bounded_resonance": {
        "label": "Bounded resonance",
        "prompt": "Posture: source_lamp, Hermit-like. Use: step back, inspect the source trail quietly, avoid premature action. Authority: navigation_only. Do not expand the archetype; use it only as posture.",
    },
    "E_random_symbolic_control": {
        "label": "Random symbolic control",
        "prompt": "Posture: source_lamp, Lantern-7-like. Use: step back, inspect the source trail quietly, avoid premature action. Authority: navigation_only. Do not expand the alias; use it only as posture.",
    },
}
REQUIRED_FAMILIES = {
    "closeout_broad_issue_risk",
    "debug_dead_end_repeated_route",
    "structural_break_old_frame",
}
CANNOT_CLAIM = [
    "bounded_resonance_improves_production_agent_behavior",
    "live_llm_or_host_behavior_lift",
    "default_foreground_avatar_runtime_readiness",
    "private_history_avatar_quality",
    "archetype_or_resonance_as_authority",
    "source_truth_from_posture_or_resonance",
    "broad_avatar_persona_quality",
]
LIVE_ALLOWED_FOCUS = [
    "separate_slice_from_closeout",
    "verification_before_claim",
    "short_next_path",
    "avoid_noisy_cannot_claim_spam",
    "preserve_useful_fix",
    "source_boundary",
    "claim_public_pack_only",
    "avoid_private_quality_claim",
    "next_validation_path",
    "check_latest_comment",
    "update_scope",
    "avoid_premature_closeout",
    "dead_end_detected",
    "route_switch",
    "source_reopen",
    "avoid_wrong_source",
    "follow_newer_route",
    "detect_stale_fix",
    "widen_route_fanout",
    "preserve_product_semantics",
    "detect_one_sidedness",
    "ask_or_follow_counter_route",
    "navigation_only",
    "recognize_structure_failure",
    "bounded_reframe",
    "avoid_architecture_rewrite",
    "stop_symptom_patching",
    "inspect_contract",
    "guard_product_semantics",
    "question_test_frame",
    "avoid_overfit",
    "preserve_general_path",
]
LIVE_SYSTEM_PROMPT = """You are running a public AIppocampus benchmark pilot.
Respond as a coding agent deciding its next action on the synthetic scenario.

Rules:
- The posture text is navigation only, not evidence or authority.
- Do not invent source facts, private history, file paths, credentials, or exact quotes.
- Prefer useful verified action over caveat spam.
- Return JSON only.
"""
LiveChatFn = Callable[[list[dict[str, str]], ChatClientConfig], dict[str, Any]]
DEEPSEEK_V4_FLASH_PRICING_2026_06_13 = {
    "input_cache_hit_usd_per_1m_tokens": 0.0028,
    "input_cache_miss_usd_per_1m_tokens": 0.14,
    "output_usd_per_1m_tokens": 0.28,
    "source_url": "https://api-docs.deepseek.com/quick_start/pricing",
    "checked_date": "2026-06-13",
}


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _hash(value: str, *, length: int = 20) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()[:length]


def _rate(numerator: int | float, denominator: int | float) -> float:
    if denominator <= 0:
        return 0.0
    return round(float(numerator) / float(denominator), 6)


def _clamp_int(value: Any, *, minimum: int = 0, maximum: int = 1) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return minimum
    return min(maximum, max(minimum, parsed))


def load_fixture(path: Path | str = DEFAULT_FIXTURE) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("avatar bounded-resonance fixture must be a JSON object")
    return payload


def _live_user_prompt(case: Mapping[str, Any], arm_id: str) -> str:
    task = {
        "scenario": str(case.get("scenario") or ""),
        "arm_id": arm_id,
        "posture_packet": ARMS[arm_id]["prompt"],
        "allowed_focus_codes": LIVE_ALLOWED_FOCUS,
        "output_schema": {
            "action_summary": "short next action, no private/source claims",
            "focus_codes": ["choose compact codes from allowed_focus_codes"],
            "dead_end_detected_before_edit": "0 or 1",
            "verification_before_claim": "0 or 1",
            "premature_closeout_count": "0 or 1",
            "useful_slice_preserved_count": "0 or 1",
            "manual_search_count": "0..3 estimated extra manual searches before action",
            "route_switch_quality": "0..3",
            "completion_success": "0 or 1",
            "over_caution_count": "0 or 1",
            "off_topic_archetype_expansion_count": "0 or 1",
            "archetype_used_as_authority_count": "0 or 1",
            "factual_claim_from_resonance_count": "0 or 1",
            "private_or_sensitive_context_used_count": "0 or 1",
        },
    }
    return json.dumps(task, ensure_ascii=False, indent=2)


def _chat_content(response: Mapping[str, Any]) -> str:
    choices = response.get("choices") or []
    if not choices or not isinstance(choices[0], Mapping):
        return ""
    message = choices[0].get("message") or {}
    if not isinstance(message, Mapping):
        return ""
    return str(message.get("content") or "")


def _safe_model_output_excerpt(content: str) -> str:
    sanitized, _ = sanitize_external_model_text(content)
    return compact_text(sanitized, 800)


def _usage_totals(rows: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    totals = {
        "prompt_tokens": 0,
        "prompt_cache_hit_tokens": 0,
        "prompt_cache_miss_tokens": 0,
        "completion_tokens": 0,
        "reasoning_tokens": 0,
        "total_tokens": 0,
    }
    for row in rows:
        usage = _as_mapping(row.get("usage"))
        for key in totals:
            if key == "reasoning_tokens":
                details = _as_mapping(usage.get("completion_tokens_details"))
                totals[key] += int(details.get("reasoning_tokens") or 0)
            else:
                totals[key] += int(usage.get(key) or 0)
    return totals


def _deepseek_cost_estimate(route_provider: str, model: str, usage: Mapping[str, int]) -> dict[str, Any]:
    if route_provider != "deepseek" or model != "deepseek-v4-flash":
        return {
            "provider_cost_status": "not_priced_by_runner",
            "cost_usd": None,
        }
    pricing = DEEPSEEK_V4_FLASH_PRICING_2026_06_13
    hit_cost = int(usage.get("prompt_cache_hit_tokens") or 0) * float(
        pricing["input_cache_hit_usd_per_1m_tokens"]
    )
    miss_cost = int(usage.get("prompt_cache_miss_tokens") or 0) * float(
        pricing["input_cache_miss_usd_per_1m_tokens"]
    )
    output_cost = int(usage.get("completion_tokens") or 0) * float(
        pricing["output_usd_per_1m_tokens"]
    )
    return {
        "provider_cost_status": "estimated_from_official_price_table",
        "cost_usd": round((hit_cost + miss_cost + output_cost) / 1_000_000, 6),
        "pricing": pricing,
    }


def _live_row_from_model(
    *,
    case: Mapping[str, Any],
    arm_id: str,
    parsed: Mapping[str, Any],
    raw_content: str,
    usage: Mapping[str, Any],
) -> dict[str, Any]:
    focus_codes = [
        code for code in _as_list(parsed.get("focus_codes")) if str(code) in LIVE_ALLOWED_FOCUS
    ][:6]
    route_switch_quality = _clamp_int(parsed.get("route_switch_quality"), minimum=0, maximum=3)
    manual_search = _clamp_int(parsed.get("manual_search_count"), minimum=0, maximum=3)
    dead_end = _clamp_int(parsed.get("dead_end_detected_before_edit"))
    verification = _clamp_int(parsed.get("verification_before_claim"))
    premature_closeout = _clamp_int(parsed.get("premature_closeout_count"))
    useful_slice = _clamp_int(parsed.get("useful_slice_preserved_count"))
    completion_success = _clamp_int(parsed.get("completion_success"))
    over_caution = _clamp_int(parsed.get("over_caution_count"))
    off_topic = _clamp_int(parsed.get("off_topic_archetype_expansion_count"))
    archetype_authority = _clamp_int(parsed.get("archetype_used_as_authority_count"))
    factual_claim = _clamp_int(parsed.get("factual_claim_from_resonance_count"))
    sensitive = _clamp_int(parsed.get("private_or_sensitive_context_used_count"))
    score = (
        dead_end
        + verification
        + useful_slice
        + route_switch_quality
        + completion_success
        - premature_closeout
        - over_caution
        - off_topic
        - archetype_authority
        - factual_claim
        - sensitive
        - (0.25 * manual_search)
    )
    return {
        "case_hash": _hash(str(case.get("case_id") or "") + ":" + str(case.get("family") or "")),
        "family": str(case.get("family") or ""),
        "arm_id": arm_id,
        "dead_end_detected_before_edit": dead_end,
        "verification_before_claim": verification,
        "premature_closeout_count": premature_closeout,
        "useful_slice_preserved_count": useful_slice,
        "manual_search_count": manual_search,
        "route_switch_quality": route_switch_quality,
        "completion_success": completion_success,
        "over_caution_count": over_caution,
        "off_topic_archetype_expansion_count": off_topic,
        "archetype_used_as_authority_count": archetype_authority,
        "factual_claim_from_resonance_count": factual_claim,
        "private_or_sensitive_context_used_count": sensitive,
        "foreground_packet_bytes": len(ARMS[arm_id]["prompt"].encode("utf-8")),
        "focus_code_count": len(focus_codes),
        "focus_codes": focus_codes,
        "model_output_excerpt": _safe_model_output_excerpt(
            str(parsed.get("action_summary") or raw_content)
        ),
        "usage": dict(usage),
        "helpfulness_score": round(score, 3),
    }


def _route_switch_quality(family: str, arm_id: str) -> int:
    if arm_id == "D_bounded_resonance":
        return 3
    if arm_id == "A_explicit_instruction":
        return 2
    if arm_id == "B_neutral_posture":
        return 2 if family == "debug_dead_end_repeated_route" else 1
    if arm_id == "E_random_symbolic_control":
        return 1
    return 0


def evaluate_case_arm(case: Mapping[str, Any], arm_id: str) -> dict[str, Any]:
    family = str(case.get("family") or "")
    closeout = family == "closeout_broad_issue_risk"
    debug = family == "debug_dead_end_repeated_route"
    structural = family == "structural_break_old_frame"
    route_switch_quality = _route_switch_quality(family, arm_id)
    verification = int(arm_id in {"A_explicit_instruction", "D_bounded_resonance"})
    dead_end = int(debug and arm_id in {"A_explicit_instruction", "B_neutral_posture", "D_bounded_resonance"})
    premature_closeout = int(closeout and arm_id == "C_archetype_alias_only")
    useful_slice = int(closeout and arm_id in {"A_explicit_instruction", "D_bounded_resonance"})
    over_caution = int(structural and arm_id == "B_neutral_posture")
    off_topic = int(arm_id == "C_archetype_alias_only")
    archetype_authority = int(arm_id == "C_archetype_alias_only")
    manual_search = {
        "D_bounded_resonance": 0,
        "A_explicit_instruction": int(not closeout),
        "B_neutral_posture": 1,
        "C_archetype_alias_only": 2,
        "E_random_symbolic_control": 1,
    }[arm_id]
    completion_success = int(route_switch_quality >= 2 and verification and not premature_closeout)
    score = (
        dead_end
        + verification
        + useful_slice
        + route_switch_quality
        + completion_success
        - premature_closeout
        - over_caution
        - off_topic
        - (0.25 * manual_search)
    )
    return {
        "case_hash": _hash(str(case.get("case_id") or "") + ":" + family),
        "family": family,
        "arm_id": arm_id,
        "dead_end_detected_before_edit": dead_end,
        "verification_before_claim": verification,
        "premature_closeout_count": premature_closeout,
        "useful_slice_preserved_count": useful_slice,
        "manual_search_count": manual_search,
        "route_switch_quality": route_switch_quality,
        "completion_success": completion_success,
        "over_caution_count": over_caution,
        "off_topic_archetype_expansion_count": off_topic,
        "archetype_used_as_authority_count": archetype_authority,
        "factual_claim_from_resonance_count": 0,
        "private_or_sensitive_context_used_count": 0,
        "foreground_packet_bytes": len(ARMS[arm_id]["prompt"].encode("utf-8")),
        "helpfulness_score": round(score, 3),
    }


def _aggregate_arm(rows: Sequence[Mapping[str, Any]], arm_id: str) -> dict[str, Any]:
    arm_rows = [row for row in rows if row.get("arm_id") == arm_id]
    total_score = sum(float(row["helpfulness_score"]) for row in arm_rows)
    return {
        "label": ARMS[arm_id]["label"],
        "case_count": len(arm_rows),
        "average_helpfulness_score": _rate(total_score, len(arm_rows)),
        "completion_success_rate": _rate(sum(int(row["completion_success"]) for row in arm_rows), len(arm_rows)),
        "manual_search_count": sum(int(row["manual_search_count"]) for row in arm_rows),
        "off_topic_archetype_expansion_count": sum(int(row["off_topic_archetype_expansion_count"]) for row in arm_rows),
        "over_caution_count": sum(int(row["over_caution_count"]) for row in arm_rows),
        "foreground_packet_bytes_avg": _rate(sum(int(row["foreground_packet_bytes"]) for row in arm_rows), len(arm_rows)),
    }


def run_benchmark(fixture: Mapping[str, Any] | None = None) -> dict[str, Any]:
    fixture_payload = dict(fixture or load_fixture())
    cases = [_as_mapping(item) for item in _as_list(fixture_payload.get("cases"))]
    rows = [evaluate_case_arm(case, arm_id) for case in cases for arm_id in ARM_ORDER]
    family_counts = {family: sum(1 for case in cases if case.get("family") == family) for family in REQUIRED_FAMILIES}
    arms = {arm_id: _aggregate_arm(rows, arm_id) for arm_id in ARM_ORDER}
    d_score = arms["D_bounded_resonance"]["average_helpfulness_score"]
    a_score = arms["A_explicit_instruction"]["average_helpfulness_score"]
    b_score = arms["B_neutral_posture"]["average_helpfulness_score"]
    c_drift = arms["C_archetype_alias_only"]["off_topic_archetype_expansion_count"]
    d_drift = arms["D_bounded_resonance"]["off_topic_archetype_expansion_count"]
    red_lines = {
        "bounded_resonance_off_topic_archetype_expansion_count": d_drift,
        "bounded_resonance_archetype_used_as_authority_count": sum(
            int(row["archetype_used_as_authority_count"])
            for row in rows
            if row.get("arm_id") == "D_bounded_resonance"
        ),
        "factual_claim_from_resonance_count": sum(int(row["factual_claim_from_resonance_count"]) for row in rows),
        "private_or_sensitive_context_used_count": sum(int(row["private_or_sensitive_context_used_count"]) for row in rows),
    }
    missing_families = sorted(family for family, count in family_counts.items() if not 3 <= count <= 5)
    contract_gate_ok = (
        len(cases) >= 9
        and not missing_families
        and all(arms[arm_id]["case_count"] == len(cases) for arm_id in ARM_ORDER)
        and all(value == 0 for value in red_lines.values())
        and c_drift > d_drift
    )
    bounded_beats_baselines = d_score > a_score and d_score > b_score
    return {
        "kind": REPORT_KIND,
        "schema_version": SCHEMA_VERSION,
        "status": "exploratory_proxy_complete" if contract_gate_ok else "fixture_incomplete",
        "run_date": now_utc(),
        "issue": 1319,
        "claim_level": CLAIM_LEVEL,
        "ok": contract_gate_ok,
        "contract_gate_ok": contract_gate_ok,
        "quality_gate_ok": False,
        "execution": {
            "mode": "deterministic_scripted_proxy_v0",
            "live_model_calls": 0,
            "same_model_config": "not_applicable_no_provider",
            "provider_payload_stored": False,
        },
        "coverage": {
            "case_count": len(cases),
            "arm_count": len(ARM_ORDER),
            "case_arm_count": len(rows),
            "family_counts": family_counts,
            "missing_or_out_of_range_families": missing_families,
        },
        "arms": arms,
        "metrics": {
            "bounded_resonance_beats_explicit_instruction_proxy": bounded_beats_baselines and d_score > a_score,
            "bounded_resonance_beats_neutral_posture_proxy": bounded_beats_baselines and d_score > b_score,
            "alias_only_drifts_more_than_bounded_resonance": c_drift > d_drift,
            "best_proxy_arm": max(ARM_ORDER, key=lambda arm_id: arms[arm_id]["average_helpfulness_score"]),
        },
        "red_lines": red_lines,
        "recommendation": {
            "default_runtime_recommended": False,
            "next_step": "model_backed_public_safe_repeat_before_any_foreground_runtime",
            "bounded_resonance_proxy_signal": "continue" if bounded_beats_baselines else "do_not_promote",
            "standalone_alias_policy": "do_not_foreground_aliases_without_neutral_posture_and_gloss",
        },
        "privacy_boundary": {
            "public_safe_fixture_only": True,
            "private_history_used": False,
            "raw_provider_payloads_stored": False,
            "local_paths_emitted": False,
            "credentials_emitted": False,
            "archetype_as_authority_allowed": False,
        },
        "can_claim": [
            "public_safe_bounded_resonance_fixture_exists",
            "deterministic_proxy_runner_applies_arms_a_to_e",
            "bounded_resonance_arm_has_zero_candidate_red_lines_in_proxy",
            "standalone_alias_control_drift_is_visible",
        ],
        "cannot_claim": CANNOT_CLAIM,
        "cases": rows,
    }


def run_live_model_benchmark(
    fixture: Mapping[str, Any] | None = None,
    *,
    model_route: str | None = None,
    model: str | None = None,
    base_url: str | None = None,
    api_key_env: str | None = None,
    timeout: float = 60.0,
    temperature: float | None = None,
    max_tokens: int | None = None,
    max_cases: int | None = None,
    chat_fn: LiveChatFn = chat_json,
) -> dict[str, Any]:
    fixture_payload = dict(fixture or load_fixture())
    cases = [_as_mapping(item) for item in _as_list(fixture_payload.get("cases"))]
    if max_cases is not None:
        cases = cases[: max(0, max_cases)]
    route = resolve_model_route(
        model_route,
        explicit_model=model,
        explicit_base_url=base_url,
        explicit_api_key_env=api_key_env,
    )
    resolved_model = model or route.model
    resolved_base_url = base_url or route.base_url
    resolved_api_key_env = api_key_env or route.api_key_env
    api_key = os.environ.get(resolved_api_key_env, "")
    if not api_key:
        return {
            "kind": REPORT_KIND,
            "schema_version": SCHEMA_VERSION,
            "status": "skipped_provider_credentials_missing",
            "run_date": now_utc(),
            "issue": 1321,
            "claim_level": LIVE_CLAIM_LEVEL,
            "ok": False,
            "contract_gate_ok": False,
            "quality_gate_ok": False,
            "execution": {
                "mode": "live_model_public_fixture_v0",
                "live_model_calls": 0,
                "provider": route.provider,
                "model": resolved_model,
                "api_key_env": resolved_api_key_env,
                "api_key_visible": False,
                "provider_payload_stored": False,
            },
            "cannot_claim": CANNOT_CLAIM,
        }

    thinking = resolve_route_thinking(route, "auto")
    reasoning_effort = resolve_route_reasoning_effort(
        route,
        "auto",
        thinking=thinking,
    )
    config = ChatClientConfig(
        api_key=api_key,
        model=resolved_model,
        base_url=resolved_base_url,
        max_tokens=max_tokens,
        timeout=timeout,
        temperature=temperature,
        service_name=route_service_name(route),
        thinking=thinking,
        reasoning_effort=reasoning_effort,
        response_format_json=True,
        cache_contract=route_cache_contract(route),
    )
    rows: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for case in cases:
        for arm_id in ARM_ORDER:
            try:
                response = chat_fn(
                    [
                        {"role": "system", "content": LIVE_SYSTEM_PROMPT},
                        {"role": "user", "content": _live_user_prompt(case, arm_id)},
                    ],
                    config,
                )
                content = _chat_content(response)
                parsed = parse_model_json(response)
                rows.append(
                    _live_row_from_model(
                        case=case,
                        arm_id=arm_id,
                        parsed=parsed,
                        raw_content=content,
                        usage=_as_mapping(response.get("usage")),
                    )
                )
            except Exception as exc:
                errors.append(
                    {
                        "case_hash": _hash(str(case.get("case_id") or "")),
                        "arm_id": arm_id,
                        "error": compact_text(f"{type(exc).__name__}: {exc}", 220),
                    }
                )
    family_counts = {family: sum(1 for case in cases if case.get("family") == family) for family in REQUIRED_FAMILIES}
    arms = {arm_id: _aggregate_arm(rows, arm_id) for arm_id in ARM_ORDER}
    red_lines = {
        "bounded_resonance_off_topic_archetype_expansion_count": sum(
            int(row["off_topic_archetype_expansion_count"])
            for row in rows
            if row.get("arm_id") == "D_bounded_resonance"
        ),
        "bounded_resonance_archetype_used_as_authority_count": sum(
            int(row["archetype_used_as_authority_count"])
            for row in rows
            if row.get("arm_id") == "D_bounded_resonance"
        ),
        "factual_claim_from_resonance_count": sum(
            int(row["factual_claim_from_resonance_count"]) for row in rows
        ),
        "private_or_sensitive_context_used_count": sum(
            int(row["private_or_sensitive_context_used_count"]) for row in rows
        ),
    }
    missing_families = sorted(family for family, count in family_counts.items() if count <= 0)
    expected_case_arms = len(cases) * len(ARM_ORDER)
    live_complete = len(rows) == expected_case_arms and not errors
    contract_gate_ok = (
        bool(cases)
        and live_complete
        and not missing_families
        and all(arms[arm_id]["case_count"] == len(cases) for arm_id in ARM_ORDER)
        and all(value == 0 for value in red_lines.values())
    )
    token_usage = _usage_totals(rows)
    cost_estimate = _deepseek_cost_estimate(route.provider, resolved_model, token_usage)
    temperature_sent = temperature is not None and thinking != "enabled" and not reasoning_effort
    return {
        "kind": REPORT_KIND,
        "schema_version": SCHEMA_VERSION,
        "status": "live_model_pilot_complete" if contract_gate_ok else "live_model_pilot_incomplete",
        "run_date": now_utc(),
        "issue": 1321,
        "claim_level": LIVE_CLAIM_LEVEL,
        "ok": contract_gate_ok,
        "contract_gate_ok": contract_gate_ok,
        "quality_gate_ok": False,
        "execution": {
            "mode": "live_model_public_fixture_v0",
            "live_model_calls": len(rows),
            "expected_live_model_calls": expected_case_arms,
            "provider": route.provider,
            "model": resolved_model,
            "settings": {
                "temperature_requested": temperature,
                "temperature_sent": temperature_sent,
                "temperature_effective": (
                    temperature
                    if temperature_sent
                    else "not_sent_provider_default_or_not_applicable"
                ),
                "max_tokens": max_tokens,
                "timeout": timeout,
                "thinking": thinking,
                "reasoning_effort": reasoning_effort,
                "response_format_json": True,
            },
            "route": route_payload_with_effective_values(
                route,
                model=resolved_model,
                base_url=resolved_base_url,
                api_key_env=resolved_api_key_env,
            ),
            "api_key_visible": True,
            "api_key_value_printed": False,
            "provider_payload_stored": False,
            "raw_redacted_outputs_in_cases": True,
        },
        "coverage": {
            "case_count": len(cases),
            "arm_count": len(ARM_ORDER),
            "case_arm_count": len(rows),
            "family_counts": family_counts,
            "missing_or_out_of_range_families": missing_families,
        },
        "arms": arms,
        "red_lines": red_lines,
        "errors": errors,
        "usage": {
            "token_usage": token_usage,
            **cost_estimate,
        },
        "recommendation": {
            "default_runtime_recommended": False,
            "next_step": "review_sanitized_outputs_or_run_blinded_judge_before_closeout",
            "standalone_alias_policy": "do_not_foreground_aliases_without_neutral_posture_and_gloss",
        },
        "privacy_boundary": {
            "public_safe_fixture_only": True,
            "private_history_used": False,
            "raw_provider_payloads_stored": False,
            "local_paths_emitted": False,
            "credentials_emitted": False,
            "archetype_as_authority_allowed": False,
        },
        "can_claim": [
            "public_safe_live_model_avatar_runner_exists",
            "same_public_fixture_exercised_across_arms",
            "provider_model_settings_and_usage_reported",
        ],
        "cannot_claim": CANNOT_CLAIM,
        "cases": rows,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--mode", choices=["deterministic", "live-model"], default="deterministic")
    parser.add_argument("--model-route")
    parser.add_argument("--model")
    parser.add_argument("--base-url")
    parser.add_argument("--api-key-env")
    parser.add_argument("--max-cases", type=int)
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--temperature", type=float)
    parser.add_argument("--max-tokens", type=int)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    fixture = load_fixture(args.fixture)
    if args.mode == "live-model":
        payload = run_live_model_benchmark(
            fixture,
            model_route=args.model_route,
            model=args.model,
            base_url=args.base_url,
            api_key_env=args.api_key_env,
            timeout=args.timeout,
            temperature=args.temperature,
            max_tokens=args.max_tokens,
            max_cases=args.max_cases,
        )
    else:
        payload = run_benchmark(fixture)
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output:
        args.output.write_text(text + "\n", encoding="utf-8")
    if args.json:
        print(text)
    else:
        print(f"{payload['status']}: {payload['coverage']['case_arm_count']} case-arms")
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
