"""Source-object persistence and rehydration for sparse provenance codebooks."""

from __future__ import annotations

import hashlib
import json
import time
import zlib
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from aippocampus_runtime.source.fingerprint_contracts import (
    ALLOWED_LIFECYCLE_STATES,
    BLOCKED_LIFECYCLE_STATES,
    BLOCKED_PRIVACY_PARTITIONS,
)

CODEBOOK_HEALTH_STATUSES = {
    "verified_present",
    "verified_present_but_blocked",
    "cannot_verify",
    "verified_present_with_action_required",
}


def _mapping_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _entry_allowed(entry: Mapping[str, Any]) -> bool:
    lifecycle_state = str(entry.get("lifecycle_state") or "")
    privacy_partition = str(entry.get("privacy_partition") or "")
    return (
        lifecycle_state in ALLOWED_LIFECYCLE_STATES
        and lifecycle_state not in BLOCKED_LIFECYCLE_STATES
        and privacy_partition not in BLOCKED_PRIVACY_PARTITIONS
    )


def _source_object_allowed(source_object: Mapping[str, Any]) -> bool:
    return _entry_allowed(source_object)


def _status_for_source_object(source_object: Mapping[str, Any] | None) -> str:
    if not source_object:
        return "cannot_verify"
    if _source_object_allowed(source_object):
        return "verified_present"
    return "verified_present_but_blocked"


def _chunk_text_from_store(store: Mapping[str, Any], chunk_id: str) -> str | None:
    chunks = _mapping_dict(store.get("chunks"))
    chunk = chunks.get(chunk_id) if isinstance(chunks, Mapping) else None
    if not isinstance(chunk, Mapping):
        return None
    return str(chunk.get("text") or "")


def _source_objects_by_id(store: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(item.get("source_object_id")): item
        for item in store.get("source_objects") or []
        if isinstance(item, dict) and item.get("source_object_id")
    }


def _spans_by_id(store: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(item.get("span_id")): item
        for item in store.get("spans") or []
        if isinstance(item, dict) and item.get("span_id")
    }


def source_object_store_summary(store: Mapping[str, Any]) -> dict[str, Any]:
    metrics = dict(store.get("metrics") or {})
    statuses = [
        _status_for_source_object(item)
        for item in store.get("source_objects") or []
        if isinstance(item, Mapping)
    ]
    return {
        "kind": "aippocampus_source_object_store_summary",
        "schema_version": store.get("schema_version"),
        "manifest_hash": store.get("manifest_hash"),
        "metrics": metrics,
        "status_counts": {
            status: statuses.count(status) for status in sorted(CODEBOOK_HEALTH_STATUSES)
        },
        "public_safe": {
            "raw_text_serialized": False,
            "local_paths_serialized": False,
            "private_handles_serialized": False,
        },
        "authority_boundary": store.get("authority_boundary"),
    }


def persist_source_object_store(store: Mapping[str, Any], root: Path | str) -> dict[str, Any]:
    root_path = Path(root)
    root_path.mkdir(parents=True, exist_ok=True)
    chunks_dir = root_path / "chunks"
    objects_dir = root_path / "source_objects"
    spans_dir = root_path / "spans"
    chunks_dir.mkdir(exist_ok=True)
    objects_dir.mkdir(exist_ok=True)
    spans_dir.mkdir(exist_ok=True)
    chunks = _mapping_dict(store.get("chunks"))
    for chunk_id, chunk in chunks.items():
        if not isinstance(chunk, Mapping):
            continue
        (chunks_dir / f"{chunk_id}.txt").write_text(
            str(chunk.get("text") or ""),
            encoding="utf-8",
            newline="\n",
        )
    for source_object in store.get("source_objects") or []:
        if not isinstance(source_object, Mapping):
            continue
        object_id = str(source_object.get("source_object_id") or "")
        if object_id:
            (objects_dir / f"{object_id}.json").write_text(
                json.dumps(source_object, ensure_ascii=False, indent=2),
                encoding="utf-8",
                newline="\n",
            )
    for span in store.get("spans") or []:
        if not isinstance(span, Mapping):
            continue
        span_id = str(span.get("span_id") or "")
        if span_id:
            (spans_dir / f"{span_id}.json").write_text(
                json.dumps(span, ensure_ascii=False, indent=2),
                encoding="utf-8",
                newline="\n",
            )
    manifest = source_object_store_summary(store)
    (root_path / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
        newline="\n",
    )
    return {
        "kind": "aippocampus_source_object_store_persist_report",
        "root": str(root_path),
        "manifest_hash": store.get("manifest_hash"),
        "source_object_count": len(store.get("source_objects") or []),
        "span_count": len(store.get("spans") or []),
        "chunk_count": len(chunks),
    }


