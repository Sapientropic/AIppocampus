# Current Evidence Claims

Role: current benchmark/readiness claim snapshot.
Status: current owner for numeric evidence claims, supersession,
`supports` / `material_limits` report projection, material claim boundaries, and
confirmed scope-boundary remediation pointers.

This is the current-claims snapshot for benchmark and readiness numbers that
are easy to over-read when old dated ledgers still say "current" in their local
context. It is not a command ledger and it does not replace source reports.

Snapshot review date: 2026-06-15.
Row-level `run_date`, metric IDs, and source-report dates are authoritative for
promoted rows added after that full-file review date.

## Claim Reviewer Card

current_status: current owner for promoted benchmark/readiness numbers; dated
reports remain bounded evidence until a row below promotes or supersedes them.

can_say: AIppocampus has source-backed continuity evidence for the named rows,
within each row's `run_date`, `cohort`, `claim_level`, `supports`, and
`material_limits`.

cannot_say: do not claim new benchmark quality, public readiness, live host
behavior, private-history quality, or official external scores from a historical
report title alone.

owner_routes:

- Current numeric claims: `docs/evidence/current-claims.md#current-claim-snapshot`.
- Readiness status and gaps: `docs/evidence/readiness/stage-0-5-readiness.md`.
- Benchmark report routers: `docs/evidence/benchmarks/reports/README.md`.

claim_safe_next_action: open the relevant claim row and source report first;
use docs-health only after deciding whether the row needs promotion,
supersession, or a no-open-followup note.

next_verification_command:

```powershell
python tools\aippocampus\docs\check_docs_health.py --json
```

## Detailed Evidence Index

Rules:

- A value is current only for the `run_date`, `cohort`, and `claim_level` named
  in its row.
- Dated evidence remains in
  [`docs/evidence/readiness/public-readiness-verification.md`](readiness/public-readiness-verification.md)
  and detailed benchmark methodology remains in
  [`docs/evidence/benchmarks/design/memory-decision-benchmark-plan.md`](benchmarks/design/memory-decision-benchmark-plan.md).
- Benchmark priority, run-profile, and claim-boundary ownership remains in
  [`docs/evidence/benchmarks/design/benchmark-priority-map.md`](benchmarks/design/benchmark-priority-map.md).
- Benchmark maturity, sample-size floors, and the separation between
  `contract_gate_ok` and `quality_gate_ok` remain in
  [`docs/evidence/benchmarks/design/benchmark-maturity-gates.md`](benchmarks/design/benchmark-maturity-gates.md).
- Closed benchmark/evidence issue states such as `harness-ready`, `pilot-run`,
  `contract-smoke`, `blocker-recorded`, and `completed-score` remain in
  [`docs/evidence/benchmark-evidence-maturity.md`](benchmark-evidence-maturity.md).
  Use that ledger before reading an issue title as a completed score.
- Stage-level positive claims and launch boundaries remain in
  [`docs/evidence/readiness/stage-0-5-readiness.md`](readiness/stage-0-5-readiness.md).
- New public-facing benchmark reports should project `measured_result`,
  `supports`, and `material_limits` first. Keep `cannot_claim` as a short
  legacy compatibility or durable-boundary field, not as the default reader
  foreground.
- Demo caveats in
  [`docs/guides/demo-scenarios.md`](../guides/demo-scenarios.md) are
  claim-boundary inputs, not standalone benchmark proof.
- AMemGym adapter smoke currently has no Current Claim Snapshot row; its
  native-score, source-backed overlay, diagnosis, utilization, and cost/latency
  boundaries stay in
  [`docs/evidence/benchmarks/amemgym.md`](benchmarks/amemgym.md) until a dated
  result owner upgrades a claim.
- STATE-Bench Agent Learning feasibility now has a blocker/defer Current Claim
  Snapshot row, not a score row. Adapter/readiness and one-domain preflight
  evidence stay in
  [`docs/evidence/benchmarks/state-bench-agent-learning.md`](benchmarks/state-bench-agent-learning.md);
  the 2026-06-14 decision rechecked the official source and records that the
  locked GPT-5.4 evaluation client endpoint/deployments are still not
  configured in this environment.
- PersonaMem / PersonaMem-v2 currently has no Current Claim Snapshot row and
  should not be run as a retrieval-only quality claim. A first public-safe
  Ficus MVP exists for schema/lifecycle/hard-mask fixtures, but it is not a
  PersonaMem score or broad profile-quality row. The readiness boundary stays
  in [`docs/evidence/benchmarks/personamem-readiness.md`](benchmarks/personamem-readiness.md).
- LoCoMo text-QA currently has a fixed-reader answer/latency harness, but no
  Current Claim Snapshot row yet. Keep its dry-run as schema/privacy evidence
  only; a dated fixed-reader provider report is required before citing answer
  quality.
- LongMemEval-S now has a first dated fixed-reader provider answer/latency
  baseline on a 25-question public cohort. Keep it separate from the larger
  500-question retrieval-only rows and from official LongMemEval judge claims.
- LongMemEval-S now has 500-question rows that separate the current
  source-worker-surface proxy, the opt-in LLM query/candidate upper bound, and
  the contract-aware full-source semantic-scope warming path. Treat the older
  100-question query/cache row as progress evidence. The full-source warming
  row improves sidecar coverage but does not improve fused R@10, so it is a
  measured bottleneck, not a product-quality closeout.
- LongMemEval-S now also has a 500-question source factual-alias closeout row.
  It improves bounded candidate evidence coverage to `463/479 = 0.9666`, keeps
  fused R@10 at `422/479 = 0.8810` with zero fused regressions, and records
  zero hot-path provider calls. This closes #1323/#1327/#1424 only as bounded
  source-side retrieval evidence, not as answer generation, official QA score,
  or source truth from aliases.
- LongMemEval-S now has a #1327 source-window coverage diagnostic that
  separates candidate-missing misses from reranker-visible misses and records a
  bounded candidate-coverage projection plus a rejected naive large-radius
  negative control. It does not make route candidates source truth or justify
  dumping wider foreground context by default.
- LongMemEval-V2 currently has an official-harness pilot decision and
  text-only Memory adapter contract, but no Current Claim Snapshot row yet.
  Keep the decision report and any tiny dry run as integration evidence only;
  a dated official-harness run is required before citing V2 answer accuracy,
  LAFS, or latency quality.

## Confirmed Scope Boundaries (Expected Null Results)

Start here before opening dated report history. These rows are the current
reader-facing ledger for open and resolved remediation routes that are easy to
over-read as either broad product failure or broad product proof. A confirmed
scope boundary is still real evidence: keep the original result visible, then
state the condition where the result does and does not apply.

### Continuous-memory short complete-spec boundary

- **Current evidence state:** The 2026-06-09 #960 product-remediation rerun preserves the expected-null boundary:
  `lower_bound_passed=false`; the historical row keeps `decision_label=no demonstrated memory
  advantage`, and the public interpretation is `no demonstrated net advantage over modeled
  fresh-context spec loop`. The product path now reports
  `product_change_status=implemented_rerun` for source-miss fallback: source-required packets
  with no reopenable ref ask for a minimal source anchor instead of guessing or silently dying.
