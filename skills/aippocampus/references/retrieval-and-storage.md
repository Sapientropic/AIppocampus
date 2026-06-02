# Retrieval And Storage

This reference owns the memory surfaces and search contracts. Keep operational
details here instead of expanding `SKILL.md`.

## Clean Source

`scripts/build_clean_source.py` creates the daily-use source layer under the
global thread store by default:
`$CODEX_HOME/aippocampus-registry/threads/<thread>/clean-source/`.

Passing an explicit `--output-dir .aippocampus/clean-source` still writes a
project-local compatibility copy.

Clean source keeps:

- user messages
- assistant `final_answer` messages
- the last assistant commentary only when a turn has no final answer
- structured tool/test behavior events in `events.jsonl`
- source session id, line spans, turn index, phase, timestamps, and hashes
- stable join keys such as `source_id`, `turn_id`, `message_id`, and
  `content_sha256`
- deterministic `scope_labels` for life-wide navigation:
  `personal_reflection`, `relationship_continuity`, `reading_notes`,
  `idea_seed`, `preference`, `life_context`, `technical_work`, and
  `open_question`

Clean source drops:

- raw tool calls and raw tool outputs from `messages.jsonl`
- raw stdout, full shell commands, full tool arguments, local paths, and secret-
  shaped payloads from `events.jsonl`
- app/event envelopes
- injected instructions
- duplicate visible messages
- routine commentary when a final answer exists
- attachment carrier payloads that are not visible message text

This layer may omit noise, but it must not rewrite expression. Use
`search_clean_source.py` first for normal recall. Return to raw rollout for
forensic audit, missing tool output, storage accounting, or source repair.

`events.jsonl` is a behavior lane, not a second message stream. It stores
deterministic traces such as tool call requested/observed, coarse
`command_class`, exit code when visible, `tool_call_failed` /
`tool_call_succeeded`, source refs, hashes of inputs or observations, and
bounded breadcrumbs such as `tool_intent`, `command_family`,
`test_target_class`, `failure_family`, `path_categories`,
`path_fingerprints`, and `generated_file`. These breadcrumbs are derived enums,
counts, booleans, or one-way hashes over safe repo-relative path tokens. They
must not contain raw command text, stdout/stderr, full tool arguments, absolute
paths, or secret-shaped material. This lets benchmark and Dream-adjacent code
cite behavior-backed rejected routes without putting terminal output or private
command text into daily recall. Assistant narration may provide context in
`messages.jsonl`, but a rejected route only becomes source-backed when the
behavior lane has a matching tool/test/edit trace or a later curated event
sidecar.

### Critical Operation Integrity

The critical-operation integrity contract is the layer above `events.jsonl`.
It says which operation facts must eventually be source-backed before
AIppocampus, benchmarks, or continuous-agent workflows may treat them as
reliable operation memory. The contract version is
`aippocampus-critical-operation-integrity-v1`, implemented as the read-only
diagnostic module `aippocampus_runtime.source.operation_integrity`.

The diagnostic reads a clean-source directory and reports coverage or gaps. It
does not reopen raw rollout payloads by default, and a gap does not block
ordinary recall. Instead, a gap means downstream code must avoid claiming that
operation family is covered, and must reopen source or raw audit material before
making a strong operation claim.

Mandatory event families:

| Family | Facts that must be captured | Never store raw | Current source |
|---|---|---|---|
| `file_edit_write_attempt` | event id, source join, privacy-safe path identity or `path_fingerprints`, generated-file classification, status | raw diffs, file contents, absolute paths, full tool args | behavior-event breadcrumbs or explicit event rows |
| `test_check_command_result` | event id, source join, command family, target class, exit status, failure family when failed | full shell command, stdout/stderr, local paths, env vars, secrets | behavior-event breadcrumbs or explicit event rows |
| `user_correction_or_superseding_decision` | event id, source join, decision kind, scope, status or successor | raw prompt payloads, broad personality summaries, unsupported model judgement | explicit event rows only |
| `source_reopen_before_risky_action` | event id, source join, reopened source ref, risk family, status | reopened source text beyond the cited ref, raw search payloads | explicit event rows only |
| `tool_failure_changed_plan` | event id, source join, tool family, failure family, plan-change ref | raw tool output, stack traces, full commands | explicit event rows only |
| `explicit_user_constraint` | event id, source join, constraint kind, scope, expiry or supersession | unconstrained user-profile summaries, local machine paths, private prompt dumps | explicit event rows only |

