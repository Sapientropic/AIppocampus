# LongMemEval Evidence

This page is the stable entrypoint for AIppocampus LongMemEval work. It keeps
dataset provenance, commands, current metrics, and claim boundaries together so
a benchmark run remains visible after the raw report stays local.

## Boundary

LongMemEval is an external public benchmark for long-term interactive memory.
AIppocampus has a deterministic retrieval-only adapter for the official cleaned
V1 files, plus a separate fixed-reader answer/latency harness. The retrieval
adapter checks whether the expected answer session and source lines are
retrievable. The answer harness can send only bounded retrieved source lines to
an opt-in reader, then scores the reader locally with a deterministic
diagnostic judge. It is not the official LongMemEval evaluator.
LongMemEval-V2 is tracked separately. The context-gathering mapping pilot can
inspect the public V2 schema and local files, but it cannot report
source-evidence R@K/MRR. #1155 chooses a tiny official answer/latency pilot as
the next valid V2 route: use the upstream Insert/Query harness, a fixed reader
and evaluator, and sanitized local-only artifacts before any full V2 run or
answer-quality claim.

Use this page to answer:

- Which LongMemEval split was run?
- Which exact dataset file and checksum were used?
- Which command reproduced the result?
- Which retrieval metrics can be claimed, and which QA claims stay out of
  bounds?

Do not use this page to claim SOTA, official LongMemEval answer quality,
LongMemEval-V2 quality, or broad memory superiority from one retrieval,
answer-harness, or mapping run.

## Official Sources

- Paper: <https://arxiv.org/abs/2410.10813>
- Repository: <https://github.com/xiaowu0162/LongMemEval>
- Cleaned dataset: <https://huggingface.co/datasets/xiaowu0162/longmemeval-cleaned>
- V2 paper: <https://arxiv.org/abs/2605.12493>
- V2 repository: <https://github.com/xiaowu0162/LongMemEval-V2>
- V2 dataset: <https://huggingface.co/datasets/xiaowu0162/longmemeval-v2>
- Local manifest: [`benchmark_corpus/longmemeval_manifest.json`](../../../benchmark_corpus/longmemeval_manifest.json)

The runner pins Hugging Face LFS content SHA-256 values, not the HTTP `ETag`
header shown by the resolved download URL. The LFS `oid` is the value that
matches the downloaded file hash.

## Dataset Splits

| Runner split | File | Bytes | LFS content SHA-256 | Intended use |
| --- | --- | ---: | --- | --- |
| `longmemeval-v1-oracle` | `longmemeval_oracle.json` | 15,388,478 | `821a2034d219ab45846873dd14c14f12cfe7776e73527a483f9dac095d38620c` | Small smoke and oracle-evidence debugging. |
| `longmemeval-v1-small` | `longmemeval_s_cleaned.json` | 277,383,467 | `d6f21ea9d60a0d56f34a05b609c79c88a451d2ae03597821ea3d5a9678c3a442` | First comparable public split. |
| `longmemeval-v1-medium` | `longmemeval_m_cleaned.json` | 2,737,100,077 | `9d79e5524794a2e6900a3aa9cb7d9152c5a3e8319c9a87c25494ba1eacee495f` | Large-context stress split. |

## LongMemEval-V2 Context Mapping Pilot

LongMemEval-V2 is a separate agentic-context benchmark. The public V2
documentation describes an Insert/Query memory API that returns compact
multimodal context for a fixed reader, and reports answer accuracy plus query
latency. AIppocampus keeps that surface separate from the V1 source-evidence
adapter.

The V2 pilot runner is:

```powershell
python benchmarks\aippocampus\benchmark_longmemeval_v2_context.py --case-limit 5 --output .tmp\longmemeval-v2-context-mapping.json
```

Local V2 JSONL files stay ignored under `benchmark_corpus/longmemeval/`.
The runner emits only aggregate counts, local path hashes, checksums, hashed
case ids, and claim boundaries; it excludes raw question text, answers,
trajectory goals, UI accessibility trees, actions, thoughts, URLs, and
screenshot paths.

Current local pilot, run on 2026-06-03:

| File | Bytes | SHA-256 |
| --- | ---: | --- |
| `v2_questions.jsonl` | 286,186 | `0a3ae5ebea938c24d7800e1e0b0828e08ae1646f939a53853b2b8cdc08e292b7` |
| `v2_trajectories.jsonl` | 1,195,604,539 | `363cec9a8e87aa8d9101ce4e600aadbf7031d674056ebe4f969e8424abc5f3c6` |

| Metric | Value |
| --- | ---: |
| Questions | 451 |
| Trajectories | 1,870 |
| Exact question/trajectory id matches | 0 |
| Environment candidate coverage | 451 / 451 |
| Ambiguous environment candidate pools | 451 / 451 |
| Question rows with gold evidence refs | 0 |
| Trajectory rows with gold question/evidence refs | 0 |

Decision: V2 can support a diagnostic context candidate-pack pilot because
every question maps to a broad domain/environment trajectory pool. It cannot
currently support benchmark-grade context-gathering scores, source-evidence
R@K/MRR, or answer-generation quality inside AIppocampus without upstream
question-to-haystack/evidence-state labels and the official reader/evaluator
harness. Missing fields are `gold_trajectory_ids` or `haystack_ids` per
question, evidence state indices or source spans, and source ids that can be
used for grading without leaking answers.

## LongMemEval-V2 Official Pilot Decision

#1155 keeps the V2 source-evidence decision above, but moves the valid answer
route toward a tiny official-harness pilot rather than another V1-style
retrieval metric. The decision runner is:

```powershell
python benchmarks\aippocampus\benchmark_longmemeval_v2_official_pilot.py --json --output benchmark_corpus\reports\longmemeval-v2-official-pilot-decision.json
```

CLI stdout is static; use `--output` for the sanitized decision report. The
report records the official harness contract, the local AIppocampus
`aippocampus_context_provider` adapter contract, fixed reader/evaluator
settings, latency and cost budgets, artifact redaction policy, and the metric
separation that a later pilot must preserve.

