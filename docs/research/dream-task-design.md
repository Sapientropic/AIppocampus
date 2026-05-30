# Dream Task Design: From Jung's Dream Theory to Subconscious Consolidation

Status: research memo with deterministic Phase 1 compensatory output, a Phase 2
source-pack/adjudication substrate, a selected real-history Phase 3 structural
eval, bounded model-backed compensatory/amplification/prospective worker paths,
an active-imagination sandbox, and a retrospective prospective-validation
harness covered by mocked tests; awaiting live smoke, cross-model validation,
and measured user-visible recall/reflection impact.
Anthropic Managed Agents Dreams are confirmed as an adjacent official Research
Preview, but this memo's Jung-inspired dream tasks are an AIppocampus-specific
design proposal.
Origin: conversation between user and Claude Code, 2026-05-27.
Implemented slices: `skills/aippocampus/scripts/compensatory_dream.py` emits
adjudication-only compensatory candidates from source-backed single-thread
extraction rows; `skills/aippocampus/scripts/dream_input_pack.py` builds
cross-thread source packs from question links, Journey rows, and ambient
residue; `skills/aippocampus/scripts/dream_working_memory.py` provides the
background adjudication guard before dream hypotheses can feed working memory;
`skills/aippocampus/scripts/dream_worker.py` runs bounded model-backed
compensatory/amplification/prospective workers plus active-imagination sandbox
candidates over ready packs and validates prospective hypotheses
retrospectively against explicit later evidence; and
`skills/aippocampus/scripts/dream_real_history_eval.py` runs selected
real-history structural and user-visible ablation evals against plain
question/frontier/Journey/working-memory surfaces with deterministic fallback
or optional model-backed workers.
Related: [affect-side-channel.md](affect-side-channel.md),
[compact-activation-signals.md](compact-activation-signals.md),
[correction-reconsolidation.md](correction-reconsolidation.md).

## TL;DR

