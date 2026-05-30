# Benchmark And Evidence Map

This is the first-stop map for AIppocampus benchmark runners, smoke evidence,
and dated measurement records. It is intentionally a navigation page, not
another command ledger. Keep the latest claim boundary in
[`stage-0-5-readiness.md`](stage-0-5-readiness.md), dated command evidence in
[`public-readiness-verification.md`](public-readiness-verification.md), and
benchmark design details in
[`memory-decision-benchmark-plan.md`](memory-decision-benchmark-plan.md).

## Reading Order

1. Need to know what the repo can honestly claim today:
   [`stage-0-5-readiness.md`](stage-0-5-readiness.md).
2. Need the dated commands and summarized results behind those claims:
   [`public-readiness-verification.md`](public-readiness-verification.md).
3. Need benchmark methodology, track boundaries, and current diagnostic notes:
   [`memory-decision-benchmark-plan.md`](memory-decision-benchmark-plan.md).
4. Need public corpus commands and local report boundaries:
   [`benchmark_corpus/README.md`](../../benchmark_corpus/README.md) and
   [`benchmark_corpus/sharegpt_manifest.json`](../../benchmark_corpus/sharegpt_manifest.json).
5. Need public-safe memory-pain fixture evidence:
   [`memory-pain-fixture-report.md`](memory-pain-fixture-report.md).
6. Need dream natural-prompt route/noise evidence:
   [`dream-natural-prompt-large-sample-2026-05-30.md`](dream-natural-prompt-large-sample-2026-05-30.md).
7. Need explicit recall-reminder shadow A/B evidence:
   [`dream-live-shadow-ab-2026-05-30.md`](dream-live-shadow-ab-2026-05-30.md).
8. Need public-corpus negative-control dream shadow evidence:
   [`dream-live-shadow-benchmark-corpus-2026-05-31.md`](dream-live-shadow-benchmark-corpus-2026-05-31.md).

Research notes may include calibration context, but they are not claim ledgers.
Use them for background only until a result is linked back to the readiness
snapshot or dated verification ledger.

## Evidence Ownership

| Evidence type | Canonical owner | What belongs there |
| --- | --- | --- |
| Current claim boundary | `docs/evidence/stage-0-5-readiness.md` | Can-claim / cannot-claim status and missing proof. |
| Dated command ledger | `docs/evidence/public-readiness-verification.md` | Summarized commands, dates, pass/fail interpretation, and scope notes. |
| Benchmark design | `docs/evidence/memory-decision-benchmark-plan.md` | Track definitions, report shape, non-goals, and diagnostic interpretation. |
| Corpus setup | `benchmark_corpus/README.md` and `benchmark_corpus/sharegpt_manifest.json` | Public corpus conversion commands, ignored local outputs, and corpus-specific claim boundaries. |
| Demo fixture report | `docs/evidence/memory-pain-fixture-report.md` | Public-safe fixture families and their narrow claim boundary. |
| Dream natural-prompt route/noise evidence | `docs/evidence/dream-natural-prompt-large-sample-2026-05-30.md` | Dated aggregate run for manual-reminder reduction, negative prompt noise, overbroad fanout, and strong-claim source-reopen gates. |
| Dream live shadow A/B reminder evidence | `docs/evidence/dream-live-shadow-ab-2026-05-30.md` | Dated aggregate run for explicit recall-reminder frequency, shadow assignment, nearest-prior exposure attribution, and delivered-vs-shadow claim boundaries. |
| Dream benchmark-corpus shadow evidence | `docs/evidence/dream-live-shadow-benchmark-corpus-2026-05-31.md` | Dated public-corpus negative-control run for explicit reminder frequency and potential dream-only over-personalization activation. |
| Raw / generated artifacts | `.tmp/` or `benchmark_corpus/reports/` | Local JSON outputs and case packs. Keep them gitignored unless a small public subset is deliberately promoted. |

## Benchmark Runners

These repository-level runners live under `benchmarks/aippocampus/`. Every new
benchmark runner should be added here and linked to its dated evidence owner.

| Surface | Entrypoint | Reads / updates |
| --- | --- | --- |
| One-command baseline suite | `benchmarks/aippocampus/benchmark_suite.py` | `docs/evidence/memory-decision-benchmark-plan.md`, `docs/evidence/public-readiness-verification.md` |
| Track A memory decision gate | `benchmarks/aippocampus/benchmark_memory_decision_gate.py` | `docs/evidence/memory-decision-benchmark-plan.md`, `docs/evidence/memory-pain-fixture-report.md` |
| Track B source-evidence retrieval wrapper | `benchmarks/aippocampus/benchmark_source_evidence_retrieval.py` | `docs/evidence/memory-decision-benchmark-plan.md`, `benchmark_corpus/README.md` |
| FTS5 real-history recall | `benchmarks/aippocampus/benchmark_fts5_recall.py` | `docs/evidence/public-readiness-verification.md`, `docs/planning/next-iteration-plan.md` |
| Track C payload fidelity | `benchmarks/aippocampus/benchmark_payload_fidelity.py` | `docs/evidence/memory-decision-benchmark-plan.md`, `docs/evidence/memory-pain-fixture-report.md` |
| Track D synthetic compaction continuity | `benchmarks/aippocampus/benchmark_compaction_continuity.py` | `docs/evidence/memory-decision-benchmark-plan.md`, `docs/evidence/public-readiness-verification.md` |
| Optional live semantic gate | `benchmarks/aippocampus/benchmark_live_semantic_gate.py` | `docs/evidence/memory-decision-benchmark-plan.md`, `benchmark_corpus/README.md` |
| Structured cognitive portrait | `benchmarks/aippocampus/benchmark_cognitive_portrait.py` | `docs/research/compact-activation-signals.md`, `docs/evidence/memory-decision-benchmark-plan.md` |
| Question-aware real-history structural benchmark | `benchmarks/aippocampus/benchmark_question_aware_real_history.py` | `docs/architecture/question-tracking-subconscious.md`, `docs/research/compact-activation-signals.md`, `docs/planning/next-iteration-plan.md`, `docs/evidence/stage-0-5-readiness.md`, `docs/evidence/memory-decision-benchmark-plan.md` |
| Question tracking selected-fixture calibration | `benchmarks/aippocampus/benchmark_question_tracking_calibration.py` | `docs/architecture/question-tracking-subconscious.md`, `docs/planning/technical-differentiation-analysis.md` |
| Warm ambient recall benchmark | `benchmarks/aippocampus/benchmark_warm_ambient_recall.py` | `docs/research/ambient-associative-recall.md`, `benchmark_corpus/README.md` |
| Warm ambient parameter sweep | `benchmarks/aippocampus/benchmark_warm_ambient_sweep.py` | `docs/research/ambient-associative-recall.md`, `docs/evidence/memory-decision-benchmark-plan.md` |
| Warm ambient case-pack builder | `benchmarks/aippocampus/build_warm_ambient_trace_cases.py` | `benchmark_corpus/README.md` |

