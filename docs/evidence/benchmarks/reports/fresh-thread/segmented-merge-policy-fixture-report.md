# Segmented Merge Policy Fixture Report

Status: deterministic public-safe calibration fixture for #375 and #853.

This report explains why the current `SEGMENT_MERGE_POLICY` defaults remain
acceptable for the first segmented-search merge layer. It is a calibration
smoke, not product-quality proof. Real recall claims still belong to Track B
source-evidence retrieval, private/public corpus runs, and dated readiness
evidence.

## Sources

- Issues: <https://github.com/Sapientropic/AIppocampus/issues/375>,
  <https://github.com/Sapientropic/AIppocampus/issues/853>
- Runner: [`benchmarks/aippocampus/benchmark_segmented_merge_policy.py`](../../../../../benchmarks/aippocampus/benchmark_segmented_merge_policy.py)
- Fixture: [`benchmark_corpus/segmented_merge_policy/fixture.json`](../../../../../benchmark_corpus/segmented_merge_policy/fixture.json)
- Policy owner: [`skills/aippocampus/scripts/aippocampus_runtime/recall/scoring_policy.py`](../../../../../skills/aippocampus/scripts/aippocampus_runtime/recall/scoring_policy.py)
- Merge owner: [`skills/aippocampus/scripts/aippocampus_runtime/recall/segment_search.py`](../../../../../skills/aippocampus/scripts/aippocampus_runtime/recall/segment_search.py)
- GB-scale boundary: [`docs/architecture/ops/gb-scale-roadmap.md`](../../../../architecture/ops/gb-scale-roadmap.md)
- Retrieval contract: [`skills/aippocampus/references/retrieval-and-storage.md`](../../../../../skills/aippocampus/references/retrieval-and-storage.md)

## Fixture Scope

The fixture is synthetic and public-safe. It uses stable synthetic source refs
and sentinel snippet text that the runner must not emit. The five required
patterns are:

| Pattern | What It Checks |
| --- | --- |
| `cross_segment_diversity` | A dense recap segment should not crowd out a distant original source. |
| `adjacent_turn_pairing` | A user cue and the resolving final answer should both survive the merge. |
| `duplicate_nearby_recap_suppression` | Nearby duplicate recap rows should not fill the whole top-k. |
| `stable_source_join_dedupe` | Overlapped segments pointing to the same stable source row should keep the higher-ranked hit and surface a dedupe count. |
| `stale_superseded_currentness` | A newer final answer can outrank an older stronger lexical hit. |

## Current Result

Command:

```powershell
python benchmarks\aippocampus\benchmark_segmented_merge_policy.py --json
```

Latest local result on 2026-06-07:

| Metric | Value |
| --- | ---: |
| Cases | 5 |
| Passed cases | 5 |
| Target hit rate | 100% |
| Source diversity pass rate | 100% |
| Adjacent-turn pairing success rate | 100% |
| Duplicate-nearby suppression success rate | 100% |
| Source-key dedupe cases | 1 |
| Source-key dedupe count | 1 |
| Stale/superseded false promotions | 0 |

Decision: keep the current default weights and add stable source-identity
dedupe ahead of the existing diversity policy. No policy values changed in this
slice.

## Sensitivity

The runner compares the default policy against two diagnostic alternatives:

| Alternative | Regressed Cases | Interpretation |
| --- | ---: | --- |
| `no_diversity_penalties` | 2 | Same-segment and nearby-line penalties are doing useful work for cross-segment diversity and duplicate recap suppression. |
| `no_final_answer_bonus` | 2 | The final-answer bonus is doing useful work for adjacent cue/answer pairing and superseded-currentness. |

These alternatives are not proposed policies. They exist so future weight
changes have a small regression contract before touching user-visible ranking.

## Cannot Claim

This fixture does not prove:

- broad long-thread recall quality;
- natural user-query quality;
- private-history segment merge quality;
- source-evidence retrieval quality;
- turn-aware segment-boundary quality;
- SOTA or external-baseline superiority.

If future real recall failures require changing `SEGMENT_MERGE_POLICY`, update
the fixture/report with before/after metrics and run the source-backed retrieval
tests that own the affected surface.
