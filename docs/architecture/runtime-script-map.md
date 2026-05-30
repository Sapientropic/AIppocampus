# Runtime Script Map

This is the maintainer navigation map for `skills/aippocampus/scripts/`. It is
not a generated call graph and should not mirror every module docstring. Keep it
focused on ownership, invocation routes, dependencies, and public/internal
status for high-risk scripts and public entrypoints.

When adding a new public entrypoint, hook path, sync path, MCP surface,
registry/retrieval component, warm ambient component, or subconscious job
component, update this map and the cheap guard in
`tools/aippocampus/docs/check_docs_health.py`.

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

Repo-owned docs, smoke, and benchmark tools may import runtime helpers through
`tools/aippocampus/repo_paths.py`. The local `_paths.py` files in docs, smoke,
and benchmark folders are compatibility wrappers around that single helper, not
new public APIs. New repo maintenance tools should reuse that helper instead of
adding fresh ad hoc `sys.path` insertion rules.

## Repo Smoke And Readiness Tools

| Tool or group | Purpose | Invocation route | Key dependencies | Status |
|---|---|---|---|---|
| `tools/aippocampus/smoke/smoke_codex_long_session_continuity.py` | Slow/live real Codex app-server long-session smoke for synthetic correction survival across host compaction, plus clean-source rebuild verification. | Manual public-readiness command; not part of the fast deterministic tier. | Codex app-server, `build_clean_source.py`, existing real-host smoke client. | Repo maintenance |
| `tools/aippocampus/smoke/smoke_claude_code_history.py` | Privacy-preserving local Claude Code history parser smoke that reports counts and booleans only. | Manual provider-readiness command; not part of the fast deterministic tier. | `conversation_sources/claude_code.py`; local Claude Code `projects/**/*.jsonl` store. | Repo maintenance |
| `tools/aippocampus/smoke/smoke_cross_agent_continuity.py` | Deterministic synthetic Codex/Claude source-backed retrieval smoke through registry clean source and MCP `search_memory`. | Manual provider-readiness command and fast reviewed sensitive test coverage. | Codex/Claude providers, registry, MCP search. | Repo maintenance |

## Public Entrypoints And Install Flow

| Script or group | Purpose | Invocation route | Key dependencies | Status |
|---|---|---|---|---|
| `aippocampus_cli.py` | Thin `aippocampus` command facade over documented script entrypoints. | Console script / operator CLI. | Existing script mains via subprocess; preserves child JSON and exit codes. | Public entrypoint |
| `aippocampus_health.py` | Runtime readiness and public smoke checks. | CLI, install docs, CI-adjacent smoke. | `registry.py`, `aippocampuslib.py`, filesystem/env checks. | Public entrypoint |
| `aippocampus_maintenance.py` | Compact maintenance wrapper for routine operator checks. | CLI/manual maintenance. | Health, registry, docs/smoke conventions. | Repo maintenance |
| `onboard.py`, `onboard_codex.py`, `onboard_frontier.py`, `onboard_status.py` | Build or report source-backed onboarding state. `onboard.py` is the provider-aware facade; `onboard_codex.py` remains the Codex-only compatibility entrypoint. | CLI and install/readiness workflows. | Clean source, registry, project timeline, optional external model env. | Public entrypoint |
| `export_bundle.py`, `import_bundle.py`, `checkpoint.py` | Move or checkpoint clean-source memory bundles. | CLI/manual export/import. | Registry paths, clean-source manifests, privacy boundaries. | Public entrypoint |
| `append_anchor.py`, `latest_reply.py`, `locate_rollout.py` | Raw rollout audit and recovery helpers. | CLI/debug paths only. | Raw rollout files and thread anchors. | Repo maintenance |

## Conversation Source Providers

Conversation providers are the ingestion boundary between host-agent transcript
storage and AIppocampus clean source. They may know about Codex, Claude Code, or
future hosts, but clean source, registry rows, retrieval, sync, MCP, semantic
sidecars, and subconscious jobs should consume provider-normalized source
identity rather than host-specific storage layouts.

