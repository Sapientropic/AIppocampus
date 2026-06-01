#!/usr/bin/env python3
"""Compare two saved AIppocampus benchmark suite reports.

This command is a diagnostic guardrail for trend drift. It intentionally stays
outside ``benchmark_suite.py`` so running a benchmark and interpreting historical
evidence remain separate steps.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
SUITE_KIND = "aippocampus_benchmark_suite"
DIFF_KIND = "aippocampus_benchmark_run_history_diff"

DEFAULT_ABSOLUTE_WARNING_DROP = 0.03
DEFAULT_ABSOLUTE_REGRESSION_DROP = 0.05
DEFAULT_RELATIVE_WARNING_DROP = 0.10
DEFAULT_RELATIVE_REGRESSION_DROP = 0.20
DEFAULT_LOWER_BOUND_WARNING_DROP = 0.05
DEFAULT_SAMPLE_SIZE_WARNING_RATIO = 0.10
DEFAULT_ELAPSED_WARNING_RATIO = 0.50

KEY_CONFIG_FIELDS = (
    "profile",
    "include_track_b",
    "include_track_d",
    "include_deterministic_source_labels",
    "include_live_semantic",
    "include_sharegpt_public_track_b",
    "include_standard_public_track_b",
    "include_private_text",
    # Keep cohort-shaping and threshold-shaping config in the identity check so
    # a sampled or optional-adapter run cannot masquerade as a strict trend diff.
    # Path-bearing config is deliberately excluded from this list.
    "gate_case_limit",
    "payload_case_limit",
    "track_d_case_limit",
    "source_ranking",
    "source_top_k",
    "source_min_hit_rate",
    "source_max_cases",
    "source_min_cases",
    "source_max_term_frequency",
    "fts5_cases",
    "fts5_min_cases",
    "fts5_seed",
    "fts5_top_k",
    "fts5_candidate_limit",
    "sharegpt_public_conversations",
    "sharegpt_public_max_cases",
    "sharegpt_public_min_cases",
    "sharegpt_public_top_k",
    "standard_dataset",
    "standard_max_questions",
    "standard_min_questions",
    "standard_top_k",
    "standard_context_radius",
    "standard_min_session_hit_rate",
    "standard_line_reranker_mode",
    "standard_line_reranker_top_sessions",
    "standard_line_reranker_max_candidates",
    "standard_line_reranker_timeout",
    "standard_line_reranker_max_tokens",
    "standard_line_reranker_workers",
    "live_semantic_conversations",
    "live_semantic_cases",
    "live_semantic_min_cases",
    "live_semantic_min_surface_recall",
    "live_semantic_mode",
    "live_semantic_timeout",
    "live_semantic_workers",
    "live_semantic_case_workers",
)

PRIVACY_BOUNDARY_FIELDS = (
    "raw_text_emitted",
    "absolute_paths_emitted",
    "raw_prompt_emitted",
    "raw_context_emitted",
    "raw_correction_text_emitted",
    "raw_source_refs_emitted",
    "snippets_emitted",
    "source_reference_details_emitted",
)

LOWER_IS_BETTER_MARKERS = (
    "false_positive",
    "false_negative",
    "privacy_breach",
    "breach_rate",
    "error_rate",
    "failure_rate",
    "miss_rate",
    "over_escalation",
    "leak",
)

PUBLIC_ADAPTER_TRACKS = (
    "sharegpt_public_source_evidence",
    "standard_public_retrieval_qa",
    "public_semantic_sidecar_source_evidence",
)

IDENTITY_PATH_SUFFIXES = ("_sha1", "_provided", "_hash", "_fingerprint")
IDENTITY_UNSAFE_KEY_MARKERS = (
    "private_debug",
    "raw_",
    "prompt",
    "snippet",
    "source_reference",
    "source_ref",
    "text",
)


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00",
        "Z",
    )


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def short_fingerprint(payload: dict[str, Any]) -> str:
    return hashlib.sha1(canonical_json(payload).encode("utf-8")).hexdigest()[:16]


def normalized_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return sorted(str(item) for item in value)


def identity_key_is_safe(key: str) -> bool:
    lowered = key.lower()
    if any(marker in lowered for marker in IDENTITY_UNSAFE_KEY_MARKERS):
        return False
    if ("path" in lowered or "dir" in lowered) and not lowered.endswith(
        IDENTITY_PATH_SUFFIXES
    ):
        return False
    return True


def safe_identity_value(value: Any) -> Any:
    if isinstance(value, dict):
        return safe_identity_mapping(value)
    if isinstance(value, list):
        safe_items = [
            safe_identity_value(item)
            for item in value
            if isinstance(item, str | int | float | bool | dict | list) or item is None
        ]
        return sorted(safe_items, key=canonical_json)
    if isinstance(value, str | int | float | bool) or value is None:
        return value
    return None


def safe_identity_mapping(value: dict[str, Any]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for key, raw_value in sorted(value.items()):
        safe_key = str(key)
        if not identity_key_is_safe(safe_key):
            continue
        safe_value = safe_identity_value(raw_value)
        if safe_value is not None:
            summary[safe_key] = safe_value
    return summary


def effective_surface(payload: dict[str, Any]) -> dict[str, Any]:
    surface = ((payload.get("profile_metadata") or {}).get("effective_surface") or {})
    return {
        "included_tracks": normalized_list(surface.get("included_tracks")),
        "optional_surfaces": normalized_list(surface.get("optional_surfaces")),
        "private_text_enabled": bool(surface.get("private_text_enabled")),
        "live_semantic_enabled": bool(surface.get("live_semantic_enabled")),
        "registry_path_provided": bool(surface.get("registry_path_provided")),
    }


def selected_profile(payload: dict[str, Any]) -> str:
    metadata = payload.get("profile_metadata") or {}
    selected = metadata.get("selected_profile") or {}
    return str(selected.get("name") or (payload.get("config") or {}).get("profile") or "")


def config_subset(payload: dict[str, Any]) -> dict[str, Any]:
    config = payload.get("config") or {}
    subset: dict[str, Any] = {}
    for field in KEY_CONFIG_FIELDS:
        if field in config:
            value = config[field]
            subset[field] = sorted(value) if isinstance(value, list) else value
    return subset


def track_status_summary(payload: dict[str, Any]) -> dict[str, Any]:
    statuses = payload.get("track_statuses") or {}
    if not isinstance(statuses, dict):
        return {}
    return safe_identity_mapping(statuses)


def public_adapter_signature(payload: dict[str, Any]) -> dict[str, Any]:
    tracks = payload.get("tracks") or {}
    if not isinstance(tracks, dict):
        return {}
    source_retrieval = tracks.get("source_evidence_retrieval") or {}
    if not isinstance(source_retrieval, dict):
        return {}
    nested_tracks = source_retrieval.get("tracks") or {}
    if not isinstance(nested_tracks, dict):
        return {}

    signatures: dict[str, Any] = {}
    for name in PUBLIC_ADAPTER_TRACKS:
        adapter = nested_tracks.get(name)
        if not isinstance(adapter, dict):
            continue
        signature: dict[str, Any] = {}
        for field in (
            "kind",
            "ok",
            "status",
            "claim_level",
            "sample_case_count",
            "minimum_empirical_case_count",
            "selection_method",
            "sample_size_warning",
        ):
            if field in adapter:
                signature[field] = adapter.get(field)
        if "skip_reason" in adapter:
            # Adapter skip reasons can contain exception text with absolute
            # machine paths. Status/config/corpus summaries carry the comparable
            # surface; the raw reason must stay out of generated diff artifacts.
            signature["skip_reason_present"] = bool(adapter.get("skip_reason"))
        for section in ("config", "corpus", "metrics", "privacy_boundary"):
            section_value = adapter.get(section)
            if isinstance(section_value, dict):
                summary = safe_identity_mapping(section_value)
                if summary:
                    signature[section] = summary
        signatures[name] = signature
    return signatures


def threshold_summary(
    payload: dict[str, Any],
    *,
    metric_names: set[str] | None = None,
) -> dict[str, Any]:
    metadata = payload.get("threshold_metadata") or {}
    metadata_summary: dict[str, Any] = {}
    if isinstance(metadata, dict):
        for name, item in sorted(metadata.items()):
            if isinstance(item, dict):
                metadata_summary[str(name)] = {
                    key: item.get(key)
                    for key in ("value", "owner", "claim_boundary")
                    if key in item
                }
            else:
                metadata_summary[str(name)] = item

    gate_thresholds: dict[str, Any] = {}
    rate_estimates = payload.get("rate_estimates") or {}
    if isinstance(rate_estimates, dict):
        for metric, estimate in sorted(rate_estimates.items()):
            if metric_names is not None and str(metric) not in metric_names:
                continue
            if not isinstance(estimate, dict):
                continue
            gate = estimate.get("gate") or {}
            if isinstance(gate, dict) and "threshold" in gate:
                gate_thresholds[str(metric)] = gate.get("threshold")

    return {
        "threshold_metadata": metadata_summary,
        "rate_gate_thresholds": gate_thresholds,
    }


def validate_suite_payload(payload: dict[str, Any], *, role: str) -> list[str]:
    reasons: list[str] = []
    if payload.get("kind") != SUITE_KIND:
        reasons.append(f"{role}_kind_not_benchmark_suite")
    if int(payload.get("schema_version") or 0) != 1:
        reasons.append(f"{role}_unsupported_schema_version")
    return reasons


def compare_run_identity(
    baseline: dict[str, Any],
    current: dict[str, Any],
) -> dict[str, Any]:
    reasons = validate_suite_payload(baseline, role="baseline") + validate_suite_payload(
        current,
        role="current",
    )
    matched_on: list[str] = []

    baseline_profile = selected_profile(baseline)
    current_profile = selected_profile(current)
    if baseline_profile == current_profile and baseline_profile:
        matched_on.append("profile")
    else:
        reasons.append("profile_changed")

    baseline_surface = effective_surface(baseline)
    current_surface = effective_surface(current)
    if baseline_surface == current_surface:
        matched_on.append("effective_surface")
    else:
        reasons.append("effective_surface_changed")

    baseline_config = config_subset(baseline)
    current_config = config_subset(current)
    if baseline_config == current_config:
        matched_on.append("config_subset")
    else:
        reasons.append("config_subset_changed")

    baseline_statuses = track_status_summary(baseline)
    current_statuses = track_status_summary(current)
    if baseline_statuses == current_statuses:
        matched_on.append("track_statuses")
    else:
        reasons.append("track_statuses_changed")

    baseline_adapters = public_adapter_signature(baseline)
    current_adapters = public_adapter_signature(current)
    if baseline_adapters == current_adapters:
        matched_on.append("public_adapter_signature")
    else:
        reasons.append("public_adapter_signature_changed")

    baseline_metric_names = set((baseline.get("rate_estimates") or {}).keys())
    current_metric_names = set((current.get("rate_estimates") or {}).keys())
    shared_metric_names = {str(metric) for metric in baseline_metric_names & current_metric_names}
    baseline_thresholds = threshold_summary(baseline, metric_names=shared_metric_names)
    current_thresholds = threshold_summary(current, metric_names=shared_metric_names)
    if baseline_thresholds == current_thresholds:
        matched_on.append("thresholds")
    else:
        reasons.append("thresholds_changed")

    return {
        "comparable": not reasons,
        "matched_on": matched_on,
        "incomparable_reasons": sorted(set(reasons)),
        "baseline_profile": baseline_profile,
        "current_profile": current_profile,
        "baseline_effective_surface": baseline_surface,
        "current_effective_surface": current_surface,
        "baseline_config_subset": baseline_config,
        "current_config_subset": current_config,
        "baseline_track_statuses": baseline_statuses,
        "current_track_statuses": current_statuses,
        "baseline_public_adapter_signature": baseline_adapters,
        "current_public_adapter_signature": current_adapters,
        "baseline_thresholds": baseline_thresholds,
        "current_thresholds": current_thresholds,
    }


def metric_direction(metric_name: str) -> str:
    lowered = metric_name.lower()
    if any(marker in lowered for marker in LOWER_IS_BETTER_MARKERS):
        return "lower_is_better"
    return "higher_is_better"


def extract_rate_estimate(estimate: dict[str, Any]) -> dict[str, Any]:
    interval = estimate.get("confidence_interval") or {}
    return {
        "point_estimate": float(estimate.get("point_estimate") or 0.0),
        "lower_bound": float(interval.get("lower") or 0.0),
        "upper_bound": float(interval.get("upper") or 0.0),
        "numerator": int(estimate.get("numerator") or 0),
        "denominator": int(estimate.get("denominator") or 0),
        "defined": bool(estimate.get("defined", True)) and int(estimate.get("denominator") or 0) > 0,
        "confidence_method": interval.get("method") or "",
    }


def metric_warning_only_reason(metric: str) -> str | None:
    lowered = metric.lower()
    if lowered.startswith("live_semantic") or ".live_semantic" in lowered:
        return "live_metric_drop_warning"
    return None


def classify_metric_delta(
    metric: str,
    baseline_estimate: dict[str, Any],
    current_estimate: dict[str, Any],
    *,
    absolute_warning_drop: float,
    absolute_regression_drop: float,
    relative_warning_drop: float,
    relative_regression_drop: float,
    lower_bound_warning_drop: float,
    sample_size_warning_ratio: float,
    warning_only_reason: str | None,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    baseline_rate = extract_rate_estimate(baseline_estimate)
    current_rate = extract_rate_estimate(current_estimate)
    direction = metric_direction(metric)
    warnings: list[dict[str, Any]] = []
    regressions: list[dict[str, Any]] = []

    delta = round(current_rate["point_estimate"] - baseline_rate["point_estimate"], 4)
    lower_delta = round(current_rate["lower_bound"] - baseline_rate["lower_bound"], 4)
    if direction == "lower_is_better":
        bad_delta = round(-delta, 4)
        bad_lower_delta = round(-lower_delta, 4)
    else:
        bad_delta = round(delta, 4)
        bad_lower_delta = round(lower_delta, 4)

    baseline_point = baseline_rate["point_estimate"]
    relative_delta = 0.0
    if baseline_point:
        relative_delta = round(delta / abs(baseline_point), 4)
    bad_relative_delta = -relative_delta if direction == "higher_is_better" else relative_delta

    classification = "unchanged"
    reasons: list[str] = []
    if not baseline_rate["defined"] or not current_rate["defined"]:
        classification = "incomparable"
        reason = {
            "reason_code": "metric_incomparable",
            "metric": metric,
            "baseline_denominator": baseline_rate["denominator"],
            "current_denominator": current_rate["denominator"],
        }
        warnings.append(reason)
        reasons.append("metric_incomparable")
    else:
        sample_drop = baseline_rate["denominator"] - current_rate["denominator"]
        sample_drop_ratio = (
            sample_drop / baseline_rate["denominator"]
            if baseline_rate["denominator"]
            else 0.0
        )
        if sample_drop_ratio >= sample_size_warning_ratio:
            classification = "warning"
            reasons.append("sample_size_drop")
            warnings.append(
                {
                    "reason_code": "sample_size_drop",
                    "metric": metric,
                    "baseline_denominator": baseline_rate["denominator"],
                    "current_denominator": current_rate["denominator"],
                    "drop_ratio": round(sample_drop_ratio, 4),
                }
            )

        if sample_drop_ratio >= sample_size_warning_ratio:
            # Large denominator shifts are themselves the signal. Avoid turning
            # a smaller cohort into a rate regression without stronger policy.
            pass
        elif (
            bad_delta <= -absolute_regression_drop
            or bad_relative_delta >= relative_regression_drop
        ):
            if warning_only_reason:
                classification = "warning"
                reasons.append(warning_only_reason)
                warnings.append(
                    {
                        "reason_code": warning_only_reason,
                        "metric": metric,
                        "direction": direction,
                        "baseline_point_estimate": baseline_rate["point_estimate"],
                        "current_point_estimate": current_rate["point_estimate"],
                        "absolute_delta": delta,
                        "relative_delta": relative_delta,
                    }
                )
            else:
                classification = "regression"
                reasons.append("metric_drop")
                regressions.append(
                    {
                        "reason_code": "metric_drop",
                        "metric": metric,
                        "direction": direction,
                        "baseline_point_estimate": baseline_rate["point_estimate"],
                        "current_point_estimate": current_rate["point_estimate"],
                        "absolute_delta": delta,
                        "relative_delta": relative_delta,
                    }
                )
        elif (
            bad_delta <= -absolute_warning_drop
            or bad_relative_delta >= relative_warning_drop
            or bad_lower_delta <= -lower_bound_warning_drop
        ):
            if classification != "regression":
                classification = "warning"
            reasons.append("metric_drop_warning")
            warnings.append(
                {
                    "reason_code": "metric_drop_warning",
                    "metric": metric,
                    "direction": direction,
                    "baseline_point_estimate": baseline_rate["point_estimate"],
                    "current_point_estimate": current_rate["point_estimate"],
                    "absolute_delta": delta,
                    "relative_delta": relative_delta,
                    "lower_bound_delta": lower_delta,
                }
            )
        elif (direction == "higher_is_better" and delta > 0) or (
            direction == "lower_is_better" and delta < 0
        ):
            classification = "improvement"

    metric_delta = {
        "metric": metric,
        "direction": direction,
        "baseline": baseline_rate,
        "current": current_rate,
        "absolute_delta": delta,
        "relative_delta": relative_delta,
        "lower_bound_delta": lower_delta,
        "classification": classification,
        "reasons": sorted(set(reasons)),
    }
    return metric_delta, warnings, regressions


def compare_elapsed_time(
    baseline: dict[str, Any],
    current: dict[str, Any],
    *,
    elapsed_warning_ratio: float,
) -> list[dict[str, Any]]:
    baseline_elapsed = baseline.get("elapsed_ms")
    current_elapsed = current.get("elapsed_ms")
    if not isinstance(baseline_elapsed, int | float) or not isinstance(
        current_elapsed,
        int | float,
    ):
        return []
    if baseline_elapsed <= 0:
        return []
    increase_ratio = (float(current_elapsed) - float(baseline_elapsed)) / float(
        baseline_elapsed
    )
    if increase_ratio < elapsed_warning_ratio:
        return []
    return [
        {
            "reason_code": "elapsed_time_increase",
            "baseline_elapsed_ms": float(baseline_elapsed),
            "current_elapsed_ms": float(current_elapsed),
            "increase_ratio": round(increase_ratio, 4),
        }
    ]


def compare_privacy_boundary(
    baseline: dict[str, Any],
    current: dict[str, Any],
) -> list[dict[str, Any]]:
    baseline_boundary = baseline.get("privacy_boundary") or {}
    current_boundary = current.get("privacy_boundary") or {}
    regressions: list[dict[str, Any]] = []
    for field in PRIVACY_BOUNDARY_FIELDS:
        baseline_value = bool(baseline_boundary.get(field))
        current_value = bool(current_boundary.get(field))
        if not baseline_value and current_value:
            regressions.append(
                {
                    "reason_code": "privacy_boundary_regression",
                    "field": field,
                    "baseline": False,
                    "current": True,
                }
            )
    return regressions


def compare_metric_deltas(
    baseline: dict[str, Any],
    current: dict[str, Any],
    **thresholds: float,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    baseline_rates = baseline.get("rate_estimates") or {}
    current_rates = current.get("rate_estimates") or {}
    metrics = sorted(set(baseline_rates) & set(current_rates))
    metric_deltas: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    regressions: list[dict[str, Any]] = []
    for metric in sorted(set(baseline_rates) - set(current_rates)):
        warnings.append({"reason_code": "metric_missing_in_current", "metric": metric})
    for metric in sorted(set(current_rates) - set(baseline_rates)):
        warnings.append({"reason_code": "metric_new_in_current", "metric": metric})
    for metric in metrics:
        baseline_estimate = baseline_rates.get(metric)
        current_estimate = current_rates.get(metric)
        if not isinstance(baseline_estimate, dict) or not isinstance(current_estimate, dict):
            continue
        metric_delta, metric_warnings, metric_regressions = classify_metric_delta(
            metric,
            baseline_estimate,
            current_estimate,
            absolute_warning_drop=float(thresholds["absolute_warning_drop"]),
            absolute_regression_drop=float(thresholds["absolute_regression_drop"]),
            relative_warning_drop=float(thresholds["relative_warning_drop"]),
            relative_regression_drop=float(thresholds["relative_regression_drop"]),
            lower_bound_warning_drop=float(thresholds["lower_bound_warning_drop"]),
            sample_size_warning_ratio=float(thresholds["sample_size_warning_ratio"]),
            warning_only_reason=metric_warning_only_reason(metric),
        )
        metric_deltas.append(metric_delta)
        warnings.extend(metric_warnings)
        regressions.extend(metric_regressions)
    return metric_deltas, warnings, regressions


def compare_benchmark_runs(
    baseline: dict[str, Any],
    current: dict[str, Any],
    *,
    absolute_warning_drop: float = DEFAULT_ABSOLUTE_WARNING_DROP,
    absolute_regression_drop: float = DEFAULT_ABSOLUTE_REGRESSION_DROP,
    relative_warning_drop: float = DEFAULT_RELATIVE_WARNING_DROP,
    relative_regression_drop: float = DEFAULT_RELATIVE_REGRESSION_DROP,
    lower_bound_warning_drop: float = DEFAULT_LOWER_BOUND_WARNING_DROP,
    sample_size_warning_ratio: float = DEFAULT_SAMPLE_SIZE_WARNING_RATIO,
    elapsed_warning_ratio: float = DEFAULT_ELAPSED_WARNING_RATIO,
    baseline_path: Path | None = None,
    current_path: Path | None = None,
) -> dict[str, Any]:
    comparison = compare_run_identity(baseline, current)
    warnings: list[dict[str, Any]] = []
    regressions = compare_privacy_boundary(baseline, current)
    metric_deltas: list[dict[str, Any]] = []

    if comparison["comparable"]:
        metric_deltas, metric_warnings, metric_regressions = compare_metric_deltas(
            baseline,
            current,
            absolute_warning_drop=absolute_warning_drop,
            absolute_regression_drop=absolute_regression_drop,
            relative_warning_drop=relative_warning_drop,
            relative_regression_drop=relative_regression_drop,
            lower_bound_warning_drop=lower_bound_warning_drop,
            sample_size_warning_ratio=sample_size_warning_ratio,
        )
        warnings.extend(metric_warnings)
        regressions.extend(metric_regressions)
        warnings.extend(
            compare_elapsed_time(
                baseline,
                current,
                elapsed_warning_ratio=elapsed_warning_ratio,
            )
        )
    else:
        warnings.append(
            {
                "reason_code": "incomparable_runs",
                "incomparable_reasons": comparison["incomparable_reasons"],
            }
        )

    if regressions:
        status = "regression"
    elif warnings:
        status = "warning"
    else:
        status = "no_regression"

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": DIFF_KIND,
        "generated_at": now_utc(),
        "status": status,
        "baseline": {
            "path": baseline_path.name if baseline_path else "",
            "generated_at": baseline.get("generated_at"),
            "fingerprint": short_fingerprint(baseline),
        },
        "current": {
            "path": current_path.name if current_path else "",
            "generated_at": current.get("generated_at"),
            "fingerprint": short_fingerprint(current),
        },
        "comparison": comparison,
        "quality_gate_context": {
            "baseline_quality_gate_ok": bool(baseline.get("quality_gate_ok")),
            "current_quality_gate_ok": bool(current.get("quality_gate_ok")),
            "baseline_status": baseline.get("status"),
            "current_status": current.get("status"),
        },
        "metric_deltas": metric_deltas,
        "warnings": warnings,
        "regressions": regressions,
        "summary": {
            "metric_delta_count": len(metric_deltas),
            "warning_count": len(warnings),
            "regression_count": len(regressions),
            "missing_metric_count": sum(
                1 for item in warnings if item.get("reason_code") == "metric_missing_in_current"
            ),
            "new_metric_count": sum(
                1 for item in warnings if item.get("reason_code") == "metric_new_in_current"
            ),
            "incomparable_metric_count": sum(
                1 for item in metric_deltas if item.get("classification") == "incomparable"
            ),
        },
        "thresholds": {
            "absolute_warning_drop": float(absolute_warning_drop),
            "absolute_regression_drop": float(absolute_regression_drop),
            "relative_warning_drop": float(relative_warning_drop),
            "relative_regression_drop": float(relative_regression_drop),
            "lower_bound_warning_drop": float(lower_bound_warning_drop),
            "sample_size_warning_ratio": float(sample_size_warning_ratio),
            "elapsed_warning_ratio": float(elapsed_warning_ratio),
        },
        "cannot_claim": [
            "trend_diff_is_diagnostic_not_public_quality_proof",
            "incomparable_profiles_or_cohorts_are_not_ranked",
            "confidence_intervals_do_not_repair_sampling_bias",
            "live_model_deltas_are_warning_only_without_stable_policy",
        ],
    }


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path.name} must contain a JSON object")
    return payload


def print_human_summary(payload: dict[str, Any]) -> None:
    print("AIppocampus benchmark run-history diff")
    print(f"- status: {payload['status']}")
    print(f"- comparable: {payload['comparison']['comparable']}")
    print(f"- metric deltas: {payload['summary']['metric_delta_count']}")
    print(f"- warnings: {payload['summary']['warning_count']}")
    print(f"- regressions: {payload['summary']['regression_count']}")
    for item in payload["regressions"][:5]:
        label = item.get("metric") or item.get("field") or "run"
        print(f"  - regression: {item.get('reason_code')} ({label})")
    for item in payload["warnings"][:5]:
        label = item.get("metric") or "run"
        print(f"  - warning: {item.get('reason_code')} ({label})")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Compare two saved benchmark_suite JSON reports and emit a "
            "diagnostic trend/regression artifact."
        )
    )
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--current", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--json", action="store_true", dest="json_output")
    parser.add_argument(
        "--absolute-warning-drop",
        type=float,
        default=DEFAULT_ABSOLUTE_WARNING_DROP,
    )
    parser.add_argument(
        "--absolute-regression-drop",
        type=float,
        default=DEFAULT_ABSOLUTE_REGRESSION_DROP,
    )
    parser.add_argument(
        "--relative-warning-drop",
        type=float,
        default=DEFAULT_RELATIVE_WARNING_DROP,
    )
    parser.add_argument(
        "--relative-regression-drop",
        type=float,
        default=DEFAULT_RELATIVE_REGRESSION_DROP,
    )
    parser.add_argument(
        "--lower-bound-warning-drop",
        type=float,
        default=DEFAULT_LOWER_BOUND_WARNING_DROP,
    )
    parser.add_argument(
        "--sample-size-warning-ratio",
        type=float,
        default=DEFAULT_SAMPLE_SIZE_WARNING_RATIO,
    )
    parser.add_argument(
        "--elapsed-warning-ratio",
        type=float,
        default=DEFAULT_ELAPSED_WARNING_RATIO,
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    baseline = load_json(args.baseline)
    current = load_json(args.current)
    payload = compare_benchmark_runs(
        baseline,
        current,
        absolute_warning_drop=args.absolute_warning_drop,
        absolute_regression_drop=args.absolute_regression_drop,
        relative_warning_drop=args.relative_warning_drop,
        relative_regression_drop=args.relative_regression_drop,
        lower_bound_warning_drop=args.lower_bound_warning_drop,
        sample_size_warning_ratio=args.sample_size_warning_ratio,
        elapsed_warning_ratio=args.elapsed_warning_ratio,
        baseline_path=args.baseline,
        current_path=args.current,
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
