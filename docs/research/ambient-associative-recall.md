# Ambient Associative Recall

Status: design memo with implementation tracker; not the full runtime contract.
Origin: user/product discussion, 2026-05-27.
Related: [The Pearl of Presence](pearl-of-presence.md),
[Thread Intuition Layer](affect-side-channel.md),
[Dream Task Design](dream-task-design.md).

## The Problem

Explicit recall works, but it is not how people usually talk.

A user will sometimes ask, "Do you remember..." and then a search-like memory
workflow is appropriate. Most of the time, though, continuity should surface
without ceremony. A person returns to a transformation-and-continuity motif,
and the old line of thought from `docs/未干的地图.md` should lightly glow without
this memo mirroring the origin wording.

The goal is not to make every answer autobiographical. It is to reduce the
user's burden of being the only one carrying the past. The agent should be able
to notice when a topic touches an old trajectory, then decide how visibly to
use that resonance.

## Product Goal

Ambient associative recall should make old traces naturally available during
ordinary conversation.

It should feel like this:

> This touches the same question you have been circling: whether continuity can
> survive transformation. I will answer from there.

It should not feel like this:

> Search result: session 019e5aea line 190 contains similar text.

The user-facing behavior is **active gentle nudge** by default. The agent may
lightly name the relevant old thread of thought when it helps the current
conversation, without forcing the user to ask for memory explicitly.

## Four Visibility Levels

Ambient recall should choose a visibility level for every candidate.

| Level | User-facing behavior | When to use |
|---|---|---|
| Silent tuning | The answer quietly follows known preferences, metaphors, and concerns. | Weak or broad resonance; technical work where memory should not interrupt. |
| Active gentle nudge | The agent briefly names the old line of thought and continues naturally. | Medium/high resonance in writing, research, life-wide, or product-direction conversations. |
| Source-backed recall card | The agent cites the prior thread, key line, and why it matters. | User asks about memory, the recalled context changes the answer, or confidence needs grounding. |
| Deep archival recall | The agent opens clean source or raw audit paths for exact wording. | The user asks for original wording, disputes a memory, or the decision depends on details. |

The default for meaningful personal, philosophical, writing, and long-running
project themes is active gentle nudge. The default for routine coding tasks is
silent tuning unless the memory changes a boundary or prevents a mistake.

## Runtime Shape

Ambient associative recall is not one search call. It is a staged recall
pipeline, and in agent workflows the pipeline spans a whole thread rather than
one user prompt. A Codex or Claude agent thread often contains many turns of
planning, implementation, clarification, and closeout. Ambient recall should
therefore behave like a thread-level warming layer: early turns may only produce
a weak scent, while later turns can benefit from recall work that finished after
the first answer already moved on.

```text
turn N user prompt
  -> cheap local prefilter
  -> thread ambient cache lookup
  -> local sidecar lookup
  -> optional timeboxed warm scouts
  -> deterministic merge and source validation
  -> private associative context
  -> agent chooses visibility level
  -> late scout results warm the thread cache for turn N+1
```

The foreground agent should not spend its attention rummaging through memory.
It should receive a compact private context that feels more like peripheral
awareness:

```yaml
associations:
  - theme: "life, transformation, identity continuity"
    resonance: high
    suggested_visibility: active_gentle_nudge
    suggested_use: "Continue from the question of whether continuity survives transformation."
    key_line: "origin essay transformation-continuity motif"
    evidence_refs:
      - "session:019e5aea... source_index:190"
    expand_if: "User asks for original wording, old context, or a deeper source-backed answer."
```

This private context is advice to the agent, not text to paste into the final
answer.

## Latency Strategy

The user experience depends on recall feeling present, not bolted on.

Use four paths with different latency budgets:

