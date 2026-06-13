# Public Readiness Continuous-Memory Ledger

Role: extracted dated-evidence detail page.
Status: current detail under the canonical public-readiness entrypoint.

This file preserves detail split out of
[`../public-readiness-verification.md`](../public-readiness-verification.md).
Keep current claim boundaries in `stage-0-5-readiness.md` and use the
entrypoint before opening this detail ledger.

## 2026-06-01 - Continuous-memory cost and harm ledger

The #410 slice adds the public-synthetic `cost_harm_ledger` to
`benchmarks/aippocampus/benchmark_continuous_memory_arms.py`, extending the
#408 attribution arms for #378.

- The report now separates foreground-only cost from amortized memory cost,
  counts modeled background prep instead of hiding it, and keeps
  `fresh_context_spec_loop` as a fair comparison baseline rather than treating
  the `no_memory` diagnostic arm as fresh-context/spec-loop.
- The harm ledger weights stale-memory false positives by severity,
  downstream turns, wrong constraints, rejected routes, current-project
  contamination, risky action before source reopen, privacy severity, and
  rollback/rework cost.
- The verified public-synthetic result reports
  `claim_level=public_synthetic_cost_harm_contract`,
  `amortized_cost_per_successful_slice=7.875` for
  `true_aippocampus_memory`, `3.07` for `fresh_context_spec_loop`,
  `harm_weighted_false_positive_cost=149.0` for `stale_wrong_memory`, and
  `highest_net_value_fair_strategy=fresh_context_spec_loop`.
- Verification commands passed:
  `python -m unittest tests.aippocampus.test_benchmark_continuous_memory_arms -v`,
  `python benchmarks/aippocampus/benchmark_continuous_memory_arms.py --json`,
  `python tools/aippocampus/docs/check_docs_health.py --json`,
  `python -m compileall -q benchmarks/aippocampus/benchmark_continuous_memory_arms.py tests/aippocampus/test_benchmark_continuous_memory_arms.py`,
  `python tools/aippocampus/run_tests.py --tier benchmark`,
  `python -m ruff check skills plugins tests tools benchmarks benchmark_corpus`,
  `git diff --check`, and `python tools/aippocampus/run_tests.py --tier fast`.
- This does not claim full #378 continuous-memory superiority, exact dollar
  accounting, live host-native cost telemetry, live compaction behavior,
  private real-history generality, answer-generation quality, or competitor
  superiority.


## 2026-06-01 - Continuous-memory pre-registration

The #407 slice adds a `preregistration` block to
`benchmarks/aippocampus/benchmark_continuous_memory_arms.py`, extending the
#378/#408/#410 report with the pre-registered endpoint and decision rule that
must be used before public-quality continuous-memory superiority claims.

- The primary endpoint is
  `source_grounded_task_success_under_equalized_cost`, chosen because it joins
  task success, source support, equalized cost, and severe false positives
  rather than allowing post-hoc metric selection.
- The report records public-quality minimums of at least 3 scenario families
  and at least 5 paired repeats per scenario x arm, with same task/seed pairs
  across arms where feasible.
- The confidence rule requires a paired `lower_bound` advantage for
  `true_aippocampus_memory` over `fresh_context_spec_loop` after hard gates
  pass; secondary metrics remain exploratory unless named in the primary
  decision rule before the run.
- The current contract-smoke preview reports
  `primary_endpoint_winner=fresh_context_spec_loop`,
  `continuous_memory_advantage_claim_allowed=false`, and decision label
  `no demonstrated memory advantage`.
- Verification commands passed:
  `python -m unittest tests.aippocampus.test_benchmark_continuous_memory_arms -v`,
  `python benchmarks/aippocampus/benchmark_continuous_memory_arms.py --json`,
  `python tools/aippocampus/docs/check_docs_health.py --json`,
  `python -m ruff check benchmarks/aippocampus/benchmark_continuous_memory_arms.py tests/aippocampus/test_benchmark_continuous_memory_arms.py`,
  `git diff --check`,
  `python -m compileall -q benchmarks/aippocampus/benchmark_continuous_memory_arms.py tests/aippocampus/test_benchmark_continuous_memory_arms.py`,
  `python tools/aippocampus/run_tests.py --tier benchmark`,
  `python -m ruff check skills plugins tests tools benchmarks benchmark_corpus`,
  and `python tools/aippocampus/run_tests.py --tier fast`.
