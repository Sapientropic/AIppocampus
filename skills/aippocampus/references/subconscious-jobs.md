# AIppocampus Subconscious Jobs

This document is the design note for AIppocampus's background cognition layer.
It is intentionally separate from `SKILL.md`: the skill entrypoint stays short,
while this file carries the evolving contract.

## Mental Model

The foreground assistant should stay responsive and evidence-aware. The
subconscious worker can be slower, cheaper, more iterative, and more exploratory.
Its job is not to answer the user directly. Its job is to shape the memory
terrain so future recall has better paths.

Use this split:

- Foreground: conversation, judgment, execution, explicit recall, source checks.
- Subconscious: clean-source inspection, relation discovery, drift detection,
  duplicate detection, trigger proposals, contradiction candidates.
- Evidence layer: clean source and raw rollout remain the facts.
- Staging layer: model-organized structure stays provisional until consumed,
  validated, or promoted by a stricter workflow.

The core safety rule is simple: subconscious jobs may create candidate structure,
but they must not rewrite source, delete source, or directly write formal memory.

## Files

- `subconscious_worker.py`: single-shot timeline-to-concept-edge extractor.
- `subconscious_agent.py`: minimal read-only tool loop for concept edges.
- `subconscious_jobs.py`: multi-job background cognition runner.
- `subconscious_staging_maintenance.py`: dry-run maintenance reporter for
  local-private staging queues. It classifies rows and pressure, but does not
  archive, compact, or delete.
- `subconscious_scheduler.py`: hook-safe scheduler that starts detached
  subconscious runs only after cooldown, new-turn, API-key, and lock checks.
- `memory_candidate_router.py`: deterministic promotion-candidate router for
  soft working memory. It prevents a human review inbox by assigning
  `use_silently`, `use_with_source`, `confirm_when_relevant`, or `park`.
- `aippocampus_runtime.recall.semantic_trigger_router` plus the
  `semantic_trigger_router.py` compatibility command: deterministic router that
  turns source-backed `hook_trigger`/project candidates into
  `semantic_triggers.jsonl`, so the prompt hook can use data-driven semantic
  cues instead of expanding hard-coded phrase lists. It also merges the
  reviewed seed triggers in `references/reviewed-semantic-triggers.seed.jsonl`;
  keep that seed compact, reviewed, source-conscious, and AIppocampus-specific.
- `build_cognitive_map.py`: deterministic materializer for DeepSeek-proposed
  landmarks, regions, and routes. It never creates routes from registry
  keywords alone.
- `build_semantic_scope_labels.py`: deterministic materializer for
  DeepSeek/subconscious `semantic_scope_labels` findings. It only writes
  `semantic-scope-labels.jsonl` rows for existing clean-source message ids with
  exact source refs.
- `$CODEX_HOME/aippocampus-registry/subconscious_edges.jsonl`: staging concept
  edges consumed by `build_concept_graph.py`.
- `$CODEX_HOME/aippocampus-registry/subconscious_jobs.jsonl`: staging findings
  from non-edge jobs.
- `$CODEX_HOME/aippocampus-registry/promotion_candidates.jsonl`: second-pass
  review output for later promotion workflows.
- `$CODEX_HOME/aippocampus-registry/working_memory.jsonl`: soft working memory
  consumed by the prompt hook as source-backed staging, not formal truth.
- `$CODEX_HOME/aippocampus-registry/semantic_triggers.jsonl`: dynamic trigger
  rows consumed by `aippocampus_runtime.recall.semantic_recall_gate` and the
  prompt hook's local pre-gate/query seed path.
- `$CODEX_HOME/aippocampus-registry/semantic_cues.jsonl`: learned multilingual
  semantic aliases from repeated prompt-hook hits. It is consumed as trigger
  context/query hints only and must not be treated as source truth.
- `$CODEX_HOME/aippocampus-registry/cognitive_map.json`: hook-safe mental-map
  sidecar consumed by the prompt hook as scent, not evidence.
- `<clean-source>/semantic-scope-labels.jsonl`: optional per-clean-source
  sidecar for DeepSeek/subconscious life-wide scope labels. It is keyed by
  `message_id`, consumed by search and timeline builders, and must not rewrite
  `messages.jsonl`.

