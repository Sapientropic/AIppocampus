#!/usr/bin/env python3
"""Small statistical reporting helpers for benchmark claim boundaries.

These helpers report uncertainty around observed rates. They do not make a
biased or selected sample representative; callers must keep claim boundaries
and sampling caveats in their own report metadata.
"""

from __future__ import annotations

import math
from typing import Any

DEFAULT_CONFIDENCE_LEVEL = 0.95
DEFAULT_SMALL_SAMPLE_THRESHOLD = 30
_Z_BY_CONFIDENCE_LEVEL = {
    0.90: 1.6448536269514722,
    0.95: 1.959963984540054,
    0.99: 2.5758293035489004,
}


def rounded_rate(numerator: int | float, denominator: int | float) -> float:
    return round(float(numerator) / float(denominator), 4) if denominator else 0.0


def _percent_text(value: int | float) -> str:
    return f"{float(value) * 100:.2f}%"


def _confidence_text(confidence_level: float) -> str:
    return f"{float(confidence_level) * 100:.0f}%"


def _z_value(confidence_level: float) -> float:
    normalized = round(float(confidence_level), 2)
    if normalized not in _Z_BY_CONFIDENCE_LEVEL:
        supported = ", ".join(str(item) for item in sorted(_Z_BY_CONFIDENCE_LEVEL))
        raise ValueError(f"unsupported confidence_level {confidence_level}; use one of {supported}")
    return _Z_BY_CONFIDENCE_LEVEL[normalized]


def wilson_score_interval(
    successes: int,
    total: int,
    *,
    confidence_level: float = DEFAULT_CONFIDENCE_LEVEL,
) -> dict[str, Any]:
    success_count = max(0, int(successes))
    total_count = max(0, int(total))
    if total_count <= 0:
        return {
            "method": "wilson_score",
            "confidence_level": round(float(confidence_level), 2),
            "success_count": 0,
            "total_count": 0,
            "point_estimate": 0.0,
            "lower": 0.0,
            "upper": 0.0,
            "defined": False,
        }
    bounded_successes = min(success_count, total_count)
    z = _z_value(confidence_level)
    p_hat = bounded_successes / total_count
    z2 = z * z
    denominator = 1.0 + z2 / total_count
    center = (p_hat + z2 / (2 * total_count)) / denominator
    half_width = (
        z
        * math.sqrt((p_hat * (1.0 - p_hat) + z2 / (4 * total_count)) / total_count)
        / denominator
    )
    return {
        "method": "wilson_score",
        "confidence_level": round(float(confidence_level), 2),
        "success_count": bounded_successes,
        "total_count": total_count,
        "point_estimate": rounded_rate(bounded_successes, total_count),
        "lower": round(max(0.0, center - half_width), 4),
        "upper": round(min(1.0, center + half_width), 4),
        "defined": True,
    }


def binomial_rate_report(
    name: str,
    *,
    numerator: int,
    denominator: int,
    threshold: float | None = None,
    confidence_level: float = DEFAULT_CONFIDENCE_LEVEL,
) -> dict[str, Any]:
    interval = wilson_score_interval(
        numerator,
        denominator,
        confidence_level=confidence_level,
    )
    point_estimate = interval["point_estimate"]
    report: dict[str, Any] = {
        "name": name,
        "numerator": int(interval["success_count"]),
        "denominator": int(interval["total_count"]),
        "point_estimate": point_estimate,
        "confidence_interval": interval,
        "defined": bool(interval["defined"]),
    }
    if threshold is not None:
        lower = float(interval["lower"])
        report["gate"] = {
            "threshold": float(threshold),
            "point_estimate": point_estimate,
            "lower_bound": lower,
            "passes_point_estimate": point_estimate >= float(threshold),
            "passes_lower_bound": lower >= float(threshold),
        }
    return report


def sample_size_warning(
    report: dict[str, Any],
    *,
    threshold: int = DEFAULT_SMALL_SAMPLE_THRESHOLD,
    evidence_kind: str = "contract-smoke",
) -> dict[str, Any]:
    denominator = int(report.get("denominator") or 0)
    low_inference = 0 < denominator < int(threshold)
    message = ""
    if low_inference:
        message = (
            f"n < {int(threshold)}: treat this as low-inference {evidence_kind} "
            "evidence, not population-quality evidence."
        )
    return {
        "low_inference": low_inference,
        "threshold": int(threshold),
        "denominator": denominator,
        "evidence_kind": evidence_kind,
        "message": message,
    }


def format_rate_report_markdown(
    report: dict[str, Any],
    *,
    include_low_inference_warning: bool = False,
    small_sample_threshold: int = DEFAULT_SMALL_SAMPLE_THRESHOLD,
    evidence_kind: str = "contract-smoke",
) -> str:
    interval = report.get("confidence_interval") or {}
    denominator = int(report.get("denominator") or 0)
    if not bool(report.get("defined")):
        rendered = "undefined (n=0)"
    else:
        confidence = _confidence_text(float(interval.get("confidence_level") or DEFAULT_CONFIDENCE_LEVEL))
        rendered = (
            f"{_percent_text(float(report.get('point_estimate') or 0.0))} "
            f"({confidence} Wilson CI {_percent_text(float(interval.get('lower') or 0.0))}-"
            f"{_percent_text(float(interval.get('upper') or 0.0))}, n={denominator})"
        )
    warning = sample_size_warning(
        report,
        threshold=small_sample_threshold,
        evidence_kind=evidence_kind,
    )
    if include_low_inference_warning and warning["low_inference"]:
        rendered = (
            f"{rendered}; low-inference {evidence_kind} evidence "
            f"(n < {small_sample_threshold})"
        )
    return rendered


def format_zero_event_upper_bound_markdown(
    report: dict[str, Any],
    *,
    include_low_inference_warning: bool = False,
    small_sample_threshold: int = DEFAULT_SMALL_SAMPLE_THRESHOLD,
    evidence_kind: str = "contract-smoke",
) -> str:
    interval = report.get("confidence_interval") or {}
    denominator = int(report.get("denominator") or 0)
    if not bool(report.get("defined")):
        rendered = "undefined (n=0)"
    else:
        confidence = _confidence_text(float(interval.get("confidence_level") or DEFAULT_CONFIDENCE_LEVEL))
        rendered = (
            f"{_percent_text(float(report.get('point_estimate') or 0.0))} observed; "
            f"{confidence} Wilson upper bound {_percent_text(float(interval.get('upper') or 0.0))} "
            f"(n={denominator})"
        )
    warning = sample_size_warning(
        report,
        threshold=small_sample_threshold,
        evidence_kind=evidence_kind,
    )
    if include_low_inference_warning and warning["low_inference"]:
        rendered = (
            f"{rendered}; low-inference {evidence_kind} evidence "
            f"(n < {small_sample_threshold})"
        )
    return rendered


def lower_bound_gate(
    report: dict[str, Any],
    *,
    threshold: float,
    applied_to_status: bool,
) -> dict[str, Any]:
    interval = report.get("confidence_interval") or {}
    point_estimate = float(report.get("point_estimate") or 0.0)
    lower = float(interval.get("lower") or 0.0)
    return {
        "metric": report.get("name"),
        "threshold": float(threshold),
        "point_estimate": point_estimate,
        "lower_bound": lower,
        "confidence_level": float(interval.get("confidence_level") or DEFAULT_CONFIDENCE_LEVEL),
        "confidence_method": interval.get("method") or "wilson_score",
        "passes_point_estimate": point_estimate >= float(threshold),
        "passes_lower_bound": lower >= float(threshold),
        "applied_to_status": bool(applied_to_status),
    }
