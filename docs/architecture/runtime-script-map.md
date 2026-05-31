# Runtime Script Map

This is the maintainer navigation map for `skills/aippocampus/scripts/`. It is
not a generated call graph and should not mirror every module docstring. Keep it
focused on ownership, invocation routes, dependencies, and public/internal
status for high-risk scripts and public entrypoints.

When adding a new public entrypoint, hook path, sync path, MCP surface,
registry/retrieval component, warm ambient component, or subconscious job
component, update this map and the cheap guard in
`tools/aippocampus/docs/check_docs_health.py`.

For the exact inventory of remaining Codex-specific raw-rollout/default-home
call sites, see `docs/architecture/provider-entrypoint-inventory.md`.

## High-Level Runtime Flow

This graph is the contributor-facing dependency map. It shows ownership and
call direction at the layer level; it is not a generated import graph.

```mermaid
flowchart TD
    User["Host agent / user prompt"] --> Hook["Prompt hook entrypoint"]
    HostSource["Host transcript source"] --> Provider["conversation source provider"]
    Provider --> SourceBuilder["clean-source builder"]
    SourceBuilder --> Source["clean source + source refs"]
    Hook --> Decision["prompt_recall_* decision layer"]
    Decision --> Registry["registry + clean-source lookup"]
    Decision --> Retrieval["retrieval/query/scoring policy"]
    Decision --> Semantic["optional semantic gate"]
    Decision --> Ambient["ambient cache/cards"]
    Registry --> Source["clean source + source refs"]
    Retrieval --> Source
    Semantic --> Model["optional external model route"]
    Ambient --> Source
    Lifecycle["lifecycle / maintenance hooks"] --> Source
    Lifecycle --> Cache["rebuildable indexes and sidecars"]
    Subconscious["subconscious jobs"] --> Source
    Subconscious --> Model
    Subconscious --> Findings["review-only findings / working memory candidates"]
    Sync["sync / export / MCP surfaces"] --> Source
    Ops["storage, retention, cold archive reports"] -. manual diagnostics .-> Source
```

Core recall is the `Hook -> Decision -> Registry/Retrieval/Semantic/Ambient`
path. Maintenance and storage tools may inspect the same generated artifacts,
but they must not become foreground recall dependencies. If a future deployment
split moves storage, retention, or cold archive work into another process, the
core recall path should still be able to run from registry, clean source, and
its rebuildable lookup sidecars.

## Status Legend

- Public entrypoint: documented or user-facing CLI / hook / MCP command.
- Runtime internal: shipped with the installable skill but called through a
  public entrypoint or scheduler.
- Repo maintenance: shipped script used for diagnostics, storage accounting, or
  operator workflows; not a stable user API.
- Rebuildable cache: may write generated indexes or sidecars, never canonical
  source truth.

## Repo Import Boundary

The installable runtime is still script-first: public and internal runtime code
lives under `skills/aippocampus/scripts/` and must keep direct script invocation
working after the skill is copied into Codex home.

Runtime helpers may move under `skills/aippocampus/scripts/aippocampus_runtime/`
when a narrow ownership boundary is clear. Keep the old top-level script/import
name as a thin compatibility shim until the public stability boundary says it
can be removed.

Current package pilots:

