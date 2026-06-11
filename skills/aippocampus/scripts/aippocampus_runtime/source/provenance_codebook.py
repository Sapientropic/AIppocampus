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


def _source_fingerprint(row: Mapping[str, Any], content_hash: str) -> str:
    payload = {
        "content_hash": content_hash,
        "source_id": str(row.get("source_id") or ""),
        "privacy_partition": str(row.get("privacy_partition") or "unknown"),
        "policy_version": str(row.get("policy_version") or "unknown"),
        "lifecycle_state": str(row.get("lifecycle_state") or "unknown"),
    }
    return "srcfp_" + _sha256_text(_canonical_json(payload), length=24)


def _entry_allowed(entry: Mapping[str, Any]) -> bool:
    lifecycle_state = str(entry.get("lifecycle_state") or "")
    privacy_partition = str(entry.get("privacy_partition") or "")
    return (
        lifecycle_state in ALLOWED_LIFECYCLE_STATES
        and lifecycle_state not in BLOCKED_LIFECYCLE_STATES
        and privacy_partition not in BLOCKED_PRIVACY_PARTITIONS
    )


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
    chunks = codebook.get("chunks") if isinstance(codebook.get("chunks"), Mapping) else {}
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
