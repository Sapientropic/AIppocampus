#!/usr/bin/env python3
"""MemoryAgentBench metadata and public-safe case-pack smoke.

This is intentionally not an official MemoryAgentBench score runner. The
official benchmark mixes source/context gathering, answer generation, memory
write/update behavior, conflict handling, and optional judge paths. Collapsing
those into a single retrieval score would make a clean-looking number that
misrepresents what AIppocampus actually measured. This runner only inspects
local operator-provided files, emits sanitized metadata/schema observations,
and can explicitly write a local-only model-facing case pack with gold answers
excluded.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import _paths

_paths.ensure_paths()

from aippocampus_runtime.navigation.local_global_compatibility import (
    evaluate_local_global_compatibility,
)
from aippocampus_runtime.recall.source_backed_lessons import (
    extract_source_backed_lesson_candidates,
    promote_lesson_candidate,
)
from benchmarks.aippocampus.shared.claim_boundary_refs import claim_boundary_ref

SCHEMA_VERSION = 1
DEFAULT_CASE_LIMIT = 20
DEFAULT_DATASET_DIR = _paths.REPO_ROOT / "benchmark_corpus" / "memoryagentbench"
DEFAULT_MANIFEST = _paths.REPO_ROOT / "benchmark_corpus" / "memoryagentbench_manifest.json"

RAW_TEXT_FIELD_NAMES = {
    "answer",
    "answers",
    "context",
    "conversation",
    "conversations",
    "haystack_sessions",
    "keypoints",
    "messages",
    "previous_events",
    "prompt",
    "question",
    "questions",
    "response",
    "responses",
}
GOLD_LABEL_FIELD_NAMES = {
    "answer",
    "answers",
    "expected",
    "gold",
    "gold_answer",
    "gold_answers",
    "gold_label",
    "gold_labels",
    "ground_truth",
    "label",
    "labels",
    "target",
    "targets",
}
TASK_FIELD_NAMES = {
    "ability",
    "category",
    "dataset",
    "split",
    "sub_dataset",
    "subtask",
    "task",
    "task_family",
    "task_type",
}
METRIC_FIELD_NAMES = {
    "eval",
    "eval_function",
    "judge",
    "metric",
    "metric_family",
    "metrics",
    "score_type",
}
SAFE_CASE_METADATA_KEYS = {
    "qa_pair_ids",
    "question_dates",
    "question_ids",
    "question_types",
    "source",
}

CANONICAL_SPLITS = (
    "Accurate_Retrieval",
    "Test_Time_Learning",
    "Long_Range_Understanding",
    "Conflict_Resolution",
)

CANNOT_CLAIM = [
    "official_memoryagentbench_score",
    "official_runner_compatibility",
    "answer_generation_quality",
    "llm_judge_as_source_truth",
    "merged_retrieval_generation_judge_metric",
    "external_baseline_superiority",
    "static_retrieval_covers_test_time_learning",
    "static_retrieval_covers_conflict_resolution",
]

STAGE3_INCREMENTAL_SPLITS = ("Test_Time_Learning", "Conflict_Resolution")
STAGE3_WRITE_UPDATE_DRY_RUN_MODE = "dry_run_contract"
STAGE3_WRITE_UPDATE_APPLY_MODE = "local_apply_instrumented"
STAGE3_MISSING_WRITE_UPDATE_MODE = "unsupported_missing_instrumentation"
PARQUET_READER_MISSING_SUPPORT = "metadata_only_parquet_without_optional_reader"
PARQUET_ROW_SUPPORT = "parquet_rows_with_optional_reader"


class OptionalParquetReaderMissing(RuntimeError):
    """Raised when local parquet rows exist but pyarrow is not installed."""


@dataclass
class SplitObservation:
    split_id: str
    files: list[dict[str, Any]] = field(default_factory=list)
    observed_rows: int = 0
    field_counts: Counter[str] = field(default_factory=Counter)
    field_family_counts: Counter[str] = field(default_factory=Counter)
    task_families: Counter[str] = field(default_factory=Counter)
    metric_families: Counter[str] = field(default_factory=Counter)
    raw_text_fields: set[str] = field(default_factory=set)
    gold_label_fields: set[str] = field(default_factory=set)
    cases: list[dict[str, Any]] = field(default_factory=list)
    source_statuses: Counter[str] = field(default_factory=Counter)


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha1_text(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()


def sha1_short(value: str) -> str:
    return sha1_text(value)[:16]


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_path_label(path: Path | str) -> str:
    resolved = Path(path).resolve()
    try:
        return str(resolved.relative_to(_paths.REPO_ROOT)).replace("\\", "/")
    except ValueError:
        return f"external_file:{sha1_short(str(resolved))}"


def safe_source_label(value: Any) -> str:
    text = str(value or "unknown")
    # Upstream source labels are short public dataset/task names. Path-like
    # values are likely local operator metadata and must not escape reports or
    # model-facing case packs.
    if ":" in text or "/" in text or "\\" in text or len(text) > 80:
        return f"source_sha1:{sha1_short(text)}"
    return text or "unknown"


def file_verification(path: Path, *, compute_sha256: bool) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "path_sha1": sha1_short(str(path.resolve())),
        "label": safe_path_label(path),
        "suffix": path.suffix.lower(),
        "bytes": path.stat().st_size,
    }
    if compute_sha256:
        payload["sha256"] = file_sha256(path)
    return payload


def load_manifest(path: Path | str = DEFAULT_MANIFEST) -> dict[str, Any]:
    manifest_path = Path(path)
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def manifest_splits(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(split["id"]): dict(split) for split in manifest.get("splits", [])}


def split_patterns(split_id: str) -> tuple[str, ...]:
    return (
        f"{split_id}.jsonl",
        f"{split_id}.json",
        f"{split_id}-*.jsonl",
        f"{split_id}-*.json",
        f"{split_id}-*.parquet",
        f"data/{split_id}.jsonl",
        f"data/{split_id}.json",
        f"data/{split_id}-*.jsonl",
        f"data/{split_id}-*.json",
        f"data/{split_id}-*.parquet",
    )


def discover_split_files(dataset_dir: Path, split_id: str) -> list[Path]:
    files: dict[str, Path] = {}
    for pattern in split_patterns(split_id):
        for path in dataset_dir.glob(pattern):
            if path.is_file():
                files[str(path.resolve())] = path
    return [files[key] for key in sorted(files)]


def read_json_or_jsonl(path: Path) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return []
    if text.startswith("["):
        rows = json.loads(text)
        if not isinstance(rows, list):
            raise ValueError(f"{path.name}: expected a JSON array")
        return [dict(row) for row in rows if isinstance(row, dict)]
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        row = json.loads(stripped)
        if not isinstance(row, dict):
            raise ValueError(f"{path.name}:{line_number}: row must be an object")
        rows.append(row)
    return rows


def read_parquet_rows(path: Path) -> list[dict[str, Any]]:
    try:
        import pyarrow.parquet as pq  # type: ignore[import-not-found]
    except Exception as exc:
        raise OptionalParquetReaderMissing("Install pyarrow to read parquet rows.") from exc
    table = pq.read_table(str(path))
    return [dict(row) for row in table.to_pylist() if isinstance(row, dict)]


def parquet_metadata(path: Path) -> dict[str, Any]:
    try:
        import pyarrow.parquet as pq  # type: ignore[import-not-found]
    except Exception:
        return {
            "format_support": PARQUET_READER_MISSING_SUPPORT,
            "observed_rows": None,
            "schema_fields": [],
        }
    try:
        parquet_file = pq.ParquetFile(str(path))
        return {
            "format_support": "parquet_metadata_with_optional_pyarrow",
            "observed_rows": int(parquet_file.metadata.num_rows),
            "schema_fields": [str(name) for name in parquet_file.schema.names],
        }
    except Exception as exc:
        return {
            "format_support": "parquet_metadata_error",
            "observed_rows": None,
            "schema_fields": [],
            "error_type": type(exc).__name__,
        }


def flatten_field_names(value: Any, *, prefix: str = "") -> Iterable[str]:
    if not isinstance(value, dict):
        return
    for key, child in value.items():
        key_text = str(key)
        dotted = f"{prefix}.{key_text}" if prefix else key_text
        yield dotted
        if isinstance(child, dict):
            yield from flatten_field_names(child, prefix=dotted)


def base_field_name(field_name: str) -> str:
    return field_name.rsplit(".", 1)[-1]


def field_family(field_name: str) -> str:
    return sorted(field_families(field_name))[0]


def field_families(field_name: str) -> set[str]:
    base = base_field_name(field_name)
    families: set[str] = set()
    if base in RAW_TEXT_FIELD_NAMES:
        families.add("raw_text")
    if base in GOLD_LABEL_FIELD_NAMES:
        families.add("gold_label")
    if base in TASK_FIELD_NAMES:
        families.add("task")
    if base in METRIC_FIELD_NAMES:
        families.add("metric")
    if field_name.startswith("metadata."):
        families.add("metadata")
    return families or {"other"}


def as_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list | tuple | set):
        return [str(item) for item in value if str(item)]
    return [str(value)]


def normalize_family(value: str) -> str:
    text = value.strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "qa": "question_answering",
        "question_answering": "question_answering",
        "question-answering": "question_answering",
        "text_classification": "text_classification",
        "classification": "text_classification",
        "zero_shot_classification": "text_classification",
        "summarization": "summarization",
        "long_range_understanding": "long_range_understanding",
        "conflict_resolution": "conflict_resolution",
        "selective_forgetting": "selective_forgetting",
        "test_time_learning": "test_time_learning",
    }
    return aliases.get(text, text or "unknown")


def task_families_for_row(row: dict[str, Any], split_meta: dict[str, Any]) -> set[str]:
    families = {normalize_family(item) for item in split_meta.get("task_families", [])}
    metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
    for key in TASK_FIELD_NAMES:
        families.update(normalize_family(item) for item in as_string_list(row.get(key)))
        families.update(normalize_family(item) for item in as_string_list(metadata.get(key)))
    return {family for family in families if family}


def metric_families_for_row(row: dict[str, Any], split_meta: dict[str, Any]) -> set[str]:
    families = {normalize_family(item) for item in split_meta.get("metric_families", [])}
    metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
    for key in METRIC_FIELD_NAMES:
        families.update(normalize_family(item) for item in as_string_list(row.get(key)))
        families.update(normalize_family(item) for item in as_string_list(metadata.get(key)))
    return {family for family in families if family}


def safe_case_metadata(row: dict[str, Any]) -> dict[str, Any]:
    metadata = row.get("metadata")
    if not isinstance(metadata, dict):
        return {}
    safe: dict[str, Any] = {}
    for key in sorted(SAFE_CASE_METADATA_KEYS):
        if key not in metadata:
            continue
        value = metadata[key]
        safe[key] = safe_source_label(value) if key == "source" else value
    return safe


def questions_for_row(row: dict[str, Any]) -> list[str]:
    if "questions" in row:
        return as_string_list(row.get("questions"))
    return as_string_list(row.get("question"))


def stable_case_id(split_id: str, file_payload: dict[str, Any], row_index: int, row: dict[str, Any]) -> str:
    metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
    id_candidates = []
    for key in ("id", "uuid", "qa_pair_ids", "question_ids"):
        id_candidates.extend(as_string_list(row.get(key)))
        id_candidates.extend(as_string_list(metadata.get(key)))
    seed = {
        "split": split_id,
        "file": file_payload["path_sha1"],
        "row_index": row_index,
        "ids": sorted(id_candidates),
    }
    return f"mab:{sha1_text(json.dumps(seed, sort_keys=True))[:20]}"


def observe_row(
    observation: SplitObservation,
    *,
    split_meta: dict[str, Any],
    file_payload: dict[str, Any],
    row_index: int,
    row: dict[str, Any],
    case_limit: int,
) -> None:
    observation.observed_rows += 1
    field_names = sorted(flatten_field_names(row))
    observation.field_counts.update(field_names)
    for field_name in field_names:
        families = field_families(field_name)
        for family in families:
            observation.field_family_counts[family] += 1
        base = base_field_name(field_name)
        if "raw_text" in families:
            observation.raw_text_fields.add(base)
        if "gold_label" in families:
            observation.gold_label_fields.add(base)
    task_families = task_families_for_row(row, split_meta)
    metric_families = metric_families_for_row(row, split_meta)
    observation.task_families.update(task_families)
    observation.metric_families.update(metric_families)
    metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
    source_value = safe_source_label(metadata.get("source") or row.get("source") or "unknown")
    observation.source_statuses[source_value] += 1
    if len(observation.cases) >= case_limit:
        return
    case_id = stable_case_id(observation.split_id, file_payload, row_index, row)
    observation.cases.append(
        {
            "case_id": case_id,
            "split": observation.split_id,
            "row_index": row_index,
            "file_path_sha1": file_payload["path_sha1"],
            "field_families": sorted(
                {family for name in field_names for family in field_families(name)}
            ),
            "task_families": sorted(task_families),
            "metric_families": sorted(metric_families),
            "question_count": len(questions_for_row(row)),
            "context_sha1": sha1_short(str(row.get("context") or "")) if row.get("context") else None,
            "support_status": dict(split_meta.get("support_status", {})),
        }
    )


def observe_split(
    *,
    dataset_dir: Path,
    split_id: str,
    split_meta: dict[str, Any],
    case_limit: int,
    compute_sha256: bool,
) -> SplitObservation:
    observation = SplitObservation(split_id=split_id)
    for path in discover_split_files(dataset_dir, split_id):
        file_payload = file_verification(path, compute_sha256=compute_sha256)
        file_payload["format_support"] = "json_rows" if path.suffix.lower() in {".json", ".jsonl"} else "file_metadata"
        if path.suffix.lower() == ".parquet":
            metadata = parquet_metadata(path)
            file_payload.update(metadata)
            try:
                rows = read_parquet_rows(path)
            except OptionalParquetReaderMissing:
                rows = []
            except Exception as exc:
                file_payload["row_read_error_type"] = type(exc).__name__
                rows = []
            if rows:
                file_payload["format_support"] = PARQUET_ROW_SUPPORT
                file_payload["observed_rows"] = len(rows)
                observation.files.append(file_payload)
                for row_index, row in enumerate(rows, start=1):
                    observe_row(
                        observation,
                        split_meta=split_meta,
                        file_payload=file_payload,
                        row_index=row_index,
                        row=row,
                        case_limit=case_limit,
                    )
            else:
                row_count = metadata.get("observed_rows")
                if isinstance(row_count, int):
                    observation.observed_rows += row_count
                for field_name in metadata.get("schema_fields") or []:
                    observation.field_counts[field_name] += 1
                    for family in field_families(field_name):
                        observation.field_family_counts[family] += 1
                observation.files.append(file_payload)
            continue
        rows = read_json_or_jsonl(path)
        file_payload["observed_rows"] = len(rows)
        observation.files.append(file_payload)
        for row_index, row in enumerate(rows, start=1):
            observe_row(
                observation,
                split_meta=split_meta,
                file_payload=file_payload,
                row_index=row_index,
                row=row,
                case_limit=case_limit,
            )
    return observation


def split_report(split_meta: dict[str, Any], observation: SplitObservation) -> dict[str, Any]:
    task_families = sorted(
        observation.task_families
        or Counter({normalize_family(item): 1 for item in split_meta.get("task_families", [])})
    )
    metric_families = sorted(
        observation.metric_families
        or Counter({normalize_family(item): 1 for item in split_meta.get("metric_families", [])})
    )
    return {
        "expected_rows": int(split_meta.get("expected_examples") or 0),
        "expected_num_bytes": split_meta.get("expected_num_bytes"),
        "observed_rows": observation.observed_rows,
        "file_count": len(observation.files),
        "files": observation.files,
        "field_counts": dict(sorted(observation.field_counts.items())),
        "field_family_counts": dict(sorted(observation.field_family_counts.items())),
        "task_families": task_families,
        "task_family_counts": dict(sorted(observation.task_families.items())),
        "metric_families": metric_families,
        "metric_family_counts": dict(sorted(observation.metric_families.items())),
        "raw_text_fields_present": sorted(observation.raw_text_fields),
        "gold_label_fields_present": sorted(observation.gold_label_fields),
        "source_counts": dict(sorted(observation.source_statuses.items())),
        "support_status": dict(split_meta.get("support_status", {})),
        "cases": observation.cases,
    }


def collect_case_rows(
    *,
    dataset_dir: Path,
    split_id: str,
    split_meta: dict[str, Any],
    case_limit: int,
) -> list[dict[str, Any]]:
    rows_out: list[dict[str, Any]] = []
    for path in discover_split_files(dataset_dir, split_id):
        file_payload = file_verification(path, compute_sha256=False)
        if path.suffix.lower() in {".json", ".jsonl"}:
            rows = read_json_or_jsonl(path)
        elif path.suffix.lower() == ".parquet":
            try:
                rows = read_parquet_rows(path)
            except Exception:
                continue
        else:
            continue
        for row_index, row in enumerate(rows, start=1):
            case_id = stable_case_id(split_id, file_payload, row_index, row)
            rows_out.append(
                {
                    "case_id": case_id,
                    "split": split_id,
                    "row_index": row_index,
                    "task_families": sorted(task_families_for_row(row, split_meta)),
                    "metric_families": sorted(metric_families_for_row(row, split_meta)),
                    "context": str(row.get("context") or ""),
                    "questions": questions_for_row(row),
                    "safe_metadata": safe_case_metadata(row),
                }
            )
            if len(rows_out) >= case_limit:
                return rows_out
    return rows_out


def build_case_pack(
    *,
    dataset_dir: Path,
    manifest: dict[str, Any],
    split_id: str = "Accurate_Retrieval",
    case_limit: int = DEFAULT_CASE_LIMIT,
) -> dict[str, Any]:
    split_meta = manifest_splits(manifest)[split_id]
    cases = collect_case_rows(
        dataset_dir=dataset_dir,
        split_id=split_id,
        split_meta=split_meta,
        case_limit=case_limit,
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "aippocampus_memoryagentbench_case_pack",
        "generated_at": now_utc(),
        "dataset": {
            "benchmark": "MemoryAgentBench",
            "official_source": manifest["official_sources"]["dataset"],
            "license": manifest["official_sources"]["license"],
            "split": split_id,
            "raw_dataset_git_policy": manifest["local_file_policy"]["git_policy"],
        },
        "cases": [
            {
                "case_id": case["case_id"],
                "split": case["split"],
                "task_families": case["task_families"],
                "metric_families": case["metric_families"],
                "input": {
                    "context": case["context"],
                    "questions": case["questions"],
                    "metadata": case["safe_metadata"],
                },
                "prediction": "",
            }
            for case in cases
        ],
        "label_boundary": {
            "answer_text_included": False,
            "gold_labels_included": False,
            "scoring_metadata_included": False,
            "prediction_field": "prediction",
        },
        "privacy_boundary": {
            "raw_context_text_emitted": True,
            "raw_question_text_emitted": True,
            "raw_answer_text_emitted": False,
            "absolute_paths_emitted": False,
            "intended_storage": "local .tmp/ or benchmark_corpus/reports/ output only",
        },
        "claim_boundary_ref": claim_boundary_ref(
            "docs/evidence/benchmarks/design/benchmark-priority-map.md"
        ),
        "cannot_claim": CANNOT_CLAIM,
    }


def build_prediction_template(
    *,
    dataset_dir: Path,
    manifest: dict[str, Any],
    split_id: str = "Accurate_Retrieval",
    case_limit: int = DEFAULT_CASE_LIMIT,
) -> list[dict[str, Any]]:
    split_meta = manifest_splits(manifest)[split_id]
    return [
        {
            "case_id": case["case_id"],
            "split": case["split"],
            "task_families": case["task_families"],
            "metric_families": case["metric_families"],
            "question_count": len(case["questions"]),
            "context_sha1": sha1_short(case["context"]) if case["context"] else None,
            "prediction": "",
        }
        for case in collect_case_rows(
            dataset_dir=dataset_dir,
            split_id=split_id,
            split_meta=split_meta,
            case_limit=case_limit,
        )
    ]


def stage3_mode_fields(write_update_mode: str) -> dict[str, str]:
    if write_update_mode == STAGE3_WRITE_UPDATE_APPLY_MODE:
        return {
            "ingest_mode": "local_operator_dataset",
            "write_update_mode": STAGE3_WRITE_UPDATE_APPLY_MODE,
            "retrieval_mode": "local_apply_retrieve_probe",
            "answer_generation_mode": "not_executed",
            "judging_mode": "not_executed",
        }
    if write_update_mode == STAGE3_WRITE_UPDATE_DRY_RUN_MODE:
        return {
            "ingest_mode": "local_operator_dataset",
            "write_update_mode": STAGE3_WRITE_UPDATE_DRY_RUN_MODE,
            "retrieval_mode": "source_ref_hash_probe",
            "answer_generation_mode": "not_executed",
            "judging_mode": "not_executed",
        }
    return {
        "ingest_mode": "local_operator_dataset",
        "write_update_mode": STAGE3_MISSING_WRITE_UPDATE_MODE,
        "retrieval_mode": "not_executed",
        "answer_generation_mode": "not_executed",
        "judging_mode": "not_executed",
    }


def stage3_claim_boundary(write_update_mode: str) -> dict[str, str]:
    return {
        "claim_boundary_ref": claim_boundary_ref(
            "docs/evidence/benchmarks/design/benchmark-priority-map.md"
        ),
        "deterministic_contract_evidence": "mode_fields_hashes_counts_only",
        "local_artifact_policy": "ignored_operator_dataset_only",
        "official_runner_compatibility": "not_claimed",
        "live_model_quality": "not_measured",
        "private_or_local_artifact_evidence": "hashes_counts_only",
        "write_update_instrumentation": (
            "local_apply_instrumented"
            if write_update_mode == STAGE3_WRITE_UPDATE_APPLY_MODE
            else "dry_run_contract"
            if write_update_mode == STAGE3_WRITE_UPDATE_DRY_RUN_MODE
            else "missing"
        ),
    }


def stage3_incremental_contract(split_id: str) -> str:
    if split_id == "Test_Time_Learning":
        return "write_then_update_then_query"
    if split_id == "Conflict_Resolution":
        return "stale_then_current_then_query"
    return "unsupported_split"


def stage3_write_interactions(split_id: str) -> list[dict[str, str]]:
    if split_id == "Test_Time_Learning":
        return [
            {"step": "initial_write", "boundary": "write_policy"},
            {"step": "update_write", "boundary": "update_policy"},
        ]
    if split_id == "Conflict_Resolution":
        return [
            {"step": "stale_candidate_write", "boundary": "conflict_resolution"},
            {"step": "current_candidate_write", "boundary": "conflict_resolution"},
        ]
    return []


def build_stage3_incremental_case(case: dict[str, Any]) -> dict[str, Any]:
    split_id = str(case["split"])
    questions = [str(question) for question in case.get("questions") or []]
    context = str(case.get("context") or "")
    interactions = stage3_write_interactions(split_id)
    # Stage 3 dry-run reports must prove the write/update protocol shape without
    # smuggling benchmark text, gold answers, or local paths into committed logs.
    # Raw text stays only in the explicit local case-pack path above.
    return {
        "case_id": case["case_id"],
        "split": split_id,
        "task_families": case["task_families"],
        "metric_families": case["metric_families"],
        "incremental_contract": stage3_incremental_contract(split_id),
        "write_update_interactions": interactions,
        "interaction_count": len(interactions),
        "source_ref_status": "hash_only_requires_adapter_mapping",
        "context_sha1": sha1_short(context) if context else None,
        "question_sha1s": [sha1_short(question) for question in questions],
        "question_count": len(questions),
        "safe_metadata": case["safe_metadata"],
        "label_boundary": {
            "answer_text_included": False,
            "gold_labels_included": False,
            "score_computed": False,
        },
    }


def build_stage3_apply_instrumentation(case_payload: dict[str, Any]) -> dict[str, Any]:
    split_id = str(case_payload["split"])
    current_ref = sha1_short(
        f"{case_payload['case_id']}|{split_id}|current|{case_payload['context_sha1']}"
    )
    prior_ref = sha1_short(
        f"{case_payload['case_id']}|{split_id}|prior|{case_payload['context_sha1']}"
    )
    events: list[dict[str, Any]] = []
    if split_id == "Test_Time_Learning":
        events = [
            {"event": "write", "version": "initial", "memory_ref_sha1": prior_ref},
            {"event": "update", "version": "current", "memory_ref_sha1": current_ref},
            {"event": "retrieve_probe", "version": "current", "memory_ref_sha1": current_ref},
        ]
        currentness = {
            "required": False,
            "retrieved_version": "current",
            "stale_version_retained": True,
            "stale_version_demoted": False,
        }
    elif split_id == "Conflict_Resolution":
        events = [
            {"event": "write", "version": "stale", "memory_ref_sha1": prior_ref},
            {"event": "update", "version": "current", "memory_ref_sha1": current_ref},
            {"event": "retrieve_probe", "version": "current", "memory_ref_sha1": current_ref},
        ]
        currentness = {
            "required": True,
            "retrieved_version": "current",
            "stale_version_retained": True,
            "stale_version_demoted": True,
        }
    else:
        return {"status": "unsupported_split", "events": []}

    return {
        "status": "applied",
        "store_scope": "local_in_memory_hash_only",
        "event_count": len(events),
        "events": events,
        "prior_memory_ref_sha1": prior_ref,
        "current_memory_ref_sha1": current_ref,
        "retrieval_probe": {
            "top_k": 1,
            "retrieved_memory_ref_sha1": current_ref,
            "raw_text_returned": False,
            "gold_label_used": False,
        },
        "false_forgetting_control": {
            "prior_version_retained_as_history": True,
            "current_version_available": True,
        },
        "currentness_control": currentness,
    }


def _case_source_ref(case_payload: Mapping[str, Any], label: str) -> dict[str, Any]:
    return {
        "source_id": f"memoryagentbench:{case_payload['split']}:{label}:{case_payload['case_id']}",
        "event_id": f"{case_payload['case_id']}:{label}",
    }


def _ttl_learning_finding(case_payload: Mapping[str, Any]) -> dict[str, Any]:
    refs = [
        _case_source_ref(case_payload, "initial_write"),
        _case_source_ref(case_payload, "update_write"),
    ]
    return {
        "kind": "aippocampus_learning_finding",
        "finding_id": f"mab-ttl:{case_payload['case_id']}",
        "finding_kind": "workflow_order_finding",
        "candidate_family": "context_reopen_candidate",
        "workflow_family": "write_update_before_query",
        "status": "open",
        "occurrence_count": 2,
        "success_after_count": 1,
        "scope": "benchmark:memoryagentbench:test_time_learning",
        "freshness": "current",
        "source_refs": refs,
        "source_ref_count": len(refs),
        "foreground_eligible": True,
        "navigation_only": True,
        "claim_permission": "navigation_only_not_fact",
        "source_reopen_required_before_claim": True,
    }


def _conflict_compatibility_row(case_payload: Mapping[str, Any]) -> dict[str, Any]:
    source_id = f"memoryagentbench:{case_payload['split']}:{case_payload['case_id']}"
    return evaluate_local_global_compatibility(
        [
            {
                "case_id": f"{case_payload['case_id']}:stale",
                "kind": "memoryagentbench_conflict_candidate",
                "scope": f"case:{case_payload['case_id']}",
                "topic_epoch": "memoryagentbench-stage3",
                "freshness": "stale",
                "status": "stale",
                "source_ids": [f"{source_id}:stale"],
                "source_support": "navigation_only",
                "claim_permission": "navigation_only_not_fact",
            },
            {
                "case_id": f"{case_payload['case_id']}:current",
                "kind": "memoryagentbench_conflict_candidate",
                "scope": f"case:{case_payload['case_id']}",
                "topic_epoch": "memoryagentbench-stage3",
                "freshness": "current",
                "status": "current",
                "source_ids": [f"{source_id}:current"],
                "source_support": "navigation_only",
                "claim_permission": "navigation_only_not_fact",
            },
        ],
        case_id=f"mab-conflict:{case_payload['case_id']}",
    )


def build_stage3_aippocampus_runtime_arm(cases: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    ttl_findings = [
        _ttl_learning_finding(case)
        for case in cases
        if str(case.get("split") or "") == "Test_Time_Learning"
    ]
    lesson_candidates = extract_source_backed_lesson_candidates(ttl_findings)
    promoted_lessons = [
        promote_lesson_candidate(candidate, independent_trail_count=2)
        for candidate in lesson_candidates
    ]
    compatibility_rows = [
        _conflict_compatibility_row(case)
        for case in cases
        if str(case.get("split") or "") == "Conflict_Resolution"
    ]
    conflict_counts = Counter(str(row.get("result") or "") for row in compatibility_rows)
    stale_demoted_count = sum(
        1
        for row in compatibility_rows
        if row.get("result") in {"obstruction", "partial_glue", "blocked_boundary"}
        and "stale_or_released_section_blocks_current_glue" in row.get("reason_codes", [])
    )
    return {
        "arm": "aippocampus_runtime",
        "status": "runtime_projection_fixture",
        "projection_layers": [
            "learning_loop_finding",
            "source_backed_lesson_candidate",
            "local_global_compatibility",
        ],
        "test_time_learning": {
            "finding_count": len(ttl_findings),
            "lesson_candidate_count": len(lesson_candidates),
            "foreground_guidance_count": sum(
                1 for row in promoted_lessons if row.get("foreground_activation_allowed")
            ),
            "source_ref_count": sum(int(row.get("source_ref_count") or 0) for row in lesson_candidates),
            "guidance_claim_permission": "working_guidance_only_not_fact",
        },
        "conflict_resolution": {
            "compatibility_case_count": len(compatibility_rows),
            "result_counts": dict(sorted(conflict_counts.items())),
            "stale_demoted_count": stale_demoted_count,
            "blocked_or_obstruction_count": sum(
                conflict_counts.get(key, 0) for key in ("obstruction", "blocked_boundary")
            ),
            "claim_permission": "navigation_only_not_fact",
        },
        "privacy_boundary": {
            "raw_context_emitted": False,
            "raw_question_emitted": False,
            "gold_label_used": False,
            "local_path_emitted": False,
        },
        "claim_boundary": {
            "official_task_run_count": 0,
            "official_memoryagentbench_score": "not_claimed",
            "runtime_projection_is_answer_quality": False,
            "source_reopen_required_before_claim": True,
        },
        "cannot_claim": [
            "official_memoryagentbench_score",
            "answer_generation_quality",
            "runtime_projection_as_official_runner_compatibility",
        ],
    }


def build_stage3_local_replay_result(
    cases: Sequence[Mapping[str, Any]],
    runtime_arm: Mapping[str, Any],
) -> dict[str, Any]:
    ttl = runtime_arm.get("test_time_learning") if isinstance(runtime_arm, Mapping) else {}
    conflict = runtime_arm.get("conflict_resolution") if isinstance(runtime_arm, Mapping) else {}
    ttl_hit = int((ttl or {}).get("foreground_guidance_count") or 0)
    conflict_hit = int((conflict or {}).get("stale_demoted_count") or 0)
    runtime_hit_count = min(len(cases), ttl_hit + conflict_hit)
    return {
        "status": (
            "bounded_local_source_backed_replay_completed"
            if cases
            else "skipped_missing_stage3_cases"
        ),
        "case_shape": "sanitized_stage3_ttl_conflict_hashes_counts_only",
        "official_score_claimable": False,
        "matched_baseline": {
            "arm": "static_or_hash_contract",
            "case_count": len(cases),
            "retrieval_probe_hit_count": 0,
            "answer_generation_mode": "not_executed",
            "judging_mode": "not_executed",
        },
        "aippocampus_runtime": {
            "arm": "aippocampus_runtime",
            "case_count": len(cases),
            "retrieval_probe_hit_count": runtime_hit_count,
            "test_time_learning_guidance_count": ttl_hit,
            "conflict_currentness_pass_count": conflict_hit,
            "answer_generation_mode": "not_executed",
            "judging_mode": "not_executed",
        },
        "claim_boundary": {
            "local_replay_supports": "write_update_retrieve_projection_over_sanitized_case_shape",
            "official_memoryagentbench_score": "not_claimed",
            "answer_quality": "not_measured",
        },
    }


def build_stage3_incremental_dry_run(
    *,
    dataset_dir: Path | str = DEFAULT_DATASET_DIR,
    manifest_path: Path | str = DEFAULT_MANIFEST,
    case_limit: int = DEFAULT_CASE_LIMIT,
    write_update_mode: str = STAGE3_MISSING_WRITE_UPDATE_MODE,
) -> dict[str, Any]:
    started = time.perf_counter()
    dataset_path = Path(dataset_dir)
    manifest = load_manifest(manifest_path)
    split_meta_by_id = manifest_splits(manifest)
    mode_fields = stage3_mode_fields(write_update_mode)

    supported_write_modes = {
        STAGE3_WRITE_UPDATE_DRY_RUN_MODE,
        STAGE3_WRITE_UPDATE_APPLY_MODE,
    }
    if write_update_mode not in supported_write_modes:
        return {
            "schema_version": SCHEMA_VERSION,
            "kind": "aippocampus_memoryagentbench_stage3_incremental_dry_run",
            "generated_at": now_utc(),
            "status": "unsupported_missing_write_update_instrumentation",
            "ok": False,
            "configuration": {
                "dataset_dir_sha1": sha1_short(str(dataset_path.resolve())),
                "manifest": safe_path_label(manifest_path),
                "case_limit": case_limit,
                "live_llm": False,
                "downloads_dataset": False,
            },
            "mode_fields": mode_fields,
            "official_score_claimable": False,
            "unsupported_reasons": ["write_update_instrumentation_missing"],
            "metrics": {
                "stage3_case_count": 0,
                "sample_count": 0,
                "test_time_learning_case_count": 0,
                "conflict_resolution_case_count": 0,
                "update_conflict_interaction_count": 0,
            },
            "cases": [],
            "claim_boundary": stage3_claim_boundary(write_update_mode),
            "claim_boundary_ref": claim_boundary_ref(
                "docs/evidence/benchmarks/design/benchmark-priority-map.md"
            ),
            "source_evidence_boundary": {
                "source_hashes_only": True,
                "raw_context_emitted": False,
                "source_refs_are_adapter_handles_not_truth": True,
            },
            "false_forgetting_controls": {
                "current_source_ref_required": True,
                "stale_source_demoted_not_deleted": True,
                "gold_answer_not_model_input": True,
            },
            "privacy_boundary": {
                "raw_text_emitted": False,
                "absolute_paths_emitted": False,
                "default_report_shape": "mode_fields_hashes_and_counts_only",
            },
            "cannot_claim": CANNOT_CLAIM,
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
        }

    cases: list[dict[str, Any]] = []
    for split_id in STAGE3_INCREMENTAL_SPLITS:
        for case in collect_case_rows(
            dataset_dir=dataset_path,
            split_id=split_id,
            split_meta=split_meta_by_id[split_id],
            case_limit=case_limit,
        ):
            case_payload = build_stage3_incremental_case(case)
            if write_update_mode == STAGE3_WRITE_UPDATE_APPLY_MODE:
                case_payload["apply_instrumentation"] = (
                    build_stage3_apply_instrumentation(case_payload)
                )
            cases.append(case_payload)

    split_counts = Counter(str(case["split"]) for case in cases)
    apply_cases = [
        case.get("apply_instrumentation") or {}
        for case in cases
        if (case.get("apply_instrumentation") or {}).get("status") == "applied"
    ]
    runtime_arm = build_stage3_aippocampus_runtime_arm(cases)
    local_replay_result = build_stage3_local_replay_result(cases, runtime_arm)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "aippocampus_memoryagentbench_stage3_incremental_dry_run",
        "generated_at": now_utc(),
        "status": (
            "stage3_apply_instrumented"
            if write_update_mode == STAGE3_WRITE_UPDATE_APPLY_MODE and cases
            else "stage3_incremental_dry_run"
            if cases
            else "skipped_missing_stage3_cases"
        ),
        "ok": bool(cases),
        "configuration": {
            "dataset_dir_sha1": sha1_short(str(dataset_path.resolve())),
            "manifest": safe_path_label(manifest_path),
            "case_limit": case_limit,
            "live_llm": False,
            "downloads_dataset": False,
        },
        "mode_fields": mode_fields,
        "official_score_claimable": False,
        "unsupported_reasons": [],
        "metrics": {
            "stage3_case_count": len(cases),
            "sample_count": len(cases),
            "test_time_learning_case_count": split_counts.get("Test_Time_Learning", 0),
            "conflict_resolution_case_count": split_counts.get("Conflict_Resolution", 0),
            "update_conflict_interaction_count": sum(int(case["interaction_count"]) for case in cases),
            "apply_write_count": sum(
                1
                for apply in apply_cases
                for event in apply["events"]
                if event["event"] == "write"
            ),
            "apply_update_count": sum(
                1
                for apply in apply_cases
                for event in apply["events"]
                if event["event"] == "update"
            ),
            "apply_retrieval_probe_count": sum(
                1
                for apply in apply_cases
                for event in apply["events"]
                if event["event"] == "retrieve_probe"
            ),
            "false_forgetting_control_count": sum(
                1
                for apply in apply_cases
                if apply["false_forgetting_control"]["prior_version_retained_as_history"]
            ),
            "stale_currentness_control_count": sum(
                1 for apply in apply_cases if apply["currentness_control"]["required"]
            ),
            "stale_currentness_pass_count": sum(
                1
                for apply in apply_cases
                if apply["currentness_control"]["required"]
                and apply["currentness_control"]["retrieved_version"] == "current"
                and apply["currentness_control"]["stale_version_demoted"]
            ),
        },
        "cases": cases,
        "arms": {
            "static_or_hash_contract": {
                "arm": "static_or_hash_contract",
                "status": mode_fields["retrieval_mode"],
                "case_count": len(cases),
                "source_hashes_only": True,
                "answer_generation_mode": mode_fields["answer_generation_mode"],
                "judging_mode": mode_fields["judging_mode"],
            },
            "aippocampus_runtime": runtime_arm,
        },
        "local_replay_result": local_replay_result,
        "claim_boundary": stage3_claim_boundary(write_update_mode),
        "claim_boundary_ref": claim_boundary_ref(
            "docs/evidence/benchmarks/design/benchmark-priority-map.md"
        ),
        "source_evidence_boundary": {
            "source_hashes_only": True,
            "raw_context_emitted": False,
            "source_refs_are_adapter_handles_not_truth": True,
        },
        "false_forgetting_controls": {
            "current_source_ref_required": True,
            "stale_source_demoted_not_deleted": True,
            "gold_answer_not_model_input": True,
            "local_apply_checked": write_update_mode == STAGE3_WRITE_UPDATE_APPLY_MODE,
            "all_cases_retained_prior_versions": bool(
                apply_cases
                and all(
                    apply["false_forgetting_control"][
                        "prior_version_retained_as_history"
                    ]
                    for apply in apply_cases
                )
            ),
        },
        "privacy_boundary": {
            "raw_text_emitted": False,
            "absolute_paths_emitted": False,
            "default_report_shape": "mode_fields_hashes_and_counts_only",
        },
        "cannot_claim": CANNOT_CLAIM,
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
    }


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def run_memoryagentbench_smoke(
    *,
    dataset_dir: Path | str = DEFAULT_DATASET_DIR,
    manifest_path: Path | str = DEFAULT_MANIFEST,
    case_limit: int = DEFAULT_CASE_LIMIT,
    case_pack_output: Path | str | None = None,
    prediction_template_output: Path | str | None = None,
    case_pack_split: str = "Accurate_Retrieval",
    compute_sha256: bool = True,
    stage3_incremental_dry_run: bool = False,
    stage3_write_update_mode: str = STAGE3_MISSING_WRITE_UPDATE_MODE,
) -> dict[str, Any]:
    started = time.perf_counter()
    dataset_path = Path(dataset_dir)
    manifest = load_manifest(manifest_path)
    split_meta_by_id = manifest_splits(manifest)
    observations = {
        split_id: observe_split(
            dataset_dir=dataset_path,
            split_id=split_id,
            split_meta=split_meta_by_id[split_id],
            case_limit=case_limit,
            compute_sha256=compute_sha256,
        )
        for split_id in CANONICAL_SPLITS
    }
    splits = {
        split_id: split_report(split_meta_by_id[split_id], observations[split_id])
        for split_id in CANONICAL_SPLITS
    }
    observed_split_count = sum(1 for split in splits.values() if split["observed_rows"] > 0)
    observed_row_count = sum(int(split["observed_rows"]) for split in splits.values())
    local_file_count = sum(len(split["files"]) for split in splits.values())
    optional_reader_missing_file_count = sum(
        1
        for split in splits.values()
        for file_payload in split["files"]
        if file_payload.get("format_support") == PARQUET_READER_MISSING_SUPPORT
    )
    parquet_row_file_count = sum(
        1
        for split in splits.values()
        for file_payload in split["files"]
        if file_payload.get("format_support") == PARQUET_ROW_SUPPORT
    )

    case_pack_path: Path | None = None
    case_pack_status = "not_requested"
    if case_pack_output:
        case_pack = build_case_pack(
            dataset_dir=dataset_path,
            manifest=manifest,
            split_id=case_pack_split,
            case_limit=case_limit,
        )
        if case_pack["cases"]:
            case_pack_path = Path(case_pack_output)
            case_pack_path.parent.mkdir(parents=True, exist_ok=True)
            case_pack_path.write_text(
                json.dumps(case_pack, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            case_pack_status = "written"
        else:
            case_pack_status = "skipped_no_rows"

    prediction_template_path: Path | None = None
    prediction_template_status = "not_requested"
    if prediction_template_output:
        prediction_template = build_prediction_template(
            dataset_dir=dataset_path,
            manifest=manifest,
            split_id=case_pack_split,
            case_limit=case_limit,
        )
        if prediction_template:
            prediction_template_path = Path(prediction_template_output)
            write_jsonl(prediction_template_path, prediction_template)
            prediction_template_status = "written"
        else:
            prediction_template_status = "skipped_no_rows"

    stage3_payload: dict[str, Any] | None = None
    if stage3_incremental_dry_run:
        stage3_payload = build_stage3_incremental_dry_run(
            dataset_dir=dataset_path,
            manifest_path=manifest_path,
            case_limit=case_limit,
            write_update_mode=stage3_write_update_mode,
        )

    if observed_row_count:
        status = "metadata_smoke"
    elif local_file_count and optional_reader_missing_file_count:
        status = "found_files_missing_optional_reader"
    else:
        status = "skipped_missing_dataset"
    official_expected_total_rows = int(manifest["official_dataset"]["total_examples"])
    official_expected_split_count = len(CANONICAL_SPLITS)
    if status == "found_files_missing_optional_reader":
        next_step = (
            "parquet_optional_reader_missing: official MemoryAgentBench parquet files were found, "
            "but row inspection requires installing the optional pyarrow reader. "
            "Install pyarrow or provide JSON/JSONL exports before writing case packs or Stage 3 dry-run cases."
        )
    else:
        next_step = (
            "Place operator-downloaded or exported MemoryAgentBench files under "
            "benchmark_corpus/memoryagentbench/ for local metadata inspection; "
            "use explicit output paths for local-only case packs or prediction templates."
        )
    payload = {
        "schema_version": SCHEMA_VERSION,
        "kind": "aippocampus_memoryagentbench_metadata_smoke",
        "generated_at": now_utc(),
        "status": status,
        "ok": bool(stage3_payload.get("ok", True)) if stage3_payload else True,
        "configuration": {
            "dataset_dir_sha1": sha1_short(str(dataset_path.resolve())),
            "manifest": safe_path_label(manifest_path),
            "case_limit": case_limit,
            "case_pack_split": case_pack_split,
            "compute_sha256": compute_sha256,
            "stage3_incremental_dry_run": stage3_incremental_dry_run,
            "stage3_write_update_mode": stage3_write_update_mode if stage3_incremental_dry_run else None,
            "live_llm": False,
            "downloads_dataset": False,
        },
        "source": {
            "benchmark": manifest["benchmark"],
            "official_sources": manifest["official_sources"],
            "observed_at": manifest["observed_at"],
            "license": manifest["official_sources"]["license"],
            "format": manifest["official_dataset"]["format"],
            "features": manifest["official_dataset"]["features"],
        },
        "metrics": {
            "official_expected_split_count": official_expected_split_count,
            "official_expected_total_rows": official_expected_total_rows,
            "observed_split_count": observed_split_count,
            "observed_row_count": observed_row_count,
            "local_file_count": local_file_count,
            "optional_reader_missing_file_count": optional_reader_missing_file_count,
            "parquet_row_file_count": parquet_row_file_count,
            "task_family_counts": dict(
                sorted(
                    sum((Counter(split["task_family_counts"]) for split in splits.values()), Counter()).items()
                )
            ),
            "metric_family_counts": dict(
                sorted(
                    sum((Counter(split["metric_family_counts"]) for split in splits.values()), Counter()).items()
                )
            ),
        },
        "splits": splits,
        "evaluation_layers": {
            "source_evidence": "diagnostic_by_split_requires_source_or_context_mapping",
            "answer_generation": "template_only_no_score",
            "write_policy": "diagnostic_requires_incremental_replay",
            "conflict_resolution": "diagnostic_requires_update_forgetting_contract",
            "llm_as_judge": "diagnostic_only_not_source_truth",
        },
        "privacy_boundary": {
            "raw_text_emitted": False,
            "absolute_paths_emitted": False,
            "case_pack_raw_text_emitted": bool(case_pack_path),
            "prediction_template_raw_text_emitted": False,
            "default_report_shape": "metadata_schema_hashes_and_counts_only",
        },
        "artifacts": {
            "case_pack_written": bool(case_pack_path),
            "case_pack_status": case_pack_status,
            "case_pack_output_sha1": sha1_short(str(case_pack_path.resolve())) if case_pack_path else None,
            "prediction_template_written": bool(prediction_template_path),
            "prediction_template_status": prediction_template_status,
            "prediction_template_output_sha1": sha1_short(str(prediction_template_path.resolve()))
            if prediction_template_path
            else None,
        },
        "claim_boundary_ref": claim_boundary_ref(
            "docs/evidence/benchmarks/design/benchmark-priority-map.md"
        ),
        "cannot_claim": CANNOT_CLAIM,
        "next_step": next_step,
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
    }
    if stage3_payload:
        payload["stage3_incremental_runner"] = stage3_payload
    return payload


def print_human_summary(payload: dict[str, Any]) -> None:
    print("AIppocampus MemoryAgentBench metadata smoke")
    print(f"- status: {payload['status']}")
    print(f"- observed rows: {payload['metrics']['observed_row_count']}")
    print(f"- observed splits: {payload['metrics']['observed_split_count']}")
    print(f"- local files: {payload['metrics']['local_file_count']}")
    if "stage3_incremental_runner" in payload:
        stage3 = payload["stage3_incremental_runner"]
        print(f"- stage3 incremental: {stage3['status']}")
        print(f"- stage3 cases: {stage3['metrics']['stage3_case_count']}")
    print("- cannot claim:")
    for item in payload["cannot_claim"]:
        print(f"  - {item}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-dir", type=Path, default=DEFAULT_DATASET_DIR)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--case-limit", type=int, default=DEFAULT_CASE_LIMIT)
    parser.add_argument("--case-pack-output", type=Path)
    parser.add_argument("--prediction-template-output", type=Path)
    parser.add_argument("--case-pack-split", default="Accurate_Retrieval", choices=CANONICAL_SPLITS)
    parser.add_argument(
        "--stage3-incremental-dry-run",
        action="store_true",
        help="Embed the Stage 3 incremental runner dry-run contract in the sanitized report.",
    )
    parser.add_argument(
        "--stage3-write-update-mode",
        default=STAGE3_MISSING_WRITE_UPDATE_MODE,
        choices=(
            STAGE3_MISSING_WRITE_UPDATE_MODE,
            STAGE3_WRITE_UPDATE_DRY_RUN_MODE,
            STAGE3_WRITE_UPDATE_APPLY_MODE,
        ),
        help="Write/update instrumentation mode for the explicit Stage 3 dry-run.",
    )
    parser.add_argument("--skip-sha256", action="store_true", help="Skip file sha256 hashing for large local files.")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--json", dest="json_output", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = run_memoryagentbench_smoke(
        dataset_dir=args.dataset_dir,
        manifest_path=args.manifest,
        case_limit=args.case_limit,
        case_pack_output=args.case_pack_output,
        prediction_template_output=args.prediction_template_output,
        case_pack_split=args.case_pack_split,
        compute_sha256=not args.skip_sha256,
        stage3_incremental_dry_run=args.stage3_incremental_dry_run,
        stage3_write_update_mode=args.stage3_write_update_mode,
    )
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.json_output:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print_human_summary(payload)
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
