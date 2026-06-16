#!/usr/bin/env python3
"""Deterministic Dream topology scout for source-backed candidate shapes."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from aippocampus_runtime.macro import transform_orbit
from aippocampus_runtime.ops import packet_topology_diagnostic

SCHEMA_VERSION = 1
REPORT_KIND = "aippocampus_dream_topology_scout_report"
CANDIDATE_KIND = "dream_topology_candidate"
SHADOW_ROUTE_KIND = "dream_shadow_route_candidate"
REVIEW_TASK_KIND = "aippocampus_dream_topology_review_task"
REVIEW_TASK_REPORT_KIND = "aippocampus_dream_topology_review_task_report"
REVIEW_FINDING_KIND = "aippocampus_dream_topology_review_finding"
FORBIDDEN_MARKERS = (
    "PRIVATE_DREAM_TOPOLOGY_TEXT",
    "raw_private_source_text",
    "source://private",
    "C:\\",
    "/Users/",
)
SHAPE_TO_DREAM_FUNCTION = {
    "cycle": "compensatory",
    "cut_point": "compensatory",
    "weak_bridge": "amplification",
    "knot": "active_imagination",
    "island": "prospective",
}
SHAPE_TO_REASON = {
    "cycle": "A repeated stale or rejected route may need compensatory review.",
    "cut_point": "A missing middle may change how source-backed material glues.",
    "weak_bridge": "Two source-backed sections may rhyme without yet forming evidence.",
    "knot": "Entangled obligations need an unlinking move before action.",
    "island": "A useful source-backed cluster may be failing to enter recall.",
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
    return text if text and all(char.isalnum() or char in "-_." for char in text) else fallback


def _safe_case_id(value: Any) -> str:
    text = _text(value)
    if (
        text
        and len(text) <= 96
        and all(char.isalnum() or char in "-_." for char in text)
    ):
        return text
    return "case_" + stable_hash(text, length=12)


def _safe_bool(value: Any) -> bool:
    return bool(value)


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if not isinstance(value, list):
        return []
    return [_text(item) for item in value if _text(item)]


def _safe_anchor(value: Any) -> str | None:
    text = _text(value)
    if (
        text
        and len(text) <= 80
        and not any(marker in text for marker in ("source://", "\\", "/", ":\\"))
        and all(char.isalnum() or char in "-_:#" for char in text)
    ):
        return text
    return None


def _source_anchors(row: Mapping[str, Any]) -> list[str]:
    raw_values = (
        _strings(row.get("source_anchors"))
        or _strings(row.get("source_anchor"))
        or _strings(row.get("source_refs"))
        or _strings(row.get("source_ref_ids"))
    )
    anchors = []
    for value in raw_values:
        anchor = _safe_anchor(value)
        if anchor and anchor not in anchors:
            anchors.append(anchor)
    return anchors[:8]


def _route_source_anchors(row: Mapping[str, Any], prefix: str) -> list[str]:
    raw_values = (
        _strings(row.get(f"{prefix}_source_anchors"))
        or _strings(row.get(f"{prefix}_source_refs"))
        or _strings(row.get(f"{prefix}_source_ref_ids"))
    )
    anchors: list[str] = []
    for value in raw_values:
        anchor = _safe_anchor(value)
        if anchor and anchor not in anchors:
            anchors.append(anchor)
    return anchors[:8]


def _has_transform_pair(row: Mapping[str, Any]) -> bool:
    return bool(_text(row.get("visible_hexagram")) and _text(row.get("latent_hexagram")))


def _transform_projection(
    row: Mapping[str, Any],
    *,
    shadow_source_overlap: bool,
) -> dict[str, Any]:
    if not _has_transform_pair(row):
        return {
            "available": False,
            "selected_for_deepen": False,
            "default_ranking_effect": "none",
        }
    diagnostic = transform_orbit.macro_transform_orbit_diagnostic(
        _text(row.get("visible_hexagram")),
        _text(row.get("latent_hexagram")),
    )
    selected = bool(diagnostic["same_reversible_orbit"]) and shadow_source_overlap
    return {
        "available": True,
        "selected_for_deepen": selected,
        "relation": diagnostic["relation"],
        "source_orbit_id": diagnostic["source_orbit_id"],
        "target_orbit_id": diagnostic["target_orbit_id"],
        "default_ranking_effect": "none",
        "next_safe_action": "deepen_shadow_route_candidate" if selected else "explain_only",
        "boundary": {
            "orbit_membership_is_not_source_support": True,
            "requires_shadow_source_overlap_for_deepen": True,
        },
    }


def _shadow_route_candidate_or_control(row: Mapping[str, Any]) -> dict[str, Any] | None:
    shadow_probe = _safe_bool(row.get("shadow_route_probe")) or bool(
        _text(row.get("visible_route_id")) and _text(row.get("latent_route_id"))
    )
    if not shadow_probe and not _has_transform_pair(row):
        return None

    case_id = _safe_case_id(row.get("case_id"))
    visible_route_id = _label(row.get("visible_route_id"), fallback="visible_route")
    latent_route_id = _label(row.get("latent_route_id"), fallback="latent_route")
    visible_anchors = _route_source_anchors(row, "visible")
    latent_anchors = _route_source_anchors(row, "latent")
    source_overlap = sorted(set(visible_anchors) & set(latent_anchors))
    route_residue_count = _safe_int(row.get("failed_route_residue_count") or row.get("route_residue_count"))
    failed_residue = route_residue_count > 0 or _safe_bool(row.get("failed_route_residue"))
    source_overlap_ok = bool(source_overlap)
    residue_ok = failed_residue and bool(visible_anchors or latent_anchors)
    shared_tokens = _strings(row.get("shared_topic_tokens"))
    transform_projection = _transform_projection(
        row,
        shadow_source_overlap=source_overlap_ok or residue_ok,
    )

    reason_codes: list[str] = []
    if source_overlap_ok:
        reason_codes.append("source_overlap_between_visible_and_latent_routes")
    if residue_ok:
        reason_codes.append("failed_route_residue_reappeared")
    glue_status = _label(row.get("local_global_result"), fallback="")
    if glue_status == "partial_glue":
        reason_codes.append("partial_glue_shadow_nomination")
    if not reason_codes:
        control_reasons = ["missing_source_overlap_or_failed_route_residue"]
        if shared_tokens:
            control_reasons.append("shared_vocabulary_without_source_or_residue")
        return {
            "kind": "dream_topology_control",
            "schema_version": SCHEMA_VERSION,
            "case_id": case_id,
            "shape": "shadow_route",
            "control_result": "no_shadow_candidate",
            "reason_codes": sorted(control_reasons),
            "shared_topic_token_count": len(shared_tokens),
            "shared_vocabulary_counts_as_overlap": False,
            "transform_orbit_candidate": transform_projection,
            "candidate_emitted": False,
        }

    return {
        "kind": SHADOW_ROUTE_KIND,
        "schema_version": SCHEMA_VERSION,
        "case_id": case_id,
        "candidate_id": "dream_shadow_route_" + stable_hash(
            case_id,
            visible_route_id,
            latent_route_id,
            *source_overlap,
            route_residue_count,
        ),
        "visible_route_id": visible_route_id,
        "latent_route_id": latent_route_id,
        "visible_source_anchors": visible_anchors,
        "latent_source_anchors": latent_anchors,
        "source_overlap": source_overlap,
        "source_overlap_count": len(source_overlap),
        "failed_route_residue_count": route_residue_count,
        "reason_codes": sorted(reason_codes),
        "candidate_authority": "candidate_only",
        "authority_level": "navigation_only",
        "action_grammar": "direction_with_ref",
        "claim_permission": "no_claim_before_reopen",
        "fact_claim_allowed": False,
        "foreground_eligible": False,
        "source_reopen_required_before_claim": True,
        "glue_status": glue_status or "not_evaluated",
        "glued_route": False,
        "transform_orbit_candidate": transform_projection,
        "next_safe_action": "deepen_visible_and_latent_source_refs",
        "boundary": {
            "fei_fu_is_visible_latent_route_metaphor_only": True,
            "not_hidden_user_intent": True,
            "candidate_not_fact": True,
            "source_overlap_or_residue_required": True,
            "shared_vocabulary_not_enough": True,
            "no_foreground_default": True,
        },
    }


def _packet_shape(row: Mapping[str, Any]) -> str:
    explicit_shape = _label(row.get("shape"))
    if explicit_shape in SHAPE_TO_DREAM_FUNCTION or explicit_shape == "no_shape":
        return explicit_shape
    if _safe_bool(row.get("weak_bridge")) or _safe_int(row.get("bridge_side_count")) >= 2:
        return "weak_bridge"
    if _safe_bool(row.get("islanded_useful_cluster")) or (
        _safe_bool(row.get("useful_source_cluster"))
        and _safe_int(row.get("recall_entry_count")) == 0
    ):
        return "island"

    diagnostic = packet_topology_diagnostic.evaluate_packet(row)["diagnostic"]
    if diagnostic == packet_topology_diagnostic.ROUTE_CYCLE:
        return "cycle"
    if diagnostic == packet_topology_diagnostic.MISSING_MIDDLE:
        return "cut_point"
    if diagnostic == packet_topology_diagnostic.KNOT_WITHOUT_UNLINKING:
        return "knot"
    return "no_shape"


def _rejection_reasons(
    row: Mapping[str, Any],
    *,
    shape: str,
    anchors: list[str],
) -> list[str]:
    reasons: list[str] = []
    if _safe_bool(row.get("private_psychological_interpretation")):
        reasons.append("private_psychological_interpretation")
    if _safe_bool(row.get("user_diagnosis")):
        reasons.append("user_diagnosis")
    if _safe_bool(row.get("profile_claim")):
        reasons.append("profile_claim")
    if _safe_bool(row.get("symbolic_claim")) and not anchors:
        reasons.append("source_free_symbolic_claim")
    if shape in SHAPE_TO_DREAM_FUNCTION and not anchors:
        reasons.append("missing_source_anchor")
    if shape == "weak_bridge" and len(anchors) < 2:
        reasons.append("weak_bridge_needs_two_source_anchors")
    return reasons


def candidate_or_rejection(row: Mapping[str, Any]) -> dict[str, Any]:
    case_id = _safe_case_id(row.get("case_id"))
    shadow_candidate = _shadow_route_candidate_or_control(row)
    if shadow_candidate is not None:
        return shadow_candidate
    anchors = _source_anchors(row)
    shape = _packet_shape(row)
    rejection_reasons = _rejection_reasons(row, shape=shape, anchors=anchors)

    if rejection_reasons:
        return {
            "kind": "dream_topology_rejection",
            "schema_version": SCHEMA_VERSION,
            "case_id": case_id,
            "shape": shape,
            "reasons": sorted(set(rejection_reasons)),
            "candidate_emitted": False,
        }
    if shape == "no_shape":
        return {
            "kind": "dream_topology_control",
            "schema_version": SCHEMA_VERSION,
            "case_id": case_id,
            "shape": "no_shape",
            "control_result": "no_candidate",
            "candidate_emitted": False,
        }

    cross_layer_projection = {}
    learning_finding_id = _safe_anchor(row.get("learning_finding_id"))
    if learning_finding_id:
        cross_layer_projection = {
            "learning_finding_id": learning_finding_id,
            "trigger_job": "pattern_completion_learning_loop_review",
            "authority": "navigation_only",
            "source_reopen_required_before_claim": True,
            "does_not_raise_authority": True,
        }
    return {
        "kind": CANDIDATE_KIND,
        "schema_version": SCHEMA_VERSION,
        "case_id": case_id,
        "candidate_id": "dream_topology_" + stable_hash(case_id, shape, *anchors),
        "shape": shape,
        "dream_function": SHAPE_TO_DREAM_FUNCTION[shape],
        "authority": "dream_synthesized_candidate_not_fact",
        "source_anchors": anchors,
        "source_anchor_count": len(anchors),
        "why_may_matter": SHAPE_TO_REASON[shape],
        "next_safe_action": "review_or_route_only",
        "foreground_eligible": False,
        "source_reopen_required_before_claim": True,
        "adjudication_status": "candidate_requires_source_ref_review",
        "failed_glue_obstruction_not_assignment": True,
        "private_psychological_interpretation": False,
        "user_diagnosis": False,
        "profile_claim": False,
        "unsupported_symbolic_claim": False,
        "cross_layer_projection": cross_layer_projection,
    }


def fixture_topology_rows() -> list[dict[str, Any]]:
    return [
        {
            "case_id": "stale_route_cycle",
            "packet_type": "route_packet",
            "route_state": "rejected",
            "reopen_attempt_count": 3,
            "repeated_failed_route": True,
            "source_anchors": ["issue:#1185", "issue:#1188"],
        },
        {
            "case_id": "missing_middle_cut_point",
            "packet_type": "narrative_packet",
            "missing_middle": True,
            "pathlet_gap": "missing_middle",
            "source_anchors": ["issue:#700", "issue:#1263"],
        },
        {
            "case_id": "weak_bridge_between_issues",
            "shape": "weak_bridge",
            "bridge_side_count": 2,
            "source_anchors": ["issue:#1263", "issue:#1270"],
        },
        {
            "case_id": "obligation_knot_needs_unlinking",
            "packet_type": "aippo_activation",
            "authority": "candidate_not_fact",
            "obligation_count": 3,
            "unlinking_move_present": False,
            "source_anchors": ["issue:#1185", "issue:#1268"],
        },
        {
            "case_id": "islanded_useful_cluster",
            "shape": "island",
            "useful_source_cluster": True,
            "recall_entry_count": 0,
            "source_anchors": ["issue:#163", "issue:#1250"],
        },
        {
            "case_id": "shadow_route_repeated_failure_orbit",
            "shadow_route_probe": True,
            "visible_route_id": "visible-exact-line-repair",
            "latent_route_id": "latent-semantic-cache-path",
            "visible_source_anchors": ["issue:#1193", "issue:#1305"],
            "latent_source_anchors": ["issue:#1305", "issue:#1313"],
            "failed_route_residue_count": 2,
            "visible_hexagram": "既济",
            "latent_hexagram": "未济",
        },
        {
            "case_id": "shadow_route_partial_glue",
            "shadow_route_probe": True,
            "visible_route_id": "visible-local-global",
            "latent_route_id": "latent-dream-topology",
            "visible_source_anchors": ["issue:#1270", "issue:#1268"],
            "latent_source_anchors": ["issue:#1270", "issue:#1313"],
            "local_global_result": "partial_glue",
        },
        {
            "case_id": "shadow_route_generic_vocab_control",
            "shadow_route_probe": True,
            "visible_route_id": "visible-generic",
            "latent_route_id": "latent-generic",
            "shared_topic_tokens": ["dream", "bridge", "topology"],
            "visible_hexagram": "既济",
            "latent_hexagram": "未济",
        },
        {
            "case_id": "transform_orbit_without_shadow_signal",
            "visible_route_id": "visible-macro",
            "latent_route_id": "latent-macro",
            "visible_hexagram": "乾",
            "latent_hexagram": "坤",
        },
        {
            "case_id": "healthy_no_shape_control",
            "packet_type": "memory_packet",
            "output_mode": "reopenable_route",
            "authority_level": "navigation_only",
            "claim_permission": "no_claim_before_reopen",
            "source_anchors": ["issue:#1263"],
        },
        {
            "case_id": "private_psych_interpretation",
            "shape": "weak_bridge",
            "source_anchors": ["issue:#163", "issue:#1268"],
            "private_psychological_interpretation": True,
        },
        {
            "case_id": "user_diagnosis",
            "shape": "cycle",
            "source_anchors": ["issue:#163"],
            "user_diagnosis": True,
        },
        {
            "case_id": "profile_claim",
            "shape": "island",
            "source_anchors": ["issue:#163"],
            "profile_claim": True,
        },
        {
            "case_id": "source_free_symbolic_claim",
            "shape": "knot",
            "symbolic_claim": True,
            "source_anchors": [],
        },
    ]


def build_dream_topology_scout_report(
    rows: Iterable[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    row_list = list(rows) if rows is not None else fixture_topology_rows()
    outputs = [candidate_or_rejection(row) for row in row_list]
    candidates = [item for item in outputs if item["kind"] == CANDIDATE_KIND]
    shadow_candidates = [item for item in outputs if item["kind"] == SHADOW_ROUTE_KIND]
    controls = [item for item in outputs if item["kind"] == "dream_topology_control"]
    rejected = [item for item in outputs if item["kind"] == "dream_topology_rejection"]
    rejected_reasons = Counter(
        reason for item in rejected for reason in item.get("reasons", [])
    )
    shape_counts = Counter(item.get("shape") for item in candidates)
    forbidden_marker_count = sum(
        1
        for marker in FORBIDDEN_MARKERS
        if marker in json.dumps(outputs, ensure_ascii=False, sort_keys=True)
    )
    foreground_leak_count = sum(1 for item in candidates if item["foreground_eligible"])
    private_interpretation_count = sum(
        1 for item in candidates if item["private_psychological_interpretation"]
    )
    shape_false_positive_count = sum(
        1
        for item in controls
        if item.get("control_result") != "no_candidate"
        and item.get("control_result") != "no_shadow_candidate"
    )
    shadow_generic_vocab_false_positive_count = sum(
        1
        for item in shadow_candidates
        if "shared_vocabulary_without_source_or_residue" in item.get("reason_codes", [])
    )
    transform_orbit_deepen_candidate_count = sum(
        1
        for item in shadow_candidates
        if item.get("transform_orbit_candidate", {}).get("selected_for_deepen")
    )
    shadow_claim_without_reopen_count = sum(
        1 for item in shadow_candidates if item.get("fact_claim_allowed") is not False
    )
    metrics = {
        "case_count": len(outputs),
        "dream_topology_candidate_count": len(candidates),
        "shadow_route_candidate_count": len(shadow_candidates),
        "shadow_route_source_overlap_count": sum(
            1 for item in shadow_candidates if item.get("source_overlap_count", 0) > 0
        ),
        "shadow_route_generic_vocab_false_positive_count": shadow_generic_vocab_false_positive_count,
        "shadow_route_claim_without_reopen_count": shadow_claim_without_reopen_count,
        "transform_orbit_deepen_candidate_count": transform_orbit_deepen_candidate_count,
        "dream_topology_source_anchor_coverage": round(
            sum(1 for item in candidates if item["source_anchor_count"] > 0)
            / max(1, len(candidates)),
            4,
        ),
        "dream_topology_foreground_leak_count": foreground_leak_count,
        "dream_topology_private_interpretation_count": private_interpretation_count,
        "dream_topology_shape_false_positive_count": shape_false_positive_count,
        "cycle_candidate_count": shape_counts["cycle"],
        "cut_point_candidate_count": shape_counts["cut_point"],
        "weak_bridge_candidate_count": shape_counts["weak_bridge"],
        "knot_candidate_count": shape_counts["knot"],
        "island_candidate_count": shape_counts["island"],
        "hard_negative_rejected_count": len(rejected),
        "source_free_symbolic_claim_rejected_count": rejected_reasons[
            "source_free_symbolic_claim"
        ],
        "profile_claim_rejected_count": rejected_reasons["profile_claim"],
        "user_diagnosis_rejected_count": rejected_reasons["user_diagnosis"],
        "private_interpretation_rejected_count": rejected_reasons[
            "private_psychological_interpretation"
        ],
    }
    red_lines = {
        "raw_private_text_emitted_count": forbidden_marker_count,
        "local_path_emitted_count": forbidden_marker_count,
        "source_handle_emitted_count": forbidden_marker_count,
        "foreground_leak_count": foreground_leak_count,
        "private_interpretation_emitted_count": private_interpretation_count,
        "shape_false_positive_count": shape_false_positive_count,
        "shadow_route_claim_without_reopen_count": shadow_claim_without_reopen_count,
    }
    expected_cases = {
        "stale_route_cycle",
        "missing_middle_cut_point",
        "weak_bridge_between_issues",
        "obligation_knot_needs_unlinking",
        "islanded_useful_cluster",
        "shadow_route_repeated_failure_orbit",
        "shadow_route_partial_glue",
        "shadow_route_generic_vocab_control",
        "transform_orbit_without_shadow_signal",
        "healthy_no_shape_control",
        "private_psych_interpretation",
        "user_diagnosis",
        "profile_claim",
        "source_free_symbolic_claim",
    }
    contract_gate_ok = rows is not None or expected_cases.issubset(
        {item["case_id"] for item in outputs}
    )
    safety_gate_ok = all(value == 0 for value in red_lines.values())
    return {
        "kind": REPORT_KIND,
        "schema_version": SCHEMA_VERSION,
        "ok": contract_gate_ok and safety_gate_ok,
        "contract_gate_ok": contract_gate_ok,
        "safety_gate_ok": safety_gate_ok,
        "benchmark_maturity_level": "contract_smoke",
        "authority_level": "dream_synthesized_candidate_not_fact",
        "runtime_boundary": "detached_background_or_explain_only",
        "every_turn_scan": False,
        "foreground_default": False,
        "truth_layer": False,
        "candidates": candidates,
        "shadow_route_candidates": shadow_candidates,
        "controls": controls,
        "rejected": rejected,
        "metrics": metrics,
        "red_lines": red_lines,
        "privacy_boundary": {
            "raw_private_text_emitted": False,
            "local_paths_emitted": False,
            "source_handles_emitted": False,
            "private_interpretations_emitted": False,
            "forbidden_marker_count": forbidden_marker_count,
        },
        "contract": {
            "uses_packet_topology_diagnostic": True,
            "failed_glue_can_be_candidate_not_assignment": True,
            "candidate_not_fact": True,
            "source_anchor_required": True,
            "foreground_disabled_by_default": True,
            "hard_negatives_rejected": True,
            "public_safe_substrate_for_163": True,
            "shadow_route_candidates_are_candidate_only": True,
            "source_overlap_or_residue_required_for_shadow_route": True,
            "transform_orbit_requires_shadow_source_overlap_for_deepen": True,
        },
        "cannot_claim": [
            "live_dream_quality",
            "private_history_dream_quality",
            "user_visible_causal_lift",
            "psychological_interpretation",
            "profile_truth",
            "source_truth_without_reopen",
            "foreground_default_usefulness",
            "shadow_route_as_hidden_fact_or_user_intent",
            "transform_orbit_as_source_support",
            "automatic_route_merge_from_partial_glue",
        ],
    }


def _topology_review_suppression_reason(candidate: Mapping[str, Any]) -> str:
    projection = candidate.get("cross_layer_projection")
    if not isinstance(projection, Mapping) or projection.get("trigger_job") != "pattern_completion_learning_loop_review":
        return "no_pattern_completion_trigger"
    bucket = _label(candidate.get("scope_bucket") or candidate.get("privacy_partition"), fallback="")
    scope = _text(candidate.get("scope")).casefold()
    if bucket in {"private", "user_private", "machine_private", "restricted"} or scope.startswith("private:"):
        return "private_scope_blocked"
    freshness = _label(candidate.get("freshness") or "current", fallback="current")
    if freshness in {"stale", "superseded", "retired", "archived", "local_only"} or scope.startswith("machine:"):
        return "stale_or_local_only"
    if not _strings(candidate.get("source_anchors")):
        return "missing_source_anchor"
    return ""


def _review_task_for_candidate(candidate: Mapping[str, Any], *, now: str) -> dict[str, Any] | None:
    reason = _topology_review_suppression_reason(candidate)
    if reason:
        return None
    projection = candidate.get("cross_layer_projection")
    projection = projection if isinstance(projection, Mapping) else {}
    anchors = _strings(candidate.get("source_anchors"))[:8]
    candidate_id = _text(candidate.get("candidate_id"))
    task_id = "dream_review_" + stable_hash(candidate_id, projection.get("learning_finding_id"), *anchors)
    return {
        "kind": REVIEW_TASK_KIND,
        "schema_version": SCHEMA_VERSION,
        "task_id": task_id,
        "created_at": now,
        "status": "queued",
        "task_type": "pattern_completion_learning_loop_review",
        "candidate_id": candidate_id,
        "learning_finding_id": projection.get("learning_finding_id"),
        "shape": candidate.get("shape"),
        "dream_function": candidate.get("dream_function"),
        "source_anchors": anchors,
        "source_anchor_count": len(anchors),
        "scope": candidate.get("scope") or "public_default",
        "scope_bucket": candidate.get("scope_bucket") or "public_default",
        "topic_epoch": candidate.get("topic_epoch") or "topic-v1",
        "foreground_eligible": False,
        "navigation_only": True,
        "claim_permission": "none",
        "source_reopen_required_before_claim": True,
        "truth_boundary": "dream_topology_review_task_not_fact",
        "next_safe_action": "background_review_or_explicit_operator_review",
    }


def materialize_pattern_completion_review_tasks(
    candidates: Iterable[Mapping[str, Any]],
    *,
    now: str = "",
) -> dict[str, Any]:
    created_at = now or "unknown_time"
    tasks: list[dict[str, Any]] = []
    suppressed: list[dict[str, Any]] = []
    for candidate in candidates:
        if not isinstance(candidate, Mapping):
            continue
        task = _review_task_for_candidate(candidate, now=created_at)
        if task:
            tasks.append(task)
            continue
        reason = _topology_review_suppression_reason(candidate)
        if reason != "no_pattern_completion_trigger":
            suppressed.append(
                {
                    "candidate_id": candidate.get("candidate_id"),
                    "case_id": candidate.get("case_id"),
                    "reason": reason,
                }
            )
    return {
        "kind": REVIEW_TASK_REPORT_KIND,
        "schema_version": SCHEMA_VERSION,
        "created_at": created_at,
        "tasks": tasks,
        "suppressed": suppressed,
        "metrics": {
            "materialized_task_count": len(tasks),
            "suppressed_task_count": len(suppressed),
            "foreground_task_count": sum(1 for task in tasks if task.get("foreground_eligible")),
            "authority_raise_count": 0,
        },
        "privacy_boundary": {
            "raw_private_text_emitted": False,
            "local_paths_emitted": False,
            "source_reopen_required_before_claim": True,
        },
        "claim_boundary": "review_tasks_are_navigation_work_not_source_truth",
    }


def consume_pattern_completion_review_tasks(
    tasks: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    noops: list[dict[str, Any]] = []
    for task in tasks:
        if not isinstance(task, Mapping) or task.get("kind") != REVIEW_TASK_KIND:
            continue
        anchors = _strings(task.get("source_anchors"))
        if task.get("status") != "queued" or not anchors:
            noops.append({"task_id": task.get("task_id"), "reason": "not_ready_or_missing_source"})
            continue
        findings.append(
            {
                "kind": REVIEW_FINDING_KIND,
                "schema_version": SCHEMA_VERSION,
                "task_id": task.get("task_id"),
                "candidate_id": task.get("candidate_id"),
                "status": "bounded_review_candidate",
                "source_anchors": anchors[:8],
                "source_anchor_count": len(anchors[:8]),
                "supports_factual_claim": False,
                "foreground_eligible": False,
                "navigation_only": True,
                "source_reopen_required_before_claim": True,
                "recommendation": "review_pattern_completion_against_reopened_sources",
            }
        )
    return {
        "kind": "aippocampus_dream_topology_review_consumer_report",
        "schema_version": SCHEMA_VERSION,
        "findings": findings,
        "noops": noops,
        "metrics": {
            "bounded_finding_count": len(findings),
            "noop_count": len(noops),
            "authority_raise_count": 0,
        },
        "claim_boundary": "bounded_findings_are_review_candidates_not_facts",
    }


def load_rows(path: Path) -> list[Mapping[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return [item for item in data if isinstance(item, Mapping)]
    if isinstance(data, Mapping):
        raw_rows = data.get("rows") or data.get("cases") or data.get("packets") or []
        return [item for item in raw_rows if isinstance(item, Mapping)]
    return []


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", help="JSON file with Dream topology rows.")
    parser.add_argument("--fixture", action="store_true", help="Use the built-in fixture.")
    parser.add_argument("--json", action="store_true", help="Emit JSON report.")
    args = parser.parse_args(argv)

    rows = load_rows(Path(args.input)) if args.input else None
    report = build_dream_topology_scout_report(rows)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print("dream topology scout: " + ("ok" if report["ok"] else "blocked"))
        print(f"metrics: {report['metrics']}")
    return 0 if report["safety_gate_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