AIppocampus's subconscious jobs currently extract structure from conversation
threads — questions, concepts, frontier markers, themes. But extraction is only
half of what a good subconscious does. Jung's dream theory provides the missing
half: **compensatory analysis** (what the thread is missing), **prospective
analysis** (what's about to emerge), **amplification** (cross-thread resonance),
and **active imagination** (creative insight beyond the source).

The design goal: AIppocampus should not just help the agent remember the
journey. It should help the agent **stay on the journey with the user** —
sensing when they're lost, when something is trying to emerge, when a pattern
across threads is calling for attention.

## The Problem: Extraction ≠ Integration

Current subconscious jobs are **extractive**:

```
clean source → question extraction → question candidates
clean source → concept edge mining → concept graph
clean source → frontier markers → knowledge boundaries
clean source → theme emergence → recurring patterns
```

These produce structured metadata. They answer: "What is in this thread?"

They do NOT answer:
- "What is this thread **avoiding**?"
- "What is **about to become important**?"
- "What does this thread **resonate with** across the user's other conversations?"
- "What **creative insight** could emerge from connecting threads that haven't been connected?"

A human psychotherapist doesn't just extract facts from a session. They notice
what the client **isn't** saying, what themes are **building** toward something,
what echoes across sessions. This is the integration function that extraction
alone cannot provide.

## Why Jung, Not Freud or Cognitive Science

Three major dream theories, evaluated for AIppocampus dream task design:

| Theory | Core claim | Strengths | Weaknesses |
|--------|-----------|-----------|------------|
| Freud | Dreams are disguised wish fulfillment | Recognizes hidden content | Too reductive — everything maps to wish/want |
| Jung | Dreams serve compensatory, prospective, and creative functions | Multi-functional, non-reductive, honors emergence | Less precisely testable |
| Cognitive science | Dreams consolidate memory via replay and synaptic strengthening | Mechanistically grounded | Too mechanistic — no creative or compensatory dimension |

Jung wins for our purposes because:

1. **Compensation**: The dream balances one-sided conscious attitudes. Directly
   maps to "what is the thread/conversation missing?"
2. **Prospective function**: The dream anticipates future development. Maps to
   "what pattern is building toward emergence?"
3. **Non-reductive**: Jung explicitly rejected "all dreams are X" formulas. A
   dream task should not reduce every thread to a single pattern.
4. **Creative**: Dreams produce new combinations, not just replays. A dream task
   should be allowed to generate insights not present in the source text.

Freud's wish-fulfillment model would turn every dream task into "what does the
user want?" — too narrow. Cognitive science's consolidation model would turn it
into "replay and strengthen existing patterns" — too mechanical. Jung's model
asks the right questions: what's missing, what's coming, what connects?

## Jung's Four Functions, Mapped to AIppocampus

### 1. Compensatory Function (补偿性)

**Jung**: Dreams balance one-sided conscious attitudes. If you're overly
rational, your dreams are emotional. If you're avoiding something, your dreams
present it.

**AIppocampus mapping**: The dream task identifies what a thread or conversation
is systematically NOT addressing.

Possible outputs:
- **Blind spot markers**: Topics adjacent to the thread's focus that never
  appeared, but probably should have. Not "missing information" (that's
  extraction), but "avoided perspectives."
- **Approach bias flags**: When a thread has been approaching a problem from
  only one angle, the compensatory output names the unexplored angles.
- **Emotional balance notes**: When a thread is purely technical and the user's
  history suggests they process emotionally, the compensatory note marks this as
  a potential frustration signal.

**Example**: A thread about optimizing database queries that never mentions the
user's recurring concern about "building things that matter." The compensatory
dream output: "Technical thread, no connection to recurring values/motivation
theme. User may be in 'grind mode' — risk of disengagement."

### 2. Prospective Function (前瞻性)

**Jung**: Dreams don't just process the past; they anticipate future
development. They sketch possibilities before they arrive.

**AIppocampus mapping**: The dream task identifies patterns that are **building
toward something** but haven't crystallized yet.

Possible outputs:
- **Emergence signals**: Recurring fragments across threads that suggest a new
  theme is forming — before any single thread names it explicitly.
- **Trajectory hints**: Based on the arc of recent threads, what the user might
  need or ask next. Not prediction, but "if this trajectory continues..."
- **Pre-articulation markers**: Concepts the user seems to be circling around
  without naming. The dream task can name them before the user does.

**Example**: User has had three threads touching on "memory," "identity," and
"continuity" in different contexts. No single thread connects them. The
prospective dream output: "Memory/identity/continuity cluster forming. Possible
emergent theme: what makes a self persistent across contexts?"

### 3. Amplification (放大法)

**Jung**: Dream symbols are amplified by connecting them to cultural, mythological,
and archetypal parallels — not reduced to a single meaning, but expanded.

**AIppocampus mapping**: The dream task connects thread patterns to the user's
**broader conversation history** and identifies cross-thread resonance.

Possible outputs:
- **Cross-thread resonance**: This thread's pattern mirrors what happened in an
  unrelated thread 2 months ago. Same structure, different domain.
- **Archetypal pattern markers**: Not "the user is on a Hero's Journey," but
  "this thread has the same structure as the previous 3 breakthrough threads:
  frustration → reframing → unexpected connection."
- **Theme deepening**: An existing theme (from theme emergence) has a new facet
  that wasn't visible from any single thread.

**Example**: A thread about debugging a UI bug resonates with a thread from
months ago about debugging a relationship pattern. Same structure: surface
symptom → assumed cause → wrong fix → deeper cause → real fix. Amplification
output: "Debugging pattern (surface→assumption→wrong fix→deeper cause→real
fix) recurring across technical and personal domains. Possible meta-pattern:
user's problem-solving style."

### 4. Active Imagination (积极想象)

**Jung**: Rather than interpreting dreams passively, engage in dialogue with
unconscious content. Let it speak back.

**AIppocampus mapping**: The dream task is allowed to produce **creative
insights not present in the source text** — to synthesize across threads and
generate something new.

Possible outputs:
- **Synthesis hypotheses**: "If theme A from thread X and theme B from thread Y
  are both active, the user might be heading toward Z."
- **Bridge concepts**: Concepts that connect two previously separate threads,
  generated by the dream task rather than extracted from either thread.
- **Questions the user hasn't asked yet**: Based on the trajectory of their
  inquiry, what question would be the natural next step?

This is the most experimental function. It risks hallucination (the model
generating plausible but ungrounded connections). Mitigation: every active
imagination output must carry `source_refs` pointing to the threads that
inspired it, and must be flagged as dream-synthesized, not source-extracted.
The implemented sandbox tightens this further: active-imagination candidates
must cite at least two independent source anchors, explain
`why_this_is_not_fact`, include `counter_evidence`, and keep
`foreground_eligible=false` / `formal_memory_eligible=false`. Sensitive
personal interpretations, durable profile/preference claims, and direct
user-facing assertions stay parked even when they cite source handles.

