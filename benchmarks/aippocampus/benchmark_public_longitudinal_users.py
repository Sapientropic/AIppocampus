#!/usr/bin/env python3
"""Public longitudinal pseudo-user scoring-contract smoke.

The fixture is small on purpose: it is a checked-in, public-safe contract for
the hardest AIppocampus coding-agent scenario from
docs/research/agent-coding-context-analysis.md. Systems are expected to recover
source-backed hidden engineering knowledge such as rejected routes, tacit
constraints, workaround rationale, stale corrections, and reopen conditions
without drifting into unrelated future work.

This runner is not the flagship Dream-recall benchmark. It checks the public
prediction/report contract and source attribution shape. The recall-aware
flagship track must use VCS-derived future-event gold where all flag-worthy
holdout events are enumerable, so safe silence can be scored as a miss.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import _paths

_paths.ensure_paths()

SCHEMA_VERSION = 1
TRACK_ROLE = "scoring_contract_smoke"
NEXT_FLAGSHIP_TRACK = "vcs_future_event_recall"
DEFAULT_DATASET = (
    _paths.REPO_ROOT
    / "benchmark_corpus"
    / "public_longitudinal_users"
    / "coding_implicit_v1.jsonl"
).resolve()
EXPECTED_DECISIONS = {"surface", "suppress", "reopen", "unknown"}
CLAIM_CATEGORIES = {
    "rejected_route",
    "tacit_constraint",
    "workaround_rationale",
    "stale_assumption_corrected",
}


@dataclass(frozen=True)
class PublicLongitudinalDataset:
    dataset_id: str
    path: Path
    user_rows: list[dict[str, Any]]
    claims_by_id: dict[str, dict[str, Any]]
    probes: list[dict[str, Any]]


@dataclass(frozen=True)
class Prediction:
    case_id: str
    decision: str
    claim_ids: tuple[str, ...]
    source_event_ids: tuple[str, ...]


def now_utc() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha1_text(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def safe_rate(numerator: int | float, denominator: int | float) -> float:
    return round(float(numerator) / float(denominator), 4) if denominator else 0.0


def as_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list | tuple):
        return [str(item) for item in value if str(item)]
    return [str(value)]


def normalize_decision(value: Any) -> str:
    decision = str(value or "unknown").strip().lower()
    if decision in {"abstain", "missing", "skip"}:
        return "unknown" if decision != "skip" else "suppress"
    return decision if decision in EXPECTED_DECISIONS else "unknown"


def read_json_or_jsonl(path: Path) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return []
    if text.startswith("["):
        rows = json.loads(text)
        if not isinstance(rows, list):
            raise ValueError(f"expected JSON array in {path}")
        return [dict(row) for row in rows]
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def load_dataset(path: Path | str = DEFAULT_DATASET) -> PublicLongitudinalDataset:
    dataset_path = Path(path).resolve()
    rows = read_json_or_jsonl(dataset_path)
    if not rows:
        raise ValueError(f"empty public longitudinal dataset: {dataset_path}")

    dataset_ids = {str(row.get("dataset_id") or "") for row in rows}
    dataset_ids.discard("")
    if len(dataset_ids) != 1:
        raise ValueError(f"expected exactly one dataset_id, got {sorted(dataset_ids)}")
    dataset_id = next(iter(dataset_ids))

    claims_by_id: dict[str, dict[str, Any]] = {}
    probes: list[dict[str, Any]] = []
    event_ids: set[str] = set()
    case_ids: set[str] = set()
    user_ids: set[str] = set()
    errors: list[str] = []

    for row_number, row in enumerate(rows, start=1):
        user_id = str(row.get("user_id") or "")
        if not user_id:
            errors.append(f"row {row_number}: missing user_id")
        if user_id in user_ids:
            errors.append(f"row {row_number}: duplicate user_id {user_id}")
        user_ids.add(user_id)

        if str(row.get("license") or "").upper() != "CC0-1.0":
            errors.append(f"row {row_number}: fixture rows must be CC0-1.0")

        for episode in row.get("episodes") or []:
            for event in episode.get("source_events") or []:
                event_id = str(event.get("event_id") or "")
                if not event_id:
                    errors.append(f"row {row_number}: source event missing event_id")
                if event_id in event_ids:
                    errors.append(f"row {row_number}: duplicate event_id {event_id}")
                event_ids.add(event_id)

        for claim in row.get("gold_claims") or []:
            claim_id = str(claim.get("claim_id") or "")
            category = str(claim.get("category") or "")
            if not claim_id:
                errors.append(f"row {row_number}: gold claim missing claim_id")
            if claim_id in claims_by_id:
                errors.append(f"row {row_number}: duplicate claim_id {claim_id}")
            if category not in CLAIM_CATEGORIES:
                errors.append(f"row {row_number}: unknown claim category {category!r}")
            missing_sources = set(as_string_list(claim.get("source_event_ids"))) - event_ids
            if missing_sources:
                errors.append(
                    f"row {row_number}: claim {claim_id} references missing events "
                    f"{sorted(missing_sources)}"
                )
            enriched = dict(claim)
            enriched["user_id"] = user_id
            claims_by_id[claim_id] = enriched

        for probe in row.get("probes") or []:
            case_id = str(probe.get("case_id") or "")
            if not case_id:
                errors.append(f"row {row_number}: probe missing case_id")
            if case_id in case_ids:
                errors.append(f"row {row_number}: duplicate case_id {case_id}")
            case_ids.add(case_id)

            expected_decision = normalize_decision(probe.get("expected_decision"))
            if expected_decision != str(probe.get("expected_decision") or ""):
                errors.append(f"row {row_number}: invalid expected_decision for {case_id}")

            missing_claims = set(as_string_list(probe.get("required_claim_ids"))) - set(
                claims_by_id
            )
            if missing_claims:
                errors.append(
                    f"row {row_number}: probe {case_id} references missing required "
                    f"claims {sorted(missing_claims)}"
                )
            enriched_probe = dict(probe)
            enriched_probe["user_id"] = user_id
            probes.append(enriched_probe)

    if errors:
        raise ValueError("public longitudinal dataset validation failed:\n- " + "\n- ".join(errors))

    return PublicLongitudinalDataset(
        dataset_id=dataset_id,
        path=dataset_path,
        user_rows=rows,
        claims_by_id=claims_by_id,
        probes=probes,
    )


def load_predictions(path: Path) -> dict[str, Prediction]:
    predictions: dict[str, Prediction] = {}
    for row in read_json_or_jsonl(path):
        case_id = str(row.get("case_id") or "")
        if not case_id:
            raise ValueError(f"prediction missing case_id in {path}")
        if case_id in predictions:
            raise ValueError(f"duplicate prediction for case_id {case_id}")
        predictions[case_id] = Prediction(
            case_id=case_id,
            decision=normalize_decision(row.get("decision")),
            claim_ids=tuple(sorted(set(as_string_list(row.get("claim_ids"))))),
            source_event_ids=tuple(sorted(set(as_string_list(row.get("source_event_ids"))))),
        )
    return predictions


def source_events_for_claims(
    claim_ids: list[str] | tuple[str, ...],
    claims_by_id: dict[str, dict[str, Any]],
) -> list[str]:
    source_ids: set[str] = set()
    for claim_id in claim_ids:
        claim = claims_by_id.get(claim_id) or {}
        source_ids.update(as_string_list(claim.get("source_event_ids")))
    return sorted(source_ids)


def baseline_predictions(
    dataset: PublicLongitudinalDataset,
    mode: str,
) -> dict[str, Prediction]:
    predictions: dict[str, Prediction] = {}
    for probe in dataset.probes:
        case_id = str(probe["case_id"])
        if mode == "empty":
            predictions[case_id] = Prediction(case_id, "unknown", (), ())
            continue
        required_claim_ids = tuple(sorted(set(as_string_list(probe.get("required_claim_ids")))))
        predictions[case_id] = Prediction(
            case_id=case_id,
            decision=normalize_decision(probe.get("expected_decision")),
            claim_ids=required_claim_ids,
            source_event_ids=tuple(source_events_for_claims(required_claim_ids, dataset.claims_by_id)),
        )
    return predictions


def score_probe(
    probe: dict[str, Any],
    prediction: Prediction,
    claims_by_id: dict[str, dict[str, Any]],
    *,
    include_public_text: bool,
) -> dict[str, Any]:
    required_claim_ids = set(as_string_list(probe.get("required_claim_ids")))
    forbidden_claim_ids = set(as_string_list(probe.get("forbidden_claim_ids")))
    predicted_claim_ids = set(prediction.claim_ids)
    unknown_claim_ids = predicted_claim_ids - set(claims_by_id)
    required_present = required_claim_ids <= predicted_claim_ids
    forbidden_present = forbidden_claim_ids & predicted_claim_ids

    expected_source_event_ids = set(source_events_for_claims(sorted(required_claim_ids), claims_by_id))
    predicted_source_event_ids = set(prediction.source_event_ids)
    missing_source_event_ids = expected_source_event_ids - predicted_source_event_ids
    extra_source_event_ids = predicted_source_event_ids - expected_source_event_ids

    expected_decision = normalize_decision(probe.get("expected_decision"))
    decision_correct = prediction.decision == expected_decision
    anti_drift_violation = expected_decision == "suppress" and (
        prediction.decision in {"surface", "reopen"}
        or bool(predicted_claim_ids)
        or bool(predicted_source_event_ids)
    )
    extra_known_claim_ids = predicted_claim_ids - required_claim_ids - forbidden_claim_ids
    correct = (
        decision_correct
        and required_present
        and not missing_source_event_ids
        and not extra_source_event_ids
        and not forbidden_present
        and not unknown_claim_ids
        and not extra_known_claim_ids
        and not anti_drift_violation
    )

    required_claim_recall = safe_rate(
        len(required_claim_ids & predicted_claim_ids),
        len(required_claim_ids),
    ) if required_claim_ids else 1.0
    claim_precision = (
        safe_rate(len(required_claim_ids & predicted_claim_ids), len(predicted_claim_ids))
        if predicted_claim_ids
        else (1.0 if not required_claim_ids else 0.0)
    )
    source_event_recall = (
        safe_rate(
            len(expected_source_event_ids & predicted_source_event_ids),
            len(expected_source_event_ids),
        )
        if expected_source_event_ids
        else 1.0
    )
    source_event_precision = (
        safe_rate(
            len(expected_source_event_ids & predicted_source_event_ids),
            len(predicted_source_event_ids),
        )
        if predicted_source_event_ids
        else (1.0 if not expected_source_event_ids else 0.0)
    )
    drift_guard = 0.0 if (anti_drift_violation or forbidden_present or unknown_claim_ids) else 1.0
    case_score = round(
        (
            float(decision_correct)
            + required_claim_recall
            + claim_precision
            + source_event_recall
            + source_event_precision
            + drift_guard
        )
        / 6,
        4,
    )

    row = {
        "case_id": probe["case_id"],
        "user_id": probe["user_id"],
        "probe_type": probe.get("probe_type"),
        "expected_decision": expected_decision,
        "actual_decision": prediction.decision,
        "probe_sha1": sha1_text(str(probe.get("probe") or ""))[:16],
        "required_claim_ids": sorted(required_claim_ids),
        "predicted_claim_ids": sorted(predicted_claim_ids),
        "required_claims_present": required_present,
        "forbidden_claim_violation": bool(forbidden_present),
        "forbidden_claim_ids_present": sorted(forbidden_present),
        "unknown_claim_ids": sorted(unknown_claim_ids),
        "extra_known_claim_ids": sorted(extra_known_claim_ids),
        "expected_source_event_ids": sorted(expected_source_event_ids),
        "predicted_source_event_ids": sorted(predicted_source_event_ids),
        "missing_source_event_ids": sorted(missing_source_event_ids),
        "extra_source_event_ids": sorted(extra_source_event_ids),
        "decision_correct": decision_correct,
        "anti_drift_violation": anti_drift_violation,
        "required_claim_recall": required_claim_recall,
        "claim_precision": claim_precision,
        "source_event_recall": source_event_recall,
        "source_event_precision": source_event_precision,
        "case_score": case_score,
        "correct": correct,
    }
    if include_public_text:
        row["probe"] = probe.get("probe")
    return row


def summarize_results(results: list[dict[str, Any]], dataset: PublicLongitudinalDataset) -> dict[str, Any]:
    total = len(results)
    correct = sum(1 for row in results if row["correct"])
    by_probe_type: dict[str, dict[str, Any]] = {}
    for row in results:
        probe_type = str(row.get("probe_type") or "unknown")
        bucket = by_probe_type.setdefault(
            probe_type,
            {"case_count": 0, "correct_count": 0, "case_score_sum": 0.0},
        )
        bucket["case_count"] += 1
        bucket["correct_count"] += int(bool(row["correct"]))
        bucket["case_score_sum"] += float(row["case_score"])
    for bucket in by_probe_type.values():
        bucket["accuracy"] = safe_rate(bucket["correct_count"], bucket["case_count"])
        bucket["mean_case_score"] = round(
            bucket["case_score_sum"] / bucket["case_count"],
            4,
        )
        del bucket["case_score_sum"]

    category_counts: dict[str, int] = {}
    for probe in dataset.probes:
        for claim_id in as_string_list(probe.get("required_claim_ids")):
            category = str((dataset.claims_by_id.get(claim_id) or {}).get("category") or "unknown")
            category_counts[category] = category_counts.get(category, 0) + 1

    expected_surface = [row for row in results if row["expected_decision"] in {"surface", "reopen"}]
    expected_suppress = [row for row in results if row["expected_decision"] == "suppress"]
    source_required = [row for row in results if row["expected_source_event_ids"]]
    return {
        "total_cases": total,
        "pseudo_user_count": len({row["user_id"] for row in results}),
        "gold_claim_count": len(dataset.claims_by_id),
        "claim_categories": category_counts,
        "track_role": TRACK_ROLE,
        "headline_score_allowed": False,
        "future_event_gold_available": False,
        "future_event_gold_count": 0,
        "future_event_recall_rate": None,
        "correct_count": correct,
        "accuracy": safe_rate(correct, total),
        "overall_score": round(
            sum(float(row["case_score"]) for row in results) / total,
            4,
        )
        if total
        else 0.0,
        "decision_accuracy": safe_rate(
            sum(1 for row in results if row["decision_correct"]),
            total,
        ),
        "required_claim_full_recall_rate": safe_rate(
            sum(1 for row in expected_surface if row["required_claims_present"]),
            len(expected_surface),
        ),
        "source_event_full_recall_rate": safe_rate(
            sum(1 for row in source_required if not row["missing_source_event_ids"]),
            len(source_required),
        ),
        "source_event_false_positive_count": sum(
            1 for row in results if row["extra_source_event_ids"]
        ),
        "forbidden_claim_violation_count": sum(
            1 for row in results if row["forbidden_claim_violation"]
        ),
        "unknown_claim_id_count": sum(len(row["unknown_claim_ids"]) for row in results),
        "extra_known_claim_count": sum(len(row["extra_known_claim_ids"]) for row in results),
        "anti_drift_case_count": len(expected_suppress),
        "anti_drift_pass_rate": safe_rate(
            sum(1 for row in expected_suppress if not row["anti_drift_violation"]),
            len(expected_suppress),
        ),
        "reopen_case_count": sum(1 for row in results if row["expected_decision"] == "reopen"),
        "reopen_decision_accuracy": safe_rate(
            sum(
                1
                for row in results
                if row["expected_decision"] == "reopen" and row["decision_correct"]
            ),
            sum(1 for row in results if row["expected_decision"] == "reopen"),
        ),
        "by_probe_type": by_probe_type,
        "aggregation_boundary": (
            "Use by_probe_type / family metrics for interpretation. The synthetic "
            "v1 overall_score is a contract-smoke diagnostic, not a flagship "
            "wedge metric for Dream recall."
        ),
    }


def run_benchmark(
    *,
    dataset_path: Path | str = DEFAULT_DATASET,
    predictions_file: Path | str | None = None,
    baseline: str = "gold",
    include_public_text: bool = False,
    min_score: float = 1.0,
    max_forbidden_claim_violations: int = 0,
    max_source_event_false_positives: int = 0,
) -> dict[str, Any]:
    started = time.perf_counter()
    dataset = load_dataset(dataset_path)
    if predictions_file:
        prediction_source = "external_predictions"
        predictions = load_predictions(Path(predictions_file).resolve())
    else:
        prediction_source = f"{baseline}_baseline"
        predictions = baseline_predictions(dataset, baseline)

    results = []
    missing_prediction_count = 0
    for probe in dataset.probes:
        case_id = str(probe["case_id"])
        prediction = predictions.get(case_id)
        if prediction is None:
            missing_prediction_count += 1
            prediction = Prediction(case_id, "unknown", (), ())
        results.append(
            score_probe(
                probe,
                prediction,
                dataset.claims_by_id,
                include_public_text=include_public_text,
            )
        )

    metrics = summarize_results(results, dataset)
    ok = (
        float(metrics["overall_score"]) >= float(min_score)
        and int(metrics["forbidden_claim_violation_count"]) <= max_forbidden_claim_violations
        and int(metrics["source_event_false_positive_count"]) <= max_source_event_false_positives
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "aippocampus_public_longitudinal_users_benchmark",
        "generated_at": now_utc(),
        "status": "contract_smoke_scored",
        "ok": ok,
        "quality_gate_ok": ok,
        "config": {
            "dataset_path_sha1": sha1_text(str(dataset.path))[:16],
            "predictions_file_sha1": sha1_text(str(predictions_file))[:16]
            if predictions_file
            else None,
            "prediction_source": prediction_source,
            "baseline": None if predictions_file else baseline,
            "include_public_text": include_public_text,
            "min_score": min_score,
            "max_forbidden_claim_violations": max_forbidden_claim_violations,
            "max_source_event_false_positives": max_source_event_false_positives,
            "live_llm": False,
        },
        "dataset": {
            "dataset_id": dataset.dataset_id,
            "track_role": TRACK_ROLE,
            "next_flagship_track": NEXT_FLAGSHIP_TRACK,
            "fixture": "benchmark_corpus/public_longitudinal_users/coding_implicit_v1.jsonl",
            "license": "CC0-1.0",
            "pseudo_user_count": len(dataset.user_rows),
            "probe_count": len(dataset.probes),
            "gold_claim_count": len(dataset.claims_by_id),
            "future_event_gold_available": False,
            "source_strategy": (
                "checked-in public synthetic pseudo-users with explicit source events "
                "and gold labels. This is a scoring-contract smoke; the flagship "
                "recall track should use VCS-derived hard future events such as "
                "merge/reject/reopen/revert/supersede/removal."
            ),
        },
        "metrics": metrics,
        "cases": results,
        "prediction_diagnostics": {
            "provided_prediction_count": len(predictions),
            "missing_prediction_count": missing_prediction_count,
            "extra_prediction_case_count": len(set(predictions) - {str(p["case_id"]) for p in dataset.probes}),
        },
        "privacy_boundary": {
            "fixture_contains_private_user_data": False,
            "raw_prompt_emitted": bool(include_public_text),
            "absolute_paths_emitted": False,
            "case_ids_are_public": True,
            "source_event_text_emitted": False,
            "output_shape": "sanitized_public_pseudo_user_scores",
        },
        "cannot_claim": [
            "answer_generation_quality",
            "external_baseline_superiority",
            "flag_recall_over_complete_future_window",
            "flagship_benchmark_readiness",
            "future_event_reopen_recall",
            "live_dream_worker_quality",
            "private_user_memory_quality",
            "real_same_user_longitudinal_identity",
            "single_headline_wedge_validation",
            "synthetic_fixture_generalization",
            "tacit_workaround_recall_over_vcs_history",
        ],
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
    }


def print_human_summary(payload: dict[str, Any]) -> None:
    metrics = payload["metrics"]
    print("AIppocampus public longitudinal pseudo-user contract smoke")
    print(f"- users: {metrics['pseudo_user_count']} cases: {metrics['total_cases']}")
    print(
        f"- accuracy: {metrics['accuracy']:.2%} contract_score: "
        f"{metrics['overall_score']:.2%} decision_accuracy: {metrics['decision_accuracy']:.2%}"
    )
    print(
        "- anti_drift_pass: {anti:.2%} reopen_accuracy: {reopen:.2%} forbidden: {forbidden}".format(
            anti=metrics["anti_drift_pass_rate"],
            reopen=metrics["reopen_decision_accuracy"],
            forbidden=metrics["forbidden_claim_violation_count"],
        )
    )


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--predictions", type=Path, default=None)
    parser.add_argument("--baseline", choices=["gold", "empty"], default="gold")
    parser.add_argument("--include-public-text", action="store_true")
    parser.add_argument("--min-score", type=float, default=1.0)
    parser.add_argument("--max-forbidden-claim-violations", type=int, default=0)
    parser.add_argument("--max-source-event-false-positives", type=int, default=0)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--json", action="store_true", dest="json_output")
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    payload = run_benchmark(
        dataset_path=args.dataset,
        predictions_file=args.predictions,
        baseline=args.baseline,
        include_public_text=args.include_public_text,
        min_score=args.min_score,
        max_forbidden_claim_violations=args.max_forbidden_claim_violations,
        max_source_event_false_positives=args.max_source_event_false_positives,
    )
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    if args.json_output:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print_human_summary(payload)
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
