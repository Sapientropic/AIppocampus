# Hippocampal Cross-System Comparison

Date: 2026-06-04

Source issue: GitHub #238. Parent: GitHub #228.

This dated report is generated from the public-safe diagnostic seed exposed by
`benchmarks/aippocampus/benchmark_hippocampal_recall.py`. It compares current
local benchmark arms on H1 degraded-cue recall, H2 interference/separation,
source reopen, calibration/confabulation, D5/D6 exploratory cells, and H5
before/after consolidation deltas.

This is not a leaderboard. External adapters are visible as missing-config or
not-implemented rows until runnable, licensed, source-backed adapters exist.

## Reproduction

```powershell
python benchmarks\aippocampus\benchmark_hippocampal_recall.py --json
python -m unittest tests.aippocampus.test_benchmark_hippocampal_recall
```

The JSON owner is `cross_system_comparison` in the benchmark report. Current
fixture size is 12 cases, and every D/I cell remains diagnostic-only rather
than publication-grade density.

## Comparison Table

| Row | Comparable | Claim level | H1/H2 N | D0 acc | D1-D6 acc | D5/D6 acc | H2 separation | Source reopen | Confab rate | Overconf rate | H5 score delta | H5 false forgetting | H5 overgeneralization | Status |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| AIppocampus diagnostic | yes | synthetic public result | 12 | 1.000 | 0.700 | 0.500 | 0.833 | 0.917 | 0.000 | 0.000 | 38.15 | 0 | 0 | Uses `full_query` for H1/H2 and fixture-authored `aippocampus_dream_consolidation` for H5. |
| Baseline RAG | yes | synthetic public result | 12 | 0.500 | 0.300 | 0.500 | 0.333 | 1.000 | 0.000 | 0.333 | n/a | n/a | n/a | Source reopen is high, but separation and overconfidence degrade under interference. |
| Keyword-only | yes | synthetic public result | 12 | 0.500 | 0.000 | 0.000 | 0.333 | 1.000 | 0.083 | 0.083 | 0.00 | 0 | 0 | Shows a 0.500 D0-to-degraded drop and no D5/D6 recall in this fixture. |
| Closed-book | yes | synthetic public result | 12 | 0.000 | 0.000 | 0.000 | 0.667 | 0.333 | 0.000 | 0.333 | n/a | n/a | n/a | Cannot substitute for source-backed memory; source reopen success is low. |
| Overactive all-evidence | yes | synthetic public result | 12 | 0.500 | 0.700 | 0.500 | 0.667 | 1.000 | 0.000 | 0.333 | n/a | n/a | n/a | More recall is not automatically better; overconfidence remains visible. |
| Random retrieval | yes | synthetic public result | 12 | 0.500 | 0.100 | 0.000 | 0.917 | 1.000 | 0.000 | 0.000 | -11.00 | 1 | 3 | Floor control exposes false forgetting and overgeneralization in H5. |
| Simple-summary consolidation | diagnostic | synthetic public result | 0 | n/a | n/a | n/a | n/a | n/a | n/a | n/a | 29.15 | 0 | 3 | H5-only control; it can improve score while still overgeneralizing. |
| Semantic-only | no | diagnostic not available | 0 | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | Adapter not implemented. |
| Mem0 | no | diagnostic missing configuration | 0 | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | Missing-config diagnostic slot only. |
| Zep / Graphiti | no | diagnostic missing configuration | 0 | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | Missing-config diagnostic slot only. |
| Letta | no | diagnostic missing configuration | 0 | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | Missing-config diagnostic slot only. |
| LangMem | no | diagnostic missing configuration | 0 | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | Missing-config diagnostic slot only. |

## Observed Diagnostic Drops

- Keyword-only drops from 0.500 D0 accuracy to 0.000 on D1-D6 and 0.000 on
  D5/D6, so degraded cues and structure/time cells are not covered by surface
  matching.
- Baseline RAG keeps source reopen at 1.000 but has 0.333 H2 separation and
  0.333 overconfidence, showing that retrieval can still fail the
  discrimination contract.
- Random H5 consolidation has a -11.00 score delta with one false-forgetting
  case and three overgeneralization cases.
- Simple-summary consolidation improves aggregate score in this synthetic seed
  but still produces three overgeneralization cases, so it is not evidence of
  safe consolidation.

## Claim Boundary

Can claim:

- first dated, row-per-arm H1/H2/H5 diagnostic comparison table;
- missing external adapters are explicit rather than hidden;
- current synthetic fixture exposes degraded-cue, interference, source-reopen,
  overconfidence, false-forgetting, and overgeneralization failure modes.

Cannot claim:

- external memory-system scores or product superiority;
- industry-hardest benchmark status;
- publication-grade confidence intervals from a 12-case diagnostic seed;
- private real-history quality;
- user-visible Dream or consolidation benefit.
