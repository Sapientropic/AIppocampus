from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from aippocampus_runtime.ops.route_readiness import route_readiness_report
from aippocampus_runtime.privacy import redact_private_paths
from aippocampus_runtime.safety import sanitize_external_model_payload
from aippocampus_runtime.warm_ambient.scout_profiles import (
    DEFAULT_SCOUTS,
    scheduler_tier_policy,
    select_scheduler_scouts,
)

MAGIC_ACTIVATION_POLICY_KIND = "aippocampus_magic_activation_policy"
MAGIC_ACTIVATION_POLICY_SCHEMA_VERSION = 1

ACTIVATION_CLASSES = ("cold_sleep", "cheap_sense", "exploratory_wake", "full_sweep")


def _safe_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value > 0
    if isinstance(value, str):
        return value.strip().casefold() in {"1", "true", "yes", "on", "high"}
    return False


def _safe_int(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def _warning_codes(spend_report: Mapping[str, Any] | None) -> list[str]:
    if not isinstance(spend_report, Mapping):
        return []
    codes = spend_report.get("warning_codes") or []
    if not isinstance(codes, (list, tuple)):
        return []
    return [str(code)[:120] for code in codes if str(code or "").strip()]


def _requested_full_sweep_without_diagnostic(
    *, scheduler_tier: str | None, diagnostic_requested: bool
) -> bool:
    if diagnostic_requested or not scheduler_tier:
        return False
    return scheduler_tier_policy(scheduler_tier)["tier"] == "tier3_diagnostic"


def _high_potential_reasons(signals: Mapping[str, Any], metrics: Mapping[str, int]) -> list[str]:
    reasons: list[str] = []
    if _safe_bool(signals.get("high_uncertainty")):
        reasons.append("high_uncertainty_prompt")
    if any(
        _safe_bool(signals.get(key))
        for key in ("multilingual_potential", "cross_thread_potential", "life_wide_potential")
    ):
        reasons.append("multilingual_or_cross_thread_potential")
    if _safe_bool(signals.get("source_gap_pressure")):
        reasons.append("source_gap_pressure")
    if metrics["deterministic_only_false_skip_count"]:
        reasons.append("deterministic_only_false_skip")
    if metrics["manual_search_rescue_count"]:
        reasons.append("manual_search_rescue")
    if metrics["over_conservative_skip_count"]:
        reasons.append("over_conservative_skip")
    return reasons


def _metrics(
    *,
    signals: Mapping[str, Any],
    readiness: Mapping[str, Any],
    spend_warning_codes: list[str],
    activation_class: str,
    selected_lane_count: int,
    full_lane_count: int,
) -> dict[str, Any]:
    readiness_metrics = readiness.get("metrics") if isinstance(readiness, Mapping) else {}
    readiness_metrics = readiness_metrics if isinstance(readiness_metrics, Mapping) else {}
    low_yield_warning_count = sum(
        1 for code in spend_warning_codes if code.startswith("low_yield_high_spend")
    )
    return {
        "exploratory_wake_count": 1 if activation_class == "exploratory_wake" else 0,
        "exploratory_wake_budget_share": (
            round(selected_lane_count / full_lane_count, 4)
            if activation_class == "exploratory_wake" and full_lane_count
            else 0.0
        ),
        "useful_surprise_count": _safe_int(signals.get("useful_surprise_count")),
        "cross_thread_route_discovered_count": _safe_int(
            signals.get("cross_thread_route_discovered_count")
        ),
        "multilingual_route_discovered_count": _safe_int(
            signals.get("multilingual_route_discovered_count")
        ),
        "source_reopen_after_surprise_rate": float(
            signals.get("source_reopen_after_surprise_rate") or 0.0
        ),
        "deterministic_only_false_skip_count": _safe_int(
            signals.get("deterministic_only_false_skip_count")
        ),
        "low_value_model_wake_count": _safe_int(signals.get("low_value_model_wake_count"))
        + low_yield_warning_count,
        "over_conservative_skip_count": _safe_int(signals.get("over_conservative_skip_count")),
        "manual_search_rescue_count": _safe_int(signals.get("manual_search_rescue_count")),
        "route_candidate_count": _safe_int(readiness_metrics.get("candidate_count")),
        "route_ready_count": _safe_int(readiness_metrics.get("ready_count")),
        "privacy_suppression_count": _safe_int(
            readiness_metrics.get("privacy_suppression_count")
        ),
        "low_value_suppression_count": _safe_int(
            readiness_metrics.get("low_value_suppression_count")
        ),
    }


def _activation_class(
    *,
    signals: Mapping[str, Any],
    readiness: Mapping[str, Any],
    spend_warning_codes: list[str],
    scheduler_tier: str | None,
) -> tuple[str, list[str], str]:
    readiness_metrics = readiness.get("metrics") if isinstance(readiness, Mapping) else {}
    readiness_metrics = readiness_metrics if isinstance(readiness_metrics, Mapping) else {}
    diagnostic_requested = _safe_bool(signals.get("diagnostic_requested"))
    draft_metrics = {
        "deterministic_only_false_skip_count": _safe_int(
            signals.get("deterministic_only_false_skip_count")
        ),
        "manual_search_rescue_count": _safe_int(signals.get("manual_search_rescue_count")),
        "over_conservative_skip_count": _safe_int(signals.get("over_conservative_skip_count")),
    }
    reasons = _high_potential_reasons(signals, draft_metrics)
    privacy_blocked = _safe_bool(signals.get("privacy_blocked"))
    low_yield_warning = any(code.startswith("low_yield_high_spend") for code in spend_warning_codes)
    ready_count = _safe_int(readiness_metrics.get("ready_count"))

    if diagnostic_requested:
        return "full_sweep", ["diagnostic_only_full_sweep"], "tier3_diagnostic"
    if privacy_blocked:
        reason_codes = ["privacy_blocked", *reasons]
        if low_yield_warning:
            reason_codes.append("low_yield_high_spend")
        return "cold_sleep", _dedupe(reason_codes), "tier0_foreground"
    if reasons:
        if low_yield_warning:
            reasons.append("low_yield_high_spend")
        return "exploratory_wake", _dedupe(reasons), "tier2_background"
    if _requested_full_sweep_without_diagnostic(
        scheduler_tier=scheduler_tier,
        diagnostic_requested=diagnostic_requested,
    ):
        return "cheap_sense", ["full_sweep_requires_diagnostic_request"], "tier1_foreground_warm_read"
    if low_yield_warning:
        return "cheap_sense", ["low_yield_high_spend"], "tier1_foreground_warm_read"
    if ready_count:
        return "cheap_sense", ["source_reopen_route_available"], "tier1_foreground_warm_read"
    return "cold_sleep", ["cold_no_model_cues"], "tier0_foreground"


def _dedupe(items: Iterable[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        text = str(item or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out


def _task_profile(signals: Mapping[str, Any], task_profile: str | None) -> str:
    if task_profile:
        return task_profile
    if any(
        _safe_bool(signals.get(key))
        for key in ("multilingual_potential", "cross_thread_potential", "source_gap_pressure")
    ):
        return "vague_multilingual"
    if _safe_bool(signals.get("privacy_sensitive")):
        return "high_risk"
    return "general"


def activation_policy_report(
    signals: Mapping[str, Any] | None = None,
    *,
    route_candidates: Iterable[Mapping[str, Any]] = (),
    spend_report: Mapping[str, Any] | None = None,
    scheduler_tier: str | None = None,
    task_profile: str | None = None,
    now_unix: float | None = None,
    min_roi_score: float = 1.0,
) -> dict[str, Any]:
    """Project whether warm Scout activation should sleep, sense, wake, or sweep.

    The report is deliberately no-write and navigation-only: it balances product
    warmth against existing spend/privacy/source gates, but it never turns Scout
    confidence, route readiness, or prewarm candidates into source evidence.
    """

    clean_signals: Mapping[str, Any] = signals if isinstance(signals, Mapping) else {}
    candidates = [candidate for candidate in route_candidates if isinstance(candidate, Mapping)]
    readiness = route_readiness_report(
        candidates,
        now_unix=now_unix,
        min_roi_score=min_roi_score,
    )
    warnings = _warning_codes(spend_report)
    activation_class, reason_codes, effective_tier = _activation_class(
        signals=clean_signals,
        readiness=readiness,
        spend_warning_codes=warnings,
        scheduler_tier=scheduler_tier,
    )
    profile = _task_profile(clean_signals, task_profile)
    selected_scouts = (
        select_scheduler_scouts(tier=effective_tier, task_profile=profile)
        if activation_class in {"exploratory_wake", "full_sweep"}
        else ()
    )
    tier_policy = scheduler_tier_policy(effective_tier)
    full_lane_count = len(DEFAULT_SCOUTS)
    metrics = _metrics(
        signals=clean_signals,
        readiness=readiness,
        spend_warning_codes=warnings,
        activation_class=activation_class,
        selected_lane_count=len(selected_scouts),
        full_lane_count=full_lane_count,
    )
    report = {
        "kind": MAGIC_ACTIVATION_POLICY_KIND,
        "schema_version": MAGIC_ACTIVATION_POLICY_SCHEMA_VERSION,
        "ok": True,
        "no_write": True,
        "navigation_only": True,
        "activation_classes": list(ACTIVATION_CLASSES),
        "activation_class": activation_class,
        "reason_codes": reason_codes,
        "scheduler": {
            **tier_policy,
            "task_profile": profile,
            "selected_scouts": list(selected_scouts),
            "selected_lane_count": len(selected_scouts),
            "full_lane_count": full_lane_count,
            "selected_lane_total": len(selected_scouts),
            "bounded_exploratory_subset": activation_class == "exploratory_wake",
            "full_sweep_only_when_diagnostic": True,
        },
        "metrics": metrics,
        "route_readiness": readiness,
        "spend_warning_codes": warnings,
        "contract": {
            "no_write_report_only": True,
            "reuses_route_readiness": True,
            "reuses_scheduler_tiers": True,
            "reuses_spend_doctor_warning_codes": True,
            "clean_source_mutation_allowed": False,
            "foreground_hook_mutation_allowed": False,
            "normal_foreground_full_sweep_allowed": False,
            "scout_output_authority": "navigation_only",
            "source_reopen_required_before_claim": True,
        },
        "privacy_boundary": {
            "raw_prompt_serialized": False,
            "raw_source_text_serialized": False,
            "local_paths_serialized": False,
            "secret_values_serialized": False,
            "thread_ids_serialized": False,
        },
        "can_claim": [
            "activation_classes_projected",
            "bounded_exploratory_wake_budgeted",
            "suppression_reason_codes_reported",
            "source_authority_preserved",
        ],
        "cannot_claim": [
            "scout_output_is_source_truth",
            "route_readiness_proves_memory_quality",
            "lowest_spend_is_best_policy",
            "foreground_full_sweep_is_default",
            "live_user_visible_magic_is_proven",
        ],
    }
    return redact_private_paths(sanitize_external_model_payload(report))


def fixture_magic_activation_policy_report() -> dict[str, Any]:
    return activation_policy_report(
        signals={
            "high_uncertainty": True,
            "multilingual_potential": True,
            "cross_thread_potential": True,
            "source_gap_pressure": True,
            "deterministic_only_false_skip_count": 2,
            "manual_search_rescue_count": 1,
            "over_conservative_skip_count": 1,
            "useful_surprise_count": 1,
            "raw_prompt": "SECRET_TOKEN=abc123 should not serialize",
        },
        route_candidates=[
            {
                "route_id": "source-backed-surprise",
                "surface_kind": "warm_ambient_candidate",
                "freshness": "current",
                "created_unix": 1_000,
                "ttl_seconds": 600,
                "expected_value": 5,
                "estimated_cost": 1,
                "source_refs": [{"thread_key": "session:old", "message_id": "msg-1"}],
                "raw_snippet": "raw private source text must not leak",
            },
            {
                "route_id": "privacy-route",
                "surface_kind": "warm_ambient_candidate",
                "freshness": "current",
                "created_unix": 1_000,
                "ttl_seconds": 600,
                "expected_value": 5,
                "estimated_cost": 1,
                "privacy_state": "blocked",
                "source_refs": [{"thread_key": "E:\\private\\thread.jsonl", "message_id": "msg-2"}],
            },
        ],
        spend_report={"kind": "aippocampus_spend_doctor", "warning_codes": []},
        now_unix=1_010,
    )
