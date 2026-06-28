#!/usr/bin/env python3
"""Shared hard-risk text gates for Dream hypotheses.

Dream sensitivity protects against unsafe interpretation, leakage, and
profile-as-fact claims. Ordinary same-user continuity words such as preference
or relationship are product signal; they must not park a source-adjudicated
hypothesis by themselves.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import Any

from aippocampus_runtime.warm_ambient.privacy_policy import (
    PRIVACY_HARD_BLOCK_ACTIONS,
)

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
    "不是用户画像事实",
    "不是用户画像",
    "不是人格结论",
    "不是人格事实",
    "不是性格事实",
    "不是性格结论",
    "不要当成用户画像事实",
    "不要当成用户画像",
)
SECRET_LIKE_TERMS = {
    "api key",
    "bearer token",
    "credential",
    "password",
    "private key",
    "secret key",
    "密码",
    "密钥",
    "凭据",
}
SENSITIVE_DOMAIN_TERMS = {
    "diagnosis",
    "mental health",
    "property risk",
    "trauma",
    "人格诊断",
    "创伤",
    "诊断",
}
PROFILE_CLAIM_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\bprofile[-\s]?like\b",
        r"\boverpersonalized\b",
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
    if isinstance(value, Mapping):
        nested: list[str] = []
        for item in value.values():
            nested.extend(_string_values(item))
        return tuple(nested)
    if isinstance(value, Iterable):
        nested = []
        for item in value:
            if item is None or item == "":
                continue
            nested.extend(_string_values(item))
        return tuple(nested)
    return ()


def _boundary_stripped_text(*parts: object) -> str:
    text = " ".join(item for part in parts for item in _string_values(part)).casefold()
    for phrase in BOUNDARY_COPY:
        text = text.replace(phrase, " ")
    return text


def _reason_codes(*values: str) -> list[str]:
    out: list[str] = []
    for value in values:
        if value and value not in out:
            out.append(value)
    return out


def dream_privacy_posture(
    *parts: object,
    cross_domain_sensitive_reuse: bool = False,
    raw_external_projection: bool = False,
    disabled_scope: bool = False,
    high_risk_answer_support: bool = False,
) -> dict[str, Any]:
    """Classify Dream text with the warm-ambient privacy action vocabulary.

    Dream runs in a personal same-user continuity path by default. Profile-like
    or sensitive interpretations should therefore stay useful as private route
    handles unless the caller is reusing them across domains or trying to
    expose secrets/raw private material.
    """

    text = _boundary_stripped_text(*parts)
    secret_like = any(term in text for term in SECRET_LIKE_TERMS)
    profile_like = any(pattern.search(text) for pattern in PROFILE_CLAIM_PATTERNS)
    sensitive_domain = any(term in text for term in SENSITIVE_DOMAIN_TERMS)
    if raw_external_projection:
        action = "external_projection_block"
        reasons = ["raw_external_projection"]
    elif disabled_scope:
        action = "hard_block"
        reasons = ["user_disabled_scope"]
    elif high_risk_answer_support:
        action = "hard_block"
        reasons = ["high_risk_answer_support"]
    elif secret_like:
        action = "hard_block"
        reasons = ["secret_like"]
    elif cross_domain_sensitive_reuse and (profile_like or sensitive_domain):
        action = "purpose_check"
        reasons = ["cross_domain_sensitive_use"]
    elif profile_like:
        action = "private_route"
        reasons = ["profile_like_interpretation"]
    elif sensitive_domain:
        action = "private_route"
        reasons = ["sensitive_domain_route"]
    else:
        action = "allow"
        reasons = []
    return {
        "privacy_action": action,
        "privacy_reason_codes": _reason_codes(*reasons),
        "hard_block": action in PRIVACY_HARD_BLOCK_ACTIONS,
        "raw_external_projection_allowed": False,
        "source_boundary": (
            "same_user_private_route_reopen_before_claim"
            if action in {"private_route", "downgrade", "purpose_check"}
            else "ordinary_same_user_continuity"
        ),
    }


def dream_text_hard_risk(*parts: object) -> bool:
    return bool(dream_privacy_posture(*parts).get("hard_block"))
