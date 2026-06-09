# Retrieval And Storage

This reference owns the memory surfaces and search contracts. Keep operational
details here instead of expanding `SKILL.md`.

## Clean Source

`aippocampus_runtime/source/clean_source` creates the daily-use source layer under the
global thread store by default:
`$CODEX_HOME/aippocampus-registry/threads/<thread>/clean-source/`.

Passing an explicit `--output-dir .aippocampus/clean-source` still writes a
project-local compatibility copy.

Clean source keeps:

- user messages
- assistant `final_answer` messages
- the last assistant commentary only when a turn has no final answer
- structured tool/test behavior events in `events.jsonl`
- source-texture interpretation input in `source-texture.jsonl`
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
- raw prompt, commentary, tool payload, stack trace, or local-path text from
  `source-texture.jsonl`
- app/event envelopes
- injected instructions
- duplicate visible messages
- routine commentary when a final answer exists
- attachment carrier payloads that are not visible message text

This layer may omit noise, but it must not rewrite expression. Use
`aippocampus_runtime.source.search` first for normal recall. Return to raw rollout for
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
- `weak_covered`: an event row exists and has required facts, but one or more
  values are placeholder-like, malformed, private-looking, implausible, or too
  weak for a strong operation claim.
- `partial`: a row exists, but required facts are missing.
- `missing`: no event row for that family exists in the clean-source build.

Safe recall may use `covered` facts with their `source_ref`, `event_id`,
`turn_index`, `call_ref`, and hash joins. `weak_covered`, `partial`, and
`missing` families must stay visible as gaps. Weak-covered rows can route
review or source reopen, but they do not support strong operation claims until
the weak value is replaced by usable source-backed evidence. Semantic
summaries, assistant narration, and benchmark gold labels must not be upgraded
into operation facts unless they join back to a source-backed event row or
curated sidecar event.

The diagnostic also reports compact `conflicts` and
`coverage_summary.conflict_count` when projected privacy-safe fact rows
contradict each other, such as incompatible statuses for the same `event_id` or
`call_ref`, conflicting test/check results for the same compact target
identity, incompatible active/superseded user constraints, or malformed /
out-of-session timestamps when a manifest time range is available. Conflicted
families are not clean `covered` evidence; they remain usable as route material
for review, but strong operation claims must reopen source or raw audit
material first. Conflict diagnostics must not serialize raw commands, raw
outputs, full tool arguments, local absolute paths, file contents, or
secret-shaped strings.

Downstream code that wants to phrase a strong operation fact should call the
machine-readable gate in
`aippocampus_runtime.source.operation_claim_gate.evaluate_operation_claim`
with the integrity report, operation family, intended support level, and any
available join keys such as `event_id`, `source_ref`, or `call_ref`. The gate
returns a bounded decision (`allow_source_backed_claim`,
`downgrade_to_candidate`, `require_source_reopen`, `block_public_claim`, or
`conflict_requires_review`) plus the existing `support_level`, `trust_level`,
`action_grammar`, and `trust_contract` fields. The gate applies only to strong
operation claims; it must not block ordinary clean-source search or
source-backed recall routing.

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
findings in `subconscious_jobs.jsonl`; `aippocampus_runtime.source.semantic_scope_builder` then
materializes accepted rows into `semantic-scope-labels.jsonl` beside a
clean-source directory. Rows are keyed by existing `message_id`s, carry
canonical `scope_labels`, and must include source refs back to the same
message. Source-review-sensitive labels such as `personal_reflection`,
`life_context`, `reading_notes`, and `preference` also require explicit
per-label model evidence and stricter per-label confidence before the
materializer keeps them; this protects against broad semantic over-labeling
without falling back to mechanical phrase-list expansion. Single-thread
clean-source search, registry deep search, and
`aippocampus_runtime.navigation.project_timeline` merge that sidecar as navigation metadata while
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

## Continuity Domains

Continuity domains are the Contract v1 source-trailed abstraction layer above
clean source. The canonical contract lives at
`docs/architecture/continuity-domains.md`; this reference owns only the runtime
storage route.

The event log is append-only and lives beside clean source:

```text
$AIPPOCAMPUS_REGISTRY_DIR/threads/<thread>/clean-source/continuity-domain-events.jsonl
```

Snapshots are rebuildable projections under the thread store:

```text
$AIPPOCAMPUS_REGISTRY_DIR/threads/<thread>/continuity-domain-snapshots/<snapshot_id>.json
$AIPPOCAMPUS_REGISTRY_DIR/threads/<thread>/continuity-domain-snapshots/latest.json
```

`aippocampus_runtime.recall.continuity_domains` materializes supported domain
and pathlet events, rejects unsupported or unresolved refs when clean source is
available, and redacts local paths or secret-shaped values before public
projection. The snapshot may contain `working_conclusion_short`, but default
hook output must render only a `continuity_domain_pointer`; explicit
`recall_deepen` or source reopen is required before factual claims.

This is a runtime substrate, not an automatic memory author. Passive hooks do
not create domain events. Explicit producers or future background jobs must
write events under the Contract v1 rules before active recall or MCP can
surface domain pointers.

The packaged local operator command for explicit writes is
`aippocampus continuity-domain`. `produce --dry-run` scans registered
clean-source history for repeated source-ref-backed candidate labels. Reviewed
sidecars such as semantic/query-pattern, working-memory, Dream, Journey, or
cognitive-map outputs may contribute labels only when their refs resolve back
to clean source; the sidecar row itself is not evidence. `produce --append`
first refreshes the existing query-pattern route sidecar, so aliases already
generated or reviewed by the registration/onboarding path are available to the
producer without adding a second alias pipeline. `produce --dry-run` remains
no-write unless `--refresh-query-pattern-routes` is explicit. The command emits
a public-safe aggregate report; `produce --append` promotes the selected
candidates into the append-only event log, and `--publish` materializes the
rebuildable snapshot. `append` writes one explicit event, `publish` materializes
the rebuildable snapshot, and `report` emits the public-safety readout. These
commands are trusted local producer/authoring surfaces, not hook paths.

When a domain source ref carries `thread_key`, MCP `recall_deepen` may consult
the machine registry to open that thread's clean-source store. Handles created
by `recall_context` include freshness for those registry clean-source targets;
blocked, stale, superseded, and retired domains still stay blocked at deepen
time even if an old handle is replayed. The handle's refs define the current
freshness/reopen set; extra refs visible in the domain brief are navigation
until another handle or source reopen selects them.

Macro tendencies in this layer are derived-only pointers. They are not
runtime-writable facts, user profile facts, or replacements for clean source.

Situation glyphs consume Dream, Journey, hexagram, cognitive-map,
source-texture, navigation-potential, working-memory, and continuity-domain
signals as `direction_only` atmosphere. They are path-order-sensitive and must
stay lower authority than their source trail.

## Agent Self-Notes

`aippocampus_runtime/source/agent_self_notes.py` owns the private
`agent-self-notes.jsonl` sidecar. A row with `kind=agent_self_note` is a short
foreground-agent margin note about stance, hesitation, surprise, or closeout
posture. It is not clean source, not a user profile, and not formal memory.

Self-notes are `memory_atmosphere` / `direction_only` only. Their `source_refs`
route a later agent back to the surrounding source neighborhood; those refs do
not prove the note text or any factual claim. The append helper rejects mostly
credential-shaped or raw tool-payload material, redacts local paths, and never
mutates clean source. Explicit active recall may surface these rows when the
agent asks to recover past state, but source-backed details still require the
normal clean-source reopen path.

The default foreground projection stays compact: `note_text` is capped at 280
characters and is the only note body active recall may inject by default. Longer
operator/agent appends may store an optional `note_body_private` body capped at
1200 characters, with `note_body_private_default_visible=false` and
`note_body_private_reopen_required=true`. That private body is a protected
reopen/deepen target, not a passive-hook or active-recall foreground surface.

Foreground agents can append one voluntary current-thread note through the
public facade:

```bash
aippocampus self-note append --current-thread --stdin --json
```

That facade attaches a compact public-safe current-thread route, returns a tiny
active-recall preview, and still treats the row as an atmosphere-only margin
note rather than formal memory, a user profile fact, or clean source.

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

