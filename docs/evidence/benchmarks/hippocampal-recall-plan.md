# Hippocampal Recall-Discrimination Benchmark Plan

Status: design intake for P1. This document defines the first executable
benchmark layer for H1 pattern completion and H2 pattern separation. It is not
yet measurement evidence, publication evidence, or proof of live model quality.

Related methodology umbrella: #216.

AIppocampus already has strong benchmark coverage for recall routing, source
retrieval, payload fidelity, compaction continuity, and VCS hard-event memory.
Those tracks mostly ask whether the system should search and whether it can
find the right source. This plan adds the next layer: whether a source-backed
memory system can recover from degraded cues while still separating similar,
superseded, or cross-context memories.

The hippocampal language here is an engineering lens, not a biological claim.
The product contract remains source-backed continuity: no answer should become
evidence until the system can reopen the supporting clean source.

## P1 Goal

Build one benchmark, `Hippocampal Recall-Discrimination`, with two axes:

- H1 pattern completion: partial, degraded, cross-language, structural, or time
  cues should reopen the correct source pack when enough evidence exists.
- H2 pattern separation: similar memories, stance reversals, homonyms, and
  superseded conclusions must not collapse into one vague "we discussed this"
  memory.

P1 should be synthetic-first and public-safe. Real-history validation follows
only after the schema, runner, and scoring contract are stable.

## What This Adds Beyond Existing Tracks

Existing Tracks A-D and the VCS benchmark stay valuable. This benchmark is a
layer on top, not a replacement.

| Existing surface | Current question | P1 adds |
| --- | --- | --- |
| Track A gate | Should the system skip, scent, or evidence? | Whether degraded cues calibrate to scent/evidence correctly. |
| Track B retrieval | Can a valid query find the expected source? | Whether almost-invalid cues can reopen the expected source. |
| Track C payload | Is surfaced payload faithful? | Whether degraded recall avoids invented details. |
| Track D compaction | Does a correction survive compression? | Whether compressed continuity still separates similar memories. |
| VCS hard events | Can source-backed event memory beat surface matching? | General conversation memory completion and discrimination. |

## Axes

### Degradation Level

| Level | Meaning | Example |
| --- | --- | --- |
| D0 | Full keyword query | "React component tree memo optimization plan" |
| D1 | Core noun removed | "That optimization plan, the one about the tree" |
| D2 | Metaphor or synonym | "How did we stop that tree from rendering again and again?" |
| D3 | Context or affect only | "You made a surprising performance call there" |
| D4 | Cross-language fragment | Chinese memory queried with two or three English fragments |
| D5 | Structure-only cue | "The answer with a code block and a warning" |
| D6 | Time cue | "The one from around two months ago, late at night" |

### Interference Density

| Level | Meaning |
| --- | --- |
| I0 | Unique target, no similar memory |
| I1 | One similar memory from the same topic |
| I2 | Two or three similar memories from repeated discussion |
| I3 | Stance reversal on the same topic |
| I4 | Cross-context same-token confusion |
| I5 | Superseded conclusion where an older conclusion was replaced |

Every benchmark case is a `(D_level, I_level)` pair. P1 must report the full
completion-separation matrix, not only an aggregate score.

## Fixture Plan

### Phase 1: Synthetic Public Fixture

Create 50 hand-authored memory scenes. Each scene has:

- one target memory with stable synthetic source refs
- zero to five distractor memories, chosen by the requested `I_level`
- seven degraded queries, D0-D6
- expected target source refs
- expected decision level: `evidence`, `scent`, or `skip`
- explicit ambiguity policy
- forbidden claims that must never appear in a recalled payload
- public-safe license metadata

This produces 350 initial cases. The fixture should be committed only if it is
synthetic and redistributable, for example under a CC0-compatible project-local
fixture license.

### Cell Density Floor

The D x I matrix has 42 cells. A 50-scene / 350-case fixture averages only
eight or nine cases per cell, and real fixture authoring will not be perfectly
uniform. Some cells, such as D6+I4 time-only cross-context cues, are inherently
hard to author and should not be overclaimed from two or three cases.

