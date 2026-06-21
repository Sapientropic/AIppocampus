"""Strict clean-source ref matching and public source-window projection."""

from __future__ import annotations

from typing import Any

from aippocampus_runtime.core import compact_text, sanitize_external_model_text
from aippocampus_runtime.privacy import redact_private_paths
from aippocampus_runtime.source.search import process_noise_reason

MAX_SOURCE_WINDOW_MESSAGES = 8


def _safe_text(value: Any, chars: int) -> str:
    sanitized, _ = sanitize_external_model_text(str(value or ""))
    return compact_text(sanitized, chars)


def _ref_value(ref: dict[str, Any], key: str) -> str:
    value = ref.get(key)
    return "" if value in (None, "") else str(value)


def _message_value(message: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = message.get(key)
        if value not in (None, ""):
            return str(value)
    return ""


def _ref_field_is_compatible(
    message: dict[str, Any],
    ref: dict[str, Any],
    ref_key: str,
    *message_keys: str,
) -> bool:
    expected = _ref_value(ref, ref_key)
    if not expected:
        return True
    actual = _message_value(message, *message_keys)
    # Missing optional metadata on old clean sources should not block an exact
    # stronger-id match. A present-but-different value is a real conflict.
    return not actual or actual == expected


def message_matches_ref(message: dict[str, Any], ref: dict[str, Any]) -> bool:
    if (
        ref.get("thread_key")
        and not any(ref.get(key) for key in ("message_id", "turn_id", "turn_index", "line"))
    ):
        message_thread = str(message.get("thread_key") or "")
        return not message_thread or message_thread == str(ref.get("thread_key"))
    if _ref_value(ref, "message_id"):
        return (
            _message_value(message, "message_id", "id") == _ref_value(ref, "message_id")
            and _ref_field_is_compatible(message, ref, "source_id", "source_id", "source_ref")
            and _ref_field_is_compatible(message, ref, "turn_id", "turn_id")
            and _ref_field_is_compatible(message, ref, "turn_index", "turn_index")
            and _ref_field_is_compatible(message, ref, "line", "source_line", "line")
        )
    if _ref_value(ref, "turn_id"):
        return (
            _message_value(message, "turn_id") == _ref_value(ref, "turn_id")
            and _ref_field_is_compatible(message, ref, "source_id", "source_id", "source_ref")
            and _ref_field_is_compatible(message, ref, "turn_index", "turn_index")
            and _ref_field_is_compatible(message, ref, "line", "source_line", "line")
        )
    if _ref_value(ref, "source_id"):
        return (
            _message_value(message, "source_id", "source_ref") == _ref_value(ref, "source_id")
            and _ref_field_is_compatible(message, ref, "turn_index", "turn_index")
            and _ref_field_is_compatible(message, ref, "line", "source_line", "line")
        )
    if _ref_value(ref, "turn_index"):
        return (
            _message_value(message, "turn_index") == _ref_value(ref, "turn_index")
            and _ref_field_is_compatible(message, ref, "line", "source_line", "line")
        )
    if _ref_value(ref, "line"):
        return _message_value(message, "source_line", "line") == _ref_value(ref, "line")
    return False


def turn_messages(messages: list[dict[str, Any]], selected: dict[str, Any]) -> list[dict[str, Any]]:
    turn_id = selected.get("turn_id")
    turn_index = selected.get("turn_index")
    if not turn_id and turn_index is None:
        return [selected]
    window = [
        message
        for message in messages
        if (turn_id and message.get("turn_id") == turn_id)
        or (turn_index is not None and message.get("turn_index") == turn_index)
    ]
    window.sort(key=lambda item: int(item.get("clean_ordinal") or item.get("source_line") or 0))
    return window[:MAX_SOURCE_WINDOW_MESSAGES]


def source_use_class(message: dict[str, Any]) -> str:
    """Classify reopened source so audit material is not mistaken for continuity."""

    text = str(message.get("text") or "")
    phase = str(message.get("phase") or "").casefold()
    role = str(message.get("role") or "").casefold()
    if process_noise_reason(text) or phase in {"commentary", "analysis", "tool", "debug"}:
        return "audit_or_commentary_source"
    if role in {"tool", "system", "developer"}:
        return "audit_or_commentary_source"
    if role == "user" or message.get("is_final") or phase == "final_answer":
        return "foreground_continuity_source"
    return "clean_source_context"


def public_source_message(message: dict[str, Any]) -> dict[str, Any]:
    clean = dict(message)
    source_class = source_use_class(message)
    if "text" in clean:
        clean["text"] = redact_private_paths(_safe_text(clean.get("text"), 1200))
    clean["source_use_class"] = source_class
    if source_class == "audit_or_commentary_source":
        clean["claim_boundary"] = "audit_or_commentary_source_reopen_only"
        clean["ordinary_continuity_priority"] = "low"
    return clean