## Shared Agent Contract

The job runner gives DeepSeek a bounded perception loop. Tools are read-only:

- `search_clean_source`: search registered clean-source messages.
- `get_turn_context`: inspect the clean messages around one turn/ref.
- `expand_concepts`: inspect nearby concepts in `concept_index.sqlite`.
- `recent_edges`: inspect recent staging concept edges.

The canonical tool contract lives in
`aippocampus_runtime.subconscious.runtime.READ_ONLY_TOOL_REGISTRY`. The agent
system prompt, agent/job initial payloads, dispatcher, and dry-run
`tool_contract_version` all derive from that registry. Keep additions small and
static: one registry entry plus tests, no dynamic tool discovery, no write
tools, and no broad agent framework. This is an anti-drift guard so prompt
wording, payload examples, and runtime dispatch cannot silently disagree.

Defaults are quality-oriented:

- `--max-steps 16`.
- `--max-steps 0` means use the hard safety cap.
- Hard safety cap: 64 steps.
- `--min-tool-steps 1`.
- `--concurrency 4` for `subconscious_jobs.py`.
- `--samples-per-job 2` by default for fresh DeepSeek-backed work, so the
  foreground hook can enqueue a fast parallel background pass instead of
  waiting on one fragile model call. Lower it explicitly only for cost-focused
  operator runs.
- `--temperature 0.2`.
- No default `max_tokens` cap.

The model can be exploratory in tool planning, but output remains constrained:
every accepted finding must have source refs that resolve to initial turn refs
or tool observation refs.

Adaptive shell selection starts as a dry-run/report policy in
`aippocampus_runtime.subconscious.shell_selection`. It may recommend
`deterministic_only`, `worker`, `agent_probe`, `agent_deep`, or
`skip_due_to_backpressure` from queue shape, corpus size, thread span, and prior
low-confidence worker output, but the scheduler must not treat that report as
permission to run expensive deep agents automatically. Use explicit operator
commands or a later named budget policy before turning `agent_probe`/`agent_deep`
into execution. The report is cost/quality routing only; it does not raise
staging rows into formal memory or bypass deterministic validation.

For operator inspection, run the scheduler with `--dry-run --json
--include-private-report`; keep the default public `--json` projection compact
for hook-safe sharing. `--shell-selection` is a report override for debugging
and does not by itself start a worker or agent path.

Concept-edge source integrity is owned by
`aippocampus_runtime.subconscious.edge_validation`. The single-shot worker and
minimal tool-using agent share the same confidence floor, edge-type fallback,
generic/noise concept filter, self-edge rejection, source-ref resolution, and
`why` compaction policy. The intentional shell difference is source-ref shape
and retention: worker staging edges keep turn-shaped refs and retain 3 refs;
agent staging edges keep `ref`/observation-compatible refs and retain 4 refs.
Do not loosen one shell's source-ref or confidence gate without adding an
explicit named policy difference and tests.

For the minimal agent, `min_tool_steps` is only a cheap anti-laziness gate. It
does not prove the final edge used useful tool evidence. Agent run JSON exposes
sanitized `tool_grounding` diagnostics with ref counts, useless tool-call
counts, and one of `tool_grounded`, `initial_only_after_tool`, or `ungrounded`.
This is diagnostic by default: cite `o*` observation refs when tool hits support
the edge, but do not cite them merely to satisfy a metric when the initial turn
refs are the real evidence or tools returned no useful source refs.

Every accepted finding also gets deterministic metadata before it is written:

- `fingerprint`: stable-ish finding id for dedup/review.
- `quality.evidence_strength`: source count/thread/final-answer support.
- `quality.specificity`: whether the finding names concrete concepts.
- `quality.novelty`: a light novelty estimate for staging triage.
- `quality.actionability`: whether a downstream action is clear.
- `quality.drift_risk`: how likely the finding needs human/context review.
- `quality.promotion_readiness`: backward-compatible alias for the heuristic
  promotion score.
