#!/usr/bin/env python3
"""Local/global route-section compatibility diagnostics.

This helper answers a narrow diagnostic question: can packet-shaped local
sections be viewed together as a route, a partial route, an obstruction, or a
blocked boundary without raising their authority?  It is deliberately an
explain/deepen/Campus surface.  A successful glue result is still navigation,
not evidence, and failed glue is an obstruction to inspect rather than an
instruction to act.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from aippocampus_runtime.navigation import (
    local_global_fixture_catalog,
    local_global_sections,
    scope_equivalence,
)

SCHEMA_VERSION = 1
REPORT_KIND = "aippocampus_local_global_compatibility_report"
ROW_KIND = "aippocampus_local_global_compatibility_row"
SURFACE = "explain_deepen_or_campus_first"
GLUED_ROUTE = "glued_route"
PARTIAL_GLUE = "partial_glue"
OBSTRUCTION = "obstruction"
BLOCKED_BOUNDARY = "blocked_boundary"
RESULTS = {GLUED_ROUTE, PARTIAL_GLUE, OBSTRUCTION, BLOCKED_BOUNDARY}
FORBIDDEN_MARKERS = (
    "PRIVATE_LOCAL_GLOBAL_TEXT",
    "raw_private_source_text",
    "source://private",
    "C:\\",
    "/Users/",
)
BLOCKING_FLAGS = {
    "no_private_source",
    "privacy_blocked",
    "no_shared_chain_of_thought",
    "no_shared_cot",
    "ignore_or_blocked",
}
STALE_STATUSES = {"stale", "released", "retired", "challenged", "rejected"}
AUTHORITY_RANK = {
    "ignore_or_blocked": 0,
    "candidate_only": 1,
    "dream_synthesized_candidate_not_fact": 1,
    "candidate_not_fact": 1,
    "navigation_only": 2,
    "direction_only": 2,
    "reopenable_route": 2,
    "bounded_evidence": 3,
    "source_open": 4,
    "source_supported": 4,
}
CLAIM_RANK = {
    "no_claim_before_reopen": 0,
    "navigation_only_not_fact": 1,
    "working_contract_allowed_no_fact_claim": 1,
    "bounded_claim_allowed": 2,
    "source_open": 3,
}


def stable_hash(*parts: Any, length: int = 16) -> str:
    digest = hashlib.sha256(
        "\u241f".join(str(part) for part in parts).encode("utf-8", errors="replace")
    ).hexdigest()
    return digest[:length]


def _text(value: Any) -> str:
    return str(value or "").strip()


def _label(value: Any, *, fallback: str = "") -> str:
    text = _text(value).casefold()
    return text if text and all(char.isalnum() or char in "-_.:#" for char in text) else fallback


def _safe_id(value: Any, *, prefix: str) -> str:
    text = _text(value)
    if (
        text
        and len(text) <= 96
        and not any(marker in text for marker in ("source://private", "\\", "/", ":\\"))
        and all(char.isalnum() or char in "-_.:#" for char in text)
    ):
        return text
    return f"{prefix}_{stable_hash(text or prefix, length=12)}"


def _safe_scope(value: Any) -> str:
    text = _text(value)
    if (
        text
        and len(text) <= 120
        and not any(marker in text for marker in ("source://private", "\\", "/", ":\\"))
        and all(char.isalnum() or char in "-_.:#" for char in text)
    ):
        return text
    return "scope_" + stable_hash(text or "missing_scope", length=12)


def _strings(value: Any, *, limit: int = 12) -> list[str]:
    raw_items: Sequence[Any]
    if isinstance(value, str):
        raw_items = [value]
    elif isinstance(value, Sequence):
        raw_items = value
    else:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in raw_items:
        if isinstance(item, Mapping):
            text = _text(
                item.get("source_id")
                or item.get("source_ref")
                or item.get("id")
                or item.get("ref")
            )
        else:
            text = _text(item)
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
        if len(out) >= limit:
            break
    return out


def _safe_source_id(value: Any) -> str | None:
    text = _text(value)
    if (
        text
        and len(text) <= 96
        and not any(marker in text for marker in ("source://private", "\\", "/", ":\\"))
        and all(char.isalnum() or char in "-_.:#" for char in text)
    ):
        return text
    return None


def _source_ids(row: Mapping[str, Any]) -> list[str]:
    values: list[str] = []
    for key in (
        "source_ids",
        "source_refs",
        "source_ref_ids",
        "source_anchors",
        "source_event_refs",
        "source_handles",
    ):
        for item in _strings(row.get(key), limit=16):
            source_id = _safe_source_id(item)
            if source_id and source_id not in values:
                values.append(source_id)
    for key in ("route_id", "deepen_route_id"):
        source_id = _safe_source_id(row.get(key))
        if source_id and source_id not in values:
            values.append(source_id)
    return values[:12]


def _section_kind(row: Mapping[str, Any]) -> str:
    return _label(
        row.get("local_section_kind") or row.get("kind") or row.get("packet_type"),
        fallback="local_section",
    )


def _authority_label(row: Mapping[str, Any]) -> str:
    support = row.get("source_support") or row.get("support_grade") or row.get("support")
    authority = row.get("authority_level") or row.get("authority") or support
    label = _label(authority, fallback="navigation_only")
    if label == "source_supported":
        return "source_open"
    if label == "dream_synthesized_candidate_not_fact":
        return label
    if label in AUTHORITY_RANK:
        return label
    return "navigation_only"


def _claim_label(row: Mapping[str, Any]) -> str:
    label = _label(row.get("claim_permission"), fallback="navigation_only_not_fact")
    return label if label in CLAIM_RANK else "navigation_only_not_fact"


def _lowest_authority(sections: Sequence[Mapping[str, Any]]) -> str:
    labels = [_authority_label(section) for section in sections]
    return min(labels, key=lambda item: AUTHORITY_RANK.get(item, 2)) if labels else "navigation_only"


def _requested_claim_rank(row: Mapping[str, Any]) -> int:
    requested = _label(row.get("requested_claim_permission"))
    if not requested:
        return -1
    return CLAIM_RANK.get(requested, CLAIM_RANK["source_open"])


def _privacy_domain(row: Mapping[str, Any]) -> str:
    domain = _label(row.get("privacy_domain"), fallback="")
    if domain in {"private", "restricted", "personal", "blocked"}:
        return domain
    if domain in {"public", "public_safe_fixture", "synthetic", "project"}:
        return "public"
    return "public"


def _boundary_flags(row: Mapping[str, Any]) -> list[str]:
    flags = [_label(item) for item in _strings(row.get("boundary_flags"), limit=12)]
    status = _label(row.get("status"))
    source_support = _label(row.get("source_support") or row.get("support"))
    if status == "blocked":
        flags.append("privacy_blocked" if _privacy_domain(row) != "public" else "blocked")
    if source_support == "ignore_or_blocked":
        flags.append("ignore_or_blocked")
    return sorted({flag for flag in flags if flag})


def _topic_tokens(row: Mapping[str, Any]) -> set[str]:
    text = " ".join(
        _text(row.get(key))
        for key in ("route_topic", "topic", "title", "display_hint")
        if _text(row.get(key))
    )
    return {
        token
        for token in text.casefold().replace("-", " ").replace("_", " ").split()
        if len(token) > 2
    }


def normalize_local_section(row: Mapping[str, Any]) -> dict[str, Any]:
    kind = _section_kind(row)
    source_ids = _source_ids(row)
    status = _label(row.get("status") or row.get("route_state") or row.get("lifecycle_status"))
    raw_scope = row.get("scope") or row.get("scope_id") or row.get("route_scope")
    section = {
        "section_id": _safe_id(
            row.get("case_id") or row.get("packet_id") or row.get("candidate_id") or kind,
            prefix="section",
        ),
        "section_kind": kind,
        "scope": _safe_scope(raw_scope),
        "scope_missing": not bool(_text(raw_scope)),
        "topic_epoch": _safe_id(row.get("topic_epoch") or row.get("epoch") or "current", prefix="epoch"),
        "privacy_domain": _privacy_domain(row),
        "authority_level": _authority_label(row),
        "claim_permission": _claim_label(row),
        "requested_claim_permission_rank": _requested_claim_rank(row),
        "source_ids": source_ids,
        "source_count": len(source_ids),
        "boundary_flags": _boundary_flags(row),
        "status": status or "current",
        "freshness": _label(row.get("freshness"), fallback="current"),
        "shape": _label(row.get("shape"), fallback=""),
        "topic_tokens": sorted(_topic_tokens(row)),
        "source_reopen_required_before_claim": True,
    }
    section["scope_identity"] = scope_equivalence.scope_identity_from_row(
        row,
        scope=str(section["scope"]),
    )
    return local_global_sections.attach_section_contract(section, row)


def _has_blocked_boundary(sections: Sequence[Mapping[str, Any]]) -> bool:
    domains = {section["privacy_domain"] for section in sections}
    if "private" in domains and len(domains) > 1:
        return True
    return any(
        section["privacy_domain"] in {"private", "restricted", "personal", "blocked"}
        or bool(set(section["boundary_flags"]) & BLOCKING_FLAGS)
        or section["status"] == "blocked"
        for section in sections
    )


def _is_stale_obstruction(section: Mapping[str, Any]) -> bool:
    return section["status"] in STALE_STATUSES or section["freshness"] in STALE_STATUSES


def _source_overlap(sections: Sequence[Mapping[str, Any]]) -> set[str]:
    source_sets = [set(section["source_ids"]) for section in sections if section["source_ids"]]
    if len(source_sets) < 2:
        return set()
    overlap = set(source_sets[0])
    for source_set in source_sets[1:]:
        overlap &= source_set
    return overlap


def _any_source_support(sections: Sequence[Mapping[str, Any]]) -> bool:
    return any(section["source_count"] > 0 for section in sections)


def _scope_overlap(sections: Sequence[Mapping[str, Any]]) -> bool:
    return bool(scope_equivalence.scope_match_diagnostic(sections)["matched"])


def _topic_epoch_overlap(sections: Sequence[Mapping[str, Any]]) -> bool:
    epochs = {section["topic_epoch"] for section in sections if section["topic_epoch"]}
    return len(epochs) <= 1


def _shared_vocabulary(sections: Sequence[Mapping[str, Any]]) -> bool:
    token_sets = [set(section["topic_tokens"]) for section in sections if section["topic_tokens"]]
    if len(token_sets) < 2:
        return False
    shared = set(token_sets[0])
    for token_set in token_sets[1:]:
        shared &= token_set
    return bool(shared)


def _authority_upgrade_attempt(sections: Sequence[Mapping[str, Any]]) -> bool:
    claim_ceiling = min(
        CLAIM_RANK.get(section["claim_permission"], 1) for section in sections
    )
    return any(
        section["requested_claim_permission_rank"] >= 0
        and section["requested_claim_permission_rank"] > claim_ceiling
        for section in sections
    )


def _result_and_reasons(
    sections: Sequence[Mapping[str, Any]],
    *,
    source_overlap: set[str],
    scope_match: Mapping[str, Any],
    shared_vocabulary: bool,
    source_coverage_time_overlap: bool,
) -> tuple[str, list[str], str]:
    reasons: list[str] = []
    scope_overlap = bool(scope_match.get("matched"))
    scope_reason = _label(scope_match.get("reason_code"), fallback="")
    if _authority_upgrade_attempt(sections):
        return BLOCKED_BOUNDARY, ["authority_or_claim_permission_upgrade_attempt"], "do_not_cross_boundary"
    if _has_blocked_boundary(sections):
        return BLOCKED_BOUNDARY, ["privacy_or_boundary_flag_blocks_glue"], "do_not_cross_boundary"
    if any(_is_stale_obstruction(section) for section in sections):
        return OBSTRUCTION, ["stale_or_released_section_blocks_current_glue"], "review_obstruction_before_action"
    if not source_coverage_time_overlap:
        return OBSTRUCTION, ["source_coverage_time_mismatch_blocks_glue"], "review_obstruction_before_action"
    explicit_kind = local_global_sections.explicit_obstruction_kind(sections)
    if explicit_kind:
        return OBSTRUCTION, [f"{explicit_kind}_obstruction"], "review_obstruction_before_action"
    if source_overlap and scope_overlap and _topic_epoch_overlap(sections):
        reason = (
            "source_scope_and_epoch_overlap"
            if scope_match.get("match_kind") == "exact"
            else scope_reason or "normalized_scope_and_epoch_overlap"
        )
        return GLUED_ROUTE, [reason], "deepen_compatible_route"
    if scope_overlap and _any_source_support(sections):
        reason = (
            "scope_overlap_without_full_source_overlap"
            if scope_match.get("match_kind") == "exact"
            else scope_reason or "normalized_scope_without_full_source_overlap"
        )
        return PARTIAL_GLUE, [reason], "deepen_each_section_before_use"
    if source_overlap and local_global_sections.common_restriction_scope(sections):
        return PARTIAL_GLUE, ["narrowed_restriction_preserves_source_overlap"], "deepen_narrowed_scope_before_use"
    if _any_source_support(sections):
        return OBSTRUCTION, [
            "source_supported_sections_need_scope_review",
            "no_safe_common_restriction_scope",
        ], "review_obstruction_before_action"
    if shared_vocabulary:
        reasons.append("shared_vocabulary_without_source_scope_support")
    if not reasons:
        reasons.append("missing_source_and_scope_overlap")
    return OBSTRUCTION, reasons, "review_obstruction_before_action"


def evaluate_local_global_compatibility(
    sections: Sequence[Mapping[str, Any]],
    *,
    case_id: str = "local_global_case",
) -> dict[str, Any]:
    normalized = [normalize_local_section(section) for section in sections if isinstance(section, Mapping)]
    source_overlap = _source_overlap(normalized)
    scope_match = scope_equivalence.scope_match_diagnostic(normalized)
    scope_overlap = bool(scope_match["matched"])
    shared_vocabulary = _shared_vocabulary(normalized)
    time_overlap = local_global_sections.source_coverage_time_overlap(normalized)
    result, reasons, next_action = _result_and_reasons(
        normalized,
        source_overlap=source_overlap,
        scope_match=scope_match,
        shared_vocabulary=shared_vocabulary,
        source_coverage_time_overlap=time_overlap,
    )
    narrowing = local_global_sections.restriction_narrowing_diagnostic(
        normalized,
        source_overlap_count=len(source_overlap),
        scope_overlap=scope_overlap,
        blocked=_has_blocked_boundary(normalized),
        stale=any(_is_stale_obstruction(section) for section in normalized),
    )
    for reason in narrowing["reason_codes"]:
        if (
            reason
            and reason not in reasons
            and narrowing["narrowed_result"] in {"glued_route", "not_glued"}
        ):
            reasons.append(reason)
    section_kinds = sorted({section["section_kind"] for section in normalized})
    obstruction_kind = local_global_sections.obstruction_kind_for(
        result=result,
        reason_codes=reasons,
        explicit_kind=local_global_sections.explicit_obstruction_kind(normalized),
        blocked=_has_blocked_boundary(normalized),
    )
    return {
        "kind": ROW_KIND,
        "schema_version": SCHEMA_VERSION,
        "case_id": _safe_id(case_id, prefix="case"),
        "result": result,
        "section_count": len(normalized),
        "section_kinds": section_kinds,
        "section_contracts": local_global_sections.section_contracts(normalized),
        "restriction_policy": dict(local_global_sections.RESTRICTION_POLICY),
        "restriction_edges": local_global_sections.restriction_edges(normalized),
        "restriction_narrowing": narrowing,
        "topology_shape": local_global_sections.topology_shape(normalized),
        "obstruction_kind": obstruction_kind,
        "overlap_basis": {
            "source_overlap_count": len(source_overlap),
            "scope_overlap": scope_overlap,
            "scope_match_kind": scope_match["match_kind"],
            "scope_match_reason_code": scope_match["reason_code"],
            "common_scope_id": scope_match["common_scope"],
            "topic_epoch_overlap": _topic_epoch_overlap(normalized),
            "source_coverage_time_overlap": time_overlap,
            "privacy_domain_compatible": not _has_blocked_boundary(normalized),
            "authority_ceiling": _lowest_authority(normalized),
            "claim_permission_ceiling": "navigation_only_not_fact",
            "freshness_current": not any(_is_stale_obstruction(section) for section in normalized),
            "shared_vocabulary_present": shared_vocabulary,
            "shared_vocabulary_counts_as_overlap": False,
        },
        "reason_codes": reasons,
        "claim_permission": "navigation_only_not_fact",
        "authority_level": "navigation_only",
        "source_reopen_required_before_claim": True,
        "foreground_projection_allowed": False,
        "full_diagnostic_surface": "explain_debug_or_campus",
        "glue_never_upgrades_authority": True,
        "failed_glue_is_obstruction_not_assignment": True,
        "next_safe_action": next_action,
    }


def build_local_global_adjudication_report(
    rows: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    return local_global_sections.build_local_global_adjudication_report(rows)


def build_local_global_compatibility_report(
    rows: Iterable[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    if rows is None:
        compatibility_rows = [
            evaluate_local_global_compatibility(sections, case_id=case_id)
            for case_id, sections in local_global_fixture_catalog.fixture_compatibility_cases()
        ]
    else:
        compatibility_rows = [
            evaluate_local_global_compatibility(list(rows), case_id="input_sections")
        ]
    counts: Counter[str] = Counter(row["result"] for row in compatibility_rows)
    reason_counts: Counter[str] = Counter(
        reason for row in compatibility_rows for reason in row["reason_codes"]
    )
    obstruction_kind_counts: Counter[str] = Counter(
        row["obstruction_kind"] for row in compatibility_rows if row["obstruction_kind"] != "none"
    )
    adjudication_report = build_local_global_adjudication_report(
        local_global_fixture_catalog.fixture_adjudication_rows()
    )
    adjudication_metrics = adjudication_report["metrics"]
    connected_section_kinds = sorted(
        {
            section_kind
            for row in compatibility_rows
            for section_kind in row["section_kinds"]
        }
    )
    encoded = json.dumps(compatibility_rows, ensure_ascii=False, sort_keys=True)
    forbidden_marker_count = sum(1 for marker in FORBIDDEN_MARKERS if marker in encoded)
    red_lines = {
        "raw_private_text_emitted_count": forbidden_marker_count,
        "local_path_emitted_count": forbidden_marker_count,
        "source_handle_emitted_count": forbidden_marker_count,
        "claim_permission_upgrade_count": 0,
        "foreground_projection_count": sum(
            1 for row in compatibility_rows if row["foreground_projection_allowed"]
        ),
    }
    metrics = {
        "case_count": len(compatibility_rows),
        "glued_route_count": counts[GLUED_ROUTE],
        "partial_glue_count": counts[PARTIAL_GLUE],
        "obstruction_count": counts[OBSTRUCTION],
        "blocked_boundary_count": counts[BLOCKED_BOUNDARY],
        "authority_upgrade_blocked_count": reason_counts[
            "authority_or_claim_permission_upgrade_attempt"
        ],
        "shared_vocabulary_only_overlap_count": reason_counts[
            "shared_vocabulary_without_source_scope_support"
        ],
        "useful_obstruction_later_used_count": adjudication_metrics[
            "useful_obstruction_later_used_count"
        ],
        "false_glue_regression_count": adjudication_metrics[
            "false_glue_regression_count"
        ],
        "no_help_count": adjudication_metrics["no_help_count"],
        "ambiguous_correlation_only_count": adjudication_metrics[
            "ambiguous_correlation_only_count"
        ],
        "claim_permission_upgrade_count": red_lines["claim_permission_upgrade_count"],
        "foreground_projection_count": red_lines["foreground_projection_count"],
        "raw_private_text_emitted_count": red_lines["raw_private_text_emitted_count"],
    }
    expected_results = {GLUED_ROUTE, PARTIAL_GLUE, OBSTRUCTION, BLOCKED_BOUNDARY}
    contract_gate_ok = rows is not None or expected_results.issubset(set(counts))
    safety_gate_ok = all(value == 0 for value in red_lines.values())
    return {
        "kind": REPORT_KIND,
        "schema_version": SCHEMA_VERSION,
        "ok": contract_gate_ok and safety_gate_ok,
        "contract_gate_ok": contract_gate_ok,
        "safety_gate_ok": safety_gate_ok,
        "runtime_boundary": SURFACE,
        "default_foreground": False,
        "authority_level": "navigation_only",
        "claim_permission": "navigation_only_not_fact",
        "compatibility_rows": compatibility_rows,
        "adjudication_report": adjudication_report,
        "connected_section_kinds": connected_section_kinds,
        "metrics": metrics,
        "obstruction_kind_counts": dict(sorted(obstruction_kind_counts.items())),
        "red_lines": red_lines,
        "privacy_boundary": {
            "raw_private_text_emitted": False,
            "local_paths_emitted": False,
            "source_handles_emitted": False,
            "chain_of_thought_emitted": False,
            "forbidden_marker_count": forbidden_marker_count,
        },
        "contract": {
            "overlap_basis_declared": True,
            "source_or_scope_required_before_glue": True,
            "shared_vocabulary_only_not_overlap": True,
            "glue_never_upgrades_authority": True,
            "claim_permission_never_upgraded": True,
            "failed_glue_is_obstruction_not_assignment": True,
            "explain_deepen_or_campus_first": True,
            "macro_yi_fixture_connected": "macro_router_context" in connected_section_kinds,
            "dream_topology_fixture_connected": "dream_topology_candidate" in connected_section_kinds,
            "telepathy_fixture_connected": "telepathy_coordination_packet" in connected_section_kinds,
            "aippo_fixture_connected": "aippocampus_aippo_activation_packet"
            in connected_section_kinds,
            "packet_topology_fixture_connected": "aippocampus_packet_topology_row"
            in connected_section_kinds,
            "typed_section_contract_version": local_global_sections.SECTION_CONTRACT_VERSION,
            "restriction_narrowing_protocol_declared": True,
            "time_semantics_split": [
                "source_coverage_time",
                "packet_created_at",
                "validity_window",
            ],
            "shi_ying_restriction_edge_policy": local_global_sections.V0_SHI_YING_POLICY,
            "useful_obstruction_metrics_require_adjudication": True,
        },
        "cannot_claim": [
            "default_foreground_compatibility",
            "fact_claim_ready_glue",
            "category_theory_runtime",
            "private_boundary_crossing",
            "shared_vocabulary_as_source_overlap",
            "failed_glue_as_decision_instruction",
        ],
    }


def load_rows(path: Path) -> list[Mapping[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return [item for item in data if isinstance(item, Mapping)]
    if isinstance(data, Mapping):
        raw_rows = data.get("sections") or data.get("rows") or data.get("packets") or []
        return [item for item in raw_rows if isinstance(item, Mapping)]
    return []


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", help="JSON file with local section rows.")
    parser.add_argument("--fixture", action="store_true", help="Use the built-in fixture.")
    parser.add_argument("--json", action="store_true", help="Emit JSON report.")
    args = parser.parse_args(argv)

    rows = load_rows(Path(args.input)) if args.input else None
    report = build_local_global_compatibility_report(rows)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print("local/global compatibility: " + ("ok" if report["ok"] else "blocked"))
        print(f"metrics: {report['metrics']}")
    return 0 if report["safety_gate_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