`aippocampus_runtime/recall/index_builder` writes `messages.jsonl`, `source_index.sqlite`,
`graph.json`, RAG-lite chunks, and `manifest.json` under the global thread store
by default. Passing `--output-dir .aippocampus` preserves the old project-local
mode when a portable bundle, repo-local audit, or explicit debug run needs it.
The stable `source_index.sqlite` path is a compatibility anchor; normal readers
should resolve `source_index.pointer.json` to the current generation before
opening SQLite, with last-known-good and stable fallbacks. When a reader opens a
resolved generation path, it creates a short-lived `.reader-pins/*.json` file
beside the pointer for the duration of the query so storage GC can distinguish
active readers from expired old generations.

Default retrieval is local lexical-structural hybrid search:

- SQLite FTS5 trigram search plus LIKE fallback for Chinese, mixed prose, and
  fuzzy literal clues.
- Anchor matching for durable titles, keywords, and preserved phrases.
- RAG-lite chunks for neighborhood recall before returning to source lines.
- Phase-aware scoring that boosts user messages and `final_answer`, while
  keeping commentary as lower-priority process evidence.
- Structure and time sidecars for source-joined ranking hints when callers
  provide those cues.
- Diversity ranking so later recaps do not crowd out original turns.

The retrieval rank weights that affect user-visible recall behavior live in
`aippocampus_runtime.recall.scoring_policy` as named frozen policy objects.
This includes phase weights, text/RAG-lite scoring contributions, diversification
penalties, segmented merge weights, active-recall decision bands, and vector /
graph score-fusion blends. Keep those values as reviewable ranking policy. Do
not mix prompt-evidence truth gates or model judgement into that module merely
because they also have numbers; source refs and stable source ids remain the
truth boundary.

The score-fusion module can blend optional vector or concept-graph signals when
another source-joined consumer supplies them, but dense vector retrieval is not
part of the default local search path. Semantic triggers, cognitive-map routes,
and graph neighbors are navigation hints that still require source reopen before
exact claims.

`aippocampus_runtime.recall.feedback_events` records public-safe recall and
active-flow feedback rows for later calibration work. It can count outcomes such
as delivered candidates, source reopen success, ignored candidates, blocked
routes, and wrong-route drag by blend context, signal family, and route kind.
Those rows are calibration evidence and route-context metadata only: they do
not store raw prompts or source excerpts, do not mutate score-fusion weights,
and do not let activation metadata become source truth.

Chinese and mixed-language recall is measured by the public-safe CJK local
fixture in
`docs/evidence/benchmarks/cjk-local-recall-fixture-report.md`. That fixture can
compare current trigram/LIKE/RAG-lite behavior with measured-only
`cjk_query_sidecar_terms()` candidates, including compact no-space CJK cues.
The sidecar terms are search/navigation material only: they do not make
generated aliases source truth, and the fixture does not claim broad Chinese
semantic search quality.

Segmented merge weights are calibrated by the public-safe #375 fixture runner
`benchmarks/aippocampus/benchmark_segmented_merge_policy.py` and documented in
`docs/evidence/benchmarks/segmented-merge-policy-fixture-report.md`. Passing
that fixture only means the default policy survives four deterministic
long-thread merge patterns; it does not prove real recall quality or replace
Track B source-evidence retrieval measurements.

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

- `aippocampus_runtime.recall.segment_builder` creates sealed `seg-0001/`, `seg-0002/`, etc. under the
  global index directory's `segments/` folder by default. New rebuilds publish
  those shards inside `segments/generations/gen_*/` and update
  `segments.pointer.json`; `segments/manifest.json` remains the compatibility
  manifest.
- Each segment has its own `messages.jsonl` and `source_index.sqlite`.
- The segment manifest records source rollout size/mtime/hash, anchor hash,
  byte spans, line spans, message spans, timestamp ranges, turn ranges,
  partial-turn boundary diagnostics, and index paths. The builder prefers
  cutting after complete turns when a bounded overshoot is enough; pathological
  oversized turns are still allowed to split and are marked as partial with a
  reason code.
