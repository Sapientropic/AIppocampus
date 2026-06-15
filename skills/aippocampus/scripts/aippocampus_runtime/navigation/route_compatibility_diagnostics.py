"""Route-bundle compatibility inputs for attention routing.

The attention router should be able to notice that two plausible routes are in
tension, but that diagnostic is navigation context only. It can lower
confidence or ask for a cautious reopen; it must never create source truth,
erase fallback routes, or raise claim permission.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

SCHEMA_VERSION = 1
KIND = "aippocampus_route_bundle_compatibility"
COMPATIBLE = "compatible"
TENSION = "tension"
OBSTRUCTION = "obstruction"
BLOCKED_BOUNDARY = "blocked_boundary"
STATUS_SEVERITY = {
    COMPATIBLE: 0,
    TENSION: 1,
    OBSTRUCTION: 2,
    BLOCKED_BOUNDARY: 3,
}
LOCAL_GLOBAL_RESULT_STATUS = {
    "glued_route": COMPATIBLE,
    "compatible": COMPATIBLE,
    "partial_glue": TENSION,
    "tension": TENSION,
    "obstruction": OBSTRUCTION,
    "blocked_boundary": BLOCKED_BOUNDARY,
}


def _text(value: Any, *, default: str = "") -> str:
    text = str(value or "").strip()
    return text or default


def _safe_label(value: Any, *, fallback: str = "") -> str:
    text = _text(value).casefold()
    if text and len(text) <= 96 and all(char.isalnum() or char in "-_.:#" for char in text):
        return text
    return fallback


def _safe_route_id(value: Any) -> str:
    text = _text(value)
    if text and len(text) <= 120 and all(char.isalnum() or char in "-_.:#" for char in text):
        return text
    return ""


def _strings(value: Any, *, limit: int = 8) -> list[str]:
    raw_items: Sequence[Any]
    if isinstance(value, str):
        raw_items = [value]
    elif isinstance(value, Sequence):
        raw_items = value
    else:
        return []
    result: list[str] = []
    seen: set[str] = set()
    for item in raw_items:
        text = _safe_label(item)
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
        if len(result) >= limit:
            break
    return result


def _route_ids_from_row(row: Mapping[str, Any]) -> list[str]:
    ids = _strings(row.get("route_ids") or row.get("related_route_ids"), limit=6)
    for key in ("route_id", "from_route_id", "to_route_id", "candidate_route_id"):
        route_id = _safe_route_id(row.get(key))
        if route_id and route_id not in ids:
            ids.append(route_id)
    return ids[:6]


def status_from_result(value: Any) -> str:
    label = _safe_label(value, fallback=OBSTRUCTION)
    return LOCAL_GLOBAL_RESULT_STATUS.get(label, OBSTRUCTION)


def normalize_compatibility_row(row: Mapping[str, Any]) -> dict[str, Any] | None:
    """Return a compact public-safe compatibility row, or None if unaddressed."""

    route_ids = _route_ids_from_row(row)
    if not route_ids:
        return None
    status = status_from_result(row.get("status") or row.get("result"))
    reason_codes = _strings(row.get("reason_codes"), limit=8)
    if not reason_codes:
        reason_codes = ["route_bundle_compatibility_diagnostic"]
    return {
        "kind": KIND,
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "severity": STATUS_SEVERITY[status],
        "route_ids": route_ids,
        "reason_codes": reason_codes,
        "next_safe_action": _safe_label(
            row.get("next_safe_action") or row.get("recommended_next"),
            fallback="cautious_source_reopen",
        ),
        "authority_level": "navigation_only",
        "claim_permission": "no_claim_before_reopen",
        "source_reopen_required_before_claim": True,
    }


def _rows_from_route(route: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    rows: list[Mapping[str, Any]] = []
    for key in ("compatibility_diagnostics", "route_bundle_compatibility"):
        value = route.get(key)
        if isinstance(value, Mapping):
            rows.append({**value, "route_id": value.get("route_id") or route.get("route_id")})
        elif isinstance(value, Sequence) and not isinstance(value, str):
            for item in value:
                if isinstance(item, Mapping):
                    rows.append({**item, "route_id": item.get("route_id") or route.get("route_id")})
    hints = route.get("route_hints")
    if isinstance(hints, Mapping):
        family = hints.get("local_global_compatibility")
        if isinstance(family, Mapping):
            rows.append({**family, "route_id": family.get("route_id") or route.get("route_id")})
    return rows


def normalize_compatibility_rows(
    routes: Sequence[Mapping[str, Any]],
    rows: Sequence[Mapping[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Normalize explicit route-bundle compatibility diagnostics.

    The foreground router consumes this as an already-derived diagnostic. It
    deliberately does not infer facts from raw source text or perform broad
    pairwise graph construction in the hot path.
    """

    raw_rows: list[Mapping[str, Any]] = list(rows or [])
    if rows is None:
        for route in routes:
            raw_rows.extend(_rows_from_route(route))
    normalized: list[dict[str, Any]] = []
    seen: set[tuple[str, tuple[str, ...], tuple[str, ...]]] = set()
    for row in raw_rows:
        item = normalize_compatibility_row(row)
        if item is None:
            continue
        key = (
            item["status"],
            tuple(item["route_ids"]),
            tuple(item["reason_codes"]),
        )
        if key in seen:
            continue
        seen.add(key)
        normalized.append(item)
    return normalized


