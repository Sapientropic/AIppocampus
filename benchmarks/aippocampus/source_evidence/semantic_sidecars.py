"""Semantic-scope sidecar materialization for standard public source artifacts."""

from __future__ import annotations

import concurrent.futures
import json
import time
from pathlib import Path
from typing import Any

from aippocampus_runtime.source.semantic_scope_labels import (
    SEMANTIC_SCOPE_LABELS_FILENAME,
    clean_messages_by_id,
    load_semantic_scope_labels,
    semantic_scope_label_rows_from_findings,
    write_semantic_scope_label_sidecar,
)
from aippocampus_runtime.subconscious.runtime import compact_usage

from .defaults import (
    DEFAULT_PUBLIC_SEMANTIC_MAX_CANDIDATES,
    DEFAULT_PUBLIC_SEMANTIC_MAX_TOKENS,
    DEFAULT_PUBLIC_SEMANTIC_MIN_CONFIDENCE,
    DEFAULT_PUBLIC_SEMANTIC_TIMEOUT,
    PublicSemanticLabelerFn,
)
from .public_semantic import (
    normalize_public_semantic_findings,
    public_semantic_candidate_messages,
    run_public_semantic_labeler,
)
from .reporting import now_utc, safe_rate, sha1_text

SOURCE_SEMANTIC_SIDECAR_MATERIALIZER_OFF = "off"
SOURCE_SEMANTIC_SIDECAR_MATERIALIZER_PUBLIC = "public_semantic_labeler"
SOURCE_SEMANTIC_SIDECAR_MATERIALIZERS = {
    SOURCE_SEMANTIC_SIDECAR_MATERIALIZER_OFF,
    SOURCE_SEMANTIC_SIDECAR_MATERIALIZER_PUBLIC,
}
SOURCE_SEMANTIC_SIDECAR_POLICY_VERSION = (
    "standard-public-semantic-scope-sidecar-v1"
)


def source_semantic_sidecar_materializer_contract(
    *,
    materializer: str,
    max_candidates: int,
    max_provider_calls: int,
    workers: int,
    timeout: int,
    max_tokens: int,
    min_confidence: float,
) -> dict[str, Any]:
    return {
        "policy_version": SOURCE_SEMANTIC_SIDECAR_POLICY_VERSION,
        "materializer": materializer,
        "sidecar_filename": SEMANTIC_SCOPE_LABELS_FILENAME,
        "finding_kind": "semantic_scope_labels",
        "job": "semantic_scope_labeling",
        "builder": "aippocampus_runtime.source.semantic_scope_labels",
        "candidate_selector": "public_semantic_candidate_messages",
        "max_candidates_per_source": int(max_candidates),
        "max_provider_calls": int(max_provider_calls),
        "workers": int(workers),
        "timeout": int(timeout),
        "max_tokens": int(max_tokens),
        "min_confidence": float(min_confidence),
        "input_boundary": {
            "cold_fill_visible": [
                "public_benchmark_clean_source_text",
                "message_id",
                "turn_id",
                "source_line",
                "role",
                "phase",
            ],
            "withheld_from_materializer": [
                "gold_answer",
                "expected_lines",
                "expected_sessions",
                "has_answer_labels",
                "judge_labels",
                "miss_taxonomy",
            ],
        },
        "output_boundary": {
            "semantic_scope_labels_are_navigation_only": True,
            "source_reopen_required_for_claims": True,
            "raw_source_text_emitted": False,
            "sidecar_values_emitted": False,
        },
    }


def _iter_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict):
                rows.append(item)
    return rows


def _usage_sum(rows: list[dict[str, Any]]) -> dict[str, Any]:
    usage: dict[str, Any] = {}
    for row in rows:
        for key, value in (row.get("usage") or {}).items():
            if isinstance(value, bool) or not isinstance(value, int | float):
                continue
            usage[str(key)] = usage.get(str(key), 0) + value
    return compact_usage(usage)


def _latency_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    values = [
        float(row["latency_ms"])
        for row in rows
        if isinstance(row.get("latency_ms"), int | float)
    ]
    if not values:
        return {"count": 0}
    return {
        "count": len(values),
        "total": round(sum(values), 2),
        "avg": round(sum(values) / len(values), 2),
        "max": round(max(values), 2),
    }


def _clean_source_dir(case: dict[str, Any]) -> Path:
    return Path(case["sqlite_path"]).with_name("messages.jsonl").parent


def _load_clean_source_messages(clean_source_dir: Path) -> list[dict[str, Any]]:
    return _iter_jsonl(clean_source_dir / "messages.jsonl")


def _reused_sidecar_result(clean_source_dir: Path, *, case_id: str) -> dict[str, Any]:
    reviewed = load_semantic_scope_labels(clean_source_dir)
    return {
        "case_id": case_id,
        "status": "reused_existing_sidecar",
        "provider_call_count": 0,
        "candidate_count": 0,
        "finding_count": 0,
        "sidecar_written": False,
        "sidecar_row_count": len(reviewed),
        "reviewed_sidecar_row_count": len(reviewed),
        "sidecar_sha1": sha1_text(
            (clean_source_dir / SEMANTIC_SCOPE_LABELS_FILENAME).read_text(
                encoding="utf-8"
            )
        )[:16],
        "usage": {},
        "latency_ms": 0.0,
        "errors": [],
    }