Cell-level reporting rules:

- P1 density floor: at least 5 cases per `(D_level, I_level)` cell before that
  cell can be reported as an independent metric.
- Cells with fewer than 5 cases must be marked `diagnostic_only`.
- D-level and I-level aggregate metrics may still be reported when individual
  cells are sparse, as long as the report exposes the sparse cells.

Fixture priority if 50 scenes cannot fill every cell:

- First fill D0-D3 x I0-I5 with at least 5 cases per cell, because these are
  the most common user-facing degraded recall situations.
- Allow D4-D6 cells to remain sparse in P1, but mark them exploratory until
  structural, cross-language, and time-window search support improves.

### Degradation Path Expectations

The benchmark should make capability gaps explicit instead of treating every
degradation level as equally reachable by the current search path.

| Levels | Expected current behavior |
| --- | --- |
| D0-D2 | Existing text plus semantic retrieval should handle many cases. |
| D3-D4 | Semantic gate and reranking may help, but recall should be treated as partially supported and still fragile. |
| D5-D6 | Existing FTS5 plus semantic rerank is likely weak because structure-only and time-only cues need structure indexes or time-window filtering. Low recall plus high skip is an expected baseline, not a benchmark defect. |

Future improvements for D5/D6 should come from adding searchable structure and
time dimensions, not from relaxing source-evidence scoring.

### D5/D6 Search Dimension Implementation

D5/D6 are not a capability ceiling. They are mostly an indexing gap in the
current text-first retrieval path.

Recommended implementation:

- Keep FTS5 focused on searchable text and BM25-style candidate generation.
- Add a source-backed `message_features` sidecar table keyed by message id and
  source ref. Hot scalar fields should be normal columns or generated columns,
  not only a blob of JSON.
- Store deterministic structure features such as `has_code_block`,
  `code_languages_json`, `has_warning`, `has_list`, `has_table`,
  `heading_count`, `line_count`, `role`, `phase`, and `is_final`.
- Add partial or normal indexes for hot filters, for example code-block,
  warning, list/table, final-answer, and role/phase combinations.
- Keep `metadata_json` for cold or experimental attributes, but do not make
  JSON scanning the hot path for D5.
- Add a time sidecar or indexed columns for message timestamp, thread
  created/updated time, and active timestamp. If `last_active_at` is available
  in a generated registry, use it; otherwise derive an active timestamp from
  message timestamps and registry `updated_at`.
- Parse temporal cues into `(window_start, window_end, confidence, cue_kind)`
  before retrieval. Exact cues can filter; vague cues should act as a ranking
  prior rather than a hard filter.
- Combine text, structure, and time lanes with a simple reciprocal-rank or
  weighted-prior fusion, then require source reopen before evidence.

This is preferable to stuffing all metadata into FTS5 columns. FTS remains good
at text; B-tree/generated/partial indexes are better for structure and time.

### Phase 2: Private Real-History Annotation

After the runner is stable, sample 20 private real-history scenes from
registered clean-source threads. Candidate scenes should include:

- themes discussed at least three times
- cross-thread decision evolution
- at least one naturally degraded recall prompt from the user
- at least one distractor that would fool lexical or embedding-only search

Raw private text, local source paths, private registry ids, and unsanitized
snippets must stay out of committed artifacts. Public evidence reports can
include only aggregate metrics, hashed local refs if needed, and cannot-claim
boundaries.

Annotation cost estimate: 15-30 minutes per scene. Start with 20 scenes to test
whether the synthetic fixture predicts real-history behavior.

## Schema Contract

The fixture schema should live in
`benchmarks/aippocampus/hippocampal_fixture_schema.py` and validate JSONL rows
like this:

