# Benchmark Design Rationale

AIppocampus benchmarks measure source-backed continuity. They are shaped around
the product risk that matters most: a future agent should recover useful old
context without pretending that a generated summary, stale association, or
nearby-looking memory is proof.

The practical rule comes from
[`source-as-world.md`](../../../research/source-as-world.md): source is the
world, interpretation is weather. A benchmark can reward interpretation only
when the evaluated surface keeps a path back to source and reports what it
cannot yet prove.

## Why Retrieval@K Is Not Enough

Plain retrieval@K can say whether a query found a nearby row. It cannot say
whether memory should have interrupted the prompt, whether private context was
unnecessarily exposed, whether a surfaced payload stayed faithful to source, or
whether a correction survived compaction without becoming a false rule.

AIppocampus therefore keeps separate benchmark surfaces for:

- whether to skip, scent, or provide evidence;
- whether a valid query can reopen the right source;
- whether the payload is source-faithful and private by default;
- whether corrections, rejected routes, and scope boundaries survive
  compression;
- whether degraded cues can complete the right memory while separating similar
  or superseded memories;
- whether public external controls measure the same layer as the claim being
  made.

## Design Principles

### 1. Source Reopen Is The Unit Of Proof

Clean source, stable source refs, and source-reviewable payloads are stronger
than generated summaries. Benchmarks should score a claim as source-backed only
when the system can reopen the supporting source or when a frozen public fixture
owns the truth labels.

Generated labels, semantic sidecars, dream findings, and cognitive-map routes
can improve navigation. They do not become truth by winning a semantic match.

### 2. The First Question Is Whether Memory Should Surface

Track A exists because memory systems can fail by being too eager. A good memory
layer must know when to stay silent, when to provide a quiet scent, and when to
show source-backed evidence. Over-escalating a vague association into evidence
is more dangerous than missing a weak fuzzy recall.

### 3. Capability Contracts Are Execution Boundaries

Capability contracts can constrain what a skill-like path is allowed to read,
which privacy partitions it may touch, which permissions it needs, and what it
must not claim. They are not an alternate fact layer. A contract-review
prototype still has to reopen eligible sources and pass the governed
knowledge-answer gate before it can emit bounded risk flags.

The #517 knowledge pollution/privacy benchmark is therefore separate from the
Track A-D headline surfaces. It tests source authority, stale/superseded
knowledge, prompt-injection-in-source-text, privacy partitioning, and a thin
contract-review capability prototype without claiming legal quality or typed
capability taxonomy completeness.

The #518 typed capability-contract architecture is owned by
[`../../../architecture/agent-skill-capability-contracts.md`](../../../architecture/host/agent-skill-capability-contracts.md).
Benchmark docs should point there instead of mirroring the full taxonomy.

### 4. Scent, Evidence, And Fact Are Different Surfaces

Scent is a tentative route. Evidence is a source-backed payload. Fact is a
claim the foreground agent can responsibly use after checking source and scope.
Reports should keep these separate so a warm association cannot be quoted as an
established user preference or project truth.

### 5. Wrong-Source Confidence Costs More Than Honest Abstention

Hard negatives and asymmetric scoring are core to the benchmark philosophy. A
system that confidently cites a nearby but wrong memory should be penalized
more than a system that says it only has a weak scent or chooses to skip.

This is especially important for stale decisions, superseded conclusions,
cross-project lookalikes, and private-context leakage.

### 6. Track Families Should Not Be Averaged Into One Headline

Track A gate decisions, Track B source retrieval, Track C payload fidelity,
Track D compaction continuity, VCS hard-event recall, and H-series
recall-discrimination test different failure modes. A single aggregate score
would hide whether a result came from silence discipline, source navigation,
payload safety, compaction behavior, or degraded-cue discrimination.

If a report needs a summary, it should preserve per-track status and keep
`cannot_claim` boundaries visible.

### 7. Evidence Layers Must Stay Separate

Deterministic contract tests, public synthetic fixtures, public corpus controls,
private real-history smokes, live model-backed runs, and external adapter
comparisons answer different questions.

They can support each other, but they should not be merged into one proof
surface:

| Evidence layer | Good for | Cannot claim by itself |
| --- | --- | --- |
| Deterministic contract | Schema, report shape, privacy defaults, source-ref handling. | Live model quality or broad user-history lift. |
| Public synthetic fixture | Reproducible scoring contract and hard-negative behavior. | Natural distribution coverage or private-history realism. |
| Public corpus control | External repeatability and baseline sanity. | Cross-thread personal continuity unless the corpus actually contains it. |
| Private real-history smoke | Product-shaped behavior on real local memory. | Public reproducibility, raw data publication, or broad statistical proof. |
| Live model-backed run | Provider/prompt/date-dependent semantic behavior. | Deterministic product quality or future model stability. |
| External adapter | Layer-aware comparison against another system or benchmark. | Official partner support, SOTA, or superiority outside the tested adapter. |

### 8. Compaction Continuity Is Behavior-Level Memory

Track D and E2E continuity benchmarks are not ordinary recall QA. They ask
whether a correction, rejected route, accepted decision, or scope narrowing can
survive compression without becoming stale authority. This is why fresh-context
spec loops, host-native compaction baselines, and no-advantage rules matter
before any continuous-memory superiority claim.

### 9. Hippocampal Tests Add Completion And Separation

The H-series benchmark direction adds degraded cues and interference density:
partial, metaphorical, cross-language, structural, or time-only prompts should
complete the right memory only when enough evidence exists, while similar or
superseded memories stay separated.

The hippocampal framing is an engineering lens. The claim remains source-backed
continuity, not biological fidelity.

### 10. External Benchmarks Must Be Layer-Aware

Long-context QA benchmarks, same-conversation evidence retrieval, parameter-edit
tests, external memory systems, and agent-host compaction baselines are not
interchangeable. AIppocampus comparisons should state which layer was tested:
retrieval, source evidence, answer quality, memory write policy, compaction
survival, or host integration.

Use [`external-benchmark-map.md`](external-benchmark-map.md) as the stable home
for comparison candidates and blockers.

## Canonical Detail Owners

- Full Track A-D methodology and profiles:
  [`memory-decision-benchmark-plan.md`](memory-decision-benchmark-plan.md).
- H-series recall-discrimination design:
  [`../reports/hippocampal/hippocampal-recall-plan.md`](../reports/hippocampal/hippocampal-recall-plan.md).
- Public longitudinal and VCS hard-event benchmark direction:
  [`../public-longitudinal-users.md`](../public-longitudinal-users.md).
- Memory-system pain taxonomy and negative-fixture motivation:
  [`../../../research/memory-system-pain-taxonomy.md`](../../../research/memory-system-pain-taxonomy.md).
- Current project claim boundary:
  [`../../readiness/stage-0-5-readiness.md`](../../readiness/stage-0-5-readiness.md).
- Dated verification ledger:
  [`../../readiness/public-readiness-verification.md`](../../readiness/public-readiness-verification.md).
- Typed agent-skill capability contracts:
  [`../../../architecture/agent-skill-capability-contracts.md`](../../../architecture/host/agent-skill-capability-contracts.md).
- ATM-Bench Hard protocol boundary for multimodal source-backed recall:
  [`atm-bench-hard-protocol-boundary.md`](atm-bench-hard-protocol-boundary.md).
