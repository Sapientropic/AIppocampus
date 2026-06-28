"""Tiny health pulse for quick foreground readiness checks."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Mapping

from aippocampus_runtime import health as health_runtime
from aippocampus_runtime.mcp.public_projection import compact_health_payload

PULSE_QUICK_HEALTH_TIMEOUT_MS = 750
PULSE_SLOW_SECTION_THRESHOLD_MS = 250


def _one_line(value: Any, *, fallback: str) -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip())
    return text or fallback


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _readiness(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    readiness = payload.get("product_readiness")
    return readiness if isinstance(readiness, Mapping) else {}


def _recommended_actions(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    actions = payload.get("recommended_actions")
    if isinstance(actions, list):
        return [item for item in actions if isinstance(item, Mapping)]
    safe_next_actions = payload.get("safe_next_actions")
    if isinstance(safe_next_actions, list):
        return [item for item in safe_next_actions if isinstance(item, Mapping)]
    foreground = payload.get("foreground_action")
    return [foreground] if isinstance(foreground, Mapping) else []


def _ordinary_first_recall_usable(payload: Mapping[str, Any], readiness: Mapping[str, Any]) -> bool:
    if "ordinary_first_recall_usable" in readiness:
        return bool(readiness.get("ordinary_first_recall_usable"))
    if "ready" in readiness:
        return bool(readiness.get("ready"))
    return bool(payload.get("ok"))


def _state(payload: Mapping[str, Any]) -> str:
    readiness = _readiness(payload)
    ordinary_usable = _ordinary_first_recall_usable(payload, readiness)
    blocking = (
        not ordinary_usable
        or bool(readiness.get("maintenance_required_before_recall"))
        or _safe_int(readiness.get("blocking_action_count")) > 0
    )
    if blocking:
        return "red"
    advisory = (
        _safe_int(readiness.get("advisory_action_count")) > 0
        or _safe_int(readiness.get("high_severity_action_count")) > 0
        or bool(readiness.get("maintenance_recommended"))
        or bool(_recommended_actions(payload))
    )
    return "yellow" if advisory else "green"


def _action_for_state(payload: Mapping[str, Any], state: str) -> Mapping[str, Any] | None:
    actions = _recommended_actions(payload)
    if not actions:
        return None
    if state == "red":
        for action in actions:
            if str(action.get("severity") or "").casefold() in {"critical", "warning"}:
                return action
    return actions[0]


def _reason(payload: Mapping[str, Any], state: str) -> str:
    action = _action_for_state(payload, state)
    if action is not None:
        return _one_line(
            action.get("reason") or action.get("message") or action.get("why"),
            fallback="health action recommended",
        )
    readiness = _readiness(payload)
    status = readiness.get("status") or payload.get("status")
    if state == "green":
        return _one_line(status, fallback="ready")
    if state == "yellow":
        return _one_line(status, fallback="advisory maintenance recommended")
    return _one_line(status, fallback="first recall is blocked")


def _next_action(payload: Mapping[str, Any], state: str) -> str:
    if state == "green":
        return "continue"
    action = _action_for_state(payload, state)
    if action is not None:
        command = action.get("facade_command") or action.get("command") or action.get("command_template")
        if command:
            return _one_line(command, fallback="aippocampus health --agent-json")
    readiness = _readiness(payload)
    next_best = readiness.get("next_best_action")
    if next_best:
        return _one_line(next_best, fallback="aippocampus health --agent-json")
    return "aippocampus health --agent-json" if state == "red" else "continue"


def pulse_payload(health_payload: Mapping[str, Any]) -> dict[str, str]:
    state = _state(health_payload)
    return {
        "kind": "aippocampus_pulse",
        "state": state,
        "reason": _reason(health_payload, state),
        "next_action": _next_action(health_payload, state),
    }


def build_pulse_payload(cwd: str | Path) -> dict[str, str]:
    """Build the compact foreground pulse from the cheap health contract.

    Pulse is the "can I use AIppocampus right now?" signal. It deliberately
    opts out of operator and expensive diagnostics so storage, host-state, and
    registry-wide repairs stay behind their owner commands. If cheap health
    cannot prove a lane is clean, the compact projection should surface a
    yellow/red next action instead of doing the expensive work inline.
    """

    try:
        health_payload = health_runtime.build_health_report(
            health_runtime.HealthOptions(
                cwd=cwd,
                include_operator_diagnostics=False,
                include_expensive_diagnostics=False,
                operator_timeout_ms=PULSE_QUICK_HEALTH_TIMEOUT_MS,
                slow_section_threshold_ms=PULSE_SLOW_SECTION_THRESHOLD_MS,
            )
        )
    except FileNotFoundError as exc:
        health_payload = health_runtime.missing_rollout_health_report(cwd, exc)
    public_payload = health_runtime.public_health_report(health_payload, include_paths=False)
    return pulse_payload(compact_health_payload(public_payload))


def render_pulse_text(payload: Mapping[str, Any]) -> str:
    state = _one_line(payload.get("state"), fallback="red")
    reason = _one_line(payload.get("reason"), fallback="health unavailable")
    next_action = _one_line(payload.get("next_action"), fallback="aippocampus health --agent-json")
    return f"AIppocampus pulse: {state} - {reason}; next: {next_action}"


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="aippocampus pulse",
        description=(
            "One-line green/yellow/red readiness pulse. Default pulse uses the "
            "cheap health path and never opts into operator or expensive diagnostics."
        ),
    )
    parser.add_argument("--cwd", default=Path.cwd())
    parser.add_argument("--json", action="store_true", dest="json_output")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    payload = build_pulse_payload(args.cwd)
    if args.json_output:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(render_pulse_text(payload))
    return 2 if payload["state"] == "red" else 0


if __name__ == "__main__":
    raise SystemExit(main())
