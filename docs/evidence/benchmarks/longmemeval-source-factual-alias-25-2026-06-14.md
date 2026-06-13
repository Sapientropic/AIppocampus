# LongMemEval Source Factual Alias 25Q

Role: evidence.

This is a bounded no-provider slice for the source-side factual alias contract
from #1424/#1425/#1426. It checks whether the new local factual alias artifact
is visible to the source-semantic cache path while preserving source-reopen and
public-report boundaries.

Command:

```powershell
python benchmarks\aippocampus\benchmark_longmemeval.py --split longmemeval-v1-small --questions 25 --min-questions 25 --top-k 10 --line-reranker source_semantic_cache --line-reranker-workers 4 --standard-cache-dir benchmark_corpus\.cache\standard-public-cases --partial-output benchmark_corpus\reports\longmemeval-v1-small-source-factual-alias-25-2026-06-14.partial.json --output docs\evidence\benchmarks\longmemeval-source-factual-alias-25-2026-06-14.json
```

The committed JSON report is
[`longmemeval-source-factual-alias-25-2026-06-14.json`](longmemeval-source-factual-alias-25-2026-06-14.json).
Local partial JSON stays under ignored `benchmark_corpus/reports/`.

## Result

Status: `retrieval_sufficient`.

| Metric | Value |
| --- | ---: |
| Questions | 25 |
| Baseline evidence top-10 | 0.92 |
| Source-semantic cache search evidence top-10 | 0.96 |
| Source-semantic cache only evidence top-10 | 0.96 |
| Fused/reranked evidence top-10 | 1.00 |
| Line-reranker candidate evidence coverage | 1.00 |
| Average candidate count | 96.00 |
| Factual-alias case count | 25 |
| Factual-alias average line count | 218.96 |
| Factual-alias evidence coverage rate | 0.36 |
| Factual-alias candidate evidence coverage rate | 0.36 |
| Gold candidate factual-alias query-overlap cases | 2 |
| Factual-alias candidate lift top-10 | 0 |
| Factual-alias fused lift top-10 | 0 |
| Source-semantic fused regressions top-10 | 0 |
| Provider calls | 0 |
| Hot-query provider calls | 0 |
| Cache policy | `aippocampus-source-worker-surface-cache-v6` |
| Builder id | `aippocampus-working-memory-factual-surface-v3` |

The public privacy boundary stayed intact:

- raw text emitted: `false`
- snippets emitted: `false`
- absolute paths emitted: `false`
- case ids are hashed: `true`

## Interpretation

The synthetic comparable fixture
`test_factual_alias_hot_path_lifts_candidate_and_fused_topk_without_window_growth`
proves the hot path can lift a source candidate when baseline FTS misses a
paraphrased factual relation. It uses no provider calls, keeps `context_radius=0`,
and reports the lift through the same sanitized aggregate fields used by the
public benchmark.

This 25Q public LongMemEval-S slice shows the source-semantic cache path reports
candidate coverage, factual-alias coverage, fused top-k, regressions, latency,
cache behavior, and provider-call counts. Fused evidence top-10 improved over
baseline on this bounded slice, with no fused top-10 regressions.

It does not prove a broad factual-alias lift. The factual alias query-overlap
signal is present but sparse on the first 25 public cases: alias-specific
candidate lift and fused lift are both `0`. So #1323-style 100Q/500Q repair
still needs broader measurement and likely richer source-local extraction
before promotion.

Cannot claim:

- answer-generation quality;
- official LongMemEval score;
- LongMemEval-V2 behavior;
- broad source-side factual recall closure;
- 100Q/500Q LongMemEval factual-alias lift;
- private-history quality.
