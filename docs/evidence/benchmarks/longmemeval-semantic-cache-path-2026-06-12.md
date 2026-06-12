# LongMemEval-S Semantic Cache Path Report

Date: 2026-06-12

Issue: [#1305](https://github.com/Sapientropic/AIppocampus/issues/1305)

Sanitized JSON:
[`longmemeval-semantic-cache-path-2026-06-12.json`](longmemeval-semantic-cache-path-2026-06-12.json)

## Decision

Status: `semantic_warm_query_cache_path_replay_report`.

This report completes the warm query/candidate cache slice for #1305. It does
not reuse the #1193 structural failure report as completion evidence. The
structural 500Q report remains a failure boundary; this follow-up measures a
separate semantic/cache path over a fresh 25Q opt-in semantic pilot with
candidate-pack hashes in the sanitized case rows.

## Cache Path

The measured path is B: warm query/candidate cache.

| Metric | Value |
| --- | ---: |
| Semantic pilot cases | 25 |
| Available cold-fill calls | 24 |
| Complete query/candidate cache keys | 24 / 24 |
| Cold-fill cache misses | 24 |
| Warm replay hits | 24 |
| Warm replay hit rate | 1.0000 |
| Two-pass hit rate | 0.5000 |
| Warm lookup latency, avg / max | 0.000079ms / 0.000300ms |
| Cold-fill latency, avg / max | 6308.67ms / 21006.74ms |
| Cold-fill tokens | 223947 |
| Provider prefix-cache hit rate | 0.0000 |

The cache key includes query hash, candidate window/span hash, reranker prompt
version, model/provider id, source or dataset fingerprint, and policy version.
The committed report does not emit cache key samples, cache values, raw
candidate text, source text, questions, answers, provider responses, credentials,
or local paths.

Runtime now emits `line_reranker_candidate_pack_sha1` for reranker rows. That
hash is derived from candidate line/routing metadata plus source-text hashes,
not raw text. It gives a real candidate-window invalidation input without
turning the report into a source-text leak.

## Exact-Line Metrics

The semantic pilot remains narrow: all 25 cases are
`longmemeval_single-session-user`.

| Metric | Value |
| --- | ---: |
| First-stage evidence-line R@10 | 23 / 25 = 0.9200 |
| Semantic-only evidence-line R@10 | 24 / 25 = 0.9600 |
| Fused reranked evidence-line R@1 | 23 / 25 = 0.9200 |
| Fused reranked evidence-line R@3/R@5/R@10 | 25 / 25 = 1.0000 |
| Fused reranked evidence-line MRR | 0.9600 |
| Rerank regression count @10 | 0 |

Miss-family focus:

| Miss family | Cases | Recovered by fused rerank |
| --- | ---: | ---: |
| `context_visible_exact_line_miss` | 2 | 2 |
| `exact_line_found_top_k` | 22 | 22 |
| `multi_evidence_partial_hit` | 1 | 1 |

The two context-visible exact-line misses were also same-session wrong-line
cases in this pilot, and both were recovered by the semantic reranker before the
warm-cache replay.

## Boundaries

Cold online semantic rerank remains explicit opt-in and must not become a
default hook path. The full 500Q semantic projection from this pilot is about
4478940 tokens and 52.57 single-worker minutes, with provider dollar cost not
reported by the chat-completions response.

The warm replay proves query/candidate cache-key completeness and hot lookup
mechanics for repeated identical queries on the sanitized pilot. It does not
claim 500Q semantic quality, source-side semantic cache quality, live hook
latency, official LongMemEval QA score, answer-generation quality, or SOTA.

The source-side semantic cache path remains unmeasured: it still needs a
source-span warming job, offline build cost, hot-path latency, stale/invalidated
cache counts, and comparison against lexical, structural, and cold semantic
arms before it can be promoted.