| Package | Top-level compatibility shims | Owner boundary |
|---|---|---|
| `aippocampus_runtime/artifacts/` | `artifact_publish.py` | Generated artifact leases, SQLite publish, and last-known-good pointer helpers shared by build/search/sync paths. |
| `aippocampus_runtime/cli/` | `aippocampus_cli.py` | Public `aippocampus` command facade and child-script dispatch policy. |
| `aippocampus_runtime/core.py` | `aippocampuslib.py` | Shared runtime helpers for provider-neutral storage defaults, raw-source compatibility helpers, text compaction, redaction, HTTP credential transport checks, CLI error payloads, file hashing, and thread-anchor parsing. |
| `aippocampus_runtime/health.py` | `aippocampus_health.py` | Runtime readiness, registry artifact health, optional question stats, and maintenance-action rendering shared by CLI, MCP, and frozen binaries without subprocess script dispatch. |
| `aippocampus_runtime/privacy.py` | `privacy_projection.py` | Public-safe projection helpers that redact local paths from registry/MCP payloads without changing private source truth. |
| `aippocampus_runtime/coding/` | `coding_rejected_route_probes.py`, `coding_ticket_host_contract.py` | Dream retrospective fixture adapter for source-backed rejected coding routes, plus host consumption contract and simulator for source-backed coding-continuity tickets. |
| `aippocampus_runtime/dream/` | `dream_delivery_policy.py`, `dream_input_pack.py`, `dream_one_sidedness.py`, `dream_precision_policy.py`, `dream_queue.py`, `dream_retrospective_lifecycle.py`, `dream_sleep_cycle.py`, `dream_worker.py`, `dream_worker_contract.py`, `dream_working_memory.py` | Hook-safe dream delivery policy, source-backed dream input packs, deterministic one-sidedness gating, deterministic dream-hypothesis precision policies, detached queue planning, retrospective lifecycle checks for parked future-facing probes, detached sleep-cycle queue execution, bounded model-backed dream workers, stable bounded-worker prompt contract, and background-adjudicated working-memory projection. |
| `aippocampus_runtime/mcp/` | `aippocampus_mcp_server.py` | Read-mostly MCP server implementation for agent clients, with privacy projection, registry/search, sync helpers, and latest-reply lookup imported through package owners rather than flat scripts. |
| `aippocampus_runtime/question/` | `question_confirmation.py`, `question_feedback_policy.py`, `question_health.py`, `question_source_refs.py`, `question_tracking.py`, `question_vector_index.py` | Borderline confirmation artifact helpers, source-id-backed feedback pressure, derived question lifecycle health stats, source-ref resolution, deterministic question-link tracking, and optional local vector-index hinting. |
| `aippocampus_runtime/recall/` | `active_recall.py`, `ambient_recall_cards.py`, `ambient_recall_policy.py`, `ambient_thread_cache.py`, `prompt_context_render.py`, `prompt_cues.py`, `prompt_life_cues.py`, `prompt_recall_ambient.py`, `prompt_recall_ambiguity.py`, `prompt_recall_budget.py`, `prompt_recall_context.py`, `prompt_recall_core.py`, `prompt_recall_decision.py`, `prompt_recall_evidence.py`, `prompt_recall_semantic.py`, `retrieval.py`, `retrieval_query_policy.py`, `retrieval_score_fusion.py`, `semantic_cue_cache.py`, `semantic_recall_gate.py`, `semantic_trigger_router.py` | Foreground recall decisions, prompt-hook rendering/budgets/context/evidence, semantic gate/cache/trigger routing, life/profile cue policy, active recall, ambient cards/cache/policy, query policy, retrieval execution, and score fusion. |
| `aippocampus_runtime/source/` | `build_clean_source.py`, `build_semantic_scope_labels.py`, `latest_reply.py`, `rollout_behavior_events.py`, `search_clean_source.py`, `semantic_scope_labels.py` | Clean-source corpus building, latest assistant reply lookup for raw audit fallback, direct clean-source search, rollout behavior-event extraction, dynamic semantic scope-label sidecar validation/merge, semantic sidecar materialization, and portable registry member path repair. |
| `aippocampus_runtime/subconscious/` | `memory_candidate_router.py`, `question_resolution.py`, `subconscious_agent.py`, `subconscious_deterministic_jobs.py`, `subconscious_job_circuits.py`, `subconscious_job_plan.py`, `subconscious_job_storage.py`, `subconscious_job_validation.py`, `subconscious_jobs.py`, `subconscious_jobs_config.py`, `subconscious_question_diagnostics.py`, `subconscious_runtime.py`, `subconscious_scheduler.py`, `subconscious_tool_loop.py`, `subconscious_validation_audit.py`, `subconscious_worker.py`, `theme_emergence.py` | Candidate routing and hook-safe foreground stripping, minimal read-only tool-loop agent runner, deterministic follow-up dispatch, deterministic question-resolution/theme-emergence runners, job circuit/schema contracts, sample-wave planning, append-only job-finding storage, finding validation, model/deterministic job runner orchestration, run configuration/default-path helpers, question-extraction diagnostics, shared read-only runtime primitives, hook-safe detached scheduler, shared tool/final loop helpers, validation diagnostics, and single-shot consolidation worker helpers used by subconscious job runners. |
| `aippocampus_runtime/sync/` | `sync_bundle.py`, `sync_contract.py` | Local-folder sync bundle command plus shared manifest, transport metadata, and privacy boundary helpers reused by sync routes. |
| `aippocampus_runtime/sync/encrypted/` | `encrypted_sync_bundle.py`, `encrypted_sync_crypto.py`, `encrypted_sync_keys.py`, `encrypted_sync_migration.py`, `encrypted_sync_object_storage.py` | Age-backed encrypted bundle, key, migration, and object-storage helpers. |
| `aippocampus_runtime/sync/object_storage/` | `sync_object_storage.py`, `object_storage_client.py`, `object_storage_providers.py` | Object-storage sync command, client construction, and provider signing helpers. |
| `aippocampus_runtime/warm_ambient/` | `ambient_warm_scheduler.py`, `warm_ambient_prompting.py`, `warm_ambient_scout_profiles.py`, `warm_ambient_source_validation.py` | Detached warm-job scheduling, prompt rendering, scout taxonomy, and source-ref validation for warm ambient recall. |

Repo-owned docs, smoke, and benchmark tools may import runtime helpers through
`tools/aippocampus/repo_paths.py`. The local `_paths.py` files in docs, smoke,
and benchmark folders are compatibility wrappers around that single helper, not
new public APIs. New repo maintenance tools should reuse that helper instead of
adding fresh ad hoc `sys.path` insertion rules.

