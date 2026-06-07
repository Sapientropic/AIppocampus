# Question Tracking as a Subconscious Layer

Role: active design.

## Origin

This document comes from two converging insights:

1. **AIppocampus** preserves original conversation wording, but does not yet
   understand *what the user was asking*. It can find old text, but cannot tell
   you which questions keep coming back, which ones went dormant or unresolved,
   or which seemingly unrelated threads share a deeper concern.

2. **Metaflow** (活知识网络引擎) articulated a cognitive framework where
   questions are first-class citizens, judgment evolves over time, and recurring
   questions reveal hidden themes (母题显影). The full Metaflow product vision is
   too heavy for daily use, but its core insight — *question continuity is the
   scarcest resource in the AI age* — is real and unaddressed.

This design integrates the thinnest useful slice of Metaflow into AIppocampus as
subconscious jobs, adding zero user-facing interaction cost.

**Reviewed by:** kimi-reviewer, gemini-researcher, deepseek-flash (2026-05-26).
Design revision v2 incorporates their feedback.
**Neuroscience grounding:** v3 adds hippocampal cognitive map mechanisms.
**v4:** Incorporates v3 neuroscience review from kimi-reviewer and
gemini-researcher: softened grid cell analogy, added pattern completion vs
separation, behavioral falsifiability, TEM and generative replay notes.
**v5:** Adds time cells, head direction cells, MEC/LEC dual streams, boundary
vector cells, and social place cells as phase-anchored design constraints.

## Implementation Status

Current code does **not** fully implement this whole design. It ships Phase 1,
the first deterministic Phase 2 baseline, and a conservative first Phase 3
theme-emergence slice, plus first question-index scale/sidecar evaluation:

- Implemented: `question_extraction` inside `JOB_SPECS`, including
  `question_candidate` and explicit `frontier_marker` output.
- Implemented first #248 extraction-gate slice: `question_extraction` now
  applies deterministic pre-filtering before model calls and same-thread
  normalized dedupe during validation. Dry/no-write runs expose aggregate
  `question_extraction_gate` diagnostics. This does not claim default question
  index adoption, live answer-quality lift, or broader theme-resonance
  calibration.
- Implemented: `question_tracking` as a deterministic runner in
  `skills/aippocampus/scripts/aippocampus_runtime/question/tracking.py`. It is
  registered as a dependency-ordered `JOB_SPECS`
  entry and groups existing source-backed
  candidates, writes append-only `question_link` findings back to
  `subconscious_jobs.jsonl`, records auditable ordering edges, skips stale refs
  when registry clean-source resolution is available, adds deterministic
  salience tags, adapts strong/borderline thresholds from six-axis evidence,
  and accepts borderline pairs only when an explicit confirmation artifact is
  supplied. Confirmation artifacts are now audited as accepted, rejected,
  malformed, stale, or source-id mismatched; rejected/invalid artifacts do not
  create links. Accepted `match_evidence` keeps a compact artifact-audit block
  with pair id, source finding ids, model/source, prompt version, and timestamp;
  it does not copy source refs or raw clean-source text into the confirmation
  layer.
- Implemented first health slice: `skills/aippocampus/scripts/aippocampus_runtime/question/health.py`
  derives source-backed question stats for `aippocampus health`, including
  recurring links, neutral dormancy, explicit-resolution signals, frontier
  counts, phase-context patterns, and longest-running open question. This is a
  heuristic reporting layer, not a durable memory fact. Public health output
  exposes aggregate counts only unless local diagnostics explicitly request
  details; `aippocampus health --question-stats` resolves refs against
  registry clean source by default, and `resolved` requires independent later
  resolution source refs.
- Implemented first #135 resolution-extraction slice:
  `skills/aippocampus/scripts/aippocampus_runtime/subconscious/question_resolution.py` can read registry clean
  source and emit append-only `question_resolution_signal` rows only when a
  later same-thread user turn explicitly says the tracked question was solved,
  understood, or no longer needed. It does not infer resolution from assistant
  answers, generic positive language, same-ref self-certification, or source
  refs that no longer resolve. The deterministic job runner now wires
  `question_resolution` after `question_tracking` when requested.
- Implemented first #134 offline confirmation/calibration slice:
  `question_tracking.py` can now export compact
  `question_pair_confirmation_request` JSONL for borderline pairs. The request
  includes pair ids, source finding ids, extracted question axes, scores, and
  threshold policy, but not clean-source messages or full source refs. The
  selected-fixture calibration runner
  `benchmarks/aippocampus/benchmark_question_tracking_calibration.py` checks
  that obvious recurring questions still link, low-information generic
  questions stay separated, and borderline pairs produce auditable pending
  requests. It also compares the static strong-threshold baseline with the
  current adaptive-threshold path and reports non-regression deltas for missed
  positives and merged negatives.
- Implemented first #134 optional live/model adapter slice:
  `skills/aippocampus/scripts/aippocampus_runtime/question/confirmation_live.py` consumes pending
  request JSONL and writes explicit confirmation artifacts that the tracking
  `--borderline-confirmations` path can consume. The adapter is
  dry-run by default; a caller must pass `--call-model` and provide an API key
  route before any external model call occurs. A sanitized no-write smoke,
  `tools/aippocampus/smoke/smoke_question_confirmation_live.py`, exercises the
  pending-request -> live artifact -> tracking round trip without writing
  formal job rows or emitting source refs/raw question text. The 2026-05-31
  local DeepSeek run over the current registry produced 25 candidates, 17
  frontiers, 1 pending request, 1 live artifact, and 1 accepted no-write
  round-trip link; it does not claim real-user calibration or recall quality.
- Implemented first #137 ambient-policy slice:
  `skills/aippocampus/scripts/aippocampus_runtime/recall/ambient_policy.py` gives reviewed
  `question_link` / `theme_candidate` / `frontier_marker` working-memory scent
  a hash-only control overlay. The hook records local surface events for
  ambient cards, caps nearby recurring question/theme hints, keeps frontier
  markers quiet unless the prompt asks to resume or diagnose an unresolved edge,
  fails open when the local overlay is too large for cheap foreground parsing,
  and supports `stop tracking this` / `ignore question about X` style dismissal.
  This is a foreground control plane, not a user-preference fact or clean-source
  record.
- Implemented first #137 feedback-pressure slice:
  `aippocampus_runtime.question.feedback_policy` lets `question_tracking.py`
  consume source-id-backed ambient dismiss/reopen events as conservative
  separation pressure for the same source-backed question pair.
  The feedback policy is now package-owner only, not a separate flat import
  promise.
  Only `target_kind="question_link"` can affect pair separation; theme/frontier
  dismissals remain hook-surface policy and do not change question-pair scoring.
  Unsourced feedback fails open, and later reopen events clear dismissal
  pressure.
- Implemented benchmark: `benchmarks/aippocampus/benchmark_cognitive_portrait.py`
  builds a structured-text cognitive portrait from existing
  `question_candidate`, `frontier_marker`, and `question_link` shapes, then
  compares the compact portrait with fuller clean-source injection. It is a
  benchmark/report surface only; full clean source remains required for quotes
  and final evidence.
- Implemented first #136 deterministic theme slice:
  `skills/aippocampus/scripts/aippocampus_runtime/subconscious/theme_emergence.py` consumes recurring
  `question_link` rows, requires shared source-derived concepts plus
  concept-graph neighbor evidence, aggregates related `frontier_marker` rows
  into a boundary map, and writes append-only `theme_candidate` findings back
  to `subconscious_jobs.jsonl`. Theme labels are selected from shared source
  concepts; no LLM discovers or names themes in this slice.
- Implemented first #138 sidecar evaluation slice:
  `skills/aippocampus/scripts/aippocampus_runtime/question/index_sidecar.py` can build or reuse a
  rebuildable SQLite `question_index.sqlite`, detect missing/stale cache state,
  degrade to the current pair-scan baseline, and report source-ref-key join
  fidelity before any future prefilter is allowed. The sidecar stores compact
  term keys and source-ref fingerprints, not question text payloads. It now
  emits a structured adoption report that separates "sidecar may be useful to
  evaluate" from "default prefilter is safe"; synthetic-only evidence never
  recommends the default path. The synthetic
  `tools/aippocampus/smoke/smoke_question_tracking_scale.py` smoke reports
  pair-scan growth, sidecar coverage, adoption decision, and privacy/cannot-
  claim boundaries without reading private registry data.
