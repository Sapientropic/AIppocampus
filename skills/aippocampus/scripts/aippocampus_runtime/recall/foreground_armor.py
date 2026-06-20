"""Foreground armor budgets for compact agent-facing memory surfaces."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

SCHEMA_VERSION = 1

COMPACT_ARMOR_BUDGET = {
    "visible_boundary_item_max": 2,
    "visible_reopen_prompt_max": 2,
    "cannot_claim_visible": False,
    "minimum_guidance_signal_count": 2,
}


def foreground_armor_budget(profile: str = "compact") -> dict[str, Any]:
    if profile != "compact":
        return {
            "profile": profile,
            "visible_boundary_item_max": 8,
            "visible_reopen_prompt_max": 6,
            "cannot_claim_visible": True,
            "minimum_guidance_signal_count": 0,
        }
    return {"profile": "compact", **COMPACT_ARMOR_BUDGET}


def compact_surface_armor_report(
    packet: Mapping[str, Any],
    *,
    surface: str,
    profile: str = "compact",
) -> dict[str, Any]:
    """Audit whether a compact packet is useful guidance or defensive armor."""

    budget = foreground_armor_budget(profile)
    encoded = json.dumps(packet, ensure_ascii=False, sort_keys=True).casefold()
    boundary_count = _visible_boundary_count(packet)
    reopen_count = encoded.count("reopen") + encoded.count("source_reopen")
    cannot_claim_visible = '"cannot_claim"' in encoded
    guidance_count = _guidance_signal_count(packet)
    red_lines = {
        "visible_boundary_item_budget_violation": int(
            boundary_count > budget["visible_boundary_item_max"]
        ),
        "visible_reopen_prompt_budget_violation": int(
            reopen_count > budget["visible_reopen_prompt_max"]
        ),
        "cannot_claim_visible_in_compact": int(
            cannot_claim_visible and not budget["cannot_claim_visible"]
        ),
        "guidance_signal_deficit": int(
            guidance_count < budget["minimum_guidance_signal_count"]
        ),
    }
    return {
        "kind": "aippocampus_foreground_armor_budget_report",
        "schema_version": SCHEMA_VERSION,
        "surface": surface,
        "profile": profile,
        "ok": all(value == 0 for value in red_lines.values()),
        "metrics": {
            "visible_boundary_item_count": boundary_count,
            "visible_reopen_prompt_count": reopen_count,
            "cannot_claim_visible": cannot_claim_visible,
            "guidance_signal_count": guidance_count,
        },
        "budget": budget,
        "red_lines": red_lines,
        "detail_profile": "explain/deepen/diagnostics may retain full source boundary fields",
    }


def _visible_boundary_count(packet: Mapping[str, Any]) -> int:
    boundary_keys = {
        "claim_boundary",
        "claim_permission",
        "cannot_claim",
        "must_reopen",
        "no_claim_before_reopen",
        "source_reopen_required",
        "source_reopen_required_before_claim",
    }
    count = 0
    for key, value in _walk(packet):
        key_text = str(key or "").casefold()
        value_text = str(value or "").casefold()
        if key_text in boundary_keys or any(marker in value_text for marker in boundary_keys):
            count += 1
    return count


def _guidance_signal_count(packet: Mapping[str, Any]) -> int:
    guidance_keys = {
        "situation",
        "frontier",
        "load_bearing_unknown",
        "unknown",
        "next_action",
        "next_step",
        "display_hint",
        "why_may_matter",
        "route_label",
        "working_orientation",
    }
    count = 0
    for key, value in _walk(packet):
        if str(key or "").casefold() in guidance_keys and str(value or "").strip():
            count += 1
    return count


def _walk(value: Any) -> list[tuple[str, Any]]:
    rows: list[tuple[str, Any]] = []
    if isinstance(value, Mapping):
        for key, item in value.items():
            rows.append((str(key), item))
            rows.extend(_walk(item))
    elif isinstance(value, list):
        for item in value:
            rows.extend(_walk(item))
    return rows