def materialize_semantic_sidecar_for_case(
    case: dict[str, Any],
    *,
    max_candidates: int,
    timeout: int,
    max_tokens: int,
    min_confidence: float,
    labeler_fn: PublicSemanticLabelerFn | None = None,
    rebuild_sidecar: bool = False,
) -> dict[str, Any]:
    started = time.perf_counter()
    case_id = str(case.get("case_id") or "")
    clean_source_dir = _clean_source_dir(case)
    sidecar_path = clean_source_dir / SEMANTIC_SCOPE_LABELS_FILENAME
    if sidecar_path.exists() and not rebuild_sidecar:
        return _reused_sidecar_result(clean_source_dir, case_id=case_id)

    messages = _load_clean_source_messages(clean_source_dir)
    candidates = public_semantic_candidate_messages(
        messages,
        max_candidates=max_candidates,
    )
    if not candidates:
        write_semantic_scope_label_sidecar(clean_source_dir, [])
        return {
            "case_id": case_id,
            "status": "empty_candidate_set",
            "provider_call_count": 0,
            "candidate_count": 0,
            "finding_count": 0,
            "sidecar_written": True,
            "sidecar_row_count": 0,
            "reviewed_sidecar_row_count": 0,
            "sidecar_sha1": sha1_text(sidecar_path.read_text(encoding="utf-8"))[:16],
            "usage": {},
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            "errors": ["empty candidate set"],
        }

    try:
        labeler_payload = (
            labeler_fn(candidates)
            if labeler_fn
            else run_public_semantic_labeler(
                candidates,
                timeout=timeout,
                max_tokens=max_tokens,
            )
        )
    except Exception as exc:  # pragma: no cover - live provider boundary
        return {
            "case_id": case_id,
            "status": "semantic_labeler_error",
            "provider_call_count": 1,
            "candidate_count": len(candidates),
            "finding_count": 0,
            "sidecar_written": False,
            "sidecar_row_count": 0,
            "reviewed_sidecar_row_count": 0,
            "sidecar_sha1": "",
            "usage": {},
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            "errors": [type(exc).__name__],
        }
    if not labeler_payload.get("available", True):
        return {
            "case_id": case_id,
            "status": "semantic_labeler_unavailable",
            "provider_call_count": 0,
            "candidate_count": len(candidates),
            "finding_count": 0,
            "sidecar_written": False,
            "sidecar_row_count": 0,
            "reviewed_sidecar_row_count": 0,
            "sidecar_sha1": "",
            "usage": {},
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            "errors": [str(item) for item in labeler_payload.get("errors") or []],
        }

    messages_by_id = clean_messages_by_id(clean_source_dir)
    findings = normalize_public_semantic_findings(
        [item for item in labeler_payload.get("findings") or [] if isinstance(item, dict)],
        candidates,
    )
    sidecar_rows = semantic_scope_label_rows_from_findings(
        findings,
        messages_by_id,
        min_confidence=min_confidence,
    )
    write_semantic_scope_label_sidecar(clean_source_dir, sidecar_rows)
    reviewed_sidecar = load_semantic_scope_labels(clean_source_dir)
    return {
        "case_id": case_id,
        "status": "materialized_sidecar",
        "provider_call_count": 1,
        "candidate_count": len(candidates),
        "finding_count": len(findings),
        "sidecar_written": True,
        "sidecar_row_count": len(sidecar_rows),
        "reviewed_sidecar_row_count": len(reviewed_sidecar),
        "sidecar_sha1": sha1_text(sidecar_path.read_text(encoding="utf-8"))[:16],
        "usage": compact_usage(labeler_payload.get("usage") or {}),
        "latency_ms": round((time.perf_counter() - started) * 1000, 2),
        "errors": [str(item) for item in labeler_payload.get("errors") or []],
    }


