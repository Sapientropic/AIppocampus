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


def explicit_recall_auto_gate() -> dict[str, Any]:
    from aippocampus_runtime.ops import recall_navigation_promotion

    report: Mapping[str, Any] = (
        recall_navigation_promotion.fixture_recall_navigation_promotion_report()
    )
    gate = report.get("attention_router_explicit_auto_gate")
    if not isinstance(gate, Mapping):
        return {
            "surface": "explicit_agent_recall",
            "gate_ok": False,
            "promotion_decision": "not_promoted",
            "blockers": ["explicit_auto_gate_missing"],
            "public_quality_gate_ok": False,
            "default_adoption_gate_ok": False,
            "metrics": {},
        }
    return dict(gate)


def resolve_policy(mode: bool | str | None = None) -> dict[str, Any]:
    normalized = normalize_mode(mode)
    if normalized == "on":
        return _base_policy("on", enabled=True, reason="explicit_operator_opt_in")
    if normalized == "off":
        return _base_policy("off", enabled=False, reason="explicit_or_default_off")
    try:
        gate = explicit_recall_auto_gate()
        metrics = gate.get("metrics") or {}
        blockers = [str(item) for item in gate.get("blockers") or []]
        gate_ok = bool(gate.get("gate_ok"))
        return {
            "mode": "auto",
            "enabled": gate_ok,
            "reason": "promotion_gate_passed" if gate_ok else "promotion_gate_blocked",
            "promotion_gate_checked": True,
            "promotion_gate_ok": gate_ok,
            "default_adoption_allowed": bool(gate.get("default_adoption_gate_ok")),
            "public_quality_gate_ok": bool(gate.get("public_quality_gate_ok")),
            "promotion_decision": str(gate.get("promotion_decision") or ""),
            "promotion_blockers": blockers,
            "neutral_noop_case_count": int(metrics.get("neutral_noop_case_count") or 0),
            "negative_control_no_help_case_count": int(
                metrics.get("negative_control_no_help_case_count") or 0
            ),
            "public_cohort_case_count": int(metrics.get("public_cohort_case_count") or 0),
            "holdout_case_count": int(metrics.get("holdout_case_count") or 0),
            "attention_router_measured": True,
            "surface": str(gate.get("surface") or "explicit_agent_recall"),
            "operator_override": "use --attention-router-mode on for explicit opt-in sorting",
        }
    except Exception as exc:  # pragma: no cover - defensive fail-closed boundary
        return {
            **_base_policy("auto", enabled=False, reason="promotion_gate_unavailable"),
            "promotion_gate_checked": True,
            "error_type": type(exc).__name__,
        }


__all__ = ["VALID_MODES", "explicit_recall_auto_gate", "normalize_mode", "resolve_policy"]
