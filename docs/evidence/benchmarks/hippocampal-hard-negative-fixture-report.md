# Hippocampal Hard-Negative Fixture Report

Status: implemented public-safe production-like synthetic diagnostic for
GitHub #244 and #1041, with contract controls kept visible.

This report records the narrow evidence boundary for
`benchmarks/aippocampus/benchmark_hippocampal_hard_negatives.py`. The runner
does not evaluate a live model. It validates a public-safe synthetic fixture,
scores a guarded production-like output slice, and keeps deterministic contract
controls for H1/H2 hard negatives: honest uncertainty must score far above
confident wrong-source evidence.

## What It Covers

- `near_neighbor_lure`: a semantically close distractor must not become target
  evidence.
- `said_but_unsupported`: a mentioned hypothesis must not become accepted fact.
- `superseded_currentness_trap`: an old source remains historical terrain, not
  current evidence after supersession.
- `surface_paraphrase_lure`: surface-nearest paraphrases must not bypass source
  reopen.

Fixture rows include target refs, distractor refs, expected decision,
acceptable scent/skip behavior, forbidden claims, currentness labels,
supersession labels, and scorer input boundaries.

The 2026-06-09 fixture contains 12 cases: 3 cases for each required family.
`production_outputs` contains one guarded/reopen-shaped output per case.
`scorer_examples` remains a 16-example contract-control slice that deliberately
includes wrong-source, stale-current, unsupported-as-fact, and confabulation
examples so the scorer taxonomy stays exercised.

## Scoring Contract

The report distinguishes seven outcomes:

- `correct_evidence`
- `honest_scent`
- `honest_skip`
- `wrong_source_evidence`
- `stale_as_current`
- `unsupported_as_fact`
- `confabulation`

The discipline score is asymmetric: `wrong_source_evidence`,
`stale_as_current`, `unsupported_as_fact`, and `confabulation` are penalized
much more heavily than `honest_scent` or `honest_skip`.

## 2026-06-09 Production-Like Slice

Command:

```powershell
python benchmarks\aippocampus\benchmark_hippocampal_hard_negatives.py --json
```

Main production-like slice:

| Metric | Value |
| --- | ---: |
| Fixture cases | 12 |
| Cases per family | 3 |
| Scored production outputs | 12 |
| Major failure count | 0 |
| Wrong-source evidence count | 0 |
| Stale-as-current count | 0 |
| Unsupported-as-fact count | 0 |
| Confabulation count | 0 |
| Honest scent / skip count | 4 |
| Evidence source-reopen count | 8 |
| Evidence source-reopen rate | 1.000 |

Contract-control slice:

| Metric | Value |
| --- | ---: |
| Scored contract examples | 16 |
| Major failure examples | 7 |
| Wrong-source examples | 2 |
| Stale-as-current examples | 2 |
| Unsupported-as-fact examples | 2 |
| Confabulation examples | 1 |
| Honest uncertainty examples | 5 |

The production-like slice is public synthetic and source-ref shaped. It is
beyond the original 4-case frozen contract smoke because it covers every family
with multiple cases and reports source-reopen behavior, but it is still not a
live model, semantic retriever, or private-history quality measurement.

## Command

```powershell
python benchmarks\aippocampus\benchmark_hippocampal_hard_negatives.py --json
python -m unittest tests.aippocampus.test_benchmark_hippocampal_hard_negatives
```

## Canonical Files

- Runner: `benchmarks/aippocampus/benchmark_hippocampal_hard_negatives.py`
- Fixture: `benchmark_corpus/hippocampal_hard_negatives/fixture.json`
- Mirror tests:
  `tests/aippocampus/test_benchmark_hippocampal_hard_negatives.py`
- Methodology owner:
  `docs/evidence/benchmarks/hippocampal-recall-plan.md`

## Cannot Claim

- real-history H1/H2 recall-discrimination quality
- live model or semantic-retriever quality
- the full 50-scene / 350-case hippocampal P1 matrix
- cross-system benchmark superiority
- broad production reliability outside the 12-case public synthetic slice
