"""Semantic-scope sidecar materialization for standard public source artifacts."""

from __future__ import annotations

import concurrent.futures
import json
import threading
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
    public_semantic_full_source_candidate_messages,
    run_public_semantic_labeler,
)
from .reporting import now_utc, safe_rate, sha1_text

SOURCE_SEMANTIC_SIDECAR_MATERIALIZER_OFF = "off"
SOURCE_SEMANTIC_SIDECAR_MATERIALIZER_PUBLIC = "public_semantic_labeler"
SOURCE_SEMANTIC_SIDECAR_MATERIALIZER_PUBLIC_FULL_SOURCE = (
    "public_semantic_labeler_full_source"
)
SOURCE_SEMANTIC_SIDECAR_MATERIALIZERS = {
    SOURCE_SEMANTIC_SIDECAR_MATERIALIZER_OFF,
    SOURCE_SEMANTIC_SIDECAR_MATERIALIZER_PUBLIC,
    SOURCE_SEMANTIC_SIDECAR_MATERIALIZER_PUBLIC_FULL_SOURCE,
}
SOURCE_SEMANTIC_SIDECAR_POLICY_VERSION = (
    "standard-public-semantic-scope-sidecar-v1"
)
SEMANTIC_SCOPE_SIDECAR_MANIFEST_FILENAME = "semantic-scope-labels.manifest.json"


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
        "candidate_selector": (
            "public_semantic_full_source_candidate_messages"
            if materializer == SOURCE_SEMANTIC_SIDECAR_MATERIALIZER_PUBLIC_FULL_SOURCE
            else "public_semantic_candidate_messages"
        ),
        "full_source_message_coverage": (
            materializer == SOURCE_SEMANTIC_SIDECAR_MATERIALIZER_PUBLIC_FULL_SOURCE
        ),
        "max_candidates_per_source_or_batch": int(max_candidates),
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


def _clean_source_messages_sha1(clean_source_dir: Path) -> str:
    path = clean_source_dir / "messages.jsonl"
    if not path.exists():
        return ""
    return sha1_text(path.read_text(encoding="utf-8"))


def _sidecar_manifest_path(clean_source_dir: Path) -> Path:
    return clean_source_dir / SEMANTIC_SCOPE_SIDECAR_MANIFEST_FILENAME


def _sidecar_path(clean_source_dir: Path) -> Path:
    return clean_source_dir / SEMANTIC_SCOPE_LABELS_FILENAME


