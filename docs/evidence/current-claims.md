# Current Evidence Claims

Role: current benchmark/readiness claim snapshot.
Status: current owner for numeric evidence claims, supersession, cannot-claim
boundaries, and confirmed scope-boundary remediation pointers.

This is the current-claims snapshot for benchmark and readiness numbers that
are easy to over-read when old dated ledgers still say "current" in their local
context. It is not a command ledger and it does not replace source reports.

Snapshot date: 2026-06-09.

Rules:

- A value is current only for the `run_date`, `cohort`, and `claim_level` named
  in its row.
- Dated evidence remains in
  [`docs/evidence/readiness/public-readiness-verification.md`](readiness/public-readiness-verification.md)
  and detailed benchmark methodology remains in
  [`docs/evidence/benchmarks/memory-decision-benchmark-plan.md`](benchmarks/memory-decision-benchmark-plan.md).
- Benchmark priority, run-profile, and cannot-claim navigation remains in
  [`docs/evidence/benchmarks/design/benchmark-priority-map.md`](benchmarks/design/benchmark-priority-map.md).
- Stage-level can-claim / cannot-claim status remains in
  [`docs/evidence/readiness/stage-0-5-readiness.md`](readiness/stage-0-5-readiness.md).
- Demo caveats in
  [`docs/guides/demo-scenarios.md`](../guides/demo-scenarios.md) are
  claim-boundary inputs, not standalone benchmark proof.
- AMemGym adapter smoke currently has no Current Claim Snapshot row; its
  native-score, source-backed overlay, diagnosis, utilization, and cost/latency
  boundaries stay in
  [`docs/evidence/benchmarks/amemgym.md`](benchmarks/amemgym.md) until a dated
  result owner upgrades a claim.

## Confirmed Scope Boundaries (Expected Null Results)

Start here before opening dated report history. These rows are the current
reader-facing ledger for open and resolved remediation routes that are easy to
over-read as either broad product failure or broad product proof. A confirmed
scope boundary is still real evidence: keep the original result visible, then
state the condition where the result does and does not apply.