## Protocol-First Ports

AIppocampus uses Protocol-first ports selectively; this is not a tagless-final architecture.
Introduce a `Protocol` only when a runtime boundary has real replacement pressure:
multiple host providers, optional local versus external
implementations, test doubles that need the same contract, or backend adapters
whose behavior must be swapped without changing source-backed payloads.

Do not introduce a port for pure helper functions, one-off call sites, package
cleanup, or code that is already clearer as direct source-backed transformation.
The default shape is still ordinary typed functions plus dataclasses/typed dicts
for durable payloads. A useful port must make a concrete swap safer; it must not
create a second schema owner, dependency-injection framework, or abstraction
layer whose only proof is that future code might need it.

When a port is justified:

- Keep the `Protocol` tiny and behavior-focused.
- Keep source ids/source refs in the payload contract, not hidden in adapter
  state.
- Provide a deterministic local or test implementation when useful.
- Preserve compatibility shims only for existing public commands/imports.
- Add tests that swap the implementation and prove source-backed evidence keys
  survive the boundary.

Current pilots:

- `ConversationProvider` is the ingestion port for Codex, Claude Code, generic
  JSONL, and future host transcript sources. Clean-source tests include a
  deterministic provider double and assert that `source_ref`, `source_id`,
  message ids, and turn links survive the swap.
- `QuestionVectorIndex` is an advisory vector-neighbor port. Its local
  implementation returns stable `source_id` values and a truth-boundary marker;
  vector scores remain navigation hints until clean source is reopened.

## Repo Smoke And Readiness Tools

| Tool or group | Purpose | Invocation route | Key dependencies | Status |
|---|---|---|---|---|
| `tools/aippocampus/smoke/smoke_codex_long_session_continuity.py` | Slow/live real Codex app-server long-session smoke for synthetic correction survival across host compaction, plus clean-source rebuild verification. | Manual public-readiness command; not part of the fast deterministic tier. | Codex app-server, `build_clean_source.py`, existing real-host smoke client. | Repo maintenance |
| `tools/aippocampus/smoke/smoke_claude_code_history.py` | Privacy-preserving local Claude Code history parser smoke that reports counts and booleans only. | Manual provider-readiness command; not part of the fast deterministic tier. | `conversation_sources/claude_code.py`; local Claude Code `projects/**/*.jsonl` store. | Repo maintenance |
| `tools/aippocampus/smoke/smoke_cross_agent_continuity.py` | Deterministic synthetic Codex/Claude source-backed retrieval smoke through registry clean source and MCP `search_memory`. | Manual provider-readiness command and fast reviewed sensitive test coverage. | Codex/Claude providers, registry, MCP search. | Repo maintenance |
| `tools/aippocampus/smoke/smoke_question_confirmation_live.py` | Sanitized no-write smoke for optional live question-pair confirmation and tracking round trip. | Manual #134 calibration smoke; dry-run unless `--call-model` is passed. | `aippocampus_runtime/question/{tracking,confirmation_live}.py`, temporary JSONL artifacts only. | Repo maintenance |

## Public Entrypoints And Install Flow

| Script or group | Purpose | Invocation route | Key dependencies | Status |
|---|---|---|---|---|
| `aippocampus_runtime/cli/facade.py` and `aippocampus_cli.py` compatibility shim | Composable `aippocampus` command facade over packaged entrypoint mains. | Console script / operator CLI; old direct script path remains available. | In-process command resolution via `CommandInvocation`; `run_command(..., capture_output=True)` returns a `CommandResult` for Python callers while preserving child JSON and exit codes. | Public entrypoint |
| `aippocampus_runtime/health.py` and `aippocampus_health.py` compatibility shim | Runtime readiness, public smoke checks, and optional derived question stats. | CLI, install docs, CI-adjacent smoke, MCP `memory_health`, active recall, registry registration, and frozen binaries. | `HealthOptions`, `build_health_report()`, and `health_report()` are the package API; CLI parsing/rendering stays at the edge. Core checks depend on `aippocampus_runtime/core.py`, `aippocampus_runtime/registry/store.py`, and filesystem/env state. Optional question stats are lazy-loaded so basic health does not pull the question/registry/subconscious graph at import time. | Public entrypoint |
| `aippocampus_maintenance.py` | Compact maintenance wrapper for routine operator checks. | CLI/manual maintenance. | Health, registry, docs/smoke conventions. | Repo maintenance |
| `aippocampus_runtime/onboarding/{facade,codex,frontier,status}.py` plus `onboard.py`, `onboard_codex.py`, `onboard_frontier.py`, and `onboard_status.py` compatibility shims | Build or report source-backed onboarding state. `facade.py` is the provider-aware facade; `codex.py` remains the Codex/default provider runner; `frontier.py` owns the optional external-model frontier boundary. | CLI and install/readiness workflows. | Clean source, registry, project timeline, optional external model env. | Public entrypoint |
| `export_bundle.py`, `import_bundle.py`, `checkpoint.py` | Move or checkpoint clean-source memory bundles. | CLI/manual export/import. | Registry paths, clean-source manifests, privacy boundaries. | Public entrypoint |
| `append_anchor.py`, `latest_reply.py`, `locate_rollout.py` | Raw rollout audit and recovery helpers; `latest_reply.py` is a compatibility shim over `aippocampus_runtime/source/latest_reply.py`. | CLI/debug paths only. | Raw rollout files, thread anchors, and packaged source helpers. | Repo maintenance |

