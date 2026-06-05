#!/usr/bin/env python3
"""LoCoMo answer-usefulness prototype over source-evidence retrieval.

This runner is deliberately second-stage: it scores whether a fixed answer
path used retrieved context well, while keeping the existing LoCoMo Track B
source-evidence runner as the source-retrieval owner. The deterministic judge
below is a CI-safe prototype, not a live LLM judge and not source truth.
"""

from __future__ import annotations

import argparse
import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import _paths
import benchmark_locomo_public_users as locomo

_paths.ensure_paths()

SCHEMA_VERSION = 1
DEFAULT_DATASET = locomo.DEFAULT_DATASET
DEFAULT_ANSWER_MODEL = "deterministic_oracle_fixture"
DETERMINISTIC_JUDGE_MODEL = "deterministic_locomo_answer_usefulness_v1"
NEGATION_TOKENS = {"no", "not", "never", "none", "without", "n't"}
LIGHT_STOPWORDS = {
    "a",
    "an",
    "and",
    "of",
    "on",
    "the",
    "to",
    "was",
    "were",
}


@dataclass(frozen=True)
class AnswerPrediction:
    case_id: str
    arm: str
    retrieved_evidence_ids: tuple[str, ...]
    answer_text: str
    citation_ids: tuple[str, ...]
    refused: bool