| Path | Budget | Work | Output |
|---|---:|---|---|
| Hot path | ~50-250 ms | Local cues, prompt terms, registry metadata, cached scent cards, recent working memory. | Immediate private associations or no-op. |
| Thread-cache path | ~50-250 ms after warmup | Read the current agent thread's ambient cards, topic epoch, negative contexts, and source validation cache. | Stable peripheral awareness across many turns in the same thread. |
| Warm path | async foreground enqueue; live quorum calibration currently needs seconds, not milliseconds | Parallel DeepSeek recall scouts over candidate windows and sidecars. Use quorum-first for foreground-style evaluation, wait-all only detached/evaluation. | Better ranked recall cards if they arrive in time; otherwise future cache material. |
| Cold path | Detached | Subconscious jobs, cognitive map, semantic scope labels, theme/dream outputs, cache refresh. | Future hot/warm path material. |

The hot path must always be safe to run for every prompt. The warm path may run
opportunistically when the prompt has meaningful semantic cues. The cold path
does the heavy lifting before the user needs it.

The foreground hook should never block on fresh deep reasoning. It may consume
available cached cards and launch or enqueue warm work. The main agent can use
warm results if they arrive inside the budget; otherwise the result becomes
future cache for the next few turns. In an agent thread, catching up one turn
late is still useful because the conversation usually keeps moving inside the
same topic field.

The hot path now treats the prompt-time scent threshold as context-aware
routing diagnostics rather than one global constant. This is a narrow #359
slice for the #201/#281 problem space: long same-thread continuations and exact
semantic-result reuse can make a weak scent measurable, while broad fresh
personal prompts, secret surfaces, and current-repo factual prompts stay at the
base threshold. The output is safe reason-code telemetry for the agent/operator;
it is not a new memory surface and it cannot upgrade a scent into source-backed
evidence.

## Thread Ambient Cache

The primary cache should be keyed to the agent thread, not only to exact prompt
text. Exact prompt cache is useful, but a long-running agent session usually
drifts through related turns rather than repeating the same sentence.

Recommended cache layers:

| Layer | Key | Stores | Why it matters |
|---|---|---|---|
| Exact prompt cache | Prompt fingerprint plus semantic cue hash. | Prior semantic-gate or scout result. | Fast repeat protection, already close to the existing semantic gate cache. |
| Thread ambient cache | `thread_id + workspace + topic_epoch`. | 3-8 current ambient recall cards, active negative contexts, mode, confidence, source-ref fingerprints, query aliases, topic decision, visibility bias. | Makes continuity immediate after the first warming pass in a multi-turn agent session. |
| Topic trajectory cache | Rolling topic hash, without raw prompt text. | Current theme, drift markers, likely next search aliases, visibility bias. | Still intentionally folded into the thread cache for now; split it only if real traces prove the metadata needs its own lifecycle. |
| Clean-source validation pass | Candidate `source_refs` plus prompt/card terms. | Per-card validation status and source-ref fingerprints in the thread cache. | Keeps evidence checks source-backed without adding a second ambient-memory store. |

The exact prompt cache should stay an optimization layer, not a memory surface.
It needs count-only telemetry for hits, misses, expired entries, writes, and
evictions so operators can see whether semantic reuse is actually reducing live
model calls. Value-aware retention may protect source-backed semantic-cue
results from low-value churn, but cached aliases remain routing hints until the
current turn reopens clean source.

Thread ambient cache is a soft working surface, not memory truth. It should be
small, expiring, source-ref-fingerprinted, and safe to discard. It must not log
raw prompt text. When the thread changes topic, the topic epoch should rotate so
old cards stop coloring unrelated work.

After an exact `thread_id + workspace + topic_epoch` miss, the foreground hook
may perform a narrow related-cache lookup over the newest same-thread,
same-workspace entries. This lookup is pattern completion over hashed stable
signals such as source refs, candidate thread keys, semantic trigger ids, scope
labels, card ids, and scout topic labels. Query aliases may be retained as weak
diagnostic evidence, but alias overlap alone must not reuse cards; that would
turn the cache into prompt-text fuzzy matching and weaken the semantic boundary.
Related hits remain advisory until the current turn reopens clean source, so
cached evidence cards should be downgraded to candidate-level guidance rather
than surfaced as fresh source-backed evidence.

