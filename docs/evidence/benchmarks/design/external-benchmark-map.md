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
| LongMemEval V1 | Public long-memory QA family with source/session evidence variants. | Retrieval-only source/session slices are tracked in [`../longmemeval.md`](../longmemeval.md) and the Track B standard retrieval-QA notes. | Implemented as a retrieval/control surface. | Answer-generation quality, SOTA, LongMemEval-V2 quality, or broad user-memory superiority. |
| LongMemEval V2 | Closer to agentic-context and workflow-memory evaluation. | Context-mapping pilot is documented in [`../longmemeval.md`](../longmemeval.md); it inspects the public V2 schema and local files without emitting raw text. | Diagnostic mapping pilot implemented; benchmark-grade context/source-evidence/answer scoring still blocked. | Comparable scores, source-evidence R@K/MRR, answer accuracy, or LAFS until explicit question-to-haystack/evidence labels and the official reader/evaluator harness are wired. |
| LoCoMo | Public long-dialogue control with evidence ids inside one conversation sample. | Public same-conversation evidence retrieval is documented in [`../public-longitudinal-users.md`](../public-longitudinal-users.md) and its dated measurement report. | Implemented as a same-conversation control. | Cross-conversation, cross-project, coding tacit-constraint, or life-wide memory proof. |
| ATM-Bench Hard | Multimodal personal-memory-corpus QA with staged raw media, derived artifacts, evidence ids, Oracle, NIAH, and agent-harness modes. | Protocol boundary is owned by [`atm-bench-hard-protocol-boundary.md`](atm-bench-hard-protocol-boundary.md); public-safe corpus-style, conversational media-ingest, and NIAH evidence-pool fixtures are documented in [`../multimodal-corpus-fixture-report.md`](../multimodal-corpus-fixture-report.md), [`../conversational-media-ingest-fixture-report.md`](../conversational-media-ingest-fixture-report.md), and [`../multimodal-niah-evidence-pool-report.md`](../multimodal-niah-evidence-pool-report.md). | Protocol boundary documented; public-safe contract fixtures added; upstream adapter planned. | Conversational media-upload recall from staged-corpus QA, product privacy behavior, ATM-Bench score, retrieval quality from NIAH, or broad multimodal-memory quality. |
| MemoryAgentBench | Incremental multi-turn memory-agent benchmark covering retrieval, test-time learning, long-range understanding, and conflict resolution. | Feasibility intake and the deterministic metadata/case-pack smoke are documented in [`../memoryagentbench.md`](../memoryagentbench.md). Incremental replay remains blocked until write/update/forgetting contracts are explicit. | Metadata/case-pack smoke implemented; full incremental replay still blocked. | Any AIppocampus score, official-runner compatibility, fairness claim, or static-retrieval substitute for test-time learning/conflict-resolution quality. |
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

- LongMemEval-V2: use the diagnostic context-mapping pilot to decide whether a
  future official haystack/evidence adapter is possible before any scoring
  result.
- ATM-Bench Hard: keep staged-corpus QA, conversational media-ingest recall,
  Oracle answer synthesis, and NIAH evidence-pool evaluation as separate slices
  before adapting the #528 multimodal track.
- MemoryAgentBench: use the Stage 1/2 metadata and public-safe case-pack smoke
  as the adapter boundary. Keep full incremental replay out of scope until
  ingestion/update/forgetting contracts are measurable without collapsing the
  benchmark into static retrieval.
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
