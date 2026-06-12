# LongMemEval-S Fixed-Reader Cleanup

Role: dated benchmark evidence.
Status: public-safe #1282 failure-review and expansion-gate cleanup.

## Decision

Do not scale the fixed-reader answer harness to 100 or 500 LongMemEval-S
questions yet. The 25-question rerun keeps retrieval/reference metrics strong,
but the answer layer still has provider errors, one false abstention on
bounded evidence, one deterministic-judge mismatch, and one true reader miss.

This cleanup is still useful: it replaces the original coarse failure labels
with a privacy-safe review artifact, adds prompt/source-line salience guidance
for bounded evidence, tests answer normalization and false-abstention cases,
and makes the next expansion decision explicit.

## Reports

| Run | Local report | SHA-256 | Prompt / judge |
| --- | --- | --- | --- |
| Original 25Q baseline | `benchmark_corpus/reports/longmemeval-v1-small-answer-fixed-reader-25-2026-06-12.json` | `8e1c3227129962f8b90071e3e5b45277dbf7536acb545a629925df77c26ee195` | `longmemeval-s-fixed-reader-v1` / `deterministic_longmemeval_answer_overlap_v1` |
| Cleanup 25Q rerun | `benchmark_corpus/reports/longmemeval-v1-small-answer-fixed-reader-v2-25-2026-06-12.json` | `b8d8ec88bb40452f49eb58a2af8cf768aea9a00865db506c790b2679d09354a9` | `longmemeval-s-fixed-reader-v2` / `deterministic_longmemeval_answer_overlap_v2` |

Both reports are generated artifacts and remain gitignored. This document
contains only aggregate metrics, hashed case ids, hashed answer identities,
and boundary metadata.

## Cleanup Changes

- Reader prompt v2 now tells the fixed reader that bounded source lines are
  intentional and that it should not abstain merely because the full
  conversation is absent.
- Candidate rows now include a salience hint:
  `direct_retrieval_hit`, `nearby_context_high_rank`, or `nearby_context`.
- The local deterministic overlap judge normalizes common numeric equivalents
  such as `9` and `nine`.
- Failure taxonomy now separates reader/provider failures, retrieval evidence
  unavailability, source-line packaging misses, false abstention on answerable
  bounded evidence, empty reader answers, deterministic-judge mismatches, and
  true reader misses.
- The report now carries a sanitized `failure_review` plus an
  `expansion_gate`.

## Original Failure Review

The original baseline reported 20 correct and 5 non-correct cases. The five
non-correct cases can be re-read safely as:

| Case id | Original label | Refined label | Safe next action |
| --- | --- | --- | --- |
| `3ac89a91fbcb1a6d` | `abstention_unanswerable_boundary` | `reader_provider_error` | rerun or inspect provider response shape |
| `24160dc2239b1841` | `evaluation_mismatch` | `deterministic_judge_mismatch` | review normalization or official judge equivalence |
| `486b34a868ce3a37` | `abstention_unanswerable_boundary` | `reader_provider_error` | rerun or inspect provider response shape |
| `f195e89f397a55c9` | `evaluation_mismatch` | `deterministic_judge_mismatch` | review normalization or official judge equivalence |
| `3e8ffb7dffdb8250` | `evidence_visible_reader_miss` | `true_reader_miss` | improve reader prompt or model route |

No raw LongMemEval question text, source text, answer text, model response, or
local path is needed to explain this taxonomy.

## Rerun Command

```powershell
python benchmarks\aippocampus\benchmark_longmemeval_answer.py --split longmemeval-v1-small --download --questions 25 --min-questions 25 --top-k 10 --reader-mode provider --reader-model deepseek-v4-flash --reader-api-key-env DEEPSEEK_API_KEY --reader-timeout 45 --reader-max-tokens 512 --reader-input-cost-per-million 0.28 --reader-output-cost-per-million 0.42 --partial-output benchmark_corpus\reports\longmemeval-v1-small-answer-fixed-reader-v2-25-2026-06-12.partial.json --provider-budget-checkpoint benchmark_corpus\reports\longmemeval-v1-small-answer-fixed-reader-v2-25-2026-06-12.budget.json --max-provider-calls 25 --max-provider-total-tokens 400000 --max-provider-estimated-cost-usd 0.25 --output benchmark_corpus\reports\longmemeval-v1-small-answer-fixed-reader-v2-25-2026-06-12.json --json
```

## Before / After

Retrieval/reference layer:

