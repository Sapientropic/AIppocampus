"""Attention-router adoption policy for agent recall.

The live recall path can use attention-router sorting, but default adoption
must be gated by the shared public-safe promotion harness. This helper keeps
that policy out of foreground packet projection code and fails closed when the
gate is unavailable.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

VALID_MODES = ("off", "on", "auto")


def normalize_mode(value: bool | str | None = None) -> str:
    if isinstance(value, bool):
        return "on" if value else "off"
    raw = str(value or "off").strip().casefold().replace("_", "-")
    aliases = {
        "0": "off",
        "false": "off",
        "no": "off",
        "disabled": "off",
        "1": "on",
        "true": "on",
        "yes": "on",
        "enabled": "on",
        "default": "auto",
        "gated": "auto",
    }
    mode = aliases.get(raw, raw)
    if mode not in VALID_MODES:
        raise ValueError(f"attention router mode must be one of {', '.join(VALID_MODES)}")
    return mode


def _base_policy(mode: str, *, enabled: bool, reason: str) -> dict[str, Any]:
    return {
        "mode": mode,
        "enabled": enabled,
        "reason": reason,
        "promotion_gate_checked": False,
        "promotion_gate_ok": None,
        "default_adoption_allowed": None,
        "promotion_blockers": [],
        "operator_override": "use --attention-router-mode on for explicit opt-in sorting",
    }


def resolve_policy(mode: bool | str | None = None) -> dict[str, Any]:
    normalized = normalize_mode(mode)
    if normalized == "on":
        return _base_policy("on", enabled=True, reason="explicit_operator_opt_in")
    if normalized == "off":
        return _base_policy("off", enabled=False, reason="explicit_or_default_off")
    try:
        from aippocampus_runtime.ops import recall_navigation_promotion

        report: Mapping[str, Any] = (
            recall_navigation_promotion.fixture_recall_navigation_promotion_report()
        )
        metrics = report.get("promotion_metrics") or {}
        readout = report.get("attention_router_readout") or {}
        blockers = [str(item) for item in report.get("promotion_blockers") or []]
        gate_ok = bool(report.get("promotion_gate_ok"))
        return {
            "mode": "auto",
            "enabled": gate_ok,
            "reason": "promotion_gate_passed" if gate_ok else "promotion_gate_blocked",
            "promotion_gate_checked": True,
            "promotion_gate_ok": gate_ok,
            "default_adoption_allowed": bool(report.get("default_adoption_allowed")),
            "promotion_decision": str(report.get("promotion_decision") or ""),
            "promotion_blockers": blockers,
            "feature_hurt_case_count": int(metrics.get("feature_hurt_case_count") or 0),
            "feature_noop_case_count": int(metrics.get("feature_noop_case_count") or 0),
            "attention_router_measured": bool(readout.get("measured")),
            "operator_override": "use --attention-router-mode on for explicit opt-in sorting",
        }
    except Exception as exc:  # pragma: no cover - defensive fail-closed boundary
        return {
            **_base_policy("auto", enabled=False, reason="promotion_gate_unavailable"),
            "promotion_gate_checked": True,
            "error_type": type(exc).__name__,
        }


__all__ = ["VALID_MODES", "normalize_mode", "resolve_policy"]