- `quality.heuristic_promotion_score`: compact blended routing score. It is
  not calibrated confidence, not evidence, and not an automatic promotion gate.
- `quality.score_version`: score contract version; current value is
  `heuristic_promotion_readiness_v1`.
- `quality.score_kind`: current value is `heuristic_routing_signal`.
- `quality.bucket`: `strong`, `usable`, `weak`, or `noise`.

`subconscious_review.py` includes aggregate `quality_diagnostics` with bucket
distribution and review outcomes by bucket. Treat those diagnostics as
threshold-sensitivity/audit data only: promotion still depends on source refs,
confidence gates, candidate-type gates, and human/context review where
applicable.

## DeepSeek Model Routing

`deepseek_model_routing.py` owns the model split for DeepSeek-compatible
background work:

- default, fast, and hook-adjacent work resolves to `deepseek-v4-flash`
- `slow_adjudication`, `suppressed_label_recovery`, and
  `agentic_source_review` resolve to `deepseek-v4-pro`
- `--model` remains an explicit operator override
- `AIPPOCAMPUS_DEEPSEEK_FLASH_MODEL` and
  `AIPPOCAMPUS_DEEPSEEK_PRO_MODEL` override the defaults; legacy
  `DEEPSEEK_MODEL` remains a flash-route fallback only

Keep Pro out of foreground hooks. Hooks enqueue detached workers and read
stable sidecars; Pro is for slower evidence work where latency is acceptable.
`semantic_scope_suppressed_recovery.py` uses Pro to re-adjudicate labels that
the strict materializer suppressed. It first inspects the clean-source message
through a tool, then sends the recovered findings back through the unchanged
strict materializer. This restores labels only when stronger per-label evidence
passes the same thresholds; it must not lower thresholds or revive empty
evidence from old broad sidecars.

## Provider Route Boundary

DeepSeek remains the default high-throughput route for semantic gates, warm
scouts, subconscious jobs, and review passes. Non-DeepSeek OpenAI-compatible
routes are explicit fallbacks, not quality or latency parity claims. Configure
one with `AIPPOCAMPUS_OPENAI_COMPAT_ROUTE`,
`AIPPOCAMPUS_OPENAI_COMPAT_PROVIDER`, `AIPPOCAMPUS_OPENAI_COMPAT_MODEL`,
`AIPPOCAMPUS_OPENAI_COMPAT_BASE_URL`, and
`AIPPOCAMPUS_OPENAI_COMPAT_API_KEY_ENV`, then select it with `--model-route`
on the relevant worker/review CLI.

By default, OpenAI-compatible fallback routes do not send DeepSeek-only
`user_id` or `thinking` fields, do not assume DeepSeek prefix-cache metrics,
and use conservative concurrency (`AIPPOCAMPUS_OPENAI_COMPAT_CONCURRENCY`,
default 1). Set `AIPPOCAMPUS_OPENAI_COMPAT_SUPPORTS_JSON`,
`AIPPOCAMPUS_OPENAI_COMPAT_SUPPORTS_USER_ID`,
`AIPPOCAMPUS_OPENAI_COMPAT_SUPPORTS_THINKING`, and
`AIPPOCAMPUS_OPENAI_COMPAT_CACHE_METRICS_KIND` only when the selected endpoint
actually supports those behaviors. Local/offline routes are appropriate for
privacy-sensitive or disconnected operation; do not route foreground hooks to
them by default or claim they match hosted Flash-class throughput.

## Concurrency Contract

DeepSeek can be used aggressively, but hooks must stay cheap. The split is:

- hooks call `subconscious_scheduler.py --maybe-start` only
- lifecycle hooks enqueue that scheduler as a detached process; they do not
  wait on scheduler imports, registry scans, stale locks, or DeepSeek calls
- the scheduler uses a short enqueue lock plus per-project lease fields in
  `subconscious_state.json`
- detached workers run `subconscious_jobs.py` with `--concurrency` and optional
  `--samples-per-job`
- worker threads call DeepSeek concurrently across distinct jobs/batches, but
  same-prefix diversity samples run in sample waves: sample 1 completes first
  so DeepSeek can land the KV prefix, then sample 2+ may run. Do not collapse
  this back into launching all samples at once; simultaneous same-prefix calls
  often both miss the server cache.
