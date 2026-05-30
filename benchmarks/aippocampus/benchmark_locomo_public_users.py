#!/usr/bin/env python3
"""LoCoMo public longitudinal-user evidence-retrieval control.

LoCoMo is useful for AIppocampus as a public, same-conversation longitudinal
control: each sample has multi-session dialogue turns plus QA evidence ids. It
does not validate the coding decision-shadow wedge, but it gives outside
projects a reproducible way to test whether a memory layer can retrieve the
right source turns for a long-lived public user without relying on private
chat history.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import _paths

_paths.ensure_paths()

SCHEMA_VERSION = 1
DEFAULT_DATASET = (_paths.REPO_ROOT / "benchmark_corpus" / "locomo" / "locomo10.json").resolve()
SESSION_KEY_RE = re.compile(r"^session_(\d+)$")


@dataclass(frozen=True)
class LocomoCase:
    case_id: str
    user_id: str
    category: str
    question: str
    answer: str
    evidence_ids: tuple[str, ...]
    missing_evidence_ids: tuple[str, ...]


@dataclass(frozen=True)
class LocomoDataset:
    dataset_id: str
    path: Path
    samples: list[dict[str, Any]]
    source_events_by_user: dict[str, dict[str, dict[str, Any]]]
    cases: list[LocomoCase]
    qa_case_count: int
    skipped_case_count: int


@dataclass(frozen=True)
class Prediction:
    case_id: str
    evidence_ids: tuple[str, ...]


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


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


def public_path_label(path: Path | str) -> str:
    resolved = Path(path).resolve()
    try:
        return str(resolved.relative_to(_paths.REPO_ROOT)).replace("\\", "/")
    except ValueError:
        return f"external_dataset:{sha1_text(str(resolved))[:16]}"


def iter_session_items(sample: dict[str, Any]) -> list[tuple[int, str, list[dict[str, Any]]]]:
    conversation = sample.get("conversation") or {}
    sessions: list[tuple[int, str, list[dict[str, Any]]]] = []
    for key, value in conversation.items():
        match = SESSION_KEY_RE.match(str(key))
        if not match or not isinstance(value, list):
            continue
        session_index = int(match.group(1))
        date_time = str(conversation.get(f"session_{session_index}_date_time") or "")
        sessions.append((session_index, date_time, [dict(item) for item in value]))
    return sorted(sessions, key=lambda row: row[0])


def source_events_for_sample(sample: dict[str, Any]) -> dict[str, dict[str, Any]]:
    events: dict[str, dict[str, Any]] = {}
    for session_index, date_time, turns in iter_session_items(sample):
        for turn_index, turn in enumerate(turns, start=1):
            dia_id = str(turn.get("dia_id") or "")
            if not dia_id:
                continue
            events[dia_id] = {
                "source_event_id": dia_id,
                "session_index": session_index,
                "turn_index": turn_index,
                "speaker": str(turn.get("speaker") or ""),
                "date_time": date_time,
                "text": str(turn.get("text") or ""),
            }
    return events


def case_sort_key(case: LocomoCase) -> tuple[str, str]:
    return (case.user_id, case.case_id)


def build_cases(
    samples: list[dict[str, Any]],
    source_events_by_user: dict[str, dict[str, dict[str, Any]]],
    *,
    max_cases: int | None = None,
) -> tuple[list[LocomoCase], int, int]:
    cases: list[LocomoCase] = []
    qa_case_count = 0
    skipped_case_count = 0
    for sample in samples:
        user_id = str(sample.get("sample_id") or "")
        source_events = source_events_by_user.get(user_id, {})
        for qa_index, qa in enumerate(sample.get("qa") or [], start=1):
            qa_case_count += 1
            evidence_ids = tuple(sorted(set(as_string_list(qa.get("evidence")))))
            missing_evidence_ids = tuple(
                sorted(evidence_id for evidence_id in evidence_ids if evidence_id not in source_events)
            )
            if not evidence_ids or missing_evidence_ids:
                skipped_case_count += 1
                continue
            cases.append(
                LocomoCase(
                    case_id=f"locomo:{user_id}:qa:{qa_index:04d}",
                    user_id=user_id,
                    category=str(qa.get("category") or "unknown"),
                    question=str(qa.get("question") or ""),
                    answer=str(qa.get("answer") or ""),
                    evidence_ids=evidence_ids,
                    missing_evidence_ids=missing_evidence_ids,
                )
            )
            if max_cases is not None and len(cases) >= max_cases:
                return cases, qa_case_count, skipped_case_count
    return cases, qa_case_count, skipped_case_count


def load_dataset(
    path: Path | str = DEFAULT_DATASET,
    *,
    max_samples: int | None = None,
    max_cases: int | None = None,
) -> LocomoDataset:
    dataset_path = Path(path).resolve()
    rows = read_json_or_jsonl(dataset_path)
    if max_samples is not None:
        rows = rows[:max_samples]
    if not rows:
        raise ValueError(f"empty LoCoMo dataset: {dataset_path}")

    source_events_by_user: dict[str, dict[str, dict[str, Any]]] = {}
    sample_ids: set[str] = set()
    errors: list[str] = []
    for row_number, sample in enumerate(rows, start=1):
        user_id = str(sample.get("sample_id") or "")
        if not user_id:
            errors.append(f"row {row_number}: missing sample_id")
            continue
        if user_id in sample_ids:
            errors.append(f"row {row_number}: duplicate sample_id {user_id}")
        sample_ids.add(user_id)
        source_events = source_events_for_sample(sample)
        if not source_events:
            errors.append(f"row {row_number}: sample {user_id} has no dialogue source events")
        source_events_by_user[user_id] = source_events

    cases, qa_case_count, skipped_case_count = build_cases(
        rows,
        source_events_by_user,
        max_cases=max_cases,
    )
    if not cases:
        errors.append("no QA cases with linked evidence ids")
    if errors:
        raise ValueError("LoCoMo dataset validation failed:\n- " + "\n- ".join(errors))

    return LocomoDataset(
        dataset_id="locomo_public_longitudinal_users_v1",
        path=dataset_path,
        samples=rows,
        source_events_by_user=source_events_by_user,
        cases=cases,
        qa_case_count=qa_case_count,
        skipped_case_count=skipped_case_count,
    )


def load_predictions(path: Path) -> dict[str, Prediction]:
    predictions: dict[str, Prediction] = {}
    for row in read_json_or_jsonl(path):
        case_id = str(row.get("case_id") or "")
        if not case_id:
            raise ValueError(f"prediction missing case_id in {path}")
        if case_id in predictions:
            raise ValueError(f"duplicate prediction for case_id {case_id}")
        evidence_ids = tuple(
            sorted(set(as_string_list(row.get("evidence_ids") or row.get("source_event_ids"))))
        )
        predictions[case_id] = Prediction(case_id=case_id, evidence_ids=evidence_ids)
    return predictions


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def build_case_pack(dataset: LocomoDataset) -> dict[str, Any]:
    """Build a local input pack for external systems without gold evidence ids.

    The pack intentionally includes LoCoMo dialogue and question text, so it is
    written only when the caller provides an output path. It excludes answers
    and gold evidence ids to keep evaluation labels out of the model-facing
    input.
    """

    users: list[dict[str, Any]] = []
    for sample in dataset.samples:
        user_id = str(sample.get("sample_id") or "")
        source_events = dataset.source_events_by_user.get(user_id, {})
        users.append(
            {
                "user_id": user_id,
                "sessions": [
                    {
                        "session_index": session_index,
                        "date_time": date_time,
                        "source_events": [
                            {
                                "source_event_id": str(turn.get("dia_id") or ""),
                                "speaker": str(turn.get("speaker") or ""),
                                "text": str(turn.get("text") or ""),
                            }
                            for turn in turns
                            if str(turn.get("dia_id") or "") in source_events
                        ],
                    }
                    for session_index, date_time, turns in iter_session_items(sample)
                ],
            }
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "aippocampus_locomo_public_users_case_pack",
        "generated_at": now_utc(),
        "dataset": {
            "dataset_id": dataset.dataset_id,
            "source_family": "LoCoMo",
            "fixture": public_path_label(dataset.path),
            "license": "CC BY-NC 4.0",
            "raw_dataset_git_policy": "ignored_or_external",
        },
        "users": users,
        "cases": [
            {
                "case_id": case.case_id,
                "user_id": case.user_id,
                "category": case.category,
                "question": case.question,
                "question_sha1": sha1_text(case.question)[:16],
            }
            for case in sorted(dataset.cases, key=case_sort_key)
        ],
        "label_boundary": {
            "gold_evidence_ids_included": False,
            "answer_text_included": False,
            "prediction_field": "evidence_ids",
            "prediction_template": {"case_id": "<case id>", "evidence_ids": []},
        },
        "privacy_boundary": {
            "fixture_contains_private_user_data": False,
            "raw_dialogue_text_emitted": True,
            "raw_question_text_emitted": True,
            "raw_answer_text_emitted": False,
            "absolute_paths_emitted": False,
            "intended_storage": "local .tmp/ or benchmark_corpus/reports/ output only",
        },
        "cannot_claim": [
            "redistributable_under_aippocampus_license",
            "answer_generation_quality",
            "coding_decision_shadow_quality",
        ],
    }


def build_prediction_template(dataset: LocomoDataset) -> list[dict[str, Any]]:
    return [
        {
            "case_id": case.case_id,
            "user_id": case.user_id,
            "category": case.category,
            "question_sha1": sha1_text(case.question)[:16],
            "evidence_ids": [],
        }
        for case in sorted(dataset.cases, key=case_sort_key)
    ]


def baseline_predictions(dataset: LocomoDataset, mode: str) -> dict[str, Prediction]:
    predictions: dict[str, Prediction] = {}
    for case in dataset.cases:
        predictions[case.case_id] = Prediction(
            case_id=case.case_id,
            evidence_ids=() if mode == "empty" else case.evidence_ids,
        )
    return predictions


def score_case(
    case: LocomoCase,
    prediction: Prediction,
    *,
    include_public_text: bool,
) -> dict[str, Any]:
    expected = set(case.evidence_ids)
    predicted = set(prediction.evidence_ids)
    missing = sorted(expected - predicted)
    extra = sorted(predicted - expected)
    true_positive_count = len(expected & predicted)
    recall = safe_rate(true_positive_count, len(expected))
    precision = safe_rate(true_positive_count, len(predicted))
    full_recall = not missing
    exact_match = full_recall and not extra
    result: dict[str, Any] = {
        "case_id": case.case_id,
        "user_id": case.user_id,
        "category": case.category,
        "question_sha1": sha1_text(case.question)[:16],
        "answer_sha1": sha1_text(case.answer)[:16],
        "expected_evidence_ids": list(case.evidence_ids),
        "predicted_evidence_ids": sorted(predicted),
        "missing_evidence_ids": missing,
        "extra_evidence_ids": extra,
        "evidence_recall": recall,
        "evidence_precision": precision,
        "full_evidence_recall": full_recall,
        "exact_evidence_match": exact_match,
        "case_score": 1.0 if exact_match else round((recall + precision) / 2, 4),
    }
    if include_public_text:
        result["question"] = case.question
        result["answer"] = case.answer
    return result


def summarize_results(
    results: list[dict[str, Any]],
    dataset: LocomoDataset,
    predictions: dict[str, Prediction],
) -> dict[str, Any]:
    by_category: dict[str, dict[str, Any]] = {}
    for row in results:
        category = str(row.get("category") or "unknown")
        bucket = by_category.setdefault(
            category,
            {
                "case_count": 0,
                "full_recall_count": 0,
                "exact_match_count": 0,
                "recall_sum": 0.0,
                "precision_sum": 0.0,
            },
        )
        bucket["case_count"] += 1
        bucket["full_recall_count"] += int(bool(row["full_evidence_recall"]))
        bucket["exact_match_count"] += int(bool(row["exact_evidence_match"]))
        bucket["recall_sum"] += float(row["evidence_recall"])
        bucket["precision_sum"] += float(row["evidence_precision"])
    for bucket in by_category.values():
        bucket["full_evidence_recall_rate"] = safe_rate(
            bucket["full_recall_count"],
            bucket["case_count"],
        )
        bucket["exact_match_rate"] = safe_rate(bucket["exact_match_count"], bucket["case_count"])
        bucket["mean_evidence_recall"] = round(bucket["recall_sum"] / bucket["case_count"], 4)
        bucket["mean_evidence_precision"] = round(
            bucket["precision_sum"] / bucket["case_count"],
            4,
        )
        del bucket["recall_sum"]
        del bucket["precision_sum"]

    source_event_count = sum(len(events) for events in dataset.source_events_by_user.values())
    session_count = sum(len(iter_session_items(sample)) for sample in dataset.samples)
    return {
        "sample_count": len(dataset.samples),
        "longitudinal_public_user_count": len(dataset.samples),
        "session_count": session_count,
        "source_event_count": source_event_count,
        "qa_case_count": dataset.qa_case_count,
        "scored_case_count": len(results),
        "skipped_case_count": dataset.skipped_case_count,
        "provided_prediction_count": len(predictions),
        "missing_prediction_count": sum(1 for row in results if not row["predicted_evidence_ids"]),
        "extra_prediction_case_count": len(set(predictions) - {str(case.case_id) for case in dataset.cases}),
        "full_evidence_recall_rate": safe_rate(
            sum(1 for row in results if row["full_evidence_recall"]),
            len(results),
        ),
        "exact_evidence_match_rate": safe_rate(
            sum(1 for row in results if row["exact_evidence_match"]),
            len(results),
        ),
        "mean_evidence_recall": round(
            sum(float(row["evidence_recall"]) for row in results) / len(results),
            4,
        )
        if results
        else 0.0,
        "mean_evidence_precision": round(
            sum(float(row["evidence_precision"]) for row in results) / len(results),
            4,
        )
        if results
        else 0.0,
        "false_positive_evidence_id_count": sum(len(row["extra_evidence_ids"]) for row in results),
        "missing_evidence_id_count": sum(len(row["missing_evidence_ids"]) for row in results),
        "by_category": by_category,
        "headline_score_allowed": False,
        "track_role": "public_longitudinal_conversation_control",
    }


def unavailable_payload(dataset_path: Path | str, started: float) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "aippocampus_locomo_public_users_benchmark",
        "generated_at": now_utc(),
        "status": "dataset_unavailable",
        "ok": False,
        "quality_gate_ok": False,
        "config": {
            "dataset": public_path_label(dataset_path),
            "live_llm": False,
        },
        "dataset": {
            "dataset_id": "locomo_public_longitudinal_users_v1",
            "fixture": public_path_label(dataset_path),
            "source_family": "LoCoMo",
            "raw_dataset_git_policy": "ignored_or_external",
        },
        "metrics": {},
        "cases": [],
        "privacy_boundary": {
            "raw_dialogue_text_emitted": False,
            "raw_question_text_emitted": False,
            "absolute_paths_emitted": False,
            "output_shape": "dataset-unavailable diagnostic",
        },
        "cannot_claim": [
            "public_longitudinal_user_score",
            "answer_generation_quality",
            "coding_decision_shadow_quality",
        ],
        "next_step": (
            "Download LoCoMo locomo10.json from the official source into "
            "benchmark_corpus/locomo/ or pass --dataset to a local copy."
        ),
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
    }


def run_benchmark(
    *,
    dataset_path: Path | str = DEFAULT_DATASET,
    predictions_file: Path | str | None = None,
    baseline: str = "gold",
    max_samples: int | None = None,
    max_cases: int | None = None,
    include_public_text: bool = False,
    min_full_recall: float = 1.0,
    min_exact_match: float = 1.0,
    case_pack_output: Path | str | None = None,
    prediction_template_output: Path | str | None = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    dataset_path = Path(dataset_path)
    if not dataset_path.exists():
        return unavailable_payload(dataset_path, started)

    dataset = load_dataset(dataset_path, max_samples=max_samples, max_cases=max_cases)
    case_pack_path: Path | None = None
    if case_pack_output:
        case_pack_path = Path(case_pack_output)
        case_pack_path.parent.mkdir(parents=True, exist_ok=True)
        case_pack_path.write_text(
            json.dumps(build_case_pack(dataset), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    prediction_template_path: Path | None = None
    if prediction_template_output:
        prediction_template_path = Path(prediction_template_output)
        write_jsonl(prediction_template_path, build_prediction_template(dataset))

    if predictions_file:
        prediction_source = "external_predictions"
        predictions = load_predictions(Path(predictions_file).resolve())
    else:
        prediction_source = f"{baseline}_baseline"
        predictions = baseline_predictions(dataset, baseline)

    results: list[dict[str, Any]] = []
    for case in dataset.cases:
        prediction = predictions.get(case.case_id) or Prediction(case.case_id, ())
        results.append(score_case(case, prediction, include_public_text=include_public_text))

    metrics = summarize_results(results, dataset, predictions)
    ok = (
        float(metrics["full_evidence_recall_rate"]) >= float(min_full_recall)
        and float(metrics["exact_evidence_match_rate"]) >= float(min_exact_match)
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "aippocampus_locomo_public_users_benchmark",
        "generated_at": now_utc(),
        "status": "public_longitudinal_control_scored",
        "ok": ok,
        "quality_gate_ok": ok,
        "config": {
            "dataset": public_path_label(dataset_path),
            "predictions_file_sha1": sha1_text(str(predictions_file))[:16]
            if predictions_file
            else None,
            "prediction_source": prediction_source,
            "baseline": None if predictions_file else baseline,
            "max_samples": max_samples,
            "max_cases": max_cases,
            "include_public_text": include_public_text,
            "case_pack_output_sha1": sha1_text(str(case_pack_output))[:16]
            if case_pack_output
            else None,
            "prediction_template_output_sha1": sha1_text(str(prediction_template_output))[:16]
            if prediction_template_output
            else None,
            "min_full_recall": min_full_recall,
            "min_exact_match": min_exact_match,
            "live_llm": False,
        },
        "dataset": {
            "dataset_id": dataset.dataset_id,
            "fixture": public_path_label(dataset.path),
            "source_family": "LoCoMo",
            "official_source": "https://github.com/snap-research/locomo",
            "license": "CC BY-NC 4.0",
            "track_role": "public_longitudinal_conversation_control",
            "raw_dataset_git_policy": "ignored_or_external",
            "claim_boundary": (
                "LoCoMo supplies public same-conversation longitudinal users "
                "with QA evidence dialogue ids. This runner scores evidence "
                "retrieval only; it is a control for long-term conversation "
                "source recovery, not coding tacit-constraint recall."
            ),
        },
        "metrics": metrics,
        "cases": results,
        "privacy_boundary": {
            "fixture_contains_private_user_data": False,
            "raw_dialogue_text_emitted": False,
            "raw_question_text_emitted": bool(include_public_text),
            "raw_answer_text_emitted": bool(include_public_text),
            "absolute_paths_emitted": False,
            "case_ids_are_public": True,
            "output_shape": "sanitized_public_longitudinal_user_evidence_scores",
            "case_pack_raw_text_emitted": bool(case_pack_path),
            "prediction_template_raw_text_emitted": False,
        },
        "artifacts": {
            "case_pack_written": bool(case_pack_path),
            "case_pack_path": public_path_label(case_pack_path) if case_pack_path else None,
            "prediction_template_written": bool(prediction_template_path),
            "prediction_template_path": public_path_label(prediction_template_path)
            if prediction_template_path
            else None,
        },
        "cannot_claim": [
            "answer_generation_quality",
            "coding_decision_shadow_quality",
            "private_real_history_quality",
            "real_human_same_user_identity",
            "flag_recall_over_future_hard_events",
            "external_baseline_superiority",
            "single_headline_wedge_validation",
        ],
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
    }


def print_human_summary(payload: dict[str, Any]) -> None:
    print("AIppocampus LoCoMo public longitudinal-users control")
    if payload.get("status") == "dataset_unavailable":
        print(f"- status: {payload['status']}")
        print(f"- next: {payload['next_step']}")
        return
    metrics = payload["metrics"]
    print(
        f"- users: {metrics['longitudinal_public_user_count']} "
        f"sessions: {metrics['session_count']} cases: {metrics['scored_case_count']}"
    )
    print(
        f"- full_recall: {metrics['full_evidence_recall_rate']:.2%} "
        f"exact_match: {metrics['exact_evidence_match_rate']:.2%} "
        f"mean_recall: {metrics['mean_evidence_recall']:.2%}"
    )
    print(
        f"- missing_evidence_ids: {metrics['missing_evidence_id_count']} "
        f"false_positive_evidence_ids: {metrics['false_positive_evidence_id_count']}"
    )


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--predictions", type=Path, default=None)
    parser.add_argument("--baseline", choices=["gold", "empty"], default="gold")
    parser.add_argument("--max-samples", type=int, default=None)
    parser.add_argument("--max-cases", type=int, default=None)
    parser.add_argument("--include-public-text", action="store_true")
    parser.add_argument("--min-full-recall", type=float, default=1.0)
    parser.add_argument("--min-exact-match", type=float, default=1.0)
    parser.add_argument(
        "--case-pack-output",
        type=Path,
        default=None,
        help=(
            "Write a local LoCoMo input pack for external systems. The pack "
            "contains raw LoCoMo dialogue and question text, but no answers or "
            "gold evidence ids; keep it out of git."
        ),
    )
    parser.add_argument(
        "--prediction-template-output",
        type=Path,
        default=None,
        help="Write JSONL rows with case_id and empty evidence_ids for external predictions.",
    )
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--json", action="store_true", dest="json_output")
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    payload = run_benchmark(
        dataset_path=args.dataset,
        predictions_file=args.predictions,
        baseline=args.baseline,
        max_samples=args.max_samples,
        max_cases=args.max_cases,
        include_public_text=args.include_public_text,
        min_full_recall=args.min_full_recall,
        min_exact_match=args.min_exact_match,
        case_pack_output=args.case_pack_output,
        prediction_template_output=args.prediction_template_output,
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
