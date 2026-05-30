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
- `subconscious_scheduler.py`: hook-safe scheduler that starts detached
  subconscious runs only after cooldown, new-turn, API-key, and lock checks.
- `memory_candidate_router.py`: deterministic promotion-candidate router for
  soft working memory. It prevents a human review inbox by assigning
  `use_silently`, `use_with_source`, `confirm_when_relevant`, or `park`.
- `semantic_trigger_router.py`: deterministic router that turns source-backed
  `hook_trigger`/project candidates into `semantic_triggers.jsonl`, so the
  prompt hook can use data-driven semantic cues instead of expanding hard-coded
  phrase lists. It also merges the reviewed seed triggers in
  `references/reviewed-semantic-triggers.seed.jsonl`; keep that seed compact and
  AIppocampus-specific.
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
  rows consumed by `semantic_recall_gate.py` and the prompt hook's local
  pre-gate/query seed path.
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

Every accepted finding also gets deterministic metadata before it is written:

- `fingerprint`: stable-ish finding id for dedup/review.
- `quality.evidence_strength`: source count/thread/final-answer support.
- `quality.specificity`: whether the finding names concrete concepts.
- `quality.novelty`: a light novelty estimate for staging triage.
- `quality.actionability`: whether a downstream action is clear.
- `quality.drift_risk`: how likely the finding needs human/context review.
- `quality.promotion_readiness`: compact blended score.
- `quality.bucket`: `strong`, `usable`, `weak`, or `noise`.

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

## Jobs

### `question_extraction`

Purpose: extract genuine user questions and explicit unresolved frontiers.

Output kinds:

- `question_candidate`: a real question the user was pursuing, with
  `question_text`, `question_short`, optional `intent_orientation`,
  `what_features`, `where_context`, `phase_context`, and
  `collaboration_context`. `question_text` is a short normalized question, not
  a pasted transcript. If the model emits a long raw excerpt, validation may
  compress it to `question_short`/title or reject it.
- `frontier_marker`: a source-backed stopping point or unresolved boundary,
  with `frontier_type` and `boundary_reason`.

This is not a regex job and not every sentence with a question mark qualifies.
DeepSeek should use tool observations and source refs to decide whether the
question mattered. `frontier_marker` is stricter: emit it only when the source
explicitly shows a block, deferral, missing evidence, dissatisfaction, or scope
boundary.

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

For the higher-level onboarding wrapper, prefer:

```powershell
python "$env:CODEX_HOME\skills\aippocampus\scripts\onboard_codex.py" --frontier-mode smoke --format json --cwd "$PWD"
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
