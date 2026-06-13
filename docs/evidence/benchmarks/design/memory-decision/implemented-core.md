# Memory Decision Implemented Core

Role: extracted implemented-slice detail page.
Status: current detail under [`implemented-slices.md`](implemented-slices.md).

## Current Implemented Slice

The first landing slices cover P0/P1/P2/P3 and a one-command baseline suite:

- `tests/aippocampus/test_routing_boundaries.py` fixes deterministic
  routing and working-memory boundary expectations.
- `benchmarks/aippocampus/benchmark_memory_decision_gate.py` runs the Track
  A synthetic and ShareGPT-coding gate-decision benchmark against the real
  `assess_prompt()` path.
- `tests/aippocampus/test_benchmark_memory_decision_gate.py` checks
  three-class metrics, report sanitization, and explicit private-debug opt-in.
- `benchmarks/aippocampus/benchmark_payload_fidelity.py` runs the thin Track
  C synthetic payload-fidelity benchmark against the final `context_for_hook()`
  output.
- `tests/aippocampus/test_benchmark_payload_fidelity.py` checks payload
  metrics, source-fidelity accounting, parked-memory protection, and sanitized
  report defaults.
- `benchmarks/aippocampus/benchmark_source_evidence_retrieval.py` remains the
  Track B CLI/report facade, with track-owned helpers under
  `benchmarks/aippocampus/source_evidence/`. It reuses the existing FTS5
  source-line benchmark and selected source-evidence recall evaluation, and it
  also has opt-in ShareGPT public-corpus, bounded public semantic-sidecar, and
  LoCoMo/LongMemEval V1 standard retrieval-QA adapters. Reports carry a Track B
  query-origin taxonomy and separate source-derived sanity arms from
  non-source-derived question-text arms so FTS5/source-label checks cannot be
  over-read as natural user-query recall.
- `benchmarks/aippocampus/benchmark_coding_decision_shadow.py` runs the
  deterministic coding-agent decision-shadow tracks A-E from
  `docs/research/agent-coding-context-analysis.md`: original source refs,
  rejected-route warnings, compaction boundary preservation, relevant
  historical-decision selection without a repo map, and anti-nag suppression.
  Its default report is sanitized and carries `cannot_claim` boundaries for
  private real-history lift, full code-index navigation quality, and live host
  timing.
- `tools/aippocampus/smoke/smoke_e2e50_seed_candidates.py` is the #279
  candidate-seed scanner for the future E2E50 silent-constraint benchmark. It
  scans registered clean-source `messages.jsonl` plus the behavior
  `events.jsonl` lane for long threads with compaction evidence, early-window
  binding/rejected-route/temporary/superseded signals, behavior-backed failure
  events, and later-window drift. Its output is `candidate_seed_discovery_only`:
  hash/count-only candidate rows, case-family guesses, and reviewer checklists.
  Its deterministic unittest is included in the `benchmark-smoke` lane so fresh
  PRs keep the scanner contract alive. It does not score agent behavior, publish
  private text/paths/ids, or claim #279 benchmark quality before manually
  annotated cases and the shared benchmark methodology are ready.
  The 2026-06-10 #1086 follow-up adds an annotation-summary path for ignored
  private/local review artifacts and records the current blocker in
  `e2e50-private-local-seed-followup-2026-06-10.md`: wide candidate discovery
  reaches 23/20, but retained/control annotation remains 7/20.
- `benchmarks/aippocampus/benchmark_e2e50_silent_constraint.py` is the
  #279/#1154 public-safe behavior-pack scorer. It consumes hash/count-only
  behavior-code cases, reports deterministic rates for silent constraint
  survival, known-bad route avoidance, transient-concern extinction,
  superseded-currentness, scope-limited constraints, summary-overhang trap
  avoidance, no-remember negative precision, and
    source-reopen-before-risky-action. It scores a checked-in 50-case
    public-safe synthetic behavior pack with explicit `annotation_status` and
  `source_family` coverage. It keeps `quality_gate_ok=false`: this pack is the
  primary public executable path, while private/local retained-case scarcity is
  optional diagnostic evidence, not the main public blocker. Its deterministic
  unittest is included in `benchmark-smoke` to keep the scorer contract alive
  while private seed material remains local and source-reviewed.
  The 2026-06-10 #279 replay can also consume the scanner's sanitized private
  annotation summary through `--private-annotation-summary` and records the
  current private/local blocker in
  `e2e50-private-annotation-readiness-2026-06-10.json`; this is a readiness
  gate over aggregate counts, not behavior-quality evidence.
  The scorer also accepts optional `episode_chain` / `sequence_packet`
  evidence and bounded `cognitive_load` sidecars through
  `aippocampus_runtime.coding.sequence_packets`: those rows are scored as
  ordered read-model contracts and routing/caution metadata only, not as current
  validity facts, affect labels, or personality claims. The companion
  `aippocampus_runtime.coding.episode_arcs` slice builds deterministic coding
  Episode/Arc read-models and source-window reopen plans for #663; the schema
  and cannot-claim boundary live in
  `docs/architecture/coordination/episode-arc-read-models.md`.