| Metric | Original 25Q | Cleanup 25Q |
| --- | ---: | ---: |
| Questions | 25 | 25 |
| Session R@10 | 25 / 25 = 1.0000 | 25 / 25 = 1.0000 |
| Evidence-line R@10 | 23 / 25 = 0.9200 | 23 / 25 = 0.9200 |
| Context-visible evidence R@10 | 25 / 25 = 1.0000 | 25 / 25 = 1.0000 |
| Evidence-line MRR | 0.6348 | 0.6348 |
| Context-visible evidence MRR | 0.9533 | 0.9533 |

Answer layer:

| Metric | Original 25Q | Cleanup 25Q |
| --- | ---: | ---: |
| Reader attempted | 25 / 25 | 25 / 25 |
| Deterministic correct | 20 / 25 = 0.8000 | 19 / 25 = 0.7600 |
| Context sufficient | 25 / 25 = 1.0000 | 25 / 25 = 1.0000 |
| Reader abstentions | 0 | 1 |
| Reader/provider errors | 2 after refinement | 3 |
| Deterministic-judge mismatches | 2 after refinement | 1 |
| False abstention on bounded evidence | 0 after refinement | 1 |
| Source-line packaging failures | not separated | 0 |
| True reader misses | 1 | 1 |

Latency, tokens, cache, and cost:

| Metric | Original 25Q | Cleanup 25Q |
| --- | ---: | ---: |
| Retrieval latency avg / max | 7.22 ms / 9.49 ms | 6.41 ms / 8.48 ms |
| Reader latency avg / max | 2723.84 ms / 6775.68 ms | 3530.63 ms / 21048.10 ms |
| Total elapsed | 192.69 s | 142.53 s |
| Prompt tokens | 376,166 | 392,148 |
| Completion tokens | 3,799 | 4,077 |
| Total tokens | 379,965 | 396,225 |
| Prefix-cache hit tokens | 0 | 0 |
| Prefix-cache miss tokens | 376,166 | 392,148 |
| Run-configured estimated cost | USD 0.106922 | USD 0.111514 |

The dollar figures use the explicit command-line price table for this run:
USD 0.28 / 1M input tokens and USD 0.42 / 1M output tokens. They are run
configuration evidence, not a durable provider-pricing claim.

## Cleanup Failure Review

The cleanup report has 6 non-correct cases:

| Refined label | Count | Notes |
| --- | ---: | --- |
| `reader_provider_error` | 3 | Provider call/response failures remain a hard expansion blocker. |
| `over_abstention_boundary_false_negative` | 1 | The evidence was visible in bounded candidate lines, but the reader abstained. |
| `deterministic_judge_mismatch` | 1 | Needs normalization or official-judge-equivalence review before scaling. |
| `true_reader_miss` | 1 | Retrieval and packaging were sufficient; the reader answer was still wrong. |

The cleanup report validator passed all configured leak checks:

- absolute local path leaks: 0;
- credential-like strings: 0;
- raw question, answer, source, or model-response text leaks: 0.

## Expansion Gate

The cleanup report emits:

- `status`: `no_go`;
- `next_action`: `fix_blockers_before_100q_or_500q`;
- blockers: `reader_provider_error`, `deterministic_judge_mismatch`,
  `over_abstention_boundary_false_negative`;
- true reader misses: 1.

Expansion criteria:

- Keep 500Q no-go while any 25Q review contains provider errors,
  unexplained judge mismatches, false abstentions on answerable bounded
  evidence, source-line packaging failures, or retrieval evidence unavailable
  for answerable cases.
- After the 25Q blockers are fixed, run 100Q before 500Q. The 100Q report must
  keep retrieval, answer, latency, token/cache, and cost layers separate and
  must pass sanitized report validation.
- Only consider 500Q after a 100Q report has no provider errors, no
  unexplained judge mismatches, no false abstentions on answerable bounded
  evidence, no packaging failures, and no retrieval-unavailable answer cases.
  Remaining true reader misses can be reported as answer-model quality limits,
  not as retrieval or packaging defects.

## Supports

- #1282 has an actionable, public-safe failure taxonomy for the original 25Q
  and the cleanup rerun.
- The reader prompt and candidate packaging now explicitly distinguish
  answerable bounded evidence from unsupported context.
- Tests cover numeric-equivalent answer normalization, bounded evidence that
  should not trigger false abstention, packaging failures, and expansion-gate
  blockers.

## Material Limits

- This is not an official LongMemEval judge score.
- This does not improve the 25Q answer score; the cleanup rerun is 19 / 25.
- This is not LongMemEval-V2, SOTA, leaderboard evidence, provider adoption,
  or model-independent memory superiority.
- This does not justify 100Q or 500Q provider answer runs until the no-go
  blockers above are fixed and rechecked.