The pilot path is deliberately small:

- default `10` questions, hard maximum `20` without a new issue;
- ignored local official checkout and ignored V2 data/output directories;
- fixed reader model/base URL/API-key env and fixed evaluator model/reasoning
  effort before a run starts;
- reports separate memory-context telemetry, answer accuracy,
  reader/evaluator dependency, and memory-query latency;
- no raw questions, answers, trajectory text, screenshots, URLs, local paths,
  raw reader responses, or credentials in AIppocampus reports.

`benchmarks/aippocampus/longmemeval_v2_aippocampus_adapter.py` provides the
minimal text-only Memory adapter shape for that pilot. The official harness
registers memory backends from its own `memory_modules` package, so a real
pilot should copy or import the adapter inside an ignored official checkout
instead of vendoring the official repository here. The adapter can return raw
trajectory-derived text to the official reader inside the local run workspace;
AIppocampus should publish only sanitized aggregate decision/report notes.

This closes the decision question, not the score. Do not cite the decision
report, adapter contract, context-mapping pilot, or a tiny dry run as
LongMemEval-V2 answer accuracy, LAFS, leaderboard readiness, SOTA, or broad
memory superiority.

## Commands

Let the dedicated runner download and verify a pinned split:

```powershell
python benchmarks\aippocampus\benchmark_longmemeval.py --split longmemeval-v1-oracle --download --questions 50 --min-questions 20 --top-k 10 --output benchmark_corpus\reports\longmemeval-v1-oracle-retrieval-50.json
```

Run the comparable LongMemEval-S retrieval slice after the S file is available:

```powershell
python benchmarks\aippocampus\benchmark_longmemeval.py --split longmemeval-v1-small --download --questions 50 --min-questions 20 --top-k 10 --output benchmark_corpus\reports\longmemeval-v1-small-retrieval-50.json
```

Run the current larger LongMemEval-S retrieval slice:

```powershell
python benchmarks\aippocampus\benchmark_longmemeval.py --split longmemeval-v1-small --download --questions 100 --min-questions 100 --top-k 10 --output benchmark_corpus\reports\longmemeval-v1-small-retrieval-100.json
```

For a larger local diagnostic, treat runtime as exploratory until a dated
report exists. Keep progress and checkpoint output enabled so a stopped run
still leaves a sanitized partial diagnostic instead of disappearing silently:

```powershell
python benchmarks\aippocampus\benchmark_longmemeval.py --split longmemeval-v1-small --download --questions 500 --min-questions 100 --top-k 10 --progress-every 25 --partial-output benchmark_corpus\reports\longmemeval-v1-small-retrieval-500.partial.json --output benchmark_corpus\reports\longmemeval-v1-small-retrieval-500.json
```

Run the optional local exact-line reranker diagnostic. This is not the default
retrieval-only row; it measures whether source-window-visible lines can be
promoted without using answer labels or an external model:

```powershell
python benchmarks\aippocampus\benchmark_longmemeval.py --split longmemeval-v1-small --download --questions 500 --min-questions 100 --top-k 10 --line-reranker lexical --line-reranker-workers 8 --progress-every 50 --partial-output benchmark_corpus\reports\longmemeval-v1-small-lexical-500.partial.json --output benchmark_corpus\reports\longmemeval-v1-small-lexical-500.json
```

Run the optional LLM exact-line reranker pilot. This sends the public benchmark
question text and bounded candidate source-line text to the configured external
chat provider, but it withholds gold answers, expected lines/sessions,
`has_answer` labels, judge labels, miss taxonomy, and raw report cases. The
report records the provider, model, prompt version, candidate pool, token
usage, cache telemetry, latency, and failures; provider dollar cost is not
reported by the chat-completions response:

```powershell
python benchmarks\aippocampus\benchmark_longmemeval.py --split longmemeval-v1-small --download --questions 25 --min-questions 25 --top-k 10 --line-reranker semantic --line-reranker-workers 1 --line-reranker-timeout 30 --progress-every 5 --output benchmark_corpus\reports\longmemeval-v1-small-semantic-pilot-25.json
```

Provider-backed reranker runs are opt-in live benchmark runs. They must declare
a case cap, per-case timeout, provider-call cap, token/cost budget or explicit
`--provider-cost-unknown`, a provider-budget checkpoint path, and a sanitized
partial-output path before the runner will call the provider:

```powershell
python benchmarks\aippocampus\benchmark_longmemeval.py --split longmemeval-v1-small --download --questions 25 --min-questions 25 --top-k 10 --line-reranker semantic --line-reranker-workers 1 --line-reranker-timeout 30 --progress-every 5 --max-provider-calls 25 --max-provider-total-tokens 300000 --provider-cost-unknown --provider-budget-checkpoint benchmark_corpus\reports\longmemeval-v1-small-semantic-pilot-25.budget.json --partial-output benchmark_corpus\reports\longmemeval-v1-small-semantic-pilot-25.partial.json --output benchmark_corpus\reports\longmemeval-v1-small-semantic-pilot-25.json
```

Use the same controls for a reviewed 50-question run, with `--questions 50`,
`--min-questions 50`, `--max-provider-calls 50`, a reviewed token or dollar
ceiling, and distinct budget/partial/output paths. A 500-question provider
sweep requires explicit operator approval before launch: confirm the provider
cost model or acknowledge `cost_unknown` with a hard token/call cap, review the
external candidate-source-text privacy boundary, keep checkpoint and partial
outputs gitignored, and record the stop reason and budget summary in the final
report. Deterministic retrieval and lexical reranker commands do not require
provider credentials and remain CI/benchmark-smoke safe.

Analyze a generated semantic reranker report without re-running the provider
call. This emits only aggregate ladder/taxonomy/projection fields and keeps the
input report path local:

```powershell
python benchmarks\aippocampus\benchmark_longmemeval_rerank_analysis.py --report benchmark_corpus\reports\longmemeval-v1-small-semantic-pilot-25.json --json
```

Run the CI-safe answer/latency report schema path. This reuses the retrieval
adapter, builds bounded candidate source windows, records retrieval and
candidate-gathering latency, and produces answer-layer fields without making a
live provider call:

```powershell
python benchmarks\aippocampus\benchmark_longmemeval_answer.py --split longmemeval-v1-oracle --download --questions 5 --min-questions 1 --reader-mode dry-run --output benchmark_corpus\reports\longmemeval-v1-oracle-answer-dry-run-5.json
```

Run the opt-in fixed-reader answer path only after choosing the provider,
model, API key environment variable, provider execution budget, checkpoint
paths, token budget, and cost table. The runner fails before the first provider
reader call when `--reader-mode provider` omits the shared provider budget
contract. The reader sees the public benchmark question and bounded retrieved
candidate source-line text. It does not receive gold answers, expected
lines/sessions, `has_answer` labels, miss taxonomy, judge labels, or raw report
cases:

```powershell
$env:AIPPOCAMPUS_LONGMEMEVAL_READER_API_KEY="<provider key>"
python benchmarks\aippocampus\benchmark_longmemeval_answer.py --split longmemeval-v1-small --questions 25 --min-questions 25 --top-k 10 --reader-mode provider --reader-model <fixed-reader-model> --reader-base-url <openai-compatible-base-url> --partial-output benchmark_corpus\reports\longmemeval-v1-small-answer-fixed-reader-25.partial.json --provider-budget-checkpoint benchmark_corpus\reports\longmemeval-v1-small-answer-fixed-reader-25.budget.json --max-provider-calls 25 --max-provider-total-tokens <token-cap> --max-provider-estimated-cost-usd <usd-cap> --reader-input-cost-per-million <prompt-price> --reader-output-cost-per-million <completion-price> --output benchmark_corpus\reports\longmemeval-v1-small-answer-fixed-reader-25.json
```

Answer reports keep `retrieval`, `answer`, `latency`, `token_usage`, and `cost`
as separate top-level fields. The local deterministic judge reports answer
overlap, abstention, citation-line counts, and a failure taxonomy for
`retrieval_miss`, `evidence_visible_reader_miss`,
`abstention_unanswerable_boundary`, `stale_update_confusion`,
`evaluation_mismatch`, and `answered_correctly`. The report validator rejects
absolute local paths, raw question/answer/source text that the runner marked
forbidden, raw model response text, and credential-like strings before the run
can be treated as a usable artifact.

`--progress-every` emits sanitized JSONL progress to stderr. `--partial-output`
writes a sanitized checkpoint/partial diagnostic with hashed local-path
identity, phase, built/evaluated counts, elapsed time, and claim boundaries; it
does not include raw LongMemEval questions, answers, snippets, or local paths.

Generated dataset files and reports stay ignored by default. Do not commit full
LongMemEval downloads or generated JSON reports unless a future change promotes
a small curated artifact with provenance and license notes.

The first dated LongMemEval-S answer/latency baseline is summarized in
[`longmemeval-fixed-reader-answer-25-2026-06-12.md`](longmemeval-fixed-reader-answer-25-2026-06-12.md).
The raw generated report remains local and gitignored; the committed summary
preserves the fixed reader config, prompt version, model/provider metadata,
token/cost telemetry, sanitized report validation, and retrieval-vs-answer
claim separation.

The #1282 fixed-reader cleanup rerun is summarized in
[`longmemeval-fixed-reader-cleanup-25-2026-06-12.md`](longmemeval-fixed-reader-cleanup-25-2026-06-12.md).
It adds a privacy-safe failure review, v2 bounded-evidence reader prompt, and
explicit expansion gate. The current decision is `no_go` for 100Q or 500Q
provider answer runs until reader/provider errors, false abstentions on
answerable bounded evidence, unexplained judge mismatches, and stale/currentness
confusion blockers are fixed. The gate treats source-line packaging as
applicable only when the LongMemEval case has exact line-gold evidence; no-line
gold cases remain reader/retrieval diagnostics, not automatic packaging
failures.

## Current Published Result

| Date | Split | Mode | Questions | Session R@10 | Evidence-line R@10 | Reranked evidence-line R@10 | Context-visible evidence R@10 | Runtime | Status |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `2026-06-12T10:10:57Z` | `longmemeval-v1-small` | retrieval-only + semantic line-reranker warm query/cache replay | 25 | 100.00% | 92.00% | 100.00% | 100.00% | 240.30s | `semantic_warm_query_cache_path_replay_report`; #1305 warm cache |
| `2026-06-12T05:56:12Z` | `longmemeval-v1-small` | retrieval-only + structural line-reranker failure report | 500 | 95.80% | 85.18% | 86.85% | 94.36% | 716.64s | `retrieval_sufficient`; #1193 failure report |
| `2026-06-12T00:59:47Z` | `longmemeval-v1-small` | fixed-reader provider answer cleanup | 25 | 100.00% | 92.00% | - | 100.00% | 142.53s | `answer_scored`; expansion `no_go` |
| `2026-06-11T22:24:24Z` | `longmemeval-v1-small` | fixed-reader provider answer baseline | 25 | 100.00% | 92.00% | - | 100.00% | 192.69s | `answer_scored` |
| `2026-06-10T07:26:53Z` | `longmemeval-v1-small` | retrieval-only + optional semantic LLM line reranker pilot | 25 | 100.00% | 92.00% | 100.00% | 100.00% | 239.15s | `retrieval_sufficient` pilot |
| `2026-06-10T04:15:44Z` | `longmemeval-v1-small` | retrieval-only + optional lexical line reranker | 500 | 95.80% | 85.18% | 87.47% | 94.36% | 737.84s | `retrieval_sufficient` |
| `2026-06-10T03:33:49Z` | `longmemeval-v1-small` | retrieval-only larger slice | 500 | 95.80% | 85.18% | - | 94.36% | 803.10s | `retrieval_sufficient` |
| `2026-06-09T14:08:17Z` | `longmemeval-v1-small` | retrieval-only larger slice | 100 | 97.00% | 87.23% | - | 96.81% | 126.72s | `retrieval_sufficient` |
| `2026-05-30T17:05:34Z` | `longmemeval-v1-small` | retrieval-only | 50 | 100.00% | 92.00% | - | 100.00% | 167.65s | `retrieval_sufficient` |
| `2026-05-30T16:47:41Z` | `longmemeval-v1-oracle` | retrieval-only smoke | 50 | 100.00% | 96.00% | - | 100.00% | not recorded | `retrieval_sufficient` |

