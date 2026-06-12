# Benchmark And Evidence Map

Role: evidence navigation map.
Status: current owner for routing readers to benchmark/evidence owners; not a
numeric claim snapshot, command ledger, or runner priority registry.

This is the first-stop map for AIppocampus benchmark evidence only after a
reader knows what kind of evidence they need. Keep current numeric claims,
scope-boundary remediation, and supersession rules in
[`docs/evidence/current-claims.md`](current-claims.md), stage-level can-claim /
claim-boundary status in
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
| What is already proven in plain positive terms? | [`can-claim-ladder.md`](can-claim-ladder.md) | Then open current claims for exact numbers and caveat retirement conditions. |
| How should a new public report phrase claims? | [`current-claims.md`](current-claims.md) | Lead with `measured_result`, `supports`, and `material_limits`; keep `cannot_claim` short and compatibility-oriented. |
| Is a closed benchmark/evidence issue a harness, pilot, blocker, contract fixture, or completed score? | [`benchmark-evidence-maturity.md`](benchmark-evidence-maturity.md) | Use the closeout vocabulary and audit ledger before promoting old issue language into a claim. |
| What works now, where did it originate, and what still blocks broader launch? | [`public-provenance-ledger.md`](public-provenance-ledger.md) | Use this for the compact public origin/current-value trail before issue archaeology. |
| What can AIppocampus currently claim, and what failed? | [`current-claims.md`](current-claims.md) | Open the source report only for the row you need. |
| Which confirmed scope boundary or benchmark result needs remediation? | [`current-claims.md#confirmed-scope-boundaries-expected-null-results`](current-claims.md#confirmed-scope-boundaries-expected-null-results) | Follow the linked issue before reading old dated reports. |
| Which material limits are testable, retired later, or durable? | [`current-claims.md#claim-boundary-owner-and-retirement-ledger`](current-claims.md#claim-boundary-owner-and-retirement-ledger) | Use the owner issue and retirement condition before changing public claims. |
| Which benchmark or smoke should I run? | [`benchmarks/design/benchmark-priority-map.md`](benchmarks/design/benchmark-priority-map.md) | Use the default run profile and claim-boundary guidance there. |
| Is this a small contract fixture or public-quality cohort evidence? | [`benchmarks/design/benchmark-maturity-gates.md`](benchmarks/design/benchmark-maturity-gates.md) | Check maturity level, sample floor, holdout, and promotion target before citing quality. |
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
2. Need confirmed scope boundaries or remediation issues before reading dated
   history:
   [`current-claims.md#confirmed-scope-boundaries-expected-null-results`](current-claims.md#confirmed-scope-boundaries-expected-null-results).
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
   For the STATE-Bench Agent Learning Track feasibility decision, train-only
   adapter path, and no-score claim boundary, use
   [`benchmarks/state-bench-agent-learning.md`](benchmarks/state-bench-agent-learning.md).
   For PersonaMem / PersonaMem-v2 staging behind AIppo/Ficus profile-readiness,
   use [`benchmarks/personamem-readiness.md`](benchmarks/personamem-readiness.md).
   For the #310 Journey public time-sliced replay fixture and no-live-quality
   claim boundary, use
   [`benchmarks/journey-public-time-sliced-replay.md`](benchmarks/journey-public-time-sliced-replay.md).
8. Need the multimodal memory benchmark-family map for #528:
   [`benchmarks/design/multimodal-memory-benchmark-map.md`](benchmarks/design/multimodal-memory-benchmark-map.md).
9. Need the ATM-Bench Hard protocol boundary for multimodal source-backed
   recall before adapting #528:
   [`benchmarks/design/atm-bench-hard-protocol-boundary.md`](benchmarks/design/atm-bench-hard-protocol-boundary.md).
10. Need LongMemEval source, commands, the current 500-question V1
   retrieval-only slice, the optional lexical exact-line reranker diagnostic,
   #1193 structural exact-line failure report, #1305 semantic warm-cache path,
   the fixed-reader answer/latency harness boundary, historical 50-question
   smoke rows, the V2 context-mapping pilot, or the V2 official-harness pilot
   decision and adapter boundary:
   [`benchmarks/longmemeval.md`](benchmarks/longmemeval.md).
11. Need the public reliability gauntlet that separates runtime pressure,
    mis-recall diagnostics, and pollution hygiene for #1102:
    [`benchmarks/public-reliability-gauntlet.md`](benchmarks/public-reliability-gauntlet.md).
12. Need the attention-router navigation-quality gate for route precision,
    masks, stale/currentness, conflict, action-time, anti-nag, and bounded
    evidence red lines:
    [`benchmarks/attention-navigation-quality.md`](benchmarks/attention-navigation-quality.md).
13. Need audited attention score-fusion calibration over sanitized feature rows
    before changing router weights:
    [`benchmarks/attention-score-fusion-calibration.md`](benchmarks/attention-score-fusion-calibration.md).
14. Need the public-safe integrated continuity loop across semantic warming,
    hot routing, facade packets, AIppo, deepen/explain, and budgets:
    [`benchmarks/agent-continuity-loop.md`](benchmarks/agent-continuity-loop.md).
15. Need map-rot lifecycle-debt evidence for stale, challenged, quarantined,
    superseded, missing-middle, deleted/no-recall, dead-lettered, or
    repeated-wrong cold navigation-map objects:
    [`benchmarks/map-rot-lifecycle-debt.md`](benchmarks/map-rot-lifecycle-debt.md).
16. Need the #1195 benchmark-family promotion decision for the first public
    cohort candidate targets, holdout/no-tuning-leak boundaries, usefulness
    blockers, and gate separation:
    [`benchmarks/benchmark-family-promotion-candidates-2026-06-12.md`](benchmarks/benchmark-family-promotion-candidates-2026-06-12.md).

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
   For the rollout behavior route-chain/actionability top-k boundary, use
   [`benchmarks/rollout-hard-event-route-chain-2026-06-12.md`](benchmarks/rollout-hard-event-route-chain-2026-06-12.md).
   For the broader #1197 public-safe rollout hard-event cohort, use
   [`benchmarks/rollout-hard-event-cohort-v2-2026-06-12.md`](benchmarks/rollout-hard-event-cohort-v2-2026-06-12.md).
   For the sparse provenance codebook V0 fixture and #1190 route-reconstruction
   proof boundary, use
   [`benchmarks/sparse-provenance-codebook-v0-2026-06-12.md`](benchmarks/sparse-provenance-codebook-v0-2026-06-12.md).
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
16. Need expanded fresh-thread demo, the #281 public validation readout, and
   multi-ref real-history smoke evidence:
   [`benchmarks/fresh-thread-expanded-coverage-2026-06-03.md`](benchmarks/fresh-thread-expanded-coverage-2026-06-03.md).
17. Need public-safe H1/H2 hard-negative production-like synthetic evidence,
   contract controls, and scorer taxonomy for #244/#1041:
   [`benchmarks/hippocampal-hard-negative-fixture-report.md`](benchmarks/hippocampal-hard-negative-fixture-report.md).
18. Need public-safe hippocampal recall-discrimination diagnostic seed evidence
   or the #1040 D5/D6 gated diagnostic for #229/#230/#231:
   [`benchmarks/hippocampal-recall-fixture-report.md`](benchmarks/hippocampal-recall-fixture-report.md).
19. Need public-safe Field Continuity / magic-moment reproducibility fixture
   evidence for #454 and the supporting bounded #281 fixture-quality proxy:
   [`benchmarks/field-continuity-fixture-report.md`](benchmarks/field-continuity-fixture-report.md).
20. Need public-safe Journey time-sliced replay and foreground hint timing
   fixture evidence for #310:
   [`benchmarks/journey-public-time-sliced-replay.md`](benchmarks/journey-public-time-sliced-replay.md).
21. Need public-safe provider-conformance kit evidence for #981 / #988:
   [`benchmarks/provider-conformance-fixture-report.md`](benchmarks/provider-conformance-fixture-report.md).
22. Need the latest Claude Code real-host local-history / MCP dogfood boundary:
   [`readiness/claude-code-dogfood-2026-06-09.md`](readiness/claude-code-dogfood-2026-06-09.md).
23. Need segmented-search merge policy calibration evidence for #375:
   [`benchmarks/segmented-merge-policy-fixture-report.md`](benchmarks/segmented-merge-policy-fixture-report.md).
24. Need agency host-surface timing evidence for #763:
   [`benchmarks/agency-host-surface-codex-desktop-2026-06-05.md`](benchmarks/agency-host-surface-codex-desktop-2026-06-05.md).
25. Need private real-history Dream offline and diagnostic evidence:
   [`dream/dream-real-history-model-backed-eval-2026-05-31.md`](dream/dream-real-history-model-backed-eval-2026-05-31.md)
   and
   [`dream/dream-private-large-history-diagnostic-2026-06-04.md`](dream/dream-private-large-history-diagnostic-2026-06-04.md).
26. Need explicit recall-reminder shadow A/B evidence:
   [`dream/dream-live-shadow-ab-2026-05-30.md`](dream/dream-live-shadow-ab-2026-05-30.md).
27. Need public-corpus negative-control dream shadow evidence:
   [`dream/dream-live-shadow-benchmark-corpus-2026-05-31.md`](dream/dream-live-shadow-benchmark-corpus-2026-05-31.md).
28. Need live question-extraction axis-coverage evidence for GitHub #153:
   [`question/question-extraction-axis-coverage-2026-05-31.md`](question/question-extraction-axis-coverage-2026-05-31.md).
29. Need community-submitted runs, demos, known gaps, or field-report intake:
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
| Current numeric claim snapshot | `docs/evidence/current-claims.md` | Current metric values, dated cohorts, claim levels, supersession, material limits, and owner/retirement routes for numbers that are easy to over-read. |
| Stage readiness boundary | `docs/evidence/readiness/stage-0-5-readiness.md` | Stage-level positive claims, material limits, and missing proof. |
| Dated command ledger | `docs/evidence/readiness/public-readiness-verification.md` | Summarized commands, dates, pass/fail interpretation, and scope notes. |
| Benchmark design rationale | `docs/evidence/benchmarks/design/README.md` and `docs/evidence/benchmarks/design/benchmark-design-rationale.md` | Evaluation philosophy, track-family why, evidence-layer separation, and external-comparison boundaries. |
| Benchmark maturity gates | `docs/evidence/benchmarks/design/benchmark-maturity-gates.md` and `benchmarks/aippocampus/benchmark_maturity.py` | Maturity ladder, sample-size floors, holdout/no-tuning-leakage fields, and promotion metadata separating `contract_gate_ok` from `quality_gate_ok`. |
| Benchmark family promotion candidates | `docs/evidence/benchmarks/benchmark-family-promotion-candidates-2026-06-12.md` and `benchmarks/aippocampus/benchmark_family_promotion_candidates.py` | #1195 first-family promotion decision for agent continuity, attention navigation, and map-rot lifecycle debt; records target sample floors, family distribution, holdout/no-tuning-leakage, uncertainty policy, sanitization, and usefulness blockers without claiming public-quality results. |
| Benchmark priority registry | `docs/evidence/benchmarks/design/benchmark-priority-map.md` | Operational priority, maturity, run-profile, claim-level, and claim-boundary guidance for benchmark and smoke surfaces. |
| Benchmark runner methodology | `docs/evidence/benchmarks/memory-decision-benchmark-plan.md` | Track definitions, report shape, non-goals, and diagnostic interpretation. |
| External benchmark analysis | `docs/evidence/benchmarks/design/external-benchmark-map.md` | Layer-aware external benchmark and memory-system comparison candidates, blockers, and material limits. |
| AMemGym evidence | `docs/evidence/benchmarks/amemgym.md`, `docs/evidence/benchmarks/amemgym-official-live-provider-blocker-2026-06-09.md`, and `benchmark_corpus/amemgym_manifest.json` | Official sources, public `v1.base` metadata smoke, source-backed overlay metrics, checked-in public fixture, official-runner bridge smoke, official AIppocampus BaseAgent adapter arms with clean-source/semantic-worker claim gates, the 2026-06-09 live-provider blocker decision for #958, Codex Desktop three-arm hook/precache-gated contract, and claim boundaries for #733/#742. |
| STATE-Bench Agent Learning feasibility | `docs/evidence/benchmarks/state-bench-agent-learning.md` and `docs/evidence/benchmarks/state-bench-agent-learning-preflight-2026-06-10.json` | Official source snapshot, train-only learning extraction boundary, read-only `retrieve_learnings` adapter scaffold, matched no-memory adapter/run-plan preflight, local ignored artifact policy, LF-checkout prompt-hash note, and locked-eval-client blocker for #1043. No score/lift claim. |
| PersonaMem readiness gate | `docs/evidence/benchmarks/personamem-readiness.md` | Stages PersonaMem / PersonaMem-v2 behind AIppo/Ficus profile-readiness; records required source-supported profile extraction, lifecycle/currentness gates, privacy masks, response-adaptation metrics, a diagnostic-only pilot shape, and no-score claim boundaries for #1159. |
| Multimodal memory benchmark map | `docs/evidence/benchmarks/design/multimodal-memory-benchmark-map.md` | Source-shape routing for #528 across conversation, corpus, personal filesystem, egocentric video, document/knowledge-source, and personalization benchmark families. |
| ATM-Bench Hard protocol boundary | `docs/evidence/benchmarks/design/atm-bench-hard-protocol-boundary.md` | Verified upstream-protocol intake for #528 multimodal source-backed recall, including corpus-style, conversational media-ingest, Oracle, and NIAH slice boundaries. |
| LongMemEval evidence | `docs/evidence/benchmarks/longmemeval.md`, `docs/evidence/benchmarks/longmemeval-exact-line-repair-2026-06-12.md`, `docs/evidence/benchmarks/longmemeval-semantic-cache-path-2026-06-12.md`, `docs/evidence/benchmarks/longmemeval-fixed-reader-answer-25-2026-06-12.md`, `docs/evidence/benchmarks/longmemeval-500-retrieval-artifact-2026-06-11.json`, and `benchmark_corpus/longmemeval_manifest.json` | Official sources, dataset checksums, dedicated runner commands, the dated 500-question LongMemEval-S V1 retrieval-only slice, public artifact-trail manifest, optional lexical exact-line reranker diagnostic, #1193 structural exact-line failure report, #1305 semantic warm query/candidate cache replay, first dated fixed-reader answer/latency baseline, historical 100/50-question rows, V2 context-mapping pilot decision, V2 official-harness pilot decision/adapter boundary, and claim boundaries. |
| Public longitudinal user evidence | `docs/evidence/benchmarks/public-longitudinal-users.md`, `docs/evidence/benchmarks/public-longitudinal-users-measurement-2026-05-31.md`, `docs/evidence/benchmarks/react-real-vcs-smoke-2026-05-31.md`, `docs/evidence/benchmarks/react-real-vcs-100-gold-2026-05-31.md`, `docs/evidence/benchmarks/react-real-vcs-adversarial-v2-2026-05-31.md`, `docs/evidence/benchmarks/react-real-vcs-production-like-disambiguation-2026-06-04.md`, `docs/evidence/benchmarks/rollout-hard-event-route-chain-2026-06-12.md`, `docs/evidence/benchmarks/rollout-hard-event-cohort-v2-2026-06-12.md`, `benchmark_corpus/public_longitudinal_users/`, and `benchmark_corpus/locomo_manifest.json` | Public synthetic coding implicit-knowledge scoring-contract smoke, LoCoMo same-conversation control users, LoCoMo fixed-reader text-QA harness, LoCoMo answer-usefulness prototype, deterministic scorers, VCS future-event recall roadmap, dated measurements, real public VCS hard-event smoke, 100+ gold React VCS measurement with anti-drift/counterfactual controls, sharper React VCS adversarial controls, non-oracle production-like source disambiguation, rollout route-chain/actionability top-k calibration, public-safe rollout hard-event cohort V2, and external-prediction contracts. |
| Corpus setup | `benchmark_corpus/README.md` and `benchmark_corpus/sharegpt_manifest.json` | Public corpus conversion commands, ignored local outputs, and corpus-specific claim boundaries. |
| Demo fixture report | `docs/evidence/benchmarks/memory-pain-fixture-report.md` | Public-safe fixture families and their narrow claim boundary. |
| Track S semantic robustness diagnostics | `docs/evidence/benchmarks/semantic-robustness-track-s.md` and `benchmarks/aippocampus/benchmark_semantic_robustness.py` | No-live-judge semantic perturbation, equivalent-query retrieval invariance, and hard-negative/negation diagnostics for #747; not human-level semantic understanding or a Track A/B replacement. |
| Public reliability gauntlet | `docs/evidence/benchmarks/public-reliability-gauntlet.md`, `docs/evidence/benchmarks/public-reliability-gauntlet-2026-06-10.json`, and `benchmarks/aippocampus/benchmark_public_reliability_gauntlet.py` | Public-safe #1102 aggregate gate over runtime stability, mis-recall quality, and pollution hygiene; keeps LongMemEval-S aggregate metrics, synthetic scale/fanout stress, hard-negative diagnostics, and pollution fixtures separate, with no single reliability score. |
| Attention navigation quality | `docs/evidence/benchmarks/attention-navigation-quality.md` and `benchmarks/aippocampus/benchmark_attention_navigation_quality.py` | Public-safe #1111 route-quality gate over positive routes, hard masks, stale/currentness, conflict, action-time, anti-nag, bounded-evidence, and wrong-source controls; hard red lines stay separate from route averages. |
| Attention score-fusion calibration | `docs/evidence/benchmarks/attention-score-fusion-calibration.md` and `benchmarks/aippocampus/benchmark_attention_score_fusion_calibration.py` | Public-safe #1112 calibration diagnostic over sanitized attention feature rows; compares current deterministic weights to a calibrated rule grid without raw text, private history, or learnable hard masks. |
| Agent continuity loop gate | `docs/evidence/benchmarks/agent-continuity-loop.md` and `benchmarks/aippocampus/benchmark_agent_continuity_loop.py` | Public-safe #1163/#1181 integration gate across semantic warming, hot routing, facade packets, safe packet triage labels/previews, AIppo working contracts, source-reopen budget, foreground budget, deepen/explain, blocked/stale/conflict, and anti-nag cases; red lines stay separate from case success. |
| Avatar bounded resonance proxy pilot | `docs/research/avatar-bounded-resonance-pilot-2026-06-12.md`, `docs/research/avatar-bounded-resonance-pilot-2026-06-12.json`, `benchmark_corpus/avatar_bounded_resonance/fixture.json`, and `benchmarks/aippocampus/benchmark_avatar_bounded_resonance.py` | Public-safe #1319 deterministic proxy over bounded-resonance posture arms A-E; exploratory only, with no live-model, private-history, default-runtime, or product-quality claim. |
| Recall degradation audit | `docs/evidence/benchmarks/recall-degradation-audit.md` and `benchmarks/aippocampus/benchmark_recall_degradation_audit.py` | Public-safe #1184 audit over the live `recall_context_packet -> agent recall -> MemoryPacket` path; proves synthetic clean-source hits with the same phase/title derive distinct safe route labels without prefilled fixture labels, while blind deepen, manual fallback, generic reopen hints, source-thin no-action failures, and foreground source leaks stay at zero. |
| Map-rot lifecycle-debt benchmark | `docs/evidence/benchmarks/map-rot-lifecycle-debt.md`, `benchmarks/aippocampus/benchmark_map_rot_lifecycle_debt.py`, and `aippocampus_runtime.ops.map_rot_maintenance` | Public-safe #1126/#1196 fixture guard for stale, challenged, quarantined, superseded, missing-middle, deleted/no-recall, dead-lettered, and repeated-wrong cold navigation-map objects; tracks red-line route leaks, challenged backlog age, review-needed count, warnings, silence, refresh, prune/decay candidates, and no-write maintenance actions without claiming automatic cleanup. |
| Multimodal corpus fixture report | `docs/evidence/benchmarks/multimodal-corpus-fixture-report.md` and `benchmark_corpus/public_multimodal_corpus/fixture.json` | Public-safe ATM-Bench-inspired corpus-style multimodal retrieval contract for #531; not conversational media upload recall, ATM-Bench score, or product privacy proof. |
| Conversational media-ingest fixture report | `docs/evidence/benchmarks/conversational-media-ingest-fixture-report.md` and `benchmark_corpus/conversational_media_ingest/fixture.json` | Public-safe conversational media-ingest recall contract for #532; media anchors attach to user turns and text hints cannot replace visual source reopen. |
| Multimodal NIAH evidence-pool fixture report | `docs/evidence/benchmarks/multimodal-niah-evidence-pool-report.md` and `benchmark_corpus/multimodal_niah_evidence_pool/fixture.json` | Public-safe NIAH-style supplied-pool answer-synthesis contract for #533; not retrieval quality, ATM-Bench score, or live vision-model quality. |
| Knowledge pollution/privacy fixture report | `docs/evidence/benchmarks/knowledge-pollution-privacy-fixture-report.md` | Public-safe pollution, stale/authority, privacy partition, source-reopen, and thin capability-contract prototype evidence for #517. |
| Hippocampal hard-negative fixture report | `docs/evidence/benchmarks/hippocampal-hard-negative-fixture-report.md`, `benchmark_corpus/hippocampal_hard_negatives/fixture.json`, and ignored LoCoMo input policy in `benchmark_corpus/locomo_manifest.json` | Public-safe #244/#1041 H1/H2 hard-negative production-like synthetic slice plus #1056 LoCoMo-derived public-dialogue cohort mode, contract controls for near-neighbor lures, unsupported speech, superseded currentness, surface paraphrase lures, seven outcome categories, source-reopen behavior, unsupported-family reporting, and asymmetric scoring; not live or real-history recall quality. |
| Hippocampal recall fixture report | `docs/evidence/benchmarks/hippocampal-recall-fixture-report.md`, `docs/evidence/benchmarks/hippocampal-cross-system-comparison-2026-06-04.md`, and `benchmark_corpus/hippocampal_fixtures/hippocampal_synthetic_v1.jsonl` | Public-safe #229/#230/#231/#236/#238/#1040 diagnostic seed for D/I matrix reporting, D5/D6 gated diagnostics, source-reopen failure, wrong-twin separation, scent layers, abstention, calibration categories, clean-clone reproduction metadata, and the dated H1/H2/H5 local-arm comparison table; not full 50-scene / 350-case P1 quality or external memory-system scores. |
| Hippocampal private annotation protocol | `docs/evidence/benchmarks/hippocampal-private-annotation-protocol.md` | Private real-history H1/H2 sampling, truth-source independence, reviewer/adjudication flow, sanitized dated report template, and privacy exclusions for #232; not a committed private case pack. |
| Fresh-thread recall demo evidence | `docs/evidence/benchmarks/fresh-thread-recall-demo-2026-05-31.md` and `docs/evidence/benchmarks/fresh-thread-expanded-coverage-2026-06-03.md` | Public-safe three-arm fresh-thread recall flows, negative controls, source-reopen boundaries, multi-turn/correction/threshold controls, the expanded #490 claim boundary, and the 2026-06-10 #281 public fixture validation readout. |
| Recall navigation comparison smoke | `docs/evidence/benchmarks/recall-navigation-comparison-2026-06-03.md` | Public-safe deterministic #465 comparison and narrow #201/#281/#309/#248/#1188 proxy for direct `search_memory`, hook-only, progressive `recall_context -> recall_deepen`, attention-router navigation-only over the same candidate set, foreground packet source reopen, and source-joined core/sentinel vague-cue candidate funnels; covers vague cues, multilingual cue fixtures including an Arabic continuity cue, stale-handle rejection, source-ref rejoin, deictic fail-closed behavior, and claim-boundary metrics without live quality, answer-quality, default-prefilter, or broad default-foreground-lift claims. |
| Recall navigation promotion harness | `docs/evidence/benchmarks/recall-navigation-comparison-2026-06-03.md` and `tools/aippocampus/smoke/smoke_recall_navigation_promotion.py` | Public-safe #1302/#1185/#1300/#1301 promotion contract for same-corpus/same-query/same-budget recall-navigation arms; reports baseline flat recall, attention-router navigation-only, macro-navigation prior, and navigation+deepen rows, feature hurt/no-op cases, stale/conflict/noise/wrong-source distractors, attention-cost counters, macro active-layer/fanout/momentum readouts, route-family selection counters, and zero safety red lines without claiming macro/router default readiness. |
| Retrieval score-fusion public calibration | `skills/aippocampus/scripts/aippocampus_runtime/recall/score_fusion_calibration.py`, `skills/aippocampus/scripts/aippocampus_runtime/recall/score_fusion.py`, and `tests/aippocampus/test_retrieval_score_fusion.py` | Public-safe #309 deterministic calibration report for post-source-join ranking weights: exact-quote guard, question-tracking semantic bridge, wrong-stance lure suppression, explicit vector-unavailable fallback, and missing source-join rejection. It is score-policy evidence only, not default vector-prefilter adoption, local embedding adapter evidence, live answer quality, or source truth. |
| Route feedback fixture | `benchmark_corpus/route_feedback/fixture.json`, `aippocampus_runtime.recall.feedback_events`, and `tests/aippocampus/test_recall_feedback_events.py` | Public-safe #937/#950 route-feedback contract for source-reopen success, blocked-route suppression, wrong-route demotion, blend-context/signal-family grouping, and route activation metadata. It is calibration evidence only: it does not mutate score-fusion weights, store private telemetry, or let activation metadata support factual claims. |
| Prompt hook hot-path funnel smoke | `benchmarks/aippocampus/benchmark_prompt_hot_path_funnel.py` and `skills/aippocampus/references/ambient-hooks.md` | Deterministic #602 local-only route-funnel contract for thread/profile hints, cue-cache aliases, bounded trigram FTS fallback, no-op skips, and latency plus false-skip/wrong-scent/promotion counters; not semantic paraphrase or live recall-quality evidence. |
| Living cue cache smoke and hook guard | `tools/aippocampus/smoke/smoke_living_cue_cache.py`, `tests/aippocampus/test_living_cue_cache.py`, and `tests/aippocampus/test_aippocampus_prompt_hook.py` | Public-safe #281 fixture and default-hook guard for learned-phrase-to-source-handle bridging, stale/temporary suppression, over-personalization diagnostics, no-live-LLM selector output, and scent-only hot-path consumption; not fresh-thread quality proof. |
| Query-pattern routes fixture | `aippocampus_runtime.warm_ambient.query_pattern_enrichment --fixture --json`, `aippocampus_runtime.warm_ambient.query_pattern_routes`, `tests/aippocampus/test_query_pattern_enrichment.py`, `tests/aippocampus/test_prompt_hot_path_funnel.py`, `tests/aippocampus/test_onboard_codex.py`, and `tests/aippocampus/test_aippocampus_prompt_hook.py` | Public-safe #574 registry/import planning plus deterministic sidecar writer/reader, default onboarding registry-metadata and reviewed-semantic-trigger route publication, alias-source diagnostics, and hot-path scent consumption; covers changed-generation work items, cache reuse, idempotent existing work, digest invalidation, provider/privacy suppression, stale sidecar filtering, no-live-LLM foreground packets, registry-only nickname misses, reviewed/generated natural multilingual alias hits, and public reports that omit alias text/local paths. Not live DeepSeek quality, scheduler adoption, or latency savings. |
| Fresh-thread real-history boundary smoke | `docs/evidence/benchmarks/fresh-thread-real-history-smoke-2026-06-02.md` and `docs/evidence/benchmarks/fresh-thread-expanded-coverage-2026-06-03.md` | Sanitized real-history boundary smoke for ready-lock reopenability, thread-only lock suppression, current-repo fact negative control, and #490 multi-ref aggregate coverage; not a recall-quality benchmark. |
| Field Continuity fixture report | `docs/evidence/benchmarks/field-continuity-eval-design.md`, `docs/evidence/benchmarks/field-continuity-fixture-report.md`, and `benchmark_corpus/field_continuity/fixture.json` | Public-safe #454/#982 scenario-family contract for second-user magic-moment reports from Discussion #428; includes public reproducibility tracks, FTS-only/summary-first/semantic-only baselines, a supporting bounded #281 `issue_readouts.github_281` fixture-quality proxy, private seed hash/aggregate rules, by-arm route/source/abstention/leakage/cost metrics, and overclaim/wrong-family/stale-route controls without live or private-history quality claims. The #281 closeout readout now lives in the fresh-thread recall demo runner. |
| Provider conformance kit report | `docs/evidence/benchmarks/provider-conformance-fixture-report.md` and `benchmark_corpus/provider_conformance/fixture.json` | Public-safe #981/#988 kit v1 for provider/session identity, cross-provider source-reopen affordances, copied-summary downgrade, injected host content demotion, MCP source-ref metadata shape, real `generic-jsonl` / `claude-code` normalizer suites, and provider failure examples; not live multi-client support, AgentMemory behavior, or real cross-host continuity quality. |
| Segmented merge policy fixture report | `docs/evidence/benchmarks/segmented-merge-policy-fixture-report.md` and `benchmark_corpus/segmented_merge_policy/fixture.json` | Public-safe #375/#853 calibration fixture for `SEGMENT_MERGE_POLICY` and stable source-key dedupe over cross-segment diversity, adjacent-turn pairing, duplicate nearby recap suppression, stable source join overlap, and stale/superseded currentness; not source-evidence retrieval or real long-thread recall quality. |
| Dream live shadow A/B reminder evidence | `docs/evidence/dream/dream-live-shadow-ab-2026-05-30.md` | Dated aggregate run for explicit recall-reminder frequency, shadow assignment, nearest-prior exposure attribution, and delivered-vs-shadow claim boundaries. |
| Dream topology and shadow-route scout | `aippocampus_runtime.dream.topology_scout` and `tests/aippocampus/test_dream_topology_scout.py` | Public-safe deterministic Dream topology scout for source-anchored candidate shapes plus #1313 shadow-route visible/latent route nominations. Shadow-route candidates require source overlap or failed-route residue; generic shared vocabulary, pure transform-orbit membership, private psychology, user diagnosis, profile claims, and source-free symbolic claims stay rejected or explain-only. |
| Agency host-surface replay evidence | `docs/evidence/benchmarks/agency-host-surface-codex-desktop-2026-06-05.md` | Public-safe #763 Codex Desktop hidden-route lifecycle replay for show/hold/suppress timing, source-visible suppression, duplicate suppression, recent negative feedback, and usefulness/annoyance/correction ledger boundaries. |
| Dream private real-history offline evidence | `docs/evidence/dream/dream-real-history-model-backed-eval-2026-05-31.md` and `docs/evidence/dream/dream-private-large-history-diagnostic-2026-06-04.md` | Sanitized aggregate private-history Dream eval and diagnostic evidence for selected ready-pack structural lift, shadow replay boundaries, coding-probe deferment, E2E50 seed scan/manual annotation boundaries, agency host-timing replay, coding decision-shadow proxy evidence, and live semantic gate worker/availability diagnostics. |
| Dream benchmark-corpus shadow evidence | `docs/evidence/dream/dream-live-shadow-benchmark-corpus-2026-05-31.md` | Dated public-corpus negative-control run for explicit reminder frequency and potential dream-only over-personalization activation. |
| Question extraction axis coverage evidence | `docs/evidence/question/question-extraction-axis-coverage-2026-05-31.md` | Dated live no-write aggregate field-presence run for GitHub #153 and its prompt/repair/telemetry fix boundary. |
| Question-aware public shadow evidence | `docs/evidence/question/question-aware-public-shadow-2026-06-10.md` and `benchmark_corpus/question_aware_public_shadow/fixture.json` | Checked-in public/source-replayable #248 shadow cases for question-aware source reopen, selected answer-review deltas, adaptive-threshold readout, and noise/code negative controls; not private-history quality, live user-visible lift, theme-resonance calibration, default prefilter adoption, or #248 closeout. |
| Thread-story public shadow closeout | `skills/aippocampus/scripts/aippocampus_runtime/reflection/thread_story.py` and `tests/aippocampus/test_thread_story_packet.py` | Public-safe #313 structured-text closeout report for source-backed thread-story packets, leakage/contradiction/persona/interference/noise controls, packet-only factual-answer blocking, and source-reopened answer comparison; not private-history story quality, live model-family behavior, default recall lift, user/personality truth, or source truth from packet routes. |
| Community field reports | `docs/evidence/community-field-reports.md`, the public `/evidence/` page, and GitHub Discussions | Public-safe user and contributor reports. These are community signals until reviewed and promoted into official benchmark evidence, readiness ledgers, or known-gap docs. |
| Raw / generated artifacts | `.tmp/` or `benchmark_corpus/reports/` | Local JSON outputs, historical benchmark snapshots, run-history diff artifacts, and case packs. Keep them gitignored unless a small public subset is deliberately promoted. |

## Benchmark Runners

These repository-level runners live under `benchmarks/aippocampus/`. Every new
benchmark runner should be added here and linked to its dated evidence owner.
Public runner files should expose direct-script help/JSON behavior, and
publicly documented runner files should also work through `python -m` when they
are reasonable module targets. Track-owned helper modules may remain
library-only, but direct execution must say so and point to the supported
aggregate runner instead of failing with an import traceback or exiting with
empty output. The PR-tier guard for this contract is
`tests/aippocampus/test_benchmark_entrypoints.py`.

| Surface | Entrypoint | Reads / updates |
| --- | --- | --- |
| Shared benchmark helper entrypoint contract | `benchmarks/aippocampus/benchmark_entrypoints.py` | Library-only helper execution contract for #1030; no benchmark score or evidence claim |
| Shared benchmark uncertainty helper | `benchmarks/aippocampus/benchmark_statistics.py` | `docs/evidence/benchmarks/memory-decision-benchmark-plan.md` |
| One-command baseline suite, profile ladder, and threshold metadata | `benchmarks/aippocampus/benchmark_suite.py` | `docs/evidence/benchmarks/memory-decision-benchmark-plan.md`, `docs/evidence/readiness/public-readiness-verification.md` |
| Benchmark run-history diff and regression guardrail | `benchmarks/aippocampus/benchmark_run_history_diff.py` | `docs/evidence/benchmarks/memory-decision-benchmark-plan.md`, `.tmp/` or `benchmark_corpus/reports/` |
| Track A memory decision gate | `benchmarks/aippocampus/benchmark_memory_decision_gate.py` | `docs/evidence/benchmarks/memory-decision-benchmark-plan.md`, `docs/evidence/benchmarks/memory-pain-fixture-report.md` |
| Track B source-evidence retrieval wrapper | `benchmarks/aippocampus/benchmark_source_evidence_retrieval.py` facade with track-owned helpers in `benchmarks/aippocampus/source_evidence/` | `docs/evidence/benchmarks/memory-decision-benchmark-plan.md`, `benchmark_corpus/README.md`; includes #309 diagnostic `semantic_bridge_lift` / wrong-stance source-joined reranker metrics, not default vector behavior |
| Track S semantic robustness diagnostics | `benchmarks/aippocampus/benchmark_semantic_robustness.py` | `docs/evidence/benchmarks/semantic-robustness-track-s.md`, `docs/evidence/benchmarks/memory-decision-benchmark-plan.md`, #747 |
| Public reliability gauntlet | `benchmarks/aippocampus/benchmark_public_reliability_gauntlet.py` | `docs/evidence/benchmarks/public-reliability-gauntlet.md`, `docs/evidence/benchmarks/public-reliability-gauntlet-2026-06-10.json`, #1102 |
| Attention navigation quality | `benchmarks/aippocampus/benchmark_attention_navigation_quality.py` | `docs/evidence/benchmarks/attention-navigation-quality.md`, #1111 |
| Attention score-fusion calibration | `benchmarks/aippocampus/benchmark_attention_score_fusion_calibration.py` | `docs/evidence/benchmarks/attention-score-fusion-calibration.md`, #1112 |
| Agent continuity loop gate | `benchmarks/aippocampus/benchmark_agent_continuity_loop.py` | `docs/evidence/benchmarks/agent-continuity-loop.md`, #1163, #1181 |
| Avatar bounded resonance proxy pilot | `benchmarks/aippocampus/benchmark_avatar_bounded_resonance.py` | `docs/research/avatar-bounded-resonance-pilot-2026-06-12.md`, `docs/research/avatar-bounded-resonance-pilot-2026-06-12.json`, `benchmark_corpus/avatar_bounded_resonance/fixture.json`, #1319 |
| Recall degradation audit | `benchmarks/aippocampus/benchmark_recall_degradation_audit.py` | `docs/evidence/benchmarks/recall-degradation-audit.md`, #1184 |
| Benchmark maturity helper | `benchmarks/aippocampus/benchmark_maturity.py` | `docs/evidence/benchmarks/design/benchmark-maturity-gates.md`, #1165 |
| Map-rot lifecycle-debt benchmark | `benchmarks/aippocampus/benchmark_map_rot_lifecycle_debt.py` and `aippocampus_runtime.ops.map_rot_maintenance` | `docs/evidence/benchmarks/map-rot-lifecycle-debt.md`, #1126, #1196 |
| Multimodal corpus-style retrieval contract | `benchmarks/aippocampus/benchmark_multimodal_corpus_retrieval.py` | `docs/evidence/benchmarks/multimodal-corpus-fixture-report.md`, `benchmark_corpus/README.md`, `benchmark_corpus/public_multimodal_corpus/fixture.json`, #531 |
| Conversational media-ingest recall contract | `benchmarks/aippocampus/benchmark_conversational_media_ingest_recall.py` | `docs/evidence/benchmarks/conversational-media-ingest-fixture-report.md`, `benchmark_corpus/README.md`, `benchmark_corpus/conversational_media_ingest/fixture.json`, #532 |
| Multimodal NIAH evidence-pool contract | `benchmarks/aippocampus/benchmark_multimodal_niah_evidence_pool.py` | `docs/evidence/benchmarks/multimodal-niah-evidence-pool-report.md`, `benchmark_corpus/README.md`, `benchmark_corpus/multimodal_niah_evidence_pool/fixture.json`, `benchmark_corpus/public_multimodal_corpus/fixture.json`, #533 |
| ShareGPT public-corpus seeded sampler | `benchmarks/aippocampus/sharegpt_sampling.py` | `docs/evidence/benchmarks/memory-decision-benchmark-plan.md`, `benchmark_corpus/sharegpt_manifest.json` |
| Coding decision-shadow Tracks A-E | `benchmarks/aippocampus/benchmark_coding_decision_shadow.py` | `docs/evidence/benchmarks/memory-decision-benchmark-plan.md`, `docs/research/agent-coding-context-analysis.md` |
| H1/H2 hard-negative production-like synthetic slice, public-dialogue cohort, and contract controls | `benchmarks/aippocampus/benchmark_hippocampal_hard_negatives.py` | `docs/evidence/benchmarks/hippocampal-hard-negative-fixture-report.md`, `docs/evidence/benchmarks/hippocampal-recall-plan.md`, `benchmark_corpus/hippocampal_hard_negatives/fixture.json`, `benchmark_corpus/locomo_manifest.json`, #244/#1041/#1056 |
| Hippocampal recall-discrimination diagnostic benchmark | `benchmarks/aippocampus/benchmark_hippocampal_recall.py` | `docs/evidence/benchmarks/hippocampal-recall-fixture-report.md`, `docs/evidence/benchmarks/hippocampal-cross-system-comparison-2026-06-04.md`, `docs/evidence/benchmarks/hippocampal-recall-plan.md`, `benchmark_corpus/hippocampal_fixtures/hippocampal_synthetic_v1.jsonl`, #229/#230/#231/#238/#1040 |
| Hippocampal recall-discrimination fixture builder | `benchmarks/aippocampus/build_hippocampal_fixture.py` | `docs/evidence/benchmarks/hippocampal-recall-fixture-report.md`, `benchmark_corpus/hippocampal_fixtures/hippocampal_synthetic_v1.jsonl`, #229 |
| Knowledge pollution, privacy partition, and capability-contract smoke | `benchmarks/aippocampus/benchmark_knowledge_pollution.py` | `docs/evidence/benchmarks/memory-decision-benchmark-plan.md`, `docs/evidence/benchmarks/knowledge-pollution-privacy-fixture-report.md`, `docs/architecture/high-risk-answer-gates.md` |
| LongMemEval retrieval-only benchmark and rerank analysis | `benchmarks/aippocampus/benchmark_longmemeval.py` and `benchmarks/aippocampus/benchmark_longmemeval_rerank_analysis.py` | `docs/evidence/benchmarks/longmemeval.md`, `docs/evidence/benchmarks/longmemeval-semantic-rerank-analysis-2026-06-10.json`, `docs/evidence/benchmarks/longmemeval-exact-line-repair-2026-06-12.json`, `docs/evidence/benchmarks/longmemeval-semantic-cache-path-2026-06-12.json`, `benchmark_corpus/longmemeval_manifest.json`, #1092, #1193, #1305 |
| LongMemEval fixed-reader answer/latency harness | `benchmarks/aippocampus/benchmark_longmemeval_answer.py` | `docs/evidence/benchmarks/longmemeval.md`, `benchmark_corpus/longmemeval_manifest.json`, #1157, #1229 |
| LongMemEval-V2 context-mapping pilot | `benchmarks/aippocampus/benchmark_longmemeval_v2_context.py` | `docs/evidence/benchmarks/longmemeval.md`, `benchmark_corpus/longmemeval_manifest.json`, #259 |
| LongMemEval-V2 official-harness pilot decision and adapter | `benchmarks/aippocampus/benchmark_longmemeval_v2_official_pilot.py` and `benchmarks/aippocampus/longmemeval_v2_aippocampus_adapter.py` | `docs/evidence/benchmarks/longmemeval.md`, `benchmark_corpus/longmemeval_manifest.json`, #1155, #1229 |
| AMemGym metadata, source-backed overlay smoke, official-runner bridge with AIppocampus BaseAgent arms, live-provider blocker, and Codex Desktop AMemGym-style arms | `benchmarks/aippocampus/benchmark_amemgym.py`, `benchmarks/aippocampus/benchmark_amemgym_official.py`, `benchmarks/aippocampus/benchmark_codex_desktop_amemgym.py` | `docs/evidence/benchmarks/amemgym.md`, `docs/evidence/benchmarks/amemgym-official-live-provider-blocker-2026-06-09.md`, `benchmark_corpus/amemgym_manifest.json`, `benchmark_corpus/amemgym_fixture/fixture.json`, #733, #742, #1229 |
| STATE-Bench Agent Learning feasibility, adapter scaffold, and matched-run preflight | `benchmarks/aippocampus/benchmark_state_bench_agent_learning.py` | `docs/evidence/benchmarks/state-bench-agent-learning.md`, `docs/evidence/benchmarks/state-bench-agent-learning-preflight-2026-06-10.json`, #1043 |
| MemoryAgentBench metadata, case-pack, Stage 3 dry-run, deterministic local apply instrumentation, and optional parquet row smoke | `benchmarks/aippocampus/benchmark_memoryagentbench.py` | `docs/evidence/benchmarks/memoryagentbench.md`, `benchmark_corpus/memoryagentbench_manifest.json`, #608, #614, #694, #995 |
| PersonaMem readiness gate | no runner yet | `docs/evidence/benchmarks/personamem-readiness.md`, #1159 |
| LoCoMo public longitudinal-users control | `benchmarks/aippocampus/benchmark_locomo_public_users.py` | `docs/evidence/benchmarks/public-longitudinal-users.md`, `benchmark_corpus/README.md`, `benchmark_corpus/locomo_manifest.json` |
| LoCoMo fixed-reader text-QA harness | `benchmarks/aippocampus/benchmark_locomo_qa.py` | `docs/evidence/benchmarks/public-longitudinal-users.md`, `benchmark_corpus/README.md`, `benchmark_corpus/locomo_manifest.json`, #1158, #1229 |
| LoCoMo answer-usefulness prototype | `benchmarks/aippocampus/benchmark_locomo_answer_usefulness.py` | `docs/evidence/benchmarks/public-longitudinal-users.md`, `benchmark_corpus/README.md`, #400 |
| Public longitudinal pseudo-user coding implicit-knowledge contract smoke | `benchmarks/aippocampus/benchmark_public_longitudinal_users.py` | `docs/evidence/benchmarks/public-longitudinal-users.md`, `benchmark_corpus/public_longitudinal_users/README.md` |
| VCS future-event recall, source-disambiguation, and route-chain/actionability benchmark scaffold | `benchmarks/aippocampus/benchmark_vcs_future_event_recall.py` | `docs/evidence/benchmarks/public-longitudinal-users.md`, `docs/evidence/benchmarks/react-real-vcs-production-like-disambiguation-2026-06-04.md`, `benchmark_corpus/public_longitudinal_users/README.md`, #309 |
| VCS / rollout future-event fixture builder | `benchmarks/aippocampus/build_vcs_future_event_fixture.py` | `docs/evidence/benchmarks/public-longitudinal-users.md`, `benchmark_corpus/public_longitudinal_users/README.md` |
| FTS5 real-history recall | `benchmarks/aippocampus/benchmark_fts5_recall.py` | `docs/evidence/readiness/public-readiness-verification.md`, `docs/planning/next-iteration-plan.md` |
| Public CJK local-recall fixture | `benchmarks/aippocampus/benchmark_fts5_recall.py --public-cjk-fixture` | `docs/evidence/benchmarks/cjk-local-recall-fixture-report.md`, #852, #1022, #1054 |
| Track C payload fidelity | `benchmarks/aippocampus/benchmark_payload_fidelity.py` | `docs/evidence/benchmarks/memory-decision-benchmark-plan.md`, `docs/evidence/benchmarks/memory-pain-fixture-report.md` |
| Track D synthetic compaction continuity | `benchmarks/aippocampus/benchmark_compaction_continuity.py` | `docs/evidence/benchmarks/memory-decision-benchmark-plan.md`, `docs/evidence/readiness/public-readiness-verification.md` |
| E2E50 public-safe behavior-pack scorer | `benchmarks/aippocampus/benchmark_e2e50_silent_constraint.py`; sequence/load validator in `aippocampus_runtime/coding/sequence_packets.py`; Episode/Arc builder in `aippocampus_runtime/coding/episode_arcs.py` | `docs/evidence/benchmarks/memory-decision-benchmark-plan.md`, `docs/architecture/episode-arc-read-models.md`, `benchmark_corpus/e2e50_silent_constraint/fixture.json`, #279/#663/#575/#1154 |
| Continuous-memory attribution arms, host-native baseline, pre-registration, preregistered slice readouts including `public_synthetic_preregistered_repeat` and `github_1153_context_loss_public_continuity_v1`, cost/harm ledger, cost/harm sensitivity, scenario provenance/holdout controls, and the missing-context diagnostic boundary | `benchmarks/aippocampus/benchmark_continuous_memory_arms.py` | `docs/evidence/benchmarks/memory-decision-benchmark-plan.md`, #378/#406/#407/#408/#409/#410/#1153 |
| Optional live semantic gate | `benchmarks/aippocampus/benchmark_live_semantic_gate.py` | `docs/evidence/benchmarks/memory-decision-benchmark-plan.md`, `benchmark_corpus/README.md` |
| Prompt hook local hot-path funnel | `benchmarks/aippocampus/benchmark_prompt_hot_path_funnel.py` | `skills/aippocampus/references/ambient-hooks.md`, #602 |
| Fresh-thread public-safe recall demo | `benchmarks/aippocampus/benchmark_fresh_thread_recall_demo.py` | `docs/evidence/benchmarks/fresh-thread-recall-demo-2026-05-31.md`, `docs/evidence/benchmarks/fresh-thread-expanded-coverage-2026-06-03.md`, `docs/evidence/current-claims.md`, `docs/guides/demo-scenarios.md`, #281 |
| Field Continuity / magic-moment reproducibility contract | `benchmarks/aippocampus/benchmark_field_continuity.py` | `docs/evidence/benchmarks/field-continuity-eval-design.md`, `docs/evidence/benchmarks/field-continuity-fixture-report.md`, `docs/evidence/benchmarks/memory-decision-benchmark-plan.md`, `benchmark_corpus/field_continuity/fixture.json`, #454, #982, #281 |
| Provider conformance contract fixture | `benchmarks/aippocampus/benchmark_provider_conformance.py` | `docs/evidence/benchmarks/provider-conformance-fixture-report.md`, `docs/architecture/provider-entrypoint-inventory.md`, `benchmark_corpus/provider_conformance/fixture.json`, #988, #981 |
| Claude Code real-host dogfood | `tools/aippocampus/smoke/smoke_claude_code_history.py`, `tools/aippocampus/smoke/smoke_claude_code_mcp_host.py`, `tools/aippocampus/smoke/smoke_cross_agent_continuity.py` | `docs/evidence/readiness/claude-code-dogfood-2026-06-09.md`, `docs/guides/claude-code-mcp.md`, #998, #1021 |
| Structured cognitive portrait | `benchmarks/aippocampus/benchmark_cognitive_portrait.py` | `docs/research/compact-activation-signals.md`, `docs/evidence/benchmarks/memory-decision-benchmark-plan.md` |
| Thread-story packet and public closeout diagnostic | `skills/aippocampus/scripts/aippocampus_runtime/reflection/thread_story.py` | `docs/research/compact-activation-signals.md`, `docs/research/affect-side-channel.md`, `docs/evidence/current-claims.md`, #313 |
| Question-aware real-history structural benchmark, optional answer-quality review, and public shadow fixture | `benchmarks/aippocampus/benchmark_question_aware_real_history.py` | `docs/architecture/question-tracking-subconscious.md`, `docs/evidence/question/question-aware-answer-quality-2026-06-08.md`, `docs/evidence/question/question-aware-public-shadow-2026-06-10.md`, `benchmark_corpus/question_aware_public_shadow/fixture.json`, `docs/research/compact-activation-signals.md`, `docs/planning/next-iteration-plan.md`, `docs/evidence/readiness/stage-0-5-readiness.md`, `docs/evidence/benchmarks/memory-decision-benchmark-plan.md`, #248 |
| Question tracking selected-fixture calibration | `benchmarks/aippocampus/benchmark_question_tracking_calibration.py` | `docs/architecture/question-tracking-subconscious.md`, `docs/planning/technical-differentiation-analysis.md`, `docs/evidence/current-claims.md`, #1059 |
| Subconscious event-salience intake gate | `tests/aippocampus/test_subconscious_event_salience_gate.py`; opt-in `python -m aippocampus_runtime.subconscious.jobs --event-salience-gate --dry-run --json` | `docs/architecture/cognitive-runtime-architecture.md`, `docs/architecture/question-tracking-subconscious.md`, `skills/aippocampus/references/subconscious-jobs.md`, `docs/evidence/current-claims.md`, #1058 |
| Warm ambient recall benchmark | `benchmarks/aippocampus/benchmark_warm_ambient_recall.py` | `docs/research/ambient-associative-recall.md`, `benchmark_corpus/README.md` |
| Warm ambient parameter sweep | `benchmarks/aippocampus/benchmark_warm_ambient_sweep.py` | `docs/research/ambient-associative-recall.md`, `docs/evidence/benchmarks/memory-decision-benchmark-plan.md` |
| State-dependent warm ambient preactivation | `benchmarks/aippocampus/benchmark_state_dependent_preactivation.py` | `docs/evidence/benchmarks/state-dependent-preactivation-2026-06-10.md`, `docs/research/ambient-associative-recall.md`, #1082 |
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
| E2E50 silent-constraint candidate seed scanner | `tools/aippocampus/smoke/smoke_e2e50_seed_candidates.py`; deterministic unittest included in `benchmark-smoke` | `docs/evidence/benchmarks/memory-decision-benchmark-plan.md`, `docs/evidence/benchmarks/e2e50-private-local-seed-followup-2026-06-10.md`, #279/#1086 |
| E2E50 public-safe behavior-pack scorer and optional private annotation readiness replay | `benchmarks/aippocampus/benchmark_e2e50_silent_constraint.py`; deterministic unittest included in `benchmark-smoke`; sequence/load validator in `aippocampus_runtime/coding/sequence_packets.py`; Episode/Arc builder in `aippocampus_runtime/coding/episode_arcs.py` | `docs/evidence/benchmarks/memory-decision-benchmark-plan.md`, `docs/architecture/episode-arc-read-models.md`, `benchmark_corpus/e2e50_silent_constraint/fixture.json`, `docs/evidence/benchmarks/e2e50-private-annotation-readiness-2026-06-10.json`, #279/#663/#575/#1154 |
| Cognitive-load public behavior-trace feedback fixture | `aippocampus_runtime.recall.cognitive_load_sidecar.build_public_behavior_trace_feedback_report`; deterministic unittest `tests/aippocampus/test_cognitive_load_sidecar.py` | `docs/architecture/cognitive-load-sidecar.md`, `docs/evidence/current-claims.md`, #575 |
| Episode/Arc public gappy-chain calibration fixture | `aippocampus_runtime.coding.episode_arcs.build_public_gappy_chain_calibration_report`; deterministic unittest `tests/aippocampus/test_episode_arcs.py` | `docs/architecture/episode-arc-read-models.md`, `docs/evidence/current-claims.md`, #663 |
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
| Recall navigation promotion harness | `tools/aippocampus/smoke/smoke_recall_navigation_promotion.py` | `docs/evidence/benchmarks/recall-navigation-comparison-2026-06-03.md`, #1302, #1185, #1300, #1301 |
| Real-history semantic scope smoke | `tools/aippocampus/smoke/smoke_semantic_scope_real_history.py` | `docs/evidence/readiness/stage-0-5-readiness.md` |
| Semantic sidecar source-review smoke | `tools/aippocampus/smoke/smoke_semantic_scope_source_review.py`; public shadow fixture in `tests/fixtures/semantic_scope_source_review_shadow/` | `docs/evidence/readiness/stage-0-5-readiness.md`, `docs/evidence/readiness/public-readiness-verification.md`, #993 |
| Selected source-evidence recall eval and candidate-space diagnostics | `tools/aippocampus/smoke/smoke_source_evidence_recall_eval.py` | `docs/evidence/readiness/stage-0-5-readiness.md`, `docs/evidence/benchmarks/memory-decision-benchmark-plan.md`, #458 |
| Optional live question-confirmation smoke | `tools/aippocampus/smoke/smoke_question_confirmation_live.py` | `docs/architecture/question-tracking-subconscious.md`, `docs/evidence/readiness/stage-0-5-readiness.md` |
| Question prefilter parity smoke | `tools/aippocampus/smoke/smoke_question_prefilter_parity.py` | `docs/architecture/question-tracking-subconscious.md`, #248 |
| Agency host-timing replay smoke | `tools/aippocampus/smoke/smoke_agency_host_timing.py` | `docs/research/agency-from-cognitive-map.md`, `docs/evidence/benchmarks/agency-host-surface-codex-desktop-2026-06-05.md`, #312, #763 |
| Route-readiness Cognitive Observatory smoke | `tools/aippocampus/smoke/smoke_route_readiness_observatory.py` and `tests/aippocampus/test_cognitive_observatory.py`; includes query-pattern and cognitive-load public/private summary projections | `docs/architecture/cognitive-runtime-architecture.md`, `docs/guides/public-api.md`, #574, #575, #576 |
| Worker-to-hook handoff smoke | `tools/aippocampus/smoke/smoke_worker_hook_handoff.py` | `docs/research/ambient-associative-recall.md`, `skills/aippocampus/references/ambient-hooks.md`, #574, #909 |
| Dream real-history structural, public shadow, topology scout, long-context atlas pack, live atlas pilot, and user-visible eval | `skills/aippocampus/scripts/aippocampus_runtime/dream/atlas_pack.py`, `skills/aippocampus/scripts/aippocampus_runtime/dream/atlas_live_pilot.py`, `skills/aippocampus/scripts/aippocampus_runtime/dream/real_history_eval.py`, `skills/aippocampus/scripts/aippocampus_runtime/dream/public_shadow_report.py`, `skills/aippocampus/scripts/aippocampus_runtime/dream/topology_scout.py`, `tests/aippocampus/test_dream_atlas_pack.py`, and `tests/aippocampus/test_dream_live_shadow_ab.py` | `docs/evidence/dream/dream-real-history-model-backed-eval-2026-05-31.md`, `docs/evidence/dream/dream-atlas-live-pilot-2026-06-12.md`, `docs/evidence/current-claims.md`, `docs/research/dream-task-design.md`, #163, #1268, #1269, #1286 |
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