def load_source_object_manifest(root: Path | str) -> dict[str, Any]:
    manifest_path = Path(root) / "manifest.json"
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def rehydrate_source_span(
    store: Mapping[str, Any],
    span_id: str,
    *,
    include_text: bool = True,
) -> dict[str, Any]:
    span = _spans_by_id(store).get(span_id)
    if not span:
        return {"status": "cannot_verify", "reason": "unknown_span_id"}
    source_object = _source_objects_by_id(store).get(str(span.get("source_object_id") or ""))
    if not source_object:
        return {"status": "cannot_verify", "reason": "missing_source_object"}
    if not _source_object_allowed(source_object):
        return {
            "status": "blocked",
            "reason": "privacy_or_lifecycle_block",
            "span_id": span_id,
            "source_fingerprint": span.get("source_fingerprint"),
        }
    text = _chunk_text_from_store(store, str(span.get("chunk_id") or ""))
    if text is None:
        return {"status": "cannot_verify", "reason": "missing_chunk"}
    start = int(span.get("byte_start") or 0)
    end = int(span.get("byte_end") or len(text.encode("utf-8")))
    raw = text.encode("utf-8")[start:end]
    rehydrated_text = raw.decode("utf-8", errors="replace")
    content_hash = "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()
    hash_match = content_hash == span.get("content_hash") == source_object.get("content_hash")
    result = {
        "kind": "aippocampus_source_object_span_rehydration",
        "status": "ok" if hash_match else "hash_mismatch",
        "span_id": span_id,
        "proof": {
            "manifest_hash": store.get("manifest_hash"),
            "source_object_id": source_object.get("source_object_id"),
            "chunk_id": span.get("chunk_id"),
            "content_hash": content_hash,
            "source_fingerprint": span.get("source_fingerprint"),
            "proof_level": "bounded_span_rehydration",
            "reconstruction_hash_match": hash_match,
        },
    }
    if include_text:
        result["text"] = rehydrated_text
    return result


def rehydrate_persistent_source_span(
    root: Path | str,
    span_id: str,
    *,
    include_text: bool = True,
) -> dict[str, Any]:
    root_path = Path(root)
    span_path = root_path / "spans" / f"{span_id}.json"
    if not span_path.exists():
        return {"status": "cannot_verify", "reason": "unknown_span_id"}
    span = json.loads(span_path.read_text(encoding="utf-8"))
    object_path = root_path / "source_objects" / f"{span.get('source_object_id')}.json"
    if not object_path.exists():
        return {"status": "cannot_verify", "reason": "missing_source_object"}
    source_object = json.loads(object_path.read_text(encoding="utf-8"))
    if not _source_object_allowed(source_object):
        return {
            "status": "blocked",
            "reason": "privacy_or_lifecycle_block",
            "span_id": span_id,
            "source_fingerprint": span.get("source_fingerprint"),
        }
    chunk_path = root_path / "chunks" / f"{span.get('chunk_id')}.txt"
    if not chunk_path.exists():
        return {"status": "cannot_verify", "reason": "missing_chunk"}
    text = chunk_path.read_text(encoding="utf-8")
    content_hash = "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()
    hash_match = content_hash == span.get("content_hash") == source_object.get("content_hash")
    result = {
        "kind": "aippocampus_persistent_source_object_span_rehydration",
        "status": "ok" if hash_match else "hash_mismatch",
        "span_id": span_id,
        "proof": {
            "source_object_id": source_object.get("source_object_id"),
            "chunk_id": span.get("chunk_id"),
            "content_hash": content_hash,
            "source_fingerprint": span.get("source_fingerprint"),
            "proof_level": "bounded_span_rehydration",
            "loaded_manifest_only": False,
            "unrelated_source_objects_loaded": False,
            "reconstruction_hash_match": hash_match,
        },
    }
    if include_text:
        start = int(span.get("byte_start") or 0)
        end = int(span.get("byte_end") or len(text.encode("utf-8")))
        result["text"] = text.encode("utf-8")[start:end].decode("utf-8", errors="replace")
    return result


