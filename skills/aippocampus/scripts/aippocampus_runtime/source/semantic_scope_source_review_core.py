from __future__ import annotations

import json
from typing import Any

LABEL_GUIDANCE = {
    "personal_reflection": "The user is reflecting on self, feelings, doubts, identity, or meaning.",
    "relationship_continuity": "The message depends on continuity with prior conversations or an ongoing relationship.",
    "reading_notes": "The message records, reacts to, or discusses reading material.",
    "idea_seed": "The message contains an early idea, metaphor, direction, or creative spark worth tracking.",
    "preference": "The user states a stable or situational preference about how things should be done.",
    "life_context": "The message concerns life circumstances, day-to-day context, body, schedule, mood, or lived situation.",
    "technical_work": "The message concerns implementation, repo work, tools, code, architecture, tests, or technical decisions.",
    "open_question": "The message contains an unresolved question, uncertainty, or inquiry to continue later.",
}


def response_content(response: dict[str, Any]) -> str:
    choices = response.get("choices") or []
    if not choices:
        return ""
    return str(((choices[0].get("message") or {}).get("content") or "").strip())


def parse_agent_action(response: dict[str, Any]) -> dict[str, Any]:
    try:
        parsed = json.loads(response_content(response))
    except json.JSONDecodeError as exc:
        return {"action": "parse_error", "error": str(exc)}
    return (
        parsed
        if isinstance(parsed, dict)
        else {"action": "parse_error", "error": "non-object response"}
    )
