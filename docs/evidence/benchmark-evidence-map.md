# Benchmark And Evidence Map

This is the first-stop map for AIppocampus benchmark runners, smoke evidence,
and dated measurement records. It is intentionally a navigation page, not
another command ledger. Keep the latest claim boundary in
[`readiness/stage-0-5-readiness.md`](readiness/stage-0-5-readiness.md),
dated command evidence in
[`readiness/public-readiness-verification.md`](readiness/public-readiness-verification.md),
benchmark design details in
[`benchmarks/memory-decision-benchmark-plan.md`](benchmarks/memory-decision-benchmark-plan.md).
Community reports belong in
[`community-field-reports.md`](community-field-reports.md) until a maintainer
promotes a public-safe result into the official evidence flow.

## Folder Layout

- `readiness/` holds claim-boundary snapshots and release/public-readiness
  verification ledgers.
- `benchmarks/` holds benchmark methodology, public benchmark evidence, and
  public-safe fixture reports.
- `dream/` holds dream-worker shadow A/B and benchmark-corpus measurement
  records.
- `question/` holds question-extraction and question-tracking evidence records.
- `community-field-reports.md` defines how user-submitted reports are collected,
  labeled, and kept separate from official claims.

## Reading Order

1. Need to know what the repo can honestly claim today:
   [`readiness/stage-0-5-readiness.md`](readiness/stage-0-5-readiness.md).
2. Need the dated commands and summarized results behind those claims:
   [`readiness/public-readiness-verification.md`](readiness/public-readiness-verification.md).
3. Need benchmark methodology, track boundaries, and current diagnostic notes:
   [`benchmarks/memory-decision-benchmark-plan.md`](benchmarks/memory-decision-benchmark-plan.md).
4. Need LongMemEval source, commands, and published retrieval-only results:
   [`benchmarks/longmemeval.md`](benchmarks/longmemeval.md).
5. Need public corpus commands and local report boundaries:
   [`benchmark_corpus/README.md`](../../benchmark_corpus/README.md) and
   [`benchmark_corpus/sharegpt_manifest.json`](../../benchmark_corpus/sharegpt_manifest.json).
6. Need the public longitudinal pseudo-user benchmark for coding implicit
   knowledge:
   [`benchmarks/public-longitudinal-users.md`](benchmarks/public-longitudinal-users.md).
7. Need the latest dated public-longitudinal-users measurement report:
   [`benchmarks/public-longitudinal-users-measurement-2026-05-31.md`](benchmarks/public-longitudinal-users-measurement-2026-05-31.md).
8. Need the first real public VCS hard-event smoke:
   [`benchmarks/react-real-vcs-smoke-2026-05-31.md`](benchmarks/react-real-vcs-smoke-2026-05-31.md).
9. Need the 100+ gold real React VCS measurement with anti-drift negatives
   and counterfactual controls:
   [`benchmarks/react-real-vcs-100-gold-2026-05-31.md`](benchmarks/react-real-vcs-100-gold-2026-05-31.md).
10. Need the sharper React VCS adversarial controls for source authority,
   keyword drift, behavior-only support, and abstention:
   [`benchmarks/react-real-vcs-adversarial-v2-2026-05-31.md`](benchmarks/react-real-vcs-adversarial-v2-2026-05-31.md).
11. Need public-safe memory-pain fixture evidence:
   [`benchmarks/memory-pain-fixture-report.md`](benchmarks/memory-pain-fixture-report.md).
12. Need public-safe fresh-thread recall demo evidence:
   [`benchmarks/fresh-thread-recall-demo-2026-05-31.md`](benchmarks/fresh-thread-recall-demo-2026-05-31.md).
13. Need explicit recall-reminder shadow A/B evidence:
   [`dream/dream-live-shadow-ab-2026-05-30.md`](dream/dream-live-shadow-ab-2026-05-30.md).
14. Need public-corpus negative-control dream shadow evidence:
   [`dream/dream-live-shadow-benchmark-corpus-2026-05-31.md`](dream/dream-live-shadow-benchmark-corpus-2026-05-31.md).