- the parent process serializes writes to `subconscious_jobs.jsonl` and
  `subconscious_edges.jsonl`
- after `semantic_scope_labeling`, the detached project run materializes
  accepted labels into per-thread `semantic-scope-labels.jsonl` sidecars and
  rebuilds `project_timeline.json` so search and timeline consumers see the
  same navigation metadata
- dream queue planning is deterministic and detached-only:
  `aippocampus_runtime.dream.queue` turns ready dream input packs into bounded
  queue items with trigger family, priority, dedup key, review/expiry horizon,
  cost budget, and `deepseek_prefix_v1` prompt-order metadata. `dream_queue.py`
  remains the direct-script compatibility shim. It does not make model calls
  and must not be run as a foreground hook worker.
- queued dream worker samples keep stable prompt-prefix groups together:
  stable worker contract first, source-pack payload second, and variable run
  directive last. This preserves the same-prefix ordering needed for DeepSeek
  KV cache warm-up when a later live worker consumes the queue.
- `aippocampus_runtime.dream.sleep_cycle` is the detached execution bridge from
  queue metadata to bounded workers; `dream_sleep_cycle.py` remains the
  documented direct-script compatibility shim. It selects only due items, unless
  the scheduler explicitly passes `--run-ready` during a detached project pass,
  never widens `foreground_eligible=false`, defaults to `--no-write`, and emits
  sanitized counts/failure/cache summaries instead of raw source handles. When
  `--write` is enabled, it appends queue lifecycle, adjudicated finding, and
  projected working-memory rows under the scheduler's serialized process lock.
- `dream_precision_policy.py` adds explicit retention, activation, and
  retrospective policy shapes. These policies separate hard gate failures from
  soft lifecycle pressure; aggregate scores tune attention/ranking only and do
  not promote model confidence into truth.
- `dream_retrospective_lifecycle.py` is the periodic retrospective check for
  parked prospective and active-imagination probes. It waits until
  `review_after`, ignores pre-probe and future-leakage rows, and counts only
  later source-backed rows that explicitly target the probe; term overlap alone
  remains diagnostic noise.
- bounded model-backed dream workers live in
  `aippocampus_runtime.dream.worker`; `dream_worker.py` is only the direct-script
  compatibility shim. They consume
  only `status="ready_for_dream_worker"` packs for compensatory,
  amplification, prospective, and active-imagination functions, require cited
  source-ref ids for every candidate/bridge claim, default to `no_write=True`,
  and pass accepted or parked candidates through
  `background_adjudicate_dream_findings()` before any working-memory projection
  is possible. Active-imagination candidates additionally require two
  independent source anchors, `why_this_is_not_fact`, and `counter_evidence`;
  sensitive/profile-style interpretations stay parked. Prospective
  retrospective validation only counts later rows that explicitly target the
  finding id and carry source refs; similar terms alone stay `unknown`.
- adjudicated dream hypotheses project through
  `aippocampus_runtime.dream.working_memory` into ordinary working-memory rows.
  Those rows carry
  `foreground_use` / `sensitive_use_gate` metadata: use quietly only when it
  changes the current answer or route, stay silent when source is already
  visible, expired, or high-annoyance, and reopen source before any strong
  user-facing claim. Accepted rows also carry the #299 trust-horizon contract:
  `validated_at`, `validated_by`, `source_fingerprint`, `review_after`,
  `expires_at`, `invalidation_triggers`, `visibility_tier`, and the nested
  `trust_horizon` capsule. Treat these as invalidation metadata, not proof;
  source drift, contradiction, user evidence requests, exact/quoted or sensitive
  claims, expiry, and review-due states must reopen source or stay silent before
  foreground use. The live consumers enforce the same boundary:
  working-memory matching skips blocked/expired/review-due rows, hook rendering
  labels the row as a dream hypothesis, ambient cards require source reopen for strong
  claims, reflection topology only accepts audited collapsed nodes, and agency
  affordances downgrade direct dream inputs to backstage-only.
