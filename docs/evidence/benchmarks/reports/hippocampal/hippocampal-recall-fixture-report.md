# Hippocampal Recall Fixture Report

Status: implemented public-safe diagnostic seed for GitHub #229, #230, #231,
#233, #237, the first #239 structure/time retrieval slice, and the 2026-06-09
#1040 D5/D6 gated diagnostic.

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
- Adapter-contract arms for #237: `full_query`, `keyword_only`,
  `baseline_rag`, `closed_book`, `overactive_all_evidence`, and
  `random_retrieval`, each with per-arm D/I, calibration, source-reopen, and
  cost/latency report views.
- H5 before/after diagnostic controls for #233: frozen H1/H2 labels and source
  state, `keyword_only` as the before arm, and `no_consolidation`,
  `aippocampus_dream_consolidation`, `random_consolidation`, and
  `simple_summary_consolidation` as after arms. The report exposes score
  deltas, false forgetting, overgeneralization, stale-as-current deltas,
  wrong-twin deltas, new association discovery, and cost per improvement.
- External adapter candidates for Mem0, Zep/Graphiti, Letta, and LangMem are
  reported as opt-in diagnostics when dependency/configuration is missing; the
  default public benchmark does not require external credentials or paid
  services.
- Report views by degradation, by interference, D/I matrix, aggregate metrics,
  and calibration categories.
- Cross-system comparison rows for #238, exposed in the benchmark JSON as
  `cross_system_comparison` and summarized in
  [`hippocampal-cross-system-comparison-2026-06-04.md`](hippocampal-cross-system-comparison-2026-06-04.md).
- First D5/D6 index/search slice for #239: `source_index.sqlite` now includes a
  deterministic `message_features` sidecar, and hybrid retrieval can expose
  separate text, structure, and temporal diagnostics when explicit cues are
  supplied.
- D5/D6 gated diagnostic for #1040: the checked-in fixture now has 16 cases,
  including 3 D5 structure-only cases and 3 D6 time-window cases. The
  `d5_d6_gate` readout gates only the `full_query` AIppocampus diagnostic arm;
  baseline arms remain comparative and do not determine whether D5/D6 enter
  this narrow gated-diagnostic state.

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

Clean-clone reproduction does not require a private registry, provider
credentials, generated local indexes, or hidden `.aippocampus/` state:

```powershell
python benchmarks\aippocampus\build_hippocampal_fixture.py --json
python benchmarks\aippocampus\benchmark_hippocampal_recall.py --json
python -m unittest tests.aippocampus.test_benchmark_hippocampal_recall
python -m unittest tests.aippocampus.test_recall_structure_time_features
```

The benchmark JSON report exposes `report_schema_version`, `fixture_dataset_id`,
`fixture_schema_version`, `fixture_version`, `fixture_seed`, and a
`reproducibility.clean_clone_command` field so later reports can be compared
without relying on local machine state.

Adapter runs also expose `adapter_contract` and `views_by_arm`. Adapter inputs
hide scoring-only truth labels such as expected decisions, expected source
refs, distractor refs, forbidden claims, truth source, and ambiguity policy, so
local baseline arms cannot score by reading the answer key.

H5 runs expose `h5_consolidation`. This is a deterministic control slice over
the same frozen H1/H2 cases, not a live Dream worker measurement. It records the
prospective-validation shape from the Dream design notes, but it requires later
time-sliced source evidence before any prospective Dream claim can be treated
as supported.

Cross-system rows expose `cross_system_comparison`. Local rows use observed
public-synthetic fixture metrics; semantic-only and external memory-system rows
stay visible as not-implemented or missing-config diagnostics until runnable
adapters exist.

Structure/time retrieval exposes `message_features`, `structure_match_score`,
`structure_signals`, and `temporal_affinity_score` for debugging D5/D6 misses.
These are retrieval diagnostics over source-backed message projections, not
claims that D5/D6 benchmark quality is solved.

## 2026-06-09 D5/D6 Gate

Command:

```powershell
python benchmarks\aippocampus\build_hippocampal_fixture.py --json
python benchmarks\aippocampus\benchmark_hippocampal_recall.py --json
```

Result:

| Field | Value |
| --- | ---: |
| Fixture cases | 16 |
| D5 cases | 3 |
| D6 cases | 3 |
| Gate arm | `full_query` |
| D5 accuracy | 1.000 |
| D6 accuracy | 1.000 |
| Combined D5/D6 accuracy | 1.000 |
| Combined D5/D6 source reopen count | 4 / 6 |
| Combined D5/D6 source reopen rate | 0.666667 |
| Wrong-source / wrong-twin count | 0 |
| Source-reopen failure count | 0 |
| Confabulation count | 0 |
| Gate status | `gated_diagnostic_passed` |

Thresholds:

- D5 and D6 must each have at least 3 public-safe synthetic cases.
- D5 and D6 must each reach accuracy >= 0.8 in the `full_query` diagnostic arm.
- D5 and D6 must each have separation accuracy 1.0.
- Wrong-source / wrong-twin, source-reopen failure, and confabulation counts
  must be 0.

This supersedes the old 12-case D5/D6 readout only for the narrow public
synthetic `full_query` D5/D6 gated diagnostic. It does not supersede the
historical 2026-06-04 cross-system comparison table for baseline arms, H5
controls, external-adapter availability, or broader P1 coverage.

## Canonical Files

- Schema: `benchmarks/aippocampus/families/hippocampal_fixture_schema.py`
- Builder: `benchmarks/aippocampus/builders/build_hippocampal_fixture.py`
- Runner: `benchmarks/aippocampus/benchmark_hippocampal_recall.py`
- Fixture:
  `benchmark_corpus/hippocampal_fixtures/hippocampal_synthetic_v1.jsonl`
- Mirror tests: `tests/aippocampus/test_benchmark_hippocampal_recall.py`
- Methodology owner:
  `docs/evidence/benchmarks/design/hippocampal-recall-plan.md`

## Cannot Claim

- full 50-scene / 350-case P1 quality
- dense independent metrics for every D/I cell
- real-history H1/H2 recall-discrimination quality
- live semantic-retriever or model quality
- D4 quality gates beyond exploratory diagnostic coverage
- bucketed calibration error without calibrated confidence bins
- external memory-system scores or cross-system superiority
- live provider quality from missing-config diagnostic adapters
- user-visible Dream benefit or predictive validity from synthetic H5 deltas
- private real-history consolidation quality
- AIppocampus-specific consolidation lift without live controls
- full D5/D6 recall quality from the public synthetic `full_query` gate
- publication-grade comparison or confidence intervals from the 16-case
  diagnostic seed