- `benchmarks/aippocampus/benchmark_knowledge_pollution.py` runs the #517
  public-safe knowledge pollution and privacy-partition benchmark. It reuses
  the governed knowledge source/claim schema and high-risk answer gate, then
  adds one repo-internal `CapabilityContract` prototype for synthetic
  contract-review assistance.
- `benchmarks/aippocampus/benchmark_field_continuity.py` runs the #454 Field
  Continuity / Magic Moment Reproducibility contract slice and exposes an
  issue-local `issue_readouts.github_281` public-safe quality proxy. It converts the
  second-user field-report shapes from Discussion #428 into public-safe
  scenario-family fixtures, negative controls, hash-only private seed reporting
  rules, and claim-boundary metrics. It is a deterministic contract smoke, not
  real-history or live-model recall quality evidence.
- `benchmarks/aippocampus/benchmark_hippocampal_hard_negatives.py` runs the
  #244 H1/H2 hard-negative scoring-contract smoke. It validates a public-safe
  synthetic fixture for near-neighbor lures, unsupported speech,
  superseded-currentness traps, and surface-paraphrase lures, then reports the
  seven outcome categories and asymmetric discipline score without using a
  model judge, private history, or live retrieval.
- `tests/aippocampus/test_benchmark_source_evidence_retrieval.py` checks
  Track B report shape, diagnostic status, ShareGPT public-corpus case
  generation, public semantic-sidecar materialization, LoCoMo/LongMemEval source
  ref handling, #309 source-joined reranker bridge/collision diagnostics, and
  default privacy boundaries.
- `tests/aippocampus/test_benchmark_coding_decision_shadow.py` checks A-E
  track statuses, wrong-source evidence, visible-source suppression, stale
  authority, and explicit private-text debug boundaries.
- `tests/aippocampus/test_benchmark_knowledge_pollution.py` checks #517
  pollution/privacy metrics, sanitized default reports, source-reopen
  enforcement, and bounded contract-review prototype behavior.
- `benchmarks/aippocampus/benchmark_suite.py` runs the repeatable baseline
  suite across Track A, Track B, Track C, and the broader deterministic
  source-label diagnostic slice, with opt-in ShareGPT public Track B, standard
  retrieval-QA Track B, and live semantic-gate tracks. Its top-level
  `rate_estimates` summary collects the per-track binomial interval reports so
  public-readiness review can inspect uncertainty without walking every nested
  report.
- `benchmarks/aippocampus/shared/benchmark_statistics.py` owns the shared Wilson
  binomial interval helper used by benchmark reports. The helper is reporting
  infrastructure only: it does not make selected, synthetic, or biased samples
  representative.
- `benchmarks/aippocampus/benchmark_live_semantic_gate.py` runs the optional
  live semantic-gate slice over public ShareGPT coding clean-source cases. It
  uses the real prompt hook and configured DeepSeek-compatible backend, but
  emits only sanitized aggregate/case diagnostics.
- `tests/aippocampus/test_benchmark_suite.py` checks that the suite can
  capture a baseline even when Track B is diagnostic-only, while keeping
  `quality_gate_ok` separate from baseline capture.
- `tests/aippocampus/test_benchmark_live_semantic_gate.py` checks missing
  backend handling, sanitized report boundaries, and live semantic diagnostics.
- `benchmarks/aippocampus/benchmark_cognitive_portrait.py` runs the #70
  structured-text cognitive portrait benchmark. It builds a compact prompt from
  source-backed question/frontier/link findings, compares it with fuller
  clean-source injection, and reports compression, source fidelity,
  over-personalization risk, fixture-level cue equivalence, `claim_level`, and
  `sample_size_warning`. The current 3-prompt fixture is a `contract_smoke`, not
  empirical portrait-quality evidence.
- `tests/aippocampus/test_benchmark_cognitive_portrait.py` checks that the
  reusable portrait artifact keeps source refs/back-pointers, records quote
  fidelity loss, keeps private debug text opt-in, and exposes the small-sample
  cannot-claim boundary.
