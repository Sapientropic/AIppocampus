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
  phrase lists.
- `build_cognitive_map.py`: deterministic materializer for DeepSeek-proposed
  landmarks, regions, and routes. It never creates routes from registry
  keywords alone.
- `$CODEX_HOME/aippocampus-registry/subconscious_edges.jsonl`: staging concept
  edges consumed by `build_concept_graph.py`.
- `$CODEX_HOME/aippocampus-registry/subconscious_jobs.jsonl`: staging findings
  from non-edge jobs.
- `$CODEX_HOME/aippocampus-registry/promotion_candidates.jsonl`: second-pass
  review output for later promotion workflows.
- `$CODEX_HOME/aippocampus-registry/working_memory.jsonl`: soft working memory
  consumed by the prompt hook as source-backed staging, not formal truth.
- `$CODEX_HOME/aippocampus-registry/semantic_triggers.jsonl`: dynamic trigger
  rows consumed by `semantic_recall_gate.py`.
- `$CODEX_HOME/aippocampus-registry/cognitive_map.json`: hook-safe mental-map
  sidecar consumed by the prompt hook as scent, not evidence.

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
- `--samples-per-job 1`; raise this when you want multiple independent
  DeepSeek passes for reducer-quality diversity.
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

## Concurrency Contract

DeepSeek can be used aggressively, but hooks must stay cheap. The split is:

- hooks call `subconscious_scheduler.py --maybe-start` only
- the scheduler uses a short enqueue lock plus per-project lease fields in
  `subconscious_state.json`
- detached workers run `subconscious_jobs.py` with `--concurrency` and optional
  `--samples-per-job`
- worker threads call DeepSeek concurrently, but the parent process serializes
  writes to `subconscious_jobs.jsonl` and `subconscious_edges.jsonl`
- one failed or malformed sample must be isolated as `ok=false`; successful
  samples continue, and the batch reports `failure_count` / `partial_failure`
- reducers and materializers still own promotion, route filtering, semantic
  triggers, working memory, and cognitive-map sidecars

This makes high concurrency safe across multiple Codex threads: duplicate hook
starts should collapse into one leased project run, and foreground hooks should
only read stable sidecars.

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
