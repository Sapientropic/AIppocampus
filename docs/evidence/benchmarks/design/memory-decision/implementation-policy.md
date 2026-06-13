# Memory Decision Benchmark Implementation Policy

Role: extracted detail page.
Status: current detail under the canonical memory-decision benchmark entrypoint.

This file preserves detail split out of
[`../memory-decision-benchmark-plan.md`](../memory-decision-benchmark-plan.md).
Keep current reader routing and cross-track summary in the entrypoint; keep
deep methodology, runner notes, and implementation detail here.

## Deterministic Boundary Tests

Routing thresholds and simple policy tables should stay in unit tests, not
benchmarks. Add parameterized tests for:

- `route_candidate()` thresholds by candidate type, confidence, ref count, and
  thread count
- `match_working_memory()` project-scope and concrete-term behavior
- prompt-hook suppression of ordinary coding prompts
- semantic-gate redaction and secret hard blocks
- weak deictic prompts that may scent but must not force evidence
- life/lifecycle and other substring traps

These tests are the P0 guardrail. They should be fast, deterministic, and part
of normal CI.


## Case Generation Policy

LLMs may help generate prompt surfaces, but not truth labels.

Rules:

- The expected label and source refs come from a checked case spec.
- The generator prompt must not include internal trigger lists such as recall
  triggers or code-surface cue tables.
- If the tested path uses a live semantic model, the prompt generator must be a
  different model family/provider.
- Generated prompts should mimic fragmented human phrasing, not benchmark
  prose.
- Track D labels must come from checked correction/outcome event specs, not from
  a model deciding whether its own generated correction was valid.
- At least a small human-reviewed sample should be audited before treating a
  generated case set as useful.
- Store private real-history case packs outside git; only sanitized aggregate
  reports belong in public docs.
- Public conversation-corpus adapters, manifests, and small curated public
  samples live in `benchmark_corpus/`. Local caches, generated clean-source
  outputs, large full-dataset downloads, and private exports stay out of git
  unless a future change deliberately promotes a public subset with provenance.


## Report Shape

Default JSON reports should include:

- schema version and benchmark kind
- git/worktree metadata when safe
- config, seed, budget, and model-mode fields
- aggregate metrics
- benchmark framing when a report compares memory, reset, oracle, or no-harm
  control arms
- per-case sanitized ids and labels
- hashed thread/case ids for private runs
- no raw prompt text, snippets, titles, source refs, or absolute paths unless an
  explicit local-debug flag is set

Each report should also include `cannot_claim` entries. A benchmark can prove a
selected slice passed; it cannot prove all future memory decisions are correct.


## Implemented Files

Implementation should reuse existing benchmark/test patterns where possible.

Scripts:

- `benchmarks/aippocampus/benchmark_memory_decision_gate.py`
- `benchmarks/aippocampus/benchmark_source_evidence_retrieval.py`
- `benchmarks/aippocampus/source_evidence/`
- `benchmarks/aippocampus/benchmark_payload_fidelity.py`
- `benchmarks/aippocampus/benchmark_compaction_continuity.py`
- `benchmarks/aippocampus/benchmark_live_semantic_gate.py`
- `benchmarks/aippocampus/benchmark_knowledge_pollution.py`
- `benchmarks/aippocampus/benchmark_field_continuity.py`
- `benchmarks/aippocampus/benchmark_hippocampal_hard_negatives.py`
- `benchmarks/aippocampus/benchmark_cognitive_portrait.py`
- `benchmarks/aippocampus/benchmark_suite.py`
- `skills/aippocampus/scripts/aippocampus_runtime/knowledge/capability_contract.py`
- `skills/aippocampus/scripts/agency_affordance.py`

Tests:

- `tests/aippocampus/test_routing_boundaries.py`
- `tests/aippocampus/test_benchmark_memory_decision_gate.py`
- `tests/aippocampus/test_benchmark_source_evidence_retrieval.py`
- `tests/aippocampus/test_benchmark_payload_fidelity.py`
- `tests/aippocampus/test_benchmark_compaction_continuity.py`
- `tests/aippocampus/test_benchmark_live_semantic_gate.py`
- `tests/aippocampus/test_benchmark_knowledge_pollution.py`
- `tests/aippocampus/test_benchmark_field_continuity.py`
- `tests/aippocampus/test_benchmark_hippocampal_hard_negatives.py`
- `tests/aippocampus/test_benchmark_cognitive_portrait.py`
- `tests/aippocampus/test_benchmark_suite.py`
- `tests/aippocampus/test_agency_affordance.py`

Structured portrait command:

```powershell
python benchmarks\aippocampus\benchmark_cognitive_portrait.py
```

Knowledge pollution/privacy command:

```powershell
python benchmarks\aippocampus\benchmark_knowledge_pollution.py
```

Field Continuity command:

```powershell
python benchmarks\aippocampus\benchmark_field_continuity.py --json
```

Track D command:

```powershell
python benchmarks\aippocampus\benchmark_compaction_continuity.py
python benchmarks\aippocampus\benchmark_suite.py
```

The implemented Track D runner is deterministic and synthetic. It covers the
planned hook-stage expectations, simulated `visible`, `post_compaction`, and
`horizon_lost` states, synthetic correction/outcome event chains, same-epoch
repeated-anchor suppression, and mocked adjudication statuses. The runner now
reuses the `correction_reconsolidation.py` status and active-anchor gate so the
benchmark does not drift from the runtime prototype. The #311 runtime slice adds
an opt-in source-ref-gated host-event adapter and aggregate-only private-history
bucket report; it still does not prove default live Codex hook writes, live
semantic adjudication quality, or broad private real-history compaction
survival.

The Track D `ok` gate is stricter than the diagnostic counters alone:
`ok=false` whenever `correct_count < total_cases`, even if no named regression
counter fired. Limited `--cases` runs remain allowed, but their report carries
`status=diagnostic_subset`, `quality_gate_ok=false`, and
`diagnostic.sufficient_quality_evidence=false`. Reports also include a
`coverage_density` block for the hook-stage x compaction-state x adjudication
matrix so sparse combination coverage stays visible instead of being hidden by
the broad axis lists. High-risk post-compaction horizon-lost cells are split
out as missing or sparse diagnostics so stale/superseded/refuted/uncertain
anchor behavior remains easy to audit.

Track D reports now also include `benchmark_framing` and
`metrics.no_harm_when_spec_complete` for the #453 boundary. The synthetic
complete-spec case expects memory silence: if the current prompt already
contains the full correct task context, a fresh-context/spec-loop win is
expected and should be reported as no-harm evidence, not as AIppocampus losing
the primary #378 endpoint.

Reusable existing pieces:

- `EvalCase`, sanitized result stubs, CLI/JSON style, and result summarization
  patterns from `benchmark_fts5_recall.py`
- source-evidence selection and privacy boundary patterns from
  `smoke_source_evidence_recall_eval.py`
- semantic-gate mocks from `test_semantic_recall_gate.py`
- working-memory factories and routing checks from
  `test_memory_candidate_router.py`
- prompt-hook boundary fixtures from `test_aippocampus_prompt_hook.py`

Public memory-pain fixture source map:

- `docs/research/memory-system-pain-taxonomy.md` is now the checked source map
  for Mem0-style pollution, Graphiti/Zep-style scale/cost, Letta-style
  compaction, and HN pattern-learning pain points.
- #27 fixtures are implemented in the synthetic Track A/C benchmark surface via
  `memory_pain_fixtures` output from `benchmark_memory_decision_gate.py` and
  `benchmark_payload_fidelity.py`. They cover public-safe negative families for
  write-time pollution, recalled-context echo loops, fabricated profiles,
  transient task state, deterministic-vs-fuzzy memory separation, metadata
  round-trip boundaries, large-document no-foreground-LLM scale pressure,
  invalid structured extraction, and a Track D seed for compaction continuity.
