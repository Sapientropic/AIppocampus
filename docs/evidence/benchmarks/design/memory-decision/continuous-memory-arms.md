# Memory Decision Continuous-Memory Arms

Role: extracted implemented-slice detail page.
Status: current detail under [`implemented-slices.md`](implemented-slices.md).

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

The `preregistered_slices` block records which narrow #378 / #1153 slices this
report actually ran. The original #378 slice remains
`github_378_continuous_memory_public_synthetic_v1`. The #1153 context-loss
slice is `github_1153_context_loss_public_continuity_v1`. The default runner
profile remains a deterministic public-synthetic contract smoke over the six
attribution-arm fixtures: it freezes sanitized case-manifest inputs,
scenario-selection role, required fair strategies, primary endpoint, decision
preview, context-loss readouts, and public-quality gates, but it has only one
deterministic repeat per case/arm.

The #1153 readout deliberately separates the missing-context condition from the
old complete-spec expected-null row. Its strategy map is:

- `fresh_missing_context` -> `no_memory`
- `summary_only_host_native` -> `host_native_continuous_no_aippocampus`
- `aippocampus_route_packet` -> `true_aippocampus_memory`
- `sham_unrelated_memory` -> `sham_unrelated_memory`
- `stale_wrong_memory` -> `stale_wrong_memory`
- `oracle_full_context` -> `oracle_memory`
- `fresh_context_spec_loop_complete_spec` -> historical boundary reference
  only, not the primary context-loss opponent.

The readout exposes separate metrics for task success, source-reopen behavior,
memory drag, stale revival, manual restatement / context-rebuild proxy cost,
token / latency cost, and no-remember controls. The 2026-06-10 smoke reports
`contract_gate_ok=true` and `quality_gate_ok=false`: selected public-safe
context-loss cases are now executable and machine-readable, but this is not a
public-quality continuous-memory advantage claim. It preserves
`continuous_memory.preregistered_repeat_profile_2026_06_08` as the short
complete-spec expected-null row.

The public-dialogue suggestion for #1153 is recorded as a control path, not as
a broad claim: LoCoMo-style same-dialogue evidence-id scoring remains useful
through `benchmark_locomo_public_users.py` / `benchmark_locomo_qa.py`, but it
must not be read as cross-thread, cross-conversation, private-history, or
life-wide continuity quality without a separate scored prediction run and
claim boundary.

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