| Area | Current evidence state | Remediation route | Reader boundary |
| --- | --- | --- | --- |
| Continuous-memory short complete-spec boundary | The 2026-06-08 public-synthetic repeat profile is a confirmed expected-null boundary: `lower_bound_passed=false`; the historical row keeps `decision_label=no demonstrated memory advantage`, and the public interpretation is `no demonstrated net advantage over modeled fresh-context spec loop`. | [#960](https://github.com/Sapientropic/AIppocampus/issues/960) owns any product remediation and next repeated-evidence slice after this boundary note. | Do not claim continuous-memory superiority until a later dated row supersedes this evidence; also do not read this as evidence that source-backed recall has no value in context-loss, cross-thread, post-compaction, or long-horizon scenarios. |
| Track B private source-evidence retrieval | The selected private slice is 97/100 top-5 after semantic-sidecar refresh, with 3 `rank_below_top_k` misses. | [#963](https://github.com/Sapientropic/AIppocampus/issues/963) owns miss taxonomy and repair. | Do not turn the 0.97 selected slice into broad real-user gate quality or semantic completeness. |
| AMemGym official live-provider score blocker | AMemGym has adapter/protocol/overlay evidence but no Current Claim Snapshot metric row yet; the 2026-06-09 blocker note records why a full live/provider `v1.base` fixed-arm run is not yet safe or reproducible. | [`amemgym-official-live-provider-blocker-2026-06-09.md`](benchmarks/amemgym-official-live-provider-blocker-2026-06-09.md) closes [#958](https://github.com/Sapientropic/AIppocampus/issues/958) as a blocker decision. | Do not present protocol output, partial OpenRouter output, or overlay diagnostics as an official live-model score. |
| React VCS lexical near-miss false positives | The current 2026-06-09 row reports 60/60 gold true positives and 30/30 explicit-cue hard negatives suppressed. | [#961](https://github.com/Sapientropic/AIppocampus/issues/961) is closed; the fix is reflected in the current snapshot row. | Do not use older 2026-06-04 false-positive evidence as the current source-disambiguation state. |
| Progressive recall route follow-through gaps | The current row reports `route_actionability_rate=1.0` and eligible `source_reopen_follow_through_rate=1.0`, with stale handles rejected before source use. | [#962](https://github.com/Sapientropic/AIppocampus/issues/962) is closed; the fix is reflected in the current snapshot row. | This still does not close broad live #201 or default foreground-lift claims. |
| Multimodal NIAH stale conflicting-source selection | The current row reports 4/4 answer/source-selection/source-anchor-citation after conflict repair and keeps the ambiguous-currentness negative control as reopen-required. | [#964](https://github.com/Sapientropic/AIppocampus/issues/964) is closed; the fix is reflected in the current snapshot row. | This is a supplied-pool synthesis contract, not retrieval or live vision-model quality. |
| Track S explicit-negation/currentness failures | The current 2026-06-09 row reports `quality_gate_ok=true`, S1 false evidence 0, and S3 explicit-negation/stale-as-current/evidence-over-escalation counts all 0. | [#992](https://github.com/Sapientropic/AIppocampus/issues/992) owns this repair; the fix is reflected in the current snapshot row. | This is a public-safe deterministic hook/retrieval diagnostic, not human-level semantic understanding or broad private-history recall quality. |
| Semantic source-review operational partial failure | The current 2026-06-09 96-case rerun has `failure_count=0` and `failure_taxonomy.by_class={}`; `preference` remains below the per-label floor as diagnostic label-quality evidence. | [#993](https://github.com/Sapientropic/AIppocampus/issues/993) owns the taxonomy/public-shadow repair; the fix is reflected in the current snapshot row. | Do not treat the broader diagnostic as human review, provider-independent quality, a green gate, or full semantic correctness. |

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

| Evidence row | What it shows | Boundary |
| --- | --- | --- |
| `boundary_confirmed.short_task_complete_spec_synthetic_2026_06_08` | Fresh context wins for short complete-spec tasks under the current cost ledger. | Expected-null boundary; memory overhead is not justified in this condition. |
| `recall_navigation.progressive_route_follow_through` | Progressive recall routes can become actionable and reopen source in deterministic fixtures. | Not broad live foreground lift. |
| `live_semantic.route_actionability_2026_06_07` | Live semantic route hits can become reopenable or source-required routes on a public checked-in corpus. | Not private-registry vague recall quality. |
| `track_b.private_semantic_sidecar_required` | Private real-history sidecar retrieved the expected source in 97/100 selected top-5 cases. | Maintainer-only private slice, not public benchmark score. |
| `episode_arc.private_history_adjudication_2026_06_08` | Rejected-route arcs exist at scale in private aggregate history. | Diagnostic aggregate, not live behavior lift. |

## Cannot-Claim Owner And Retirement Ledger

This table keeps testable `cannot_claim` entries from becoming permanent
background caveats. Use the metadata shape `category`, `owner_issue`,
`retirement_condition`, and `next_review` when adding or reviewing rows.

`actionable` entries need an owner issue and a retirement condition.
`durable_non_goal`, `research_blocked`, and `external_dependency` entries can
remain without a direct implementation owner when a test would not honestly
retire the caveat. Do not retire a broader caveat from a narrow smoke; add or
update a dated claim row first.

| Caveat | Category | Owner issue | Retirement condition | Next review |
| --- | --- | --- | --- | --- |
| Continuous-memory superiority after the preregistered repeat negative result | `actionable` | [#960](https://github.com/Sapientropic/AIppocampus/issues/960) | A later dated repeated-evidence row supersedes `continuous_memory.preregistered_repeat_profile_2026_06_08` with a passing preregistered lower-bound decision and explicit cost/harm boundary. | Before any #378 or continuous-memory public-readiness upgrade. |
| Track B private source-evidence retrieval top-k misses | `actionable` | [#963](https://github.com/Sapientropic/AIppocampus/issues/963) | The three `rank_below_top_k` misses are taxonomized, repaired or deliberately bounded, and a later dated Track B row records the updated hit/miss state without broad semantic-completeness claims. | Before treating selected Track B as gate-quality evidence. |
| E2E50 representative seed pack | `actionable` | [#994](https://github.com/Sapientropic/AIppocampus/issues/994) | A reviewed 20-case representative seed pack or a clearly smaller accepted slice is checked in with selection rationale, negative controls, and a dated report boundary. | Before using E2E50 evidence outside candidate-seed language. |
| Claude Code hook real-host firing and unsupported events | `actionable` | [#1020](https://github.com/Sapientropic/AIppocampus/issues/1020) | A local or public-safe real-host event log shows the scoped handlers firing, and later slices add payload-safe `PostToolUse`/`PostToolBatch` or compaction support before those events are claimed. | Before widening the scoped #1020 synthetic hook contract beyond `UserPromptSubmit` and `Stop`. |
| Persistent Claude Code MCP config health | `external_dependency` | [#1021](https://github.com/Sapientropic/AIppocampus/issues/1021) | The #1021 diagnostic narrowed the current local blocker to `bad_command_path` / `configured_arg_path_missing`. Retire this caveat only after the local stale command path is repaired and a later persistent-config diagnostic reports `healthy`. | When an operator opts in to repairing persistent Claude MCP settings. |
| CJK recall quality beyond the first public fixture | `actionable` | [#1022](https://github.com/Sapientropic/AIppocampus/issues/1022) | The 2026-06-09 expanded public-safe CJK pack reports FTS-only, lexical-structural, and `cjk_aware_sidecar` paths separately while preserving 0 negative false positives; future default-production changes need a new dated row. | Before widening Chinese recall claims beyond the expanded fixture. |
| Cognitive-load false positives and usefulness | `actionable` | [#575](https://github.com/Sapientropic/AIppocampus/issues/575) | Reviewed false-positive and caution-usefulness evidence, or a dated blocker, supersedes the aggregate private-history calibration row without treating load signals as affect or personality truth. | Before enabling any default host-timing or foreground weighting claim. |
| Episode/Arc gappy-chain overclaim risk | `actionable` | [#663](https://github.com/Sapientropic/AIppocampus/issues/663) | Richer adapter or live/private adjudication evidence shows how complete and gappy chains are used, while preserving source-reopen requirements for current validity. | Before treating Episode/Arc packets as more than navigation/read-model context. |
| AMemGym official live-provider score | `external_dependency` | - | A later dated AMemGym note records a complete pinned live/provider `overall` / `upperbound` / `random` fixed-arm run, sanitized cost/latency, and parity-arm decision without promoting protocol smoke into live score claims. | When bounded/resumable official execution and cost extraction are available. |
| Private text disclosure in public evidence | `durable_non_goal` | - | Not retired by benchmark evidence; public reports stay aggregate, sanitized, or source-reopenable without raw private text. | Recheck only if the public/private evidence policy changes. |
| Hosted or cloud continuity from a single local-host smoke | `external_dependency` | - | Requires a scoped cloud/sync/provider evidence issue before it becomes actionable; local host proof cannot retire hosted or cross-device caveats. | Before any hosted/cloud product claim. |
| Broad private-history quality from selected local diagnostics | `research_blocked` | - | Requires a separately scoped private-history quality protocol with privacy-preserving review and explicit cohort limits; selected aggregates do not retire it. | Before any broad real-history quality claim. |

## Current Claim Snapshot

| metric_id | current_value | run_date | source_report | claim_level | cohort | supersedes / superseded_by | cannot_claim |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `registry.local_real_history_aggregate` | 964 clean-source/index/graph-backed threads; 110 scope-labeled threads; 88 non-technical life-wide threads; 244 semantic sidecar rows across 46 threads; all eight canonical labels observed. | 2026-05-30 | [`public-readiness-verification.md`, #55 Stage 2 evidence](readiness/public-readiness-verification.md#2026-05-30-issues-5556-evidence-closeout) | `first_pass_real_history_slice` | Local real-history registry aggregate; aggregate-only smoke output. | Supersedes the older 949-thread aggregate paragraph for public currentness. | Full-history refresh, semantic completeness, label correctness without clean-source review, or private-text disclosure. |
| `semantic_sidecar.aggregate_materialized_rows` | 244 semantic sidecar rows across 46 threads, with all eight canonical labels observed. | 2026-05-30 | [`public-readiness-verification.md`, #55 Stage 2 evidence](readiness/public-readiness-verification.md#2026-05-30-issues-5556-evidence-closeout) | `first_pass_real_history_slice` | Local real-history dynamic semantic sidecar observation. | Supersedes the older 2-thread / 5-row strict-survival number for aggregate materialized coverage only. | Global semantic correctness, human review, complete life-wide labeling, or relaxed materializer gates. |
| `semantic_sidecar.strict_survival_snapshot` | Historical strict-survival slice: 5 rows across 2 real clean-source threads and 5 semantic latest timeline turns. | 2026-05-29 | [`public-readiness-verification.md`, earlier Stage 2 closeout](readiness/public-readiness-verification.md) and [`memory-decision-benchmark-plan.md`](benchmarks/memory-decision-benchmark-plan.md) | `historical_strict_survival_snapshot` | Strict per-label evidence gate after source-review tightening. | Superseded by `semantic_sidecar.aggregate_materialized_rows` for aggregate coverage; retained as a stricter survival baseline. | Latest aggregate coverage, global Stage 2 correctness, or proof that suppressed labels are safe to restore. |
| `semantic_sidecar.source_review_green_gate` | 24 selected semantic sidecar label cases reviewed; 24/24 passed; `pass_rate=1.0`; no live model failures. | 2026-05-30 | [`public-readiness-verification.md`, #55 Stage 2 evidence](readiness/public-readiness-verification.md#2026-05-30-issues-5556-evidence-closeout) | `selected_source_review_green_gate` | Selected strict semantic sidecar labels reviewed through the live DeepSeek-compatible source-review smoke. | Supersedes the older 5-case strict-review pass as the selected green gate. | Human review, broad correctness, or full-history semantic quality. |
| `semantic_sidecar.source_review_diagnostic` | 96 selected cases reviewed; 88 passed; `pass_rate=0.9167`; `failed_label_categories=["preference"]`; `failure_count=0`; `failure_taxonomy.by_class={}`. | 2026-06-09 | [`public-readiness-verification.md`, 2026-06-09 #993 rerun](readiness/public-readiness-verification.md#2026-06-09---source-review-taxonomy-and-public-shadow-rerun) | `broader_selected_source_review_diagnostic` | Broader selected source-review smoke with live provider behavior. | Supersedes the 2026-05-30 96-case diagnostic that had one live model partial failure; the 24-case row remains the named green gate. | Human review, full-history semantic correctness, release gate, selected source-review green gate, provider-independent quality, or private-text disclosure. |
| `track_b.private_semantic_sidecar_required` | 100 selected private real-history cases; 97/100 top-5 hits; 0.97 hit rate; 3 `rank_below_top_k` failures after the 45-thread / 243-row semantic-sidecar refresh. | 2026-05-29 | [`memory-decision-benchmark-plan.md`, private real-history Track B wrapper](benchmarks/memory-decision-benchmark-plan.md#track-b-source-evidence-retrieval) | `private_bounded_track_b_slice` | Maintainer-only private real-history semantic-sidecar-required source-evidence slice. | Supersedes the sparse-pool blocker for this selected slice only. | Public benchmark score, real-user gate quality, full semantic completeness, or live semantic-model quality. |
| `fts5.real_history_recall_2026_05_29` | Post-repair 100 selected source-backed cases; FTS5 91/100 top-1, 100/100 top-5, 100/100 top-10; production lexical-structural hybrid 100/100 top-10. | 2026-05-29 | [`public-readiness-verification.md`, FTS5 real-history recall benchmark](readiness/public-readiness-verification.md) and [`memory-decision-benchmark-plan.md`](benchmarks/memory-decision-benchmark-plan.md) | `bounded_real_history_regression_smoke` | Local 949-thread real-history registry slice after stale SQLite index repair. | Superseded only by a newer dated FTS5 real-history run. | Natural-language user-query quality, private text disclosure, broad product recall quality, or dense vector retrieval as a default path. |
| `cjk.local_recall_public_fixture_2026_06_09` | Public-safe expanded CJK fixture: 10 synthetic cases; `cjk_aware_sidecar` hit 7/7 positive cases at top-5 with 0 negative false positives; production lexical-structural hybrid hit 6/7 positives with 0 negative false positives; FTS5 trigram alone hit 3/7 positives. | 2026-06-09 | [`cjk-local-recall-fixture-report.md`](benchmarks/cjk-local-recall-fixture-report.md) | `public_safe_deterministic_fixture` | Synthetic public exact/short/mixed/deictic/paraphrase/compact no-space/project-symbol/negative CJK local-recall cases. | Supersedes `cjk.local_recall_public_fixture_2026_06_07` for the checked-in public CJK fixture. | Broad Chinese recall quality, semantic Chinese search from trigram alone, production hybrid handling every compact CJK cue, private-history CJK quality, heavyweight tokenizer need, or dense vector retrieval as a default path. |
| `demo_scenarios.claim_boundaries` | Public-safe demo scenarios show product shape; their `Cannot claim` lines are claim-boundary sources for demos. | 2026-06-03 | [`docs/guides/demo-scenarios.md`](../guides/demo-scenarios.md) | `claim_boundary_source` | Public example bundle, public-safe demo commands, and explicit live/smoke demo flows. | Not a metric row; it routes demo caveats into evidence governance. | Official benchmark proof, readiness metric upgrades, or private real-history performance. |
| `claude_code.real_host_dogfood_2026_06_09` | Local Claude Code history parser passed on 222 detected sessions; dry-run onboarding planned 223 registrations and 3 stale-index repairs without writing; synthetic cross-agent clean-source retrieval passed in both directions; temporary strict-config Claude Code MCP live call reached `memory_health`; persistent Claude Code MCP config still reports failed connection, and the #1021 diagnostic narrowed the blocker to `bad_command_path` / `configured_arg_path_missing` before server startup. | 2026-06-09 | [`claude-code-dogfood-2026-06-09.md`](readiness/claude-code-dogfood-2026-06-09.md) | `local_real_host_dogfood_with_precise_persistent_blocker` | Single Windows operator host plus public-safe synthetic Codex/Claude fixture. | Supersedes older "persistent host reachable" wording for the current local host state; preserves temporary strict-config MCP reachability as the positive live-host proof and narrows the persistent-config blocker to a stale/missing command path. | Claude Code real-host hook firing beyond the scoped #1020 synthetic contract, persistent MCP config health until the stale command path is repaired and a later diagnostic reports `healthy`, unattended private-history ingestion, cross-device sync, hosted/cloud continuity, broad cross-host relationship continuity, or private-history quality. |
| `claude_code.hooks_contract_2026_06_09` | Scoped Claude Code hook contract slice: `status`, `dry-run`, and `smoke` commands exist; `UserPromptSubmit` and `Stop` synthetic Claude-shaped hook inputs exit 0 without leaking raw prompt text, session ids, transcript paths, cwd values, settings paths, source refs, or synthetic tool payload text; `PostToolUse`/`PostToolBatch` and compaction hooks report event-level blockers. | 2026-06-09 | [`claude-code-hooks-contract-2026-06-09.md`](readiness/claude-code-hooks-contract-2026-06-09.md) | `scoped_synthetic_hook_contract` | Public-safe synthetic Claude-shaped hook payloads plus official-contract intake. | Narrows the broad Claude Code hook caveat into scoped `UserPromptSubmit`/`Stop` handler availability and explicit unsupported-event blockers. | Real-host hook firing, Claude settings mutation, configuration-mutating installer availability, `PostToolUse`/`PostToolBatch` payload capture, compaction survival packet utility, all Claude Code versions, MCP health, transcript onboarding, or private-history quality. |
| `multimodal_niah.evidence_pool_conflict_resolution` | Public-safe NIAH evidence-pool contract: 4/4 answer/source-selection/source-anchor-citation after conflict repair; one stale input source selection preserved as `input_selected_evidence_ids`, `current_source_selected_count=1`, `stale_or_conflicting_distractor_selection_count=0`, `needs_source_reopen_count=0`; ambiguous-currentness regression control requires `needs_source_reopen` instead of guessing. | 2026-06-09 | [`multimodal-niah-evidence-pool-report.md`](benchmarks/multimodal-niah-evidence-pool-report.md) | `public_safe_deterministic_contract` | Four public synthetic NIAH supplied-pool rows plus one in-test ambiguous-currentness negative control; retrieval is intentionally not scored. | Supersedes the 2026-06-03 expected stale-source failure interpretation for the #533 NIAH supplied-pool contract. | Retrieval quality, ATM-Bench Hard score/support, live vision-model answer quality, raw-media model quality, private media behavior, or broad multimodal-memory quality. |
| `recall_navigation.progressive_route_follow_through` | Progressive `recall_context -> recall_deepen` arm: `route_actionability_rate=1.0`, eligible `source_reopen_follow_through_rate=1.0` (3/3 eligible route reopens reached expected clean-source refs), `source_reopen_fail_closed_count=1` with `failure_class=stale_handle_rejected_before_source_use`, `avg_manual_query_invention_count=0.0`; foreground packet candidate ref follow-through reached the expected fixture source with `foreground_manual_query_invention_count=0`. | 2026-06-09 | [`recall-navigation-comparison-2026-06-03.md`](benchmarks/recall-navigation-comparison-2026-06-03.md) | `public_safe_deterministic_proxy` | Four public synthetic clean-source fixtures plus one foreground hook packet/cache fixture; all use temporary public-safe clean-source/index/cache data. | Updates the #465 comparison with a narrow #201 route-follow-through readout; does not supersede live #201 field reports. | Live user quality, broad default foreground first-turn or second-turn lift, production selector superiority, source-backed answer quality beyond the synthetic fixtures, or closing #201. |
| `live_semantic.route_actionability_2026_06_07` | Public checked-in local corpus live smoke: 8/8 correct; semantic available 4/4; `semantic_evidence_guarded_to_scent_count=3`; all 3 guarded high-confidence semantic route hits became `source_required` / `reopenable_route`; `semantic_evidence_guarded_to_plain_scent_count=0`; `paid_semantic_hit_to_source_reopen_rate=1.0`; `manual_query_invention_after_paid_semantic_hit_count=0`; evidence false positives 0. | 2026-06-07 | [`memory-decision-benchmark-plan.md`, live semantic route-actionability smoke](benchmarks/memory-decision-benchmark-plan.md#track-a-memory-decision-gate) | `public_live_semantic_route_smoke` | Public checked-in testdata converted to clean source; DeepSeek-compatible live semantic path; sanitized aggregate report only. | Complements `recall_navigation.progressive_route_follow_through`: live smoke measures high-confidence semantic route actionability; deterministic fixture measures source reopen / bounded-evidence follow-through. | Private-registry vague recall quality, all future semantic prompts, broad default foreground first/second-turn lift, external baseline comparison, or live bounded-evidence-after-reopen rate. |
| `continuous_memory.preregistered_repeat_profile_2026_06_08` | Public-synthetic #378 repeat profile: 6 cases, 5 deterministic paired repeats per case/arm, 30 case-arm trials, 180 rows, `lower_bound_units=-27.7675`, `mean_delta_units=-27.7675`, `lower_bound_passed=false`, `primary_endpoint_winner=fresh_context_spec_loop`, and historical `decision_label=no demonstrated memory advantage`; scope-boundary alias `boundary_confirmed.short_task_complete_spec_synthetic_2026_06_08` means no demonstrated net advantage over the modeled fresh-context spec loop. | 2026-06-08 | [`memory-decision-benchmark-plan.md`, #378 repeat profile](benchmarks/memory-decision-benchmark-plan.md) and [`public-readiness-verification.md`, 2026-06-08 continuous-memory preregistered repeat readout](readiness/public-readiness-verification.md#2026-06-08---continuous-memory-preregistered-repeat-readout) | `confirmed_scope_boundary_expected_null` | Deterministic public-safe continuous-memory attribution fixtures; short complete-spec boundary condition; no live model, no private history, no live host-native telemetry. | Supersedes the earlier one-repeat #378 slice only for the lower-bound gate status; preserves the negative/no-advantage conclusion and adds the boundary-oriented reading alias. | Full #378 continuous-memory superiority, live host-native cost or compaction telemetry, private real-history generality, cost-weight robust advantage, answer-generation model quality, competitor superiority, or a claim that source-backed recall has no value outside complete-spec short tasks. |
| `react_vcs.production_like_source_disambiguation` | 60/60 gold true positives, `current_source_top_k_hit_rate=1.0`, `current_vs_stale_pairwise_win_rate=1.0`, `wrong_source_evidence_rate=0.0`, `negative_false_positive_rate=0.0`, and `hard_negative_suppression_rate=1.0` after suppressing 30/30 explicit-cue lexical near-miss hard negatives. | 2026-06-09 | [`react-real-vcs-production-like-disambiguation-2026-06-04.md`](benchmarks/react-real-vcs-production-like-disambiguation-2026-06-04.md) | `production_like_non_oracle_fixture_slice` | Local React adversarial V2 fixture with sanitized aggregate report; no live provider/model call. | Supersedes the 2026-06-04 source-disambiguation row that exposed 30 lexical near-miss false positives; does not supersede the 2026-05-31 oracle/bad-control report. | Broad semantic near-miss understanding, live model quality, wild VCS corpus quality, private real-history continuity quality, or license-safe redistribution of the local fixture. |
| `track_s.semantic_robustness_public_fixture` | Public-safe Track S diagnostic: `quality_gate_ok=true`; S1 `decision_stability_rate=1.0`, `false_evidence_escalation_count=0`; S2 `top_k_survival_rate=1.0`; S3 `hard_negative_suppression_rate=1.0`, `explicit_negation_violation_count=0`, `stale_as_current_count=0`, `source_evidence_over_escalation_count=0`. | 2026-06-09 | [`semantic-robustness-track-s.md`](benchmarks/semantic-robustness-track-s.md) | `public_safe_deterministic_diagnostic` | Track S public fixtures over Track A prompt-hook gate behavior and Track B local source-retrieval behavior; no live LLM judge or private text. | Supersedes the initial #747 diagnostic reading that exposed explicit-negation and superseded-currentness failures. | Human-level semantic understanding, Track A/B replacement, live semantic-model quality, proxy-model truth, broad real-history robustness, or private-history recall quality. |
| `dream.private_large_history_diagnostic` | Selected private ready-pack Dream eval: 18 packs; model-backed run with provider/default thinking and no explicit max-token cap produced source-thread coverage delta 1.6111, structural reflection-ready delta 616, bridge-claim coverage delta 1.0; historical shadow replay had 0 delivered events, 1 dream eligible exposure, and 1 attributed reminder; E2E50 scan found 17/20 requested candidate seeds and local annotation retained 4 gold-seed plus 2 calibration candidates; agency host-timing replay passed 5 deterministic cases; coding decision-shadow Tracks A-E passed; invalid `--semantic-workers default` run had 15 semantic calls but 0 available workers before the worker-validation fix. | 2026-06-04 | [`dream-private-large-history-diagnostic-2026-06-04.md`](dream/dream-private-large-history-diagnostic-2026-06-04.md) | `selected_private_history_offline_diagnostic` | Local sanitized aggregate private-history diagnostic for #158/#164; no private text, raw source refs, thread ids, message ids, or absolute paths checked in. | Updates the 2026-05-31 Dream private-history evidence with corrected no-cap/provider-thinking run, E2E50 local annotation, host-timing/coding-shadow deterministic proxy evidence, and live semantic worker root-cause diagnosis. | Causal real-user behavior lift, general Dream quality, full private-history coverage, safe delivered Dream treatment, completed 20/50-case E2E50 benchmark quality, live host timing or annoyance lift, private-history coding decision-shadow behavior lift, or live semantic-model quality from the invalid-worker run. |
| `cognitive_load.private_history_calibration_2026_06_08` | Public-safe private-history aggregate scan: 100 local registry threads, 5,268 clean-source message rows, 82,695 clean-source event rows, 76 signal-bearing threads, 26,505 load signal events, 26,035 sidecar entries, max boost 0.16, decay coverage 1.0, and 0 over-personalization emissions. | 2026-06-08 | [`cognitive-load-private-history-calibration-2026-06-08.md`](cognitive-load-private-history-calibration-2026-06-08.md) | `private_history_aggregate_diagnostic` | Local clean-source registry aggregate for #575; checked-in evidence is aggregate-only with no private text, raw source refs, local paths, raw command text, thread ids, or message ids. | First private-history calibration row for the cognitive-load sidecar. | Live hook capture, delivered host timing, host-timing quality, false-positive rate, caution-hint usefulness, user-visible recall improvement, source truth, semantic relevance, affect, stress, identity, or personality truth from load signals. |
| `episode_arc.private_history_adjudication_2026_06_08` | Public-safe private-history aggregate scan: 100 local registry threads, 5,164 clean-source message rows, 82,965 behavior event rows, 5,052 coding decision candidates, 1,851 rejected-route candidates/arcs, 684 complete rejected-route arcs connected to nearby failed behavior, and 1,167 gappy single-point arcs. | 2026-06-08 | [`episode-arc-private-history-adjudication-2026-06-08.md`](episode-arc-private-history-adjudication-2026-06-08.md) | `private_history_aggregate_diagnostic` | Local clean-source registry aggregate for #663; checked-in evidence is aggregate-only with no private text, raw command text, source refs, source-ref hash samples, event ids, thread ids, or local paths. | First private-history adjudication row for Episode/Arc rejected-route read-models. | Broader #663 owner completion, live host behavior lift, user-visible recall lift, current rejected-route validity without source reopen, private-history generality beyond this registry, or Episode/Arc as a new truth layer. |

## Supersession Notes

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
  The 2026-06-09 expansion separately reports FTS5 trigram, production hybrid,
  and measured `cjk_aware_sidecar` behavior. It exposes a production compact-CJK
  gap while showing that lightweight query chunks can recover the case; it does
  not supersede the real-history FTS5 row and must not be treated as a broad
  Chinese semantic-search claim.
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
  strict-config MCP reachability is positive live-host evidence; the persistent
  local Claude Code MCP config is currently blocked by a #1021
  `bad_command_path` / `configured_arg_path_missing` diagnostic and must not be
  described as healthy until a later dated smoke supersedes it.
- The Claude Code hooks contract row is a scoped synthetic contract, not
  real-host firing evidence. It retires the vague "Claude Code hooks" caveat by
  proving the public status/dry-run/smoke surface and fail-open
  `UserPromptSubmit` / `Stop` handler behavior, while preserving event-level
  cannot-claim boundaries for real host firing, settings mutation, tool payload
  capture, and compaction summary handling.
- The live semantic route-actionability row is the matching public live smoke
  for high-confidence semantic hits. It records that guarded model-only
  `evidence` became `source_required` / `reopenable_route` with zero manual
  query invention in that cohort; it does not itself measure bounded evidence
  after source reopen or private-registry quality.
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
- The Episode/Arc private-history row is an aggregate diagnostic over rejected
  route chains. It shows real local chain material exists and gappy rows are
  counted, but it does not prove sequence packets improve live host behavior or
  that old rejected routes remain current without source reopen.