- Implemented first #248 prefilter-reporting slice:
  `question_tracking` now emits `prefilter_mode="pair_scan"` plus a compact
  `question_tracking_prefilter` report that says sidecar/vector prefilters are
  not used by the default runtime path. This is observability for the remaining
  #248 gap, not adoption of the SQLite or vector prefilter.
- Implemented #248 prefilter parity smoke:
  `tools/aippocampus/smoke/smoke_question_prefilter_parity.py` runs the
  optional SQLite sidecar against selected/current question rows with a
  temporary rebuildable index, then emits only structural counts, strong-pair
  coverage, source-ref-key join status, and default-prefilter boundary labels.
  It is private-safe parity evidence for evaluating future acceleration, not
  answer-quality, user-visible recall lift, or default prefilter enablement.
- Implemented first #139 structural benchmark slice:
  `benchmarks/aippocampus/benchmark_question_aware_real_history.py` selects
  private real-history question/frontier/link/theme rows when available,
  emits sanitized aggregate packs with hashed source refs only, and compares
  question-aware portrait scaffolding against plain source-derived terms. The
  report records pack-selection strategy, aggregate coverage/token metrics,
  known failure modes, and the boundary between helpful navigation scaffolding
  and evidence that still requires clean-source lookup. The 2026-05-30 local
  run over the current registry was explicitly conservative:
  `structural_proxy_ready_but_scaffold_regressed`, with 697 job rows, 42
  eligible rows, 2 sanitized packs, source-ref fidelity 1.0, no private text
  emitted, token ratio 3.7005, and term-coverage delta -0.4412. It is a
  structural proxy, not answer-quality or user-visible recall proof.
- Implemented a #248 opt-in answer-quality review slice in the same benchmark:
  operators can pass source-reopened review rows for paired `plain_baseline`
  versus `question_aware_source_reopen` arms. The report emits case hashes and
  aggregate support/usefulness/citation/wrong-hint rates only; it never emits
  raw answer text, source text, raw refs, message ids, or local paths. This is
  selected answer-quality review evidence, not full-history quality, live model
  behavioral equivalence, user-visible recall lift, or default prefilter safety.
- Closed first-slice queue: umbrella #133 and focused #134 through #139 are
  implementation evidence for the first deterministic/question-health/theme/
  ambient/sidecar/structural slices. Do not route remaining work back there.
- Current follow-up owner: #248 owns unresolved design/runtime gaps after that
  closeout, including extraction gates, default prefilter adoption,
  answer-quality validation, broader calibration, and theme resonance.
- Adjacent user-visible symptoms: #201 and #281 cover places where vague or
  fresh-thread recall still feels too much like manual source search.