- **Remediation route:** [#960](https://github.com/Sapientropic/AIppocampus/issues/960) is closed as the first
  remediation/rerun slice; a future repeated-evidence row would need a new owner before
  superseding this boundary.
- **Reader boundary:** Do not claim continuous-memory superiority until a later dated row supersedes this evidence;
  also do not read this as evidence that source-backed recall has no value in context-loss,
  cross-thread, post-compaction, or long-horizon scenarios.

### Track B private source-evidence retrieval

- **Current evidence state:** The current selected private slice is 100/100 top-5 after the #963 dynamic-source ranking
  repair; the pre-repair same-day run exposed 5 top-k pruning misses, all with the gold source
  present in the raw candidate pool.
- **Remediation route:** [#963](https://github.com/Sapientropic/AIppocampus/issues/963) is closed; the fix is reflected in the current snapshot row.
- **Reader boundary:** Do not turn the selected slice into broad real-user gate quality, semantic completeness, or public benchmark score.

### Retrieval score-fusion calibration

- **Current evidence state:** The 2026-06-10 public fixture reports 5/5 expected top matches across exact-quote guard,
  question-tracking semantic bridge, wrong-stance lure suppression, explicit vector-unavailable
  fallback, and missing source-join rejection. The 2026-06-14 source-joined routing decision
  keeps text-first defaults and defers vector prefilter/local embedding adoption.
- **Remediation route:** [#309](https://github.com/Sapientropic/AIppocampus/issues/309) closed as a bounded routing/fusion decision owner.
- **Reader boundary:** Do not treat this as default vector-prefilter adoption, local embedding adapter evidence, live
  answer quality, source truth, or broad vector/graph/rerank consumer safety by default.

### AMemGym official live-provider score blocker

- **Current evidence state:** AMemGym has adapter/protocol/overlay evidence but no Current Claim Snapshot metric row yet; the
  2026-06-11 #1232 resume attempt used #1229 provider-budget preflight and a topped-up
  OpenRouter account, then diagnosed the post-top-up failure as an OpenRouter provider-route
  block: the required OpenAI-family routes fail even on a harmless fixed prompt, while
  non-OpenAI OpenRouter routes still accept that prompt. Outputs remain partial: `overall` is
  still partial at 6/20 user items, `upperbound` is still partial at 38/882 choice evaluations,
  and `random` is complete.
- **Remediation route:** [`amemgym-official-live-provider-1232-blocker-2026-06-11.md`](benchmarks/reports/amemgym/amemgym-official-live-provider-1232-blocker-2026-06-11.md)
  closes [#1232](https://github.com/Sapientropic/AIppocampus/issues/1232) as the current
  provider-route-blocked report;
  [`amemgym-official-live-provider-1083-checkpoint-2026-06-10.md`](benchmarks/reports/amemgym/amemgym-official-live-provider-1083-checkpoint-2026-06-10.md)
  closed [#1083](https://github.com/Sapientropic/AIppocampus/issues/1083);
  [`amemgym-official-live-provider-blocker-2026-06-09.md`](benchmarks/reports/amemgym/amemgym-official-live-provider-blocker-2026-06-09.md)
  closed [#958](https://github.com/Sapientropic/AIppocampus/issues/958).
- **Reader boundary:** Do not present protocol output, partial OpenRouter output, bounded subset output,
  resume/checkpoint output, provider-budget adoption, route-preflight output, or overlay
  diagnostics as an official live-model score.

### E2E50 public behavior-pack / private-local blocker split

- **Current evidence state:** The 2026-06-12 #279 update makes the checked-in 50-case public-safe behavior pack the primary
  executable E2E50 path: it covers silent constraints, rejected-route avoidance,
  transient-concern extinction, superseded currentness, scope-limited constraints,
  summary-overhang traps, no-remember negatives, and source reopen before risky action. The
  private/local #1086/#279 follow-up remains useful dogfood: the wide scanner finds 23/20
  candidate seeds, but local annotation retains only 7 control/seed cases against the 20-case
  private target.
- **Remediation route:** `python benchmarks/aippocampus/benchmark_e2e50_silent_constraint.py --json` is the public
  behavior-pack replay;
  [`e2e50-private-local-seed-followup-2026-06-10.md`](benchmarks/reports/e2e50/e2e50-private-local-seed-followup-2026-06-10.md)
  closes [#1086](https://github.com/Sapientropic/AIppocampus/issues/1086) as a private/local
  blocker report;
  [`e2e50-private-annotation-readiness-2026-06-10.json`](benchmarks/reports/e2e50/e2e50-private-annotation-readiness-2026-06-10.json)
  is the optional private scorer replay.
- **Reader boundary:** Do not make private-history case scarcity the main public E2E50 blocker. Also do not claim
  private-history behavior lift, completed private 20-case quality, representative or live
  50-case E2E50 quality, or live host behavior from the public pack.

### React VCS lexical near-miss false positives

- **Current evidence state:** The current 2026-06-09 row reports 60/60 gold true positives and 30/30 explicit-cue hard negatives suppressed.
- **Remediation route:** [#961](https://github.com/Sapientropic/AIppocampus/issues/961) is closed; the fix is reflected in the current snapshot row.
- **Reader boundary:** Do not use older 2026-06-04 false-positive evidence as the current source-disambiguation state.

### Progressive recall route follow-through gaps

- **Current evidence state:** The current row reports `route_actionability_rate=1.0` and eligible
  `source_reopen_follow_through_rate=1.0`, with stale handles rejected before source use.
- **Remediation route:** [#962](https://github.com/Sapientropic/AIppocampus/issues/962) is closed; the fix is reflected in the current snapshot row.
- **Reader boundary:** This still does not close broad live #201 or default foreground-lift claims.

### Multimodal NIAH stale conflicting-source selection

- **Current evidence state:** The current row reports 4/4 answer/source-selection/source-anchor-citation after conflict repair
  and keeps the ambiguous-currentness negative control as reopen-required.
- **Remediation route:** [#964](https://github.com/Sapientropic/AIppocampus/issues/964) is closed; the fix is reflected in the current snapshot row.
- **Reader boundary:** This is a supplied-pool synthesis contract, not retrieval or live vision-model quality.

### Track S explicit-negation/currentness failures

- **Current evidence state:** The current 2026-06-09 row reports `quality_gate_ok=true` for the diagnostic Track S threshold
  only, S1 false evidence 0, and S3 explicit-negation/stale-as-current/evidence-over-escalation
  counts all 0.
- **Remediation route:** [#992](https://github.com/Sapientropic/AIppocampus/issues/992) owns this repair; the fix is reflected in the current snapshot row.
- **Reader boundary:** This is a public-safe deterministic hook/retrieval diagnostic, not human-level semantic
  understanding, public product quality, or broad private-history recall quality.

### Semantic source-review operational partial failure

- **Current evidence state:** The current 2026-06-09 #1053 96-case rerun has `failure_count=0`,
  `failure_taxonomy.by_class={}`, and `failed_label_categories=[]`; `preference` met the
  per-label floor at 6/9.
- **Remediation route:** [#993](https://github.com/Sapientropic/AIppocampus/issues/993) and
  [#1053](https://github.com/Sapientropic/AIppocampus/issues/1053) are closed; the fixes are
  reflected in the current snapshot row.
- **Reader boundary:** Do not treat the broader diagnostic as human review, provider-independent quality, a green gate, or full semantic correctness.


### Continuous-Memory Reading Boundary

> **Reading boundary:** The 2026-06-08 repeat profile is an expected null result
> for a short, complete-spec, public-synthetic task slice. AIppocampus is
> designed for context loss, cross-thread recovery, post-compaction source
> reopening, and long-horizon continuity; this experiment deliberately includes
> a condition where rebuilding fresh context is expected to be cheaper. The
> result confirms a scope boundary: memory overhead is not justified when the
> task already has a complete fresh spec. It should not be read as evidence that
> source-backed recall has no value in the scenarios AIppocampus is built for.

Keep the historical metric id discoverable:
`continuous_memory.preregistered_repeat_profile_2026_06_08`. When citing the
scope interpretation, prefer the alias
`boundary_confirmed.short_task_complete_spec_synthetic_2026_06_08` and the
decision phrase `no demonstrated net advantage over modeled fresh-context spec
loop`.

Adjacent evidence prevents this boundary row from becoming the whole project
verdict:

#### `boundary_confirmed.short_task_complete_spec_synthetic_2026_06_08`

- **What it shows:** Fresh context wins for short complete-spec tasks under the current cost ledger.
- **Boundary:** Expected-null boundary; memory overhead is not justified in this condition.

#### `continuous_memory.context_loss_public_continuity_2026_06_10`

- **What it shows:** The #1153 readout adds a stable missing-context diagnostic slice:
  `github_1153_context_loss_public_continuity_v1`; `contract_gate_ok=true`,
  `quality_gate_ok=false`; selected deterministic public-safe cases keep
  `fresh_missing_context`, `summary_only_host_native`, `aippocampus_route_packet`,
  `sham_unrelated_memory`, `stale_wrong_memory`, `oracle_full_context`, and the old
  complete-spec boundary separate.
- **Boundary:** Contract slice only. It does not supersede
  `continuous_memory.preregistered_repeat_profile_2026_06_08`, claim public-quality
  continuous-memory advantage, or prove LoCoMo / private / live continuity quality.

#### `recall_navigation.progressive_route_follow_through`

- **What it shows:** Progressive recall routes can become actionable and reopen source in deterministic fixtures.
- **Boundary:** Not broad live foreground lift.

#### `recall_navigation.macro_prior_fixture_2026_06_12`

- **What it shows:** The opt-in agent recall path can consume scoped project macro state from a project-local default
  file, and the promotion harness shows one public-safe macro case where the prior changes
  active-layer route ordering, widens fanout, emits momentum recheck diagnostics, and reduces
  manual-search fallback with zero red-line counts.
- **Boundary:** Fixture/default-path contract only; not macro default-readiness, live foreground lift,
  private-history quality, or source evidence from macro state.

#### `macro.transform_orbit_diagnostic_2026_06_12`

- **What it shows:** Deterministic macro diagnostics distinguish C/R reversible transform orbits from line-flip
  adjacency and non-invertible nuclear projection basins, while keeping every packet
  navigation-only and source-reopen-bound.
- **Boundary:** Structural diagnostic only; not Dream quality, route merging, evidence support, foreground
  prose, default ranking, private-history behavior, or Yi interpretation quality.

#### `macro.timing_recheck_experiment_2026_06_12`

- **What it shows:** Public-safe timing experiment maps source-backed deltas onto active line axes and source-epoch
  cadence thresholds; it emits recheck diagnostics without mutating currentness, replacing
  temporal cues, using calendar cycles, or changing default ranking.
- **Boundary:** Fixture/research candidate only; not live recall adoption, quality lift, cost/token savings,
  private-history evidence, literal calendar timing, or fact/currentness support.

#### `fresh_thread.public_validation_2026_06_10`

- **What it shows:** The #281 public validation readout records 6 positive public flows, 5 negative controls,
  first-turn scent precision 1.0, progressive activation gain 1.0, source reopen before specific
  claims 1.0, irrelevant-memory drag 0.0, over-personalization count 0, and manual-query
  invention count 0.
- **Boundary:** Public fixture closeout only; not live fresh-thread quality, private-history quality, universal
  fresh-thread recall, foreground-hook-only sufficiency, or innate model memory.

#### `live_semantic.route_actionability_2026_06_07`

- **What it shows:** Live semantic route hits can become reopenable or source-required routes on a public checked-in corpus.
- **Boundary:** Not private-registry vague recall quality.

#### `track_b.private_semantic_sidecar_required`

- **What it shows:** Private real-history sidecar retrieved the expected source in 100/100 selected top-5 cases after the #963 dynamic-source ranking repair.
- **Boundary:** Maintainer-only private slice, not public benchmark score.

#### `episode_arc.private_history_adjudication_2026_06_08`

- **What it shows:** Rejected-route arcs exist at scale in private aggregate history.
- **Boundary:** Diagnostic aggregate, not live behavior lift.

#### `episode_arc.public_gappy_chain_calibration_2026_06_10`

- **What it shows:** Selected public fixtures distinguish complete, gappy, wrong-order, single-point, and
  temporary-concern arcs, with gappy chains projected to ask/refresh only.
- **Boundary:** Public deterministic fixture, not broad live or private-history quality.

#### `cognitive_load.public_behavior_trace_feedback_2026_06_10`

- **What it shows:** Selected public fixtures separate useful caution, irrelevant load drag / false positives, and
  over-personalization-risk feedback; the 2026-06-14 default-path replay then narrows current
  adoption to diagnostic-only.
- **Boundary:** Public deterministic fixtures, not live host-timing or default foreground policy quality.

#### `journey.public_time_sliced_replay_2026_06_10`

- **What it shows:** Selected public replayable cohort builds four time-sliced Journey candidates, excludes four
  future rows, surfaces one active relevant-prompt hint, suppresses resolved/stale/wrong-route
  relevant prompts, and suppresses 12 source-visible / unrelated / high-risk controls without
  serializing raw rows, source refs, or route handles.
- **Boundary:** Public deterministic fixture, not live/private Journey quality or default foreground usefulness.

#### `dream.shadow_route_topology_scout_2026_06_12`

- **What it shows:** Public-safe Dream topology scout now emits source/residue-gated shadow-route candidates and
  transform-orbit deepen candidates only when the shadow gate is already satisfied; generic
  shared vocabulary and pure orbit membership remain no-candidate/explain-only.
- **Boundary:** Deterministic scout fixture only; not live Dream quality, private-history usefulness, route
  merge, hidden user intent, foreground usefulness, or source support from transform structure.

#### `thread_story.public_shadow_closeout_2026_06_10`

- **What it shows:** Public structured-text #313 closeout report covers source-backed thread-story packet boundaries,
  packet-only factual-answer blocking, source-reopened answer comparison, and leakage /
  contradiction / persona / interference / unrelated-noise controls.
- **Boundary:** Public deterministic closeout fixture, not private-history story quality, live model behavior,
  default recall lift, or source truth from packet routes.

#### `attention_router.contract_fixture_2026_06_10`

- **What it shows:** Public-safe contract fixture proves hard masks block high-relevance routes, route packets are
  handles not facts, source-backed packets stay `reopenable_route` before source reopen, bounded
  summaries remain navigation-only routes, bounded evidence requires source-open/bounded scope,
  and masked source resurrection count is 0.
- **Boundary:** Public deterministic contract fixture, not broad router quality, private-history behavior, model
  training, summary-as-evidence, or default adoption.

#### `attention_router.route_token_fixture_2026_06_10`

- **What it shows:** Public-safe route-token fixture projects a long event into a tight source-span token, preserves
  reopen handles through event and episode/question tokens, carries
  salience/currentness/privacy/conflict slots, and keeps grouped episode/question tokens
  navigation-only.
- **Boundary:** Public deterministic token-projection fixture, not hot-router scoring quality, private-history
  token quality, source truth without reopen, or default adoption.

#### `attention_router.hot_router_fixture_2026_06_10`

- **What it shows:** Public-safe deterministic V0 router fixture applies hard masks before scoring, emits audited
  head votes, uses `calibrated_rule_grid_v1` as the current route-token score policy, raises
  thresholds for stale/conflict risk, routes positive and stale/conflict tokens as reopenable
  routes, and leaves weak tokens direction-only.
- **Boundary:** Public deterministic router fixture, not learned attention, production calibration,
  private-history quality, live foreground usefulness, or default foreground-hook adoption.

#### `attention_router.action_head_fixture_2026_06_10`

- **What it shows:** Public-safe action-query fixture shows pending path/issue/test cues can lift a route when
  prompt-only terms are weak, while privacy masks and anti-nag suppression still block or
  downshift action-matched routes.
- **Boundary:** Public deterministic action-head fixture, not live hook behavior, private tool-argument quality,
  E2E50 lift, or default foreground action routing.

#### `attention_router.evidence_packaging_fixture_2026_06_10`

- **What it shows:** Public-safe evidence-packaging fixture preserves first-stage source-window retrieval while
  tightening context-visible candidates into source-span route packets;
  source-open/current/unconflicted spans can become bounded evidence, and
  wrong-source/stale/conflicted controls stay rejected or reopenable.
- **Boundary:** Public deterministic packaging fixture, not LongMemEval QA score, exact-line quality being
  solved, reranker output as source truth, private-history packaging quality, or default
  foreground adoption.

#### `attention_router.navigation_quality_public_cohort_2026_06_13`

- **What it shows:** Public-safe benchmark keeps the 12-case contract fixture green and adds a 9-family
  public/holdout cohort with explicit gate names: `contract_safety_gate_ok`,
  `router_design_gate_ok`, `public_quality_gate_ok`, and `default_adoption_gate_ok`. Legacy
  `quality_gate_ok` is a public-quality alias, not a V0 design verdict.
- **Boundary:** Public/holdout navigation-quality gate for the narrow explicit agent-pull path; not live host
  behavior, answer-generation quality, private-history behavior, broad live/default
  route-producer quality, broad default-session usefulness, or default foreground-hook adoption.

#### `attention_router.score_fusion_calibration_2026_06_11`

- **What it shows:** Public-safe #1112/#1230 calibration/adoption report exports 12 sanitized attention feature rows;
  legacy deterministic weights still show the old false-negative/anti-nag gap, while
  `runtime_default_policy=calibrated_rule_grid_v1` matches the calibrated arm at
  precision/recall 1.0 with all red lines 0.
- **Boundary:** Public deterministic hot-router policy adoption, not default foreground-hook adoption,
  private-history training quality, answer-generation quality, source truth from scores, or
  production calibration.

#### `attention_router.agent_recall_opt_in_sorting_2026_06_12`

- **What it shows:** `aippocampus agent recall --attention-router` can project existing `recall_context` routes into
  attention-route tokens, reorder only already emitted reopenable routes, keep all original
  routes as fallback candidates, and report public-safe `attention_router_navigation` metrics
  without foregrounding source refs or head votes. The same projection now reports no-help
  diagnostics such as applied-but-no-help, query/route overlap, bridge-reason,
  specificity-floor, and `why_this_may_matter` specificity signals.
- **Boundary:** Public-safe opt-in agent route-sorting contract and usefulness diagnostics, not default
  foreground adoption, broad live route-producer quality, private-history router quality, answer
  generation, source truth from scores, or broad live/default successor quality.

#### `attention_router.agent_recall_auto_policy_2026_06_13`

- **What it shows:** `aippocampus agent recall --attention-router-mode auto` checks the shared recall-navigation
  promotion harness before enabling router sorting. Neutral no-op cases are now ROI signals
  instead of hard blockers, true no-help/feature-hurt/red-line controls remain visible, and the
  public/holdout cohort can enable sorting for the explicit agent-recall surface.
- **Boundary:** Explicit-pull auto policy only; not default hooks, every-turn recall, live-host usefulness lift,
  private-history quality, answer generation, evidence support from attention scores, or broad
  live/default successor quality.

#### `recall.default_hook_usefulness_2026_06_20`

- **What it shows:** Public-safe #1439/#1449 four-arm benchmark compares no-packet baseline, explicit recall,
  default-hook foreground candidate, and `default_hook_tiny_agent_recall_affordance` under the
  same packet/source-reopen budget. Explicit recall and the tiny affordance both reach helpful
  next-action rate 0.636364 and manual-search reduction 11; the broad default-hook foreground
  candidate remains rejected with helpful rate 0.272727, wrong-route drag rate 0.363636, and
  irrelevant-memory drag rate 0.272727. The tiny `not evidence` affordance now has a
  host-faithful replay gate with 7 emitted/followed `agent_recall` calls, 7 recall-after-hint
  successes, 0 broad-manual-search-before-recall, and 0 wrong-route, irrelevant-memory,
  source-truth, raw-handle, or provenance-dump counts.
- **Boundary:** Public synthetic diagnostic benchmark only; not live default-hook or tiny-affordance quality,
  private-history question/theme usefulness, default foreground adoption readiness, source truth
  from theme/load/router rows, or source claims from the tiny affordance without
  recall/deepen/source reopen.

#### `map_rot.lifecycle_debt_2026_06_11`

- **What it shows:** Public-safe lifecycle fixture covers 9 stale, challenged, quarantined, superseded,
  missing-middle, deleted/no-recall, dead-lettered, repeated-wrong, and current-route cases;
  hard red-line counters are 0, `benchmark_maturity_level=contract_smoke`,
  `contract_gate_ok=true`, and `quality_gate_ok=false`. The same runner now emits a no-write
  maintenance plan: 8 hot-surface removals, 2 review-queue rows, 2 source-refresh reactivation
  rows, and 1 dead-letter compaction row.
- **Boundary:** Public deterministic lifecycle-debt contract gate and maintenance-action plan, not
  representative map-rot distribution, automatic cleanup proof, completed forgetting, conflict
  auto-resolution, private-history map-rot quality, or live current-route quality.

#### `agent_continuity.loop_gate_2026_06_11`

- **What it shows:** Public-safe integration gate composes semantic warm routes, hot-router packets, agent-native
  foreground/deepen/explain, AIppo activation, source-reopen budget, foreground budget, packet
  triage, blocked/stale/conflict, and anti-nag cases; 8/8 cases pass, all red lines are 0,
  `packet_triage_distinctiveness=1.0`, `blind_deepen_required_count=0`,
  `benchmark_maturity_level=contract_smoke`, `contract_gate_ok=true`, and
  `quality_gate_ok=false`.
- **Boundary:** Supports deterministic composition and route-selection usefulness on checked-in fixtures;
  material limits are no private-history or live-host lift, no answer-generation or
  external-model quality, and no default foreground adoption claim.

#### `agent_continuity.foreground_action_card_2026_06_15`

- **What it shows:** Public-safe #1620 foreground field-budget contract: default agent recall / MCP payloads include
  a bounded `foreground_action_card` before audit details, with decisions for `use_route_first`,
  `continue_normally`, `deepen_before_claim`, and `ignore_or_blocked`; callable local handles
  are present only in local JSON and redacted from public projection; audit-only fields stay out
  of the card while full diagnostics remain available.
- **Boundary:** Deterministic fixture and replay proxy only; not live behavior lift, default-hook adoption,
  source truth from the card, or proof that every agent will avoid broad manual search.

#### `telepathy.opt_in_handoff_workflow_2026_06_12`

- **What it shows:** Opt-in local Telepathy handoff workflow stores append-only card lifecycle events, supports CLI
  create/list/deepen/release/diagnose, exposes MCP read-only list/deepen tools, keeps
  candidate-only cards navigation-only, and sanitizes source refs to selector fields or
  fingerprints.
- **Boundary:** Supports a local handoff-card workflow over the existing packet/topology contract; material
  limits are no distributed lock correctness, no MCP write surface, no automatic work
  assignment, no live multi-agent usefulness claim, and no source truth without reopen.

#### `sparse_provenance.codebook_v0_2026_06_12`

- **What it shows:** Public-safe #1190 V0 fixture builds 8 clean-source-like entries into 6 content-addressed chunks
  (`compression_ratio=0.75`), reduces route-chain lookup candidates from 8 to 5, suppresses 2
  stale/quarantined matches, emits 0 foreground reconstructed text items, and reports all
  reconstruction/privacy red lines at 0 with topology preservation `status=ok`.
- **Boundary:** Supports deterministic sparse provenance build/lookup/rehydration proof on a checked-in fixture;
  material limits are no natural-dialogue template compression, no zstd value claim, no neural
  MoE routing, no private-history behavior, no GB/TB-scale infrastructure readiness, and no
  source truth from codebook routes.

#### `avatar.bounded_resonance_proxy_pilot_2026_06_12`

- **What it shows:** Public-safe #1319 exploratory proxy fixture runs 12 cases across closeout, repeated-debug-route,
  and structural-break families through arms A-E; the deterministic proxy marks bounded
  resonance as best (`average_helpfulness_score=5.666667`), standalone archetype alias drift as
  visible (`off_topic_archetype_expansion_count=12`), and bounded-resonance candidate red lines
  as 0.
- **Boundary:** Exploratory deterministic proxy only, not live model behavior, production agent lift, default
  foreground avatar readiness, private-history quality, archetype authority, or source truth
  from posture/resonance.


<a id="cannot-claim-owner-and-retirement-ledger"></a>

## Claim-Boundary Owner And Retirement Ledger

This table keeps testable material limits from becoming permanent background
caveats. Reports may still use the legacy `cannot_claim` field for compatibility,
but reader-facing prose should lead with what the result measured and supports.
Use the metadata shape `category`, `owner_issue`, `retirement_condition`, and
`next_review` when adding or reviewing rows.

`actionable` entries need an owner issue and a retirement condition.
`durable_non_goal`, `research_blocked`, and `external_dependency` entries can
remain without a direct implementation owner when a test would not honestly
retire the caveat. Do not retire a broader caveat from a narrow smoke; add or
update a dated claim row first.

| Caveat | Category | Owner issue | Retirement condition | Next review |
| --- | --- | --- | --- | --- |
| Continuous-memory superiority after the preregistered repeat negative result | `actionable` | [#960](https://github.com/Sapientropic/AIppocampus/issues/960) closed remediation owner; [#378](https://github.com/Sapientropic/AIppocampus/issues/378) / future repeated-evidence slice | #960 retired the first remediation/rerun blocker by implementing source-miss anchor recovery while preserving the expected-null result. This broader caveat retires only when a later dated repeated-evidence row supersedes `continuous_memory.preregistered_repeat_profile_2026_06_08` with a passing preregistered lower-bound decision and explicit cost/harm boundary. | Before any #378 or continuous-memory public-readiness upgrade. |
| Track B private source-evidence retrieval top-k misses | `actionable` | [#963](https://github.com/Sapientropic/AIppocampus/issues/963) | Retired for the current selected private slice by the 2026-06-09 `track_b.private_semantic_sidecar_required` row: the top-k misses were taxonomized as candidate-generated/rank-pruned, repaired through a public analogue, and rerun at 100/100 without broad semantic-completeness claims. | Reopen only if a later selected Track B row reports top-k misses or before widening Track B beyond the current selected private slice. |
| E2E50 public behavior-pack path | `actionable` | [#994](https://github.com/Sapientropic/AIppocampus/issues/994) / [#1154](https://github.com/Sapientropic/AIppocampus/issues/1154) / [#279](https://github.com/Sapientropic/AIppocampus/issues/279) | Retired for the immediate public/shareable behavior-pack path by the 2026-06-12 `e2e50.public_safe_behavior_pack_contract_2026_06_12` row: a 50-case public-safe synthetic behavior pack is checked in with no-remember negatives, summary-overhang traps, scope-limited constraints, source-family coverage, and a report boundary. | Reopen before claiming representative E2E50 quality, private-history behavior lift, or live-host behavior quality. |
| E2E50 private/local annotated seed pack | `actionable` | [#1086](https://github.com/Sapientropic/AIppocampus/issues/1086) | The 2026-06-10 follow-up retires the ambiguous private/local candidate-count blocker by showing 23/20 wide-scan candidates, but preserves the private annotation blocker: only 7 retained/control cases against the 20-case private target. This is optional dogfood evidence after #1154, not the main public E2E50 gate. Retire this caveat only before claiming private-history E2E50 quality. | Before claiming private-history behavior lift, completed private 20-case E2E50 quality, or representative 50-case quality. |
| Fresh-thread public fixture validation | `actionable` | [#281](https://github.com/Sapientropic/AIppocampus/issues/281) | Retired for the public, inspectable fixture closeout path by the 2026-06-10 `fresh_thread.public_validation_2026_06_10` row: the checked-in runner reports first-turn scent precision, progressive activation gain, source reopen before specific claims, negative-control drag suppression, over-personalization suppression, and manual-query invention suppression. Future live/private/external-dataset work needs a new scoped owner. | Reopen only before claiming live fresh-thread quality, private real-history quality, universal fresh-thread quality, foreground-hook-only sufficiency, or innate model memory. |
| Claude Code hook real-host firing and unsupported events | `actionable` | [#1020](https://github.com/Sapientropic/AIppocampus/issues/1020) | A local or public-safe real-host event log shows the scoped handlers firing, and later slices add payload-safe `PostToolUse`/`PostToolBatch` or compaction support before those events are claimed. | Before widening the scoped #1020 synthetic hook contract beyond `UserPromptSubmit` and `Stop`. |
| Persistent Claude Code MCP config health | `actionable` | [#1021](https://github.com/Sapientropic/AIppocampus/issues/1021) / [#1235](https://github.com/Sapientropic/AIppocampus/issues/1235) | Retired for the current local operator host by #1235: the stale path was repaired to the portable `aippocampus mcp` command, and the no-write persistent diagnostic reported `persistent_config_healthy` with the nested MCP probe `healthy`. Reopen only if a later diagnostic reports a broken persistent config or before claiming broad Claude host portability. | Before any cross-host, package-distribution, or real-hook-firing Claude Code claim. |
| CJK recall quality beyond the first public fixture | `actionable` | [#1022](https://github.com/Sapientropic/AIppocampus/issues/1022) | The 2026-06-09 #1054 public-safe CJK rerun retires the narrow default-path compact-CJK gap: production hybrid now reports 7/7 positive top-5 hits with 0 negative false positives after lightweight CJK query chunks entered the default local hybrid path. Broader Chinese recall quality still needs richer public and private-safe evidence. | Before widening Chinese recall claims beyond the expanded fixture. |
| Cognitive-load false positives and usefulness | `durable_non_goal` | [#575](https://github.com/Sapientropic/AIppocampus/issues/575) closed as diagnostic-only | The 2026-06-10 public behavior-trace feedback fixture retires the reviewed-feedback gap, and the 2026-06-14 default-path replay records one useful hint plus one memory-drag regression. The owner is narrowed to diagnostic-only behavior; any future default foreground weighting needs a new issue with stronger live/default evidence. | Before enabling any default host-timing or foreground weighting claim. |
| Journey default hint timing and public reproducibility | `actionable` | [#310](https://github.com/Sapientropic/AIppocampus/issues/310) | The 2026-06-10 public time-sliced replay cohort retires the selected public-reproducibility gap for a replayable hint/no-hint, stale/resolved/wrong-route suppression, false-foreground, and no-future-leak contract. The broader caveat retires only when live/private reviewed host-timing or user-visible quality evidence shows Journey hints help without source-truth, persona, or future-leak overclaim. | Before enabling default foreground Journey hints or claiming private/live Journey quality. |
| Episode/Arc gappy-chain overclaim risk | `durable_non_goal` | [#663](https://github.com/Sapientropic/AIppocampus/issues/663) closed as bounded owner track; future live/default issue if needed | The 2026-06-10 public fixture retires the selected builder/reopen-projection overclaim gap for complete, gappy, wrong-order, single-point, and temporary-concern arcs, and the 2026-06-14 route-producer fixture adds richer adapters and route guidance. The remaining caveat is a durable boundary: do not treat Episode/Arc packets as current validity or source truth without reopen. | Before treating Episode/Arc packets as more than navigation/read-model context. |
| AMemGym official live-provider score | `external_dependency` | [#1232](https://github.com/Sapientropic/AIppocampus/issues/1232) closed as provider-route-blocked after post-top-up diagnosis | The 2026-06-11 #1232 resume attempt preserves the caveat: partial live-provider outputs remain incomplete, provider cost is not extractable from official outputs, and the pinned OpenRouter Native condition is blocked because the required OpenAI-family routes fail provider-policy preflight even on a harmless prompt. Retire this only when a later dated AMemGym note records a complete fixed-arm run under a declared provider/model condition, sanitized cost/latency or an explicit unavailable-provider-field reason, and parity-arm decision without promoting protocol smoke, bounded subsets, checkpoint output, provider-budget preflight, or route-preflight output into live score claims. | When a complete bounded/resumable fixed-arm run is produced and reviewed under a declared provider/model condition. |
| Private text disclosure in public evidence | `durable_non_goal` | - | Not retired by benchmark evidence; public reports stay aggregate, sanitized, or source-reopenable without raw private text. | Recheck only if the public/private evidence policy changes. |
| Hosted or cloud continuity from a single local-host smoke | `external_dependency` | - | Requires a scoped cloud/sync/provider evidence issue before it becomes actionable; local host proof cannot retire hosted or cross-device caveats. | Before any hosted/cloud product claim. |
| Broad private-history quality from selected local diagnostics | `research_blocked` | - | Requires a separately scoped private-history quality protocol with privacy-preserving review and explicit cohort limits; selected aggregates do not retire it. | Before any broad real-history quality claim. |

## Current Claim Snapshot

Each block below is one `metric_id` entry with `current_value`, `run_date`,
`source_report`, `claim_level`, `cohort`, `supersedes / superseded_by`, and
`cannot_claim` fields. Keep this block format line-addressable; do not turn it
back into giant Markdown table rows.

### `registry.local_real_history_aggregate`

- **current_value:** 964 clean-source/index/graph-backed threads; 110 scope-labeled threads; 88 non-technical
  life-wide threads; 244 semantic sidecar rows across 46 threads; all eight canonical labels
  observed.
- **run_date:** 2026-05-30
- **source_report:** [`public-readiness-verification.md`, #55 Stage 2
  evidence](readiness/public-readiness-verification.md#2026-05-30-issues-5556-evidence-closeout)
- **claim_level:** `first_pass_real_history_slice`
- **cohort:** Local real-history registry aggregate; aggregate-only smoke output.
- **supersedes / superseded_by:** Supersedes the older 949-thread aggregate paragraph for public currentness.
- **cannot_claim:** Full-history refresh, semantic completeness, label correctness without clean-source review, or private-text disclosure.

### `semantic_sidecar.aggregate_materialized_rows`

- **current_value:** 244 semantic sidecar rows across 46 threads, with all eight canonical labels observed.
- **run_date:** 2026-05-30
- **source_report:** [`public-readiness-verification.md`, #55 Stage 2
  evidence](readiness/public-readiness-verification.md#2026-05-30-issues-5556-evidence-closeout)
- **claim_level:** `first_pass_real_history_slice`
- **cohort:** Local real-history dynamic semantic sidecar observation.
- **supersedes / superseded_by:** Supersedes the older 2-thread / 5-row strict-survival number for aggregate materialized coverage only.
- **cannot_claim:** Global semantic correctness, human review, complete life-wide labeling, or relaxed materializer gates.

### `semantic_sidecar.strict_survival_snapshot`

- **current_value:** Historical strict-survival slice: 5 rows across 2 real clean-source threads and 5 semantic latest timeline turns.
- **run_date:** 2026-05-29
- **source_report:** [`public-readiness-verification.md`, earlier Stage 2
  closeout](readiness/public-readiness-verification.md) and
  [`memory-decision-benchmark-plan.md`](benchmarks/design/memory-decision-benchmark-plan.md)
- **claim_level:** `historical_strict_survival_snapshot`
- **cohort:** Strict per-label evidence gate after source-review tightening.
- **supersedes / superseded_by:** Superseded by `semantic_sidecar.aggregate_materialized_rows` for aggregate coverage; retained as a stricter survival baseline.
- **cannot_claim:** Latest aggregate coverage, global Stage 2 correctness, or proof that suppressed labels are safe to restore.

### `semantic_sidecar.source_review_green_gate`

- **current_value:** 24 selected semantic sidecar label cases reviewed; 24/24 passed; `pass_rate=1.0`; no live model failures.
- **run_date:** 2026-05-30
- **source_report:** [`public-readiness-verification.md`, #55 Stage 2
  evidence](readiness/public-readiness-verification.md#2026-05-30-issues-5556-evidence-closeout)
- **claim_level:** `selected_source_review_green_gate`
- **cohort:** Selected strict semantic sidecar labels reviewed through the live DeepSeek-compatible source-review smoke.
- **supersedes / superseded_by:** Supersedes the older 5-case strict-review pass as the selected green gate.
- **cannot_claim:** Human review, broad correctness, or full-history semantic quality.

### `semantic_sidecar.source_review_diagnostic`

- **current_value:** 96 selected cases reviewed; 89 passed; `pass_rate=0.9271`; `failed_label_categories=[]`;
  `failure_count=0`; `failure_taxonomy.by_class={}`;
  `label_failure_taxonomy.by_class={"unsupported_label_evidence":7}`; `preference` passed 6/9
  with `pass_rate=0.6667`.
- **run_date:** 2026-06-09
- **source_report:** [`public-readiness-verification.md`, 2026-06-09 #1053
  rerun](readiness/public-readiness-verification.md#2026-06-09-issue-1053-preference-source-review-floor-and-taxonomy-slice)
- **claim_level:** `broader_selected_source_review_diagnostic`
- **cohort:** Broader selected source-review smoke with live provider behavior.
- **supersedes / superseded_by:** Supersedes the same-day #993 96-case diagnostic where `preference` was below the per-label
  floor; the 24-case row remains the named green gate.
- **cannot_claim:** Human review, full-history semantic correctness, release gate, selected source-review green
  gate, provider-independent quality, or private-text disclosure.

### `question_tracking.six_axis_threshold_fixture_2026_06_09`

- **current_value:** Selected public-safe fixture calibration: 6 scenarios passed; fixed low similarity threshold
  (`0.52`) had false merge 1/3 = 0.333333; static strong threshold (`0.80`) had false split 1/2
  = 0.5; dynamic six-axis threshold had false merge 0/3 and false split 0/2; borderline-auto
  correct count 1 and wrong count 0; source-ref coverage 12/12 = 1.0.
- **run_date:** 2026-06-09
- **source_report:** `benchmarks/aippocampus/benchmark_question_tracking_calibration.py --json`
- **claim_level:** `selected_fixture_navigation_policy_calibration`
- **cohort:** Public-safe selected question-candidate fixtures over recurring context, low-information,
  orientation shift, over-merge conflict, over-split same-frontier, and borderline-confirmation
  families; no private text and no live model.
- **supersedes / superseded_by:** Extends the earlier static-vs-adaptive non-regression row with #1059 false-merge / false-split / reason-code audit metrics.
- **cannot_claim:** Source truth from dynamic thresholds, real-user calibration, private-history threshold quality,
  live external model confirmation, user-visible recall improvement, or broad question-tracking
  quality.

### `fresh_thread.public_validation_2026_06_10`

- **current_value:** Public-safe #281 fresh-thread validation: 6 positive public flows, 5 negative controls,
  first-turn positive route success 6, first-turn false activations 0,
  `first_turn_scent_precision=1.0`, `progressive_activation_gain=1.0`,
  `source_reopen_before_specific_claim_rate=1.0`, `irrelevant_memory_drag_rate=0.0`,
  `overpersonalization_count=0`, `manual_query_invention_count=0`,
  `manual_query_expected_count=0`, `ready_lock_use_count=5`, `unsupported_evidence_count=0`, and
  `negative_control_active_recall_count=0`.
- **run_date:** 2026-06-10
- **source_report:** [`fresh-thread-expanded-coverage-2026-06-03.md`, GitHub #281 public validation
  readout](benchmarks/reports/fresh-thread/fresh-thread-expanded-coverage-2026-06-03.md#github-281-public-validation-readout)
  and `python benchmarks\aippocampus\benchmark_fresh_thread_recall_demo.py --json`
- **claim_level:** `public_safe_fixture_validation`
- **cohort:** Checked-in public synthetic fresh-thread flows over positive, negative, multi-turn, correction,
  threshold, active-recall, source-reopen, and manual-query-invention controls; no private text,
  live model, raw source snippets, or local paths.
- **supersedes / superseded_by:** Retires #281's public-fixture validation blocker while preserving live/private/external-dataset
  follow-ups as new scoped issues.
- **cannot_claim:** Live fresh-thread quality, private real-history fresh-thread quality, universal fresh-thread
  recall quality, foreground-hook-only sufficiency, base-model innate memory, live
  semantic-model quality, or source truth without reopen.

### `question_tracking.public_shadow_question_aware_reopen_2026_06_10`

- **current_value:** Public/source-replayable #248 shadow fixture: 4 public cases, 2 negative controls, source-ref
  fidelity 1.0, preregistered selected public baseline/cohort, question-aware over
  question-blind term delta 0.75, answer-usefulness delta 1.0, manual-query-reduction delta 1.5,
  question-aware wrong-hint rate 0.0, no-question retrieval recall 0.5 vs question-aware
  retrieval recall 1.0, stale-question carryover 0, missed resurfacing without question tracking
  2, wrong-route drag 0, noise false positives 0, materialization-review status
  `public_shadow_review_evidence_ready`, public-safe local calibration status
  `public_safe_local_calibration_ready`, and dynamic six-axis false merge 0/3 and false split
  0/2.
- **run_date:** 2026-06-10
- **source_report:** [`question-aware-public-shadow-2026-06-10.md`](question/question-aware-public-shadow-2026-06-10.md)
  and `python benchmarks\aippocampus\benchmark_question_aware_real_history.py --public-shadow
  --json`
- **claim_level:** `public_replayable_shadow_fixture`
- **cohort:** Checked-in public-safe VCS-style and agent-trajectory question-continuity cases plus
  multilingual/noise and code negative controls; no private text, live model, or default
  prefilter.
- **supersedes / superseded_by:** Retires #1367, #1368, and #1369 as bounded public-safe #248 slices and makes #248 closeable as a
  public-safe owner closeout while preserving private/live/default boundaries.
- **cannot_claim:** Private real-history answer quality, live user-visible recall improvement, broad
  question-tracking quality, theme-resonance calibration, default prefilter adoption, source
  truth from question/theme rows, or broad no-question retrieval quality beyond the checked-in
  fixture.

### `usefulness.natural_handoff_synthetic_validation_2026_06_14`

- **current_value:** Public/synthetic #1384 validation: 6 cases, wins 2, no-help 1, regressions 3; natural handoff
  success rate 0.3333, default-session continuity success rate 0.5, implicit-context activation
  success rate 1.0. Regressions cover safe-but-noisy protocol dumps, safe route demoted to
  scent, and wrong-route/manual-search drag.
- **run_date:** 2026-06-14
- **source_report:** [`natural-handoff-usefulness-2026-06-14.md`](benchmarks/reports/coordination/natural-handoff-usefulness-2026-06-14.md)
  and `python benchmarks\aippocampus\benchmark_natural_handoff_usefulness.py --json`
- **claim_level:** `bounded_synthetic_default_session_validation`
- **cohort:** Checked-in public-safe synthetic natural-handoff/default-session cases using the canonical
  `continuity_usefulness` gate; no private text, provider calls, local paths, or live hook
  behavior.
- **supersedes / superseded_by:** Closes #1384 and makes #1185 closeable as a bounded usefulness-owner closeout, while preserving
  future broad default-path/live-host usefulness as new scoped work.
- **cannot_claim:** Broad default-session product lift, private-history user-visible lift, live host hook activation
  rate, or a rule that every deictic prompt should trigger recall without clarification.

### `subconscious.event_salience_intake_fixture_2026_06_09`

- **current_value:** Deterministic intake fixture: 7 clean-source-like turns classified into correction,
  frontier/blocker, preference/style, supersession/currentness, failed command/test, scope
  boundary, and low-information noise; 6/7 selected for candidate extraction, 1/7 skipped as
  low-information noise, missed-high-signal count 0, source-ref coverage 7/7 = 1.0. Opt-in job
  integration filters model payloads and writes a rebuildable salience sidecar; public
  projection omits raw source text and refs.
- **run_date:** 2026-06-09
- **source_report:** `python -m unittest tests.aippocampus.test_subconscious_event_salience_gate -v`
- **claim_level:** `deterministic_intake_contract`
- **cohort:** Public-safe synthetic clean-source-like turn fixtures and mocked job-runner integration; no private text and no live model.
- **supersedes / superseded_by:** First #1058 event-salience intake gate fixture row.
- **cannot_claim:** Memory truth from salience tags, foreground-hook model work, deletion of low-salience source,
  real-user salience quality, review-priority quality, private-history candidate-reduction
  quality, or user-visible recall improvement.

### `retrieval_reconsolidation.review_window_fixture_2026_06_10`

- **current_value:** Deterministic retrieval lifecycle fixtures project source-backed `superseded`, `refuted`,
  `conflicted`, and `still_current` outcomes into staging review candidates; no-write reports
  count activated, used, ignored, conflicted, superseded, refuted, still-current, and
  source-missing-blocked rows; source-key-only rows do not produce review candidates.
- **run_date:** 2026-06-10
- **source_report:** `python -m pytest tests\aippocampus\test_retrieval_lifecycle.py -q`
- **claim_level:** `deterministic_review_window_contract`
- **cohort:** Public-safe synthetic retrieval lifecycle rows over prompt/active/MCP/source-reopen style
  events; no private text, live model, or default hook write.
- **supersedes / superseded_by:** Extends #1019 retrieval lifecycle diagnostics with #1081 retrieval-triggered reconsolidation review-window candidates.
- **cannot_claim:** Default foreground hook writes, automatic memory updates, clean-source mutation, raw-rollout
  mutation, live semantic adjudication quality, #1082 state-dependent preactivation quality,
  private-history behavior lift, or user-visible recall improvement.

### `warm_ambient.state_dependent_preactivation_2026_06_10`

- **current_value:** Public-safe deterministic #1082 fixture: 4 cases, 7 candidates; state-dependent arm keeps
  preactivation hit rate 1.0, lowers false preactivation rate from simple-baseline 0.4 to 0.0,
  keeps source-reopen success rate 1.0, improves foreground-noise suppression from 0.6 to 1.0,
  and reduces source-reopen attempt cost units from 4 to 2 without model calls. Stale,
  privacy-blocked, and conflicted candidates stay suppressed, and predicted handles use only
  `direction_only` or `reopenable_route`.
- **run_date:** 2026-06-10
- **source_report:** [`state-dependent-preactivation-2026-06-10.md`](benchmarks/reports/fresh-thread/state-dependent-preactivation-2026-06-10.md)
  and `python -m pytest tests\aippocampus\test_prewarm_planner.py
  tests\aippocampus\test_benchmark_state_dependent_preactivation.py -q`
- **claim_level:** `public_safe_deterministic_preactivation_fixture`
- **cohort:** Selected public synthetic warm ambient cases over phase context, frontier proximity, salience,
  cache state, active recall locks, stale/conflicted routes, and privacy suppression; no private
  text, no live model, no foreground hook write.
- **supersedes / superseded_by:** Closes the #1082 evaluation slice after #1081 supplied the retrieval-reconsolidation vocabulary;
  complements warm ambient recall and route-readiness diagnostics.
- **cannot_claim:** Live foreground preactivation rollout, source truth from predicted routes, live latency savings,
  ADHD productivity lift, broad proactive-agent behavior, private-history quality, or
  user-visible recall improvement.

### `e2e50.public_safe_behavior_pack_contract_2026_06_12`

- **current_value:** Public-safe synthetic E2E50 behavior pack: 50 annotated cases; `contract_gate_ok=true`;
  `quality_gate_ok=false`; 50/50 correct; `claim_level=public_safe_behavior_pack_contract`;
  covers binding constraint survival, rejected-route avoidance, transient-concern extinction,
  superseded currentness, scope-limited constraints, summary-overhang traps, benign no-remember
  negatives, and source reopen before risky action; `no_remember_negative_precision=1.0`;
  annotation status counts `gold_seed=23`, `calibration_seed=11`, `negative_control=3`,
  `rejected_candidate=4`, `duplicate_candidate=5`, `source_visible_candidate=4`; source-family
  counts `synthetic_public_safe=30`, `public_vcs=11`, `public_longitudinal=9`.
- **run_date:** 2026-06-12
- **source_report:** `python benchmarks/aippocampus/benchmark_e2e50_silent_constraint.py --json`
- **claim_level:** `public_safe_behavior_pack_contract`
- **cohort:** Public-safe synthetic behavior-pack contract; no private text, no live host, no semantic judge, no raw behavior trace in reports.
- **supersedes / superseded_by:** Supersedes the 2026-06-10 20-case public behavior-pack row for public case count and current
  coverage; keeps private retained-case scarcity as optional dogfood/private-quality evidence.
- **cannot_claim:** E2E50 behavior benchmark quality, private real-history behavior lift, representative E2E50
  sample quality, live host behavior lift, semantic-judge quality, or public-dialogue continuity
  proof.

### `e2e50.label_oracle_live_diagnostic_2026_06_13`

- **current_value:** Public-safe #1322 live-model E2E50 diagnostic: 50 public cases were run across a labeled
  baseline prompt and AIppocampus packet arm for 100 DeepSeek V4-Flash calls. The historical run
  recorded packet `correct_rate=1.0` and baseline `0.94`, but follow-up audit found the baseline
  prompt exposed `case_family`, family-specific scenario text, the action-code glossary, and an
  `AIppocampus packet` shell. Treat the high baseline and `assisted_correct_rate_lift=0.06` as
  label-oracle / runner-wiring output, not behavior-lift evidence. Temperature was not sent
  under provider/default thinking.
- **run_date:** 2026-06-13
- **source_report:** [`e2e50-live-behavior-pilot-2026-06-13.md`](../archive/research/e2e50/e2e50-live-behavior-pilot-2026-06-13.md),
  [`e2e50-live-behavior-pilot-2026-06-13.json`](../archive/research/e2e50/e2e50-live-behavior-pilot-2026-06-13.json),
  and `python -m unittest tests.aippocampus.test_benchmark_e2e50_behavior_live -v`
- **claim_level:** `public_safe_label_oracle_diagnostic`
- **cohort:** Public-safe checked-in E2E50 fixture only, sanitized model excerpts, aggregate usage/cost
  estimates, and no raw provider payloads, private history, local paths, credentials, live host
  state, or raw behavior trace rows.
- **supersedes / superseded_by:** Does not close #1322; it preserves the live runner/report path while marking that a blind public
  surface-task fixture is still required before baseline-vs-AIppocampus behavior validation.
- **cannot_claim:** Clean no-memory baseline quality, AIppocampus-assisted behavior lift, #1322 behavior-validation
  closeout, broad E2E50 benchmark quality, private-history behavior lift, live host behavior
  lift, default foreground packet adoption, provider-general behavior quality, or source truth
  from packet summaries.

### `e2e50.blind_surface_live_behavior_2026_06_13`

- **current_value:** Corrected public-safe #1322 live-model E2E50 behavior run: 50 public cases across blind baseline
  and AIppocampus packet arms for 100 DeepSeek V4-Flash calls. Baseline prompt hides
  `case_family`, expected behavior codes, source hashes, family-specific scenario labels,
  action-code glossary, and empty packet shell. Packet arm scores `correct_rate=1.0` and
  `useful_next_action_rate=1.0`; baseline scores `0.42` on both;
  `assisted_correct_rate_lift=0.58`; baseline has 10 manual-search choices, 21 source-reopen
  choices, and 29 safe-but-non-answer choices; packet arm has 0 manual-search and 0 safe
  non-answer choices; wrong actions, over-constrained actions, invalid actions, and
  private/sensitive model-output hits are 0; negative-control correct rate is 1.0 in both arms.
  Temperature is not sent under provider/default thinking.
- **run_date:** 2026-06-13
- **source_report:** [`e2e50-blind-surface-live-behavior-2026-06-13.md`](../research/reports/e2e50-blind-surface-live-behavior-2026-06-13.md),
  [`e2e50-blind-surface-live-behavior-2026-06-13.json`](../research/e2e50-blind-surface-live-behavior-2026-06-13.json),
  and `python -m unittest tests.aippocampus.test_benchmark_e2e50_behavior_live -v`
- **claim_level:** `public_safe_blind_surface_live_behavior_pilot`
- **cohort:** Public-safe checked-in E2E50 fixture rendered into blind surface tasks, sanitized model
  excerpts, aggregate usage/cost estimates, and no raw provider payloads, private history, local
  paths, credentials, live host state, source hashes in prompts, or raw behavior trace rows.
- **supersedes / superseded_by:** Closes the #1322 small public behavior-validation slice by scoring generated next-action choices
  under a blind baseline and packet-assisted arm while keeping deterministic contract,
  label-oracle diagnostic, and model-backed behavior evidence separate.
- **cannot_claim:** Broad E2E50 benchmark quality, private-history behavior lift, live host behavior lift, default
  foreground packet adoption, provider-general behavior quality, source truth from packet
  summaries, or representative product quality beyond this synthetic public surface.

### `e2e50.private_local_seed_annotation_blocker_2026_06_10`

- **current_value:** Private/local E2E50 follow-up: wide scan found 23 candidate seeds against a 20-candidate
  minimum; local annotation summary reviewed 17 candidates and retained 7 control/seed cases,
  including 4 gold, 2 calibration, and 1 negative control; retained/control shortfall is 13
  against the 20-case private target.
- **run_date:** 2026-06-10
- **source_report:** [`e2e50-private-local-seed-followup-2026-06-10.md`](benchmarks/reports/e2e50/e2e50-private-local-seed-followup-2026-06-10.md)
  and `python tools/aippocampus/smoke/smoke_e2e50_seed_candidates.py --annotation
  <ignored-local-manual-annotation-json> --json`
- **claim_level:** `private_local_sanitized_blocker_report`
- **cohort:** Local private clean-source annotation summary plus sanitized scanner aggregate; no private text,
  raw source refs, thread ids, message ids, local paths, or candidate rows checked in.
- **supersedes / superseded_by:** Narrows the 2026-06-04 17/20 candidate-count blocker: candidate discovery is sufficient under
  the wide scan, but annotation retained/control count is still insufficient for private-history
  E2E50 quality. The public behavior pack is now the primary public path.
- **cannot_claim:** Completed private-history 20-case or 50-case E2E50 quality, private real-history behavior lift,
  representative E2E50 sample quality, live host behavior lift, or semantic-judge quality.

### `track_b.private_semantic_sidecar_required`

- **current_value:** 100 selected private real-history cases; 100/100 top-5 hits; 1.0 hit rate; `failed_count=0`;
  sanitized miss taxonomy empty after the #963 dynamic-source ranking repair.
- **run_date:** 2026-06-09
- **source_report:** [`public-readiness-verification.md`, 2026-06-09 #963
  rerun](readiness/public-readiness-verification.md#2026-06-09-issue-963-track-b-top-k-miss-repair)
- **claim_level:** `private_bounded_track_b_slice`
- **cohort:** Maintainer-only private real-history semantic-sidecar-required source-evidence slice.
- **supersedes / superseded_by:** Supersedes the 2026-05-29 97/100 selected private Track B row; the pre-repair same-day rerun
  exposed 5 top-k pruning misses, all with the gold source present in the raw candidate pool.
- **cannot_claim:** Public benchmark score, real-user gate quality, full semantic completeness, live semantic-model quality, or private-text disclosure.

### `retrieval_score_fusion.public_calibration_2026_06_10`

- **current_value:** Public-safe synthetic calibration: 5 cases; expected top match 5/5; semantic bridge lift 1;
  wrong-stance lure suppressed 1; vector-disabled fallback 1; source-join gate reject 1;
  exact-text guard preserved 1; raw source refs, candidate text, absolute paths, and private
  user data are not serialized.
- **run_date:** 2026-06-10
- **source_report:** `python -m pytest tests\aippocampus\test_retrieval_score_fusion.py -q`
- **claim_level:** `public_safe_deterministic_fixture`
- **cohort:** Synthetic #309 score-policy cases over `score_fusion.blend()` and `build_public_score_fusion_calibration_report()`.
- **supersedes / superseded_by:** Adds a public score-fusion calibration row next to the existing candidate-funnel and source-evidence/reranker diagnostics.
- **cannot_claim:** Default vector-prefilter adoption, local embedding adapter quality, live answer quality, broad
  reranker safety, latency/cost quality, private-history generality, or score output as source
  truth.

### `source_joined_routing.decision_2026_06_14`

- **current_value:** Public-safe #1370/#1372/#309 consumer decision: selected `recall_context -> recall_deepen` plus
  foreground packet source reopen as the measured consumer; 5 fixture cases; direct
  source-backed success 1.0 with average manual query invention 1.4; progressive source-reopen
  follow-through 1.0 with one stale-handle fail-closed case; source-ref rejoin 1.0; semantic
  bridge lift count 2; sentinel false-positive rate 0.0; wrong-route drag from sentinel 0;
  wrong-stance collision 0; source-join gate rejects 1; vector-disabled fallback 1; provider,
  foreground embedding, and external model calls 0.
- **run_date:** 2026-06-14
- **source_report:** [`source-joined-routing-decision-2026-06-14.md`](benchmarks/reports/recall-navigation/source-joined-routing-decision-2026-06-14.md)
  and `python -m pytest tests\aippocampus\test_source_joined_routing_decision.py -q`
- **claim_level:** `public_safe_consumer_decision_report`
- **cohort:** Deterministic public fixture over the progressive recall consumer plus post-source-join
  score-fusion calibration. No private data, live model calls, raw source text, raw source refs,
  credential environment variable names, provider payloads, local paths, or source-free vector
  hits.
- **supersedes / superseded_by:** Closes #1370 and #1372, and closes #309 as a decision issue: keep text-first source-joined
  defaults, allow score fusion only after source join, and defer vector prefilter / local
  embedding default adoption. Future vector, LLM expansion, or graph work should be new narrow
  product-gap issues with replayable public consumer evidence.
- **cannot_claim:** Live answer-quality lift, private-history generalization, default vector-prefilter safety, local
  embedding adapter quality, universal semantic or graph retrieval quality, or score output as
  source truth.

### `rollout_hard_event.route_chain_topk_calibration_2026_06_12`

- **current_value:** Public-safe rollout behavior route-chain calibration: top-k 1 fails because it recovers 0/3
  required two-source chains and records 3 source-support failures; top-k 2 passes with 3/3
  recall, 3/3 precision, 3/3 chain recovery, wrong-source evidence 0, stale-source top-k rate 0,
  and foreground action false positives 0; top-k 3 preserves main recall/precision but admits
  2/3 stale or narrative decoys into the top source set.
- **run_date:** 2026-06-12
- **source_report:** [`rollout-hard-event-route-chain-2026-06-12.md`](benchmarks/reports/public-longitudinal/rollout-hard-event-route-chain-2026-06-12.md)
- **claim_level:** `public_safe_synthetic_route_chain_diagnostic`
- **cohort:** Checked-in CC0 synthetic rollout behavior fixture; deterministic production-like retrieval; no
  private history, live model, raw source text, raw rollout text, provider call, or local
  absolute paths in committed outputs.
- **supersedes / superseded_by:** Adds a route-chain/actionability top-k boundary next to the #309 score-fusion and React VCS
  source-disambiguation rows: the useful budget is enough to complete a behavior-backed chain,
  not enough to foreground narrative decoys.
- **cannot_claim:** Representative #1197 public-quality cohort, #1195 benchmark promotion, live agent quality, wild
  VCS corpus quality, private real-history continuity quality, source truth from assistant
  narrative, or external-system superiority.

### `rollout_hard_event.public_cohort_v2_2026_06_12`

- **current_value:** Public-safe #1197 rollout hard-event cohort V2: 17 synthetic agent-behavior projects, 34 future
  events, 17 flag-worthy hard events, 17 anti-drift negatives; production-like top-k2 retrieval
  recovered 17/17 two-source chains with recall 1.0, precision 1.0, source-support failures 0,
  wrong-source evidence rate 0.0, stale-source top-k rate 0.0, foreground action false positives
  0, anti-drift violations 0, and current-vs-stale pairwise wins 34/34.
- **run_date:** 2026-06-12
- **source_report:** [`rollout-hard-event-cohort-v2-2026-06-12.md`](benchmarks/reports/public-longitudinal/rollout-hard-event-cohort-v2-2026-06-12.md)
- **claim_level:** `public_safe_synthetic_hard_event_cohort`
- **cohort:** Checked-in CC0 synthetic rollout behavior cohort; deterministic production-like retrieval; no
  private history, live model, raw source text, raw rollout text, provider call, or local
  absolute paths in committed outputs.
- **supersedes / superseded_by:** Adds the first broader public-safe hard-event pack for temporal override, cross-scope drift,
  cross-project contamination, post-compaction gaps, forget boundaries, Dream candidate
  boundaries, route-topic specificity, host-surface readiness, privacy redlines, observability,
  latency/cost, and tool-scope failures.
- **cannot_claim:** Live agent quality, wild public VCS corpus quality, private real-history continuity quality,
  #1195 benchmark-family promotion by itself, external-system superiority, or source truth from
  assistant narrative.

### `benchmark_family.promotion_candidates_2026_06_20`

- **current_value:** #1195 public-safe family-promotion decision: attention navigation remains promoted
  for the explicit-pull public/holdout surface, and selected agent continuity loop plus map-rot
  lifecycle debt now include observed public/holdout cohort measurements. Agent continuity
  measures 180 public-safe cases with 45 holdout; map-rot measures 270 public-safe cases with
  68 holdout. For both selected families, required usefulness blocker counts/rates are 0,
  `holdout_used_for_tuning_count=0`, and unresolved `next_measurement_actions=[]`.
- **run_date:** 2026-06-20
- **source_report:** [`benchmark-family-promotion-candidates-2026-06-20.md`](benchmarks/reports/benchmark-family/benchmark-family-promotion-candidates-2026-06-20.md),
  [`benchmark-family-promotion-candidates-2026-06-20.json`](benchmarks/reports/benchmark-family/benchmark-family-promotion-candidates-2026-06-20.json),
  and `python benchmarks\aippocampus\benchmark_family_promotion_candidates.py --json`
- **claim_level:** `public_safe_family_promotion_public_cohort_report`
- **cohort:** Public-safe generated cohort reports plus retained deterministic contract surfaces; no private
  history, live model, raw text, raw source refs, local paths, provider output, or cleanup writes
  in committed evidence.
- **supersedes / superseded_by:** Supersedes the 2026-06-12 target-only candidate report by embedding observed
  public/holdout measurements and treating #1969/#1948 as historical closed owners rather than
  active unresolved owner issues.
- **cannot_claim:** Live/private behavior lift, answer-generation quality, E2E50 closeout, cleanup-write runtime
  adoption, or external-system superiority.

### `fts5.real_history_recall_2026_05_29`

- **current_value:** Post-repair 100 selected source-backed cases; FTS5 91/100 top-1, 100/100 top-5, 100/100 top-10;
  production lexical-structural hybrid 100/100 top-10.
- **run_date:** 2026-05-29
- **source_report:** [`public-readiness-verification.md`, FTS5 real-history recall
  benchmark](readiness/public-readiness-verification.md) and
  [`memory-decision-benchmark-plan.md`](benchmarks/design/memory-decision-benchmark-plan.md)
- **claim_level:** `bounded_real_history_regression_smoke`
- **cohort:** Local 949-thread real-history registry slice after stale SQLite index repair.
- **supersedes / superseded_by:** Superseded only by a newer dated FTS5 real-history run.
- **cannot_claim:** Natural-language user-query quality, private text disclosure, broad product recall quality, or dense vector retrieval as a default path.

### `cjk.local_recall_public_fixture_2026_06_09_default_chunks`

- **current_value:** Public-safe expanded CJK fixture after #1054: 10 synthetic cases; production lexical-structural
  hybrid with default lightweight CJK query chunks hit 7/7 positive cases at top-5 with 0
  negative false positives; explicit `cjk_aware_sidecar` comparison also hit 7/7 positives; FTS5
  trigram alone hit 3/7 positives.
- **run_date:** 2026-06-09
- **source_report:** [`cjk-local-recall-fixture-report.md`](benchmarks/reports/recall-navigation/cjk-local-recall-fixture-report.md)
- **claim_level:** `public_safe_deterministic_fixture`
- **cohort:** Synthetic public exact/short/mixed/deictic/paraphrase/compact no-space/project-symbol/negative CJK local-recall cases.
- **supersedes / superseded_by:** Supersedes `cjk.local_recall_public_fixture_2026_06_09` for default-path behavior; the earlier
  same-day row remains historical gap evidence in the CJK report.
- **cannot_claim:** Broad Chinese recall quality, semantic Chinese search from trigram alone, production hybrid
  handling every compact CJK cue beyond this fixture, private-history CJK quality, heavyweight
  tokenizer need, or dense vector retrieval as a default path.

### `longmemeval_s.retrieval_only_500_2026_06_10`

- **current_value:** LongMemEval-S cleaned V1 retrieval-only larger slice: 500 questions; session R@10 479/500 =
  0.9580; evidence-line R@10 408/479 = 0.8518; context-visible evidence R@10 452/479 = 0.9436;
  session MRR 0.8809, evidence-line MRR 0.6309, context-visible evidence MRR 0.8086;
  warning_count 0. The exact-line taxonomy records evidence-line R@1/3/5/20/50 and classifies
  the 71 R@10 misses without raw text.
- **run_date:** 2026-06-10
- **source_report:** [`longmemeval.md`, current published result](benchmarks/longmemeval.md#current-published-result)
- **claim_level:** `public_external_retrieval_only_slice`
- **cohort:** LongMemEval-S cleaned V1 first 500 questions; deterministic retrieval-only adapter; top-k 10;
  evidence context radius 5; progress / partial-output path completed; no QA generation or judge
  model.
- **supersedes / superseded_by:** Supersedes the 2026-06-09 100-question LongMemEval-S row for current sample size and retires the
  incomplete 500-question missing-artifact blocker; oracle 50 remains a smoke row.
- **cannot_claim:** Answer-generation quality, LongMemEval QA score, judge-model score, LongMemEval-V2 score, SOTA
  or external baseline superiority, decision-gate quality, broad memory superiority, or
  exact-line citation quality being solved.

### `longmemeval_s.lexical_line_reranker_500_2026_06_10`

- **current_value:** Optional local lexical exact-line reranker diagnostic on the same 500 LongMemEval-S questions:
  first-stage evidence-line R@10 remains 408/479 = 0.8518; fused reranked evidence-line R@10 is
  419/479 = 0.8747; fused evidence-line MRR improves from 0.6309 to 0.6746; source-joined bridge
  lifts 11, including 10 context-visible exact-line misses and 1 same-session wrong-line top-k
  miss; reranker error count 0.
- **run_date:** 2026-06-10
- **source_report:** [`longmemeval.md`, optional lexical line-reranker follow-up](benchmarks/longmemeval.md#current-published-result)
- **claim_level:** `public_external_retrieval_reranker_diagnostic`
- **cohort:** LongMemEval-S cleaned V1 first 500 questions; deterministic retrieval-only adapter plus explicit
  `--line-reranker lexical`; top-k 10; evidence context radius 5; no external model, no answer
  labels, no expected-line leakage.
- **supersedes / superseded_by:** Adds a #1087 exact-line ranking follow-up next to the default retrieval-only 500-question row;
  does not supersede the default-off retrieval baseline.
- **cannot_claim:** Default exact-line citation quality, answer-generation quality, LongMemEval QA score,
  judge-model score, LongMemEval-V2 score, broad reranker safety, semantic understanding, SOTA
  or external baseline superiority, decision-gate quality, or broad memory superiority.

### `longmemeval_s.structural_exact_line_failure_500_2026_06_12`

- **current_value:** #1193 deterministic structural exact-line repair failure report: structural fused evidence-line
  R@10 is 416/479 = 0.8685 versus lexical 419/479 = 0.8747 on the same split; structural
  evidence-line MRR is 0.6663 versus lexical 0.6746; context-visible conversions are 8 versus
  lexical 10; same-session wrong-line reductions are 8 versus lexical 11. The report identifies
  36 context-visible candidate-visible misses that still need semantic/model line selection,
  plus source-window-not-visible miss families that need broader routing or source-side semantic
  support.
- **run_date:** 2026-06-12
- **source_report:** [`longmemeval-exact-line-repair-2026-06-12.md`](benchmarks/reports/longmemeval/repair/longmemeval-exact-line-repair-2026-06-12.md)
  and
  [`longmemeval-exact-line-repair-2026-06-12.json`](benchmarks/reports/longmemeval/repair/longmemeval-exact-line-repair-2026-06-12.json)
- **claim_level:** `public_external_retrieval_reranker_failure_report`
- **cohort:** LongMemEval-S cleaned V1 first 500 questions; deterministic retrieval-only adapter plus explicit
  `--line-reranker structural`; top-k 10; evidence context radius 5; no external model in the
  structural arm, no answer labels, no expected-line leakage, and no raw text/source/local paths
  in committed reports.
- **supersedes / superseded_by:** Closes #1193 as a measured deterministic failure boundary and separates cold online semantic
  rerank, warm query/candidate cache, and source-side semantic cache paths before further spend.
- **cannot_claim:** Improved-over-lexical exact-line quality, default structural reranker adoption, default
  exact-line citation quality, 500Q semantic reranker quality, source-side semantic cache
  latency/build cost, answer-generation quality, official LongMemEval QA score, judge-model
  score, provider-independent quality, SOTA, or broad memory superiority.

### `longmemeval_s.semantic_warm_query_cache_25_2026_06_12`

- **current_value:** #1305 warm query/candidate cache replay over a fresh 25Q semantic pilot with candidate-pack
  hashes: 24/24 available cold-fill calls had complete cache keys; first pass recorded 24
  cold-fill misses, second pass recorded 24 warm hits with hit rate 1.0000 and two-pass hit rate
  0.5000; warm lookup latency averaged 0.000079ms; cold-fill latency averaged 6308.67ms with
  223947 total tokens and provider prefix-cache hit rate 0.0000. Exact-line metrics on the
  narrow pilot were first-stage R@10 23/25, semantic-only R@10 24/25, fused reranked R@1 23/25,
  fused reranked R@3/R@5/R@10 25/25, MRR 0.9600, and top-10 regression count 0; context-visible
  exact-line misses 2/2 and the same two same-session wrong-line focus cases were recovered.
- **run_date:** 2026-06-12
- **source_report:** [`longmemeval-semantic-cache-path-2026-06-12.md`](benchmarks/reports/longmemeval/semantic-cache/longmemeval-semantic-cache-path-2026-06-12.md),
  [`longmemeval-semantic-cache-path-2026-06-12.json`](benchmarks/reports/longmemeval/semantic-cache/longmemeval-semantic-cache-path-2026-06-12.json),
  and [`longmemeval.md`, warm query/candidate cache
  replay](benchmarks/longmemeval.md#current-published-result)
- **claim_level:** `public_external_llm_reranker_warm_cache_replay`
- **cohort:** LongMemEval-S cleaned V1 first 25 questions, all `longmemeval_single-session-user`; explicit
  DeepSeek-compatible semantic line reranker; candidate-pack hash includes candidate
  line/routing metadata plus source-text hashes, while committed reports emit only aggregates
  and no raw question, answer, source text, cache keys, cache values, provider responses,
  credentials, or local paths.
- **supersedes / superseded_by:** Completes #1305 path B by measuring warm query/candidate cache-key completeness and local replay
  lookup separately from cold provider latency and provider prefix-cache behavior. It does not
  supersede the 500Q retrieval, lexical, or structural rows, and it leaves source-side semantic
  warming as a separate unmeasured path.
- **cannot_claim:** 500Q semantic reranker quality, source-side semantic cache build cost or hot-path latency, live
  hook latency, default semantic reranker adoption, provider-independent quality,
  answer-generation quality, official LongMemEval QA score, LongMemEval-V2 quality, SOTA, broad
  per-type quality, or broad memory superiority.

### `longmemeval_s.semantic_query_cache_100_2026_06_12`

- **current_value:** #1323 100Q semantic query/candidate cache progress: first 100 LongMemEval-S questions, 94
  evidence-line cases; session R@10 `97/100 = 0.9700`; context-visible evidence R@10 `91/94 =
  0.9681`; first-stage evidence-line R@10 `82/94 = 0.8723`, MRR `0.6481`; same-cohort lexical
  fused R@10 `84/94 = 0.8936`, MRR `0.6990`; semantic-only first run R@10 `87/94 = 0.9255`, MRR
  `0.8989`; semantic fused first run R@10 `91/94 = 0.9681`, MRR `0.9246`; semantic fused
  repeated workers=8 R@10 stayed `91/94` with MRR `0.9037`. Query/candidate replay found `90/90`
  complete cache keys and `90/90` second-pass warm hits; warm local lookup averaged
  `0.000063ms`; cold-fill provider latency averaged `11136.85ms` with `979237` tokens. Provider
  prefix-cache telemetry rose from `0.2514` on the workers=2 first run to `0.9932` on the
  workers=8 repeated run, while wall time fell from `767.25s` to `273.35s`.
- **run_date:** 2026-06-12
- **source_report:** [`longmemeval-semantic-cache-100q-2026-06-12.md`](benchmarks/reports/longmemeval/semantic-cache/longmemeval-semantic-cache-100q-2026-06-12.md),
  [`longmemeval-semantic-cache-100q-2026-06-12.json`](benchmarks/reports/longmemeval/semantic-cache/longmemeval-semantic-cache-100q-2026-06-12.json),
  and [`longmemeval.md`, 100Q semantic query/candidate cache
  progress](benchmarks/longmemeval.md#current-published-result)
- **claim_level:** `public_external_llm_reranker_query_cache_100q_progress`
- **cohort:** LongMemEval-S cleaned V1 first 100 questions: `70` single-session-user and `30` multi-session
  cases; explicit DeepSeek-compatible semantic line reranker; same-cohort deterministic lexical
  comparison; top-k `10`; provider budget and partial-output checkpoints declared; committed
  reports emit only aggregate metrics and short report hashes, not raw question, answer, source
  text, provider responses, cache keys, cache values, credentials, or absolute paths.
- **supersedes / superseded_by:** Scales the #1305 query/candidate cache evidence from 25Q to 100Q and adds same-cohort lexical
  comparison for #1323. It is superseded as a same-cohort comparison point by the 500Q
  worker-surface proxy and LLM upper-bound row.
- **cannot_claim:** Source-side semantic cache build cost or hot-path latency before the 2026-06-13 row, full 500Q
  semantic reranker quality before the 2026-06-13 row, live hook latency, default semantic
  reranker adoption, provider-independent quality, answer-generation quality, official
  LongMemEval QA score, LongMemEval-V2 quality, SOTA, broad per-type quality, or broad memory
  superiority.

### `longmemeval_s.source_worker_surface_and_semantic_upper_bound_500_2026_06_13`

- **current_value:** 500Q measurement separates two arms on the same LongMemEval-S first-500 cohort. Current
  source-worker-surface proxy: baseline evidence-line R@10 `408/479 = 0.8518`, baseline MRR
  `0.6309`; source-worker search alone R@10 `156/479 = 0.3257`, MRR `0.1391`; source-worker
  rerank only R@10 `398/479 = 0.8309`, MRR `0.5046`; FTS-preserving fused R@10 `422/479 =
  0.8810`, MRR `0.6734`; bridge lifts `14`; fused top-10 regression count `0`; source-only
  regression count `24`; line-reranker errors `0`; provider calls/tokens `0`. Proxy prewarm
  built `246738` `aippocampus_working_memory` navigation rows with complete rate `1.0`; hot
  source-worker search averaged `1044.5179ms`, while candidate rerank averaged `1.18ms`.
  Separate LLM query/candidate upper bound: semantic fused R@10 `451/479 = 0.9415`, MRR
  `0.8738`, bridge lifts `43`, available calls `470/479`, errors `9` including `7` timeouts
  under explicit `180s` timeout, and `4719903` total provider tokens with provider prefix-cache
  hit rate `0.2290`.
- **run_date:** 2026-06-13
- **source_report:** [`longmemeval-source-worker-surface-500q-2026-06-13.md`](benchmarks/reports/longmemeval/semantic-cache/longmemeval-source-worker-surface-500q-2026-06-13.md),
  [`longmemeval-source-worker-surface-500q-2026-06-13.json`](benchmarks/reports/longmemeval/semantic-cache/longmemeval-source-worker-surface-500q-2026-06-13.json),
  and [`longmemeval.md`, 500Q source-worker-surface proxy and LLM upper
  bound](benchmarks/longmemeval.md#current-published-result)
- **claim_level:** `public_external_source_worker_surface_proxy_and_llm_upper_bound_500q`
- **cohort:** LongMemEval-S cleaned V1 first 500 questions; proxy arm builds existing AIppocampus
  `aippocampus_working_memory` row shape from clean source and uses the existing matcher, with
  source reopen required for claims; it does not exercise `semantic_scope_labeling`,
  `semantic_scope_builder`, subconscious jobs, warm ambient routes, or attention-router handoff
  as the canonical source-side materializer. LLM arm is explicit query/candidate DeepSeek
  rerank. Reports and committed summaries emit aggregate metrics and report hashes, not raw
  question, answer, source text, cache values, provider responses, credentials, or absolute
  local paths.
- **supersedes / superseded_by:** Measures the current worker-row proxy and the 500Q query/candidate LLM upper bound. It
  supersedes the 100Q progress row as a same-cohort comparison point while preserving that row
  as provider-prefix-cache comparison evidence.
- **cannot_claim:** Official LongMemEval QA score, answer-generation quality, SOTA, provider-independent semantic
  quality, default foreground LLM rerank, canonical source-side semantic warming/materializer
  quality, broad life-history memory superiority, or a claim that current worker-surface quality
  equals the LLM upper bound.

### `longmemeval_s.full_source_semantic_warming_500_2026_06_13`

- **current_value:** #1323 contract-aware full-source semantic-scope warming over the same LongMemEval-S first-500
  cohort: source-index cache hit `500/500` with `0` source-index rebuilds; materializer
  `public_semantic_labeler_full_source` sent `246738` clean-source candidate messages across
  `500` batches; provider cold-fill calls `500`; sidecar materialization status was partial with
  `458` materialized cases and `42` labeler errors; reviewed source cache had `451` sidecar
  cases and `2745` semantic-scope label rows; hot-query provider calls stayed `0`. Sidecar
  evidence coverage rose to `53/479`, context coverage to `74/479`, and query/sidecar term
  overlap to `260` cases / `502` total overlaps, but fused evidence-line R@10 stayed `422/479 =
  0.8810` with MRR `0.6763`. No-lift diagnosis: only `3/71` baseline misses had sidecar exact
  coverage; `50/53` sidecar exact evidence hits were already baseline top-10 hits; among the
  `37` fused misses where the gold line was candidate-visible, the gold line had `0/37`
  semantic-scope labels/terms/query overlaps. Provider telemetry reported `60710135` total
  tokens, `12548480` prompt-cache hit tokens, and `43575795` prompt-cache miss tokens; that miss
  count is provider prefix-cache telemetry for cold full-source prompts, not local AIppocampus
  source-index cache failure.
- **run_date:** 2026-06-13
- **source_report:** [`longmemeval-full-source-semantic-warming-500q-2026-06-13.md`](benchmarks/reports/longmemeval/semantic-cache/longmemeval-full-source-semantic-warming-500q-2026-06-13.md),
  [`longmemeval-full-source-semantic-warming-500q-2026-06-13.json`](benchmarks/reports/longmemeval/semantic-cache/longmemeval-full-source-semantic-warming-500q-2026-06-13.json),
  and [`longmemeval.md`, current published
  result](benchmarks/longmemeval.md#current-published-result)
- **claim_level:** `public_external_full_source_semantic_scope_warming_diagnostic`
- **cohort:** LongMemEval-S cleaned V1 first 500 questions; public source-side semantic-scope sidecar
  materialization with contract-aware sidecar manifests; no private history; no answer labels,
  raw question, answer, source text, provider responses, cache values, credentials, or absolute
  local paths in committed evidence. The hot retrieval/rerank path uses local source cache only
  after prewarming.
- **supersedes / superseded_by:** Supersedes the 8-candidate/top-selector sidecar diagnostic as the fairer source-side semantic
  warming measurement and fixes the cache-contract boundary by requiring materializer manifests
  before sidecar reuse. It shows that the current full-source sidecar is still a sparse
  continuity-scope layer, not a dense factual retrieval surface; the next fix must attach
  source-side retrieval terms/summaries to hard factual rows before fusion can lift this
  benchmark.
- **cannot_claim:** Official LongMemEval QA score, answer-generation quality, SOTA or external baseline superiority,
  provider-independent semantic quality, default foreground LLM rerank, full AIppocampus product
  ability, semantic sidecar values as source truth, or a claim that full-source warming improves
  fused R@10 on this adapter.

### `longmemeval_s.source_factual_alias_500_2026_06_14`

- **current_value:** 500Q source factual-alias closeout on the same LongMemEval-S first-500 cohort: baseline session
  R@10 `479/500 = 0.9580`; baseline evidence-line R@10 `408/479 = 0.8518`; context-visible
  evidence R@10 `452/479 = 0.9436`; fused source-semantic-cache evidence R@10 `422/479 =
  0.8810`; fused MRR `0.6744`; candidate evidence coverage `463/479 = 0.9666`, up from the
  earlier lexical 500Q diagnostic's `455/479 = 0.9499`; remaining fused misses split into `15`
  candidate-missing and `42` reranker-visible misses. Factual-alias evidence coverage is
  `227/479 = 0.4739`, factual-alias candidate coverage is `220/479 = 0.4593`, gold candidate
  alias cases `220`, gold candidate query-overlap cases `28`, factual-alias candidate lift
  top-10 `16`, factual-alias fused lift top-10 `2`, and fused regression top-10 `0`. Cache
  metrics: `500` source caches, `246738` source rows/spans, `109144` factual-alias profiles,
  `738561` factual-alias terms, cache-key complete rate `1.0`, hot-query provider calls `0`,
  provider tokens `0`, hot-query latency average `1092.5576ms` and max `1926.4032ms`.
- **run_date:** 2026-06-14
- **source_report:** [`longmemeval-source-factual-alias-500-2026-06-14.md`](benchmarks/reports/longmemeval/factual-alias/longmemeval-source-factual-alias-500-2026-06-14.md),
  [`longmemeval-source-factual-alias-500-2026-06-14.json`](benchmarks/reports/longmemeval/factual-alias/longmemeval-source-factual-alias-500-2026-06-14.json),
  and [`longmemeval.md`, 500Q source factual-alias
  closeout](benchmarks/longmemeval.md#current-published-result)
- **claim_level:** `public_external_source_factual_alias_closeout_500q`
- **cohort:** LongMemEval-S cleaned V1 first 500 questions; deterministic source-side factual-alias and
  answer-bearing source handles built from clean source; source-semantic-cache hot path; no
  private history, no answer labels, no raw question, answer, source text, provider responses,
  cache values, credentials, or absolute local paths in committed evidence. Aliases and
  working-memory rows are navigation-only and require source reopen before factual claims.
- **supersedes / superseded_by:** Closes #1327 as a bounded source-window coverage diagnostic, closes #1424 as a source-side
  factual artifact/hot-path owner, and makes #1323 closeable as a measured source-side benchmark
  slice while preserving the full-source semantic-scope no-lift row as a real boundary. Future
  exact-line/reranker improvements should be new scoped issues, not a reason to keep these owner
  issues open.
- **cannot_claim:** Answer-generation quality, official LongMemEval QA score, LongMemEval-V2 behavior, SOTA or
  external baseline superiority, broad life-history memory superiority, default foreground
  adoption, perfect exact-line citation quality, or source truth from aliases/working-memory
  rows/candidate routes without source reopen.

### `longmemeval_s.post_factual_alias_rerank_closeout_500_2026_06_14`

- **current_value:** #1437 post-factual-alias closeout on the same LongMemEval-S first-500 sanitized report: 500
  questions; 479 evidence-line cases; reranked evidence-line R@10 `422/479 = 0.8810`; MRR
  `0.6744`; candidate evidence coverage `463/479 = 0.9666`; top-10 regressions `0`; hot-query
  provider calls `0`; hot-query latency avg/max `1092.5576ms / 1926.4032ms`. The 57 fused misses
  split into `15` candidate-missing and `42` reranker-visible misses. Scoped
  `post_factual_alias_exact_line_rerank_v1` default reranker change is rejected; bounded
  candidate coverage projection is accepted only as a future candidate-builder slice with
  `candidate_coverage_lift=6` and `candidate_byte_growth_ratio=0.0001`;
  `full_500_projection.decision` is `already_measured_local_hot_path` because this path has no
  provider calls or tokens.
- **run_date:** 2026-06-14
- **source_report:** [`longmemeval-post-factual-alias-rerank-closeout-500-2026-06-14.md`](benchmarks/reports/longmemeval/factual-alias/longmemeval-post-factual-alias-rerank-closeout-500-2026-06-14.md),
  [`longmemeval-post-factual-alias-rerank-closeout-500-2026-06-14.analysis.json`](benchmarks/reports/longmemeval/factual-alias/longmemeval-post-factual-alias-rerank-closeout-500-2026-06-14.analysis.json),
  and `python -m pytest tests\aippocampus\test_benchmark_longmemeval_rerank_analysis.py -q`
- **claim_level:** `public_external_post_alias_reranker_closeout`
- **cohort:** Same sanitized LongMemEval-S first-500 factual-alias report; no private history, raw question,
  answer, source text, source refs, provider payloads, cache values, credentials, or absolute
  local paths in committed evidence. Candidate-builder projection is not an exact-line ranking
  result and aliases/routes require source reopen.
- **supersedes / superseded_by:** Closes #1437 by analyzing the remaining 57 misses, explicitly rejecting a default exact-line
  reranker change from this evidence, and separating a bounded candidate-builder follow-up from
  source-truth or answer-quality claims.
- **cannot_claim:** Perfect exact-line citation quality, default reranker adoption, answer-generation quality,
  official LongMemEval QA score, LongMemEval-V2 behavior, SOTA or external baseline superiority,
  broad memory superiority, provider-backed full-rerank budget need for this local closeout, or
  source truth from aliases/candidate routes without source reopen.

### `longmemeval_s.semantic_llm_line_reranker_pilot_25_2026_06_10`

- **current_value:** Optional external-model exact-line reranker pilot on the first 25 LongMemEval-S questions:
  first-stage evidence-line R@10 is 23/25 = 0.9200; semantic-only evidence-line R@10 is 24/25 =
  0.9600; fused reranked evidence-line R@10 is 25/25 = 1.0000; fused evidence-line MRR improves
  from 0.6348 to 1.0000; reranked ladder R@1/R@3/R@5/R@10/R@20/R@50 is all 25/25 = 1.0000;
  context-visible rescue conversion 2/2; same-session wrong-line reduction 2/2; regression count
  0; source-joined bridge lifts 2; reranker availability 24/25 with 1 timeout; total tokens
  225170 and average available-call latency 7156.27ms. The 500-question projection is about
  4503400 tokens and 59.64 single-worker minutes, with provider dollar cost not reported, so the
  full 500Q semantic run is explicit opt-in only.
- **run_date:** 2026-06-10
- **source_report:** [`longmemeval.md`, optional semantic LLM line-reranker
  pilot](benchmarks/longmemeval.md#current-published-result) and
  [`longmemeval-semantic-rerank-analysis-2026-06-10.json`](benchmarks/reports/longmemeval/semantic-cache/longmemeval-semantic-rerank-analysis-2026-06-10.json)
- **claim_level:** `public_external_llm_reranker_pilot_budget_bounded`
- **cohort:** LongMemEval-S cleaned V1 first 25 questions, all `longmemeval_single-session-user`;
  retrieval-only adapter plus explicit `--line-reranker semantic`; DeepSeek-compatible
  `deepseek-v4-flash`; prompt version `llm-window-to-line-rerank-v1`; top-k 10; evidence context
  radius 5; external model saw question text and bounded candidate source text, but not gold
  answers, expected lines/sessions, `has_answer` labels, judge labels, miss taxonomy, or raw
  report cases.
- **supersedes / superseded_by:** Adds the #1092 pilot analysis and full-500 budget/latency/privacy decision next to the default
  retrieval-only and lexical rows; it keeps the arm available but does not supersede the
  500-question retrieval baseline or adopt semantic reranking as default.
- **cannot_claim:** Default exact-line citation quality, 500-question LLM-reranker quality, answer-generation
  quality, LongMemEval QA score, judge-model score, LongMemEval-V2 score, provider-independent
  quality, broad reranker safety, per-type full-split quality, SOTA or external baseline
  superiority, decision-gate quality, or broad memory superiority.

### `longmemeval_s.fixed_reader_answer_25_2026_06_12`

- **current_value:** Provider-backed fixed-reader answer/latency baseline on 25 LongMemEval-S cleaned V1 cases:
  reader attempted 25/25; deterministic answer-correct count 20/25 = 0.8000; context sufficient
  25/25; reader abstention count 0; retrieval/reference layer in the same run had session R@10
  25/25, evidence-line R@10 23/25, context-visible evidence R@10 25/25, and warning_count 0;
  reader latency averaged 2723.84ms with max 6775.68ms; total elapsed 192.69s; token use 379965
  total; run-configured estimated cost USD 0.106922; sanitized report validation passed.
- **run_date:** 2026-06-12
- **source_report:** [`longmemeval-fixed-reader-answer-25-2026-06-12.md`](benchmarks/reports/longmemeval/fixed-reader/longmemeval-fixed-reader-answer-25-2026-06-12.md)
  and [`longmemeval.md`, current published
  result](benchmarks/longmemeval.md#current-published-result)
- **claim_level:** `public_external_fixed_reader_answer_latency_pilot`
- **cohort:** LongMemEval-S cleaned V1 first 25 questions, all `longmemeval_single-session-user`;
  DeepSeek-compatible `deepseek-v4-flash`; prompt version `longmemeval-s-fixed-reader-v1`; local
  deterministic overlap judge; top-k 10; evidence context radius 5; external reader saw public
  question text and bounded candidate source lines but not gold answers, expected
  lines/sessions, has-answer labels, retrieval miss taxonomy, judge labels, or raw report cases.
- **supersedes / superseded_by:** Adds the first #1194 dated fixed-reader answer/latency row. It does not supersede the
  500-question retrieval-only row; it adds a small answer-quality, latency, token, and cost
  baseline layered on the same source-evidence adapter.
- **cannot_claim:** Official LongMemEval judge score, official leaderboard/SOTA, LongMemEval-V2 quality, default
  reader/provider adoption, model-independent memory superiority, private real-history quality,
  LoCoMo answer quality, broad per-type LongMemEval-S quality, or answer quality beyond this
  25-case single-session-user pilot.

### `longmemeval_s.fixed_reader_cleanup_25_2026_06_12`

- **current_value:** Public-safe #1282 cleanup reran the same 25 LongMemEval-S cleaned V1 cases with prompt v2 and
  refined taxonomy: retrieval/reference remained session R@10 25/25, evidence-line R@10 23/25,
  and context-visible evidence R@10 25/25; deterministic answer-correct count was 19/25 =
  0.7600; failure review found 3 reader/provider errors, 1 false abstention on answerable
  bounded evidence, 1 deterministic-judge mismatch, and 1 true reader miss; sanitized report
  validation passed; expansion gate status is `no_go` for 100Q or 500Q until blockers are fixed.
- **run_date:** 2026-06-12
- **source_report:** [`longmemeval-fixed-reader-cleanup-25-2026-06-12.md`](benchmarks/reports/longmemeval/fixed-reader/longmemeval-fixed-reader-cleanup-25-2026-06-12.md)
  and [`longmemeval.md`, current published
  result](benchmarks/longmemeval.md#current-published-result)
- **claim_level:** `public_external_fixed_reader_failure_review_no_go`
- **cohort:** LongMemEval-S cleaned V1 first 25 questions, all `longmemeval_single-session-user`;
  DeepSeek-compatible `deepseek-v4-flash`; prompt version `longmemeval-s-fixed-reader-v2`; local
  deterministic overlap judge v2; top-k 10; evidence context radius 5; external reader saw
  public question text and bounded candidate source lines plus salience hints and bounded-answer
  policy, but not gold answers, expected lines/sessions, has-answer labels, retrieval miss
  taxonomy, judge labels, or raw report cases.
- **supersedes / superseded_by:** Turns the #1194 answer baseline into an actionable #1282 failure-review and expansion-gate
  artifact; it explicitly blocks larger provider answer runs rather than treating the 25Q pilot
  as scale-ready.
- **cannot_claim:** Improved answer score, official LongMemEval judge score, 100Q or 500Q answer quality,
  LongMemEval-V2 quality, default reader/provider adoption, model-independent memory
  superiority, private real-history quality, broad per-type LongMemEval-S quality, or proof that
  the fixed reader is ready to scale.

### `demo_scenarios.claim_boundaries`

- **current_value:** Public-safe demo scenarios show product shape; their material-limit lines are claim-boundary sources for demos.
- **run_date:** 2026-06-03
- **source_report:** [`docs/guides/demo-scenarios.md`](../guides/demo-scenarios.md)
- **claim_level:** `claim_boundary_source`
- **cohort:** Public example bundle, public-safe demo commands, and explicit live/smoke demo flows.
- **supersedes / superseded_by:** Not a metric row; it routes demo caveats into evidence governance.
- **cannot_claim:** Official benchmark proof, readiness metric upgrades, or private real-history performance.

### `claude_code.real_host_dogfood_2026_06_11`

- **current_value:** Local Claude Code history parser passed on 222 detected sessions; dry-run onboarding planned 223
  registrations and 3 stale-index repairs without writing; synthetic cross-agent clean-source
  retrieval passed in both directions; temporary strict-config Claude Code MCP live call reached
  `memory_health`; #1235 then repaired the persistent local Claude MCP entry to `aippocampus
  mcp`, after which the no-write persistent diagnostic reported `persistent_config_healthy`,
  nested status `healthy`, tool count 10, and `memory_health` listed.
- **run_date:** 2026-06-11
- **source_report:** [`claude-code-dogfood-2026-06-09.md`](readiness/claude-code-dogfood-2026-06-09.md),
  [`claude-code-mcp.md`](../guides/setup/claude-code-mcp.md), and #1235 persistent diagnostic
  closeout
- **claim_level:** `local_real_host_dogfood_with_persistent_config_repair`
- **cohort:** Single Windows operator host plus public-safe synthetic Codex/Claude fixture.
- **supersedes / superseded_by:** Supersedes the 2026-06-09 persistent-config blocker for this local host only; preserves
  temporary strict-config MCP reachability as the original positive live-host proof and records
  the portable persistent config repair.
- **cannot_claim:** Claude Code real-host hook firing beyond the scoped #1020 synthetic contract, cross-host
  persistent MCP health, unattended private-history ingestion, cross-device sync, hosted/cloud
  continuity, broad cross-host relationship continuity, package-manager availability on every
  machine, or private-history quality.

### `claude_code.hooks_contract_2026_06_09`

- **current_value:** Scoped Claude Code hook contract slice: `status`, `dry-run`, and `smoke` commands exist;
  `UserPromptSubmit` and `Stop` synthetic Claude-shaped hook inputs exit 0 without leaking raw
  prompt text, session ids, transcript paths, cwd values, settings paths, source refs, or
  synthetic tool payload text; `PostToolUse`/`PostToolBatch` and compaction hooks report
  event-level blockers.
- **run_date:** 2026-06-09
- **source_report:** [`claude-code-hooks-contract-2026-06-09.md`](readiness/claude-code-hooks-contract-2026-06-09.md)
- **claim_level:** `scoped_synthetic_hook_contract`
- **cohort:** Public-safe synthetic Claude-shaped hook payloads plus official-contract intake.
- **supersedes / superseded_by:** Narrows the broad Claude Code hook caveat into scoped `UserPromptSubmit`/`Stop` handler
  availability and explicit unsupported-event blockers.
- **cannot_claim:** Real-host hook firing, Claude settings mutation, configuration-mutating installer availability,
  `PostToolUse`/`PostToolBatch` payload capture, compaction survival packet utility, all Claude
  Code versions, MCP health, transcript onboarding, or private-history quality.

### `multimodal_niah.evidence_pool_conflict_resolution`

- **current_value:** Public-safe NIAH evidence-pool contract: 4/4 answer/source-selection/source-anchor-citation
  after conflict repair; one stale input source selection preserved as
  `input_selected_evidence_ids`, `current_source_selected_count=1`,
  `stale_or_conflicting_distractor_selection_count=0`, `needs_source_reopen_count=0`;
  ambiguous-currentness regression control requires `needs_source_reopen` instead of guessing.
- **run_date:** 2026-06-09
- **source_report:** [`multimodal-niah-evidence-pool-report.md`](benchmarks/reports/multimodal/multimodal-niah-evidence-pool-report.md)
- **claim_level:** `public_safe_deterministic_contract`
- **cohort:** Four public synthetic NIAH supplied-pool rows plus one in-test ambiguous-currentness negative control; retrieval is intentionally not scored.
- **supersedes / superseded_by:** Supersedes the 2026-06-03 expected stale-source failure interpretation for the #533 NIAH supplied-pool contract.
- **cannot_claim:** Retrieval quality, ATM-Bench Hard score/support, live vision-model answer quality, raw-media
  model quality, private media behavior, or broad multimodal-memory quality.

### `recall_navigation.progressive_route_follow_through`

- **current_value:** Progressive `recall_context -> recall_deepen` arm: `route_actionability_rate=1.0`, eligible
  `source_reopen_follow_through_rate=1.0` (3/3 eligible route reopens reached expected
  clean-source refs), `source_reopen_fail_closed_count=1` with
  `failure_class=stale_handle_rejected_before_source_use`,
  `avg_manual_query_invention_count=0.0`; foreground packet candidate ref follow-through reached
  the expected fixture source with `foreground_manual_query_invention_count=0`.
- **run_date:** 2026-06-09
- **source_report:** [`recall-navigation-comparison-2026-06-03.md`](benchmarks/reports/recall-navigation/recall-navigation-comparison-2026-06-03.md)
- **claim_level:** `public_safe_deterministic_proxy`
- **cohort:** Four public synthetic clean-source fixtures plus one foreground hook packet/cache fixture; all
  use temporary public-safe clean-source/index/cache data.
- **supersedes / superseded_by:** Updates the #465 comparison with a narrow #201 route-follow-through readout; does not supersede live #201 field reports.
- **cannot_claim:** Live user quality, broad default foreground first-turn or second-turn lift, production selector
  superiority, source-backed answer quality beyond the synthetic fixtures, or closing #201.

### `recall_navigation.macro_prior_fixture_2026_06_12`

- **current_value:** #1300 runtime/promotion slice: `agent_continuity.recall` consumes
  `.aippocampus/macro-orientation.jsonl` or `.aippocampus/macro_orientation.jsonl` from the
  supplied `cwd` when no explicit `--macro-state-jsonl` is passed; the promotion harness reports
  `macro_navigation_readout.measured=true`, `active_layer_order_delta_count=1`,
  `hamming_fanout_delta_count=1`, `momentum_recheck_diagnostic_count=1`,
  `manual_search_fallback_reduction_count=1`, `stale_as_current_count=0`, and
  `claim_without_source_reopen_count=0`; `default_adoption_allowed=false`.
- **run_date:** 2026-06-12
- **source_report:** [`recall-navigation-comparison-2026-06-03.md`](benchmarks/reports/recall-navigation/recall-navigation-comparison-2026-06-03.md)
  and `python -m unittest tests.aippocampus.test_agent_opt_in_continuity
  tests.aippocampus.test_recall_navigation_promotion -v`
- **claim_level:** `public_safe_default_path_and_promotion_fixture`
- **cohort:** Project-local default macro state file, synthetic public-safe route set,
  same-corpus/same-query/same-budget promotion arms, and no private history or external model
  calls.
- **supersedes / superseded_by:** Adds the #1300 default-path/runtime slice and macro promotion readout without changing the #1185
  default-session usefulness gate.
- **cannot_claim:** Macro/router default-ready behavior, live host lift, private-history macro quality, source truth
  from macro state, answer-generation quality, broad route-selector superiority, or MCP-core
  default behavior.

### `macro.transform_orbit_diagnostic_2026_06_12`

- **current_value:** #1315 reversible transform-orbit diagnostic slice: `cr_reversible` uses only opposite and
  reverse transforms; the inventory reports 20 unique C/R orbits across 64 hexagrams with size
  distribution `{2: 8, 4: 12}`; line flips are emitted as adjacency; nuclear dynamics are
  emitted as non-invertible projection basins with four 16-source basins; packets keep
  `authority_level=navigation_only`, `candidate_authority=candidate_only`,
  `claim_permission=no_claim_before_reopen`, `fact_claim_allowed=false`, and
  `default_ranking_effect=none`.
- **run_date:** 2026-06-12
- **source_report:** [`yi-macro-runtime-interfaces.md`](../architecture/coordination/yi-macro-runtime-interfaces.md)
  and `python -m unittest tests.aippocampus.test_yi_macro_runtime_interfaces -v`
- **claim_level:** `public_safe_deterministic_macro_structure_fixture`
- **cohort:** Canonical public 64-hexagram table, deterministic structural transforms, no private history, no
  model calls, no raw source handles, and no foreground rendering.
- **supersedes / superseded_by:** Adds the #1315 macro route-equivalence diagnostic substrate without promoting it into Dream
  routing, foreground packets, or source evidence.
- **cannot_claim:** Dream integration quality, route merging, source support, default ranking or fanout changes,
  foreground symbolic prose, private-history behavior, Yi interpretation quality, or claim
  support without source reopen.

### `macro.timing_recheck_experiment_2026_06_12`

- **current_value:** #1314 public-safe timing experiment: four synthetic source-event cases cover active-axis
  route-success recency, stale/counter-evidence recheck pressure, normal source-epoch cadence,
  and slow-quiet below-threshold cadence; report metrics are `case_count=4`,
  `distinct_signal_count=2`, `claim_without_source_reopen_count=0`,
  `currentness_mutation_count=0`, `default_adoption_allowed=false`, and
  `promotion_status=fixture_candidate_not_promoted`.
- **run_date:** 2026-06-12
- **source_report:** [`yi-macro-runtime-interfaces.md`](../architecture/coordination/yi-macro-runtime-interfaces.md)
  and `python -m unittest tests.aippocampus.test_macro_timing_recheck_experiment
  tests.aippocampus.test_yi_macro_runtime_interfaces -v`
- **claim_level:** `public_safe_deterministic_macro_timing_fixture`
- **cohort:** Synthetic source-event rows only; source deltas are aggregate numeric fixtures; no private
  history, no raw source refs, no model calls, no live hooks, no calendar/solar-term schedule,
  and no foreground rendering.
- **supersedes / superseded_by:** Adds a usable #1314 experiment boundary for active-axis and source-epoch recheck diagnostics
  while leaving currentness/temporal heads and live recall untouched.
- **cannot_claim:** Live recall adoption, recall-quality lift, token/tool-cost savings, private-history timing
  quality, classical calendar timing, currentness/freshness truth, default ranking changes,
  scheduled background work, or claim support without source reopen.

### `dream.shadow_route_topology_scout_2026_06_12`

- **current_value:** #1313 public-safe Dream topology scout slice: built-in fixture reports
  `dream_topology_candidate_count=5`, `shadow_route_candidate_count=2`,
  `shadow_route_source_overlap_count=2`, `transform_orbit_deepen_candidate_count=1`,
  `shadow_route_generic_vocab_false_positive_count=0`, and
  `shadow_route_claim_without_reopen_count=0`; candidates keep
  `candidate_authority=candidate_only`, `authority_level=navigation_only`,
  `action_grammar=direction_with_ref`, `source_reopen_required_before_claim=true`,
  `foreground_eligible=false`, and `fact_claim_allowed=false`.
- **run_date:** 2026-06-12
- **source_report:** [`dream-task-design.md`](../research/dream-task-design.md),
  [`benchmark-evidence-map.md`](benchmark-evidence-map.md), and `python -m unittest
  tests.aippocampus.test_dream_topology_scout -v`
- **claim_level:** `public_safe_deterministic_dream_shadow_route_fixture`
- **cohort:** Built-in synthetic/public-safe Dream topology rows only; sanitized issue anchors, deterministic
  transform-orbit diagnostics, no private history, no model calls, no raw source handles, no
  local paths, and no foreground rendering.
- **supersedes / superseded_by:** Adds the #1313 shadow-route candidate substrate inside the existing Dream topology scout without
  changing the Dream worker or live delivery path.
- **cannot_claim:** Live Dream quality, private-history Dream usefulness, automatic route merging, hidden user
  intent, foreground usefulness, transform-orbit source support, default ranking/fanout changes,
  or claim support without source reopen.

### `live_semantic.route_actionability_2026_06_07`

- **current_value:** Public checked-in local corpus live smoke: 8/8 correct; semantic available 4/4;
  `semantic_evidence_guarded_to_scent_count=3`; all 3 guarded high-confidence semantic route
  hits became `source_required` / `reopenable_route`;
  `semantic_evidence_guarded_to_plain_scent_count=0`;
  `paid_semantic_hit_to_source_reopen_rate=1.0`;
  `manual_query_invention_after_paid_semantic_hit_count=0`; evidence false positives 0.
- **run_date:** 2026-06-07
- **source_report:** [`memory-decision-benchmark-plan.md`, live semantic route-actionability
  smoke](benchmarks/design/memory-decision-benchmark-plan.md#track-a-memory-decision-gate)
- **claim_level:** `public_live_semantic_route_smoke`
- **cohort:** Public checked-in testdata converted to clean source; DeepSeek-compatible live semantic path; sanitized aggregate report only.
- **supersedes / superseded_by:** Complements `recall_navigation.progressive_route_follow_through`: live smoke measures
  high-confidence semantic route actionability; deterministic fixture measures source reopen /
  bounded-evidence follow-through.
- **cannot_claim:** Private-registry vague recall quality, all future semantic prompts, broad default foreground
  first/second-turn lift, external baseline comparison, or live bounded-evidence-after-reopen
  rate.

### `continuous_memory.preregistered_repeat_profile_2026_06_08`

- **current_value:** Public-synthetic #378 repeat profile, rerun on 2026-06-09 after the #960 source-miss recovery
  change: 6 cases, 5 deterministic paired repeats per case/arm, 30 case-arm trials, 180 rows,
  `lower_bound_units=-27.7675`, `mean_delta_units=-27.7675`, `lower_bound_passed=false`,
  `primary_endpoint_winner=fresh_context_spec_loop`, and historical `decision_label=no
  demonstrated memory advantage`; `product_change_status=implemented_rerun`,
  `source_miss_recovery_action=ask_light_question`, and `manual_query_invention_expected=false`;
  scope-boundary alias `boundary_confirmed.short_task_complete_spec_synthetic_2026_06_08` means
  no demonstrated net advantage over the modeled fresh-context spec loop.
- **run_date:** 2026-06-09
- **source_report:** [`memory-decision-benchmark-plan.md`, #960 product-remediation
  rerun](benchmarks/design/memory-decision-benchmark-plan.md) and
  [`public-readiness-verification.md`, 2026-06-08 continuous-memory preregistered repeat
  readout](readiness/public-readiness-verification.md#2026-06-08---continuous-memory-preregistered-repeat-readout)
- **claim_level:** `confirmed_scope_boundary_expected_null_with_product_remediation`
- **cohort:** Deterministic public-safe continuous-memory attribution fixtures; short complete-spec boundary
  condition; no live model, no private history, no live host-native telemetry.
- **supersedes / superseded_by:** Supersedes the earlier one-repeat #378 slice only for the lower-bound gate status, and retires
  #960's first source-miss remediation/rerun blocker while preserving the negative/no-advantage
  conclusion and the boundary-oriented reading alias.
- **cannot_claim:** Full #378 continuous-memory superiority, live host-native cost or compaction telemetry, private
  real-history generality, cost-weight robust advantage, answer-generation model quality,
  competitor superiority, calibrated user-visible friction reduction, or a claim that
  source-backed recall has no value outside complete-spec short tasks.

### `continuous_memory.context_loss_public_continuity_2026_06_10`

- **current_value:** Public-safe #1153 context-loss diagnostic slice: 6 selected cases; missing-context success 2/6,
  host-native summary-only 4/6, source-backed AIppocampus route packet 5/6, sham unrelated
  memory 2/6, stale wrong memory 0/6, and oracle full context 6/6. Source-reopen obedience for
  the AIppocampus route packet is 1.0, source-backed hit proxy is 4/6,
  abstention-on-missing-source is 2/6, stale wrong-memory false-positive rate is 1.0, and
  no-remember precision is 1.0.
- **run_date:** 2026-06-10
- **source_report:** [`memory-decision-benchmark-plan.md`, #1153 context-loss
  readout](benchmarks/design/memory-decision-benchmark-plan.md) and `python
  benchmarks\aippocampus\benchmark_continuous_memory_arms.py --json`
- **claim_level:** `preregistered_context_loss_diagnostic_slice`
- **cohort:** Deterministic public-safe synthetic and public VCS-derived context-loss fixtures; separated arms
  and cost/harm/source-reopen/manual-restatement proxy metrics; no raw source text in the
  report.
- **supersedes / superseded_by:** Adds the missing-context slice requested by #1153 while preserving the old complete-spec expected-null row.
- **cannot_claim:** Public-quality continuous-memory advantage, superseding
  `continuous_memory.preregistered_repeat_profile_2026_06_08`, LoCoMo public-dialogue continuity
  quality without a scored prediction run, private real-history generality, live host-native
  behavior, calibrated user-visible restatement burden reduction, answer-generation quality, or
  leaderboard superiority.

### `react_vcs.production_like_source_disambiguation`

- **current_value:** 60/60 gold true positives, `current_source_top_k_hit_rate=1.0`,
  `current_vs_stale_pairwise_win_rate=1.0`, `wrong_source_evidence_rate=0.0`,
  `negative_false_positive_rate=0.0`, and `hard_negative_suppression_rate=1.0` after suppressing
  30/30 explicit-cue lexical near-miss hard negatives.
- **run_date:** 2026-06-09
- **source_report:** [`react-real-vcs-production-like-disambiguation-2026-06-04.md`](benchmarks/reports/public-longitudinal/react-real-vcs-production-like-disambiguation-2026-06-04.md)
- **claim_level:** `production_like_non_oracle_fixture_slice`
- **cohort:** Local React adversarial V2 fixture with sanitized aggregate report; no live provider/model call.
- **supersedes / superseded_by:** Supersedes the 2026-06-04 source-disambiguation row that exposed 30 lexical near-miss false
  positives; does not supersede the 2026-05-31 oracle/bad-control report.
- **cannot_claim:** Broad semantic near-miss understanding, live model quality, wild VCS corpus quality, private
  real-history continuity quality, or license-safe redistribution of the local fixture.

### `track_s.semantic_robustness_public_fixture`

- **current_value:** Public-safe Track S diagnostic: `quality_gate_ok=true` means the narrow deterministic diagnostic
  threshold passed, not public product quality. S1 `decision_stability_rate=1.0`,
  `false_evidence_escalation_count=0`; S2 `top_k_survival_rate=1.0`; S3
  `hard_negative_suppression_rate=1.0`, `explicit_negation_violation_count=0`,
  `stale_as_current_count=0`, `source_evidence_over_escalation_count=0`.
- **run_date:** 2026-06-09
- **source_report:** [`semantic-robustness-track-s.md`](benchmarks/semantic-robustness-track-s.md)
- **claim_level:** `public_safe_deterministic_diagnostic`
- **cohort:** Track S public fixtures over Track A prompt-hook gate behavior and Track B local source-retrieval behavior; no live LLM judge or private text.
- **supersedes / superseded_by:** Supersedes the initial #747 diagnostic reading that exposed explicit-negation and superseded-currentness failures.
- **cannot_claim:** Human-level semantic understanding, Track A/B replacement, public product quality, live
  semantic-model quality, proxy-model truth, broad real-history robustness, or private-history
  recall quality.

### `public_reliability.gauntlet_2026_06_10`

- **current_value:** Public-safe #1102 reliability gauntlet reports three axes separately: runtime stability
  `passed_with_warnings` with LongMemEval-S 500Q runtime `803.10s`, synthetic clean source `4
  GiB`, synthetic segment count `64`, worst-case SQLite handles `192`, planned handles `64`,
  warning count `3`, blocker count `0`, and question-tracking all-pair count `1128`; mis-recall
  quality `diagnostic_passed` with LongMemEval-S session R@10 `479/500 = 0.9580`, exact
  evidence-line R@10 `408/479 = 0.8518`, context-visible evidence R@10 `452/479 = 0.9436`,
  hard-negative suppression `1.0`, explicit-negation violations `0`, and source-evidence
  over-escalations `0`; pollution hygiene `fixture_gates_passed` with knowledge-pollution rates
  `0.0` and auto-hook durable-write / bounded-evidence / source-backed-fact / recalled-echo /
  empty-message counts all `0`.
- **run_date:** 2026-06-10
- **source_report:** [`public-reliability-gauntlet.md`](benchmarks/public-reliability-gauntlet.md) and
  [`public-reliability-gauntlet-2026-06-10.json`](benchmarks/reports/public-reliability/public-reliability-gauntlet-2026-06-10.json)
- **claim_level:** `public_safe_aggregate_gate`
- **cohort:** Public aggregate runner over existing public-safe LongMemEval, synthetic scale/fanout,
  question-tracking, Track S, knowledge-pollution, and auto-hook pollution surfaces; no private
  text, raw LongMemEval text, local paths, external-model payloads, or single aggregate score.
- **supersedes / superseded_by:** Adds the #1102 aggregate gate without superseding the individual LongMemEval, Track S,
  knowledge-pollution, or scale-smoke evidence owners.
- **cannot_claim:** LongMemEval QA score, answer-generation quality, SOTA, real GB/TB runtime, private-history
  quality, exact-line citation quality being solved, live hook write-path quality, competitor
  superiority, or a single aggregate reliability score.

### `attention_router.contract_fixture_2026_06_10`

- **current_value:** Public-safe deterministic attention-router contract fixture: 6 cases; privacy-domain hard mask
  blocks lexical/semantic high-score candidate with `output_mode=silence`,
  `claim_permission=blocked`, and `emitted=false`; source-backed candidate emits
  `reopenable_route` with `no_claim_before_reopen`; valid bounded summary emits
  `bounded_summary_as_route` with `direction_only` grammar and `no_claim_before_reopen`; stale /
  weak summary falls back to `direction_only`; source-open bounded candidate emits
  `bounded_evidence`; source-thin candidate emits `direction_only`;
  `masked_source_resurrection_count=0`; `source_backed_claim_without_reopen=0`;
  `summary_claim_ready_without_reopen_count=0`; raw source text, summary text, and private
  sentinels are not serialized.
- **run_date:** 2026-06-10
- **source_report:** [`source-backed-attention-router.md`](../architecture/recall/source-backed-attention-router.md)
  and `python -m pytest tests\aippocampus\test_attention_router_contract.py -q`
- **claim_level:** `public_safe_contract_fixture`
- **cohort:** Selected public-safe contract cases for #1107/#1116 over hard-mask gating, route packet values,
  summary-as-route boundaries, output modes, and claim permissions; no private text, live model,
  or default foreground routing.
- **supersedes / superseded_by:** Establishes the boundary contract needed before #1113/#1108 token/router implementation and
  documents the #1115 cold-sidecar familiarity boundary.
- **cannot_claim:** Broad attention-router quality, private-history behavior quality, model training or learned
  attention, score-fusion calibration, bounded summaries as source truth, route packet as source
  truth, or default foreground router adoption.

### `attention_router.route_token_fixture_2026_06_10`

- **current_value:** Public-safe deterministic #1113 route-token fixture: 1 long event token, 1 tight source-span
  token, and 1 episode/question token; the span preserves char range `[128, 220]` and line range
  `[45, 53]`; event/span/episode tokens preserve reopen handles; route metadata slots include
  salience, currentness, privacy, and conflict; episode/question token uses `direction_only` and
  `no_claim_before_reopen`; `token_claim_ready_without_reopen_count=0`; raw span text and
  private sentinels are not serialized.
- **run_date:** 2026-06-10
- **source_report:** [`source-backed-attention-router.md`](../architecture/recall/source-backed-attention-router.md)
  and `python -m pytest tests\aippocampus\test_attention_route_tokens.py -q`
- **claim_level:** `public_safe_token_projection_fixture`
- **cohort:** Selected public-safe token projection cases for #1113 over span/event/episode hierarchy, source
  handle preservation, metadata slots, and navigation-only episode grouping; no private text,
  live model, or router scoring.
- **supersedes / superseded_by:** Supplies the route-token input shape needed before #1108 deterministic hot-router scoring.
- **cannot_claim:** Hot attention-router quality, score fusion quality, learned attention, private-history token
  quality, source truth without reopen, default foreground adoption, or broad episode/question
  grouping quality.

### `attention_router.hot_router_fixture_2026_06_10`

- **current_value:** Public-safe deterministic #1108 hot-router fixture: 4 route-token cases; privacy-domain hard
  mask blocks a high-scoring private route with `output_mode=silence`; positive source-span
  route emits `reopenable_route`; stale/conflict route emits `reopenable_route` with
  `stale_or_conflicted_source_reopen`; weak abstention case emits `direction_only`; per-head
  diagnostics include lexical, semantic, action, evidence-packaging, scope, salience,
  currentness, conflict, risk, and abstention heads where present;
  `score_policy=calibrated_rule_grid_v1`; adaptive threshold rises for stale/conflict routes;
  `masked_high_score_emission_count=0`; `claim_ready_without_source_open_count=0`.
- **run_date:** 2026-06-10
- **source_report:** [`source-backed-attention-router.md`](../architecture/recall/source-backed-attention-router.md)
  and `python -m unittest tests.aippocampus.test_attention_hot_router -v`
- **claim_level:** `public_safe_deterministic_router_fixture`
- **cohort:** Selected public-safe V0 router cases for #1108/#1230 over hard masks, head diagnostics,
  calibrated deterministic score policy, adaptive thresholding, positive/stale/abstention
  routing, and claim boundaries; no private text, live model, action-time tool integration, hook
  mutation, or default foreground-hook enablement.
- **supersedes / superseded_by:** Uses #1113 route tokens as router input and now consumes the adopted `calibrated_rule_grid_v1`
  score policy without replacing existing recall/search paths.
- **cannot_claim:** Learned attention quality, production score-fusion calibration, private-history router quality,
  live foreground usefulness, action-time tool routing, broad route precision, or default
  foreground-hook adoption.

### `attention_router.action_head_fixture_2026_06_10`

- **current_value:** Public-safe deterministic #1109 action-head fixture: synthetic pending action payload extracts
  normalized tool/path/issue/command/test features without raw tool args; `action_head` lifts
  the path/issue matched route when prompt-only lexical score is weak; privacy-domain hard mask
  still blocks a high action-score private route; repeated-hint anti-nag suppression downshifts
  an action-matched route to `direction_only`; `action_cue_lift_over_prompt_only_count=1`;
  `anti_nag_suppressed_count=1`; `masked_action_match_emission_count=0`; raw command/tool-arg
  sentinel is not serialized.
- **run_date:** 2026-06-10
- **source_report:** [`source-backed-attention-router.md`](../architecture/recall/source-backed-attention-router.md)
  and `python -m pytest tests\aippocampus\test_attention_hot_router.py -q`
- **claim_level:** `public_safe_action_query_fixture`
- **cohort:** Selected public-safe action-time payload cases for #1109 over pending path/issue/test cues,
  action-head reason codes, prompt-only weakness, privacy masks, and anti-nag suppression; no
  private tool args, live hook mutation, E2E50 behavior test, or default foreground routing.
- **supersedes / superseded_by:** Adds pending-action query features to the V0 router without changing hook settings or live behavior.
- **cannot_claim:** Live host behavior lift, private tool-argument quality, E2E50 or real-agent action utility,
  default foreground action routing, or broad route precision.

### `action_hints.pretool_replay_2026_06_15`

- **current_value:** Public-safe #435/#1608-#1610 action-time hint slice:
  `aippocampus_runtime.hooks.action_hint_cache` materializes compact prepared records from AAR
  v2, learning-loop guidance, active recall locks, and attention route tokens;
  `aippocampus_runtime.hooks.action_hint` accepts Codex-style `PreToolUse` envelopes and emits
  at most one `navigation_only` / `no_claim_before_reopen` hint; installer/status support is
  scoped to Codex `hooks.json` `PreToolUse`; replay telemetry covers 4 positive cases and 6
  negative controls with source-truth overclaim, raw leak, command rewrite, and
  permission-system red lines all 0.
- **run_date:** 2026-06-15
- **source_report:** [`action-time-hints.md`](../architecture/coordination/action-time-hints.md), `python -m unittest
  tests.aippocampus.test_action_hint_cache tests.aippocampus.test_action_hint_hook
  tests.aippocampus.test_action_hint_replay tests.aippocampus.test_install_action_hint_hook -v`,
  and `python -m aippocampus_runtime.hooks.action_hint_replay --json`
- **claim_level:** `public_safe_pretool_replay_fixture`
- **cohort:** Public synthetic/replay fixture and local hook-config tests only; no private history, live host
  firing, raw tool args, raw command text, raw source snippets, local paths, model calls,
  command rewriting, or permission enforcement.
- **supersedes / superseded_by:** Moves #435 from scattered fixtures into a real prepared-cache plus hot `PreToolUse` reader while
  keeping upstream provider work and live promotion separate.
- **cannot_claim:** Causal real-user lift, live/default foreground adoption, private-history usefulness, every host
  supporting `PreToolUse`, source truth from hints, command safety enforcement, or broad
  action-time route quality.

### `learning_loop.replay_companion_2026_06_15`

- **current_value:** Source-backed learning loop closeout for #1593-#1612: scrubbed behavior events become review
  signals, recurring/workflow findings, action-time guidance, source-backed lesson candidates,
  and Active Path Packet routes; `private_replay` provides a local private-history harness with
  aggregate metrics including `repeated_failure_detection_recall`,
  `workflow_order_detection_count`, `context_reopen_before_action_rate`,
  `false_positive_nudge_rate`, and `raw_private_text_leak_count`; the public companion eval
  reuses public longitudinal rollout behavior events and VCS future events, surfaces VCS
  future-event cues before later flag-worthy events, and reports negative no-lesson paths plus
  source-shape gaps.
- **run_date:** 2026-06-15
- **source_report:** [`source-backed-learning-loop.md`](../architecture/coordination/source-backed-learning-loop.md),
  `python3 -m unittest tests.aippocampus.test_learning_loop
  tests.aippocampus.test_learning_loop_private_replay
  tests.aippocampus.test_benchmark_learning_loop_public_companion -v`, `python3 -m
  aippocampus_runtime.learning_loop.private_replay --json`, and `python3
  benchmarks/aippocampus/benchmark_learning_loop_public_companion.py --json`
- **claim_level:** `source_backed_learning_loop_replay_fixture`
- **cohort:** Public committed outputs are aggregate/redacted; private dogfood input is a local sanitized
  behavior-event export, not raw rollout text; public companion uses checked-in public fixtures
  without raw text, local paths, private history, or official STATE-Bench held-out execution.
- **supersedes / superseded_by:** Gives the learning loop both a local dogfood harness and a public reproducible companion instead
  of letting private history be the only proof path.
- **cannot_claim:** Causal live behavior lift, broad private-history generality, official STATE-Bench score or
  held-out lift, model self-improvement, guidance as source truth, or product-quality default
  adoption.

### `learning_loop.source_shape_aippo_feedback_2026_06_15`

- **current_value:** Public-safe #1613-#1619 fixture closeout: eligible learning-loop findings can seed low-authority
  AIppo clauses, prepared action-time cache rows, source-shape projections, navigation-potential
  transition diagnostics, topology pattern-completion candidates, local/global obstruction
  localization, clause lifecycle probes, prerequisite/conflict decisions, freshness decay,
  circuit feedback plans, microcircuit prune diagnostics, semantic-subregion budget decisions,
  and controlled salience decay. Negative controls suppress immature, local-only, stale,
  one-off, missing-source, self-report-only, unsupported, and private-looking rows.
- **run_date:** 2026-06-15
- **source_report:** [`source-backed-learning-loop.md`](../architecture/coordination/source-backed-learning-loop.md),
  [`action-time-hints.md`](../architecture/coordination/action-time-hints.md),
  [`cognitive-runtime-architecture.md`](../architecture/runtime/cognitive-runtime-architecture.md),
  and `python3 -m unittest tests.aippocampus.test_learning_loop_aippo_adapter
  tests.aippocampus.test_aippo_clause_lifecycle tests.aippocampus.test_source_shape_projection
  tests.aippocampus.test_circuit_feedback tests.aippocampus.test_microcircuit_router
  tests.aippocampus.test_semantic_subregion_budget tests.aippocampus.test_action_hint_cache
  tests.aippocampus.test_aippocampus_cli -v`
- **claim_level:** `public_safe_cross_layer_fixture`
- **cohort:** Deterministic public fixtures and sanitized dictionaries only; no private history, raw rollout
  text, raw tool output, full commands, source snippets, local paths, model calls, live hook
  firing, or foreground source truth.
- **supersedes / superseded_by:** Closes the learning-loop-to-AIppo/action-hint bridge and adds route-miss feedback surfaces
  without turning them into a benchmark score or default live adoption claim.
- **cannot_claim:** Causal live behavior lift, broad private-history generality, AIppo marketplace quality, source
  truth from clauses/routes/hints, automatic memory mutation, default foreground hook adoption,
  official STATE-Bench score, or proof that every microcircuit/semantic worker is
  production-calibrated.

### `learning_loop.live_private_replay_and_action_cache_2026_06_15`

- **current_value:** #1622-#1631 closeout slice: source-backed `PostToolUse` failures can create learning activations
  without an existing correction activation id; prepared action-hint cache has an explicit
  refresh/write path and install status reports cache readiness; learning guidance effectiveness
  has an append-only navigation ledger; private replay has an opt-in sanitized export path;
  second-user dogfood cases cover plugin/cache, manual-search, Python/PATH, retirement, and
  current-thread visibility cases; workflow candidates carry transferability labels; learned
  AIppo/source-shape projection preserves scope/topic/environment provenance; foreground action
  cards use a central field budget profile. Follow-up dogfood fixes align MCP semantic
  provider-bridge visibility, AIppo workflow aliases, plugin-cache multi-candidate recovery
  wording, public card metrics, malformed hook fail-open behavior, and explicit route-limit
  validation. A local private-history replay on 2026-06-15 exported 38 sanitized events with
  raw/private/local leak counts at 0 and produced one useful navigation-only
  guidance/effectiveness row.
- **run_date:** 2026-06-15
- **source_report:** [`source-backed-learning-loop.md`](../architecture/coordination/source-backed-learning-loop.md),
  [`action-time-hints.md`](../architecture/coordination/action-time-hints.md),
  [`learning-loop-private-replay-2026-06-15.md`](reports/learning-loop-private-replay-2026-06-15.md),
  and `python3 -m unittest tests.aippocampus.test_correction_reconsolidation
  tests.aippocampus.test_action_hint_cache tests.aippocampus.test_install_action_hint_hook
  tests.aippocampus.test_learning_loop_private_replay
  tests.aippocampus.test_learning_loop_effectiveness_ledger
  tests.aippocampus.test_learning_loop_second_user_dogfood tests.aippocampus.test_learning_loop
  tests.aippocampus.test_consolidation_priority tests.aippocampus.test_circuit_feedback
  tests.aippocampus.test_learning_loop_aippo_adapter
  tests.aippocampus.test_source_shape_projection tests.aippocampus.test_schema_profiles
  tests.aippocampus.test_foreground_action_card tests.aippocampus.test_aippocampus_cli -v`
- **claim_level:** `public_safe_contract_plus_local_private_replay_readout`
- **cohort:** Unit fixtures, public-safe dogfood rows, and one operator-local sanitized private replay
  summary; raw rollout text, commands, stdout/stderr, source snippets, local paths, and
  temporary replay events are not committed.
- **supersedes / superseded_by:** Turns the new learning-loop pieces into real runtime entrypoints rather than fixture-only
  helpers, while preserving navigation-only/source-reopen authority.
- **cannot_claim:** Causal live behavior lift, broad private-history generality, default hook adoption, source truth
  from hints/cards/clauses, official STATE-Bench score, or automatic memory mutation.

### `attention_router.evidence_packaging_fixture_2026_06_10`

- **current_value:** Public-safe deterministic #1110 evidence-packaging fixture: 4 source-window cases preserve
  baseline retrieval metadata; context-visible source-open/current/unconflicted spans can be
  packaged into tighter source-span packets; wrong-source top span is rejected before fallback
  selection; stale spans require currentness checks; conflicted spans include counter-evidence
  handles; `bounded_evidence_packet_count=2`; `wrong_source_span_promoted_count=0`;
  `stale_or_conflicted_claim_ready_count=0`; raw source-window text, raw span text, gold
  answers, and miss taxonomy are not serialized.
- **run_date:** 2026-06-10
- **source_report:** [`source-backed-attention-router.md`](../architecture/recall/source-backed-attention-router.md)
  and `python -m pytest tests\aippocampus\test_attention_evidence_packager.py -q`
- **claim_level:** `public_safe_evidence_packaging_fixture`
- **cohort:** Selected synthetic LongMemEval-style source-window to source-span packaging cases for #1110 over
  baseline preservation, candidate counts, selected span rank, currentness/conflict flags,
  counter-evidence handles, and claim permission; no private text, gold labels, external model,
  or broad benchmark rerun.
- **supersedes / superseded_by:** Adds an optional packaging head between source-window routing and answer-time evidence gates
  without treating reranker or packaging scores as truth.
- **cannot_claim:** LongMemEval QA score, exact-line citation quality being solved, reranker output as source truth,
  private-history packaging quality, default foreground adoption, #1087 closeout, or SOTA
  claims.

### `attention_router.navigation_quality_public_cohort_2026_06_13`

- **current_value:** Public-safe #1111/#1347/#1349 Attention Navigation Quality benchmark: the 12-case contract
  fixture keeps route precision/recall/source-reopen rates at 1.0 with hard red lines 0, and the
  public/holdout cohort covers positive route, hard-mask, stale/currentness, conflict,
  action-time, wrong-source, generic-hint specificity, anti-nag, and multilingual-alias families
  with 30 cases per family and 10 holdout cases per family. The report now separates
  `contract_safety_gate_ok`, `router_design_gate_ok`, `public_quality_gate_ok`, and
  `default_adoption_gate_ok`; legacy `quality_gate_ok` is only a public-quality alias, not a V0
  design verdict.
- **run_date:** 2026-06-13
- **source_report:** [`attention-navigation-quality.md`](benchmarks/reports/recall-navigation/attention-navigation-quality.md)
  and `python -m unittest tests.aippocampus.test_benchmark_attention_navigation_quality -v`
- **claim_level:** `public_safe_navigation_public_cohort_gate`
- **cohort:** Aggregates public-safe synthetic/router fixtures without raw source text, private text, gold
  answers, private history, or answer generation; holdout rows are explicit and tuning leakage
  remains zero.
- **supersedes / superseded_by:** Promotes the router evidence from contract-smoke wording into a narrow public/holdout
  navigation-quality gate for explicit agent pull while keeping hard red lines separate from
  route averages and default-hook adoption.
- **cannot_claim:** Live host behavior lift, private-history router quality, answer-generation quality, every-turn
  recall, default foreground-hook adoption, broad #1188 live route-producer completion, #1185
  default-session usefulness closeout, source truth from attention scores, or broad production
  route precision.

### `attention_router.score_fusion_calibration_2026_06_11`

- **current_value:** Public-safe #1112/#1230 score-fusion calibration/adoption report: exports 12 sanitized feature
  rows from the #1111 fixture; legacy deterministic weights still score
  `route_precision_at_threshold=3/4=0.75`, `route_recall_at_threshold=3/9=0.3333`, and
  `anti_nag_violation_count=1`; `runtime_default_policy=calibrated_rule_grid_v1` matches the
  selected calibrated arm with `route_precision_at_threshold=9/9=1.0`,
  `route_recall_at_threshold=9/9=1.0`, `anti_nag_violation_count=0`, `privacy_bypass_count=0`,
  and `hard_mask_override_count=0`; raw text, private text, raw tool args, and raw source
  handles are not emitted.
- **run_date:** 2026-06-11
- **source_report:** [`attention-score-fusion-calibration.md`](benchmarks/reports/recall-navigation/attention-score-fusion-calibration.md)
  and `python -m unittest tests.aippocampus.test_benchmark_attention_score_fusion_calibration
  tests.aippocampus.test_attention_hot_router
  tests.aippocampus.test_benchmark_attention_navigation_quality -v`
- **claim_level:** `public_safe_hot_router_policy_fixture`
- **cohort:** Sanitized numeric attention feature rows and deterministic hot-router runtime policy adoption
  only; no private-history training, raw text, source contents, hook mutation, or default
  foreground-hook enablement.
- **supersedes / superseded_by:** Promotes the calibrated rule grid into the hot router default route-token score policy while
  preserving hard masks as policy gates and keeping quality promotion separate.
- **cannot_claim:** Default foreground-hook adoption, private-history training quality, answer-generation quality,
  source truth from scores, learnable hard masks, production score-fusion calibration, live host
  behavior lift, or representative public-quality router performance.

### `attention_router.agent_recall_opt_in_sorting_2026_06_12`

- **current_value:** Public-safe #1301/#1188 agent recall sorting slice: `agent_continuity.recall(...,
  attention_router=True)` and `aippocampus agent recall --attention-router` project the existing
  `recall_context` candidate set into attention route tokens, ask the deterministic hot router
  to score them, move only already emitted `reopenable_route` packets forward, preserve all
  original routes in fallback order, and emit `attention_router_navigation` diagnostics plus
  metrics for applied/ranked/top-route-changed/foreground-packet bytes. The projection now also
  reports no-help diagnostics: applied-but-no-help, selected query/route term overlap, explicit
  bridge reason, route-label specificity floor, expected-family match, and whether
  `why_this_may_matter` is specific enough for a fresh agent to choose the first deepen step.
  The fixture keeps `foreground_forbidden_key_count=0`, `source_backed_claim_without_reopen=0`,
  and no source refs, source handles, or head votes in the foreground report.
- **run_date:** 2026-06-12
- **source_report:** [`source-backed-attention-router.md`](../architecture/recall/source-backed-attention-router.md)
  and `python -m unittest tests.aippocampus.test_agent_opt_in_continuity
  tests.aippocampus.test_recall_navigation_comparison -v`
- **claim_level:** `public_safe_opt_in_agent_route_sorting_contract`
- **cohort:** Mocked public-safe route fixtures plus existing recall-navigation comparison fixtures; no
  private history, raw source text, raw source refs in foreground packets, live host calls,
  model calls, hook mutation, or default enablement.
- **supersedes / superseded_by:** Moves Attention Router from report-only diagnostics into an explicit opt-in agent recall
  candidate-ordering path while retaining source reopen, fallback, promotion gates, and no-help
  visibility.
- **cannot_claim:** Default foreground-hook adoption, broad live route-producer quality, private-history router
  quality, source truth from scores, answer-generation quality, closing #1188/#1185, replacing
  the default `recall_context` order, or claiming agent recall quality lift.

### `attention_router.agent_recall_auto_policy_2026_06_13`

- **current_value:** Public-safe #1348/#1350 explicit-pull policy slice: `agent_continuity.recall(...,
  attention_router="auto")` and `aippocampus agent recall --attention-router-mode auto` consult
  the shared recall-navigation promotion harness before enabling attention-router sorting.
  Neutral no-op cases are now reported as ROI signals, not hard blockers; true
  no-help/feature-hurt/red-line controls remain blockers for broader promotion. With the
  public/holdout cohort gate passing for the explicit agent-recall surface, auto mode can enable
  sorting while still preserving fallback ordering and reporting policy metadata.
- **run_date:** 2026-06-13
- **source_report:** `python -m unittest tests.aippocampus.test_agent_opt_in_continuity tests.aippocampus.test_recall_navigation_promotion -v`
- **claim_level:** `public_safe_explicit_pull_auto_policy`
- **cohort:** Public-safe fixture promotion harness only; no private history, live host calls, model calls,
  raw source text, hook mutation, or silent default hook sorting.
- **supersedes / superseded_by:** Lands the narrow explicit-pull auto path requested by #1350 after gate naming, neutral no-op
  handling, and the public/holdout cohort are in place.
- **cannot_claim:** Default hook adoption, every-turn recall, live-host usefulness lift, broad #1188 route-producer
  completion, #1185 natural-handoff/default-session usefulness closeout, private-history
  quality, answer generation, or source truth from attention scores.

### `recall.default_hook_usefulness_2026_06_20`

- **current_value:** Public-safe #1439/#1449 same-budget four-arm benchmark: 11 cases across deictic prompts,
  multilingual prompts, self-referential continuity, explicit-route/hook-skip gap, already-good
  no-op, stale/conflict controls, question resurfacing, theme user-review lift, stale theme
  carryover, cognitive-load drag, and attention-route specificity. Explicit recall helpful
  next-action rate 0.636364, manual-search reduction 11, source-reopen follow-through rate
  0.636364, wrong-route drag 0, and irrelevant-memory drag 0. Default-hook candidate activation
  rate 0.727273, helpful next-action rate 0.272727, manual-search reduction 5, source-reopen
  follow-through rate 0.272727, wrong-route drag rate 0.363636, irrelevant-memory drag rate
  0.272727, latency proxy avg 15.363636, and cost proxy avg 0.727273. Tiny `agent_recall`
  affordance activation/emission rate 0.636364, helpful next-action rate 0.636364, manual-search
  reduction 11, source-reopen follow-through rate 0.636364, wrong-route drag 0,
  irrelevant-memory drag 0, source-truth overclaim 0, and quiet-for-a-reason count 4. The tiny
  affordance now has a host-faithful replay gate with 7 emitted/followed `agent_recall` calls,
  7 recall-after-hint successes, and 0 source-truth, raw-handle, provenance-dump,
  broad-manual-search-before-recall, wrong-route, or irrelevant-memory red lines. Decision:
  keep default hook foreground diagnostic-only; mark `default_hook_tiny_agent_recall_affordance`
  eligible as an action-only runtime-policy candidate, not as foreground context/evidence.
- **run_date:** 2026-06-20
- **source_report:** [`default-hook-recall-usefulness-2026-06-20.md`](benchmarks/reports/recall-navigation/default-hook-recall-usefulness-2026-06-20.md),
  [`default-hook-recall-usefulness-2026-06-20.json`](benchmarks/reports/recall-navigation/default-hook-recall-usefulness-2026-06-20.json),
  and `python -m pytest tests\aippocampus\test_benchmark_default_hook_recall_usefulness.py -q`
- **claim_level:** `public_safe_four_arm_default_hook_usefulness_eval`
- **cohort:** Public synthetic same-budget cohort only; no private history, live hook, model calls, raw
  prompts, raw source text, source refs, thread/message handles, local paths, provider payloads,
  credentials, or source truth from question/theme/load/router rows.
- **supersedes / superseded_by:** Closes #1439 by measuring the default-hook candidate before adoption and addresses #1449 by
  separating the tiny hook-to-agent affordance from broad foreground context injection.
- **cannot_claim:** Live default-hook quality, live tiny-affordance quality, default foreground adoption readiness,
  broad private-history question/theme usefulness, theme rows as source truth, cognitive-load
  default foreground readiness, or source claims from the tiny affordance without
  recall/deepen/source reopen.

### `map_rot.lifecycle_debt_2026_06_10`

- **current_value:** Public-safe #1126 lifecycle-debt benchmark: 9 fixture cases cover stale current-pointer refresh,
  challenged conflict backlog, quarantined masked route, superseded successor route,
  missing-middle pathlet, deleted/no-recall object, dead-lettered cache row, repeated-wrong
  route suppression, and one current reopenable route; `historically_preserved_count=8`;
  `eligible_current_navigation_count=1`; `review_needed_count=2`;
  `prune_or_decay_candidate_count=5`; hard red-line counters are 0;
  `benchmark_maturity_level=contract_smoke`; `contract_gate_ok=true`; `quality_gate_ok=false`;
  sample floor, public/external cohort, and holdout requirements are not met.
- **run_date:** 2026-06-10
- **source_report:** [`map-rot-lifecycle-debt.md`](benchmarks/reports/field-journey/map-rot-lifecycle-debt.md) and
  `python -m pytest tests\aippocampus\test_benchmark_map_rot_lifecycle_debt.py -q`
- **claim_level:** `public_safe_lifecycle_contract_gate`
- **cohort:** Selected public-safe lifecycle-state fixtures without raw source text, private text, local
  paths, or live host behavior; red-line navigation leaks stay separate from backlog/decay
  metrics and quality promotion gates.
- **supersedes / superseded_by:** Provides a deterministic contract guard for stale/challenged/quarantined/superseded/deleted map
  objects before any auto-cleanup or live current-route claim.
- **cannot_claim:** Representative map-rot distribution, automatic semantic cleanup, private-history map-rot
  quality, live current-route quality, all conflicts resolved, or production self-cleaning.

### `agent_continuity.loop_gate_2026_06_11`

- **current_value:** Public-safe #1163/#1181/#1184 integration gate: 8 fixture cases cover positive bounded-summary
  route, positive reopenable source route, two similar packet-triage reopenable routes with
  distinct safe labels, AIppo low-risk workflow guidance, blocked privacy route,
  stale/conflicted reopen route, and anti-nag recently dismissed route;
  `integrated_loop_success_count=8/8`; `deepen_required_follow_through_count=7`;
  `aippo_low_risk_guidance_success_count=1`; `anti_nag_suppressed_count=1`;
  `packet_triage_distinctiveness=1.0`; `blind_deepen_required_count=0`;
  `top_route_selection_hint_present_count=5`; `agent_packet_budget_violation_count=0`;
  `foreground_forbidden_key_count=0`; all red lines are 0;
  `benchmark_maturity_level=contract_smoke`; `contract_gate_ok=true`; `quality_gate_ok=false`;
  sample floor, public/external cohort, and holdout requirements are not met.
- **run_date:** 2026-06-11
- **source_report:** [`agent-continuity-loop.md`](benchmarks/reports/recall-navigation/agent-continuity-loop.md) and
  `python -m pytest tests\aippocampus\test_benchmark_agent_continuity_loop.py -q`
- **claim_level:** `public_safe_integration_contract_gate`
- **cohort:** `supports`: checked-in public-safe fixtures compose semantic warming, hot router, facade/deepen,
  AIppo, source-reopen budget, and foreground budget; similar reopenable routes now carry
  distinct safe triage hints instead of forcing blind deepen.
- **supersedes / superseded_by:** `material_limits`: no private history, live host, external model call, raw source text,
  answer-generation quality, or opt-in/default foreground adoption claim; red-line composition
  checks remain separate from quality promotion gates.
- **cannot_claim:** Live host behavior lift, private-history quality, answer-generation quality, default foreground adoption, or production readiness.

### `agent_continuity.foreground_usefulness_contract_2026_06_11`

- **current_value:** Public-safe foreground usefulness and candidate-survival contract: continuity usefulness
  separates safety, usefulness, and attention cost; the audit matrix covers hook, active-recall,
  AIppo, router, bounded-summary, and macro surfaces; candidate survival tracks dropped/parked
  later-useful candidates, direction-only false positives/negatives, silent nudge drift,
  suppressed useful candidates, and emergent-bridge preservation.
- **run_date:** 2026-06-11
- **source_report:** [`foreground-memory-ux-budget.md`](../architecture/recall/foreground-memory-ux-budget.md) and
  `python -m unittest tests.aippocampus.test_foreground_usefulness_and_candidate_survival -v`
- **claim_level:** `public_safe_foreground_usefulness_contract`
- **cohort:** Selected public-safe fixtures for #1185/#1248/#1250 over useful packet rate, route
  actionability, packet distinctiveness, protocol-noise ratio, attention saved/spent proxy,
  overreach, overfiltering, and candidate false negatives; no private text, live host, default
  hook adoption, or external model calls.
- **supersedes / superseded_by:** Adds agency/usability gates so safe-but-useless packets and over-conservative filtering are visible before quality promotion.
- **cannot_claim:** Broad foreground usefulness, private-history candidate quality, live annoyance/lift, default
  foreground adoption, or answer-generation quality.

### `aippo.feedback_eval_ficus_contract_2026_06_13`

- **current_value:** Public-safe AIppo feedback/eval/Ficus contract: feedback rows are grouped into
  reripening/degrade/review signals without mutating source truth; the eval-environment fixture
  has five runnable instances, fixed scorer metadata, rejected trivial/impossible/novelty cases,
  and rendered baseline-vs-AIppo prompts; the Ficus MVP carries source authority classes, hard
  masks, compact activation, and deepen output for selected low-risk impressions. The
  working-contract fixture now also reports a Dream-candidate readout: Dream-synthesized
  candidates may be nominated backstage, but only source-supported candidates ripen into
  foreground-eligible AIppo guidance, and repeated wrong routes stay prevented.
- **run_date:** 2026-06-13
- **source_report:** [`personamem-readiness.md`](benchmarks/personamem-readiness.md) and `python -m unittest
  tests.aippocampus.test_aippo_feedback_eval_ficus tests.aippocampus.test_aippo_working_contract
  -v`
- **claim_level:** `public_safe_aippo_ficus_contract`
- **cohort:** Selected public-safe fixtures for #1189/#1254/#1256 plus a small Dream/AIppo bridge slice for
  #163/#248/#575/#576/#663; no private history, live model, raw source text, user-profile truth,
  dream-only foreground leakage, or automatic self-improvement.
- **supersedes / superseded_by:** Establishes a usable contract slice for AIppo feedback loops, AIppo-vs-baseline evaluation
  shape, first Ficus MVP, and source-supported ripening of Dream/subconscious candidates before
  PersonaMem-style benchmark work.
- **cannot_claim:** Autonomous AIppo self-improvement, PersonaMem score, broad personalization quality, private
  Ficus quality, live Dream quality, question-tracking quality, cognitive-load/Observatory
  product quality, marketplace readiness, production default profile use, or source truth from
  Dream-only candidates.

### `aippo.skill_bridge_seed_contract_2026_06_11`

- **current_value:** Public-safe Skill-to-AIppo bridge contract: a `SKILL.md` can be imported as a compact
  `candidate_aippo_seed` with trigger, workflow, command, boundary, and output-expectation
  clauses; every clause keeps `authority=skill_declared_instruction` and
  `support_status=declared_not_observed`; commands/references stay in deepen output; over-broad
  or sensitive instructions are suppressed before foreground activation.
- **run_date:** 2026-06-11
- **source_report:** [`agent-native-recall-facade.md`](../architecture/recall/agent-native-recall-facade.md) and
  `python -m unittest tests.aippocampus.test_aippo_skill_bridge -v`
- **claim_level:** `public_safe_skill_seed_contract`
- **cohort:** Selected public-safe parser fixtures over the repository's own `skills/aippocampus/SKILL.md` and
  an over-broad synthetic skill; no private skill imports, raw skill dump foregrounding,
  marketplace import, live model, or observed-usefulness claim.
- **supersedes / superseded_by:** Gives existing skills a migration/coexistence path into lower-authority AIppo seeds while
  preserving #1254 feedback and #1256 eval-environment promotion boundaries.
- **cannot_claim:** Automatic conversion of arbitrary skills into ripe AIppos, proof that a skill is useful, skill
  marketplace readiness, private skill generalization, or eval environments as a default cost
  for every skill.

### `aippo.skill_observed_use_ripening_contract_2026_06_12`

- **current_value:** Public-safe Skill-to-AIppo observed-use ripening contract: selected clauses from the
  repository's `skills/aippocampus/SKILL.md` can move from `declared_not_observed` seed guidance
  into a partial `aippo_working_contract` only when source-backed observed-use feedback also
  supports them; self-report-only corrections, command clauses, and unsupported declared
  guidance remain candidate-only or challenged.
- **run_date:** 2026-06-12
- **source_report:** [`agent-native-recall-facade.md`](../architecture/recall/agent-native-recall-facade.md) and
  `python -m unittest tests.aippocampus.test_aippo_skill_bridge -v`
- **claim_level:** `public_safe_skill_observed_use_contract`
- **cohort:** Selected public-safe fixture over the repository skill seed plus synthetic observed-use feedback
  rows; activation packet size, next-action clarity, avoided unnecessary deepen, source-backed
  clause count, and candidate-only clause count are reported; source support rows and
  command/reference details stay behind deepen/explain.
- **supersedes / superseded_by:** Closes the first #1289 ripening path by connecting #1254 feedback rows and #1256 eval candidacy
  without making expensive evals a default import cost.
- **cannot_claim:** Broad skill migration quality, automatic skill-to-ripe-AIppo conversion, proof that arbitrary
  skill text is useful, private skill generalization, marketplace readiness, live model quality,
  or source truth without deepen/source reopen.

### `state_bench.agent_learning_defer_2026_06_14`

- **current_value:** STATE-Bench Agent Learning official path rechecked against `microsoft/STATE-Bench` main
  `a0ffc655e7a36c179bfd2b037a08b0f3d75c9431`; official docs still require train-only learning
  extraction, `--num-runs 5`, `--retrieve-learnings-top-k 3`, and the locked GPT-5.4 evaluation
  client. The local environment has neither `STATE_BENCH_EVAL_ENDPOINT` nor
  `STATE_BENCH_EVAL_DEPLOYMENTS`, so `official_task_run_count=0` remains the honest state.
- **run_date:** 2026-06-14
- **source_report:** [`state-bench-agent-learning-decision-2026-06-14.md`](benchmarks/reports/state-bench/state-bench-agent-learning-decision-2026-06-14.md),
  [`state-bench-agent-learning.md`](benchmarks/state-bench-agent-learning.md), and `git
  ls-remote https://github.com/microsoft/STATE-Bench.git refs/heads/main`
- **claim_level:** `external_dependency_defer_decision`
- **cohort:** Public official-source/env-readiness recheck; no private history, no provider credentials
  emitted, no raw train trajectories, no official task run, and no score.
- **supersedes / superseded_by:** Closes #1379 by recording the access blocker, closes #1381 by recording a defer decision, and
  makes #1043 closeable as currently not feasible from this environment.
- **cannot_claim:** Official STATE-Bench score, Agent Learning lift, matched one-domain task quality, leaderboard
  readiness, STATE-Bench SOTA, or external memory-system superiority.

### `benchmark.provider_execution_budget_adoption_2026_06_11`

- **current_value:** Public-safe #1229 provider-execution budget adoption: LongMemEval fixed-reader answer and LoCoMo
  text-QA provider modes fail before reader calls when shared provider budget fields are
  missing, then report successful budget summaries when max calls, token/cost budget,
  checkpoint, and partial-output paths are declared; AMemGym official `openrouter` surface
  execution is blocked before subprocess start without budget; LongMemEval-V2 official pilot
  reports `no_provider_budget_required` because it is a decision report and does not execute the
  official reader.
- **run_date:** 2026-06-11
- **source_report:** `python -m unittest tests.aippocampus.test_benchmark_longmemeval_answer
  tests.aippocampus.test_benchmark_locomo_qa tests.aippocampus.test_benchmark_amemgym_official
  tests.aippocampus.test_benchmark_longmemeval_v2_official_pilot -v`
- **claim_level:** `public_safe_provider_budget_contract`
- **cohort:** Selected public-safe fixtures over active provider-backed benchmark runners; no live provider
  calls, no private history, no raw benchmark text in reports, no official harness execution,
  and no provider credentials emitted.
- **supersedes / superseded_by:** Extends the #1198 shared helper beyond the first LongMemEval semantic-reranker path and makes
  provider budgets reusable before #1194/#1232/#1043-style live benchmark work.
- **cannot_claim:** Actual provider cost, actual cache hit rate, official benchmark score, live model quality,
  STATE-Bench official run readiness, or complete external-harness provider usage extraction.

### `update.plugin_cache_agent_callable_readiness_2026_06_12`

- **current_value:** #1307 local update readiness contract: `aippocampus update status` distinguishes repo plugin
  source version, staged package version, explicit local marketplace copy, explicit or
  auto-detected Codex installed cache, and foreground host exposure; stale marketplace/cache
  layers report recommended repair actions, while successful host probe reports can set
  `agent_callable_status=host_live_probe_ok`. `aippocampus update apply --surface plugin`
  rebuilds the staged package and refreshes marketplace/installed cache layers only when the
  operator supplies `--plugin-marketplace-dir` or `--plugin-installed-dir`; installed cache
  refresh preserves portable existing `.mcp.json` instead of treating host MCP launch config as
  package drift.
- **run_date:** 2026-06-12
- **source_report:** `python -m unittest tests.aippocampus.test_update_sync -v`, `python -m unittest
  tests.aippocampus.test_plugin_distribution -v`, `python
  plugins\aippocampus\smoke_plugin_install.py --repo-root . --json`, and [`install-guide.md`,
  Updating AIppocampus](../guides/install-guide.md#updating-aippocampus)
- **claim_level:** `public_safe_local_update_readiness_contract`
- **cohort:** Public-safe temp-directory fixtures plus package-level plugin smoke; no private history, real
  user memory, API-key values, raw host logs, or persistent Codex plugin-cache writes are
  committed.
- **supersedes / superseded_by:** Completes the #1307 local repair path after the first agent-callable status split: package
  freshness, marketplace/cache freshness, and host tool exposure are visible and separately
  repairable.
- **cannot_claim:** Public marketplace submission, every Codex UI wrapper, third-party fresh-clone review,
  persistent live Codex install state, actual foreground recall quality, or host tool exposure
  without a host probe/report.

### `update.codex_plugin_one_command_install_2026_06_13`

- **current_value:** #1335/#1345 local Codex plugin installer: `aippocampus plugin install --codex --verify` builds
  the repo-local plugin package, refreshes the AIppocampus-owned local marketplace, refreshes
  the current Codex Desktop versioned installed cache for `aippocampus@aippocampus-local`, asks
  the Codex app-server to reload MCP servers, calls `sync_status`, and reports
  `agent_callable_status=host_live_probe_ok` when the host probe passes. Existing local
  marketplace registration and non-Git marketplace upgrade errors are treated as compatible
  local-marketplace states, not install failures. `aippocampus plugin uninstall --codex`
  unregisters the local marketplace and deletes only AIppocampus-owned marketplace/cache
  artifacts.
- **run_date:** 2026-06-13
- **source_report:** `python -m unittest tests.aippocampus.test_aippocampus_cli tests.aippocampus.test_update_sync
  tests.aippocampus.test_plugin_distribution tests.aippocampus.test_plugin_installer -v`,
  `python -m aippocampus_runtime.cli.facade plugin install --codex --verify --json`,
  `$env:PYTHONPATH='skills/aippocampus/scripts'; python -m
  aippocampus_runtime.update.plugin_installer install --codex --verify --json`, and
  [`install-guide.md`, Updating AIppocampus](../guides/install-guide.md#updating-aippocampus)
- **claim_level:** `public_safe_local_codex_plugin_install_contract`
- **cohort:** Public-safe unit fixtures for first install, rerun/current, existing-marketplace compatibility,
  Windows launcher resolution, and rollback, plus one maintainer local Codex Desktop 0.130.0
  app-server probe with stderr local paths redacted; no private memory data, raw user prompts,
  key values, hook enablement, or public marketplace writes are committed.
- **supersedes / superseded_by:** Converts the manual build/marketplace/cache-refresh/reload/probe sequence into one reversible
  local command while preserving the distinction between package freshness, host exposure,
  hooks, and provider-key setup.
- **cannot_claim:** Public marketplace submission, third-party fresh-clone install review, every Codex Desktop/CLI
  version, non-Codex plugin hosts, plugin install without a source checkout, actual foreground
  recall quality, hosted API behavior, or provider-key/hook setup.

### `avatar.bounded_resonance_proxy_pilot_2026_06_12`

- **current_value:** Public-safe #1319 bounded-resonance avatar-posture proxy pilot: 12 fixtures across
  closeout/broad-issue risk, repeated debug dead-end, and structural-break families are
  evaluated across arms A explicit instruction, B neutral posture, C archetype alias only, D
  bounded resonance, and E random symbolic control; `case_arm_count=60`; D is the best
  deterministic proxy arm with `average_helpfulness_score=5.666667`,
  `completion_success_rate=1.0`, `manual_search_count=0`, and candidate red lines 0; standalone
  C has `off_topic_archetype_expansion_count=12`, making alias-only drift visible.
- **run_date:** 2026-06-12
- **source_report:** [`avatar-bounded-resonance-pilot-2026-06-12.md`](../archive/research/avatar-bounded-resonance/avatar-bounded-resonance-pilot-2026-06-12.md)
  and `python -m unittest tests.aippocampus.test_benchmark_avatar_bounded_resonance -v`
- **claim_level:** `exploratory_public_safe_deterministic_proxy`
- **cohort:** Public-safe fixture text and scripted proxy scoring only; no private history, raw provider
  payloads, live model calls, local paths, credentials, runtime hooks, or default foreground
  avatar packets.
- **supersedes / superseded_by:** Closes the #1319 harness/report slice and recommends a model-backed public-safe repeat before
  any runtime avatar/posture proposal.
- **cannot_claim:** Bounded resonance improves production agent behavior, live LLM or host behavior lift, default
  foreground avatar runtime readiness, private-history avatar quality, archetype/resonance as
  authority, source truth from posture/resonance, or broad avatar/persona quality.

### `avatar.bounded_resonance_live_model_pilot_2026_06_13`

- **current_value:** Public-safe #1321 live-model repeat of the bounded-resonance avatar-posture pilot: 12 public
  fixture cases across arms A-E produced 60 DeepSeek V4-Flash calls; hard red-line count stayed
  0, but the bounded-resonance arm did not beat neutral or alias-only arms (`D
  average_helpfulness_score=2.375`, `B=2.833333`, `C=2.979167`) and the quality gate remains
  false. Temperature was not sent (`temperature_requested=null`, `temperature_sent=false`)
  because the run used provider/default thinking with reasoning effort `high`.
- **run_date:** 2026-06-13
- **source_report:** [`avatar-bounded-resonance-live-model-2026-06-13.md`](../archive/research/avatar-bounded-resonance/avatar-bounded-resonance-live-model-2026-06-13.md),
  [`avatar-bounded-resonance-live-model-2026-06-13.json`](../archive/research/avatar-bounded-resonance/avatar-bounded-resonance-live-model-2026-06-13.json),
  and `python -m unittest tests.aippocampus.test_benchmark_avatar_bounded_resonance
  tests.aippocampus.test_model_client -v`
- **claim_level:** `exploratory_public_safe_live_model_negative_result`
- **cohort:** Public-safe checked-in fixture prompts, sanitized model excerpts, aggregate usage/cost
  estimates, and no raw provider payloads, private history, local paths, credentials, runtime
  hooks, or default foreground avatar packets.
- **supersedes / superseded_by:** Closes the #1321 model-backed pilot slice by recording a negative/mixed result instead of
  promoting bounded resonance from the deterministic proxy.
- **cannot_claim:** Bounded resonance improves production agent behavior, default foreground avatar runtime
  readiness, broad avatar/persona quality, private-history avatar quality, provider-general
  behavior, or source truth from posture/resonance.

### `agent_continuity.opt_in_cli_path_2026_06_10`

- **current_value:** Opt-in runtime path: `aippocampus agent recall` returns compact `MemoryPacket` rows plus
  separate opaque deepen handles; `agent aippo` returns the project/workflow activation packet;
  `agent deepen` and `agent explain` work for both recall handles and `deepen:aippo...`;
  stale/malformed handles return `cannot_verify`; `agent feedback` returns or appends
  low-authority feedback receipts without changing source truth.
- **run_date:** 2026-06-10
- **source_report:** `python -m unittest tests.aippocampus.test_agent_opt_in_continuity tests.aippocampus.test_aippocampus_cli -v`
- **claim_level:** `opt_in_agent_runtime_contract`
- **cohort:** Public-safe CLI/runtime adapter over existing recall navigation, agent facade projection, AIppo
  working contract, and feedback-event contract; no private history, live host, raw source text
  in foreground packets, default hook mutation, or MCP write expansion.
- **supersedes / superseded_by:** Closes the practical #1162 wiring gap after #1129/#1130/#1131/#1163 established the packet
  grammar and fixture composition gate.
- **cannot_claim:** Default foreground adoption, every-turn recall, public SDK stability, hosted API behavior, broad
  private-history quality, answer-generation quality, AIppo marketplace readiness, or feedback
  as source truth.

### `hippocampal.d5_d6_public_synthetic_gate_2026_06_09`

- **current_value:** Public-safe D5/D6 gated diagnostic over the `full_query` arm: 16 fixture cases total; D5 3/3 and
  D6 3/3 cases pass; combined D5/D6 accuracy 1.000; source reopen count 4/6; source reopen rate
  0.666667; wrong-source / wrong-twin count 0; source-reopen failure count 0; confabulation
  count 0; gate status `gated_diagnostic_passed`.
- **run_date:** 2026-06-09
- **source_report:** [`hippocampal-recall-fixture-report.md`, 2026-06-09 D5/D6
  gate](benchmarks/reports/hippocampal/hippocampal-recall-fixture-report.md#2026-06-09-d5d6-gate)
- **claim_level:** `public_synthetic_gated_diagnostic`
- **cohort:** Public synthetic H1/H2 fixture seed v2; D5 structure-only cues and D6 time-window cues; deterministic `full_query` diagnostic arm only.
- **supersedes / superseded_by:** Supersedes the older 12-case D5/D6 readout for current D5/D6 sample size and `full_query` gate
  state only; the 2026-06-04 cross-system table remains historical for baseline arms, H5
  controls, and external-adapter availability.
- **cannot_claim:** Full D5/D6 recall quality, full 50-scene / 350-case P1 quality, real-history H1/H2 quality, live
  semantic-retriever quality, cross-system superiority, or publication-grade confidence
  intervals.

### `hippocampal.hard_negative_public_synthetic_slice_2026_06_09`

- **current_value:** Public-safe hard-negative production-like slice: 12 cases, 3 per family; 12 guarded production
  outputs; major failure count 0; wrong-source evidence 0; stale-as-current 0;
  unsupported-as-fact 0; confabulation 0; honest scent / skip 4; evidence source-reopen count 8;
  evidence source-reopen rate 1.000. Contract controls separately score 16 examples with all
  seven outcome categories exercised.
- **run_date:** 2026-06-09
- **source_report:** [`hippocampal-hard-negative-fixture-report.md`, 2026-06-09 production-like
  slice](benchmarks/reports/hippocampal/hippocampal-hard-negative-fixture-report.md#2026-06-09-production-like-slice)
- **claim_level:** `public_production_like_synthetic_diagnostic`
- **cohort:** Public synthetic hard-negative fixture; near-neighbor, said-but-unsupported,
  superseded-currentness, and surface-paraphrase families; no live model and no private history.
- **supersedes / superseded_by:** Supersedes the original 4-case hard-negative contract smoke for current public synthetic
  family/sample coverage; contract controls remain the scorer taxonomy owner.
- **cannot_claim:** Real-history H1/H2 recall-discrimination quality, live model or semantic-retriever quality, full
  hippocampal P1 matrix, broad production reliability, or cross-system benchmark superiority.

### `hippocampal.hard_negative_public_dialogue_cohort_2026_06_09`

- **current_value:** LoCoMo-derived public-dialogue hard-negative cohort mode: 12 source-id cases from 1 public
  sample; near-neighbor 4, said-but-unsupported 4, surface-paraphrase 4, superseded-currentness
  0 and reported unsupported; major failure count 0; wrong-source evidence 0;
  unsupported-as-fact 0; evidence source-reopen rate 1.000.
- **run_date:** 2026-06-09
- **source_report:** [`hippocampal-hard-negative-fixture-report.md`, 2026-06-09 public-dialogue-derived
  cohort](benchmarks/reports/hippocampal/hippocampal-hard-negative-fixture-report.md#2026-06-09-public-dialogue-derived-cohort)
- **claim_level:** `public_dialogue_derived_hard_negative_cohort`
- **cohort:** Ignored / external LoCoMo file, public QA evidence ids, sanitized report with query hashes and
  source-ref hashes only; no private history and no raw public dialogue text in default output.
- **supersedes / superseded_by:** Adds the public-dialogue-derived cohort path requested after the synthetic #244/#1041 slice;
  keeps synthetic and public metrics separate and reports unsupported families instead of
  forcing weak labels.
- **cannot_claim:** Live retrieval/model quality, private real-history H1/H2 quality, full P1 matrix,
  cross-conversation/life-wide continuity quality, or public currentness/supersession quality
  for LoCoMo families without explicit correction/update labels.

### `dream.private_large_history_diagnostic`

- **current_value:** Selected private ready-pack Dream eval: 18 packs; model-backed run with provider/default
  thinking and no explicit max-token cap produced source-thread coverage delta 1.6111,
  structural reflection-ready delta 616, bridge-claim coverage delta 1.0; historical shadow
  replay had 0 delivered events, 1 dream eligible exposure, and 1 attributed reminder; E2E50
  scan found 17/20 requested candidate seeds and local annotation retained 4 gold-seed plus 2
  calibration candidates; agency host-timing replay passed 5 deterministic cases; coding
  decision-shadow Tracks A-E passed; invalid `--semantic-workers default` run had 15 semantic
  calls but 0 available workers before the worker-validation fix.
- **run_date:** 2026-06-04
- **source_report:** [`dream-private-large-history-diagnostic-2026-06-04.md`](dream/dream-private-large-history-diagnostic-2026-06-04.md)
- **claim_level:** `selected_private_history_offline_diagnostic`
- **cohort:** Local sanitized aggregate private-history diagnostic for #158/#164; no private text, raw source
  refs, thread ids, message ids, or absolute paths checked in.
- **supersedes / superseded_by:** Updates the 2026-05-31 Dream private-history evidence with corrected no-cap/provider-thinking
  run, E2E50 local annotation, host-timing/coding-shadow deterministic proxy evidence, and live
  semantic worker root-cause diagnosis. The 2026-06-12 public-safe 50-case row complements this
  private scanner result; the 2026-06-10 E2E50 private/local follow-up supersedes the
  candidate-count reading while preserving the annotation blocker.
- **cannot_claim:** Causal real-user behavior lift, general Dream quality, full private-history coverage, safe
  delivered Dream treatment, completed private-history 20-case E2E50 benchmark quality,
  representative/live 50-case E2E50 quality, live host timing or annoyance lift, private-history
  coding decision-shadow behavior lift, or live semantic-model quality from the invalid-worker
  run.

### `dream.public_vs_baseline_shadow_2026_06_10`

- **current_value:** Public-safe deterministic Dream-vs-baseline shadow report: 4 synthetic cases; Dream route-lift
  count 2; useful action-delta count 2; total verification-cost delta is negative; visible
  wrong-hint count 0; wrong-hint rate 0.0; no-harm count 2; suppressed wrong-hint control count
  1; raw case text, source refs, absolute paths, and private user data are not serialized.
- **run_date:** 2026-06-10
- **source_report:** `python -m pytest tests\aippocampus\test_dream_live_shadow_ab.py -q`
- **claim_level:** `public_synthetic_dream_vs_baseline_shadow`
- **cohort:** Selected public synthetic cases for #163 over rejected-route recovery, stale-hypothesis
  demotion, temporary-concern quieting, and wrong/over-personalized hint suppression; no private
  text, no live delivery, and no external model calls.
- **supersedes / superseded_by:** Complements the private structural diagnostic by making the route-lift, useful-action,
  verification-cost, no-harm, and wrong-hint axes public and reproducible.
- **cannot_claim:** Causal real-user behavior lift, live delivered Dream quality, private-history reviewed quality,
  general Dream quality, active-imagination usefulness, production hint timing, or source truth
  without reopen.

### `dream.public_closeout_review_2026_06_14`

- **current_value:** Public-safe #1364/#1365 closeout review: public shadow cases report Dream wins 2, no-help quiet
  cases 1, visible regressions 0, suppressed regression-risk controls 1, route-lift count 2,
  useful action-delta count 2, visible wrong-hint count/rate 0/0.0, and verification-cost delta
  -3; sanitized candidate review has 6 rows, useful candidates 2, quiet/no-help candidates 1,
  rejected or blocked candidates 3, false-positive categories `stale_route`,
  `noisy_generic_vocab`, and `privacy_or_safety_boundary`, source-reopenable candidate rate
  0.666667, and foreground leak count 0.
- **run_date:** 2026-06-14
- **source_report:** [`dream-public-closeout-review-2026-06-14.md`](dream/dream-public-closeout-review-2026-06-14.md),
  [`dream-public-closeout-review-2026-06-14.json`](dream/dream-public-closeout-review-2026-06-14.json),
  and `python -m pytest tests\aippocampus\test_dream_live_shadow_ab.py -q`
- **claim_level:** `public_synthetic_dream_vs_baseline_shadow`
- **cohort:** Selected public synthetic Dream-vs-baseline and candidate-review cases; no private history, live
  delivery, model calls, raw source text, raw source refs, local paths, or foreground Dream
  truth.
- **supersedes / superseded_by:** Closes #1364 and #1365 through the public-safe equivalent path and makes #163 closeable only as
  a bounded public-safe owner closeout.
- **cannot_claim:** Live/default Dream delivery quality, broad private-history Dream quality, causal real-user lift,
  general Dream behavior quality, active-imagination usefulness, or source truth from Dream
  summaries or Dream-only candidates.

### `dream.delivery_quality_eval_2026_06_14`

- **current_value:** Public-safe #1438 three-arm Dream delivery-quality eval: pre-registered arms
  `baseline_no_dream`, `dream_backstage_only`, and `dream_bounded_action_hint`; 6 synthetic
  cases; bounded route lift 3; bounded action lift 2; verification-cost delta -3; visible wrong
  hints/rate 0/0.0; quiet/no-harm cases 4; source-ripening cases 2; stale route suppressions 1;
  noisy hint suppressions 1; over-personalization suppressions 1; Dream-only foreground leaks 0;
  source-truth overclaims 0; source reopen required count 6; provider calls 0.
- **run_date:** 2026-06-14
- **source_report:** [`dream-delivery-quality-eval-2026-06-14.md`](dream/dream-delivery-quality-eval-2026-06-14.md),
  [`dream-delivery-quality-eval-2026-06-14.json`](dream/dream-delivery-quality-eval-2026-06-14.json),
  and `python -m pytest tests\aippocampus\test_benchmark_dream_delivery_quality.py -q`
- **claim_level:** `public_synthetic_three_arm_delivery_quality_eval`
- **cohort:** Public synthetic delivery fixture only; no private history, live delivery, model calls, raw
  prompts, raw source text, source refs, thread/message handles, local paths, provider payloads,
  credentials, or foreground Dream truth.
- **supersedes / superseded_by:** Closes #1438 through a shareable delivery-quality proxy after #163's bounded public owner
  closeout, while keeping live/default and broad private-history claims out of scope.
- **cannot_claim:** Live/default Dream delivery quality, broad private-history Dream quality, causal real-user lift,
  default foreground Dream adoption, Dream-only material as source truth, or source claims
  without reopen.

### `dream.topology_scout_contract_2026_06_11`

- **current_value:** Public-safe Dream topology scout fixture: 5 source-anchored candidates for repeated route cycle,
  missing-middle/cut-point, weak bridge, knot, and island shapes; 1 healthy no-shape control; 4
  hard negatives rejected for private psychological interpretation, user diagnosis, profile
  claim, and source-free symbolic claim; foreground leak count 0; private-interpretation
  emission count 0; source-anchor coverage 1.0.
- **run_date:** 2026-06-11
- **source_report:** `python -m unittest tests.aippocampus.test_dream_topology_scout -v`
- **claim_level:** `public_safe_dream_topology_candidate_contract`
- **cohort:** Selected public-safe #1268 fixtures over existing packet topology and Dream candidate
  boundaries; no private text, raw source handles, local paths, live model calls, or foreground
  delivery.
- **supersedes / superseded_by:** Adds a reproducible topology-candidate substrate for #163 evaluation without replacing
  Jung-inspired Dream functions or source-ref adjudication.
- **cannot_claim:** Live Dream quality, private-history Dream quality, user-visible causal lift,
  psychological/profile truth, broad topology quality, foreground default usefulness, or source
  truth without reopen.

### `dream.long_context_atlas_pack_contract_2026_06_11`

- **current_value:** Public-safe #1269 long-context Dream atlas-pack fixture: 4 ready packs selected; 8 source refs;
  4 source threads; DeepSeek V4 family atlas metadata uses 1,000,000 context-window budget and
  `deepseek_prefix_v1`; prompt order is stable worker contract, stable atlas/source-card
  payload, then variable run directive; bounded-pack candidate count 0; atlas candidate count 2;
  bounded-missed bridge/cycle count 2; source-ref validity rate 1.0; unsupported candidate count
  0; 3 hard negatives rejected; offline cache telemetry unavailable with no invented hit rate.
- **run_date:** 2026-06-11
- **source_report:** `python -m unittest tests.aippocampus.test_dream_atlas_pack -v`
- **claim_level:** `public_safe_long_context_atlas_contract`
- **cohort:** Selected public-safe fixture for #1269 over cache-friendly atlas prompt order, source-card-only
  privacy, cross-pack bridge/cycle recovery, provider-usage cache telemetry boundary, and
  hard-negative rejection; no raw source text, raw source handles, local paths, private
  identifiers, live DeepSeek call, or foreground delivery.
- **supersedes / superseded_by:** Gives Dream a reproducible long-context batching and comparison surface before any live DeepSeek
  V4 quality or cache-efficiency claim. Official DeepSeek V4 1M context and KV-cache telemetry
  docs were checked on 2026-06-11.
- **cannot_claim:** Live DeepSeek quality, actual provider cache hit rate without provider `usage`, private-history
  atlas quality, broad long-context candidate quality, foreground default usefulness, or source
  truth without reopen.

### `dream.long_context_atlas_live_pilot_2026_06_12`

- **current_value:** Public-safe #1286 DeepSeek V4 Flash atlas pilot: live provider call completed over the built-in
  atlas fixture; bounded-pack candidate count 0; deterministic atlas candidate count 2; live
  atlas worker findings 2; accepted 1; parked 1; rejected 0; live source-ref validity rate 1.0;
  provider usage `prompt_tokens=3395`, `completion_tokens=1303`, `total_tokens=4698`; provider
  cache fields `prompt_cache_hit_tokens=3328`, `prompt_cache_miss_tokens=67`, hit rate 0.9803;
  latency 13417.244 ms; cost mode `provider_pricing_not_configured`.
- **run_date:** 2026-06-12
- **source_report:** [`dream-atlas-live-pilot-2026-06-12.md`](dream/dream-atlas-live-pilot-2026-06-12.md),
  [`dream-atlas-live-pilot-2026-06-12.json`](dream/dream-atlas-live-pilot-2026-06-12.json), and
  `python -m unittest tests.aippocampus.test_dream_atlas_pack -v`
- **claim_level:** `public_safe_live_deepseek_v4_flash_fixture`
- **cohort:** Selected public-safe fixture for #1286 over the opt-in live atlas command, stable DeepSeek
  prefix order, provider usage/cache telemetry from real response fields, background
  adjudication, bounded-vs-atlas-vs-live comparison, and no-key skip behavior; no private
  history, raw source text, API key values, API key environment names, local paths, foreground
  hook calls, or embedded provider pricing.
- **supersedes / superseded_by:** Closes the first live atlas pilot slice by proving the command/eval mode and
  telemetry/adjudication path on a shareable fixture; the parked candidate remains visible as a
  source-audit quality boundary rather than being forced through.
- **cannot_claim:** Broad live DeepSeek quality, private-history atlas quality, representative long-context
  candidate quality, user-visible Dream lift, foreground default usefulness, provider invoice
  cost, source truth without reopen, or a claim that all live model candidates survive
  adjudication.

### `journey.public_time_sliced_replay_2026_06_10`

- **current_value:** Public-safe deterministic Journey replay report: 4 replayable public-style cases; 4 Journey
  candidates created from visible source-backed rows; 4 future rows excluded; taxonomy counts
  `active_hint=1`, `resolved_frontier=1`, `stale_frontier_demotion=1`,
  `wrong_route_suppression=1`; 1 relevant prompt produced an agent-visible navigation hint; 3
  relevant prompts stayed backstage after resolved/stale/wrong-route demotion; 12 source-visible
  / unrelated / high-risk controls stayed silent, backstage, or source-reopen-required; expected
  relevant decisions passed 4/4; false foreground hints 0; future leakage count 0; raw row text,
  source refs, message ids, future rows, and private route handles are not serialized.
- **run_date:** 2026-06-10
- **source_report:** [`journey-public-time-sliced-replay.md`](benchmarks/reports/field-journey/journey-public-time-sliced-replay.md)
- **claim_level:** `public_safe_deterministic_fixture`
- **cohort:** Selected public-style replay cohort for #310 over Journey time slicing, hint/no-hint timing,
  stale/resolved/wrong-route suppression, false-foreground controls, and future-row exclusion;
  no private text, no live host, and no external model calls.
- **supersedes / superseded_by:** Complements the existing no-write live-row fixture by making the timing/no-leak taxonomy public and reproducible.
- **cannot_claim:** Private real-history Journey quality, live host timing quality, default foreground hint
  usefulness, user-visible recall lift, future-state prediction, Journey as user/persona truth,
  or source evidence without reopen.

### `thread_story.public_shadow_closeout_2026_06_10`

- **current_value:** Public-safe deterministic #313 closeout report: source-backed packet source-ref count 3; 4/4
  leakage and over-personalization controls pass; packet-only factual answer blocked 1/1;
  source-reopened answer allowed 1/1; public leakage hit count 0; agent-visible control emission
  count 0; false source-claim count 0; private story quality required for closeout is false.
- **run_date:** 2026-06-10
- **source_report:** `python -m unittest tests.aippocampus.test_thread_story_packet -v`
- **claim_level:** `public_structured_text_shadow_fixture`
- **cohort:** Selected structured-text thread-story rows and public controls for contradiction, persona-claim,
  multi-channel interference, and unrelated-story noise; no private text, raw symbolic channel,
  local path, live model, external model call, or default hook mutation.
- **supersedes / superseded_by:** Retires #313's public shadow closeout requirement while keeping future live/private thread-story
  quality as a separate evidence question.
- **cannot_claim:** Private real-history thread-story quality, live model-family behavioral equivalence, default
  recall or AAR improvement, user-visible recall improvement, user/personality truth, source
  truth from thread-story packets, or activation-steering equivalence.

### `cognitive_load.private_history_calibration_2026_06_08`

- **current_value:** Public-safe private-history aggregate scan: 100 local registry threads, 5,268 clean-source
  message rows, 82,695 clean-source event rows, 76 signal-bearing threads, 26,505 load signal
  events, 26,035 sidecar entries, max boost 0.16, decay coverage 1.0, and 0 over-personalization
  emissions.
- **run_date:** 2026-06-08
- **source_report:** [`cognitive-load-private-history-calibration-2026-06-08.md`](reports/cognitive-load-private-history-calibration-2026-06-08.md)
- **claim_level:** `private_history_aggregate_diagnostic`
- **cohort:** Local clean-source registry aggregate for #575; checked-in evidence is aggregate-only with no
  private text, raw source refs, local paths, raw command text, thread ids, or message ids.
- **supersedes / superseded_by:** First private-history calibration row for the cognitive-load sidecar.
- **cannot_claim:** Live hook capture, delivered host timing, host-timing quality, false-positive rate, caution-hint
  usefulness, user-visible recall improvement, source truth, semantic relevance, affect, stress,
  identity, or personality truth from load signals.

### `cognitive_load.public_behavior_trace_feedback_2026_06_10`

- **current_value:** Public-safe deterministic fixture report: 3 selected behavior-trace feedback cases; reviewed
  feedback cases 3; helpful caution-hint count 1; irrelevant load-drag count 1;
  over-personalization-risk count 1; `load_weight_false_positive_rate=0.333333`;
  `caution_hint_useful_rate=0.5`; `irrelevant_load_drag_rate=0.333333`; and source refs, raw
  notes, local paths, raw stress text, and trace source ids are not serialized.
- **run_date:** 2026-06-10
- **source_report:** `python -m pytest tests\aippocampus\test_cognitive_load_sidecar.py -q`
- **claim_level:** `public_safe_deterministic_fixture`
- **cohort:** Selected public synthetic behavior traces for #575; no private text and no live hook.
- **supersedes / superseded_by:** Complements the private aggregate row by adding selected public reviewed-feedback outcomes to the runtime report surface.
- **cannot_claim:** Live hook capture, delivered host timing, default foreground usefulness, broad false-positive or
  caution-usefulness quality, private-history generality, user-visible recall improvement,
  source truth, semantic relevance, affect, stress, identity, or personality truth from load
  signals.

### `cognitive_load.default_path_usefulness_2026_06_14`

- **current_value:** Public-safe #1375 default-path replay: 4 cases, useful hint count 1, wrong-route drag reduction
  1, blind-deepen reduction 1, no-hint/no-op pass count 2, default-path regression count 1,
  default-path usefulness rate 0.25, no-op behavior pass rate 1.0, feedback false-positive rate
  0.5, and recommended maturity `dogfood_diagnostic_only`.
- **run_date:** 2026-06-14
- **source_report:** [`cognitive-load-default-path-usefulness-2026-06-14.md`](benchmarks/reports/recall-navigation/cognitive-load-default-path-usefulness-2026-06-14.md),
  [`cognitive-load-default-path-usefulness-2026-06-14.json`](benchmarks/reports/recall-navigation/cognitive-load-default-path-usefulness-2026-06-14.json),
  and `python -m pytest tests\aippocampus\test_cognitive_load_sidecar.py -q`
- **claim_level:** `public_safe_default_path_replay`
- **cohort:** Selected public synthetic default-path replay cases for #1375/#575; no private history, live
  hook, raw source handles, local paths, raw notes, or affect/personality claims.
- **supersedes / superseded_by:** Closes #1375 and narrows #575 to diagnostic-only behavior rather than default foreground weighting.
- **cannot_claim:** Live hook capture quality, default foreground weighting readiness while regressions exist, broad
  private-history generality, source truth, semantic relevance, affect, stress, identity,
  intent, or personality truth from load signals.

### `cognitive_observatory.current_completeness_2026_06_14`

- **current_value:** Public-safe #1443 current completeness smoke: 7 expected surfaces and 7 included surfaces across
  route readiness, activation authority, recall diagnostics, query-pattern routes,
  cognitive-load calibration, sleep-cycle public summaries, and Campus usefulness panels;
  missing surfaces 0; stale bucket count 21; privacy-blocked bucket count 17; suppressed bucket
  count 26; blocked control attempts 1; attempted foreground-hook mutations 1; live ranking /
  hook mutations 0; raw leak flags 0. The top-level reader contract reports included surfaces,
  missing optional surfaces, blocked/suppressed surfaces, read-only control-plane status, and
  safe next actions; each surface row separates supported, present-in-this-readout, and
  fixture-validated states.
- **run_date:** 2026-06-14
- **source_report:** [`cognitive-observatory-current-completeness-2026-06-14.md`](benchmarks/reports/cognitive-runtime/cognitive-observatory-current-completeness-2026-06-14.md),
  [`cognitive-observatory-current-completeness-2026-06-14.json`](benchmarks/reports/cognitive-runtime/cognitive-observatory-current-completeness-2026-06-14.json),
  and `python -m pytest tests\aippocampus\test_cognitive_observatory_current_completeness.py -q`
- **claim_level:** `public_safe_current_completeness_smoke`
- **cohort:** Local/current public fixture only; no private raw history, raw prompts, raw source text, source
  refs, thread/message handles, local paths, provider payloads, credentials, live ranking
  mutation, hook mutation, or control-plane action.
- **supersedes / superseded_by:** Closes #1443 as an observability completeness/read-only boundary check, covers the latest
  reader-contract issue comment, and proves missing surfaces are explicit rather than silent.
- **cannot_claim:** Live user-visible quality lift, Observatory as a control plane, activation-order mutation,
  default foreground-hook adoption, source truth from summaries, private-history generality,
  absent optional surface validation, or source claims without reopen.

### `episode_arc.private_history_adjudication_2026_06_08`

- **current_value:** Public-safe private-history aggregate scan: 100 local registry threads, 5,164 clean-source
  message rows, 83,221 behavior event rows, 5,052 coding decision candidates, 1,851
  rejected-route candidates/arcs, 684 complete rejected-route arcs connected to nearby failed
  behavior, and 1,167 gappy single-point arcs.
- **run_date:** 2026-06-08
- **source_report:** [`episode-arc-private-history-adjudication-2026-06-08.md`](reports/episode-arc-private-history-adjudication-2026-06-08.md)
- **claim_level:** `private_history_aggregate_diagnostic`
- **cohort:** Local clean-source registry aggregate for #663; checked-in evidence is aggregate-only with no
  private text, raw command text, source refs, source-ref hash samples, event ids, thread ids,
  or local paths.
- **supersedes / superseded_by:** First private-history adjudication row for Episode/Arc rejected-route read-models.
- **cannot_claim:** Live host behavior lift, user-visible recall lift, current rejected-route validity without
  source reopen, private-history generality beyond this registry, default route-producer
  adoption, or Episode/Arc as a new truth layer.

### `episode_arc.public_gappy_chain_calibration_2026_06_10`

- **current_value:** Public-safe deterministic fixture report: 5 synthetic Episode/Arc cases; 2 complete arcs, 3
  gappy arcs; missing-middle, wrong-order, and single-point gap counts each 1; temporary-concern
  extinction count 1; `gappy_reopen_only_count=3`; `gappy_visible_action_overclaim_count=0`;
  `single_point_overclaim_rate=0.0`; `needs_reopen_projection_rate=1.0`; and raw source text,
  source refs, thread ids, registry paths, and local paths are not serialized.
- **run_date:** 2026-06-10
- **source_report:** `python -m pytest tests\aippocampus\test_episode_arcs.py -q`
- **claim_level:** `public_safe_deterministic_fixture`
- **cohort:** Selected public synthetic complete/gappy/wrong-order/single-point/temporary Episode/Arc cases for #663; no private text and no live model.
- **supersedes / superseded_by:** Complements the private aggregate row by proving selected public gappy-chain downshift behavior
  through the runtime report surface.
- **cannot_claim:** Live host behavior lift, user-visible recall lift, broad public corpus coverage, private-history
  generality, current route validity without source reopen, default route-producer adoption, or
  Episode/Arc as a new truth layer.

### `episode_arc.public_route_producer_2026_06_14`

- **current_value:** Public-safe deterministic #1362/#1363 route-producer fixture: 7 Episode/Arc families over commit
  revert, PR rejection/merge, issue reopen, patch supersession, workaround removal,
  missing-middle, and wrong-order controls; `sequence_route_count=7`;
  `repeated_wrong_route_prevented_count=2`; `unresolved_frontier_reopen_count=1`;
  `missing_middle_detected_count=1`; `wrong_order_suppressed_count=1`;
  `ordered_route_helpfulness_rate=0.571429`; `sequence_order_claim_requires_reopen_count=7`;
  `sequence_route_claim_without_reopen_count=0`; `foreground_story_dump_count=0`.
- **run_date:** 2026-06-14
- **source_report:** [`episode-arc-read-models.md`](../architecture/coordination/episode-arc-read-models.md) and
  `python -m pytest tests\aippocampus\test_episode_arc_route_producer.py -q`
- **claim_level:** `public_safe_deterministic_route_producer_fixture`
- **cohort:** Public synthetic VCS/hard-event-style case summaries only; no raw source text, source refs,
  event ids, thread ids, registry paths, local paths, private history, live host calls, or model
  calls.
- **supersedes / superseded_by:** Closes the public deterministic route-producer/evidence slice for #1361, #1362, and #1363, and
  makes #663 closeable as a bounded owner closeout while preserving live/default successor work.
- **cannot_claim:** Live host behavior lift, user-visible recall lift, default recall route-producer adoption,
  private-history generality, current route validity without source reopen, or Episode/Arc as a
  new truth layer.

### `episode_arc.sequence_usefulness_2026_06_14`

- **current_value:** Public-safe #1440 sequence-usefulness workload: 7 public synthetic Episode/Arc cases compare
  `baseline_no_episode_arc` against `episode_arc_route_packet` under the same source-ref-hash
  budget; treatment wins 4, regressions 0, manual-search step delta 7, repeated-mistake
  avoidance lift 2, correct source-reopen lift 4, stale-chain suppression lift 1, quiet/no-harm
  controls 2, wrong-project contamination 0, and source-truth overclaim count 0.
- **run_date:** 2026-06-14
- **source_report:** [`episode-arc-sequence-usefulness-2026-06-14.md`](benchmarks/reports/coordination/episode-arc-sequence-usefulness-2026-06-14.md),
  [`episode-arc-sequence-usefulness-2026-06-14.json`](benchmarks/reports/coordination/episode-arc-sequence-usefulness-2026-06-14.json),
  and `python -m pytest tests\aippocampus\test_benchmark_episode_arc_sequence_usefulness.py -q`
- **claim_level:** `public_safe_sequence_usefulness_workload`
- **cohort:** Public synthetic route-producer-derived cases only; same source-ref-hash budget, no raw source
  text, raw source refs, thread/message handles, local paths, provider payloads, private
  history, live host calls, or model calls.
- **supersedes / superseded_by:** Closes #1440 as selected public sequence-usefulness evidence for repeated wrong-route avoidance,
  frontier/source reopen, patch supersession, and incomplete/wrong-order no-harm behavior.
- **cannot_claim:** Live host behavior lift, user-visible recall lift, default recall route-producer adoption,
  private-history generality, current route validity without source reopen, or Episode/Arc as a
  new truth layer.


## Supersession Notes

- The 2026-06-15 learning-loop/action-cache closeout includes the follow-up
  issue-comment fixes: MCP `agent_recall` now receives the same semantic
  provider-key bridge as `recall_diagnostic`; AIppo workflow activation covers
  hook install UX, action-hint cache/status readiness, macOS `python3` install
  docs, and upstream-issue writing language, while unmatched tasks report a
  public-safe no-family reason; ambiguous Codex plugin-cache repairs recommend
  the one-command reinstall path before manual candidate selection; public
  foreground cards expose no local handle or fake short action token; malformed
  action-hint cache/input rows fail open with diagnostics; and explicit invalid
  route limits are rejected instead of silently broadening recall.
- The 2-thread / 5-row strict-survival slice remains useful because it records
  what survived stronger per-label evidence gates. It is no longer the current
  aggregate materialized semantic-sidecar coverage.
- The 24-case source-review row remains the named selected green gate. The
  2026-06-09 96-case row resolves the old operational partial failure and is
  still broader diagnostic evidence, not human review or global semantic
  correctness.
- Metric families with multiple valid cohorts must name the cohort and date:
  public corpus, private real-history, selected source-review, aggregate
  registry smoke, and demo scenario caveats are separate evidence layers.
- The CJK local recall fixture is a public deterministic regression fixture.
  The 2026-06-09 #1054 rerun separately reports FTS5 trigram, production
  hybrid, and explicit CJK query-chunk behavior. It shows that lightweight CJK
  query chunks now recover the checked fixture's compact no-space cue in the
  default local hybrid path; it does not supersede the real-history FTS5 row
  and must not be treated as a broad Chinese semantic-search claim.
- The LongMemEval-S 500-question row is the current larger retrieval-only
  external-benchmark slice. It supersedes the earlier 100-question
  LongMemEval-S row only for sample size and dated currentness, and it keeps
  answer generation, judge scoring, V2, SOTA comparison, exact-line citation
  quality, and decision-gate claims out of scope.
- The LongMemEval-S lexical line-reranker row is a default-off diagnostic over
  the same 500-question cohort. It records a fused exact-line ranking
  improvement, but it does not supersede the retrieval-only row or prove broad
  reranker safety.
- The LongMemEval-S semantic warm query/cache rows retire #1305's immediate
  unmeasured warm query/candidate cache gap and preserve a 100Q provider
  prefix-cache comparison for #1323. The 2026-06-13 row supersedes them as a
  same-cohort comparison point by measuring both the current source-worker
  proxy, the 500Q LLM query/candidate upper bound, and the contract-aware
  full-source semantic-scope warming path. The full-source row proves the
  materializer can read the full public source side, but also shows current
  ranking/fusion does not lift fused R@10 from that signal yet.
- The LongMemEval-S fixed-reader answer/latency row is the first small
  provider-backed answer-quality baseline over the first 25 `single-session-user`
  cases. It records reader config, prompt version, retrieval metrics, answer
  metrics, latency, token use, cost basis, sanitized validation, and
  cannot-claim boundaries separately. It does not supersede the larger
  500-question retrieval-only row or establish official judge quality.
- The public reliability gauntlet row is an aggregate gate over existing
  runtime, mis-recall, and pollution surfaces. It does not supersede the
  individual LongMemEval, Track S, knowledge-pollution, or scale-smoke owners,
  and it deliberately provides no single reliability score.
- The multimodal NIAH row is a supplied-pool synthesis contract. It shows
  conflict/currentness decision behavior after retrieval has been removed from
  the measurement; it is not evidence for ATM-Bench retrieval, live vision
  answers, or product behavior over private media.
- The React VCS source-disambiguation row is intentionally split
  from the 2026-05-31 source-window oracle reports. Its current/effective
  source ranking succeeds on the adversarial source-authority tracks, and the
  2026-06-09 rerun suppresses the explicit-cue lexical near-miss hard-negative
  track without using gold source ids as ranking input. It still must not be
  treated as broad semantic near-miss understanding, live model quality, or wild
  VCS corpus quality.
- The recall-navigation follow-through row is a deterministic source-navigation
  proxy only. It records that a route handle can be reopened through
  `recall_deepen` and that a foreground packet candidate ref can reopen one
  public fixture source; it is not evidence that the default foreground hook now
  improves vague first or second turns in real use.
- The Claude Code dogfood row splits host surfaces deliberately. Temporary
  strict-config MCP reachability is positive live-host evidence; #1235
  supersedes the old #1021 persistent local blocker only for this repaired
  operator host. Do not read that as cross-host persistent MCP health or
  real-host hook firing evidence.
- The Claude Code hooks contract row is a scoped synthetic contract, not
  real-host firing evidence. It retires the vague "Claude Code hooks" caveat by
  proving the public status/dry-run/smoke surface and fail-open
  `UserPromptSubmit` / `Stop` handler behavior, while preserving event-level
  material limits for real host firing, settings mutation, tool payload
  capture, and compaction summary handling.
- The live semantic route-actionability row is the matching public live smoke
  for high-confidence semantic hits. It records that guarded model-only
  `evidence` became `source_required` / `reopenable_route` with zero manual
  query invention in that cohort; it does not itself measure bounded evidence
  after source reopen or private-registry quality.
- The hippocampal D5/D6 row is a narrow public synthetic gate over the
  `full_query` diagnostic arm. It supersedes the older 12-case combined D5/D6
  readout for current D5/D6 sample size and gate status only; it does not
  update baseline-arm, H5, external-adapter, live, private-history, or full P1
  claims.
- The hippocampal hard-negative row separates production-like outputs from
  contract controls. Use the 12-output production slice for current
  public-synthetic failure counts, and use the 16-example contract controls
  only to understand the scorer taxonomy.
- The 2026-06-04 Dream private-history diagnostic row is intentionally split
  between valid model-backed Dream evidence and invalid operator/config
  evidence. The invalid max-token, disabled-thinking, and invalid-worker runs
  must not be used as main quality evidence.
- Its E2E50 annotation update reviewed all 17 local scanner candidates but kept
  only 4 gold-seed candidates and 2 calibration cases. That is progress toward
  #279, not a representative E2E50 benchmark.
- The cognitive-load private-history row is an aggregate diagnostic. It shows
    that private clean-source load signals can be measured without public leakage,
    but the failed-command-heavy distribution still needs reviewed feedback before
    any default foreground or host-timing claim.
- The cognitive-load public behavior-trace row supplies selected reviewed
  feedback outcomes for usefulness, irrelevant drag, and over-personalization
  risk. It narrows the public reproducibility gap, but it does not prove live
  host timing, default foreground usefulness, or broad private-history quality.
- The Episode/Arc private-history row is an aggregate diagnostic over rejected
  route chains. It shows real local chain material exists and gappy rows are
  counted, but it does not prove sequence packets improve live host behavior or
  that old rejected routes remain current without source reopen.
- The Episode/Arc public gappy-chain row is the matching public fixture for
  downshift behavior. It proves selected complete/gappy/wrong-order/single-point
  projections stay within the source-reopen boundary, but it does not replace
  richer adapter, private-history generality, or live host-behavior evidence.
