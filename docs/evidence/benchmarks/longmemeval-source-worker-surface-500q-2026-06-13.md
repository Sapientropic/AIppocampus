# LongMemEval #1323 Source-Side Worker-Surface Closeout

Run date: 2026-06-13 local / 2026-06-12 UTC.

This closes the measurement gap from #1323 for the current public
AIppocampus path. It separates two things that must not be conflated:

- `source_semantic_cache`: current AIppocampus source-side worker-memory
  surface. It materializes `aippocampus_working_memory` navigation rows from
  clean source, uses the existing hot matcher, requires source reopen, and
  makes no provider calls.
- `semantic`: opt-in DeepSeek query/candidate LLM reranker. This is a stronger
  query-time upper bound, not evidence that AIppocampus has a source-side LLM
  cache.

## Dataset Scale

- Split: LongMemEval-S cleaned, first 500 questions.
- Dataset SHA-256:
  `d6f21ea9d60a0d56f34a05b609c79c88a451d2ae03597821ea3d5a9678c3a442`.
- Runner-scanned source messages: `246,738`.
- Direct JSON scan of the same first 500 questions: `246,750` messages and
  `244,651,645` characters. The 12-message difference is the adapter cleaning
  boundary.
- Rough token scale, using only character ratios: about `61.2M` tokens at
  chars/4, `69.9M` at chars/3.5, or `81.6M` at chars/3. This is not a
  tokenizer-measured value.

## Source-Side Worker Surface

Command:

```powershell
python benchmarks\aippocampus\benchmark_longmemeval.py --split longmemeval-v1-small --questions 500 --min-questions 100 --top-k 10 --line-reranker source_semantic_cache --line-reranker-workers 32 --progress-every 50 --output benchmark_corpus\reports\longmemeval-v1-small-source-worker-surface-500-2026-06-13.json
```

Raw local report SHA-1:
`5A0937321ECE0B236357740E8C3CAF212DB7CAD0`.

Key result:

- Baseline evidence-line R@10: `408/479 = 0.8518`; MRR `0.6309`.
- Source worker-surface search alone: R@10 `156/479 = 0.3257`; MRR `0.1391`.
- Source worker-surface rerank only: R@10 `398/479 = 0.8309`; MRR `0.5046`.
- Source worker-surface fused path: R@10 `422/479 = 0.8810`; MRR `0.6734`.
- Bridge lifts over baseline: `14`.
- Fused top-10 regressions: `0`.
- Source-only top-10 regressions: `24`.
- Errors: `0`.

Cold build / hot path:

- Prewarm workers: `64`.
- Source caches: `500`.
- Working-memory rows materialized: `246,738`.
- Complete rows: `246,738`; failed rows: `0`; complete rate `1.0`.
- Build latency summary is the sum of per-case local cache builds:
  total `27,595,877.06ms`, average `55,191.75ms`, max `82,634.04ms`.
- Hot source-worker search latency: average `1044.5179ms`, max
  `3464.3719ms`.
- Candidate rerank latency after source-worker search: average `1.18ms`, max
  `1.92ms`.
- Provider calls, provider tokens, and hot query provider calls: all `0`.

Boundary:

- This is current AIppocampus source-side worker-memory surface evidence.
- It is navigation-only: worker rows are source refs and route terms, not
  factual answers.
- It does not claim a future DeepSeek source-side semantic materializer would
  have the same quality.
- It does not make foreground LLM reranking default.

## Query/Candidate LLM Upper Bound

Command:

```powershell
python benchmarks\aippocampus\benchmark_longmemeval.py --split longmemeval-v1-small --questions 500 --min-questions 100 --top-k 10 --line-reranker semantic --line-reranker-timeout 180 --line-reranker-workers 8 --progress-every 25 --partial-output benchmark_corpus\reports\longmemeval-v1-small-semantic-500-2026-06-13.partial.json --provider-budget-checkpoint benchmark_corpus\reports\longmemeval-v1-small-semantic-500-2026-06-13.budget.json --max-provider-calls 500 --max-provider-total-tokens 10000000 --provider-cost-unknown --output benchmark_corpus\reports\longmemeval-v1-small-semantic-500-2026-06-13.json
```

Raw local report SHA-1:
`A3D2A89E9CB48CB26B8C9BD81059F7E3884593BC`.

Key result:

- Semantic-only evidence-line R@10: `440/479 = 0.9186`; MRR `0.8428`.
- Semantic fused R@10: `451/479 = 0.9415`; MRR `0.8738`.
- Bridge lifts over baseline: `43`.
- Available calls: `470/479`; error count `9`.
- Error kinds: `7` timeout, `2` line-reranker error.
- Timeout was explicitly set to `180s`; this was not the default `12s`
  timeout and not a source-side hardcoded cap.
- Token usage: `4,719,903` total tokens; provider prefix-cache hit rate
  `0.2290`.

Boundary:

- This arm proves the query/candidate LLM upper bound is meaningfully stronger
  than the current worker-surface path.
- It is not a source-side AIppocampus cache result.
- It is not default-hook evidence and should remain explicit opt-in until a
  separate product decision changes that.

## Interpretation

The honest reading is:

- Current source-side AIppocampus surface helps but is not enough to replace
  model-quality semantic line selection.
- FTS-preserving fusion is important: the source-side fused path improves R@10
  without top-10 regressions, while source-only ranking is weaker.
- The source-side arm is cheap at provider level because it uses no provider
  calls, but its current Python hot matcher is around one second per query on
  this 246k-row surface. If this becomes product-critical, the next engineering
  work is indexing/packing the worker surface, not another foreground LLM call.
- A future DeepSeek source-side materializer may still be worth testing, but
  that is a new materializer/productization question. It should not be counted
  as already proven by this worker-surface run.

Sanitized JSON summary:
[`longmemeval-source-worker-surface-500q-2026-06-13.json`](longmemeval-source-worker-surface-500q-2026-06-13.json).