Safe to discard does not have to mean wasted. The cache may optionally export
`ambient_residue` rows when a topic epoch rotates, a cache entry expires, or a
caller explicitly wants to keep source-backed unused resonance for future dream
work. Residue is a dream seed, not a dream finding and not formal memory. It
keeps card ids, themes, support levels, source-ref fingerprints, and negative
contexts while still avoiding raw prompt text. Unsourced one-off scent cards
should stay disposable by default.

The desired flow is:

```text
turn N:
  local scent + thread cache lookup
  launch warm scouts if cache is weak or stale
  answer using available cards only

late warm results:
  deterministic validation
  serial cache update
  optional active-recall lock enrichment
  optional residue export for source-backed unused resonance

turn N+1:
  read warmed thread ambient cache
  answer with more natural peripheral awareness
```

This makes high concurrency useful without requiring the current prompt to wait
for the full scout batch. Late results must flow through next-turn cache,
active-recall lock enrichment, or an explicit later pull; they should not
silently revise the current-turn foreground context after the hook has returned.

## High-Concurrency DeepSeek Scouts

DeepSeek-class fast LLM workers are worth using aggressively because their job
is narrow, provisional, and cheap after cache optimization. The warm prototype
now uses 50 structured lanes: 10 functional scout families across 5
candidate-window/query variants.

This is a proposed warm-path evolution, not the current stable hook contract.
Until measured prototypes prove the foreground budget, the operational boundary
in `skills/aippocampus/references/ambient-hooks.md` remains authoritative.

The foreground rule is quorum, not completion. A warm-path caller may launch the
full lane set, but it should only wait for the first useful subset inside the
budget, for example the first 2-3 valid scout results plus privacy/scope guard
if available. Late results should update the thread ambient cache after
deterministic validation. A foreground hook must not require all 50 lanes to
finish before the user prompt can proceed.

The 10 scout families should not be ten copies of the same prompt. They should
cover different recall functions:

| Scout | Purpose |
|---|---|
| Intent & mode classifier (P0) | Decide task mode, visibility bias, collaboration posture, and cognitive load. |
| Privacy & boundary guard (P0) | Suppress credentials, personal/financial/relationship material, professional secrets, and over-personalized associations. |
| Deep theme matcher (P0) | Match long-running philosophical, product, emotional, obsession-level, and trade-off themes. |
| Key-line hunter (P0) | Find memorable lines, visual images, metaphors, strong assertions, and unresolved questions. |
| Evidence & gap sentinel (P0) | Validate source refs and downgrade hallucinated, unsupported, stale, or premise-missing candidates. |
| User style & preference (P1) | Detect source-backed expression habits, language preferences, pacing, and thinking style. |
| Trajectory matcher (P1) | Locate the current turn in project, life, or thread trajectory when sidecars support it. |
| Cross-domain bridge (P1) | Map technical issues to non-technical ideas, and non-technical ideas back to concrete work. |
| Nudge writer (P1) | Draft natural active-gentle-nudge phrasings for the main agent to adapt. |
| Semantic expander (P1) | Generate multilingual, metaphor, and query aliases for cold path and next-turn recall. |

Each family runs across 5 variants: direct prompt, registry window,
clean-source/source-ref window, current prompt trace window, and skeptic window.
This gives sampling depth without losing merge structure.

The runtime prompt keeps the largest shared prefix before the lane split:
`output_budget`, `shared_context`, and `prompt_context` come before
`scout_task`. This is deliberate. In a 50-lane batch, same-case prompt and
trace context is usually the largest reusable prefix; putting the scout task
before it makes every lane diverge too early and tanks cache hit rate. The
stable catalog still sits before prompt text for cross-case reuse, but the
50-lens matrix is not duplicated into every request. Cache-hit ratios remain an
evaluation target; do not document guessed numbers as measured results.
Because DeepSeek persists cache prefix units after completed requests, detached
and evaluation runs should not launch every same-prefix lane cold at the exact
same instant. Use a small prefix-cache warmup wave, then launch the remaining
thin scout suffixes; foreground prompt hooks keep warmup disabled and rely on
the already-written thread cache.

