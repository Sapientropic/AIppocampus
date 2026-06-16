# Multimodal NIAH Evidence-Pool Report

Status: public-safe deterministic contract smoke for GitHub #533 and the #528
multimodal source-backed recall track.

This is a NIAH-style evidence-pool evaluation. It reuses the public-safe
multimodal corpus fixture from #531, but retrieval is intentionally removed
from the measurement: each question receives a fixed evidence pool containing
all ground-truth source ids plus distractors.

## Fixture Shape

The fixture lives at
[`../../../../../benchmark_corpus/multimodal_niah_evidence_pool/fixture.json`](../../../../../benchmark_corpus/multimodal_niah_evidence_pool/fixture.json).

It points back to
[`../../../../../benchmark_corpus/public_multimodal_corpus/fixture.json`](../../../../../benchmark_corpus/public_multimodal_corpus/fixture.json)
for the source ids, modalities, hashes, and reopenable anchors.

Each NIAH row records:

- the referenced corpus QA row;
- `ground_truth_evidence_ids`;
- distractor evidence ids;
- a deterministic shuffled `pool_evidence_ids` list;
- optional `input_selected_evidence_ids` and `input_cited_source_anchor_ids`
  when the fixture preserves a stale or weaker initial answerer choice for
  conflict-resolution repair;
- optional `observed_answerer_replay_cases` for fixed-reader replay over
  source selection, citation, conflict repair, prompt leakage, retrieval
  boundary, and abstention behavior;
- sanitized conflict-resolution decision fields such as `selection_decision`,
  `currentness_decision`, `selection_reason_codes`, and
  `needs_source_reopen`;
- sanitized scoring-state fields for the deterministic contract smoke.

The agent-visible prompt boundary excludes ground-truth ids, expected answers,
answer correctness flags, failure-mode labels, and hidden scoring metadata.

## Query Shapes

| Query shape | What it tests |
| --- | --- |
| Personalized reference | The right image source must be selected from a small pool with nearby media/text distractors. |
| Conflict resolution | The correct final-bill source is in the pool; stale input choices must be repaired only when source metadata supports currentness, otherwise the answer should request source reopen. |
| Cross-modal join | Calendar/location and receipt sources must both be selected from a medium pool. |
| Unsupported detail | Related visual evidence is present, but the requested detail is unsupported, so the answer abstains. |

## Commands

```powershell
python benchmarks\aippocampus\benchmark_multimodal_niah_evidence_pool.py --json
python benchmarks\aippocampus\benchmark_multimodal_niah_evidence_pool.py --source-reopen-mode deterministic_fixture --json
python benchmarks\aippocampus\benchmark_multimodal_niah_evidence_pool.py --answerer-replay --json
```

Latest local deterministic replay run on 2026-06-17:

- `status=fixture_contract_scored`
- `ok=true`
- `niah_observed_answerer_case_count=6`
- `deterministic_fixture_only_case_count=4`
- `pool_ground_truth_coverage_rate=1.0`
- `answer_correctness=1.0`
- `source_selection_accuracy=1.0`
- `source_anchor_citation_accuracy=1.0`
- `unsupported_claim_rate=0.0`
- `abstention_accuracy=1.0`
- `stale_or_conflicting_distractor_selection_rate=0.0`
- `ambiguous_currentness_reopen_or_abstain_rate=1.0`
- `prompt_ground_truth_leak_count=0`
- `retrieval_quality_claimed=false`
- `provider_unavailable_blocker_count=0`
- `raw_media_bytes_public_reported_count=0`
- `absolute_path_leak_count=0`
- `input_stale_or_conflicting_distractor_selection_count=1`
- `current_source_selected_count=1`
- `needs_source_reopen_count=0`

The conflict row preserves the old stale input choice as
`input_selected_evidence_ids`, then runs a deterministic source-metadata
decision step. In the final-bill case the current source is identifiable by
captured time plus authority metadata, so the selected source becomes the final
bill and the stale/conflicting distractor selection count drops to 0. A
regression negative control covers the opposite boundary: when currentness is
ambiguous, the decision step emits `needs_source_reopen` instead of guessing.
The observed/fixed-reader replay keeps that ambiguity as a scored answerer case
and treats reopen or abstention as the correct behavior, while prompt leakage
and retrieval-quality claims remain guard metrics instead of answer-quality
inputs.

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
- observed/fixed-reader replay covers ground-truth-present selection,
  stale-conflict repair, ambiguous-currentness reopen, unsupported visual
  detail abstention, prompt leakage guard, and retrieval-not-scored guard;
- conflict-resolution decisions expose the old input selection, final selected
  source ids, currentness reason codes, and `needs_source_reopen` counts;
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
