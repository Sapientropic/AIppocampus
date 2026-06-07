# Question-Aware No-Lift Diagnostic - 2026-06-08

This evidence slice records a maintainer-private #248 question-aware recall
diagnostic run from 2026-06-08 local time. It is sanitized aggregate evidence
only. The local review rows stayed under `.tmp/` and no raw source text, answer
text, source refs, local paths, registry paths, or message ids are committed.

## Commands

```powershell
python benchmarks\aippocampus\benchmark_question_aware_real_history.py --json --max-packs 2 --min-packs 1 --answer-quality-review .tmp\question-aware-answer-quality-review-2026-06-08.jsonl --output docs\evidence\question\question-aware-answer-quality-2026-06-08.json
python -m aippocampus_runtime.subconscious.theme_emergence --no-write --json
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
- Question-blind term coverage: 0.7143
- Question-aware term coverage: 1.0
- Term-coverage delta: 0.0
- Question-aware over question-blind delta: 0.2857
- Portrait token ratio: 3.1481
- Question-aware / question-blind token ratio: 4.2518
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

## Root Cause

This run cannot prove that question-aware recall has no value. It explains why
the original plain-baseline comparison did not show lift:

- The plain baseline was not a true no-question-aware baseline. It used the
  same selected question/frontier/link/theme rows and received
  `question_short`, `linked_question_short`, `theme_short`, concepts, and
  hashed source-ref routes.
- Expected terms were derived from those same rows, so plain coverage reached a
  1.0 ceiling before question-aware structure could show positive term lift.
- The revised benchmark also reports a question-blind same-row structural
  baseline that omits question/theme labels. On the same selected slice,
  question-blind term coverage was 0.7143 while question-aware term coverage was
  1.0, so question-aware fields added 0.2857 structural route-term coverage
  over that label-blind baseline.
- The selected registry slice was too thin for theme-aware behavior: only 1
  `question_link` and 0 `theme_candidate` rows were present.
- `theme_emergence` reported `not_enough_question_links` with 1 link and a
  minimum of 3.

## Decision

Do not close #248 from this evidence. It proves the sanitized reporting path
and resolves the first evaluation-design problem, but it does not prove
user-visible answer lift or no-lift. The question-blind structural baseline is
fairer than the contaminated plain baseline, but it still uses the same selected
rows and is not a true no-question-aware retrieval or generated-answer arm.

The runtime should also not block ordinary borderline question links on human
confirmation by default. Borderline links should materialize as low-confidence,
source-backed navigation with audit metadata; explicit confirmation remains a
calibration path, not the default path to usability.

## Can Claim

- Selected private question/frontier/link rows can form sanitized source-backed
  packs.
- The opt-in answer-quality review path records paired source-reopened review
  without emitting raw private text, source text, raw refs, message ids, local
  paths, or registry paths.
- The original 2026-06-08 plain-baseline no-lift result is explained by
  baseline contamination and a thin upstream question/theme layer.
- Question-aware fields added structural route-term coverage over the
  question-blind same-row baseline on this selected slice.

## Cannot Claim

- Full private-history answer quality.
- Live model behavioral equivalence.
- User-visible recall improvement without a release trial.
- Default question-index/vector prefilter safety.
- Theme-resonance calibration; this registry slice contained no theme
  candidates.
- True no-question-aware retrieval baseline or generated-answer lift.
- #248 closeout.
