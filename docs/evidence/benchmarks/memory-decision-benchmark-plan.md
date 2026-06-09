# AIppocampus Memory Decision Benchmark Plan

Status: repeatable baseline suite, named profile ladder, threshold metadata,
and `public-fast` fresh-clone profile implemented; current source-evidence
recall has improved, live semantic-gate smoke is opt-in, semantic-sidecar
coverage remains a known gap, and deterministic synthetic Track D
compaction-continuity testing is implemented as a measurement surface.

This document defines the benchmark direction for AIppocampus memory decisions.
It complements the existing FTS5/source-evidence checks; it does not replace
them and does not turn AIppocampus into a generic vector-search benchmark.
For the shortest map of every benchmark runner, smoke surface, corpus note, and
dated evidence owner, start with `docs/evidence/benchmark-evidence-map.md`.

## Goal

AIppocampus should be evaluated on the product behavior that matters most:

- when to stay silent
- when to emit quiet recall scent
- when to emit source-backed evidence
- whether surfaced payloads are faithful to clean source
- whether unrelated work prompts remain free of personal/private context
- whether work-task corrections and accepted decisions survive compaction
  without being promoted as automatic truth

The benchmark should prove that the system is useful without becoming noisy.
False positives, evidence over-escalation, and privacy leakage are worse than a
missed fuzzy recall.

## Existing Baseline

The existing lexical/source baseline lives in
`benchmarks/aippocampus/benchmark_fts5_recall.py`. It answers a narrower
question: given a source-backed recall case, can the FTS5 and production hybrid
paths navigate back to the expected clean-source message?

That baseline should remain because stale indexes, lexical misses, and ranking
regressions are real risks. The new benchmark layer should not re-score the
same thing under more complicated names.

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
- `benchmarks/aippocampus/benchmark_e2e50_silent_constraint.py` is the #279/#994
  public-safe annotated case-pack scorer scaffold. It consumes hash/count-only
  behavior-code cases, reports deterministic rates for silent constraint
  survival, known-bad route avoidance, transient-concern extinction,
  superseded-currentness, and source-reopen-before-risky-action, and now scores
  a checked-in 20-case public-safe synthetic seed pack with explicit
  `annotation_status` and `source_family` coverage. It still keeps
  `quality_gate_ok=false`: this pack retires the immediate public/shareable
  20-case seed-path blocker, not representative 50-case E2E50 quality,
  private-history behavior lift, or live host evidence. Its deterministic
  unittest is included in `benchmark-smoke` to keep the scorer contract alive
  while private seed material remains local and source-reviewed.
  The scaffold now also accepts optional `episode_chain` / `sequence_packet`
  evidence and bounded `cognitive_load` sidecars through
  `aippocampus_runtime.coding.sequence_packets`: those rows are scored as
  ordered read-model contracts and routing/caution metadata only, not as current
  validity facts, affect labels, or personality claims. The companion
  `aippocampus_runtime.coding.episode_arcs` slice builds deterministic coding
  Episode/Arc read-models and source-window reopen plans for #663; the schema
  and cannot-claim boundary live in
  `docs/architecture/episode-arc-read-models.md`.
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
- `benchmarks/aippocampus/benchmark_statistics.py` owns the shared Wilson
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
[`field-continuity-eval-design.md`](field-continuity-eval-design.md). It does
not replace Track A-D, and it does not turn community field reports into
official benchmark proof by itself. Its job is to make the user-visible
"magic moment" reports reproducible as scenario contracts with controls,
baselines, and privacy-safe reporting. For #281, the same public fixture also
exposes
`issue_readouts.github_281` as a bounded fresh-thread progressive-recall proxy:
it records whether the `fresh_projectless_familiarity` family is covered and
whether source reopen, progressive route recovery, wrong-family suppression,
and irrelevant-memory suppression hold in the deterministic fixture.

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

The first implementation proves the fixture and report contract. The #281
readout is `public_safe_fixture_quality_proxy` only. The #982 design closes the
design/fixture/runner-contract prerequisite, while keeping
`live_fresh_thread_quality`, `private_real_history_quality`, and private seed
review outside the claim. It cannot claim real-history field-continuity recall
quality, live semantic-model quality, foreground-hook-only sufficiency,
summary-first/semantic-only/FTS-only superiority, or hosted/cross-device
readiness.

### Benchmark Suite Profiles

`benchmark_suite.py` exposes named profiles so benchmark runs can be compared by
claim surface instead of by an opaque pile of flags. The CLI help links here,
and each JSON report includes `profile_metadata`, `threshold_metadata`, and
`claim_surface_warnings` so later run-history comparison can reject mismatched
surfaces before interpreting score deltas.

Profiles are presets plus safety boundaries. Maintainers may still use explicit
flags for narrow experiments, but those runs should be treated as mixed claim
surfaces unless the report metadata says otherwise.

| Profile | Intended use | Default included surface | Default exclusions / boundary pointer |
| --- | --- | --- | --- |
| `public-fast` | Fresh-clone public smoke and quick local confidence. | Track A gate decision, Track C payload fidelity, Track D compaction continuity. | Excludes private text, live semantic calls, Track B, and optional public-corpus adapters. |
| `ci-deterministic` | Deterministic CI-oriented baseline where Track B diagnostics are allowed. | Tracks A/C/D, Track B source-evidence retrieval, deterministic source-label diagnostic slice. | Excludes private text, live semantic calls, and optional public-corpus adapters. |
| `local-calibration` | Maintainer local calibration with deterministic Track B enabled. | Tracks A/C/D and deterministic Track B surfaces. | Excludes private text and live semantic calls by default; registry/data availability affects interpretation. |
| `live-semantic` | Explicit provider-backed semantic calibration. | Tracks A/C/D, Track B, and `live_semantic_gate`. | Live/provider-dependent surface; excludes private text by default. |
| `private-full` | Maintainer-only private-history regression. | Tracks A/C/D and Track B with private text allowed. | Private-history maintainer surface; public-release claims need sanitized dated evidence. |
| `release-evidence` | Public-safe release evidence with stable metadata. | Tracks A/C/D and deterministic Track B surfaces. | Excludes private text, live semantic calls, and optional public-corpus adapters unless explicitly opted in and documented. |
| `baseline` | Backward-compatible default baseline capture. | Current default suite surface. | Legacy continuity surface; prefer a named non-legacy profile for new evidence comparison. |