## Relationship to Existing Architecture

```
┌─────────────────────────────────────────────────────────────┐
│ EXTRACTIVE tasks (existing)                                  │
│                                                              │
│ question_extraction → question candidates                    │
│ concept_edge_mining → concept graph                          │
│ frontier_markers → knowledge boundaries                      │
│ theme_emergence → recurring patterns                         │
│                                                              │
│ Answers: "What IS in this thread?"                           │
│ Mode: deterministic → semantic (gated)                       │
│ Output: structured metadata with source_refs                 │
└─────────────────────────────────────────────────────────────┘
                    ↕ complementary
┌─────────────────────────────────────────────────────────────┐
│ INTEGRATIVE tasks (dream, proposed)                          │
│                                                              │
│ compensatory_analysis → blind spots, approach biases         │
│ prospective_analysis → emergence signals, trajectory hints   │
│ amplification → cross-thread resonance, archetypal patterns  │
│ active_imagination → synthesis hypotheses, bridge concepts   │
│                                                              │
│ Answers: "What is MISSING, COMING, or CONNECTING?"           │
│ Mode: semantic (model-dependent), always flagged as dream    │
│ Output: annotated insights with source_refs + dream flag     │
└─────────────────────────────────────────────────────────────┘
```

Extractive tasks are deterministic-first (rules + semantic gates).
Integrative tasks are semantic-first (require model reasoning) and must always
be clearly flagged as dream output, not source-grounded fact.

### Implemented Phase 1 Contract

The first implemented slice is intentionally narrower than the full dream
design. `skills/aippocampus/scripts/compensatory_dream.py` is a deterministic
Phase 1 helper with this concrete contract:

- Input: source-backed extraction rows for a single `thread_key`. Rows may come
  from question/frontier/concept extraction, but they must carry thread-scoped
  `source_refs` or they are ignored. In the live `question_extraction` path,
  canonical `scope_labels` / `semantic_scope_labels` from the selected
  timeline source refs are preserved into validated findings so life-wide
  dream branches are not starved by validator field loss.
- Output: adjudication-only `finding_kind="dream_synthesized"` candidates with
  `dream_function="compensatory"`, `support_level="candidate"`,
  `review_state="needs_review"`, and `foreground_eligible=false`.
- Filtering: unsourced rows, rows whose refs belong to another thread, and
  existing dream rows are discarded before synthesis.
- Audit boundary: every bridge claim carries `source_refs`; source-ref
  resolution is structural unless a later registry/clean-source index is
  supplied.
- Write boundary: Phase 1 writes no clean-source or formal-memory updates. The
  default trigger policy is lower-frequency than extraction
  (`run_after_extraction_passes=3`) and not allowed in foreground hooks. A
  separate post-adjudication projection can turn `agent_adjudicated`,
  `auto_adjudicated`, `source_adjudicated`, or compatible accepted states into
  existing `working_memory` rows for recall/ambient/reflection use. This is not
  a default user approval loop; raw candidates stay in the holding queue until a
  background worker or operator adjudicates them.

The executable contract lives in
`tests/aippocampus/test_compensatory_dream.py`. Keep changes to this schema
paired with that test file and the runtime map in `docs/architecture/runtime-script-map.md`.

### Implemented Phase 2 Source-Pack Contract

The second implemented slice is still infrastructure, not a full dream worker.
`skills/aippocampus/scripts/dream_input_pack.py` creates a deterministic
`kind="aippocampus_dream_input_pack"` object from existing source-backed
navigation artifacts:

- `question_link` rows from `question_tracking.py`
- `aippocampus_journey` rows from `journey_tracking.py`
- `aippocampus_ambient_residue` rows from `ambient_thread_cache.py`
- `concept_edge` rows from subconscious concept extraction
- source-backed `theme_candidate` rows from warm/ambient recall scouts
- correction activation/outcome/adjudication rows from
  `correction_reconsolidation.py`
- reflection feedback/adjustment rows from `reflection_space.py`
- agency/coding tickets and decision events when they carry clean source refs

