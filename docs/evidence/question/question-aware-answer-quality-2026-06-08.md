# Question-Aware Answer-Quality Review - 2026-06-08

This evidence slice records a maintainer-private #248 question-aware recall
review run from 2026-06-08 local time. It is a sanitized aggregate record only.
The local review rows stayed under `.tmp/` and contain no raw source text,
answer text, source refs, local paths, or registry paths.

## Commands

```powershell
python benchmarks\aippocampus\benchmark_question_aware_real_history.py --json --max-packs 2 --min-packs 1 --answer-quality-review .tmp\question-aware-answer-quality-review-2026-06-08.jsonl --output docs\evidence\question\question-aware-answer-quality-2026-06-08.json
```

## Input Surface

- Subconscious job rows: 698
- Eligible source-backed rows: 43
- Selected packs: 2
- Selected seed kinds: 17 frontier markers, 25 question candidates, 1 question
  link
- Theme candidates in this registry slice: 0
- Private text emitted: no

## Results

- Status: `structural_proxy_ready_but_lookup_required`
- Source-ref fidelity rate: 1.0
- Plain term coverage: 1.0
- Question-aware term coverage: 1.0
- Term-coverage delta: 0.0
- Portrait token ratio: 3.1481
- Over-personalization risk count: 0

Source-reopened answer-quality review:

- Review cases: 2
- Complete paired comparisons: 2
- Plain baseline answer useful rate: 1.0
- Question-aware source-reopen answer useful rate: 1.0
- Answer-usefulness delta: 0.0
- Plain baseline supported / citation-correct rate: 1.0 / 1.0
- Question-aware supported / citation-correct rate: 1.0 / 1.0
- Question-aware source-reopened rate: 1.0
- Question-aware wrong-hint rate: 0.0
- Mean extra verification-steps delta: 0.0

## Decision

Do not enable a heavier default question-aware prefilter or scaffold from this
evidence. The selected private rows were fully source-backed and public-safe,
but the plain source-derived baseline already covered the reviewed cases, while
the question-aware scaffold was materially longer and showed no usefulness
lift.

The current implementation should keep question/theme/frontier rows as
navigation and review material. Accelerated prefilters or richer scaffolds need
fresh evidence only if a future registry slice shows text-only/source-derived
baseline misses, user-visible answer lift, or a concrete latency/cost win.

## Can Claim

- Selected private question/frontier/link rows can form sanitized source-backed
  packs.
- The opt-in answer-quality review path records paired source-reopened review
  without emitting raw private text, source text, raw refs, message ids, local
  paths, or registry paths.
- On this selected private slice, question-aware source-reopen did not improve
  answer usefulness over the plain source-derived baseline.
- Current default-prefilter adoption should remain disabled.

## Cannot Claim

- Full private-history answer quality.
- Live model behavioral equivalence.
- User-visible recall improvement without a release trial.
- Default question-index/vector prefilter safety.
- Theme-resonance calibration; this registry slice contained no theme
  candidates.
