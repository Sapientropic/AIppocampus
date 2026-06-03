#!/usr/bin/env python3
"""LongMemEval-V2 context-mapping pilot for AIppocampus.

This runner is deliberately not a LongMemEval-V2 score runner. The public V2
release evaluates Insert/Query context gathering plus a fixed reader, while
AIppocampus' existing LongMemEval V1 adapter measures deterministic
source-evidence retrieval. The pilot below inspects whether the released V2
questions and trajectories expose enough join/evidence fields to score that
source-evidence layer without inventing labels.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import _paths

_paths.ensure_paths()

SCHEMA_VERSION = 1
DEFAULT_CASE_LIMIT = 20
DEFAULT_QUESTIONS_FILE = (
    _paths.REPO_ROOT / "benchmark_corpus" / "longmemeval" / "v2_questions.jsonl"
)
DEFAULT_TRAJECTORIES_FILE = (
    _paths.REPO_ROOT / "benchmark_corpus" / "longmemeval" / "v2_trajectories.jsonl"
)
LONGMEMEVAL_V2_DATASET_URL = "https://huggingface.co/datasets/xiaowu0162/longmemeval-v2"
LONGMEMEVAL_V2_REPO_URL = "https://github.com/xiaowu0162/LongMemEval-V2"
LONGMEMEVAL_V2_PROJECT_URL = "https://xiaowu0162.github.io/longmemeval-v2/"
LONGMEMEVAL_V2_PAPER_URL = "https://arxiv.org/abs/2605.12493"
LONGMEMEVAL_V2_LICENSE = "Apache-2.0"

QUESTION_EVIDENCE_REF_KEYS = {
    "answer_session_ids",
    "answer_trajectory_ids",
    "evidence_ids",
    "evidence_refs",
    "evidence_spans",
    "evidence_state_indices",
    "gold_evidence",
    "gold_evidence_ids",
    "gold_source_ids",
    "gold_trajectory_ids",
    "haystack_ids",
    "source_ids",
    "source_refs",
    "trajectory_ids",
}
TRAJECTORY_GOLD_REF_KEYS = {
    "answer_labels",
    "evidence_labels",
    "gold_evidence_ids",
    "gold_question_ids",
    "gold_source_ids",
    "question_ids",
}
RAW_TEXT_FIELDS_EXCLUDED = (
    "question",
    "answer",
    "eval_function",
    "goal",
    "outcome",
    "start_url",
    "states",
    "accessibility_tree",
    "action",
    "thought",
    "screenshot",
    "url",
)


@dataclass(frozen=True)
class QuestionRow:
    source_id: str
    domain: str
    environment: str
    environment_family: str
    question_type: str
    evidence_ref_keys: tuple[str, ...]


@dataclass(frozen=True)
class TrajectoryRow:
    source_id: str
    domain: str
    environment: str
    environment_family: str
    state_count: int
    gold_ref_keys: tuple[str, ...]


@dataclass
class TrajectoryIndex:
    rows: list[TrajectoryRow] = field(default_factory=list)
    ids: set[str] = field(default_factory=set)
    by_domain_environment: Counter[tuple[str, str]] = field(default_factory=Counter)
    state_counts: list[int] = field(default_factory=list)
    domain_counts: Counter[str] = field(default_factory=Counter)
    environment_counts: Counter[str] = field(default_factory=Counter)
    gold_ref_count: int = 0


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha1_short(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:16]


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_verification(path: Path, *, compute_sha256: bool) -> dict[str, Any]:
    if not path.exists():
        return {
            "ok": False,
            "status": "missing",
            "path_sha1": sha1_short(str(path)),
        }
    payload: dict[str, Any] = {
        "ok": True,
        "status": "present",
        "path_sha1": sha1_short(str(path)),
        "bytes": path.stat().st_size,
    }
    if compute_sha256:
        payload["sha256"] = file_sha256(path)
    return payload


def normalize_environment(environment: object) -> str:
    value = str(environment or "unknown").strip().lower()
    if value.startswith("webarena"):
        return "webarena"
    if value.startswith("workarena"):
        return "workarena"
    return value or "unknown"


def countable_ref_keys(row: dict[str, Any], candidate_keys: set[str]) -> tuple[str, ...]:
    keys: list[str] = []
    for key in sorted(candidate_keys):
        value = row.get(key)
        if value:
            keys.append(key)
    return tuple(keys)


def read_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                row = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path.name}:{line_number}: invalid JSONL") from exc
            if not isinstance(row, dict):
                raise ValueError(f"{path.name}:{line_number}: row must be an object")
            yield row


def load_questions(path: Path, *, max_questions: int | None = None) -> tuple[list[QuestionRow], dict[str, Any]]:
    rows: list[QuestionRow] = []
    domain_counts: Counter[str] = Counter()
    environment_counts: Counter[str] = Counter()
    environment_family_counts: Counter[str] = Counter()
    question_type_counts: Counter[str] = Counter()
    field_counts: Counter[str] = Counter()
    evidence_ref_count = 0
    for raw in read_jsonl(path):
        if max_questions is not None and len(rows) >= max_questions:
            break
        source_id = str(raw.get("id") or "")
        domain = str(raw.get("domain") or "unknown")
        environment = str(raw.get("environment") or "unknown")
        question_type = str(raw.get("question_type") or "unknown")
        environment_family = normalize_environment(environment)
        evidence_keys = countable_ref_keys(raw, QUESTION_EVIDENCE_REF_KEYS)
        if evidence_keys:
            evidence_ref_count += 1
        rows.append(
            QuestionRow(
                source_id=source_id,
                domain=domain,
                environment=environment,
                environment_family=environment_family,
                question_type=question_type,
                evidence_ref_keys=evidence_keys,
            )
        )
        domain_counts[domain] += 1
        environment_counts[environment] += 1
        environment_family_counts[environment_family] += 1
        question_type_counts[question_type] += 1
        field_counts.update(raw.keys())
    summary = {
        "domain_counts": dict(sorted(domain_counts.items())),
        "environment_counts": dict(sorted(environment_counts.items())),
        "environment_family_counts": dict(sorted(environment_family_counts.items())),
        "question_type_counts": dict(sorted(question_type_counts.items())),
        "field_counts": dict(sorted(field_counts.items())),
        "evidence_ref_count": evidence_ref_count,
    }
    return rows, summary


def load_trajectories(path: Path) -> tuple[TrajectoryIndex, dict[str, Any]]:
    index = TrajectoryIndex()
    field_counts: Counter[str] = Counter()
    for raw in read_jsonl(path):
        source_id = str(raw.get("id") or "")
        domain = str(raw.get("domain") or "unknown")
        environment = str(raw.get("environment") or "unknown")
        environment_family = normalize_environment(environment)
        states = raw.get("states")
        state_count = len(states) if isinstance(states, list) else 0
        gold_ref_keys = countable_ref_keys(raw, TRAJECTORY_GOLD_REF_KEYS)
        row = TrajectoryRow(
            source_id=source_id,
            domain=domain,
            environment=environment,
            environment_family=environment_family,
            state_count=state_count,
            gold_ref_keys=gold_ref_keys,
        )
        index.rows.append(row)
        index.ids.add(source_id)
        index.by_domain_environment[(domain, environment_family)] += 1
        index.state_counts.append(state_count)
        index.domain_counts[domain] += 1
        index.environment_counts[environment] += 1
        field_counts.update(raw.keys())
        if gold_ref_keys:
            index.gold_ref_count += 1
    summary = {
        "domain_counts": dict(sorted(index.domain_counts.items())),
        "environment_counts": dict(sorted(index.environment_counts.items())),
        "field_counts": dict(sorted(field_counts.items())),
        "gold_ref_count": index.gold_ref_count,
        "state_count": {
            "total": sum(index.state_counts),
            "min": min(index.state_counts) if index.state_counts else 0,
            "max": max(index.state_counts) if index.state_counts else 0,
            "mean": round(statistics.fmean(index.state_counts), 2) if index.state_counts else 0.0,
        },
    }
    return index, summary


def benchmark_metadata(
    *,
    questions_file: Path,
    trajectories_file: Path,
    questions_verification: dict[str, Any],
    trajectories_verification: dict[str, Any],
) -> dict[str, Any]:
    return {
        "name": "LongMemEval-V2",
        "paper_url": LONGMEMEVAL_V2_PAPER_URL,
        "official_repo_url": LONGMEMEVAL_V2_REPO_URL,
        "project_url": LONGMEMEVAL_V2_PROJECT_URL,
        "dataset_url": LONGMEMEVAL_V2_DATASET_URL,
        "license": LONGMEMEVAL_V2_LICENSE,
        "dataset_version": "public Hugging Face release inspected 2026-06-03",
        "local_files": {
            "questions": questions_verification,
            "trajectories": trajectories_verification,
        },
        "local_path_sha1": {
            "questions": sha1_short(str(questions_file)),
            "trajectories": sha1_short(str(trajectories_file)),
        },
    }


def privacy_boundary() -> dict[str, Any]:
    return {
        "raw_text_emitted": False,
        "snippets_emitted": False,
        "absolute_paths_emitted": False,
        "case_ids_are_hashed": True,
        "raw_fields_excluded": list(RAW_TEXT_FIELDS_EXCLUDED),
        "output_shape": "sanitized_longmemeval_v2_context_mapping",
    }


def cannot_claim(status: str) -> list[str]:
    claims = {
        "answer_generation_quality",
        "benchmark_grade_context_gathering_score",
        "longmemeval_v2_answer_accuracy",
        "longmemeval_v2_lafs_gain",
        "longmemeval_v2_mrr",
        "longmemeval_v2_retrieval_score",
        "longmemeval_v2_source_evidence_hit_rate",
        "sota_or_external_baseline_superiority",
    }
    if status.startswith("skipped_"):
        claims.add("longmemeval_v2_context_mapping_pilot")
    return sorted(claims)


def skipped_payload(
    *,
    status: str,
    questions_file: Path,
    trajectories_file: Path,
    questions_verification: dict[str, Any],
    trajectories_verification: dict[str, Any],
    started: float,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "aippocampus_longmemeval_v2_context_mapping",
        "generated_at": now_utc(),
        "status": status,
        "ok": True,
        "benchmark": benchmark_metadata(
            questions_file=questions_file,
            trajectories_file=trajectories_file,
            questions_verification=questions_verification,
            trajectories_verification=trajectories_verification,
        ),
        "evaluation": evaluation_metadata(case_limit=0, max_questions=None),
        "metrics": {"question_count": 0, "trajectory_count": 0},
        "decision": decision_payload(
            can_build_context_candidate_packs=False,
            can_score_benchmark_grade_context_gathering=False,
            can_score_source_evidence_retrieval=False,
            exact_id_match_count=0,
            question_evidence_ref_count=0,
            trajectory_gold_ref_count=0,
        ),
        "cases": [],
        "privacy_boundary": privacy_boundary(),
        "cannot_claim": cannot_claim(status),
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
    }


def evaluation_metadata(*, case_limit: int, max_questions: int | None) -> dict[str, Any]:
    return {
        "mode": "context_mapping_pilot",
        "claim_level": "source_evidence_mapping_pilot",
        "retrieval_metric_scope": "schema and join-key feasibility only",
        "context_gathering": "candidate_pack_diagnostic_only",
        "qa_generation": "not_run",
        "judge_model": None,
        "case_limit": int(case_limit),
        "max_questions": max_questions,
        "runner": "benchmarks/aippocampus/benchmark_longmemeval_v2_context.py",
    }


def decision_payload(
    *,
    can_build_context_candidate_packs: bool,
    can_score_benchmark_grade_context_gathering: bool,
    can_score_source_evidence_retrieval: bool,
    exact_id_match_count: int,
    question_evidence_ref_count: int,
    trajectory_gold_ref_count: int,
) -> dict[str, Any]:
    if can_score_source_evidence_retrieval:
        source_scoring = "supported_by_gold_evidence_refs"
    else:
        source_scoring = "not_supported_missing_gold_evidence_refs"
    if can_score_benchmark_grade_context_gathering:
        context_scoring = "supported_by_explicit_question_to_haystack_mapping"
    elif can_build_context_candidate_packs:
        context_scoring = "diagnostic_only_environment_pool"
    else:
        context_scoring = "not_supported_missing_candidate_pool"
    return {
        "source_evidence_scoring": source_scoring,
        "context_gathering_scoring": context_scoring,
        "answer_generation": "not_run_requires_official_reader_harness",
        "can_build_context_candidate_packs": can_build_context_candidate_packs,
        "can_score_benchmark_grade_context_gathering": can_score_benchmark_grade_context_gathering,
        "can_score_source_evidence_retrieval": can_score_source_evidence_retrieval,
        "observed_exact_question_trajectory_id_matches": exact_id_match_count,
        "observed_question_evidence_ref_rows": question_evidence_ref_count,
        "observed_trajectory_gold_ref_rows": trajectory_gold_ref_count,
        "missing_upstream_fields": [
            "gold_trajectory_ids or haystack_ids per question",
            "gold evidence state indices or source spans",
            "source ids usable for retrieval grading without exposing answers",
            "official reader/evaluator harness output for answer accuracy",
        ],
    }


def build_cases(
    questions: list[QuestionRow],
    trajectory_index: TrajectoryIndex,
    *,
    case_limit: int,
) -> tuple[list[dict[str, Any]], dict[str, int | float]]:
    cases: list[dict[str, Any]] = []
    exact_id_match_count = 0
    environment_candidate_coverage_count = 0
    ambiguous_candidate_count = 0
    missing_mapping_count = 0
    candidate_counts: list[int] = []
    for question in questions:
        exact_match = question.source_id in trajectory_index.ids
        if exact_match:
            exact_id_match_count += 1
        candidate_count = trajectory_index.by_domain_environment[
            (question.domain, question.environment_family)
        ]
        if candidate_count > 0:
            environment_candidate_coverage_count += 1
        if exact_match:
            mapping_status = "exact_id_match"
        elif candidate_count > 1:
            mapping_status = "environment_pool_only"
            ambiguous_candidate_count += 1
        elif candidate_count == 1:
            mapping_status = "environment_pool_only"
        else:
            mapping_status = "missing_candidate_pool"
            missing_mapping_count += 1
        candidate_counts.append(candidate_count)
        if len(cases) < case_limit:
            cases.append(
                {
                    "case_id_hash": sha1_short(question.source_id),
                    "domain": question.domain,
                    "environment_family": question.environment_family,
                    "question_type": question.question_type,
                    "mapping_status": mapping_status,
                    "candidate_trajectory_count": candidate_count,
                    "has_question_evidence_refs": bool(question.evidence_ref_keys),
                }
            )
    aggregate = {
        "exact_id_match_count": exact_id_match_count,
        "environment_candidate_coverage_count": environment_candidate_coverage_count,
        "ambiguous_candidate_count": ambiguous_candidate_count,
        "missing_mapping_count": missing_mapping_count,
        "candidate_trajectory_count_mean": round(statistics.fmean(candidate_counts), 2)
        if candidate_counts
        else 0.0,
        "candidate_trajectory_count_max": max(candidate_counts) if candidate_counts else 0,
    }
    return cases, aggregate


def rate(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 6)


def run_longmemeval_v2_context_mapping(
    *,
    questions_file: Path | str = DEFAULT_QUESTIONS_FILE,
    trajectories_file: Path | str = DEFAULT_TRAJECTORIES_FILE,
    case_limit: int = DEFAULT_CASE_LIMIT,
    max_questions: int | None = None,
    compute_sha256: bool = True,
) -> dict[str, Any]:
    started = time.perf_counter()
    questions_path = Path(questions_file).resolve()
    trajectories_path = Path(trajectories_file).resolve()
    questions_verification = file_verification(questions_path, compute_sha256=compute_sha256)
    trajectories_verification = file_verification(trajectories_path, compute_sha256=compute_sha256)
    if not questions_verification["ok"] or not trajectories_verification["ok"]:
        return skipped_payload(
            status="skipped_missing_dataset",
            questions_file=questions_path,
            trajectories_file=trajectories_path,
            questions_verification=questions_verification,
            trajectories_verification=trajectories_verification,
            started=started,
        )

    questions, question_summary = load_questions(questions_path, max_questions=max_questions)
    trajectory_index, trajectory_summary = load_trajectories(trajectories_path)
    cases, mapping_aggregate = build_cases(
        questions,
        trajectory_index,
        case_limit=max(0, case_limit),
    )
    question_count = len(questions)
    trajectory_count = len(trajectory_index.rows)
    question_evidence_ref_count = int(question_summary["evidence_ref_count"])
    trajectory_gold_ref_count = int(trajectory_summary["gold_ref_count"])
    exact_id_match_count = int(mapping_aggregate["exact_id_match_count"])
    environment_candidate_coverage_count = int(
        mapping_aggregate["environment_candidate_coverage_count"]
    )
    can_build_context_candidate_packs = environment_candidate_coverage_count > 0
    can_score_source_evidence_retrieval = (
        question_evidence_ref_count > 0 and trajectory_gold_ref_count > 0 and exact_id_match_count > 0
    )
    can_score_benchmark_grade_context_gathering = (
        question_evidence_ref_count > 0 and exact_id_match_count > 0
    )
    status = "mapping_pilot_diagnostic"
    metrics: dict[str, Any] = {
        "question_count": question_count,
        "trajectory_count": trajectory_count,
        "exact_id_match_count": exact_id_match_count,
        "exact_id_match_rate": rate(exact_id_match_count, question_count),
        "environment_candidate_coverage_count": environment_candidate_coverage_count,
        "environment_candidate_coverage_rate": rate(
            environment_candidate_coverage_count,
            question_count,
        ),
        "ambiguous_candidate_count": mapping_aggregate["ambiguous_candidate_count"],
        "ambiguous_candidate_rate": rate(
            int(mapping_aggregate["ambiguous_candidate_count"]),
            question_count,
        ),
        "missing_mapping_count": mapping_aggregate["missing_mapping_count"],
        "missing_mapping_rate": rate(int(mapping_aggregate["missing_mapping_count"]), question_count),
        "candidate_trajectory_count_mean": mapping_aggregate["candidate_trajectory_count_mean"],
        "candidate_trajectory_count_max": mapping_aggregate["candidate_trajectory_count_max"],
        "question_evidence_ref_count": question_evidence_ref_count,
        "question_evidence_ref_rate": rate(question_evidence_ref_count, question_count),
        "trajectory_gold_ref_count": trajectory_gold_ref_count,
        "trajectory_gold_ref_rate": rate(trajectory_gold_ref_count, trajectory_count),
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "aippocampus_longmemeval_v2_context_mapping",
        "generated_at": now_utc(),
        "status": status,
        "ok": True,
        "benchmark": benchmark_metadata(
            questions_file=questions_path,
            trajectories_file=trajectories_path,
            questions_verification=questions_verification,
            trajectories_verification=trajectories_verification,
        ),
        "evaluation": evaluation_metadata(case_limit=case_limit, max_questions=max_questions),
        "schema_observation": {
            "questions": question_summary,
            "trajectories": trajectory_summary,
        },
        "metrics": metrics,
        "decision": decision_payload(
            can_build_context_candidate_packs=can_build_context_candidate_packs,
            can_score_benchmark_grade_context_gathering=can_score_benchmark_grade_context_gathering,
            can_score_source_evidence_retrieval=can_score_source_evidence_retrieval,
            exact_id_match_count=exact_id_match_count,
            question_evidence_ref_count=question_evidence_ref_count,
            trajectory_gold_ref_count=trajectory_gold_ref_count,
        ),
        "cases": cases,
        "privacy_boundary": privacy_boundary(),
        "cannot_claim": cannot_claim(status),
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
    }


def print_human_summary(payload: dict[str, Any]) -> None:
    metrics = payload.get("metrics") or {}
    decision = payload.get("decision") or {}
    print("AIppocampus LongMemEval-V2 context mapping pilot")
    print(f"- status: {payload.get('status')}")
    print(f"- questions: {metrics.get('question_count', 0)}")
    print(f"- trajectories: {metrics.get('trajectory_count', 0)}")
    print(
        "- exact id matches: "
        f"{metrics.get('exact_id_match_count', 0)} "
        f"({metrics.get('exact_id_match_rate', 0.0):.2%})"
    )
    print(
        "- environment candidate coverage: "
        f"{metrics.get('environment_candidate_coverage_count', 0)} "
        f"({metrics.get('environment_candidate_coverage_rate', 0.0):.2%})"
    )
    print(f"- source-evidence scoring: {decision.get('source_evidence_scoring')}")
    print(f"- context gathering scoring: {decision.get('context_gathering_scoring')}")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--questions-file", type=Path, default=DEFAULT_QUESTIONS_FILE)
    parser.add_argument("--trajectories-file", type=Path, default=DEFAULT_TRAJECTORIES_FILE)
    parser.add_argument("--case-limit", type=int, default=DEFAULT_CASE_LIMIT)
    parser.add_argument("--max-questions", type=int, default=None)
    parser.add_argument("--skip-sha256", action="store_true")
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--json", action="store_true", dest="json_output")
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    payload = run_longmemeval_v2_context_mapping(
        questions_file=args.questions_file,
        trajectories_file=args.trajectories_file,
        case_limit=args.case_limit,
        max_questions=args.max_questions,
        compute_sha256=not args.skip_sha256,
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