This table is a profile navigation map, not the active run claim boundary. It
names excluded surfaces so readers can choose the right profile, but it should
not mirror every profile's `default_cannot_claim` list. The selected profile in
the JSON report carries the active `cannot_claim` list, while inactive ladders
and docs maps should follow the count/pointer rule in
[`schema-field-profiles.md#cannot-claim`](../../architecture/schema-field-profiles.md#cannot-claim).

Run `public-fast` from a fresh clone when you need the deterministic public
benchmark surface without private registry data, live model calls, or external
dataset downloads:

```powershell
python benchmarks\aippocampus\benchmark_suite.py --profile public-fast --json
```

`public-fast` runs the Track A gate-decision, Track C payload-fidelity, and
Track D compaction-continuity slices. It forcibly disables private text, live
semantic checks, Track B source-evidence retrieval, and optional public-corpus
adapters. Its report includes `cannot_claim` entries for those omitted surfaces
so the profile cannot be mistaken for Track B, private-history, or live-model
quality evidence.

Suite reports keep `cannot_claim` as a backward-compatible flat union of all
claim boundaries, but readers should use `cannot_claim_by_track` and
`suite_level_cannot_claim` to interpret source and scope. For example, Track A's
`payload_fidelity` boundary means the gate-decision track does not validate
Track C payload fidelity; it does not contradict
`track_statuses.payload_fidelity=sufficient`. Track C can pass its
synthetic/public-safe payload-fidelity slice while still carrying
`real_history_payload_fidelity` as a track-local boundary.

Threshold metadata intentionally explains the comparison boundary rather than
just repeating numbers:

| Metadata key | Meaning | Claim boundary |
| --- | --- | --- |
| `fts5_min_cases` | Minimum deterministic source-line cases for the Track B FTS5 baseline. | Sample-count floor only; not a quality pass by itself. |
| `source_min_cases` | Minimum selected source-evidence cases. | Avoids tiny selected slices, but does not repair selection bias. |
| `source_min_hit_rate` | Diagnostic selected source-evidence top-k hit-rate floor. | Bounded retrieval diagnostic; not broad private real-history quality. |
| `live_semantic_min_cases` | Minimum optional live semantic cases. | Live provider smoke only; model/provider dependent. |
| `live_semantic_min_surface_recall` | Optional live semantic surface-recall threshold. | Local live slice threshold, not a guarantee for future semantic prompts. |
| `standard_min_questions` | Minimum LoCoMo/LongMemEval public retrieval-QA questions. | Public-control retrieval only; no answer-generation claim. |
| `standard_min_session_hit_rate` | Expected answer-session retrieval floor for standard public QA. | Session retrieval only; not SOTA, not LongMemEval-V2, and not answer quality. |

Do not lower thresholds to make a profile pass. If a run captures a baseline
but misses a threshold, keep `quality_gate_ok=false`, preserve `known_gaps`, and
use the result as regression evidence rather than as a product-quality
certificate.

### Run-History Diff Guardrails

`benchmarks/aippocampus/benchmark_run_history_diff.py` compares two saved
`benchmark_suite.py` JSON reports and emits a diagnostic artifact with
`status=no_regression`, `warning`, or `regression`:

```powershell
python benchmarks\aippocampus\benchmark_run_history_diff.py --baseline .tmp\prior-suite.json --current .tmp\current-suite.json --json
```

The comparator only treats runs as comparable when the benchmark-suite schema,
selected profile, `profile_metadata.effective_surface`, and key config fields
match. Profile changes, Track B / Track D switches, optional public adapter
changes, seed/top-k/ranking/dataset changes, private-text boundaries, and live
semantic surface changes are warnings about incomparable surfaces, not metric
regressions.

The comparable identity also includes track statuses, public adapter
status/corpus fingerprints such as `corpus_path_sha1`, threshold metadata, and
per-metric gate thresholds for metrics present in both runs. It deliberately
excludes absolute local paths and raw text fields from the diff artifact. If a
rate metric disappears or appears inside an otherwise comparable surface, the
diff emits a warning (`metric_missing_in_current` or `metric_new_in_current`)
instead of silently comparing only the intersection.

Trend status is separate from `quality_gate_ok`. A current run can still clear
its point-in-time threshold while receiving `status=regression` because it
dropped materially from the previous comparable run. Conversely, a run with
`quality_gate_ok=false` can still be useful as a baseline snapshot if the diff
shows the same known gap and no additional trend regression.

The first diff policy is intentionally conservative:

- higher-is-better rate estimates warn on absolute drops of at least `0.03` and
  regress on drops of at least `0.05`, unless the sample size changed enough to
  make a sample-size warning more honest than a regression claim;
- lower-is-better rates such as false-positive, false-negative, over-escalation,
  error, miss, failure, and privacy-breach rates regress when they increase;
- Wilson lower-bound drops are warnings, not proof that sampling bias was
  solved;
- privacy boundary fields moving from safe to unsafe, such as
  `raw_text_emitted=false` to `true`, are direct regressions;
- sample-size shrinkage is a warning, not a healthy pass;
- live semantic metric drops are warning-only until the project defines a
  stable provider/model comparison policy;
- `elapsed_ms` increases are warnings only because local machine, cache, and
  provider conditions can dominate single-run timing.

Historical suite JSON and diff artifacts remain local/generated evidence under
`.tmp/` or `benchmark_corpus/reports/` unless a small public-safe summary is
deliberately promoted into docs. The comparator never rewrites old reports and
does not replace the dated public-readiness ledger.

Cannot-claim boundaries:

- a run-history diff is diagnostic trend evidence, not proof of overall product
  quality;
- different profiles, corpora, seeds, public adapters, private-text settings, or
  live providers are not directly ranked;
- confidence intervals make small-N uncertainty visible but do not repair sample
  construction bias;
- live semantic deltas are warning-only until a stable provider/model policy is
  explicitly defined.

### Continuous-Memory Attribution Arms

Issue #408 adds a diagnostic arm runner for the broader #378 question: when a
continuous agent appears to improve, did correct source-backed memory help, or
did the model merely benefit from extra nearby structured text?

Run the public-safe attribution slice directly:

```powershell
python benchmarks\aippocampus\benchmark_continuous_memory_arms.py --json
```

The runner intentionally stays outside the default `public-fast` suite for now.
It uses six public-safe coding-continuity cases and six arms:

- `no_memory`: the `bare_continuous_no_memory` diagnostic arm has no recall
  context and no host-native compaction help.
- `host_native_continuous_no_aippocampus`: a Codex-style same-thread
  compaction/summary baseline with AIppocampus hook recall, MCP
  `recall_context` / `recall_deepen`, active recall, and registry memory
  injection disabled.
- `true_aippocampus_memory`: production-shaped route handles require source
  reopen and may still abstain when the source is incomplete.
- `sham_unrelated_memory`: same nearby memory-shaped format, but unrelated, so
  any lift is a memory-presence effect rather than memory correctness.
- `stale_wrong_memory`: matched-format plausible wrong memory used as an
  adversarial diagnostic stressor, not a product mode.
- `oracle_memory`: minimal source-grounded context used only as an upper-bound
  arm and never as input to true-memory scoring.

Reports must keep these effects separate:

- `memory_presence_effect`: sham vs no-memory.
- `host_native_compaction_lift_over_bare_continuous`: host-native continuous
  no-AIppocampus vs `bare_continuous_no_memory`.
- `memory_correctness_effect`: true memory vs sham.
- `stale_memory_harm`: stale-wrong harm against no-memory.
- `oracle_headroom`: oracle memory against true memory.
- `source_reopen_obedience_by_arm`: whether strong memory-shaped claims were
  source-reopened or safely abstained when source support was missing.

The #410 cost and harm ledger lives under `cost_harm_ledger`. It uses
public-synthetic units rather than exact billing data:

- `foreground_cost_per_successful_slice` counts visible prompt/context tokens,
  fixture latency, and source reopen work.
- `background_cost_per_successful_slice` counts modeled memory-prep tokens,
  optional background calls, indexing/maintenance time, and storage growth.
- `amortized_cost_per_successful_slice` adds foreground, background, recovery,
  and human-correction proxies so memory cannot look cheap only because its
  preparation was offscreen.
- `harm_weighted_false_positive_cost` squares stale false-positive severity and
  adds downstream-turn, wrong-constraint, rejected-route, project-contamination,
  risky-before-source-reopen, privacy, and rollback/rework weights.
- `net_value_under_equalized_cost` keeps success, cost, and harm separate. It
  excludes `oracle_memory` from fair cost winners and compares memory arms with
  a `fresh_context_spec_loop` baseline; reports must allow that baseline to win
  when memory overhead or harm outweighs recall lift.
- `sensitivity_analysis` reruns the fair-winner calculation under a few
  public-synthetic weight settings, including harm-heavy, memory-cost-light,
  and fresh-context-rebuild-expensive variants. It reports winner distribution
  and the true-memory margin against the best non-true-memory strategy. This is
  a diagnostic robustness sweep, not calibrated user-study or live telemetry
  evidence.

`no_memory` remains a diagnostic attribution arm with no recall context and no
host-native compaction help. It is not the same thing as either a
fresh-context/spec-loop workflow or a realistic continuous host workflow, so
reports keep `fresh_context_spec_loop` and
`host_native_continuous_no_aippocampus` distinct in
`comparison_baselines`.

The #406 host-native arm is deliberately narrow. The documented v1 host family
is Codex, with normal current-thread context, host compaction/summary, and host
session state allowed. AIppocampus prompt-hook recall, MCP recall tools, active
recall, and registry memory injection are disabled. The deterministic report
records
`compaction_settings=host_default_same_thread_summary_or_compaction_contract`
and can run this contract arm, but it still records
`live_measurement_status=not_measured_in_this_diagnostic_runner`; any
cross-host claim must split Codex, Claude Code, Cursor / VS Code agents, or
other clients into separately documented live paths.

Fresh-context/spec-loop baselines must be named by role:

- `oracle_fresh_context_spec_loop` or
  `complete_spec_fresh_context_upper_bound` means every iteration receives the
  complete correct task context. This is an upper-bound and no-harm control. It
  is expected to win many short complete-spec tasks, and that is not an
  AIppocampus failure.
- `realistic_fresh_context_handoff_loop` means the reset workflow carries an
  incomplete, lossy, compressed, stale, or missing handoff. This is the primary
  reset baseline for #378-style memory value.

Reports must keep the endpoints separate. Primary #378 value is measured under
context loss or instability: silent constraint loss, known-bad-route repetition,
operation-fact reopen/repetition, stale summary overhang, human corrections,
source reopen before risky action, and cost per successful slice. The
complete-spec endpoint is a no-harm gate: AIppocampus should not inject
irrelevant or stale memory when the current prompt already contains the full
correct spec. `cannot_claim` should include that the benchmark does not prove
memory is useful when the current prompt already carries the full task context.

The #409 scenario provenance and holdout controls live under
`scenario_controls`, with row-level sanitized scenario metadata:

- Provenance categories are fixed as `author_written_synthetic`,
  `external_written_synthetic`, `public_log_or_vcs_derived`,
  `private_real_history_aggregate`, and `holdout_blind`.
- At least 30% of a public-quality #378 suite must come from
  `external_written_synthetic`, `public_log_or_vcs_derived`, or
  `holdout_blind` scenarios. The current contract smoke includes two
  `public_log_or_vcs_derived` + `holdout_blind` cases, so this share gate can
  pass, but it still lacks public-quality repeat power.
- Holdout scenarios must use `holdout_excluded` and must not be used for
  prompt or threshold tuning. The runner exposes
  `--scenario-selection-role prompt_threshold_tuning` for that path; it
  physically excludes `holdout_blind` cases from rows and metrics rather than
  relying only on labels.
- Scenario scripts record a sanitized generator/source-material label and
  whether AIppocampus internals were visible to the scenario author. Public
  report metadata rejects path separators, URI/drive separators, and
  secret-like/private labels before JSON emission.
- Scenario-level negative controls count unnecessary memory interventions,
  including expired-memory reuse and same-token public VCS anti-drift
  contamination. Reports keep `negative_control_memory_intervention_by_arm`
  separate from the harmful
  `negative_control_unnecessary_intervention_by_arm` so ordinary no-memory
  failure is not misread as memory intervention. These controls are separate
  from the stale wrong arm, which remains an adversarial diagnostic stressor.

This is enough to prove the public-safe attribution, #406 host-native baseline,
#409 scenario-control, #410 ledger, and diagnostic cost/harm sensitivity
contracts exist. It does not prove full #378 continuous-memory superiority,
cost-weight robust continuous-memory advantage, exact dollar accounting for
every local operation, live host-native cost telemetry, live host-native
compaction behavior, private real-history generality, answer-generation
quality, or competitor superiority.

The #407 pre-registration contract lives under `preregistration`. It is the
rule for future public-quality #378 claims, not a claim that the current
contract smoke has enough power:

- Primary endpoint:
  `source_grounded_task_success_under_equalized_cost`.
- Why this endpoint: it combines task success, source support, equalized cost,
  and severe false positives so the memory arm cannot win by hiding background
  work or unsafe stale recall.
- Public-quality minimums: at least 3 scenario families and at least 5 paired
  repeats per scenario x arm, with the same task/seed pairs across arms where
  feasible. At least 30% of cases must come from external-written,
  public-log/VCS-derived, or holdout sources before public-quality superiority
  claims.
- Required fair arms: `fresh_context_spec_loop`,
  `host_native_continuous_no_aippocampus`, `true_aippocampus_memory`,
  `sham_unrelated_memory`, and `stale_wrong_memory`; `oracle_memory` stays an
  upper bound and is excluded from the fair winner.
- Seed rule:
  `sha256(preregistration_id + scenario_family + case_id + repeat_index)`.
  The current contract smoke remains deterministic public-safe cases with no
  random seed.
- Confidence rule: continuous-memory advantage requires the paired
  `lower_bound` for true AIppocampus memory over `fresh_context_spec_loop` to
  be greater than 0 after hard gates pass. Binary success and harm rates should
  expose Wilson lower bounds; net-value deltas should use paired bootstrap or a
  stricter registered equivalent.
- Secondary metrics, including `memory_presence_effect`,
  `memory_correctness_effect`, `stale_memory_harm`, `oracle_headroom`,
  `source_reopen_obedience_by_arm`, `harm_weighted_false_positive_cost`, and
  `amortized_cost_per_successful_slice`, are exploratory unless named in the
  primary decision rule before the run.
- No-advantage rule: if the primary endpoint does not beat the baseline under
  the registered lower-bound rule, the report must say
  `no demonstrated memory advantage` even when secondary metrics favor
  AIppocampus.

The `preregistered_slices` block records which narrow #378 slice this report
actually ran. The current slice is
`github_378_continuous_memory_public_synthetic_v1`. The default runner profile
remains a deterministic public-synthetic contract smoke over the six
attribution-arm fixtures: it freezes a sanitized case-manifest digest,
scenario-selection role, required fair strategies, primary endpoint, decision
preview, and public-quality gates, but it has only one deterministic repeat per
case/arm.

For the registered repeat readout, run:

```powershell
python benchmarks\aippocampus\benchmark_continuous_memory_arms.py --public-quality-repeat-profile --json
```

That `public_synthetic_preregistered_repeat` profile expands the same
public-safe fixture pack to `repeat_count_per_case_arm=5`,
`case_arm_trial_count=30`, and `row_count=180`.
It evaluates the registered lower-bound rule with
`lower_bound_method=minimum_observed_paired_delta_for_deterministic_public_synthetic_repeats`.
The 2026-06-08 local run reported `lower_bound_units=-27.7675`,
`mean_delta_units=-27.7675`, `lower_bound_passed=false`,
`primary_endpoint_winner=fresh_context_spec_loop`, and
`decision_label=no demonstrated memory advantage`.

This repeated public-synthetic slice is useful scope-boundary evidence for
#378's no-advantage rule. It should be read as
`no demonstrated net advantage over modeled fresh-context spec loop`, not as
"AIppocampus recall never helps." The `fresh_context_spec_loop` arm is a
complete-spec reset workflow, and the current ledger expects that arm to win
short tasks where the right source can be cheaply rebuilt. The repeat rows are
deterministic replicated lower-bound rows for the registered gate; they are not
independent human or live-model trials.

The 2026-06-09 #960 product-remediation rerun preserved the negative rule and
reported the following per-case remediation taxonomy. The product change was
narrow: source-required fresh-thread packets with no reopenable source ref now
ask for a minimal source anchor instead of silently ignoring the route or
inventing manual query terms.

The machine-readable report now exposes this under
`expected_null_remediation`. That block is a remediation ledger, not a scoring
layer: it keeps `primary_endpoint_changed=false`,
`benchmark_thresholds_changed=false`, and
`product_change_status=implemented_rerun`; it also records
`source_miss_recovery_action=ask_light_question` and
`manual_query_invention_expected=false`. The expected-null boundary remains
because the registered lower-bound result is still negative:
`lower_bound_units=-27.7675`.

| Case family | Success lift | Source-miss abstention | Fresh-context advantage | Memory cost drag / repair hypothesis |
| --- | --- | --- | --- | --- |
| `post_compaction_rejected_route` | True memory succeeds where `no_memory`, sham, and stale arms fail by reopening source and avoiding a rejected route. | None. | The complete-spec reset loop already carries the right rejected-route source. | Route is useful but expensive; inspect `route_packet`, `source_reopen`, and `cost_harm_accounting` for cheaper actionability. |
| `post_compaction_scope_constraint` | True memory succeeds where `no_memory`, sham, and stale arms fail by carrying the scope constraint forward. | None. | The reset loop has the full scope constraint in prompt. | Reduce prompt-hook/route overhead before changing scoring. |
| `transient_concern_expiry` | True memory succeeds and stale wrong memory fails; `no_memory` and sham also succeed because silence is enough for this negative-control-like slice. | None. | Fresh context or memory silence is expected to be cheap and safe. | Product target is restraint: avoid unnecessary foreground hints and keep old concerns quiet unless source reopening changes action. |
| `incomplete_handoff_recovery` | No task-success lift: true memory fails like `no_memory` and sham because the source is missing. | True memory source-checks, abstains, and now uses the product source-miss recovery action `ask_light_question` to recover a minimal source anchor without guessing. | The modeled reset loop has the missing source, so it is expected to win. | Source-reopen fallback is improved for safety and usefulness, but the primary endpoint still does not reward unsupported answers. |
| `public_vcs_temporal_override` | True memory succeeds where `no_memory`, sham, and stale arms fail by following the current counterfactual source. | None. | The reset loop already has the current source, with lower modeled cost. | Memory correctness is not the failure; net-value drag is. Inspect route minimality and source-reopen cost. |
| `public_vcs_anti_drift_negative` | True memory succeeds like `no_memory` and sham by suppressing unrelated same-token memory; stale wrong memory fails. | True memory source-checks/abstains on the irrelevant route. | Fresh context wins by staying silent without doing memory work. | Treat as a no-harm gate: suppress irrelevant hints earlier and avoid charging avoidable memory work. |

This table is a remediation ledger, not a benchmark rewrite. The #960 source-miss
fallback is implemented and rerun, but future work still needs measured user
friction or net-value lift before any scoring or threshold change. The row still does not claim full #378
continuous-memory superiority, live host-native cost or compaction telemetry,
private real-history generality, or cost-weight robust continuous-memory
advantage.

The current public-synthetic report exposes the pre-registration decision as a
contract-smoke preview by default and as a repeated lower-bound readout when
`--public-quality-repeat-profile` is used. With the current #410 ledger values,
`fresh_context_spec_loop` is the current fair-strategy winner, so
`continuous_memory_advantage_claim_allowed=false`.

### Repeatable Baseline Command

Run from the repository root:

```powershell
python benchmarks\aippocampus\benchmark_suite.py
```

For a machine-local JSON artifact, write into the gitignored private benchmark
area:

```powershell
python benchmarks\aippocampus\benchmark_suite.py --json --output benchmark_corpus\reports\baseline-suite.json
```

Default suite semantics:

- `ok=true` means the current baseline was captured and the report stayed inside
  the default privacy boundary.
- `quality_gate_ok=false` is allowed for the current baseline and means at least
  one track is diagnostic or below target.
- `status=baseline_captured_with_known_gaps` is the expected current status.
- Raw prompts, context, source refs, snippets, absolute paths, and private
  registry details stay out of default reports.
- `--include-private-text` is a local-debug opt-in only and should not be used
  for public docs or committed artifacts.
- Private real-history case selection delegates obvious sensitive-content
  detection to `aippocampus_runtime.safety.benchmark_sensitive_text_policy`.
  That policy skips candidates with credential/path/recipient/database/private
  host signals; it is stricter than external-model prompt redaction because
  benchmark fixtures should avoid selecting publishable targets from sensitive
  text in the first place.

### Uncertainty And Gate Semantics

Empirical benchmark reports should expose `rate_estimates` for key binomial
rates. Each entry includes numerator, denominator, point estimate, and a
Wilson-score confidence interval. This makes small-N reports visibly wide
instead of letting a perfect point estimate read like a release-quality result.

Confidence intervals do not repair sampling bias. Selected real-history slices,
synthetic contract fixtures, public-corpus pilots, and opt-in semantic-sidecar
pilots must keep their `claim_level`, `sample_size_warning`, and `cannot_claim`
boundaries. A high point estimate with a wide lower bound is still diagnostic
unless the owning track's design says the sample is release/public-readiness
evidence.

Default deterministic contract gates keep their existing point/count
semantics. They answer "did this fixed contract fail today?" rather than
"would this pass with statistical confidence?" Broader empirical gates may opt
into lower-bound semantics when that is the product claim under review. The VCS
future-event recall benchmark exposes this explicitly with
`--gate-statistic lower_bound`; the default remains point-estimate gating so
small fixtures do not silently become release blockers.

MRR and rank-order metrics are still point estimates unless a runner exposes a
dedicated bootstrap interval. Do not average Track A gate decisions, Track B
retrieval, Track C payload fidelity, and Track D continuity into one headline
confidence number; their sample construction and product meanings differ.

### Coding Decision-Shadow A-E Benchmark

Run the public deterministic coding-agent decision-shadow contract:

```powershell
python benchmarks\aippocampus\benchmark_coding_decision_shadow.py --json
```

This benchmark is narrower than the one-command baseline suite. It directly
exercises the coding continuity wedge: source-backed decision refs,
rejected-route warnings, compaction boundary preservation, historical decision
selection, and anti-nag suppression. Negative controls cover wrong-source
evidence, visible-source suppression, and stale authority. The default report
is sanitized and cannot claim private real-history behavior lift, full
code-index navigation quality, or live host intervention timing.

### Optional ShareGPT Public Track B

The ShareGPT public Track B slice uses the converted public clean-source corpus
to create source-evidence retrieval cases with stable source refs. It is local
and opt-in because the generated corpus is large and gitignored.

Run from the repository root:

```powershell
python benchmarks\aippocampus\benchmark_source_evidence_retrieval.py --include-sharegpt-public --sharegpt-public-conversations 100 --sharegpt-public-cases 200 --sharegpt-public-min-cases 50 --sharegpt-public-sampling-mode seeded-stratified --sharegpt-public-seed 218
```

Or include it in the suite:

```powershell
python benchmarks\aippocampus\benchmark_suite.py --include-sharegpt-public-track-b --sharegpt-public-conversations 100 --sharegpt-public-cases 200 --sharegpt-public-min-cases 50 --sharegpt-public-sampling-mode seeded-stratified --sharegpt-public-seed 218
```

Boundary:

- this is a public-corpus Track B baseline, not a private real-history quality
  claim
- cases bind expected evidence to clean-source `source_id`, `message_id`,
  `turn_id`, and line metadata; model summaries are not grading truth
- default public-corpus runs use seeded stratified conversation sampling and
  report seed, selected id hashes, eligible population count, skipped counts,
  and stratum counts; `--sharegpt-public-sampling-mode first-n` is only an
  explicit smoke/debug override and carries a cannot-claim boundary for full
  population sampling

### Optional Public Semantic Sidecar Track B

The public semantic-sidecar pilot first builds a bounded ShareGPT clean-source
registry subset, runs the live semantic labeler over a limited candidate set,
materializes reviewed `semantic-scope-labels.jsonl` rows with the existing
sidecar validator, then runs the selected source-evidence evaluator against that
subset. It is a separate `public_semantic_sidecar` track.

Run from the repository root:

```powershell
python benchmarks\aippocampus\benchmark_source_evidence_retrieval.py --allow-deterministic-labels --include-public-semantic-sidecar --public-semantic-output-dir .tmp\public-semantic-sidecar-20260529-wide --public-semantic-conversations 80 --public-semantic-max-messages 160 --public-semantic-max-candidates 48 --public-semantic-cases 40 --public-semantic-min-cases 3 --public-semantic-top-k 5 --public-semantic-max-tokens 16384 --public-semantic-timeout 90 --output .tmp\track-b-public-semantic-sidecar-wide-20260529.json
```

Boundary:

- this is a public semantic-sidecar pilot, not the private real-history
  `semantic-sidecar-required` metric
- reviewed means accepted by the source-ref/label-evidence sidecar validator;
  it does not mean human-reviewed
- generated subset, registry, sidecar, and live report stay local under `.tmp/`
  unless a curated public fixture is deliberately promoted later
- reports include `claim_level`, `minimum_empirical_case_count`, and
  `sample_size_warning`; passing top-k hits below that density stays a
  `diagnostic_pilot`, not an empirical benchmark claim
- reports include `anti_circular_controls`: the same bounded subset is evaluated
  with a no-sidecar deterministic/source-visible baseline and a wrong-message
  negative sidecar. The semantic-sidecar quality gate must not treat a passing
  wrong-message control as valid evidence; those controls are diagnostics, not
  a replacement for human-reviewed labels.
- metrics include message-level hit and turn-level hit so sibling rows in the
  same user/assistant turn do not become false hard failures
- default reports hash ids and queries and do not emit raw public conversation
  text; `--include-private-text` remains local-debug only

### Optional Live Semantic Gate

Live semantic checks are intentionally outside the required CI/default suite.
They exercise the real semantic backend and can vary by provider, model, cache,
quota, and network state.

Run from the repository root:

```powershell
python benchmarks\aippocampus\benchmark_live_semantic_gate.py --sharegpt-conversations 100 --semantic-mode on --semantic-workers gate --output .tmp\live-semantic-gate-100.json
```

Or include the same optional track in the suite:

```powershell
python benchmarks\aippocampus\benchmark_suite.py --include-live-semantic --live-semantic-conversations 100 --live-semantic-mode on --live-semantic-workers gate
```

Report boundary:

- missing API key or disabled semantic mode returns
  `skipped_missing_semantic_backend`; this is a clean skip, not a failed test
  run
- `quality_gate_ok=true` means the configured live slice cleared its local
  thresholds, not that all future semantic prompts are solved
- `--case-workers` controls case-level parallelism. The default `0` resolves to
  `ceil(sharegpt_conversations / 2)`, so a 20-conversation run uses 10 case
  workers and a 100-conversation run uses 50. Parallel runs disable the local
  JSON result cache to avoid shared-file write races; provider-side prefix cache
  still appears in `semantic_usage`
- reports include `semantic_available_count`, `semantic_error_case_count`,
  `semantic_decision_counts`, `semantic_evidence_guarded_to_scent_count`,
  `semantic_evidence_to_source_required_route_count`,
  `semantic_evidence_guarded_to_plain_scent_count`,
  `paid_semantic_hit_count`,
  `paid_semantic_hit_to_source_reopen_rate`,
  `manual_query_invention_after_paid_semantic_hit_count`,
  `useful_route_suppressed_count`, `all_scent_collapse_rate`,
  `semantic_evidence_allowed_count`, sanitized `semantic_error_kind_counts`,
  `issue_readouts.github_201.live_semantic_route_actionability`, and
  `issue_readouts.github_786.live_semantic_reopen_quality`
- reports do not emit raw prompts, aliases, model reasons, snippets, titles,
  source-reference details, absolute paths, or provider error text
- semantic payload construction is quality-first for the foreground hook:
  default `memory_catalog` and `trigger_catalog` are full compact catalogs
  (`AIPPOCAMPUS_SEMANTIC_CATALOG_LIMIT=0` and
  `AIPPOCAMPUS_SEMANTIC_TRIGGER_LIMIT=0`). Prompt-local
  `prompt_relevant_catalog` and `prompt_relevant_triggers` remain after the
  prompt as emphasis/diagnostic slices and to protect explicit limit/debug
  runs. Non-zero env limits are debug/performance overrides, not product
  defaults.

Current smoke and diagnostic results from 2026-05-30:

- synthetic Track A gate benchmark now includes the original 13 synthetic
  boundary cases plus public memory-pain fixtures and a 166-case harder bank.
  The harder bank currently reports 163/166 correct, accuracy 0.9819, macro F1
  0.9839, over-escalation 0, evidence false positives 0, evidence false
  negatives 0, and expected-evidence source match 37/37. This remains a
  deterministic routing contract, not a live semantic-model quality claim: the
  mocked `positive_scent`, `overeager_evidence`, `timeout`, and paraphrase
  fixtures validate hook routing and evidence guards after a semantic decision.
  The optional live semantic-gate benchmark owns whether the configured model
  would make that decision on real prompts. The harder bank now covers hard
  negatives with high registry overlap, false memory cues inside code-surface
  prompts, cross-project same-name entity traps, semantic over-evidence traps,
  competing-source evidence requests, mixed-language paraphrase,
  timeout/degradation behavior, secret-like suppression, explicit source-free
  evidence/scent twin contracts, four alias-ablation controls, and 30 natural
  oral prompts, including 12 should-evidence cases that catch under-recall on
  weak user wording such as "上次那个 bug 怎么说的来着". The alias-ablation
  controls run with benchmark-authored exact trigger aliases removed from the
  sidecar and report `exact_prompt_alias_violation_count=0`; they prove the
  fixture is not only rewarding prompts that repeat `external hippocampus`,
  `raw history`, or `source-backed` verbatim.
- Private real-history memory-pain prompt smoke now has a hash-only runner:
  `tools/aippocampus/smoke/smoke_memory_pain_prompt_hook.py`. On 2026-05-30,
  local deterministic mode over the installed real registry reported 8 cases,
  decisions `{evidence: 2, scent: 5, skip: 1}`, 6 evidence rows, 0 unsafe
  issues, and 0 positive misses. Foreground semantic-budget mode
  (`--semantic-gate on --semantic-timeout 20 --max-elapsed-ms 4300`) kept the
  same decisions and evidence count while surfacing 9 `read_timeout` buckets.
  Relaxed live semantic mode (`--max-elapsed-ms 0`) reported decisions
  `{evidence: 2, scent: 6}`, 6 evidence rows, 0 unsafe issues, 0 positive
  misses, and one `semantic_evidence_without_source_bridge` diagnostic for a
  deliberately vague cross-project prompt. The output is aggregate/hash-only and
  is a bounded real-history regression smoke, not a full private-history quality
  claim.
- ShareGPT public Track B source-evidence slice over
  `sharegpt_all_multiturn`, first 100 conversations, max 200 cases:
  `status=sufficient`, 200 cases, 194 answer source-evidence cases and 6
  continuation source-evidence cases, message top-10 hit rate 0.985, turn
  top-10 hit rate 1.0, message MRR 0.9052, turn MRR 0.9613, 0 warnings, wall
  time 23.1 seconds. This is a public-corpus baseline and does not replace the
  private real-history semantic-sidecar source-evidence slice.
- Public semantic-sidecar Track B pilot over `sharegpt_all_multiturn`,
  bounded to 80 conversations / 160 clean-source messages / 48 label candidates:
  `status=diagnostic_only`, `claim_level=diagnostic_pilot`, 3 reviewed
  `semantic-scope-labels.jsonl` rows, 3 selected public semantic-sidecar cases,
  3/3 top-5 hits, and `minimum_empirical_case_count=50`. The generated subset
  lives under `.tmp/public-semantic-sidecar-20260529-wide/` and the sanitized
  report is `.tmp/track-b-public-semantic-sidecar-wide-20260529.json`. This is
  deliberately reported as `public_semantic_sidecar`; it does not upgrade to an
  empirical public semantic-sidecar claim or replace the private real-history
  `semantic-sidecar-required` claim.
- Private real-history semantic-sidecar refresh:
  `smoke_semantic_scope_real_history.py --live --write-sidecars
  --full-candidate-coverage --full-candidate-source-turn-cap 160
  --candidate-batch-size 16 --samples-per-job 1` evaluated 414 selected
  candidate turns in 26 successful batches. Reviewed sidecar coverage grew from
  2 threads / 5 rows to 45 threads / 243 rows, with 108 timeline latest turns
  carrying semantic sidecar labels. The live jobs accepted 238 findings and 269
  labels with `weak_or_missing_evidence_label_count=0`. This is a bounded
  private slice, not a full-history semantic completeness claim.
- Private real-history Track B wrapper after that refresh:
  `.tmp/track-b-private-semantic-after-live-20260529.json` reports
  `status=sufficient`. The `semantic-sidecar-required` source-evidence track now
  has 100 selected cases, 97/100 top-5 hits, 0.97 hit rate, and 3 failures, all
  `rank_below_top_k` with extended ranks 6, 8, and 10. The same wrapper reports
  959 registry threads, 810 eligible threads, 9,699 messages scanned, 97/100
  FTS5 top-10 hits, and 98/100 production-hybrid top-10 hits.
- Standard retrieval-QA Track B smoke:
  LoCoMo first 100 QA from the local `locomo10.json` produced session R@10
  0.89, session MRR 0.6271, exact evidence-line R@10 0.56, exact evidence-line
  MRR 0.3704, context-visible evidence-line R@10 0.81 with radius 5, and
  context-visible evidence-line MRR 0.5963. The context-visible metric matters
  because LoCoMo evidence often points to a line whose answer is visible in the
  nearby source context, for example an image-caption or direct reply line.
  LongMemEval V1 Oracle first 50 questions produced session R@10 1.0, session
  MRR 1.0, exact evidence-line R@10 0.96, exact evidence-line MRR 0.7409,
  context-visible evidence-line R@10 1.0, and context-visible evidence-line MRR
  0.9. The context window improved 14/50 Oracle line cases and rescued 2/50
  exact line misses at top 10. LongMemEval V1 Small first 20 questions produced
  session R@10 1.0, session MRR 0.9667, exact evidence-line R@10 0.95, exact
  evidence-line MRR 0.681, context-visible evidence-line R@10 1.0, and
  context-visible evidence-line MRR 0.9417. The context window improved 9/20
  Small line cases and rescued 1/20 exact line miss at top 10. These LME
  results show the same granularity boundary as LoCoMo: the exact `has_answer`
  row is often adjacent to a higher-ranked source row from the same answer
  session, so product-visible evidence is stronger than strict single-row MRR.
  These are retrieval-only numbers using question text as query, not
  answer-generation accuracy. They are the current deterministic
  non-source-derived Track B arm because the query comes from public dataset
  questions rather than from the target source line. LongMemEval V2 now has a
  dedicated context-mapping pilot that inspects the public questions and
  trajectories without emitting raw text. The 2026-06-03 local pilot observed
  451 questions, 1,870 trajectories, 0 exact question/trajectory id matches,
  and 0 question or trajectory rows with gold evidence refs. The standard
  source-evidence adapter therefore still reports V2 as skipped rather than
  inventing R@K, while the V2 pilot reports only schema, checksum, join-key
  coverage, environment-pool ambiguity, and `cannot_claim` boundaries.
- Standard retrieval-QA semantic line-reranker smoke:
  the optional top-session/top-context second stage keeps the first-stage FTS5
  session/context boundary fixed, sends only bounded candidate source lines to
  the configured DeepSeek-compatible reranker, and scores whether the exact
  evidence row moves up. Reports keep `semantic_only_*` separate from
  FTS-preserving `reranked_*` metrics, because product ranking should not hide a
  line that first-stage FTS already surfaced. The first-stage reranker boundary
  now uses two honest query channels: the original question terms plus a
  content-term channel with generic question words removed. LoCoMo first 100
  improved from exact evidence-line MRR 0.3704 to semantic-only MRR 0.7417 and
  fused reranked MRR 0.7564; fused line R@10 improved from 0.56 to 0.85, with
  candidate evidence coverage 0.88, 100/100 reranker calls available, 0 errors,
  and average candidate count 90.81. The remaining LoCoMo gap is mostly
  first-stage candidate coverage and harder evidence granularity, not only
  source-line ordering.
  LongMemEval V1 Oracle first 50 improved from exact evidence-line MRR 0.7409
  to semantic-only MRR 0.9467 and fused reranked MRR 0.9767, with fused line
  R@10 1.0, candidate evidence coverage 1.0, 50/50 reranker calls available, 0
  errors, and average candidate count 24.9. LongMemEval V1 Small first 20
  improved from exact evidence-line MRR
  0.681 to semantic-only and fused reranked MRR 1.0, with fused line R@10 1.0,
  candidate evidence coverage 1.0, 20/20 reranker calls available, 0 errors,
  and average candidate count 57.25.
  This is a live-model Track B line-ranking result, not a required deterministic
  CI metric and not answer-generation accuracy.
- Current default 100-conversation live run after switching foreground semantic
  payloads to full compact catalogs and leaving `--case-workers` on auto:
  400 cases, 399 correct, accuracy 0.9975, `status=sufficient`,
  `scent_or_evidence_recall` 0.9967, evidence recall 1.0, evidence false
  positives 0, semantic calls 300, semantic available 299, semantic error cases
  1. The resolved `case_workers` value was 50. Chinese continuation surfaced
  99/100; English continuation surfaced 100/100. Wall time was 62.8 seconds,
  semantic latency p50 3.91s and p95 5.78s, reported semantic tokens about
  5.00M, and provider prefix-cache hit rate 0.7918.
- 2-conversation live boundary smoke, gate worker only, `--case-workers 10`: 8
  cases, 8 correct, semantic calls 6. The live model returned `evidence` for one
  vague continuation prompt and two explicit evidence prompts; the hook guarded
  the vague continuation to `scent` and allowed both explicit cases to surface
  source-backed `evidence`.
- 20-conversation live smoke, gate worker only, `--case-workers 10`: 80 cases,
  78 correct, accuracy 0.975, `status=sufficient`, semantic calls 60, semantic
  available 60, semantic error cases 0, evidence recall 1.0, evidence false
  positives 0. Chinese continuation surfaced 18/20; English continuation
  surfaced 20/20. `semantic_evidence_guarded_to_scent_count` was 16 and
  `semantic_evidence_allowed_count` was 20.
- 100-conversation live run before the prompt-relevant catalog fix, gate worker
  only, `--case-workers 10`: 400 cases, 281 correct, accuracy 0.7025,
  `status=insufficient_live_semantic_recall`, `scent_or_evidence_recall` 0.6033.
  Root cause: `semantic_recall_gate.registry_catalog()` exposed only the stable
  top 28 registry entries to the semantic model. In the 100-case fixture, most
  positive continuation labels referred to conversations outside that window.
  Out-of-catalog Chinese continuation surfaced only 4/72, while in-catalog
  Chinese continuation surfaced 26/28.
- 100-conversation live run after adding `prompt_relevant_catalog` and
  `prompt_relevant_triggers`, the Chinese continuation template was still much
  weaker than the English template. A/B over the 12 Chinese misses showed that
  changing `这个问题后面怎么接，重点是 X` to `能接着我们之前关于 X 的那段对话继续吗？`
  recovered 12/12 misses. This was a benchmark-template mismatch, not evidence
  that Chinese continuation was inherently much worse.
- 100-conversation live run after both repairs, gate worker only,
  `--case-workers 10`: 400 cases, 399 correct, accuracy 0.9975,
  `status=sufficient`, `scent_or_evidence_recall` 0.9967, evidence recall 1.0,
  evidence false positives 0, semantic calls 300, semantic available 299,
  semantic error cases 1. Chinese continuation surfaced 99/100; English
  continuation surfaced 100/100. `semantic_evidence_guarded_to_scent_count` was
  137 and `semantic_evidence_allowed_count` was 99.
- Cost/latency observation for the corrected 10-worker 100 run: wall time 148.8
  seconds, semantic latency p50 3.70s and p95 5.48s, about 1.83M reported
  semantic tokens, provider prefix-cache hit rate 0.7373. Using DeepSeek's
  current `deepseek-v4-flash` price table, that token mix is roughly $0.102 for
  the live semantic calls. Pricing changes over time; check the official page
  before using this as a budget commitment.
- Stability observation from the earlier no-explicit-evidence run: serial and
  10-parallel 100 runs disagreed on 69 continuation semantic decisions over the
  same case ids, while both kept backend errors to 1/200 semantic calls. After
  prompt-relevant catalog repair and equivalent Chinese continuation wording,
  the remaining miss count is small enough for this slice to act as a live
  release smoke rather than a diagnosis of systemic Chinese recall weakness.
- Evidence boundary observation: the live model often returns `evidence` for
  vague continuation prompts, especially English. The hook must not blindly
  downgrade every semantic `evidence` to `scent`; the live evidence cases now
  prove the narrower boundary: vague continuation stays `scent`, while explicit
  prior wording/source/decision prompts may surface source-backed evidence.
- #201 / #786 live semantic route-actionability smoke on 2026-06-07: public
  checked-in local corpus converted to clean source, 4 conversations / 8 cases,
  DeepSeek-compatible live semantic route enabled with `--semantic-workers
  default`, `--case-workers 1`, and sanitized JSON output under `.tmp`. Result:
  `status=sufficient`, `quality_gate_ok=true`, 8/8 correct, semantic available
  4/4, evidence false positives 0, and `semantic_evidence_guarded_to_scent_count=3`.
  All 3 high-confidence paid/live semantic `evidence -> scent` continuation
  cases carried `source_required` / `reopenable_route`,
  `semantic_evidence_guarded_to_plain_scent_count=0`,
  `paid_semantic_hit_to_source_reopen_rate=1.0`,
  `manual_query_invention_after_paid_semantic_hit_count=0`,
  `all_scent_collapse_rate=0.0`, and
  `live_semantic_route_actionability=source_required_reopen_route`. This proves
  the source-reopen route projection and no-manual-query handoff for this public
  live smoke only. It pairs with the deterministic recall-navigation
  follow-through fixture for bounded-evidence-after-reopen behavior; the live
  smoke itself reports `bounded_evidence_after_semantic_reopen_rate` as not
  measured and does not claim all future semantic prompts or private-registry
  vague recall are solved.
- #786 semantic-reopen smoke on 2026-06-06: public checked-in local corpus
  converted to clean source, 4 conversations / 8 cases, DeepSeek-compatible
  live semantic route enabled with `--semantic-workers default`,
  `--case-workers 1`, and sanitized JSON output under `.tmp`. Result:
  `status=sufficient`, `quality_gate_ok=true`, 8/8 correct,
  semantic available 4/4, evidence false positives 0, and
  `semantic_evidence_guarded_to_scent_count=3`. All 3 guarded semantic
  `evidence -> scent` continuation cases now carried
  `source_required` / `reopenable_route`, with
  `semantic_evidence_guarded_to_plain_scent_count=0` and
  `live_semantic_reopen_quality=source_required_reopen_route`. This proves the
  source-reopen route projection for this public smoke only; it does not claim
  all future semantic prompts are correct.
- Sampling caveat: these runs consume the first converted coding conversations,
  not a stratified sample of the full public coding corpus.

Current smoke and diagnostic results from 2026-05-27:

- repeatable baseline suite: `baseline_captured_with_known_gaps`,
  `ok=true`, `quality_gate_ok=false`; the remaining suite gap is the
  semantic-sidecar-required source-evidence slice, because selected sample count
  is still below the minimum
- synthetic Track A gate benchmark before the harder family: 7 cases, 7
  correct, macro F1 1.0, over-escalation 0, evidence false positives 0,
  semantic model calls 0
- public-real ShareGPT coding Track A P1 gate benchmark now defaults to seeded
  stratified sampling:
  `python benchmarks\aippocampus\benchmark_memory_decision_gate.py --case-set sharegpt-coding --sharegpt-conversations 100 --sharegpt-sampling-mode seeded-stratified --sharegpt-seed 218`;
  reports include sampling seed, selected conversation id hashes, eligible
  population count, skipped counts, and stratum counts. The earlier 2026-05-29
  baseline used the first 100 converted coding conversations and was 500/500
  correct, accuracy 1.0, macro F1 1.0,
  `scent_or_evidence_recall` 1.0, `evidence_recall` 1.0, evidence false
  positives 0, over-escalation 0, semantic model calls 200
- the ShareGPT P1 case families now make the vague-continuation boundary
  explicit: fresh user prompts stay `skip`; semantic-off vague-continuation
  controls stay `skip`; mock semantic-positive Chinese and English continuation
  prompts become `scent`; explicit source-backed requests become `evidence`
- root-cause check for the earlier ShareGPT P1 score: all 100 previous
  `should_scent` cases had registry candidates, with score range 21.5 to 51.5
  and median 32.5, so the miss was not candidate retrieval. The old
  deterministic runner disabled the semantic gate while labeling weak-deictic
  prompts as `should_scent`. The repaired boundary does not plug this with a
  larger static continuation word list; it treats vague continuation as
  semantic-required, then uses deterministic semantic fixtures to verify the
  prompt hook's downstream behavior. The earlier `should_skip -> scent` false
  positives came from short English associative cue substring matches such as
  `rag` inside unrelated words and bare `hook/evidence` in non-memory prose;
  those are now covered by token-boundary tests and narrower cue phrases.
- historical sampling caveat: pre-#218 `--sharegpt-conversations 100` smoke
  reports consumed the first 100 converted conversations, which came from
  `common_en_70k.jsonl` in that run. Those older reports remain reproducible
  smoke evidence, but not stratified samples of the full coding corpus.
- existing real-history FTS5/source baseline after the 2026-05-29 rerun: 959
  registry threads, 810 eligible threads, 9,699 messages scanned, 97/100 FTS5
  top-10 hits, and 98/100 production-hybrid top-10 hits. This is a
  source-derived sparse-query sanity line for index health and stale-SQLite
  detection; by itself it does not claim natural user-query, paraphrase, or
  cross-language recall.
- synthetic Track C payload benchmark: first run caught a false positive where a
  parked-memory trap prompt woke an unrelated active working-memory row via the
  generic action term `mutation`; after tightening working-memory trigger noise,
  rerun result was 8 cases, 8 payload-correct, source fidelity 1.0, privacy
  breaches 0, parked-memory injections 0, evidence-without-source 0
- Track B unified retrieval wrapper, FTS5 source-line track: 100 real-history
  cases, FTS5 R@1 0.86, R@3 0.96, R@5 0.97, R@10 0.97, MRR 0.9073; production
  hybrid R@10 0.98, MRR 0.8898. In the unified report this track is classified
  as `source_derived_sparse`, and its hit rates must be reported beside, not
  averaged into, non-source-derived query arms.
- Track B selected source-evidence track, semantic-sidecar-required slice after
  the bounded 2026-05-29 private sidecar refresh:
  sufficient, 100 selected cases, 97/100 top-5 hits, 0.97 hit rate. The 3 misses
  were all `rank_below_top_k` with extended ranks 6, 8, and 10. This fixed the
  earlier sparse-pool problem without weakening the sidecar validator: accepted
  semantic labels still require exact message refs and per-label evidence.
  `benchmark_corpus/` can feed public Track B retrieval baselines, but it should
  not be counted into this private real-history slice unless it is reported as a
  separate bounded public semantic-sidecar track.
- #963 Track B selected private rerun and repair:
  a same-day pre-repair rerun on current main observed 100 selected cases,
  95/100 top-5 hits, and 5 sanitized misses. All five had the gold source in
  the raw candidate pool but below top-5, so the miss taxonomy was
  `candidate_pruned_before_verifier` / `candidate_generated_rank_below_top_k`,
  not candidate generation failure or source reopen failure. A public
  deterministic analogue now covers the actionable class where repeated use of
  one cue term outranks the correct source that covers several source-derived
  cues. After bounding repeat scoring and preferring distinct source-term
  coverage in the local `dynamic_source` diagnostic ranking path, the selected
  private rerun reports 100/100 top-5 hits, `top_k_hit_rate=1.0`,
  `failed_count=0`, and an empty sanitized taxonomy. This supersedes the
  97/100 selected-private Track B row only for this bounded slice.
- Track B public semantic-sidecar track:
  implemented as a separate optional wrapper track. Current 2026-05-29 pilot
  uses a bounded ShareGPT public registry subset with generated/reviewed
  `semantic-scope-labels.jsonl`; result is 3 reviewed sidecar rows, 3 selected
  cases, 3/3 top-5 hits, `claim_level=diagnostic_pilot`, and
  `minimum_empirical_case_count=50`. Keep this as a public pilot until the
  sidecar-reviewed public sample is materially larger; do not merge it into the
  private `semantic-sidecar-required` metric. Current runner reports also carry
  no-sidecar and wrong-message anti-circular controls, so a future larger pilot
  must show sidecar lift without a matching negative-control pass.
- Track B selected source-evidence track, deterministic source-label slice:
  sufficient, 100 selected cases, 97/100 top-5 hits, 0.97 hit rate. The
  remaining misses are 2 `rank_below_top_k` cases and 1
  `scope_term_split_across_expected_turn` case. The default selected-source
  sample is now 100 max / 50 min cases for this deterministic slice.

These results show the first deterministic gate slice is stable and the exact
source-line retrieval layer is strong but not perfect. The ShareGPT P1 slice is
a baseline, not a repair target: it exposes the current product shape on public
coding conversations before AIppocampus finishes its next upgrades. The first B
fixes removed two evaluator weaknesses: source labels and query terms split
across sibling clean-source rows in the same turn, and generic fuzzy-prompt
frame terms dominating the source-derived cue terms. The latest private
semantic-sidecar refresh removed the sparse-pool blocker, and #963 removed the
current selected-slice top-k pruning misses by preventing repeated single-cue
decoys from outranking broader source-term coverage. These results do not yet
prove real-history gate quality, live semantic-model quality, full semantic
completeness, or end-to-end payload fidelity on private real-history prompts.

- #400 LoCoMo answer-usefulness prototype:
  `benchmark_locomo_answer_usefulness.py` adds a second-stage public
  retrieval-QA scorer over LoCoMo. It keeps Track B source-evidence retrieval,
  context gathering, answer generation, source citation, and unsupported
  inference refusal as separate report layers. The runner consumes external
  answer predictions with retrieved context ids, answer text, citation ids, and
  refusal flags; it also ships a deterministic contract baseline for CI. Gold
  answers and gold evidence ids stay out of answer-generation inputs, while the
  deterministic judge can use them only for scoring. This is product-layer
  usefulness telemetry under fixed answer-model/evaluator settings, not a
  replacement for retrieval-only Track B metrics and not a SOTA or competitor
  comparison.

## Non-Goals

- Do not use this as a MemPalace/CraniMem comparison unless explicit adapters
  and equivalent case runners exist.
- Do not treat embedding similarity as ground truth. Similarity scores may be
  reported as analysis, but labels must come from source-backed case specs.
- Do not let an LLM generate both the cases and the grading labels.
- Do not put live LLM calls in the required CI gate.
- Do not emit raw private text, snippets, absolute paths, or local registry
  details in benchmark reports by default.

## Benchmark Positioning: Retrieval Quality vs End-to-End QA

AIppocampus benchmarks measure retrieval and decision quality, not end-to-end
question-answering accuracy. This is an intentional design choice, not a gap.
AIppocampus is the agent's little hippocampus: it decides when old memory should
surface, selects the relevant scope, and retrieves source-backed evidence. The
main agent still owns reading that evidence, reasoning with the current task,
and generating the final answer.

The dominant industry benchmarks (LoCoMo LLM-as-Judge, LongMemEval aggregate
accuracy) score the product of two independent capabilities:

1.  **Memory retrieval**: can the system find the right source?
2.  **LLM reasoning**: given the retrieved source, can the model produce the
    correct answer?

These two factors are conflated in a single percentage. Swapping the underlying
LLM changes the score without any change to the memory system itself. Published
evidence of this conflation:

- Mem0 LongMemEval: 93.4% (self-test, unspecified model) vs 49%
  (Vectorize.io independent evaluation with different model/prompt). The 44-point
  gap is a model and methodology artifact, not a memory quality difference.
- Mem0 extraction-model ablation on LongMemEval: GPT-5 scores 91.0%, Llama 4
  Maverick scores 88.6%. Same memory system, same data, 2.4-point spread from
  model choice alone.
- Exabase M-1 (96.4% LongMemEval) uses Gemini Flash. Their own analysis states
  "retrieval architecture drove performance independent of model strength," yet
  the headline number still depends on which model generates the final answer.

Because of this conflation, leaderboard rankings primarily compare
memory-system-and-LLM combinations, not memory systems in isolation. A
higher-ranked system may simply be using a stronger answer-generation model, with
no clear way to attribute the improvement.

### What AIppocampus measures instead

AIppocampus benchmarks decompose memory quality into orthogonal layers that do
not depend on answer-generation model choice:

| Layer | Metric | What it measures | Model-dependent? |
|-------|--------|-----------------|------------------|
| Track A: Gate Decision | skip/scent/evidence accuracy, macro F1, over-escalation rate | Whether the system chooses the right memory surface | No (deterministic gate + optional semantic, scored against source labels) |
| Track B: Retrieval | R@K, MRR, message/turn hit rate, context-visible hit rate | Whether the system finds the correct source row | No (retrieval-only, no answer generation) |
| Track C: Payload Fidelity | source fidelity, privacy breach rate, parked-memory injection count | Whether the final payload is correct and safe | No (synthetic fixtures, mocked semantic gate) |
| Track D: Compaction Continuity | correction retention, adjudication status, stale-anchor suppression | Whether work-task corrections survive compaction without becoming false memory | Mixed: deterministic event checks plus optional semantic adjudication, scored against source labels |
| Track S: Semantic Robustness Diagnostics | perturbation stability, retrieval invariance, hard-negative suppression | Whether Track A/B behavior remains stable under semantic rewrites and negative constraints | No by default; optional proxy/vector diagnostics are explicit and diagnostic-only |

The optional live semantic-gate track does exercise an external model, but it
evaluates the gate decision, not answer quality. The model is part of the tested
path, not part of the scoring rubric.

### Track S: no-live-judge semantic robustness

`benchmark_semantic_robustness.py` is the Track S facade for #747. It reuses
Track A prompt-hook fixtures and Track B local source-retrieval helpers, then
reports the following diagnostics separately:

- S1 gate robustness under paraphrase, register shift, typo, syntax rewrite,
  and current-task distractor prompts.
- S2 retrieval invariance for equivalent but lexically distant public-safe
  query bundles.
- S3 hard-negative and explicit-negation suppression.
- S4 offline proxy alignment only when a local reviewed model is explicitly
  configured.
- S5 representation-space health only when a local embedding index is supplied.

Track S is diagnostic evidence, not source truth. Do not average it into Track
A/B/C/D quality scores, do not use proxy-model agreement as ground truth, and
do not require live LLM calls in the default path. See
[`semantic-robustness-track-s.md`](semantic-robustness-track-s.md) for the
current runner boundary.

### When end-to-end QA benchmarks are appropriate

End-to-end LLM-as-Judge benchmarks are useful for product-level comparisons when:

- the product is a complete conversational agent, not a memory layer
- the evaluation goal is to compare full-stack systems (memory + model + prompt)
  under identical conditions, including the same LLM, the same judge, and the
  same prompt template
- the benchmark controls for model choice by running all systems with the same
  answer-generation model and the same evaluation model

AIppocampus is a memory layer, not a full-stack agent. Adding LLM-as-Judge
scores would measure something AIppocampus does not own. If a fair head-to-head
comparison is needed, the right experiment is: same LLM, same prompt, swap only
the memory system, measure answer quality delta. That delta, not the absolute
score, is the memory system's contribution.

### Summary

AIppocampus benchmark metrics are retrieval and decision metrics. They are
comparable across any system willing to report the same retrieval-only numbers
(R@K, MRR, decision accuracy) on the same datasets. They are not directly
comparable to LoCoMo or LongMemEval aggregate accuracy percentages, because
those measure a different thing. This distinction should be stated explicitly
in any public benchmark report or comparison.

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
feasibility.

Segmented-search merge policy calibration is a separate deterministic
diagnostic under Track B's ranking boundary. The #375 runner
`benchmarks/aippocampus/benchmark_segmented_merge_policy.py` feeds synthetic
source-ref-shaped hits directly into `search_segments.py::merge_topk()` and
checks cross-segment diversity, adjacent-turn pairing, duplicate nearby recap
suppression, and stale/superseded currentness. Its report belongs in
`docs/evidence/benchmarks/segmented-merge-policy-fixture-report.md`. Passing it
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
[`docs/research/correction-reconsolidation.md`](../../research/correction-reconsolidation.md).
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