```json
{
  "dataset_id": "hippocampal_synthetic_v1",
  "scene_id": "react_tree_memo_v1",
  "case_id": "react_tree_memo_v1__d2_i3",
  "degradation_level": "D2",
  "interference_level": "I3",
  "query": "How did we stop that tree from rendering again and again?",
  "expected_decision": "evidence",
  "expected_source_refs": ["source:react_tree_memo:target"],
  "acceptable_scent_refs": ["source:react_tree_memo:target"],
  "distractor_source_refs": ["source:react_tree_memo:old_stance"],
  "forbidden_claims": ["The old stance is still current"],
  "ambiguity_policy": "single_target",
  "truth_source": "human_authored_fixture",
  "scorer_allowed_inputs": ["query", "candidate_refs", "source_reopen_result"]
}
```

Recommended top-level concepts:

- `scene`: target plus distractor memory bundle
- `query_case`: one degraded query and expected behavior
- `truth_source`: how labels were produced
- `ambiguity_policy`: whether a single target, multi-candidate scent, or skip
  is the correct behavior
- `forbidden_claims`: content that would indicate confabulation or stale-source
  overconfidence
- `source_reopen_contract`: which refs must reopen and which payload fields are
  allowed to be checked

## Ground Truth Rules

P1 must avoid the semantic-sidecar circularity risk from older benchmark work.

| Truth source | Allowed use | Claim strength |
| --- | --- | --- |
| Human-authored synthetic fixture | H1/H2 baseline and gates | High for contract behavior |
| Real conversation with human labels | Real-history H1/H2 validation | High but private and expensive |
| Real conversation with extracted structure plus review | H3/H4 later | Medium until adjudicated |
| LLM-generated queries with human-verified labels | Natural degradation expansion | Medium |
| LLM labels scored by the same or similar LLM | Diagnostics only | Not a primary metric |

Rules:

- The truth-label source and the system being evaluated must be independent.
- If AIppocampus recall is being measured, truth labels come from humans or a
  frozen hand-authored fixture.
- If dream consolidation is being measured, truth comes from the frozen
  pre-consolidation fixture and source state.
- A model may generate candidate phrasings, but a human or frozen fixture owns
  the expected label.
- Do not let one external model act as both label generator and score judge for
  a primary metric.

## Scoring

### Main Metrics

- `recall_accuracy_by_degradation`: top-5 hit rate for D0-D6.
- `separation_accuracy_by_interference`: precision by I0-I5.
- `completion_separation_curve`: D x I matrix showing where degradation causes
  confusion.
- `confabulation_rate`: returned content not present in the reopened source or
  explicitly forbidden by the fixture.

### Scent Scoring Boundary

Scent is intentionally softer than evidence, but it still needs separation
accounting. Score scent in three layers:

- `scent_hit`: the scent includes the target ref. This is fully correct.
- `scent_distractor`: the scent includes only distractor refs and omits the
  target. This is a `partial_miss`: related memory was activated, but the target
  was not recovered.
- `scent_both`: the scent includes both target and distractor refs. This counts
  as a hit, but records `low_separation` for the relevant I-level.

`scent_precision` should count only `scent_hit` in the numerator.
`scent_distractor` should count as a separation failure but not as a pure scent
precision failure, because it did activate related memory rather than unrelated
noise.

### Calibration Metrics

These are part of P1, not a later track.

- `scent_precision`: when the system emits scent, source validation later finds
  a relevant memory.
- `evidence_confidence_accuracy`: high-confidence evidence is actually correct.
- `overconfidence_rate`: expected scent but emitted evidence.
- `underconfidence_rate`: expected evidence but emitted scent.
- `calibration_error`: optional bucketed reliability error over confidence
  scores once confidence buckets are available.

### Boundary Metrics

- `source_reopen_success`: degraded cue leads to the expected source pack and
  source verification succeeds.
- `minimum_sufficient_cue`: shortest or weakest cue that still triggers correct
  recall.
- `abstention_accuracy`: ambiguous or unsupported prompts correctly remain
  scent or skip instead of forced evidence.
- `cost_per_case`: elapsed time, source reopen count, candidate count, model
  calls, and tokens where available.