Fresh reproduction commands:

```powershell
python benchmarks\aippocampus\benchmark_longmemeval.py --split longmemeval-v1-oracle --download --questions 50 --min-questions 20 --top-k 10 --output benchmark_corpus\reports\longmemeval-v1-oracle-retrieval-50.json
python benchmarks\aippocampus\benchmark_longmemeval.py --split longmemeval-v1-small --download --questions 50 --min-questions 20 --top-k 10 --output benchmark_corpus\reports\longmemeval-v1-small-retrieval-50.json
python benchmarks\aippocampus\benchmark_longmemeval.py --split longmemeval-v1-small --download --questions 100 --min-questions 100 --top-k 10 --output benchmark_corpus\reports\longmemeval-v1-small-retrieval-100.json
python benchmarks\aippocampus\benchmark_longmemeval.py --split longmemeval-v1-small --download --questions 500 --min-questions 100 --top-k 10 --progress-every 25 --partial-output benchmark_corpus\reports\longmemeval-v1-small-retrieval-500.partial.json --output benchmark_corpus\reports\longmemeval-v1-small-retrieval-500.json
python benchmarks\aippocampus\benchmark_longmemeval.py --split longmemeval-v1-small --download --questions 500 --min-questions 100 --top-k 10 --line-reranker lexical --line-reranker-workers 8 --progress-every 50 --partial-output benchmark_corpus\reports\longmemeval-v1-small-lexical-500.partial.json --output benchmark_corpus\reports\longmemeval-v1-small-lexical-500.json
python benchmarks\aippocampus\benchmark_longmemeval.py --split longmemeval-v1-small --questions 500 --min-questions 100 --top-k 10 --line-reranker structural --line-reranker-workers 8 --progress-every 50 --partial-output benchmark_corpus\reports\longmemeval-v1-small-structural-500.partial.json --output benchmark_corpus\reports\longmemeval-v1-small-structural-500.json
python benchmarks\aippocampus\benchmark_longmemeval_rerank_analysis.py --report benchmark_corpus\reports\longmemeval-v1-small-structural-500.json --baseline-report benchmark_corpus\reports\longmemeval-v1-small-lexical-500.json --semantic-pilot-report benchmark_corpus\reports\longmemeval-v1-small-semantic-pilot-25.json --output docs\evidence\benchmarks\longmemeval-exact-line-repair-2026-06-12.json --json
python benchmarks\aippocampus\benchmark_longmemeval.py --split longmemeval-v1-small --download --questions 25 --min-questions 25 --top-k 10 --line-reranker semantic --line-reranker-workers 1 --line-reranker-timeout 30 --progress-every 5 --max-provider-calls 25 --max-provider-total-tokens 300000 --provider-cost-unknown --provider-budget-checkpoint benchmark_corpus\reports\longmemeval-v1-small-semantic-pilot-25.budget.json --partial-output benchmark_corpus\reports\longmemeval-v1-small-semantic-pilot-25.partial.json --output benchmark_corpus\reports\longmemeval-v1-small-semantic-pilot-25.json
python benchmarks\aippocampus\benchmark_longmemeval.py --split longmemeval-v1-small --download --questions 25 --min-questions 25 --top-k 10 --line-reranker semantic --line-reranker-workers 1 --line-reranker-timeout 30 --progress-every 5 --max-provider-calls 25 --max-provider-total-tokens 300000 --provider-cost-unknown --provider-budget-checkpoint benchmark_corpus\reports\longmemeval-v1-small-semantic-pilot-25-cachehash.budget.json --partial-output benchmark_corpus\reports\longmemeval-v1-small-semantic-pilot-25-cachehash.partial.json --output benchmark_corpus\reports\longmemeval-v1-small-semantic-pilot-25-cachehash.json
python benchmarks\aippocampus\benchmark_longmemeval_rerank_analysis.py --report benchmark_corpus\reports\longmemeval-v1-small-structural-500.json --baseline-report benchmark_corpus\reports\longmemeval-v1-small-lexical-500.json --semantic-pilot-report benchmark_corpus\reports\longmemeval-v1-small-semantic-pilot-25-cachehash.json --output docs\evidence\benchmarks\longmemeval-semantic-cache-path-2026-06-12.json --json
python benchmarks\aippocampus\benchmark_longmemeval_answer.py --split longmemeval-v1-small --download --questions 25 --min-questions 25 --top-k 10 --reader-mode provider --reader-model deepseek-v4-flash --reader-api-key-env DEEPSEEK_API_KEY --reader-timeout 45 --reader-max-tokens 512 --reader-input-cost-per-million 0.28 --reader-output-cost-per-million 0.42 --partial-output benchmark_corpus\reports\longmemeval-v1-small-answer-fixed-reader-25-2026-06-12.partial.json --provider-budget-checkpoint benchmark_corpus\reports\longmemeval-v1-small-answer-fixed-reader-25-2026-06-12.budget.json --max-provider-calls 25 --max-provider-total-tokens 400000 --max-provider-estimated-cost-usd 0.25 --output benchmark_corpus\reports\longmemeval-v1-small-answer-fixed-reader-25-2026-06-12.json --json
python benchmarks\aippocampus\benchmark_longmemeval_answer.py --split longmemeval-v1-small --download --questions 25 --min-questions 25 --top-k 10 --reader-mode provider --reader-model deepseek-v4-flash --reader-api-key-env DEEPSEEK_API_KEY --reader-timeout 45 --reader-max-tokens 512 --reader-input-cost-per-million 0.28 --reader-output-cost-per-million 0.42 --partial-output benchmark_corpus\reports\longmemeval-v1-small-answer-fixed-reader-v2-25-2026-06-12.partial.json --provider-budget-checkpoint benchmark_corpus\reports\longmemeval-v1-small-answer-fixed-reader-v2-25-2026-06-12.budget.json --max-provider-calls 25 --max-provider-total-tokens 400000 --max-provider-estimated-cost-usd 0.25 --output benchmark_corpus\reports\longmemeval-v1-small-answer-fixed-reader-v2-25-2026-06-12.json --json
```

