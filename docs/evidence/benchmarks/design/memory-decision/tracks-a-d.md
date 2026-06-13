# Memory Decision Benchmark Tracks A-D

Role: extracted detail page.
Status: current detail under the canonical memory-decision benchmark entrypoint.

This file preserves detail split out of
[`../memory-decision-benchmark-plan.md`](../memory-decision-benchmark-plan.md).
Keep current reader routing and cross-track summary in the entrypoint; keep
deep methodology, runner notes, and implementation detail here.

## Core Labels

The primary decision label is three-class, matching the prompt hook surface:

| Label | Meaning | Allowed output |
| --- | --- | --- |
| `should_skip` | Memory should not surface. | `skip` only |
| `should_scent` | Memory may help, but the user did not ask for proof. | `scent`; `skip` is a miss; `evidence` is over-escalation |
| `should_evidence` | The prompt asks for exact/source-backed prior context, or a decision depends on old source facts. | `evidence`; `scent` is partial; `skip` is a miss |

This distinction is mandatory. A binary fire/skip score hides the most dangerous
failure mode: a fuzzy prompt that should only get scent but receives source
snippets.


## Track A: Gate Decision

Target: `assess_prompt()` and the foreground prompt-hook decision path.

This track measures whether AIppocampus chooses the right memory surface before
any payload is judged.

### Case Families

`should_skip` cases:

- ordinary coding tasks, including issue-style prompts that avoid the current
  hard-coded code cue list
- system/goal/status injection text such as thread budget or current-goal noise
- false memory cues, for example "remember this function name" in a local code
  task
- source-free public memory-pain statements that provide no route, source
  request, old-thread deixis, or continuation intent
- generic daily chat and generic status questions without a stable memory
  target
- over-personalization traps where life-wide terms overlap accidentally
- secret-like prompts that must not call external semantic gates
- ambiguous same-name entity prompts that have registry overlap but no memory
  intent

`should_scent` cases:

- vague continuation with real registry or clean-source overlap
- project continuity prompts that are useful but not asking for exact proof
- life-wide recency prompts backed by timeline/source metadata
- working-memory matches that pass project scope and concrete-term checks
- cognitive-map, concept-graph, or semantic-trigger matches that are navigation
  hints only
- multilingual or paraphrased prompts where quiet scent is the right product
  behavior
- cross-project same-name entity prompts that identify the current project but
  do not ask for source proof
- explicit but project-ambiguous same-name entity recall, which should surface
  scent but withhold source evidence until the project/source is clear
- cwd-reversal continuation where the current workspace points to a different
  same-name entity than the highest-risk remembered project
- mixed Chinese/English continuation prompts that should not depend on a
  static single-language continuation word list
- explicit source-free evidence/scent twins whose `should_scent` side removes
  source-request language through hand-written invariant-checked fixture
  contracts, not through ad hoc string replacement

`should_evidence` cases:

- explicit requests for prior wording, quotes, last replies, source lines, or
  citations
- mixed Chinese/English explicit source recall when the query contains enough
  source-derived content to identify the expected clean-source row
- alias-ablated paraphrase controls where the prompt avoids exact reviewed
  trigger aliases, but a mocked semantic/subconscious decision supplies bounded
  query aliases and clean-source evidence still must match the expected thread
- source-backed status questions where the user asks what was decided before
- decision-continuation prompts whose current answer would depend on old source
  facts and whose source probe is strong enough

### Metrics

Required metrics:

- three-class confusion matrix: `skip / scent / evidence`
- macro F1 across the three expected labels
- `scent_or_evidence_recall` for prompts where memory should surface at all
- `evidence_recall` for exact/source-backed requests
- `over_escalation_rate`: expected `scent`, actual `evidence`
- `evidence_false_positive_rate`: expected `skip` or `scent`, actual
  `evidence`
- weighted false-positive cost:
  `code->evidence` and `secret->model_call` are highest severity
- semantic model call rate for prompts that should stay local
- latency distribution under foreground budgets

Initial targets:

- privacy breach rate: `0`
- secret-like prompt external model calls: `0`
- evidence false positives on `should_skip`: `0`
- over-escalation rate: less than `2%`
- `should_evidence` recall: at least `80%`
- `scent_or_evidence_recall`: at least `70%`
- ordinary coding prompt scent/evidence false positive rate: less than `5%`
- `semantic_trigger_alias_ablation.exact_prompt_alias_violation_count`: `0`
  for the synthetic alias-ablation controls
- `track_a_residual_calibration.unresolved_count`: `0` for the checked
  residual taxonomy; additions must explain whether they are product
  reclassification or runtime-rule repair

These numbers are starting gates. Tighten them after the first real-history
case set exposes the natural error distribution.


## Track B: Source Evidence Retrieval

