"""Compact foreground projection for agent_explain route diagnostics."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from aippocampus_runtime import core


def _as_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _as_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _without_empty(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: cleaned
            for key, item in value.items()
            if (cleaned := _without_empty(item)) not in (None, "", [])
        }
    if isinstance(value, list):
        return [cleaned for item in value if (cleaned := _without_empty(item)) not in (None, "", [])]
    return value


def _detail_command(request_index: int | None, *, last_recall: bool) -> str | None:
    if request_index is None or not last_recall:
        return None
    return (
        f"aippocampus agent explain --request {request_index} "
        "--last-recall --json --detail full"
    )


def _deepen_action(request_index: int | None, *, last_recall: bool) -> dict[str, Any]:
    if request_index is not None and last_recall:
        return {
            "id": "deepen_selected_route",
            "tool_name": "agent_deepen",
            "arguments": {"request_index": request_index, "last_recall": True},
            "cli_command": (
                f"aippocampus agent deepen --request {request_index} --last-recall --json"
            ),
            "mutation_risk": "read_only",
            "claim_boundary": "no_claim_before_reopen",
        }
    return {
        "id": "select_route_from_fresh_recall",
        "tool_name": "agent_recall",
        "arguments_template": {"query": "{memory_cue}"},
        "requires": ["memory_cue"],
        "template_only": True,
        "cli_command_template": 'aippocampus agent recall "{memory_cue}" --json',
        "why": "Compact explain cannot expose local-private handles; recall again and use a request index.",
        "claim_boundary": "no_claim_before_reopen",
    }


def _primary_decision(reason_codes: list[Any], explanation: Mapping[str, Any]) -> str:
    for code in reason_codes:
        text = str(code or "").strip()
        if _foreground_reason_code(text):
            return text
    return str(explanation.get("next_safe_action") or explanation.get("decision") or "explain_route")


def _foreground_reason_code(text: str) -> bool:
    return bool(
        text
        and text not in {"handle_is_navigation_not_fact", "macro_orientation_not_applied"}
        and not text.startswith("macro_")
        and not text.startswith("projection_status_")
    )


def compact_agent_explain_payload(
    payload: Mapping[str, Any],
    *,
    request_index: int | None = None,
    last_recall: bool = False,
    surface: str = "agent_explain_compact",
) -> dict[str, Any]:
    """Return a compact route explanation before macro/operator diagnostics.

    The full explain envelope remains available for local diagnostics. Compact
    output is deliberately a foreground action card: route explanations are
    navigation context and still require deepen/source reopen before claims.
    """

    source = dict(payload)
    if source.get("surface") != "recall":
        return source
    explanation = _as_dict(source.get("explanation"))
    action = _as_dict(source.get("foreground_action"))
    if source.get("status") != "ok":
        primary = action or _deepen_action(request_index, last_recall=last_recall)
        next_action = _as_dict(source.get("agent_next_action")) or primary
        safe_actions = _as_list(source.get("safe_next_actions")) or [next_action]
        result = _as_dict(source.get("result"))
        error = (
            _as_dict(source.get("error"))
            or _as_dict(result.get("error"))
            or _as_dict(explanation.get("error"))
        )
        return _without_empty(
            {
                "detail": "compact",
                "kind": "aippocampus_route_explain_card",
                "schema_version": source.get("schema_version"),
                "mode": source.get("mode"),
                "surface": surface,
                "status": source.get("status"),
                "ok": source.get("ok", False),
                "error": error,
                "foreground_action": primary,
                "agent_next_action": next_action,
                "safe_next_actions": safe_actions,
                "next_safe_action": next_action,
                "next_safe_action_id": next_action.get("id"),
                "follow_up_action": source.get("follow_up_action"),
                "claim_boundary": "navigation_only_until_source_reopened",
                "detail_command": _detail_command(request_index, last_recall=last_recall),
                "output_boundary": "compact_explain_no_macro_diagnostics",
                "policy_boundary": source.get("policy_boundary"),
            }
        )
    reason_codes = _as_list(explanation.get("reason_codes"))
    primary = _deepen_action(request_index, last_recall=last_recall)
    decision = _primary_decision(reason_codes, explanation)
    foreground_reasons = [
        str(code).strip() for code in reason_codes if _foreground_reason_code(str(code).strip())
    ][:3]
    route_reason = core.compact_text(
        "Route is available as navigation context; reopen source before using it as evidence. "
        + "; ".join(foreground_reasons),
        220,
    )
    return _without_empty(
        {
            "detail": "compact",
            "kind": "aippocampus_route_explain_card",
            "schema_version": source.get("schema_version"),
            "mode": source.get("mode"),
            "surface": surface,
            "status": source.get("status"),
            "ok": True,
            "decision": decision,
            "route_id": explanation.get("route_id"),
            "route_reason": route_reason,
            "foreground_action": primary,
            "agent_next_action": primary,
            "safe_next_actions": [primary],
            "next_safe_action": primary,
            "next_safe_action_id": primary.get("id"),
            "claim_boundary": "navigation_only_until_source_reopened",
            "detail_command": _detail_command(request_index, last_recall=last_recall),
            "output_boundary": "compact_explain_no_macro_diagnostics",
            "policy_boundary": source.get("policy_boundary"),
        }
    )


def project_agent_explain_payload(
    payload: Mapping[str, Any],
    *,
    request_index: int | None = None,
    last_recall: bool = False,
    detail: str = "compact",
    surface: str = "agent_explain_compact",
) -> dict[str, Any]:
    if detail == "full":
        return {"detail": "full", "output_boundary": "local_private_diagnostic_full", **dict(payload)}
    return compact_agent_explain_payload(
        payload,
        request_index=request_index,
        last_recall=last_recall,
        surface=surface,
    )


def project_agent_explain_cli_payload(
    payload: Mapping[str, Any],
    args: Any,
    *,
    surface: str,
) -> dict[str, Any]:
    has_request_selector = bool(getattr(args, "last_recall", False) or getattr(args, "request", None) is not None)
    request_index = int(getattr(args, "request", None) or 1) if has_request_selector else None
    return project_agent_explain_payload(
        payload,
        request_index=request_index,
        last_recall=request_index is not None,
        detail=str(getattr(args, "detail", "compact") or "compact"),
        surface=surface,
    )
