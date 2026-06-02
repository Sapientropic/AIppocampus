# External Benchmark Map

This page is the stable home for external benchmark and memory-system
comparison analysis. It records what each candidate can test, what AIppocampus
has in the repo today, and what remains blocked before any comparison can be
quoted as evidence.

It is not a leaderboard. Do not use this page to claim SOTA, broad competitor
superiority, official partner support, or product-quality proof.

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
| LongMemEval V2 | Closer to agentic-context and workflow-memory evaluation. | Mentioned as a near-neighbor in [`../public-longitudinal-users.md`](../public-longitudinal-users.md); needs explicit source-evidence mapping before scoring. | Planned analysis surface. | Comparable scores until the dataset source contract, adapter, and claim boundary are implemented. |
| LoCoMo | Public long-dialogue control with evidence ids inside one conversation sample. | Public same-conversation evidence retrieval is documented in [`../public-longitudinal-users.md`](../public-longitudinal-users.md) and its dated measurement report. | Implemented as a same-conversation control. | Cross-conversation, cross-project, coding tacit-constraint, or life-wide memory proof. |
| MemoryAgentBench | Candidate benchmark for memory-agent behavior. | No repo-owned adapter yet. Use this page for future intake before adding runner docs. | Planned / unverified. | Any AIppocampus score, compatibility, or fairness claim. |
| Mem0 | External memory-system comparison candidate and source of public pain-taxonomy signals. | Pain categories are summarized in [`../../../research/memory-system-pain-taxonomy.md`](../../../research/memory-system-pain-taxonomy.md); no adapter baseline is implemented. | Analysis only. | Competitor superiority or current adapter parity. |
| Zep / Graphiti | External graph-memory comparison candidate and source of scale/structured-extraction pain signals. | Pain categories are summarized in [`../../../research/memory-system-pain-taxonomy.md`](../../../research/memory-system-pain-taxonomy.md); no adapter baseline is implemented. | Analysis only. | Graph-memory superiority, scale win, or API compatibility. |
| Letta | External agent-memory and compaction comparison candidate. | Pain categories inform compaction-continuity fixtures; no direct adapter baseline is implemented. | Analysis only. | Host-native compaction superiority or failure claims beyond cited public signals. |
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

- LongMemEval-V2: define source-evidence mapping before any scoring result.
- MemoryAgentBench: decide whether it tests memory write policy, tool use, or
  answer quality before building an adapter.
- Mem0 / Zep / Graphiti: add only after install/license review and a fair
  source-evidence or pain-fixture adapter exists.
- Host-native compaction: keep separate from bare continuous-context baselines
  and report when the host-native baseline wins. The current #406 contract arm
  names the Codex-style host path; future live runs still need exact host
  version/build and measured compaction behavior before external claims.