The pack only becomes `status="ready_for_dream_worker"` when it has clean
source refs from at least two distinct source threads. Ambient residue is
allowed to add themes, weak `source_ref_fingerprints`, and negative contexts.
Theme candidates with only fingerprints follow the same weak-context rule.
Weak handles can enrich a pack, but they cannot make a clean source pack by
themselves. Each seed is also summarized in `source_contributions` so later
workers can explain which inputs supplied clean anchors and which supplied weak
context. The ready pack may advertise
`eligible_dream_functions=["compensatory", "amplification"]`; this only means
the source substrate is fit for those background workers, not that amplification
output quality has been proven.

The pack stays out of foreground hooks and formal memory:

- `foreground_eligible=false`
- `formal_memory_eligible=false`
- `clean_source_mutation=false`
- `truth_boundary="dream_input_pack_seed_not_fact"`

Background adjudication lives in `dream_working_memory.py` as structural guard
code, not a user approval ritual. `background_adjudicate_dream_finding()` only
sets `review_state="agent_adjudicated"` when the finding is a dream-synthesized
candidate, carries source refs, passes its source-ref audit, has source refs on
every bridge claim, meets the confidence floor, and, when a P2 pack is supplied,
overlaps that pack's clean source refs. Parked findings remain
`review_state="needs_review"` and do not project to working memory. The working
memory projection also refuses forced adjudicated rows whose bridge claims lack
source refs.

The executable contract lives in
`tests/aippocampus/test_dream_input_pack.py`. The CLI defaults to a public
summary (`kind="aippocampus_dream_input_pack_summary"`) that reports aggregate
readiness and source-count diagnostics without raw `source_refs`, message ids,
thread ids, questions, or frontier text. Full internal packs require
`--internal-full` and are not suitable for public logs, docs, or issue comments.

### Implemented Phase 2.5 Queue Lifecycle

`skills/aippocampus/scripts/dream_queue.py` is the deterministic handoff layer
between ready packs and future detached dream workers. It does not call a model
or promote dream output. It creates `kind="aippocampus_dream_queue_item"` rows
only for `status="ready_for_dream_worker"` packs, one bounded item per eligible
dream function.

Queue items carry lifecycle and cost metadata:

- `pack_id`, `dream_function`, `trigger_family`, `priority`, and `dedup_key`
- `review_after` and `expires_at`
- `cost_budget` with one model call / one sample per item by default
- `execution_mode="detached_background"`
- `foreground_eligible=false` and `live_model_allowed_in_foreground=false`
- `cache_contract="deepseek_prefix_v1"` with stable
  `prompt_order=["stable_dream_worker_contract", "source_pack_payload",
  "variable_run_directive"]`

Default trigger frequency is low-frequency background work: ready source packs,
topic-epoch residue, correction/outcome events, Journey frontier changes,
explicit operator requests, and periodic maintenance may enqueue items, but
dream work must not run after every extraction and must not run in foreground
hooks. Human/operator intervention is reserved for explicit requests and
sensitive review; ordinary accepted/parked decisions use background
adjudication.

The queue also keeps dream work from regenerating the same hypothesis by
suppressing items whose `dedup_key` already appears in active previous queue
state or adjudicated dream findings. Expired queued items and parked findings
are reported as aggregate diagnostics. Public summaries report counts and
trigger-family totals only, not raw source refs, message ids, or thread ids.

The executable contract lives in `tests/aippocampus/test_dream_queue.py`.

### Implemented Phase 3 Structural Eval

`skills/aippocampus/scripts/dream_real_history_eval.py` is the first selected
real-history evaluation loop. It is intentionally not a private-history dream
quality benchmark. It does three narrow things:

- Selects source-backed cross-thread resonance packs from currently
  materialized `question_candidate`, `frontier_marker`, `question_link`, and
  `aippocampus_working_memory` rows.
- Runs a tiny deterministic worker that emits one compensatory and one
  amplification candidate per ready pack, then sends them through the background
  adjudication guard.
- Compares plain source rows against the augmented surface that includes
  adjudicated `candidate_type="dream_hypothesis"` working-memory rows.

The first metric layer is structural lift, not user-visible usefulness:

- prompt hit-rate delta
- source-thread coverage delta
- reflection-ready row delta
- bridge-claim coverage delta