- This does not claim public-quality #378 superiority, adequate statistical
  power, holdout scenario coverage, host-native compaction behavior, or private
  real-history generality.


## 2026-06-02 - Continuous-memory scenario provenance and holdout controls

The #409 slice extends
`benchmarks/aippocampus/benchmark_continuous_memory_arms.py` with
scenario-level provenance, holdout, and negative-control reporting for #378.

- The report now uses schema version 2 and keeps all scenario metadata
  sanitized. Rows expose `scenario_provenance`, `scenario_generated_by`,
  `scenario_source_material`, `aippocampus_internals_visible`, and
  `prompt_threshold_tuning_role`, but still hash case ids, source refs, source
  windows, and memory packet text.
- The current contract-smoke preview has 6 cases and 30 rows. Provenance slices
  are reported separately: 4 `author_written_synthetic` cases and 2
  `public_log_or_vcs_derived` + `holdout_blind` cases. The external/holdout
  share is `0.3333`, above the registered `0.30` share gate, while
  `external_written_synthetic` and `private_real_history_aggregate` remain
  `0` for this public-safe slice.
- Holdout cases use `holdout_excluded`; the report records
  `holdout_used_for_prompt_or_threshold_tuning_count=0`.
- The runner also exposes
  `--scenario-selection-role prompt_threshold_tuning`; that selection returns
  4 tuning-visible cases, excludes 2 holdout cases from rows/metrics, and keeps
  `holdout_used_for_prompt_or_threshold_tuning_count=0`.
- Public scenario metadata is guarded before JSON emission: report-visible
  generator/source-material labels reject local path separators, URI/drive
  separators, private raw-log labels, and secret-like strings.
- Scenario-level negative controls now distinguish unnecessary memory
  intervention from useful source-backed memory. The current report has 2
  negative-control cases; `true_aippocampus_memory` records 2 memory
  interventions but 0 harmful unnecessary interventions, while
  `stale_wrong_memory` triggers 2 harmful unnecessary interventions.
- The #409 controls do not turn the current contract smoke into public-quality
  superiority evidence. The report still records
  `primary_endpoint_winner=fresh_context_spec_loop`,
  `continuous_memory_advantage_claim_allowed=false`, and the cannot-claim
  boundary for public-quality #378 superiority from only
  `author_written_synthetic` or tuning-visible diagnostic scenarios.
- Verification commands passed during this slice:
  `python -m unittest tests.aippocampus.test_benchmark_continuous_memory_arms -v`,
  `python benchmarks/aippocampus/benchmark_continuous_memory_arms.py --json`,
  `python benchmarks/aippocampus/benchmark_continuous_memory_arms.py --scenario-selection-role prompt_threshold_tuning --json`,
  `python tools/aippocampus/docs/check_docs_health.py --json`,
  `python -m ruff check benchmarks/aippocampus/benchmark_continuous_memory_arms.py tests/aippocampus/test_benchmark_continuous_memory_arms.py`,
  `python -m compileall -q benchmarks/aippocampus/benchmark_continuous_memory_arms.py tests/aippocampus/test_benchmark_continuous_memory_arms.py`,
  `python tools/aippocampus/run_tests.py --tier benchmark`,
  `python -m ruff check skills plugins tests tools benchmarks benchmark_corpus`,
  `git diff --check`, and `python tools/aippocampus/run_tests.py --tier fast`.
- This does not claim live host-native compaction behavior, external-written
  synthetic reviewer coverage, private real-history generality, competitor
  superiority, or public-quality #378 advantage.


## 2026-06-02 - Continuous-memory host-native baseline contract

The #406 slice extends
`benchmarks/aippocampus/benchmark_continuous_memory_arms.py` with a
host-native continuous baseline for #378.

- The report now distinguishes `bare_continuous_no_memory` from
  `host_native_continuous_no_aippocampus`. The former is the old no-context
  diagnostic arm; the latter is a Codex-style same-thread compaction/summary
  contract with AIppocampus hook recall, MCP recall tools, active recall, and
  registry memory injection disabled.