Target: `search_hybrid_index()` and source-evidence retrieval helpers.

This track keeps the existing recall-quality question, but reports it in the
same suite as the decision benchmarks so regressions are visible together.

Validation mode matters for this track:

- Portable wiring smoke: use
  `python benchmarks/aippocampus/benchmark_source_evidence_retrieval.py --fts5-cases 1 --fts5-min-cases 1 --source-max-cases 1 --source-min-cases 1 --allow-deterministic-labels --json`.
  This path can pass on a fresh or second-user machine without prebuilt
  semantic sidecars. It proves the wrapper, FTS5 source-line arm, selected
  source-evidence wiring, privacy-safe report shape, and deterministic fallback
  path. It cannot claim semantic-sidecar coverage or selected semantic-source
  evidence quality.
- Semantic-sidecar quality check: omit `--allow-deterministic-labels`, keep the
  semantic-sidecar-required selected source-evidence arm, and ensure the local
  registry has eligible `semantic-scope-labels.jsonl` sidecar rows first. If
  this run returns `insufficient_selected_cases`, treat it as a coverage/prep
  diagnostic rather than a Track B refactor regression. The wrapper emits
  `validation_guidance.track_b_source_evidence` with the portable smoke command,
  the guidance-local fallback boundary, and a pointer/count back to the parent
  report `cannot_claim` field instead of mirroring inherited caveats.

Case labels must identify an expected source message or line range. Query text
may be exact, normalized, paraphrased, multilingual, or generated from source
terms, but the expected answer is still the clean-source source ref.

Every arm must report `query_origin` and `claim_boundary`. The current taxonomy
groups `source_derived_exact` and `source_derived_sparse` into
`source_derived`; these arms measure index/source-label sanity and stale-source
diagnostics, not natural user-query recall. It groups
`human_or_fixture_question`, `human_or_fixture_paraphrase`, `cross_language`,
`degraded_cue`, and `adversarial_near_miss` into `non_source_derived`; these
arms can support user-like source-navigation claims only within their fixture
and dataset boundary. The wrapper must report source-derived and
non-source-derived hit rates separately, and reports that only ran
source-derived arms must keep `natural_user_query_recall`,
`semantic_generalized_memory_recall`, and
`paraphrase_or_cross_language_recall` in `cannot_claim`. This is the Track B
boundary for #216, #301, and #355.

Metrics:

- R@K for K=`1,3,5,10`
- MRR
- exact message hit rate
- turn-level hit rate for public conversation corpora, so retrieval of the
  adjacent user/assistant row in the expected turn can be measured separately
  from exact message recall
- exact line or line-range hit rate when available
- context-visible evidence-line hit rate when available: the expected source
  line falls inside the retrieved result's bounded source context window. This
  is separate from exact-line R@K and must be labeled with its radius.
- stale-index miss count, separated from lexical/ranking misses
- source-diversity diagnostics when one recap cluster crowds out the expected
  source
- sanitized failure taxonomy for selected source-evidence misses, including
  scope/query-term split, rank-below-budget, and candidate-scored-too-low cases
- candidate-space diagnostics for source-backed gold cases: raw candidate pool
  size, candidate pool limit, whether the gold source entered the raw pool,
  whether it survived the truncated verifier-visible pool, the coarse pruning
  reason, and the resulting `failure_class`. These fields are diagnostic
  counts/ranks only; they must not include raw prompt text, snippets, local
  paths, message ids, thread keys, or source-ref details.
  In the selected source-evidence smoke, `verifier_seen_gold` means the
  source-ref / expected-ref check could inspect the gold candidate; it is not an
  answer-generation verifier and must not support answer-quality claims.

Embedding similarity may be logged as an analysis column, but it must not define
the expected label or pass/fail boundary.

ShareGPT public Track B is a local opt-in extension of this track. It should use
`sharegpt_all_multiturn` for broad public-corpus retrieval and
`sharegpt_coding_multiturn` only when comparing against the coding-heavy Track A
slice. Its public-corpus result should be reported separately from private
real-history source-evidence quality.

