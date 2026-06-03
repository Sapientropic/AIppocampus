# Hippocampal Recall Fixture Report

Status: implemented public-safe diagnostic seed for GitHub #229, #230, and
#231.

This report records the narrow evidence boundary for
`benchmarks/aippocampus/benchmark_hippocampal_recall.py`. The runner validates a
small synthetic JSONL fixture, executes deterministic baseline outputs, and
reports degradation/interference views plus abstention, scent, evidence,
source-reopen, and calibration categories. It does not run a live model or a
private registry.

## What It Covers

- Fixture schema for D0-D6 degradation and I0-I5 interference labels.
- Public-safety metadata, CC0-compatible synthetic text, and source-ref based
  truth labels.
- Validation failures for missing source refs, invalid D/I levels, missing
  ambiguity policy, unsupported truth source, and scorer inputs that would leak
  internal cues.
- Deterministic baseline arms: `full_query`, `keyword_only`, and
  `random_retrieval`.
- Report views by degradation, by interference, D/I matrix, aggregate metrics,
  and calibration categories.

## Scoring Contract

The scorer distinguishes evidence success, scent success, correct skip,
underconfident scent, overconfident evidence, partial scent misses, unsupported
skip, wrong twin selection, source reopen failure, wrong evidence, and
confabulation.

Scent metrics keep the #231 layers separate:

- `scent_hit`: target included without distractor.
- `scent_distractor`: only distractors returned.
- `scent_both`: target and distractor both returned, marked low separation.

Only `scent_hit` contributes to the `scent_precision` numerator.

## Command

```powershell
python benchmarks\aippocampus\build_hippocampal_fixture.py --json
python benchmarks\aippocampus\benchmark_hippocampal_recall.py --json
python -m unittest tests.aippocampus.test_benchmark_hippocampal_recall
```

## Canonical Files

- Schema: `benchmarks/aippocampus/hippocampal_fixture_schema.py`
- Builder: `benchmarks/aippocampus/build_hippocampal_fixture.py`
- Runner: `benchmarks/aippocampus/benchmark_hippocampal_recall.py`
- Fixture:
  `benchmark_corpus/hippocampal_fixtures/hippocampal_synthetic_v1.jsonl`
- Mirror tests: `tests/aippocampus/test_benchmark_hippocampal_recall.py`
- Methodology owner:
  `docs/evidence/benchmarks/hippocampal-recall-plan.md`

## Cannot Claim

- full 50-scene / 350-case P1 quality
- dense independent metrics for every D/I cell
- real-history H1/H2 recall-discrimination quality
- live semantic-retriever or model quality
- D4-D6 quality gates beyond exploratory diagnostic coverage
- bucketed calibration error without calibrated confidence bins
