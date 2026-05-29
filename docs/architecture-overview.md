# Architecture Overview

AIppocampus is a local-first continuity layer. It helps an agent recover prior
source and continue honestly, without claiming the model itself has innate
memory.

## Layers

1. Raw rollout
   - Immutable audit provenance from Codex sessions.
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
raw rollout
  -> clean source
  -> local index and registry
  -> search / MCP / hooks / sync / plugin distribution
```

Model-organized outputs can point back into clean source, but they should not
replace it. Any high-level finding that matters must remain tied to source
refs.

## Runtime Contracts

Detailed runtime behavior lives in the skill references:

- `skills/aippocampus/references/retrieval-and-storage.md`
- `skills/aippocampus/references/ambient-hooks.md`
- `skills/aippocampus/references/maintenance-and-operations.md`
- `skills/aippocampus/references/subconscious-jobs.md`

Product direction remains in `docs/roadmap.md`.
The public-core license, adapter, and schema boundary lives in
`docs/public-core-boundary.md`.