Provider modules must not decide where AIppocampus stores generated artifacts.
Registry storage remains owned by `registry_store.py` and
`aippocampus_registry_dir()`: `AIPPOCAMPUS_REGISTRY_DIR` and the legacy
`CODEX_HOME/aippocampus-registry` path are storage compatibility concerns, not
conversation-provider homes.

| Script or group | Purpose | Invocation route | Key dependencies | Status |
|---|---|---|---|---|
| `conversation_sources/base.py` | Shared `ConversationProvider`, `ConversationSourceRef`, and provider-normalized visible message shapes. | Imported by registry/onboarding/source builders. | Standard library typing/dataclasses only. | Runtime internal |
| `conversation_sources/codex.py` | Codex Desktop provider for live `sessions/` and `archived_sessions/` rollout JSONL discovery, current-cwd lookup, metadata extraction, and thread identity. | Legacy wrappers in `aippocampuslib.py`, registry scan, current-thread registration. | Codex rollout JSONL first-line `session_meta`; no registry writes. | Runtime internal |
| `conversation_sources/claude_code.py` | Claude Code provider for local `projects/**/*.jsonl` transcript discovery, current-cwd lookup, public metadata extraction, provider-prefixed thread identity, and visible-message clean-source parsing. | `onboard.py --provider claude-code`, registry scan, provider smoke tests. | Claude Code JSONL top-level `sessionId` / `cwd` / `timestamp`; filters thinking/tool payloads from daily clean source. | Runtime internal |
| `conversation_sources/generic_jsonl.py` | Validated generic JSONL import provider for non-Codex/non-Claude hosts. | `onboard.py --provider generic-jsonl`, explicit import/smoke paths. | `AIPPOCAMPUS_GENERIC_IMPORT_DIR` or explicit provider path; rejects ambiguous roles/turns. | Runtime internal |

Claude Code support has a clean-source parser for visible text and explicit
registration. Host MCP setup remains a separate integration surface documented
in `docs/guides/claude-code-mcp.md`. Claude Code hook/skill installers are not
claimed by the provider contract.

## Hook Paths

| Script or group | Purpose | Invocation route | Key dependencies | Status |
|---|---|---|---|---|
| `aippocampus_prompt_hook.py` | Foreground prompt hook that emits skip/scent/evidence under a strict budget. | Opt-in Codex `UserPromptSubmit` hook. | `prompt_recall_*`, `semantic_recall_gate.py`, registry/search modules. | Public entrypoint |
| `aippocampus_lifecycle_hook.py` | Lifecycle hook for deterministic maintenance around Codex session events. | Opt-in Codex lifecycle hook. | Clean source, registry, maintenance helpers. | Public entrypoint |
| `install_aippocampus_prompt_hook.py`, `install_aippocampus_lifecycle_hook.py`, `diagnose_hooks.py` | Install and diagnose hook wiring. | CLI/install docs. | Codex config paths, hook command validation. | Public entrypoint |
| `prompt_cues.py`, `prompt_context_render.py`, `prompt_recall_ambient.py`, `prompt_recall_budget.py`, `prompt_recall_context.py`, `prompt_recall_core.py`, `prompt_recall_decision.py`, `prompt_recall_evidence.py` | Prompt recall policy, budget, rendering, and source-evidence assembly. | Called by prompt hook and smokes. | Registry/search, timeline, semantic cue cache. | Runtime internal |
| `semantic_trigger_router.py`, `semantic_recall_gate.py`, `semantic_cue_cache.py` | Optional semantic gate and cache around foreground recall. | Prompt hook and targeted smokes. | `model_client.py`, external model route metadata, cache files. | Runtime internal |

## Registry, Retrieval, And Indexing