Each report classifies a family as:

- `covered`: at least one event row has the required source-backed facts.
- `partial`: a row exists, but required facts are missing.
- `missing`: no event row for that family exists in the clean-source build.

Safe recall may use `covered` facts with their `source_ref`, `event_id`,
`turn_index`, `call_ref`, and hash joins. `partial` and `missing` families must
stay visible as gaps. Semantic summaries, assistant narration, and benchmark
gold labels must not be upgraded into operation facts unless they join back to
a source-backed event row or curated sidecar event.

Run the diagnostic from an installed package or the script root:

```powershell
python -m aippocampus_runtime.source.operation_integrity --clean-source-dir "<clean-source>" --json
```

`scope_labels` are conservative lexical hints over clean visible text. They
support filtering and future timeline sidecars, but they are not summaries and
must not be treated as stronger evidence than the quoted source. Search can
filter them with `search_clean_source.py --scope-label <label>`.

Fuzzy life-wide judgments such as metaphors, pivots, dissatisfaction, or
excitement should not be solved by endlessly expanding the deterministic phrase
list. Background semantic jobs stage source-backed `semantic_scope_labels`
findings in `subconscious_jobs.jsonl`; `build_semantic_scope_labels.py` then
materializes accepted rows into `semantic-scope-labels.jsonl` beside a
clean-source directory. Rows are keyed by existing `message_id`s, carry
canonical `scope_labels`, and must include source refs back to the same
message. Source-review-sensitive labels such as `personal_reflection`,
`life_context`, `reading_notes`, and `preference` also require explicit
per-label model evidence and stricter per-label confidence before the
materializer keeps them; this protects against broad semantic over-labeling
without falling back to mechanical phrase-list expansion. Single-thread
clean-source search, registry deep search, and
`build_project_timeline.py` merge that sidecar as navigation metadata while
leaving `messages.jsonl` unchanged. Treat semantic sidecar labels as
DeepSeek/subconscious hints, not source truth.

For Stage 2 regression evidence, `smoke_semantic_scope_real_history.py` can run
full selected life-wide candidate coverage in bounded DeepSeek batches, and
`smoke_source_evidence_recall_eval.py` can build selected fuzzy life-wide
prompts from dynamic low-frequency source cue terms. The recall eval uses
dynamic clean-source corpus-rarity reranking for evaluation instead of a fixed
fuzzy phrase list. `smoke_semantic_scope_source_review.py` can also run a live
DeepSeek-compatible label-case review that checks selected sidecar labels
against their matching clean-source messages. These evals prove only that the
selected prompt or label samples passed their configured thresholds; they are
not global semantic correctness claims or human review.

Schema upgrades should be rebuildable. Do not put embeddings, DWM state, or
debug provenance into `messages.jsonl`; use sidecars joined by `message_id`,
`turn_id`, or `event_id`.

## Raw Rollout Discovery

Raw rollout lookup scans both `$CODEX_HOME/sessions/` and
`$CODEX_HOME/archived_sessions/`. Codex Desktop's thread archive can move raw
rollout JSONL files into the flat `archived_sessions/` directory, and those
files remain the source-backed audit surface for locate, health, clean-source
rebuilds, and raw search.

Treat `archived_sessions/` as a read-only app-owned source location. It is not
AIppocampus cold archive, and it should still resolve to the same session-keyed
global thread store under `$CODEX_HOME/aippocampus-registry/threads/`.