def summarize_source_semantic_sidecar_materialization(
    rows: list[dict[str, Any]],
    *,
    materializer: str,
    max_candidates: int,
    max_provider_calls: int,
    workers: int,
    timeout: int,
    max_tokens: int,
    min_confidence: float,
    requested_case_count: int,
) -> dict[str, Any]:
    status_counts: dict[str, int] = {}
    for row in rows:
        status = str(row.get("status") or "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1
    provider_call_count = sum(int(row.get("provider_call_count") or 0) for row in rows)
    sidecar_count = sum(
        1
        for row in rows
        if int(row.get("reviewed_sidecar_row_count") or row.get("sidecar_row_count") or 0) > 0
    )
    reviewed_rows = sum(int(row.get("reviewed_sidecar_row_count") or 0) for row in rows)
    error_count = sum(len(list(row.get("errors") or [])) for row in rows)
    skipped_budget = max(0, int(requested_case_count) - len(rows))
    status = (
        "measured_materialized_semantic_scope_sidecars"
        if sidecar_count > 0 and error_count == 0 and skipped_budget == 0
        else "partial_materialized_semantic_scope_sidecars"
        if sidecar_count > 0
        else "no_semantic_scope_sidecars_materialized"
    )
    return {
        "schema_version": 1,
        "kind": "standard_public_source_semantic_sidecar_materialization",
        "generated_at": now_utc(),
        "status": status,
        "policy_version": SOURCE_SEMANTIC_SIDECAR_POLICY_VERSION,
        "materializer": materializer,
        "contract": source_semantic_sidecar_materializer_contract(
            materializer=materializer,
            max_candidates=max_candidates,
            max_provider_calls=max_provider_calls,
            workers=workers,
            timeout=timeout,
            max_tokens=max_tokens,
            min_confidence=min_confidence,
        ),
        "requested_case_count": int(requested_case_count),
        "attempted_case_count": len(rows),
        "skipped_call_budget_case_count": skipped_budget,
        "provider_call_count": provider_call_count,
        "case_provider_call_rate": safe_rate(provider_call_count, len(rows)),
        "source_count": len(rows),
        "sidecar_count": sidecar_count,
        "semantic_scope_sidecar_count": sidecar_count,
        "sidecar_row_count": sum(int(row.get("sidecar_row_count") or 0) for row in rows),
        "reviewed_sidecar_row_count": reviewed_rows,
        "semantic_scope_label_row_count": reviewed_rows,
        "candidate_message_count": sum(int(row.get("candidate_count") or 0) for row in rows),
        "finding_count": sum(int(row.get("finding_count") or 0) for row in rows),
        "status_counts": dict(sorted(status_counts.items())),
        "error_count": error_count,
        "usage": _usage_sum(rows),
        "latency_ms": _latency_summary(rows),
        "raw_source_text_emitted": False,
        "sidecar_values_emitted": False,
        "absolute_paths_emitted": False,
        "source_text_sent_to_labeler": materializer
        == SOURCE_SEMANTIC_SIDECAR_MATERIALIZER_PUBLIC,
        "source_text_is_public_benchmark_data": True,
        "hot_query_provider_call_count": 0,
        "source_reopen_required_for_claims": True,
    }


def materialize_source_semantic_sidecars(
    cases: list[dict[str, Any]],
    *,
    materializer: str,
    max_candidates: int = DEFAULT_PUBLIC_SEMANTIC_MAX_CANDIDATES,
    max_provider_calls: int = 0,
    workers: int = 1,
    timeout: int = DEFAULT_PUBLIC_SEMANTIC_TIMEOUT,
    max_tokens: int = DEFAULT_PUBLIC_SEMANTIC_MAX_TOKENS,
    min_confidence: float = DEFAULT_PUBLIC_SEMANTIC_MIN_CONFIDENCE,
    labeler_fn: PublicSemanticLabelerFn | None = None,
    rebuild_sidecars: bool = False,
) -> dict[str, Any]:
    resolved_materializer = str(materializer or "").strip().casefold()
    if resolved_materializer not in SOURCE_SEMANTIC_SIDECAR_MATERIALIZERS:
        raise ValueError(f"unsupported source semantic sidecar materializer: {materializer}")
    if resolved_materializer == SOURCE_SEMANTIC_SIDECAR_MATERIALIZER_OFF:
        return summarize_source_semantic_sidecar_materialization(
            [],
            materializer=resolved_materializer,
            max_candidates=max_candidates,
            max_provider_calls=max_provider_calls,
            workers=workers,
            timeout=timeout,
            max_tokens=max_tokens,
            min_confidence=min_confidence,
            requested_case_count=len(cases),
        )
    if int(max_provider_calls) <= 0:
        raise ValueError(
            "source semantic sidecar materialization requires --max-source-semantic-sidecar-calls"
        )

    bounded_cases = cases[: max(0, int(max_provider_calls))]

    def run(case: dict[str, Any]) -> dict[str, Any]:
        return materialize_semantic_sidecar_for_case(
            case,
            max_candidates=max_candidates,
            timeout=timeout,
            max_tokens=max_tokens,
            min_confidence=min_confidence,
            labeler_fn=labeler_fn,
            rebuild_sidecar=rebuild_sidecars,
        )

    if int(workers) > 1:
        with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, int(workers))) as executor:
            rows = list(executor.map(run, bounded_cases))
    else:
        rows = [run(case) for case in bounded_cases]
    return summarize_source_semantic_sidecar_materialization(
        rows,
        materializer=resolved_materializer,
        max_candidates=max_candidates,
        max_provider_calls=max_provider_calls,
        workers=workers,
        timeout=timeout,
        max_tokens=max_tokens,
        min_confidence=min_confidence,
        requested_case_count=len(cases),
    )