## Conversation Source Providers

Conversation providers are the ingestion boundary between host-agent transcript
storage and AIppocampus clean source. They may know about Codex, Claude Code, or
future hosts, but clean source, registry rows, retrieval, sync, MCP, semantic
sidecars, and subconscious jobs should consume provider-normalized source
identity rather than host-specific storage layouts.

Provider modules must not decide where AIppocampus stores generated artifacts.
Registry storage remains owned by `aippocampus_runtime/registry/store.py` and
`aippocampus_registry_dir()`: `AIPPOCAMPUS_REGISTRY_DIR` and the legacy
`CODEX_HOME/aippocampus-registry` path are storage compatibility concerns, not
conversation-provider homes.

| Script or group | Purpose | Invocation route | Key dependencies | Status |
|---|---|---|---|---|
| `conversation_sources/base.py` | Shared `ConversationProvider`, `ConversationSourceRef`, and provider-normalized visible message shapes. | Imported by registry/onboarding/source builders. | Standard library typing/dataclasses only. | Runtime internal |
| `conversation_sources/codex.py` | Codex Desktop provider for live `sessions/` and `archived_sessions/` rollout JSONL discovery, current-cwd lookup, metadata extraction, and thread identity. | Legacy wrappers in `aippocampus_runtime/core.py`, registry scan, current-thread registration. | Codex rollout JSONL first-line `session_meta`; no registry writes. | Runtime internal |
| `conversation_sources/claude_code.py` | Claude Code provider for local `projects/**/*.jsonl` transcript discovery, current-cwd lookup, public metadata extraction, provider-prefixed thread identity, and visible-message clean-source parsing. | `onboard.py --provider claude-code`, registry scan, provider smoke tests. | Claude Code JSONL top-level `sessionId` / `cwd` / `timestamp`; filters thinking/tool payloads from daily clean source. | Runtime internal |
| `conversation_sources/generic_jsonl.py` | Validated generic JSONL import provider for non-Codex/non-Claude hosts. | `onboard.py --provider generic-jsonl`, explicit import/smoke paths. | `AIPPOCAMPUS_GENERIC_IMPORT_DIR` or explicit provider path; rejects ambiguous roles/turns. | Runtime internal |

Claude Code support has a clean-source parser for visible text and explicit
registration. Host MCP setup remains a separate integration surface documented
in `docs/guides/claude-code-mcp.md`. The repository also ships a minimal
project skill at `.claude/skills/aippocampus/SKILL.md` that points Claude Code
at the existing MCP/CLI surfaces; Claude Code hooks and configuration-mutating
installers are not claimed by the provider contract.

## Hook Paths

| Script or group | Purpose | Invocation route | Key dependencies | Status |
|---|---|---|---|---|
| `aippocampus_runtime/hooks/prompt.py` plus `aippocampus_prompt_hook.py` compatibility shim | Foreground prompt hook that emits skip/scent/evidence under a strict budget. | Opt-in Codex `UserPromptSubmit` hook; direct script path remains stable for Codex hook configs. | Packaged prompt recall modules, Dream delivery boundary, registry/search modules. | Public entrypoint |
| `aippocampus_runtime/hooks/lifecycle.py` plus `aippocampus_lifecycle_hook.py` compatibility shim | Lifecycle hook for deterministic maintenance around Codex session events. | Opt-in Codex lifecycle hook; direct script path remains stable for Codex hook configs. | Clean source, registry, maintenance helpers. | Public entrypoint |
| `aippocampus_runtime/hooks/install_prompt.py` and `aippocampus_runtime/hooks/install_lifecycle.py` plus `install_aippocampus_prompt_hook.py` / `install_aippocampus_lifecycle_hook.py` compatibility shims, `diagnose_hooks.py` | Install and diagnose hook wiring. | CLI/install docs. | Codex config paths, hook command validation. | Public entrypoint |
| `aippocampus_runtime/recall/prompt_*`, `aippocampus_runtime/recall/semantic_*`, and top-level compatibility shims (`prompt_cues.py`, `prompt_life_cues.py`, `prompt_context_render.py`, `prompt_recall_*.py`, `semantic_cue_cache.py`, `semantic_recall_gate.py`, `semantic_trigger_router.py`) | Prompt recall policy, life-wide/profile cue catalogs, ambient cards/cache/policy, budget, rendering, query policy, source-evidence assembly, optional semantic gate/cache, and trigger routing. | Called by prompt hook, active recall, scheduler, and smokes. | Registry/search, timeline, semantic cue cache, model route metadata. | Runtime internal |