## Local Index

`scripts/build_index.py` writes `messages.jsonl`, `source_index.sqlite`,
`graph.json`, RAG-lite chunks, and `manifest.json` under the global thread store
by default. Passing `--output-dir .aippocampus` preserves the old project-local
mode when a portable bundle, repo-local audit, or explicit debug run needs it.

Default retrieval is local hybrid search:

- SQLite FTS5 trigram search for Chinese, mixed prose, and fuzzy literal clues.
- Anchor matching for durable titles, keywords, and preserved phrases.
- RAG-lite chunks for neighborhood recall before returning to source lines.
- Phase-aware scoring that boosts user messages and `final_answer`, while
  keeping commentary as lower-priority process evidence.
- Diversity ranking so later recaps do not crowd out original turns.

The retrieval rank weights that affect user-visible recall behavior live in
`aippocampus_runtime.recall.scoring_policy` as named frozen policy objects.
This includes phase weights, text/RAG-lite scoring contributions, diversification
penalties, segmented merge weights, active-recall decision bands, and vector /
graph score-fusion blends. Keep those values as reviewable ranking policy. Do
not mix prompt-evidence truth gates or model judgement into that module merely
because they also have numbers; source refs and stable source ids remain the
truth boundary.

Use `--mode literal` only for chronological/debug behavior. Use `--diversity
none` when inspecting pure score order.

## Turn-Level RAG-Lite

RAG-lite chunks live in the same SQLite file. They store message spans, rollout
line spans, anchor titles, extractive summaries, local text, and sparse lexical
vectors.

When turn metadata is available, chunks prefer the user request plus
`final_answer`; commentary is fallback only when no final exists. Answers should
cite source message lines or anchors, not chunk summaries.

This is not a semantic embedding backend. Embeddings can be added later as an
optional adapter for very fuzzy queries or large corpora.

## Segmented Retrieval

For hundred-MB or GB threads, use segments:

- `build_segments.py` creates sealed `seg-0001/`, `seg-0002/`, etc. under the
  global index directory's `segments/` folder by default.
- Each segment has its own `messages.jsonl` and `source_index.sqlite`.
- The segment manifest records source rollout size/mtime, anchor hash, byte
  spans, line spans, message spans, and index paths.
- `search_segments.py` fans queries out to segments, retrieves top candidates
  per segment, and merges global top-k with diversity penalties.

Segment-local ids collide by design. Treat `(segment_id, id, line)` as the hit
key.

## Global Registry

The global thread store is the canonical generated-artifact location. This keeps
AIppocampus useful when a new project is opened and avoids dropping private
rollout-derived files into public repositories by default.

`scripts/registry.py` is the machine-wide discovery layer. It stores where
thread memories live; it is not a duplicate of every thread.

Default registry files under `$CODEX_HOME/aippocampus-registry/` include:

- `threads.json` and `threads.md`
- `associations.json`
- `cognitive_map.json`
- `concept_index.sqlite`
- `semantic_cues.jsonl`
- `semantic_triggers.jsonl`
- `semantic_recall_cache.json`
- `working_memory.jsonl`
- `subconscious_edges.jsonl`, `subconscious_jobs.jsonl`,
  `promotion_candidates.jsonl`
- `subconscious_state.json` and `subconscious_scheduler.log`

Common commands:

- `python ...\onboard.py --provider codex --all --format json`
- `python ...\registry.py register --cwd "$PWD" --build-index`
- `python ...\registry.py register-rollout --rollout "<rollout.jsonl>" --project "<label>"`
- `python ...\registry.py scan-sessions --dry-run`
- `python ...\registry.py list`
- `python ...\registry.py search "terms"`
- `python ...\registry.py search --metadata-only "terms"`

In a new thread, check the registry before saying old memory is unavailable.

