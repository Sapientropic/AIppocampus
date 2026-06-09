# Architecture Overview

Role: current contract.

AIppocampus is a local-first continuity layer. It helps an agent recover prior
source and continue honestly, without claiming the model itself has innate
memory.

## Layers

1. Conversation source
   - Provider-owned transcript provenance from a host agent, such as Codex
     Desktop rollout JSONL files.
   - The provider boundary owns session discovery, current-session lookup,
     metadata extraction, and stable source identity. It does not own the
     AIppocampus registry location.
   - Used for exact repair, latest-reply fallback, storage accounting, and
     optional raw audit.
   - Not the daily recall surface.

2. Clean source
   - Original visible user messages plus assistant final answers, with routine
     commentary, tool payloads, injected instructions, and duplicate carriers
     removed.
   - Preserves source ids, turn ids, message ids, line spans, timestamps, and
     hashes.
   - Optional redaction projections may be written for local-at-rest or public
     export privacy, but `raw-private` clean source remains the canonical
     evidence source.
   - Search and MCP tools should prefer this layer for ordinary recall.

3. Registry and local indexes
   - Machine-wide registry under `$CODEX_HOME/aippocampus-registry/`.
   - Per-thread clean source, SQLite/RAG-lite indexes, graph sidecars, and
     segment indexes for large threads.
   - Project-local `.aippocampus/` remains explicit export/debug mode.

4. Ambient recall hooks
   - Prompt hook provides scent or small source-backed evidence when a prompt
     smells related.
   - Lifecycle hook performs deterministic maintenance.
   - Hooks are opt-in in public/plugin distribution because they can surface
     private memory into future prompts.

5. Optional semantic and subconscious layers
   - DeepSeek-compatible semantic gates and background jobs can propose routes,
     triggers, concept edges, and working-memory candidates.
   - They are navigation layers, not replacement truth.
   - External-model payloads must pass through shared redaction.

6. Access and distribution
   - CLI scripts remain deterministic building blocks.
   - MCP exposes read-mostly memory tools to compatible agent clients.
   - Local-folder and HTTP object-storage sync exchange clean source,
     manifests, registry rows, and sidecars; raw rollout sync is explicit only.
   - Codex plugin packaging bundles skill and MCP config as a friendly install
     surface, while the standalone repository remains canonical.

## Data Flow

```text
host transcript
  -> conversation source provider
  -> clean source
  -> local index and registry
  -> search / MCP / hooks / sync / plugin distribution
```

Model-organized outputs can point back into clean source, but they should not
replace it. Any high-level finding that matters must remain tied to source
refs.

## Source-Backed Kernel Contract

Every higher-level memory surface hangs off this kernel chain:

```text
ConversationProvider -> CleanSource -> SourceRef/Registry -> Rebuildable Index -> RecallCandidate -> RecallDecision -> SourceReopen -> BoundedEvidence
```

The names may vary at a module boundary, but the authority transition must not
vary. Clean source is the truth substrate. Registry rows and source refs give
portable identity and reopen handles. Indexes are rebuildable caches, not
truth. Recall candidates and recall decisions are navigation until they lead to
source reopen. Source reopen is the transition from route/context to
claim-supporting evidence. Bounded evidence can support claims only within its
declared scope; source-open evidence can support exact wording only inside its
scope and redaction boundary.

Authority rings:

| Ring | Examples | Authority |
| --- | --- | --- |
| Truth substrate | ConversationProvider output, raw audit source, clean source | Ground for later claims; clean source is the ordinary evidence surface. |
| Rebuildable cache | SQLite/FTS/RAG-lite indexes, segment indexes, graph indexes | Speeds lookup and ranking; can be rebuilt from source and must not become truth. |
| Navigation sidecar | Semantic sidecars, concept edges, cognitive maps, continuity domains, route notes, Dream/Journey/subconscious findings, vault projections, Observatory diagnostics | Routes attention, proposes synthesis, or explains system state; cannot support factual claims by itself. |
| Foreground packet | Ambient cards, Active Path Packets, MCP recall handles, evidence drawer packets | Tells the agent what action is allowed: scent, route, bounded evidence, source open, or blocked. |
| Bounded / source-open evidence | Reopened clean-source windows, bounded evidence cards, scoped source-open context | May support answer content within scope; exact, sensitive, stale, disputed, or high-risk claims still follow source-court rules. |

