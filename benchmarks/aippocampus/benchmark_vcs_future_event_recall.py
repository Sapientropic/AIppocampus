#!/usr/bin/env python3
"""Recall-aware public VCS future-event benchmark for AIppocampus Dream work.

This is the first hard-event scaffold for the public longitudinal-user track.
Unlike the synthetic pseudo-user contract smoke, this runner scores over the
whole future window: every flag-worthy hard event that is not predicted is a
false negative. That prevents a silent Dream layer from winning by precision
alone.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import _paths

_paths.ensure_paths()

from benchmark_statistics import binomial_rate_report, lower_bound_gate

SCHEMA_VERSION = 1
DEFAULT_DATASET = (
    _paths.REPO_ROOT
    / "benchmark_corpus"
    / "public_longitudinal_users"
    / "vcs_future_events_v1.jsonl"
).resolve()
FLAG_DECISIONS = {"flag", "suppress", "unknown"}
HARD_EVENT_KINDS = {
    "pull_request_merged",
    "pull_request_rejected",
    "issue_reopened",
    "commit_reverted",
    "patchset_superseded",
    "satd_comment_removed",
    "tool_call_failed",
    "tool_call_succeeded",
    "test_failed",
    "test_passed",
    "edit_reverted",
    "route_abandoned",
}


@dataclass(frozen=True)
class VcsFutureEventDataset:
    dataset_id: str
    path: Path
    rows: list[dict[str, Any]]
    events_by_id: dict[str, dict[str, Any]]
    flag_worthy_event_ids: set[str]
    non_flag_event_ids: set[str]


@dataclass(frozen=True)
class Prediction:
    prediction_id: str
    event_id: str
    decision: str
    past_source_ids: tuple[str, ...]
    family: str | None = None


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha1_text(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def public_path_label(path: Path | str) -> str:
    resolved = Path(path).resolve()
    try:
        return str(resolved.relative_to(_paths.REPO_ROOT)).replace("\\", "/")
    except ValueError:
        return f"external_dataset:{sha1_text(str(resolved))[:16]}"


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
    return decision if decision in FLAG_DECISIONS else "unknown"


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


def load_dataset(
    path: Path | str = DEFAULT_DATASET,
    *,
    require_cc0: bool = True,
) -> VcsFutureEventDataset:
    dataset_path = Path(path).resolve()
    rows = read_json_or_jsonl(dataset_path)
    if not rows:
        raise ValueError(f"empty VCS future-event dataset: {dataset_path}")

    dataset_ids = {str(row.get("dataset_id") or "") for row in rows}
    dataset_ids.discard("")
    if len(dataset_ids) != 1:
        raise ValueError(f"expected exactly one dataset_id, got {sorted(dataset_ids)}")
    dataset_id = next(iter(dataset_ids))

    project_ids: set[str] = set()
    source_ids: set[str] = set()
    events_by_id: dict[str, dict[str, Any]] = {}
    flag_worthy_event_ids: set[str] = set()
    non_flag_event_ids: set[str] = set()
    errors: list[str] = []

    for row_number, row in enumerate(rows, start=1):
        project_id = str(row.get("project_id") or "")
        if not project_id:
            errors.append(f"row {row_number}: missing project_id")
        if project_id in project_ids:
            errors.append(f"row {row_number}: duplicate project_id {project_id}")
        project_ids.add(project_id)

        license_id = str(row.get("license") or "")
        if not license_id:
            errors.append(f"row {row_number}: missing license")
        elif require_cc0 and license_id.upper() != "CC0-1.0":
            errors.append(f"row {row_number}: fixture rows must be CC0-1.0")

        row_source_ids: set[str] = set()
        row_sources_by_id: dict[str, dict[str, Any]] = {}
        for source in row.get("past_window") or []:
            source_id = str(source.get("source_id") or "")
            if not source_id:
                errors.append(f"row {row_number}: past source missing source_id")
            if source_id in source_ids:
                errors.append(f"row {row_number}: duplicate source_id {source_id}")
            source_ids.add(source_id)
            row_source_ids.add(source_id)
            row_sources_by_id[source_id] = dict(source)

        future_window = row.get("future_window") or []
        if not future_window:
            errors.append(f"row {row_number}: missing future_window")
        for event in future_window:
            event_id = str(event.get("event_id") or "")
            if not event_id:
                errors.append(f"row {row_number}: future event missing event_id")
            if event_id in events_by_id:
                errors.append(f"row {row_number}: duplicate event_id {event_id}")
            hard_event_kind = str(event.get("hard_event_kind") or "")
            if hard_event_kind not in HARD_EVENT_KINDS:
                errors.append(f"row {row_number}: unsupported hard_event_kind {hard_event_kind!r}")
            missing_sources = set(as_string_list(event.get("required_past_source_ids"))) - row_source_ids
            if missing_sources:
                errors.append(
                    f"row {row_number}: event {event_id} references missing past sources "
                    f"{sorted(missing_sources)}"
                )
            for required_source_id in as_string_list(event.get("required_past_source_ids")):
                required_source = row_sources_by_id.get(required_source_id) or {}
                # Agent rollout fixtures may contain assistant narration as context,
                # but narrative-only text cannot be the gold support for a rejected
                # route. Only deterministic behavior traces should support future
                # hard-event labels when the source explicitly declares this boundary.
                if bool(event.get("flag_worthy")) and required_source.get("behavior_backed") is False:
                    errors.append(
                        f"row {row_number}: event {event_id} uses narrative-only source "
                        f"{required_source_id} as required support"
                    )
            enriched = dict(event)
            enriched["project_id"] = project_id
            events_by_id[event_id] = enriched
            if bool(event.get("flag_worthy")):
                flag_worthy_event_ids.add(event_id)
            else:
                non_flag_event_ids.add(event_id)

    if errors:
        raise ValueError("VCS future-event dataset validation failed:\n- " + "\n- ".join(errors))

    return VcsFutureEventDataset(
        dataset_id=dataset_id,
        path=dataset_path,
        rows=rows,
        events_by_id=events_by_id,
        flag_worthy_event_ids=flag_worthy_event_ids,
        non_flag_event_ids=non_flag_event_ids,
    )


def load_predictions(path: Path) -> list[Prediction]:
    predictions: list[Prediction] = []
    seen_prediction_ids: set[str] = set()
    for index, row in enumerate(read_json_or_jsonl(path), start=1):
        event_id = str(row.get("event_id") or "")
        prediction_id = str(row.get("prediction_id") or "") or f"{event_id or 'missing'}:{index}"
        if prediction_id in seen_prediction_ids:
            raise ValueError(f"duplicate prediction_id {prediction_id}")
        seen_prediction_ids.add(prediction_id)
        predictions.append(
            Prediction(
                prediction_id=prediction_id,
                event_id=event_id,
                decision=normalize_decision(row.get("decision")),
                past_source_ids=tuple(sorted(set(as_string_list(row.get("past_source_ids"))))),
                family=str(row.get("family") or "") or None,
            )
        )
    return predictions


def baseline_predictions(dataset: VcsFutureEventDataset, mode: str) -> list[Prediction]:
    if mode == "empty":
        return []
    predictions: list[Prediction] = []
    for event_id in sorted(dataset.flag_worthy_event_ids):
        event = dataset.events_by_id[event_id]
        predictions.append(
            Prediction(
                prediction_id=f"gold:{event_id}",
                event_id=event_id,
                decision="flag",
                past_source_ids=tuple(sorted(as_string_list(event.get("required_past_source_ids")))),
                family=str(event.get("family") or "") or None,
            )
        )
    return predictions


def score_predictions(
    dataset: VcsFutureEventDataset,
    predictions: list[Prediction],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    event_rows: list[dict[str, Any]] = []
    prediction_rows: list[dict[str, Any]] = []

    flagged_by_event: dict[str, list[Prediction]] = {}
    for prediction in predictions:
        if prediction.decision == "flag":
            flagged_by_event.setdefault(prediction.event_id, []).append(prediction)

    for event_id, event in dataset.events_by_id.items():
        flag_worthy = bool(event.get("flag_worthy"))
        event_predictions = flagged_by_event.get(event_id, [])
        best_prediction = event_predictions[0] if event_predictions else None
        required_sources = set(as_string_list(event.get("required_past_source_ids")))
        predicted_sources = set(best_prediction.past_source_ids) if best_prediction else set()
        source_supported = required_sources <= predicted_sources
        flagged = bool(event_predictions)
        true_positive = flag_worthy and flagged and source_supported
        false_negative = flag_worthy and not true_positive
        false_positive = (not flag_worthy) and flagged
        event_rows.append(
            {
                "event_id": event_id,
                "project_id": event.get("project_id"),
                "family": event.get("family"),
                "hard_event_kind": event.get("hard_event_kind"),
                "flag_worthy": flag_worthy,
                "event_text_sha1": sha1_text(str(event.get("text") or ""))[:16],
                "required_past_source_ids": sorted(required_sources),
                "predicted_past_source_ids": sorted(predicted_sources),
                "flagged": flagged,
                "source_supported": source_supported if flagged else False,
                "true_positive": true_positive,
                "false_negative": false_negative,
                "false_positive": false_positive,
                "anti_drift_violation": false_positive,
                "prediction_count": len(event_predictions),
            }
        )

    known_event_ids = set(dataset.events_by_id)
    for prediction in predictions:
        maybe_event = dataset.events_by_id.get(prediction.event_id)
        unknown_event_id = prediction.event_id not in known_event_ids
        non_flag_event = prediction.event_id in dataset.non_flag_event_ids
        flag_worthy = prediction.event_id in dataset.flag_worthy_event_ids
        required_sources = (
            set(as_string_list(maybe_event.get("required_past_source_ids"))) if maybe_event else set()
        )
        predicted_sources = set(prediction.past_source_ids)
        source_supported = required_sources <= predicted_sources if maybe_event else False
        prediction_rows.append(
            {
                "prediction_id": prediction.prediction_id,
                "event_id": prediction.event_id,
                "decision": prediction.decision,
                "family": prediction.family or (maybe_event.get("family") if maybe_event else None),
                "known_event_id": not unknown_event_id,
                "flag_worthy_event": flag_worthy,
                "non_flag_event": non_flag_event,
                "source_supported": source_supported,
                "unknown_event_false_positive": unknown_event_id and prediction.decision == "flag",
                "non_flag_false_positive": non_flag_event and prediction.decision == "flag",
                "missing_required_sources": sorted(required_sources - predicted_sources),
                "extra_past_source_ids": sorted(predicted_sources - required_sources),
            }
        )
    return event_rows, prediction_rows


def summarize(event_rows: list[dict[str, Any]], prediction_rows: list[dict[str, Any]]) -> dict[str, Any]:
    positive_rows = [row for row in event_rows if row["flag_worthy"]]
    non_flag_rows = [row for row in event_rows if not row["flag_worthy"]]
    true_positive_count = sum(1 for row in positive_rows if row["true_positive"])
    false_negative_count = sum(1 for row in positive_rows if row["false_negative"])
    false_positive_count = sum(1 for row in event_rows if row["false_positive"]) + sum(
        1 for row in prediction_rows if row["unknown_event_false_positive"]
    )
    predicted_flag_count = sum(1 for row in prediction_rows if row["decision"] == "flag")
    family_counts: dict[str, dict[str, Any]] = {}
    for row in positive_rows:
        family = str(row.get("family") or "unknown")
        bucket = family_counts.setdefault(
            family,
            {"gold_event_count": 0, "true_positive_count": 0, "false_negative_count": 0},
        )
        bucket["gold_event_count"] += 1
        bucket["true_positive_count"] += int(bool(row["true_positive"]))
        bucket["false_negative_count"] += int(bool(row["false_negative"]))
    for bucket in family_counts.values():
        bucket["recall"] = safe_rate(bucket["true_positive_count"], bucket["gold_event_count"])
    precision = safe_rate(true_positive_count, predicted_flag_count)
    recall = safe_rate(true_positive_count, len(positive_rows))
    f1 = round(2 * precision * recall / (precision + recall), 4) if precision + recall else 0.0
    anti_drift_violation_count = sum(1 for row in non_flag_rows if row["false_positive"])
    rate_estimates = {
        "future_event_flag_recall": binomial_rate_report(
            "future_event_flag_recall",
            numerator=true_positive_count,
            denominator=len(positive_rows),
        ),
        "future_event_flag_precision": binomial_rate_report(
            "future_event_flag_precision",
            numerator=true_positive_count,
            denominator=predicted_flag_count,
        ),
        "anti_drift_pass_rate": binomial_rate_report(
            "anti_drift_pass_rate",
            numerator=sum(1 for row in non_flag_rows if not row["false_positive"]),
            denominator=len(non_flag_rows),
        ),
        "anti_drift_violation_rate": binomial_rate_report(
            "anti_drift_violation_rate",
            numerator=anti_drift_violation_count,
            denominator=len(non_flag_rows),
        ),
    }
    return {
        "total_future_event_count": len(event_rows),
        "future_event_gold_count": len(positive_rows),
        "non_flag_future_event_count": len(non_flag_rows),
        "predicted_flag_count": predicted_flag_count,
        "true_positive_count": true_positive_count,
        "false_negative_count": false_negative_count,
        "false_positive_count": false_positive_count,
        "future_event_flag_recall_rate": recall,
        "future_event_flag_precision": precision,
        "future_event_flag_f1": f1,
        "rate_estimates": rate_estimates,
        "silent_dream_penalty_applies": True,
        "anti_drift_negative_count": len(non_flag_rows),
        "anti_drift_violation_count": anti_drift_violation_count,
        "anti_drift_pass_rate": safe_rate(
            sum(1 for row in non_flag_rows if not row["false_positive"]),
            len(non_flag_rows),
        ),
        "unknown_event_false_positive_count": sum(
            1 for row in prediction_rows if row["unknown_event_false_positive"]
        ),
        "source_support_failure_count": sum(
            1
            for row in prediction_rows
            if row["flag_worthy_event"] and not row["source_supported"]
        ),
        "by_family": family_counts,
    }


def run_benchmark(
    *,
    dataset_path: Path | str = DEFAULT_DATASET,
    predictions_file: Path | str | None = None,
    closed_book_predictions_file: Path | str | None = None,
    baseline: str = "gold",
    require_cc0_dataset: bool = True,
    min_recall: float = 1.0,
    min_precision: float = 1.0,
    max_false_positives: int = 0,
    gate_statistic: str = "point",
) -> dict[str, Any]:
    started = time.perf_counter()
    dataset = load_dataset(dataset_path, require_cc0=require_cc0_dataset)
    predictions = (
        load_predictions(Path(predictions_file).resolve())
        if predictions_file
        else baseline_predictions(dataset, baseline)
    )
    event_rows, prediction_rows = score_predictions(dataset, predictions)
    metrics = summarize(event_rows, prediction_rows)
    closed_book: dict[str, Any] | None = None
    if closed_book_predictions_file:
        closed_book_predictions = load_predictions(Path(closed_book_predictions_file).resolve())
        closed_event_rows, closed_prediction_rows = score_predictions(
            dataset,
            closed_book_predictions,
        )
        closed_metrics = summarize(closed_event_rows, closed_prediction_rows)
        closed_book = {
            "predictions_file_sha1": sha1_text(str(closed_book_predictions_file))[:16],
            "metrics": closed_metrics,
            "source_over_closed_book_lift": {
                "recall": round(
                    float(metrics["future_event_flag_recall_rate"])
                    - float(closed_metrics["future_event_flag_recall_rate"]),
                    4,
                ),
                "precision": round(
                    float(metrics["future_event_flag_precision"])
                    - float(closed_metrics["future_event_flag_precision"]),
                    4,
                ),
                "f1": round(
                    float(metrics["future_event_flag_f1"])
                    - float(closed_metrics["future_event_flag_f1"]),
                    4,
                ),
                "false_negative_reduction": int(closed_metrics["false_negative_count"])
                - int(metrics["false_negative_count"]),
            },
            "interpretation": (
                "If closed-book performance is near source-window performance, "
                "the fixture may be measuring pretrained public knowledge rather "
                "than source-backed recovery."
            ),
        }
    if gate_statistic not in {"point", "lower_bound"}:
        raise ValueError("gate_statistic must be 'point' or 'lower_bound'")
    gate_applied_to_status = gate_statistic == "lower_bound"
    recall_gate = lower_bound_gate(
        metrics["rate_estimates"]["future_event_flag_recall"],
        threshold=min_recall,
        applied_to_status=gate_applied_to_status,
    )
    precision_gate = lower_bound_gate(
        metrics["rate_estimates"]["future_event_flag_precision"],
        threshold=min_precision,
        applied_to_status=gate_applied_to_status,
    )
    if gate_applied_to_status:
        rate_gate_ok = (
            recall_gate["passes_lower_bound"]
            and precision_gate["passes_lower_bound"]
        )
    else:
        rate_gate_ok = (
            recall_gate["passes_point_estimate"]
            and precision_gate["passes_point_estimate"]
        )
    ok = bool(rate_gate_ok and int(metrics["false_positive_count"]) <= int(max_false_positives))
    row_licenses = sorted({str(row.get("license") or "") for row in dataset.rows})
    source_families = sorted({str(row.get("source_family") or "") for row in dataset.rows})
    has_rollout_sources = any("rollout" in source_family for source_family in source_families)
    claim_boundary = (
        "V1 is a hard-event public contract fixture. It proves recall-aware "
        "scoring semantics over deterministic rollout behavior traces, not "
        "live agent quality or private real-history continuity."
        if has_rollout_sources
        else (
            "V1 is a VCS-shaped public contract fixture. It proves recall-aware "
            "scoring semantics, not wild MSR/Gerrit/SATD corpus performance."
        )
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "aippocampus_vcs_future_event_recall_benchmark",
        "generated_at": now_utc(),
        "status": "future_event_recall_scored",
        "ok": ok,
        "quality_gate_ok": ok,
        "config": {
            "dataset_path_sha1": sha1_text(str(Path(dataset_path).resolve()))[:16],
            "predictions_file_sha1": sha1_text(str(predictions_file))[:16]
            if predictions_file
            else None,
            "closed_book_predictions_file_sha1": sha1_text(str(closed_book_predictions_file))[:16]
            if closed_book_predictions_file
            else None,
            "prediction_source": "external_predictions" if predictions_file else f"{baseline}_baseline",
            "baseline": None if predictions_file else baseline,
            "closed_book_ablation": bool(closed_book_predictions_file),
            "require_cc0_dataset": require_cc0_dataset,
            "min_recall": min_recall,
            "min_precision": min_precision,
            "max_false_positives": max_false_positives,
            "gate_statistic": gate_statistic,
            "live_llm": False,
        },
        "dataset": {
            "dataset_id": dataset.dataset_id,
            "fixture": public_path_label(dataset_path),
            "license": row_licenses[0] if len(row_licenses) == 1 else "mixed",
            "source_family": source_families[0] if len(source_families) == 1 else "mixed",
            "project_count": len(dataset.rows),
            "future_event_count": len(dataset.events_by_id),
            "future_event_gold_available": True,
            "hard_event_kinds": sorted({row["hard_event_kind"] for row in event_rows}),
            "claim_boundary": claim_boundary,
        },
        "metrics": metrics,
        "lower_bound_gates": {
            "future_event_flag_recall": recall_gate,
            "future_event_flag_precision": precision_gate,
        },
        "contamination_control": {
            "closed_book_ablation_available": bool(closed_book_predictions_file),
            "closed_book": closed_book,
            "time_split_required_for_public_claims": True,
            "counterfactual_perturbation_required_for_public_claims": True,
            "private_real_history_must_report_separately": True,
            "why": (
                "Public VCS outcomes may be memorized by pretrained models. "
                "Closed-book collapse is the cheap first contamination test; "
                "time splits and counterfactual variants are needed before "
                "wild public-corpus claims."
            ),
        },
        "events": event_rows,
        "predictions": prediction_rows,
        "privacy_boundary": {
            "fixture_contains_private_user_data": False,
            "raw_event_text_emitted": False,
            "raw_past_source_text_emitted": False,
            "absolute_paths_emitted": False,
            "event_ids_are_public": True,
            "output_shape": "sanitized_vcs_future_event_recall_scores",
        },
        "cannot_claim": [
            "wild_vcs_corpus_quality",
            "contamination_resistant_public_score_without_closed_book_lift",
            "private_real_history_coding_continuity_quality",
            "live_dream_worker_quality",
            "external_baseline_superiority",
            "soft_semantic_reopen_support",
        ],
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
    }


def print_human_summary(payload: dict[str, Any]) -> None:
    metrics = payload["metrics"]
    print("AIppocampus VCS future-event recall benchmark")
    print(
        f"- gold_events: {metrics['future_event_gold_count']} "
        f"predicted_flags: {metrics['predicted_flag_count']}"
    )
    print(
        f"- recall: {metrics['future_event_flag_recall_rate']:.2%} "
        f"precision: {metrics['future_event_flag_precision']:.2%} "
        f"f1: {metrics['future_event_flag_f1']:.2%}"
    )
    print(
        f"- false_negatives: {metrics['false_negative_count']} "
        f"false_positives: {metrics['false_positive_count']} "
        f"anti_drift_pass: {metrics['anti_drift_pass_rate']:.2%}"
    )


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--predictions", type=Path, default=None)
    parser.add_argument("--closed-book-predictions", type=Path, default=None)
    parser.add_argument("--baseline", choices=["gold", "empty"], default="gold")
    parser.add_argument(
        "--allow-non-cc0-dataset",
        action="store_true",
        help=(
            "Allow scoring an external public VCS dataset with a non-CC0 license. "
            "Use only for local reports whose raw dataset is not checked into the repo."
        ),
    )
    parser.add_argument("--min-recall", type=float, default=1.0)
    parser.add_argument("--min-precision", type=float, default=1.0)
    parser.add_argument("--max-false-positives", type=int, default=0)
    parser.add_argument(
        "--gate-statistic",
        choices=["point", "lower_bound"],
        default="point",
        help="Use point estimates by default; lower_bound applies Wilson lower bounds to status.",
    )
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--json", action="store_true", dest="json_output")
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    payload = run_benchmark(
        dataset_path=args.dataset,
        predictions_file=args.predictions,
        closed_book_predictions_file=args.closed_book_predictions,
        baseline=args.baseline,
        require_cc0_dataset=not args.allow_non_cc0_dataset,
        min_recall=args.min_recall,
        min_precision=args.min_precision,
        max_false_positives=args.max_false_positives,
        gate_statistic=args.gate_statistic,
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