- `aippocampus_runtime.recall.segment_search` fans queries out to segments, optionally enforces
  `--fanout-budget` / `--max-segments` before opening SQLite shards, resolves
  the segment pointer once per query, writes a short-lived reader pin beside the
  pointer while it searches that resolved generation, identifies partial-turn
  boundary segments in JSON diagnostics,
  identifies adjacent segment ids for cross-boundary partial turns without
  stitching text, and merges global top-k with diversity penalties. Missing
  manifests or shard indexes report structured `segments_unavailable` /
  `build_required` status unless the caller explicitly asks to build segments.
  Deterministic temporal cues such as explicit dates, `last month`, or
  `半年前` may reorder the planned segment list before the fanout cap is
  applied, but they must not expand `--fanout-budget` / `--max-segments`. Legacy
  manifests without timestamp ranges fall back to recency ordering and report no
  boosted segments.
  Old generations are rebuildable cache targets. Health/capacity/storage-gc
  dry-runs report reader-pin/TTL cleanup status, and storage GC apply may delete
  only old generation directories whose active pins are gone, TTL has elapsed,
  and current/LKG pointer protection still passes.

Segment-local ids collide by design. Segmented merge first dedupes hits by
stable source join identity when a hit exposes `stable_source_id`, `source_id`,
`thread_key` + `message_id`, source refs, or a scalar `source_ref`; old or
partial shard rows without a stable source key keep `(segment_id, id, line)` as
the segment-local fallback hit key. The merge diagnostics report
`source_key_dedupe_count` so overlap suppression is visible without reopening
SQLite shards after fanout.

## Global Registry

The global thread store is the canonical generated-artifact location. This keeps
AIppocampus useful when a new project is opened and avoids dropping private
rollout-derived files into public repositories by default.

`aippocampus_runtime/registry/api` is the machine-wide discovery layer. It stores where
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

- `python -m aippocampus_runtime.onboarding.facade --provider codex --all --format json`
- `python -m aippocampus_runtime.registry.api register --cwd "$PWD" --build-index`
- `python -m aippocampus_runtime.registry.api register-rollout --rollout "<rollout.jsonl>" --project "<label>"`
- `python -m aippocampus_runtime.registry.api scan-sessions --dry-run`
- `python -m aippocampus_runtime.registry.api list`
- `python -m aippocampus_runtime.registry.api search "terms"`
- `python -m aippocampus_runtime.registry.api search --metadata-only "terms"`

In a new thread, check the registry before saying old memory is unavailable.

`semantic_cues.jsonl` and `semantic_triggers.jsonl` are search-hint sidecars.
They can provide multilingual/domain aliases to the foreground hook and
semantic gate, but they are never source truth. Retrieval policy should extract
query terms from these rows through `retrieval_query_policy.semantic_trigger_terms`
instead of growing `ALIASES` or `ASSOCIATIVE_CUES` with semantic proxy phrases.
`aippocampus_runtime.recall.semantic_trigger_router` writes reviewed seed
triggers plus source-backed promotion candidates into `semantic_triggers.jsonl`;
the top-level `aippocampus_runtime.recall.semantic_trigger_router` remains a compatibility command.
Reviewed seed rows are allowed only as public, scent-only routing hints: active
seeds need review metadata plus source refs or an explicit reviewed-seed
rationale, and the router reports skipped seeds, dropped aliases, and promoted
candidate counts. Legacy trigger ids are retained in `legacy_trigger_ids` when
rows are migrated to the longer SHA-256 `st_...` form.
The provider-aware `aippocampus_runtime.onboarding.facade` wrapper refreshes that sidecar during
onboarding so a fresh registry has the data path before the foreground hook
needs it.

`aippocampus_runtime.navigation.project_timeline` writes `project_timeline.json`. The `projects`
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
wrapper. `aippocampus_runtime.onboarding.codex` remains the Codex-only compatibility wrapper. The
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

`aippocampus_runtime.recall.search_decision_adapter` is a narrow local contract for #381-style
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

## Route Note Lane

`route-notes.jsonl` is a generated sidecar beside clean source for Codex-style
process commentary and action-summary material. It is not part of
`messages.jsonl`, and it must not reintroduce routine commentary into ordinary
clean-source search. A route note may become Active Path Packet input only when
it is joined to adjacent source, final-answer, or structured tool/test evidence.