| Script or group | Purpose | Invocation route | Key dependencies | Status |
|---|---|---|---|---|
| `registry.py`, `registry_store.py`, `registry_search.py` | Resolve registry paths, store thread rows, and search registry metadata. | Most runtime entrypoints. | Global registry layout and privacy policy. | Runtime internal |
| `build_clean_source.py` | Convert provider-normalized transcript messages into source-backed clean messages/turns. | Onboarding, import, maintenance, tests. | Provider parsers, raw transcript audit, scope-label policy. | Public entrypoint |
| `retrieval.py`, `retrieval_query_policy.py`, `retrieval_score_fusion.py`, `search_clean_source.py`, `search_rollout.py` | Source-backed retrieval, explicit score-fusion policy, and raw audit fallback. | Prompt hook, MCP, CLI search surfaces, future vector/graph fusion consumers. | Clean-source JSONL, registry rows, query policy, stable source ids/source refs; scores remain ranking hints only. | Runtime internal |
| `build_index.py`, `build_segments.py`, `search_segments.py` | SQLite/RAG-lite index and large-thread segment fanout. | Maintenance, query paths, scale smokes. | Clean source, segment manifests, last-known-good publish semantics. | Rebuildable cache |
| `build_project_timeline.py`, `build_semantic_scope_labels.py`, `build_associations.py` | Timeline, semantic sidecars, and source-derived associations. | Onboarding, prompt recall, semantic smokes. | Registry rows, clean source, optional model sidecars. | Rebuildable cache |
| `build_concept_graph.py`, `build_cognitive_map.py`, `question_vector_index.py` | Advisory graph/map/vector navigation layers. | Maintenance, research smokes, future question tracking. | Clean-source ids and source refs; never truth replacement. | Rebuildable cache |
| `storage_capacity_report.py`, `rollout_size_audit.py`, `retention_report.py`, `cold_archive.py` | Storage, retention, and capacity diagnostics. | Manual readiness / GB-scale work. | Registry and generated-artifact accounting. | Repo maintenance |

These diagnostics are deliberately outside the core recall path. They can read
registry, clean-source manifests, raw rollout audit paths, and generated
sidecars to answer operator questions, but foreground prompt recall should not
import them or wait on them. The user-facing cleanup sequence remains
`retention_report.py --write` before `cold_archive.py`.

## MCP Surface

| Script or group | Purpose | Invocation route | Key dependencies | Status |
|---|---|---|---|---|
| `aippocampus_mcp_server.py` | Read-mostly MCP server for agent clients. | MCP config and plugin install path. | Registry, retrieval/search, public schema boundary. | Public entrypoint |

The MCP server must remain read-mostly unless a future issue explicitly expands
write APIs with privacy review. It should not become the owner of lifecycle,
sync, or retention policy.

## Sync And Vault Projection

This section is the canonical sync responsibility map. Keep README and install
docs focused on commands; put sync ownership changes here instead of mirroring
the contract across multiple docs.

`sync_contract.py` owns reusable manifest, transport, and privacy metadata
helpers. `sync_bundle.py` owns the local bundle CLI plus portable registry
locators, clean-source chunk selection, relative-path validation,
managed-directory safety, and conflict-preserving pull behavior. Transport
modules must reuse those contracts rather than inventing their own manifest,
file-selection, path, conflict, or raw-rollout defaults.