Fixed-reader answer baseline for #1194:

- Summary:
  [`longmemeval-fixed-reader-answer-25-2026-06-12.md`](longmemeval-fixed-reader-answer-25-2026-06-12.md).
- Reader attempted: `25/25`; deterministic answer-correct count:
  `20/25 = 0.8000`.
- Retrieval/reference layer in the same run: session R@10 `25/25`, evidence-line
  R@10 `23/25`, and context-visible evidence R@10 `25/25`.
- Reader latency: average `2723.84ms`, max `6775.68ms`; total elapsed
  `192.69s`.
- Token/cost: `379965` total tokens; run-configured cost estimate
  `USD 0.106922` under the explicit command-line price table.
- Sanitized report validation: passed; the committed summary does not include
  raw question text, raw answers, raw source text, local paths, raw model
  responses, or credentials.
- Boundary: this is not the official LongMemEval judge, not LongMemEval-V2,
  not SOTA/leaderboard evidence, and not default reader/provider adoption.

Fixed-reader cleanup for #1282:

- Summary:
  [`longmemeval-fixed-reader-cleanup-25-2026-06-12.md`](longmemeval-fixed-reader-cleanup-25-2026-06-12.md).
- Reader attempted: `25/25`; deterministic answer-correct count:
  `19/25 = 0.7600`.
- Retrieval/reference layer in the same run stayed unchanged from the baseline:
  session R@10 `25/25`, evidence-line R@10 `23/25`, and context-visible
  evidence R@10 `25/25`.
- Failure review: `3` reader/provider errors, `1` false abstention on
  answerable bounded evidence, `1` deterministic-judge mismatch, and `1`
  true reader miss.
- Expansion gate: `no_go` for 100Q or 500Q until the blocker categories above
  are fixed and rerun on the 25Q slice. Currentness/stale-update confusion is
  now a gate blocker; no-line-gold wrong answers are not counted as exact-line
  packaging failures without line evidence.

LongMemEval-S 500-question verification summary:

- Public artifact trail:
  [`longmemeval-500-retrieval-artifact-2026-06-11.json`](longmemeval-500-retrieval-artifact-2026-06-11.json).
  This manifest records the deterministic rerun metadata, dataset checksum,
  command shape, report SHA-256, aggregate metrics, privacy checks, and schema
  preview without committing the raw dataset or full generated report.
- Dataset file: `longmemeval_s_cleaned.json`
- Bytes: `277383467`
- SHA-256: `d6f21ea9d60a0d56f34a05b609c79c88a451d2ae03597821ea3d5a9678c3a442`
- Total runner time: `803.10s`
- Questions: `500`
- Case mix: `70` single-session-user, `133` multi-session,
  `30` single-session-preference, `133` temporal-reasoning,
  `78` knowledge-update, and `56` single-session-assistant cases.
- Evidence-line cases: `479`
- Top-k: `10`
- Evidence context radius: `5`
- Session R@10: `479/500`, Wilson 95% CI `0.9366..0.9724`
- Evidence-line R@10: `408/479`, Wilson 95% CI `0.8172..0.8808`
- Context-visible evidence R@10: `452/479`, Wilson 95% CI
  `0.9192..0.9610`
- MRR: session `0.8809`, evidence-line `0.6309`,
  context-visible evidence `0.8086`
- Evidence context rescued top-10 cases: `44`
- Evidence context improved cases: `179`
- Evidence-line recall ladder: R@1 `240/479 = 0.5010`, R@3
  `349/479 = 0.7286`, R@5 `380/479 = 0.7933`, R@10
  `408/479 = 0.8518`, R@20 `429/479 = 0.8956`, and R@50
  `450/479 = 0.9395`.
- Evidence miss taxonomy for the 71 exact-line R@10 misses:
  context-visible exact-line miss `44`, session found below top-k `9`,
  same-session wrong-line top-k `9`, gold line low-ranked at 21-50 `5`,
  gold line below rank 50 `3`, and gold line near-miss rank 11-20 `1`.
- The 44 context-visible rescues were near the exact evidence line: distance 1
  `29`, distance 2-to-context-radius `15`.
- Warning count: `0`
- Evaluator model / API: none; deterministic retrieval-only run.
- Progress checkpoints were emitted every 25 cases, and the final partial-output
  payload completed rather than recording a blocker.
- Raw report location:
  `benchmark_corpus/reports/longmemeval-v1-small-retrieval-500.json`
  locally, intentionally gitignored.

Optional lexical line-reranker 500-question follow-up for #1087:

- Run date: `2026-06-10T04:15:44Z`
- Command: same 500-question LongMemEval-S split and top-k as above, with
  `--line-reranker lexical --line-reranker-workers 8`.
- Total runner time: `737.84s`
- The first-stage retrieval baseline in the same run stayed unchanged:
  session R@10 `479/500`, exact evidence-line R@10 `408/479`, and
  context-visible evidence R@10 `452/479`.
- Fused reranked evidence-line R@10: `419/479 = 0.8747`, up 11 exact-line
  top-10 hits over first-stage FTS.