def compatibility_by_route_id(
    routes: Sequence[Mapping[str, Any]],
    rows: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, dict[str, Any]]:
    normalized = normalize_compatibility_rows(routes, rows)
    by_route: dict[str, dict[str, Any]] = {}
    for row in normalized:
        for route_id in row["route_ids"]:
            current = by_route.get(route_id)
            if current is None or row["severity"] > current["severity"]:
                by_route[route_id] = {
                    "status": row["status"],
                    "severity": row["severity"],
                    "reason_codes": list(row["reason_codes"]),
                    "related_route_ids": [
                        item for item in row["route_ids"] if item != route_id
                    ][:5],
                    "next_safe_action": row["next_safe_action"],
                    "authority_level": "navigation_only",
                    "claim_permission": "no_claim_before_reopen",
                    "source_reopen_required_before_claim": True,
                }
                continue
            for reason in row["reason_codes"]:
                if reason not in current["reason_codes"]:
                    current["reason_codes"].append(reason)
            for related in row["route_ids"]:
                if related != route_id and related not in current["related_route_ids"]:
                    current["related_route_ids"].append(related)
            current["reason_codes"] = current["reason_codes"][:8]
            current["related_route_ids"] = current["related_route_ids"][:5]
    return by_route


def public_route_compatibility(value: Mapping[str, Any] | None) -> dict[str, Any]:
    if not value:
        return {}
    status = status_from_result(value.get("status"))
    return {
        "status": status,
        "severity": STATUS_SEVERITY[status],
        "reason_codes": _strings(value.get("reason_codes"), limit=6),
        "related_route_ids": _strings(value.get("related_route_ids"), limit=5),
        "next_safe_action": _safe_label(
            value.get("next_safe_action"),
            fallback="cautious_source_reopen",
        ),
        "authority_level": "navigation_only",
        "claim_permission": "no_claim_before_reopen",
        "source_reopen_required_before_claim": True,
    }


def report_for_routes(
    routes: Sequence[Mapping[str, Any]],
    rows: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    normalized = normalize_compatibility_rows(routes, rows)
    by_route = compatibility_by_route_id(routes, rows)
    return {
        "kind": "aippocampus_route_bundle_compatibility_report",
        "schema_version": SCHEMA_VERSION,
        "ok": True,
        "diagnostic_count": len(normalized),
        "affected_route_count": len(by_route),
        "diagnostics": normalized,
        "boundary": {
            "navigation_diagnostic_only": True,
            "does_not_create_source_truth": True,
            "does_not_raise_claim_permission": True,
            "fallback_routes_preserved": True,
        },
    }


__all__ = [
    "BLOCKED_BOUNDARY",
    "COMPATIBLE",
    "OBSTRUCTION",
    "TENSION",
    "compatibility_by_route_id",
    "normalize_compatibility_rows",
    "public_route_compatibility",
    "report_for_routes",
    "status_from_result",
]