- The current contract-smoke preview still uses 6 public-safe cases, now across
  6 arms, and bumps the report contract to `schema_version=3`. It reports
  `host_native_compaction_lift_over_bare_continuous` and includes
  `host_native_continuous_no_aippocampus` in `comparison_baselines` with
  `documented_host_family=codex`,
  `host_version_or_build=record_at_live_run_when_available`,
  `compaction_settings=host_default_same_thread_summary_or_compaction_contract`,
  `aippocampus_memory_surfaces_disabled=true`, and
  `host_native_compaction_enabled=true`.
- This is a deterministic baseline contract, not live host telemetry. The
  report keeps `uses_live_host_native_compaction=false` and
  `live_measurement_status=not_measured_in_this_diagnostic_runner`.
- Verification commands passed during this slice:
  `python -m unittest tests.aippocampus.test_benchmark_continuous_memory_arms -v`,
  `python benchmarks/aippocampus/benchmark_continuous_memory_arms.py --json`,
  `python tools/aippocampus/docs/check_docs_health.py --json`,
  `python -m ruff check benchmarks/aippocampus/benchmark_continuous_memory_arms.py tests/aippocampus/test_benchmark_continuous_memory_arms.py`,
  `python -m compileall -q benchmarks/aippocampus/benchmark_continuous_memory_arms.py tests/aippocampus/test_benchmark_continuous_memory_arms.py`,
  `git diff --check`, `python tools/aippocampus/run_tests.py --tier fast`, and
  `python tools/aippocampus/run_tests.py --tier benchmark`.
- This does not claim
  `AIppocampus_has_beaten_realistic_host_native_continuous_workflows`, live
  host-native compaction behavior, cross-host baseline coverage, private
  real-history generality, or public-quality #378 advantage.


## 2026-06-03 - Continuous-memory cost/harm sensitivity sweep

The #378 runner now extends `cost_harm_ledger` with
`sensitivity_analysis`, bumping
`benchmarks/aippocampus/benchmark_continuous_memory_arms.py` to
`schema_version=4`.

- The sweep reports `basis=public_synthetic_weight_sweep` and
  `claim_level=diagnostic_weight_sensitivity`.
- It reruns the fair-winner calculation across `base_formula`, `harm_heavy`,
  `memory_cost_light`, and `fresh_context_rebuild_expensive` scenarios, while
  still excluding `oracle_memory` from fair winners.
- The verified public-synthetic result reports
  `winner_distribution={"fresh_context_spec_loop": 3,
  "host_native_continuous_no_aippocampus": 1}`,
  `continuous_memory_advantage_stable_across_sweep=false`, and
  `true_memory_margin_vs_best_baseline_units={"min": -27.7675,
  "max": -9.6738}`.
- This is a guard against treating one heuristic formula as headline evidence.
  It does not calibrate weights against user studies, production incidents, or
  live host telemetry.
- Verification commands passed during this slice:
  `python -m unittest tests.aippocampus.test_benchmark_continuous_memory_arms`,
  `python benchmarks/aippocampus/benchmark_continuous_memory_arms.py --json`,
  `python tools/aippocampus/docs/check_docs_health.py --json`,
  `python -m ruff check benchmarks/aippocampus/benchmark_continuous_memory_arms.py tests/aippocampus/test_benchmark_continuous_memory_arms.py`,
  `git diff --check`, `python tools/aippocampus/run_tests.py --tier fast`, and
  `python tools/aippocampus/run_tests.py --tier benchmark`.
- This does not claim cost-weight robust continuous-memory advantage,
  public-quality #378 superiority, live host-native cost telemetry, private
  real-history generality, or competitor superiority.


## 2026-06-10 - Context-loss continuous-memory diagnostic slice

The #1153 readout adds a stable missing-context / incomplete-handoff slice to
the existing continuous-memory attribution runner.

- Command:
  `python benchmarks\aippocampus\benchmark_continuous_memory_arms.py --json --output .tmp\continuous-memory-1153-smoke.json`.
- The report now includes
  `github_1153_context_loss_public_continuity_v1` under
  `preregistered_slices`.
- It preserves
  `continuous_memory.preregistered_repeat_profile_2026_06_08` as the old
  short complete-spec expected-null row and sets
  `supersedes_historical_row=false`.
- The 2026-06-10 smoke reports `contract_gate_ok=true` and
  `quality_gate_ok=false`.
- Strategy success rates are separated: `fresh_missing_context=2/6`,
  `summary_only_host_native=4/6`, `aippocampus_route_packet=5/6`,
  `sham_unrelated_memory=2/6`, `stale_wrong_memory=0/6`, and
  `oracle_full_context=6/6`.