| Script or group | Purpose | Invocation route | Key dependencies | Status |
|---|---|---|---|---|
| `sync_contract.py`, `sync_bundle.py` | Shared manifest/privacy contract plus local-folder clean-source bundle sync. | CLI/sync docs. | Content-addressed chunks, path repair, conflict policy. | Public entrypoint |
| `sync_object_storage.py`, `object_storage_client.py`, `object_storage_providers.py` | HTTP/S3/R2/GCS-compatible object transport. | CLI/sync docs. | Shared bundle semantics, provider config, no secret logging. | Public entrypoint |
| `encrypted_sync_bundle.py`, `encrypted_sync_object_storage.py`, `encrypted_sync_crypto.py`, `encrypted_sync_keys.py`, `encrypted_sync_migration.py`, `encrypted_sync_admin.py` | Age-backed encrypted sync overlay, device-key UX, and plaintext migration helpers. | CLI/encrypted sync docs. | Sync bundle/object transport plus key handling. | Public entrypoint |
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
| `subconscious_jobs.py`, `subconscious_jobs_config.py`, `subconscious_scheduler.py`, `subconscious_worker.py`, `question_tracking.py`, `journey_tracking.py`, `compensatory_dream.py`, `dream_input_pack.py`, `dream_queue.py`, `dream_worker.py`, `dream_real_history_eval.py`, `dream_working_memory.py`, `reflection_space.py` | Schedule and run background semantic/subconscious jobs, including deterministic Phase 2 question-link tracking, source-backed Journey P1-P3 helpers, Phase 1 compensatory dream candidates, P2 cross-thread dream input packs, deterministic dream queue lifecycle planning, bounded model-backed compensatory/amplification/prospective dream workers, active-imagination sandbox candidates, selected real-history structural dream eval, background-adjudicated dream-hypothesis projection to working memory, and reflection-space topology/feedback MVP helpers with collapsed dream-hypothesis nodes. | CLI, scheduler, opt-in maintenance. | Registry, model client, route metadata, job validation, source-backed question candidates with source-derived scope labels, journey waypoints, extraction rows, question links, Journey rows, working-memory rows, ambient residue handles, dream input packs, dream queue metadata, dream candidate refs, adjudicated dream source refs, active-imagination audit gates, retrospective prospective-validation events, reflection feedback rows, and topology source refs. | Public entrypoint |
| `subconscious_runtime.py`, `subconscious_agent.py`, `subconscious_tool_loop.py` | Runtime loops and tool execution for background agents. | Scheduler/worker internals. | Job config, external model client, registry outputs. | Runtime internal |
| `subconscious_review.py`, `memory_candidate_router.py`, `subconscious_job_plan.py`, `subconscious_job_validation.py`, `subconscious_job_circuits.py`, `correction_reconsolidation.py`, `coding_decision_events.py`, `agency_affordance.py` | Review, route, plan, validate, and adjudicate findings before promotion, including correction activation/outcome evidence, coding decision candidates, conservative source-backed agency tickets, and backstage-only dream-hypothesis agency safeguards. | Worker, maintenance CLI, and tests. | Working-memory rules, source refs, candidate schemas, privacy-scanned append-only event rows, clean-source message refs, dream sensitive-use gates, host-owned permission and sequencing boundaries. | Runtime internal |
| `model_client.py`, `deepseek_model_routing.py` | External-model request helper and provider route/capability metadata. | Semantic gates and subconscious jobs. | Env config, redaction, provider-specific capability gates. | Runtime internal |
| `semantic_scope_source_review_core.py`, `semantic_scope_suppressed_recovery.py` | Source review and suppressed-label recovery flows. | Smoke/maintenance and optional pro-model jobs. | Clean source, model client, semantic route metadata. | Repo maintenance |

Generated findings, sidecars, and vector neighbors are advisory until they point
back to clean source. External-model features must stay optional.

## Warm Ambient Recall

| Script or group | Purpose | Invocation route | Key dependencies | Status |
|---|---|---|---|---|
| `warm_ambient_recall.py`, `warm_ambient_prompting.py`, `warm_ambient_scout_profiles.py`, `warm_ambient_source_validation.py` | Multi-scout ambient recall, prompting, profile taxonomy, and validation. | Optional warm recall jobs and smokes. | Registry, clean source, semantic/model routes, privacy filters. | Runtime internal |
| `ambient_warm_scheduler.py`, `ambient_thread_cache.py`, `active_recall.py`, `ambient_recall_cards.py` | Scheduling, cache, active recall cards, and thread-level ambient state. | Hook/maintenance/warm recall paths. | Prompt hook budget, thread cache, source-backed card rendering. | Runtime internal |

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
