# Sparse Provenance Codebook V0

Run date: 2026-06-12.

Command:

```powershell
python -m aippocampus_runtime.source.provenance_codebook --input benchmark_corpus\sparse_provenance\public_clean_source_like_events.jsonl --query "route chain calibration" --json
```

Machine-readable output:
[`sparse-provenance-codebook-v0-2026-06-12.json`](sparse-provenance-codebook-v0-2026-06-12.json).

## Measured Result

- 8 public-safe clean-source-like entries were represented as 6 unique
  content-addressed chunks.
- `deduped_entry_count=2`, `compression_ratio=0.75`, and
  `dedupe_saved_bytes=204`.
- Route lookup reduced candidate consideration from 8 naive entries to 5
  indexed candidates for the route-chain query.
- 2 stale/quarantined candidates matched the query but were suppressed.
- Foreground lookup emitted 0 reconstructed text items.
- Rehydration proof checks passed for emitted route handles:
  `wrong_source_reconstruction_count=0` and
  `reconstruction_hash_mismatch_count=0`.
- Topology preservation reported `status=ok` with pathlet,
  supersession-direction, privacy-partition, and source-support-chain fields.

## Supports

This supports #1190 as a small deterministic V0: sparse provenance can dedupe
repeated public source structure, return route handles, block
stale/quarantined/deleted-no-recall material from foreground/reconstruction,
and prove selected rehydration against a manifest/chunk hash.

## Material Limits

This does not prove natural-dialogue template compression, zstd dictionary
value, neural MoE routing, private-history behavior, GB/TB-scale infrastructure,
or broad lookup quality. Clean source remains the authority layer; the codebook
only compresses, routes, and proves reconstruction.