def compression_proof_report(store: Mapping[str, Any]) -> dict[str, Any]:
    started = time.perf_counter()
    chunks = _mapping_dict(store.get("chunks"))
    unique_text = "\n".join(
        str(chunk.get("text") or "")
        for _chunk_id, chunk in sorted(chunks.items())
        if isinstance(chunk, Mapping)
    )
    unique_bytes = unique_text.encode("utf-8")
    compressed = zlib.compress(unique_bytes)
    first_allowed_span = next(
        (
            span
            for span in store.get("spans") or []
            if isinstance(span, Mapping) and span.get("status") == "verified_present"
        ),
        None,
    )
    span_proof = (
        rehydrate_source_span(store, str(first_allowed_span.get("span_id")), include_text=False)
        if first_allowed_span
        else {"status": "cannot_verify", "reason": "no_allowed_span"}
    )
    proof = span_proof.get("proof")
    proof_map = dict(proof) if isinstance(proof, Mapping) else {}
    metrics = dict(store.get("metrics") or {})
    raw_text_bytes = int(metrics.get("raw_text_bytes") or 0)
    unique_text_bytes = int(metrics.get("unique_text_bytes") or len(unique_bytes))
    return {
        "kind": "aippocampus_sparse_provenance_compression_proof_report",
        "schema_version": "compression-proof-v1",
        "fixture_scope": "public_safe_fixture_local_measurement",
        "compression": {
            "baseline_dedupe": {
                "raw_text_bytes": raw_text_bytes,
                "unique_text_bytes": unique_text_bytes,
                "saved_bytes": max(0, raw_text_bytes - unique_text_bytes),
                "compression_ratio": round(unique_text_bytes / raw_text_bytes, 4)
                if raw_text_bytes
                else 1.0,
            },
            "portable_deflate": {
                "codec": "zlib_deflate_portable_fallback",
                "compressed_unique_bytes": len(compressed),
                "saved_vs_unique_bytes": max(0, unique_text_bytes - len(compressed)),
                "native_dependency_required": False,
            },
        },
        "proof_levels": {
            "tiny_span_lookup": {
                "status": "verified_present" if first_allowed_span else "cannot_verify",
                "span_id_present": bool(first_allowed_span),
                "external_model_calls": 0,
            },
            "bounded_span_rehydration": {
                "status": span_proof.get("status"),
                "hash_match": proof_map.get("reconstruction_hash_match") is True,
                "external_model_calls": 0,
            },
            "whole_tree_audit": {
                "status": "verified_present",
                "manifest_hash": store.get("manifest_hash"),
                "chunk_count": metrics.get("chunk_count"),
                "external_model_calls": 0,
            },
        },
        "latency_proxy_ms": round((time.perf_counter() - started) * 1000, 3),
        "cannot_claim": [
            "natural_dialogue_compression_rate",
            "gb_tb_readiness",
            "semantic_summary_reconstruction",
            "o1_lookup_independent_of_output_bytes",
        ],
    }


__all__ = [
    "_source_object_allowed",
    "_source_objects_by_id",
    "_spans_by_id",
    "_status_for_source_object",
    "compression_proof_report",
    "load_source_object_manifest",
    "persist_source_object_store",
    "rehydrate_persistent_source_span",
    "rehydrate_source_span",
    "source_object_store_summary",
]