`semantic_cues.jsonl` and `semantic_triggers.jsonl` are search-hint sidecars.
They can provide multilingual/domain aliases to the foreground hook and
semantic gate, but they are never source truth. Retrieval policy should extract
query terms from these rows through `retrieval_query_policy.semantic_trigger_terms`
instead of growing `ALIASES` or `ASSOCIATIVE_CUES` with semantic proxy phrases.
`aippocampus_runtime.recall.semantic_trigger_router` writes reviewed seed
triggers plus source-backed promotion candidates into `semantic_triggers.jsonl`;
the top-level `semantic_trigger_router.py` remains a compatibility command.
Reviewed seed rows are allowed only as public, scent-only routing hints: active
seeds need review metadata plus source refs or an explicit reviewed-seed
rationale, and the router reports skipped seeds, dropped aliases, and promoted
candidate counts. Legacy trigger ids are retained in `legacy_trigger_ids` when
rows are migrated to the longer SHA-256 `st_...` form.
The provider-aware `onboard.py` wrapper refreshes that sidecar during
onboarding so a fresh registry has the data path before the foreground hook
needs it.

`build_project_timeline.py` writes `project_timeline.json`. The `projects`
section keeps the older project-scoped recent-turn view used by hooks and
subconscious jobs. The `life_wide` section groups the same bounded recent
clean-source turns by `scope_labels` across registered threads and projects,
with `source_refs` pointing back to thread keys, message ids, clean ordinals,
and source lines. Treat this as a navigation sidecar for recurring concerns and
idea evolution; do not quote it as source truth without following the refs back
to clean source. Foreground prompt recall may use `life_wide` only as a quiet
scent when the prompt contains both a recency cue and a life-wide scope-label
cue, so ordinary technical or status prompts are not over-personalized by
global memory.

`onboard.py --provider codex` is the preferred first-install and agent-facing
wrapper. `onboard_codex.py` remains the Codex-only compatibility wrapper. The
wrapper returns a single JSON envelope with `ok`, `data`, `next`, and `meta`,
including before/after registry counts, repair actions, cognitive-map status,
and frontier extraction availability. Use `--dry-run` before large imports when
an agent needs a preview. The command keeps generated artifacts in the global
registry and treats project-local `.aippocampus/` as explicit export/debug
compatibility only. When `--frontier-mode smoke|write` is used without an
explicit `--frontier-project`, the command infers the current `--cwd` project
and includes compact `sample_findings` in the frontier result so an agent can
judge quality before writing. Use `--frontier-project *` only for a global
whole-machine frontier pass. Explicit `smoke`/`write` modes are DeepSeek-backed
quality checks: missing `DEEPSEEK_API_KEY`, model failures, partial failures, or
zero accepted findings return a partial/blocking frontier status instead of
quietly falling back to deterministic registry maintenance.

Full-machine search has one important boundary: old clean-source files may
already contain injected skill or instruction carrier blocks from earlier
builds. Registry deep search keeps those hits auditable but demotes them with a
structural `search_noise` marker so repeated tool/skill instructions do not
outrank real user turns or assistant final answers.

## Search-Decision Adapter

`scripts/search_decision_adapter.py` is a narrow local contract for #381-style
external-search decisions. It does not call Google, browser search, Perplexity,
or any remote authority ranker. It only accepts the current prompt plus
source-backed candidate rows and returns:

- `before_search`: `skip` / `scent` / `candidate` / `evidence` routing for
  whether old source can safely clarify the search intent.
- `during_search`: a query expansion packet only when candidate source refs are
  present. Expansion terms are navigation hints, not recalled facts.
- `after_search`: `extension`, `correction`, `replacement`, or
  `disposable_residue` classification. External search results are not
  long-term truth unless the user explicitly imports or reviews them through a
  provenance-bearing path.

This adapter should reuse existing query policy, clean-source refs, and ambient
support levels instead of adding a separate score layer. If a prompt only looks
related through broad words such as browser/search/local/permission, the correct
behavior is `skip`, not personalized query expansion.

