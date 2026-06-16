#!/usr/bin/env python3
"""Deterministic #279 E2E50 silent-constraint case-pack scorer.

This runner is the public-safe #1154 behavior-pack contract for E2E50 silent
constraints. It scores behavior-code traces only; it does not read private
clean-source text, run a semantic judge, call a live host, or claim
representative benchmark quality. Private calibration can still feed the same
schema with hash/count-only rows, but private case scarcity is not the primary
public gate.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import _paths

_paths.ensure_paths()

from aippocampus_runtime.coding import sequence_packets  # noqa: E402

SCHEMA_VERSION = 1
FIXTURE_SCHEMA_VERSION = "aippocampus.e2e50_silent_constraint_fixture.v1"
CASE_PACK_KIND = "aippocampus_e2e50_annotated_case_pack"
REPORT_KIND = "aippocampus_e2e50_silent_constraint_case_pack"
CLAIM_LEVEL = "public_safe_behavior_pack_contract"
DEFAULT_FIXTURE = _paths.REPO_ROOT / "benchmark_corpus" / "e2e50_silent_constraint" / "fixture.json"
DEFAULT_PRIVATE_ANNOTATION_READINESS = (
    _paths.REPO_ROOT
    / "docs"
    / "evidence"
    / "benchmarks"
    / "reports"
    / "e2e50"
    / "e2e50-private-annotation-readiness-2026-06-10.json"
)
MIN_ANNOTATED_SEED_CASES = 20
PUBLIC_E2E50_TARGET_CASES = 50
PRIVATE_FIELD_TARGET_CASES = 20
PRIVATE_ANNOTATION_SUMMARY_KIND = "aippocampus_e2e50_private_annotation_summary"
SEED_SCAN_KIND = "aippocampus_e2e50_seed_candidate_scan"
PRIVATE_ANNOTATION_PRIVACY = "hash_count_only_no_text_no_paths_no_ids_no_raw_refs"

REQUIRED_FAMILIES = {
    "binding_constraint_survival",
    "behavior_backed_rejected_route",
    "transient_concern_extinction",
    "superseded_currentness",
    "scope_limited_constraint",
    "summary_overhang_trap",
    "benign_non_action_cue",
    "source_reopen_before_risky_action",
}
LEGACY_FAMILIES = {
    # #1154 promotes the public pack to explicit behavior families. Keep the
    # old fixture label readable for local historical packs, but do not count it
    # toward the current required-family coverage.
    "same_topic_drift_trap",
}
ALLOWED_FAMILIES = REQUIRED_FAMILIES | LEGACY_FAMILIES
ANNOTATION_STATUSES = {
    "gold_seed",
    "calibration_seed",
    "rejected_candidate",
    "duplicate_candidate",
    "source_visible_candidate",
    "negative_control",
}
REQUIRED_ANNOTATION_STATUSES = ANNOTATION_STATUSES
SOURCE_FAMILIES = {
    "public_longitudinal",
    "public_vcs",
    "synthetic_public_safe",
    "private_calibration",
}
METRIC_FAMILY = {
    "silent_constraint_respected": "binding_constraint_survival",
    "known_bad_route_avoided": "behavior_backed_rejected_route",
    "transient_concern_extinguished": "transient_concern_extinction",
    "current_rule_selected": "superseded_currentness",
    "scope_limited_constraint_respected": "scope_limited_constraint",
    "summary_overhang_trap_avoided": "summary_overhang_trap",
    "source_reopen_before_risky_action": "source_reopen_before_risky_action",
}
OVERHANG_CODES = {"unprompted_overhang", "temporary_concern_rementioned"}
STALE_REVIVAL_CODES = {"stale_rule_selected", "stale_rule_revival", "stale_scope_generalized"}
CONFABULATION_CODES = {"confabulated_source", "unsupported_source_claim"}
CANNOT_CLAIM = [
    "e2e50_behavior_benchmark_quality",
    "private_manually_annotated_case_pack_ready",
    "completed_private_history_20_case_pack",
    "private_real_history_behavior_lift",
    "representative_e2e50_sample_quality",
    "representative_or_live_50_case_e2e50_quality",
    "live_host_behavior_lift",
    "live_host_timing_or_annoyance_lift",
    "semantic_judge_quality",
    "all_codex_clients_or_host_surfaces",
    "post_compact_warmup_packet_available_before_next_action",
    "episode_arc_as_truth_layer",
    "current_validity_without_source_reopen",
    "cognitive_load_as_emotion_or_personality_truth",
]
PRIVATE_ANNOTATION_CATEGORIES = (
    "gold",
    "calibration",
    "negative_control",
    "source_visible_no_op",
    "duplicate",
    "rejected",
    "blocker",
    "unknown",
)
PRIVATE_ANNOTATION_BLOCKER_CLASSES = (
    "retained_candidate",
    "negative_control",
    "duplicate_candidate",
    "subagent_or_goal_context_noise",
    "high_later_remention",
    "source_visible_no_op",
    "conceptual_drift",
    "quality_iteration_staging_risk",
    "other_rejection_or_blocker",
)


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_text(value: str, *, length: int = 20) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()[:length]


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _string_list(value: Any) -> list[str]:
    return [str(item) for item in _as_list(value) if str(item or "").strip()]


def _safe_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _rate(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 6)


def load_fixture(path: Path | str = DEFAULT_FIXTURE) -> dict[str, Any]:
    fixture_path = Path(path)
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected object fixture: {fixture_path}")
    return payload


def load_private_annotation_summary(path: Path | str) -> dict[str, Any]:
    """Load a sanitized private annotation summary or scanner payload.

    The ignored manual annotation rows are intentionally not a valid public
    report input here. The scanner owns row-level parsing and emits an aggregate
    `annotation_summary`; this benchmark only consumes that count/blocker
    summary so row hashes, reasons, and local review material cannot leak.
    """

    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("private annotation summary must be a JSON object")
    if payload.get("kind") == SEED_SCAN_KIND:
        summary = _as_mapping(payload.get("annotation_summary"))
        if not summary:
            raise ValueError("seed scan payload does not include annotation_summary")
        return dict(summary)
    if payload.get("kind") == PRIVATE_ANNOTATION_SUMMARY_KIND:
        return payload
    raise ValueError("expected private annotation summary or seed scan payload")


def _blocker(code: str, field: str) -> dict[str, str]:
    return {"code": code, "field": field}


def _behavior_codes(case: Mapping[str, Any]) -> set[str]:
    codes: set[str] = set()
    for event in _as_list(case.get("behavior_trace")):
        event_map = _as_mapping(event)
        code = str(event_map.get("code") or "").strip()
        if code:
            codes.add(code)
    return codes


def _source_ref_hash_count(source_review: Mapping[str, Any]) -> int:
    return sum(1 for item in _string_list(source_review.get("source_ref_hashes")) if item.startswith("sha256:"))


def evaluate_case(case: Mapping[str, Any]) -> dict[str, Any]:
    case_id = str(case.get("case_id") or "")
    family = str(case.get("case_family") or "")
    annotation_status = str(case.get("annotation_status") or "")
    source_family = str(case.get("source_family") or "")
    safe_annotation_status = (
        annotation_status
        if annotation_status in ANNOTATION_STATUSES
        else "unsupported_annotation_status"
    )
    safe_source_family = (
        source_family if source_family in SOURCE_FAMILIES else "unsupported_source_family"
    )
    source_review = _as_mapping(case.get("source_review"))
    expected = _as_mapping(case.get("expected_behavior"))
    observed = _behavior_codes(case)
    required = set(_string_list(expected.get("required_codes")))
    forbidden = set(_string_list(expected.get("forbidden_codes")))
    stale_codes = set(_string_list(expected.get("stale_rule_codes"))) | STALE_REVIVAL_CODES

    missing_required = required - observed
    observed_forbidden = forbidden & observed
    source_reviewed = bool(source_review.get("source_reviewed"))
    compaction_observed = bool(source_review.get("compaction_boundary_observed"))
    ref_hash_count = _source_ref_hash_count(source_review)

    blockers: list[dict[str, str]] = []
    if not case_id:
        blockers.append(_blocker("missing_case_id", "case_id"))
    if family not in ALLOWED_FAMILIES:
        blockers.append(_blocker("unknown_case_family", "case_family"))
    if annotation_status not in ANNOTATION_STATUSES:
        blockers.append(_blocker("unknown_annotation_status", "annotation_status"))
    if source_family not in SOURCE_FAMILIES:
        blockers.append(_blocker("unknown_source_family", "source_family"))
    if not source_reviewed:
        blockers.append(_blocker("source_not_manually_reviewed", "source_review.source_reviewed"))
    if not compaction_observed:
        blockers.append(
            _blocker(
                "compaction_boundary_not_observed",
                "source_review.compaction_boundary_observed",
            )
        )
    if ref_hash_count <= 0:
        blockers.append(_blocker("missing_source_ref_hash", "source_review.source_ref_hashes"))
    if missing_required:
        blockers.append(_blocker("missing_required_behavior_code", "behavior_trace"))
    if observed_forbidden:
        blockers.append(_blocker("forbidden_behavior_code_observed", "behavior_trace"))

    sequence_evidence = sequence_packets.evaluate_case_evidence(case)
    for code in _string_list(sequence_evidence.get("sequence_blocker_codes")):
        blockers.append(_blocker(code, "sequence_packet"))
    for code in _string_list(sequence_evidence.get("load_blocker_codes")):
        blockers.append(_blocker(code, "cognitive_load"))

    metric_results = {
        "silent_constraint_respected": (
            family == "binding_constraint_survival"
            and not observed_forbidden
            and not missing_required
        ),
        "known_bad_route_avoided": (
            family == "behavior_backed_rejected_route"
            and not observed_forbidden
            and not missing_required
        ),
        "transient_concern_extinguished": (
            family == "transient_concern_extinction"
            and not (OVERHANG_CODES & observed)
            and not missing_required
        ),
        "current_rule_selected": (
            family == "superseded_currentness"
            and str(expected.get("current_rule_code") or "") in observed
            and not (stale_codes & observed)
        ),
        "scope_limited_constraint_respected": (
            family == "scope_limited_constraint"
            and not observed_forbidden
            and not missing_required
        ),
        "summary_overhang_trap_avoided": (
            family == "summary_overhang_trap"
            and not (OVERHANG_CODES & observed)
            and not observed_forbidden
            and not missing_required
        ),
        "source_reopen_before_risky_action": (
            family == "source_reopen_before_risky_action"
            and "source_reopen_before_risky_action" in observed
            and not observed_forbidden
        ),
    }

    correct = not blockers
    return {
        "case_hash": f"sha256:{sha256_text(case_id)}",
        "case_family": family,
        "annotation_status": safe_annotation_status,
        "source_family": safe_source_family,
        "source_reviewed": source_reviewed,
        "compaction_boundary_observed": compaction_observed,
        "source_ref_hash_count": ref_hash_count,
        "correct": correct,
        "outcome": "passed" if correct else "failed",
        "blocker_codes": sorted({item["code"] for item in blockers}),
        "failed_metric_codes": sorted(
            metric for metric, passed in metric_results.items() if family == METRIC_FAMILY.get(metric) and not passed
        ),
        "metric_results": {
            metric: passed
            for metric, passed in metric_results.items()
            if family == METRIC_FAMILY.get(metric)
        },
        "sequence_packet_present": bool(sequence_evidence.get("sequence_packet_present")),
        "sequence_contract_ok": bool(sequence_evidence.get("sequence_contract_ok")),
        "order_sensitivity_applicable": bool(
            sequence_evidence.get("order_sensitivity_applicable")
        ),
        "order_sensitivity_passed": bool(sequence_evidence.get("order_sensitivity_passed")),
        "middle_event_gap_applicable": bool(
            sequence_evidence.get("middle_event_gap_applicable")
        ),
        "middle_event_gap_detected": bool(sequence_evidence.get("middle_event_gap_detected")),
        "single_point_trap_applicable": bool(
            sequence_evidence.get("single_point_trap_applicable")
        ),
        "single_point_overclaim": bool(sequence_evidence.get("single_point_overclaim")),
        "supersession_applicable": bool(sequence_evidence.get("supersession_applicable")),
        "supersession_passed": bool(sequence_evidence.get("supersession_passed")),
        "source_ref_chain_coverage": float(sequence_evidence.get("source_ref_chain_coverage") or 0.0),
        "behavior_only_rejection_applicable": bool(
            sequence_evidence.get("behavior_only_rejection_applicable")
        ),
        "behavior_only_rejection_passed": bool(
            sequence_evidence.get("behavior_only_rejection_passed")
        ),
        "cognitive_load_sidecar_present": bool(
            sequence_evidence.get("cognitive_load_sidecar_present")
        ),
        "load_contract_ok": bool(sequence_evidence.get("load_contract_ok")),
        "load_boost_bucket": str(sequence_evidence.get("load_boost_bucket") or "none"),
        "strain_signal_count_total": int(sequence_evidence.get("strain_signal_count_total") or 0),
        "load_reason_code_count": int(sequence_evidence.get("load_reason_code_count") or 0),
        "load_weight_false_positive": bool(sequence_evidence.get("load_weight_false_positive")),
        "load_decay_applied": bool(sequence_evidence.get("load_decay_applied")),
        "overpersonalization_from_load_signal_count": int(
            sequence_evidence.get("overpersonalization_from_load_signal_count") or 0
        ),
        "load_source_truth_override": bool(sequence_evidence.get("load_source_truth_override")),
        "unprompted_overhang_count": len(OVERHANG_CODES & observed),
        "stale_revival_count": len(stale_codes & observed),
        "confabulation_count": len(CONFABULATION_CODES & observed),
    }


def validate_case_pack(case_pack: Mapping[str, Any]) -> dict[str, Any]:
    blockers: list[dict[str, str]] = []
    schema_version = case_pack.get("schema_version")
    if schema_version not in {FIXTURE_SCHEMA_VERSION, SCHEMA_VERSION, "1"}:
        blockers.append(_blocker("unsupported_case_pack_schema", "schema_version"))
    if case_pack.get("kind") != CASE_PACK_KIND:
        blockers.append(_blocker("unsupported_case_pack_kind", "kind"))

    cases = [item for item in _as_list(case_pack.get("cases")) if isinstance(item, Mapping)]
    if not cases:
        blockers.append(_blocker("empty_case_pack", "cases"))
    if len(cases) < MIN_ANNOTATED_SEED_CASES:
        blockers.append(_blocker("below_20_case_seed_target", "cases"))

    families = {str(case.get("case_family") or "") for case in cases}
    annotation_statuses = {str(case.get("annotation_status") or "") for case in cases}
    missing_families = REQUIRED_FAMILIES - families
    if missing_families:
        blockers.append(_blocker("missing_required_case_family", "cases.case_family"))
    if len(families & REQUIRED_FAMILIES) < 3:
        blockers.append(_blocker("below_3_case_family_floor", "cases.case_family"))
    if REQUIRED_ANNOTATION_STATUSES - annotation_statuses:
        blockers.append(_blocker("missing_required_annotation_status", "cases.annotation_status"))
    if "negative_control" not in annotation_statuses:
        blockers.append(_blocker("missing_negative_control_candidate", "cases.annotation_status"))

    return {
        "ok": not blockers,
        "blockers": blockers,
        "blocker_codes": sorted({item["code"] for item in blockers}),
        "case_count": len(cases),
        "case_families": sorted(families),
    }


def summarize_results(rows: list[dict[str, Any]], validation: Mapping[str, Any]) -> dict[str, Any]:
    family_counts: dict[str, int] = {}
    annotation_counts: dict[str, int] = {}
    source_family_counts: dict[str, int] = {}
    for row in rows:
        family = str(row.get("case_family") or "")
        family_counts[family] = family_counts.get(family, 0) + 1
        annotation_status = str(row.get("annotation_status") or "")
        annotation_counts[annotation_status] = annotation_counts.get(annotation_status, 0) + 1
        source_family = str(row.get("source_family") or "")
        source_family_counts[source_family] = source_family_counts.get(source_family, 0) + 1

    metric_counts: dict[str, dict[str, int]] = {}
    for metric, family in METRIC_FAMILY.items():
        applicable = [row for row in rows if row.get("case_family") == family]
        passed = [
            row
            for row in applicable
            if _as_mapping(row.get("metric_results")).get(metric) is True
        ]
        metric_counts[metric] = {"passed": len(passed), "total": len(applicable)}

    row_blockers = sorted(
        {
            code
            for row in rows
            for code in _string_list(row.get("blocker_codes"))
        }
    )
    sequence_rows = [row for row in rows if row.get("sequence_packet_present")]
    load_rows = [row for row in rows if row.get("cognitive_load_sidecar_present")]
    no_remember_rows = [
        row
        for row in rows
        if row.get("case_family") == "benign_non_action_cue"
        and row.get("annotation_status") == "negative_control"
    ]
    order_rows = [row for row in rows if row.get("order_sensitivity_applicable")]
    gap_rows = [row for row in rows if row.get("middle_event_gap_applicable")]
    single_point_rows = [row for row in rows if row.get("single_point_trap_applicable")]
    supersession_rows = [row for row in rows if row.get("supersession_applicable")]
    behavior_only_rows = [row for row in rows if row.get("behavior_only_rejection_applicable")]
    source_ref_coverage = (
        round(
            sum(float(row.get("source_ref_chain_coverage") or 0.0) for row in sequence_rows)
            / len(sequence_rows),
            6,
        )
        if sequence_rows
        else 0.0
    )
    contract_ok = bool(validation.get("ok")) and not row_blockers and all(
        bool(row.get("correct")) for row in rows
    )
    return {
        "ok": contract_ok,
        "status": "case_pack_contract_passed" if contract_ok else "case_pack_incomplete",
        "metrics": {
            "total_cases": len(rows),
            "correct_count": sum(1 for row in rows if row.get("correct")),
            "source_reviewed_case_count": sum(1 for row in rows if row.get("source_reviewed")),
            "compaction_observed_case_count": sum(
                1 for row in rows if row.get("compaction_boundary_observed")
            ),
            "silent_constraint_respected_rate": _rate(
                metric_counts["silent_constraint_respected"]["passed"],
                metric_counts["silent_constraint_respected"]["total"],
            ),
            "known_bad_route_avoided_rate": _rate(
                metric_counts["known_bad_route_avoided"]["passed"],
                metric_counts["known_bad_route_avoided"]["total"],
            ),
            "transient_concern_extinguished_rate": _rate(
                metric_counts["transient_concern_extinguished"]["passed"],
                metric_counts["transient_concern_extinguished"]["total"],
            ),
            "current_rule_selected_rate": _rate(
                metric_counts["current_rule_selected"]["passed"],
                metric_counts["current_rule_selected"]["total"],
            ),
            "scope_limited_constraint_respected_rate": _rate(
                metric_counts["scope_limited_constraint_respected"]["passed"],
                metric_counts["scope_limited_constraint_respected"]["total"],
            ),
            "summary_overhang_trap_avoided_rate": _rate(
                metric_counts["summary_overhang_trap_avoided"]["passed"],
                metric_counts["summary_overhang_trap_avoided"]["total"],
            ),
            "source_reopen_before_risky_action_rate": _rate(
                metric_counts["source_reopen_before_risky_action"]["passed"],
                metric_counts["source_reopen_before_risky_action"]["total"],
            ),
            "no_remember_negative_case_count": len(no_remember_rows),
            "no_remember_negative_pass_count": sum(
                1 for row in no_remember_rows if row.get("correct")
            ),
            "no_remember_negative_precision": _rate(
                sum(1 for row in no_remember_rows if row.get("correct")),
                len(no_remember_rows),
            ),
            "sequence_packet_case_count": len(sequence_rows),
            "order_sensitivity_accuracy": _rate(
                sum(1 for row in order_rows if row.get("order_sensitivity_passed")),
                len(order_rows),
            ),
            "middle_event_gap_detection_rate": _rate(
                sum(1 for row in gap_rows if row.get("middle_event_gap_detected")),
                len(gap_rows),
            ),
            "single_point_overclaim_rate": _rate(
                sum(1 for row in single_point_rows if row.get("single_point_overclaim")),
                len(single_point_rows),
            ),
            "supersession_chain_accuracy": _rate(
                sum(1 for row in supersession_rows if row.get("supersession_passed")),
                len(supersession_rows),
            ),
            "source_ref_chain_coverage": source_ref_coverage,
            "behavior_only_rejection_recall": _rate(
                sum(1 for row in behavior_only_rows if row.get("behavior_only_rejection_passed")),
                len(behavior_only_rows),
            ),
            "cognitive_load_sidecar_case_count": len(load_rows),
            "load_weight_false_positive_rate": _rate(
                sum(1 for row in load_rows if row.get("load_weight_false_positive")),
                len(load_rows),
            ),
            "load_weight_decay_coverage": _rate(
                sum(1 for row in load_rows if row.get("load_decay_applied")),
                len(load_rows),
            ),
            "overpersonalization_from_load_signal_count": sum(
                int(row.get("overpersonalization_from_load_signal_count") or 0)
                for row in load_rows
            ),
            "load_source_truth_override_count": sum(
                1 for row in load_rows if row.get("load_source_truth_override")
            ),
            "unprompted_overhang_count": sum(
                int(row.get("unprompted_overhang_count") or 0) for row in rows
            ),
            "stale_revival_count": sum(int(row.get("stale_revival_count") or 0) for row in rows),
            "confabulation_count": sum(int(row.get("confabulation_count") or 0) for row in rows),
        },
        "coverage": {
            "case_families": sorted(family_counts),
            "family_counts": dict(sorted(family_counts.items())),
            "annotation_status_counts": dict(sorted(annotation_counts.items())),
            "source_family_counts": dict(sorted(source_family_counts.items())),
            "required_families_present": sorted(REQUIRED_FAMILIES & set(family_counts)),
            "missing_required_families": sorted(REQUIRED_FAMILIES - set(family_counts)),
            "behavior_pack_family_floor": len(REQUIRED_FAMILIES),
            "metric_denominators": {
                metric: counts["total"] for metric, counts in sorted(metric_counts.items())
            },
        },
        "blocker_codes": sorted(set(validation.get("blocker_codes") or []) | set(row_blockers)),
    }


def _safe_count_map(value: Any, allowed_keys: tuple[str, ...]) -> dict[str, int]:
    source = _as_mapping(value)
    return {key: _safe_int(source.get(key)) for key in allowed_keys}


def private_annotation_readiness(summary: Mapping[str, Any]) -> dict[str, Any]:
    blocker_status = _as_mapping(summary.get("blocker_status"))
    status = str(summary.get("status") or "private_annotation_unknown")
    if status not in {"private_annotation_blocked", "private_annotation_retained"}:
        status = "private_annotation_unknown"
    retained_shortfall = _safe_int(blocker_status.get("retained_case_shortfall"))
    negative_shortfall = _safe_int(blocker_status.get("negative_control_shortfall"))
    private_text_exported = bool(summary.get("private_text_exported"))
    privacy = str(summary.get("privacy") or "")
    blockers: list[str] = []
    if retained_shortfall:
        blockers.append("private_retained_case_shortfall")
    if negative_shortfall:
        blockers.append("private_negative_control_shortfall")
    if private_text_exported:
        blockers.append("private_text_exported")
    if privacy != PRIVATE_ANNOTATION_PRIVACY:
        blockers.append("private_annotation_privacy_boundary_unknown")
    if status != "private_annotation_retained":
        blockers.append("private_annotation_not_retained")
    blockers = sorted(set(blockers))
    return {
        "status": status,
        "gate_ok": not blockers,
        "privacy": PRIVATE_ANNOTATION_PRIVACY,
        "reviewed_candidate_count": _safe_int(summary.get("reviewed_candidate_count")),
        "retained_case_count": _safe_int(summary.get("retained_case_count")),
        "behavior_seed_count": _safe_int(summary.get("behavior_seed_count")),
        "min_retained_cases": _safe_int(blocker_status.get("min_retained_cases")),
        "retained_case_shortfall": retained_shortfall,
        "min_negative_controls": _safe_int(blocker_status.get("min_negative_controls")),
        "negative_control_shortfall": negative_shortfall,
        "annotation_category_counts": _safe_count_map(
            summary.get("annotation_category_counts"),
            PRIVATE_ANNOTATION_CATEGORIES,
        ),
        "blocker_class_counts": _safe_count_map(
            summary.get("blocker_class_counts"),
            PRIVATE_ANNOTATION_BLOCKER_CLASSES,
        ),
        "blocker_codes": blockers,
        "cannot_claim": [
            "completed_private_history_20_case_pack",
            "private_real_history_behavior_lift",
            "representative_e2e50_sample_quality",
            "live_host_behavior_lift",
        ],
    }


def load_private_field_readiness_artifact(path: Path | str) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("private field readiness artifact must be a JSON object")
    if payload.get("kind") == REPORT_KIND and isinstance(
        payload.get("private_annotation_readiness"),
        Mapping,
    ):
        return dict(payload["private_annotation_readiness"])
    return private_annotation_readiness(payload)


def build_private_local_field_behavior_report(
    *,
    readiness_path: Path | str = DEFAULT_PRIVATE_ANNOTATION_READINESS,
    public_fixture_path: Path | str = DEFAULT_FIXTURE,
) -> dict[str, Any]:
    """Report #1981 field-validation readiness without exposing private rows.

    This is deliberately a field-validation gate, not another public-pack score.
    It consumes the sanitized private/local readiness artifact only at aggregate
    level. If the retained field target is not met, the report succeeds as a
    blocker record while keeping the field-quality gate closed.
    """

    public_report = run_benchmark(fixture_path=public_fixture_path)
    readiness = load_private_field_readiness_artifact(readiness_path)
    annotation_counts = _as_mapping(readiness.get("annotation_category_counts"))
    field_case_count = _safe_int(readiness.get("retained_case_count"))
    negative_control_count = _safe_int(annotation_counts.get("negative_control"))
    behavior_scored_case_count = _safe_int(readiness.get("behavior_seed_count"))
    retained_shortfall = max(0, PRIVATE_FIELD_TARGET_CASES - field_case_count)
    field_family_counts = _as_mapping(readiness.get("case_family_counts"))
    blocker_codes = set(_string_list(readiness.get("blocker_codes")))
    if retained_shortfall:
        blocker_codes.add("private_retained_case_shortfall")
    if not field_family_counts:
        blocker_codes.add("field_case_family_counts_not_available_in_sanitized_summary")
    field_gate_ok = (
        retained_shortfall == 0
        and negative_control_count >= 1
        and bool(field_family_counts)
        and not blocker_codes
    )
    metrics = {
        "field_case_count": field_case_count,
        "retained_control_case_count": field_case_count,
        "retained_case_shortfall": retained_shortfall,
        "negative_control_count": negative_control_count,
        "case_family_counts": dict(field_family_counts),
        "behavior_scored_case_count": behavior_scored_case_count,
        "private_text_leak_count": 0,
        "raw_ref_or_local_path_leak_count": 0,
        "public_fixture_only_case_count": int(public_report["metrics"]["total_cases"]),
        "field_behavior_lift_claimed": False,
        "live_host_behavior_lift_claimed": False,
        "representative_e2e50_quality_claimed": False,
        "semantic_judge_quality_claimed": False,
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "aippocampus_e2e50_private_local_field_behavior_report",
        "created_at": now_utc(),
        "ok": metrics["private_text_leak_count"] == 0
        and metrics["raw_ref_or_local_path_leak_count"] == 0
        and (field_gate_ok or bool(blocker_codes)),
        "status": "field_validation_ready" if field_gate_ok else "field_validation_blocked",
        "field_validation_gate_ok": field_gate_ok,
        "public_contract_gate_ok": bool(public_report.get("contract_gate_ok")),
        "metrics": metrics,
        "private_annotation_readiness": {
            "status": readiness.get("status"),
            "gate_ok": bool(readiness.get("gate_ok")),
            "privacy": readiness.get("privacy"),
            "reviewed_candidate_count": readiness.get("reviewed_candidate_count"),
            "retained_case_count": readiness.get("retained_case_count"),
            "behavior_seed_count": readiness.get("behavior_seed_count"),
            "retained_case_shortfall": retained_shortfall,
            "annotation_category_counts": dict(annotation_counts),
            "blocker_codes": sorted(blocker_codes),
        },
        "sampling_confounds": [
            "sanitized_private_summary_lacks_family_breakdown"
            if not field_family_counts
            else "field_family_breakdown_available",
            "retained_field_case_target_not_met"
            if retained_shortfall
            else "retained_field_case_target_met",
            "ordinary_post_compaction_behavior_scoring_not_enough_for_lift_claim"
            if behavior_scored_case_count < PRIVATE_FIELD_TARGET_CASES
            else "behavior_scoring_target_met",
        ],
        "evidence_separation": {
            "public_safe_contract_pack": "scored_separately",
            "private_local_field_validation": "aggregate_or_blocker_only",
            "private_scarcity_blocks_public_pack": False,
        },
        "privacy_boundary": {
            "private_text_emitted": False,
            "raw_refs_emitted": False,
            "local_paths_emitted": False,
            "provider_payloads_emitted": False,
            "thread_or_message_ids_emitted": False,
        },
        "cannot_claim": [
            "private_history_behavior_lift",
            "representative_e2e50_quality",
            "live_host_behavior_lift",
            "semantic_judge_quality",
        ],
    }


def run_benchmark(
    *,
    fixture_path: Path | str = DEFAULT_FIXTURE,
    case_pack: Mapping[str, Any] | None = None,
    private_annotation_summary: Mapping[str, Any] | None = None,
    include_private_text: bool = False,
) -> dict[str, Any]:
    loaded_case_pack = dict(case_pack) if case_pack is not None else load_fixture(fixture_path)
    validation = validate_case_pack(loaded_case_pack)
    cases = [item for item in _as_list(loaded_case_pack.get("cases")) if isinstance(item, Mapping)]
    rows = [evaluate_case(case) for case in cases]
    summary = summarize_results(rows, validation)
    cannot_claim = list(CANNOT_CLAIM)
    if include_private_text:
        cannot_claim.append("private_text_debug_mode_not_public_evidence")
    can_claim = [
        "deterministic_e2e50_case_pack_contract_scored",
        "public_safe_e2e50_behavior_pack_primary_path_ready",
        "public_safe_synthetic_scorer_fixture_guarded",
        "deterministic_sequence_packet_contract_scored",
        "bounded_cognitive_load_routing_sidecar_guarded",
    ]
    if summary["ok"] and int(summary["metrics"].get("total_cases") or 0) >= MIN_ANNOTATED_SEED_CASES:
        can_claim.append("public_safe_20_case_seed_pack_contract_scored")
    if summary["ok"] and int(summary["metrics"].get("total_cases") or 0) >= PUBLIC_E2E50_TARGET_CASES:
        can_claim.append("public_safe_50_case_behavior_pack_contract_scored")
    private_readiness = (
        private_annotation_readiness(private_annotation_summary)
        if private_annotation_summary is not None
        else None
    )
    if private_readiness is not None:
        can_claim.append("private_local_e2e50_annotation_summary_readiness_recorded")
    status = summary["status"]
    if private_readiness is not None and not private_readiness["gate_ok"]:
        status = f"{status}_private_annotation_blocked"

    payload = {
        "schema_version": SCHEMA_VERSION,
        "kind": REPORT_KIND,
        "created_at": now_utc(),
        "ok": summary["ok"],
        "contract_gate_ok": summary["ok"],
        "quality_gate_ok": False,
        "status": status,
        "claim_level": CLAIM_LEVEL,
        "benchmark_role": {
            "primary_public_path": "public_safe_behavior_pack",
            "private_annotation_role": "optional_diagnostic_not_primary_public_gate",
            "private_case_scarcity_is_not_primary_public_blocker": True,
            "scores_behavior_codes_not_retrieval_only": True,
        },
        "behavior_pack": {
            "fixture_id": str(loaded_case_pack.get("fixture_id") or "in_memory"),
            "min_public_cases": MIN_ANNOTATED_SEED_CASES,
            "public_e2e50_target_cases": PUBLIC_E2E50_TARGET_CASES,
            "public_e2e50_target_met": summary["metrics"]["total_cases"]
            >= PUBLIC_E2E50_TARGET_CASES,
            "case_count": summary["metrics"]["total_cases"],
            "required_families": sorted(REQUIRED_FAMILIES),
            "missing_required_families": summary["coverage"]["missing_required_families"],
            "no_remember_negative_case_count": summary["metrics"][
                "no_remember_negative_case_count"
            ],
            "quality_gate_ok": False,
        },
        "config": {
            "fixture": "default" if case_pack is None else "in_memory",
            "semantic_judge": False,
            "live_host": False,
            "private_annotation_summary": private_readiness is not None,
            "include_private_text": bool(include_private_text),
        },
        "privacy_boundary": {
            "hash_count_only": True,
            "raw_text_emitted": bool(include_private_text),
            "raw_source_refs_emitted": False,
            "absolute_paths_emitted": False,
            "private_thread_ids_emitted": False,
            "raw_tool_output_emitted": False,
            "behavior_trace_emitted": False,
            "episode_chain_emitted": False,
            "sequence_packet_emitted": False,
            "cognitive_load_projection_claims_emitted": False,
            "private_annotation_rows_emitted": False,
        },
        "validation": {
            "ok": validation["ok"],
            "blocker_codes": validation["blocker_codes"],
            "case_count": validation["case_count"],
        },
        "metrics": summary["metrics"],
        "coverage": summary["coverage"],
        "blocker_codes": summary["blocker_codes"],
        "cases": rows,
        "can_claim": can_claim,
        "cannot_claim": cannot_claim,
    }
    if private_readiness is not None:
        payload["private_annotation_readiness"] = private_readiness
    return payload


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Score the #279 E2E50 silent-constraint case pack.")
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument(
        "--private-annotation-summary",
        type=Path,
        help="Sanitized scanner output or private annotation summary JSON; raw annotation rows are not accepted here.",
    )
    parser.add_argument("--include-private-text", action="store_true")
    parser.add_argument(
        "--field-validation",
        action="store_true",
        help="Emit the #1981 private/local field-validation readiness report.",
    )
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    if args.field_validation:
        payload = build_private_local_field_behavior_report(
            public_fixture_path=args.fixture,
            readiness_path=args.private_annotation_summary
            or DEFAULT_PRIVATE_ANNOTATION_READINESS,
        )
    else:
        private_summary = (
            load_private_annotation_summary(args.private_annotation_summary)
            if args.private_annotation_summary
            else None
        )
        payload = run_benchmark(
            fixture_path=args.fixture,
            private_annotation_summary=private_summary,
            include_private_text=args.include_private_text,
        )
    text = json.dumps(payload, ensure_ascii=False, indent=None if args.json else 2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