## Registry, Retrieval, And Indexing

| Script or group | Purpose | Invocation route | Key dependencies | Status |
|---|---|---|---|---|
| `aippocampus_runtime/registry/{api,store,search,provider}.py`, `registry.py`, and `registry_store.py` / `registry_search.py` / `registry_provider.py` compatibility shims | Resolve registry paths, register/scan thread rows, search registry metadata, and build provider-aware thread keys. | Most runtime entrypoints; `registry.py` remains the public CLI/import compatibility shim over `api.py`. | Global registry layout and privacy policy. | Runtime internal |
| `aippocampus_runtime/source/{behavior_events,clean_source,latest_reply,registry_paths,search,semantic_scope_builder,semantic_scope_labels}.py`, `build_clean_source.py` / `build_semantic_scope_labels.py` / `latest_reply.py` / `rollout_behavior_events.py` / `search_clean_source.py` / `semantic_scope_labels.py` compatibility shims | Convert provider-normalized transcript messages into source-backed clean messages/turns, find the latest assistant reply for raw-audit fallback, search clean-source JSONL directly, validate/merge semantic scope-label sidecars, materialize sidecars from source-backed findings, repair portable registry member paths, and emit structured rollout behavior events. | Onboarding, import, MCP/search surfaces, maintenance, tests. | Provider parsers, raw transcript audit, scope-label policy, clean-source JSONL, semantic sidecars, tool/test event hashing. | Public entrypoint |
| `aippocampus_runtime/recall/{retrieval,query_policy,score_fusion,rollout_search}.py`, `retrieval.py` / `retrieval_query_policy.py` / `retrieval_score_fusion.py` / `search_rollout.py` compatibility shims | Source-backed retrieval, explicit score-fusion policy, and raw audit fallback. | Prompt hook, MCP, CLI search surfaces, future vector/graph fusion consumers. | Clean-source JSONL, registry rows, query policy, stable source ids/source refs; scores remain ranking hints only. | Runtime internal |
| `aippocampus_runtime/recall/{index_builder,segment_builder,segment_search}.py` plus `build_index.py`, `build_segments.py`, and `search_segments.py` compatibility shims, and `aippocampus_runtime/artifacts/publish.py` plus `artifact_publish.py` compatibility shim | SQLite/RAG-lite index, large-thread segment fanout, artifact leases, and last-known-good publish pointers. | Maintenance, query paths, scale smokes, and sync bundle reads. | Clean source, segment manifests, last-known-good publish semantics. | Rebuildable cache |
| `aippocampus_runtime/navigation/{associations,project_timeline}.py` plus `build_associations.py` / `build_project_timeline.py` compatibility shims | Timeline and source-derived associations. | Onboarding, prompt recall, semantic smokes. | Registry rows, clean source, optional model sidecars. | Rebuildable cache |
| `aippocampus_runtime/navigation/{concept_graph,cognitive_map}.py` plus `build_concept_graph.py` / `build_cognitive_map.py` compatibility shims, `aippocampus_runtime/question/vector_index.py` plus `question_vector_index.py` compatibility shim, and `aippocampus_runtime/question/index_sidecar.py` plus `question_index_sidecar.py` compatibility shim | Advisory graph/map/vector/navigation layers, including optional question-index sidecar evaluation. | Maintenance, research smokes, future question tracking. | Clean-source ids, source-ref fingerprints, source signatures; never truth replacement. | Rebuildable cache |
| `aippocampus_runtime/question/{confirmation,tracking}.py` plus `question_confirmation.py` / `question_tracking.py` compatibility shims | Deterministic question-link tracking plus borderline confirmation artifact parsing and audit diagnostics. | Deterministic job runner, manual CLI, and future live calibration; top-level scripts remain direct compatibility paths. | Pair ids, compact source-backed question payloads, source refs, salience/threshold policy; no full-history model input. | Runtime internal |
| `aippocampus_runtime/question/confirmation_live.py` plus `question_confirmation_live.py` compatibility shim | Optional live/model adapter from pending question-pair confirmation requests to explicit confirmation artifacts. | Manual #134 calibration, future scheduler integration; default dry-run unless `--call-model` is passed. | Pending request JSONL, OpenAI-compatible model route, no clean-source messages or full source refs in model payload. | Runtime internal |
| `aippocampus_runtime/question/{feedback_policy,source_refs}.py` plus `question_feedback_policy.py` / `question_source_refs.py` compatibility shims | Source-id-backed dismissal/reopen feedback adapter and compact source-ref resolution helpers for question-pair separation pressure. | Imported by packaged question tracking and sibling question/semantic helpers. | `ambient_recall_policy.jsonl` events with source finding ids, registry clean-source refs; unsourced feedback fails open. | Runtime internal |
| `aippocampus_runtime/subconscious/theme_emergence.py` plus `theme_emergence.py` compatibility shim | Deterministic Phase 3 theme candidates over recurring source-backed question links and concept-graph neighbors. | Imported by deterministic job runner; optional CLI for no-write diagnostics. | `subconscious_jobs.jsonl`, `concept_index.sqlite`, question-link source refs, frontier-marker rows. | Runtime internal |
| `aippocampus_runtime/question/health.py` and `question_health.py` compatibility shim | Derived aggregate question lifecycle and health stats for source-backed subconscious job rows, with explicit local-detail mode. | `aippocampus_health.py --question-stats`, manual diagnostics. | `subconscious_jobs.jsonl`, optional registry clean-source ref resolution. | Repo maintenance |
| `aippocampus_runtime/subconscious/question_resolution.py` plus `question_resolution.py` compatibility shim | Deterministic explicit user follow-up resolution signal extraction for tracked questions. | Deterministic `subconscious_jobs.py` follow-up after `question_tracking`, plus manual diagnostics; feeds packaged question health through append-only `question_resolution_signal` rows. | Registry clean-source user turns, tracked question rows, compact source refs; no raw follow-up text in emitted signals. | Runtime internal |
| `storage_capacity_report.py`, `rollout_size_audit.py`, `retention_report.py`, `cold_archive.py` | Storage, retention, and capacity diagnostics. | Manual readiness / GB-scale work. | Registry and generated-artifact accounting. | Repo maintenance |

