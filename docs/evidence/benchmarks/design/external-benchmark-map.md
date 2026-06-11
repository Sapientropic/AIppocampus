# External Benchmark Map

This page is the stable home for external benchmark and memory-system
comparison analysis. It records what each candidate can test, what AIppocampus
has in the repo today, and what remains blocked before any comparison can be
quoted as evidence.

It is not a leaderboard. Do not use this page to claim SOTA, broad competitor
superiority, official partner support, or product-quality proof.

Current hippocampal H1/H2/H5 diagnostic comparison:
[`hippocampal-cross-system-comparison-2026-06-04.md`](../hippocampal-cross-system-comparison-2026-06-04.md).
This table keeps local public-synthetic arms separate from missing-config
external adapters and does not claim external memory-system scores.

For the #528-specific multimodal source-shape map across HippoCamp, MemLens,
ATM-Bench, Ego-series episodic memory, UniDoc-Bench, PersonaVLM/Persona-MME,
Mem-Gallery, and MMRC, use
[`multimodal-memory-benchmark-map.md`](multimodal-memory-benchmark-map.md).

## Comparison Boundary

Every external comparison must name the layer it measures:

- source-evidence retrieval;
- answer generation or judge quality;
- memory write policy;
- compaction or long-context continuity;
- cross-session / cross-project user memory;
- hosted or local integration behavior;
- cost, privacy, or failure-mode behavior.

If two systems are tested on different layers, report them separately.

## Candidate Map

