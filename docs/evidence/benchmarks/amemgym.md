# AMemGym Adapter Boundary

This page is the AIppocampus evidence owner for GitHub #733. It records what
the AMemGym adapter can inspect today, what source-backed overlay metrics mean,
and what remains out of scope before any official or comparative score can be
quoted.

Decision: suitable as a staged external benchmark adapter, but not as an
official AMemGym score runner yet. The repository now has a deterministic,
public-safe metadata smoke for the public `v1.base` JSON plus a local
prediction-overlay smoke that keeps native answer accuracy, write/read
diagnosis, utilization, source-backed fidelity, cost/latency, and public claim
boundaries separate.

## Official Sources

- Paper: <https://arxiv.org/abs/2603.01966>
- OpenReview: <https://openreview.net/forum?id=sfrVLzsmlf>
- Repository: <https://github.com/AGI-Eval-Official/amemgym>
- Dataset: <https://huggingface.co/datasets/AGI-Eval/AMemGym>
- Public `v1.base` JSON: <https://huggingface.co/datasets/AGI-Eval/AMemGym/raw/main/v1.base/data.json>
- `v1.base` environment config: <https://raw.githubusercontent.com/AGI-Eval-Official/amemgym/main/configs/env/v1.base.json>

Verified source facts on 2026-06-05:

- The public Hugging Face dataset exposes `default` / `v1.base` as JSON with 20
  rows and top-level fields `id`, `start_time`, `user_profile`,
  `state_schema`, `periods`, and `qas`.
- The official `v1.base` config records 20 user profiles, 10 questions, 10
  evolution periods, two states per question, four changes per period, and seed
  42.
- The official repository describes four agent arms: Native, RAG, AWI, and AWE.
- The default official metric list currently enables `accuracy`; `hamming` and
  `jaccard` exist in the metric code but are not in the default metric list.
- The official diagnosis path writes `write_failure`, `read_failure`, and
  `memory_success`. Utilization is owned by the upper-bound/utilization path,
  so AIppocampus must not pretend `utilization_failure` is a native diagnosis
  output.

Local download smoke on 2026-06-05:

```powershell
python benchmarks\aippocampus\benchmark_amemgym.py --download-official --skip-sha256 --json
```

The sanitized report observed 20 rows, 220 periods, 943 sessions, zero messages
inside those sessions, 1206 updates, 200 QAs, 882 answer choices, and the
expected top-level field shape. This is schema evidence only; it is not an
AMemGym score.

## Runner

The adapter lives at `benchmarks/aippocampus/benchmark_amemgym.py` with source
metadata in `benchmark_corpus/amemgym_manifest.json`.

Fresh clones can run the missing-dataset boundary without network:

```powershell
python benchmarks\aippocampus\benchmark_amemgym.py --json
```

To inspect the public `v1.base` JSON, download it into the ignored local data
directory:

```powershell
python benchmarks\aippocampus\benchmark_amemgym.py --download-official --skip-sha256 --json
```

To exercise the source-backed overlay metrics on the checked-in public fixture:

```powershell
python benchmarks\aippocampus\benchmark_amemgym.py --dataset-path benchmark_corpus\amemgym_fixture\fixture.json --predictions benchmark_corpus\amemgym_fixture\predictions.jsonl --prediction-template-output .tmp\amemgym-predictions-template.jsonl --json
```

The default report emits only schema counts, case ids, hashes, local file
hashes, field histograms, layer names, and `cannot_claim` boundaries. It does
not emit raw profile text, session/query text, answer text, downloaded dataset
rows, local absolute paths, provider keys, or model outputs.

Downloaded official data belongs under the ignored
`benchmark_corpus/amemgym/` directory. Generated reports and prediction
templates belong under `.tmp/` or `benchmark_corpus/reports/`.

## Metric Layers

Keep these layers separate:

| Layer | Current adapter support | Not the same as |
| --- | --- | --- |
| AMemGym native score | Local exact answer-choice match only when an explicit prediction JSONL is supplied. | Official AMemGym leaderboard score or official runner compatibility. |
| Official diagnosis | The adapter can carry operator prediction flags for write/read failures, but it does not parse official diagnosis logs yet. | A verified `amemgym.eval.diagnosis` result. |
| Utilization | `utilization_failure_rate` is an AIppocampus overlay flag in the local prediction JSONL. | Official diagnosis output; utilization belongs to the official upper-bound/utilization path. |
| Source-backed overlay | `source_reopen_success`, `current_state_source_hit`, `stale_state_as_current_rate`, `unsupported_personalization_rate`, `scent_as_evidence_rate`, and `answer_correct_but_unsupported_rate`. | Native accuracy, answer quality, or SOTA. |
| Cost/latency | `elapsed_ms` for this deterministic local helper only. | Model/provider cost, official AMemGym run cost, or live user latency. |

The checked-in fixture deliberately includes one current-vs-stale control, one
unsupported-personalization control, and one local utilization/read/write
failure flag so the report shape cannot collapse into a single accuracy number.

## Claim Boundary

Can claim now:

- AIppocampus has a deterministic AMemGym metadata smoke that can read the
  public `v1.base` JSON with the Python standard library.
- The repository has a public-safe fixture and local prediction-overlay path
  for source-backed AMemGym-style diagnostics.
- Reports separate native answer-choice exact match, source-backed overlay
  fidelity, diagnosis-like flags, utilization overlay flags, cost/latency, and
  public claim boundaries.

Cannot claim now:

- AIppocampus has an official AMemGym score.
- AIppocampus is compatible with the official AMemGym runner.
- AIppocampus has evaluated or beaten Native, RAG, AWI, AWE, Mem0, or any other
  official/external baseline on AMemGym.
- The local overlay metrics are official AMemGym accuracy.
- The structured LLM-simulated AMemGym users prove real human life-wide
  continuity.
- `utilization_failure_rate` is an official diagnosis output.

## Deferred Work

Full official-runner compatibility needs a separate issue or follow-up slice
that installs the official environment, fixes model/provider versions, records
cost/latency, and runs Native/RAG/AWI/AWE arms without leaking raw rows or
keys.

The commentary/action-summary write-material arm is deliberately deferred to
the source-backed situation/work-material design work in #701 and #703. That
arm should only be added after the producer/consumer contract says which
source-backed action summaries can be written, reopened, demoted as stale, and
excluded from over-personalization.