Warm scouts stay quality-first: DeepSeek thinking mode is enabled by default,
and `AIPPOCAMPUS_WARM_RECALL_THINKING=disabled` is only an explicit diagnostic
or ablation setting. Do not couple thinking mode to sampling temperature.
DeepSeek's thinking-mode contract says temperature/top-p style sampling
parameters are not supported there, so the client omits `temperature` when
`thinking=enabled`. JSON stability comes from `response_format=json_object`,
strict parse isolation, output profiles, and deterministic validation rather
than pretending a high temperature is safe.

Each scout returns a small strict JSON object. A malformed result is isolated as
`ok=false`; it must not poison the batch. The parent process owns merging,
validation, dedupe, and any writes.

The full wait-all scout batch belongs to explicit recall, evaluation, or
detached warming. The always-on foreground route should be cache-first,
timeboxed, and fail-open.

DeepSeek scheduling details matter more than raw account limit for this path.
The 50-lane batch is small relative to the documented v4-flash account
concurrency limit, but foreground latency still depends on useful scout
completion. Warm scouts therefore send one stable hashed `user_id` for the
batch, preserving privacy-safe KV-cache/scheduler isolation without embedding
user names, prompts, or paths. Benchmark output should distinguish
`rate_limited_429`, `service_unavailable_503`, and `read_timeout`: 429 asks for
concurrency/backoff tuning, 503 means the provider is currently too busy to read
quality from the run, and read timeout usually means the caller should stay
quorum-first or move wait-all to detached evaluation.

Initial live calibration on `benchmark_corpus/output/sharegpt_coding_multiturn`
showed that low worker caps can underuse Flash rather than protect it: on a
small public-corpus case pack, quorum-first with 5/10 workers at 15s only reached
`available_rate=0.5`, while 50 workers reached `available_rate=1.0` with no
429/read-timeout bucket. A follow-up 6-case run found 20 and 50 workers both
passed at 15s, but 8s under-sampled useful scouts and failed the availability
gate. Treat 15s as the current foreground-style evaluation floor for public
corpus sweeps, and keep the actual foreground hook cache-first/asynchronous so
the user never waits for that wall time.

Large case packs need two separate concurrency dials. `--max-workers` controls
the 50 scout lanes inside one case; `--case-workers` controls how many cases run
at once. Do not treat `case_workers=50` as the natural companion to
`max_workers=50`: that would create up to 2500 simultaneous provider calls.
Use `--case-offset`, `--case-limit`, and `--progress-jsonl` / `--progress-dir`
for sharded long runs so interrupted calibration still leaves sanitized
per-case evidence.

The cache optimization path now has two separate controls:
`--prefix-cache-warmup-scouts` controls how many initial same-prefix scout lanes
complete before the rest of the batch launches, and
`--prefix-cache-warmup-delay` can add a small detached/evaluation pause after
that warmup. Detached warm jobs default to a tiny warmup wave; foreground-style
direct calls default to zero warmup so user-visible latency stays cache-first
and fail-open.

Do not make `max_tokens` the primary tuning lever. It remains `None` by default
so Flash can return complete compact JSON; only test token caps as an explicit
diagnostic after source validation, case pass rate, invalid JSON, and false
evidence remain stable. If live output costs spike, first inspect
`completion_tokens_details.reasoning_tokens`, the request `thinking` mode,
`completion_tokens_by_family`, and per-family prompt-cache hit/miss tokens
before changing worker count or truncating model answers.
`AIPPOCAMPUS_WARM_RECALL_MAX_WORKERS` can cap live worker count for shared
accounts or pro-model experiments without changing the 50-lane taxonomy.

## Source-Backed Merge

Model output is never memory truth.

The deterministic merger should:

- require source refs before a candidate can become evidence
- dereference source refs against clean-source messages when a registry path is
  available; cards with concrete refs that are missing locally or unsupported
  are dropped so lower-ranked supported cards can surface instead
- use sanitized prior prompt-trace refs as a deterministic fallback only when
  they overlap the current prompt and still pass the same local source
  validation; never use the current prompt itself as memory
- distinguish `scent`, `candidate`, and `evidence`
- suppress current-thread-only echoes by default unless the caller explicitly
  allows recent-thread recall
- weight user turns and assistant final answers above commentary and tool text
- penalize injected skill instructions, generic project boilerplate, and noisy
  status updates
- dedupe candidates by theme, source thread, and key line, then merge
  near-duplicate themes by significant terms before the final card cap
- let `privacy_boundary_guard` and `evidence_gap_sentinel` block by scout family even
  when the running lane has a `family:variant` suffix
- preserve uncertainty instead of forcing a match

The merger produces recall cards, not formal memory. Formal memory still uses
the existing retain/review paths.

## Private Context Contract

The main agent should receive a compact private block:

```yaml
ambient_recall:
  mode: active_gentle_nudge
  confidence: high
  cards:
    - theme: "new thread continuity"
      provenance_class: cached_warm_card
      cached_origin: warm_scout_proposal
      nudge: "This is close to the fear that a new window can inherit rules but lose the road that made them matter."
      key_line: "知识可以打包，那个瞬间打包不了。"
      source_refs: ["..."]
      visibility: active_gentle_nudge
      source_reopen_required: true
      reopenable_ref_count: 1
      cache_status:
        status: hit
        topic_epoch: epoch_...
      expand_if: "User asks whether AIppocampus solves this grief."
  avoid:
    - "Do not claim innate memory."
    - "Do not expose source ids unless the user asks or grounding is needed."
```

The agent then writes naturally. It may ignore the card when the current task
would be better served without it. `provenance_class` tells the agent whether a
card came from deterministic cues, warm scouts, cache replay, cognitive-map
wayfinding, working memory, or a source-backed reopen path. It does not replace
`support_level`, `visibility`, or local source validation.

## Active Gentle Nudge Style

Good nudges are short, situated, and non-performative.

Examples:

- "这其实碰到了你之前一直在摸的那条线：变化之后，连续性还在不在。"
- "我会沿着那个『规则能迁移，但路会不会走失』的问题来答。"
- "这让我想到你对新线程的担心：不是怕功能丢了，是怕共同走出来的意义丢了。"

Bad nudges sound like database output:

- "I retrieved a memory from session..."
- "You previously stated..."
- "Based on your profile..."

Source ids belong in the agent's private context or in explicit recall answers,
not in ordinary conversation.

## Concurrency And Cache Design

High concurrency is safe only if writes and visibility are controlled.

Design constraints:

- Run scouts concurrently, write serially.
- Cache exact prompt results by prompt fingerprint plus semantic cue hash, not
  raw prompt text.
- Keep exact-cache and cue-cache diagnostics count-only: cache keys, telemetry
  counters, value classes, and source-backed buckets are acceptable; raw prompt
  text, cue text, source snippets, and local paths are not.
- Prefer value-aware eviction for high-confidence source-backed semantic-cue
  results over pure recency when low-value prompt churn would otherwise evict
  them.
- Cache thread-level ambient cards by `thread_id + workspace + topic_epoch`.
- Cache candidate cards with expiry and source-ref fingerprints.
- Rotate topic epochs from scout output, not hard-coded prompt rules. Scouts
  vote `reuse`, `rotate`, or `suppress` with a short topic label; the parent
  hashes that label and never stores raw prompt text.
- Keep provider output provisional until deterministic validation accepts it.
- Keep foreground hook output small: no raw prompt logs, no source dumps, no
  long explanations.
- Use stale-but-safe cached cards rather than blocking the user for fresh
  DeepSeek output.
- Record latency, thread-cache hit rate, prompt-cache hit rate, scout failure
  rate, late-result usefulness, and visibility decisions.