| Surface | Why it matters | Current AIppocampus path | Current status | Cannot claim yet |
| --- | --- | --- | --- | --- |
| LongMemEval V1 | Public long-memory QA family with source/session evidence variants. | Retrieval-only source/session slices and the fixed-reader answer/latency harness are tracked in [`../longmemeval.md`](../longmemeval.md) and the Track B standard retrieval-QA notes. | Retrieval/control surface implemented; answer harness implemented as opt-in diagnostic scaffold with no promoted provider score yet. | Official answer score, official judge score, SOTA, LongMemEval-V2 quality, or broad user-memory superiority. |
| LongMemEval V2 | Closer to agentic-context and workflow-memory evaluation. | Context-mapping pilot plus the tiny official-harness pilot decision and text-only Memory adapter contract are documented in [`../longmemeval.md`](../longmemeval.md); both keep raw V2 files and official outputs local/ignored. | Diagnostic mapping pilot implemented; official-harness pilot decision and adapter scaffold implemented; no dated official run or V2 score yet. | Comparable scores, source-evidence R@K/MRR, answer accuracy, LAFS, leaderboard readiness, or SOTA until a bounded official-harness run reports sanitized metrics with fixed reader/evaluator configuration. |
| AMemGym | Interactive memory benchmark with structured user profiles, state evolution, Native/RAG/AWI/AWE arms, and write/read/utilization failure analysis. | Public `v1.base` intake, deterministic metadata smoke, checked-in fixture, source-backed overlay metrics, the official-runner bridge with AIppocampus clean-source and semantic-sidecar `BaseAgent` arms, the `local-scripted` full-output protocol run, the [2026-06-09 live-provider blocker note](../amemgym-official-live-provider-blocker-2026-06-09.md), the [2026-06-11 #1232 route-blocker note](../amemgym-official-live-provider-1232-blocker-2026-06-11.md), and the separate Codex Desktop AMemGym-style three-arm contract are documented in [`../amemgym.md`](../amemgym.md). | Metadata and local overlay smoke implemented; official runner bridge and AIppocampus adapter arms exist; full public `v1.base` official-output discovery is proven for the deterministic no-provider protocol arm; the semantic-sidecar official arm can prepare visible-message working-memory / trigger / cue navigation surfaces before scoring. Live provider fixed-arm scores, official baseline parity arms, and clean isolated live Desktop arm results are explicitly blocked until complete bounded runs are produced and reviewed; #1232 shows the pinned OpenRouter Native condition is currently blocked because its required OpenAI-family routes fail harmless-prompt route preflight after provider-budget validation and account top-up, while non-OpenAI OpenRouter routes still work. AIppocampus Desktop arms also require trusted Codex hooks, observed hook notifications, and non-scored precache/warmup proof, not just a temporary `hooks.json`. | Live-model official AMemGym `v1.base` score, leaderboard compatibility, Native/RAG/AWI/AWE parity, treating `local-scripted` protocol values as model quality, treating route preflight as a score, treating clean-source-only as full AIppocampus, claiming semantic-sidecar results without prepared worker metadata, live Desktop superiority over Codex native, cold-start timeout as warmed memory quality, or treating overlay utilization flags as official diagnosis output. |
| STATE-Bench Agent Learning Track | Enterprise workflow benchmark track that tests reusable improvements from prior task trajectories through a read-only retrieval hook. | Feasibility and adapter boundary are documented in [`../state-bench-agent-learning.md`](../state-bench-agent-learning.md). The runner can inspect a local ignored STATE-Bench checkout, derive train-only learning strings, and generate an `AIppocampusStateBenchAgent` subclass with `retrieve_learnings(query, top_k=3) -> list[str]`. | Adapter/readiness scaffold implemented. A 2026-06-10 local `customer_support` feasibility slice observed 100 train trajectories and generated 100 learning strings, but ran 0 official held-out tasks and 0 matched no-memory task baselines. | Official STATE-Bench score, Agent Learning Track lift, leaderboard readiness, held-out task quality, end-to-end task performance, cost/UX improvement, or SOTA. |
| LoCoMo | Public long-dialogue control with evidence ids inside one conversation sample. | Public same-conversation evidence retrieval, the fixed-reader text-QA harness, and the answer-usefulness prototype are documented in [`../public-longitudinal-users.md`](../public-longitudinal-users.md) and its dated measurement report. | Implemented as a same-conversation control; the default gold run is an oracle scorer self-check. The text-QA harness separates retrieval, fixed-reader answer quality, citation, latency, token/cache, cost, and failure taxonomy with static stdout plus sanitized report output. Answer-usefulness reports setup/artifact success separately from the quality gate. | Cross-conversation, cross-project, coding tacit-constraint, life-wide memory proof, official LoCoMo judge/leaderboard score, or answer-generation quality without a dated fixed-reader provider report. |
| ATM-Bench Hard | Multimodal personal-memory-corpus QA with staged raw media, derived artifacts, evidence ids, Oracle, NIAH, and agent-harness modes. | Protocol boundary is owned by [`atm-bench-hard-protocol-boundary.md`](atm-bench-hard-protocol-boundary.md); public-safe corpus-style, conversational media-ingest, and NIAH evidence-pool fixtures are documented in [`../multimodal-corpus-fixture-report.md`](../multimodal-corpus-fixture-report.md), [`../conversational-media-ingest-fixture-report.md`](../conversational-media-ingest-fixture-report.md), and [`../multimodal-niah-evidence-pool-report.md`](../multimodal-niah-evidence-pool-report.md). | Protocol boundary documented; public-safe contract fixtures added; upstream adapter planned. | Conversational media-upload recall from staged-corpus QA, product privacy behavior, ATM-Bench score, retrieval quality from NIAH, or broad multimodal-memory quality. |
| MemoryAgentBench | Incremental multi-turn memory-agent benchmark covering retrieval, test-time learning, long-range understanding, and conflict resolution. | Feasibility intake and the deterministic metadata/case-pack smoke are documented in [`../memoryagentbench.md`](../memoryagentbench.md). Official parquet files can feed metadata/case-pack/Stage 3 paths when the optional local reader is installed. Stage 3 now includes a local hash-only apply-instrumented write/update/retrieve probe for Test-Time Learning and Conflict Resolution rows. | Metadata/case-pack smoke implemented; optional parquet row happy path implemented; local apply instrumentation implemented; official/quality incremental replay still blocked. | Any AIppocampus score, official-runner compatibility, fairness claim, answer-generation quality, judge quality, or static-retrieval substitute for test-time learning/conflict-resolution quality. |
| PersonaMem / PersonaMem-v2 | Personalization benchmark family for evolving user preferences, profile updates, and response adaptation. | Readiness gate is documented in [`../personamem-readiness.md`](../personamem-readiness.md); it stages full runs behind AIppo/Ficus profile-readiness. | Planned and intentionally staged. A tiny public-safe pilot may validate schema/red lines, but the full benchmark should wait for source-supported profile extraction, lifecycle/currentness gates, privacy masks, and response-adaptation metrics. | PersonaMem score, personalization quality, privacy-safe profile use, or broad life-wide memory quality from source retrieval, AIppo working contracts, Dream material, summaries, or semantic sidecars alone. |
| Mem0 | External memory-system comparison candidate and source of public pain-taxonomy signals. | Pain categories are summarized in [`../../../research/memory-system-pain-taxonomy.md`](../../../research/memory-system-pain-taxonomy.md); the hippocampal recall runner exposes a missing-config diagnostic adapter slot but no live Mem0 scorer. | Diagnostic adapter slot only. | Competitor superiority, current adapter parity, or API compatibility. |
| Zep / Graphiti | External graph-memory comparison candidate and source of scale/structured-extraction pain signals. | Pain categories are summarized in [`../../../research/memory-system-pain-taxonomy.md`](../../../research/memory-system-pain-taxonomy.md); the hippocampal recall runner exposes a missing-config diagnostic adapter slot but no live Zep/Graphiti scorer. | Diagnostic adapter slot only. | Graph-memory superiority, scale win, current adapter parity, or API compatibility. |
| Letta | External agent-memory and compaction comparison candidate. | Pain categories inform compaction-continuity fixtures; the hippocampal recall runner exposes a missing-config diagnostic adapter slot but no live Letta scorer. | Diagnostic adapter slot only. | Host-native compaction superiority or failure claims beyond cited public signals. |
| Host-native compaction baselines | Real users often get host summaries or compaction without AIppocampus. | #406 adds the first Codex-style `host_native_continuous_no_aippocampus` deterministic contract arm to #378, with AIppocampus hook/MCP/active-recall/registry surfaces disabled. | Contract implemented; live host telemetry missing. | AIppocampus has beaten realistic host-native continuous workflows, cross-host baseline coverage, or live host-native compaction behavior. |

## Adapter Readiness Checklist

Before adding a new external adapter result, document:

- source dataset, version, license, and local artifact policy;
- exact task layer and metric layer;
- prediction input shape and whether raw text is committed, local-only, or
  hashed;
- whether the baseline system writes memory, retrieves source, answers
  questions, or all three;
- model/provider versions for live runs;
- negative controls, closed-book controls, or no-memory arms where applicable;
- `cannot_claim` boundaries and known fairness gaps.

## Next Slices

- LongMemEval-V2: keep the diagnostic context-mapping pilot out of scoring, and
  use the #1155 official-harness pilot decision plus
  `aippocampus_context_provider` adapter for the next credible slice: a tiny
  5-20 question local run with fixed reader/evaluator config, latency/cost
  budgets, and sanitized aggregate reporting only.
- ATM-Bench Hard: keep staged-corpus QA, conversational media-ingest recall,
  Oracle answer synthesis, and NIAH evidence-pool evaluation as separate slices
  before adapting the #528 multimodal track.
- AMemGym: use the public `v1.base` metadata smoke, checked-in overlay fixture,
  official-runner bridge with AIppocampus adapter arms, and Codex Desktop
  AMemGym-style contract before attempting public evidence claims. Keep
  official AMemGym native accuracy, diagnosis, utilization, source-backed
  overlay fidelity, clean-source-only retrieval, prepared semantic-worker
  arms, Desktop native versus AIppocampus arms, and cost/latency separate.
- STATE-Bench Agent Learning: use the feasibility adapter and train-only
  learning extractor before any official attempt. The next credible slice is a
  matched one-domain run with identical model, harness, run count, top-k,
  worker settings, and pricing assumptions for no-memory and AIppocampus
  agents.
- MemoryAgentBench: use the Stage 1/2 metadata, public-safe case-pack smoke,
  optional parquet row reader, and Stage 3 local apply instrumentation as the
  adapter boundary. Keep official/quality incremental replay out of scope until
  answer generation, judging, model/provider versions, and official-runner
  compatibility are measured without collapsing the benchmark into static
  retrieval.
- PersonaMem / PersonaMem-v2: keep this track behind the
  [`../personamem-readiness.md`](../personamem-readiness.md) gate. The next
  useful work is a source-backed AIppo/Ficus personal-impression compiler and
  a tiny diagnostic pilot, not a full benchmark run.
- Mem0 / Zep / Graphiti / Letta / LangMem: keep missing-config diagnostic
  slots separate from scores. Add live adapters only after install/license
  review and a fair source-evidence or pain-fixture adapter exists.
- Hippocampal H1/H2/H5: keep
  [`../hippocampal-cross-system-comparison-2026-06-04.md`](../hippocampal-cross-system-comparison-2026-06-04.md)
  as the dated diagnostic table until live external adapters produce comparable
  source-backed runs.
- Host-native compaction: keep separate from bare continuous-context baselines
  and report when the host-native baseline wins. The current #406 contract arm
  names the Codex-style host path; future live runs still need exact host
  version/build and measured compaction behavior before external claims.