Dream, Journey, subconscious jobs, semantic sidecars, ambient recall, sync,
vault, Observatory, continuity domains, cognitive maps, and future cognitive
layers may route attention, compress interpretation, schedule review, explain
activation, or move source-backed artifacts across devices. They must not
replace clean source, raw audit source, or source reopen. Generated findings
must not replace clean source; summaries can be useful maps only when they keep
a route back to source and remain lower authority than reopened evidence.

This contract is deliberately not search-only memory. Higher-level cognition is
allowed, but its product job is to help a later agent find and use source with
care, not to create a second memory truth layer.

## Metaphor Discipline

AIppocampus uses neuroscience-adjacent language as an engineering and product
metaphor. The metaphor is useful only when it leaves a checkable obligation:
which runtime mechanism exists, what constraint it imposes, and what evidence
currently supports the claim.

| Design metaphor | Runtime mechanism | Design constraint | What can be claimed today | Claim boundary |
| --- | --- | --- | --- | --- |
| External hippocampus / little hippocampus | Clean source, registry, local indexes, recall hooks, and source-backed evidence retrieval. | AIppocampus owns memory activation, scope selection, and evidence retrieval; the foreground agent still owns task reasoning and answer generation. | AIppocampus provides a local-first continuity layer that can recover prior source for an agent. | Do not imply biological hippocampal equivalence, innate model memory, changed model weights, or a complete agent mind. |
| Scent / ambient recall | Prompt-time hooks, thread ambient cache, warm recall cards, and small source-backed cards. | Scent can preactivate a route before evidence, but factual claims still need source refs or an explicit uncertainty label. | Selected prompts can receive tentative recall cues or source-backed cards, with benchmark, smoke, and field-report evidence tracked in `docs/evidence/`. | Do not treat a scent as a fact, user profile, or permission to inject private context into unrelated work. |
| Staging / materialization / consolidation | Clean-source materialization, registry rows, staging findings, review gates, and source-ref validation. | Model-organized candidates remain navigation until they are tied back to source and accepted by the owning flow. | Clean source and selected staging flows preserve source refs while allowing provisional organization. | Do not call summaries, candidates, or concept edges memory truth by themselves. |
| Cognitive map | Concept edges, semantic sidecars, route cues, and source-reopen pressure. | The map should improve wayfinding through old source, not replace the source or decide what is true. | Navigation sidecars can suggest routes back into source; broader map quality remains roadmap/prototype direction. | Do not imply a complete mental model, neuroscience fidelity, or a solved personal ontology. |
| Dream / subconscious jobs | Background job circuits, dream input packs, adjudication rules, and optional staging writes. | Detached synthesis must be labeled, reviewable, discardable, and lower authority than source-backed recall. | Implemented slices and dated evidence exist for selected paths; broader Dream quality remains research. | Do not claim predictive dream quality, privileged user simulation, or solved proactive replay. |

## Activation-Surface Authority Budget

Strategy-like activation surfaces include AAR/reflection nudges, dream
hypotheses, working memory, semantic triggers, ambient cards, active recall
locks, and pruning rows. They may guide attention, route checks, slow risky
actions, or retire noisy cues; they are not a second factual memory store.

The shared authority vocabulary is:

- `candidate`: navigation hint only.
- `advisory`: may bias attention or suggest a check.
- `guardrail`: may block or slow a risky action until source/current state is
  checked.
- `source_required`: cannot support a claim/action without source reopen or
  equivalent evidence.
- `blocked`: not eligible for foreground use until later review changes state.

Conflict precedence is deterministic: explicit user correction suppresses
strategy surfaces, current-checkout evidence and reopened clean source override
activation rows for truth, and blocked/guardrail/source-required rows cannot
upgrade scent, dream, cached, or AAR material into evidence. Pruning changes
activation eligibility only; it must not change source or truth status.

