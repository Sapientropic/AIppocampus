#!/usr/bin/env python3
"""H1/H2 hard-negative discipline contract benchmark.

This runner is the first public-safe slice for GitHub #244. It validates a
small synthetic fixture and scores deterministic example outputs. It is not a
live model benchmark and does not claim real-history H1/H2 quality.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

import _paths

_paths.ensure_paths()

SCHEMA_VERSION = 1
FIXTURE_SCHEMA_VERSION = "aippocampus.hippocampal_hard_negative_fixture.v1"
DEFAULT_FIXTURE = (
    _paths.REPO_ROOT / "benchmark_corpus" / "hippocampal_hard_negatives" / "fixture.json"
)
REQUIRED_FAMILIES = {
    "near_neighbor_lure",
    "said_but_unsupported",
    "superseded_currentness_trap",
    "surface_paraphrase_lure",
}
PRODUCTION_LIKE_MIN_CASES_PER_FAMILY = 3
OUTCOME_CATEGORIES = (
    "correct_evidence",
    "honest_scent",
    "honest_skip",
    "wrong_source_evidence",
    "stale_as_current",
    "unsupported_as_fact",
    "confabulation",
)
MAJOR_FAILURE_OUTCOMES = {
    "wrong_source_evidence",
    "stale_as_current",
    "unsupported_as_fact",
    "confabulation",
}
OUTCOME_WEIGHTS = {
    "correct_evidence": 1.0,
    "honest_scent": 0.6,
    "honest_skip": 0.4,
    "wrong_source_evidence": -4.0,
    "stale_as_current": -5.0,
    "unsupported_as_fact": -5.0,
    "confabulation": -6.0,
}
REQUIRED_CASE_FIELDS = {
    "case_id",
    "family",
    "degradation_level",
    "interference_level",
    "query",
    "expected_decision",
    "target_source_refs",
    "acceptable_scent_refs",
    "distractor_source_refs",
    "unsupported_source_refs",
    "forbidden_claims",
    "currentness",
    "ambiguity_policy",
    "truth_source",
    "scorer_allowed_inputs",
}
STALE_CURRENTNESS = {"superseded", "disputed", "historical_only"}
STALE_VISIBILITY = {"demote", "scent_only", "hidden_from_default_recall"}


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha1_text(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8", errors="replace")).hexdigest()


def _as_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value] if value.strip() else []
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item or "").strip()]


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def load_fixture(path: str | Path = DEFAULT_FIXTURE) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected object fixture: {path}")
    return payload


def cases_by_id(fixture: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    return {
        str(case.get("case_id")): case
        for case in fixture.get("cases") or []
        if isinstance(case, Mapping) and case.get("case_id")
    }


def _currentness_schema_present(fixture: Mapping[str, Any]) -> bool:
    schema = _as_mapping(fixture.get("currentness_schema"))
    return all(
        set(_as_list(schema.get(field)))
        for field in ("memory_event_type", "currentness", "visibility_policy")
    )


def validate_fixture(fixture: Mapping[str, Any]) -> dict[str, Any]:
    blockers: list[dict[str, str]] = []
    missing_required_fields: dict[str, list[str]] = {}
    if fixture.get("schema_version") != FIXTURE_SCHEMA_VERSION:
        blockers.append(
            {
                "code": "unsupported_fixture_schema_version",
                "field": "schema_version",
                "message": "Unsupported hippocampal hard-negative fixture schema.",
            }
        )

    cases = [case for case in fixture.get("cases") or [] if isinstance(case, Mapping)]
    family_counts = _family_counts(cases)
    case_ids = [str(case.get("case_id") or "") for case in cases]
    if len(set(case_ids)) != len(case_ids):
        blockers.append(
            {
                "code": "duplicate_case_id",
                "field": "cases.case_id",
                "message": "Case ids must be unique.",
            }
        )

    families_present = {str(case.get("family") or "") for case in cases if case.get("family")}
    missing_families = REQUIRED_FAMILIES - families_present
    if missing_families:
        blockers.append(
            {
                "code": "missing_hard_negative_family",
                "field": "cases.family",
                "message": "Fixture must include all four #244 hard-negative families.",
            }
        )

    for case in cases:
        missing = sorted(field for field in REQUIRED_CASE_FIELDS if field not in case)
        if missing:
            missing_required_fields[str(case.get("case_id") or "<missing>")] = missing
        if str(case.get("truth_source") or "") != "human_authored_synthetic_fixture":
            blockers.append(
                {
                    "code": "non_independent_truth_source",
                    "field": f"cases.{case.get('case_id')}.truth_source",
                    "message": "Primary labels must come from the frozen synthetic fixture.",
                }
            )
        currentness = _as_mapping(case.get("currentness"))
        if not _as_mapping(currentness.get("source_ref_currentness")):
            blockers.append(
                {
                    "code": "missing_currentness_labels",
                    "field": f"cases.{case.get('case_id')}.currentness",
                    "message": "Each case must label source-ref currentness.",
                }
            )

    if missing_required_fields:
        blockers.append(
            {
                "code": "case_missing_required_field",
                "field": "cases",
                "message": "One or more cases is missing required #244 fields.",
            }
        )

    config = _as_mapping(fixture.get("config"))
    truth_source_independent = (
        not bool(config.get("uses_model_judge"))
        and all(
            str(case.get("truth_source") or "") == "human_authored_synthetic_fixture"
            for case in cases
        )
    )
    if not truth_source_independent:
        blockers.append(
            {
                "code": "model_judge_primary_truth",
                "field": "config.uses_model_judge",
                "message": "A model judge cannot be the primary truth source.",
            }
        )

    return {
        "ok": not blockers,
        "blockers": blockers,
        "blocker_codes": sorted({item["code"] for item in blockers}),
        "case_count": len(cases),
        "family_counts": family_counts,
        "families_present": families_present,
        "missing_families": missing_families,
        "missing_required_fields": missing_required_fields,
        "truth_source_independent": truth_source_independent,
        "currentness_schema_present": _currentness_schema_present(fixture),
    }


def _claim_hits_forbidden(case: Mapping[str, Any], response: Mapping[str, Any]) -> bool:
    forbidden = [item.casefold() for item in _as_list(case.get("forbidden_claims"))]
    claims = [item.casefold() for item in _as_list(response.get("claims"))]
    return any(forbidden_item in claim for forbidden_item in forbidden for claim in claims)


def _source_ref_currentness(case: Mapping[str, Any]) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    currentness = _as_mapping(case.get("currentness"))
    return (
        _as_mapping(currentness.get("source_ref_currentness")),
        _as_mapping(currentness.get("source_ref_visibility_policy")),
    )


def _has_stale_current_evidence(case: Mapping[str, Any], evidence_refs: set[str]) -> bool:
    currentness_by_ref, visibility_by_ref = _source_ref_currentness(case)
    return any(
        str(currentness_by_ref.get(ref) or "") in STALE_CURRENTNESS
        or str(visibility_by_ref.get(ref) or "") in STALE_VISIBILITY
        for ref in evidence_refs
    )


def _family_counts(cases: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    counts = {family: 0 for family in sorted(REQUIRED_FAMILIES)}
    for case in cases:
        family = str(case.get("family") or "")
        if family:
            counts[family] = counts.get(family, 0) + 1
    return counts


def _score_payload(outcome: str, *, reasons: Sequence[str], matched_refs: set[str]) -> dict[str, Any]:
    return {
        "outcome": outcome,
        "score": OUTCOME_WEIGHTS[outcome],
        "reasons": list(reasons),
        "matched_ref_hashes": [sha1_text(ref)[:16] for ref in sorted(matched_refs)],
    }


def score_response(case: Mapping[str, Any], response: Mapping[str, Any]) -> dict[str, Any]:
    decision = str(response.get("decision") or "skip")
    evidence_refs = set(_as_list(response.get("evidence_refs")))
    scent_refs = set(_as_list(response.get("scent_refs")))
    target_refs = set(_as_list(case.get("target_source_refs")))
    acceptable_scent_refs = set(_as_list(case.get("acceptable_scent_refs")))
    distractor_refs = set(_as_list(case.get("distractor_source_refs")))
    unsupported_refs = set(_as_list(case.get("unsupported_source_refs")))
    acceptable_uncertainty = set(_as_list(case.get("acceptable_uncertainty")))
    source_reopened = bool(response.get("source_reopened"))

    if _claim_hits_forbidden(case, response):
        return _score_payload(
            "confabulation",
            reasons=["claim_matches_forbidden_fixture_claim"],
            matched_refs=evidence_refs | scent_refs,
        )
    if decision == "evidence" and (evidence_refs & unsupported_refs or not evidence_refs):
        return _score_payload(
            "unsupported_as_fact",
            reasons=["evidence_promotes_unsupported_or_unreferenced_claim"],
            matched_refs=evidence_refs,
        )
    if decision == "evidence" and _has_stale_current_evidence(case, evidence_refs):
        return _score_payload(
            "stale_as_current",
            reasons=["evidence_uses_superseded_or_hidden_ref_as_current"],
            matched_refs=evidence_refs,
        )
    if decision == "evidence" and evidence_refs & distractor_refs and not evidence_refs & target_refs:
        return _score_payload(
            "wrong_source_evidence",
            reasons=["evidence_selects_distractor_without_target_ref"],
            matched_refs=evidence_refs & distractor_refs,
        )
    if decision == "evidence" and evidence_refs and not source_reopened:
        return _score_payload(
            "unsupported_as_fact",
            reasons=["evidence_answer_without_successful_source_reopen"],
            matched_refs=evidence_refs,
        )
    if decision == "evidence" and evidence_refs & target_refs:
        return _score_payload(
            "correct_evidence",
            reasons=["evidence_reopens_expected_target_ref"],
            matched_refs=evidence_refs & target_refs,
        )
    if decision == "scent":
        scent_hit_refs = (scent_refs | evidence_refs) & (acceptable_scent_refs | target_refs)
        if scent_hit_refs or "scent" in acceptable_uncertainty:
            return _score_payload(
                "honest_scent",
                reasons=["uncertain_response_stays_below_evidence"],
                matched_refs=scent_hit_refs,
            )
    if decision == "skip" and (
        "skip" in acceptable_uncertainty or str(case.get("expected_decision")) == "skip"
    ):
        return _score_payload(
            "honest_skip",
            reasons=["uncertain_response_abstains_instead_of_forcing_evidence"],
            matched_refs=set(),
        )
    if decision == "skip":
        return _score_payload(
            "honest_skip",
            reasons=["abstention_is_safer_than_unsupported_evidence"],
            matched_refs=set(),
        )
    return _score_payload(
        "confabulation",
        reasons=["response_does_not_match_any_source_backed_outcome"],
        matched_refs=evidence_refs | scent_refs,
    )


def _sanitized_case_result(
    example: Mapping[str, Any],
    case: Mapping[str, Any],
    score: Mapping[str, Any],
    *,
    include_private_text: bool,
) -> dict[str, Any]:
    query = str(case.get("query") or "")
    payload: dict[str, Any] = {
        "example_id": example.get("example_id"),
        "case_id": case.get("case_id"),
        "family": case.get("family"),
        "degradation_level": case.get("degradation_level"),
        "interference_level": case.get("interference_level"),
        "expected_decision": case.get("expected_decision"),
        "actual_decision": example.get("decision"),
        "source_reopened": bool(example.get("source_reopened")),
        "outcome": score.get("outcome"),
        "score": score.get("score"),
        "query_sha1": sha1_text(query)[:16],
        "matched_ref_hashes": score.get("matched_ref_hashes") or [],
    }
    if include_private_text:
        payload["query"] = query
        payload["claims"] = _as_list(example.get("claims"))
    return payload


def _quality_gates(validation: Mapping[str, Any], outcome_counts: Mapping[str, int]) -> dict[str, Any]:
    return {
        "fixture_valid": bool(validation.get("ok")),
        "all_required_families_present": not bool(validation.get("missing_families")),
        "production_like_family_floor_met": all(
            count >= PRODUCTION_LIKE_MIN_CASES_PER_FAMILY
            for count in _as_mapping(validation.get("family_counts")).values()
        ),
        "all_outcome_categories_reported": set(outcome_counts) == set(OUTCOME_CATEGORIES),
        "asymmetric_penalty_contract": (
            OUTCOME_WEIGHTS["honest_skip"] > OUTCOME_WEIGHTS["wrong_source_evidence"]
            and OUTCOME_WEIGHTS["honest_scent"] > OUTCOME_WEIGHTS["unsupported_as_fact"]
            and OUTCOME_WEIGHTS["wrong_source_evidence"] < 0
            and OUTCOME_WEIGHTS["confabulation"] < OUTCOME_WEIGHTS["wrong_source_evidence"]
        ),
        "truth_source_independent": bool(validation.get("truth_source_independent")),
    }


def _score_example_set(
    examples: Sequence[Any],
    cases: Mapping[str, Mapping[str, Any]],
    *,
    include_private_text: bool,
) -> dict[str, Any]:
    outcome_counts = {outcome: 0 for outcome in OUTCOME_CATEGORIES}
    outcome_counts_by_family = {
        family: {outcome: 0 for outcome in OUTCOME_CATEGORIES}
        for family in sorted(REQUIRED_FAMILIES)
    }
    scored_examples_by_family = {family: 0 for family in sorted(REQUIRED_FAMILIES)}
    case_results: list[dict[str, Any]] = []
    discipline_score = 0.0
    evidence_decision_count = 0
    source_reopen_count = 0
    evidence_without_reopen_count = 0
    target_source_reopen_count = 0
    for example in examples:
        if not isinstance(example, Mapping):
            continue
        case = cases.get(str(example.get("case_id") or ""))
        if not case:
            continue
        score = score_response(case, example)
        outcome = str(score["outcome"])
        family = str(case.get("family") or "")
        outcome_counts[outcome] += 1
        if family:
            scored_examples_by_family[family] = scored_examples_by_family.get(family, 0) + 1
            if family not in outcome_counts_by_family:
                outcome_counts_by_family[family] = {
                    item: 0 for item in OUTCOME_CATEGORIES
                }
            outcome_counts_by_family[family][outcome] += 1
        if str(example.get("decision") or "") == "evidence":
            evidence_decision_count += 1
            if bool(example.get("source_reopened")):
                source_reopen_count += 1
            else:
                evidence_without_reopen_count += 1
        if outcome == "correct_evidence" and bool(example.get("source_reopened")):
            target_source_reopen_count += 1
        discipline_score += float(score["score"])
        case_results.append(
            _sanitized_case_result(
                example,
                case,
                score,
                include_private_text=include_private_text,
            )
        )

    return {
        "outcome_counts": outcome_counts,
        "outcome_counts_by_family": outcome_counts_by_family,
        "metrics": {
            "scored_example_count": len(case_results),
            "scored_examples_by_family": scored_examples_by_family,
            "outcome_counts_by_family": outcome_counts_by_family,
            "discipline_score": round(discipline_score, 6),
            "major_failure_count": sum(outcome_counts[item] for item in MAJOR_FAILURE_OUTCOMES),
            "wrong_source_evidence_count": outcome_counts["wrong_source_evidence"],
            "stale_as_current_count": outcome_counts["stale_as_current"],
            "unsupported_as_fact_count": outcome_counts["unsupported_as_fact"],
            "confabulation_count": outcome_counts["confabulation"],
            "honest_scent_count": outcome_counts["honest_scent"],
            "honest_skip_count": outcome_counts["honest_skip"],
            "honest_uncertainty_count": outcome_counts["honest_scent"] + outcome_counts["honest_skip"],
            "correct_evidence_count": outcome_counts["correct_evidence"],
            "evidence_decision_count": evidence_decision_count,
            "source_reopen_count": source_reopen_count,
            "target_source_reopen_count": target_source_reopen_count,
            "evidence_without_reopen_count": evidence_without_reopen_count,
            "evidence_source_reopen_rate": (
                round(source_reopen_count / evidence_decision_count, 6)
                if evidence_decision_count
                else 0.0
            ),
        },
        "cases": case_results,
    }


def run_benchmark(
    *,
    fixture_path: str | Path = DEFAULT_FIXTURE,
    include_private_text: bool = False,
) -> dict[str, Any]:
    fixture = load_fixture(fixture_path)
    validation = validate_fixture(fixture)
    cases = cases_by_id(fixture)
    case_family_counts = _family_counts(list(cases.values()))
    contract_slice = _score_example_set(
        fixture.get("scorer_examples") or [],
        cases,
        include_private_text=include_private_text,
    )
    production_slice = _score_example_set(
        fixture.get("production_outputs") or [],
        cases,
        include_private_text=include_private_text,
    )
    outcome_counts = contract_slice["outcome_counts"]
    metrics = {
        "case_count": int(validation.get("case_count") or 0),
        "scored_example_count": contract_slice["metrics"]["scored_example_count"],
        "family_counts": case_family_counts,
        **contract_slice["metrics"],
        "production_slice": {
            **production_slice["metrics"],
            "case_count": int(validation.get("case_count") or 0),
            "family_counts": case_family_counts,
        },
    }
    quality_gates = _quality_gates(validation, outcome_counts)
    ok = all(bool(value) for value in quality_gates.values())
    cannot_claim = [
        "public production-like synthetic slice only; cannot claim real-history H1/H2 quality",
        "does not run a live model, semantic retriever, or private registry",
        "does not prove the full 50-scene / 350-case hippocampal P1 matrix",
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "aippocampus_hippocampal_hard_negative_benchmark",
        "status": "production_like_public_synthetic_slice" if ok else "failed_contract_smoke",
        "ok": ok,
        "generated_at": now_utc(),
        "config": {
            "fixture": "hippocampal_hard_negatives/fixture.json",
            "uses_model_judge": False,
            "uses_private_history": False,
            "include_private_text": include_private_text,
            "claim_surface": _as_mapping(fixture.get("config")).get("claim_surface"),
            "production_like_min_cases_per_family": PRODUCTION_LIKE_MIN_CASES_PER_FAMILY,
        },
        "fixture_validation": {
            "ok": bool(validation.get("ok")),
            "case_count": validation.get("case_count"),
            "family_counts": validation.get("family_counts"),
            "families_present": sorted(validation.get("families_present") or []),
            "missing_families": sorted(validation.get("missing_families") or []),
            "blocker_codes": validation.get("blocker_codes") or [],
            "currentness_schema_present": bool(validation.get("currentness_schema_present")),
        },
        "outcome_weights": dict(OUTCOME_WEIGHTS),
        "outcome_counts": outcome_counts,
        "metrics": metrics,
        "quality_gates": quality_gates,
        "cases": contract_slice["cases"],
        "production_slice": {
            "claim_level": "public_production_like_synthetic_diagnostic",
            "outcome_counts": production_slice["outcome_counts"],
            "metrics": metrics["production_slice"],
            "cases": production_slice["cases"],
            "cannot_claim": [
                "real_history_h1_h2_recall_discrimination_quality",
                "live_model_or_semantic_retriever_quality",
                "full_50_scene_350_case_p1_matrix",
            ],
        },
        "privacy_boundary": {
            "raw_query_text_emitted": include_private_text,
            "raw_source_text_emitted": False,
            "absolute_paths_emitted": False,
            "source_ref_hashes_only": not include_private_text,
        },
        "cannot_claim": cannot_claim,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", default=str(DEFAULT_FIXTURE))
    parser.add_argument("--include-private-text", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args()

    payload = run_benchmark(
        fixture_path=args.fixture,
        include_private_text=bool(args.include_private_text),
    )
    if args.json_output:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"{payload['kind']}: {payload['status']}")
        print(f"score: {payload['metrics']['discipline_score']}")
        print(f"major failures: {payload['metrics']['major_failure_count']}")
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