## MCP Access Layer

`scripts/aippocampus_mcp_server.py` is the local MCP surface for agent clients
that should not shell out through skill instructions for every read. It exposes
`search_memory`, `recall_context`, `recall_deepen`, `latest_reply`,
`get_turn_context`, `list_threads`, `register_thread`, `sync_status`, and
`memory_health`.

Default MCP tools read clean source, registry rows, or health metadata. The
only mutating tool is `register_thread`, and it is explicit. `sync_status`
reports real local-folder sync state when the caller supplies `sync_dir`;
without one, it reports capability truth instead of pretending sync is active.

`recall_context` and `recall_deepen` are the agent-facing progressive recall
funnel between hook-time scent and low-level source reopen. `recall_context`
turns a fuzzy cue into compact route handles, source-window candidates, scope
labels, and evidence levels. It must not include raw prompt text, raw private
paths, raw tool payloads, or source claims that have not been reopened.
`recall_deepen` consumes those handles, ambient navigation seeds, or active
recall lock handles and opens clean source only when the handle is still fresh
and reopenable. Handles carry source-artifact freshness so a changed
clean-source file forces the agent to rerun `recall_context` rather than using
old navigation as evidence.

The navigation packet may expose small benchmark-oriented counters such as
funnel stage, handle count, source reopen success, and stale-handle detection.
Those counters are operational observations for future comparisons against
direct `search_memory` and hook-card-only baselines; they are not answer-quality
or benchmark-lift claims by themselves.

## Cognitive Map

`build_cognitive_map.py` materializes `$CODEX_HOME/aippocampus-registry/cognitive_map.json`.
This is the AIppocampus "mental map" layer: episodes come from registry rows,
while landmarks, regions, and routes come only from source-backed DeepSeek
subconscious findings with `job=cognitive_map`.

Do not create routes directly from registry keywords. Registry metadata can
place an episode on the map, but the model-assisted subconscious layer must
propose the navigable route. The deterministic builder validates source refs,
filters weak findings when quality metadata is present, clamps fields, and
writes a hook-safe sidecar. Prompt hooks may use route matches as scent and
query expansion; exact claims still require clean-source, SQLite, or raw-rollout
evidence.

Question/frontier findings are not cognitive-map routes by themselves. They are
stored as `subconscious_jobs.jsonl` findings from the `question_extraction` job
and may later feed hook scent, boundary maps, or review workflows. A
`frontier_marker` must point to an explicit stopping point or unresolved
boundary; do not infer one merely because a question was asked. A
`question_candidate` should carry a short normalized `question_text`; overlong
raw monologues are compressed to `question_short`/title when available or
rejected before staging.

Phase 2 `question_tracking` reads those staged candidates and writes
`question_link` findings back to the same stream. The deterministic runner uses
local question text/features/context scoring as a shortlist mechanism, keeps
auditable ordering edges among linked questions, and, when registry clean
source is available, skips stale candidates whose refs no longer resolve to a
concrete thread/message/line anchor. Borderline links require an explicit
confirmation artifact and still inherit truth only from the original question
source refs.

## Associations And Concept Graph

`build_associations.py` reads registry rows and indexes to create prompt-hook
associations. Curated anchors and keywords are `verified`; automatically mined
final-answer terms are `staging`. Trivial utterances, repeated Goal/system text,
and injection noise should be filtered before they become triggers.

`build_concept_graph.py` creates a bounded concept graph. Depth-1 expansion may
use staging edges; depth-2 expansion is restricted to verified or
high-confidence edges and remains scent-only.

## Vault And Dashboard

