# LongMemEval-S 100Q Semantic Query/Cache Progress

Date: 2026-06-12

Issue: [#1323](https://github.com/Sapientropic/AIppocampus/issues/1323)

Related prior slice:
[#1305](https://github.com/Sapientropic/AIppocampus/issues/1305)

Sanitized JSON:
[`longmemeval-semantic-cache-100q-2026-06-12.json`](longmemeval-semantic-cache-100q-2026-06-12.json)

## Decision

Status: `semantic_query_cache_100q_progress_source_side_unmeasured`.

Supersession: as of 2026-06-13, #1323 is superseded for closeout status by
[`longmemeval-source-worker-surface-500q-2026-06-13.md`](longmemeval-source-worker-surface-500q-2026-06-13.md),
which measures the current AIppocampus source-side worker-memory surface and
the separate 500Q LLM query/candidate upper bound. Keep this file as the 100Q
query/candidate cache and provider-prefix-cache progress artifact only.

This report is progress toward #1323. It expands the #1305 warm
query/candidate cache path from the 25Q single-session pilot to the first 100
LongMemEval-S questions and adds a same-cohort deterministic lexical 100Q
comparison. At its run date, it did not close #1323 because the source-side
semantic cache path and full 500Q semantic-quality boundary remained
unmeasured.

## Runs

All runs use `longmemeval-v1-small`, the first 100 questions, top-k `10`, and
the existing source-evidence adapter. Raw generated reports remain local and
gitignored under `benchmark_corpus/reports/`.

| Run | Workers | Runtime | Provider calls | Tokens | Provider prefix-cache hit rate | Raw report SHA-1 |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| Lexical reranker comparison | 8 | 154.73s | 0 | 5656 local scored candidates | 0.0000 | `f7badccfaa2fac3d` |
| Semantic cold-fill / first 100Q | 2 | 767.25s | 90 available, 4 timeouts | 979237 | 0.2514 | `f37896cf860f9942` |
| Semantic repeated provider-prefix replay | 8 | 273.35s | 90 available, 4 timeouts | 962144 | 0.9932 | `8131fe2d77db1fd` |

The workers=8 repeat answers the throughput/cache question for the external
provider path: wall time fell from 767.25s to 273.35s and DeepSeek-style prefix
cache telemetry rose from 25.14% to 99.32% on repeated prompt/candidate inputs.
That is provider response telemetry, not the product's local query/candidate
cache and not source-side semantic warming.

## Exact-Line Metrics

There are 100 questions and 94 evidence-line cases in this slice. Session R@10
is `97/100 = 0.9700`; context-visible evidence R@10 is
`91/94 = 0.9681`.

| Arm | Evidence R@1 | Evidence R@3 | Evidence R@5 | Evidence R@10 | MRR |
| --- | ---: | ---: | ---: | ---: | ---: |
| First-stage retrieval | 49 / 94 = 0.5213 | 69 / 94 = 0.7340 | 76 / 94 = 0.8085 | 82 / 94 = 0.8723 | 0.6481 |
| Lexical reranker only | 37 / 94 = 0.3936 | 62 / 94 = 0.6596 | 69 / 94 = 0.7340 | 81 / 94 = 0.8617 | 0.5488 |
| Lexical fused | 56 / 94 = 0.5957 | 71 / 94 = 0.7553 | 78 / 94 = 0.8298 | 84 / 94 = 0.8936 | 0.6990 |
| Semantic only, first run | 82 / 94 = 0.8723 | 87 / 94 = 0.9255 | 87 / 94 = 0.9255 | 87 / 94 = 0.9255 | 0.8989 |
| Semantic fused, first run | 84 / 94 = 0.8936 | 89 / 94 = 0.9468 | 90 / 94 = 0.9574 | 91 / 94 = 0.9681 | 0.9246 |

The workers=8 repeat preserved semantic fused R@10 at `91/94 = 0.9681` but
had lower MRR (`0.9037`) than the workers=2 first run (`0.9246`), so the first
run remains the primary quality row and the repeat is cache/throughput
telemetry.

## Query/Candidate Cache Replay

The local warm replay is computed over sanitized semantic rows. It uses query
hash, candidate-pack hash, reranker prompt version, model/provider id, source or
dataset fingerprint, and policy version. It does not emit cache keys, cache
values, raw source text, raw question text, provider responses, credentials, or
absolute local paths.

| Metric | Value |
| --- | ---: |
| Available semantic rows | 90 |
| Complete query/candidate cache keys | 90 / 90 |
| Cold-fill misses, first pass | 90 |
| Warm replay hits, second pass | 90 |
| Warm replay hit rate | 1.0000 |
| Two-pass hit rate | 0.5000 |
| Warm local lookup latency, avg / max | 0.000063ms / 0.000300ms |
| Cache fill lookup latency, avg / max | 0.002803ms / 0.009300ms |
| Cold-fill provider latency, avg / max | 11136.85ms / 40084.59ms |
| Cold-fill token count | 979237 |
| Provider cost | unknown; provider response did not report cost |

This is an identical-query local cache replay over sanitized benchmark rows. It
proves key completeness and hot lookup mechanics for this path, but it does not
measure a deployed persistent product cache or source-side warming.

## Hurt Cases And Regressions

Semantic-only top-10 ranking regressed 4 baseline top-10 cases, all in
`multi_evidence_partial_hit`. The fused path had 0 top-10 regressions because it
is FTS-preserving; that should be read as a property of the fusion rule, not a
pure model-quality guarantee.

| Miss family | Cases | Baseline R@10 | Lexical fused R@10 | Semantic fused R@10 |
| --- | ---: | ---: | ---: | ---: |
| `context_visible_exact_line_miss` | 9 | 0 | 2 | 9 |
| `exact_line_found_top_k` | 62 | 62 | 62 | 62 |
| `multi_evidence_partial_hit` | 20 | 20 | 20 | 20 |
| `gold_line_low_rank_21_50` | 1 | 0 | 0 | 0 |
| `same_session_wrong_line_top_k` | 1 | 0 | 0 | 0 |
| `session_found_below_top_k` | 1 | 0 | 0 | 0 |

Per type, semantic fused R@10 is `64/64` for `single-session-user` evidence-line
cases and `27/30` for `multi-session` evidence-line cases. All 4 semantic
timeouts were in the multi-session slice.

The remaining fused misses are source-window-not-visible or low-rank families:
`gold_line_low_rank_21_50`, `same_session_wrong_line_top_k`, and
`session_found_below_top_k`. These are better candidates for broader routing or
source-side semantic warming than for more foreground per-query reranking.

## Boundaries

Cold online semantic rerank remains explicit opt-in and must not become a
default hook path. The 100Q first run projects to about `5208705` tokens and
92.81 single-worker minutes for 500 questions under the same workers=2
available-call latency, with provider dollar cost unavailable.

This report supports a 100Q warm query/candidate cache progress claim for
#1323. It does not claim source-side semantic cache build cost, source-side hot
path latency, full 500Q semantic quality, live hook latency, official
LongMemEval QA score, answer-generation quality, provider-independent quality,
SOTA, or broad memory superiority.
