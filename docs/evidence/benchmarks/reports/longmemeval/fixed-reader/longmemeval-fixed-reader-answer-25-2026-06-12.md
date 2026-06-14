# LongMemEval-S Fixed-Reader Answer Baseline

Role: dated benchmark evidence.
Status: public-safe provider-backed answer/latency baseline for #1194.

## Run

- Local date: 2026-06-12 Asia/Shanghai.
- Report timestamp: `2026-06-11T22:24:24Z`.
- Surface: `longmemeval-v1-small`, first 25 questions.
- Case mix: 25 `longmemeval_single-session-user` cases.
- Runner: `benchmarks/aippocampus/benchmark_longmemeval_answer.py`.
- Reader: DeepSeek-compatible API, `deepseek-v4-flash`.
- Prompt version: `longmemeval-s-fixed-reader-v1`.
- Local deterministic judge: `deterministic_longmemeval_answer_overlap_v1`.
- Full local report: `benchmark_corpus/reports/longmemeval-v1-small-answer-fixed-reader-25-2026-06-12.json`.
- Full local report SHA-256:
  `8e1c3227129962f8b90071e3e5b45277dbf7536acb545a629925df77c26ee195`.

The full report remains gitignored. This summary contains only aggregate
metrics, hashed report identity, public dataset provenance, and boundary
metadata.

## Command

```powershell
python benchmarks\aippocampus\benchmark_longmemeval_answer.py --split longmemeval-v1-small --download --questions 25 --min-questions 25 --top-k 10 --reader-mode provider --reader-model deepseek-v4-flash --reader-api-key-env DEEPSEEK_API_KEY --reader-timeout 45 --reader-max-tokens 512 --reader-input-cost-per-million 0.28 --reader-output-cost-per-million 0.42 --partial-output benchmark_corpus\reports\longmemeval-v1-small-answer-fixed-reader-25-2026-06-12.partial.json --provider-budget-checkpoint benchmark_corpus\reports\longmemeval-v1-small-answer-fixed-reader-25-2026-06-12.budget.json --max-provider-calls 25 --max-provider-total-tokens 400000 --max-provider-estimated-cost-usd 0.25 --output benchmark_corpus\reports\longmemeval-v1-small-answer-fixed-reader-25-2026-06-12.json --json
```

Provider budget outcome:

- completed units: 25 / 25;
- failed units recorded by provider-budget summary: 2;
- timeouts: 0;
- stop reason: `answer_scored`;
- token cap: 400,000 total tokens;
- token use: 379,965 total tokens.

## Results

Retrieval/reference layer:

- Session R@10: 25 / 25 = 1.0000.
- Evidence-line R@10: 23 / 25 = 0.9200.
- Context-visible evidence R@10: 25 / 25 = 1.0000.
- Evidence-line MRR: 0.6348.
- Context-visible evidence MRR: 0.9533.
- Evidence context rescued top-10 cases: 2.
- Warning count: 0.

Answer layer:

- Reader attempted: 25 / 25.
- Context sufficient: 25 / 25 = 1.0000.
- Deterministic answer-correct count: 20 / 25 = 0.8000.
- Reader abstention count: 0.
- Failure taxonomy counts:
  - `answered_correctly`: 20;
  - `abstention_unanswerable_boundary`: 2;
  - `evaluation_mismatch`: 2;
  - `evidence_visible_reader_miss`: 1.

Latency and cost layer:

- Retrieval latency: average 7.22 ms, max 9.49 ms.
- Reader latency: average 2723.84 ms, max 6775.68 ms.
- Total elapsed time: 192,694.46 ms.
- Prompt tokens: 376,166.
- Completion tokens: 3,799.
- DeepSeek prefix-cache hit tokens: 0.
- Run-configured cost estimate: USD 0.106922 using the explicit command-line
  table of USD 0.28 / 1M input tokens and USD 0.42 / 1M output tokens.

The command-line price table is the run configuration, not a durable public
price claim. DeepSeek's
[official pricing page](https://api-docs.deepseek.com/quick_start/pricing) for
`deepseek-v4-flash` listed USD 0.14 / 1M cache-miss input tokens and USD 0.28 /
1M output tokens when checked during closeout; prices may change, so future runs
should record the price table used by the runner and the pricing source
separately.

## Privacy And Claim Boundary

Sanitized report validation passed:

- `absolute_path_leak`: 0;
- `credential_like_string`: 0;
- raw question / answer / source text leak: 0.

The reader saw the public benchmark question text plus bounded candidate source
lines, line numbers, roles, ranks, nearest-hit rank, and context distance. It
did not receive gold answers, expected lines/sessions, `has_answer` labels,
retrieval miss taxonomy, judge labels, or raw report cases.

Supports:

- AIppocampus now has a dated LongMemEval-S fixed-reader answer/latency
  baseline on a small public cohort.
- The first 25 LongMemEval-S cases can be reported with retrieval, answer,
  latency, token/cache, and cost layers kept separate.

Material limits:

- Not an official LongMemEval judge score.
- Not LongMemEval-V2.
- Not SOTA or leaderboard evidence.
- Not model-independent memory superiority.
- Not default reader/provider adoption.
- Not private real-history quality.
- Narrow case mix: all 25 cases are `longmemeval_single-session-user`.