The cache should make common themes feel immediate after a thread has warmed up.
DeepSeek concurrency should improve recall diversity and freshness without
becoming a wait-all critical path for every prompt.

## Failure Modes

| Risk | Mitigation |
|---|---|
| Over-personalization | Use visibility levels, scope guard, and quiet mode for routine technical tasks. |
| False familiarity | Require source refs for evidence and phrase nudges as resonance, not certainty. |
| Current-thread echo | Penalize current-thread-only hits unless the user asks about recent context. |
| Latency creep | Hot path returns first; warm path has strict timeout; cold path precomputes. |
| Model hallucinated refs | Deterministic source-ref validation before any card becomes evidence. |
| Privacy leakage | Foreground scent hides exact refs unless needed; raw rollout remains audit-only. |
| Scout collapse | Isolate malformed scout outputs and let successful scouts continue. |
| Stale thread cache | Rotate topic epochs, expire cards, and require negative contexts for routine coding or unrelated work. |

## First Implementable Slice

Status: implementation slice landed and calibrated. Card/cache first, the
50-lane warm prototype, detached warm jobs, residue export, source-ref
validation, current-thread echo suppression, topic-epoch voting, and labeled
benchmark calibration are all in place. The runtime boundary is intentionally
narrow: foreground hook decisions stay cache-first, while the 50-lane batch
runs only in explicit warm CLI/evaluation paths or detached jobs. The installed
foreground path now default-enqueues detached warming after non-skip cache
misses when a thread id and `DEEPSEEK_API_KEY` are available; explicit opt-out
remains available for shared machines and budget debugging. Detached jobs have
their own default timeout (`AIPPOCAMPUS_DETACHED_WARM_TIMEOUT`, 45s) so the
runtime loop does not inherit the short standalone foreground-style warm
timeout. Keep 15s as the foreground-style quorum-first evaluation floor; for
detached wait-all jobs, use 45s by default because they do not block the user
and should not sit on the read-timeout boundary.

The first slice should stay small but real:

1. Add `ambient_recall_cards.py` to define and validate compact private recall
   cards. Done for the first runtime shape.
2. Add `ambient_thread_cache.py` keyed by `thread_id + workspace + topic_epoch`,
   with read, write, expiry, and drift-rotation helpers. Done for the first
   local JSON cache; it stores hashed thread/workspace identities and no raw
   prompt text.
3. Read only registry metadata, semantic scope labels, timeline sidecars,
   cognitive-map sidecars, and clean-source index snippets.
4. Run local hot-path candidate lookup first, then consume the thread ambient
   cache. Done for foreground cache reads/writes; default background enqueueing
   now schedules detached warm work only after a non-skip foreground decision
   and a weak/missing cache. Use `--no-warm-background` or
   `AIPPOCAMPUS_WARM_RECALL_BACKGROUND=0|false|off` to turn this off without
   changing the runtime contract.
5. Add `warm_ambient_recall.py` as a standalone warm-path prototype. Done for
   the current shape: it defines the 5 P0 + 5 P1 scout taxonomy above across 5
   variants, gives each lane a family/variant `lens_task`, serializes shared
   context before the lane suffix for prefix-cache friendliness, runs the
   resulting 50 lanes concurrently, isolates malformed outputs, and returns on
   quorum inside a strict timeout. It fails open when no API key is available.
6. Merge into at most 3 private recall cards and serialize useful results back
   into the thread cache. Done for quorum-gated writes, source-ref validation,
   current-thread echo suppression, guard-family blocking, similar-theme merge,
   validation metadata, query aliases, topic decision, visibility bias, and a
   prior-trace fallback for supported source-ref misses. Privacy guard remains
   a hard visibility veto; evidence sentinels veto model-generated cards but do
   not suppress prompt-trace fallback cards that pass local source validation.
   Strong continuation cues such as "continue where you left off", "instead",
   and "format you did above" can use the immediately prior source-backed trace
   even when lexical overlap is thin. Generic overlap terms such as
   "model/error/use" are filtered so source-ref calibration does not reward
   citing an unrelated old error. Explicit `--wait-all` is reserved for
   evaluation or detached warming, not the foreground hook.