15. Need live question-extraction axis-coverage evidence for GitHub #153:
   [`question/question-extraction-axis-coverage-2026-05-31.md`](question/question-extraction-axis-coverage-2026-05-31.md).
16. Need community-submitted runs, demos, known gaps, or field-report intake:
   [`community-field-reports.md`](community-field-reports.md) and the public
   [`/evidence/`](https://www.aippocampus.com/evidence/) page.

Research notes may include calibration context, but they are not claim ledgers.
Use them for background only until a result is linked back to the readiness
snapshot or dated verification ledger.

## Evidence Ownership

| Evidence type | Canonical owner | What belongs there |
| --- | --- | --- |
| Current claim boundary | `docs/evidence/readiness/stage-0-5-readiness.md` | Can-claim / cannot-claim status and missing proof. |
| Dated command ledger | `docs/evidence/readiness/public-readiness-verification.md` | Summarized commands, dates, pass/fail interpretation, and scope notes. |
| Benchmark design | `docs/evidence/benchmarks/memory-decision-benchmark-plan.md` | Track definitions, report shape, non-goals, and diagnostic interpretation. |
| LongMemEval evidence | `docs/evidence/benchmarks/longmemeval.md` and `benchmark_corpus/longmemeval_manifest.json` | Official sources, dataset checksums, dedicated runner commands, dated retrieval-only results, and claim boundaries. |
| Public longitudinal user evidence | `docs/evidence/benchmarks/public-longitudinal-users.md`, `docs/evidence/benchmarks/public-longitudinal-users-measurement-2026-05-31.md`, `docs/evidence/benchmarks/react-real-vcs-smoke-2026-05-31.md`, `docs/evidence/benchmarks/react-real-vcs-100-gold-2026-05-31.md`, `docs/evidence/benchmarks/react-real-vcs-adversarial-v2-2026-05-31.md`, `benchmark_corpus/public_longitudinal_users/`, and `benchmark_corpus/locomo_manifest.json` | Public synthetic coding implicit-knowledge scoring-contract smoke, LoCoMo same-conversation control users, deterministic scorers, VCS future-event recall roadmap, dated measurements, real public VCS hard-event smoke, 100+ gold React VCS measurement with anti-drift/counterfactual controls, sharper React VCS adversarial controls, and external-prediction contracts. |
| Corpus setup | `benchmark_corpus/README.md` and `benchmark_corpus/sharegpt_manifest.json` | Public corpus conversion commands, ignored local outputs, and corpus-specific claim boundaries. |
| Demo fixture report | `docs/evidence/benchmarks/memory-pain-fixture-report.md` | Public-safe fixture families and their narrow claim boundary. |
| Fresh-thread recall demo evidence | `docs/evidence/benchmarks/fresh-thread-recall-demo-2026-05-31.md` | Public-safe three-arm fresh-thread recall flows, negative controls, and source-reopen boundaries for #285. |
| Dream live shadow A/B reminder evidence | `docs/evidence/dream/dream-live-shadow-ab-2026-05-30.md` | Dated aggregate run for explicit recall-reminder frequency, shadow assignment, nearest-prior exposure attribution, and delivered-vs-shadow claim boundaries. |
| Dream benchmark-corpus shadow evidence | `docs/evidence/dream/dream-live-shadow-benchmark-corpus-2026-05-31.md` | Dated public-corpus negative-control run for explicit reminder frequency and potential dream-only over-personalization activation. |
| Question extraction axis coverage evidence | `docs/evidence/question/question-extraction-axis-coverage-2026-05-31.md` | Dated live no-write aggregate field-presence run for GitHub #153 and its prompt/repair/telemetry fix boundary. |
| Community field reports | `docs/evidence/community-field-reports.md`, the public `/evidence/` page, and GitHub Discussions | Public-safe user and contributor reports. These are community signals until reviewed and promoted into official benchmark evidence, readiness ledgers, or known-gap docs. |
| Raw / generated artifacts | `.tmp/` or `benchmark_corpus/reports/` | Local JSON outputs, historical benchmark snapshots, run-history diff artifacts, and case packs. Keep them gitignored unless a small public subset is deliberately promoted. |

## Benchmark Runners

These repository-level runners live under `benchmarks/aippocampus/`. Every new
benchmark runner should be added here and linked to its dated evidence owner.

| Surface | Entrypoint | Reads / updates |
| --- | --- | --- |
| Shared benchmark uncertainty helper | `benchmarks/aippocampus/benchmark_statistics.py` | `docs/evidence/benchmarks/memory-decision-benchmark-plan.md` |
| One-command baseline suite, profile ladder, and threshold metadata | `benchmarks/aippocampus/benchmark_suite.py` | `docs/evidence/benchmarks/memory-decision-benchmark-plan.md`, `docs/evidence/readiness/public-readiness-verification.md` |
| Benchmark run-history diff and regression guardrail | `benchmarks/aippocampus/benchmark_run_history_diff.py` | `docs/evidence/benchmarks/memory-decision-benchmark-plan.md`, `.tmp/` or `benchmark_corpus/reports/` |
| Track A memory decision gate | `benchmarks/aippocampus/benchmark_memory_decision_gate.py` | `docs/evidence/benchmarks/memory-decision-benchmark-plan.md`, `docs/evidence/benchmarks/memory-pain-fixture-report.md` |
| Track B source-evidence retrieval wrapper | `benchmarks/aippocampus/benchmark_source_evidence_retrieval.py` | `docs/evidence/benchmarks/memory-decision-benchmark-plan.md`, `benchmark_corpus/README.md` |
| Coding decision-shadow Tracks A-E | `benchmarks/aippocampus/benchmark_coding_decision_shadow.py` | `docs/evidence/benchmarks/memory-decision-benchmark-plan.md`, `docs/research/agent-coding-context-analysis.md` |
| LongMemEval retrieval-only benchmark | `benchmarks/aippocampus/benchmark_longmemeval.py` | `docs/evidence/benchmarks/longmemeval.md`, `benchmark_corpus/longmemeval_manifest.json` |
| LoCoMo public longitudinal-users control | `benchmarks/aippocampus/benchmark_locomo_public_users.py` | `docs/evidence/benchmarks/public-longitudinal-users.md`, `benchmark_corpus/README.md`, `benchmark_corpus/locomo_manifest.json` |
| Public longitudinal pseudo-user coding implicit-knowledge contract smoke | `benchmarks/aippocampus/benchmark_public_longitudinal_users.py` | `docs/evidence/benchmarks/public-longitudinal-users.md`, `benchmark_corpus/public_longitudinal_users/README.md` |
| VCS future-event recall benchmark scaffold | `benchmarks/aippocampus/benchmark_vcs_future_event_recall.py` | `docs/evidence/benchmarks/public-longitudinal-users.md`, `benchmark_corpus/public_longitudinal_users/README.md` |
| VCS / rollout future-event fixture builder | `benchmarks/aippocampus/build_vcs_future_event_fixture.py` | `docs/evidence/benchmarks/public-longitudinal-users.md`, `benchmark_corpus/public_longitudinal_users/README.md` |
| FTS5 real-history recall | `benchmarks/aippocampus/benchmark_fts5_recall.py` | `docs/evidence/readiness/public-readiness-verification.md`, `docs/planning/next-iteration-plan.md` |
| Track C payload fidelity | `benchmarks/aippocampus/benchmark_payload_fidelity.py` | `docs/evidence/benchmarks/memory-decision-benchmark-plan.md`, `docs/evidence/benchmarks/memory-pain-fixture-report.md` |
| Track D synthetic compaction continuity | `benchmarks/aippocampus/benchmark_compaction_continuity.py` | `docs/evidence/benchmarks/memory-decision-benchmark-plan.md`, `docs/evidence/readiness/public-readiness-verification.md` |
| Continuous-memory attribution arms, pre-registration, cost/harm ledger, and scenario provenance/holdout controls | `benchmarks/aippocampus/benchmark_continuous_memory_arms.py` | `docs/evidence/benchmarks/memory-decision-benchmark-plan.md`, #378/#407/#408/#409/#410 |
| Optional live semantic gate | `benchmarks/aippocampus/benchmark_live_semantic_gate.py` | `docs/evidence/benchmarks/memory-decision-benchmark-plan.md`, `benchmark_corpus/README.md` |
| Fresh-thread public-safe recall demo | `benchmarks/aippocampus/benchmark_fresh_thread_recall_demo.py` | `docs/evidence/benchmarks/fresh-thread-recall-demo-2026-05-31.md`, `docs/guides/demo-scenarios.md` |
| Structured cognitive portrait | `benchmarks/aippocampus/benchmark_cognitive_portrait.py` | `docs/research/compact-activation-signals.md`, `docs/evidence/benchmarks/memory-decision-benchmark-plan.md` |
| Question-aware real-history structural benchmark | `benchmarks/aippocampus/benchmark_question_aware_real_history.py` | `docs/architecture/question-tracking-subconscious.md`, `docs/research/compact-activation-signals.md`, `docs/planning/next-iteration-plan.md`, `docs/evidence/readiness/stage-0-5-readiness.md`, `docs/evidence/benchmarks/memory-decision-benchmark-plan.md` |
| Question tracking selected-fixture calibration | `benchmarks/aippocampus/benchmark_question_tracking_calibration.py` | `docs/architecture/question-tracking-subconscious.md`, `docs/planning/technical-differentiation-analysis.md` |
| Warm ambient recall benchmark | `benchmarks/aippocampus/benchmark_warm_ambient_recall.py` | `docs/research/ambient-associative-recall.md`, `benchmark_corpus/README.md` |
| Warm ambient parameter sweep | `benchmarks/aippocampus/benchmark_warm_ambient_sweep.py` | `docs/research/ambient-associative-recall.md`, `docs/evidence/benchmarks/memory-decision-benchmark-plan.md` |
| Warm ambient case-pack builder | `benchmarks/aippocampus/build_warm_ambient_trace_cases.py` | `benchmark_corpus/README.md` |

Benchmark mirror tests live in `tests/aippocampus/test_benchmark_*.py`. The
test tier is selected with `python tools/aippocampus/run_tests.py --tier benchmark`.

## Smoke And Live Evidence Surfaces

These scripts are stronger or broader than unit tests, but each has a narrow
claim boundary. Link results to the dated verification ledger instead of
pasting raw JSON into multiple docs.

| Surface | Entrypoint | Primary evidence owner |
| --- | --- | --- |
| Unified Stage 0-5 public-readiness smoke | `tools/aippocampus/smoke/run_stage_0_5_smoke.py` | `docs/evidence/readiness/public-readiness-verification.md` |
| Prompt-hook regression smoke | `tools/aippocampus/smoke/simulate_prompt_hook.py` | `docs/evidence/benchmarks/memory-decision-benchmark-plan.md` |
| Prompt-hook latency probe | `tools/aippocampus/smoke/smoke_prompt_hook_latency.py` | `docs/evidence/benchmarks/memory-decision-benchmark-plan.md`, `skills/aippocampus/references/ambient-hooks.md` |
| Multilingual prompt-hook smoke | `tools/aippocampus/smoke/simulate_multilingual_prompt_hook.py` | `docs/evidence/benchmarks/memory-decision-benchmark-plan.md` |
| Semantic paraphrase reuse smoke | `tools/aippocampus/smoke/smoke_semantic_paraphrase_reuse.py` | `docs/evidence/benchmarks/memory-decision-benchmark-plan.md` |
| Real Codex long-session continuity smoke | `tools/aippocampus/smoke/smoke_codex_long_session_continuity.py` | `docs/evidence/readiness/public-readiness-verification.md` |
| Claude Code MCP host probe | `tools/aippocampus/smoke/smoke_claude_code_mcp_host.py` | `docs/evidence/readiness/public-readiness-verification.md` |
| Claude Code local-history parser smoke | `tools/aippocampus/smoke/smoke_claude_code_history.py` | `docs/evidence/readiness/public-readiness-verification.md` |
| Synthetic cross-agent continuity smoke | `tools/aippocampus/smoke/smoke_cross_agent_continuity.py` | `docs/evidence/readiness/public-readiness-verification.md` |
| Life-wide registry aggregate smoke | `tools/aippocampus/smoke/smoke_life_wide_registry.py` | `docs/evidence/readiness/stage-0-5-readiness.md` |
| Real-history memory-pain prompt-hook smoke | `tools/aippocampus/smoke/smoke_memory_pain_prompt_hook.py` | `docs/evidence/benchmarks/memory-decision-benchmark-plan.md` |
| Real-history semantic scope smoke | `tools/aippocampus/smoke/smoke_semantic_scope_real_history.py` | `docs/evidence/readiness/stage-0-5-readiness.md` |
| Semantic sidecar source-review smoke | `tools/aippocampus/smoke/smoke_semantic_scope_source_review.py` | `docs/evidence/readiness/stage-0-5-readiness.md` |
| Selected source-evidence recall eval | `tools/aippocampus/smoke/smoke_source_evidence_recall_eval.py` | `docs/evidence/readiness/stage-0-5-readiness.md` |
| Optional live question-confirmation smoke | `tools/aippocampus/smoke/smoke_question_confirmation_live.py` | `docs/architecture/question-tracking-subconscious.md`, `docs/evidence/readiness/stage-0-5-readiness.md` |
| Synthetic GB-scale capacity smoke | `tools/aippocampus/smoke/smoke_synthetic_scale_capacity.py` | `docs/architecture/gb-scale-roadmap.md` |
| Synthetic question-tracking scale smoke | `tools/aippocampus/smoke/smoke_question_tracking_scale.py` | `docs/architecture/question-tracking-subconscious.md`, `docs/architecture/gb-scale-roadmap.md` |
| Single-machine cross-device sync smoke | `tools/aippocampus/smoke/smoke_cross_device_sync.py` | `docs/evidence/readiness/public-readiness-verification.md` |
| HTTP object-storage sync smoke | `tools/aippocampus/smoke/smoke_object_storage_sync.py` | `docs/evidence/readiness/public-readiness-verification.md` |
| Docker / WSL alternate-runtime sync smoke | `tools/aippocampus/smoke/smoke_alternate_runtime_sync.py` | `docs/evidence/readiness/public-readiness-verification.md` |
| Real-provider encrypted object-storage smoke | `tools/aippocampus/smoke/smoke_real_provider_encrypted_sync.py` | `docs/evidence/readiness/public-readiness-verification.md` |
| Package-level plugin install smoke | `plugins/aippocampus/smoke_plugin_install.py` | `docs/evidence/readiness/public-readiness-verification.md` |
| Real Codex app-server plugin smoke | `plugins/aippocampus/smoke_real_codex_host.py` | `docs/evidence/readiness/public-readiness-verification.md` |

## Update Rules

- Add every new `benchmarks/aippocampus/benchmark_*.py` runner to this map.
- Add support builders that create benchmark case packs, such as
  `benchmarks/aippocampus/build_warm_ambient_trace_cases.py`, when other docs
  tell people to run them.
- Add every new `tools/aippocampus/smoke/*.py` evidence runner except local
  import helpers such as `_paths.py`.
- Add plugin or client smoke scripts when their result is used for release,
  public-readiness, or distribution claims.
- Put raw outputs, large case packs, private registry-derived samples, and live
  provider reports under `.tmp/` or ignored report directories.
- If a result changes what can be claimed, update
  `docs/evidence/readiness/stage-0-5-readiness.md`. If it only records a dated
  run, update `docs/evidence/readiness/public-readiness-verification.md`.

The docs-health guard checks that benchmark and smoke entrypoints are listed on
this page, so a new runner should not become invisible to the next agent.
