# Multimodal NIAH Evidence-Pool Report

Status: public-safe deterministic contract smoke for GitHub #533 and the #528
multimodal source-backed recall track.

This is a NIAH-style evidence-pool evaluation. It reuses the public-safe
multimodal corpus fixture from #531, but retrieval is intentionally removed
from the measurement: each question receives a fixed evidence pool containing
all ground-truth source ids plus distractors.

## Fixture Shape

The fixture lives at
[`../../../benchmark_corpus/multimodal_niah_evidence_pool/fixture.json`](../../../benchmark_corpus/multimodal_niah_evidence_pool/fixture.json).

It points back to
[`../../../benchmark_corpus/public_multimodal_corpus/fixture.json`](../../../benchmark_corpus/public_multimodal_corpus/fixture.json)
for the source ids, modalities, hashes, and reopenable anchors.

Each NIAH row records:

- the referenced corpus QA row;
- `ground_truth_evidence_ids`;
- distractor evidence ids;
- a deterministic shuffled `pool_evidence_ids` list;
- sanitized scoring-state fields for the deterministic contract smoke.

The agent-visible prompt boundary excludes ground-truth ids, expected answers,
answer correctness flags, failure-mode labels, and hidden scoring metadata.

## Query Shapes

| Query shape | What it tests |
| --- | --- |
| Personalized reference | The right image source must be selected from a small pool with nearby media/text distractors. |
| Conflict resolution | The correct final-bill source is in the pool, but the fixture includes a deliberate stale-source failure. |
| Cross-modal join | Calendar/location and receipt sources must both be selected from a medium pool. |
| Unsupported detail | Related visual evidence is present, but the requested detail is unsupported, so the answer abstains. |

## Commands

```powershell
python benchmarks\aippocampus\benchmark_multimodal_niah_evidence_pool.py --json
python benchmarks\aippocampus\benchmark_multimodal_niah_evidence_pool.py --source-reopen-mode deterministic_fixture --json
```

Latest local deterministic run on 2026-06-03:

- `status=fixture_contract_scored`
- `ok=true`
- `pool_ground_truth_coverage_rate=1.0`
- `answer_correctness=0.75`
- `source_selection_accuracy=0.75`
- `source_anchor_citation_accuracy=0.75`
- `unsupported_claim_rate=0.0`
- `abstention_accuracy=1.0`
- `stale_or_conflicting_distractor_selection_rate=1.0`

The non-perfect answer/source-selection metrics are intentional. The fixture
contains one expected failure where the correct final-bill source is present in
the pool, but the deterministic answerer selects the stale conflicting source.
That proves this slice catches reasoning/selection failures, not only missing
retrieval.

This is a small-N contract smoke over four synthetic QA rows with pool sizes
3, 4, and 5. Treat the Wilson intervals in the JSON report as uncertainty
metadata, not population-quality evidence.

## Claim Boundary

Can claim:

- the public-safe fixture encodes the #533 NIAH-style evidence-pool contract;
- every fixed pool contains all ground-truth evidence ids plus distractors;
- pool construction is deterministic and reproducible;
- reports separate answer correctness, source selection, source-anchor
  citation, unsupported claims, abstention, and stale/conflicting distractor
  selection;
- deterministic source-reopen mode verifies original source anchors without
  calling a live provider.

Cannot claim:

- retrieval quality;
- ATM-Bench Hard support or score;
- live vision-model answer quality;
- raw-media model quality;
- conversational media-upload recall;
- product privacy behavior for local photo libraries, disks, cloud drives,
  calendars, or email boxes;
- background scanning consent semantics;
- captions, OCR, or tags as source truth.

## Privacy Boundary

Default reports emit sanitized ids, hashes, pool ids, source-anchor ids, and
metrics only. They do not emit raw questions, raw answers, raw fixture text,
raw media bytes, absolute local paths, or provider prompts. The deterministic
source-reopen mode only checks source-anchor reopenability; it does not call an
external model.
