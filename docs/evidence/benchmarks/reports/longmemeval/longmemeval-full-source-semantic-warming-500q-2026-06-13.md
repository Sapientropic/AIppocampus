# LongMemEval Full-Source Semantic Warming Diagnostic

Run date: 2026-06-13 local / 2026-06-13 UTC.

Issue: [#1323](https://github.com/Sapientropic/AIppocampus/issues/1323)

Sanitized JSON:
[`longmemeval-full-source-semantic-warming-500q-2026-06-13.json`](longmemeval-full-source-semantic-warming-500q-2026-06-13.json).

Raw local report SHA-1:
`B6CFB24C883969CDD711EAD1AC1D31702895D6E6`.

## Decision

Status: `contract_aware_full_source_semantic_warming_measured`.

This is the fairer 500-question source-side semantic warming diagnostic. It
does not use private history and does not send query-time candidate text to an
external provider. It materializes public LongMemEval-S clean source with the
`public_semantic_labeler_full_source` sidecar path, prewarms source-side
worker surfaces, and evaluates retrieval-only source-line recall.

The result is mixed:

- Full-source materialization really covered all 246,738 clean-source message
  rows across the 500 selected sources.
- The source index cache was finally reused correctly: `500/500` source-index
  hits, `0` source-index rebuilds.
- Hot-query provider calls stayed `0`.
- Sidecar evidence coverage improved substantially versus the sparse top-8
  sidecar diagnostic.
- Fused evidence R@10 did not improve: it remained `422/479 = 0.8810`.

So this should not be presented as "AIppocampus full ability is 88.10%" or as
"full-source warming solves #1323". It is a fair public diagnostic for the
current source-side semantic warming adapter, and it says the next bottleneck
is ranking/fusion and candidate construction, not merely whether the sidecar
read the source.

## Cache Finding

The earlier cache miss pattern had three causes:

- the old standard case cache key included `max_questions`, so 100Q and 500Q
  prefix runs used different cache roots;
- source artifact cache files were stored under the per-prefix case root even
  though their artifact key was content-addressed;
- semantic sidecar files had no materializer manifest, so a full-source run
  could accidentally reuse older top-candidate sidecars.

The code now uses a shared-prefix standard cache root, stores source artifacts
under the shared benchmark cache root, and requires a sidecar manifest matching
the requested materializer contract before reuse. Because this run replaced
legacy non-manifest sidecars with contract-aware full-source sidecars, the
source artifact cache rebuilt `499` artifacts in this run. The standard source
indexes themselves were reused: `500` hits, `0` misses.

## Command

```powershell
python benchmarks\aippocampus\benchmark_longmemeval.py --split longmemeval-v1-small --questions 500 --min-questions 500 --top-k 10 --line-reranker source_semantic_cache --line-reranker-workers 64 --standard-cache-dir benchmark_corpus\.cache\standard-public-cases --source-semantic-sidecar-materializer public_semantic_labeler_full_source --source-semantic-sidecar-max-candidates 768 --max-source-semantic-sidecar-calls 700 --source-semantic-sidecar-workers 180 --source-semantic-sidecar-timeout 480 --source-semantic-sidecar-max-tokens 20000 --progress-every 100 --partial-output benchmark_corpus\reports\longmemeval-v1-small-semantic-scope-full-source-sidecar-v3-contract-500-2026-06-13.partial.json --output benchmark_corpus\reports\longmemeval-v1-small-semantic-scope-full-source-sidecar-v3-contract-500-2026-06-13.json
```

## Main Result

The run measured the first 500 LongMemEval-S questions and 479 evidence-line
cases.

| Arm | Evidence R@10 | MRR |
| --- | ---: | ---: |
| First-stage retrieval | `408/479 = 0.8518` | `0.6309` |
| Context-visible ceiling | `452/479 = 0.9436` | `0.8086` |
| Source-side search only | `156/479 = 0.3257` | `0.1380` |
| Source-side rerank only | `398/479 = 0.8309` | `0.5071` |
| FTS-preserving fused | `422/479 = 0.8810` | `0.6763` |

Compared with the worker-surface proxy, fused R@10 stayed the same
(`422/479`). Fused MRR moved slightly from `0.6734` to `0.6763`.

## Materialization

| Metric | Value |
| --- | ---: |
| Provider calls | `500` |
| Full-source candidate messages | `246,738` |
| Candidate batches | `500` |
| Materialized sidecar cases | `458` |
| Semantic labeler errors | `42` |
| Reviewed sidecar cases with rows | `451` |
| Reviewed semantic-scope label rows | `2,745` |
| Prompt tokens | `56,124,275` |
| Completion tokens | `4,585,860` |
| Total tokens | `60,710,135` |
| Prompt cache hit tokens | `12,548,480` |
| Prompt cache miss tokens | `43,575,795` |
| Hot-query provider calls | `0` |

The high prompt-cache miss count is not evidence that local AIppocampus cache
was ignored. It is provider-side prefix-cache telemetry for 500 distinct
full-source prompts. Local source-index cache hit `500/500`; sidecar
materialization intentionally sent public benchmark source text to the labeler
because this was the first contract-aware full-source pass.

## Sidecar Signal

| Metric | Value |
| --- | ---: |
| Cases with sidecar lines in source cache | `430/479 = 0.8977` |
| Sidecar exact evidence coverage | `53/479 = 0.1106` |
| Sidecar +/-5 context coverage | `74/479 = 0.1545` |
| Candidate evidence coverage through sidecar lines | `49/479 = 0.1023` |
| Candidate profiles with semantic-scope terms | `596` |
| Query/sidecar term overlap count | `260` |
| Query/sidecar term overlap total | `502` |
| Query/canonical-label overlap count | `0` |

This is meaningfully better than the sparse top-8 sidecar diagnostic, but still
too weak to move fused top-10 recall. The adapter can now observe source-side
semantic terms, but the actual top-10 failures are still dominated by source
window, candidate, and ranking/fusion behavior.

## No-Lift Diagnosis

The no-lift cause is not a generic "ranking needs work" placeholder. The
measured chain is:

- Of the `71` baseline evidence-line misses, the full-source sidecar exactly
  covered only `3`; it covered +/-5 context for `7`; and it put `0` missed gold
  lines into a sidecar-backed candidate intersection.
- Of the `53` total sidecar exact evidence hits, `50` were already baseline
  top-10 hits. The extra sidecar coverage mostly landed on easy rows that FTS
  already found.
- Final fusion is FTS-preserving: `reranked_evidence_rank =
  best_rank(evidence_rank, semantic_only_rank)`. A sidecar can only improve
  top-10 when the semantic-only ranking itself places the gold line in top-10;
  it does not soft-blend sidecar scores into the original FTS rank.
- Among the `57` fused misses, `37` had the gold line in the candidate pack.
  For those `37` candidate-visible misses, the gold line had `0/37`
  `semantic_scope_labels`, `0/37` `semantic_scope_terms`, and `0/37`
  query/semantic-scope term overlaps. The top wrong line had much stronger
  lexical proximity: average direct source-term overlap `5.03` versus `1.73`
  for gold, and average context distance `0.43` versus `2.35` for gold.
- The 37 candidate-visible miss gold ranks after source-semantic scoring were:
  `17` at ranks 11-20, `14` at ranks 21-50, and `6` below rank 50.

Two no-provider counterfactuals also constrain the fix:

| Counterfactual | Result |
| --- | --- |
| Candidate cap `96 -> 240` with existing search/scoring | Candidate evidence coverage rose `456/479 -> 472/479`, but fused R@10 only rose `422/479 -> 423/479`. Candidate width is not the main blocker. |
| Profile-scored source search over all cached profiles using `semantic_scope_terms` | Source-search R@10 rose, but fused R@10 fell to `421/479`. Naively sweeping all sidecar/profile terms adds noisy lexical matches instead of useful top-10 lift. |

The concrete root cause is that the current full-source materializer still
produces sparse semantic-scope labels, not dense retrieval semantics. Its prompt
asks the labeler to return compact findings only for messages that genuinely
need fuzzy scope labels and to omit ordinary one-off requests. That is a
reasonable AIppocampus continuity sidecar contract, but it does not label most
LongMemEval hard gold evidence rows. The current ranking path then mostly sees
ordinary lexical/context features for those hard rows, so wrong nearby lines
beat them.

Next measured fix should not be a blind weight tweak. It should add a
source-side retrieval signal that attaches to answer-bearing factual rows and
query aliases without using gold labels, then retest the same 500Q cohort. Good
candidates are a dense or lexicalized per-line/chunk semantic-retrieval term
surface, or a session-level source-side summary/alias surface that feeds
candidate construction before the existing FTS-preserving fusion.

## Boundary

This report supports a public, source-backed diagnostic for contract-aware
full-source semantic warming on LongMemEval-S. It does not claim official
LongMemEval QA score, answer-generation quality, SOTA, full AIppocampus product
ability, default foreground recall quality, or that semantic sidecar values are
source truth.