The runner returns `claim_level="selected_real_history_structural_eval"` and
`private_text_emitted=false`. Public/sanitized output omits raw source text,
raw source refs, and source thread ids; it keeps aggregate counts, selected
resonance terms, seed kinds, and claim boundaries. A 2026-05-30 local smoke over
the current registry observed 697 subconscious job rows, 63 working-memory rows,
4 selected packs, 8 adjudicated dream working-memory rows, unchanged prompt hit
rate at 1.0, `source_thread_coverage_delta=2.5`,
`reflection_ready_delta=64`, and `bridge_claim_coverage_delta=1.0`.

This can claim that the pipeline can select real-history packs and measure the
structural substrate added by dream hypotheses. It still cannot claim live model
behavioral lift, private real-history dream quality, user-visible reflection
value, full-history coverage, or clean-source factual resolution without
reopening source.

The #131 visibility-ablation harness adds a second, still conservative layer:
`metrics.user_visible` reports recall lift, reflection lift, unsupported
strong-claim suppression, source-support correctness, manual source-review
coverage, and cost/cache behavior separately. This distinguishes "the substrate
has more bridge structure" from "a visible answer would improve." The harness
can ingest selected manual source-review rows, but when no reviewed sample is
provided it explicitly lists `manual_source_review_support` and
`real_user_behavior` under `cannot_claim`. Public output remains sanitized and
does not include raw source refs, message ids, thread ids, local paths, or
private text.

### Implemented Phase 3.5 Bounded Model-Backed Workers

`skills/aippocampus/scripts/dream_worker.py` adds the first bounded
model-backed path for `dream_function="compensatory"` and
`dream_function="amplification"` over `status="ready_for_dream_worker"` packs,
then extends the same contract to `dream_function="prospective"` and a
high-risk `dream_function="active_imagination"` sandbox. The selected source
pack remains the source boundary: the worker prompt exposes sanitized pack
metadata plus a `source_ref_inventory`, and model outputs must cite those
source-ref ids before they can become `finding_kind="dream_synthesized"`
candidates.

The worker keeps the Phase 1/Phase 3 deterministic paths as fallback. In
`dream_real_history_eval.py`, `run_pack_dream_worker()` only uses the
model-backed path when a `model_client.ChatClientConfig` is supplied; otherwise
the deterministic compensatory/amplification fixture remains the conservative
baseline.

The model-backed worker is bounded by design:

- prompt order is always `stable_dream_worker_contract`, then
  `source_pack_payload`, then `variable_run_directive`
- DeepSeek-flavored configs must use `cache_contract="deepseek_prefix_v1"`
- `max_samples` limits accepted candidate shaping per dream function
- `no_write=True` is the default, so accepted candidates do not project to
  working memory unless the caller explicitly asks for projection
- malformed candidates, unsupported candidate kinds, missing source refs,
  bridge claims without source refs, and overconfident dream claims are rejected
  or parked by `background_adjudicate_dream_findings()`
- prospective candidates carry `emergence_signal`, `trajectory_hint`,
  `counter_evidence`, `review_after`, `expires_at`, and
  `language_boundary="hypothesis_not_prediction"`
- retrospective prospective validation reports `supported`, `refuted`,
  `stale`, and `unknown` buckets, but only when later evidence explicitly
  targets the finding id and carries source refs; similar terms alone do not
  count as support
- active-imagination sandbox candidates carry `sandbox_boundary`, require
  `why_this_is_not_fact` and `counter_evidence`, require two independent source
  anchors, and park sensitive/profile-style interpretations even when
  source-backed
- public summaries report aggregate counts, provider usage, and cache metrics
  without source refs, message ids, thread ids, or private text

This can claim mocked evidence for the runtime contract: all four worker functions
preserve prompt ordering, pass DeepSeek cache usage through sanitized telemetry,
route every candidate through background adjudication, and keep prospective
language framed as possibility rather than prediction. It still cannot claim
private real-history dream quality, live provider quality, predictive validity,
active-imagination usefulness, or user-visible recall/reflection lift until
selected real-history smokes and human/source review exist.

### Live Dream Worker DeepSeek KV Cache Contract

The default P1-P3 fallback remains deterministic, so it must not claim provider
cache hits. The model-backed worker path must use the shared
`model_client.ChatClientConfig(cache_contract="deepseek_prefix_v1")` path before
it can call DeepSeek. This is a runtime contract, not an optional optimization.

DeepSeek's KV cache is server-side and automatic, but the official guide says
requests only hit when later prompts fully match previously landed cache-prefix
units; it also exposes `usage.prompt_cache_hit_tokens` and
`usage.prompt_cache_miss_tokens` for verification. Therefore live dream prompts
must preserve this order:

- stable dream worker contract first: role, function, truth boundary, output
  schema, tool/source rules, and the exact dream function definitions
- source pack payload next: selected source-pack metadata, sanitized source-ref
  summaries, pack audit, and already adjudicated context
- variable run directive last: current objective, sample/diversity instruction,
  repair instruction, operator focus, and one-off evaluation prompt

Do not alphabetize or generic-format the dream JSON if doing so moves variable
fields upward. Same-prefix amplification/compensatory follow-up samples should
run after an earlier request has completed enough to warm DeepSeek's cache,
mirroring the existing subconscious sample-wave rule.

The executable guard has three layers:

- `model_client.py` rejects DeepSeek-flavored chat configs that omit
  `cache_contract="deepseek_prefix_v1"`.
- `tools/aippocampus/docs/check_docs_health.py` scans production script
  `ChatClientConfig(...)` call sites and fails docs health if a new LLM caller
  omits an explicit `cache_contract`.
- `dream_worker.py` builds the stable-prefix message order and reports provider
  `usage` plus DeepSeek cache metrics when a model call is used.
- `dream_real_history_eval.py` returns a `live_worker_contract` block so the
  dream layer carries this boundary even when using the deterministic fallback.

DeepSeek cache telemetry can be reported only from provider `usage` fields. Do
not invent hit rates for deterministic dream evals, OpenAI-compatible fallback
routes, or offline providers that do not return DeepSeek prefix-cache metrics.

## Dream Outputs As Reusable Inference Substrate

Dream tasks should not be treated as a foreground answerer. Their job is to
move expensive integrative reasoning out of the moment when the user is waiting
and into a slower background layer. The foreground agent should usually read
small, already-validated dream outputs instead of asking a live reflect path to
rediscover the same pattern from scratch.

This matters for questions such as:

- "What unnamed question has the user been circling for the last few months?"
- "Which thread patterns keep recurring under different surface topics?"
- "What blind spot or unresolved edge should color the next conversation?"

Those questions are too synthetic for ordinary retrieval and too latency-prone
for every prompt to solve live. Dream outputs should therefore be stored as
reusable `source-backed hypothesis` records:

- `finding_kind`: `blind_spot`, `emergence_signal`,
  `cross_thread_resonance`, `trajectory_hint`, or `synthesis_hypothesis`
- `dream_function`: `compensatory`, `prospective`, `amplification`, or
  `active_imagination`
- `source_refs`: the clean-source turns or thread-level findings that inspired
  the hypothesis
- `confidence`, `counter_evidence`, `updated_at`, and `expires_or_review_after`
- `downstream_use`: whether the finding may feed a cognitive portrait,
  ambient recall card, thread ambient cache, or an explicit user-facing check
  when the hypothesis is high-risk or would be stated directly to the user

The contract stays conservative: a dream finding is not a fact and must not
rewrite clean source. It is a prepared interpretive layer over source. When the
user asks a high-level continuity question, or when ambient recall detects a
matching theme, the agent can retrieve these records as a starting map, then
follow `source_refs` back to clean source before making strong claims.

The first runtime bridge reuses the existing soft working-memory substrate
instead of creating a dream-specific foreground channel. Only adjudicated dream
findings with source refs can be projected as `candidate_type="dream_hypothesis"`
working-memory rows. Most adjudication should be background/system work:
source-ref checks, counter-evidence checks, confidence/risk routing, expiry, and
parking. User intervention is reserved for hypotheses that would affect a
sensitive personal interpretation, a durable preference/profile claim, or a
direct user-facing assertion. The boundary remains:
`adjudicated_dream_hypothesis_not_fact`, no clean-source mutation, and no formal
memory promotion. As of the P2 substrate, projection also requires
source-ref-backed bridge claims; a forced accepted state without those refs must
still be ignored.