- Source reopen, stale revival, memory drag, manual restatement /
  context-rebuild proxy, token / latency cost, and no-remember controls are
  separate fields rather than one flattering aggregate.
- LoCoMo-style public dialogue remains an optional same-dialogue evidence-id
  control path. This slice does not claim LoCoMo continuity quality, private
  real-history generality, live host-native behavior, calibrated restatement
  burden reduction, answer-generation quality, or public-quality continuous
  memory advantage.


## 2026-06-08 - Continuous-memory preregistered repeat readout

The #378 runner now has an explicit public-synthetic repeat profile for the
registered lower-bound rule.

- Command:
  `python benchmarks\aippocampus\benchmark_continuous_memory_arms.py --public-quality-repeat-profile --json --output .tmp\continuous-memory-repeat-profile.json`.
- The run reported `runner_profile=public_synthetic_preregistered_repeat`,
  `repeat_count_per_case_arm=5`, `case_arm_trial_count=30`, and
  `row_count=180`.
- The repeated readout reported
  `lower_bound_method=minimum_observed_paired_delta_for_deterministic_public_synthetic_repeats`,
  `lower_bound_units=-27.7675`, `mean_delta_units=-27.7675`,
  `lower_bound_passed=false`,
  `primary_endpoint_winner=fresh_context_spec_loop`, and
  `decision_label=no demonstrated memory advantage`.
- This is public-safe expected-null evidence for the preregistered no-advantage
  rule. The public interpretation is `no demonstrated net advantage over
  modeled fresh-context spec loop`: the true-memory arm still beats `no_memory`
  and `sham_unrelated_memory` on success rate, but loses the primary endpoint
  because the complete-spec reset loop is modeled as perfect, lower-cost, and
  harm-free for this short task slice.
- The five repeats are deterministic replicated lower-bound rows, not
  independent empirical trials. A future repeat profile should either make
  repeat seeds drive real perturbations or keep this deterministic label
  prominent.
- The boundary-oriented alias is
  `boundary_confirmed.short_task_complete_spec_synthetic_2026_06_08`; the
  historical metric id remains
  `continuous_memory.preregistered_repeat_profile_2026_06_08` for source
  continuity.
- It evaluates the lower-bound gate instead of leaving it as prose, but it
  still does not claim full #378 continuous-memory superiority.
- Verification commands passed during this slice:
  `python -m unittest tests.aippocampus.test_benchmark_continuous_memory_arms -v`
  and the repeat-profile command above. Broader PR-lane verification is tracked
  in the merge PR for this slice.
- This does not claim live host-native cost or compaction telemetry, private
  real-history generality, cost-weight robust continuous-memory advantage,
  answer-generation model quality, or competitor superiority.


## 2026-06-09 - Continuous-memory expected-null interpretation

The #960 documentation rerun keeps the 2026-06-08 no-advantage decision
unchanged while reclassifying the public reading as a short complete-spec
boundary condition.

- Command:
  `python benchmarks\aippocampus\benchmark_continuous_memory_arms.py --public-quality-repeat-profile --json --output .tmp\continuous-memory-repeat-profile-960-verify.json`.
- The run again reported `runner_profile=public_synthetic_preregistered_repeat`,
  `repeat_count_per_case_arm=5`, `row_count=180`,
  `true_aippocampus_memory.success_rate=0.8333`,
  `no_memory.success_rate=0.3333`,
  `sham_unrelated_memory.success_rate=0.3333`,
  `host_native_continuous_no_aippocampus.success_rate=0.6667`, and
  `primary_endpoint_winner=fresh_context_spec_loop`.
- Interpretation: the result remains negative for the registered net-value
  endpoint, but it is not evidence that source-backed recall has no useful
  lift. It shows no demonstrated net advantage over the modeled fresh-context
  spec loop for a short complete-spec public-synthetic slice.
- The report exposes `expected_null_remediation` as a machine-readable #960
  ledger with `primary_endpoint_changed=false`,
  `benchmark_thresholds_changed=false`, and
  `product_change_status=candidate_identified_not_implemented`; this records
  per-family hypotheses without weakening the lower-bound rule.
- Follow-up product surfaces are route minimality, source-reopen fallback,
  abstention usefulness, no-harm hint suppression, and cost/harm accounting.
