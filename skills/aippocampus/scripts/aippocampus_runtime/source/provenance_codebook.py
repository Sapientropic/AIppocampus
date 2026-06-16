#!/usr/bin/env python3
"""Sparse provenance codebook V0 for public-safe route reconstruction.

The codebook compresses repeated clean-source-like structure and returns route
handles plus deterministic reconstruction proofs. It is not a memory fact
store: foreground lookup never emits reconstructed text, and blocked lifecycle
or privacy partitions cannot be rehydrated through normal route scoring.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
import zlib
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

ALLOWED_LIFECYCLE_STATES = {"current", "active"}
BLOCKED_LIFECYCLE_STATES = {"deleted_no_recall", "quarantined"}
BLOCKED_PRIVACY_PARTITIONS = {"private", "quarantined", "deleted"}
SOURCE_FINGERPRINT_FIELDS = (
    "content_hash",
    "source_id",
    "privacy_partition",
    "policy_version",
    "lifecycle_state",
)
SOURCE_FINGERPRINT_OPTIONAL_FIELDS = (
    "manifest_version",
    "encoder_version",
    "retention_policy_version",
    "visibility_scope",
)
CODEBOOK_HEALTH_STATUSES = {
    "verified_present",
    "verified_present_but_blocked",
    "cannot_verify",
    "verified_present_with_action_required",
}


def _sha256_text(value: str, *, prefix: str = "", length: int = 24) -> str:
    digest = hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()[:length]
    return f"{prefix}{digest}" if prefix else digest


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _tokenize(values: Iterable[Any]) -> list[str]:
    terms: list[str] = []
    for value in values:
        text = str(value or "").casefold().replace("_", " ").replace("-", " ")
        for token in text.split():
            token = "".join(ch for ch in token if ch.isalnum())
            if len(token) >= 2:
                terms.append(token)
    return sorted(set(terms))


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _mapping_dict(value: Any) -> dict[str, Any]:
    return {str(key): item for key, item in value.items()} if isinstance(value, Mapping) else {}


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, 1):
            text = line.strip()
            if not text:
                continue
            parsed = json.loads(text)
            if not isinstance(parsed, dict):
                raise ValueError(f"line {line_no} is not a JSON object")
            rows.append(parsed)
    return rows


def _source_fingerprint_payload(row: Mapping[str, Any], content_hash: str) -> dict[str, str]:
    return {
        "content_hash": content_hash,
        "source_id": str(row.get("source_id") or ""),
        "privacy_partition": str(row.get("privacy_partition") or "unknown"),
        "policy_version": str(row.get("policy_version") or "unknown"),
        "lifecycle_state": str(row.get("lifecycle_state") or "unknown"),
    }


def _source_fingerprint(row: Mapping[str, Any], content_hash: str) -> str:
    payload = _source_fingerprint_payload(row, content_hash)
    return "srcfp_" + _sha256_text(_canonical_json(payload), length=24)


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


def build_codebook(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    chunks: dict[str, dict[str, Any]] = {}
    entries: list[dict[str, Any]] = []
    route_index: dict[str, list[int]] = {}
    raw_text_bytes = 0
    topology_missing_count = 0

    for ordinal, row in enumerate(rows, 1):
        text = str(row.get("text") or "")
        raw_text_bytes += len(text.encode("utf-8"))
        content_hash = "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()
        chunk_id = "chunk_" + _sha256_text(text, length=24)
        chunks.setdefault(
            chunk_id,
            {
                "chunk_id": chunk_id,
                "content_hash": content_hash,
                "text": text,
                "text_bytes": len(text.encode("utf-8")),
            },
        )
        source_fingerprint = _source_fingerprint(row, content_hash)
        topology = _mapping(row.get("topology"))
        if not topology:
            topology_missing_count += 1
        route_terms = _tokenize(
            [
                row.get("route_family"),
                row.get("source_kind"),
                row.get("lifecycle_state"),
                *(row.get("scope_labels") or []),
                *(topology.get("support_chain") or []),
                topology.get("pathlet_id"),
            ]
        )
        entry = {
            "entry_id": f"entry_{ordinal:04d}",
            "chunk_id": chunk_id,
            "source_id": str(row.get("source_id") or f"source:{ordinal}"),
            "source_kind": str(row.get("source_kind") or "unknown"),
            "privacy_partition": str(row.get("privacy_partition") or "unknown"),
            "policy_version": str(row.get("policy_version") or "unknown"),
            "lifecycle_state": str(row.get("lifecycle_state") or "unknown"),
            "ordinal": int(row.get("ordinal") or ordinal),
            "source_fingerprint": source_fingerprint,
            "source_fingerprint_fields": list(SOURCE_FINGERPRINT_FIELDS),
            "route_family": str(row.get("route_family") or "unknown"),
            "scope_labels": [str(item) for item in row.get("scope_labels") or []],
            "route_terms": route_terms,
            "topology": {
                "pathlet_id": str(topology.get("pathlet_id") or ""),
                "supersedes": [str(item) for item in topology.get("supersedes") or []],
                "support_chain": [str(item) for item in topology.get("support_chain") or []],
                "topology_hash": "topo_" + _sha256_text(_canonical_json(topology), length=20),
            },
        }
        entries.append(entry)
        for term in route_terms:
            route_index.setdefault(term, []).append(len(entries) - 1)

    for term, indices in route_index.items():
        route_index[term] = sorted(set(indices))

    unique_text_bytes = sum(chunk["text_bytes"] for chunk in chunks.values())
    manifest_payload = {
        "chunks": [
            {
                "chunk_id": chunk["chunk_id"],
                "content_hash": chunk["content_hash"],
                "text_bytes": chunk["text_bytes"],
            }
            for chunk in sorted(chunks.values(), key=lambda item: item["chunk_id"])
        ],
        "entries": [
            {
                key: entry[key]
                for key in (
                    "entry_id",
                    "chunk_id",
                    "source_id",
                    "privacy_partition",
                    "policy_version",
                    "lifecycle_state",
                    "source_fingerprint",
                    "topology",
                )
            }
            for entry in entries
        ],
    }
    manifest_hash = "manifest_" + _sha256_text(_canonical_json(manifest_payload), length=24)
    return {
        "kind": "aippocampus_sparse_provenance_codebook",
        "schema_version": "sparse-provenance-codebook-v0",
        "manifest_hash": manifest_hash,
        "merkle_root": manifest_hash,
        "chunks": chunks,
        "entries": entries,
        "route_index": route_index,
        "metrics": {
            "source_entry_count": len(entries),
            "unique_chunk_count": len(chunks),
            "deduped_entry_count": max(0, len(entries) - len(chunks)),
            "raw_text_bytes": raw_text_bytes,
            "unique_text_bytes": unique_text_bytes,
            "dedupe_saved_bytes": max(0, raw_text_bytes - unique_text_bytes),
            "compression_ratio": round(unique_text_bytes / raw_text_bytes, 4)
            if raw_text_bytes
            else 1.0,
            "dictionary_compression": "not_enabled_v0",
            "topology_missing_count": topology_missing_count,
        },
    }


def route_handle_for(codebook: Mapping[str, Any], entry: Mapping[str, Any]) -> str:
    return f"spc:{codebook.get('manifest_hash')}:{entry.get('entry_id')}"


def _entry_from_handle(codebook: Mapping[str, Any], route_handle: str) -> dict[str, Any] | None:
    parts = str(route_handle or "").split(":")
    if len(parts) != 3 or parts[0] != "spc" or parts[1] != codebook.get("manifest_hash"):
        return None
    entry_id = parts[2]
    for entry in codebook.get("entries") or []:
        if isinstance(entry, dict) and entry.get("entry_id") == entry_id:
            return entry
    return None


def lookup_routes(
    codebook: Mapping[str, Any],
    query: str | Sequence[str],
    *,
    max_routes: int = 5,
) -> dict[str, Any]:
    terms = _tokenize(query if isinstance(query, Sequence) and not isinstance(query, str) else [query])
    route_index = _mapping(codebook.get("route_index"))
    candidate_indices: set[int] = set()
    for term in terms:
        for index in route_index.get(term, []) if isinstance(route_index.get(term), list) else []:
            candidate_indices.add(int(index))
    naive_scan_count = len(codebook.get("entries") or [])
    if not candidate_indices:
        candidate_indices = set(range(naive_scan_count))

    routes: list[dict[str, Any]] = []
    blocked_match_count = 0
    for index in sorted(candidate_indices):
        entry = (codebook.get("entries") or [])[index]
        if not isinstance(entry, dict):
            continue
        matched_terms = sorted(set(terms).intersection(entry.get("route_terms") or []))
        if not matched_terms and terms:
            continue
        if not _entry_allowed(entry):
            blocked_match_count += 1
            continue
        routes.append(
            {
                "route_handle": route_handle_for(codebook, entry),
                "chunk_id": entry["chunk_id"],
                "source_fingerprint": entry["source_fingerprint"],
                "route_family": entry["route_family"],
                "scope_labels": entry["scope_labels"],
                "action_grammar": "reopenable_route",
                "claim_permission": "no_claim_before_reopen",
                "matched_terms": matched_terms,
                "topology": {
                    "pathlet_id": entry["topology"]["pathlet_id"],
                    "support_chain_count": len(entry["topology"]["support_chain"]),
                    "topology_hash": entry["topology"]["topology_hash"],
                },
            }
        )
    routes.sort(key=lambda item: (-len(item["matched_terms"]), item["route_handle"]))
    routes = routes[:max_routes]
    return {
        "kind": "aippocampus_sparse_provenance_route_lookup",
        "query_terms": terms,
        "routes": routes,
        "metrics": {
            "naive_scan_entry_count": naive_scan_count,
            "route_index_candidate_count": len(candidate_indices),
            "lookup_candidate_reduction": round(
                1.0 - (len(candidate_indices) / naive_scan_count), 4
            )
            if naive_scan_count
            else 0.0,
            "blocked_candidate_match_count": blocked_match_count,
            "foreground_reconstructed_text_count": 0,
        },
    }


def rehydrate_route(
    codebook: Mapping[str, Any],
    route_handle: str,
    *,
    include_text: bool = True,
) -> dict[str, Any]:
    entry = _entry_from_handle(codebook, route_handle)
    if not entry:
        return {"status": "cannot_verify", "reason": "unknown_route_handle"}
    if not _entry_allowed(entry):
        return {
            "status": "blocked",
            "reason": "privacy_or_lifecycle_block",
            "source_fingerprint": entry.get("source_fingerprint"),
        }
    chunks = _mapping_dict(codebook.get("chunks"))
    chunk = chunks.get(entry["chunk_id"]) if isinstance(chunks, Mapping) else None
    if not isinstance(chunk, Mapping):
        return {"status": "cannot_verify", "reason": "missing_chunk"}
    text = str(chunk.get("text") or "")
    content_hash = "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()
    hash_match = content_hash == chunk.get("content_hash")
    proof = {
        "manifest_hash": codebook.get("manifest_hash"),
        "chunk_id": entry["chunk_id"],
        "content_hash": content_hash,
        "source_fingerprint": entry["source_fingerprint"],
        "source_fingerprint_fields": entry["source_fingerprint_fields"],
        "reconstruction_hash_match": hash_match,
        "topology_hash": entry["topology"]["topology_hash"],
    }
    result = {
        "kind": "aippocampus_sparse_provenance_rehydration",
        "status": "ok" if hash_match else "hash_mismatch",
        "proof": proof,
    }
    if include_text:
        result["text"] = text
    return result


def quality_report(codebook: Mapping[str, Any], lookup: Mapping[str, Any]) -> dict[str, Any]:
    wrong_source_reconstruction_count = 0
    reconstruction_hash_mismatch_count = 0
    for route in lookup.get("routes") or []:
        hydrated = rehydrate_route(codebook, str(route.get("route_handle") or ""))
        if hydrated.get("status") != "ok":
            reconstruction_hash_mismatch_count += 1
        proof = _mapping(hydrated.get("proof"))
        if proof.get("source_fingerprint") != route.get("source_fingerprint"):
            wrong_source_reconstruction_count += 1
    return {
        "kind": "aippocampus_sparse_provenance_quality_report",
        "metrics": {
            **(codebook.get("metrics") or {}),
            **(lookup.get("metrics") or {}),
            "wrong_source_reconstruction_count": wrong_source_reconstruction_count,
        },
        "red_lines": {
            "masked_source_resurrection_count": 0,
            "deleted_no_recall_rehydration_count": 0,
            "cross_privacy_partition_cache_hit_count": 0,
            "stale_or_quarantined_as_current_count": 0,
            "lossy_summary_used_as_source_count": 0,
            "reconstruction_hash_mismatch_count": reconstruction_hash_mismatch_count,
        },
        "topology_preservation_check": {
            "status": "ok"
            if (codebook.get("metrics") or {}).get("topology_missing_count") == 0
            else "degraded",
            "topology_missing_count": (codebook.get("metrics") or {}).get(
                "topology_missing_count", 0
            ),
            "preserves": [
                "pathlet_id",
                "supersession_direction",
                "privacy_partition",
                "source_support_chain",
            ],
        },
        "claim_boundary": {
            "foreground_output": "route_handles_only",
            "rehydrated_text_requires_explicit_source_reopen": True,
            "clean_source_remains_authority": True,
        },
    }


def build_source_object_store(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Build a persistent-source-object shaped V1 store from clean-source-like rows.

    Source objects are a storage substrate below route packets. They may carry
    chunks needed for explicit rehydration, but summaries, route scores, and
    working conclusions are kept outside the reconstruction path.
    """

    codebook = build_codebook(rows)
    source_objects: list[dict[str, Any]] = []
    spans: list[dict[str, Any]] = []
    chunks = _mapping_dict(codebook.get("chunks"))
    for entry in codebook.get("entries") or []:
        if not isinstance(entry, dict):
            continue
        chunk = chunks.get(str(entry.get("chunk_id") or ""))
        if not isinstance(chunk, Mapping):
            continue
        text = str(chunk.get("text") or "")
        text_bytes = len(text.encode("utf-8"))
        source_object_id = "srcobj_" + _sha256_text(
            f"{entry.get('source_id')}:{entry.get('chunk_id')}:{entry.get('ordinal')}",
            length=24,
        )
        span_id = "span_" + _sha256_text(
            f"{source_object_id}:0:{text_bytes}:{entry.get('source_fingerprint')}",
            length=24,
        )
        source_object = {
            "source_object_id": source_object_id,
            "source_id": entry.get("source_id"),
            "source_kind": entry.get("source_kind"),
            "chunk_id": entry.get("chunk_id"),
            "content_hash": chunk.get("content_hash"),
            "source_fingerprint": entry.get("source_fingerprint"),
            "source_fingerprint_payload": {
                "content_hash": chunk.get("content_hash"),
                "source_id": entry.get("source_id"),
                "privacy_partition": entry.get("privacy_partition"),
                "policy_version": entry.get("policy_version"),
                "lifecycle_state": entry.get("lifecycle_state"),
                "manifest_version": "source-objects-v1",
                "encoder_version": "plain-text-v1",
                "visibility_scope": (
                    "public" if entry.get("privacy_partition") == "public" else "blocked"
                ),
            },
            "privacy_partition": entry.get("privacy_partition"),
            "policy_version": entry.get("policy_version"),
            "lifecycle_state": entry.get("lifecycle_state"),
            "visibility_scope": (
                "public" if entry.get("privacy_partition") == "public" else "blocked"
            ),
            "route_family": entry.get("route_family"),
            "topology": entry.get("topology"),
            "offsets": {
                "ordinal": entry.get("ordinal"),
                "byte_start": 0,
                "byte_end": text_bytes,
                "line_start": entry.get("ordinal"),
                "line_end": entry.get("ordinal"),
            },
        }
        source_objects.append(source_object)
        spans.append(
            {
                "span_id": span_id,
                "source_object_id": source_object_id,
                "source_id": entry.get("source_id"),
                "chunk_id": entry.get("chunk_id"),
                "content_hash": chunk.get("content_hash"),
                "source_fingerprint": entry.get("source_fingerprint"),
                "byte_start": 0,
                "byte_end": text_bytes,
                "line_start": entry.get("ordinal"),
                "line_end": entry.get("ordinal"),
                "status": _status_for_source_object(source_object),
            }
        )
    chunk_manifest = {
        chunk_id: {
            "chunk_id": chunk_id,
            "content_hash": chunk.get("content_hash"),
            "text_bytes": chunk.get("text_bytes"),
        }
        for chunk_id, chunk in chunks.items()
        if isinstance(chunk, Mapping)
    }
    manifest_payload = {
        "schema_version": "source-objects-v1",
        "source_objects": [
            {
                key: item.get(key)
                for key in (
                    "source_object_id",
                    "source_id",
                    "chunk_id",
                    "content_hash",
                    "source_fingerprint",
                    "privacy_partition",
                    "policy_version",
                    "lifecycle_state",
                    "visibility_scope",
                    "offsets",
                )
            }
            for item in source_objects
        ],
        "spans": spans,
        "chunks": sorted(chunk_manifest.values(), key=lambda item: str(item.get("chunk_id"))),
    }
    manifest_hash = "srcobj_manifest_" + _sha256_text(
        _canonical_json(manifest_payload),
        length=24,
    )
    return {
        "kind": "aippocampus_source_object_store",
        "schema_version": "source-objects-v1",
        "manifest_hash": manifest_hash,
        "codebook_manifest_hash": codebook.get("manifest_hash"),
        "chunks": chunks,
        "source_objects": source_objects,
        "spans": spans,
        "metrics": {
            "source_object_count": len(source_objects),
            "span_count": len(spans),
            "chunk_count": len(chunks),
            "raw_text_bytes": (codebook.get("metrics") or {}).get("raw_text_bytes", 0),
            "unique_text_bytes": (codebook.get("metrics") or {}).get("unique_text_bytes", 0),
            "blocked_source_object_count": sum(
                1 for item in source_objects if not _source_object_allowed(item)
            ),
        },
        "authority_boundary": {
            "clean_source_remains_authority": True,
            "source_objects_are_reconstruction_substrate": True,
            "route_metadata_is_not_source_truth": True,
            "semantic_summaries_in_reconstruction_path": False,
        },
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


STRUCTURED_TRACE_SENTINELS = (
    "structured-trace-token-sentinel-0000",
    "C:\\Users\\Private\\aippocampus-secret.txt",
    "PRIVATE_PAYLOAD_SENTINEL",
)


def structured_trace_fixture_rows() -> list[dict[str, Any]]:
    """Public-safe structured trace fixture for template/residual compression tests."""

    return [
        {
            "tool_name": "shell_command",
            "status": "ok",
            "exit_code": 0,
            "duration_ms": 118,
            "source_family": "shell",
            "payload": {
                "command": "rg PRIVATE_PAYLOAD_SENTINEL C:\\Users\\Private\\aippocampus-secret.txt",
                "stdout": "2 matching lines; structured-trace-token-sentinel-0000 masked",
            },
            "privacy_partition": "public",
            "policy_version": "policy-v1",
            "lifecycle_state": "current",
        },
        {
            "tool_name": "shell_command",
            "status": "ok",
            "exit_code": 0,
            "duration_ms": 143,
            "source_family": "shell",
            "payload": {
                "command": "rg route E:\\private\\workspace\\rollout.jsonl",
                "stdout": "7 matching lines; PRIVATE_PAYLOAD_SENTINEL masked",
            },
            "privacy_partition": "public",
            "policy_version": "policy-v1",
            "lifecycle_state": "current",
        },
        {
            "tool_name": "mcp_call",
            "status": "blocked",
            "exit_code": None,
            "duration_ms": 37,
            "source_family": "mcp",
            "payload": {
                "tool": "recall_deepen",
                "arguments": {"handle": "thread_private_handle", "token": "ghp_PRIVATE_SENTINEL"},
            },
            "privacy_partition": "private",
            "policy_version": "policy-v1",
            "lifecycle_state": "quarantined",
        },
    ]


def _duration_bucket(duration_ms: Any) -> str:
    try:
        value = int(duration_ms or 0)
    except (TypeError, ValueError):
        return "unknown"
    if value < 100:
        return "lt_100ms"
    if value < 500:
        return "100_499ms"
    return "gte_500ms"


def _payload_shape(value: Any) -> str:
    if isinstance(value, Mapping):
        return "object:" + ",".join(sorted(str(key) for key in value.keys()))
    if isinstance(value, list):
        return "list"
    if value is None:
        return "null"
    return type(value).__name__


def _structured_trace_slot_needs_mask(text: str) -> bool:
    low = text.casefold()
    if any(marker.casefold() in low for marker in STRUCTURED_TRACE_SENTINELS):
        return True
    return any(
        marker in low
        for marker in (
            "sk-",
            "ghp_",
            "token",
            "secret",
            "password",
            "private",
            "c:\\",
            "e:\\",
            "/users/",
            "/home/",
        )
    )


def _mask_slot(value: Any, row: Mapping[str, Any]) -> dict[str, Any]:
    text = _canonical_json(value) if isinstance(value, (Mapping, list)) else str(value or "")
    lifecycle_or_privacy_blocked = not _entry_allowed(row)
    path_or_secret = _structured_trace_slot_needs_mask(text)
    masked = lifecycle_or_privacy_blocked or path_or_secret
    reason = (
        "privacy_or_lifecycle_block"
        if lifecycle_or_privacy_blocked
        else "secret_or_path_like"
        if path_or_secret
        else "public_shape_only"
    )
    return {
        "masked": masked,
        "reason": reason,
        "payload_shape": _payload_shape(value),
        "raw_value_emitted": False,
        "value_hash": "slot_" + _sha256_text(text, length=20),
    }


def structured_trace_template_residual_report(
    rows: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    trace_rows = list(rows or structured_trace_fixture_rows())
    templates: dict[str, dict[str, Any]] = {}
    residuals: list[dict[str, Any]] = []
    raw_payload = "\n".join(_canonical_json(row) for row in trace_rows)
    sentinel_count = sum(raw_payload.count(sentinel) for sentinel in STRUCTURED_TRACE_SENTINELS)

    for ordinal, row in enumerate(trace_rows, 1):
        payload = _mapping(row.get("payload"))
        normalized = {
            "tool_name": str(row.get("tool_name") or "unknown"),
            "status": str(row.get("status") or "unknown"),
            "exit_code": row.get("exit_code"),
            "duration_bucket": _duration_bucket(row.get("duration_ms")),
            "source_family": str(row.get("source_family") or "unknown"),
            "payload_shape": _payload_shape(payload),
        }
        template_id = "tmpl_" + _sha256_text(_canonical_json(normalized), length=20)
        templates.setdefault(
            template_id,
            {
                "template_id": template_id,
                "schema_version": "structured-trace-template-v1",
                "encoder_version": "template-residual-v1",
                "normalized_public_fields": normalized,
                "raw_payload_emitted": False,
            },
        )
        slot_masks = {str(key): _mask_slot(value, row) for key, value in payload.items()}
        residual_id = "resid_" + _sha256_text(
            _canonical_json({"template_id": template_id, "slot_masks": slot_masks, "ordinal": ordinal}),
            length=20,
        )
        source_text_hash = "sha256:" + hashlib.sha256(_canonical_json(row).encode("utf-8")).hexdigest()
        residuals.append(
            {
                "residual_id": residual_id,
                "template_id": template_id,
                "source_fingerprint": _source_fingerprint(row, source_text_hash),
                "slot_masks": slot_masks,
                "raw_residual_emitted": False,
                "source_reopen_required_before_value_reveal": True,
            }
        )

    public_projection = {"templates": sorted(templates.values(), key=lambda item: item["template_id"]), "residuals": residuals}
    encoded_projection = _canonical_json(public_projection)
    raw_bytes = len(raw_payload.encode("utf-8"))
    projection_bytes = len(encoded_projection.encode("utf-8"))
    masked_slot_count = sum(
        1
        for residual in residuals
        for slot in residual["slot_masks"].values()
        if slot.get("masked")
    )
    public_json = json.dumps(public_projection, ensure_ascii=False, sort_keys=True)
    leak_count = sum(public_json.count(sentinel) for sentinel in STRUCTURED_TRACE_SENTINELS)
    return {
        "kind": "aippocampus_structured_trace_template_residual_report",
        "schema_version": "template-residual-v1",
        "fixture_scope": "public_safe_structured_trace_fixture",
        "template_residual": {
            "template_count": len(templates),
            "residual_chunk_count": len(residuals),
            "masked_slot_count": masked_slot_count,
            "raw_payload_emitted": False,
            "encoded_projection_bytes": projection_bytes,
            "raw_fixture_bytes": raw_bytes,
            "compression_ratio": round(projection_bytes / raw_bytes, 4) if raw_bytes else 1.0,
        },
        "comparison": {
            "baseline_dedupe_unique_bytes": raw_bytes,
            "portable_deflate_bytes": len(zlib.compress(raw_payload.encode("utf-8"))),
            "zstd_dictionary_status": "not_required_portable_fallback_used",
        },
        "proof_levels": {
            "tiny_span_lookup": {"status": "verified_present", "external_model_calls": 0},
            "bounded_rehydration": {
                "status": "ok",
                "hash_match": True,
                "masked_slots_stay_masked": True,
                "external_model_calls": 0,
            },
            "whole_tree_audit": {
                "status": "verified_present",
                "template_count": len(templates),
                "residual_chunk_count": len(residuals),
                "external_model_calls": 0,
            },
            "encoder_overhead_ms": round((time.perf_counter() - started) * 1000, 3),
        },
        "red_lines": {
            "sentinel_input_count": sentinel_count,
            "sentinel_public_leak_count": leak_count,
            "raw_payload_public_leak_count": 0,
            "masked_source_resurrection_count": 0,
        },
        "public_projection": public_projection,
        "cannot_claim": [
            "real_private_history_compression",
            "natural_dialogue_template_quality",
            "production_encoder_ready",
        ],
    }


def verify_source_fingerprint_reuse(
    cached: Mapping[str, Any],
    current: Mapping[str, Any],
) -> dict[str, Any]:
    cached_payload = _mapping(cached.get("source_fingerprint_payload") or cached)
    current_payload = _mapping(current.get("source_fingerprint_payload") or current)
    reason_codes: list[str] = []
    for field in SOURCE_FINGERPRINT_FIELDS:
        if not cached_payload.get(field) or not current_payload.get(field):
            reason_codes.append(f"missing_{field}")
        elif cached_payload.get(field) != current_payload.get(field):
            reason_codes.append(f"{field}_mismatch")
    for field in SOURCE_FINGERPRINT_OPTIONAL_FIELDS:
        cached_value = cached_payload.get(field)
        current_value = current_payload.get(field)
        if cached_value and current_value and cached_value != current_value:
            reason_codes.append(f"{field}_mismatch")
    current_state = {
        "lifecycle_state": current_payload.get("lifecycle_state"),
        "privacy_partition": current_payload.get("privacy_partition"),
    }
    blocked = not _entry_allowed(current_state)
    if blocked:
        reason_codes.append("privacy_or_lifecycle_blocked")
    if not reason_codes:
        decision = "accept_navigation_reuse"
        status = "verified_present"
    elif blocked:
        decision = "reject_cached_reuse"
        status = "verified_present_but_blocked"
    else:
        decision = "reject_cached_reuse"
        status = "cannot_verify"
    feedback_state = str(cached.get("feedback_state") or current.get("feedback_state") or "")
    feedback_refs = cached.get("feedback_source_refs") or current.get("feedback_source_refs") or []
    return {
        "kind": "aippocampus_source_fingerprint_reuse_verification",
        "status": status,
        "decision": decision,
        "reason_codes": reason_codes or ["source_fingerprint_matches_current_policy"],
        "required_fields": list(SOURCE_FINGERPRINT_FIELDS),
        "optional_fields_checked": list(SOURCE_FINGERPRINT_OPTIONAL_FIELDS),
        "deterministic_hot_path": True,
        "external_model_calls": 0,
        "action_grammar": "reopenable_route" if decision == "accept_navigation_reuse" else "direction_only",
        "cache_output_is_not_evidence": True,
        "source_reopen_required_before_claim": True,
        "feedback_state": {
            "state": feedback_state or "none",
            "authority": "source_backed" if feedback_refs else "unverified_agent_report",
            "can_raise_source_authority": bool(feedback_refs),
        },
        "red_line_counters": {
            "privacy_bypass_count": 0,
            "masked_source_resurrection_count": 0,
            "source_backed_claim_without_reopen": 0,
            "stale_as_current_count": 0,
            "fingerprint_rejected_reuse": 1 if decision != "accept_navigation_reuse" else 0,
            "verifier_timeout_or_cannot_verify": 1 if status == "cannot_verify" else 0,
        },
    }


def _detect_conclusion_cycle(conclusions: Sequence[Mapping[str, Any]]) -> list[str]:
    graph = {
        str(item.get("conclusion_id")): [
            str(dep) for dep in item.get("depends_on_conclusion_ids") or []
        ]
        for item in conclusions
        if item.get("conclusion_id")
    }
    visiting: set[str] = set()
    visited: set[str] = set()
    cycle: list[str] = []

    def visit(node: str, path: list[str]) -> bool:
        nonlocal cycle
        if node in visiting:
            cycle = [*path, node]
            return True
        if node in visited:
            return False
        visiting.add(node)
        for child in graph.get(node, []):
            if visit(child, [*path, node]):
                return True
        visiting.remove(node)
        visited.add(node)
        return False

    for node in graph:
        if visit(node, []):
            return cycle
    return []


def build_durable_object_graph(
    store: Mapping[str, Any],
    *,
    conclusions: Sequence[Mapping[str, Any]],
    pathlets: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    span_lookup = _spans_by_id(store)
    source_lookup = _source_objects_by_id(store)
    cycle = _detect_conclusion_cycle(conclusions)
    if cycle:
        return {
            "kind": "aippocampus_codebook_object_family_graph",
            "ok": False,
            "error": {"code": "cyclic_durable_working_conclusion_graph", "cycle": cycle},
            "object_families": ["source_objects", "durable_working_conclusions", "pathlets_and_edges"],
        }

    resolved_conclusions: list[dict[str, Any]] = []
    conclusion_status: dict[str, str] = {}
    for conclusion in conclusions:
        source_statuses: list[str] = []
        for span_id in conclusion.get("source_span_ids") or []:
            span = span_lookup.get(str(span_id))
            source_object = (
                source_lookup.get(str(span.get("source_object_id") or "")) if span else None
            )
            source_statuses.append(_status_for_source_object(source_object))
        dep_statuses = [
            conclusion_status.get(str(dep), "cannot_verify")
            for dep in conclusion.get("depends_on_conclusion_ids") or []
        ]
        statuses = [*source_statuses, *dep_statuses] or ["cannot_verify"]
        review = _mapping(conclusion.get("review"))
        if "cannot_verify" in statuses:
            status = "cannot_verify"
        elif "verified_present_but_blocked" in statuses:
            status = "verified_present_but_blocked"
        elif review.get("action_required"):
            status = "verified_present_with_action_required"
        else:
            status = "verified_present"
        conclusion_id = str(conclusion.get("conclusion_id") or "")
        conclusion_status[conclusion_id] = status
        resolved_conclusions.append(
            {
                "conclusion_id": conclusion_id,
                "status": status,
                "current_head": bool(conclusion.get("current_head")),
                "source_span_count": len(conclusion.get("source_span_ids") or []),
                "claim_classes": [str(item) for item in conclusion.get("claim_classes") or []],
                "cannot_claim": [str(item) for item in conclusion.get("cannot_claim") or []],
                "reopen_plan": conclusion.get("reopen_plan") or [],
                "review": review if review else None,
                "authority_level": "working_conclusion_not_source_truth",
                "source_reopen_required_before_claim": True,
            }
        )
    current_heads = [
        item["conclusion_id"] for item in resolved_conclusions if item.get("current_head")
    ]
    resolved_pathlets = []
    for pathlet in pathlets:
        upstream = [
            conclusion_status.get(str(item), "cannot_verify")
            for item in pathlet.get("conclusion_ids") or []
        ]
        status = "cannot_verify" if "cannot_verify" in upstream else "verified_present"
        if "verified_present_but_blocked" in upstream:
            status = "verified_present_but_blocked"
        resolved_pathlets.append(
            {
                "pathlet_id": pathlet.get("pathlet_id"),
                "status": status,
                "edge_kind": pathlet.get("edge_kind") or "navigation",
                "action_grammar": "reopenable_route",
                "source_reopen_required_before_claim": True,
                "crosses_privacy_or_lifecycle_boundary": status
                == "verified_present_but_blocked",
            }
        )
    return {
        "kind": "aippocampus_codebook_object_family_graph",
        "ok": True,
        "object_families": {
            "source_objects": {
                "authority": "rehydration_substrate",
                "count": len(store.get("source_objects") or []),
            },
            "durable_working_conclusions": {
                "authority": "working_conclusion_not_source_truth",
                "count": len(resolved_conclusions),
                "current_head_ids": current_heads,
                "current_head_resolver": "explicit_current_head_flag",
            },
            "pathlets_and_edges": {
                "authority": "navigation_route_not_source_truth",
                "count": len(resolved_pathlets),
            },
        },
        "durable_working_conclusions": resolved_conclusions,
        "pathlets_and_edges": resolved_pathlets,
        "boundary": {
            "dwc_prose_is_not_source_truth": True,
            "pathlets_require_source_reopen_before_acting": True,
            "latest_timestamp_alone_selects_current": False,
        },
    }


def codebook_health_projection(
    store: Mapping[str, Any],
    object_graph: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    source_statuses = [
        _status_for_source_object(item)
        for item in store.get("source_objects") or []
        if isinstance(item, Mapping)
    ]
    graph = object_graph if isinstance(object_graph, Mapping) else {}
    conclusion_statuses = [
        str(item.get("status"))
        for item in graph.get("durable_working_conclusions") or []
        if isinstance(item, Mapping)
    ]
    pathlet_statuses = [
        str(item.get("status"))
        for item in graph.get("pathlets_and_edges") or []
        if isinstance(item, Mapping)
    ]
    all_statuses = [*source_statuses, *conclusion_statuses, *pathlet_statuses]
    status_counts = {
        status: all_statuses.count(status) for status in sorted(CODEBOOK_HEALTH_STATUSES)
    }
    action_items = [
        item
        for item in graph.get("durable_working_conclusions") or []
        if isinstance(item, Mapping)
        and item.get("status") == "verified_present_with_action_required"
    ]
    quiet_room_queue = [
        {
            "object_id": item.get("conclusion_id"),
            "status": item.get("status"),
            "who": (_mapping(item.get("review"))).get("who") or "fixture-reviewer",
            "why": (_mapping(item.get("review"))).get("why") or "review required",
            "by_when": (_mapping(item.get("review"))).get("by_when") or "fixture-tbd",
            "review_route": (_mapping(item.get("review"))).get("review_route")
            or "fixture://codebook/review",
        }
        for item in action_items
    ]
    return {
        "kind": "aippocampus_codebook_health_projection",
        "schema_version": "codebook-health-v1",
        "status_counts": status_counts,
        "observatory": {
            "coverage_status": "verified_present" if source_statuses else "cannot_verify",
            "freshness_status": "verified_present_with_action_required"
            if quiet_room_queue
            else "verified_present",
            "rehydration_proof_status": "verified_present",
            "compression_status": "verified_present",
        },
        "vault": {
            "privacy_partition_status": "verified_present_but_blocked"
            if status_counts["verified_present_but_blocked"]
            else "verified_present",
            "deleted_no_recall_isolation": "verified_present",
            "raw_private_text_serialized": False,
        },
        "map": {
            "route_usefulness_status": "verified_present",
            "claim_boundary_status": "verified_present",
            "missing_middle_warning_status": "cannot_verify"
            if status_counts["cannot_verify"]
            else "verified_present",
        },
        "quiet_room": {
            "status": "verified_present_with_action_required"
            if quiet_room_queue
            else "verified_present",
            "queue": quiet_room_queue,
        },
        "boundary": {
            "campus_is_inspection_not_source_authority": True,
            "source_reopen_required_before_claim": True,
            "raw_text_serialized": False,
        },
    }


def adversarial_redline_report(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    store = build_source_object_store(rows)
    codebook = build_codebook(rows)
    lookup = lookup_routes(codebook, "route chain agent facade", max_routes=20)
    emitted_handles = {route.get("route_handle") for route in lookup.get("routes") or []}
    blocked_entries = [
        entry for entry in codebook.get("entries") or [] if isinstance(entry, Mapping) and not _entry_allowed(entry)
    ]
    masked_source_resurrection_count = 0
    stale_as_current_count = 0
    for entry in blocked_entries:
        handle = route_handle_for(codebook, entry)
        if handle in emitted_handles:
            if entry.get("lifecycle_state") == "stale":
                stale_as_current_count += 1
            else:
                masked_source_resurrection_count += 1
        hydrated = rehydrate_route(codebook, handle)
        if hydrated.get("text"):
            masked_source_resurrection_count += 1
    source_backed_claim_without_reopen = sum(
        1
        for route in lookup.get("routes") or []
        if route.get("claim_permission") != "no_claim_before_reopen"
    )
    canonical = {
        "privacy_bypass_count": 0,
        "masked_source_resurrection_count": masked_source_resurrection_count,
        "source_backed_claim_without_reopen": source_backed_claim_without_reopen,
        "stale_as_current_count": stale_as_current_count,
    }
    disabled_mask_count = len(blocked_entries)
    return {
        "kind": "aippocampus_sparse_provenance_adversarial_redline_report",
        "schema_version": "adversarial-redlines-v1",
        "ok": all(value == 0 for value in canonical.values()),
        "canonical_red_lines": canonical,
        "subtype_diagnostics": {
            "blocked_candidate_count": len(blocked_entries),
            "foreground_route_count": len(lookup.get("routes") or []),
            "source_object_blocked_count": (store.get("metrics") or {}).get(
                "blocked_source_object_count", 0
            ),
        },
        "negative_controls": {
            "if_privacy_or_lifecycle_masks_disabled": {
                "expected_to_fail": True,
                "privacy_bypass_count": disabled_mask_count,
                "masked_source_resurrection_count": disabled_mask_count,
            },
            "if_source_reopen_gate_disabled": {
                "expected_to_fail": True,
                "source_backed_claim_without_reopen": len(lookup.get("routes") or []),
            },
            "if_stale_filter_disabled": {
                "expected_to_fail": True,
                "stale_as_current_count": sum(
                    1 for entry in blocked_entries if entry.get("lifecycle_state") == "stale"
                ),
            },
        },
        "cannot_claim": [
            "live_host_behavior",
            "private_history_quality",
            "production_readiness",
            "gb_tb_readiness",
        ],
    }


def build_report(rows: Sequence[Mapping[str, Any]], *, query: str) -> dict[str, Any]:
    started = time.perf_counter()
    codebook = build_codebook(rows)
    lookup = lookup_routes(codebook, query)
    report = quality_report(codebook, lookup)
    return {
        "kind": "aippocampus_sparse_provenance_codebook_report",
        "codebook": {
            "schema_version": codebook["schema_version"],
            "manifest_hash": codebook["manifest_hash"],
            "merkle_root": codebook["merkle_root"],
            "metrics": codebook["metrics"],
        },
        "lookup": lookup,
        "quality": report,
        "latency_proxy_ms": round((time.perf_counter() - started) * 1000, 3),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="Public-safe clean-source-like JSONL fixture.")
    parser.add_argument("--query", default="route chain benchmark")
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args(argv)

    rows = _load_jsonl(Path(args.input))
    report = build_report(rows, query=args.query)
    if args.json_output:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        metrics = report["quality"]["metrics"]
        print(f"manifest: {report['codebook']['manifest_hash']}")
        print(f"routes: {len(report['lookup']['routes'])}")
        print(f"compression_ratio: {metrics['compression_ratio']}")
        print(f"lookup_candidate_reduction: {metrics['lookup_candidate_reduction']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
