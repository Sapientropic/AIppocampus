"""Compact foreground projection for agent_deepen source-court output."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from aippocampus_runtime import core


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


def _operator_detail_command(request_index: int | None, *, last_recall: bool) -> str | None:
    if request_index is None or not last_recall:
        return None
    return (
        f"aippocampus agent deepen --request {request_index} "
        "--last-recall --json --detail full"
    )


def compact_agent_deepen_payload(
    payload: Mapping[str, Any],
    *,
    request_index: int | None = None,
    last_recall: bool = False,
    surface: str = "agent_deepen_compact",
) -> dict[str, Any]:
    """Return source-court summary without source-window bodies or diagnostics.

    The full payload remains the source-open/operator view. Compact output is a
    foreground decision card: it can say that source was opened and where the
    scope boundary is, but it must not ship message text, source refs, macro
    diagnostics, or local reopen handles by default.
    """

    source = dict(payload)
    if source.get("status") != "ok" or source.get("surface") != "recall":
        return source
    result = _as_dict(source.get("result"))
    source_window = _as_dict(result.get("source_window"))
    messages = [item for item in source_window.get("messages") or [] if isinstance(item, dict)]
    source_refs = [item for item in result.get("source_refs") or [] if isinstance(item, dict)]
    message_count = int(source_window.get("message_count") or len(messages))
    why = core.compact_text(str(result.get("why_this_may_matter") or ""), 180)
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
            "operator_detail_command": _operator_detail_command(
                request_index,
                last_recall=last_recall,
            ),
            "output_boundary": "compact_source_court_no_source_window_messages",
            "policy_boundary": source.get("policy_boundary"),
        }
    )
