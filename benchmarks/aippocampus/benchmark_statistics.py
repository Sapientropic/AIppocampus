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
_Z_BY_CONFIDENCE_LEVEL = {
    0.90: 1.6448536269514722,
    0.95: 1.959963984540054,
    0.99: 2.5758293035489004,
}


def rounded_rate(numerator: int | float, denominator: int | float) -> float:
    return round(float(numerator) / float(denominator), 4) if denominator else 0.0


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