- cross-surface authority is audited, not inferred from confidence. Use
  `aippocampus_runtime.ops.activation_authority_audit` to inspect whether AAR
  nudges, dream hypotheses, working memory, semantic triggers, ambient cards,
  active recall locks, or pruning rows are leaking into factual-evidence
  territory. Its no-write report treats pruning as activation eligibility only,
  requires source/current-checkout evidence for truth conflicts, and lets
  explicit user correction suppress otherwise plausible strategy surfaces
  without making the correction itself an ungrounded fact. The #483 extension
  adds foreground-usefulness counters for false scent reduction, wrong-route
  drag reduction, duplicate-route collapse, recent helpful/harmful outcomes,
  and estimated verification tool calls saved; apply mode writes only an
  append-only lifecycle manifest for the owning surface writer, not source or
  truth mutations.
- `dream_real_history_eval.py` reports dream impact in two layers: structural
  substrate lift and a sanitized user-visible ablation harness. The latter
  separates recall, reflection, unsupported-claim suppression, source-support,
  manual source-review, and cost/cache metrics; it must not be treated as real
  user-value proof without reviewed samples and live/behavioral evidence.
- `aippocampus_runtime.dream.input_pack` owns source-pack assembly and
  `dream_input_pack.py` remains the public-summary CLI compatibility shim. Use
  `--internal-full` only for local worker handoff paths that are allowed to
  carry source refs; do not paste full pack output into public logs, docs, or
  GitHub issues.
- human/operator intervention is explicit: ordinary queue items go to detached
  background adjudication; sensitive direct assertions or operator-requested
  dream runs may require review, but the queue itself is not a user approval
  ritual.
- one failed or malformed sample must be isolated as `ok=false`; successful
  samples continue, and the batch reports `failure_count` / `partial_failure`
- reducers and materializers still own promotion, route filtering, semantic
  triggers, working memory, and cognitive-map sidecars

This makes high concurrency safe across multiple Codex threads: duplicate hook
starts should collapse into one leased project run, and foreground hooks should
only read stable sidecars.

## DeepSeek KV Cache Contract

DeepSeek's server-side KV cache is automatic; AIppocampus does not implement a
local prompt cache for model calls. The optimization here is prompt shape:
requests should put stable contracts first, source payloads next, and
run-specific fields last so DeepSeek can land and later match complete prefix
units. See the official
DeepSeek KV cache guide:
`https://api-docs.deepseek.com/zh-cn/guides/kv_cache`.

Keep this ordering rule when changing DeepSeek-compatible payload builders:

- stable contract/schema/tool payloads first, such as job specs, label
  guidance, output schemas, and tool lists
- stable source/catalog payloads next, such as timeline turns, registry
  catalog, trigger catalog, and findings
- variable run directives last, such as current prompt, objective, focus,
  worker name, diversity sample instruction, and repair text
- model responses should preserve `usage.prompt_cache_hit_tokens` and
  `usage.prompt_cache_miss_tokens`; command JSON returns also expose a compact
  `cache` object with `hit_tokens`, `miss_tokens`, and `hit_rate`
- interpret provider-level cache hit rates by request shape. A broad smoke that
  creates one new prefix and one follow-up sample per batch can naturally land
  near 50% even when the second request hits near 99%; the bug signal is the
  same-prefix follow-up staying cold, or all same-prefix samples launching
  before the first request can warm the server cache.

This mirrors the T-Sense monitor extraction lesson: stable
profile/schema/instructions and repeated scan context belong before incremental
or per-run questions. Do not "clean up" the JSON key order alphabetically; for
DeepSeek cache behavior, order is part of the runtime contract.

All production `ChatClientConfig(...)` call sites must now pass an explicit
`cache_contract`: `deepseek_prefix_v1` for DeepSeek-compatible routes and
`none` for providers where AIppocampus must not claim DeepSeek prefix-cache
telemetry. `model_client.py` rejects DeepSeek-flavored configs without the
DeepSeek contract, and docs health scans scripts for missing keywords so newly
added LLM callers cannot silently bypass this billing guard.

## Jobs

### `question_extraction`

Purpose: extract genuine user questions and explicit unresolved frontiers.