- Fused reranked evidence-line MRR: `0.6746`, up `0.0437` over the
  first-stage evidence-line MRR `0.6309`.
- Source-joined bridge lifts: `11`; these came from 10
  context-visible exact-line misses and 1 same-session wrong-line top-k miss.
- Reranker candidate evidence coverage: `455/479 = 0.9499`; average candidate
  count: `51.58`.
- Reranker error count: `0`; warning count: `0`.
- Evaluator model / API: none. The `lexical` reranker uses only question terms,
  source-window candidate text, role, channel, rank, and context-distance
  metadata. It does not use answer labels, expected lines, or model summaries.
- Sanitized report spot-check found no raw fixture strings, local absolute
  paths, or source text markers.
- Raw report location:
  `benchmark_corpus/reports/longmemeval-v1-small-lexical-500.json` locally,
  intentionally gitignored.

Structural exact-line repair failure report for #1193:

- Summary:
  [`longmemeval-exact-line-repair-2026-06-12.md`](longmemeval-exact-line-repair-2026-06-12.md).
- Sanitized JSON:
  [`longmemeval-exact-line-repair-2026-06-12.json`](longmemeval-exact-line-repair-2026-06-12.json).
- Run date: `2026-06-12T05:56:12Z`.
- Command: same 500-question LongMemEval-S split and top-k as above, with
  `--line-reranker structural --line-reranker-workers 8`.
- The `structural` reranker uses only query text, candidate source text,
  adjacent source-window text, route rank metadata, and context distance. It
  withholds gold answers, expected lines/sessions, `has_answer` labels, judge
  labels, and miss taxonomy.
- It did not beat the same-split lexical 500Q baseline: structural fused
  evidence-line R@10 was `416/479 = 0.8685` versus lexical `419/479 = 0.8747`;
  structural MRR was `0.6663` versus lexical `0.6746`.
- Context-visible conversion fell from lexical `10` to structural `8`;
  same-session wrong-line reduction fell from lexical `11` to structural `8`.
- Miss-family conclusion: 36 context-visible exact-line misses still had the
  target line in the candidate pool but were not selected; 9 session-found-below
  top-k cases and most low-rank/below-rank-50 cases need source-window routing
  or source-side semantic support rather than more local line heuristics.
- Semantic path boundary: the existing 25Q semantic pilot remains a quality
  ceiling/debugging signal. Its cold online path averaged `7156.27ms`, used
  `225170` tokens, and projects to about `4503400` tokens and `59.64`
  single-worker minutes for 500 questions. Warm query cache and source-side
  semantic cache are documented as distinct paths, but their latency/build cost
  were not yet measured in the #1193 artifact. The #1305 follow-up below now
  measures the warm query/candidate replay path separately; source-side
  semantic warming remains unmeasured.
- Decision: close #1193 as a deterministic failure report and cache-path
  boundary. Do not make cold online semantic rerank a default hook path, and do
  not spend more effort on untuned structural heuristics before testing
  source-side semantic warming or an explicitly budgeted 500Q semantic arm.

Warm query/candidate cache replay for #1305:

- Summary:
  [`longmemeval-semantic-cache-path-2026-06-12.md`](longmemeval-semantic-cache-path-2026-06-12.md).
- Sanitized JSON:
  [`longmemeval-semantic-cache-path-2026-06-12.json`](longmemeval-semantic-cache-path-2026-06-12.json).
- Run date: `2026-06-12T10:10:57Z`.
- The fresh 25Q semantic pilot now emits `line_reranker_candidate_pack_sha1`,
  a hash of candidate line/routing metadata plus source-text hashes. The hash
  is used as the candidate-window cache-key input without committing raw
  candidate text, questions, answers, source text, provider responses,
  credentials, or local paths.
- Warm query/candidate replay status:
  `measured_sanitized_warm_query_cache_replay`.
- Complete cache keys: `24/24` available cold-fill calls. The key fields are
  query hash, candidate window/span hash, reranker prompt version,
  model/provider id, source or dataset fingerprint, and policy version.
- Cold-fill provider path: `24` available calls, average `6308.67ms`, max
  `21006.74ms`, `223947` tokens. Provider prefix-cache hit rate was `0.0000`
  in this rerun, so the product query/cache path is measured separately from
  provider prefix-cache behavior.
- Warm replay: `24/24` hits, hit rate `1.0000`; average local lookup latency
  `0.000079ms`; two-pass hit rate `0.5000` because the first pass fills and the
  second pass hits.
- Exact-line metrics on the 25Q pilot: first-stage evidence-line R@10
  `23/25 = 0.9200`, semantic-only evidence-line R@10 `24/25 = 0.9600`,
  fused reranked evidence-line R@1 `23/25 = 0.9200`, fused reranked
  evidence-line R@3/R@5/R@10 `25/25 = 1.0000`, MRR `0.9600`, and
  top-10 regression count `0`.
- Miss-family breakdown: `context_visible_exact_line_miss` `2/2` recovered;
  those same two cases are also the same-session wrong-line focus cases in this
  narrow pilot. `exact_line_found_top_k` stayed `22/22`, and
  `multi_evidence_partial_hit` stayed `1/1`.
- Boundary: this completes the warm query/candidate cache measurement slice for
  #1305, not the 500Q semantic-quality slice and not source-side semantic
  warming. Cold online semantic rerank remains explicit opt-in and is still not
  a default hook path.

Optional semantic LLM line-reranker pilot for #1092:

- Run date: `2026-06-10T07:26:53Z`
- Command: first 25 LongMemEval-S questions, top-k `10`, with
  `--line-reranker semantic --line-reranker-workers 1 --line-reranker-timeout 30`.
- Prompt / arm: `llm_window_to_line_rerank`,
  `llm-window-to-line-rerank-v1`.
- Provider/model: DeepSeek-compatible chat API, `deepseek-v4-flash`.
- Input boundary: the external model saw question text plus bounded candidate
  line number, role, session rank, nearest-hit rank, context distance, and
  candidate source text. It did not receive gold answers, expected
  lines/sessions, `has_answer` labels, judge labels, miss taxonomy, or raw
  report cases.
