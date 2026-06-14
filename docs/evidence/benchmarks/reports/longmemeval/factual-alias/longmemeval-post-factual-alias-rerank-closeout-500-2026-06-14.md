# LongMemEval Post-Factual-Alias Rerank Closeout - 2026-06-14

This report closes #1437 by analyzing the same sanitized LongMemEval-S first
500-question factual-alias report after the #1323/#1327/#1424 closeout. It does
not introduce a default reranker change.

## Command

```powershell
python benchmarks\aippocampus\benchmark_longmemeval_rerank_analysis.py `
  --report docs\evidence\benchmarks\reports\longmemeval\longmemeval-source-factual-alias-500-2026-06-14.json `
  --output docs\evidence\benchmarks\reports\longmemeval\longmemeval-post-factual-alias-rerank-closeout-500-2026-06-14.analysis.json `
  --json
```

Focused verification:

```powershell
python -m pytest tests\aippocampus\test_benchmark_longmemeval_rerank_analysis.py -q
```

## Same-Cohort Evidence

| Metric | Value |
|---|---:|
| Questions | 500 |
| Evidence-line cases | 479 |
| Reranked evidence-line R@10 | 422/479 = 0.8810 |
| Reranked evidence-line MRR | 0.6744 |
| Candidate evidence coverage | 463/479 = 0.9666 |
| Top-10 regressions | 0 |
| Hot-query provider calls | 0 |
| Hot-query latency avg | 1092.5576ms |
| Hot-query latency max | 1926.4032ms |

The report's `full_500_projection` is marked
`already_measured_local_hot_path`: this closeout used the local AIppocampus
runtime source-semantic-cache path with no provider calls and no provider
tokens. Follow-up work should name a candidate-builder or source-reopen
boundary question, not reuse the older external-model budget gate.

## Miss Split

| Bucket | Count |
|---|---:|
| Fused misses | 57 |
| Candidate-missing misses | 15 |
| Reranker-visible misses | 42 |

## Decision

- `post_factual_alias_exact_line_rerank_v1`: rejected as a default reranker
  change. The 42 reranker-visible misses are candidate-visible exact-line
  ranking failures, while factual-alias candidate evidence produced only 2
  fused top-10 lifts from 16 candidate lifts on this cohort.
- `bounded_candidate_coverage_v1`: accepted only as a future candidate-builder
  slice. The projection lifts candidate coverage by 6 with candidate byte
  growth ratio `0.0001`, but this is coverage work, not exact-line rerank
  quality.
- No provider-backed full rerank is being requested or implied by this
  closeout; source reopen and navigation-only candidate boundaries stay in
  force.

## Can Claim

- #1437's remaining 57 misses have been analyzed on the same 500Q cohort.
- A scoped default reranker change was explicitly rejected from this evidence.
- A bounded candidate-builder follow-up is separated from exact-line rerank
  quality and source-truth claims.

## Cannot Claim

- Perfect exact-line citation quality.
- Answer-generation quality or official LongMemEval QA score.
- Default reranker adoption.
- Source truth from aliases or candidate routes.
- Broad memory superiority or SOTA.

## Public Boundary

The committed analysis emits aggregate sanitized metrics only. It does not
serialize raw questions, answers, source text, source refs, provider payloads,
cache values, credentials, local paths, or private-history rows.
