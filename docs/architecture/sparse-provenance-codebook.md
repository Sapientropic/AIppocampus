# Sparse Provenance Codebook

Role: current contract

Status: V0 runtime and public fixture for #1190. This is a deterministic
storage/router primitive, not a replacement for clean source.

## Boundary

The sparse provenance codebook may compress repeated clean-source-like
structure, dedupe content-addressed chunks, and return route handles with
reconstruction proofs. It must not turn compressed chunks, route scores, lossy
summaries, or topology metadata into source-backed claims.

Useful slogan:

> Let the codebook compress and route; let clean source testify.

Foreground lookup returns route handles, source fingerprints, route family,
scope labels, and topology hashes. It does not return reconstructed text.
Rehydrated text is available only through an explicit source-reopen /
rehydration call and only when lifecycle and privacy partitions allow it.

## Runtime Owner

`aippocampus_runtime.source.provenance_codebook` owns the V0 fixture path:

- build content-addressed chunks from public clean-source-like rows;
- compute source fingerprints from content hash, source id, privacy partition,
  policy version, and lifecycle state;
- build a small route index from route families, scope labels, source kind,
  lifecycle state, and topology ids;
- return compact `spc:<manifest>:<entry>` route handles;
- rehydrate a selected allowed route with a manifest/chunk hash proof;
- report compression, lookup reduction, reconstruction, red-line, and topology
  preservation metrics.

The public fixture lives at
`benchmark_corpus/sparse_provenance/public_clean_source_like_events.jsonl`.

## Red Lines

The V0 report keeps these as zero-failure counters:

- `masked_source_resurrection_count`
- `deleted_no_recall_rehydration_count`
- `cross_privacy_partition_cache_hit_count`
- `stale_or_quarantined_as_current_count`
- `lossy_summary_used_as_source_count`
- `reconstruction_hash_mismatch_count`

Blocked or stale candidates may be counted as matched-and-suppressed
diagnostics, but that is not a red-line failure unless they are emitted as a
route or rehydrated as current source.

## Topology

The codebook must preserve more than bytes. Each entry can carry a topology
hash over pathlet id, supersession direction, privacy partition boundary, and
source-support chain. This supports route reconstruction and observability
without making topology a ranking override or evidence layer.

Topology preservation is a diagnostic check. Missing topology degrades the
report; it does not authorize broader search, cross-partition reuse, or
foreground claims.

## Non-Claims

This V0 does not prove natural-dialogue semantic template compression, neural
MoE routing, private-history quality, or GB/TB-scale infrastructure readiness.
It only proves that a small public corpus can be deduped, route-indexed,
rehydrated deterministically, and blocked by lifecycle/privacy masks.