Cost belongs in the score report because pattern completion should not be
implemented as "deep search everything every time".

## Gates

Must pass before P1 can be used as release evidence:

- `confabulation_rate = 0`
- D0 `recall_accuracy >= 0.95`
- I3-I5 `separation_accuracy >= 0.90`

Targets worth claiming if reached:

- D2 `recall_accuracy >= 0.70`
- D3+ confusion growth less than 2x relative to D0-D2
- `scent_precision >= 0.80`

Exploratory only in the first report:

- D4-D6 recall accuracy
- minimum sufficient cue distribution
- human baseline, if later collected

## Baselines

At minimum, P1 should report:

- `full_query_baseline`: D0 performance using the normal system path.
- `keyword_only_baseline`: simple keyword extraction plus FTS5.
- `random_retrieval_baseline`: floor control.

Useful later controls:

- overactive all-evidence arm
- closed-book arm with source refs removed
- semantic-only arm without source reopen
- stale-source arm where old and current conclusions coexist

## Public Reproducibility And Cross-System Claim Gate

To claim this as one of the hardest memory-system benchmarks, the project needs
three additional deliverables beyond the design itself:

- P1 fixture and runner must be publicly reproducible from a clean clone, with
  fixed seeds, sanitized reports, no private registry dependency, and a single
  documented command.
- The benchmark needs adapter arms for AIppocampus, baseline RAG, keyword-only,
  overactive, closed-book, and selected external memory systems such as Mem0,
  Zep, and Graphiti when their licenses and install paths are compatible.
- A dated comparison table must show where systems that do well on ordinary
  retrieval memory benchmarks drop on H1/H2/H5 dimensions: degraded cues,
  interference, source reopen, calibration, forgetting, and consolidation
  benefit.

Until those exist, the honest external claim is "designed to be among the most
adversarial source-backed memory benchmarks", not "the hardest in industry".

## Anti-Gaming Controls

- Do not build degraded queries from the same trigger alias registry used by the
  router.
- D1-D6 query writers, whether human or model-assisted, must not see
  AIppocampus internal cue lists, trigger aliases, or router term registries.
- Ideally, degraded queries should be written by people unfamiliar with the
  implementation, or by an independently prompted model whose outputs are then
  human-verified.
- Shuffle distractor order and source ids during scoring.
- Include lexical near-misses and same-token cross-context cases.
- Include stale/superseded cases where the older memory is more keyword-rich
  than the current answer.
- Include canary forbidden claims and fail the case if they appear in evidence.
- Report case-family scores so one easy family cannot hide a hard-family
  collapse.

## Output Boundary

The benchmark scores the memory layer's ability to route to source, not the
assistant's ability to improvise a reconstructed answer.

Correct sequence:

1. degraded cue
2. candidate recall decision: skip, scent, or evidence
3. source pack selection
4. source reopen validation
5. only then, optional payload fidelity scoring

If source reopen fails, evidence must fail even when the natural-language answer
sounds plausible.

## Ambiguity And Abstention

Some degraded cues are genuinely ambiguous. The fixture must not force every
query into one target evidence answer.

Supported policies:

- `single_target`: one expected target should be evidence.
- `multi_candidate_scent`: several memories are plausibly related; scent is
  correct, evidence is overconfident.
- `unsupported_skip`: no source-backed memory is sufficiently supported.
- `source_required`: the system may scent but cannot evidence until a specific
  source reopens.

This keeps P1 aligned with the existing three-class gate instead of rewarding a
system that turns all fuzzy cues into evidence.

## Forgetting And Extinction

Forgetting is not a separate P1 track, but P1 must include enough I5 cases to
make stale conclusions visible. H5 should later turn this into explicit
consolidation and extinction scoring:

- `superseded_detection`: old conclusions are demoted when a later source
  replaces them.
- `explicit_forget_compliance`: user-requested forgetting removes the item from
  normal recall surfaces.
