# Multimodal Corpus Fixture Report

Status: public-safe deterministic contract smoke for GitHub #531 and the #528
multimodal source-backed recall track.

This is an ATM-Bench-inspired corpus-style fixture. It is not an ATM-Bench Hard
adapter, not a benchmark score, and not a conversational media-upload recall
benchmark.

## Fixture Shape

The fixture lives at
[`../../../benchmark_corpus/public_multimodal_corpus/fixture.json`](../../../benchmark_corpus/public_multimodal_corpus/fixture.json).

It contains six synthetic public sources across:

- image;
- video frame;
- email/message;
- receipt;
- invoice/final bill;
- calendar/location metadata.

Each original source declares a stable id, content hash, timestamp, origin
policy, privacy class, source owner, license/access policy, provenance chain,
and reopenable source anchor. Derived artifacts include captions, OCR, object
tags, thumbnail/embedding hints, and schema rows. They carry parent source,
anchor, provider route, confidence, and creation time.

Derived artifacts are navigation only. They can route retrieval, but they are
not source truth.

## Query Shapes

The deterministic smoke covers four corpus-style multimodal retrieval cases:

| Query shape | What it tests |
| --- | --- |
| Personalized reference | A source-backed label resolves to the right image/media source. |
| Conflict resolution | An earlier estimate and later final bill disagree; the later stronger source wins. |
| Cross-modal join | Calendar/location context and a receipt/image-like source must join by time/place/entity. |
| Unsupported detail | Related media exists, but the asked visual detail is unsupported, so the answer abstains. |

## Commands

```powershell
python benchmarks\aippocampus\benchmark_multimodal_corpus_retrieval.py --json
python benchmarks\aippocampus\benchmark_multimodal_corpus_retrieval.py --raw-media-mode deterministic_fixture --json
```

Latest local deterministic run on 2026-06-03:

- `status=fixture_contract_scored`
- `ok=true`
- `retrieval_recall_at_3=1.0`
- `source_reopen_success_rate=1.0`
- `unsupported_visual_claim_rate=0.0`
- `stale_or_weaker_source_selected_rate=0.0`
- `cross_modal_join_success_rate=1.0`
- `abstention_accuracy=1.0`

This is a small-N contract smoke over four synthetic QA rows. Treat the Wilson
intervals in the JSON report as uncertainty metadata, not population-quality
evidence.

## Claim Boundary

Can claim:

- the public-safe fixture encodes the #531 corpus-style multimodal retrieval
  contract;
- derived captions/OCR/tags can route to reopenable original source anchors in
  this deterministic fixture;
- the report includes the required retrieval, source-reopen, unsupported-claim,
  stale/weaker-source, cross-modal join, and abstention metrics.

Cannot claim:

- ATM-Bench Hard support or score;
- live vision-model answer quality;
- conversational media-upload recall;
- product privacy behavior for local photo libraries, disks, cloud drives,
  calendars, or email boxes;
- background scanning consent semantics;
- face-recognition identity graph behavior;
- captions, OCR, or tags as source truth.

## Privacy Boundary

Default reports emit sanitized ids, hashes, anchors, and metrics only. They do
not emit raw fixture text, raw captions/OCR text, raw media bytes, absolute
local paths, or provider prompts. The deterministic raw-media mode only checks
source-anchor reopenability; it does not call an external model.