def _read_sidecar_manifest(clean_source_dir: Path) -> dict[str, Any] | None:
    path = _sidecar_manifest_path(clean_source_dir)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _write_sidecar_manifest(clean_source_dir: Path, payload: dict[str, Any]) -> None:
    path = _sidecar_manifest_path(clean_source_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    tmp.replace(path)


def _remove_sidecar_files(clean_source_dir: Path) -> None:
    for path in (_sidecar_path(clean_source_dir), _sidecar_manifest_path(clean_source_dir)):
        try:
            path.unlink()
        except FileNotFoundError:
            continue


def _sidecar_manifest_payload(
    clean_source_dir: Path,
    *,
    materializer: str,
    max_candidates: int,
    min_confidence: float,
    candidate_coverage_mode: str,
    candidate_count: int,
    candidate_batch_count: int,
    sidecar_sha1: str,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "kind": "standard_public_source_semantic_sidecar_manifest",
        "policy_version": SOURCE_SEMANTIC_SIDECAR_POLICY_VERSION,
        "materializer": materializer,
        "source_messages_sha1": _clean_source_messages_sha1(clean_source_dir),
        "sidecar_sha1": sidecar_sha1,
        "candidate_coverage_mode": candidate_coverage_mode,
        "max_candidates_per_source_or_batch": int(max_candidates),
        "min_confidence": float(min_confidence),
        "candidate_count": int(candidate_count),
        "candidate_batch_count": int(candidate_batch_count),
        "source_reopen_required_for_claims": True,
    }


def _write_materialized_sidecar_manifest(
    clean_source_dir: Path,
    *,
    materializer: str,
    max_candidates: int,
    min_confidence: float,
    candidate_coverage_mode: str,
    candidate_count: int,
    candidate_batch_count: int,
    sidecar_sha1: str,
) -> None:
    _write_sidecar_manifest(
        clean_source_dir,
        _sidecar_manifest_payload(
            clean_source_dir,
            materializer=materializer,
            max_candidates=max_candidates,
            min_confidence=min_confidence,
            candidate_coverage_mode=candidate_coverage_mode,
            candidate_count=candidate_count,
            candidate_batch_count=candidate_batch_count,
            sidecar_sha1=sidecar_sha1,
        ),
    )


def _sidecar_manifest_matches(
    clean_source_dir: Path,
    *,
    materializer: str,
    max_candidates: int,
    min_confidence: float,
) -> bool:
    manifest = _read_sidecar_manifest(clean_source_dir)
    if not manifest:
        return False
    if manifest.get("kind") != "standard_public_source_semantic_sidecar_manifest":
        return False
    if manifest.get("policy_version") != SOURCE_SEMANTIC_SIDECAR_POLICY_VERSION:
        return False
    if str(manifest.get("materializer") or "") != str(materializer):
        return False
    if str(manifest.get("source_messages_sha1") or "") != _clean_source_messages_sha1(
        clean_source_dir
    ):
        return False
    if int(manifest.get("max_candidates_per_source_or_batch") or 0) != int(
        max_candidates
    ):
        return False
    return float(manifest.get("min_confidence") or 0.0) == float(min_confidence)


class _ProviderCallBudget:
    def __init__(self, max_calls: int) -> None:
        self._remaining = max(0, int(max_calls))
        self._lock = threading.Lock()

    def try_take(self) -> bool:
        with self._lock:
            if self._remaining <= 0:
                return False
            self._remaining -= 1
            return True


def _candidate_batches(
    candidates: list[dict[str, Any]], *, batch_size: int
) -> list[list[dict[str, Any]]]:
    bounded_batch_size = max(1, int(batch_size))
    return [
        candidates[start : start + bounded_batch_size]
        for start in range(0, len(candidates), bounded_batch_size)
    ]


def _reused_sidecar_result(
    clean_source_dir: Path,
    *,
    case_id: str,
    materializer: str,
    max_candidates: int,
    min_confidence: float,
) -> dict[str, Any] | None:
    if not _sidecar_path(clean_source_dir).exists():
        return None
    if not _sidecar_manifest_matches(
        clean_source_dir,
        materializer=materializer,
        max_candidates=max_candidates,
        min_confidence=min_confidence,
    ):
        return None
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
            _sidecar_path(clean_source_dir).read_text(encoding="utf-8")
        )[:16],
        "usage": {},
        "latency_ms": 0.0,
        "errors": [],
    }


