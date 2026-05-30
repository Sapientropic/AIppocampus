# LongMemEval Evidence

This page is the stable entrypoint for AIppocampus LongMemEval work. It keeps
dataset provenance, commands, current metrics, and claim boundaries together so
a benchmark run remains visible after the raw report stays local.

## Boundary

LongMemEval is an external public benchmark for long-term interactive memory.
AIppocampus currently has a deterministic retrieval-only adapter for the
official cleaned V1 files. It checks whether the expected answer session and
source lines are retrievable; it does not generate answers or run an LLM judge.

Use this page to answer:

- Which LongMemEval split was run?
- Which exact dataset file and checksum were used?
- Which command reproduced the result?
- Which retrieval metrics can be claimed, and which QA claims stay out of
  bounds?

Do not use this page to claim SOTA, answer-generation quality, LongMemEval-V2
quality, or broad memory superiority from one retrieval run.

## Official Sources

- Paper: <https://arxiv.org/abs/2410.10813>
- Repository: <https://github.com/xiaowu0162/LongMemEval>
- Cleaned dataset: <https://huggingface.co/datasets/xiaowu0162/longmemeval-cleaned>
- Local manifest: [`benchmark_corpus/longmemeval_manifest.json`](../../benchmark_corpus/longmemeval_manifest.json)

The runner pins Hugging Face LFS content SHA-256 values, not the HTTP `ETag`
header shown by the resolved download URL. The LFS `oid` is the value that
matches the downloaded file hash.

## Dataset Splits

| Runner split | File | Bytes | LFS content SHA-256 | Intended use |
| --- | --- | ---: | --- | --- |
| `longmemeval-v1-oracle` | `longmemeval_oracle.json` | 15,388,478 | `821a2034d219ab45846873dd14c14f12cfe7776e73527a483f9dac095d38620c` | Small smoke and oracle-evidence debugging. |
| `longmemeval-v1-small` | `longmemeval_s_cleaned.json` | 277,383,467 | `d6f21ea9d60a0d56f34a05b609c79c88a451d2ae03597821ea3d5a9678c3a442` | First comparable public split. |
| `longmemeval-v1-medium` | `longmemeval_m_cleaned.json` | 2,737,100,077 | `9d79e5524794a2e6900a3aa9cb7d9152c5a3e8319c9a87c25494ba1eacee495f` | Large-context stress split. |

LongMemEval-V2 is a separate agentic-context benchmark. This V1
source-evidence adapter intentionally reports V2 as out of scope instead of
assigning fake source-retrieval scores.

## Commands

Let the dedicated runner download and verify a pinned split:

```powershell
python benchmarks\aippocampus\benchmark_longmemeval.py --split longmemeval-v1-oracle --download --questions 50 --min-questions 20 --top-k 10 --output benchmark_corpus\reports\longmemeval-v1-oracle-retrieval-50.json
```

Run the comparable LongMemEval-S retrieval slice after the S file is available:

```powershell
python benchmarks\aippocampus\benchmark_longmemeval.py --split longmemeval-v1-small --download --questions 50 --min-questions 20 --top-k 10 --output benchmark_corpus\reports\longmemeval-v1-small-retrieval-50.json
```

For a larger local diagnostic:

```powershell
python benchmarks\aippocampus\benchmark_longmemeval.py --split longmemeval-v1-small --download --questions 500 --min-questions 100 --top-k 10 --output benchmark_corpus\reports\longmemeval-v1-small-retrieval-500.json
```

Generated dataset files and reports stay ignored by default. Do not commit full
LongMemEval downloads or generated JSON reports unless a future change promotes
a small curated artifact with provenance and license notes.

## Current Published Result

| Date | Split | Mode | Questions | Session R@10 | Evidence-line R@10 | Context-visible evidence R@10 | Runtime | Status |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| `2026-05-30T17:05:34Z` | `longmemeval-v1-small` | retrieval-only | 50 | 100.00% | 92.00% | 100.00% | 167.65s | `retrieval_sufficient` |
| `2026-05-30T16:47:41Z` | `longmemeval-v1-oracle` | retrieval-only smoke | 50 | 100.00% | 96.00% | 100.00% | not recorded | `retrieval_sufficient` |

Fresh reproduction command:

```powershell
python benchmarks\aippocampus\benchmark_longmemeval.py --split longmemeval-v1-oracle --download --questions 50 --min-questions 20 --top-k 10 --output benchmark_corpus\reports\longmemeval-v1-oracle-retrieval-50.json
python benchmarks\aippocampus\benchmark_longmemeval.py --split longmemeval-v1-small --download --questions 50 --min-questions 20 --top-k 10 --output benchmark_corpus\reports\longmemeval-v1-small-retrieval-50.json
```

LongMemEval-S verification summary:

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
  context-visible source-line recall, and MRR where available.
- `cases`: sanitized per-case rows with hashed ids and no raw LongMemEval text.
- `cannot_claim`: QA, judge-model, V2, SOTA, and broad-comparison boundaries.

When a future run changes what the project can claim, update
[`stage-0-5-readiness.md`](stage-0-5-readiness.md). If it only records a dated
run, update this page and keep
[`benchmark-evidence-map.md`](benchmark-evidence-map.md) as a pointer map.
