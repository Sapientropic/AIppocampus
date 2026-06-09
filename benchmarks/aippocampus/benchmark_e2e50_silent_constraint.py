#!/usr/bin/env python3
"""Deterministic #279 E2E50 silent-constraint case-pack scorer.

This runner is a public-safe scaffold for manually annotated E2E50 seeds. It
scores behavior-code traces only; it does not read private clean-source text,
run a semantic judge, call a live host, or claim representative benchmark
quality. Private calibration should feed the same schema with hash/count-only
rows and keep raw source material outside the repository.
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
CLAIM_LEVEL = "public_synthetic_case_pack_scaffold_only"
DEFAULT_FIXTURE = _paths.REPO_ROOT / "benchmark_corpus" / "e2e50_silent_constraint" / "fixture.json"
MIN_ANNOTATED_SEED_CASES = 20

REQUIRED_FAMILIES = {
    "binding_constraint_survival",
    "behavior_backed_rejected_route",
    "transient_concern_extinction",
    "superseded_currentness",
    "same_topic_drift_trap",
    "benign_non_action_cue",
    "source_reopen_before_risky_action",
}
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
    "source_reopen_before_risky_action": "source_reopen_before_risky_action",
}
OVERHANG_CODES = {"unprompted_overhang", "temporary_concern_rementioned"}
STALE_REVIVAL_CODES = {"stale_rule_selected", "stale_rule_revival", "stale_scope_generalized"}
CONFABULATION_CODES = {"confabulated_source", "unsupported_source_claim"}
CANNOT_CLAIM = [
    "e2e50_behavior_benchmark_quality",
    "manually_annotated_case_pack_ready",
    "private_real_history_behavior_lift",
    "representative_e2e50_sample_quality",
    "completed_50_case_e2e50_sample",
    "live_host_behavior_lift",
    "live_host_timing_or_annoyance_lift",
    "semantic_judge_quality",
    "all_codex_clients_or_host_surfaces",
    "post_compact_warmup_packet_available_before_next_action",
    "episode_arc_as_truth_layer",
    "current_validity_without_source_reopen",
    "cognitive_load_as_emotion_or_personality_truth",
]


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
    if family not in REQUIRED_FAMILIES:
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
            "source_reopen_before_risky_action_rate": _rate(
                metric_counts["source_reopen_before_risky_action"]["passed"],
                metric_counts["source_reopen_before_risky_action"]["total"],
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
            "metric_denominators": {
                metric: counts["total"] for metric, counts in sorted(metric_counts.items())
            },
        },
        "blocker_codes": sorted(set(validation.get("blocker_codes") or []) | set(row_blockers)),
    }


def run_benchmark(
    *,
    fixture_path: Path | str = DEFAULT_FIXTURE,
    case_pack: Mapping[str, Any] | None = None,
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
        "public_safe_synthetic_scorer_fixture_guarded",
        "deterministic_sequence_packet_contract_scored",
        "bounded_cognitive_load_routing_sidecar_guarded",
    ]
    if summary["ok"] and int(summary["metrics"].get("total_cases") or 0) >= MIN_ANNOTATED_SEED_CASES:
        can_claim.append("public_safe_20_case_seed_pack_contract_scored")

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": REPORT_KIND,
        "created_at": now_utc(),
        "ok": summary["ok"],
        "contract_gate_ok": summary["ok"],
        "quality_gate_ok": False,
        "status": summary["status"],
        "claim_level": CLAIM_LEVEL,
        "config": {
            "fixture": "default" if case_pack is None else "in_memory",
            "semantic_judge": False,
            "live_host": False,
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


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Score the #279 E2E50 silent-constraint case pack.")
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--include-private-text", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    payload = run_benchmark(fixture_path=args.fixture, include_private_text=args.include_private_text)
    text = json.dumps(payload, ensure_ascii=False, indent=None if args.json else 2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
