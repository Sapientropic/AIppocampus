# Question-Aware Public Shadow Fixture - 2026-06-10

This evidence slice records a public/source-replayable #248 question-aware
shadow benchmark. It complements the 2026-06-08 private selected-registry
review by using checked-in public-safe cases that another agent can inspect
without private clean-source access.

The fixture lives at
`benchmark_corpus/question_aware_public_shadow/fixture.json`. The generated
machine-readable report lives at
`docs/evidence/question/question-aware-public-shadow-2026-06-10.json`.

## Commands

```powershell
python benchmarks\aippocampus\benchmark_question_aware_real_history.py --public-shadow --json --output docs\evidence\question\question-aware-public-shadow-2026-06-10.json
python -m pytest tests\aippocampus\test_benchmark_question_aware_real_history.py -q
python -m ruff check benchmarks\aippocampus\benchmark_question_aware_real_history.py tests\aippocampus\test_benchmark_question_aware_real_history.py
```

## Input Surface

- Public shadow cases: 4
- Negative controls: 2, evaluated through the deterministic question-extraction
  gate
- Source families: 2 public VCS-style cases and 2 public agent-trajectory cases
- Selected source-backed rows: 1 `question_candidate`, 1 `frontier_marker`, 1
  `question_link`, and 1 `theme_candidate`
- Raw source text emitted: no
- Raw answer text emitted: no
- Raw source refs or local paths emitted: no

## Results

- Status: `public_shadow_ready`
- Claim level: `public_replayable_shadow_fixture`
- Source-ref fidelity rate: 1.0
- Plain term coverage: 1.0
- Question-blind term coverage: 0.25
- Question-aware term coverage: 1.0
- Question-aware over question-blind delta: 0.75
- Answer-usefulness delta: 1.0
- Manual-query-reduction delta: 1.5
- Question-aware wrong-hint rate: 0.0
- Negative controls passed: 2/2 (`noise` and `code_heavy` skip reasons)

Threshold readout from the selected calibration fixture:

- Fixed low similarity threshold (`0.52`): false merge 1/3 = 0.333333
- Static strong threshold (`0.80`): false split 1/2 = 0.5
- Dynamic six-axis threshold: false merge 0/3 and false split 0/2

## Decision

This retires the public-replayable shadow-case gap added to #248 on
2026-06-08. It shows a checked-in source-replayable path for question-aware
source reopen, answer-review deltas, adaptive-threshold readout, and
noise/code negative controls.

Do not close #248 from this slice. The benchmark still uses selected public
fixtures, not a broad public corpus, private-history answer-quality cohort, or
live user-visible trial. It also does not decide default question-index or
vector prefilter adoption.

## Can Claim

- Public shadow cases can exercise question-aware source reopen without
  emitting raw source text, raw answer text, raw refs, local paths, or fixture
  paths.
- Question-aware fields improved selected source-reopened answer usefulness
  over the shadow plain baseline on this fixture.
- The public shadow report records static-threshold and adaptive-threshold
  behavior so regressions do not silently collapse back to fixed-threshold
  matching.
- The fixture includes multilingual/noise and code negative controls.

## Cannot Claim

- Private real-history answer quality.
- Live user-visible recall improvement.
- Broad question-tracking quality.
- Theme-resonance calibration.
- Default prefilter adoption.
- Source truth from question, theme, or frontier rows.
- #248 closeout.