- The first-stage retrieval baseline in the same run: session R@10 `25/25`,
  exact evidence-line R@10 `23/25`, and context-visible evidence R@10 `25/25`.
- Semantic-only evidence-line R@10: `24/25`; fused reranked evidence-line R@10:
  `25/25`; fused evidence-line MRR `1.0000`, up `0.3652` over first-stage
  evidence-line MRR `0.6348`.
- Sanitized analysis report:
  [`longmemeval-semantic-rerank-analysis-2026-06-10.json`](longmemeval-semantic-rerank-analysis-2026-06-10.json).
- Reranked evidence-line ladder from the analysis report: R@1/R@3/R@5/R@10/R@20/R@50
  all `25/25 = 1.0000`. Baseline ladder for the same 25 cases was R@1
  `12/25 = 0.4800`, R@3 `18/25 = 0.7200`, R@5 `21/25 = 0.8400`, R@10
  `23/25 = 0.9200`, R@20 `24/25 = 0.9600`, and R@50 `24/25 = 0.9600`.
- Context-visible rescue conversion: `2/2`; same-session wrong-line reduction:
  `2/2`; top-10 rerank regression count: `0`.
- Gold-rank bucket movement: not retrieved to rank 1 `1`, rank 11-20 to rank 1
  `1`, rank 6-10 to rank 1 `2`, rank 4-5 to rank 1 `3`, rank 2-3 to rank 1
  `6`, and rank 1 stayed rank 1 `12`.
- Per-case-type coverage in this pilot is narrow: all `25` cases are
  `longmemeval_single-session-user`. That is useful for debugging the arm, but
  it is not enough to claim per-type quality across the full LongMemEval-S mix.
- Source-joined bridge lifts: `2`; reranker candidate evidence coverage:
  `25/25`; average candidate count: `54.32`.
- Reranker availability: `24/25`; one case timed out; warning count `0`.
- Token / latency / cache telemetry: `225170` total tokens
  (`212482` prompt, `12688` completion); DeepSeek prefix-cache hit tokens
  `75392`, miss tokens `137090`, hit rate `0.3548`; latency count `24`,
  average `7156.27ms`, max `29434.87ms`.
- Provider dollar cost: unavailable in the chat-completions response; the
  report records usage/cache/latency instead.
- 500-question projection from the 25Q pilot: about `4503400` total tokens,
  `1507840` projected prompt-cache hit tokens, `2741800` projected prompt-cache
  miss tokens, and `59.64` single-worker minutes at the observed average
  available-call latency. Because provider dollar cost is not reported and the
  arm sends public benchmark question/candidate source text to an external
  model, the full 500Q semantic run is explicit opt-in only. Required before a
  full run: operator budget approval, a provider cost model or ceiling, privacy
  review for external candidate source text, and a gitignored partial-output
  path.
- Raw report location:
  `benchmark_corpus/reports/longmemeval-v1-small-semantic-pilot-25.json`
  locally, intentionally gitignored.
- Decision: the semantic arm remains useful and reproducible, but the full
  500Q LLM rerank is not run by default. The current #1092 result is a bounded
  pilot plus explicit budget/latency/privacy boundary, not a 500-question LLM
  quality claim.

This retires the 2026-06-09 incomplete 500-question missing-artifact attempt:
the current blocker is no longer completion. The remaining LongMemEval gap is
quality: even with the optional lexical reranker, exact evidence-line ranking
is still weaker than source-window routing.

Earlier 100-question LongMemEval-S verification summary:

- Dataset file: `longmemeval_s_cleaned.json`
- Bytes: `277383467`
- SHA-256: `d6f21ea9d60a0d56f34a05b609c79c88a451d2ae03597821ea3d5a9678c3a442`
- Total runner time: `126.72s`
- Questions: `100`
- Case mix: `70` single-session-user and `30` multi-session cases.
- Evidence-line cases: `94`
- Top-k: `10`
- Evidence context radius: `5`
- Session R@10: `97/100`, Wilson 95% CI `0.9155..0.9897`
- Evidence-line R@10: `82/94`, Wilson 95% CI `0.7900..0.9254`
- Context-visible evidence R@10: `91/94`, Wilson 95% CI
  `0.9103..0.9891`
- MRR: session `0.8749`, evidence-line `0.6481`,
  context-visible evidence `0.8233`
- Evidence context rescued top-10 cases: `9`
- Evidence context improved cases: `36`
- Warning count: `0`
- Evaluator model / API: none; deterministic retrieval-only run.
- Raw report location: `benchmark_corpus/reports/longmemeval-v1-small-retrieval-100.json`
  locally, intentionally gitignored.

2026-06-10 exact-line taxonomy addendum for #1087:

- Re-run command used the same public split, 100-question cap, top-k `10`, and
  evidence context radius `5`; the sanitized local report was written to a
  gitignored `.tmp` path and did not emit raw LongMemEval questions, answers,
  snippets, local absolute paths, or source text.
- Evidence-line recall ladder: R@1 `49/94 = 0.5213`, R@3
  `69/94 = 0.7340`, R@5 `76/94 = 0.8085`, R@10
  `82/94 = 0.8723`, R@20 `85/94 = 0.9043`, and R@50
  `89/94 = 0.9468`.
- Evidence rank buckets: rank 1 `49`, rank 2-3 `20`, rank 4-5 `7`,
  rank 6-10 `6`, rank 11-20 `3`, rank 21-50 `4`,
  below rank 50 `3`, and not retrieved `2`.
- Top-10 line taxonomy: exact line found `62`, multi-evidence partial hit
  `20`, context-visible exact-line miss `9`, same-session wrong-line top-10
  `1`, session found below top-k `1`, and gold line low-ranked at 21-50 `1`.
