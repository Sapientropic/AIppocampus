# LongMemEval Source Factual Alias 25Q

Role: evidence.

This is a bounded no-provider slice for the source-side factual alias contract
from #1424/#1425/#1426. It checks whether the new local factual alias artifact
is visible to the source-semantic cache path while preserving source-reopen and
public-report boundaries.

Command:

```powershell
python benchmarks\aippocampus\benchmark_longmemeval.py --split longmemeval-v1-small --questions 25 --min-questions 25 --top-k 10 --line-reranker source_semantic_cache --line-reranker-workers 4 --standard-cache-dir benchmark_corpus\.cache\standard-public-cases --partial-output benchmark_corpus\reports\longmemeval-v1-small-source-factual-alias-25-2026-06-14.partial.json --output benchmark_corpus\reports\longmemeval-v1-small-source-factual-alias-25-2026-06-14.json
```

Local generated JSON stays under ignored `benchmark_corpus/reports/`.

## Result

Status: `retrieval_sufficient`.

| Metric | Value |
| --- | ---: |
| Questions | 25 |
| Baseline evidence top-10 | 0.92 |
| Source-semantic cache search evidence top-10 | 0.96 |
| Fused/reranked evidence top-10 | 1.00 |
| Factual-alias case count | 25 |
| Factual-alias average line count | 218.96 |
| Factual-alias evidence coverage rate | 0.36 |
| Gold candidate factual-alias query-overlap cases | 2 |
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

The synthetic unit fixture proves the new artifact can lift a source candidate
when baseline FTS misses a paraphrased factual relation. This 25Q public slice
shows the metrics, cache contract, local provider-free path, and public boundary
are now wired into the benchmark report.

This does not yet prove a broad LongMemEval lift. The factual alias query-overlap
signal is present but sparse on the first 25 public cases, so #1323-style
large-slice repair still needs broader measurement and likely richer
source-local extraction before promotion.

Cannot claim:

- answer-generation quality;
- official LongMemEval score;
- LongMemEval-V2 behavior;
- broad source-side factual recall closure;
- private-history quality.