`aippocampus_runtime.ops.activation_authority_audit` is the no-write diagnostic
for this boundary. It reports `activation_surface_authority_leak_count` when a
strategy row is quoted or acted on as factual evidence without source support,
and emits conflict-resolution reasons without raw prompts, snippets, secrets,
or local paths. The same report also carries foreground-usefulness pruning
metrics such as `false_scent_reduction_count`,
`wrong_route_drag_reduction_count`, `duplicate_route_collapse_count`, recent
helpful/harmful counts, and estimated verification tool calls saved. Those
metrics are about reducing stale foreground drag, not about deleting older
source or making memory merely quieter.

The same audit now emits a #582 dead-letter candidate report for activation
rows that have already been demoted, parked, superseded, retired, or blocked
and also cross repeated wrong-route or no-source-reopen thresholds. Candidate
identity is hash-only, reports contain counts and reason codes rather than raw
payloads or source refs, and protected rows referenced by promotion candidates,
dream inputs, review artifacts, question links, or source-reopen evidence are
skipped.

Apply-capable pruning remains bounded. The audit helper can write an
append-only lifecycle update manifest for activation rows, but that manifest is
not a clean-source mutator and not a truth-status editor. It records demote,
park, supersede, or retire actions for the owning surface writer to consume
later, preserving source refs and provenance while removing noisy rows from
foreground eligibility.

Dead-letter apply manifests follow the same rule: they are append-only
activation lifecycle patches for owner-specific writers, not physical source or
raw-rollout deletion. Physical payload compaction remains owner-specific and
must pass source, provenance, reference, and rebuild/review checks before any
stored payload is minimized.

The first owner-specific compaction slice is the ambient thread cache:
`aippocampus_runtime.recall.ambient_cache_compaction` can consume a dead-letter apply
manifest and replace matching `ambient_card` payloads with tombstones that keep
hash identity, source-ref counts, provenance-pointer hash, reason codes,
timestamps, and rebuild/review notes. This reduces stale related-cache drag
without mutating clean source, raw rollout, registry refs, truth status, or
foreground hook state. Other activation surfaces still need their own owners to
implement equivalent apply checks before #582 can be treated as fully done.

Two positive examples anchor the rule:

- A prompt-time scent is allowed to say "this old thread may be relevant" before
  the system has strong evidence. It is not allowed to become a source-backed
  claim unless the hook or foreground answer carries source refs.
- A staging candidate can help future agents notice a pattern. It remains
  provisional until materialization or review ties it to clean source, so the
  product stays source-backed rather than summary-first.

## Runtime Contracts

Detailed runtime behavior lives in the skill references:

- `skills/aippocampus/references/retrieval-and-storage.md`
- `skills/aippocampus/references/ambient-hooks.md`
- `skills/aippocampus/references/maintenance-and-operations.md`
- `skills/aippocampus/references/subconscious-jobs.md`

Product direction remains in `docs/roadmap.md`.
The public-core license, adapter, and schema boundary lives in
`docs/guides/public-core-boundary.md`.
Field-budget and profile discipline for minimal, runtime, high-risk, governance,
and diagnostic projections lives in `docs/architecture/schema-field-profiles.md`.
Optional clean-source redaction profiles and source-fidelity boundaries live in
`docs/architecture/clean-source-redaction-profiles.md`.
Path identity, display spelling, and privacy-safe path projection boundaries live
in `docs/architecture/path-identity.md`.
Runtime script ownership and dependency navigation lives in
`docs/architecture/runtime-script-map.md`.
The Rust deterministic-core migration boundary lives in
`docs/architecture/rust-deterministic-core.md`; Rust ports must replay frozen
Python-owned source-backed contracts before becoming authoritative.
Typed execution boundaries for composable agent skills live in
`docs/architecture/agent-skill-capability-contracts.md`.
Multimodal source identity, media-origin policy, and derived-artifact truth
boundaries live in `docs/architecture/multimodal-source-manifests.md`.
Multimodal provider route capability and media-origin gating lives in
`docs/architecture/multimodal-provider-routing.md`.
Answer-time multimodal source reopen, cross-modal join packets, and abstention
metrics live in `docs/architecture/multimodal-answer-gate.md`.
