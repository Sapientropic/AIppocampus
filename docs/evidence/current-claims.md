# Current Evidence Claims

This is the current-claims snapshot for benchmark and readiness numbers that
are easy to over-read when old dated ledgers still say "current" in their local
context. It is not a command ledger and it does not replace source reports.

Snapshot date: 2026-06-04.

Rules:

- A value is current only for the `run_date`, `cohort`, and `claim_level` named
  in its row.
- Dated evidence remains in
  [`docs/evidence/readiness/public-readiness-verification.md`](readiness/public-readiness-verification.md)
  and detailed benchmark methodology remains in
  [`docs/evidence/benchmarks/memory-decision-benchmark-plan.md`](benchmarks/memory-decision-benchmark-plan.md).
- Stage-level can-claim / cannot-claim status remains in
  [`docs/evidence/readiness/stage-0-5-readiness.md`](readiness/stage-0-5-readiness.md).
- Demo caveats in
  [`docs/guides/demo-scenarios.md`](../guides/demo-scenarios.md) are
  claim-boundary inputs, not standalone benchmark proof.

## Current Claim Snapshot

| metric_id | current_value | run_date | source_report | claim_level | cohort | supersedes / superseded_by | cannot_claim |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `registry.local_real_history_aggregate` | 964 clean-source/index/graph-backed threads; 110 scope-labeled threads; 88 non-technical life-wide threads; 244 semantic sidecar rows across 46 threads; all eight canonical labels observed. | 2026-05-30 | [`public-readiness-verification.md`, #55 Stage 2 evidence](readiness/public-readiness-verification.md#2026-05-30-issues-5556-evidence-closeout) | `first_pass_real_history_slice` | Local real-history registry aggregate; aggregate-only smoke output. | Supersedes the older 949-thread aggregate paragraph for public currentness. | Full-history refresh, semantic completeness, label correctness without clean-source review, or private-text disclosure. |
| `semantic_sidecar.aggregate_materialized_rows` | 244 semantic sidecar rows across 46 threads, with all eight canonical labels observed. | 2026-05-30 | [`public-readiness-verification.md`, #55 Stage 2 evidence](readiness/public-readiness-verification.md#2026-05-30-issues-5556-evidence-closeout) | `first_pass_real_history_slice` | Local real-history dynamic semantic sidecar observation. | Supersedes the older 2-thread / 5-row strict-survival number for aggregate materialized coverage only. | Global semantic correctness, human review, complete life-wide labeling, or relaxed materializer gates. |
| `semantic_sidecar.strict_survival_snapshot` | Historical strict-survival slice: 5 rows across 2 real clean-source threads and 5 semantic latest timeline turns. | 2026-05-29 | [`public-readiness-verification.md`, earlier Stage 2 closeout](readiness/public-readiness-verification.md) and [`memory-decision-benchmark-plan.md`](benchmarks/memory-decision-benchmark-plan.md) | `historical_strict_survival_snapshot` | Strict per-label evidence gate after source-review tightening. | Superseded by `semantic_sidecar.aggregate_materialized_rows` for aggregate coverage; retained as a stricter survival baseline. | Latest aggregate coverage, global Stage 2 correctness, or proof that suppressed labels are safe to restore. |
| `semantic_sidecar.source_review_green_gate` | 24 selected semantic sidecar label cases reviewed; 24/24 passed; `pass_rate=1.0`; no live model failures. | 2026-05-30 | [`public-readiness-verification.md`, #55 Stage 2 evidence](readiness/public-readiness-verification.md#2026-05-30-issues-5556-evidence-closeout) | `selected_source_review_green_gate` | Selected strict semantic sidecar labels reviewed through the live DeepSeek-compatible source-review smoke. | Supersedes the older 5-case strict-review pass as the selected green gate. | Human review, broad correctness, or full-history semantic quality. |
| `semantic_sidecar.source_review_diagnostic` | 96 selected cases reviewed; 88 passed; `pass_rate=0.9167`; `failed_label_categories=[]`; one live model partial failure. | 2026-05-30 | [`public-readiness-verification.md`, #55 Stage 2 evidence](readiness/public-readiness-verification.md#2026-05-30-issues-5556-evidence-closeout) | `diagnostic_only` | Broader selected source-review smoke with live provider behavior. | Supersedes vague "96-case green" wording; it is not a green gate until rerun cleanly. | Pass/fail release gate, human review, or provider-independent quality. |
| `track_b.private_semantic_sidecar_required` | 100 selected private real-history cases; 97/100 top-5 hits; 0.97 hit rate; 3 `rank_below_top_k` failures after the 45-thread / 243-row semantic-sidecar refresh. | 2026-05-29 | [`memory-decision-benchmark-plan.md`, private real-history Track B wrapper](benchmarks/memory-decision-benchmark-plan.md#track-b-source-evidence-retrieval) | `private_bounded_track_b_slice` | Maintainer-only private real-history semantic-sidecar-required source-evidence slice. | Supersedes the sparse-pool blocker for this selected slice only. | Public benchmark score, real-user gate quality, full semantic completeness, or live semantic-model quality. |
| `fts5.real_history_recall_2026_05_29` | Post-repair 100 selected source-backed cases; FTS5 91/100 top-1, 100/100 top-5, 100/100 top-10; production hybrid 100/100 top-10. | 2026-05-29 | [`public-readiness-verification.md`, FTS5 real-history recall benchmark](readiness/public-readiness-verification.md) and [`memory-decision-benchmark-plan.md`](benchmarks/memory-decision-benchmark-plan.md) | `bounded_real_history_regression_smoke` | Local 949-thread real-history registry slice after stale SQLite index repair. | Superseded only by a newer dated FTS5 real-history run. | Natural-language user-query quality, private text disclosure, or broad product recall quality. |
| `demo_scenarios.claim_boundaries` | Public-safe demo scenarios show product shape; their `Cannot claim` lines are claim-boundary sources for demos. | 2026-06-03 | [`docs/guides/demo-scenarios.md`](../guides/demo-scenarios.md) | `claim_boundary_source` | Public example bundle, public-safe demo commands, and explicit live/smoke demo flows. | Not a metric row; it routes demo caveats into evidence governance. | Official benchmark proof, readiness metric upgrades, or private real-history performance. |
| `recall_navigation.progressive_route_follow_through` | Progressive `recall_context -> recall_deepen` arm: `route_actionability_rate=1.0`, `source_reopen_follow_through_rate=0.75` (3/4 attempted route reopens reached expected clean-source refs), `avg_manual_query_invention_count=0.0`; foreground packet candidate ref follow-through reached the expected fixture source with `foreground_manual_query_invention_count=0`; stale-handle negative rejected before source use. | 2026-06-04 | [`recall-navigation-comparison-2026-06-03.md`](benchmarks/recall-navigation-comparison-2026-06-03.md) | `public_safe_deterministic_proxy` | Four public synthetic clean-source fixtures plus one foreground hook packet/cache fixture; all use temporary public-safe clean-source/index/cache data. | Updates the #465 comparison with a narrow #201 route-follow-through readout; does not supersede live #201 field reports. | Live user quality, broad default foreground first-turn or second-turn lift, production selector superiority, source-backed answer quality beyond the synthetic fixtures, or closing #201. |
| `react_vcs.production_like_source_disambiguation` | 60/60 gold true positives, `current_source_top_k_hit_rate=1.0`, `current_vs_stale_pairwise_win_rate=1.0`, `wrong_source_evidence_rate=0.0`, but `negative_false_positive_rate=0.5263` from 30 lexical near-miss false positives. | 2026-06-04 | [`react-real-vcs-production-like-disambiguation-2026-06-04.md`](benchmarks/react-real-vcs-production-like-disambiguation-2026-06-04.md) | `production_like_non_oracle_fixture_slice` | Local React adversarial V2 fixture with sanitized aggregate report; no live provider/model call. | Supersedes source-window-only interpretation for #254 source-disambiguation evidence; does not supersede the 2026-05-31 oracle/bad-control report. | Live model quality, wild VCS corpus quality, private real-history continuity quality, negative-control pass for lexical near-misses, or license-safe redistribution of the local fixture. |

## Supersession Notes

- The 2-thread / 5-row strict-survival slice remains useful because it records
  what survived stronger per-label evidence gates. It is no longer the current
  aggregate materialized semantic-sidecar coverage.
- The 24-case source-review row is the selected green gate. The 96-case row is
  broader but diagnostic because it had one live model partial failure.
- Metric families with multiple valid cohorts must name the cohort and date:
  public corpus, private real-history, selected source-review, aggregate
  registry smoke, and demo scenario caveats are separate evidence layers.
- The 2026-06-04 React VCS source-disambiguation row is intentionally split
  from the 2026-05-31 source-window oracle reports. Its current/effective
  source ranking succeeded on the adversarial source-authority tracks, while
  lexical near-miss anti-drift failed and must not be hidden by the source-hit
  metrics.
- The recall-navigation follow-through row is a deterministic source-navigation
  proxy only. It records that a route handle can be reopened through
  `recall_deepen` and that a foreground packet candidate ref can reopen one
  public fixture source; it is not evidence that the default foreground hook now
  improves vague first or second turns in real use.
