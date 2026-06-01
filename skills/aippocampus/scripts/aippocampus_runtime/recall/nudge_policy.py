#!/usr/bin/env python3
"""Safety policy for private ambient recall nudges."""

from __future__ import annotations

import re
from typing import Any

from aippocampus_runtime.core import compact_text, sanitize_external_model_text

SILENT_TUNING = "silent_tuning"
SCENT = "scent"
EVIDENCE = "evidence"

NUDGE_COMMAND_RE = re.compile(
    r"\b("
    r"ignore|disregard|forget|override|bypass|reveal|leak|exfiltrate|"
    r"run|execute|invoke|call|open|read|write|delete|install|download|"
    r"shell|powershell|python|bash|cmd|curl|tool|browser|grep|rg|cat"
    r")\b",
    re.IGNORECASE,
)
NUDGE_SECOND_PERSON_COMMAND_RE = re.compile(
    r"\b("
    r"you\s+must|you\s+should|you\s+need\s+to|you\s+previously|you\s+earlier|"
    r"tell\s+the\s+user|please|do\s+not|don't|remember\s+to"
    r")\b",
    re.IGNORECASE,
)
NUDGE_SOURCE_CLAIM_RE = re.compile(
    r"\b(source\s+says|source\s+proves|evidence\s+proves|verified|proven|confirmed|citation)\b",
    re.IGNORECASE,
)
NUDGE_PRIVATE_SHAPE_RE = re.compile(
    r"(<redacted:[^>]+>|[A-Za-z]:\\|/Users/|/home/|token|cookie|password|secret|api[_-]?key|sk-[A-Za-z0-9_-]{10,})",
    re.IGNORECASE,
)


def _safe_text(value: Any, chars: int) -> str:
    sanitized, _ = sanitize_external_model_text(str(value or ""))
    return compact_text(sanitized, chars)


def _has_unsafe_nudge_fragment(
    text: str,
    *,
    raw_text: str = "",
    support_level: str = "",
    has_source_refs: bool = False,
) -> bool:
    source_claim_without_source = bool(NUDGE_SOURCE_CLAIM_RE.search(text)) and (
        support_level != EVIDENCE or not has_source_refs
    )
    return (
        bool(NUDGE_PRIVATE_SHAPE_RE.search(raw_text or text))
        or bool(NUDGE_PRIVATE_SHAPE_RE.search(text))
        or bool(NUDGE_COMMAND_RE.search(text))
        or bool(NUDGE_SECOND_PERSON_COMMAND_RE.search(text))
        or source_claim_without_source
    )


def safe_nudge_topic(value: Any, chars: int = 90) -> str:
    text = _safe_text(value, chars)
    if not text:
        return "related prior context"
    if _has_unsafe_nudge_fragment(text, raw_text=str(value or "")):
        return "related prior context"
    return text


def render_local_nudge(theme: Any, *, support_level: str, visibility: str) -> str:
    """Render deterministic guidance without letting model text become advice."""
    if visibility in {SILENT_TUNING, ""}:
        return ""
    topic = safe_nudge_topic(theme)
    if support_level == EVIDENCE:
        return f"Open clean source before using {topic}."
    if support_level == SCENT:
        return f"This may lightly connect to {topic}."
    return f"This may connect to {topic}."


def safe_model_nudge_text(
    value: Any,
    *,
    theme: Any,
    support_level: str,
    visibility: str,
    has_source_refs: bool,
) -> str:
    # Warm scouts can draft pleasant wording, but foreground nudges are still
    # model-authored advice. Reject prompt/tool/source/private-shaped text here
    # and fall back to local templates so the nudge cannot become evidence or an
    # instruction to the foreground agent.
    raw = str(value or "")
    sanitized, secret_policy = sanitize_external_model_text(raw)
    text = compact_text(sanitized, 160)
    if not text:
        return ""
    unsafe = bool(secret_policy.get("hard_block")) or _has_unsafe_nudge_fragment(
        text,
        raw_text=raw,
        support_level=support_level,
        has_source_refs=has_source_refs,
    )
    if unsafe:
        return render_local_nudge(theme, support_level=support_level, visibility=visibility)
    return text