- `benchmarks/aippocampus/benchmark_question_aware_real_history.py` runs the
  #139 private real-history structural proxy. It selects source-backed
  question/frontier/link/theme rows when present, emits sanitized packs with
  hashed source refs by default, and reports pack selection, source-fidelity,
  term-coverage delta, token ratio, known failure modes, and clean-source
  lookup boundaries. The current 2026-05-30 registry run proves source-faithful
  pack formation but reports scaffold regression, so it is not an answer-quality
  or token-savings claim.
- `benchmarks/aippocampus/benchmark_continuous_memory_arms.py` runs the #408
  continuous-memory attribution controls for #378. It compares
  `no_memory`, `host_native_continuous_no_aippocampus`,
  `true_aippocampus_memory`, `sham_unrelated_memory`, `stale_wrong_memory`, and
  `oracle_memory` arms on public-safe synthetic coding-continuity cases, then
  reports `memory_presence_effect`,
  `host_native_compaction_lift_over_bare_continuous`,
  `memory_correctness_effect`, `stale_memory_harm`, `oracle_headroom`, and
  source-reopen obedience by arm. Its #410 `cost_harm_ledger` also separates
  foreground-only cost from amortized memory cost, severity-weights stale
  memory false positives, and keeps a separate `fresh_context_spec_loop`
  comparison baseline so a fair non-memory strategy can win on cost or safety.
  The ledger also includes `sensitivity_analysis`, a public-synthetic weight
  sweep that reports whether the fair winner changes under alternate cost/harm
  assumptions before any headline advantage claim.
  Its #407 `preregistration` block fixes the primary endpoint, paired
  seed/repeat strategy, lower-bound decision rule, and no-advantage rule before
  any public-quality #378 superiority claim. Its #409 scenario provenance and
  holdout controls record per-case generation context, report provenance
  slices separately, exclude `holdout_blind` cases from prompt/threshold
  tuning through `holdout_excluded`, and add scenario-level negative controls
  that penalize unnecessary memory intervention.
  Its #453 fresh-context framing treats complete-spec fresh context as an
  upper-bound / no-harm control, not the primary opponent. The primary endpoint
  is context loss or instability: incomplete handoffs, post-compaction horizon
  loss, stale/superseded state, and operation facts that were not carried
  forward. The implemented Track D report also exposes
  `metrics.no_harm_when_spec_complete` so a complete short-task prompt rewards
  memory silence rather than noisy retrieval.
  Its #406 host-native baseline separates `bare_continuous_no_memory` from a
  Codex-style host-native compaction path with AIppocampus hook, MCP recall,
  active recall, and registry memory disabled. That arm is a deterministic
  contract baseline; it records the host/version field that a future live run
  must fill, but it is not live host telemetry.
  Fixture arm construction is typed through `CommonArmSpecConfig`; this keeps
  host-native fallback and stale-harm knobs explicit without changing the
  public report schema.
  This runner is diagnostic and not a public superiority claim.

This slice is a smoke gate, not a real-history quality claim. It proves the
benchmark runners can catch skip/scent/evidence mistakes, report sanitized
metrics, and exercise deterministic Track D compaction-continuity behavior. The
next slices still need broader private real-history gate cases, budget curves,
larger live semantic-model verification, and live host-native baseline
telemetry.


### Knowledge Pollution And Privacy Partition Benchmark

`benchmark_knowledge_pollution.py` is a separate #517 contract-smoke surface.
It is not averaged into Track A-D, because it tests whether governed knowledge
and capability execution stay inside source authority, source-reopen, and
privacy-partition boundaries after a source or memory candidate has already
looked relevant.

Run it directly:

```powershell
python benchmarks\aippocampus\benchmark_knowledge_pollution.py --json
```

The runner covers these synthetic public-safe families:

- stale guideline and old-law/effective-date mismatch
- source-looking fake authority and low-authority override
- prompt injection inside source text
- model-summary-as-truth
- medical-memory to legal review, therapy-memory to work advice, contract
  secret to external-tool route, and cross-case context bleed

Required lower-is-better metrics are
`contamination_escape_rate`, `stale_source_harm_rate`,
`authority_override_rate`, `privacy_partition_leak_rate`,
`source_reopen_required_violation_count`, and `unsupported_claim_rate`.
Reports also include `source_prompt_injection_escape_rate` and
`model_summary_as_truth_rate` as direct diagnostics for issue #517.

The `CapabilityContract` fixture is a repo-internal prototype. It constrains a
synthetic contract-review capability by allowed sources, required permissions,
privacy partitions, source-reopen requirements, human-review boundaries,
input/output schema, cannot-claim entries, audit events, and fixture test
cases. It does not replace `knowledge.schema`, `knowledge.answer_gate`, or the
source-as-truth boundary.