7. Reuse optional residue export for source-ref-fingerprinted warm cards so
   unused resonance can become dream-task seed material without logging raw
   prompt text.
8. Use `benchmarks/aippocampus/benchmark_warm_ambient_recall.py` for sanitized
   calibration. Deterministic mode now uses 13 built-in cases and quality gates
   for available rate, observed scout result rate, expectation pass rate, error
   rate, false evidence, and missing-source-ref visibility; `--cases-file` can
   add larger sanitized JSON/JSONL prompt-trace suites. Real-trace calibration
   can now start from `benchmarks/aippocampus/build_warm_ambient_trace_cases.py`,
   which exports private cases from registered clean source or an explicit
   clean-source `messages.jsonl` such as `benchmark_corpus/output/...`, while
   skipping redacted prompts by default. For corpus sweeps, pair
   `--clean-source-dir` or `--clean-source-messages` with `--subset-messages-out`
   and `--registry-out`; the subset registry lets source-ref validation deref
   sampled public-corpus lines without exposing the full generated corpus.
   Use `--min-turn-index 2` for trace calibration so sampled prompts include
   real prior user/assistant context instead of mostly first-turn questions.
   `--label-template` adds empty manual labels for source-ref validation status
   counts, current-thread echo bounds, and allowed topic-epoch actions. For the
   automated 100-case labeled pack, build separate views with
   `--label-policy source_ref_supported`, `--label-policy echo_guard`, and
   `--label-policy topic_epoch_vote`; keep `topic_epoch_heuristic` as a review
   aid only. Source-ref calibration requires supported evidence only when the
   trace has a strong continuation cue or meaningful prior overlap; generic
   capability questions and prompts pointing at freshly pasted current text
   should not be forced to cite memory. Prior trace rows containing redaction
   placeholders are also excluded from source-ref support labels so privacy
   guard suppression does not become a benchmark failure. Echo calibration is
   narrower and expects
   `current_thread_echo_count >= 1` only for short, strong continuation turns;
   long pasted-document prompts, generic topic overlap, and current-object
   prompts like "this code" should not be forced to manufacture current-text
   echoes. The metric counts suppressed current-thread echo attempts, not
   leaked cards.
   Topic epoch rotation remains an LLM judgment: the automated gate requires an
   explicit `reuse|rotate|suppress` vote, not agreement with a local lexical
   heuristic. Run topic-vote packs with `--min-available-rate 0`, because a
   valid `suppress` vote may intentionally leave no visible card. The benchmark
   runner treats labels as per-case expectation failures without emitting raw
   prompts or cards. Live mode may call the configured DeepSeek-compatible
   model but emits only hashes, aggregate metrics, validation status counts,
   error-kind buckets, and cache metrics.
   For source-ref packs, `false_evidence_count == 0` is the hard safety gate;
   `case_pass_rate` is recall coverage and may be tuned separately because a
   safe miss is better than an unsupported citation. The benchmark reports
   `trace_fallback_card_count` so live sweeps can distinguish model recall from
   deterministic prior-trace fallback coverage.
   `benchmark_warm_ambient_sweep.py` now compares quorum-first vs. wait-all,
   worker caps, and timeout values over the same private case pack, ranking
   quality gates and source health before latency. Its sanitized `analysis`
   block gives foreground/detached recommendations plus gate failures, scout
   error buckets, and source-ref pressure so a wide run can directly inform the
   next tuning pass. Sweep defaults now keep `max_tokens=None` and use 50
   workers to match the 10x5 Flash lane design; lower worker lists are explicit
   rate-limit diagnostics, not the quality baseline. Strict labeled evaluation
   should read the three focused packs separately: source-ref support for
   evidence grounding, echo-guard activation for current-thread suppression,
   and topic-epoch vote presence for drift handling.
   2026-05-28 live 100-case calibration with `max_workers=50`,
   `case_workers=2`, wait-all, and prefix warmup showed the current quality
   shape: source-ref had `false_evidence_count=0` and raw `case_pass_rate=0.84`;
   after tightening the labels to 54 true source-required cases, the same run
   rescored to 0.90 with 10 real safe misses. Echo labels tightened to 22 true
   echo-required cases; combined first-10 plus offset-90 live results rescored
   to 0.98 with 2 real misses and `current_thread_echo_count=418`. Topic-vote
   passed 100/100 with actions `suppress=79`, `rotate=17`, `reuse=4`.
   Prompt-cache hit rate was roughly 0.83-0.85 under this outer concurrency.
   This calibration is sufficient for the implementation slice; do not rerun
   the same packs unless runtime behavior, prompt layout, model settings, or
   label policy changes.
   The 2026-05-28 calibration was not a token smoke test: the provider
   dashboard showed 36,899 API requests that day across repeated 100-case
   source-ref, echo, topic-epoch, timeout, worker, and ablation runs. Treat
   those results as the completed calibration record for this implementation
   slice, not as a reason to spend another full-day sweep re-confirming the
   same product boundary.
   Follow-up targeted live calibration after the evidence-blocker/fallback
   adjustment cleared the known miss cluster: source-ref target pack passed
   11/11 with `false_evidence_count=0`, `scout_error_rate=0`, and
   `prompt_cache_hit_rate=0.8489`; echo target pack passed 3/3 with
   `false_evidence_count=0` and `prompt_cache_hit_rate=0.8285`.
   A rebuilt source-ref 100-case pack based on the sanitized prompt traces
   narrowed source-required cases to 43. With `case_workers=2`,
   `max_workers=50`, wait-all, and `timeout=30`, the full 100-case run reached
   `case_pass_rate=1.0` and `false_evidence_count=0`; the only failed gate was
   `scout_error_rate=0.0522`, mostly read timeouts, with
   `prompt_cache_hit_rate=0.8412`. A `timeout=45` early-stop check over 34
   cases kept `case_pass_rate=1.0`, reduced scout errors to 0.0076, and kept
   prompt-cache hit rate at 0.8444. Treat this as evidence that 30 seconds is
   tight for wait-all evaluation; it is not a reason to shrink the 50-lane
   design or reintroduce `max_tokens` truncation.
