"""Query-time macro-field atlas materialization.

The atlas is a derived foreground packet. It selects a small top-N section set,
computes hard local/global checks only inside that set, merges declared and
posture edges as separate soft surfaces, then projects a compact lane packet.
It is not a persistent all-pairs graph and it does not create source truth.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

from aippocampus_runtime.core import compact_text
from aippocampus_runtime.navigation import avatar_posture, local_global_compatibility

SCHEMA_VERSION = 1
AUTHORITY_LEVEL = "direction_only"
CLAIM_PERMISSION = "none"
DECLARED_RELATIONS = {
    "shared_source_event",
    "precondition",
    "supersedes",
    "blocks",
    "unblocks",
    "correction_applies_to",
}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _stable_id(prefix: str, *parts: Any) -> str:
    raw = "\n".join(json.dumps(part, ensure_ascii=False, sort_keys=True) for part in parts)
    digest = hashlib.sha1(raw.encode("utf-8", errors="replace")).hexdigest()[:18]
    return f"{prefix}_{digest}"


def _safe_refs(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    refs: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, Mapping):
            continue
        ref = {
            str(key): item[key]
            for key in ("source_id", "message_id", "turn_ref", "issue", "url")
            if item.get(key) not in (None, "")
        }
        if ref:
            refs.append(ref)
    return refs[:8]


def normalize_atlas_section(row: Mapping[str, Any], *, index: int = 0) -> dict[str, Any]:
    posture = (
        {"posture_id": row.get("posture_id"), "reason_codes": ["explicit_posture_id"]}
        if row.get("posture_id")
        else avatar_posture.reduce_avatar_posture(row)
    )
    section_id = _text(row.get("section_id") or row.get("id")) or _stable_id("section", index, row)
    source_refs = _safe_refs(row.get("source_refs"))
    return {
        "section_id": section_id,
        "title": compact_text(_text(row.get("title") or row.get("summary") or section_id), 120),
        "section_kind": _text(row.get("section_kind") or row.get("kind") or "macro_section"),
        "scope": _text(row.get("scope") or row.get("normalized_scope") or row.get("project") or "global"),
        "domain": _text(row.get("domain") or row.get("domain_id") or ""),
        "task_family": _text(row.get("task_family") or row.get("route_family") or ""),
        "topic_epoch": _text(row.get("topic_epoch") or row.get("epoch") or "current"),
        "time_bucket": _text(row.get("time_bucket") or row.get("created_bucket") or "current"),
        "lifecycle": _text(row.get("lifecycle") or row.get("status") or "active"),
        "freshness": _text(row.get("freshness") or row.get("currentness") or "current"),
        "privacy_state": _text(row.get("privacy_state") or row.get("privacy") or "public_safe"),
        "source_refs": source_refs,
        "source_ref_count": len(source_refs),
        "authority_level": AUTHORITY_LEVEL,
        "claim_permission": CLAIM_PERMISSION,
        "posture_id": _text(posture.get("posture_id") or "ambiguous_posture"),
        "posture_basis": posture,
        "atlas_metadata": {
            "materialized_view_only": True,
            "source_reopen_required": True,
        },
    }


def _query_terms(query: str) -> set[str]:
    return {
        item
        for item in query.casefold().replace("/", " ").replace("-", " ").split()
        if len(item) >= 3
    }


def _policy_lift(section: Mapping[str, Any], policies: Sequence[Mapping[str, Any]]) -> tuple[float, list[str]]:
    lifts: list[float] = []
    reasons: list[str] = []
    posture = _text(section.get("posture_id"))
    for row in policies:
        if row.get("expired") or row.get("policy_state") == "expired":
            continue
        if not row.get("accepted", row.get("promoted", True)):
            continue
        if posture and posture in {_text(row.get("from_posture_id")), _text(row.get("to_posture_id"))}:
            lift = min(0.2, max(0.0, float(row.get("lift") or row.get("suggested_lift") or 0.05)))
            lifts.append(lift)
            reasons.append(f"posture_relation_lift:{_text(row.get('relation') or 'policy')}")
    return round(sum(lifts), 6), reasons[:4]


def select_top_sections(
    sections: Sequence[Mapping[str, Any]],
    *,
    query: str = "",
    top_n: int = 8,
    posture_policies: Sequence[Mapping[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    terms = _query_terms(query)
    policies = list(posture_policies or [])
    scored: list[dict[str, Any]] = []
    for index, raw in enumerate(sections):
        if not isinstance(raw, Mapping):
            continue
        section = normalize_atlas_section(raw, index=index)
        if section["privacy_state"] in {"blocked", "private_blocked"}:
            section["atlas_score"] = -1.0
            section["atlas_reason_codes"] = ["privacy_blocked_suppressed"]
            scored.append(section)
            continue
        haystack = " ".join(
            _text(section.get(key))
            for key in ("title", "scope", "domain", "task_family", "topic_epoch", "posture_id")
        ).casefold()
        query_hits = sum(1 for term in terms if term in haystack)
        lift, lift_reasons = _policy_lift(section, policies)
        score = (
            query_hits
            + min(int(section["source_ref_count"]), 3) * 0.3
            + (0.2 if section["freshness"] in {"current", "fresh"} else -0.4)
            + lift
        )
        section["atlas_score"] = round(score, 6)
        section["atlas_reason_codes"] = [
            *(["query_term_match"] if query_hits else []),
            *(["source_refs_present"] if section["source_ref_count"] else ["source_refs_missing"]),
            *lift_reasons,
        ]
        scored.append(section)
    eligible = [row for row in scored if float(row.get("atlas_score") or 0.0) >= 0]
    eligible.sort(key=lambda row: (-float(row.get("atlas_score") or 0.0), str(row["section_id"])))
    return eligible[: max(0, top_n)]


def hard_overlap_edges(selected: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    edges: list[dict[str, Any]] = []
    for left_index, left in enumerate(selected):
        for right in selected[left_index + 1 :]:
            diagnostic = local_global_compatibility.evaluate_local_global_compatibility(
                [left, right],
                case_id=f"{left['section_id']}::{right['section_id']}",
            )
            result = str(diagnostic.get("result") or "obstruction")
            freshness_current = bool((diagnostic.get("overlap_basis") or {}).get("freshness_current"))
            source_count = int((diagnostic.get("overlap_basis") or {}).get("source_overlap_count") or 0)
            status = "active" if result == "glued_route" and freshness_current else "needs_overlap_recheck"
            if source_count <= 0:
                status = "needs_source_reopen"
            edges.append(
                {
                    "edge_id": _stable_id("hard_edge", left["section_id"], right["section_id"], result),
                    "edge_kind": "hard_overlap_edge",
                    "from_section_id": left["section_id"],
                    "to_section_id": right["section_id"],
                    "edge_epoch": f"{left.get('topic_epoch')}::{right.get('topic_epoch')}",
                    "basis": diagnostic.get("overlap_basis"),
                    "compatibility_result": result,
                    "status": status,
                    "reason_codes": diagnostic.get("reason_codes") or [],
                    "authority_level": "navigation_only",
                    "claim_permission": "navigation_only_not_fact",
                    "may_satisfy_glue": result == "glued_route",
                    "recommended_next": diagnostic.get("next_safe_action"),
                }
            )
    return edges


def normalize_declared_edge(
    event: Mapping[str, Any],
    *,
    known_section_ids: set[str],
) -> dict[str, Any] | None:
    relation = _text(event.get("relation") or event.get("relation_kind"))
    source_id = _text(event.get("from_section_id") or event.get("from"))
    target_id = _text(event.get("to_section_id") or event.get("to"))
    refs = _safe_refs(event.get("source_refs"))
    if relation not in DECLARED_RELATIONS or not source_id or not target_id:
        return None
    if source_id not in known_section_ids or target_id not in known_section_ids:
        return None
    if event.get("blocked") or event.get("privacy_state") in {"blocked", "private_blocked"}:
        return None
    status = "active" if refs and not event.get("stale") else "needs_source_reopen"
    return {
        "edge_id": _stable_id("declared_edge", event.get("source_event_id"), source_id, target_id, relation),
        "edge_kind": "declared_edge",
        "source_event_id": _text(event.get("source_event_id") or event.get("event_id")),
        "from_section_id": source_id,
        "to_section_id": target_id,
        "relation": relation,
        "authority": _text(event.get("authority") or AUTHORITY_LEVEL),
        "reasons": [compact_text(_text(item), 120) for item in event.get("reasons") or []][:4],
        "source_refs": refs,
        "status": status,
        "claim_permission": CLAIM_PERMISSION,
        "may_satisfy_glue": False,
        "recommended_next": "follow_declared_relation_then_reopen_source",
    }


def posture_edges(selected: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    edges: list[dict[str, Any]] = []
    for left in selected:
        for right in selected:
            if left.get("section_id") == right.get("section_id"):
                continue
            edge = avatar_posture.posture_dependency_edge(left, right)
            if edge:
                edges.append(edge)
    dedup: dict[str, dict[str, Any]] = {}
    for edge in edges:
        dedup[str(edge["edge_id"])] = edge
    return list(dedup.values())


def compact_foreground_lanes(
    selected: Sequence[Mapping[str, Any]],
    edges: Sequence[Mapping[str, Any]],
    *,
    timing_affordance: Mapping[str, Any] | None = None,
    invariant_diagnostics: Sequence[Mapping[str, Any]] | None = None,
    byte_budget: int = 4200,
) -> dict[str, Any]:
    hard_obstructions = [
        edge for edge in edges if edge.get("edge_kind") == "hard_overlap_edge" and edge.get("status") != "active"
    ]
    timing = timing_affordance or {}
    warnings = [
        _text(item.get("runtime_recheck_reason"))
        for item in invariant_diagnostics or []
        if _text(item.get("runtime_recheck_reason"))
    ]
    if _text(timing.get("runtime_recheck_reason")):
        warnings.append(_text(timing.get("runtime_recheck_reason")))
    posture_ids = {str(row.get("posture_id") or "") for row in selected if row.get("posture_id")}
    if not selected:
        posture = "obstructed"
    elif len(selected) > 3:
        posture = "noisy"
    elif hard_obstructions:
        posture = "obstructed"
    elif len(posture_ids) > 1:
        posture = "mixed"
    else:
        posture = "single"
    lanes: list[dict[str, Any]] = []
    for index, section in enumerate(selected[:3]):
        role = "primary" if index == 0 else "secondary"
        lane_action = "source_reopen_required"
        bandwidth = _text(timing.get("attention_bandwidth") or "narrow")
        if "timing_affordance_falsified" in warnings:
            bandwidth = "backstage"
            lane_action = "recheck_timing_before_foreground"
        if "source_reanchoring_required" in warnings and index == 0:
            bandwidth = "reopen_first"
            lane_action = "reopen_anchor_source_first"
        lanes.append(
            {
                "lane_id": _stable_id("lane", section["section_id"], role),
                "role": role,
                "section_id": section["section_id"],
                "title": section["title"],
                "posture_id": section.get("posture_id"),
                "attention_bandwidth": bandwidth,
                "agent_instruction": lane_action,
                "source_reopen_required": True,
                "claim_permission": CLAIM_PERMISSION,
                "authority_level": AUTHORITY_LEVEL,
            }
        )
    packet = {
        "kind": "macro_field_foreground_projection",
        "schema_version": SCHEMA_VERSION,
        "posture": posture,
        "primary_lane": lanes[0] if lanes else None,
        "secondary_lanes": lanes[1:],
        "lane_count": len(lanes),
        "warnings": sorted(set(warnings)),
        "source_reopen_required": True,
        "claim_permission": CLAIM_PERMISSION,
        "authority_level": AUTHORITY_LEVEL,
        "byte_budget": byte_budget,
    }
    encoded = json.dumps(packet, ensure_ascii=False, sort_keys=True)
    packet["within_byte_budget"] = len(encoded.encode("utf-8")) <= byte_budget
    return packet


def materialize_macro_field_atlas(
    sections: Sequence[Mapping[str, Any]],
    *,
    query: str = "",
    top_n: int = 8,
    declared_edges: Sequence[Mapping[str, Any]] | None = None,
    posture_policies: Sequence[Mapping[str, Any]] | None = None,
    timing_affordance: Mapping[str, Any] | None = None,
    invariant_diagnostics: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    selected = select_top_sections(
        sections,
        query=query,
        top_n=top_n,
        posture_policies=posture_policies,
    )
    known_ids = {str(row["section_id"]) for row in selected}
    hard = hard_overlap_edges(selected)
    declared = [
        edge
        for event in declared_edges or []
        if isinstance(event, Mapping)
        for edge in [normalize_declared_edge(event, known_section_ids=known_ids)]
        if edge is not None
    ]
    posture = posture_edges(selected)
    edges = [*hard, *declared, *posture]
    projection = compact_foreground_lanes(
        selected,
        edges,
        timing_affordance=timing_affordance,
        invariant_diagnostics=invariant_diagnostics,
    )
    total_sections = len([row for row in sections if isinstance(row, Mapping)])
    pairwise_checks = len(selected) * (len(selected) - 1) // 2
    total_pairs = total_sections * (total_sections - 1) // 2
    return {
        "kind": "macro_field_atlas_materialization",
        "schema_version": SCHEMA_VERSION,
        "query_time_materialized": True,
        "persistent_all_pairs_graph": False,
        "input_section_count": total_sections,
        "selected_section_count": len(selected),
        "top_n": top_n,
        "pairwise_hard_check_count": pairwise_checks,
        "total_possible_pair_count": total_pairs,
        "all_pairs_recomputed": False,
        "selected_sections": selected,
        "edges": edges,
        "edge_counts": dict(Counter(str(edge.get("edge_kind")) for edge in edges)),
        "foreground_projection": projection,
        "authority_level": AUTHORITY_LEVEL,
        "claim_permission": CLAIM_PERMISSION,
        "cannot_claim": [
            "macro_field_atlas_is_source_truth",
            "posture_edge_satisfies_glue",
            "declared_edge_transfers_fact_without_source_reopen",
            "persistent_all_pairs_recompute",
        ],
    }


__all__ = [
    "compact_foreground_lanes",
    "hard_overlap_edges",
    "materialize_macro_field_atlas",
    "normalize_atlas_section",
    "normalize_declared_edge",
    "posture_edges",
    "select_top_sections",
]
