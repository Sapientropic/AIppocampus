#!/usr/bin/env python3
"""Privacy action compatibility helpers for warm ambient scouts."""

from __future__ import annotations

import re
from typing import Any

from aippocampus_runtime.core import compact_text
from aippocampus_runtime.recall.ambient_cards import (
    ACTIVE_GENTLE_NUDGE,
    DEEP_ARCHIVAL_RECALL,
    SOURCE_BACKED_RECALL_CARD,
)
from aippocampus_runtime.registry.api import unique_preserve

VALID_PRIVACY_ACTIONS = {
    "allow",
    "private_route",
    "downgrade",
    "purpose_check",
    "external_projection_block",
    "hard_block",
}
PRIVACY_HARD_BLOCK_ACTIONS = {"external_projection_block", "hard_block"}
PRIVACY_ROUTE_ACTIONS = {"private_route", "downgrade", "purpose_check"}
PRIVACY_ROUTE_ACTION_PRIORITY = {
    "purpose_check": 3,
    "private_route": 2,
    "downgrade": 1,
    "allow": 0,
}


def clean_privacy_reason_codes(values: Any) -> list[str]:
    if isinstance(values, str):
        raw_values = [values]
    elif isinstance(values, list):
        raw_values = values
    else:
        raw_values = []
    codes: list[str] = []
    seen: set[str] = set()
    for value in raw_values:
        code = re.sub(r"[^a-z0-9_]+", "_", str(value or "").strip().casefold()).strip("_")
        if not code or code in seen:
            continue
        seen.add(code)
        codes.append(code[:80])
        if len(codes) >= 6:
            break
    return codes


def normalize_privacy_action(value: Any) -> str:
    action = re.sub(r"[^a-z0-9_]+", "_", str(value or "").strip().casefold()).strip("_")
    return action if action in VALID_PRIVACY_ACTIONS else ""


def privacy_block_value(parsed: dict[str, Any], *, family: str, action: str) -> bool:
    if family != "privacy_boundary_guard":
        return bool(parsed.get("block"))
    if action in PRIVACY_HARD_BLOCK_ACTIONS:
        return True
    if action:
        return False
    return bool(parsed.get("block"))


def privacy_fields_from_parsed(
    parsed: dict[str, Any],
    *,
    family: str,
    allowed_fields: set[str],
) -> dict[str, Any]:
    is_privacy_guard = family == "privacy_boundary_guard"
    action = (
        normalize_privacy_action(parsed.get("privacy_action"))
        if is_privacy_guard and "privacy_action" in allowed_fields
        else ""
    )
    if is_privacy_guard and not action and bool(parsed.get("block")):
        action = "hard_block"
    allows_reason_codes = bool(
        {"privacy_reason_code", "privacy_reason_codes"} & allowed_fields
    )
    reason_codes = (
        clean_privacy_reason_codes(
            parsed.get("privacy_reason_codes")
            if "privacy_reason_codes" in parsed
            else parsed.get("privacy_reason_code")
        )
        if is_privacy_guard and allows_reason_codes
        else []
    )
    allows_external_projection = "raw_external_projection_allowed" in allowed_fields
    return {
        "block": privacy_block_value(parsed, family=family, action=action)
        if "block" in allowed_fields
        else False,
        "privacy_action": action,
        "privacy_reason_codes": reason_codes,
        "raw_external_projection_allowed": bool(parsed.get("raw_external_projection_allowed"))
        if action == "allow" and allows_external_projection
        else False,
    }


def empty_privacy_fields() -> dict[str, Any]:
    return {
        "privacy_action": "",
        "privacy_reason_codes": [],
        "raw_external_projection_allowed": False,
    }


def privacy_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    actions = unique_preserve(
        [
            str(row.get("privacy_action") or "")
            for row in rows
            if row.get("scout_family") == "privacy_boundary_guard" and row.get("privacy_action")
        ],
        limit=6,
    )
    reason_codes = unique_preserve(
        [
            str(code or "")
            for row in rows
            if row.get("scout_family") == "privacy_boundary_guard"
            for code in (row.get("privacy_reason_codes") or [])
        ],
        limit=12,
    )
    external_allowed = bool(actions) and all(
        bool(row.get("raw_external_projection_allowed"))
        for row in rows
        if row.get("scout_family") == "privacy_boundary_guard" and row.get("privacy_action")
    )
    return {
        "privacy_actions": actions,
        "privacy_reason_codes": reason_codes,
        "raw_external_projection_allowed": external_allowed,
    }


def merge_result(
    cards: list[dict[str, Any]],
    mode: str,
    confidence: str,
    negative_contexts: list[str],
    query_aliases: list[str],
    blocked_rows: list[dict[str, Any]],
    summary: dict[str, Any],
    calibration: dict[str, Any],
) -> dict[str, Any]:
    return {
        "cards": cards,
        "mode": mode,
        "confidence": confidence,
        "negative_contexts": unique_preserve(negative_contexts, limit=8),
        "query_aliases": unique_preserve(query_aliases, limit=16),
        "blocked_by": [row.get("scout") for row in blocked_rows],
        **summary,
        **calibration,
    }


def _dominant_privacy_route_action(actions: list[str]) -> str:
    route_actions = [action for action in actions if action in PRIVACY_ROUTE_ACTIONS]
    if not route_actions:
        return ""
    return max(route_actions, key=lambda action: PRIVACY_ROUTE_ACTION_PRIORITY.get(action, 0))


def apply_privacy_route_policy(
    cards: list[dict[str, Any]],
    summary: dict[str, Any],
) -> list[dict[str, Any]]:
    action = _dominant_privacy_route_action(list(summary.get("privacy_actions") or []))
    if not action:
        return cards
    reason_codes = list(summary.get("privacy_reason_codes") or [])
    annotated: list[dict[str, Any]] = []
    for card in cards:
        clean = dict(card)
        clean["privacy_action"] = action
        clean["privacy_reason_codes"] = reason_codes
        clean["raw_external_projection_allowed"] = False
        if clean.get("visibility") in {SOURCE_BACKED_RECALL_CARD, DEEP_ARCHIVAL_RECALL}:
            clean["visibility"] = ACTIVE_GENTLE_NUDGE
        clean["suggested_use"] = compact_text(
            " ".join(
                item
                for item in [
                    str(clean.get("suggested_use") or "").strip(),
                    "Keep this as a private route handle; reopen clean source before mentioning it.",
                ]
                if item
            ),
            220,
        )
        annotated.append(clean)
    return annotated
