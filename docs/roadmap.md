# AIppocampus Roadmap

AIppocampus is not only a project-memory utility. Its central purpose is
continuity between a person and their agents across threads, devices, projects,
and phases of life. It should help a newly activated agent catch up quickly
without pretending its weights changed or that it has innate autobiographical
memory.

The product promise is simple: the archive is still here, so the journey can
continue.

## North Star

AIppocampus preserves source-backed continuity for long-running relationships
with AI agents.

It is the agent's little hippocampus, not the whole agent: AIppocampus owns
memory activation, scope selection, and source-backed evidence retrieval. The
foreground agent owns task reasoning and answer generation after those memory
signals are surfaced.

It should remember more than task outcomes:

- what the person kept circling back to
- what questions, anxieties, doubts, and fascinations were alive at the time
- where ideas came from, including casual chat, reading, experiments, and
  seemingly unrelated topics
- how preferences, metaphors, project direction, and self-understanding changed
- which old conversations are worth reopening when a new prompt smells related

Work memory matters, but it is not the center. A coding thread can be highly
valuable and still contain little of the user's interior life. A casual thread
can carry the actual continuity signal.

## Design Commitments

1. Source-backed, not summary-first
   - Clean source keeps original visible wording when possible.
   - Summaries, concept edges, and model-organized findings are navigation
     layers, not replacement truth.
   - Raw rollout remains optional audit provenance, not the daily memory
     surface.

2. Relationship continuity without false claims
   - The agent should not claim innate memory or changed identity.
   - It can honestly say that AIppocampus recovered the prior source and can
     continue from it.
   - The system should make "I can catch up" feel natural without making every
     prompt about the user's personal history.

3. Life-wide memory, not project-only memory
   - Project labels help organize work, but memory scope must also include
     everyday conversation, reflection, taste, recurring questions, inspirations,
     and unresolved tensions.
   - Cross-project recall should be allowed when the user's actual conceptual
     thread crosses project boundaries.

4. Quiet by default, available when needed
   - Ambient recall should provide scent before evidence.
   - Hooks should avoid over-personalization and avoid dragging private context
     into unrelated tasks.
   - Strong claims require source hits.

5. Portable across machines
   - Mac, Windows, and future devices should share the same clean memory graph.
   - Local absolute paths are hints, not identity.
   - Content hashes, source ids, turn ids, and manifests are the stable join
     layer.

6. Scales to huge memory
   - Design for GB-scale and eventually larger archives from the start.
   - Segment indexes, manifests, sidecar semantic layers, and optional raw cold
     archives should keep growth manageable without forcing premature summaries.

## Roadmap Stages

### Stage 0: Current Skill Baseline

Status: underway.

- Clean source from raw rollouts.
- Conclusion-first search over user turns and final answers.
- Registry for old and cross-thread memories.
- Ambient prompt hook with deterministic and semantic recall paths.
- Lifecycle maintenance hooks.
- Subconscious jobs for concept edges, trigger mining, review, and soft working
  memory.
- Segment indexes and GB-scale planning.
- Public skill copy with portable environment variable names.

### Stage 1: Standalone Public Repository

Goal: make AIppocampus understandable, installable, and reviewable as its own
project.

- Move from a shared skills shelf into a dedicated `AIppocampus` repository.
- Keep `skills/aippocampus/` as the installable skill package.
- Add root README, architecture overview, privacy model, install guide, and
  demo scenarios.
- Maintain the Apache-2.0 public-core boundary, commercial extension boundary,
  adapter contract, and contribution notes.
- Keep public defaults portable and avoid machine-specific paths.
- Maintain smoke tests for clean source, search, registry, hooks, sync, and
  docs health.

### Stage 2: Life-Wide Memory Model

Goal: treat non-project conversations as first-class memory.

- Register all relevant Codex threads, not only repo workspaces.
- Add memory scope labels beyond project: `personal_reflection`,
  `relationship_continuity`, `reading_notes`, `idea_seed`, `preference`,
  `life_context`, `technical_work`, `open_question`.
- Build timelines that show recurring concerns and idea evolution across
  unrelated threads.
- Improve ambient recall so it can notice conceptual continuity without turning
  every answer into biography.
- Preserve "casual but important" turns: questions, metaphors, dilemmas,
  excitement, dissatisfaction, and pivots.

### Stage 3: Cross-Device Sync

Goal: a person can move between Mac, Windows, and future devices without losing
memory continuity.

- Define a device-neutral sync bundle for clean source, manifests, anchors,
  registry rows, concept graph sidecars, semantic triggers, and working memory.
- Add encrypted sync over the bundle contract before treating object storage or
  cloud-synced folders as a product-ready backend; see
  `encrypted-sync-v1.md`.
- Keep raw rollout sync optional, explicit, and encrypted when it leaves the
  device.
- Support backends in increasing order of complexity: local folder, Git repo,
  cloud-synced folder, object storage, and private service.
- Use content hashes and stable ids for dedup/conflict handling.
- Treat paths as per-device locators that can be repaired, not canonical truth.
- Add `sync status`, `sync push`, `sync pull`, and `sync repair` flows.

### Stage 4: MCP Access Layer

Goal: agents can use memory without shelling out through skill instructions for
every operation.

- Provide a local MCP server for read-mostly memory tools:
  `search_memory`, `recall_context`, `recall_deepen`, `latest_reply`,
  `get_turn_context`, `list_threads`, `register_thread`, `sync_status`, and
  `memory_health`.
- Keep mutating tools narrow and explicit.
- Default tools should search clean source and registry, not raw rollout.
- Raw/audit tools should be opt-in and clearly labeled.
- The MCP layer should be usable by Codex CLI, Codex Desktop, and other
  compatible agent clients.

### Stage 5: Plugin Distribution

Goal: package the skill, hooks, and MCP configuration as an installable product.

- Bundle `skills/aippocampus/`, MCP server config, lifecycle hook installers,
  and UI metadata in a Codex plugin.
- Keep plugin install/uninstall reversible.
- Expose privacy and external-model boundaries before enabling hooks or
  DeepSeek-compatible routes.
- Treat plugin as the friendly distribution surface, not the core source of
  truth. The standalone repo remains canonical.

### Stage 6: Deep Consolidation

Goal: let cheap models help organize memory without replacing source.

- Expand subconscious jobs for theme evolution, contradictions, unresolved
  questions, long-term preferences, and concept drift.
- Add better multilingual semantic gates and source-backed trigger mining.
- Support optional embedding or stronger semantic indexes only when lexical and
  concept-graph recall fail.
- Keep every high-level finding tied to clean source refs.

### Stage 7: Official-Quality Release

Goal: make AIppocampus credible enough to recommend outside a personal setup.

- Stable install docs for skill-only, plugin, and MCP modes.
- Public privacy/security review checklist.
- Cross-platform tests on Windows and macOS.
- Example memory bundle that contains no private user data.
- Evaluation prompts covering exact quote recall, fuzzy life-topic recall,
  project continuity, multilingual recall, and over-personalization avoidance.
- Clear statement of what AIppocampus can and cannot claim.

## Non-Goals

- Do not become a generic vector database wrapper.
- Do not make raw rollout mining the daily default.
- Do not pretend summaries are memories.
- Do not make every prompt about personal context.
- Do not require users to stay in one giant thread.
- Do not require a cloud service for local-first use.

## Success Criteria

AIppocampus is working when a new thread can naturally resume a long-running
conversation without the user re-explaining the whole self, project, or journey.

It is working when casual conversations become searchable source, not discarded
noise.

It is working when the agent can say, honestly and calmly: I found where we were,
and we can continue from there.