- The 12 exact-line R@10 misses break down as: context-visible exact-line miss
  `9`, session found below top-k `1`, same-session wrong-line top-k `1`, and
  gold line low-ranked at 21-50 `1`.
- The 9 context-visible rescues were near the exact evidence line: distance 1
  `6`, distance 2-to-context-radius `3`.

Product interpretation: the current adapter is strong at source-window and
reopenable-route navigation, but exact evidence-line citation remains a real
improvement area. Most exact-line misses are not total retrieval failures: they
are nearby source-window hits or line-ranking misses. Do not treat
context-visible evidence as equivalent to exact-line retrieval; it means the
foreground agent can usually reopen the right source window, not that a final
citation span is already selected.

Historical note: the 2026-06-09 attempt to run a 500-question LongMemEval-S
diagnostic stopped without stdout, stderr, or an output report. The 2026-06-10
completed run above supersedes that blocker and confirms the progress /
partial-output path is sufficient for this local diagnostic.

Earlier 50-question LongMemEval-S verification summary:

- Dataset file: `longmemeval_s_cleaned.json`
- Bytes: `277383467`
- SHA-256: `d6f21ea9d60a0d56f34a05b609c79c88a451d2ae03597821ea3d5a9678c3a442`
- Download time: `13.48s`
- Total runner time: `167.65s`
- Evaluator model / API: none; deterministic retrieval-only run.
- Evidence context radius: `5`
- Evidence context rescued top-10 cases: `4`
- Raw report location: `benchmark_corpus/reports/longmemeval-v1-small-retrieval-50.json` locally, intentionally gitignored.

Oracle smoke verification summary:

- Dataset file: `longmemeval_oracle.json`
- Bytes: `15388478`
- SHA-256: `821a2034d219ab45846873dd14c14f12cfe7776e73527a483f9dac095d38620c`
- Evidence context radius: `5`
- Evidence context rescued top-10 cases: `2`
- Raw report location: `benchmark_corpus/reports/longmemeval-v1-oracle-retrieval-50.json` locally, intentionally gitignored.

These results support bounded V1 retrieval-only source-evidence claims for
LongMemEval-S and the oracle smoke split. They do not support answer-generation
quality, judge-model scores, V2 quality, SOTA comparisons, or decision-gate
quality.

## Report Shape

Reports have `kind: aippocampus_longmemeval_benchmark` and include:

- `benchmark`: official URLs, split name, dataset version, local path hash, and
  checksum verification.
- `evaluation`: retrieval-only mode, top-k settings, and the explicit absence
  of QA generation or judge model.
- `metrics`: question count, session recall@K, source-line recall@K,
  context-visible source-line recall, MRR where available, rank-bucket
  diagnostics, exact-line recall ladders, and sanitized miss taxonomy counts.
- `provider_execution_budget`: present for live/provider reranker runs; records
  declared caps, completed/skipped/failed/timed-out units, elapsed time,
  token/cache usage, estimated cost or unavailable reason, stop reason, and
  preflight validation errors.
- `cases`: sanitized per-case rows with hashed ids and no raw LongMemEval text.
- `cannot_claim`: legacy compatibility boundary field for QA, judge-model, V2,
  SOTA, and broad-comparison limits.

Answer reports have `kind: aippocampus_longmemeval_answer_benchmark` and
include:

- `evaluation.reader`: fixed prompt version, provider/model/base-url hash,
  cache policy, API-key environment variable name, and input/output boundaries.
- `retrieval`: the existing session/source-line/source-window metrics and
  corpus counts.
- `answer`: deterministic local answer metrics and failure taxonomy counts,
  without raw reader answer text.
- `latency`, `token_usage`, `reader_cache`, and `cost`: measured separately
  from retrieval quality and answer correctness.
- `sanitized_report_validation`: absolute-path, raw-text, and credential-like
  string checks that must pass before the report can be used.
- `cannot_claim`: legacy compatibility boundary field for official leaderboard
  score, official judge score, V2, LoCoMo, PersonaMem, SOTA, private-history
  quality, and default reader/provider adoption limits.

V2 mapping reports have
`kind: aippocampus_longmemeval_v2_context_mapping` and include:

- `benchmark`: official V2 URLs, license, local file path hashes, byte counts,
  and SHA-256 values when available.
- `schema_observation`: field/domain/environment/question-type counts only.
- `metrics`: join-key coverage, environment-pool coverage, ambiguity rate, and
  evidence-ref availability.
- `decision`: whether source-evidence, context-gathering, and answer-generation
  scoring are supported, diagnostic-only, or not run.
- `cases`: hashed case ids with domain, environment family, question type,
  mapping status, and candidate counts only.
- `cannot_claim`: legacy compatibility boundary field for V2 source-evidence hit
  rate, MRR, answer accuracy, LAFS, SOTA, and benchmark-grade
  context-gathering score limits.

V2 official-pilot decision reports have
`kind: aippocampus_longmemeval_v2_official_pilot_decision` and include:

- `decision`: the tiny official answer/latency pilot route, default and hard
  maximum question counts, and the run-order checklist.
- `official_harness_contract`: upstream Memory API method shape, required
  input files, fixed reader/evaluator configuration, and expected output
  layers.
- `adapter_contract`: local `aippocampus_context_provider` Memory adapter
  boundary and ignored official-checkout integration path.
- `metric_separation`: memory-context quality, answer accuracy,
  reader/evaluator dependency, and memory-query latency as separate layers.
- `privacy_and_artifact_policy`: ignored local official checkout/data/output
  policy plus sanitized aggregate-only publication requirements.
- `cannot_claim`: legacy compatibility boundary field for V2 answer accuracy,
  LAFS, leaderboard readiness, SOTA, source-evidence R@K/MRR, and broad
  memory-superiority limits.

When a future run changes what the project can claim, update
[`stage-0-5-readiness.md`](../readiness/stage-0-5-readiness.md). If it only records a dated
run, update this page and keep
[`benchmark-evidence-map.md`](../benchmark-evidence-map.md) as a pointer map.