These diagnostics are deliberately outside the core recall path. They can read
registry, clean-source manifests, raw rollout audit paths, and generated
sidecars to answer operator questions, but foreground prompt recall should not
import them or wait on them. The user-facing cleanup sequence remains
`retention_report.py --write` before `cold_archive.py`.

## MCP Surface

| Script or group | Purpose | Invocation route | Key dependencies | Status |
|---|---|---|---|---|
| `aippocampus_runtime/mcp/server.py` and `aippocampus_mcp_server.py` compatibility shim | Read-mostly MCP server for agent clients. | MCP config, plugin install path, and package API consumers. | Packaged registry, source search/latest-reply, sync, core, and privacy helpers; public schema boundary. | Public entrypoint |

The MCP server must remain read-mostly unless a future issue explicitly expands
write APIs with privacy review. It should not become the owner of lifecycle,
sync, or retention policy.

## Sync And Vault Projection

This section is the canonical sync responsibility map. Keep README and install
docs focused on commands; put sync ownership changes here instead of mirroring
the contract across multiple docs.

`aippocampus_runtime.sync.contract` owns reusable manifest, transport, and
privacy metadata helpers; `sync_contract.py` remains the compatibility import
shim. `aippocampus_runtime.sync.bundle` owns the local bundle CLI plus portable
registry locators, clean-source chunk selection, relative-path validation,
managed-directory safety, and conflict-preserving pull behavior.
`sync_bundle.py` remains the public direct-script/import compatibility shim.
Transport modules must reuse those contracts rather than inventing their own
manifest, file-selection, path, conflict, or raw-rollout defaults.

| Script or group | Purpose | Invocation route | Key dependencies | Status |
|---|---|---|---|---|
| `aippocampus_runtime/sync/{bundle,contract}.py` plus `sync_bundle.py` / `sync_contract.py` compatibility shims | Shared manifest/privacy contract plus local-folder clean-source bundle sync. | CLI/sync docs; top-level scripts remain direct-script/import compatibility shims. | Content-addressed chunks, path repair, conflict policy. | Public entrypoint |
| `aippocampus_runtime/sync/object_storage/{cli,client,providers}.py` plus `sync_object_storage.py` / `object_storage_*` compatibility shims | HTTP/S3/R2/GCS-compatible object transport. | CLI/sync docs; `sync_object_storage.py` remains the public command shim. | Shared bundle semantics, provider config, no secret logging. | Public entrypoint |
| `encrypted_sync_admin.py`, `aippocampus_runtime/sync/encrypted/{bundle,object_storage,crypto,keys,migration}.py`, and `encrypted_sync_*` compatibility shims | Age-backed encrypted sync overlay, device-key UX, and plaintext migration helpers. | CLI/encrypted sync docs; `encrypted_sync_admin.py` remains the public command. | Sync bundle/object transport plus key handling. | Public entrypoint |
| `vault_sync_utils.py`, `sync_vault.py`, `vault_notes.py`, `vault_dashboard.py` | Human-readable vault projection and dashboard. | CLI/manual projection. | Clean source and registry rows; not a transport backend. | Public entrypoint |

The local-folder route writes the bundle directly. The object-storage route is
only a PUT/GET adapter over the same bundle. The encrypted route wraps a
temporary plaintext bundle with `age`, refuses mixed plaintext/encrypted roots
or object prefixes, and imports through the same repair/pull semantics after
decryption. `sync_vault.py` is a projection surface, not a third transport
implementation.

