# LongMemEval Source Factual Alias 500Q

Role: benchmark closeout evidence.

This is the 500-question public LongMemEval-S replay for the source-side
factual alias contract. It exists to decide the bounded #1323/#1327/#1424
owner questions after the 25Q slice proved the mechanics but was too small to
close broad owner wording.

Command:

```powershell
python benchmarks\aippocampus\benchmark_longmemeval.py --split longmemeval-v1-small --questions 500 --min-questions 500 --top-k 10 --line-reranker source_semantic_cache --line-reranker-workers 4 --standard-cache-dir benchmark_corpus\.cache\standard-public-cases --progress-every 25 --partial-output benchmark_corpus\reports\longmemeval-v1-small-source-factual-alias-500-2026-06-14.partial.json --output docs\evidence\benchmarks\reports\longmemeval\longmemeval-source-factual-alias-500-2026-06-14.json
```

The committed JSON report is
[`longmemeval-source-factual-alias-500-2026-06-14.json`](longmemeval-source-factual-alias-500-2026-06-14.json).
Local partial/stdout/stderr files stay under ignored `benchmark_corpus/reports/`.

## Result

Status: `retrieval_sufficient`.

| Metric | Value |
| --- | ---: |
| Questions | 500 |
| Evidence-line cases | 479 |
| Baseline session R@10 | 479/500 = 0.9580 |
| Baseline evidence-line R@10 | 408/479 = 0.8518 |
| Context-visible evidence R@10 | 452/479 = 0.9436 |
| Source-semantic cache search evidence R@10 | 387/479 = 0.8079 |
| Source-semantic cache only evidence R@10 | 394/479 = 0.8225 |
| Fused/reranked evidence R@10 | 422/479 = 0.8810 |
| Fused/reranked evidence MRR | 0.6744 |
| Reranker candidate evidence coverage | 463/479 = 0.9666 |
| Previous lexical candidate evidence coverage | 455/479 = 0.9499 |
| Average candidate count | 96.00 |
| Fused miss count | 57 |
| Candidate-missing miss count | 15 |
| Reranker-visible miss count | 42 |
| Factual-alias case count | 479 |
| Factual-alias average line count | 218.27 |
| Factual-alias evidence coverage | 227/479 = 0.4739 |
| Factual-alias candidate evidence coverage | 220/479 = 0.4593 |
| Gold candidate alias cases | 220 |
| Gold candidate query-overlap cases | 28 |
| Factual-alias candidate lift top-10 | 16 |
| Factual-alias fused lift top-10 | 2 |
| Source-semantic fused regressions top-10 | 0 |
| Hot-query provider calls | 0 |
| Provider tokens | 0 |
| Source caches | 500 |
| Source rows / spans | 246,738 |
| Factual-alias profiles | 109,144 |
| Factual-alias terms | 738,561 |
| Cache-key complete rate | 1.0 |
| Hot query latency average | 1092.5576ms |
| Hot query latency max | 1926.4032ms |

The public privacy boundary stayed intact:

- raw source text emitted: `false`
- cache values emitted: `false`
- candidate rows are routes, not claims: `true`
- foreground window growth policy: `bounded_candidate_routes_only`
- provider calls and tokens on the hot path: `0`

## Interpretation

This closes the bounded #1327 source-window coverage question. Candidate
evidence coverage improves from the earlier lexical 500Q diagnostic's
`455/479 = 0.9499` to `463/479 = 0.9666` without widening the default
foreground context window. The remaining 57 fused misses are now split into 15
candidate-missing misses and 42 reranker-visible misses, which is enough to
route future work toward exact-line/reranker quality rather than treating
source-window coverage as an unresolved owner blocker.

This also closes #1424 as a bounded source-side factual recall owner. The
runtime contract keeps local factual aliases and answer-bearing source handles
available to source-side routing, reports cache/latency/regression metrics, and
requires source reopen before factual claims. The replay shows those handles
are usable at 500Q scale with zero hot-path provider calls and zero fused
top-10 regressions.

For #1323, this is the measured product-shaped successor to the earlier
semantic-scope warming experiments. The full-source semantic-scope materializer
still matters as a negative result: it improved sidecar coverage but did not
lift fused R@10. The factual-alias layer supplies the source-local factual
surface the benchmark actually needed, so the current #1323 owner can close
as a measured source-side benchmark slice while preserving the no-lift
semantic-scope result as a boundary, not pretending it became a success.

## Cannot Claim

- answer-generation quality;
- official LongMemEval QA score or leaderboard result;
- LongMemEval-V2 behavior;
- SOTA or external baseline superiority;
- broad life-history memory superiority;
- default foreground adoption;
- perfect exact-line citation quality;
- source truth from aliases, working-memory rows, or candidate routes without
  source reopen.
