# MemoryAgentBench Feasibility

This page is the feasibility closeout for GitHub #258. It decides whether
MemoryAgentBench should become an AIppocampus external benchmark adapter before
any runner code is added.

Decision: suitable as a staged benchmark family, but not as an immediate
default runner. The first AIppocampus slice should be a deterministic,
public-safe metadata and case-pack smoke. Full incremental runner support is
deferred until the write/update/forgetting contracts can be measured without
collapsing the benchmark into static retrieval.

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

Add a small runner that inspects local MemoryAgentBench files only after the
operator downloads them. It should emit:

- dataset source URLs, license, local path hashes, byte counts, and checksums;
- split and row counts;
- observed fields, task families, and metric families;
- whether each split can support AIppocampus source-evidence, answer,
  write-policy, or conflict-resolution scoring;
- `cannot_claim` boundaries.

No model calls, provider keys, full contexts, raw questions, or answers should
be emitted. This stage is a public-boundary and schema-readiness smoke, not a
quality benchmark.

### Stage 2: Public-Safe Case-Pack Projection

Build a prediction-template format for one narrow subset, preferably Accurate
Retrieval or Conflict Resolution. The case pack should give the system under
test only the permitted interaction/context payload and blank prediction slots.
It should keep gold answers, gold labels, and scoring-only metadata out of the
model-facing input.

Reports should separate:

- memory ingestion/update state;
- source or context gathering;
- answer generation;
- source citation or refusal;
- judge/model-assisted scoring when present.

### Stage 3: Incremental Runner

Only after Stage 2 proves the boundary, add an incremental evaluation harness
that can replay insert/query/update interactions. This is where Test-Time
Learning and Conflict Resolution become meaningful. The harness must report the
memory write/update mode and whether AIppocampus is being used as retrieval
only, source-backed memory, or a full agent memory substrate.

### Stage 4: Comparative Runs

Comparable scores require fixed model/provider versions, cost and latency
accounting, no-memory and closed-book controls, and clear separation between
AIppocampus retrieval/source evidence and downstream answer model quality.

## Blockers Before Scoring

- The current repository has no MemoryAgentBench runner or manifest.
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
- The first implementation should be a deterministic metadata/case-pack smoke,
  not a full runner.

Cannot claim now:

- AIppocampus has a MemoryAgentBench score.
- AIppocampus is compatible with the official MemoryAgentBench runner.
- AIppocampus beats RAG, long-context agents, Mem0, Letta, Cognee, or any
  official baseline.
- Static retrieval results would represent Test-Time Learning, Conflict
  Resolution, or selective forgetting.
- LLM-as-judge outputs are source truth.

## Follow-Up Implementation Issue Scope

Follow-up implementation is tracked in #608. It should be scoped to Stage 1
and Stage 2 only:

- add `benchmark_corpus/memoryagentbench_manifest.json` with official source
  URLs, license, local ignored path policy, and expected checksums once local
  files are downloaded;
- add `benchmarks/aippocampus/benchmark_memoryagentbench.py` or a staged helper
  that emits schema/metadata observations without raw text;
- add tests for public-safe report shape, license/checksum metadata,
  `cannot_claim` boundaries, and no raw question/answer/context leakage;
- update `docs/evidence/benchmark-evidence-map.md` only after the runner exists,
  so the map does not point to a non-existent executable surface.

Non-goals for that follow-up:

- no official-score claim;
- no default CI download of external data;
- no provider/API-key dependency in deterministic tests;
- no merged retrieval/generation/judge metric.