`sync_vault.py` creates a human-readable memory surface, usually under
`AIPPOCAMPUS_VAULT` when set, otherwise `~/AIppocampus Memory`. Optional
Publish-like shell assets can be supplied with `AIPPOCAMPUS_STYLE_SOURCE`,
`AIPPOCAMPUS_SCRIPT_SOURCE`, `AIPPOCAMPUS_SITE_MARK`, and
`AIPPOCAMPUS_SITE_TITLE`. The older `CODEX_MEMORY_*` names are accepted only as
backward-compatible fallbacks. Generated content should stay inside `Threads/`,
`_dashboards/`, and the named CSS snippet. Do not overwrite user-authored vault
notes.

The dashboard may use vendored `assets/pixi-7.2.4.min.js` and
`assets/d3-7.9.0.min.js`; keep these as local assets so recall does not depend
on a network CDN.

## Graphify Bridge

`prepare_graphify_corpus.py` exports a prepared corpus under the global index
directory's `graphify-corpus/`: anchors, index metadata, anchor graph, and
chunked transcript Markdown with source provenance.

Run the separate `graphify` skill only when the user wants deeper graph
analysis, community detection, or `GRAPH_REPORT.md`. Keep Graphify output under
the corpus folder's `graphify-out/`.

## Bundles

`aippocampus_runtime.artifacts.export_bundle` produces portable thread-memory
bundles, with `export_bundle.py` and `aippocampus export` preserved as operator
entrypoints. Bundles normally include manifest, handoff, index files, graph,
anchors, and raw rollout unless `--no-raw` is used.
`aippocampus_runtime.artifacts.import_bundle` extracts the bundle and appends a
pointer to the current workspace's anchors, with `import_bundle.py` and
`aippocampus import` preserved as compatibility/facade entrypoints.

`aippocampus_runtime.sync.bundle` is the first Stage 3 sync backend.
`sync_bundle.py` remains the direct-script/import compatibility shim. It
supports explicit local-folder `status`, `push`, `pull`, and `repair` commands
over clean source, registry rows, manifests, semantic triggers, working memory,
and cognitive-map sidecars. `encrypted_sync_bundle.py` adds the age-backed
encrypted variant and keeps ciphertext under `encrypted-sync/`.

`aippocampus_runtime.sync.object_storage.cli` reuses that same bundle manifest
over an HTTP object-storage transport; `sync_object_storage.py` remains the
compatibility shim. Each manifest file is stored as an object under
`AIPPOCAMPUS_OBJECT_PREFIX`, the manifest object is written last, and
`status`/`repair` verify object content by sha256 before `pull` imports it.
`encrypted_sync_object_storage.py` uses the same encrypted bundle contract over
HTTP `PUT`/`GET` and writes the encrypted outer manifest last.
`encrypted_sync_admin.py` owns device-key UX and plaintext-to-encrypted
migration/cleanup so the core sync entrypoints stay focused on transport. The
object-store client boundary is split into the `object_storage_client.py`
compatibility shim and package-only
`aippocampus_runtime.sync.object_storage.providers`; provider mode covers
generic HTTP bearer-token endpoints, S3-compatible SigV4, Cloudflare R2 region
`auto`, and Google Cloud Storage XML HMAC signing. Provider-specific setup
notes live in `docs/guides/object-storage-providers.md`.

Raw rollout files are excluded from plaintext sync. Normal raw rollout transfer
requires encrypted sync. Pull never overwrites conflicting local files; it
writes the incoming copy under `.sync-conflicts/` for manual review.

Push rewrites synced `registry/threads.json` to device-neutral
bundle-relative locators for generated artifacts and clears source-device
workspace paths. Pull repairs those generated-artifact locators to the target
registry's local paths. Raw rollout locators remain absent unless the user
explicitly opts into `--include-raw`.

The local object-storage smoke starts a throwaway HTTP object store and proves
the adapter makes real `PUT`/`GET` object calls. That is stronger than copying
between folders, but it is still not proof of a managed cloud provider or a
physical second device. `sync_status` on the MCP surface reports local-folder
capability by default and can report object-storage status when the caller
supplies an `object_store_url`.