9. Source-ref validation, current-thread echo suppression, LLM-directed topic
   epoch rotation, and detached late-result cache warming are now implemented.
   Deep archival recall now has a source-backed visibility mode for original
   wording/detail requests. The foreground enqueue path now passes the current
   `session:<id>` source-ref key and a sanitized current-prompt trace into the
   detached warm job, so background scouts can apply echo and topic-drift
   judgments against real thread context. This enqueue path is now default-on
   when the hook has the required runtime inputs, while foreground behavior
   stays cache-first and fail-open. Prompt-hook cache hits now keep warmed cards
   ahead of fresh local hints and expose sanitized cache metadata for debugging.
   Learned semantic cues also act as a foreground reuse gate: once a cue has
   repeated source-backed hits, neighboring paraphrases use the local
   semantic-cue path and skip a cold live semantic call unless an operator
   explicitly forces `semantic_gate=on` for calibration. Hook diagnostics report
   `exact_cache_hit`, `semantic_cue_hit`, and `cold_model_call` separately, and
   exact-cache reports now expose sanitized hit/miss/expired/write/eviction
   counters without prompt or cue text.
   Further work should be driven by new regressions or product behavior gaps,
   not by repeating the completed calibration suite.

Success for slice one is not perfect recall. It is that the agent receives
useful, source-backed peripheral awareness without making the user wait, and
that a multi-turn agent thread becomes warmer after the first few turns instead
of re-solving recall from scratch every time.

## Product Promise

AIppocampus should not merely remember when asked.

It should let old traces glow at the right moment, lightly enough that the
conversation keeps moving, and faithfully enough that the user no longer has to
carry the whole past alone.
