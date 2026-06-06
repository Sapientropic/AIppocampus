#!/usr/bin/env python3
"""Shared hard-risk text gates for Dream hypotheses.

Dream sensitivity protects against unsafe interpretation, leakage, and
profile-as-fact claims. Ordinary same-user continuity words such as preference
or relationship are product signal; they must not park a source-adjudicated
hypothesis by themselves.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

BOUNDARY_COPY = (
    "not as a user-profile fact",
    "not as user-profile fact",
    "not a user-profile fact",
    "not a user profile fact",
    "not as a profile fact",
    "not a profile fact",
    "do not treat this as a user-profile fact",
    "do not treat this as a user profile fact",
    "without becoming a profile fact",
    "without becoming a profile claim",
)
HARD_RISK_TERMS = {
    "api key",
    "bearer token",
    "credential",
    "diagnosis",
    "hidden state",
    "mental health",
    "password",
    "private key",
    "property risk",
    "secret key",
    "secretly",
    "trauma",
    "人格诊断",
    "创伤",
    "密码",
    "密钥",
    "凭据",
    "偷偷",
    "隐藏状态",
    "诊断",
}
PROFILE_CLAIM_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\b(?:personality|profile|identity)\s+(?:diagnosis|fact|claim|trait)\b",
        r"\b(?:user'?s\s+)?(?:personality|profile|identity)\b.{0,32}\b"
        r"(?:means|proves|reveals|shows|determines|explains)\b",
        r"(?:性格|人格|用户画像).{0,16}(?:证明|说明|决定|揭示)",
        r"(?:用户画像|人格|性格).{0,8}(?:事实|诊断|结论)",
    )
)


def _string_values(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,)
    if isinstance(value, Iterable):
        return tuple(str(item) for item in value if item not in {None, ""})
    return ()


def dream_text_hard_risk(*parts: object) -> bool:
    text = " ".join(item for part in parts for item in _string_values(part)).casefold()
    for phrase in BOUNDARY_COPY:
        text = text.replace(phrase, " ")
    return any(term in text for term in HARD_RISK_TERMS) or any(
        pattern.search(text) for pattern in PROFILE_CLAIM_PATTERNS
    )
