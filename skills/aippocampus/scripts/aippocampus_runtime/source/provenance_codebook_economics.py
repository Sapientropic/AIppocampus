"""Read-only source-family economics runner for sparse provenance codebooks."""

from __future__ import annotations

import hashlib
import importlib
import importlib.util
import json
import time
import zlib
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from aippocampus_runtime.source import provenance_codebook as codebook


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _family_rows(family: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = family.get("rows")
    if isinstance(rows, Sequence) and not isinstance(rows, (str, bytes)):
        return [dict(row) for row in rows if isinstance(row, Mapping)]
    path = family.get("jsonl_path") or family.get("path")
    if path:
        return codebook._load_jsonl(Path(str(path)))
    return []


def _raw_rows_payload(rows: Sequence[Mapping[str, Any]]) -> str:
    return "\n".join(_canonical_json(row) for row in rows)


def _evidence_candidate_usefulness(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    text = _raw_rows_payload(rows).casefold()
    signals = {
        "repeated_mistakes": ("mistake", "regression", "again", "repeat"),
        "rejected_routes": ("reject", "blocked", "no-recall", "quarantined"),
        "environment_workarounds": ("workaround", "env", "path", "windows", "shell"),
        "workflow_candidates": ("workflow", "next action", "apply", "repair"),
        "pathlet_action_traces": ("pathlet", "route", "supersession", "correction"),
    }
    return {
        name: {
            "supports_candidate": any(token in text for token in tokens),
            "signal_terms": [token for token in tokens if token in text][:4],
        }
        for name, tokens in signals.items()
    }


def _family_kind_default(family_id: str) -> str:
    normalized = family_id.casefold().replace("_", "-")
    if "structured" in normalized or "trace" in normalized:
        return "structured_tool_system_model_traces"
    if "generated" in normalized or "report" in normalized or "benchmark" in normalized:
        return "generated_indexes_reports_benchmark_artifacts"
    if "mixed" in normalized or "agent" in normalized or "bundle" in normalized:
        return "mixed_long_agent_session_bundle"
    return "human_visible_natural_conversation_like_clean_source"


def _privacy_partition(rows: Sequence[Mapping[str, Any]]) -> str:
    partitions = sorted({str(row.get("privacy_partition") or "unknown") for row in rows})
    if len(partitions) == 1:
        return partitions[0]
    if not partitions:
        return "unknown"
    return "mixed"


def _dictionary_training_rows(rows: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    return [
        row
        for row in rows
        if str(row.get("privacy_partition") or "") == "public"
        and str(row.get("lifecycle_state") or "current") in {"current", "active"}
    ]


def _stable_id(prefix: str, value: bytes | str) -> str:
    data = value.encode("utf-8", errors="replace") if isinstance(value, str) else value
    return f"{prefix}_{hashlib.sha256(data).hexdigest()[:20]}"


def _zstd_codec(raw: bytes, rows: Sequence[Mapping[str, Any]], family_id: str) -> dict[str, Any]:
    base = {
        "codec_id": "zstd",
        "codec_version": "unavailable",
        "status": "skipped",
        "skip_reason": "zstandard_python_module_not_available",
        "encoded_bytes": None,
        "build_time_ms": 0.0,
        "decode_time_ms": 0.0,
        "native_dependency_required": True,
    }
    if not raw:
        return {**base, "skip_reason": "empty_family"}
    if importlib.util.find_spec("zstandard") is None:
        return base
    try:
        zstd = importlib.import_module("zstandard")
    except Exception as exc:  # pragma: no cover - optional dependency guard
        return {**base, "skip_reason": f"zstd_import_failed:{exc.__class__.__name__}"}
    started = time.perf_counter()
    compressed = zstd.ZstdCompressor(level=3).compress(raw)
    decode_started = time.perf_counter()
    decoded = zstd.ZstdDecompressor().decompress(compressed)
    return {
        "codec_id": "zstd",
        "codec_version": getattr(zstd, "ZSTD_VERSION", "unknown"),
        "status": "available",
        "encoded_bytes": len(compressed),
        "compression_ratio": round(len(compressed) / len(raw), 4),
        "build_time_ms": round((decode_started - started) * 1000, 3),
        "decode_time_ms": round((time.perf_counter() - decode_started) * 1000, 3),
        "rehydration_hash_correct": decoded == raw,
        "native_dependency_required": True,
        "dictionary_id": None,
        "training_source_family": family_id,
        "training_privacy_partition": _privacy_partition(rows),
        "raw_dictionary_bytes_serialized": False,
    }


def _zstd_dictionary_codec(
    raw: bytes,
    rows: Sequence[Mapping[str, Any]],
    family_id: str,
) -> dict[str, Any]:
    training_rows = _dictionary_training_rows(rows)
    base = {
        "codec_id": "zstd_dictionary",
        "codec_version": "unavailable",
        "status": "skipped",
        "skip_reason": "zstandard_python_module_not_available",
        "encoded_bytes": None,
        "dictionary_id": _stable_id("zstd_dict", family_id),
        "dictionary_byte_length": 0,
        "training_source_family": family_id,
        "training_privacy_partition": _privacy_partition(training_rows),
        "redaction_policy_version": "policy-v1",
        "mask_policy_version": "structured-trace-mask-v1",
        "raw_dictionary_bytes_serialized": False,
        "native_dependency_required": True,
    }
    if not raw:
        return {**base, "skip_reason": "empty_family"}
    if importlib.util.find_spec("zstandard") is None:
        return base
    try:
        zstd = importlib.import_module("zstandard")

        samples = [
            _canonical_json(row).encode("utf-8", errors="replace")
            for row in training_rows
            if isinstance(row, Mapping)
        ]
        if len(samples) < 2:
            return {**base, "skip_reason": "dictionary_training_needs_at_least_two_samples"}
        dict_size = min(8192, max(1024, len(raw) // 8))
        trained = zstd.train_dictionary(dict_size, samples)
        compressor = zstd.ZstdCompressor(dict_data=trained)
        started = time.perf_counter()
        compressed = compressor.compress(raw)
        decode_started = time.perf_counter()
        decoded = zstd.ZstdDecompressor(dict_data=trained).decompress(compressed)
        dict_bytes = trained.as_bytes()
        return {
            **base,
            "codec_version": getattr(zstd, "ZSTD_VERSION", "unknown"),
            "status": "available",
            "skip_reason": None,
            "encoded_bytes": len(compressed),
            "compression_ratio": round(len(compressed) / len(raw), 4),
            "dictionary_id": _stable_id("zstd_dict", dict_bytes),
            "dictionary_byte_length": len(dict_bytes),
            "build_time_ms": round((decode_started - started) * 1000, 3),
            "decode_time_ms": round((time.perf_counter() - decode_started) * 1000, 3),
            "rehydration_hash_correct": decoded == raw,
        }
    except Exception as exc:  # pragma: no cover - depends on optional backend
        return {**base, "skip_reason": f"zstd_dictionary_failed:{exc.__class__.__name__}"}


def _codec_matrix(
    *,
    family_id: str,
    family_kind: str,
    rows: Sequence[Mapping[str, Any]],
    raw_payload: str,
    built: Mapping[str, Any],
    trace_report: Mapping[str, Any],
    ordinary_deflate_bytes: int,
) -> dict[str, Any]:
    raw = raw_payload.encode("utf-8")
    metrics = built.get("metrics") or {}
    template_residual = trace_report.get("template_residual") or {}
    structured = "structured" in family_kind or "trace" in family_kind
    return {
        "baseline_content_addressed_dedupe": {
            "codec_id": "content_addressed_chunk_dedupe",
            "status": "available",
            "encoded_bytes": int(metrics.get("unique_text_bytes") or 0),
            "raw_bytes": int(metrics.get("raw_text_bytes") or len(raw)),
            "unique_chunk_count": int(metrics.get("unique_chunk_count") or 0),
            "deduped_entry_count": int(metrics.get("deduped_entry_count") or 0),
            "compression_ratio": metrics.get("compression_ratio", 1.0),
        },
        "portable_deflate": {
            "codec_id": "zlib_deflate_portable_fallback",
            "status": "available",
            "encoded_bytes": ordinary_deflate_bytes,
            "compression_ratio": round(ordinary_deflate_bytes / len(raw), 4) if raw else 1.0,
            "native_dependency_required": False,
        },
        "zstd_no_dictionary": _zstd_codec(raw, rows, family_id),
        "zstd_dictionary": _zstd_dictionary_codec(raw, rows, family_id),
        "template_residual": {
            "codec_id": "template_residual",
            "codec_version": "template-residual-v1",
            "status": "available" if structured and rows else "skipped",
            "skip_reason": None if structured and rows else "not_structured_trace_family",
            "encoded_bytes": int(template_residual.get("encoded_projection_bytes") or 0),
            "template_count": int(template_residual.get("template_count") or 0),
            "residual_bytes": int(template_residual.get("encoded_projection_bytes") or 0),
            "raw_residual_bytes_serialized": False,
            "masked_slot_count": int(template_residual.get("masked_slot_count") or 0),
        },
    }


def _storage_primitive_decision_gate(family_reports: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    total_chunks = sum(
        int(((item.get("codebook_metrics") or {}).get("unique_chunk_count") or 0))
        for item in family_reports
    )
    max_amp = max(
        (
            float(item.get("memory_disk_amplification_vs_clean_source_index_path") or 0.0)
            for item in family_reports
        ),
        default=0.0,
    )
    return {
        "kind": "aippocampus_sparse_provenance_storage_primitive_decision_gate",
        "cdc": {
            "decision": "defer",
            "reason_codes": [
                "source_family_evidence_fixture_or_synthetic_only",
                "cdc_overlap_gain_not_measured_after_codec_matrix",
                "must_not_cross_source_span_or_privacy_partition_boundaries",
            ],
            "observed_unique_chunk_count": total_chunks,
            "expected_cdc_dedupe_gain_after_codecs": "not_measured",
            "reopen_thresholds": {
                "estimated_extra_dedupe_gain_after_deflate_zstd_template_residual": ">=0.15",
                "public_safe_family_bytes": ">=1073741824",
                "source_span_boundary_preservation": "required",
                "privacy_partition_boundary_preservation": "required",
            },
        },
        "lmdb": {
            "decision": "defer",
            "reason_codes": [
                "file_per_chunk_pressure_not_proven",
                "windows_mmap_and_single_writer_cost_unjustified_now",
                "migration_and_backup_repair_contract_not_needed_for_fixture_scale",
            ],
            "observed_unique_chunk_count": total_chunks,
            "max_store_raw_amplification": round(max_amp, 4),
            "reopen_thresholds": {
                "chunk_count": ">=100000",
                "file_system_chunk_overhead_share": ">=0.20",
                "rebuild_or_lookup_latency_p95_ms": ">=250",
                "backup_repair_plan": "required_before_implementation",
            },
        },
        "storage_primitives_are_not_implemented_by_this_gate": True,
    }


def source_family_economics_report(
    families: Sequence[Mapping[str, Any]],
    *,
    lookup_query: str = "route chain workflow correction",
) -> dict[str, Any]:
    started = time.perf_counter()
    family_reports: list[dict[str, Any]] = []
    for index, family in enumerate(families, 1):
        rows = _family_rows(family)
        family_id = str(family.get("family_id") or family.get("name") or f"family-{index}")
        family_kind = str(family.get("family_kind") or _family_kind_default(family_id))
        raw_payload = _raw_rows_payload(rows)
        raw_bytes = len(raw_payload.encode("utf-8"))
        build_started = time.perf_counter()
        built = codebook.build_codebook(rows)
        store = codebook.build_source_object_store(rows)
        build_ms = round((time.perf_counter() - build_started) * 1000, 3)
        lookup_started = time.perf_counter()
        lookup = codebook.lookup_routes(
            built,
            str(family.get("lookup_query") or lookup_query),
            max_routes=5,
        )
        lookup_ms = round((time.perf_counter() - lookup_started) * 1000, 3)
        span = next(
            (
                item
                for item in store.get("spans") or []
                if isinstance(item, Mapping) and item.get("status") == "verified_present"
            ),
            None,
        )
        rehydrate_started = time.perf_counter()
        hydrated = (
            codebook.rehydrate_source_span(store, str(span.get("span_id")))
            if span
            else {"status": "missing"}
        )
        rehydrate_ms = round((time.perf_counter() - rehydrate_started) * 1000, 3)
        trace_report = codebook.structured_trace_template_residual_report(rows)
        encoded_store_bytes = len(_canonical_json(store).encode("utf-8"))
        template_residual = trace_report.get("template_residual") or {}
        residual_bytes = int(template_residual.get("encoded_projection_bytes") or 0)
        ordinary_deflate_bytes = len(zlib.compress(raw_payload.encode("utf-8"))) if raw_payload else 0
        metrics = built.get("metrics") or {}
        lookup_metrics = lookup.get("metrics") or {}
        redlines = codebook.adversarial_redline_report(rows).get("canonical_red_lines") if rows else {}
        baseline_bytes = int(family.get("clean_source_index_baseline_bytes") or raw_bytes or 1)
        proof = hydrated.get("proof")
        proof_map = proof if isinstance(proof, Mapping) else {}
        family_reports.append(
            {
                "family_id": family_id,
                "family_kind": family_kind,
                "fixture_or_input_scope": "public_safe_or_operator_supplied_read_only",
                "raw_bytes": raw_bytes,
                "encoded_store_bytes": encoded_store_bytes,
                "build_time_ms": build_ms,
                "lookup_latency_ms": lookup_ms,
                "lookup_candidate_reduction": lookup_metrics.get("lookup_candidate_reduction", 0),
                "template_count": int(template_residual.get("template_count") or 0),
                "residual_bytes": residual_bytes,
                "rehydration_latency_ms": rehydrate_ms,
                "rehydration_hash_correct": bool(proof_map.get("reconstruction_hash_match")),
                "privacy_lifecycle_red_lines": redlines,
                "memory_disk_amplification_vs_clean_source_index_path": round(
                    encoded_store_bytes / max(1, baseline_bytes),
                    4,
                ),
                "ordinary_compression": {
                    "portable_deflate_bytes": ordinary_deflate_bytes,
                    "deflate_ratio": round(ordinary_deflate_bytes / raw_bytes, 4)
                    if raw_bytes
                    else 1.0,
                },
                "codec_matrix": _codec_matrix(
                    family_id=family_id,
                    family_kind=family_kind,
                    rows=rows,
                    raw_payload=raw_payload,
                    built=built,
                    trace_report=trace_report,
                    ordinary_deflate_bytes=ordinary_deflate_bytes,
                ),
                "codebook_metrics": {
                    "source_entry_count": metrics.get("source_entry_count", 0),
                    "unique_chunk_count": metrics.get("unique_chunk_count", 0),
                    "deduped_entry_count": metrics.get("deduped_entry_count", 0),
                    "compression_ratio": metrics.get("compression_ratio", 1.0),
                },
                "evidence_candidate_usefulness": _evidence_candidate_usefulness(rows),
                "supports": [
                    "read_only_source_family_economics",
                    "family_separated_measurement",
                    "source_reopen_required_for_claims",
                ],
                "material_limits": [
                    "fixture_size_does_not_claim_100mb_gb_tb_readiness",
                    "operator_must_supply_public_safe_large_family_inputs_for_scale_claims",
                    "semantic_quality_not_measured_by_storage_economics",
                ],
            }
        )
    top_by_storage = max(
        family_reports,
        key=lambda item: int(item.get("encoded_store_bytes") or 0),
        default=None,
    )
    return {
        "kind": "aippocampus_source_family_economics_report",
        "schema_version": "source-family-economics-v1",
        "read_only": True,
        "family_count": len(family_reports),
        "by_source_family": family_reports,
        "dominant_family_by_encoded_store_bytes": (
            top_by_storage.get("family_id") if top_by_storage else None
        ),
        "compression_artifact_contract": codebook.compression_artifact_contract_report(),
        "storage_primitive_decision_gate": _storage_primitive_decision_gate(family_reports),
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
        "privacy_boundary": {
            "paths_included": False,
            "raw_text_included": False,
            "private_history_payloads_required": False,
        },
        "cannot_claim": [
            "gb_tb_readiness",
            "private_real_history_compression",
            "source_family_gate_closed_without_large_public_safe_inputs",
        ],
    }
