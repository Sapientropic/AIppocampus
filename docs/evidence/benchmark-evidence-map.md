# Benchmark And Evidence Map

Role: evidence navigation map.
Status: current owner for routing readers to benchmark/evidence owners; not a
numeric claim snapshot, command ledger, or runner priority registry.

This is the first-stop map for AIppocampus benchmark evidence only after a
reader knows what kind of evidence they need. Keep current numeric claims,
negative-result remediation, and supersession rules in
[`docs/evidence/current-claims.md`](current-claims.md), stage-level can-claim /
cannot-claim status in
[`readiness/stage-0-5-readiness.md`](readiness/stage-0-5-readiness.md), proof-slice maturity in
[`readiness/proof-slice-maturity.md`](readiness/proof-slice-maturity.md), dated command evidence in
[`readiness/public-readiness-verification.md`](readiness/public-readiness-verification.md),
benchmark design rationale in
[`benchmarks/design/README.md`](benchmarks/design/README.md), and detailed
runner methodology in
[`benchmarks/memory-decision-benchmark-plan.md`](benchmarks/memory-decision-benchmark-plan.md).
Community reports belong in
[`community-field-reports.md`](community-field-reports.md) until a maintainer
promotes a public-safe result into the official evidence flow.

## Start Here

| Reader question | First stop | Then use |
| --- | --- | --- |
| What can AIppocampus currently claim, and what failed? | [`current-claims.md`](current-claims.md) | Open the source report only for the row you need. |
| Which known benchmark result needs remediation? | [`current-claims.md#known-negative-results-and-remediation`](current-claims.md#known-negative-results-and-remediation) | Follow the linked issue before reading old dated reports. |
| Which benchmark or smoke should I run? | [`benchmarks/design/benchmark-priority-map.md`](benchmarks/design/benchmark-priority-map.md) | Use the default run profile and cannot-claim column there. |
| Which file owns a specific dated report or runner? | [`#evidence-ownership`](#evidence-ownership) and [`#benchmark-runners`](#benchmark-runners) | Treat this page as the maintainer directory. |
| Where are historical reports? | [`benchmarks/`](benchmarks/) plus [`readiness/public-readiness-verification.md`](readiness/public-readiness-verification.md) | Historical reports stay visible but do not set current claims by themselves. |

## Folder Layout

- `readiness/` holds claim-boundary snapshots and release/public-readiness
  verification ledgers.
- `benchmarks/` holds benchmark design, methodology, public benchmark evidence,
  and public-safe fixture reports.
- `dream/` holds dream-worker shadow A/B and benchmark-corpus measurement
  records.
- `question/` holds question-extraction and question-tracking evidence records.
- `community-field-reports.md` defines how user-submitted reports are collected,
  labeled, and kept separate from official claims.

## Reader Path

1. Need current benchmark/readiness numbers and supersession rules:
   [`current-claims.md`](current-claims.md).
2. Need known negative results or remediation issues before reading dated
   history:
   [`current-claims.md#known-negative-results-and-remediation`](current-claims.md#known-negative-results-and-remediation).
3. Need to know what the repo can honestly claim by stage:
   [`readiness/stage-0-5-readiness.md`](readiness/stage-0-5-readiness.md).
4. Need the dated commands and summarized results behind those claims:
   [`readiness/public-readiness-verification.md`](readiness/public-readiness-verification.md).
5. Need to understand why the benchmarks are shaped this way:
   [`benchmarks/design/benchmark-design-rationale.md`](benchmarks/design/benchmark-design-rationale.md).
6. Need benchmark methodology, track boundaries, and diagnostic notes:
   [`benchmarks/memory-decision-benchmark-plan.md`](benchmarks/memory-decision-benchmark-plan.md).
7. Need external benchmark and memory-system comparison boundaries:
   [`benchmarks/design/external-benchmark-map.md`](benchmarks/design/external-benchmark-map.md).
   For the AMemGym public `v1.base` intake, runner, source-backed overlay
   metrics, and claim limits, use
   [`benchmarks/amemgym.md`](benchmarks/amemgym.md).
   For the MemoryAgentBench feasibility decision and staged adapter boundary,
   runner, and claim limits, use
   [`benchmarks/memoryagentbench.md`](benchmarks/memoryagentbench.md).
8. Need the multimodal memory benchmark-family map for #528:
   [`benchmarks/design/multimodal-memory-benchmark-map.md`](benchmarks/design/multimodal-memory-benchmark-map.md).
9. Need the ATM-Bench Hard protocol boundary for multimodal source-backed
   recall before adapting #528:
   [`benchmarks/design/atm-bench-hard-protocol-boundary.md`](benchmarks/design/atm-bench-hard-protocol-boundary.md).
10. Need LongMemEval source, commands, published V1 retrieval-only results, or
   the V2 context-mapping pilot:
   [`benchmarks/longmemeval.md`](benchmarks/longmemeval.md).

## Maintainer Directory

Use this directory only when the fast path above does not answer the question.
It stays complete for maintainers, but it is not the recommended first reading
path for reviewers trying to understand current claims.

1. Need public corpus commands and local report boundaries:
   [`benchmark_corpus/README.md`](../../benchmark_corpus/README.md) and
   [`benchmark_corpus/sharegpt_manifest.json`](../../benchmark_corpus/sharegpt_manifest.json).
2. Need the public longitudinal pseudo-user benchmark for coding implicit
   knowledge:
   [`benchmarks/public-longitudinal-users.md`](benchmarks/public-longitudinal-users.md).
3. Need the latest dated public-longitudinal-users measurement report:
   [`benchmarks/public-longitudinal-users-measurement-2026-05-31.md`](benchmarks/public-longitudinal-users-measurement-2026-05-31.md).
4. Need the first real public VCS hard-event smoke:
   [`benchmarks/react-real-vcs-smoke-2026-05-31.md`](benchmarks/react-real-vcs-smoke-2026-05-31.md).
5. Need the 100+ gold real React VCS measurement with anti-drift negatives
   and counterfactual controls:
   [`benchmarks/react-real-vcs-100-gold-2026-05-31.md`](benchmarks/react-real-vcs-100-gold-2026-05-31.md).
6. Need the sharper React VCS adversarial controls for source authority,
   keyword drift, behavior-only support, and abstention:
   [`benchmarks/react-real-vcs-adversarial-v2-2026-05-31.md`](benchmarks/react-real-vcs-adversarial-v2-2026-05-31.md).
7. Need the non-oracle React VCS production-like source-disambiguation
   follow-up for current/effective-vs-stale source ranking:
   [`benchmarks/react-real-vcs-production-like-disambiguation-2026-06-04.md`](benchmarks/react-real-vcs-production-like-disambiguation-2026-06-04.md).
8. Need public-safe memory-pain fixture evidence:
   [`benchmarks/memory-pain-fixture-report.md`](benchmarks/memory-pain-fixture-report.md).
9. Need Track S no-live-judge semantic robustness diagnostics:
   [`benchmarks/semantic-robustness-track-s.md`](benchmarks/semantic-robustness-track-s.md).
10. Need public-safe multimodal corpus-style retrieval fixture evidence for
   #531:
   [`benchmarks/multimodal-corpus-fixture-report.md`](benchmarks/multimodal-corpus-fixture-report.md).
11. Need public-safe conversational media-ingest recall fixture evidence for
   #532:
   [`benchmarks/conversational-media-ingest-fixture-report.md`](benchmarks/conversational-media-ingest-fixture-report.md).
12. Need public-safe NIAH-style multimodal evidence-pool fixture evidence for
   #533:
   [`benchmarks/multimodal-niah-evidence-pool-report.md`](benchmarks/multimodal-niah-evidence-pool-report.md).
13. Need public-safe knowledge pollution, privacy partition, and capability
   contract-smoke evidence:
   [`benchmarks/knowledge-pollution-privacy-fixture-report.md`](benchmarks/knowledge-pollution-privacy-fixture-report.md).
14. Need public-safe fresh-thread recall demo evidence:
   [`benchmarks/fresh-thread-recall-demo-2026-05-31.md`](benchmarks/fresh-thread-recall-demo-2026-05-31.md).
15. Need sanitized real-history fresh-thread boundary evidence for #302:
   [`benchmarks/fresh-thread-real-history-smoke-2026-06-02.md`](benchmarks/fresh-thread-real-history-smoke-2026-06-02.md).
16. Need expanded fresh-thread demo and multi-ref real-history smoke evidence:
   [`benchmarks/fresh-thread-expanded-coverage-2026-06-03.md`](benchmarks/fresh-thread-expanded-coverage-2026-06-03.md).
17. Need public-safe H1/H2 hard-negative scoring-contract fixture evidence for
   #244:
   [`benchmarks/hippocampal-hard-negative-fixture-report.md`](benchmarks/hippocampal-hard-negative-fixture-report.md).
18. Need public-safe hippocampal recall-discrimination diagnostic seed evidence
   for #229/#230/#231:
   [`benchmarks/hippocampal-recall-fixture-report.md`](benchmarks/hippocampal-recall-fixture-report.md).
19. Need public-safe Field Continuity / magic-moment reproducibility fixture
   evidence for #454 and the bounded #281 fixture-quality proxy:
   [`benchmarks/field-continuity-fixture-report.md`](benchmarks/field-continuity-fixture-report.md).
20. Need segmented-search merge policy calibration evidence for #375:
   [`benchmarks/segmented-merge-policy-fixture-report.md`](benchmarks/segmented-merge-policy-fixture-report.md).
21. Need agency host-surface timing evidence for #763:
   [`benchmarks/agency-host-surface-codex-desktop-2026-06-05.md`](benchmarks/agency-host-surface-codex-desktop-2026-06-05.md).
22. Need private real-history Dream offline and diagnostic evidence:
   [`dream/dream-real-history-model-backed-eval-2026-05-31.md`](dream/dream-real-history-model-backed-eval-2026-05-31.md)
   and
   [`dream/dream-private-large-history-diagnostic-2026-06-04.md`](dream/dream-private-large-history-diagnostic-2026-06-04.md).
23. Need explicit recall-reminder shadow A/B evidence:
   [`dream/dream-live-shadow-ab-2026-05-30.md`](dream/dream-live-shadow-ab-2026-05-30.md).
24. Need public-corpus negative-control dream shadow evidence:
   [`dream/dream-live-shadow-benchmark-corpus-2026-05-31.md`](dream/dream-live-shadow-benchmark-corpus-2026-05-31.md).
25. Need live question-extraction axis-coverage evidence for GitHub #153:
   [`question/question-extraction-axis-coverage-2026-05-31.md`](question/question-extraction-axis-coverage-2026-05-31.md).
26. Need community-submitted runs, demos, known gaps, or field-report intake:
   [`community-field-reports.md`](community-field-reports.md) and the public
   [`/evidence/`](https://www.aippocampus.com/evidence/) page.

Research notes may include calibration context, but they are not claim ledgers.
Use them for background only until a result is linked back to the readiness
snapshot or dated verification ledger.

When deciding which benchmark or smoke surface to prioritize, run, or treat as
diagnostic-only, use
[`benchmarks/design/benchmark-priority-map.md`](benchmarks/design/benchmark-priority-map.md)
instead of deriving priority from this directory map.

## Evidence Ownership

| Evidence type | Canonical owner | What belongs there |
| --- | --- | --- |
| Current numeric claim snapshot | `docs/evidence/current-claims.md` | Current metric values, dated cohorts, claim levels, supersession, and cannot-claim boundaries for numbers that are easy to over-read. |
| Stage readiness boundary | `docs/evidence/readiness/stage-0-5-readiness.md` | Stage-level can-claim / cannot-claim status and missing proof. |
| Dated command ledger | `docs/evidence/readiness/public-readiness-verification.md` | Summarized commands, dates, pass/fail interpretation, and scope notes. |
| Benchmark design rationale | `docs/evidence/benchmarks/design/README.md` and `docs/evidence/benchmarks/design/benchmark-design-rationale.md` | Evaluation philosophy, track-family why, evidence-layer separation, and external-comparison boundaries. |
| Benchmark priority registry | `docs/evidence/benchmarks/design/benchmark-priority-map.md` | Operational priority, maturity, run-profile, claim-level, and cannot-claim guidance for benchmark and smoke surfaces. |
| Benchmark runner methodology | `docs/evidence/benchmarks/memory-decision-benchmark-plan.md` | Track definitions, report shape, non-goals, and diagnostic interpretation. |
| External benchmark analysis | `docs/evidence/benchmarks/design/external-benchmark-map.md` | Layer-aware external benchmark and memory-system comparison candidates, blockers, and cannot-claim boundaries. |
| AMemGym evidence | `docs/evidence/benchmarks/amemgym.md` and `benchmark_corpus/amemgym_manifest.json` | Official sources, public `v1.base` metadata smoke, source-backed overlay metrics, checked-in public fixture, official-runner bridge smoke, official AIppocampus BaseAgent adapter arms with clean-source/semantic-worker claim gates, Codex Desktop three-arm hook/precache-gated contract, and claim boundaries for #733/#742. |
| Multimodal memory benchmark map | `docs/evidence/benchmarks/design/multimodal-memory-benchmark-map.md` | Source-shape routing for #528 across conversation, corpus, personal filesystem, egocentric video, document/knowledge-source, and personalization benchmark families. |
| ATM-Bench Hard protocol boundary | `docs/evidence/benchmarks/design/atm-bench-hard-protocol-boundary.md` | Verified upstream-protocol intake for #528 multimodal source-backed recall, including corpus-style, conversational media-ingest, Oracle, and NIAH slice boundaries. |
| LongMemEval evidence | `docs/evidence/benchmarks/longmemeval.md` and `benchmark_corpus/longmemeval_manifest.json` | Official sources, dataset checksums, dedicated runner commands, dated V1 retrieval-only results, V2 context-mapping pilot decision, and claim boundaries. |
| Public longitudinal user evidence | `docs/evidence/benchmarks/public-longitudinal-users.md`, `docs/evidence/benchmarks/public-longitudinal-users-measurement-2026-05-31.md`, `docs/evidence/benchmarks/react-real-vcs-smoke-2026-05-31.md`, `docs/evidence/benchmarks/react-real-vcs-100-gold-2026-05-31.md`, `docs/evidence/benchmarks/react-real-vcs-adversarial-v2-2026-05-31.md`, `docs/evidence/benchmarks/react-real-vcs-production-like-disambiguation-2026-06-04.md`, `benchmark_corpus/public_longitudinal_users/`, and `benchmark_corpus/locomo_manifest.json` | Public synthetic coding implicit-knowledge scoring-contract smoke, LoCoMo same-conversation control users, LoCoMo answer-usefulness prototype, deterministic scorers, VCS future-event recall roadmap, dated measurements, real public VCS hard-event smoke, 100+ gold React VCS measurement with anti-drift/counterfactual controls, sharper React VCS adversarial controls, non-oracle production-like source disambiguation, and external-prediction contracts. |
| Corpus setup | `benchmark_corpus/README.md` and `benchmark_corpus/sharegpt_manifest.json` | Public corpus conversion commands, ignored local outputs, and corpus-specific claim boundaries. |
| Demo fixture report | `docs/evidence/benchmarks/memory-pain-fixture-report.md` | Public-safe fixture families and their narrow claim boundary. |
| Track S semantic robustness diagnostics | `docs/evidence/benchmarks/semantic-robustness-track-s.md` and `benchmarks/aippocampus/benchmark_semantic_robustness.py` | No-live-judge semantic perturbation, equivalent-query retrieval invariance, and hard-negative/negation diagnostics for #747; not human-level semantic understanding or a Track A/B replacement. |
| Multimodal corpus fixture report | `docs/evidence/benchmarks/multimodal-corpus-fixture-report.md` and `benchmark_corpus/public_multimodal_corpus/fixture.json` | Public-safe ATM-Bench-inspired corpus-style multimodal retrieval contract for #531; not conversational media upload recall, ATM-Bench score, or product privacy proof. |
| Conversational media-ingest fixture report | `docs/evidence/benchmarks/conversational-media-ingest-fixture-report.md` and `benchmark_corpus/conversational_media_ingest/fixture.json` | Public-safe conversational media-ingest recall contract for #532; media anchors attach to user turns and text hints cannot replace visual source reopen. |
| Multimodal NIAH evidence-pool fixture report | `docs/evidence/benchmarks/multimodal-niah-evidence-pool-report.md` and `benchmark_corpus/multimodal_niah_evidence_pool/fixture.json` | Public-safe NIAH-style supplied-pool answer-synthesis contract for #533; not retrieval quality, ATM-Bench score, or live vision-model quality. |
| Knowledge pollution/privacy fixture report | `docs/evidence/benchmarks/knowledge-pollution-privacy-fixture-report.md` | Public-safe pollution, stale/authority, privacy partition, source-reopen, and thin capability-contract prototype evidence for #517. |
| Hippocampal hard-negative fixture report | `docs/evidence/benchmarks/hippocampal-hard-negative-fixture-report.md` and `benchmark_corpus/hippocampal_hard_negatives/fixture.json` | Public-safe #244 H1/H2 hard-negative contract smoke for near-neighbor lures, unsupported speech, superseded currentness, surface paraphrase lures, seven outcome categories, and asymmetric scoring; not live or real-history recall quality. |
| Hippocampal recall fixture report | `docs/evidence/benchmarks/hippocampal-recall-fixture-report.md`, `docs/evidence/benchmarks/hippocampal-cross-system-comparison-2026-06-04.md`, and `benchmark_corpus/hippocampal_fixtures/hippocampal_synthetic_v1.jsonl` | Public-safe #229/#230/#231/#236/#238 diagnostic seed for D/I matrix reporting, source-reopen failure, wrong-twin separation, scent layers, abstention, calibration categories, clean-clone reproduction metadata, and the dated H1/H2/H5 local-arm comparison table; not full 50-scene / 350-case P1 quality or external memory-system scores. |
| Hippocampal private annotation protocol | `docs/evidence/benchmarks/hippocampal-private-annotation-protocol.md` | Private real-history H1/H2 sampling, truth-source independence, reviewer/adjudication flow, sanitized dated report template, and privacy exclusions for #232; not a committed private case pack. |
| Fresh-thread recall demo evidence | `docs/evidence/benchmarks/fresh-thread-recall-demo-2026-05-31.md` and `docs/evidence/benchmarks/fresh-thread-expanded-coverage-2026-06-03.md` | Public-safe three-arm fresh-thread recall flows, negative controls, source-reopen boundaries, multi-turn/correction/threshold controls, and the expanded #490 claim boundary. |
| Recall navigation comparison smoke | `docs/evidence/benchmarks/recall-navigation-comparison-2026-06-03.md` | Public-safe deterministic #465 comparison and narrow #201/#281/#309/#248 proxy for direct `search_memory`, hook-only, progressive `recall_context -> recall_deepen`, foreground packet source reopen, and source-joined core/sentinel vague-cue candidate funnels; covers vague cues, multilingual cue fixtures, stale-handle rejection, source-ref rejoin, and claim-boundary metrics without live quality, answer-quality, default-prefilter, or broad default-foreground-lift claims. |
| Prompt hook hot-path funnel smoke | `benchmarks/aippocampus/benchmark_prompt_hot_path_funnel.py` and `skills/aippocampus/references/ambient-hooks.md` | Deterministic #602 local-only route-funnel contract for thread/profile hints, cue-cache aliases, bounded trigram FTS fallback, no-op skips, and latency plus false-skip/wrong-scent/promotion counters; not semantic paraphrase or live recall-quality evidence. |
| Living cue cache smoke and hook guard | `tools/aippocampus/smoke/smoke_living_cue_cache.py`, `tests/aippocampus/test_living_cue_cache.py`, and `tests/aippocampus/test_aippocampus_prompt_hook.py` | Public-safe #281 fixture and default-hook guard for learned-phrase-to-source-handle bridging, stale/temporary suppression, over-personalization diagnostics, no-live-LLM selector output, and scent-only hot-path consumption; not fresh-thread quality proof. |
| Query-pattern routes fixture | `aippocampus_runtime.warm_ambient.query_pattern_enrichment --fixture --json`, `aippocampus_runtime.warm_ambient.query_pattern_routes`, `tests/aippocampus/test_query_pattern_enrichment.py`, `tests/aippocampus/test_prompt_hot_path_funnel.py`, `tests/aippocampus/test_onboard_codex.py`, and `tests/aippocampus/test_aippocampus_prompt_hook.py` | Public-safe #574 registry/import planning plus deterministic sidecar writer/reader, default onboarding registry-metadata and reviewed-semantic-trigger route publication, alias-source diagnostics, and hot-path scent consumption; covers changed-generation work items, cache reuse, idempotent existing work, digest invalidation, provider/privacy suppression, stale sidecar filtering, no-live-LLM foreground packets, registry-only nickname misses, reviewed/generated natural multilingual alias hits, and public reports that omit alias text/local paths. Not live DeepSeek quality, scheduler adoption, or latency savings. |
| Fresh-thread real-history boundary smoke | `docs/evidence/benchmarks/fresh-thread-real-history-smoke-2026-06-02.md` and `docs/evidence/benchmarks/fresh-thread-expanded-coverage-2026-06-03.md` | Sanitized real-history boundary smoke for ready-lock reopenability, thread-only lock suppression, current-repo fact negative control, and #490 multi-ref aggregate coverage; not a recall-quality benchmark. |
| Field Continuity fixture report | `docs/evidence/benchmarks/field-continuity-fixture-report.md` and `benchmark_corpus/field_continuity/fixture.json` | Public-safe #454 scenario-family contract for second-user magic-moment reports from Discussion #428; includes a bounded #281 `issue_readouts.github_281` fixture-quality proxy, two-plus public synthetic families, private seed hash/aggregate rules, and overclaim/wrong-family/stale-route controls without live or private-history quality claims. |
| Segmented merge policy fixture report | `docs/evidence/benchmarks/segmented-merge-policy-fixture-report.md` and `benchmark_corpus/segmented_merge_policy/fixture.json` | Public-safe #375/#853 calibration fixture for `SEGMENT_MERGE_POLICY` and stable source-key dedupe over cross-segment diversity, adjacent-turn pairing, duplicate nearby recap suppression, stable source join overlap, and stale/superseded currentness; not source-evidence retrieval or real long-thread recall quality. |
| Dream live shadow A/B reminder evidence | `docs/evidence/dream/dream-live-shadow-ab-2026-05-30.md` | Dated aggregate run for explicit recall-reminder frequency, shadow assignment, nearest-prior exposure attribution, and delivered-vs-shadow claim boundaries. |
| Agency host-surface replay evidence | `docs/evidence/benchmarks/agency-host-surface-codex-desktop-2026-06-05.md` | Public-safe #763 Codex Desktop hidden-route lifecycle replay for show/hold/suppress timing, source-visible suppression, duplicate suppression, recent negative feedback, and usefulness/annoyance/correction ledger boundaries. |
| Dream private real-history offline evidence | `docs/evidence/dream/dream-real-history-model-backed-eval-2026-05-31.md` and `docs/evidence/dream/dream-private-large-history-diagnostic-2026-06-04.md` | Sanitized aggregate private-history Dream eval and diagnostic evidence for selected ready-pack structural lift, shadow replay boundaries, coding-probe deferment, E2E50 seed scan/manual annotation boundaries, agency host-timing replay, coding decision-shadow proxy evidence, and live semantic gate worker/availability diagnostics. |
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
| Track B source-evidence retrieval wrapper | `benchmarks/aippocampus/benchmark_source_evidence_retrieval.py` facade with track-owned helpers in `benchmarks/aippocampus/source_evidence/` | `docs/evidence/benchmarks/memory-decision-benchmark-plan.md`, `benchmark_corpus/README.md`; includes #309 diagnostic `semantic_bridge_lift` / wrong-stance source-joined reranker metrics, not default vector behavior |
| Track S semantic robustness diagnostics | `benchmarks/aippocampus/benchmark_semantic_robustness.py` | `docs/evidence/benchmarks/semantic-robustness-track-s.md`, `docs/evidence/benchmarks/memory-decision-benchmark-plan.md`, #747 |
| Multimodal corpus-style retrieval contract | `benchmarks/aippocampus/benchmark_multimodal_corpus_retrieval.py` | `docs/evidence/benchmarks/multimodal-corpus-fixture-report.md`, `benchmark_corpus/README.md`, `benchmark_corpus/public_multimodal_corpus/fixture.json`, #531 |
| Conversational media-ingest recall contract | `benchmarks/aippocampus/benchmark_conversational_media_ingest_recall.py` | `docs/evidence/benchmarks/conversational-media-ingest-fixture-report.md`, `benchmark_corpus/README.md`, `benchmark_corpus/conversational_media_ingest/fixture.json`, #532 |
| Multimodal NIAH evidence-pool contract | `benchmarks/aippocampus/benchmark_multimodal_niah_evidence_pool.py` | `docs/evidence/benchmarks/multimodal-niah-evidence-pool-report.md`, `benchmark_corpus/README.md`, `benchmark_corpus/multimodal_niah_evidence_pool/fixture.json`, `benchmark_corpus/public_multimodal_corpus/fixture.json`, #533 |
| ShareGPT public-corpus seeded sampler | `benchmarks/aippocampus/sharegpt_sampling.py` | `docs/evidence/benchmarks/memory-decision-benchmark-plan.md`, `benchmark_corpus/sharegpt_manifest.json` |
| Coding decision-shadow Tracks A-E | `benchmarks/aippocampus/benchmark_coding_decision_shadow.py` | `docs/evidence/benchmarks/memory-decision-benchmark-plan.md`, `docs/research/agent-coding-context-analysis.md` |
| H1/H2 hard-negative scoring contract smoke | `benchmarks/aippocampus/benchmark_hippocampal_hard_negatives.py` | `docs/evidence/benchmarks/hippocampal-hard-negative-fixture-report.md`, `docs/evidence/benchmarks/hippocampal-recall-plan.md`, `benchmark_corpus/hippocampal_hard_negatives/fixture.json`, #244 |
| Hippocampal recall-discrimination diagnostic benchmark | `benchmarks/aippocampus/benchmark_hippocampal_recall.py` | `docs/evidence/benchmarks/hippocampal-recall-fixture-report.md`, `docs/evidence/benchmarks/hippocampal-cross-system-comparison-2026-06-04.md`, `docs/evidence/benchmarks/hippocampal-recall-plan.md`, `benchmark_corpus/hippocampal_fixtures/hippocampal_synthetic_v1.jsonl`, #229/#230/#231/#238 |
| Hippocampal recall-discrimination fixture builder | `benchmarks/aippocampus/build_hippocampal_fixture.py` | `docs/evidence/benchmarks/hippocampal-recall-fixture-report.md`, `benchmark_corpus/hippocampal_fixtures/hippocampal_synthetic_v1.jsonl`, #229 |
| Knowledge pollution, privacy partition, and capability-contract smoke | `benchmarks/aippocampus/benchmark_knowledge_pollution.py` | `docs/evidence/benchmarks/memory-decision-benchmark-plan.md`, `docs/evidence/benchmarks/knowledge-pollution-privacy-fixture-report.md`, `docs/architecture/high-risk-answer-gates.md` |
| LongMemEval retrieval-only benchmark | `benchmarks/aippocampus/benchmark_longmemeval.py` | `docs/evidence/benchmarks/longmemeval.md`, `benchmark_corpus/longmemeval_manifest.json` |
| LongMemEval-V2 context-mapping pilot | `benchmarks/aippocampus/benchmark_longmemeval_v2_context.py` | `docs/evidence/benchmarks/longmemeval.md`, `benchmark_corpus/longmemeval_manifest.json`, #259 |
| AMemGym metadata, source-backed overlay smoke, official-runner bridge with AIppocampus BaseAgent arms, and Codex Desktop AMemGym-style arms | `benchmarks/aippocampus/benchmark_amemgym.py`, `benchmarks/aippocampus/benchmark_amemgym_official.py`, `benchmarks/aippocampus/benchmark_codex_desktop_amemgym.py` | `docs/evidence/benchmarks/amemgym.md`, `benchmark_corpus/amemgym_manifest.json`, `benchmark_corpus/amemgym_fixture/fixture.json`, #733, #742 |
| MemoryAgentBench metadata, case-pack, Stage 3 dry-run, and optional parquet row smoke | `benchmarks/aippocampus/benchmark_memoryagentbench.py` | `docs/evidence/benchmarks/memoryagentbench.md`, `benchmark_corpus/memoryagentbench_manifest.json`, #608, #614, #694 |
| LoCoMo public longitudinal-users control | `benchmarks/aippocampus/benchmark_locomo_public_users.py` | `docs/evidence/benchmarks/public-longitudinal-users.md`, `benchmark_corpus/README.md`, `benchmark_corpus/locomo_manifest.json` |
| LoCoMo answer-usefulness prototype | `benchmarks/aippocampus/benchmark_locomo_answer_usefulness.py` | `docs/evidence/benchmarks/public-longitudinal-users.md`, `benchmark_corpus/README.md`, #400 |
| Public longitudinal pseudo-user coding implicit-knowledge contract smoke | `benchmarks/aippocampus/benchmark_public_longitudinal_users.py` | `docs/evidence/benchmarks/public-longitudinal-users.md`, `benchmark_corpus/public_longitudinal_users/README.md` |
| VCS future-event recall, source-disambiguation, and route-chain/actionability benchmark scaffold | `benchmarks/aippocampus/benchmark_vcs_future_event_recall.py` | `docs/evidence/benchmarks/public-longitudinal-users.md`, `docs/evidence/benchmarks/react-real-vcs-production-like-disambiguation-2026-06-04.md`, `benchmark_corpus/public_longitudinal_users/README.md`, #309 |
| VCS / rollout future-event fixture builder | `benchmarks/aippocampus/build_vcs_future_event_fixture.py` | `docs/evidence/benchmarks/public-longitudinal-users.md`, `benchmark_corpus/public_longitudinal_users/README.md` |
| FTS5 real-history recall | `benchmarks/aippocampus/benchmark_fts5_recall.py` | `docs/evidence/readiness/public-readiness-verification.md`, `docs/planning/next-iteration-plan.md` |
| Public CJK local-recall fixture | `benchmarks/aippocampus/benchmark_fts5_recall.py --public-cjk-fixture` | `docs/evidence/benchmarks/cjk-local-recall-fixture-report.md`, #852 |
| Track C payload fidelity | `benchmarks/aippocampus/benchmark_payload_fidelity.py` | `docs/evidence/benchmarks/memory-decision-benchmark-plan.md`, `docs/evidence/benchmarks/memory-pain-fixture-report.md` |
| Track D synthetic compaction continuity | `benchmarks/aippocampus/benchmark_compaction_continuity.py` | `docs/evidence/benchmarks/memory-decision-benchmark-plan.md`, `docs/evidence/readiness/public-readiness-verification.md` |
| E2E50 silent-constraint case-pack scorer scaffold | `benchmarks/aippocampus/benchmark_e2e50_silent_constraint.py`; sequence/load validator in `aippocampus_runtime/coding/sequence_packets.py`; Episode/Arc builder in `aippocampus_runtime/coding/episode_arcs.py` | `docs/evidence/benchmarks/memory-decision-benchmark-plan.md`, `docs/architecture/episode-arc-read-models.md`, `benchmark_corpus/e2e50_silent_constraint/fixture.json`, #279/#663/#575 |
| Continuous-memory attribution arms, host-native baseline, pre-registration, preregistered slice readouts including `public_synthetic_preregistered_repeat`, cost/harm ledger, cost/harm sensitivity, and scenario provenance/holdout controls | `benchmarks/aippocampus/benchmark_continuous_memory_arms.py` | `docs/evidence/benchmarks/memory-decision-benchmark-plan.md`, #378/#406/#407/#408/#409/#410 |
| Optional live semantic gate | `benchmarks/aippocampus/benchmark_live_semantic_gate.py` | `docs/evidence/benchmarks/memory-decision-benchmark-plan.md`, `benchmark_corpus/README.md` |
| Prompt hook local hot-path funnel | `benchmarks/aippocampus/benchmark_prompt_hot_path_funnel.py` | `skills/aippocampus/references/ambient-hooks.md`, #602 |
| Fresh-thread public-safe recall demo | `benchmarks/aippocampus/benchmark_fresh_thread_recall_demo.py` | `docs/evidence/benchmarks/fresh-thread-recall-demo-2026-05-31.md`, `docs/evidence/benchmarks/fresh-thread-expanded-coverage-2026-06-03.md`, `docs/guides/demo-scenarios.md` |
| Field Continuity / magic-moment reproducibility contract | `benchmarks/aippocampus/benchmark_field_continuity.py` | `docs/evidence/benchmarks/field-continuity-fixture-report.md`, `docs/evidence/benchmarks/memory-decision-benchmark-plan.md`, `benchmark_corpus/field_continuity/fixture.json`, #454, #281 |
| Structured cognitive portrait | `benchmarks/aippocampus/benchmark_cognitive_portrait.py` | `docs/research/compact-activation-signals.md`, `docs/evidence/benchmarks/memory-decision-benchmark-plan.md` |
| Question-aware real-history structural benchmark and optional answer-quality review | `benchmarks/aippocampus/benchmark_question_aware_real_history.py` | `docs/architecture/question-tracking-subconscious.md`, `docs/evidence/question/question-aware-answer-quality-2026-06-08.md`, `docs/research/compact-activation-signals.md`, `docs/planning/next-iteration-plan.md`, `docs/evidence/readiness/stage-0-5-readiness.md`, `docs/evidence/benchmarks/memory-decision-benchmark-plan.md`, #248 |
| Question tracking selected-fixture calibration | `benchmarks/aippocampus/benchmark_question_tracking_calibration.py` | `docs/architecture/question-tracking-subconscious.md`, `docs/planning/technical-differentiation-analysis.md` |
| Warm ambient recall benchmark | `benchmarks/aippocampus/benchmark_warm_ambient_recall.py` | `docs/research/ambient-associative-recall.md`, `benchmark_corpus/README.md` |
| Warm ambient parameter sweep | `benchmarks/aippocampus/benchmark_warm_ambient_sweep.py` | `docs/research/ambient-associative-recall.md`, `docs/evidence/benchmarks/memory-decision-benchmark-plan.md` |
| Warm ambient case-pack builder | `benchmarks/aippocampus/build_warm_ambient_trace_cases.py` | `benchmark_corpus/README.md` |
| Segmented merge policy calibration | `benchmarks/aippocampus/benchmark_segmented_merge_policy.py` | `docs/evidence/benchmarks/segmented-merge-policy-fixture-report.md`, `benchmark_corpus/segmented_merge_policy/fixture.json`, #375 |

Benchmark mirror tests live in `tests/aippocampus/test_benchmark_*.py`. The
fresh-clone deterministic suite smoke plus curated PR mirror/support smoke is
selected with
`python tools/aippocampus/run_tests.py --tier benchmark-smoke --benchmark-suite-profile public-fast`;
the complete benchmark mirror tier is selected with
`python tools/aippocampus/run_tests.py --tier benchmark`.

## Benchmark Test Tiers

| Need | Command | Dependency / claim boundary |
| --- | --- | --- |
| Quick local inner loop | `python tools/aippocampus/run_tests.py --tier quick` | Small manifest-classified deterministic core for local iteration. It is intentionally smaller than the broad PR lane and excludes smoke/integration/provider/install/sync surfaces. |
| Broad deterministic PR gate | `python tools/aippocampus/run_tests.py --tier pr` | Manifest-classified deterministic PR matrix. `fast` remains a deprecated compatibility alias for this lane, not the inner-loop tier. |
| Deterministic benchmark PR smoke | `python -m pip install -e ".[benchmark]"` then `python tools/aippocampus/run_tests.py --tier benchmark-smoke --benchmark-suite-profile public-fast` | Public-fast suite smoke plus curated public benchmark/report/schema/profile guards and the #279 candidate-seed discovery support guard. No provider calls, private registry data, raw reports, or large corpus downloads. |
| Full benchmark mirror tests | `python tools/aippocampus/run_tests.py --tier benchmark` | All `tests/aippocampus/test_benchmark_*.py` modules. Use when changing benchmark runners, profiles, reports, or claim-boundary helpers. |
| Full repository suite | `python tools/aippocampus/run_tests.py --tier full` | All manifest-classified quick, PR, smoke, integration, slow, and benchmark tests. Use before broad repository-health, release, or public-readiness claims. |
| Optional live/provider tracks | Track-specific CLI flags, environment variables, and owner docs | Not normal contributor deps and not part of default PR CI. They require explicit operator setup, documented provider/env boundaries, and sanitized outputs. |

The `benchmark` optional dependency extra is intentionally empty while the
deterministic smoke lane uses only stdlib plus checked-in public fixtures. It is
the stable install target for contributors; add packages there only when a
committed deterministic benchmark genuinely requires them.

Python callers should prefer
`BenchmarkSuiteConfig` plus `run_benchmark_suite_with_config()` for benchmark
suite runs. The long `run_benchmark_suite(**kwargs)` function remains a
compatibility bridge for existing callers and scripts.

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
| Living cue cache public-safe smoke | `tools/aippocampus/smoke/smoke_living_cue_cache.py` | `skills/aippocampus/references/ambient-hooks.md`, `docs/research/ambient-associative-recall.md`, #281 |
| Query-pattern routes fixture | `python -m aippocampus_runtime.warm_ambient.query_pattern_enrichment --fixture --json`; unit coverage for `aippocampus_runtime.warm_ambient.query_pattern_routes` and hot-path consumption | `skills/aippocampus/references/subconscious-jobs.md`, `docs/guides/public-api.md`, #574 |
| Real Codex long-session continuity smoke | `tools/aippocampus/smoke/smoke_codex_long_session_continuity.py` | `docs/evidence/readiness/public-readiness-verification.md` |
| Provider-key bridge OS credential-store smoke | `tools/aippocampus/smoke/smoke_provider_key_bridge_os_store.py` | `docs/guides/install-guide.md`, `docs/evidence/readiness/public-readiness-verification.md`, #784 |
| E2E50 silent-constraint candidate seed scanner | `tools/aippocampus/smoke/smoke_e2e50_seed_candidates.py`; deterministic unittest included in `benchmark-smoke` | `docs/evidence/benchmarks/memory-decision-benchmark-plan.md`, #279 |
| E2E50 silent-constraint case-pack scorer scaffold | `benchmarks/aippocampus/benchmark_e2e50_silent_constraint.py`; deterministic unittest included in `benchmark-smoke`; sequence/load validator in `aippocampus_runtime/coding/sequence_packets.py`; Episode/Arc builder in `aippocampus_runtime/coding/episode_arcs.py` | `docs/evidence/benchmarks/memory-decision-benchmark-plan.md`, `docs/architecture/episode-arc-read-models.md`, `benchmark_corpus/e2e50_silent_constraint/fixture.json`, #279/#663/#575 |
| Episode/Arc private-history aggregate readout | `aippocampus episode-arcs --json`; runtime owner `aippocampus_runtime.coding.episode_arc_private_adjudication`; deterministic unittest `tests/aippocampus/test_episode_arc_private_adjudication.py` | `docs/evidence/episode-arc-private-history-adjudication-2026-06-08.md`, `docs/architecture/episode-arc-read-models.md`, #663 |
| Claude Code MCP host probe | `tools/aippocampus/smoke/smoke_claude_code_mcp_host.py` | `docs/evidence/readiness/public-readiness-verification.md` |
| Claude Code local-history parser smoke | `tools/aippocampus/smoke/smoke_claude_code_history.py` | `docs/evidence/readiness/public-readiness-verification.md` |
| Synthetic cross-agent continuity smoke | `tools/aippocampus/smoke/smoke_cross_agent_continuity.py` | `docs/evidence/readiness/public-readiness-verification.md` |
| Generic JSONL ecosystem integration smoke | `tools/aippocampus/smoke/smoke_generic_jsonl_integration.py` | `docs/guides/ecosystem-integration-matrix.md` |
| OpenAI Agents SDK function-tool contract smoke | `tools/aippocampus/smoke/smoke_openai_agents_sdk_tool_contract.py`, `tests/aippocampus/test_openai_agents_sdk_smoke.py` | `docs/guides/ecosystem-integration-matrix.md` |
| Life-wide registry aggregate smoke | `tools/aippocampus/smoke/smoke_life_wide_registry.py` | `docs/evidence/readiness/stage-0-5-readiness.md` |
| Real-history memory-pain prompt-hook smoke | `tools/aippocampus/smoke/smoke_memory_pain_prompt_hook.py` | `docs/evidence/benchmarks/memory-decision-benchmark-plan.md` |
| Fresh-thread real-history boundary smoke | `tools/aippocampus/smoke/smoke_fresh_thread_real_history.py` | `docs/evidence/benchmarks/fresh-thread-real-history-smoke-2026-06-02.md`, `docs/evidence/benchmarks/fresh-thread-expanded-coverage-2026-06-03.md` |
| Recall navigation arm comparison smoke | `tools/aippocampus/smoke/smoke_recall_navigation_comparison.py` | `docs/evidence/benchmarks/recall-navigation-comparison-2026-06-03.md`, #201, #281, #309, #248, #465 |
| Real-history semantic scope smoke | `tools/aippocampus/smoke/smoke_semantic_scope_real_history.py` | `docs/evidence/readiness/stage-0-5-readiness.md` |
| Semantic sidecar source-review smoke | `tools/aippocampus/smoke/smoke_semantic_scope_source_review.py` | `docs/evidence/readiness/stage-0-5-readiness.md` |
| Selected source-evidence recall eval and candidate-space diagnostics | `tools/aippocampus/smoke/smoke_source_evidence_recall_eval.py` | `docs/evidence/readiness/stage-0-5-readiness.md`, `docs/evidence/benchmarks/memory-decision-benchmark-plan.md`, #458 |
| Optional live question-confirmation smoke | `tools/aippocampus/smoke/smoke_question_confirmation_live.py` | `docs/architecture/question-tracking-subconscious.md`, `docs/evidence/readiness/stage-0-5-readiness.md` |
| Question prefilter parity smoke | `tools/aippocampus/smoke/smoke_question_prefilter_parity.py` | `docs/architecture/question-tracking-subconscious.md`, #248 |
| Agency host-timing replay smoke | `tools/aippocampus/smoke/smoke_agency_host_timing.py` | `docs/research/agency-from-cognitive-map.md`, `docs/evidence/benchmarks/agency-host-surface-codex-desktop-2026-06-05.md`, #312, #763 |
| Route-readiness Cognitive Observatory smoke | `tools/aippocampus/smoke/smoke_route_readiness_observatory.py` and `tests/aippocampus/test_cognitive_observatory.py` | `docs/architecture/cognitive-runtime-architecture.md`, `docs/guides/public-api.md`, #574, #576 |
| Worker-to-hook handoff smoke | `tools/aippocampus/smoke/smoke_worker_hook_handoff.py` | `docs/research/ambient-associative-recall.md`, `skills/aippocampus/references/ambient-hooks.md`, #574, #909 |
| Dream real-history structural and user-visible eval | `skills/aippocampus/scripts/dream_real_history_eval.py` | `docs/evidence/dream/dream-real-history-model-backed-eval-2026-05-31.md`, `docs/research/dream-task-design.md`, #163 |
| Synthetic GB-scale capacity smoke | `tools/aippocampus/smoke/smoke_synthetic_scale_capacity.py` | `docs/architecture/gb-scale-roadmap.md` |
| Long-thread segment build/search soak | `tools/aippocampus/smoke/smoke_long_thread_segment_soak.py`, `tests/aippocampus/test_long_thread_segment_soak.py` | `docs/architecture/gb-scale-roadmap.md`, #376 |
| Synthetic question-tracking scale smoke | `tools/aippocampus/smoke/smoke_question_tracking_scale.py` | `docs/architecture/question-tracking-subconscious.md`, `docs/architecture/gb-scale-roadmap.md` |
| Source-backed repo familiarity smoke | `tools/aippocampus/smoke/smoke_repo_familiarity.py` | `docs/architecture/source-backed-familiarity-map.md` |
| Repo familiarity foreground experiment smoke | `tools/aippocampus/smoke/smoke_repo_familiarity_foreground_experiment.py` | `docs/architecture/source-backed-familiarity-map.md`, #250 |
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
