# Sparse Provenance Source-Family Economics Evidence - 2026-06-16

Source: #1891 closeout gate for the sparse provenance codebook track.

This is a read-only measurement over temporary public-safe synthetic JSONL
families. The large inputs were generated during the run and were not committed.
No private real-history payloads, local paths, thread ids, prompt text, or source
contents are included in this artifact.

## Scope

Measured families:

| Family | Kind | Raw bytes | Rows |
| --- | --- | ---: | ---: |
| `natural-clean-source-100mb` | human-visible natural conversation-like clean source | 106,971,807 | 2,885 |
| `structured-tool-traces-100mb` | structured tool/system/model traces | 106,959,500 | 2,879 |
| `generated-reports-100mb` | generated indexes/reports/benchmark artifacts | 106,980,026 | 2,886 |
| `mixed-long-agent-bundle-100mb` | mixed long-agent session bundle | 106,956,938 | 2,886 |

Runner:
`aippocampus_runtime.source.provenance_codebook_economics.source_family_economics_report()`.

## Results

| Family | Encoded/store bytes | Build ms | Lookup ms | Candidate reduction | Templates | Residual bytes | Rehydrate ms | Hash correct | Store/raw amp | Deflate bytes |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | ---: | ---: |
| `natural-clean-source-100mb` | 111,035,402 | 293.778 | 1.106 | 0.0 | 1 | 2,327,491 | 0.741 | true | 1.0380 | 696,647 |
| `structured-tool-traces-100mb` | 4,100,259 | 104.439 | 1.163 | 0.0 | 1 | 2,740,092 | 0.506 | true | 0.0383 | 829,118 |
| `generated-reports-100mb` | 111,047,918 | 289.494 | 1.268 | 0.0 | 1 | 2,319,633 | 0.659 | true | 1.0380 | 694,245 |
| `mixed-long-agent-bundle-100mb` | 111,099,866 | 316.913 | 1.209 | 0.0 | 1 | 2,336,935 | 0.654 | true | 1.0387 | 662,126 |

Dominant family by encoded/store bytes:
`mixed-long-agent-bundle-100mb`.

## Codec Matrix

The runner now reports a per-family codec matrix:

- `baseline_content_addressed_dedupe`
- `portable_deflate`
- `zstd_no_dictionary`
- `zstd_dictionary`
- `template_residual`

On this local run, the portable baseline and template/residual arms are
available. The optional zstd and zstd-dictionary arms are reported as
`skipped` because the `zstandard` Python module is not installed in the local
runtime. That is a dependency boundary, not evidence that zstd would lose.

Dictionary arms expose public-safe metadata only: codec id/version,
dictionary id, dictionary byte length, training source family, training privacy
partition, redaction/mask policy versions, encoded bytes when available, and
timing. Raw dictionary bytes are never serialized. Dictionary training uses
public/current samples only; mixed or private rows do not become a reusable
cross-partition dictionary.

Template/residual and zstd dictionary arms are reported side by side for
structured trace families. In this environment the dictionary arm is skipped,
while template/residual remains measurable without native dependencies.

## Compression Artifact Contract

Compression dictionaries, templates, residual chunks, route handles, chunk ids,
proof anchors, and manifest anchors are classified as privacy-partitioned
derived artifacts. The canonical code-adjacent contract is
`compression_artifact_contract_report()` in
`aippocampus_runtime.source.provenance_codebook`.

Allowed public projections are aggregate ids, byte counts, codec/encoder
versions, privacy partition, source family, lifecycle/visibility, redaction and
mask policy versions, and hash-only handles. Public reports must not serialize
raw dictionary bytes, raw residuals, raw payloads, raw source text, private
handles, local paths, token-like strings, or proof material sufficient to
reconstruct masked slots.

Executable negative controls now cover dictionary trained from unredacted
sentinel-bearing samples, cross-privacy-partition dictionary reuse, and public
projection leaks in addition to the prior mask, reopen, stale/current, and
template/residual controls.

## CDC / LMDB Decision Gate

The report includes a `storage_primitive_decision_gate` section. Current
decisions:

| Primitive | Decision | Why |
| --- | --- | --- |
| FastCDC / content-defined chunking | `defer` | Extra overlap gain after deflate/zstd/template-residual is not measured, and CDC must prove it can preserve source span and privacy-partition boundaries. |
| LMDB chunk storage | `defer` | File-per-chunk pressure is not proven; Windows mmap, single-writer, backup, repair, and migration costs are not justified by the fixture-scale evidence. |

Reopen thresholds include at least 15% extra dedupe after codec arms for CDC,
1GB+ public-safe source-family evidence, source-span/privacy-boundary
preservation, 100k+ chunk count or 20% file-system overhead for LMDB, and a
backup/repair plan before implementation.

## Interpretation

Structured traces dominated the positive storage result in this synthetic gate:
template/residual shape plus repeated payload structure reduced encoded store
bytes far more than the natural/generated/mixed text-like families.

Natural conversation-like, generated report, and mixed-agent synthetic rows did
not show sparse-provenance store compression at this shape. Their encoded store
size was slightly above raw input because source-object metadata is deliberately
kept beside the reconstruction substrate.

Candidate reduction was 0.0 for this synthetic query because every generated row
intentionally carried the route/workflow/pathlet terms. This is useful as a
stress shape, but it is not evidence of lookup selectivity in natural corpora.

## Supports

- Source families are measured separately.
- The runner reports raw bytes, encoded/store bytes, build time, lookup latency,
  candidate reduction, template count, residual bytes, rehydration latency, hash
  correctness, red-line behavior, store/raw amplification, and ordinary deflate.
- The report can identify which family dominates local storage/rebuild pressure.
- The measurement is source-family economics evidence, not source truth.

## Material Limits

- Cannot claim GB/TB readiness.
- Cannot claim private real-history compression.
- Cannot claim natural-dialogue usefulness from this synthetic corpus.
- Cannot close broader scale-layer adoption without large public-safe or
  explicitly opt-in real-history families with more varied cue distribution.
- Cannot claim zstd dictionary performance until a supported zstd backend is
  present and measured.
- Cannot adopt FastCDC or LMDB from this fixture gate; both remain deferred
  until their reopen thresholds are met.