Benchmark mirror tests live in `tests/aippocampus/test_benchmark_*.py`. The
test tier is selected with `python tools/aippocampus/run_tests.py --tier benchmark`.

## Smoke And Live Evidence Surfaces

These scripts are stronger or broader than unit tests, but each has a narrow
claim boundary. Link results to the dated verification ledger instead of
pasting raw JSON into multiple docs.

| Surface | Entrypoint | Primary evidence owner |
| --- | --- | --- |
| Unified Stage 0-5 public-readiness smoke | `tools/aippocampus/smoke/run_stage_0_5_smoke.py` | `docs/evidence/public-readiness-verification.md` |
| Prompt-hook regression smoke | `tools/aippocampus/smoke/simulate_prompt_hook.py` | `docs/evidence/memory-decision-benchmark-plan.md` |
| Multilingual prompt-hook smoke | `tools/aippocampus/smoke/simulate_multilingual_prompt_hook.py` | `docs/evidence/memory-decision-benchmark-plan.md` |
| Real Codex long-session continuity smoke | `tools/aippocampus/smoke/smoke_codex_long_session_continuity.py` | `docs/evidence/public-readiness-verification.md` |
| Claude Code MCP host probe | `tools/aippocampus/smoke/smoke_claude_code_mcp_host.py` | `docs/evidence/public-readiness-verification.md` |
| Claude Code local-history parser smoke | `tools/aippocampus/smoke/smoke_claude_code_history.py` | `docs/evidence/public-readiness-verification.md` |
| Synthetic cross-agent continuity smoke | `tools/aippocampus/smoke/smoke_cross_agent_continuity.py` | `docs/evidence/public-readiness-verification.md` |
| Life-wide registry aggregate smoke | `tools/aippocampus/smoke/smoke_life_wide_registry.py` | `docs/evidence/stage-0-5-readiness.md` |
| Real-history memory-pain prompt-hook smoke | `tools/aippocampus/smoke/smoke_memory_pain_prompt_hook.py` | `docs/evidence/memory-decision-benchmark-plan.md` |
| Real-history semantic scope smoke | `tools/aippocampus/smoke/smoke_semantic_scope_real_history.py` | `docs/evidence/stage-0-5-readiness.md` |
| Semantic sidecar source-review smoke | `tools/aippocampus/smoke/smoke_semantic_scope_source_review.py` | `docs/evidence/stage-0-5-readiness.md` |
| Selected source-evidence recall eval | `tools/aippocampus/smoke/smoke_source_evidence_recall_eval.py` | `docs/evidence/stage-0-5-readiness.md` |
| Optional live question-confirmation smoke | `tools/aippocampus/smoke/smoke_question_confirmation_live.py` | `docs/architecture/question-tracking-subconscious.md`, `docs/evidence/stage-0-5-readiness.md` |
| Synthetic GB-scale capacity smoke | `tools/aippocampus/smoke/smoke_synthetic_scale_capacity.py` | `docs/architecture/gb-scale-roadmap.md` |
| Synthetic question-tracking scale smoke | `tools/aippocampus/smoke/smoke_question_tracking_scale.py` | `docs/architecture/question-tracking-subconscious.md`, `docs/architecture/gb-scale-roadmap.md` |
| Single-machine cross-device sync smoke | `tools/aippocampus/smoke/smoke_cross_device_sync.py` | `docs/evidence/public-readiness-verification.md` |
| HTTP object-storage sync smoke | `tools/aippocampus/smoke/smoke_object_storage_sync.py` | `docs/evidence/public-readiness-verification.md` |
| Docker / WSL alternate-runtime sync smoke | `tools/aippocampus/smoke/smoke_alternate_runtime_sync.py` | `docs/evidence/public-readiness-verification.md` |
| Real-provider encrypted object-storage smoke | `tools/aippocampus/smoke/smoke_real_provider_encrypted_sync.py` | `docs/evidence/public-readiness-verification.md` |
| Package-level plugin install smoke | `plugins/aippocampus/smoke_plugin_install.py` | `docs/evidence/public-readiness-verification.md` |
| Real Codex app-server plugin smoke | `plugins/aippocampus/smoke_real_codex_host.py` | `docs/evidence/public-readiness-verification.md` |

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
  `docs/evidence/stage-0-5-readiness.md`. If it only records a dated run, update
  `docs/evidence/public-readiness-verification.md`.

The docs-health guard checks that benchmark and smoke entrypoints are listed on
this page, so a new runner should not become invisible to the next agent.