Output kinds:

- `question_candidate`: a real question the user was pursuing, with
  `question_text`, `question_short`, `intent_orientation`, and source-backed
  `what_features`, `where_context`, and `phase_context` unless that axis is
  unavailable from the source/tool context. `collaboration_context` and
  `recommendation` stay optional and must not be invented. `question_text` is a
  short normalized question, not a pasted transcript. If the model emits a long
  raw excerpt, validation may compress it to `question_short`/title or reject it.
- `frontier_marker`: a source-backed stopping point or unresolved boundary,
  with `frontier_type`, `boundary_reason`, and `where_context` or
  `phase_context` when source-backed.

This is not a regex job and not every sentence with a question mark qualifies.
DeepSeek should use tool observations and source refs to decide whether the
question mattered. `frontier_marker` is stricter: emit it only when the source
explicitly shows a block, deferral, missing evidence, dissatisfaction, or scope
boundary.

Local job results include counts-only
`quality_diagnostics.question_extraction_field_presence` for this job. It
reports raw-final, accepted-final, and validated field coverage by kind, but
never source text, paths, refs, message ids, thread ids, or field values. Public
CLI `--json` output remains sanitized and does not expose local-private job
details.

### `question_tracking`

Purpose: group existing source-backed `question_candidate` findings into
append-only `question_link` findings.

The Phase 2 runner is deterministic and lives in
`aippocampus_runtime.question.tracking`; `question_tracking.py` is the
direct-script/import compatibility shim. `subconscious_jobs.py --job
question_tracking` invokes it after semantic extraction jobs have serialized
their writes, so tracking reads completed `question_candidate` rows instead of
racing the concurrent worker pool.

Output: `question_link` findings in the same `subconscious_jobs.jsonl` stream,
with `question_cluster_id`, `linked_questions`, `dependency_edges`,
`match_evidence`, and merged `source_refs`.

Borderline pairs are not accepted by score alone. They remain skipped unless an
explicit confirmation artifact accepts the pair; the accepted link still cites
the original question source refs, not the confirmation as truth.

### `concept_edges`

Purpose: propose concept graph edges for ambient recall.

Output: job finding plus optional sync into `subconscious_edges.jsonl`.

Use when vague prompts need better bridge concepts, for example:

- `本地底座` -> `Go runtime`
- `gotd/td` contrasts with `gogram`
- `AGPLv3` related to `GPLv3`

### `decision_evolution`

Purpose: detect decisions that changed, narrowed, or stabilized.

This should phrase most changes as evolution, not contradiction. Example:
`Telethon is enough for current product` can evolve into
`Go runtime is worth a spike before market push` without either being false.

### `trigger_mining`

Purpose: propose ambient recall triggers and query aliases.

It must avoid:

- trivial utterances such as `好，开干`
- Goal/system/tool injection text
- broad personalization triggers that make every topic about the user

Good triggers are concrete, user-natural phrases that would help a future hook
smell relevant memory without forcing it into the foreground.

### `semantic_scope_labeling`

Purpose: add dynamic life-wide navigation labels when lexical rules are too
blunt.

This is where fuzzy judgments belong: metaphors, pivots, excitement,
dissatisfaction, dilemmas, recurring fascinations, and other casual-important
signals that should not become hard-coded phrase-list sprawl. Output should be
staged `semantic_scope_labels` findings with `message_id`, canonical
`scope_labels`, `label_evidence`, `confidence`, and exact source refs. Every
materialized label must have its own short source-grounded evidence reason and
label-specific confidence; row-level confidence is not a fallback. The
materializer uses a default evidence threshold plus stricter thresholds for
source-review-sensitive labels. These thresholds intentionally suppress broad
or over-inferred labels until DeepSeek can defend them with stronger evidence:
for example `relationship_continuity` is not a generic "memory over time"
label, `open_question` is not every immediate question, and `reading_notes` is
not general film/media reaction. The deterministic
`build_semantic_scope_labels.py` materializer turns those findings into
`semantic-scope-labels.jsonl` rows only when the target message exists in clean
source and at least one source ref points to that same `message_id`. Consumers
merge these labels for search and timeline navigation, but exact claims still
require following source refs back to clean source. These findings are
navigation-only and are excluded from the default promotion-review path so a
fuzzy label does not become formal memory by accident.

