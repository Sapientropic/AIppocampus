"""Compact foreground projection for agent_deepen source-court output."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from aippocampus_runtime import core
from aippocampus_runtime.contracts import canonical_foreground_action_fields, shell_quote
from aippocampus_runtime.privacy import (
    SENSITIVE_ASSIGNMENT_RE,
    SENSITIVE_VALUE_REDACTION,
    redact_private_paths,
    redact_sensitive_values,
)

SOURCE_SNIPPET_CHAR_LIMIT = 420


def _as_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


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


def _source_classes(messages: list[dict[str, Any]]) -> list[str]:
    classes: list[str] = []
    for message in messages:
        value = str(message.get("phase") or message.get("role") or "source_window").strip()
        if value and value not in classes:
            classes.append(value)
    return classes[:4]


def _message_rank(message: Mapping[str, Any]) -> int:
    source_class = str(message.get("source_use_class") or "").strip()
    phase = str(message.get("phase") or "").strip().casefold()
    role = str(message.get("role") or "").strip().casefold()
    if source_class == "foreground_continuity_source":
        return 0
    if role in {"user", "assistant"} and phase not in {"audit", "debug", "tool"}:
        return 1
    if phase in {"commentary", "final_answer"}:
        return 2
    return 3


def _primary_source_snippet(messages: list[dict[str, Any]]) -> dict[str, Any]:
    ranked = sorted(enumerate(messages, start=1), key=lambda item: (_message_rank(item[1]), item[0]))
    for index, message in ranked:
        text = str(message.get("text") or "").strip()
        if not text:
            continue
        compact = core.compact_text(text, SOURCE_SNIPPET_CHAR_LIMIT)
        compact = SENSITIVE_ASSIGNMENT_RE.sub(SENSITIVE_VALUE_REDACTION, compact)
        redacted = str(redact_sensitive_values(redact_private_paths(compact)) or "").strip()
        if not redacted:
            continue
        snippet: dict[str, Any] = {
            "text": redacted,
            "message_index": index,
            "max_chars": SOURCE_SNIPPET_CHAR_LIMIT,
            "truncated": len(text) > len(compact),
            "source_scope": "opened_window_primary_message",
            "claim_boundary": "exact_wording_inside_this_snippet_only",
        }
        role = str(message.get("role") or "").strip()
        phase = str(message.get("phase") or "").strip()
        source_class = str(message.get("source_use_class") or "").strip()
        if role:
            snippet["role"] = role
        if phase:
            snippet["phase"] = phase
        if source_class:
            snippet["source_use_class"] = source_class
        return snippet
    return {}


def _operator_detail_command(request_index: int | None, *, last_recall: bool) -> str | None:
    if request_index is None or not last_recall:
        return None
    return (
        f"aippocampus agent deepen --request {request_index} "
        "--last-recall --json --detail full"
    )


def _feedback_actions(route_id: Any) -> list[dict[str, Any]]:
    clean_route = str(route_id or "").strip()
    if not clean_route:
        return []
    quoted_route = shell_quote(clean_route)
    base = {
        "mutation_risk": "durable_low_authority_feedback_write",
        "claim_boundary": "feedback_is_not_source_truth",
    }
    return [
        {
            "id": "mark_route_helpful",
            "label": "Mark route helpful",
            "command": f"aippocampus agent feedback {quoted_route} --outcome helped --json",
            "why": "Use after the reopened source helped the task; this calibrates routing only.",
            **base,
        },
        {
            "id": "mark_route_wrong",
            "label": "Mark route wrong",
            "command": f"aippocampus agent feedback {quoted_route} --outcome wrong_route --json",
            "why": "Use when the route pulled attention to the wrong source or project.",
            **base,
        },
        {
            "id": "keep_route_quiet",
            "label": "Keep route quiet",
            "command": f"aippocampus agent feedback {quoted_route} --outcome ignored --json",
            "why": "Use when the route is harmless but should not keep surfacing for this kind of task.",
            **base,
        },
    ]


def _carry_next_actions() -> list[dict[str, Any]]:
    base = {
        "mutation_risk": "read_only",
        "claim_boundary": "transfer_setup_not_expanded_source_truth",
    }
    return [
        {
            "id": "choose_export_for_next_thread",
            "label": "Carry context with export",
            "command": "aippocampus export --json",
            "why": "Use after source is reopened when the next step is moving context to another thread or device.",
            **base,
        },
        {
            "id": "choose_sync_for_next_device",
            "label": "Carry context with sync",
            "command": "aippocampus sync --json",
            "why": "Use when continuity should survive across a local sync folder or device boundary.",
            **base,
        },
    ]


def compact_agent_deepen_payload(
    payload: Mapping[str, Any],
    *,
    request_index: int | None = None,
    last_recall: bool = False,
    surface: str = "agent_deepen_compact",
) -> dict[str, Any]:
    """Return a compact source-court card with one capped opened-source snippet.

    The full payload remains the source-open/operator view. Compact output is a
    foreground decision card: it should show the exact reopened wording that
    makes the source step useful, while still withholding full source refs,
    macro diagnostics, and local reopen handles by default.
    """

    source = dict(payload)
    if source.get("surface") == "recall" and source.get("status") != "ok":
        # Recovery cards must be parseable foreground JSON even for module
        # entrypoints. Keep the actionable error and compatibility aliases up
        # front, while any heavier local diagnostics stay behind detail fields.
        result = _as_dict(source.get("result"))
        primary_action = _as_dict(source.get("foreground_action") or source.get("agent_next_action"))
        follow_up_action = _as_dict(source.get("follow_up_action"))
        safe_next_actions = [primary_action] if primary_action else []
        if follow_up_action and follow_up_action != primary_action:
            safe_next_actions.append(follow_up_action)
        foreground_fields = (
            canonical_foreground_action_fields(
                primary_action,
                safe_next_actions=safe_next_actions,
            )
            if primary_action
            else {}
        )
        return _without_empty(
            {
                "detail": "compact",
                "kind": source.get("kind"),
                "schema_version": source.get("schema_version"),
                "mode": source.get("mode"),
                "surface": surface,
                "status": source.get("status"),
                "ok": False,
                "error": result.get("error") or source.get("error"),
                **foreground_fields,
                "next_safe_action": primary_action,
                "next_safe_action_id": source.get("next_safe_action_id") or primary_action.get("id"),
                "boundary_detail": source.get("boundary_detail"),
                "operator_detail": source.get("operator_detail"),
                "output_boundary": "compact_recovery_operator_detail_gated",
            }
        )
    if source.get("status") != "ok" or source.get("surface") != "recall":
        return source
    result = _as_dict(source.get("result"))
    source_window = _as_dict(result.get("source_window"))
    messages = [item for item in source_window.get("messages") or [] if isinstance(item, dict)]
    source_refs = [item for item in result.get("source_refs") or [] if isinstance(item, dict)]
    message_count = int(source_window.get("message_count") or len(messages))
    primary_snippet = _primary_source_snippet(messages)
    why = core.compact_text(str(result.get("why_this_may_matter") or ""), 180)
    route_id = result.get("route_id")
    primary_action = {
        "id": "use_opened_source_window",
        "label": "Use the opened source window",
        "mutation_risk": "read_only",
        "claim_boundary": "source_open_within_returned_window",
        "why": "Source has been reopened; use only the returned window unless you deepen or request full detail.",
    }
    feedback = _feedback_actions(route_id)
    carry_actions = _carry_next_actions()
    foreground_fields = canonical_foreground_action_fields(
        primary_action,
        safe_next_actions=[primary_action, *carry_actions],
    )
    return _without_empty(
        {
            "detail": "compact",
            "kind": source.get("kind"),
            "schema_version": source.get("schema_version"),
            "mode": source.get("mode"),
            "surface": surface,
            "status": source.get("status"),
            "ok": True,
            "evidence_level": result.get("evidence_level") or result.get("support_level"),
            "route_id": result.get("route_id"),
            "summary": why,
            "source_window_summary": {
                "message_count": message_count,
                "source_ref_count": len(source_refs),
                "source_classes": _source_classes(messages),
                "has_exact_source": bool(message_count or source_refs),
            },
            "primary_source_snippet": primary_snippet,
            "claim_boundary": {
                "can_use_for": [
                    "source_open_within_returned_window",
                    "exact_wording_inside_opened_window",
                ],
                "must_reopen_for": [
                    "facts_outside_opened_window",
                    "wider_context",
                    "conflicts",
                    "sensitive_or_stale_claims",
                ],
                "source_summary_is_not_quote": True,
            },
            **foreground_fields,
            "feedback_id": route_id,
            "feedback_actions": feedback,
            "carry_next_actions": carry_actions,
            "feedback_boundary": {
                "feedback_is_source_truth": False,
                "feedback_can_adjust_future_route_ordering": True,
                "feedback_does_not_expand_opened_source_scope": True,
            },
            "operator_detail_command": _operator_detail_command(
                request_index,
                last_recall=last_recall,
            ),
            "output_boundary": "compact_source_court_primary_snippet_no_operator_diagnostics",
            "policy_boundary": source.get("policy_boundary"),
        }
    )