As of the #130 gate, projected rows also carry `foreground_use` and
`sensitive_use_gate` metadata. The default action is `quiet_substrate`: the
foreground can let a dream hypothesis change routing, recall selection, or
reflection topology only when it changes the current answer. It should stay
silent when the relevant source is already visible, the hypothesis is expired,
or annoyance risk is high. Any strong user-facing claim must reopen source
first; rendered previews must say "Dream hypothesis, not source fact" and keep
uncertainty/source-reopen wording. Sensitive personal interpretations,
relationship-continuity stories, durable profile/preference claims, and
overconfident dream language are parked before working-memory projection.
The actual foreground path enforces this through working-memory matching and
hook rendering: blocked/expired/sensitive dream rows are not matched, matched
dream rows carry a `dream_hypothesis_use` plan, and hook context renders the
dream boundary instead of the generic working-memory wording. Ambient recall
cards generated from dream rows likewise say to use the hint quietly and reopen
source before strong claims. Reflection topology may include only adjudicated,
source-ref-carried dream hypotheses as collapsed interpretive nodes with a
source-reopen boundary. Agency affordance mapping treats direct dream
hypothesis inputs as backstage-only and drops rows blocked by the sensitive-use
gate, so a dream cannot become a foreground action ticket merely by bypassing
ambient recall.

### Ambient Residue As Dream Seed

Thread ambient cache can also feed dream work, but only through an intermediate
residue layer. A cache card is foreground working context; a dream finding is a
model-synthesized interpretive output. Collapsing those two would turn short
term resonance into overconfident story.

The bridge is `ambient_residue`: a small JSONL seed exported from
`ambient_thread_cache.py` when a topic epoch rotates, a cache entry expires, or
an operator explicitly wants to preserve useful unused resonance. Residue is
not a dream output. It is only a source-ref-fingerprinted hint that says:
"something here was warm enough to hand to a later dream task."

Residue rows should stay narrow:

- `kind`: `aippocampus_ambient_residue`
- `status`: `dream_seed`
- `topic_epoch`, `reason`, `mode`, `confidence`
- `card_ids`, `themes`, `support_levels`
- `source_ref_fingerprints`, not raw prompt text
- `negative_contexts`, if they explain why a card stayed quiet
- `downstream_use`: `dream_task_seed`
- `dream_contract`: seed only; not a dream finding, memory fact, or
  source-backed claim

The first export policy is conservative: unsourced one-off scent cards are not
exported. A residue seed needs source-ref fingerprints so the dream worker can
re-open clean source before producing compensatory, prospective, amplification,
or active-imagination output.

### Correction Reconsolidation

User corrections and model closeouts form a smaller, higher-reliability dream
loop than broad ambient residue. A correction is a trigger for adjudication, not
truth by itself: the user may be right, locally right, superseded later, or
wrong. The foreground hook should capture compact source-backed activation
events; post-work hooks should capture outcome and verification evidence; a
detached semantic worker should decide whether the correction becomes an active
task anchor, soft working memory, a promotion candidate, or a refuted
correction note.

Keep the detailed contract in
[Correction Reconsolidation](correction-reconsolidation.md) so this memo stays
focused on the general dream-task layer.

## The Hero's Journey Insight

The Hero's Journey (Campbell) has a known flaw: it imposes a quest narrative
shape onto experiences that don't all fit it. Not every conversation is a quest.
Some are meandering, some are dead ends, some are pure exploration.

But this flaw is also a feature. Humans **want** to be on a journey. Everyone
wants to be the protagonist of their own story. The Hero's Journey persists not
because it's accurate, but because it's **compelling** — it gives shape to
experiences that would otherwise feel formless.

This has a direct implication for AIppocampus:

**AIppocampus does not encode the Hero's Journey into memory.** The intuition
layer uses hexagram arcs (state transitions, no narrative assumption) precisely
because threads don't all follow a quest shape.

**But AIppocampus should recognize when a thread IS following a journey
pattern**, and when it does, the agent should be able to sense it. The dream
task's amplification function can detect journey-pattern resonance across
threads — not to impose the pattern, but to recognize it when it emerges
naturally.

The real purpose: **AIppocampus helps the agent stay on the journey with the
user.** Not by enforcing a narrative structure, but by maintaining enough
intuition about the user's trajectory that the agent doesn't lose the thread
(pun intended). When the user is in the middle of their own story, the agent
should sense where they are — not analytically, but intuitively.

This is the 感而遂通 of the dream layer: the agent senses the shape of the
user's ongoing journey, then can retrieve the specifics on demand.

## Design Principles

1. **Dream output is not fact.** Every dream output must be flagged as
   dream-synthesized and must carry `source_refs` to the threads that inspired
   it. Users and agents must be able to distinguish extraction from integration.