### `cognitive_map`

Purpose: propose hippocampus-like mental-map structure: landmarks, regions,
route cues, possible detours, and negative cues.

This is the intelligent part of the cognitive map. DeepSeek should inspect
clean source and propose source-backed navigation, for example:

- landmark: `AIppocampus`
- region: `memory architecture`
- route cues: `心理地图`, `位置细胞`, `网格细胞`
- target thread keys backed by source refs

`build_cognitive_map.py` then validates and materializes the result. If no
`cognitive_map` finding exists, the sidecar may contain episodes but must report
zero routes and `needs_subconscious`.

### `memory_dedup`

Purpose: find duplicate or near-duplicate memory material across registered
threads.

Output is a merge/canonicalization candidate only. It must not delete anything.
This job is especially useful when the same thread was registered twice, or when
similar conclusions exist in several project sessions.

### `project_drift`

Purpose: detect project direction shifts and phase changes.

Examples:

- script -> desktop app
- crawler -> local-first review system
- Telethon scanner -> runtime abstraction / Go sidecar investigation

This helps future recall understand why older wording may be historically true
but no longer the dominant project frame.

### `preference_candidates`

Purpose: stage possible durable user preferences for later formal review.

This job should be conservative. A preference candidate should include when it
applies and when it does not apply. It does not write formal `prefs` memory.

### `contradiction_scan`

Purpose: find tensions or possible contradictions needing review.

Prefer `tension` for evolving decisions. Use contradiction only when two claims
cannot both be true under the same scope and time frame.

## Operating Pattern

Lifecycle hooks should call only the cheap scheduler entrypoint:

```powershell
python "$env:CODEX_HOME\skills\aippocampus\scripts\subconscious_scheduler.py" --maybe-start --cwd "$PWD" --json
```

`--maybe-start` never sends prompt text and should return quickly. When due, it
starts a detached `--run-due` worker and logs to
`$CODEX_HOME/aippocampus-registry/subconscious_scheduler.log`. This keeps the
subconscious automatic without making every user prompt or Stop hook wait for
DeepSeek.

Run one focused job:

```powershell
python "$env:CODEX_HOME\skills\aippocampus\scripts\subconscious_jobs.py" --job project_drift --project "T-Sense" --json
```

Run no-write question/frontier extraction smoke:

```powershell
python "$env:CODEX_HOME\skills\aippocampus\scripts\subconscious_jobs.py" --job question_extraction --project "AIppocampus" --no-write --json
```

Run deterministic Phase 2 tracking over staged question candidates:

```powershell
python "$env:CODEX_HOME\skills\aippocampus\scripts\subconscious_jobs.py" --job question_tracking --json
```

Run extraction and tracking in dependency order:

```powershell
python "$env:CODEX_HOME\skills\aippocampus\scripts\subconscious_jobs.py" --job all --project "AIppocampus" --json
```

For the higher-level onboarding wrapper, prefer:

```powershell
python "$env:CODEX_HOME\skills\aippocampus\scripts\onboard.py" --provider codex --frontier-mode smoke --format json --cwd "$PWD"
```

That wrapper returns compact `sample_findings` and defaults the frontier scope
to the current project inferred from `--cwd`. Use `--frontier-project *` only
when intentionally inspecting whole-machine frontier quality.

Run all jobs:

```powershell
python "$env:CODEX_HOME\skills\aippocampus\scripts\subconscious_jobs.py" --job all --project "T-Sense" --concurrency 4 --json
```

Run multiple independent samples per job:

```powershell
python "$env:CODEX_HOME\skills\aippocampus\scripts\subconscious_jobs.py" --job cognitive_map --project "AIppocampus" --concurrency 4 --samples-per-job 3 --json
```

Rebuild concept graph after `concept_edges`:

```powershell
python "$env:CODEX_HOME\skills\aippocampus\scripts\build_concept_graph.py"
```

Materialize semantic life-wide labels after `semantic_scope_labeling`:

