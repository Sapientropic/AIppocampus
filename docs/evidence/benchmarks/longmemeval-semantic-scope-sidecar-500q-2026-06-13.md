# LongMemEval Semantic-Scope Sidecar Diagnostic

Run date: 2026-06-13 local / 2026-06-13 UTC.

Issue: [#1323](https://github.com/Sapientropic/AIppocampus/issues/1323)

Sanitized JSON:
[`longmemeval-semantic-scope-sidecar-500q-2026-06-13.json`](longmemeval-semantic-scope-sidecar-500q-2026-06-13.json).

## Decision

Status: `diagnostic_materialized_sidecar_arm_no_rank_delta`.

This run should not be read as a win for source-side semantic warming. It
measured a real materialized semantic-scope sidecar path on public
LongMemEval-S data, but the resulting 500Q ranking is exactly identical to the
older worker-surface proxy. The useful result is the failure analysis:

- the first 100 questions are genuinely easier than the worst middle slice;
- the sidecar materializer produced nonzero sidecars, so this is not a
  no-op/load failure;
- those sidecars did not change any 500Q ranked case compared with the proxy;
- current sidecar labels rarely cover gold evidence lines and rarely overlap
  the query-side label namespace.

Do not close #1323 from this as a product-quality semantic cache success. Treat
it as the dated negative baseline for the current 8-candidate public sidecar
materializer.

## Commands

100Q smoke:

```powershell
python benchmarks\aippocampus\benchmark_longmemeval.py --split longmemeval-v1-small --questions 100 --min-questions 100 --top-k 10 --line-reranker source_semantic_cache --line-reranker-workers 16 --standard-cache-dir benchmark_corpus\.cache\standard-public-cases --rebuild-standard-cache --source-semantic-sidecar-materializer public_semantic_labeler --source-semantic-sidecar-max-candidates 8 --max-source-semantic-sidecar-calls 100 --source-semantic-sidecar-workers 8 --source-semantic-sidecar-timeout 90 --source-semantic-sidecar-max-tokens 0 --progress-every 10 --partial-output benchmark_corpus\reports\longmemeval-v1-small-semantic-scope-sidecar-100-2026-06-13.partial.json --output benchmark_corpus\reports\longmemeval-v1-small-semantic-scope-sidecar-100-2026-06-13.json
```

500Q diagnostic:

```powershell
python benchmarks\aippocampus\benchmark_longmemeval.py --split longmemeval-v1-small --questions 500 --min-questions 100 --top-k 10 --line-reranker source_semantic_cache --line-reranker-workers 32 --standard-cache-dir benchmark_corpus\.cache\standard-public-cases --source-semantic-sidecar-materializer public_semantic_labeler --source-semantic-sidecar-max-candidates 8 --max-source-semantic-sidecar-calls 500 --source-semantic-sidecar-workers 12 --source-semantic-sidecar-timeout 90 --source-semantic-sidecar-max-tokens 0 --progress-every 50 --partial-output benchmark_corpus\reports\longmemeval-v1-small-semantic-scope-sidecar-500-2026-06-13.partial.json --output benchmark_corpus\reports\longmemeval-v1-small-semantic-scope-sidecar-500-2026-06-13.json
```

Raw local report SHA-1 values:

- 100Q: `26D0984D8FC66DA6A68029B4CB8A44B25875FA86`.
- 500Q: `85074B2B76544D8FD010126C9A2005E820E4A215`.

Raw reports remain ignored under `benchmark_corpus/reports/`.

## Main Result

The 500Q run measured the first 500 LongMemEval-S questions and 479
evidence-line cases.

| Arm | Evidence R@10 | MRR |
| --- | ---: | ---: |
| First-stage retrieval | `408/479 = 0.8518` | `0.6309` |
| Context-visible ceiling | `452/479 = 0.9436` | `0.8086` |
| Source-side search only | `156/479 = 0.3257` | `0.1391` |
| Source-side rerank only | `398/479 = 0.8309` | `0.5046` |
| FTS-preserving fused | `422/479 = 0.8810` | `0.6734` |

The sidecar run and the older worker-surface proxy had `0` per-case rank
differences across the compared source-search, semantic-only, fused,
candidate-pack, and bridge-lift fields. The separate 100Q run and the first
100 cases of the 500Q run also had `0` differences.

## Why 100Q Looked Good

The first 100 cases are not representative of the hardest slice in the first
500. The drag comes mainly from q101-q200.

| Slice | Main mix | Evidence cases | Baseline R@10 | Candidate coverage | Fused R@10 | Fused misses |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| q1-q100 | 70 single-session-user, 30 multi-session | 94 | `0.8723` | `0.9574` | `0.9255` | 7 |
| q101-q200 | 70 multi-session, 30 preference | 95 | `0.7263` | `0.9263` | `0.7579` | 23 |
| q201-q300 | 67 temporal, 33 multi-session | 97 | `0.8351` | `0.8969` | `0.8454` | 15 |
| q301-q400 | 66 temporal, 34 knowledge-update | 99 | `0.9192` | `0.9798` | `0.9495` | 5 |
| q401-q500 | 56 assistant, 44 knowledge-update | 94 | `0.9043` | `1.0000` | `0.9255` | 7 |

So the 100Q smoke was not falsely high because of run instability; it was the
same prefix cohort. The 500Q score falls because the next slices, especially
q101-q200, are harder.

## Why Sidecar Did Not Help

The materializer did run:

- provider calls: `500`;
- materialized sidecar files with reviewed rows: `428`;
- reviewed semantic-scope label rows: `1,205`;
- source-cache hot query provider calls: `0`.

But the generated signal did not reach exact-line ranking:

- current sidecar rows exactly covered only `8/479 = 1.67%` gold evidence
  cases, and same-session +/-5-line coverage was `15/479 = 3.13%`;
- among the 57 fused misses, sidecar exact coverage was `0/57` and +/-5-line
  coverage was `0/57`;
- query-side labels directly overlapped sidecar labels in only `3/479`
  evidence cases;
- sidecar label distribution was mostly `personal_reflection`, `open_question`,
  `technical_work`, `idea_seed`, `reading_notes`, `preference`, and
  `life_context`, while query-side regex labels were mostly `value_like`,
  `answer_like_statement`, `currentness_or_temporal`, `preference`, and
  `technical_or_task`.

The current `public_semantic_candidate_messages` selector also explains the
coverage problem. With the same source-side selector and no gold labels:

| Max sidecar candidates | Gold exact coverage | Gold +/-5 coverage | Fused-miss exact coverage | Fused-miss +/-5 coverage |
| ---: | ---: | ---: | ---: | ---: |
| 8 | `27/479 = 0.0564` | `49/479 = 0.1023` | `2/57 = 0.0351` | `4/57 = 0.0702` |
| 24 | `61/479 = 0.1273` | `179/479 = 0.3737` | `7/57 = 0.1228` | `16/57 = 0.2807` |
| 48 | `66/479 = 0.1378` | `298/479 = 0.6221` | `7/57 = 0.1228` | `27/57 = 0.4737` |
| 96 | `104/479 = 0.2171` | `376/479 = 0.7850` | `10/57 = 0.1754` | `37/57 = 0.6491` |

This says the tested 8-candidate sidecar materializer is far too sparse for
LongMemEval exact-line repair. Raising the budget increases nearby coverage,
but exact-line coverage remains modest and cost grows sharply.

## Follow-Up

The next useful implementation should not just rerun the same 500Q job. It
should change one of the actual bottlenecks and then rerun:

- add source-side diagnostics for sidecar evidence coverage and query-label
  overlap to every report;
- align canonical semantic-scope labels with query-side scoring terms without
  making sidecar labels source truth;
- improve cold-fill candidate selection so the materializer labels likely
  evidence-bearing windows, not only the longest/user/question rows;
- compare against the worker-surface proxy and the query/candidate LLM upper
  bound on the same cohort.

## Boundary

This report supports a public negative diagnostic for the current 8-candidate
semantic-scope sidecar materializer. It does not claim official LongMemEval QA
score, answer-generation quality, SOTA, default foreground LLM reranking,
provider-independent semantic quality, broad life-history memory superiority,
or that semantic sidecar values are source truth.