Sync code must preserve raw-rollout opt-in, path traversal checks, conflict
preservation, and encrypted-sync requirements. If a future refactor touches
transport or encryption, add tests that prove the shared manifest privacy
boundary still reaches local-folder, object-storage, and encrypted paths.

## Subconscious Jobs And External Models

| Script or group | Purpose | Invocation route | Key dependencies | Status |
|---|---|---|---|---|
| `aippocampus_runtime/subconscious/jobs.py` plus `subconscious_jobs.py` compatibility shim, `subconscious_scheduler.py`, `subconscious_worker.py`, `aippocampus_runtime/question/tracking.py` plus `question_tracking.py` compatibility shim, `aippocampus_runtime/subconscious/{question_resolution,theme_emergence}.py` plus `question_resolution.py` / `theme_emergence.py` compatibility shims, `journey_tracking.py`, `compensatory_dream.py`, `aippocampus_runtime/dream/{input_pack,one_sidedness,precision_policy,queue,retrospective_lifecycle,sleep_cycle,worker,worker_contract,working_memory}.py` plus `dream_input_pack.py` / `dream_one_sidedness.py` / `dream_precision_policy.py` / `dream_queue.py` / `dream_retrospective_lifecycle.py` / `dream_sleep_cycle.py` / `dream_worker.py` / `dream_worker_contract.py` / `dream_working_memory.py` compatibility shims, `aippocampus_runtime/coding/rejected_route_probes.py` plus `coding_rejected_route_probes.py` compatibility shim, `aippocampus_runtime/dream/delivery_policy.py` plus `dream_delivery_policy.py` compatibility shim, `dream_real_history_eval.py`, `dream_live_shadow_ab.py`, `reflection_space.py` | Schedule and run background semantic/subconscious jobs, including deterministic Phase 2 question-link tracking, deterministic explicit question-resolution signals, deterministic Phase 3 theme candidates, source-backed Journey P1-P3 helpers, Phase 1 compensatory dream candidates, P2 cross-thread dream input packs, deterministic dream queue lifecycle planning, detached sleep-cycle queue execution with no-write defaults, precision policies that keep hard gates separate from soft lifecycle pressure, deterministic one-sidedness gating before opposite-hexagram dream probes, retrospective lifecycle checks for parked future-facing dream probes, coding rejected-route Dream probe fixtures, bounded model-backed compensatory/amplification/prospective dream workers and their stable prompt contract, active-imagination sandbox candidates, selected real-history structural dream eval, opt-in live shadow/delivered A/B reminder-frequency ledger and hook policy plus public clean-source directory negative-control replay, background-adjudicated dream-hypothesis projection to working memory, and reflection-space topology/feedback MVP helpers with collapsed dream-hypothesis nodes. | CLI, scheduler, opt-in maintenance. | Registry, model client, route metadata, job validation, source-backed question candidates with source-derived scope labels, journey waypoints, extraction rows, question links, explicit user follow-up resolution refs, concept-graph neighbors, theme candidate refs, Journey rows, coding decision events, working-memory rows, ambient residue handles, dream input packs, dream queue metadata, dream precision policy components, dream one-sidedness gate rows, dream sleep-cycle lifecycle rows, dream retrospective lifecycle rows, coding rejected-route probe rows, dream candidate refs, adjudicated dream source refs, active-imagination audit gates, retrospective prospective-validation events, benchmark-corpus clean-source rows, shadow/delivered A/B event rows, and reflection feedback rows. | Public entrypoint |
| `aippocampus_runtime/subconscious/{agent,deterministic_jobs,job_circuits,job_plan,job_storage,job_validation,jobs,jobs_config,question_diagnostics,question_resolution,runtime,scheduler,theme_emergence,tool_loop,validation_audit,worker}.py` plus `subconscious_agent.py` / `subconscious_deterministic_jobs.py` / `subconscious_job_circuits.py` / `subconscious_job_plan.py` / `subconscious_job_storage.py` / `subconscious_job_validation.py` / `subconscious_jobs.py` / `subconscious_jobs_config.py` / `subconscious_question_diagnostics.py` / `question_resolution.py` / `subconscious_runtime.py` / `subconscious_scheduler.py` / `theme_emergence.py` / `subconscious_tool_loop.py` / `subconscious_validation_audit.py` / `subconscious_worker.py` compatibility shims | Runtime loops, tool execution, minimal read-only tool-loop agent runner, deterministic follow-up dispatch and deterministic follow-up runners, job circuit/schema contracts, sample-wave planning, append-only finding storage, finding validation, job-run orchestration/configuration, question-extraction diagnostics, shared read-only runtime primitives, hook-safe detached scheduling, shared tool/final loop helpers, non-text validation diagnostics, and single-shot consolidation worker helpers for background agents/jobs. | Scheduler/worker internals. | Job config, external model client, registry outputs. | Runtime internal |
| `subconscious_review.py`, `aippocampus_runtime/subconscious/candidate_router.py` plus `memory_candidate_router.py` compatibility shim, `subconscious_job_validation.py`, `subconscious_job_circuits.py`, `correction_reconsolidation.py`, `coding_decision_events.py`, `aippocampus_runtime/coding/host_contract.py` plus `coding_ticket_host_contract.py` compatibility shim, `agency_affordance.py` | Review, route, validate, and adjudicate findings before promotion, including correction activation/outcome evidence, coding decision candidates, coding-ticket host consumption simulation, conservative source-backed agency tickets, and backstage-only dream-hypothesis agency safeguards. | Worker, maintenance CLI, and tests. | Working-memory rules, source refs, candidate schemas, privacy-scanned append-only event rows, clean-source message refs, coding continuity host contract fields, dream sensitive-use gates, host-owned permission and sequencing boundaries. | Runtime internal |
| `aippocampus_runtime/model/{client,routing}.py`, plus `model_client.py` and `deepseek_model_routing.py` compatibility shims | External-model request helper and provider route/capability metadata. | Semantic gates and subconscious jobs. | Env config, redaction, provider-specific capability gates. | Runtime internal |
| `semantic_scope_source_review_core.py`, `semantic_scope_suppressed_recovery.py` | Source review and suppressed-label recovery flows. | Smoke/maintenance and optional pro-model jobs. | Clean source, model client, semantic route metadata. | Repo maintenance |