def normalize_answer(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").casefold()).strip()


def answer_matches_gold(answer_text: str, gold_answer: str) -> bool:
    answer = normalize_answer(answer_text)
    gold = normalize_answer(gold_answer)
    return bool(answer and gold and gold in answer)


def answer_tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", normalize_answer(text))


def stem_token(token: str) -> str:
    for suffix in ("ing", "ed", "es", "s"):
        if len(token) > len(suffix) + 3 and token.endswith(suffix):
            return token[: -len(suffix)]
    return token


def content_tokens(text: str) -> list[str]:
    return [
        stem_token(token)
        for token in answer_tokens(text)
        if token and token not in LIGHT_STOPWORDS
    ]


def has_negation_trap(answer_text: str, gold_answer: str) -> bool:
    tokens = answer_tokens(answer_text)
    gold = set(content_tokens(gold_answer))
    if not tokens or not gold:
        return False
    stemmed_tokens = [stem_token(token) for token in tokens]
    for index, token in enumerate(stemmed_tokens):
        if token not in gold:
            continue
        window = tokens[max(0, index - 4) : min(len(tokens), index + 2)]
        if any(item in NEGATION_TOKENS for item in window):
            return True
    return False


def answer_quality(answer_text: str, gold_answer: str) -> dict[str, Any]:
    gold_tokens = set(content_tokens(gold_answer))
    predicted_tokens = set(content_tokens(answer_text))
    overlap = gold_tokens & predicted_tokens
    token_overlap_rate = locomo.safe_rate(len(overlap), len(gold_tokens))
    strong_match = bool(gold_tokens and token_overlap_rate >= 0.8)
    negation_trap = bool(strong_match and has_negation_trap(answer_text, gold_answer))
    return {
        "legacy_substring_match": answer_matches_gold(answer_text, gold_answer),
        "token_overlap_rate": token_overlap_rate,
        "strong_match": strong_match,
        "negation_trap": negation_trap,
        "gold_token_count": len(gold_tokens),
        "overlap_token_count": len(overlap),
    }


def bool_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().casefold()
    return text in {"1", "true", "yes", "y", "refused", "abstain", "abstained"}


def load_answer_predictions(path: Path) -> dict[str, dict[str, AnswerPrediction]]:
    by_arm: dict[str, dict[str, AnswerPrediction]] = {}
    for row in locomo.read_json_or_jsonl(path):
        case_id = str(row.get("case_id") or "").strip()
        if not case_id:
            raise ValueError(f"answer prediction missing case_id in {path}")
        arm = str(row.get("arm") or "retrieved_context").strip() or "retrieved_context"
        arm_rows = by_arm.setdefault(arm, {})
        if case_id in arm_rows:
            raise ValueError(f"duplicate answer prediction for {arm}/{case_id}")
        retrieved = tuple(
            sorted(
                set(
                    locomo.as_string_list(
                        row.get("retrieved_evidence_ids")
                        or row.get("evidence_ids")
                        or row.get("source_event_ids")
                    )
                )
            )
        )
        citations = tuple(
            sorted(set(locomo.as_string_list(row.get("citation_ids") or row.get("citations"))))
        )
        arm_rows[case_id] = AnswerPrediction(
            case_id=case_id,
            arm=arm,
            retrieved_evidence_ids=retrieved,
            answer_text=str(row.get("answer_text") or row.get("answer") or ""),
            citation_ids=citations,
            refused=bool_value(row.get("refused") or row.get("abstained")),
        )
    return by_arm


def oracle_answer_prediction(case: locomo.LocomoCase) -> AnswerPrediction:
    return AnswerPrediction(
        case_id=case.case_id,
        arm="retrieved_context",
        retrieved_evidence_ids=case.evidence_ids,
        answer_text=case.answer,
        citation_ids=case.evidence_ids,
        refused=False,
    )


def empty_context_prediction(case: locomo.LocomoCase) -> AnswerPrediction:
    return AnswerPrediction(
        case_id=case.case_id,
        arm="empty_context",
        retrieved_evidence_ids=(),
        answer_text="",
        citation_ids=(),
        refused=True,
    )


def default_prediction_arms(dataset: locomo.LocomoDataset) -> dict[str, dict[str, AnswerPrediction]]:
    return {
        "retrieved_context": {case.case_id: oracle_answer_prediction(case) for case in dataset.cases},
        "empty_context": {case.case_id: empty_context_prediction(case) for case in dataset.cases},
    }


def ensure_empty_context_arm(
    arms: dict[str, dict[str, AnswerPrediction]],
    dataset: locomo.LocomoDataset,
) -> dict[str, dict[str, AnswerPrediction]]:
    if "empty_context" not in arms:
        arms["empty_context"] = {
            case.case_id: empty_context_prediction(case) for case in dataset.cases
        }
    return arms


def score_case(case: locomo.LocomoCase, prediction: AnswerPrediction) -> dict[str, Any]:
    expected = set(case.evidence_ids)
    retrieved = set(prediction.retrieved_evidence_ids)
    citations = set(prediction.citation_ids)
    missing = sorted(expected - retrieved)
    context_sufficient = not missing
    quality = answer_quality(prediction.answer_text, case.answer)
    answer_correct = bool(
        context_sufficient
        and not prediction.refused
        and quality["strong_match"]
        and not quality["negation_trap"]
    )
    correct_source_citation = bool(context_sufficient and expected.issubset(citations))
    expected_refusal = not context_sufficient
    unsupported_inference_refused = bool(expected_refusal and prediction.refused)
    return {
        "case_id": case.case_id,
        "user_id": case.user_id,
        "category": case.category,
        "question_sha1": locomo.sha1_text(case.question)[:16],
        "answer_sha1": locomo.sha1_text(case.answer)[:16],
        "answer_text_sha1": locomo.sha1_text(prediction.answer_text)[:16]
        if prediction.answer_text
        else None,
        "expected_evidence_ids": list(case.evidence_ids),
        "retrieved_evidence_ids": sorted(retrieved),
        "citation_ids": sorted(citations),
        "missing_evidence_ids": missing,
        "extra_retrieved_evidence_ids": sorted(retrieved - expected),
        "source_evidence_recall": locomo.safe_rate(len(expected & retrieved), len(expected)),
        "context_sufficient": context_sufficient,
        "answer_quality": quality,
        "answer_correct": answer_correct,
        "correct_source_citation": correct_source_citation,
        "expected_refusal": expected_refusal,
        "unsupported_inference_refused": unsupported_inference_refused,
        "refused": prediction.refused,
    }


def summarize_cases(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(rows)
    insufficient = [row for row in rows if row["expected_refusal"]]
    quality_rows = [row.get("answer_quality") or {} for row in rows]
    return {
        "case_count": total,
        "full_evidence_recall_rate": locomo.safe_rate(
            sum(1 for row in rows if not row["missing_evidence_ids"]),
            total,
        ),
        "mean_source_evidence_recall": round(
            sum(float(row["source_evidence_recall"]) for row in rows) / total,
            4,
        )
        if rows
        else 0.0,
        "context_sufficient_rate": locomo.safe_rate(
            sum(1 for row in rows if row["context_sufficient"]),
            total,
        ),
        "answer_correct_rate": locomo.safe_rate(
            sum(1 for row in rows if row["answer_correct"]),
            total,
        ),
        "legacy_substring_gold_match_rate": locomo.safe_rate(
            sum(1 for row in quality_rows if row.get("legacy_substring_match")),
            total,
        ),
        "token_overlap_strong_match_rate": locomo.safe_rate(
            sum(1 for row in quality_rows if row.get("strong_match")),
            total,
        ),
        "negation_trap_count": sum(1 for row in quality_rows if row.get("negation_trap")),
        "correct_source_citation_rate": locomo.safe_rate(
            sum(1 for row in rows if row["correct_source_citation"]),
            total,
        ),
        "unsupported_inference_case_count": len(insufficient),
        "unsupported_inference_refusal_rate": locomo.safe_rate(
            sum(1 for row in insufficient if row["unsupported_inference_refused"]),
            len(insufficient),
        ),
        "non_refused_unsupported_inference_count": sum(
            1 for row in insufficient if not row["unsupported_inference_refused"]
        ),
    }


def score_arm(
    arm_name: str,
    predictions: dict[str, AnswerPrediction],
    dataset: locomo.LocomoDataset,
) -> dict[str, Any]:
    rows = [
        score_case(
            case,
            predictions.get(case.case_id)
            or AnswerPrediction(case.case_id, arm_name, (), "", (), False),
        )
        for case in sorted(dataset.cases, key=locomo.case_sort_key)
    ]
    metrics = summarize_cases(rows)
    return {
        "arm": arm_name,
        "metrics": metrics,
        "cases": rows,
    }


def build_answer_prediction_template(dataset: locomo.LocomoDataset) -> list[dict[str, Any]]:
    return [
        {
            "case_id": case.case_id,
            "arm": "retrieved_context",
            "user_id": case.user_id,
            "category": case.category,
            "question_sha1": locomo.sha1_text(case.question)[:16],
            "retrieved_evidence_ids": [],
            "answer_text": "",
            "citation_ids": [],
            "refused": False,
        }
        for case in sorted(dataset.cases, key=locomo.case_sort_key)
    ]


def unavailable_payload(
    dataset_path: Path | str,
    started: float,
    *,
    answer_template_output: Path | str | None = None,
) -> dict[str, Any]:
    template_requested = answer_template_output is not None
    template_path = Path(answer_template_output) if template_requested else None
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "aippocampus_locomo_answer_usefulness_benchmark",
        "generated_at": locomo.now_utc(),
        "status": "dataset_unavailable",
        "ok": False,
        "quality_gate_ok": False,
        "quality_gate_status": "not_scored",
        "report_generation_ok": False,
        "artifact_generation_ok": not template_requested,
        "artifact_generation_status": "skipped_missing_dataset"
        if template_requested
        else "not_requested",
        "dataset": {
            "dataset_id": "locomo_public_longitudinal_users_v1",
            "fixture": locomo.public_path_label(dataset_path),
        },
        "arms": {},
        "privacy_boundary": {
            "raw_dialogue_text_emitted": False,
            "raw_question_text_emitted": False,
            "raw_answer_text_emitted": False,
            "answer_prediction_text_emitted": False,
            "absolute_paths_emitted": False,
        },
        "cannot_claim": [
            "source_evidence_retrieval_quality",
            "answer_generation_quality",
        ],
        "artifacts": {
            "answer_template_requested": template_requested,
            "answer_template_written": False,
            "answer_template_status": "skipped_missing_dataset"
            if template_requested
            else "not_requested",
            "answer_template_row_count": 0,
            "answer_template_path": locomo.public_path_label(template_path)
            if template_path
            else None,
        },
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
    }


def run_benchmark(
    *,
    dataset_path: Path | str = DEFAULT_DATASET,
    predictions_file: Path | str | None = None,
    answer_model: str = DEFAULT_ANSWER_MODEL,
    judge_model: str = DETERMINISTIC_JUDGE_MODEL,
    max_samples: int | None = None,
    max_cases: int | None = None,
    answer_template_output: Path | str | None = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    dataset_path = Path(dataset_path)
    if not dataset_path.exists():
        return unavailable_payload(
            dataset_path,
            started,
            answer_template_output=answer_template_output,
        )
    dataset = locomo.load_dataset(
        dataset_path,
        max_samples=max_samples,
        max_cases=max_cases,
    )
    if predictions_file:
        arms = ensure_empty_context_arm(
            load_answer_predictions(Path(predictions_file).resolve()),
            dataset,
        )
        prediction_source = "external_answer_predictions"
    else:
        arms = default_prediction_arms(dataset)
        prediction_source = "deterministic_contract_fixture"

    template_path: Path | None = None
    template_requested = answer_template_output is not None
    template_written = False
    template_row_count = 0
    template_status = "not_requested"
    if answer_template_output:
        template_path = Path(answer_template_output)
        template_rows = build_answer_prediction_template(dataset)
        template_row_count = len(template_rows)
        if template_rows:
            locomo.write_jsonl(template_path, template_rows)
            template_written = True
            template_status = "written"
        else:
            # Empty templates look like successful setup while giving a model no
            # cases to fill; keep the requested path in the report but do not
            # create a misleading zero-row artifact.
            template_status = "skipped_no_cases"

    scored_arms = {
        arm_name: score_arm(arm_name, arm_predictions, dataset)
        for arm_name, arm_predictions in sorted(arms.items())
    }
    retrieved_metrics = scored_arms.get("retrieved_context", {}).get("metrics", {})
    empty_metrics = scored_arms.get("empty_context", {}).get("metrics", {})
    ok = bool(
        retrieved_metrics.get("full_evidence_recall_rate") == 1.0
        and retrieved_metrics.get("answer_correct_rate") == 1.0
        and retrieved_metrics.get("correct_source_citation_rate") == 1.0
        and empty_metrics.get("unsupported_inference_refusal_rate") == 1.0
    )
    artifact_generation_ok = bool(
        (not template_requested)
        or (template_written and template_status == "written")
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "aippocampus_locomo_answer_usefulness_benchmark",
        "generated_at": locomo.now_utc(),
        "status": "answer_usefulness_contract_scored",
        "ok": ok,
        "quality_gate_ok": ok,
        "quality_gate_status": "passed" if ok else "failed",
        "report_generation_ok": True,
        "artifact_generation_ok": artifact_generation_ok,
        "artifact_generation_status": template_status,
        "evaluation": {
            "answer_model": answer_model,
            "judge_model": judge_model,
            "prediction_source": prediction_source,
            "live_llm": False,
            "answer_input_boundary": (
                "case pack may include question and bounded dialogue context, "
                "but not gold answers or gold evidence labels"
            ),
            "judge_input_boundary": (
                "deterministic prototype judge can see gold answers/evidence ids "
                "for scoring, but judge output is not source truth"
            ),
        },
        "dataset": {
            "dataset_id": dataset.dataset_id,
            "fixture": locomo.public_path_label(dataset.path),
            "source_family": "LoCoMo",
            "track_role": "public_retrieval_qa_answer_usefulness_prototype",
            "raw_dataset_git_policy": "ignored_or_external",
        },
        "layers": {
            "source_evidence_retrieval": {
                "metric": "full_evidence_recall_rate",
                "owner": "benchmark_locomo_public_users.py",
            },
            "context_gathering": {"metric": "context_sufficient_rate"},
            "answer_generation": {"metric": "answer_correct_rate"},
            "source_citation": {"metric": "correct_source_citation_rate"},
            "unsupported_inference_refusal": {
                "metric": "unsupported_inference_refusal_rate",
            },
        },
        "arms": scored_arms,
        "privacy_boundary": {
            "fixture_contains_private_user_data": False,
            "raw_dialogue_text_emitted": False,
            "raw_question_text_emitted": False,
            "raw_answer_text_emitted": False,
            "answer_prediction_text_emitted": False,
            "absolute_paths_emitted": False,
            "answer_template_raw_text_emitted": False,
        },
        "artifacts": {
            "answer_template_requested": template_requested,
            "answer_template_written": template_written,
            "answer_template_status": template_status,
            "answer_template_row_count": template_row_count,
            "answer_template_path": locomo.public_path_label(template_path)
            if template_path
            else None,
        },
        "cannot_claim": [
            "answer_generation_quality_depends_on_fixed_answer_model",
            "model_independent_memory_superiority",
            "longmemeval_v2_quality",
            "sota_or_external_system_comparison",
            "private_real_history_quality",
            "llm_judge_as_source_truth",
            "retrieval_only_track_b_replaced",
        ],
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
    }


def print_human_summary(payload: dict[str, Any]) -> None:
    print("AIppocampus LoCoMo answer-usefulness prototype")
    print(f"- status: {payload.get('status')}")
    if "quality_gate_ok" in payload:
        print(f"- quality gate: {payload.get('quality_gate_status', 'unknown')}")
    if "report_generation_ok" in payload:
        print(
            "- report generation: "
            f"{'ok' if payload.get('report_generation_ok') else 'failed'}"
        )
    artifacts = payload.get("artifacts") or {}
    if artifacts.get("answer_template_requested"):
        print(f"- answer template: {artifacts.get('answer_template_status')}")
    for arm, body in (payload.get("arms") or {}).items():
        metrics = body.get("metrics") or {}
        print(
            f"- {arm}: answer={metrics.get('answer_correct_rate', 0):.2%} "
            f"citation={metrics.get('correct_source_citation_rate', 0):.2%} "
            f"refusal={metrics.get('unsupported_inference_refusal_rate', 0):.2%}"
        )


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--predictions", type=Path, default=None)
    parser.add_argument("--answer-model", default=DEFAULT_ANSWER_MODEL)
    parser.add_argument("--judge-model", default=DETERMINISTIC_JUDGE_MODEL)
    parser.add_argument("--max-samples", type=int, default=None)
    parser.add_argument("--max-cases", type=int, default=None)
    parser.add_argument("--answer-template-output", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--json", action="store_true", dest="json_output")
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    payload = run_benchmark(
        dataset_path=args.dataset,
        predictions_file=args.predictions,
        answer_model=args.answer_model,
        judge_model=args.judge_model,
        max_samples=args.max_samples,
        max_cases=args.max_cases,
        answer_template_output=args.answer_template_output,
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