Standard retrieval-QA Track B is also opt-in. LoCoMo uses dialogue evidence ids
such as `D1:3` as line/session ground truth. LongMemEval V1 uses
`answer_session_ids` for session-level R@K/MRR and `has_answer` message flags
for line-level metrics when available. Reports include exact line hits,
context-visible line hits, context-improved counts, and top-K context-rescued
counts. Keep both line views visible. Exact line metrics measure whether the
specific annotated row was retrieved. Context-visible metrics match
AIppocampus' source-backed payload shape more closely: a retrieved line can
carry a small neighboring source window without pretending the adjacent text was
the exact evidence line. The optional semantic line reranker adds a second
stage inside that same top-session/top-context candidate set. It may reorder
candidate line numbers, but it must not add lines outside the first-stage source
boundary and must not use answer text or labels as input. The candidate
boundary uses both the raw question terms and a content-term variant that drops
generic question words; this fixes LoCoMo-style speaker/generic-word noise
without replacing the original query. `semantic_only_*` shows the model's pure
line ordering; FTS-preserving `reranked_*` fuses that ordering with the original
first-stage hits so a reranker cannot regress lines already surfaced by local
retrieval. `line_reranker_candidate_evidence_coverage_rate` is an oracle
diagnostic for the benchmark report only: it measures whether the labeled
source row entered the candidate set and is not an input to retrieval. These
runs also report the #309 diagnostic counters
`semantic_bridge_lift_topK`, `source_joined_candidate_evidence_coverage_rate`,
and `wrong_stance_rerank_rate_topK`. They mean "a source-joined auxiliary
candidate/reranker path found or misprioritized a labeled source row after a
top-k text miss"; they do not make embeddings, graph hints, or rerankers source
truth. These runs answer only "can the retriever navigate to the source
session/message from the question text, and can an optional reranker pick the
exact source row without ranking a stale/opposite-meaning neighbor above it?"
They do not measure whether a model generates the final answer correctly, and
they must not be merged with Track A gate-decision scores.
LongMemEval V2 has a diagnostic context-mapping pilot, but it still needs
explicit question-to-haystack/evidence-state labels before it can produce
comparable retrieval R@K/MRR. Until then the source-evidence adapter reports a
skipped source-evidence status and the V2 runner reports only mapping
feasibility. The official-harness pilot decision is intentionally separate:
it can measure memory context, answer accuracy, reader/evaluator dependency,
and query latency in a future tiny local run, but it cannot retire the
source-evidence skipped status by itself.

Segmented-search merge policy calibration is a separate deterministic
diagnostic under Track B's ranking boundary. The #375 runner
`benchmarks/aippocampus/benchmark_segmented_merge_policy.py` feeds synthetic
source-ref-shaped hits directly into `search_segments.py::merge_topk()` and
checks cross-segment diversity, adjacent-turn pairing, duplicate nearby recap
suppression, and stale/superseded currentness. Its report belongs in
`docs/evidence/benchmarks/reports/fresh-thread/segmented-merge-policy-fixture-report.md`. Passing it
means the default merge weights have a small public-safe regression contract; it
does not prove source-evidence retrieval quality, real long-thread recall
quality, or turn-aware segment-boundary quality.


## Track C: End-to-End Payload Fidelity

Target: prompt to hook payload, including `context_for_hook()` output.

This track checks that the final injected payload is the right product artifact,
not merely that the decision label was correct.

Required checks:

- decision matches the expected three-class label
- evidence payload points to the expected source message or line when evidence
  is expected
- expected `scent` cases do not include source snippets
- parked/private/low-confidence memory candidates are not injected
- semantic sidecar labels are never treated as source truth by themselves
- reports remain sanitized by default
- latency degradation is explicit for budgets such as 500 ms, 1500 ms, and
  3000 ms

Metrics:

- payload correctness: correct decision plus correct source behavior
- source fidelity rate
- privacy breach rate
- parked-memory injection count
- evidence-without-source count
- budget compliance by latency bucket

The first implementation should be thin and deterministic: mocked semantic
gate, synthetic/public fixtures, and no live LLM dependency. A broader local
private run can follow once the thin path catches regressions.


## Track D: Compaction Continuity Benchmark

Target: correction reconsolidation across `UserPromptSubmit`, `PostToolUse`,
`Stop`, `SubagentStart`/`SubagentStop`, thread cache, active task anchors, and
compaction boundaries.

This track measures a different reliability property from Tracks A-C. Track A
asks whether memory should surface at all. Track B asks whether the right source
can be found. Track C asks whether the injected payload is faithful. Track D
asks whether the system preserves high-value work-task corrections, accepted
decisions, failed-route lessons, and task invariants after the visible
conversation has been compressed or pushed out of the model horizon.

The track must keep the truth boundary explicit: a user correction is not
automatically true. It is a source-backed activation event that later semantic
or evidence-based review may mark valid, refuted, superseded, local-only, or
uncertain.

Track D depends on the Hook Timing Matrix in
[`docs/research/correction-reconsolidation.md`](../../../../research/correction-reconsolidation.md).
The benchmark should measure event-stage behavior without turning every hook
into a semantic judge. In particular, `PreToolUse` is a contextual preview hook
only; security, approval, and permission policy remain outside the memory
benchmark. It must also test that AIppocampus stays quiet when the model
already has the relevant context; continuity hints are a scarce prompt budget,
not a reason to repeat everything the agent should already know.