- These fixtures are boundary evidence, not competitor-comparison evidence. They
  prove unsupported synthetic prompts are skipped or downgraded to scent-only
  rather than emitted as source-backed evidence.


## Rollout Plan

P0: deterministic boundary tests and shared case schema.

P1: Track A with public synthetic fixtures, mocked semantic gate, and the
public ShareGPT coding clean-source sample. The synthetic slice stays CI-safe;
the ShareGPT slice is a local/public-corpus baseline command because the full
clean-source output is large and gitignored.

P2: thin Track C payload-fidelity runner over the same fixtures. Keep it
deterministic and privacy-focused.

P3: Track B unification, reusing existing FTS5 and source-evidence evaluation
logic so retrieval regressions sit beside decision regressions. Initial wrapper
is implemented. The broader deterministic source-label slice now uses a 100
case max / 50 case min default and clears the target. After the bounded
2026-05-29 private semantic-sidecar refresh, the semantic-sidecar-required slice
also clears the selected-source target at 100 cases / 97 top-5 hits; remaining
misses are ranking misses, not selected-case scarcity.

P4: one-command baseline suite. Implemented as `benchmark_suite.py`; current
status records known gaps rather than treating them as failures to run the
baseline.

P5: Track D compaction-continuity runner. Implemented as the deterministic
synthetic `benchmark_compaction_continuity.py` runner with correction/outcome
fixtures, mocked semantic adjudication, and simulated
visible/post-compaction/horizon-lost states. The #65 deterministic
correction-reconsolidation helper now owns append-only event rows, adjudication
candidates, and active-anchor rendering; live hook wiring and private
real-history packs remain future work.

P6: coding decision-event extraction. The first deterministic slice is
implemented in `skills/aippocampus/scripts/coding_decision_events.py`: it reads
clean-source messages, emits source-backed staging `decision_event` candidates,
keeps broad/branch-local decisions as `needs_confirmation` or `local_only`, and
uses the correction-reconsolidation anti-nag gate before rendering at most one
compact `coding_continuity_ticket`. Broader real-history review and host-agent
intervention timing remain future work.

P7: agency affordance tickets. The first deterministic slice is implemented in
`skills/aippocampus/scripts/agency_affordance.py`: it normalizes conservative
source-backed affordances from cognitive-map-like rows, correction windows,
ambient recall cards, dream outputs, coding tickets, unfinished tasks, and
scheduled revisits; selects at most one foreground ticket and a bounded
backstage set per topic epoch; suppresses repeated, visible, thin, or
matched-terms-only reminders; and records append-only outcome feedback rows. A
deterministic replay smoke now exercises show/hold/suppress host-timing policy,
visible-source suppression, recent negative-feedback suppression, and
source-backed cross-host duplicate keys. Live host timing, real annoyance
calibration, live multi-host delivery, and any autonomous push-forward behavior
remain future work.

P8: local private real-history case generation. Reports must stay sanitized and
aggregate-only by default.

P9: optional live semantic-model slices for release verification. The first
opt-in live semantic-gate runner is implemented; broader scheduled runs remain
manual verification jobs, not required CI gates.

P10: optional external baseline adapters. Only start this after AIppocampus has a
stable internal decision benchmark; otherwise "competitor comparison" will
measure mismatched product semantics.


## Acceptance Criteria

The suite is credible when it catches these regressions:

- an ordinary coding task starts surfacing old memory
- a fuzzy continuation prompt gets source evidence instead of quiet scent
- explicit quote/source requests stop returning evidence
- parked or private working memory appears in foreground payload
- semantic sidecar labels are treated as facts without source refs
- generated benchmark reports leak private wording or local paths
- retrieval misses are incorrectly reported as decision failures, or stale-index
  misses are incorrectly reported as lexical ranking failures
- a user correction that was adopted before compaction disappears from the
  continuation context
- a refuted or superseded correction is promoted as an active anchor
- current-thread echo suppression hides a correction after compaction/horizon
  loss, or repeats a correction that is still visible

If the benchmark cannot catch those failures, it is not yet measuring the thing
AIppocampus exists to protect.
