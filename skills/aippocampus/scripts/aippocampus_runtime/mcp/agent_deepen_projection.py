"""Compact foreground projection for agent_deepen source-court output."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from aippocampus_runtime import core
from aippocampus_runtime.contracts import canonical_foreground_action_fields, shell_quote
from aippocampus_runtime.mcp.compact_profile import strip_compact_foreground_debug_fields
from aippocampus_runtime.mcp.contracts import MCPCompactResponseContract, build_mcp_compact_card
from aippocampus_runtime.privacy import (
    SENSITIVE_ASSIGNMENT_RE,
    SENSITIVE_VALUE_REDACTION,
    redact_private_paths,
    redact_sensitive_values,
)

SOURCE_SNIPPET_CHAR_LIMIT = 420


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


def _operator_detail_command(
    request_index: int | None,
    *,
    last_recall: bool,
    recall_selector: str = "",
) -> str | None:
    if request_index is None or not (last_recall or recall_selector):
        return None
    selector = str(recall_selector or "").strip()
    if selector:
        return (
            f"aippocampus agent deepen --request {request_index} "
            f"--recall-selector {shell_quote(selector)} --json --detail full"
        )
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
    recall_selector: str = "",
    surface: str = "agent_deepen_compact",
) -> dict[str, Any] | MCPCompactResponseContract:
    """Return a compact source-court card with one capped opened-source snippet.

    The full payload remains the source-open/operator view. Compact output is a
    foreground decision card: it should show the exact reopened wording that
    makes the source step useful, while still withholding full source refs,
    macro diagnostics, and local reopen handles by default.
    """

    source = dict(payload)
    if source.get("surface") == "recall" and source.get("status") != "ok":
        # Recovery cards must be parseable foreground JSON even for module
        # entrypoints. Keep the actionable error and canonical v2 foreground
        # action up front, while any heavier local diagnostics stay behind
        # detail fields.
        result = core.dict_or_empty(source.get("result"))
        primary_action = core.dict_or_empty(source.get("foreground_action"))
        follow_up_action = core.dict_or_empty(source.get("follow_up_action"))
        safe_next_actions = [primary_action] if primary_action else []
        if follow_up_action and follow_up_action != primary_action:
            safe_next_actions.append(follow_up_action)
        error = result.get("error") or source.get("error")
        if isinstance(error, Mapping) and error.get("code") == "last_recall_unavailable":
            error = {
                "code": "last_recall_unavailable",
                "message": "Last-recall cache is unavailable; rerun recall for a fresh route.",
            }
        foreground_fields = (
            canonical_foreground_action_fields(
                primary_action,
                safe_next_actions=safe_next_actions,
            )
            if primary_action
            else {}
        )
        return build_mcp_compact_card(
            core.strip_empty(
                {
                    "detail": "compact",
                    "kind": source.get("kind"),
                    "schema_version": source.get("schema_version"),
                    "mode": source.get("mode"),
                    "surface": surface,
                    "surface_class": source.get("surface_class"),
                    "status": source.get("status"),
                    "ok": False,
                    "error": error,
                    **foreground_fields,
                    "follow_up_action": follow_up_action,
                    "claim_boundary": source.get("claim_boundary"),
                }
            ),
            surface=surface,
        )
    if source.get("status") != "ok" or source.get("surface") != "recall":
        return source
    result = core.dict_or_empty(source.get("result"))
    source_window = core.dict_or_empty(result.get("source_window"))
    messages = [item for item in source_window.get("messages") or [] if isinstance(item, dict)]
    source_refs = [item for item in result.get("source_refs") or [] if isinstance(item, dict)]
    message_count = int(source_window.get("message_count") or len(messages))
    primary_snippet = _primary_source_snippet(messages)
    why = core.compact_text(str(result.get("why_this_may_matter") or ""), 180)
    apw_identity = result.get("apw_route_identity") or source.get("apw_route_identity")
    apw_identity = dict(apw_identity) if isinstance(apw_identity, Mapping) else {}
    recall_gate_context = core.dict_or_empty(
        result.get("recall_gate_context") or source.get("recall_gate_context")
    )
    source_anchor_gate = core.dict_or_empty(
        result.get("source_anchor_gate")
        or source.get("source_anchor_gate")
        or recall_gate_context.get("source_anchor_gate")
    )
    target_source_matched = (
        result.get("target_source_matched")
        if "target_source_matched" in result
        else source.get("target_source_matched")
        if "target_source_matched" in source
        else recall_gate_context.get("target_source_matched")
    )
    recommended_evidence_route = (
        result.get("recommended_evidence_route")
        if "recommended_evidence_route" in result
        else source.get("recommended_evidence_route")
        if "recommended_evidence_route" in source
        else recall_gate_context.get("recommended_evidence_route")
    )
    diagnostic_only = source_anchor_gate.get("status") == "blocked" or recommended_evidence_route is False
    source_open_posture = "opened_diagnostic_only" if diagnostic_only else "target_evidence_opened"
    if diagnostic_only:
        primary_action = {
            "id": "treat_opened_source_as_diagnostic",
            "label": "Treat opened source as diagnostic",
            "mutation_risk": "read_only",
            "claim_boundary": "opened_source_not_target_evidence",
            "continue_without_command": True,
            "why": (
                "Source opened, but recall did not accept it as the target evidence route; "
                "use search or another deepen route before making source-backed claims."
            ),
        }
    else:
        primary_action = {
            "id": "use_opened_source_window",
            "label": "Use the opened source window",
            "mutation_risk": "read_only",
            "claim_boundary": "source_open_within_returned_window",
            "continue_without_command": True,
            "why": "Source has been reopened; use only the returned window unless you deepen or request full detail.",
        }
    foreground_fields = canonical_foreground_action_fields(
        primary_action,
        safe_next_actions=[primary_action],
    )
    compact = core.strip_empty(
        {
            "detail": "compact",
            "kind": source.get("kind"),
            "schema_version": source.get("schema_version"),
            "mode": source.get("mode"),
            "surface": surface,
            "status": source.get("status"),
            "ok": True,
            "source_open_posture": source_open_posture,
            "evidence_level": (
                result.get("evidence_level") or result.get("support_level")
                if source_open_posture == "target_evidence_opened"
                else "not_target_evidence"
            ),
            "route_id": result.get("route_id"),
            "source_chain_role": (
                result.get("source_chain_role")
                or source.get("source_chain_role")
                or recall_gate_context.get("source_chain_role")
            ),
            "summary": why,
            "source_window_summary": {
                "message_count": message_count,
                "source_ref_count": len(source_refs),
                "source_classes": _source_classes(messages),
                "has_exact_source": bool(message_count or source_refs),
                "target_source_matched": bool(target_source_matched),
            },
            "primary_source_snippet": primary_snippet,
            "source_scope": (
                "diagnostic_orientation_only"
                if source_open_posture == "opened_diagnostic_only"
                else "opened_window_only"
            ),
            "use_this_for": (
                "orientation only; do not make source-backed claims from this window"
                if source_open_posture == "opened_diagnostic_only"
                else "quote or paraphrase only the opened source window"
            ),
            "reopen_more_if": [
                "facts outside this window",
                "wider context",
                "conflicts",
                "sensitive or stale claims",
            ],
            **foreground_fields,
        }
    )
    return build_mcp_compact_card(
        strip_compact_foreground_debug_fields(compact),
        surface=surface,
    )