- `emotional_decay`: one-off emotional states do not become durable preference.
- `experiment_cleanup`: unfinished exploratory branches leave active recall
  after they stop being useful.
- `false_forgetting_rate`: useful memory was wrongly demoted.

False forgetting is more dangerous than merely forgetting, so it must be
reported beside any extinction win.

## H5 Consolidation Handoff

H5 should run immediately after the first H1/H2 baseline exists:

1. freeze the H1/H2 fixture and scoring labels
2. run H1/H2 without consolidation
3. run the dream or consolidation worker
4. rerun the same H1/H2 cases
5. compare deltas without relabeling cases after the consolidation run

H5 should measure:

- new cross-thread associations found after consolidation
- noise pruning and stale-memory demotion
- pattern extraction for user preferences, repeated questions, and open loops
- separation improvement under dense interference
- overgeneralization and false-forgetting regressions
- compute and token cost per improvement

Controls should include no-consolidation, random consolidation, and simple
summary-only consolidation before claiming AIppocampus-specific benefit:

- `no_consolidation`: rerun the frozen H1/H2 cases without changing the memory
  surface.
- `random_consolidation`: randomly choose source-ref pairs and create the same
  number of cross-thread associations as the AIppocampus consolidation run,
  without using semantic, time, or topic relatedness.
- `simple_summary_consolidation`: generate or use one summary per conversation
  and search over summaries instead of clean source or structured associations.

## Implementation Slices

Proposed files:

- `benchmarks/aippocampus/hippocampal_fixture_schema.py`
- `benchmarks/aippocampus/build_hippocampal_fixture.py`
- `benchmarks/aippocampus/benchmark_hippocampal_recall.py`
- `tests/aippocampus/test_benchmark_hippocampal_recall.py`
- `benchmark_corpus/hippocampal_fixtures/hippocampal_synthetic_v1.jsonl`
- `docs/evidence/benchmarks/hippocampal-recall-DATED.md`

Implementation guidance:

- Reuse Track A's decision routing path where possible.
- Reuse Track B's hit-rate, MRR, report-sanitization, and source-ref handling
  utilities where possible.
- Keep new logic in fixture design and D x I scoring, not in a novel scoring
  framework unless reuse becomes genuinely awkward.
- Keep the committed fixture synthetic and public-safe.
- Keep private real-history packs local or gitignored, with sanitized aggregate
  evidence only.

## Priority

P1:

- synthetic fixture schema and validation
- synthetic fixture builder
- runner and D x I scoring report
- calibration and confabulation accounting
- keyword/random/full-query baselines
- public reproducibility command and sanitized dated report
- docs and mirror unit tests

P2:

- private real-history annotation protocol
- 20-scene private validation pack
- human-label adjudication workflow
- seeded expansion of natural degraded queries with human verification
- structure and time search dimensions for D5/D6

P3:

- H5 consolidation before/after evaluation
- explicit forgetting/extinction cases
- adapter arms for external memory systems and baseline controls
- cross-system comparison table for H1/H2/H5
- public-safe dated measurement report

Later tracks:

- H3 temporal binding after timeline/question tracking is stable enough to
  score before/after, causal-chain, interval, evolution, and cross-timeline
  questions.
- H4 relational inference after concept graph and association extraction can
  expose source-backed relation edges with per-step fidelity.

## Open Risks

- Synthetic cases can overfit to the author's phrasing. Mitigation: human review
  of labels, independent degraded-query writers, and real-history validation.
- D5/D6 may be too weak for evidence. Mitigation: allow scent or skip as correct
  labels through `ambiguity_policy`.
- Real-history packs are expensive and private. Mitigation: publish only
  aggregate metrics and sanitized cannot-claim boundaries.
- Calibration needs confidence values that some paths may not expose yet.
  Mitigation: start with decision-level over/underconfidence and add bucketed
  confidence once available.
- H5 can self-prove if consolidation changes labels or source truth after the
  first run. Mitigation: freeze fixture labels and source state before dream
  workers run.
