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

## V1 Scale-Layer Contract

The scale-layer work tracked by #1869 keeps one authority order:

1. `source_objects` are the reconstruction substrate below route packets.
   They carry stable `source_object_id`, `chunk_id`, `span_id`, offsets,
   content hash, manifest hash, source fingerprint, privacy partition, policy
   version, lifecycle state, and visibility scope. Public summaries must show
   counts, bytes, hashes, and proof status without raw source text.
2. `durable_working_conclusions` are reviewable working objects linked back to
   source spans. They may carry scope, freshness, claim classes, cannot-claim
   fields, and reopen plans, but their prose is not source truth. Current
   heads require an explicit resolver or head pointer; latest timestamp alone
   is not enough.
3. `pathlets_and_edges` preserve sequence-sensitive navigation such as
   rejected paths, corrections, supersession, missing-middle links, and
   outcome-shaped edges. They remain `reopenable_route` objects and require
   source reopen before action.

The V1 public fixture code lives in the same runtime owner,
`aippocampus_runtime.source.provenance_codebook`, and adds:

- persistent source-object layout with manifest, per-object JSON, per-span
  JSON, and chunk files;
- explicit span rehydration proofs that hash-match content and source
  fingerprints;
- fixture-local compression/proof reports using baseline dedupe plus portable
  deflate fallback, without native dependency requirements;
- early structured-trace template/residual encoding over public-safe
  tool-call and machine-output-like fixtures. This reports stable template ids,
  residual ids, normalized public fields, slot-level mask metadata, separate
  template/residual metrics, baseline dedupe, portable compression comparison,
  and proof levels without emitting raw payloads, local paths, token-like
  strings, or private handles;
- source-fingerprint reuse verification that fails closed on content, source
  id, privacy partition, policy version, lifecycle state, or optional manifest
  / encoder / retention / visibility mismatch;
- durable working conclusion DAG validation and downstream degradation when
  upstream source objects are blocked, missing, or cannot verify;
- codebook health projection for Observatory, Vault, Map, and Quiet Room
  inspection surfaces.

## Compression Artifact Contract

Compression-derived artifacts are navigation-only derived artifacts, not source
truth. Dictionaries, templates, residual chunks, route handles, chunk ids,
proof anchors, and manifest integrity anchors must carry privacy/lifecycle
metadata before reuse or public projection.

The code-adjacent contract is
`aippocampus_runtime.source.provenance_codebook.compression_artifact_contract_report()`.
It is the canonical field owner for #1898 and points to #1893/#1894 for
enforcement tests instead of mirroring verifier logic here.

Allowed public projections may include aggregate ids, byte counts, codec
versions, training scope, privacy partition, redaction/mask policy versions,
template/residual counts, and hash-only route/chunk/proof anchors. They must
not include raw dictionary bytes, raw residuals, raw payloads, raw source text,
private handles, local paths, token-like strings, or proof material sufficient
to reconstruct masked slots.

Cross-privacy-partition dictionary/residual reuse, stale redaction policy
reuse, and source-family mismatch reuse are blocked by the compression-aware
fingerprint verifier.

## Measurement And Storage Decision Gate

`aippocampus_runtime.source.provenance_codebook_economics.source_family_economics_report()`
is the read-only source-family measurement entrypoint. Per family it compares:

- baseline content-addressed dedupe;
- portable zlib deflate;
- optional zstd without dictionary;
- optional zstd dictionary with public-safe metadata only;
- template/residual encoding for structured trace families.

Optional zstd arms must degrade to `skipped` when no supported backend exists.
The portable baseline remains available without native dependencies.

FastCDC/content-defined chunking and LMDB chunk storage stay behind the
`storage_primitive_decision_gate` section. The current default decision is
`defer` unless public-safe source-family evidence shows material extra dedupe
or file-system pressure while preserving source spans, privacy partitions,
lifecycle boundaries, and rehydration proofs.

Campus/Observatory status is inspection, not authority. The four public-safe
status values are:

- `verified_present`
- `verified_present_but_blocked`
- `cannot_verify`
- `verified_present_with_action_required`

`verified_present_with_action_required` must include a review route or
fixture-safe placeholders for `who`, `why`, and `by_when`.

## Red Lines

The V0 report keeps these as zero-failure counters:

- `masked_source_resurrection_count`
- `deleted_no_recall_rehydration_count`
- `cross_privacy_partition_cache_hit_count`
- `stale_or_quarantined_as_current_count`
- `lossy_summary_used_as_source_count`
- `reconstruction_hash_mismatch_count`

The V1 adversarial fixture also emits the canonical #1106 counters:

- `privacy_bypass_count`
- `masked_source_resurrection_count`
- `source_backed_claim_without_reopen`
- `stale_as_current_count`

Negative controls may intentionally fail when hard masks or source-reopen
gates are disabled, but passing reports must keep the canonical counters at
zero and separate them from subtype diagnostics.

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

This V0/V1 fixture track does not prove natural-dialogue semantic template
compression, real private-history compression, neural MoE routing,
private-history quality, Campus product readiness, or GB/TB-scale
infrastructure readiness. It proves only fixture-local storage,
dedupe/compression measurement, structured-trace template/residual masking,
deterministic rehydration, cache-reuse rejection, object-family degradation,
and lifecycle/privacy red-line behavior.