- Designed/deferred under #248: real-user / private real-history calibration
  beyond selected fixtures and the one sanitized no-write external-provider
  smoke for #134, broader resolution extraction from non-explicit final-answer
  or fuzzy follow-up evidence (#135), enabling the question index as a default
  tracking prefilter (#138), full theme calibration / LLM naming beyond
  deterministic #136, full ambient recall calibration beyond the first
  working-memory cap/dismissal slice (#137), live/private answer-quality
  validation beyond the first #139 structural proxy, and predictive /
  generative replay (#127).

Do not read later architecture sections as current behavior until matching
`JOB_SPECS`, tests, and scheduler support exist in code.

## Phase Anchors For ADHD-Safe Continuity

Phase 1 may deliberately stay small, but the later dimensions are not optional
memory scraps. They are preserved here so future agents do not forget them when
only the first slice ships.

- **Phase 1 ships extraction plus orientation/boundary fields:** implement
  `question_extraction`, `intent_orientation`, and clear `frontier_marker`
  findings when the source explicitly shows a stopping point. Do not implement
  full tracking first.
- **Phase 2 ships multi-axis tracking:** compare questions with `what`,
  `where`, `heading`, `when`, and `with_whom` axes instead of one embedding
  score.
- **Phase 3 ships theme and boundary maps:** recurring question clusters and
  unresolved frontiers become hook-safe scent, with frequency caps and user
  escape hatches.
- **Phase 4+ remains research:** SR, TEM, generative replay, and anticipatory
  questions are useful only after Phase 1-3 produce stable source-backed
  signals.

This section is a continuity guard. If Phase 1 is implemented first, keep this
roadmap in the doc and carry it into handoff notes. Do not delete the later
mechanisms merely because they are not in the first implementation slice.

## Neuroscience Grounding: The Hippocampus as Cognitive Map

The name AIppocampus was chosen before this feature existed. The original
justification was about memory storage — the hippocampus is popularly known as
the brain's memory center. But the hippocampus's most important function, and
the one that earned O'Keefe and the Mosers their Nobel Prize, is not storage.
It is **cognitive mapping**: the ability to construct spatial and relational
maps of any environment — physical, social, or conceptual.

Question tracking gives AIppocampus the hippocampus's map-making ability, not
just its filing ability.

### Place Cells: Marking Locations in Cognitive Space

Place cells in CA1/CA3 fire when an animal occupies a specific location. Each
cell has a "place field" — a region of space where it is active. A population of
place cells collectively encodes "where am I right now."

**Key mechanism — BTSP (Behavioral Time Scale Plasticity):**
A single calcium plateau potential can establish a place field within seconds.
The hippocampus does not need repeated exposure to mark a location. One visit is
enough. This is non-Hebbian: the learning happens on the first experience, not
through gradual reinforcement.

**Remapping:** When the environment changes, place cells remap:

- **Global remapping:** Completely new map for a new environment.
- **Rate remapping:** Same map, different firing intensity for different tasks
  within the same space.
- **Partial remapping:** Some cells remap, others stay stable.

**What AIppocampus borrows:**

- **Single-pass extraction (BTSP analog):** `question_extraction` must identify
  questions from a single conversation pass. No question needs to appear
  multiple times before it is worth extracting. One mention is enough.
- **Context-bound maps (remapping analog):** Different projects and work modes
  get local views, but AIppocampus remains a global continuity layer. A
  question can recur across projects when it reflects a life-wide concern
  (memory continuity, agent alignment, creative process); the project view is a
  map overlay, not the boundary of recall.
- **Intensity variation (rate remap analog):** The same question can have
  different urgency or relevance depending on the current task context. This is
  captured by `question_link.link_type` — `recurring` with different
  `evolution_note` values.

### Grid Cells: A Metric for Cognitive Distance

Grid cells in the medial entorhinal cortex (MEC) fire in a hexagonal lattice
pattern across space. They do not mark specific locations — they provide a
**metric**: a way to measure distance and direction between locations. Multiple
grid modules operate at different scales (spacing increases by ~√2), creating a
multi-resolution coordinate system.

Grid cells have been shown to operate beyond physical space. fMRI studies find
grid-like hexagonal signals when humans navigate:

- **Morphology space** (bird size/color features) — Bellmund et al., 2018
- **Social space** (dominance/affiliation axes) — Tavares et al., 2015
- **Odor space** — Bao et al., 2019
- **Conceptual knowledge spaces** — Theocore et al., 2021

The hippocampus treats any structured relational space the same way it treats
physical space. Questions and their relationships form such a space.

**What AIppocampus borrows (with caveats):**

- **Embedding space as distance function:** Vector embeddings provide a
  distance metric between questions. This is the *mechanical function* that
  grid cells serve (measuring distance), but the analogy stops there.
  Embeddings lack grid cells' hexagonal periodicity, path integration
  (cumulative self-motion tracking), and the √2 scaling between modules
  (which is a biological observation, not a design constraint we replicate).
- **Pipeline stages at different grain:** The three job layers operate at
  different granularity — extraction (specific question) → tracking
  (cross-thread cluster) → emergence (母题). But they are pipeline stages,
  not multi-resolution representations of the same space. Grid cell modules
  all represent the same physical space at different scales; our three jobs
  produce progressively abstracted *outputs*. The analogy is loose and should
  not be over-extended.
- **Deterministic before LLM:** Grid cells are deterministic neural circuits.
  The pattern emerges from network structure, not deliberation. Similarly,
  `question_tracking` uses deterministic embedding similarity as its primary
  matching mechanism, with LLM confirmation only for pre-clustered groups.
  This structural point holds regardless of how close the functional analogy
  is.

### Successor Representation: Predictive Maps, Not Static Maps

The Successor Representation (SR) theory (Dayan 1993, applied to hippocampus by
Stachenfeld, Botvinick & Gershman 2017) proposes that the hippocampus does not
store a static map. Instead, it stores a **predictive map**: "given that I am at
state A, what states am I likely to visit in the future?"

This is not "A is near B." It is "starting from A, what is the probability of
reaching B within N steps?" The SR captures the structure of experience, not
just the structure of space.

**What AIppocampus borrows:**

- **Evolution-aware tracking:** `question_link` with `link_type="evolving"`
  already captures that a question changed direction. An optional
  `predicted_next` field could extend this: based on the question's historical
  trajectory (what sub-questions emerged, what concepts it connected to), the
  system can estimate what the user might ask next — not as a guess, but as a
  structural prediction from the question's transition history.
- **Transition matrices, not adjacency lists:** The concept graph currently
  stores edges (A relates to B). An SR layer would store transition probabilities
  (from A, you are likely to move to B within 3 conversational steps). This is a
  Phase 3+ extension, not a Phase 1 requirement.

  **Caveat:** Conversation turns are not Markovian. Users jump between topics,
  revisit old threads nonlinearly, and the "transition probability" between
  questions depends heavily on context that turn sequences do not capture. Any
  SR implementation must treat transition matrices as noisy heuristic
  summaries, not true probabilistic models. Forcing a Markov structure on
  non-sequential conversation data would be a modeling error.

  **Alternative — TEM (Tolman-Eichenbaum Machine):** Whittington et al. (2020)
  proposed that the hippocampus constructs a TEM that generalizes relational
  structure across domains. For `theme_emergence`, TEM would mean: rather than
  clustering questions by shared concept neighbors, the system could learn the
  *relational structure* between concepts (A is a prerequisite for B, C
  contradicts D) and use that structure to predict which questions belong
  together — even when they share no surface concepts. This is a Phase 3+
  research direction, but it is the more principled alternative to SR for
  theme discovery.

### Replay and Consolidation: Offline Map Refinement

During sleep and quiet wakefulness, the hippocampus generates sharp-wave ripple
events (SPW-R). During these events, sequences of place cells fire in rapid
replay — sometimes forward (replaying the day's trajectory), sometimes reverse
(replaying from the endpoint backward).

Replay serves three functions:

1. **Consolidation:** Transfer memory from hippocampus to neocortex.
2. **Planning:** Simulate future trajectories before acting.
3. **Generalization:** Extract statistical regularities from repeated
   experiences into a generalized map.

**What AIppocampus borrows:**

- **Forward replay → theme prediction:** `theme_emergence` is not purely
  retrospective. Once a theme cluster is identified, the system can simulate
  "what related questions might emerge if the user continues along this
  trajectory" — forward replay as anticipatory scent.
- **Reverse replay → gap detection:** The subconscious review pass can work
  backward from recent turns to check whether earlier conversations contained
  questions that were missed during initial extraction — reverse replay as
  backfill.
- **Generalization → the entire review pipeline:** `subconscious_review.py`
  already generalizes from individual findings to promotion candidates. The
  versioned heuristic scoring and routing mechanisms are the analog of
  hippocampal consolidation during sleep; they prioritize review, but do not
  prove calibrated finding quality.
- **Generative replay → anticipatory questions:** Beyond replaying past
  sequences, the hippocampus can generate novel trajectories through cognitive
  space (preplay). In Phase 3+, `theme_emergence` could generate candidate
  questions the user has not yet asked but that share the relational structure
  of existing themes. These would not be surfaced as recall — they would be
  stored as low-confidence predictions, validated or discarded when the user's
  actual questions arrive.

### Novelty Detection: Dopaminergic Gating

The hippocampus does not map everything equally. Novel environments trigger
dopamine release from the VTA (ventral tegmental area), which gates plasticity
in CA1. New locations get mapped preferentially; familiar ones get maintained
but not actively reshaped.

**What AIppocampus borrows:**

- **Novelty scoring in extraction:** `question_extraction` already produces
  `evidence_strength`. Adding a `novelty` score — how far is this question from
  all previously extracted questions in embedding space — would allow the
  candidate router to prioritize genuinely new questions for
  `use_with_source` routing while keeping familiar questions at `use_silently`.
- **This maps to existing infrastructure:** `estimate_finding_quality()` already
  computes `quality.novelty`. The question extraction job simply needs to
  populate this field using embedding distance to the nearest existing question.

**Tension with recurring value:** Novelty detection prioritizes *new*
questions, but the system's highest-value output is *recurring* question
links. These are not contradictory: novelty gates extraction (a new question
is worth extracting), while recurrence gates promotion (a recurring question
is worth surfacing). A question moves from novel extraction → recurring
detection → theme emergence. The dopamine signal is strongest on first
extraction; the value signal is strongest on recurrence detection.

### Pattern Completion vs Separation: The Threshold Dilemma

The hippocampus faces a fundamental tension between two competing needs:

- **Pattern completion (CA3):** A partial cue should reactivate the full
  memory. You see a fragment of a face and recognize the whole person.
  CA3's recurrent collaterals implement this: similar inputs converge on
  the same representation.

- **Pattern separation (dentate gyrus / CA1):** Similar but distinct inputs
  must remain distinct. Two different faces should not be confused, even
  if they share features. The dentate gyrus orthogonalizes inputs to
  prevent interference.

This is the central algorithmic tension in `question_tracking`: how similar
is "same"? A high similarity threshold (strict separation) means the system
treats every rephrasing as a new question — high precision, low recall, no
cross-thread linking. A low threshold (generous completion) means the system
collapses distinct questions into one — high recall, low precision, false
links.

The current design uses 0.80 cosine similarity as the initial threshold, with
LLM confirmation for borderline cases. This mirrors the hippocampal solution:
the dentate gyrus provides a hard separation gate, then CA3 does soft
completion on what passes through. The embedding similarity threshold is the
hard gate; the LLM is the soft completion.

**ADHD implication:** Generous completion (low threshold) is safer for ADHD
users. Missing a link is worse than making a soft link that can be ignored.
The system should err on the side of recognizing patterns, with the escape
hatch ("stop tracking this") as the correction mechanism.

### Time Cells: Work Phase, Not Just Timestamps

CA1 time cells fire at specific moments in a sequence even when physical
location is unchanged. They encode "where am I in the episode?" rather than
"where am I in space?"

Plain timestamps cannot capture this. "You ask this every time a new project
starts" is not a date pattern; it is a work-phase pattern.

**What AIppocampus borrows:**

- **`phase_context`:** derived labels such as `new_project_start`,
  `debugging_loop`, `post_compaction`, `architecture_review`,
  `pre_closeout`, `implementation_handoff`, and `creative_exploration`.
- **Periodicity as context:** repeated questions can be linked by phase even
  when they are months apart and share few surface terms.
- **Timestamp remains evidence metadata:** `created_at` and source timestamps
  still support audit, but `phase_context` is the map dimension used for
  question tracking.

### Head Direction Cells: Intent Orientation

Head direction cells fire according to facing direction, independent of where
the animal is. In question space, this maps to the user's angle of approach.

"AI memory" asked during debugging, product design, philosophy, relationship
continuity, or implementation planning are not the same question. They may
share words and embedding neighborhoods while pointing in different directions.

**What AIppocampus borrows:**

- **`intent_orientation`:** a Phase 1 field on `question_candidate`, with values
  such as `debugging`, `design`, `implementation`, `evaluation`,
  `philosophy`, `relationship_continuity`, and `self_reflection`.
- **`orientation_evidence`:** a short source-backed note explaining why this
  orientation was assigned. It is audit evidence, not hidden reasoning.
- **Matching gate:** when two questions have similar embeddings but conflicting
  orientations, `question_tracking` may create a weak `related` link, but must
  not collapse them into one recurring question without stronger evidence.

This is the highest-priority addition after basic extraction because it reduces
both false merges and missed intent shifts.

### MEC/LEC Dual Streams: What x Where

The entorhinal cortex feeds the hippocampus through two complementary streams:
MEC contributes spatial/contextual structure ("where"), while LEC contributes
object/content information ("what"). Episodic memory needs both.

The current question-tracking design risks treating each question as a single
point in embedding space. That is too MEC-heavy. Two questions can be near in
embedding space while differing in content kind: technical implementation,
philosophical meaning, product positioning, relationship continuity, or
emotional friction.

**What AIppocampus borrows:**

- **`what_features`:** content objects and content type, such as
  `technical_implementation`, `product_design`, `philosophical_meaning`,
  `relationship_continuity`, `workflow_process`, named tools, and artifacts.
- **`where_context`:** project/workspace label, thread neighborhood, concept
  region, task phase, and local/global scope.
- **Two-stream matching:** `question_tracking` should combine content
  similarity and context similarity instead of relying on one embedding score.

The practical rule: high embedding similarity is only a candidate. A durable
question link needs compatible `what_features` and `where_context`, or a clear
source-backed explanation for why the mismatch is meaningful.

### Boundary Vector Cells: Cognitive Frontiers

Boundary vector cells fire near environmental edges such as walls or cliffs.
They define where a map stops.

In AIppocampus, the analogous signal is not "what did the user ask?" but "where
did the user's exploration stop?" This may be the deepest value of question
tracking: finding regions the user repeatedly approaches but never crosses.

**What AIppocampus borrows:**

- **`frontier_marker`:** a finding kind for source-backed stopping points.
- **`frontier_type`:** `unresolved`, `blocked`, `deferred`,
  `unsatisfied`, `needs_external_evidence`, or `scope_boundary`.
- **`stopped_at` / `why_stopped`:** short source-backed descriptions of the
  boundary. Examples: missing external data, unclear product direction, model
  limitation, user fatigue, unresolved philosophical premise.
- **Neutral language:** do not label these as failures or "stalled" states.
  For ADHD users, boundary scent should feel like a saved trail marker, not a
  nag.

`frontier_marker` can be produced in Phase 1 when the source is explicit. Full
boundary maps belong to Phase 3 after enough markers exist.

### Social Place Cells: Collaboration Context

Social place cells show that hippocampal maps can track other agents' positions
as well as one's own. For AIppocampus, the relevant signal is collaboration
context: which agent, profile, or collaborator the user involved when exploring
a question.

If the user brings the same question to `deepseek-writer` but not
`gemini-researcher`, or asks one profile for philosophical framing and another
for implementation critique, that routing pattern is information.

**What AIppocampus borrows:**

- **`collaboration_context`:** optional labels for profiles, reviewers, tools,
  or human collaborators present in the source.
- **Use as a weak axis:** social context can explain why similar questions
  diverge, but it must not become a personality inference layer.
- **Phase 2 timing:** record the field when available in Phase 1, but do not
  use it for matching until question extraction quality is stable.

### Summary: Hippocampal Mechanisms → AIppocampus Design

| Hippocampal mechanism | AIppocampus implementation | Job |
|---|---|---|
| Place cells (single-pass marking) | One-mention extraction threshold | `question_extraction` |
| Grid cells (distance, caveat) | Embedding cosine similarity (mechanical, not hexagonal) | `question_tracking` |
| Pipeline stages at different grain | Three-layer granularity (extraction → tracking → emergence) | All three jobs |
| Remapping (context switching) | Local project/work-mode overlays on a global continuity map | `question_tracking` + `theme_emergence` |
| Successor Representation (predictive) | `evolving` link type, optional `predicted_next` | `question_tracking` |
| TEM (relational generalization) | Shared-structure theme prediction (Phase 3+ research) | `theme_emergence` |
| Forward replay (planning) | Anticipatory theme prediction | `theme_emergence` |
| Reverse replay (gap detection) | Backfill extraction from older turns | `subconscious_review.py` |
| Generative replay (preplay) | Anticipatory question candidates (Phase 3+) | `theme_emergence` |
| SPW-R consolidation | Existing review + router pipeline | All three jobs |
| Novelty gating (dopamine) | `quality.novelty` from embedding distance | `question_extraction` |
| Pattern completion (CA3) | Low similarity threshold for cross-thread linking | `question_tracking` |
| Pattern separation (DG/CA1) | LLM confirmation gate for borderline clusters | `question_tracking` |
| Rate remapping (intensity variation) | Context-dependent question urgency | `memory_candidate_router.py` |
| Time cells | `phase_context` such as new-project start, post-compaction, pre-closeout | `question_extraction` + `question_tracking` |
| Head direction cells | `intent_orientation` and matching gate for angle-of-approach | `question_extraction` + `question_tracking` |
| MEC/LEC dual streams | `where_context` x `what_features` two-stream matching | `question_tracking` |
| Boundary vector cells | `frontier_marker` for unresolved edges and stopping points | `question_extraction` + `theme_emergence` |
| Social place cells | `collaboration_context` for agent/profile/collaborator routing | `question_extraction` + `question_tracking` |

The implementation can be summarized as a six-axis question map:

| Axis | Field | Purpose | Phase |
|---|---|---|---|
| What | `what_features` | Content objects and content kind | 1 records, 2 matches |
| Where | `where_context` | Project, concept region, local/global scope | 1 records, 2 matches |
| Heading | `intent_orientation` | User's angle of approach | 1 |
| Boundary | `frontier_marker` | Where exploration stopped | 1 records explicit, 3 maps |
| When | `phase_context` | Work phase beyond timestamp | 1 records, 2 matches |
| With whom | `collaboration_context` | Agent/profile/collaborator context | 1 records, 2 matches |

This grounding is not decorative. It generates testable predictions with
measurable behavioral indicators:

1. **Cross-thread link precision:** When the system links questions across
   threads, ≥70% of those links should be ones the user agrees represent the
   same underlying concern (measured by user confirmation rate when links
   surface via ambient recall).

2. **Theme label resonance:** Emergent theme labels should match the user's
   own vocabulary for describing their recurring concerns. If the user
   consistently describes a theme differently than the system labels it,
   the clustering is wrong.

3. **Anticipatory value:** Once theme clusters stabilize, the system should
   surface relevant forgotten questions *before* the user re-asks them. A
   monthly count of "hits" (user was about to ask, system already surfaced)
   versus "misses" (user re-asked without system prompt) is a direct
   navigation-quality metric.

4. **Orientation separation:** When the same surface topic appears under
   different `intent_orientation` values, the system should avoid collapsing
   them unless the user agrees they are the same concern.

5. **Frontier usefulness:** `frontier_marker` hints should help the user resume
   an abandoned edge of thought without feeling accused of failing to finish it.

If none of these indicators converge over a reasonable evaluation period,
the hippocampal analogy is not holding and the design should be reconsidered —
not reinterpreted.

## Why Subconscious

Question extraction, cross-thread tracking, and theme emergence are exactly the
kind of work the subconscious layer is designed for:

- **Slow is fine.** The user does not need real-time question detection. It can
  run during cooldown-detached consolidation passes.
- **Cheap model is fine.** Identifying "what is this person asking" does not
  require frontier reasoning. DeepSeek Flash is sufficient.
- **Provisional by default.** Extracted questions go through the existing
  staging → review → promotion pipeline. They are never truth until consumed or
  validated.
- **Zero user cost.** The user never fills in a form, tags a node, or
  classifies anything. The system reads clean source and extracts questions
  autonomously.

## Architecture Decision: Reuse the Existing Pipeline

**All question/theme jobs, plus explicit frontier markers, should output to the
existing `subconscious_jobs.jsonl`.** No new staging files. In current code,
Phase 1 `question_extraction` and the first deterministic Phase 2
`question_tracking` runner are implemented, and the first deterministic Phase 3
`theme_emergence` runner is registered behind source-backed `question_link`
rows and the concept graph.

This is the most critical design decision. The existing subconscious pipeline
already provides:

- `estimate_finding_quality()` — deterministic heuristic scoring with evidence
  strength, specificity, novelty, actionability, drift risk, score version, and
  bucketed promotion-readiness diagnostics.
- `subconscious_review.py` — LLM second-pass review that produces promotion
  candidates.
- `memory_candidate_router.py` — four-way deterministic routing (`use_silently`,
  `use_with_source`, `confirm_when_relevant`, `park`).

Creating separate staging files (`question_candidates.jsonl`,
`theme_candidates.jsonl`, `frontier_markers.jsonl`) would bypass all of these
controls. The implementation target is that each phase registers `JOB_SPECS`
entries in `subconscious_jobs.py` and uses `finding_kind` to distinguish
output:

| Job | `finding_kind` | Description |
|-----|---------------|-------------|
| `question_extraction` | `question_candidate` | A question extracted from user turns |
| `question_extraction` | `frontier_marker` | A source-backed stopping point or unresolved boundary |
| `question_tracking` | `question_link` | Cross-thread link between question candidates |
| `theme_emergence` | `theme_candidate` | A cluster of recurring questions forming a theme |

Today, every extracted question and frontier marker from `question_extraction`
gets versioned heuristic scoring, review, and routing through the same pipeline
that already handles `concept_edges`, `decision_evolution`, `trigger_mining`,
etc.
The deterministic Phase 2 runner can also append `question_link` rows back to
the same stream. The first #136 Phase 3 runner can now append conservative
`theme_candidate` rows to that stream; richer calibration and LLM naming remain
deferred.

## What It Adds

Phase 1 added one semantic job circuit, one cross-cutting `frontier_marker`
finding kind, and zero new staging files. Phase 2 now has a deterministic
follow-up runner for `question_link` rows. Phase 3 now has a conservative
`theme_emergence` runner that only clusters recurring links when concept-graph
neighbor evidence is available.

### Job 1: `question_extraction`

**Purpose:** Identify the live questions embedded in user turns.

**Input:** Recent clean-source turns (same as existing jobs).

**Output:** Findings with `finding_kind="question_candidate"` in
`subconscious_jobs.jsonl`.

```json
{
  "finding_kind": "question_candidate",
  "question_text": "how to keep agent output aligned with user intent",
  "question_short": "agent intent alignment",
  "intent_orientation": "design",
  "orientation_evidence": "The user is comparing design paths, not reporting a runtime failure.",
  "what_features": ["agent behavior", "intent alignment"],
  "where_context": ["AIppocampus", "memory architecture"],
  "phase_context": "architecture_review",
  "collaboration_context": ["codex"],
  "thread_key": "...",
  "turn_id": "...",
  "source_refs": [...],
  "evidence_strength": 0.8
}
```

Note: no `status` field. Status tracking is `question_tracking`'s job, not
extraction's. At extraction time, every question is simply a new observation.

**Prompt contract:** The model receives compact user turns and is asked to
extract genuine questions the user was pursuing. The output schema asks for a
short source-backed `brief_reason`; it must not store hidden reasoning:

```json
{
  "brief_reason": "The user is expressing confusion about X. This is a conceptual unknown, not a tool instruction.",
  "is_genuine_question": true,
  "question_text": "...",
  "question_short": "...",
  "intent_orientation": "...",
  "what_features": [...],
  "where_context": [...],
  "phase_context": "...",
  "collaboration_context": [...],
  "source_refs": [...]
}
```

Negative examples are embedded in the prompt:

- `"Could you rewrite this function to use list comprehensions?"` → **IGNORE**
  (tool instruction)
- `"Why does the agent keep dropping context?"` → **EXTRACT** (genuine question)
- `"好，开干"` → **IGNORE** (confirmation)
- `"我不太明白第三点"` → **EXTRACT** with context (implicit question)

**Deterministic pre-filter (before LLM call):**

- Skip turns that are >80% code blocks.
- Skip turns under 5 words.
- Skip turns matching known noise patterns (greetings, confirmations, tool
  invocations) using the existing `semantic_trigger_router` noise list.
- Only send turns that contain interrogative words (who/what/why/how/怎么/为什么/
  哪/是否) or question marks, or local implicit-question cues such as "I don't
  understand", "卡住", "困惑", "不确定", "到底", or "怎么判断".
- Also keep explicit frontier/stopping-signal cues such as unresolved,
  blocked, deferred, or needing external evidence before closure, because
  `question_extraction` owns source-backed `frontier_marker` rows too.

**Deterministic post-filter (after LLM response):**

- Skip questions shorter than 4 tokens or longer than 60 tokens.
- Deduplicate within the same thread by normalized content hash (lowercased,
  whitespace-collapsed, punctuation-stripped). This is more lenient than exact
  hash matching.
- Assign `evidence_strength` based on how explicitly the user stated the
  question versus how much the model inferred it.
- Treat `intent_orientation`, `what_features`, `where_context`, and
  `phase_context` as expected question-map axes whenever source/tool context
  supports them; omit rather than invent only when an axis is genuinely
  unavailable.
- Treat `collaboration_context` as optional and source-backed. It should not be
  filled from generic assumptions about the current agent.
- Live/no-write runs expose aggregate `question_extraction_field_presence`
  diagnostics so missing-axis failures are visible without leaking raw source
  text.
- They also expose validation-retention diagnostics by accepted final versus
  all final attempts, so a model output that is sourceful but dropped by
  confidence/ref/summary gates is not misread as model semantic failure.

**Frontier extraction in Phase 1:** The same job may also emit
`finding_kind="frontier_marker"` when the source clearly shows an unresolved
edge:

```json
{
  "finding_kind": "frontier_marker",
  "frontier_type": "blocked",
  "stopped_at": "how to keep recall useful across new projects",
  "why_stopped": "The discussion identified global storage as necessary, but implementation tradeoffs were still open.",
  "intent_orientation": "design",
  "phase_context": "architecture_review",
  "source_refs": [...]
}
```

Do not infer a frontier merely because a question was asked. A frontier needs
an explicit stopping signal: unresolved dissatisfaction, deferred decision,
missing evidence, contradiction, scope boundary, or repeated return without
closure.

### Job 2: `question_tracking`

**Purpose:** Detect when the same question appears across different threads or
sessions, and track its evolution.

**Input:** `question_candidate` findings from `subconscious_jobs.jsonl` (all
registered threads), pre-filtered by deterministic vector similarity.

**Output:** Findings with `finding_kind="question_link"` in
`subconscious_jobs.jsonl`. Append-only — never updates existing entries.

```json
{
  "finding_kind": "question_link",
  "linked_question_short": "agent intent alignment",
  "question_count": 3,
  "link_type": "recurring",
  "first_seen": "2026-04-12T...",
  "last_seen": "2026-05-20T...",
  "evolution_note": "Started broad (agent alignment), narrowed to Codex-specific context loss after compaction",
  "source_refs": [...]
}
```

**Deterministic matching first, LLM confirmation second:**

1. Compute a lightweight embedding for every `question_short`. Prefer local
   embeddings by default; remote embedding providers are optional and must be
   documented as external-model routes.
2. Compare new candidates against the vector index of past questions using
   cosine similarity. Candidates with similarity > 0.80 form candidate clusters.
3. Adjust candidate clusters with the six axes: `what_features`,
   `where_context`, `intent_orientation`, `phase_context`,
   `collaboration_context`, and any conflicting `frontier_marker`.
4. Only pass candidate clusters to the LLM for `link_type` classification
   (`recurring`, `evolving`, `parent_of`, `child_of`).

This avoids the O(N²) LLM-comparison trap. The LLM only sees pre-clustered
groups, not the full history.

The matching rule is intentionally not "embedding says yes, so link it."
Embedding similarity proposes candidates; the six-axis map decides whether the
candidate is a same-question link, an orientation shift, a related-but-distinct
topic, or a boundary/frontier pattern.

**Resolution detection (heuristic, not LLM):**

A question is considered `dormant` (not `stalled`) when:

- It has not appeared in any new turns for 30+ days.
- No affirmative resolution signal was detected.

A question is considered `resolved` when at least one of:

- The user explicitly said something like "解决了"/"明白了"/"不再需要了" in a
  later turn related to the question, and that later user turn has independent
  source refs.

Assistant `final_answer` text is not a resolution signal in the current
implementation. It may become a future heuristic only if paired with later
source-backed user confirmation; otherwise it is too easy to self-certify a
question as resolved.

`stalled` is not used. The distinction between "stalled" and "dormant" is not
reliable without user confirmation, and `stalled` implies failure that creates
anxiety. `dormant` is neutral.

### Job 3: `theme_emergence`

**Purpose:** Find 母题 — the deep, recurring concerns that surface as
seemingly unrelated questions across time.

**Input:** `question_link` findings with `link_type="recurring"` from
`subconscious_jobs.jsonl`, plus the concept graph.

**Output:** Findings with `finding_kind="theme_candidate"` in
`subconscious_jobs.jsonl`.

**Deterministic clustering first; LLM naming later:**

1. Query `concept_index.sqlite` for shared neighbors among recurring questions.
   If multiple questions share ≥2 common concept nodes, they form a candidate
   theme cluster.
2. Current code names the cluster from shared source-derived concepts only.
   A later LLM naming pass may generate a more readable label, but it must name
   only validated deterministic clusters. It must not discover themes.

```json
{
  "finding_kind": "theme_candidate",
  "theme_label": "memory continuity across agent restarts",
  "theme_short": "memory continuity",
  "cluster_method": "deterministic_shared_concept_neighbors_v1",
  "shared_concepts": ["AIppocampus", "clean source", "Codex rollout"],
  "linked_question_count": 4,
  "thread_span": 5,
  "time_span_days": 42,
  "source_refs": [...]
}
```

**Trigger condition:** Only runs when there are ≥3 `recurring` question_link
findings that share concept graph neighbors. This prevents premature theme
extraction from sparse data.

**Execution ordering:** In the current `--job all` path, registered job order
runs `question_tracking` before `theme_emergence`, so new recurring links can be
picked up in the same pass. The `depends_on` field documents the intended
dependency, but arbitrary explicit job lists are not yet topologically
reordered; callers should use `--job all` or pass deterministic jobs in
dependency order until a general planner owns that guarantee.

## Integration with Existing Subconscious Pipeline

```
Clean source turns
       │
       ▼
  ┌─────────────────────────────────┐
  │  subconscious_scheduler.py      │  (Phase 1 unchanged;
  │  --maybe-start / --run-due      │   Phase 2 adds job groups)
  └─────────────────────────────────┘
       │
       ▼
  build_project_timeline.py          (existing)
       │
       ▼
  subconscious_jobs.py               (existing, +3 new JOB_SPECS)
       │
       ├── question_extraction ──┐  question_candidate
       │                         ├  frontier_marker
       ├── question_tracking  ──┤  all output to
       ├── theme_emergence    ──┤  subconscious_jobs.jsonl
       │                        │
       ├── concept_edges       ──┤  (existing)
       ├── decision_evolution  ──┤
       ├── trigger_mining      ──┤
       └── ... other jobs      ──┘
       │
       ▼
  estimate_finding_quality()         (existing, applies to all findings)
       │
       ▼
  subconscious_review.py             (existing, +4 new candidate_types
       │                              in prompt enum string)
       ▼
  memory_candidate_router.py         (existing, +4 new routing rules)
       │
       ▼
  working_memory.jsonl / concept graph / ambient hook
```

### New Staging Files

None. All output goes to existing `subconscious_jobs.jsonl`.

A lightweight vector adapter now exists in
`aippocampus_runtime.question.vector_index` for Phase 2 tests and small local
smoke runs. It is deliberately package-owner only and not the default retrieval
path:
neighbors carry stable source ids, and `question_tracking` must re-open clean
source before accepting or promoting a link.

The first score-fusion policy now exists in
`skills/aippocampus/scripts/aippocampus_runtime/recall/score_fusion.py`. Its `question_tracking`
context is vector-heavy, but only after candidate rows join back to stable
source ids, message/turn ids, or source refs. Missing-source vector neighbors
are skipped, not treated as evidence.

### Changes to Existing Files

**`subconscious_jobs.py` / `aippocampus_runtime.subconscious.job_circuits`:** Current code
registers `question_extraction`, deterministic `question_tracking`, and
deterministic `theme_emergence`. The deterministic runners are not LLM jobs;
they run after semantic jobs write their rows so tracking and emergence do not
race fresh extraction in the high-concurrency worker pool.

**`subconscious_review.py`:** The review prompt currently admits
`question_candidate`, `question_link`, `theme_candidate`, and `frontier_marker`
candidate types. Review/router handling remains quiet ambient navigation; it
does not make `theme_candidate` foreground truth.

**`memory_candidate_router.py`:** Current code has routing rules for the
question/theme finding kinds and the frontier marker:

- `question_candidate` → default `use_silently`
- `frontier_marker` → default `use_silently`, promote only when the current
  prompt explicitly asks to resume or diagnose unresolved edges
- `question_link` (recurring) → `use_with_source` when the hook detects
  semantic relevance to the current prompt
- `theme_candidate` → `use_silently` (ambient scent only, never pushed)

The first #137 hook-level policy slice now exists in
`ambient_recall_policy.py`: reviewed `question_link` and `frontier_marker`
working-memory rows carry stable control keys into ambient cards, and the hook
uses local surface/dismiss/reopen events to cap or suppress foreground scent.
This is not yet full question-aware recall calibration.

**`build_concept_graph.py`:** Do **not** add `question` or `母题` as concept
node kinds. Instead, question, theme, and frontier findings are stored as
attributes on existing concept nodes. This avoids modifying the core graph
schema and keeps the concept graph focused on durable concepts rather than
ephemeral questions.

### No Changes To

- `subconscious_scheduler.py` for Phase 1. Current scheduler runs
  `subconscious_jobs.py --job all`, and `question_tracking` runs after semantic
  job writes. `theme_emergence` follows `question_tracking` in the registered
  `--job all` order; future scheduler work should add a general depends-on
  planner before claiming arbitrary explicit job-list reordering.
- `subconscious_worker.py` — concept-edge extraction is unaffected.
- Clean source format — questions are derived, never stored in source.
- SKILL.md — new jobs are referenced in `references/subconscious-jobs.md`.

## Consumption: How Questions Surface

### Ambient Recall Hook

Current code can route reviewed question/theme/frontier candidates into soft
working memory, and the prompt hook can consume working-memory rows generically.
The first #137 slice adds local cap/dismissal policy for those rows. By default
this remains model-facing scent, not user-facing notification. When the user's
new prompt is semantically related to a tracked question, the hook can add
compact recall context:

```
[recall scent] related question: "memory continuity across agent restarts";
seen across 5 threads since April. Related old turns: t012, t047, t083.
```

This is a hint, not a claim. It does not force the question into the foreground,
and it should not phrase the hint as a judgment about the user.

**Frequency control:** Implemented first slice: reviewed recurring question
cards carry the working-memory `candidate_key`, and `ambient_recall_policy.py`
records hash-only `surface` events so nearby prompts do not repeat the same
hint. Frontier rows are more conservative: the policy filters them unless the
prompt asks to resume, diagnose, or plan around an unresolved edge. This
prevents the same scent from becoming background noise without storing raw
prompt text or treating suppression as a durable user trait.

### User escape hatch

Implemented first slice: if the hook surfaces a working-memory
question/frontier card and the user says "stop tracking this" or "ignore
question about X", the prompt hook writes a local dismissal event keyed by the
reviewed candidate. The candidate stops surfacing until a later reopen event
wins. This does not delete source refs, does not alter clean source, and must
not be interpreted as "the user no longer cares about this topic" outside the
foreground hint policy.

### Health Report

Target behavior for #135: `aippocampus_health.py` or a focused health helper
can report question statistics:

- Total tracked questions.
- Questions recurring across threads.
- Dormant questions (not appeared in 30+ days).
- Explicitly resolved questions from source-backed follow-up signals.
- Active themes.
- Frontier markers by type.
- Repeated `phase_context` patterns, such as new-project-start questions.
- Longest-running open question.

Note: no `stalled` metric. Dormant is neutral, not a failure signal.

### Future: Question-Aware Recall

When the user asks "what was I working on last week", the recall system can
answer from questions, not just from keywords. This is the bridge between
AIppocampus's source-backed recall and Metaflow's question-continuity vision.
The first #139 benchmark now validates sanitized structural pack formation over
private real-history rows and records known failure modes. The current local
run shows the scaffold is source-faithful but not yet more compact or more
complete than the plain structural baseline, so answer usefulness and live
behavioral lift remain unproven until a later opt-in evaluation reopens clean
source and compares actual answers.

## ADHD Design Principles

These principles are non-negotiable for this feature:

1. **Zero interaction cost.** The user never fills in a form, classifies a
   node, or answers a metadata prompt. Questions are extracted from what the
   user already said.

2. **Zero notification spam.** Questions surface as ambient scent in the recall
   hook, not as push notifications, dashboards, or "you should review this"
   prompts. The user sees them only when relevant to the current conversation.

3. **Frequency-capped scent.** Each recurring question's ambient hint appears at
   most once per 7 days. The user is not repeatedly reminded of the same
   question.

4. **User-controlled escape hatch.** The user can say "stop tracking this" to
   archive a question. No UI, no settings page — just a natural language
   command.

5. **Provisional by default.** Extracted questions are staging candidates. They
   do not become truth until the review pipeline promotes them. Wrong
   extractions are noise in a staging file, not pollution in the user's memory.

6. **Works with forgetfulness.** The system does not rely on the user
   remembering to maintain anything. It reads what already exists and extracts
   structure from it.

7. **Graceful degradation.** If question extraction quality is poor (wrong
   questions, missed questions), the worst case is useless scent, not broken
   recall. The existing keyword and concept-graph recall paths are unaffected.

## Implementation Order

### Phase 1: `question_extraction` + Orientation/Frontier Fields

- New `JOB_SPECS` entry in `subconscious_jobs.py`.
- Deterministic pre-filter and post-filter.
- `question_candidate` schema includes `intent_orientation`, `what_features`,
  `where_context`, `phase_context`, and optional `collaboration_context`.
- `frontier_marker` is emitted only when the source explicitly shows a stopping
  point or unresolved boundary.
- Integration with `subconscious_review.py` for quality filtering.
- Test with real clean source from existing threads.
- No full cross-thread tracking yet. No new staging files.

**Validation criterion:** Do the extracted questions match what a human reader
would identify as the user's genuine questions? Precision matters more than
recall here — a few high-quality extracted questions are more useful than many
noisy ones. Frontier markers must feel like saved trail markers, not guilt.

### Phase 2: `question_tracking`

- Shipped first slice (2026-05-30): deterministic local scoring over
  `question_text`, `question_short`, `what_features`, `where_context`,
  `intent_orientation`, `phase_context`, and `collaboration_context`.
- Shipped first slice: append-only `question_link` findings in
  `subconscious_jobs.jsonl`, including `linked_questions`, auditable ordering
  edges, merged `source_refs`, and `match_evidence`.
- Shipped first slice: `subconscious_jobs.py` runs deterministic tracking after
  semantic extraction writes, so tracking does not race the concurrent runner.
- Shipped first slice: stale candidates without concrete source anchors are
  skipped rather than linked; when a registry clean-source index is available,
  well-shaped refs are rechecked against it.
- Shipped first slice: borderline pairs are accepted only when an explicit
  confirmation artifact accepts the pair; the link still derives truth from the
  original question source refs.
- Shipped artifact-audit slice: rejected, malformed, stale, and source-id
  mismatched confirmation artifacts are counted in diagnostics and never replace
  the original question source refs. Accepted pairs keep a compact artifact
  audit in `match_evidence` so reviewers can trace model/source, prompt version,
  created time, pair id, and source finding ids without copying source refs.
- Shipped first #134 offline confirmation/calibration slice:
  `aippocampus_runtime.question.tracking --pending-confirmations-output` exports compact
  confirmation-request JSONL for borderline pairs without full history or source
  refs. `benchmark_question_tracking_calibration.py` provides selected-fixture
  evidence that default thresholds keep obvious recurring questions, reject
  low-information generic merges, surface pending requests for review, and do
  not regress the static strong-threshold baseline on selected positive /
  negative pairs.
- Shipped first #134 optional live/model adapter slice:
  `question_confirmation_live.py` turns pending request JSONL into explicit
  confirmation artifacts for the tracking `--borderline-confirmations` path.
  The CLI defaults to dry-run and requires `--call-model` plus an API key route
  before contacting an external provider. The sanitized
  `smoke_question_confirmation_live.py` no-write smoke exercises request
  generation, optional live artifact generation, and tracking round trip without
  persisting formal jobs or emitting source refs/raw question text.
- Shipped materialization bridge: the deterministic `question_tracking` job now
  writes compact pending requests to the registry sibling
  `question_pair_confirmation_requests.jsonl` and consumes explicit sibling
  artifacts from `question_pair_confirmation_artifacts.jsonl` on later runs
  before appending formal `question_link` rows. It still does not call a live
  model by default; the artifact only confirms a borderline pair and never
  becomes source truth.
- Shipped first salience/threshold slice: every parsed candidate gets a
  deterministic `salience` profile with score, tags, reasons, and `trackable`.
  Low-information source-backed rows are kept as candidates but skipped as
  noisy link inputs. Pair thresholds are adjusted from source-backed axes:
  compatible `what_features`, `where_context`, `intent_orientation`,
  `phase_context`, and collaboration context lower completion thresholds,
  while orientation/context conflicts raise separation pressure.
- Shipped first #137 feedback-pressure slice: source-id-backed ambient
  dismiss/reopen events are consumed by `question_tracking.py` through
  `aippocampus_runtime.question.feedback_policy`. A dismissed same
  source-backed `question_link` pair is treated as separated unless a later
  reopen event wins; dismissals for `theme_candidate` or `frontier_marker`
  remain ambient-surface policy only.
- Shipped first health slice: `question_health.py` reports neutral `dormant`
  and explicit `resolved` states from source-backed job rows, skips stale refs
  through default registry resolution in `aippocampus_health.py --question-stats`,
  rejects same-ref self-certification, and does not use `stalled`.
- Shipped first #135 resolution-extraction slice: `question_resolution.py`
  emits `question_resolution_signal` only for later same-thread user clean-source
  turns with explicit solved / understood / no-longer-needed wording and
  matching question terms. `question_health.py` consumes those rows as
  independent resolution evidence. `question_resolution` is now available as a
  deterministic follow-up job after `question_tracking`.
- Shipped first #138 scale/sidecar evaluation slice:
  `question_index_sidecar.py` can build or reuse an optional rebuildable SQLite
  question-index cache, detect missing/stale caches, degrade to the current
  pair-scan baseline, and report whether index candidates still join back to
  current source-backed question rows and their source-ref keys. The cache does
  not store `question_text` or `question_short` in its row payload.
  `smoke_question_tracking_scale.py` provides synthetic lookup-cost,
  source-join coverage, and adoption-decision evidence. This is evaluation and
  smoke substrate, not a default acceleration path: synthetic evidence can show
  the boundary behaves, but real-history parity and wall-clock evidence are
  still required before default prefiltering.
- Shipped first #248 prefilter-reporting slice: the default
  `question_tracking` result reports its pair-generation path as `pair_scan`
  and marks sidecar/vector acceleration as disabled. This prevents a sidecar
  evaluation result from being misread as default runtime behavior.
- Shipped #248 prefilter parity smoke:
  `smoke_question_prefilter_parity.py` reuses the sidecar evaluator with a
  temporary index and reports whether sidecar candidates preserve pair-scan
  strong-pair coverage and source-ref-key joins. Output is counts/boundaries
  only: no private source text, raw refs, registry paths, or source signatures.
  Passing this smoke still does not make the sidecar the default prefilter.
- Shipped #248 opt-in answer-quality review reporting:
  `benchmark_question_aware_real_history.py --answer-quality-review` accepts
  paired review rows for `plain_baseline` and `question_aware_source_reopen`
  arms, then reports public-safe aggregate support/usefulness/citation and
  wrong-hint metrics. This is a review evidence path for selected clean-source
  cases, not a replacement for broader calibration or default prefilter
  adoption evidence.
- Deferred: real-user / private real-history calibration beyond selected
  fixtures and the one sanitized no-write external-provider smoke (#134),
  fuzzy/non-explicit resolution inference beyond explicit user follow-up signals
  (#135), enabling `question_index.sqlite` as a default lookup prefilter (#138),
  and broader live acceptance/dismissal calibration beyond source-id-backed
  same-pair feedback (#137).

**Validation criterion:** Does the system correctly identify that "how do I
keep agent context" and "why does Codex forget everything after compaction" are
the same underlying question?

### Phase 3: `theme_emergence`

- Shipped first slice (2026-05-30): deterministic clustering over recurring
  `question_link` rows via shared source-derived concepts and concept graph
  neighbors.
- Shipped first slice: append-only `theme_candidate` findings in
  `subconscious_jobs.jsonl`, with preserved question-link ids, source refs,
  thread/time span, shared concepts, and match/naming evidence.
- Shipped first slice: boundary-map aggregation from related
  `frontier_marker` findings, explicitly marked as navigation rather than
  proof of unresolved status.
- Shipped #248 theme-resonance boundary reporting slice: each
  `theme_candidate` and `run_theme_emergence()` result now reports
  `theme_resonance_calibration.status = "absent"`,
  `user_review_evidence = false`, and cannot-claim boundaries. This is runtime
  claim hygiene, not user-review calibration evidence.
- Shipped first ambient-policy coverage: `theme_candidate` uses the same
  frequency cap and dismiss/reopen latest-wins overlay as question scent.
- Deferred: LLM naming for already-validated clusters, user resonance
  calibration beyond explicit absent-status reporting, and theme-specific hook
  calibration beyond the existing quiet `theme_candidate` router/policy path.

**Validation criterion:** Do the emergent themes resonate with the user's
self-understanding? This is inherently subjective and can only be validated by
the user reading the output.

### Phase 4+: Predictive And Generative Map Research

- SR/TEM-style transition structure.
- Generative replay/preplay for anticipatory question candidates.
- Social collaboration routing patterns once enough `collaboration_context`
  evidence exists.

**Validation criterion:** These features should not ship until Phase 1-3 prove
that extracted questions, orientation gates, and frontier markers are useful.
Prediction is valuable only after the map is trustworthy.

### Continuity Safeguard

At the end of each phase, update this Implementation Order section with:

- what shipped
- what validation showed
- what is intentionally deferred
- the next smallest phase slice

This is not bureaucracy. It is an ADHD-safe memory rail so "Phase 1 first" does
not become "Phase 1 forever."

## Risks

**Risk 1: Over-extraction.** The model might extract too many trivial
questions. Mitigated by deterministic pre-filtering (interrogative words,
length gates, noise patterns), short source-backed `brief_reason` prompting,
and the existing review pipeline.

**Risk 2: False cross-thread links.** Different questions with surface lexical
overlap might be incorrectly linked. Mitigated by using vector similarity
(semantic, not lexical) as the primary filter, with LLM confirmation only for
pre-clustered groups. Vector similarity threshold starts at 0.80 and can be
tuned up if false positives are common.

**Risk 3: Theme hallucination.** The model might invent deep themes that do not
actually connect the linked questions. Mitigated by the two-step approach:
deterministic clustering via shared concept graph neighbors (the cluster must
exist before the LLM sees it), and LLM limited to naming the cluster.

**Risk 4: Scope creep toward full Metaflow.** This design intentionally does
not include: judgment nodes, confidence tracking, counterexample objects,
structured input flows, weekly metabolism dashboards, or output generators.
Those belong to Metaflow's full vision. If judgment or evidence layers are ever
needed, they must go through an independent design review. They are not a
natural extension of this system.

**Risk 5: LLM returning empty or malformed results.** If the extraction model
returns no questions or malformed JSON, the job logs the error and exits
cleanly. The downstream pipeline is not affected because nothing was written.
Empty results are not a failure — they mean the turns contained no extractable
questions, which is a valid outcome.

**Risk 6: Orientation overfitting.** The system might over-classify intent and
split genuinely recurring questions into too many buckets. Mitigated by using
`intent_orientation` as a matching gate, not as a hard taxonomy: mismatched
orientation creates a weak related link unless source evidence supports
separation.

**Risk 7: Frontier hints becoming guilt.** Boundary markers could feel like
"unfinished homework" if surfaced too aggressively. Mitigated by neutral
language, conservative hook routing, and user escape hatches. A frontier is a
saved trail marker, not a failure label.

## Review Credits

This design was reviewed by three external profiles on 2026-05-26:

- **kimi-reviewer:** Identified the critical pipeline-bypass issue (independent
  staging files), append-only semantics violation, premature status fields,
  missing resolution detection, and execution ordering gap. Suggested
  deterministic concept-graph pre-filtering for themes, frequency capping,
  escape hatches, and tighter Metaflow boundary language.

- **gemini-researcher:** Identified O(N²) scaling risk in question_tracking,
  content-hash deduplication brittleness, and LLM apophenia in theme
  extraction. Recommended embedding-based matching for tracking,
  HDBSCAN/community detection for themes, negative few-shot prompting,
  explicit rationale fields, and sqlite-vec for scaling. Referenced
  MemGPT/Zep, BERTopic, and search query intent mining as prior art.

- **deepseek-flash:** Confirmed Phase 1 is achievable in 2-3 days. Flagged
  Windows JSONL concurrent write risk (existing codebase already uses
  append-only with atomic writes, so this is mitigated). Identified
  "Garbage In, Garbage Out" as the core risk — weak extraction poisons all
  downstream jobs. Recommended starting with extraction only.

**v3 neuroscience review (2026-05-26):**

- **kimi-reviewer:** Flagged grid cell → embedding as weakest analogy (no
  hexagonal periodicity, no path integration). Clarified that three job layers
  are pipeline stages, not multi-resolution representations. Identified
  falsifiability criterion as too subjective — needed measurable behavioral
  indicators. Identified missing pattern completion vs separation as core
  algorithm tension. Noted novelty vs recurring value tension.

- **gemini-researcher:** Confirmed neuroscience descriptions as "非常准确且前沿".
  Recommended TEM (Tolman-Eichenbaum Machine) over SR for theme_emergence.
  Suggested generative replay/preplay for anticipatory questions. Acknowledged
  √2 scaling as biological coincidence, not design constraint. "绝非装饰"
  (absolutely not decoration).

**v5 neuroscience expansion (2026-05-26):**

- **User + CC discussion:** Added time cells, head direction cells, MEC/LEC
  dual streams, boundary vector cells, and social place cells. The strongest
  immediate additions are head direction cells (`intent_orientation`) and
  boundary vector cells (`frontier_marker`). Time and social dimensions are
  preserved as fields and Phase 2 matching axes so they are not forgotten.

## Relationship to Metaflow

Metaflow's full product vision (five node types, directed relationships, weekly
metabolism, output generators) remains a separate project. This design extracts
one narrow but high-value slice:

- **Question nodes** → `question_extraction` job
- **Question continuity** → `question_tracking` job
- **母题显影** → `theme_emergence` job

The v5 hippocampal additions are AIppocampus-native, not Metaflow imports:

- **Intent orientation** → prevents same-topic/different-angle false merges.
- **Frontier markers** → preserve where exploration stopped.
- **Phase/social context** → capture when and with whom a question appears.

The remaining Metaflow concepts (judgment evolution, evidence/counterexample
tracking, project-driven output) are out of scope. If they are ever needed,
they require an independent design review. They are not a natural extension of
this system and must not be appended to it without explicit scoping.