def _call_public_semantic_labeler(
    candidates: list[dict[str, Any]],
    *,
    timeout: int,
    max_tokens: int,
    labeler_fn: PublicSemanticLabelerFn | None,
) -> dict[str, Any]:
    return (
        labeler_fn(candidates)
        if labeler_fn
        else run_public_semantic_labeler(
            candidates,
            timeout=timeout,
            max_tokens=max_tokens,
        )
    )


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
    if not rebuild_sidecar:
        reused = _reused_sidecar_result(
            clean_source_dir,
            case_id=case_id,
            materializer=SOURCE_SEMANTIC_SIDECAR_MATERIALIZER_PUBLIC,
            max_candidates=max_candidates,
            min_confidence=min_confidence,
        )
        if reused is not None:
            return reused
    _remove_sidecar_files(clean_source_dir)

    messages = _load_clean_source_messages(clean_source_dir)
    candidates = public_semantic_candidate_messages(
        messages,
        max_candidates=max_candidates,
    )
    if not candidates:
        write_semantic_scope_label_sidecar(clean_source_dir, [])
        sidecar_sha1 = sha1_text(sidecar_path.read_text(encoding="utf-8"))[:16]
        _write_materialized_sidecar_manifest(
            clean_source_dir,
            materializer=SOURCE_SEMANTIC_SIDECAR_MATERIALIZER_PUBLIC,
            max_candidates=max_candidates,
            min_confidence=min_confidence,
            candidate_coverage_mode="top_candidate_selector",
            candidate_count=0,
            candidate_batch_count=0,
            sidecar_sha1=sidecar_sha1,
        )
        return {
            "case_id": case_id,
            "status": "empty_candidate_set",
            "provider_call_count": 0,
            "candidate_count": 0,
            "finding_count": 0,
            "sidecar_written": True,
            "sidecar_row_count": 0,
            "reviewed_sidecar_row_count": 0,
            "sidecar_sha1": sidecar_sha1,
            "usage": {},
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            "errors": ["empty candidate set"],
        }

    try:
        labeler_payload = _call_public_semantic_labeler(
            candidates,
            timeout=timeout,
            max_tokens=max_tokens,
            labeler_fn=labeler_fn,
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
    sidecar_sha1 = sha1_text(sidecar_path.read_text(encoding="utf-8"))[:16]
    _write_materialized_sidecar_manifest(
        clean_source_dir,
        materializer=SOURCE_SEMANTIC_SIDECAR_MATERIALIZER_PUBLIC,
        max_candidates=max_candidates,
        min_confidence=min_confidence,
        candidate_coverage_mode="top_candidate_selector",
        candidate_count=len(candidates),
        candidate_batch_count=1,
        sidecar_sha1=sidecar_sha1,
    )
    return {
        "case_id": case_id,
        "status": "materialized_sidecar",
        "provider_call_count": 1,
        "candidate_count": len(candidates),
        "finding_count": len(findings),
        "sidecar_written": True,
        "sidecar_row_count": len(sidecar_rows),
        "reviewed_sidecar_row_count": len(reviewed_sidecar),
        "sidecar_sha1": sidecar_sha1,
        "usage": compact_usage(labeler_payload.get("usage") or {}),
        "latency_ms": round((time.perf_counter() - started) * 1000, 2),
        "errors": [str(item) for item in labeler_payload.get("errors") or []],
    }


def materialize_full_source_semantic_sidecar_for_case(
    case: dict[str, Any],
    *,
    max_candidates: int,
    timeout: int,
    max_tokens: int,
    min_confidence: float,
    call_budget: _ProviderCallBudget,
    labeler_fn: PublicSemanticLabelerFn | None = None,
    rebuild_sidecar: bool = False,
) -> dict[str, Any]:
    started = time.perf_counter()
    case_id = str(case.get("case_id") or "")
    clean_source_dir = _clean_source_dir(case)
    sidecar_path = clean_source_dir / SEMANTIC_SCOPE_LABELS_FILENAME
    if not rebuild_sidecar:
        reused = _reused_sidecar_result(
            clean_source_dir,
            case_id=case_id,
            materializer=SOURCE_SEMANTIC_SIDECAR_MATERIALIZER_PUBLIC_FULL_SOURCE,
            max_candidates=max_candidates,
            min_confidence=min_confidence,
        )
        if reused is not None:
            reused["candidate_coverage_mode"] = "reused_existing_sidecar"
            return reused
    _remove_sidecar_files(clean_source_dir)

    messages = _load_clean_source_messages(clean_source_dir)
    candidates = public_semantic_full_source_candidate_messages(messages)
    if not candidates:
        write_semantic_scope_label_sidecar(clean_source_dir, [])
        sidecar_sha1 = sha1_text(sidecar_path.read_text(encoding="utf-8"))[:16]
        _write_materialized_sidecar_manifest(
            clean_source_dir,
            materializer=SOURCE_SEMANTIC_SIDECAR_MATERIALIZER_PUBLIC_FULL_SOURCE,
            max_candidates=max_candidates,
            min_confidence=min_confidence,
            candidate_coverage_mode="full_source_ordered_chunks",
            candidate_count=0,
            candidate_batch_count=0,
            sidecar_sha1=sidecar_sha1,
        )
        return {
            "case_id": case_id,
            "status": "empty_candidate_set",
            "provider_call_count": 0,
            "candidate_count": 0,
            "candidate_coverage_mode": "full_source_ordered_chunks",
            "candidate_batch_count": 0,
            "finding_count": 0,
            "sidecar_written": True,
            "sidecar_row_count": 0,
            "reviewed_sidecar_row_count": 0,
            "sidecar_sha1": sidecar_sha1,
            "usage": {},
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            "errors": ["empty candidate set"],
        }

    findings: list[dict[str, Any]] = []
    errors: list[str] = []
    usage_rows: list[dict[str, Any]] = []
    attempted_batches = 0
    successful_batches = 0
    scheduled_candidate_count = 0
    for batch in _candidate_batches(candidates, batch_size=max_candidates):
        if not call_budget.try_take():
            errors.append("provider_call_budget_exhausted")
            break
        attempted_batches += 1
        scheduled_candidate_count += len(batch)
        try:
            labeler_payload = _call_public_semantic_labeler(
                batch,
                timeout=timeout,
                max_tokens=max_tokens,
                labeler_fn=labeler_fn,
            )
        except Exception as exc:  # pragma: no cover - live provider boundary
            errors.append(type(exc).__name__)
            continue
        if not labeler_payload.get("available", True):
            errors.extend(str(item) for item in labeler_payload.get("errors") or [])
            continue
        successful_batches += 1
        usage_rows.append({"usage": compact_usage(labeler_payload.get("usage") or {})})
        findings.extend(
            normalize_public_semantic_findings(
                [
                    item
                    for item in labeler_payload.get("findings") or []
                    if isinstance(item, dict)
                ],
                batch,
            )
        )
        errors.extend(str(item) for item in labeler_payload.get("errors") or [])

    if successful_batches <= 0:
        return {
            "case_id": case_id,
            "status": (
                "provider_call_budget_exhausted"
                if "provider_call_budget_exhausted" in errors
                else "semantic_labeler_error"
            ),
            "provider_call_count": attempted_batches,
            "candidate_count": scheduled_candidate_count,
            "candidate_coverage_mode": "full_source_ordered_chunks",
            "candidate_batch_count": attempted_batches,
            "full_source_candidate_count": len(candidates),
            "finding_count": 0,
            "sidecar_written": False,
            "sidecar_row_count": 0,
            "reviewed_sidecar_row_count": 0,
            "sidecar_sha1": "",
            "usage": _usage_sum(usage_rows),
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            "errors": errors,
        }

    messages_by_id = clean_messages_by_id(clean_source_dir)
    sidecar_rows = semantic_scope_label_rows_from_findings(
        findings,
        messages_by_id,
        min_confidence=min_confidence,
    )
    write_semantic_scope_label_sidecar(clean_source_dir, sidecar_rows)
    reviewed_sidecar = load_semantic_scope_labels(clean_source_dir)
    sidecar_sha1 = sha1_text(sidecar_path.read_text(encoding="utf-8"))[:16]
    _write_materialized_sidecar_manifest(
        clean_source_dir,
        materializer=SOURCE_SEMANTIC_SIDECAR_MATERIALIZER_PUBLIC_FULL_SOURCE,
        max_candidates=max_candidates,
        min_confidence=min_confidence,
        candidate_coverage_mode="full_source_ordered_chunks",
        candidate_count=scheduled_candidate_count,
        candidate_batch_count=attempted_batches,
        sidecar_sha1=sidecar_sha1,
    )
    return {
        "case_id": case_id,
        "status": (
            "partial_materialized_sidecar"
            if errors
            else "materialized_sidecar"
        ),
        "provider_call_count": attempted_batches,
        "candidate_count": scheduled_candidate_count,
        "candidate_coverage_mode": "full_source_ordered_chunks",
        "candidate_batch_count": attempted_batches,
        "full_source_candidate_count": len(candidates),
        "finding_count": len(findings),
        "sidecar_written": True,
        "sidecar_row_count": len(sidecar_rows),
        "reviewed_sidecar_row_count": len(reviewed_sidecar),
        "sidecar_sha1": sidecar_sha1,
        "usage": _usage_sum(usage_rows),
        "latency_ms": round((time.perf_counter() - started) * 1000, 2),
        "errors": errors,
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
    coverage_modes: dict[str, int] = {}
    for row in rows:
        status = str(row.get("status") or "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1
        mode = str(row.get("candidate_coverage_mode") or "top_candidate_selector")
        coverage_modes[mode] = coverage_modes.get(mode, 0) + 1
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
        "full_source_candidate_count": sum(
            int(row.get("full_source_candidate_count") or 0) for row in rows
        ),
        "candidate_batch_count": sum(
            int(row.get("candidate_batch_count") or 0) for row in rows
        ),
        "candidate_coverage_mode_counts": dict(sorted(coverage_modes.items())),
        "finding_count": sum(int(row.get("finding_count") or 0) for row in rows),
        "status_counts": dict(sorted(status_counts.items())),
        "error_count": error_count,
        "usage": _usage_sum(rows),
        "latency_ms": _latency_summary(rows),
        "raw_source_text_emitted": False,
        "sidecar_values_emitted": False,
        "absolute_paths_emitted": False,
        "source_text_sent_to_labeler": materializer
        in {
            SOURCE_SEMANTIC_SIDECAR_MATERIALIZER_PUBLIC,
            SOURCE_SEMANTIC_SIDECAR_MATERIALIZER_PUBLIC_FULL_SOURCE,
        },
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

    full_source_mode = (
        resolved_materializer == SOURCE_SEMANTIC_SIDECAR_MATERIALIZER_PUBLIC_FULL_SOURCE
    )
    bounded_cases = cases if full_source_mode else cases[: max(0, int(max_provider_calls))]
    call_budget = _ProviderCallBudget(max_provider_calls)

    def run(case: dict[str, Any]) -> dict[str, Any]:
        if full_source_mode:
            return materialize_full_source_semantic_sidecar_for_case(
                case,
                max_candidates=max_candidates,
                timeout=timeout,
                max_tokens=max_tokens,
                min_confidence=min_confidence,
                call_budget=call_budget,
                labeler_fn=labeler_fn,
                rebuild_sidecar=rebuild_sidecars,
            )
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
