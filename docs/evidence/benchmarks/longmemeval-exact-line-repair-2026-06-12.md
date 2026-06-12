# LongMemEval-S Exact-Line Repair Report

Date: 2026-06-12

Issue: [#1193](https://github.com/Sapientropic/AIppocampus/issues/1193)

Sanitized JSON: [`longmemeval-exact-line-repair-2026-06-12.json`](longmemeval-exact-line-repair-2026-06-12.json)

## Decision

Status: `full_split_exact_line_repair_failure_report`.

The deterministic `structural` source-window reranker did not beat the same-split
`lexical` 500-question baseline. It is kept as an explicit diagnostic mode, not
a promoted default path.

| Arm | Exact evidence-line R@10 | Evidence-line MRR | Context-visible conversions | Same-session wrong-line reductions |
| --- | ---: | ---: | ---: | ---: |
| Lexical 500Q baseline | 419 / 479 = 0.8747 | 0.6746 | 10 | 11 |
| Structural 500Q repair | 416 / 479 = 0.8685 | 0.6663 | 8 | 8 |
| Delta | -3 | -0.0083 | -2 | -3 |

The first-stage retrieval layer remains unchanged: evidence-line R@10 is
408 / 479 = 0.8518. The structural reranker lifts some cases over the first
stage, but less than the older lexical reranker.

## Miss Families

The failure is concentrated in two different layers:

| Miss family | Count | Structural recovered | Interpretation |
| --- | ---: | ---: | --- |
| `context_visible_exact_line_miss` | 44 | 8 | Candidate window contains the answer line, but deterministic line selection still fails for 36 cases. |
| `same_session_wrong_line_top_k` | 9 | 0 | Wrong line in the right session remains mostly a semantic evidence-selection problem. |
| `session_found_below_top_k` | 9 | 0 | Source-window routing, not line reranking, is the blocker. |
| `gold_line_low_rank_21_50` | 5 | 0 | Needs broader routing or source-side semantic support. |
| `gold_line_rank_below_50` | 3 | 0 | Mostly source-window visibility; one case had candidate evidence but line selection failed. |
| `gold_line_near_miss_rank_2_20` | 1 | 0 | Not rescued by structural features. |

By case type, structural only adds small first-stage lifts: temporal reasoning
adds 3, and knowledge-update, multi-session, single-session-assistant,
single-session-preference, and single-session-user add 1 each.

## Semantic Path Boundary

The existing 25-question semantic pilot remains directional evidence, not a
500Q quality claim. Its cold online path averaged 7156.27 ms over 24 available
calls, used 225170 total tokens, and projects to about 4503400 tokens and
59.64 single-worker minutes for 500 questions. Provider dollar cost was not
reported by the chat-completions response.

The #1193 report distinguishes the three product paths:

| Path | Status | Boundary |
| --- | --- | --- |
| Cold online semantic rerank | `measured_pilot` | Quality ceiling/debugging only; not a default hook path. |
| Warm query/candidate cache | `contract_defined_not_measured` | Cache key must include query hash, candidate hashes, prompt version, model/provider id, source or dataset fingerprint, and policy version. |
| Source-side semantic cache | `not_measured_for_semantic_cache` / `not_run` | Must be built from source spans, not benchmark questions, before claiming hot-path latency or build cost. |

## Claim Boundary

This closes #1193 as a measured deterministic failure report plus cache-path
boundary. It does not claim default exact-line citation quality, 500Q semantic
reranker quality, answer-generation quality, official LongMemEval QA score,
judge-model score, provider-independent quality, or SOTA.

The useful next slice is source-side semantic warming or a budget-approved 500Q
semantic rerank arm, not more untuned local structural heuristics.
