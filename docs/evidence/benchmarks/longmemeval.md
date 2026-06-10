# LongMemEval Evidence

This page is the stable entrypoint for AIppocampus LongMemEval work. It keeps
dataset provenance, commands, current metrics, and claim boundaries together so
a benchmark run remains visible after the raw report stays local.

## Boundary

LongMemEval is an external public benchmark for long-term interactive memory.
AIppocampus currently has a deterministic retrieval-only adapter for the
official cleaned V1 files. It checks whether the expected answer session and
source lines are retrievable; it does not generate answers or run an LLM judge.
LongMemEval-V2 is tracked separately as a context-gathering mapping pilot: it
can inspect the public V2 schema and local files, but it cannot report
source-evidence R@K/MRR or answer accuracy without upstream gold evidence refs
and the official reader/evaluator harness.

Use this page to answer:

- Which LongMemEval split was run?
- Which exact dataset file and checksum were used?
- Which command reproduced the result?
- Which retrieval metrics can be claimed, and which QA claims stay out of
  bounds?

Do not use this page to claim SOTA, answer-generation quality,
LongMemEval-V2 quality, or broad memory superiority from one retrieval or
mapping run.

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

`--progress-every` emits sanitized JSONL progress to stderr. `--partial-output`
writes a sanitized checkpoint/partial diagnostic with hashed local-path
identity, phase, built/evaluated counts, elapsed time, and claim boundaries; it
does not include raw LongMemEval questions, answers, snippets, or local paths.

Generated dataset files and reports stay ignored by default. Do not commit full
LongMemEval downloads or generated JSON reports unless a future change promotes
a small curated artifact with provenance and license notes.

## Current Published Result

| Date | Split | Mode | Questions | Session R@10 | Evidence-line R@10 | Context-visible evidence R@10 | Runtime | Status |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| `2026-06-10T03:33:49Z` | `longmemeval-v1-small` | retrieval-only larger slice | 500 | 95.80% | 85.18% | 94.36% | 803.10s | `retrieval_sufficient` |
| `2026-06-09T14:08:17Z` | `longmemeval-v1-small` | retrieval-only larger slice | 100 | 97.00% | 87.23% | 96.81% | 126.72s | `retrieval_sufficient` |
| `2026-05-30T17:05:34Z` | `longmemeval-v1-small` | retrieval-only | 50 | 100.00% | 92.00% | 100.00% | 167.65s | `retrieval_sufficient` |
| `2026-05-30T16:47:41Z` | `longmemeval-v1-oracle` | retrieval-only smoke | 50 | 100.00% | 96.00% | 100.00% | not recorded | `retrieval_sufficient` |

Fresh reproduction commands:

```powershell
python benchmarks\aippocampus\benchmark_longmemeval.py --split longmemeval-v1-oracle --download --questions 50 --min-questions 20 --top-k 10 --output benchmark_corpus\reports\longmemeval-v1-oracle-retrieval-50.json
python benchmarks\aippocampus\benchmark_longmemeval.py --split longmemeval-v1-small --download --questions 50 --min-questions 20 --top-k 10 --output benchmark_corpus\reports\longmemeval-v1-small-retrieval-50.json
python benchmarks\aippocampus\benchmark_longmemeval.py --split longmemeval-v1-small --download --questions 100 --min-questions 100 --top-k 10 --output benchmark_corpus\reports\longmemeval-v1-small-retrieval-100.json
python benchmarks\aippocampus\benchmark_longmemeval.py --split longmemeval-v1-small --download --questions 500 --min-questions 100 --top-k 10 --progress-every 25 --partial-output benchmark_corpus\reports\longmemeval-v1-small-retrieval-500.partial.json --output benchmark_corpus\reports\longmemeval-v1-small-retrieval-500.json
```

LongMemEval-S 500-question verification summary:

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

This retires the 2026-06-09 incomplete 500-question missing-artifact attempt:
the current blocker is no longer completion. The remaining LongMemEval gap is
quality: exact evidence-line ranking is weaker than source-window routing.

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
- `cases`: sanitized per-case rows with hashed ids and no raw LongMemEval text.
- `cannot_claim`: QA, judge-model, V2, SOTA, and broad-comparison boundaries.

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
- `cannot_claim`: V2 source-evidence hit rate, MRR, answer accuracy, LAFS, SOTA,
  and benchmark-grade context-gathering score boundaries.

When a future run changes what the project can claim, update
[`stage-0-5-readiness.md`](../readiness/stage-0-5-readiness.md). If it only records a dated
run, update this page and keep
[`benchmark-evidence-map.md`](../benchmark-evidence-map.md) as a pointer map.