The taxonomy is deliberately small: `intent_before_tool`,
`decision_breadcrumb`, `rejected_route`, `open_question`, `handoff_hint`, and
`source_to_action_link`. Rows serialize bounded reason codes, note kind,
source/event refs, counts, and hashes. They do not serialize raw commentary,
commands, stdout, local paths, secrets, or private transcript text. A note
without adjacent evidence stays diagnostic-only or is ignored.

Route notes are process evidence for navigation. They can explain why an agent
should reopen a source or avoid a rejected route, but they never override user
turns, final answers, tool output, or reopened clean source. Specific
memory-backed claims still require source reopen.

## Source Texture Lane

`source-texture.jsonl` is a rebuildable interpretation sidecar beside clean
source. It joins clean-source messages, `events.jsonl`, and `route-notes.jsonl`
into typed process signals for Dream, Journey, and correction layers without
mutating `messages.jsonl`.

Rows carry `signal_kind`, `signal_detail`, `source_refs` or `event_refs`,
bounded fingerprints, `privacy_profile=raw-private`, and
`truth_boundary=texture_signal_not_source_fact`. They may distinguish texture
such as `self_correction_signal`, `uncertainty_or_frontier_signal`,
`affect_marker`, `abandoned_direction`, `process_route_note`, and
`tool_failure_texture`, but they must not serialize raw source text, raw
commentary, commands, stdout/stderr, stack traces, local paths, or secrets.

This lane is useful routing weather, not source truth. A consumer may use it to
choose which source or event to reopen, but exact claims still require
following the row refs back to clean source, route notes, behavior events, or
raw audit when clean source is insufficient. Public/export projections omit
this private sidecar unless a future explicit redacted texture projection is
implemented with the same source-ref reopen boundary.

Consumers should go through
`aippocampus_runtime.source.texture_consumption`, which projects only
`texture_id`, signal kind/detail/labels, safe source/event refs, truth boundary,
and a consumer-specific `suggested_use`. Dream, Journey, and correction may let
these projected signals change background worker eligibility, waypoint labels /
frontier hints, or outcome reconstruction evidence. Foreground recall remains
quiet by default; texture rows are not ordinary search hits and do not support
facts without source reopen.

## MCP Access Layer

`aippocampus_runtime/mcp/server` is the local MCP surface for agent clients
that should not shell out through skill instructions for every read. It exposes
`search_memory`, `recall_context`, `recall_deepen`, `latest_reply`,
`get_turn_context`, `list_threads`, `register_thread`, `sync_status`, and
`memory_health`.

Default MCP tools read clean source, registry rows, or health metadata. The
only mutating tool is `register_thread`, and it is explicit. `sync_status`
reports real local-folder sync state when the caller supplies `sync_dir`;
without one, it reports capability truth instead of pretending sync is active.
`register_thread` is a control-plane registry operation: it serializes registry
metadata writes with `.threads-registry.lock` and reports retryable
`registry_writer_busy` contention, but it does not unlock broad memory-write
tools or put global locks around read-only MCP queries.

`recall_context` and `recall_deepen` are the agent-facing progressive recall
funnel between hook-time scent and low-level source reopen. `recall_context`
turns a fuzzy cue into compact route handles, source-window candidates, scope
labels, and evidence levels. It must not include raw prompt text, raw private
paths, raw tool payloads, or source claims that have not been reopened.
When a published continuity-domain snapshot exists, `recall_context` may also
surface continuity-domain handles or ordered pathlet handles before broad
manual search. If that snapshot is missing or unreadable, the response should
say so as a missing route artifact instead of flattening the result into "no
memory." `recall_deepen` consumes those handles, ambient navigation seeds, or
active recall lock handles and opens clean source only when the handle is still
fresh and reopenable. Handles carry source-artifact freshness so a changed
clean-source file forces the agent to rerun `recall_context` rather than using
old navigation as evidence.

The navigation packet may expose small benchmark-oriented counters such as
funnel stage, handle count, source reopen success, and stale-handle detection.
Those counters are operational observations for future comparisons against
direct `search_memory` and hook-card-only baselines; they are not answer-quality
or benchmark-lift claims by themselves.