Generated findings, sidecars, and vector neighbors are advisory until they point
back to clean source. External-model features must stay optional.

## Warm Ambient Recall

| Script or group | Purpose | Invocation route | Key dependencies | Status |
|---|---|---|---|---|
| `aippocampus_runtime/warm_ambient/{recall,scheduler,prompting,scout_profiles,source_validation}.py` plus `warm_ambient_*` and `ambient_warm_scheduler.py` compatibility shims | Multi-scout ambient recall, detached warm-job scheduling, prompting, profile taxonomy, and validation. | Optional warm recall jobs and smokes; top-level `warm_ambient_recall.py` and `ambient_warm_scheduler.py` remain direct-script/import shims. | Registry, clean source, semantic/model routes, privacy filters, prompt-hook enqueue budget. | Runtime internal |
| `aippocampus_runtime/recall/{active_recall,ambient_cache,ambient_cards,ambient_policy}.py`, `active_recall.py`, and `ambient_*` compatibility shims | Cache, anti-nag policy overlay, active recall cards, and thread-level ambient state. | Hook/maintenance/warm recall paths. | Thread cache, source-backed card rendering, hash-only dismissal/surface events. | Runtime internal |

Warm ambient output should remain quiet and advisory unless a prompt explicitly
needs source-backed evidence. Do not let scout summaries replace clean source.

## Recall Decision Test Map

The recall tests are intentionally split by responsibility rather than gathered
into one giant fixture file. Use this map when changing core recall behavior:

| Surface | Primary tests | What they protect |
|---|---|---|
| Prompt hook glue and budgets | `tests/aippocampus/test_aippocampus_prompt_hook.py`, `tests/aippocampus/test_prompt_recall_decision_boundaries.py` | Hook output shape, quiet/default behavior, budget boundaries, ambient attach rules, and decision-module ownership. |
| Deterministic cue and semantic gate | `tests/aippocampus/test_semantic_recall_gate.py`, `tests/aippocampus/test_semantic_trigger_router.py`, `tests/aippocampus/test_semantic_cue_cache.py` | Vague-continuation gating, semantic trigger review, cache behavior, and unavailable-model diagnostics. |
| Source-backed retrieval | `tests/aippocampus/test_search_clean_source.py`, `tests/aippocampus/test_retrieval_query_policy.py`, `tests/aippocampus/test_retrieval_score_fusion.py` | Query expansion, scoring hints, clean-source search, and source-ref-preserving result ranking. |
| Warm ambient recall | `tests/aippocampus/test_warm_ambient_recall.py`, `tests/aippocampus/test_benchmark_warm_ambient_recall.py`, `tests/aippocampus/test_benchmark_warm_ambient_sweep.py` | Scout merge behavior, source validation, privacy guards, cache write policy, and benchmark payload contracts. |
| Architecture and coupling guardrails | `tests/aippocampus/test_import_coupling.py`, `tests/aippocampus/test_architecture_boundaries.py` | Import boundaries, hook/core separation, large-script debt registration, and high-risk mypy coverage. |

For ordinary documentation-only changes, the fast deterministic command remains
`python tools/aippocampus/run_tests.py --tier fast`. For targeted recall-policy
work, run the relevant tests above in addition to the tier command when the
change touches that surface.

## Maintenance Rule

This map intentionally groups low-level helpers. Do not add every helper merely
because it exists. Do update it when a script becomes a public entrypoint,
creates or mutates generated artifacts, calls external models, handles sync or
encryption, participates in hooks/MCP, or owns a durable source boundary.
