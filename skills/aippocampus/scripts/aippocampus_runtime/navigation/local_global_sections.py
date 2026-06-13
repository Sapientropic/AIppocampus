#!/usr/bin/env python3
"""Typed Section, restriction, and adjudication helpers.

These helpers keep local/global compatibility's object language small and
navigation-only. Restriction may narrow a diagnostic scope, but it must never
raise authority, privacy access, claim permission, or source support.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

SECTION_CONTRACT_VERSION = 1
ADJUDICATION_REPORT_KIND = "aippocampus_local_global_adjudication_report"
V0_SHI_YING_POLICY = "v0_project_scoped_navigation_hint"

RESTRICTION_POLICY: dict[str, Any] = {
    "transitive": True,
    "order_preserving": True,
    "may_raise_authority": False,
    "may_raise_claim_permission": False,
    "may_raise_privacy_access": False,
    "may_raise_source_support": False,
    "may_change_source_truth": False,
    "classical_bagua_positions_enabled": False,
    "shi_ying_restriction_edge_policy": V0_SHI_YING_POLICY,
}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _label(value: Any, *, fallback: str = "") -> str:
    text = _text(value).casefold()
    return text if text and all(char.isalnum() or char in "-_.:#" for char in text) else fallback


def _safe_scope(value: Any) -> str:
    text = _text(value)
    if (
        text
        and len(text) <= 120
        and not any(marker in text for marker in ("source://private", "\\", "/", ":\\"))
        and all(char.isalnum() or char in "-_.:#" for char in text)
    ):
        return text
    return ""


def _safe_time_value(value: Any) -> str:
    text = _text(value)
    if len(text) <= 40 and all(char.isalnum() or char in "-_:.+TZ" for char in text):
        return text
    return ""


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: Any) -> Sequence[Any]:
    return value if isinstance(value, Sequence) and not isinstance(value, (str, bytes)) else ()


def _safe_time_window(value: Any) -> dict[str, str]:
    raw = _mapping(value)
    start = _safe_time_value(raw.get("start"))
    end = _safe_time_value(raw.get("end"))
    out: dict[str, str] = {}
    if start:
        out["start"] = start
    if end:
        out["end"] = end
    return out


def restriction_path_from_row(row: Mapping[str, Any], *, scope: str) -> list[str]:
    raw_path = _sequence(row.get("restriction_path") or row.get("restriction_scopes"))
    path = [_safe_scope(item) for item in raw_path]
    path = [item for item in path if item]
    if path:
        return path[:8]
    return [scope] if scope else []


def time_semantics_from_row(row: Mapping[str, Any]) -> dict[str, Any]:
    coverage = _safe_time_window(row.get("source_coverage_time") or row.get("section_time_window"))
    validity = {
        key: _safe_time_value(row.get(key))
        for key in ("valid_after", "valid_until", "review_after")
        if _safe_time_value(row.get(key))
    }
    return {
        "source_coverage_time": coverage,
        "packet_created_at": _safe_time_value(
            row.get("packet_created_at") or row.get("created_at") or row.get("materialized_at")
        ),
        "validity_window": validity,
        "source_coverage_time_required_for_exact_glue": True,
    }


def relation_position_edges(row: Mapping[str, Any]) -> list[str]:
    relation = _mapping(row.get("relation_position"))
    encoded = json.dumps(relation, ensure_ascii=False, sort_keys=True)
    if "世" in encoded or "应" in encoded or "shi" in encoded.casefold() or "ying" in encoded.casefold():
        return ["shi_ying_v0_project_role_hint"]
    return []


def attach_section_contract(section: dict[str, Any], row: Mapping[str, Any]) -> dict[str, Any]:
    scope = str(section.get("scope") or "")
    time_semantics = time_semantics_from_row(row)
    section["section_contract_version"] = SECTION_CONTRACT_VERSION
    section["restriction_path"] = restriction_path_from_row(row, scope=scope)
    section["time_semantics"] = time_semantics
    section["relation_position_edges"] = relation_position_edges(row)
    section["explicit_obstruction_kind"] = _label(row.get("obstruction_kind"), fallback="")
    return section


def section_contracts(sections: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    contracts: list[dict[str, Any]] = []
    for section in sections:
        contracts.append(
            {
                "section_contract_version": SECTION_CONTRACT_VERSION,
                "section_id": section.get("section_id"),
                "section_kind": section.get("section_kind"),
                "scope": section.get("scope"),
                "restriction_path": list(_sequence(section.get("restriction_path"))),
                "time_semantics": dict(_mapping(section.get("time_semantics"))),
                "authority_level": section.get("authority_level"),
                "claim_permission": section.get("claim_permission"),
                "privacy_domain": section.get("privacy_domain"),
                "source_count": section.get("source_count"),
            }
        )
    return contracts


def source_coverage_time_overlap(sections: Sequence[Mapping[str, Any]]) -> bool:
    windows: list[tuple[str, str]] = []
    for section in sections:
        semantics = _mapping(section.get("time_semantics"))
        window = _mapping(semantics.get("source_coverage_time"))
        start = _safe_time_value(window.get("start"))
        end = _safe_time_value(window.get("end"))
        if start and end:
            windows.append((start, end))
    if len(windows) < 2:
        return True
    latest_start = max(start for start, _ in windows)
    earliest_end = min(end for _, end in windows)
    return latest_start <= earliest_end


def common_restriction_scope(sections: Sequence[Mapping[str, Any]]) -> str:
    paths = [
        [str(item) for item in _sequence(section.get("restriction_path")) if _safe_scope(item)]
        for section in sections
    ]
    paths = [path for path in paths if path]
    if len(paths) < 2:
        return ""
    common = set(paths[0])
    for path in paths[1:]:
        common &= set(path)
    if not common:
        return ""
    for item in reversed(paths[0]):
        if item in common:
            return item
    return ""


def restriction_edges(sections: Sequence[Mapping[str, Any]]) -> list[str]:
    edges: list[str] = []
    for section in sections:
        for edge in _sequence(section.get("relation_position_edges")):
            edge_text = _label(edge)
            if edge_text and edge_text not in edges:
                edges.append(edge_text)
    return edges


def restriction_narrowing_diagnostic(
    sections: Sequence[Mapping[str, Any]],
    *,
    source_overlap_count: int,
    scope_overlap: bool,
    blocked: bool,
    stale: bool,
) -> dict[str, Any]:
    common_scope = common_restriction_scope(sections)
    if blocked:
        narrowed = "not_attempted"
        reason = "privacy_or_blocked_boundary_is_not_narrowable"
    elif stale:
        narrowed = "not_attempted"
        reason = "stale_boundary_requires_source_review_before_narrowing"
    elif scope_overlap:
        narrowed = "not_needed"
        reason = "already_same_scope"
    elif common_scope and source_overlap_count > 0:
        narrowed = "glued_route"
        reason = "common_restriction_scope_preserves_source_overlap"
    else:
        narrowed = "not_glued"
        reason = "no_safe_common_restriction_scope"
    return {
        "broad_result": "obstruction" if narrowed == "glued_route" else "not_glued",
        "narrowed_result": narrowed,
        "narrowed_scope": common_scope,
        "attempted_scope_count": len(
            {scope for section in sections for scope in _sequence(section.get("restriction_path"))}
        ),
        "reason_codes": [reason],
        "raises_authority": False,
        "raises_claim_permission": False,
        "raises_privacy_access": False,
        "raises_source_support": False,
    }


def topology_shape(sections: Sequence[Mapping[str, Any]]) -> str:
    for section in sections:
        shape = _label(section.get("shape"), fallback="")
        if shape:
            return shape
    return "none"


def explicit_obstruction_kind(sections: Sequence[Mapping[str, Any]]) -> str:
    for section in sections:
        kind = _label(section.get("explicit_obstruction_kind"), fallback="")
        if kind:
            return kind
    return ""


def obstruction_kind_for(
    *,
    result: str,
    reason_codes: Sequence[str],
    explicit_kind: str,
    blocked: bool,
) -> str:
    reasons = set(reason_codes)
    if explicit_kind:
        return explicit_kind
    if "authority_or_claim_permission_upgrade_attempt" in reasons:
        return "authority_boundary"
    if blocked:
        return "privacy_boundary"
    if "stale_or_released_section_blocks_current_glue" in reasons:
        return "stale_boundary"
    if "source_coverage_time_mismatch_blocks_glue" in reasons:
        return "time_window_mismatch"
    if "shared_vocabulary_without_source_scope_support" in reasons or "missing_source_and_scope_overlap" in reasons:
        return "missing_middle"
    if "no_safe_common_restriction_scope" in reasons:
        return "agent_scope_split"
    if result == "glued_route":
        return "none"
    return "restriction_review"


def build_local_global_adjudication_report(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    safe_rows: list[dict[str, str]] = []
    for index, row in enumerate(rows):
        label = _label(row.get("adjudication_label"), fallback="ambiguous_correlation")
        result = _label(row.get("diagnostic_result"), fallback="unknown")
        safe_rows.append(
            {
                "case_id": _label(row.get("case_id"), fallback=f"case_{index}"),
                "diagnostic_result": result,
                "adjudication_label": label,
            }
        )
    counts = Counter(row["adjudication_label"] for row in safe_rows)
    return {
        "kind": ADJUDICATION_REPORT_KIND,
        "schema_version": 1,
        "rows": safe_rows,
        "metrics": {
            "case_count": len(safe_rows),
            "useful_obstruction_later_used_count": counts["useful_obstruction"],
            "false_glue_regression_count": counts["false_glue"],
            "no_help_count": counts["no_help"],
            "ambiguous_correlation_only_count": counts["ambiguous_correlation"],
        },
        "claims": {
            "live_product_lift_claimed": False,
            "causality_claimed_from_correlation": False,
            "diagnostic_counts_are_product_lift": False,
        },
    }
