#!/usr/bin/env python3
"""Shared privacy-boundary taxonomy for local route diagnostics."""

from __future__ import annotations

import re
from typing import Any

LOCAL_ROUTE_PRIVACY_ACTIONS = {"private_route", "downgrade", "purpose_check"}
HARD_PRIVACY_ACTIONS = {"external_projection_block", "hard_block"}
EXTERNAL_PAYLOAD_REASON_CODES = {
    "external_payload",
    "external_payload_blocked",
    "external_projection",
    "unredacted_external_payload",
}
SECRET_OR_PROPERTY_REASON_CODES = {
    "credential",
    "credential_like",
    "payment_sensitive",
    "property_risk",
    "secret_like",
    "secret_or_property_risk",
}


def public_code(value: Any) -> str:
    return re.sub(r"[^a-z0-9_]+", "_", str(value or "").strip().casefold()).strip("_")


def public_codes(value: Any) -> list[str]:
    values = [value] if isinstance(value, str) else value if isinstance(value, list) else []
    codes: list[str] = []
    seen: set[str] = set()
    for item in values:
        code = public_code(item)
        if code and code not in seen:
            seen.add(code)
            codes.append(code)
    return codes


def normalize_privacy_action(value: Any) -> str:
    action = public_code(value)
    return action if action in LOCAL_ROUTE_PRIVACY_ACTIONS | HARD_PRIVACY_ACTIONS | {"allow"} else ""


def privacy_action_is_local_route(value: Any) -> bool:
    return normalize_privacy_action(value) in LOCAL_ROUTE_PRIVACY_ACTIONS


def privacy_boundary_reason_bucket(
    *,
    privacy_action: Any = "",
    reason_codes: Any = None,
    blocked: bool = False,
) -> str:
    action = normalize_privacy_action(privacy_action)
    codes = set(public_codes(reason_codes))
    if action == "external_projection_block" or codes & EXTERNAL_PAYLOAD_REASON_CODES:
        return "external_payload_blocked"
    if codes & SECRET_OR_PROPERTY_REASON_CODES:
        return "secret_or_property_risk_blocked"
    if action in LOCAL_ROUTE_PRIVACY_ACTIONS:
        return "local_route_handle_only"
    if action == "hard_block" or blocked:
        return "privacy_blocked"
    return ""