2. **Compensatory before prospective.** The safest function to implement first
   is compensatory analysis (what's missing). Prospective and active imagination
   are more powerful but more prone to hallucination.

3. **Amplification requires cross-thread registration.** You can't detect
   cross-thread resonance until multiple threads are registered and their
   extractive metadata exists. Amplification depends on the existing extraction
   pipeline being mature.

4. **Dream frequency should be lower than extraction.** Extraction runs after
   every thread. Dream tasks should run periodically (e.g., after N threads, or
   on explicit trigger) to avoid noise and cost.

5. **Active imagination outputs must be auditable.** If the dream task produces
   a "bridge concept" connecting two threads, the bridge must include the
   specific turns in both threads that inspired it, so a human can verify the
   connection is real and not hallucinated.

6. **Do not impose narrative shape.** The dream task should detect patterns, not
   impose them. It may observe that a thread follows a quest structure, but it
   should not force threads into narrative templates.

7. **Adjudicate or discard before influence.** Raw Phase 1 dream output can
   enter a holding queue only. A background worker should accept, correct, park,
   expire, or discard it before it influences recall, reflection space,
   cognitive portraits, or ambient cards. User confirmation is not the default
   path; ask only when a current answer would depend on a sensitive or uncertain
   hypothesis. Accepted hypotheses may use the existing working-memory
   substrate; do not add a parallel dream foreground channel unless that route
   proves inadequate.

## Implementation Priority

| Phase | Function | Depends on | Risk |
|-------|----------|------------|------|
| 1 | Compensatory analysis | Single thread extraction | Low; first deterministic helper implemented |
| 2 | Prospective analysis | Multiple thread extraction + theme emergence | Medium |
| 3 | Amplification | Cross-thread registration + concept edges | Medium |
| 4 | Active imagination | All above + explicit dream flag + audit trail | High |

Phase 1 is implemented as a conservative local helper, not as proof that dream
output improves live recall. Phase 4 remains a research target that depends on
everything else being stable.

## Open Questions

1. How does dream output interact with the intuition layer (hexagram arcs)?
   Should dream insights also be compressible into thread mood markers?
2. What is the right trigger for dream tasks? After N threads? On user request?
   Time-based? When the compensatory function detects a significant blind spot?
3. How to prevent the dream task from becoming a "storytelling engine" that
   imposes narrative on non-narrative threads?
4. Does compensatory analysis work for technical threads, or is it primarily
   valuable for life-wide/personal threads?
5. How to evaluate dream output quality? Extraction quality is measurable
   (precision/recall against source). Dream quality is harder to ground-truth.
6. Can the prospective function be validated retroactively — i.e., do emergence
   signals actually predict future threads?

## Related Work

- Jung, C.G. "The Practical Use of Dream-Analysis" (1934) — compensatory and
  prospective dream functions
- Jung, C.G. "Psychology and Alchemy" (1944) — amplification method
- Campbell, J. "The Hero with a Thousand Faces" (1949) — monomyth structure
- [affect-side-channel.md](affect-side-channel.md) — thread intuition layer,
  hexagram arcs, two-layer memory architecture
- [compact-activation-signals.md](compact-activation-signals.md) — cognitive
  portrait as activation signal
- Anthropic Managed Agents Dreams (Research Preview, 2026) — memory store
  reorganization from prior sessions:
  [Claude API docs](https://platform.claude.com/docs/en/managed-agents/dreams)
- Emotional RAG: [arXiv:2410.23041](https://arxiv.org/abs/2410.23041)
- Representation Engineering (Zou et al., 2023): [arXiv:2310.01405](https://arxiv.org/abs/2310.01405)

## Review Credits

**User insight (2026-05-27):**
Connected Jung's dream theory to AIppocampus's subconscious consolidation
pipeline. Key observation: extraction is only half of what a subconscious does;
the other half is integrative (compensatory, prospective, amplificatory,
creative). Also noted that the Hero's Journey's "flaw" (imposing quest
narrative) is also its strength (people want to be protagonists), and that
AIppocampus's goal is to help the agent stay on the journey with the user —
not by imposing narrative structure, but by maintaining enough intuition that
the agent doesn't lose the thread.

**User insight (2026-05-28):**
Framed user corrections and model closeouts as two natural hooks for a
subconscious reconsolidation loop. The key addition is that work-task
continuity needs semantic adjudication: a user's correction should be captured
and preserved across compaction, but later dream work must still be able to
mark it valid, refuted, superseded, local-only, or uncertain.