```powershell
python "$env:CODEX_HOME\skills\aippocampus\scripts\build_semantic_scope_labels.py" --jobs-output "$env:CODEX_HOME\aippocampus-registry\subconscious_jobs.jsonl" --clean-source-dir "<thread-clean-source-dir>" --json
```

For smoke tests without adding staging noise:

```powershell
python "$env:CODEX_HOME\skills\aippocampus\scripts\subconscious_jobs.py" --job all --project "T-Sense" --no-write --json
```

Run second-pass review over staging findings:

```powershell
python "$env:CODEX_HOME\skills\aippocampus\scripts\subconscious_review.py" --json
```

Route promotion candidates into soft working memory:

```powershell
python "$env:CODEX_HOME\skills\aippocampus\scripts\memory_candidate_router.py" --json
```

Use `--focus` for lightweight rerank without splitting every job into tiny
scopes:

```powershell
python "$env:CODEX_HOME\skills\aippocampus\scripts\subconscious_review.py" --focus "T-Sense runtime and product strategy" --json
```

Review produces:

- `aippocampus_promotion_candidate`
- `aippocampus_subconscious_duplicate_group`
- `aippocampus_subconscious_weak_finding`

This is the main bridge from "the subconscious noticed things" to "a later
workflow can consume the strongest candidates".

## Staging Maintenance

Staging queues are append-only review surfaces. Maintenance defaults to a
dry-run report:

```powershell
python "$env:CODEX_HOME\skills\aippocampus\scripts\subconscious_staging_maintenance.py" --json
```

The report classifies `subconscious_edges.jsonl` and
`subconscious_jobs.jsonl` rows as `active`, `review`, or
`archive_candidate`, counts duplicates and legacy/new finding-id formats, and
reports row/byte backpressure. In default mode, `archive_candidate` is only a
proposed action: the command does not rewrite, move, compact, or delete rows.

Explicit apply mode is an operator maintenance action, not a hook path:

```powershell
python "$env:CODEX_HOME\skills\aippocampus\scripts\subconscious_staging_maintenance.py" --apply --json
```

Apply mode archives only rows already classified as `archive_candidate`, writes
a local-private archive manifest, verifies archive file hashes / row counts /
stable ids, and only then rewrites the active staging JSONL files with
`active` and `review` rows. It preserves the archived rows themselves plus
manifest counts for `source_refs`, promotion traceability,
dream/question/review references, and private audit provenance. Referenced rows
stay `review` until the owning consumer can prove its trace chain survives.
JSONL readers must remain tolerant of legacy `sf_...` finding ids and
deterministic SHA-style ids.

Producer warnings are soft pressure signals only. `append_staging_edges()` and
`append_job_findings()` may return `staging_pressure` when
`AIPPOCAMPUS_SUBCONSCIOUS_STAGING_WARN_ROWS` or
`AIPPOCAMPUS_SUBCONSCIOUS_STAGING_WARN_BYTES` is exceeded, but they must not
drop source-backed rows. The scheduler/operator can use those warnings to run
the dry-run report or reduce noisy batches.

## Promotion Boundary

Staging findings can be consumed in several ways:

- concept edges can feed `concept_index.sqlite`
- cognitive-map findings can feed `cognitive_map.json` for hook-safe
  wayfinding
- semantic scope-label findings can feed per-thread
  `semantic-scope-labels.jsonl` for search/timeline navigation
- trigger candidates can feed future hook association generation
- preference candidates can feed a formal memory review workflow
- contradiction candidates can become human review prompts
- drift/evolution findings can help answer future "why did we change course"
  questions
- promotion candidates can feed explicit user review or future automatic
  consumers
- working-memory routes can feed foreground hook scent/context while preserving
  the source-backed boundary. `confirm_when_relevant` is not a notification; it
  means the assistant should ask only if the current action would depend on that
  candidate or if source signals conflict.

Some candidate generation can happen automatically through
`subconscious_scheduler.py`, and router output can be used as soft working
memory, but formal promotion still does not happen implicitly. The subconscious
layer is a generator of candidate structure, not a source of truth.
