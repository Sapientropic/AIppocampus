# MemoryAgentBench Feasibility

This page is the feasibility closeout for GitHub #258. It decides whether
MemoryAgentBench should become an AIppocampus external benchmark adapter before
any runner code is added.

Decision: suitable as a staged benchmark family, but not as an immediate
official-score runner. AIppocampus now has a deterministic, public-safe
metadata and case-pack smoke for Stage 1/2, plus an explicit Stage 3 contract
harness that separates ingest, write/update, retrieval, generation, and judging
modes. Stage 3 now has a deterministic local apply-instrumented slice for
write/update and stale/currentness controls. Full quality/scoring support is
still deferred until answer generation, judging, and official-runner
compatibility can be measured without collapsing the benchmark into static
retrieval.

## Official Sources

- Paper: <https://arxiv.org/abs/2507.05257>
- OpenReview: <https://openreview.net/forum?id=DT7JyQC3MR>
- Repository: <https://github.com/HUST-AI-HYZ/MemoryAgentBench>
- Dataset: <https://huggingface.co/datasets/ai-hyz/MemoryAgentBench>

Verified source facts on 2026-06-03:

- The paper was submitted to arXiv on 2025-07-07 and revised as v3 on
  2026-03-17.
- OpenReview lists the paper as an ICLR 2026 poster, published on 2026-01-26
  and last modified on 2026-05-14.
- The official repository is MIT licensed and describes code for evaluating
  memory-capable agents.
- The Hugging Face dataset card lists an MIT license, 146 rows, and four
  splits: Accurate Retrieval, Test-Time Learning, Long-Range Understanding, and
  Conflict Resolution.
- The paper and dataset naming differ slightly around the forgetting/conflict
  surface: the benchmark direction covers selective forgetting / conflict
  resolution, but AIppocampus should preserve the upstream split name used by
  each artifact instead of silently treating them as identical labels.

Do not commit downloaded dataset rows or generated MemoryAgentBench reports
until a future adapter issue defines checksums, sanitization, and local artifact
policy.

## What It Tests

MemoryAgentBench is relevant because it evaluates memory-agent behavior through
incremental multi-turn interactions rather than only asking a static retrieval
question over a fixed context. The official materials define four competencies:

| Competency | AIppocampus mapping | Adapter implication |
| --- | --- | --- |
| Accurate Retrieval | Source-evidence retrieval, H1 pattern completion, and source reopen. | Closest to existing Track B and hippocampal recall surfaces, but still needs source-ref mapping. |
| Test-Time Learning | Ingest/update semantics, decision-shadow capture, and live correction handling. | Requires write-policy and update-state instrumentation, not just retrieval scoring. |
| Long-Range Understanding | Timeline, relational, and codebase-map style memory. | Can align with public longitudinal and H3/H4 benchmark directions. |
| Conflict Resolution / Selective Forgetting | Superseded conclusions, correction reconsolidation, and selective forgetting. | Requires explicit stale/currentness and false-forgetting controls, while preserving the upstream split/metric label used by each artifact. |

The official benchmark also includes task families with different metric
shapes: substring exact match, exact match, Recall@5, and LLM-as-judge paths.
An AIppocampus adapter must keep these layers separate.

## Fit With Existing Evidence

MemoryAgentBench should not replace current AIppocampus benchmark tracks.

- LongMemEval V1 remains the current public retrieval-only source/session
  evidence control.
- LongMemEval V2 remains a diagnostic context-mapping pilot until explicit
  evidence labels and an official reader/evaluator harness are wired.
- LoCoMo remains a same-conversation public control, not proof of cross-thread
  or life-wide memory.
- Public longitudinal VCS and rollout fixtures remain the better path for
  coding-agent tacit constraints and future-event memory.
- Hippocampal recall-discrimination remains the source-backed H1/H2 fixture
  family for degraded cues and interference separation.

MemoryAgentBench is valuable as a bridge across those surfaces because it asks
whether an agent can learn, update, retrieve, understand long-range context, and
resolve conflicts across incremental interactions. That makes it too broad for
a shallow one-command wrapper.

## Minimum Credible Adapter Plan

### Stage 0: Feasibility Intake

Status: complete in this document.

The repository may cite MemoryAgentBench as a planned external benchmark
candidate with an accepted staged direction. It still cannot claim any score,
compatibility, or fairness result.

### Stage 1: Deterministic Metadata Smoke

