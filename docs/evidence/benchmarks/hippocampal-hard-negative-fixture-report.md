# Hippocampal Hard-Negative Fixture Report

Status: implemented public-safe contract-smoke fixture for GitHub #244.

This report records the narrow evidence boundary for
`benchmarks/aippocampus/benchmark_hippocampal_hard_negatives.py`. The runner
does not evaluate a live model. It validates a frozen synthetic fixture and a
deterministic scoring contract for H1/H2 hard negatives: honest uncertainty
must score far above confident wrong-source evidence.

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