Default reports emit ids, hashes, gate codes, and metrics only. They do not
emit raw input text, source text, private conversation text, contract-secret
text, or absolute local paths. The prototype cannot claim legal advice,
compliance certification, real contract-review quality, clinical/therapy
quality, private-history quality, typed capability taxonomy completeness, or
public API stability.


### Field Continuity / Magic Moment Reproducibility Suite

`benchmark_field_continuity.py` is a separate #454 contract-smoke surface and
the executable fixture layer for the #982 Field Continuity Eval design in
[`../../field-continuity-eval-design.md`](../../field-continuity-eval-design.md). It does
not replace Track A-D, and it does not turn community field reports into
official benchmark proof by itself. Its job is to make the user-visible
"magic moment" reports reproducible as scenario contracts with controls,
baselines, and privacy-safe reporting. For #281, the same public fixture also
exposes
`issue_readouts.github_281` as a supporting bounded fresh-thread
progressive-recall proxy: it records whether the
`fresh_projectless_familiarity` family is covered and whether source reopen,
progressive route recovery, wrong-family suppression, and irrelevant-memory
suppression hold in the deterministic fixture. The #281 public-fixture closeout
readout now lives in `benchmark_fresh_thread_recall_demo.py`, which reports the
larger first-turn/progressive/source-reopen/negative-control metrics in
`issue_readouts.github_281`.

Scenario families:

| Family | Expected behavior | Non-claims |
| --- | --- | --- |
| `fresh_projectless_familiarity` | light scent or progressive recall, source reopen before specific claims, uncertainty boundary | base-model innate memory, universal fresh-thread quality, foreground-hook-only sufficiency |
| `multilingual_vague_recall_with_route_correction` | accept a small correction, switch memory family, keep source uncertainty when exact lesson/source is unavailable | first route is always right, multilingual recall is solved |
| `external_state_restraint` | refuse live external-state overclaims, separate local automation/tool evidence from external account truth, mark unverified state | browser/account access, external platform state verified |
| `long_thread_fuzzy_self_reference` | recover an old referent when source reopen is available, preserve completion nuance, distinguish hook orientation from source recovery | hook-only sufficiency, private real-history quality |
| `cross_thread_exact_prompt_tool_failure` | recover prompt shape and tool-failure provenance across a language/thread boundary, without publishing raw prompt or error text | ambient hook solved exact recall, tool failure was caused by the memory system |

The public fixture lives in `benchmark_corpus/field_continuity/fixture.json`.
It includes one synthetic public-safe row for each family, arms for
`no_memory`, `fts_only`, `summary_first`, `semantic_only`, `hook_only`,
`active_recall_or_source_reopen`, and `stale_wrong_route_control`, plus
negative controls for overclaiming, wrong-family persistence, and stale-route
dominance. The runner reports top-level active-arm metrics plus
`metrics.by_arm` so baselines stay inspectable without collapsing into one
leaderboard score.

Private real-history seed runs stay outside git. Shared reports may include
only hash/aggregate rows: `seed_hash_sha256`, `case_family`, `source_kind`,
`date_bucket`, `scenario_tags`, `arm`, `metric_key`, `metric_value`,
`denominator`, and `cannot_claim`. They must not include raw prompts, source
snippets, local paths, rollout ids, thread ids, session ids, credentials,
cookies, or raw tool-error text.

Run it directly:

```powershell
python benchmarks\aippocampus\benchmark_field_continuity.py --json
```

Required metrics mirror #454 without reducing the suite to top-k retrieval:
`source_reopen_success`, `progressive_route_recovery`,
`external_state_overclaim`, `uncertainty_boundary_preserved`,
`abstains_when_evidence_insufficient`,
`exact_prompt_or_tool_failure_recovery`, `completion_nuance_preserved`,
`wrong_family_persistence`, `irrelevant_memory_drag`, `report_leakage`,
`latency_budget_overrun`, and `prompt_budget_overrun`.

The first implementation proves the fixture and report contract. The Field
Continuity #281 readout is `public_safe_fixture_quality_proxy` only; it is
supporting evidence, not the issue closeout surface. The #982 design closes the
design/fixture/runner-contract prerequisite, while the 2026-06-10 fresh-thread
runner readout retires #281's public-fixture validation blocker. Both keep
`live_fresh_thread_quality`, `private_real_history_quality`, and private seed
review outside the claim. They cannot claim real-history field-continuity recall
quality, live semantic-model quality, foreground-hook-only sufficiency,
summary-first/semantic-only/FTS-only superiority, or hosted/cross-device
readiness.