Status: implemented by
`benchmarks/aippocampus/benchmark_memoryagentbench.py` with source metadata in
`benchmark_corpus/memoryagentbench_manifest.json`.

The runner inspects local MemoryAgentBench files only after the operator
downloads or exports them. It emits:

- dataset source URLs, license, local path hashes, byte counts, and checksums;
- split and row counts;
- observed fields, task families, and metric families;
- whether each split can support AIppocampus source-evidence, answer,
  write-policy, or conflict-resolution scoring;
- `cannot_claim` boundaries.

No model calls, provider keys, full contexts, raw questions, or answers should
be emitted. This stage is a public-boundary and schema-readiness smoke, not a
quality benchmark.

Fresh clones can run:

```powershell
python benchmarks\aippocampus\benchmark_memoryagentbench.py --json
```

When the ignored local dataset directory is absent, the runner returns a
`skipped_missing_dataset` metadata payload with the official split expectations
and `cannot_claim` boundaries. For local JSON/JSONL exports, it observes row
and field families. For official parquet files, it reports file metadata and
can read parquet rows into the same metadata/case-pack/Stage 3 dry-run paths
when the optional `pyarrow` reader is installed. If parquet files are present
but the reader is unavailable, the status is
`found_files_missing_optional_reader` with a `parquet_optional_reader_missing`
next-step hint instead of pretending the dataset is absent. No parquet
dependency is required by the deterministic smoke lane.

### Stage 2: Public-Safe Case-Pack Projection

Status: implemented for an explicit local-only case-pack output, defaulting to
the Accurate Retrieval split.

The case-pack path is opt-in:

```powershell
python benchmarks\aippocampus\benchmark_memoryagentbench.py --case-pack-output .tmp\memoryagentbench-case-pack.json --prediction-template-output .tmp\memoryagentbench-predictions.jsonl --json
```

The case pack gives the system under test the permitted context/question
payload and blank prediction slots. It keeps gold answers, gold labels, and
scoring-only metadata out of the model-facing input. Because it may contain raw
benchmark text, keep it under `.tmp/` or `benchmark_corpus/reports/`, both of
which are ignored local artifact locations.

For the official parquet dataset, this path no longer requires a manual JSONL
export when `pyarrow` is installed. The runner still treats fields such as
`answers` as both raw/sensitive text and gold-label material, so they remain out
of the model-facing case pack and default reports.
If local files are present but the optional parquet reader is missing, requested
case-pack or prediction-template paths are reported as `skipped_no_rows` rather
than written; empty artifacts should not be read as a successful adapter path.

Reports should separate:

- memory ingestion/update state;
- source or context gathering;
- answer generation;
- source citation or refusal;
- judge/model-assisted scoring when present.

### Stage 3: Incremental Runner

Status: first dry-run contract harness implemented by #614, with a deterministic
local apply-instrumented slice added by #995.

The runner can now embed a sanitized Stage 3 dry-run report:

```powershell
python benchmarks\aippocampus\benchmark_memoryagentbench.py --stage3-incremental-dry-run --stage3-write-update-mode dry_run_contract --json
```

The Stage 3 report names these modes separately:

- ingest mode;
- write/update mode;
- retrieval mode;
- answer-generation mode;
- judging/scoring mode.

It reads only local operator-provided MemoryAgentBench files and emits case ids,
hashes, split counts, mode fields, and update/conflict interaction counts. It
does not emit raw context, questions, answers, labels, local paths, model calls,
or scores. When write/update instrumentation is not explicitly selected, the
Stage 3 report fails closed as `unsupported_missing_write_update_instrumentation`
instead of pretending that static retrieval measured Test-Time Learning or
Conflict Resolution.

With `pyarrow` installed, the Stage 3 dry-run can collect its TTL/CR cases
directly from official parquet files. Without that optional reader, parquet-only
operator folders still report file presence and reader-missing diagnostics but
do not synthesize Stage 3 cases.

This is still a dry-run/protocol surface, not an official MemoryAgentBench
runner. Test-Time Learning and Conflict Resolution become quality evidence only
after an apply-capable adapter can perform real memory writes, updates,
retrieval, answer generation, false-forgetting controls, and scoring under a
documented local artifact policy.

The #995 apply-instrumented slice can be run explicitly:

```powershell
python benchmarks\aippocampus\benchmark_memoryagentbench.py --stage3-incremental-dry-run --stage3-write-update-mode local_apply_instrumented --json
```