### Hook Stage Coverage

Each case should state which hook stage is under test:

| Stage | Expected Track D behavior |
|---|---|
| `UserPromptSubmit` | Creates a correction activation event and, when appropriate, a hot anchor. |
| `PreToolUse` | Emits no output unless an active anchor is relevant to the pending tool call; never acts as a permission gate. |
| `PostToolUse` | Captures sanitized tool evidence and links it to an open correction window. |
| `SubagentStart` | Propagates only task-relevant active anchors into delegated work. |
| `SubagentStop` | Reconciles delegated claims, transcript refs, and anchor adoption or contradiction. |
| `Stop` | Captures final claim/adoption state and enqueues detached adjudication. |
| `PreCompact` | Flushes open correction windows and anchor refs before context rewrite. |
| `PostCompact` | Rehydrates anchors only when visibility changed or horizon loss occurred. |

### Case Families

`should_anchor_after_compaction` cases:

- user corrects an agent's wrong assumption, the agent later adopts it, and a
  post-compaction continuation depends on that correction
- user rejects a failed implementation route, later work succeeds through a
  different route, and the old route should not be retried
- user narrows scope or definition of done, long tool work follows, and the
  final continuation should still honor the narrowed scope
- user corrects a benchmark or docs interpretation, and the later answer should
  carry the corrected distinction rather than the older summary
- an active correction is propagated into a subagent and reconciled after the
  subagent returns

`should_not_anchor` cases:

- the correction is still visible in the current prompt window, so repeating it
  would be current-thread echo noise
- the same anchor was already injected in the current topic epoch and no
  contradictory action is pending
- the anchor is true but not actionable for the next prompt or tool call
- the correction is unrelated to the current workspace or active task
- the correction was explicitly superseded by a later user turn
- the user correction is refuted by code, tests, tool output, or later clean
  source
- `PreToolUse` sees an unrelated command and correctly emits no memory context

`should_confirm_when_relevant` cases:

- source evidence is insufficient to decide whether the user correction was
  valid
- the correction was local to a branch, task, or one-off experiment and may be
  stale
- semantic adjudication disagrees with deterministic evidence signals

### Required Inputs

Case specs should bind labels to source-backed events, not generated summaries:

- user correction turn source ref
- assistant claim or route being corrected, when available
- hook stage under test and event id
- post-work outcome source ref or closeout source ref
- optional verification evidence: tests, changed files, docs, tool input/output,
  or subagent transcript refs
- simulated context state: `visible`, `post_compaction`, or `horizon_lost`
- expected adjudication: `valid_adopted`, `valid_ignored`, `refuted`,
  `superseded`, `local_only`, or `uncertain`

### Metrics

Required metrics:

- correction anchor recall after compaction
- false anchor rate for visible, unrelated, refuted, or superseded corrections
- stale route retry rate: refuted or rejected routes that resurface as guidance
- adjudication accuracy across valid/refuted/superseded/local/uncertain labels
- visibility-aware echo correctness: suppress when visible, inject when
  compaction removed the needed source
- anti-nag precision: suppress true-but-unnecessary reminders that do not
  change the next likely action
- repeated-anchor rate within a topic epoch
- hook stage correctness: each event emits only the allowed activation,
  evidence, propagation, closeout, or rehydration artifact for that stage
- `PreToolUse` silence rate for unrelated tool calls
- source fidelity for injected anchors
- confirmation correctness for uncertain cases
- privacy breach rate and raw prompt leakage rate

Initial targets:

- privacy breach rate: `0`
- raw prompt leakage rate: `0`
- false anchor rate for refuted corrections: `0`
- `PreToolUse` false intervention rate for unrelated tool calls: `0`
- repeated-anchor rate for visible or recently injected context: less than `2%`
- correction anchor recall after compaction: at least `85%`
- stale route retry rate: less than `2%`
- uncertain cases routed to confirmation or low-confidence working memory:
  at least `90%`

These targets should tighten after private real-history correction packs expose
the natural failure distribution.

### Runner Shape

The first Track D runner should be deterministic and synthetic:

- fixture threads with correction/outcome events and simulated compaction
  states
- fixture hook envelopes for `UserPromptSubmit`, `PreToolUse`, `PostToolUse`,
  `SubagentStart`, `SubagentStop`, `Stop`, `PreCompact`, and `PostCompact`
- mocked semantic adjudication for valid, refuted, superseded, local-only, and
  uncertain cases
- no live model dependency in CI
- sanitized reports that hash case ids and never emit raw correction text

The broader private runner can later use real-history correction packs and an
optional live dream-worker adjudication slice. Live adjudication results must
remain separate from deterministic event-capture and source-fidelity metrics so
model variance does not hide continuity regressions.
