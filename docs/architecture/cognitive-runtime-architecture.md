# Cognitive Runtime Architecture

Role: current contract.

AIppocampus should not become one large all-purpose agent. It should become a
fine-grained cognitive runtime: many small deterministic gates, semantic
workers, job circuits, and routing layers cooperating over source-backed memory.

This document defines the engineering metaphor behind that runtime. It is not a
neuroscience claim. It is a design discipline for deciding when to use scripts,
embeddings, fast LLMs, small agent shells, or a larger orchestration pipeline.
The public cross-document boundary for these metaphors lives in the
[architecture overview](architecture-overview.md#metaphor-discipline).

## Core Claim

The smallest useful intelligent unit in AIppocampus is not a "cell". It is a
job circuit.

A biological cell is mostly a thresholding component: integrate input, fire or
do not fire. That is closer to a deterministic function than to an intelligent
agent. A fast LLM call replaces something larger: a local semantic subregion
that can integrate context, tolerate ambiguity, and propose structured
candidates.

The corrected mapping is:

| Runtime layer | Biological analogy | AIppocampus examples | Responsibility |
|---|---|---|---|
| Deterministic cell | Synapse, ion channel, single cell firing | `if`, regex, schema validation, cooldown, lock, threshold | Reliable fire/not-fire gating |
| Microcircuit | Small recurrent/local circuit | embeddings, cosine similarity, clustering, dedupe | Pattern separation and candidate grouping |
| Semantic subregion | CA1/CA3/DG-like local area | fast LLM call with a minimal agent shell | Fuzzy integration and source-backed interpretation |
| Job circuit | Functional local circuit | one `subconscious_jobs.py` job | Deterministic gates + semantic subregion + validation + staging output |
| Hippocampal system | Hippocampus, entorhinal cortex, prefrontal routing | scheduler, review, router, hook, registry | Coordination, consolidation, routing, recall scent |

This mapping matters because it prevents two opposite mistakes:

- asking a script to understand user intent from brittle hard-coded terms
- asking a large agent to do cheap deterministic work that should be auditable
  and repeatable

## Why Not One Big Agent

The all-purpose-agent model is expensive, slow, and hard to verify. It also
blurs responsibility: the same agent reads source, decides scope, infers user
intent, writes memory, routes recall, and explains itself afterward.

AIppocampus needs a different shape:

- Many small workers should each have a narrow contract.
- Fast LLMs should be used where ambiguity is real.
- Deterministic code should own source integrity, routing boundaries, and
  repeatable checks.
- The pipeline should make every semantic output provisional until source refs,
  validation, review, and routing accept it.

Future agent systems are likely to be clusters, but not just clusters of
persona experts. A better cluster is made of finer roles: extractors, matchers,
validators, routers, reviewers, materializers, and hook readers. Most of these
workers are not personalities. They are cognitive functions.

## Deterministic Cells

Scripts are not low-status glue. They are the reliable cells of the runtime.

Use deterministic cells for:

- source path selection and registry lookup
- raw rollout and clean-source parsing
- JSON schema validation
- source-ref validation
- exact deduplication and fingerprinting
- cooldowns, leases, locks, and frequency caps
- privacy redaction and secret-like string suppression
- monotonic counters, timestamps, and state transitions
- "write or do not write" decisions after validation

Active recall locks are in this layer: they are route gates with freshness
vectors, versions, consumer counters, and source-reopen handles. They are not
semantic findings, and lock ROI counters are tuning diagnostics rather than
public memory-quality claims.

Deterministic cells should be boring, fast, and testable. They should not try to
understand subtle user meaning. A hard-coded phrase list can suppress obvious
noise or catch explicit commands, but it must not become the main mechanism for
recognizing user intent near the human-facing layer.

## Microcircuits

Vector and graph operations are microcircuits. They are more flexible than
single thresholds but still not semantic authorities.

Use microcircuits for:

- embedding similarity
- nearest-neighbor candidate retrieval
- clustering candidate questions or routes
- graph-neighbor expansion
- ranking and diversity sampling
- pattern separation before LLM confirmation

Microcircuits propose candidate neighborhoods. They do not decide truth. A high
cosine score means "inspect this relation", not "these are the same concern."

Candidate generation is still influence. If a nearest-neighbor, graph, scope,
or reranking microcircuit only exposes the top few rows to a deterministic
verifier, then rows outside that budget never reach the truth gate. Benchmark
and debug surfaces that have a known source ref should therefore report
candidate-space diagnostics: whether the gold source entered the raw candidate
pool, whether it was pruned by `top_k` / threshold / budget / source filtering,
and whether the verifier actually saw it. These diagnostics explain misses;
they do not upgrade candidate scores into truth.

## Semantic Subregions

A fast LLM is not a cell. It is a semantic subregion.

It should be called when the task requires fuzzy integration:

- Is this user turn a genuine question or just an instruction?
- What is the user's intent orientation?
- Where did the discussion stop?
- Which route cues should navigate back to this source?
- Are these clustered questions the same concern, an evolution, or only
  related?
- What compact label names this validated cluster?

Fast LLM calls should usually run in the subconscious layer, not foreground
hooks. They can be highly concurrent because their outputs are provisional and
the parent process can serialize writes.

## Minimal Agent Shells

A semantic subregion should not be a naked completion call. It should have a
minimal agent shell:

- **Source window:** compact clean-source turns or validated candidate rows.
- **Objective:** one narrow task, such as extract questions or classify links.
- **Tool budget:** optional read-only tools, bounded by step count and timeout.
- **Output schema:** strict JSON with source refs and confidence.
- **Validator:** deterministic source-ref, schema, quality, and privacy checks.
- **Failure isolation:** malformed or empty samples become structured failures;
  successful samples continue.
- **Write boundary:** the shell returns candidates; parent code performs
  serialized staging writes.

This shell is what turns a fast LLM from "chat model" into a dependable
semantic worker.

## Job Circuits

A job circuit is the minimum deployable intelligent unit.

Examples:

- `cognitive_map`
- `question_extraction`
- `question_tracking`
- `theme_emergence`
- `journey_tracking`
- `compensatory_dream`
- `dream_input_pack`
- `dream_real_history_eval`
- `trigger_mining`
- `decision_evolution`

Each job circuit should contain:

- deterministic prefilters
- one or more semantic subregion calls
- deterministic postfilters
- source-backed validation
- quality scoring
- staging output
- review/routing integration

The job circuit is where "intelligence" becomes useful. The script cells keep
the circuit safe; the semantic subregion gives it flexibility; the validator
keeps it source-backed.

## Hippocampal System

The full AIppocampus pipeline is the hippocampal system:

- `subconscious_scheduler.py` decides when work is due.
- `subconscious_jobs.py` runs job circuits.
- `subconscious_review.py` reviews provisional candidates.
- `memory_candidate_router.py` routes accepted working memory.
- `build_cognitive_map.py` materializes hook-safe sidecars.
- `aippocampus_runtime.hooks.prompt` reads stable scent and source-backed evidence.

No single layer should pretend to be the whole system. The foreground hook is
not the place for fresh deep inference. The LLM worker is not the place for
final truth. The deterministic builder is not the place to invent semantic
routes.

`subconscious_scheduler.py` is a local best-effort coordinator, not a
distributed scheduler. Its lock files and project leases are meant to prevent
ordinary same-machine hook and detached-worker overlap on local filesystems.
They are not an NFS-safe lock protocol, multi-host queue, or historical access
revocation mechanism. Foreground hook mode must stay cheap and fail-open; use
strict failures only for explicit operator diagnostics.

## Near-User Layers Need Semantics

The closer a behavior is to the user's lived intent, the less acceptable it is
to rely only on hard-coded terms.

Hard-coded vocabulary can be useful for:

- explicit opt-out commands
- obvious noise suppression
- known safety/privacy patterns
- deterministic fallbacks
- test fixtures

It is not enough for:

- detecting genuine questions
- recognizing intent orientation
- identifying cognitive frontiers
- interpreting emotional or philosophical context
- deciding whether two cross-thread concerns are really the same
- mining natural route cues for ambient recall

Near-user layers should use semantic subregions, then validate their output
with deterministic cells. The rule is semantic where needed, deterministic
where possible, source-backed always.

## Fine-Grained Agent Clusters

AIppocampus should prefer fine-grained cognitive workers over role-play agent
teams.

This describes AIppocampus's internal cognitive workers. It does not constrain
external multi-agent orchestration strategies such as Orchestra profiles
(`deepseek-writer`, `kimi-reviewer`, reviewer profiles, or handoff workflows).
Those persona-based dispatch layers can remain useful for human-facing review,
writing, critique, or broader project work. Inside AIppocampus, however,
workers should be defined by narrow contracts and artifacts rather than by
personality roles.

Less useful:

- "one agent is the philosopher"
- "one agent is the engineer"
- "one agent is the memory expert"

More useful:

- one worker extracts source-backed questions
- one worker classifies intent orientation
- one worker proposes frontier markers
- one worker validates source refs
- one worker clusters candidate questions
- one worker names a validated theme
- one worker routes accepted candidates into working memory

These workers can use fast LLMs, scripts, embeddings, or all three. Their
identity is defined by contract and interface, not personality.

## Decision Rules

Use deterministic code when:

- the input and output can be specified exactly
- failure must be reproducible
- privacy or source integrity is at stake
- the operation is cheap and repeated often
- a test can fully define the behavior

Use embeddings or graph operations when:

- you need candidate neighborhoods
- exact matching is too brittle
- the output is a shortlist for later validation
- you need scale before semantic confirmation

Use fast LLM semantic subregions when:

- the task is fuzzy but bounded
- the output can be validated against source refs
- multiple concurrent samples can improve diversity
- a malformed sample can be isolated without harming the batch

Use a larger agent only when:

- the task crosses multiple job circuits
- tool use and planning are both necessary
- the user needs an integrated explanation or intervention
- smaller workers cannot provide enough context

## Contract For New Cognitive Workers

Every new worker should answer these questions before it is implemented:

1. What layer is this: deterministic cell, microcircuit, semantic subregion,
   job circuit, or system router?
2. What source does it read?
3. What exact artifact does it write, if any?
4. Can its output be validated deterministically?
5. What happens when it returns empty, malformed, or low-confidence output?
6. Is it allowed to run in foreground hooks?
7. Does it treat model output as scent, candidate, or evidence?

When a worker or skill path needs a machine-readable execution boundary, use
[Agent Skill Capability Contracts](agent-skill-capability-contracts.md). Those
contracts type permissions, source boundaries, side effects, and evaluation
protocols; they do not replace clean source, worker validation, or this
cognitive-runtime layer map.

Default answers:

- foreground hooks read stable scent and source-backed evidence only
- semantic workers write provisional candidates only
- deterministic builders materialize validated sidecars only
- local source remains the authority

Fresh semantic workers are allowed in foreground hooks only behind an explicit
fail-open deadline and a per-worker timeout within that deadline. Their output
remains routing scent until local source search reopens clean source; high-risk
worker disagreement must cap semantic escalation rather than silently becoming
evidence.

## Relationship To Question Tracking

`question_extraction` should not be a script-only phrase detector. It is close
to user intent, so it needs a semantic subregion. But it should still be wrapped
in deterministic cells:

- prefilter obvious non-question turns
- ask a fast LLM to extract genuine questions, intent orientation, and explicit
  frontier markers
- validate source refs and schema
- score quality and novelty
- write only staging findings

`question_tracking` should not trust one embedding score. Embeddings form a
microcircuit that proposes candidate clusters. The six-axis question map
defined in
[Question Tracking as a Subconscious Layer](question-tracking-subconscious.md#summary-hippocampal-mechanisms--aippocampus-design)
then decides whether the relation is same-question, evolving-question,
related-but-distinct, or frontier-boundary.

The first deterministic salience/threshold slice now lives inside
`aippocampus_runtime.question.tracking`: candidates get source-backed salience tags before pair
comparison, and each pair gets an adaptive threshold policy from compatible or
conflicting six-axis evidence. This remains a staging/navigation layer; it does
not turn salience scores or thresholds into memory truth.

## Relationship To Dream Tasks

`aippocampus_runtime.dream.compensatory` is the first implemented integrative worker. It is a
job-circuit-adjacent helper over already extracted, source-backed single-thread
rows: deterministic cells validate source refs, suppress unsourced or prior
dream rows, suppress refs that belong to another thread, and emit only
`dream_synthesized` candidates whose bridge claims carry source refs. Its output
is candidate weather over source, not source truth. The live question-extraction
chain now preserves source-derived `scope_labels` / `semantic_scope_labels`
into validated findings, which keeps life-wide dream branches fed without
trusting model-invented labels.

`aippocampus_runtime.dream.input_pack` is the first cross-thread dream substrate. It combines
source-backed `question_link` rows, `aippocampus_journey` rows, and weak
`aippocampus_ambient_residue` handles into an
`aippocampus_dream_input_pack` only when clean source refs span at least two
threads. Ambient residue can add themes and negative contexts, but cannot stand
in for clean source. The pack advertises background dream functions such as
compensatory analysis and amplification without claiming those workers have
already produced validated dream quality.

`aippocampus_runtime.dream.real_history_eval` adds a selected real-history structural eval over
the same boundary. It selects cross-thread packs from materialized
question/frontier/question-link/working-memory rows, runs a tiny deterministic
compensatory/amplification worker, adjudicates the outputs, and measures the
delta versus plain rows for prompt hit-rate, source-thread coverage,
reflection-ready rows, and bridge-claim coverage. Its output is sanitized
aggregate evidence; it does not prove private-history dream quality or live
model/user-visible lift.

`dream_live_shadow_ab.py` adds the opt-in live measurement ledger for that last
boundary. Prompt hooks can record hash-only shadow events for baseline and
dream arms without changing foreground recall; later analysis counts explicit
user reminder language and attributes each reminder to only the nearest prior
eligible exposure. Historical clean-source replay and public benchmark-corpus
directory replay are diagnostic only; the latter is useful as a negative-control
over-personalization stress test. Causal user-behavior lift requires delivered
treatment/control arms.

Background-adjudicated dream hypotheses can project onto the existing
working-memory substrate for recall, ambient, and reflection consumers, but
only after structural adjudication in `aippocampus_runtime.dream.working_memory`:
the finding must carry source refs, every bridge claim must carry source refs, and
pack-backed findings must overlap the pack that triggered them. Unadjudicated
or parked dream candidates remain in a background holding queue and are not
eligible for foreground hooks. User confirmation is a high-risk escape hatch,
not the default dream workflow.

The first Cognitive Observatory slice is a read-only diagnostic projection,
not a live control plane. `aippocampus_runtime.ops.route_readiness` classifies
prewarm/route handles as navigation-only `ready` or `suppressed` rows using
TTL, freshness, privacy, source-ref, and ROI gates; stale, privacy-blocked, or
low-value rows stay silent. `aippocampus_runtime.ops.cognitive_observatory`
then aggregates that report with activation authority, recall diagnostics, and
sleep-cycle public summaries so operators can inspect route readiness without
writing clean source, owner caches, durable memory, or foreground hook state.
It also emits `control_authority_audit`, which counts attempted activation or
mutation requests as blocked diagnostics rather than granting any control
authority. It can render the same sanitized readout as JSON, text, or static
no-script HTML for local inspection. These rows can justify reopening source,
but they cannot support factual claims by themselves.

## Anti-Patterns

Avoid these:

- replacing every deterministic gate with an LLM call
- adding a hard-coded phrase list for every new user-intent nuance
- letting a model write formal memory directly
- making the foreground hook wait for fresh DeepSeek reasoning
- creating persona agents when a narrow worker contract would do
- treating a semantic label as evidence without source refs
- adding separate staging files when the existing subconscious pipeline can
  carry the candidate type
- letting unadjudicated dream candidates influence foreground recall before
  adjudication or source re-opening

## Summary

AIppocampus should be built like a cognitive runtime:

- deterministic cells for reliable gates
- microcircuits for candidate structure
- semantic subregions for bounded fuzzy interpretation
- job circuits for useful intelligence
- a hippocampal system for consolidation and recall

This is cheaper than one big agent, safer than script-only memory, and more
adaptable than role-play agent teams. It preserves the core AIppocampus rule:
semantic workers may organize memory, but local source remains the authority.