This mode executes a local in-memory, hash-only write/update/retrieve probe for
Test-Time Learning and Conflict Resolution rows. It reports:

- `write_update_mode=local_apply_instrumented`;
- `retrieval_mode=local_apply_retrieve_probe`;
- apply write/update/retrieval-probe event counts;
- false-forgetting controls that retain prior versions as history;
- stale/currentness controls that retrieve the current version while keeping
  stale material demoted rather than deleted.

It still does not generate answers, call a model, invoke an LLM judge, expose
raw benchmark text, or claim official MemoryAgentBench runner compatibility.

### Stage 4: Comparative Runs

Comparable scores require fixed model/provider versions, cost and latency
accounting, no-memory and closed-book controls, and clear separation between
AIppocampus retrieval/source evidence and downstream answer model quality.

## Blockers Before Scoring

- The current repository has only a metadata/case-pack smoke, not an
  official-score runner.
- The official runner expects a separate Python environment and external model
  API keys for several paths.
- Some task families require LLM-as-judge evaluation, which cannot be treated
  as source truth.
- Dataset fields are not AIppocampus clean-source refs by default; a future
  adapter must map contexts and interaction chunks to source ids or explicit
  local-only case-pack handles.
- Test-Time Learning and Conflict Resolution need write/update/forgetting
  contracts. Static retrieval R@K would underfit the issue's goal.
- Large or raw benchmark artifacts must stay local/ignored unless a small
  public-safe subset is deliberately promoted with license and checksum notes.

## Claim Boundary

Can claim now:

- MemoryAgentBench is a relevant external benchmark candidate for incremental
  memory-agent evaluation.
- A staged adapter path is defined.
- The repository has a deterministic MemoryAgentBench metadata/case-pack smoke
  that reports public-safe schema observations, local file hashes, split/row
  expectations, support status by evaluation layer, and `cannot_claim`
  boundaries.
- The repository has a Stage 3 dry-run contract harness that reports explicit
  ingest/write-update/retrieve/generate/judge modes and fails closed when
  write/update instrumentation is missing.
- The repository has a deterministic Stage 3 local apply-instrumented slice
  that records hash-only write/update/retrieve events and false-forgetting /
  stale-currentness controls for Test-Time Learning and Conflict Resolution
  rows.
- Official parquet files can feed metadata, case-pack, and Stage 3 dry-run
  paths when the optional local `pyarrow` reader is installed; missing reader
  states are reported separately from missing datasets.

Cannot claim now:

- AIppocampus has a MemoryAgentBench score.
- AIppocampus is compatible with the official MemoryAgentBench runner.
- AIppocampus beats RAG, long-context agents, Mem0, Letta, Cognee, or any
  official baseline.
- Static retrieval results would represent Test-Time Learning, Conflict
  Resolution, or selective forgetting.
- LLM-as-judge outputs are source truth.

## Follow-Up Implementation Issue Scope

Follow-up implementation was tracked in #608 and is scoped to Stage 1 and
Stage 2 only:

- added `benchmark_corpus/memoryagentbench_manifest.json` with official source
  URLs, license, local ignored path policy, and expected checksums once local
  files are downloaded;
- added `benchmarks/aippocampus/benchmark_memoryagentbench.py`, a staged helper
  that emits schema/metadata observations without raw text;
- added tests for public-safe report shape, license/checksum metadata,
  `cannot_claim` boundaries, and no raw question/answer/context leakage;
- updated `docs/evidence/benchmark-evidence-map.md` after the executable runner
  existed, so the map does not point to a non-existent surface.

Non-goals for that follow-up:

- no official-score claim;
- no default CI download of external data;
- no provider/API-key dependency in deterministic tests;
- no merged retrieval/generation/judge metric.

Follow-up implementation tracked in #614 adds only the first Stage 3 dry-run
contract harness:

- added explicit mode fields for ingest, write/update, retrieval, answer
  generation, and judging;
- added sanitized update/conflict interaction skeletons for Test-Time Learning
  and Conflict Resolution rows;
- kept raw context/question/answer text, local paths, and gold labels out of
  the default Stage 3 report;
- made missing write/update instrumentation report `unsupported` instead of
  producing a misleading score.

Non-goals for #614:

- no official MemoryAgentBench score;
- no official-runner compatibility claim;
- no live model or provider dependency;
- no official or persistent AIppocampus memory writes;
- no claim that the dry-run harness measures user-visible memory quality.