## Cognitive Map

`aippocampus_runtime.navigation.cognitive_map` materializes `$CODEX_HOME/aippocampus-registry/cognitive_map.json`.
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

`aippocampus_runtime.navigation.associations` reads registry rows and indexes to create prompt-hook
associations. Curated anchors and keywords are `verified`; automatically mined
final-answer terms are `staging`. Trivial utterances, repeated Goal/system text,
and injection noise should be filtered before they become triggers.

`aippocampus_runtime.navigation.concept_graph` creates a bounded concept graph. Depth-1 expansion may
use staging edges; depth-2 expansion is restricted to verified or
high-confidence edges and remains scent-only.

Concept graph row status is graph participation metadata, not source truth.
`verified` rows rank ahead of `staging`, but exact claims still require source
reopen. `parked` and `retired` rows remain in the rebuildable SQLite projection
only as lifecycle diagnostics and are excluded from default expansion. Promotion
is conservative and source-joined: repeated refs, cross-thread refs, reviewed
input, or curated associations may upgrade graph participation; high model
confidence alone may not. Parking/retirement suppresses noisy, stale,
low-confidence, contradicted, or superseded graph hints without deleting source
refs or writing back to clean source.

`aippocampus_runtime.navigation.concept_edge_utility` records explicit,
privacy-safe utility events for graph expansions and emits an offline aggregate
report grouped by edge type, edge status, score bucket, and optional hashed
project/domain buckets. These rows are route telemetry only: they do not store
raw prompt text, raw source excerpts, or local paths; they do not mutate
`EDGE_TYPE_MULTIPLIER`; and they do not turn graph proximity into source
evidence. Use the report to justify a later explicit scoring-policy change,
not as online learning.

## Vault And Dashboard

`aippocampus_runtime.vault.sync` creates a human-readable memory surface, usually under
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

`aippocampus_runtime.ops.graphify_corpus` exports a prepared corpus under the global index
directory's `graphify-corpus/`: anchors, index metadata, anchor graph, and
chunked transcript Markdown with source provenance.

Run the separate `graphify` skill only when the user wants deeper graph
analysis, community detection, or `GRAPH_REPORT.md`. Keep Graphify output under
the corpus folder's `graphify-out/`.

## Bundles

`aippocampus_runtime.artifacts.export_bundle` produces portable thread-memory
bundles, with `aippocampus_runtime.artifacts.export_bundle` and `aippocampus export` preserved as operator
entrypoints. Bundles normally include manifest, handoff, index files, graph,
anchors, and raw rollout unless `--no-raw` is used.
`aippocampus_runtime.artifacts.import_bundle` extracts the bundle and appends a
pointer to the current workspace's anchors, with `aippocampus_runtime.artifacts.import_bundle` and
`aippocampus import` preserved as compatibility/facade entrypoints.

`aippocampus_runtime.sync.bundle` is the first Stage 3 sync backend.
`aippocampus_runtime.sync.bundle` remains the package-owner module. It
supports explicit local-folder `status`, `push`, `pull`, and `repair` commands
over clean source, registry rows, manifests, semantic triggers, working memory,
and cognitive-map sidecars. `aippocampus_runtime.sync.encrypted.bundle` adds the age-backed
encrypted variant and keeps ciphertext under `encrypted-sync/`.

`aippocampus_runtime.sync.object_storage.cli` reuses that same bundle manifest
over an HTTP object-storage transport; `aippocampus_runtime.sync.object_storage.cli` remains the
package owner. Each manifest file is stored as an object under
`AIPPOCAMPUS_OBJECT_PREFIX`, the manifest object is written last, and
`status`/`repair` verify object content by sha256 before `pull` imports it.
`aippocampus_runtime.sync.encrypted.object_storage` uses the same encrypted
bundle contract over HTTP `PUT`/`GET` and writes the encrypted outer manifest
last.
`aippocampus_runtime.sync.encrypted.admin` owns device-key UX and plaintext-to-encrypted
migration/cleanup so the core sync entrypoints stay focused on transport. The
object-store client boundary is split into the `aippocampus_runtime.sync.object_storage.client`
package owner and package-only
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
