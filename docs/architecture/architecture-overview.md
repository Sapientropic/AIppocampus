# Architecture Overview

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
or local paths.

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
Runtime script ownership and dependency navigation lives in
`docs/architecture/runtime-script-map.md`.
