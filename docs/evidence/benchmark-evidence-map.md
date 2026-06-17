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
[`benchmarks/design/memory-decision-benchmark-plan.md`](benchmarks/design/memory-decision-benchmark-plan.md).
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

## Task Cards

| Task | Open first | Do not do |
| --- | --- | --- |
| Recommend AIppocampus publicly | [`can-claim-ladder.md`](can-claim-ladder.md) | Do not quote a dated report as current product copy until it has a current-claims row. |
| Close or update a benchmark issue | [`benchmark-evidence-maturity.md`](benchmark-evidence-maturity.md) | Do not close a broad runtime-capability issue from a narrow fixture or adapter smoke. |
| Choose what to run next | [`benchmarks/design/benchmark-priority-map.md`](benchmarks/design/benchmark-priority-map.md) | Do not derive priority from the length or age of the maintainer directory. |
| Explain a negative or blocker result | [`current-claims.md#confirmed-scope-boundaries-expected-null-results`](current-claims.md#confirmed-scope-boundaries-expected-null-results) | Do not hide expected-null or provider-blocked rows in archaeology. |
| Add a new public-safe field report | [`community-field-reports.md`](community-field-reports.md) | Do not paste private source, local paths, or raw rollouts into evidence docs. |

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

## Ledger Hygiene

New evidence rows should be line-addressable: one stable heading per issue or
report slice, short summarized metrics, links to source files/commands, and no
raw command JSON. If a result needs a large payload, write a separate report or
fixture file and link it from the ledger instead of embedding the payload.

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
   [`benchmarks/design/memory-decision-benchmark-plan.md`](benchmarks/design/memory-decision-benchmark-plan.md).
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
   [`benchmarks/reports/field-journey/journey-public-time-sliced-replay.md`](benchmarks/reports/field-journey/journey-public-time-sliced-replay.md).
8. Need the multimodal memory benchmark-family map for #528:
   [`benchmarks/design/multimodal-memory-benchmark-map.md`](benchmarks/design/multimodal-memory-benchmark-map.md).
9. Need the ATM-Bench Hard protocol boundary for multimodal source-backed
   recall before adapting #528:
   [`benchmarks/design/atm-bench-hard-protocol-boundary.md`](benchmarks/design/atm-bench-hard-protocol-boundary.md).
10. Need LongMemEval source, commands, the current 500-question V1
   retrieval-only slice, the optional lexical exact-line reranker diagnostic,
   #1193 structural exact-line failure report, #1305 semantic warm-cache path,
   source-worker-surface proxy and 500Q LLM upper-bound comparison, the
   #1424/#1425/#1426 source factual-alias slice, the fixed-reader
   answer/latency harness boundary, historical 50-question smoke rows, the V2
   context-mapping pilot, or the V2 official-harness pilot decision and adapter
   boundary:
   [`benchmarks/longmemeval.md`](benchmarks/longmemeval.md).
11. Need the public reliability gauntlet that separates runtime pressure,
    mis-recall diagnostics, and pollution hygiene for #1102:
    [`benchmarks/public-reliability-gauntlet.md`](benchmarks/public-reliability-gauntlet.md).
12. Need the attention-router navigation-quality gate for route precision,
    masks, stale/currentness, conflict, action-time, anti-nag, and bounded
    evidence red lines:
    [`benchmarks/reports/recall-navigation/attention-navigation-quality.md`](benchmarks/reports/recall-navigation/attention-navigation-quality.md).
13. Need audited attention score-fusion calibration over sanitized feature rows
    before changing router weights:
    [`benchmarks/reports/recall-navigation/attention-score-fusion-calibration.md`](benchmarks/reports/recall-navigation/attention-score-fusion-calibration.md).
14. Need the public-safe integrated continuity loop across semantic warming,
    hot routing, facade packets, AIppo, deepen/explain, and budgets:
    [`benchmarks/reports/recall-navigation/agent-continuity-loop.md`](benchmarks/reports/recall-navigation/agent-continuity-loop.md).
15. Need map-rot lifecycle-debt evidence for stale, challenged, quarantined,
    superseded, missing-middle, deleted/no-recall, dead-lettered, or
    repeated-wrong cold navigation-map objects:
    [`benchmarks/reports/field-journey/map-rot-lifecycle-debt.md`](benchmarks/reports/field-journey/map-rot-lifecycle-debt.md).
16. Need the #1195 benchmark-family promotion decision for the first public
    cohort candidate targets, holdout/no-tuning-leak boundaries, usefulness
    blockers, and gate separation:
    [`benchmarks/reports/benchmark-family/benchmark-family-promotion-candidates-2026-06-12.md`](benchmarks/reports/benchmark-family/benchmark-family-promotion-candidates-2026-06-12.md).

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
   [`benchmarks/reports/public-longitudinal/public-longitudinal-users-measurement-2026-05-31.md`](benchmarks/reports/public-longitudinal/public-longitudinal-users-measurement-2026-05-31.md).
4. Need the first real public VCS hard-event smoke:
   [`benchmarks/reports/public-longitudinal/react-real-vcs-smoke-2026-05-31.md`](benchmarks/reports/public-longitudinal/react-real-vcs-smoke-2026-05-31.md).
5. Need the 100+ gold real React VCS measurement with anti-drift negatives
   and counterfactual controls:
   [`benchmarks/reports/public-longitudinal/react-real-vcs-100-gold-2026-05-31.md`](benchmarks/reports/public-longitudinal/react-real-vcs-100-gold-2026-05-31.md).
6. Need the sharper React VCS adversarial controls for source authority,
   keyword drift, behavior-only support, and abstention:
   [`benchmarks/reports/public-longitudinal/react-real-vcs-adversarial-v2-2026-05-31.md`](benchmarks/reports/public-longitudinal/react-real-vcs-adversarial-v2-2026-05-31.md).
7. Need the non-oracle React VCS production-like source-disambiguation
   follow-up for current/effective-vs-stale source ranking:
   [`benchmarks/reports/public-longitudinal/react-real-vcs-production-like-disambiguation-2026-06-04.md`](benchmarks/reports/public-longitudinal/react-real-vcs-production-like-disambiguation-2026-06-04.md).
   For the rollout behavior route-chain/actionability top-k boundary, use
   [`benchmarks/reports/public-longitudinal/rollout-hard-event-route-chain-2026-06-12.md`](benchmarks/reports/public-longitudinal/rollout-hard-event-route-chain-2026-06-12.md).
   For the broader #1197 public-safe rollout hard-event cohort, use
   [`benchmarks/reports/public-longitudinal/rollout-hard-event-cohort-v2-2026-06-12.md`](benchmarks/reports/public-longitudinal/rollout-hard-event-cohort-v2-2026-06-12.md).
   For the sparse provenance codebook V0 fixture and #1190 route-reconstruction
   proof boundary, use
   [`benchmarks/reports/public-longitudinal/sparse-provenance-codebook-v0-2026-06-12.md`](benchmarks/reports/public-longitudinal/sparse-provenance-codebook-v0-2026-06-12.md).
   For the #1869 scale-layer follow-up, use the canonical contract in
   [`../architecture/source/sparse-provenance-codebook.md`](../architecture/source/sparse-provenance-codebook.md):
   current V1 evidence is fixture-local source-object persistence,
   structured-trace template/residual masking, compression/proof reporting,
   fingerprint-reuse rejection, object-family status propagation, health
   projection, and adversarial red-line tests, not GB/TB readiness,
   private-history quality, neural routing trust, or Campus product readiness.
8. Need public-safe memory-pain fixture evidence:
   [`benchmarks/reports/field-journey/memory-pain-fixture-report.md`](benchmarks/reports/field-journey/memory-pain-fixture-report.md).
9. Need Track S no-live-judge semantic robustness diagnostics:
   [`benchmarks/semantic-robustness-track-s.md`](benchmarks/semantic-robustness-track-s.md).
10. Need public-safe multimodal corpus-style retrieval fixture evidence for
   #531:
   [`benchmarks/reports/multimodal/multimodal-corpus-fixture-report.md`](benchmarks/reports/multimodal/multimodal-corpus-fixture-report.md).
11. Need public-safe conversational media-ingest recall fixture evidence for
   #532:
   [`benchmarks/reports/multimodal/conversational-media-ingest-fixture-report.md`](benchmarks/reports/multimodal/conversational-media-ingest-fixture-report.md).
12. Need public-safe NIAH-style multimodal evidence-pool fixture evidence for
   #533:
   [`benchmarks/reports/multimodal/multimodal-niah-evidence-pool-report.md`](benchmarks/reports/multimodal/multimodal-niah-evidence-pool-report.md).
13. Need public-safe knowledge pollution, privacy partition, and capability
   contract-smoke evidence:
   [`benchmarks/reports/multimodal/knowledge-pollution-privacy-fixture-report.md`](benchmarks/reports/multimodal/knowledge-pollution-privacy-fixture-report.md).
14. Need public-safe fresh-thread recall demo evidence:
   [`benchmarks/reports/fresh-thread/fresh-thread-recall-demo-2026-05-31.md`](benchmarks/reports/fresh-thread/fresh-thread-recall-demo-2026-05-31.md).
15. Need sanitized real-history fresh-thread boundary evidence for #302:
   [`benchmarks/reports/fresh-thread/fresh-thread-real-history-smoke-2026-06-02.md`](benchmarks/reports/fresh-thread/fresh-thread-real-history-smoke-2026-06-02.md).
16. Need expanded fresh-thread demo, the #281 public validation readout, and
   multi-ref real-history smoke evidence:
   [`benchmarks/reports/fresh-thread/fresh-thread-expanded-coverage-2026-06-03.md`](benchmarks/reports/fresh-thread/fresh-thread-expanded-coverage-2026-06-03.md).
17. Need public-safe H1/H2 hard-negative production-like synthetic evidence,
   contract controls, and scorer taxonomy for #244/#1041:
   [`benchmarks/reports/hippocampal/hippocampal-hard-negative-fixture-report.md`](benchmarks/reports/hippocampal/hippocampal-hard-negative-fixture-report.md).
18. Need public-safe hippocampal recall-discrimination diagnostic seed evidence
   or the #1040 D5/D6 gated diagnostic for #229/#230/#231:
   [`benchmarks/reports/hippocampal/hippocampal-recall-fixture-report.md`](benchmarks/reports/hippocampal/hippocampal-recall-fixture-report.md).
19. Need public-safe Field Continuity / magic-moment reproducibility fixture
   evidence for #454 and the supporting bounded #281 fixture-quality proxy:
   [`benchmarks/reports/field-journey/field-continuity-fixture-report.md`](benchmarks/reports/field-journey/field-continuity-fixture-report.md).
20. Need public-safe Journey time-sliced replay and foreground hint timing
   fixture evidence for #310:
   [`benchmarks/reports/field-journey/journey-public-time-sliced-replay.md`](benchmarks/reports/field-journey/journey-public-time-sliced-replay.md).
21. Need public-safe provider-conformance kit evidence for #981 / #988:
   [`benchmarks/reports/multimodal/provider-conformance-fixture-report.md`](benchmarks/reports/multimodal/provider-conformance-fixture-report.md).
22. Need the latest Claude Code real-host local-history / MCP dogfood boundary:
   [`readiness/claude-code-dogfood-2026-06-09.md`](readiness/claude-code-dogfood-2026-06-09.md).
23. Need segmented-search merge policy calibration evidence for #375:
   [`benchmarks/reports/fresh-thread/segmented-merge-policy-fixture-report.md`](benchmarks/reports/fresh-thread/segmented-merge-policy-fixture-report.md).
24. Need agency host-surface timing evidence for #763:
   [`benchmarks/reports/fresh-thread/agency-host-surface-codex-desktop-2026-06-05.md`](benchmarks/reports/fresh-thread/agency-host-surface-codex-desktop-2026-06-05.md).
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

### Current numeric claim snapshot

- **Canonical owner:** `docs/evidence/current-claims.md`
- **What belongs there:** Current metric values, dated cohorts, claim levels, supersession, material limits, and
  owner/retirement routes for numbers that are easy to over-read.

### Stage readiness boundary

- **Canonical owner:** `docs/evidence/readiness/stage-0-5-readiness.md`
- **What belongs there:** Stage-level positive claims, material limits, and missing proof.

### Dated command ledger

- **Canonical owner:** `docs/evidence/readiness/public-readiness-verification.md`
- **What belongs there:** Summarized commands, dates, pass/fail interpretation, and scope notes.

### Benchmark design rationale

- **Canonical owner:** `docs/evidence/benchmarks/design/README.md` and `docs/evidence/benchmarks/design/benchmark-design-rationale.md`
- **What belongs there:** Evaluation philosophy, track-family why, evidence-layer separation, and external-comparison boundaries.

### Benchmark maturity gates

- **Canonical owner:** `docs/evidence/benchmarks/design/benchmark-maturity-gates.md` and `benchmarks/aippocampus/shared/benchmark_maturity.py`
- **What belongs there:** Maturity ladder, sample-size floors, holdout/no-tuning-leakage fields, and promotion metadata
  separating `contract_gate_ok` from `quality_gate_ok`.

### Benchmark family promotion candidates

- **Canonical owner:** `docs/evidence/benchmarks/reports/benchmark-family/benchmark-family-promotion-candidates-2026-06-12.md`
  and `benchmarks/aippocampus/benchmark_family_promotion_candidates.py`
- **What belongs there:** #1195 first-family promotion decision for agent continuity, attention navigation, and map-rot
  lifecycle debt; records target sample floors, family distribution, holdout/no-tuning-leakage,
  uncertainty policy, sanitization, and usefulness blockers without claiming public-quality
  results.

### Benchmark priority registry

- **Canonical owner:** `docs/evidence/benchmarks/design/benchmark-priority-map.md`
- **What belongs there:** Operational priority, maturity, run-profile, claim-level, and claim-boundary guidance for benchmark and smoke surfaces.

### Benchmark runner methodology

- **Canonical owner:** `docs/evidence/benchmarks/design/memory-decision-benchmark-plan.md`
- **What belongs there:** Track definitions, report shape, non-goals, and diagnostic interpretation.

### Natural handoff usefulness validation

- **Canonical owner:** `docs/evidence/benchmarks/reports/coordination/natural-handoff-usefulness-2026-06-14.md`
- **What belongs there:** Bounded public/synthetic #1185/#1384 validation over natural handoff and default-session shapes.
  Records wins, no-help cases, and regressions through the canonical `continuity_usefulness`
  gate; not broad default-session product lift or private-history user-visible evidence.

### External benchmark analysis

- **Canonical owner:** `docs/evidence/benchmarks/design/external-benchmark-map.md`
- **What belongs there:** Layer-aware external benchmark and memory-system comparison candidates, blockers, and material limits.

### AMemGym evidence

- **Canonical owner:** `docs/evidence/benchmarks/amemgym.md`,
  `docs/evidence/benchmarks/reports/amemgym/amemgym-official-live-provider-blocker-2026-06-09.md`,
  and `benchmark_corpus/amemgym_manifest.json`
- **What belongs there:** Official sources, public `v1.base` metadata smoke, source-backed overlay metrics, checked-in
  public fixture, official-runner bridge smoke, official AIppocampus BaseAgent adapter arms with
  clean-source/semantic-worker claim gates, the 2026-06-09 live-provider blocker decision for
  #958, Codex Desktop three-arm hook/precache-gated contract, and claim boundaries for
  #733/#742.

### STATE-Bench Agent Learning feasibility

- **Canonical owner:** `docs/evidence/benchmarks/state-bench-agent-learning.md`,
  `docs/evidence/benchmarks/reports/state-bench/state-bench-agent-learning-preflight-2026-06-10.json`,
  and
  `docs/evidence/benchmarks/reports/state-bench/state-bench-agent-learning-decision-2026-06-14.md`
- **What belongs there:** Official source snapshot, train-only learning extraction boundary, read-only
  `retrieve_learnings` adapter scaffold, matched no-memory adapter/run-plan preflight, local
  ignored artifact policy, LF-checkout prompt-hash note, locked-eval-client blocker, and
  2026-06-14 defer decision for #1043/#1379/#1381. No score/lift claim.

### PersonaMem readiness gate

- **Canonical owner:** `docs/evidence/benchmarks/personamem-readiness.md`
- **What belongs there:** Stages PersonaMem / PersonaMem-v2 behind AIppo/Ficus profile-readiness; records required
  source-supported profile extraction, lifecycle/currentness gates, privacy masks,
  response-adaptation metrics, a diagnostic-only pilot shape, and no-score claim boundaries for
  #1159.

### Multimodal memory benchmark map

- **Canonical owner:** `docs/evidence/benchmarks/design/multimodal-memory-benchmark-map.md`
- **What belongs there:** Source-shape routing for #528 across conversation, corpus, personal filesystem, egocentric
  video, document/knowledge-source, and personalization benchmark families.

### ATM-Bench Hard protocol boundary

- **Canonical owner:** `docs/evidence/benchmarks/design/atm-bench-hard-protocol-boundary.md`
- **What belongs there:** Verified upstream-protocol intake for #528 multimodal source-backed recall, including
  corpus-style, conversational media-ingest, Oracle, and NIAH slice boundaries.

### LongMemEval evidence

- **Canonical owner:** `docs/evidence/benchmarks/longmemeval.md`,
  `docs/evidence/benchmarks/reports/longmemeval/repair/longmemeval-exact-line-repair-2026-06-12.md`,
  `docs/evidence/benchmarks/reports/longmemeval/semantic-cache/longmemeval-semantic-cache-path-2026-06-12.md`,
  `docs/evidence/benchmarks/reports/longmemeval/semantic-cache/longmemeval-semantic-cache-100q-2026-06-12.md`,
  `docs/evidence/benchmarks/reports/longmemeval/semantic-cache/longmemeval-source-worker-surface-500q-2026-06-13.md`,
  `docs/evidence/benchmarks/reports/longmemeval/semantic-cache/longmemeval-full-source-semantic-warming-500q-2026-06-13.md`,
  `docs/evidence/benchmarks/reports/longmemeval/factual-alias/longmemeval-source-factual-alias-25-2026-06-14.md`,
  `docs/evidence/benchmarks/reports/longmemeval/factual-alias/longmemeval-source-factual-alias-500-2026-06-14.md`,
  `docs/evidence/benchmarks/reports/longmemeval/factual-alias/longmemeval-source-factual-alias-500-2026-06-14.json`,
  `docs/evidence/benchmarks/reports/longmemeval/fixed-reader/longmemeval-fixed-reader-answer-25-2026-06-12.md`,
  `docs/evidence/benchmarks/reports/longmemeval/repair/longmemeval-500-retrieval-artifact-2026-06-11.json`,
  and `benchmark_corpus/longmemeval_manifest.json`
- **What belongs there:** Official sources, dataset checksums, dedicated runner commands, the dated 500-question
  LongMemEval-S V1 retrieval-only slice, public artifact-trail manifest, optional lexical
  exact-line reranker diagnostic, #1193 structural exact-line failure report, #1305 semantic
  warm query/candidate cache replay, #1323 100Q semantic query/candidate cache progress with
  same-cohort lexical comparison, #1327 source-window coverage diagnostics and bounded
  candidate-coverage projection, 500Q current source-worker-surface proxy measurement, the
  separate 500Q LLM query/candidate upper bound, contract-aware full-source semantic warming
  no-lift diagnosis, #1424/#1425/#1426 source factual-alias 25Q mechanics slice, the 500Q
  #1323/#1327/#1424 source factual-alias closeout slice, first dated fixed-reader answer/latency
  baseline, historical 100/50-question rows, V2 context-mapping pilot decision, V2
  official-harness pilot decision/adapter boundary, and claim boundaries.

### LongMemEval post-factual-alias rerank closeout

- **Canonical owner:** `benchmarks/aippocampus/benchmark_longmemeval_rerank_analysis.py` and `tests/aippocampus/test_benchmark_longmemeval_rerank_analysis.py`
- **What belongs there:** `docs/evidence/benchmarks/reports/longmemeval/factual-alias/longmemeval-post-factual-alias-rerank-closeout-500-2026-06-14.md`,
  `docs/evidence/benchmarks/reports/longmemeval/factual-alias/longmemeval-post-factual-alias-rerank-closeout-500-2026-06-14.analysis.json`,
  `docs/evidence/benchmarks/longmemeval.md`, #1437

### Public longitudinal user evidence

- **Canonical owner:** `docs/evidence/benchmarks/public-longitudinal-users.md`,
  `docs/evidence/benchmarks/reports/public-longitudinal/public-longitudinal-users-measurement-2026-05-31.md`,
  `docs/evidence/benchmarks/reports/public-longitudinal/react-real-vcs-smoke-2026-05-31.md`,
  `docs/evidence/benchmarks/reports/public-longitudinal/react-real-vcs-100-gold-2026-05-31.md`,
  `docs/evidence/benchmarks/reports/public-longitudinal/react-real-vcs-adversarial-v2-2026-05-31.md`,
  `docs/evidence/benchmarks/reports/public-longitudinal/react-real-vcs-production-like-disambiguation-2026-06-04.md`,
  `docs/evidence/benchmarks/reports/public-longitudinal/rollout-hard-event-route-chain-2026-06-12.md`,
  `docs/evidence/benchmarks/reports/public-longitudinal/rollout-hard-event-cohort-v2-2026-06-12.md`,
  `benchmark_corpus/public_longitudinal_users/`, and `benchmark_corpus/locomo_manifest.json`
- **What belongs there:** Public synthetic coding implicit-knowledge scoring-contract smoke, LoCoMo same-conversation
  control users, LoCoMo fixed-reader text-QA harness, LoCoMo answer-usefulness prototype,
  deterministic scorers, VCS future-event recall roadmap, dated measurements, real public VCS
  hard-event smoke, 100+ gold React VCS measurement with anti-drift/counterfactual controls,
  sharper React VCS adversarial controls, non-oracle production-like source disambiguation,
  rollout route-chain/actionability top-k calibration, public-safe rollout hard-event cohort V2,
  and external-prediction contracts.

### Corpus setup

- **Canonical owner:** `benchmark_corpus/README.md` and `benchmark_corpus/sharegpt_manifest.json`
- **What belongs there:** Public corpus conversion commands, ignored local outputs, and corpus-specific claim boundaries.

### Demo fixture report

- **Canonical owner:** `docs/evidence/benchmarks/reports/field-journey/memory-pain-fixture-report.md`
- **What belongs there:** Public-safe fixture families and their narrow claim boundary.

### Track S semantic robustness diagnostics

- **Canonical owner:** `docs/evidence/benchmarks/semantic-robustness-track-s.md` and `benchmarks/aippocampus/benchmark_semantic_robustness.py`
- **What belongs there:** No-live-judge semantic perturbation, equivalent-query retrieval invariance, and
  hard-negative/negation diagnostics for #747; not human-level semantic understanding or a Track
  A/B replacement.

### Public reliability gauntlet

- **Canonical owner:** `docs/evidence/benchmarks/public-reliability-gauntlet.md`,
  `docs/evidence/benchmarks/reports/public-reliability/public-reliability-gauntlet-2026-06-10.json`,
  and `benchmarks/aippocampus/benchmark_public_reliability_gauntlet.py`
- **What belongs there:** Public-safe #1102 aggregate gate over runtime stability, mis-recall quality, and pollution
  hygiene; keeps LongMemEval-S aggregate metrics, synthetic scale/fanout stress, hard-negative
  diagnostics, and pollution fixtures separate, with no single reliability score.

### Attention navigation quality

- **Canonical owner:** `docs/evidence/benchmarks/reports/recall-navigation/attention-navigation-quality.md` and
  `benchmarks/aippocampus/benchmark_attention_navigation_quality.py`
- **What belongs there:** Public-safe #1111 route-quality gate over positive routes, hard masks, stale/currentness,
  conflict, action-time, anti-nag, bounded-evidence, and wrong-source controls; #1347-#1350
  split contract/design/public/default gate names, add the public/holdout cohort, treat neutral
  no-op as ROI signal, and enable the narrow explicit `agent recall --attention-router-mode
  auto` gate without claiming default hooks.

### Attention score-fusion calibration

- **Canonical owner:** `docs/evidence/benchmarks/reports/recall-navigation/attention-score-fusion-calibration.md` and
  `benchmarks/aippocampus/benchmark_attention_score_fusion_calibration.py`
- **What belongs there:** Public-safe #1112 calibration diagnostic over sanitized attention feature rows; compares current
  deterministic weights to a calibrated rule grid without raw text, private history, or
  learnable hard masks.

### Agent continuity loop gate

- **Canonical owner:** `docs/evidence/benchmarks/reports/recall-navigation/agent-continuity-loop.md` and
  `benchmarks/aippocampus/benchmark_agent_continuity_loop.py`
- **What belongs there:** Public-safe #1163/#1181 integration gate across semantic warming, hot routing, facade packets,
  safe packet triage labels/previews, AIppo working contracts, source-reopen budget, foreground
  budget, deepen/explain, blocked/stale/conflict, and anti-nag cases; red lines stay separate
  from case success.

### Source-backed learning loop replay

- **Canonical owner:** `docs/architecture/coordination/source-backed-learning-loop.md`,
  `aippocampus_runtime.learning_loop.private_replay`,
  `aippocampus_runtime.learning_loop.aippo_adapter`,
  `aippocampus_runtime.navigation.source_shape_projection`,
  `aippocampus_runtime.aippo.clause_lifecycle`, and
  `benchmarks/aippocampus/benchmark_learning_loop_public_companion.py`
- **What belongs there:** #1593-#1602 runtime learning-loop contract with #1611 private dogfood harness, #1612 public
  VCS/public-longitudinal companion eval, and #1613-#1619 deterministic cross-layer fixtures for
  AIppo seed bridges, action-hint cache records, clause lifecycle, feedback ledgers,
  microcircuit diagnostics, semantic-subregion budgets, and controlled salience decay; private
  outputs are aggregate/redacted only, public companion separates reproducible metrics from
  private-dogfood comparable metrics, and STATE-Bench remains a no-official-score boundary
  unless the locked held-out eval client is available.
- **Current public closeout hooks:** #1749/#1750 first-magic-moment and agent-initiative
  fixture readouts, #1751 surfaced-vs-helped outcome ledger, #1752 foreground cognitive-load
  budget, and #1754 sanitized dogfood repro package output; private source text remains redacted.

### Semantic candidate bridge and meta-calibration

- **Canonical owner:** `aippocampus_runtime.navigation.semantic_candidate_context`,
  `aippocampus_runtime.recall.semantic_bridge_map`,
  `aippocampus_runtime.recall.semantic_effectiveness`,
  `benchmarks/aippocampus/benchmark_diagnostic_meta_calibration.py`, and
  `tests/aippocampus/test_semantic_candidate_context_bridge_effectiveness.py`
- **What belongs there:** Public-safe #1640-#1643 routing layer: source-shaped semantic candidate envelopes,
  source/event-backed bridge rows for query expansion, semantic candidate effectiveness ledgers
  by scope bucket, and a no-write diagnostic meta-calibration report. These are navigation and
  review surfaces only; they do not emit source truth, mutate weights, learn hard masks, or
  generalize private/local signals into public defaults.

### Continuity density curve diagnostic

- **Canonical owner:** `benchmarks/aippocampus/benchmark_continuity_density_curve.py` and `tests/aippocampus/test_benchmark_continuity_density_curve.py`
- **What belongs there:** Public-safe #1568/#1607 density evidence split: `--mode synthetic` is only the shape contract
  for cold/light/medium/heavy/noisy-saturated continuity payloads, while `--mode replay`
  computes aggregate tiers from source/registry/route counts plus source-reopen, manual-search,
  wrong-route/noisy-saturation, and context-pressure metrics. Both outputs omit raw text, paths,
  thread ids, and source refs; product-quality claims remain blocked until replay-backed public
  quality gates pass.

### Avatar bounded resonance proxy pilot

- **Canonical owner:** `docs/archive/research/avatar-bounded-resonance/avatar-bounded-resonance-pilot-2026-06-12.md`,
  `docs/archive/research/avatar-bounded-resonance/avatar-bounded-resonance-pilot-2026-06-12.json`,
  `benchmark_corpus/avatar_bounded_resonance/fixture.json`, and
  `benchmarks/aippocampus/benchmark_avatar_bounded_resonance.py`
- **What belongs there:** Public-safe #1319 deterministic proxy over bounded-resonance posture arms A-E; exploratory only,
  with no live-model, private-history, default-runtime, or product-quality claim.

### Avatar bounded resonance live-model pilot

- **Canonical owner:** `docs/archive/research/avatar-bounded-resonance/avatar-bounded-resonance-live-model-2026-06-13.md`,
  `docs/archive/research/avatar-bounded-resonance/avatar-bounded-resonance-live-model-2026-06-13.json`,
  `benchmark_corpus/avatar_bounded_resonance/fixture.json`, and
  `benchmarks/aippocampus/benchmark_avatar_bounded_resonance.py`
- **What belongs there:** Public-safe #1321 live-model repeat over the same arms A-E; records a negative/mixed result
  where bounded resonance does not beat neutral or alias-only arms, with temperature not sent
  under provider/default thinking.

### E2E50 live-model label-oracle diagnostic

- **Canonical owner:** `docs/archive/research/e2e50/e2e50-live-behavior-pilot-2026-06-13.md`,
  `docs/archive/research/e2e50/e2e50-live-behavior-pilot-2026-06-13.json`,
  `benchmark_corpus/e2e50_silent_constraint/fixture.json`, and
  `benchmarks/aippocampus/benchmark_e2e50_behavior_live.py`
- **What belongs there:** Public-safe #1322 diagnostic over the 50-case E2E50 pack; the baseline prompt exposed
  case-family labels, family-specific scenario text, the action-code glossary, and a packet
  shell, so this is runner/report-path evidence only and does not close the #1322
  behavior-validation gap.

### E2E50 blind-surface live behavior

- **Canonical owner:** `docs/research/reports/e2e50-blind-surface-live-behavior-2026-06-13.md`,
  `docs/research/e2e50-blind-surface-live-behavior-2026-06-13.json`,
  `benchmark_corpus/e2e50_silent_constraint/fixture.json`, and
  `benchmarks/aippocampus/benchmark_e2e50_behavior_live.py`
- **What belongs there:** Corrected public-safe #1322 live-model behavior slice: baseline prompt hides case-family labels,
  expected codes, source hashes, action-code glossary, and empty packet shell; packet arm scores
  `1.00` correct/useful next-action vs baseline `0.42`, with zero wrong actions, invalid
  outputs, over-constraint, or private-context red lines.

### Recall degradation audit

- **Canonical owner:** `docs/evidence/benchmarks/reports/recall-navigation/recall-degradation-audit.md` and
  `benchmarks/aippocampus/benchmark_recall_degradation_audit.py`
- **What belongs there:** Public-safe #1184 audit over the live `recall_context_packet -> agent recall -> MemoryPacket`
  path; proves synthetic clean-source hits with the same phase/title derive distinct safe route
  labels without prefilled fixture labels, while blind deepen, manual fallback, generic reopen
  hints, source-thin no-action failures, and foreground source leaks stay at zero.

### Map-rot lifecycle-debt benchmark

- **Canonical owner:** `docs/evidence/benchmarks/reports/field-journey/map-rot-lifecycle-debt.md`,
  `benchmarks/aippocampus/benchmark_map_rot_lifecycle_debt.py`, and
  `aippocampus_runtime.ops.map_rot_maintenance`
- **What belongs there:** Public-safe #1126/#1196 fixture guard for stale, challenged, quarantined, superseded,
  missing-middle, deleted/no-recall, dead-lettered, and repeated-wrong cold navigation-map
  objects; tracks red-line route leaks, challenged backlog age, review-needed count, warnings,
  silence, refresh, prune/decay candidates, and no-write maintenance actions without claiming
  automatic cleanup.

### Multimodal corpus fixture report

- **Canonical owner:** `docs/evidence/benchmarks/reports/multimodal/multimodal-corpus-fixture-report.md` and
  `benchmark_corpus/public_multimodal_corpus/fixture.json`
- **What belongs there:** Public-safe ATM-Bench-inspired corpus-style multimodal retrieval contract for #531; not
  conversational media upload recall, ATM-Bench score, or product privacy proof.

### Conversational media-ingest fixture report

- **Canonical owner:** `docs/evidence/benchmarks/reports/multimodal/conversational-media-ingest-fixture-report.md` and
  `benchmark_corpus/conversational_media_ingest/fixture.json`
- **What belongs there:** Public-safe conversational media-ingest recall contract for #532; media anchors attach to user
  turns and text hints cannot replace visual source reopen.

### Multimodal NIAH evidence-pool fixture report

- **Canonical owner:** `docs/evidence/benchmarks/reports/multimodal/multimodal-niah-evidence-pool-report.md` and
  `benchmark_corpus/multimodal_niah_evidence_pool/fixture.json`
- **What belongs there:** Public-safe NIAH-style supplied-pool answer-synthesis contract for #533; not retrieval quality,
  ATM-Bench score, or live vision-model quality.

### Knowledge pollution/privacy fixture report

- **Canonical owner:** `docs/evidence/benchmarks/reports/multimodal/knowledge-pollution-privacy-fixture-report.md`
- **What belongs there:** Public-safe pollution, stale/authority, privacy partition, source-reopen, and thin capability-contract prototype evidence for #517.

### Hippocampal hard-negative fixture report

- **Canonical owner:** `docs/evidence/benchmarks/reports/hippocampal/hippocampal-hard-negative-fixture-report.md`,
  `benchmark_corpus/hippocampal_hard_negatives/fixture.json`, and ignored LoCoMo input policy in
  `benchmark_corpus/locomo_manifest.json`
- **What belongs there:** Public-safe #244/#1041 H1/H2 hard-negative production-like synthetic slice plus #1056
  LoCoMo-derived public-dialogue cohort mode, contract controls for near-neighbor lures,
  unsupported speech, superseded currentness, surface paraphrase lures, seven outcome
  categories, source-reopen behavior, unsupported-family reporting, and asymmetric scoring; not
  live or real-history recall quality.

### Hippocampal recall fixture report

- **Canonical owner:** `docs/evidence/benchmarks/reports/hippocampal/hippocampal-recall-fixture-report.md`,
  `docs/evidence/benchmarks/reports/hippocampal/hippocampal-cross-system-comparison-2026-06-04.md`,
  and `benchmark_corpus/hippocampal_fixtures/hippocampal_synthetic_v1.jsonl`
- **What belongs there:** Public-safe #229/#230/#231/#236/#238/#1040 diagnostic seed for D/I matrix reporting, D5/D6 gated
  diagnostics, source-reopen failure, wrong-twin separation, scent layers, abstention,
  calibration categories, clean-clone reproduction metadata, and the dated H1/H2/H5 local-arm
  comparison table; not full 50-scene / 350-case P1 quality or external memory-system scores.

### Hippocampal private annotation protocol

- **Canonical owner:** `docs/evidence/benchmarks/hippocampal-private-annotation-protocol.md`
- **What belongs there:** Private real-history H1/H2 sampling, truth-source independence, reviewer/adjudication flow,
  sanitized dated report template, and privacy exclusions for #232; not a committed private case
  pack.

### Fresh-thread recall demo evidence

- **Canonical owner:** `docs/evidence/benchmarks/reports/fresh-thread/fresh-thread-recall-demo-2026-05-31.md` and
  `docs/evidence/benchmarks/reports/fresh-thread/fresh-thread-expanded-coverage-2026-06-03.md`
- **What belongs there:** Public-safe three-arm fresh-thread recall flows, negative controls, source-reopen boundaries,
  multi-turn/correction/threshold controls, the expanded #490 claim boundary, and the 2026-06-10
  #281 public fixture validation readout.

### Recall navigation comparison smoke

- **Canonical owner:** `docs/evidence/benchmarks/reports/recall-navigation/recall-navigation-comparison-2026-06-03.md`
- **What belongs there:** Public-safe deterministic #465 comparison and narrow #201/#281/#309/#248/#1188 proxy for direct
  `search_memory`, hook-only, progressive `recall_context -> recall_deepen`, attention-router
  navigation-only over the same candidate set, foreground packet source reopen, and
  source-joined core/sentinel vague-cue candidate funnels; covers vague cues, multilingual cue
  fixtures including an Arabic continuity cue, stale-handle rejection, source-ref rejoin,
  deictic fail-closed behavior, and claim-boundary metrics without live quality, answer-quality,
  default-prefilter, or broad default-foreground-lift claims.

### Recall navigation promotion harness

- **Canonical owner:** `docs/evidence/benchmarks/reports/recall-navigation/recall-navigation-comparison-2026-06-03.md`
  and `tools/aippocampus/smoke/smoke_recall_navigation_promotion.py`
- **What belongs there:** Public-safe #1302/#1185/#1300/#1301 promotion contract for same-corpus/same-query/same-budget
  recall-navigation arms; reports baseline flat recall, attention-router navigation-only,
  macro-navigation prior, and navigation+deepen rows, feature hurt/no-op cases,
  stale/conflict/noise/wrong-source distractors, attention-cost counters, macro
  active-layer/fanout/momentum readouts, route-family selection counters, and zero safety red
  lines without claiming macro/router default readiness.

### Natural handoff usefulness validation

- **Canonical owner:** `benchmarks/aippocampus/benchmark_natural_handoff_usefulness.py`
- **What belongs there:** `docs/evidence/benchmarks/reports/coordination/natural-handoff-usefulness-2026-06-14.md`, #1185, #1384

### Retrieval score-fusion public calibration

- **Canonical owner:** `skills/aippocampus/scripts/aippocampus_runtime/recall/score_fusion_calibration.py`,
  `skills/aippocampus/scripts/aippocampus_runtime/recall/score_fusion.py`, and
  `tests/aippocampus/test_retrieval_score_fusion.py`
- **What belongs there:** Public-safe #309 deterministic calibration report for post-source-join ranking weights:
  exact-quote guard, question-tracking semantic bridge, wrong-stance lure suppression, explicit
  vector-unavailable fallback, and missing source-join rejection. It is score-policy evidence
  only, not default vector-prefilter adoption, local embedding adapter evidence, live answer
  quality, or source truth.

### Source-joined routing consumer decision

- **Canonical owner:** `skills/aippocampus/scripts/aippocampus_runtime/ops/source_joined_routing_decision.py` and
  `tests/aippocampus/test_source_joined_routing_decision.py`
- **What belongs there:** `docs/evidence/benchmarks/reports/recall-navigation/source-joined-routing-decision-2026-06-14.md`;
  public-safe #1370/#1372/#309 decision report over the progressive recall consumer and
  post-source-join score-fusion variant. It records the default decision to keep text-first
  source-joined routing and defer vector prefilter/local embedding adoption; not live answer
  quality, private-history generalization, default vector safety, or source truth from scores.

### Route feedback fixture

- **Canonical owner:** `benchmark_corpus/route_feedback/fixture.json`, `aippocampus_runtime.recall.feedback_events`,
  and `tests/aippocampus/test_recall_feedback_events.py`
- **What belongs there:** Public-safe #937/#950 route-feedback contract for source-reopen success, blocked-route
  suppression, wrong-route demotion, blend-context/signal-family grouping, and route activation
  metadata. It is calibration evidence only: it does not mutate score-fusion weights, store
  private telemetry, or let activation metadata support factual claims.

### Prompt hook hot-path funnel smoke

- **Canonical owner:** `benchmarks/aippocampus/benchmark_prompt_hot_path_funnel.py` and `skills/aippocampus/references/ambient-hooks.md`
- **What belongs there:** Deterministic #602 local-only route-funnel contract for thread/profile hints, cue-cache aliases,
  bounded trigram FTS fallback, no-op skips, and latency plus false-skip/wrong-scent/promotion
  counters; not semantic paraphrase or live recall-quality evidence.

### Living cue cache smoke and hook guard

- **Canonical owner:** `tools/aippocampus/smoke/smoke_living_cue_cache.py`,
  `tests/aippocampus/test_living_cue_cache.py`, and
  `tests/aippocampus/test_aippocampus_prompt_hook.py`
- **What belongs there:** Public-safe #281 fixture and default-hook guard for learned-phrase-to-source-handle bridging,
  stale/temporary suppression, over-personalization diagnostics, no-live-LLM selector output,
  and scent-only hot-path consumption; not fresh-thread quality proof.

### Query-pattern routes fixture

- **Canonical owner:** `aippocampus_runtime.warm_ambient.query_pattern_enrichment --fixture --json`,
  `aippocampus_runtime.warm_ambient.query_pattern_routes`,
  `tests/aippocampus/test_query_pattern_enrichment.py`,
  `tests/aippocampus/test_prompt_hot_path_funnel.py`, `tests/aippocampus/test_onboard_codex.py`,
  and `tests/aippocampus/test_aippocampus_prompt_hook.py`
- **What belongs there:** Public-safe #574 registry/import planning plus deterministic sidecar writer/reader, default
  onboarding registry-metadata and reviewed-semantic-trigger route publication, alias-source
  diagnostics, and hot-path scent consumption; covers changed-generation work items, cache
  reuse, idempotent existing work, digest invalidation, provider/privacy suppression, stale
  sidecar filtering, no-live-LLM foreground packets, registry-only nickname misses,
  reviewed/generated natural multilingual alias hits, and public reports that omit alias
  text/local paths. Not live DeepSeek quality, scheduler adoption, or latency savings.

### Fresh-thread real-history boundary smoke

- **Canonical owner:** `docs/evidence/benchmarks/reports/fresh-thread/fresh-thread-real-history-smoke-2026-06-02.md`
  and
  `docs/evidence/benchmarks/reports/fresh-thread/fresh-thread-expanded-coverage-2026-06-03.md`
- **What belongs there:** Sanitized real-history boundary smoke for ready-lock reopenability, thread-only lock
  suppression, current-repo fact negative control, and #490 multi-ref aggregate coverage; not a
  recall-quality benchmark.

### Field Continuity fixture report

- **Canonical owner:** `docs/evidence/benchmarks/field-continuity-eval-design.md`,
  `docs/evidence/benchmarks/reports/field-journey/field-continuity-fixture-report.md`, and
  `benchmark_corpus/field_continuity/fixture.json`
- **What belongs there:** Public-safe #454/#982 scenario-family contract for second-user magic-moment reports from
  Discussion #428; includes public reproducibility tracks, FTS-only/summary-first/semantic-only
  baselines, a supporting bounded #281 `issue_readouts.github_281` fixture-quality proxy,
  private seed hash/aggregate rules, by-arm route/source/abstention/leakage/cost metrics, and
  overclaim/wrong-family/stale-route controls without live or private-history quality claims.
  The #281 closeout readout now lives in the fresh-thread recall demo runner.

### Provider conformance kit report

- **Canonical owner:** `docs/evidence/benchmarks/reports/multimodal/provider-conformance-fixture-report.md` and
  `benchmark_corpus/provider_conformance/fixture.json`
- **What belongs there:** Public-safe #981/#988 kit v1 for provider/session identity, cross-provider source-reopen
  affordances, copied-summary downgrade, injected host content demotion, MCP source-ref metadata
  shape, real `generic-jsonl` / `claude-code` normalizer suites, and provider failure examples;
  not live multi-client support, AgentMemory behavior, or real cross-host continuity quality.

### Segmented merge policy fixture report

- **Canonical owner:** `docs/evidence/benchmarks/reports/fresh-thread/segmented-merge-policy-fixture-report.md` and
  `benchmark_corpus/segmented_merge_policy/fixture.json`
- **What belongs there:** Public-safe #375/#853 calibration fixture for `SEGMENT_MERGE_POLICY` and stable source-key
  dedupe over cross-segment diversity, adjacent-turn pairing, duplicate nearby recap
  suppression, stable source join overlap, and stale/superseded currentness; not source-evidence
  retrieval or real long-thread recall quality. #1977 also lets the same runner emit an
  optional public-safe replay/source-evidence cohort with source-open support validation
  reported separately from ranking hit-rate. The #376 generated physical-path soak remains
  owned by `tools/aippocampus/smoke/smoke_long_thread_segment_soak.py`.

### Dream live shadow A/B reminder evidence

- **Canonical owner:** `docs/evidence/dream/dream-live-shadow-ab-2026-05-30.md`
- **What belongs there:** Dated aggregate run for explicit recall-reminder frequency, shadow assignment, nearest-prior
  exposure attribution, and delivered-vs-shadow claim boundaries.

### Dream topology, shadow-route scout, and AIppo ripening readout

- **Canonical owner:** `aippocampus_runtime.dream.topology_scout`, `aippocampus_runtime.aippo.working_contract`,
  `tests/aippocampus/test_dream_topology_scout.py`, and
  `tests/aippocampus/test_aippo_working_contract.py`
- **What belongs there:** Public-safe deterministic Dream topology scout for source-anchored candidate shapes plus #1313
  shadow-route visible/latent route nominations and a public fixture where a Dream-synthesized
  candidate ripens only after source support. Shadow-route and Dream candidates remain
  navigation/candidate surfaces until source overlap, failed-route residue, or source-backed
  support exists; generic shared vocabulary, pure transform-orbit membership, private
  psychology, user diagnosis, profile claims, and source-free symbolic claims stay rejected,
  backstage, or explain-only.

### Agency host-surface replay evidence

- **Canonical owner:** `docs/evidence/benchmarks/reports/fresh-thread/agency-host-surface-codex-desktop-2026-06-05.md`
- **What belongs there:** Public-safe #763 Codex Desktop hidden-route lifecycle replay for show/hold/suppress timing,
  source-visible suppression, duplicate suppression, recent negative feedback, and
  usefulness/annoyance/correction ledger boundaries.

### Dream private real-history offline evidence

- **Canonical owner:** `docs/evidence/dream/dream-real-history-model-backed-eval-2026-05-31.md` and
  `docs/evidence/dream/dream-private-large-history-diagnostic-2026-06-04.md`
- **What belongs there:** Sanitized aggregate private-history Dream eval and diagnostic evidence for selected ready-pack
  structural lift, shadow replay boundaries, coding-probe deferment, E2E50 seed scan/manual
  annotation boundaries, agency host-timing replay, coding decision-shadow proxy evidence, and
  live semantic gate worker/availability diagnostics.

### Dream benchmark-corpus shadow evidence

- **Canonical owner:** `docs/evidence/dream/dream-live-shadow-benchmark-corpus-2026-05-31.md`
- **What belongs there:** Dated public-corpus negative-control run for explicit reminder frequency and potential dream-only over-personalization activation.

### Question extraction axis coverage evidence

- **Canonical owner:** `docs/evidence/question/question-extraction-axis-coverage-2026-05-31.md`
- **What belongs there:** Dated live no-write aggregate field-presence run for GitHub #153 and its prompt/repair/telemetry fix boundary.

### Question-aware public shadow evidence

- **Canonical owner:** `docs/evidence/question/question-aware-public-shadow-2026-06-10.md` and `benchmark_corpus/question_aware_public_shadow/fixture.json`
- **What belongs there:** Checked-in public/source-replayable #248 shadow cases for question-aware source reopen, selected
  baseline preregistration, no-question retrieval/answer proxy, public-safe local calibration
  readout for stale carryover / missed resurfacing / wrong-route drag / false-positive and
  false-negative classes, materialization-review usefulness categories, selected answer-review
  deltas, adaptive-threshold readout, and noise/code negative controls; not private-history
  quality, live user-visible lift, theme-resonance calibration, default prefilter adoption, or
  source truth from question rows.

### Thread-story public shadow closeout

- **Canonical owner:** `skills/aippocampus/scripts/aippocampus_runtime/reflection/thread_story.py` and `tests/aippocampus/test_thread_story_packet.py`
- **What belongs there:** Public-safe #313 structured-text closeout report for source-backed thread-story packets,
  leakage/contradiction/persona/interference/noise controls, packet-only factual-answer
  blocking, and source-reopened answer comparison; not private-history story quality, live
  model-family behavior, default recall lift, user/personality truth, or source truth from
  packet routes.

### Community field reports

- **Canonical owner:** `docs/evidence/community-field-reports.md`, the public `/evidence/` page, and GitHub Discussions
- **What belongs there:** Public-safe user and contributor reports. These are community signals until reviewed and
  promoted into official benchmark evidence, readiness ledgers, or known-gap docs.

### Raw / generated artifacts

- **Canonical owner:** `.tmp/` or `benchmark_corpus/reports/`
- **What belongs there:** Local JSON outputs, historical benchmark snapshots, run-history diff artifacts, and case packs.
  Keep them gitignored unless a small public subset is deliberately promoted.


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

### Shared benchmark helper entrypoint contract

- **Entrypoint:** `benchmarks/aippocampus/shared/benchmark_entrypoints.py`
- **Reads / updates:** Library-only helper execution contract for #1030; no benchmark score or evidence claim
- **Current boundary:** #1655 slow/heavy JSON entrypoint manifest classifies heavy-local
  runners without executing them or treating timeout avoidance as a quality score.

### Shared benchmark uncertainty helper

- **Entrypoint:** `benchmarks/aippocampus/shared/benchmark_statistics.py`
- **Reads / updates:** `docs/evidence/benchmarks/design/memory-decision-benchmark-plan.md`

### One-command baseline suite, profile ladder, and threshold metadata

- **Entrypoint:** `benchmarks/aippocampus/benchmark_suite.py`
- **Reads / updates:** `docs/evidence/benchmarks/design/memory-decision-benchmark-plan.md`, `docs/evidence/readiness/public-readiness-verification.md`

### Benchmark run-history diff and regression guardrail

- **Entrypoint:** `benchmarks/aippocampus/benchmark_run_history_diff.py`
- **Reads / updates:** `docs/evidence/benchmarks/design/memory-decision-benchmark-plan.md`, `.tmp/` or `benchmark_corpus/reports/`

### Track A memory decision gate

- **Entrypoint:** `benchmarks/aippocampus/benchmark_memory_decision_gate.py`
- **Reads / updates:** `docs/evidence/benchmarks/design/memory-decision-benchmark-plan.md`,
  `docs/evidence/benchmarks/reports/field-journey/memory-pain-fixture-report.md`

### Track B source-evidence retrieval wrapper

- **Entrypoint:** `benchmarks/aippocampus/benchmark_source_evidence_retrieval.py` facade with track-owned helpers in `benchmarks/aippocampus/source_evidence/`
- **Reads / updates:** `docs/evidence/benchmarks/design/memory-decision-benchmark-plan.md`,
  `benchmark_corpus/README.md`; includes #309 diagnostic `semantic_bridge_lift` / wrong-stance
  source-joined reranker metrics, not default vector behavior

### Track S semantic robustness diagnostics

- **Entrypoint:** `benchmarks/aippocampus/benchmark_semantic_robustness.py`
- **Reads / updates:** `docs/evidence/benchmarks/semantic-robustness-track-s.md`, `docs/evidence/benchmarks/design/memory-decision-benchmark-plan.md`, #747
- **Current boundary:** #1659 emits explicit diagnostic contract fields with
  `public_quality_gate_ok=false`; the Track S gate is not a public product-quality pass.

### Public reliability gauntlet

- **Entrypoint:** `benchmarks/aippocampus/benchmark_public_reliability_gauntlet.py`
- **Reads / updates:** `docs/evidence/benchmarks/public-reliability-gauntlet.md`,
  `docs/evidence/benchmarks/reports/public-reliability/public-reliability-gauntlet-2026-06-10.json`,
  #1102

### Attention navigation quality

- **Entrypoint:** `benchmarks/aippocampus/benchmark_attention_navigation_quality.py`
- **Reads / updates:** `docs/evidence/benchmarks/reports/recall-navigation/attention-navigation-quality.md`, #1111, #1347, #1348, #1349, #1350

### Attention score-fusion calibration

- **Entrypoint:** `benchmarks/aippocampus/benchmark_attention_score_fusion_calibration.py`
- **Reads / updates:** `docs/evidence/benchmarks/reports/recall-navigation/attention-score-fusion-calibration.md`, #1112

### Agent continuity loop gate

- **Entrypoint:** `benchmarks/aippocampus/benchmark_agent_continuity_loop.py`
- **Reads / updates:** `docs/evidence/benchmarks/reports/recall-navigation/agent-continuity-loop.md`, #1163, #1181

### Avatar bounded resonance proxy pilot

- **Entrypoint:** `benchmarks/aippocampus/benchmark_avatar_bounded_resonance.py`
- **Reads / updates:** `docs/archive/research/avatar-bounded-resonance/avatar-bounded-resonance-pilot-2026-06-12.md`,
  `docs/archive/research/avatar-bounded-resonance/avatar-bounded-resonance-pilot-2026-06-12.json`,
  `benchmark_corpus/avatar_bounded_resonance/fixture.json`, #1319

### Recall degradation audit

- **Entrypoint:** `benchmarks/aippocampus/benchmark_recall_degradation_audit.py`
- **Reads / updates:** `docs/evidence/benchmarks/reports/recall-navigation/recall-degradation-audit.md`, #1184

### Benchmark maturity helper

- **Entrypoint:** `benchmarks/aippocampus/shared/benchmark_maturity.py`
- **Reads / updates:** `docs/evidence/benchmarks/design/benchmark-maturity-gates.md`, #1165

### Map-rot lifecycle-debt benchmark

- **Entrypoint:** `benchmarks/aippocampus/benchmark_map_rot_lifecycle_debt.py` and `aippocampus_runtime.ops.map_rot_maintenance`
- **Reads / updates:** `docs/evidence/benchmarks/reports/field-journey/map-rot-lifecycle-debt.md`, #1126, #1196

### Multimodal corpus-style retrieval contract

- **Entrypoint:** `benchmarks/aippocampus/benchmark_multimodal_corpus_retrieval.py`
- **Reads / updates:** `docs/evidence/benchmarks/reports/multimodal/multimodal-corpus-fixture-report.md`,
  `benchmark_corpus/README.md`, `benchmark_corpus/public_multimodal_corpus/fixture.json`, #531

### Conversational media-ingest recall contract

- **Entrypoint:** `benchmarks/aippocampus/benchmark_conversational_media_ingest_recall.py`
- **Reads / updates:** `docs/evidence/benchmarks/reports/multimodal/conversational-media-ingest-fixture-report.md`,
  `benchmark_corpus/README.md`, `benchmark_corpus/conversational_media_ingest/fixture.json`,
  #532

### Multimodal NIAH evidence-pool contract

- **Entrypoint:** `benchmarks/aippocampus/benchmark_multimodal_niah_evidence_pool.py`
- **Reads / updates:** `docs/evidence/benchmarks/reports/multimodal/multimodal-niah-evidence-pool-report.md`,
  `benchmark_corpus/README.md`, `benchmark_corpus/multimodal_niah_evidence_pool/fixture.json`,
  `benchmark_corpus/public_multimodal_corpus/fixture.json`, #533

### ShareGPT public-corpus seeded sampler

- **Entrypoint:** `benchmarks/aippocampus/shared/sharegpt_sampling.py`
- **Reads / updates:** `docs/evidence/benchmarks/design/memory-decision-benchmark-plan.md`, `benchmark_corpus/sharegpt_manifest.json`

### Coding decision-shadow Tracks A-E

- **Entrypoint:** `benchmarks/aippocampus/benchmark_coding_decision_shadow.py`
- **Reads / updates:** `docs/evidence/benchmarks/design/memory-decision-benchmark-plan.md`, `docs/research/agent-coding-context-analysis.md`

### H1/H2 hard-negative production-like synthetic slice, public-dialogue cohort, and contract controls

- **Entrypoint:** `benchmarks/aippocampus/benchmark_hippocampal_hard_negatives.py`
- **Reads / updates:** `docs/evidence/benchmarks/reports/hippocampal/hippocampal-hard-negative-fixture-report.md`,
  `docs/evidence/benchmarks/design/hippocampal-recall-plan.md`,
  `benchmark_corpus/hippocampal_hard_negatives/fixture.json`,
  `benchmark_corpus/locomo_manifest.json`, #244/#1041/#1056

### Hippocampal recall-discrimination diagnostic benchmark

- **Entrypoint:** `benchmarks/aippocampus/benchmark_hippocampal_recall.py`
- **Reads / updates:** `docs/evidence/benchmarks/reports/hippocampal/hippocampal-recall-fixture-report.md`,
  `docs/evidence/benchmarks/reports/hippocampal/hippocampal-cross-system-comparison-2026-06-04.md`,
  `docs/evidence/benchmarks/design/hippocampal-recall-plan.md`,
  `benchmark_corpus/hippocampal_fixtures/hippocampal_synthetic_v1.jsonl`,
  #229/#230/#231/#238/#1040

### Hippocampal recall-discrimination fixture builder

- **Entrypoint:** `benchmarks/aippocampus/builders/build_hippocampal_fixture.py`
- **Reads / updates:** `docs/evidence/benchmarks/reports/hippocampal/hippocampal-recall-fixture-report.md`,
  `benchmark_corpus/hippocampal_fixtures/hippocampal_synthetic_v1.jsonl`, #229

### Knowledge pollution, privacy partition, and capability-contract smoke

- **Entrypoint:** `benchmarks/aippocampus/benchmark_knowledge_pollution.py`
- **Reads / updates:** `docs/evidence/benchmarks/design/memory-decision-benchmark-plan.md`,
  `docs/evidence/benchmarks/reports/multimodal/knowledge-pollution-privacy-fixture-report.md`,
  `docs/architecture/host/high-risk-answer-gates.md`

### LongMemEval retrieval-only benchmark and rerank analysis

- **Entrypoint:** `benchmarks/aippocampus/benchmark_longmemeval.py` and `benchmarks/aippocampus/benchmark_longmemeval_rerank_analysis.py`
- **Reads / updates:** `docs/evidence/benchmarks/longmemeval.md`,
  `docs/evidence/benchmarks/reports/longmemeval/semantic-cache/longmemeval-semantic-rerank-analysis-2026-06-10.json`,
  `docs/evidence/benchmarks/reports/longmemeval/repair/longmemeval-exact-line-repair-2026-06-12.json`,
  `docs/evidence/benchmarks/reports/longmemeval/semantic-cache/longmemeval-semantic-cache-path-2026-06-12.json`,
  `docs/evidence/benchmarks/reports/longmemeval/semantic-cache/longmemeval-semantic-cache-100q-2026-06-12.json`,
  `docs/evidence/benchmarks/reports/longmemeval/semantic-cache/longmemeval-source-worker-surface-500q-2026-06-13.json`,
  `docs/evidence/benchmarks/reports/longmemeval/semantic-cache/longmemeval-full-source-semantic-warming-500q-2026-06-13.json`,
  `docs/evidence/benchmarks/reports/longmemeval/factual-alias/longmemeval-source-factual-alias-25-2026-06-14.md`,
  `docs/evidence/benchmarks/reports/longmemeval/factual-alias/longmemeval-source-factual-alias-500-2026-06-14.md`,
  `docs/evidence/benchmarks/reports/longmemeval/factual-alias/longmemeval-source-factual-alias-500-2026-06-14.json`,
  `benchmark_corpus/longmemeval_manifest.json`, #1092, #1193, #1305, #1323, #1327, #1387, #1388,
  #1424, #1425, #1426

### LongMemEval fixed-reader answer/latency harness

- **Entrypoint:** `benchmarks/aippocampus/benchmark_longmemeval_answer.py`
- **Reads / updates:** `docs/evidence/benchmarks/longmemeval.md`, `benchmark_corpus/longmemeval_manifest.json`, #1157, #1229

### LongMemEval-V2 context-mapping pilot

- **Entrypoint:** `benchmarks/aippocampus/benchmark_longmemeval_v2_context.py`
- **Reads / updates:** `docs/evidence/benchmarks/longmemeval.md`, `benchmark_corpus/longmemeval_manifest.json`, #259

### LongMemEval-V2 official-harness pilot decision and adapter

- **Entrypoint:** `benchmarks/aippocampus/benchmark_longmemeval_v2_official_pilot.py` and
  `benchmarks/aippocampus/adapters/longmemeval_v2_aippocampus_adapter.py`
- **Reads / updates:** `docs/evidence/benchmarks/longmemeval.md`, `benchmark_corpus/longmemeval_manifest.json`, #1155, #1229
- **Current boundary:** #1701 fixture pilot may exercise the Memory API adapter arms,
  but `official_score_claimable=false` until dated official-harness outputs exist.

### AMemGym metadata, source-backed overlay smoke, official-runner bridge with AIppocampus BaseAgent arms, live-provider blocker, and Codex Desktop AMemGym-style arms

- **Entrypoint:** `benchmarks/aippocampus/benchmark_amemgym.py`,
  `benchmarks/aippocampus/benchmark_amemgym_official.py`,
  `benchmarks/aippocampus/benchmark_codex_desktop_amemgym.py`
- **Reads / updates:** `docs/evidence/benchmarks/amemgym.md`,
  `docs/evidence/benchmarks/reports/amemgym/amemgym-official-live-provider-blocker-2026-06-09.md`,
  `benchmark_corpus/amemgym_manifest.json`, `benchmark_corpus/amemgym_fixture/fixture.json`,
  #733, #742, #1229

### STATE-Bench Agent Learning feasibility, adapter scaffold, matched-run preflight, and defer decision

- **Entrypoint:** `benchmarks/aippocampus/benchmark_state_bench_agent_learning.py` plus the 2026-06-14 source/env recheck
- **Reads / updates:** `docs/evidence/benchmarks/state-bench-agent-learning.md`,
  `docs/evidence/benchmarks/reports/state-bench/state-bench-agent-learning-preflight-2026-06-10.json`,
  `docs/evidence/benchmarks/reports/state-bench/state-bench-agent-learning-decision-2026-06-14.md`,
  #1043/#1379/#1381
- **Current boundary:** #1700 matched fixture arm can compare no-memory vs AIppocampus
  adapter behavior locally, but stays adapter-only/no-go for official score claims.

### MemoryAgentBench metadata, case-pack, Stage 3 dry-run, deterministic local apply instrumentation, and optional parquet row smoke

- **Entrypoint:** `benchmarks/aippocampus/benchmark_memoryagentbench.py`
- **Reads / updates:** `docs/evidence/benchmarks/memoryagentbench.md`, `benchmark_corpus/memoryagentbench_manifest.json`, #608, #614, #694, #995
- **Current boundary:** #1699 local TTL/conflict replay is source-backed and bounded;
  it does not claim an official MemoryAgentBench score or leaderboard result.

### PersonaMem readiness gate

- **Entrypoint:** no runner yet
- **Reads / updates:** `docs/evidence/benchmarks/personamem-readiness.md`, #1159

### LoCoMo public longitudinal-users control

- **Entrypoint:** `benchmarks/aippocampus/benchmark_locomo_public_users.py`
- **Reads / updates:** `docs/evidence/benchmarks/public-longitudinal-users.md`, `benchmark_corpus/README.md`, `benchmark_corpus/locomo_manifest.json`

### LoCoMo fixed-reader text-QA harness

- **Entrypoint:** `benchmarks/aippocampus/benchmark_locomo_qa.py`
- **Reads / updates:** `docs/evidence/benchmarks/public-longitudinal-users.md`, `benchmark_corpus/README.md`,
  `benchmark_corpus/locomo_manifest.json`, #1158, #1229

### LoCoMo answer-usefulness prototype

- **Entrypoint:** `benchmarks/aippocampus/benchmark_locomo_answer_usefulness.py`
- **Reads / updates:** `docs/evidence/benchmarks/public-longitudinal-users.md`, `benchmark_corpus/README.md`, #400

### Public longitudinal pseudo-user coding implicit-knowledge contract smoke

- **Entrypoint:** `benchmarks/aippocampus/benchmark_public_longitudinal_users.py`
- **Reads / updates:** `docs/evidence/benchmarks/public-longitudinal-users.md`, `benchmark_corpus/public_longitudinal_users/README.md`

### VCS future-event recall, source-disambiguation, and route-chain/actionability benchmark scaffold

- **Entrypoint:** `benchmarks/aippocampus/benchmark_vcs_future_event_recall.py`
- **Reads / updates:** `docs/evidence/benchmarks/public-longitudinal-users.md`,
  `docs/evidence/benchmarks/reports/public-longitudinal/react-real-vcs-production-like-disambiguation-2026-06-04.md`,
  `benchmark_corpus/public_longitudinal_users/README.md`, #309

### VCS / rollout future-event fixture builder

- **Entrypoint:** `benchmarks/aippocampus/builders/build_vcs_future_event_fixture.py`
- **Reads / updates:** `docs/evidence/benchmarks/public-longitudinal-users.md`, `benchmark_corpus/public_longitudinal_users/README.md`

### FTS5 real-history recall

- **Entrypoint:** `benchmarks/aippocampus/benchmark_fts5_recall.py`
- **Reads / updates:** `docs/evidence/readiness/public-readiness-verification.md`, `docs/planning/next-iteration-plan.md`

### Public CJK local-recall fixture

- **Entrypoint:** `benchmarks/aippocampus/benchmark_fts5_recall.py --public-cjk-fixture`
- **Reads / updates:** `docs/evidence/benchmarks/reports/recall-navigation/cjk-local-recall-fixture-report.md`, #852, #1022, #1054

### Track C payload fidelity

- **Entrypoint:** `benchmarks/aippocampus/benchmark_payload_fidelity.py`
- **Reads / updates:** `docs/evidence/benchmarks/design/memory-decision-benchmark-plan.md`,
  `docs/evidence/benchmarks/reports/field-journey/memory-pain-fixture-report.md`

### Track D synthetic compaction continuity

- **Entrypoint:** `benchmarks/aippocampus/benchmark_compaction_continuity.py`
- **Reads / updates:** `docs/evidence/benchmarks/design/memory-decision-benchmark-plan.md`, `docs/evidence/readiness/public-readiness-verification.md`

### E2E50 public-safe behavior-pack scorer and private/local field-validation gate

- **Entrypoint:** `benchmarks/aippocampus/benchmark_e2e50_silent_constraint.py`; sequence/load validator in
  `aippocampus_runtime/coding/sequence_packets.py`; Episode/Arc builder in
  `aippocampus_runtime/coding/episode_arcs.py`
- **Reads / updates:** `docs/evidence/benchmarks/design/memory-decision-benchmark-plan.md`,
  `docs/architecture/coordination/episode-arc-read-models.md`,
  `benchmark_corpus/e2e50_silent_constraint/fixture.json`,
  `docs/evidence/benchmarks/reports/e2e50/e2e50-field-validation-2026-06-16.md`,
  #279/#663/#575/#1154/#1981

### Continuous-memory attribution arms, host-native baseline, pre-registration, preregistered slice readouts including `public_synthetic_preregistered_repeat` and `github_1153_context_loss_public_continuity_v1`, cost/harm ledger, cost/harm sensitivity, scenario provenance/holdout controls, and the missing-context diagnostic boundary

- **Entrypoint:** `benchmarks/aippocampus/benchmark_continuous_memory_arms.py`
- **Reads / updates:** `docs/evidence/benchmarks/design/memory-decision-benchmark-plan.md`, #378/#406/#407/#408/#409/#410/#1153

### Source-backed learning loop public companion

- **Entrypoint:** `benchmarks/aippocampus/benchmark_learning_loop_public_companion.py`; private harness in
  `aippocampus_runtime.learning_loop.private_replay`; cross-layer fixtures in
  `aippocampus_runtime.learning_loop.aippo_adapter`,
  `aippocampus_runtime.navigation.source_shape_projection`,
  `aippocampus_runtime.aippo.clause_lifecycle`,
  `aippocampus_runtime.subconscious.circuit_feedback`,
  `aippocampus_runtime.navigation.microcircuit_router`, and
  `aippocampus_runtime.subconscious.semantic_subregion_budget`
- **Reads / updates:** `docs/architecture/coordination/source-backed-learning-loop.md`,
  `benchmark_corpus/public_longitudinal_users/rollout_behavior_events_v2.json`,
  `benchmark_corpus/public_longitudinal_users/vcs_future_events_v1.jsonl`, #1611, #1612, #1613,
  #1614, #1615, #1616, #1617, #1618, #1619

### Continuity density curve diagnostic

- **Entrypoint:** `benchmarks/aippocampus/benchmark_continuity_density_curve.py --mode synthetic`; aggregate companion in `--mode replay`
- **Reads / updates:** #1568, #1607

### Optional live semantic gate

- **Entrypoint:** `benchmarks/aippocampus/benchmark_live_semantic_gate.py`
- **Reads / updates:** `docs/evidence/benchmarks/design/memory-decision-benchmark-plan.md`, `benchmark_corpus/README.md`

### Prompt hook local hot-path funnel

- **Entrypoint:** `benchmarks/aippocampus/benchmark_prompt_hot_path_funnel.py`
- **Reads / updates:** `skills/aippocampus/references/ambient-hooks.md`, #602

### Fresh-thread public-safe recall demo

- **Entrypoint:** `benchmarks/aippocampus/benchmark_fresh_thread_recall_demo.py`
- **Reads / updates:** `docs/evidence/benchmarks/reports/fresh-thread/fresh-thread-recall-demo-2026-05-31.md`,
  `docs/evidence/benchmarks/reports/fresh-thread/fresh-thread-expanded-coverage-2026-06-03.md`,
  `docs/evidence/current-claims.md`, `docs/guides/demo-scenarios.md`, #281

### Field Continuity / magic-moment reproducibility contract

- **Entrypoint:** `benchmarks/aippocampus/benchmark_field_continuity.py`
- **Reads / updates:** `docs/evidence/benchmarks/field-continuity-eval-design.md`,
  `docs/evidence/benchmarks/reports/field-journey/field-continuity-fixture-report.md`,
  `docs/evidence/benchmarks/design/memory-decision-benchmark-plan.md`,
  `benchmark_corpus/field_continuity/fixture.json`, #454, #982, #281

### Provider conformance contract fixture

- **Entrypoint:** `benchmarks/aippocampus/benchmark_provider_conformance.py`
- **Reads / updates:** `docs/evidence/benchmarks/reports/multimodal/provider-conformance-fixture-report.md`,
  `docs/architecture/host/provider-entrypoint-inventory.md`,
  `benchmark_corpus/provider_conformance/fixture.json`, #988, #981

### Claude Code real-host dogfood

- **Entrypoint:** `tools/aippocampus/smoke/smoke_claude_code_history.py`,
  `tools/aippocampus/smoke/smoke_claude_code_mcp_host.py`,
  `tools/aippocampus/smoke/smoke_cross_agent_continuity.py`
- **Reads / updates:** `docs/evidence/readiness/claude-code-dogfood-2026-06-09.md`, `docs/guides/setup/claude-code-mcp.md`, #998, #1021

### Structured cognitive portrait

- **Entrypoint:** `benchmarks/aippocampus/benchmark_cognitive_portrait.py`
- **Reads / updates:** `docs/research/frontiers/compact-activation-signals.md`, `docs/evidence/benchmarks/design/memory-decision-benchmark-plan.md`

### Thread-story packet and public closeout diagnostic

- **Entrypoint:** `skills/aippocampus/scripts/aippocampus_runtime/reflection/thread_story.py`
- **Reads / updates:** `docs/research/frontiers/compact-activation-signals.md`,
  `docs/research/frontiers/affect-side-channel.md`, `docs/evidence/current-claims.md`, #313

### Question-aware real-history structural benchmark, optional answer-quality review, and public shadow fixture

- **Entrypoint:** `benchmarks/aippocampus/benchmark_question_aware_real_history.py`
- **Reads / updates:** `docs/architecture/recall/question-tracking-subconscious.md`,
  `docs/evidence/question/question-aware-answer-quality-2026-06-08.md`,
  `docs/evidence/question/question-aware-public-shadow-2026-06-10.md`,
  `benchmark_corpus/question_aware_public_shadow/fixture.json`,
  `docs/research/frontiers/compact-activation-signals.md`,
  `docs/planning/next-iteration-plan.md`, `docs/evidence/readiness/stage-0-5-readiness.md`,
  `docs/evidence/benchmarks/design/memory-decision-benchmark-plan.md`, #248

### Question tracking selected-fixture calibration

- **Entrypoint:** `benchmarks/aippocampus/benchmark_question_tracking_calibration.py`
- **Reads / updates:** `docs/architecture/recall/question-tracking-subconscious.md`,
  `docs/planning/technical-differentiation-analysis.md`, `docs/evidence/current-claims.md`,
  #1059

### Subconscious event-salience intake gate

- **Entrypoint:** `tests/aippocampus/test_subconscious_event_salience_gate.py`; default CLI/scheduler path `python
  -m aippocampus_runtime.subconscious.jobs --dry-run --json`; explicit bypass
  `--no-event-salience-gate`
- **Reads / updates:** `docs/architecture/runtime/cognitive-runtime-architecture.md`,
  `docs/architecture/recall/question-tracking-subconscious.md`,
  `skills/aippocampus/references/subconscious-jobs.md`, `docs/evidence/current-claims.md`, #1058

### Warm ambient recall benchmark

- **Entrypoint:** `benchmarks/aippocampus/benchmark_warm_ambient_recall.py`
- **Reads / updates:** `docs/research/ambient-associative-recall.md`, `benchmark_corpus/README.md`

### Warm ambient parameter sweep

- **Entrypoint:** `benchmarks/aippocampus/benchmark_warm_ambient_sweep.py`
- **Reads / updates:** `docs/research/ambient-associative-recall.md`, `docs/evidence/benchmarks/design/memory-decision-benchmark-plan.md`

### State-dependent warm ambient preactivation

- **Entrypoint:** `benchmarks/aippocampus/benchmark_state_dependent_preactivation.py`
- **Reads / updates:** `docs/evidence/benchmarks/reports/fresh-thread/state-dependent-preactivation-2026-06-10.md`,
  `docs/research/ambient-associative-recall.md`, #1082

### Successor evidence sweep

- **Entrypoint:** `benchmarks/aippocampus/benchmark_successor_evidence_sweep.py`
- **Reads / updates:** `docs/evidence/reports/successor-evidence-sweep-2026-06-16.md`,
  #1918-#1981
- **Boundary:** executable closeout gate for proxy-successor issues; not a
  benchmark score, live product-lift claim, or default-adoption proof. Hard
  blocker rows must keep an open successor/reopened owner/deferred pointer; a
  recorded blocker alone is not a completed issue.

### Warm ambient case-pack builder

- **Entrypoint:** `benchmarks/aippocampus/builders/build_warm_ambient_trace_cases.py`
- **Reads / updates:** `benchmark_corpus/README.md`

### Segmented merge policy calibration

- **Entrypoint:** `benchmarks/aippocampus/benchmark_segmented_merge_policy.py`
- **Reads / updates:** `docs/evidence/benchmarks/reports/fresh-thread/segmented-merge-policy-fixture-report.md`,
  `benchmark_corpus/segmented_merge_policy/fixture.json`, #375


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
| Changed-surface planner | `python tools/aippocampus/test_plan.py --json` | Agent-facing planner that maps changed files to focused tests before escalating to a broader tier. It does not replace CI or broad benchmark lanes. |
| Fast local PR gate | `python tools/aippocampus/run_tests.py --tier pr` | Manifest-classified quick plus PR-critical deterministic contracts for ordinary pre-push use. `fast` is a compatibility alias for this lane. |
| Broad deterministic pre-merge gate | `python tools/aippocampus/run_tests.py --tier broad-pr` | The old broad deterministic surface: fast PR plus smoke and integration modules. CI runs this lane in shards; local agents should run it only when the changed surface needs broad coverage. |
| Deterministic benchmark PR smoke | `python -m pip install -e ".[benchmark]"` then `python tools/aippocampus/run_tests.py --tier benchmark-smoke --benchmark-suite-profile public-fast` | Public-fast suite smoke plus curated public benchmark/report/schema/profile guards and the #279 candidate-seed discovery support guard. No provider calls, private registry data, raw reports, or large corpus downloads. |
| Full benchmark mirror tests | `python tools/aippocampus/run_tests.py --tier benchmark` | All `tests/aippocampus/test_benchmark_*.py` modules. Use when changing benchmark runners, profiles, reports, or claim-boundary helpers. |
| Full repository suite | `python tools/aippocampus/run_tests.py --tier full` | All manifest-classified quick, PR, smoke, integration, slow, and benchmark tests. Use before broad repository-health or public-readiness claims that explicitly need the slow/benchmark surface; routine releases use the release preflight planner plus CI/publish gates. |
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

### Unified Stage 0-5 public-readiness smoke

- **Entrypoint:** `tools/aippocampus/smoke/run_stage_0_5_smoke.py`
- **Primary evidence owner:** `docs/evidence/readiness/public-readiness-verification.md`

### Prompt-hook regression smoke

- **Entrypoint:** `tools/aippocampus/smoke/simulate_prompt_hook.py`
- **Primary evidence owner:** `docs/evidence/benchmarks/design/memory-decision-benchmark-plan.md`

### Prompt-hook latency probe

- **Entrypoint:** `tools/aippocampus/smoke/smoke_prompt_hook_latency.py`
- **Primary evidence owner:** `docs/evidence/benchmarks/design/memory-decision-benchmark-plan.md`, `skills/aippocampus/references/ambient-hooks.md`

### Multilingual prompt-hook smoke

- **Entrypoint:** `tools/aippocampus/smoke/simulate_multilingual_prompt_hook.py`
- **Primary evidence owner:** `docs/evidence/benchmarks/design/memory-decision-benchmark-plan.md`

### Semantic paraphrase reuse smoke

- **Entrypoint:** `tools/aippocampus/smoke/smoke_semantic_paraphrase_reuse.py`
- **Primary evidence owner:** `docs/evidence/benchmarks/design/memory-decision-benchmark-plan.md`

### Living cue cache public-safe smoke

- **Entrypoint:** `tools/aippocampus/smoke/smoke_living_cue_cache.py`
- **Primary evidence owner:** `skills/aippocampus/references/ambient-hooks.md`, `docs/research/ambient-associative-recall.md`, #281

### Query-pattern routes fixture

- **Entrypoint:** `python -m aippocampus_runtime.warm_ambient.query_pattern_enrichment --fixture --json`; unit
  coverage for `aippocampus_runtime.warm_ambient.query_pattern_routes` and hot-path consumption
- **Primary evidence owner:** `skills/aippocampus/references/subconscious-jobs.md`, `docs/guides/public-api.md`, #574

### Real Codex long-session continuity smoke

- **Entrypoint:** `tools/aippocampus/smoke/smoke_codex_long_session_continuity.py`
- **Primary evidence owner:** `docs/evidence/readiness/public-readiness-verification.md`

### Provider-key bridge OS credential-store smoke

- **Entrypoint:** `tools/aippocampus/smoke/smoke_provider_key_bridge_os_store.py`
- **Primary evidence owner:** `docs/guides/install-guide.md`, `docs/evidence/readiness/public-readiness-verification.md`, #784

### E2E50 silent-constraint candidate seed scanner

- **Entrypoint:** `tools/aippocampus/smoke/smoke_e2e50_seed_candidates.py`; deterministic unittest included in `benchmark-smoke`
- **Primary evidence owner:** `docs/evidence/benchmarks/design/memory-decision-benchmark-plan.md`,
  `docs/evidence/benchmarks/reports/e2e50/e2e50-private-local-seed-followup-2026-06-10.md`,
  #279/#1086

### E2E50 public-safe behavior-pack scorer, optional private annotation readiness replay, and private/local field-validation gate

- **Entrypoint:** `benchmarks/aippocampus/benchmark_e2e50_silent_constraint.py`; deterministic unittest included
  in `benchmark-smoke`; `--field-validation` emits the #1981 retained private/local case-count gate;
  sequence/load validator in
  `aippocampus_runtime/coding/sequence_packets.py`; Episode/Arc builder in
  `aippocampus_runtime/coding/episode_arcs.py`
- **Primary evidence owner:** `docs/evidence/benchmarks/design/memory-decision-benchmark-plan.md`,
  `docs/architecture/coordination/episode-arc-read-models.md`,
  `benchmark_corpus/e2e50_silent_constraint/fixture.json`,
  `docs/evidence/benchmarks/reports/e2e50/e2e50-private-annotation-readiness-2026-06-10.json`,
  `docs/evidence/benchmarks/reports/e2e50/e2e50-field-validation-2026-06-16.md`,
  #279/#663/#575/#1154/#1981

### Cognitive-load public behavior-trace feedback and default-path replay fixtures

- **Entrypoint:** `aippocampus_runtime.recall.cognitive_load_sidecar.build_public_behavior_trace_feedback_report`,
  `aippocampus_runtime.recall.cognitive_load_sidecar.build_public_default_path_usefulness_report`;
  deterministic unittest `tests/aippocampus/test_cognitive_load_sidecar.py`
- **Primary evidence owner:** `docs/architecture/recall/cognitive-load-sidecar.md`, `docs/evidence/current-claims.md`,
  `docs/evidence/benchmarks/reports/recall-navigation/cognitive-load-default-path-usefulness-2026-06-14.md`,
  #575/#1375

### Episode/Arc public gappy-chain calibration fixture

- **Entrypoint:** `aippocampus_runtime.coding.episode_arcs.build_public_gappy_chain_calibration_report`;
  deterministic unittest `tests/aippocampus/test_episode_arcs.py`
- **Primary evidence owner:** `docs/architecture/coordination/episode-arc-read-models.md`, `docs/evidence/current-claims.md`, #663

### Episode/Arc public route-producer fixture

- **Entrypoint:** `aippocampus_runtime.coding.episode_arc_route_producer.build_public_episode_arc_route_producer_report`;
  deterministic unittest `tests/aippocampus/test_episode_arc_route_producer.py`
- **Primary evidence owner:** `docs/architecture/coordination/episode-arc-read-models.md`, `docs/evidence/current-claims.md`, #1362/#1363/#663

### Episode/Arc private-history aggregate readout

- **Entrypoint:** `aippocampus episode-arcs --json`; runtime owner
  `aippocampus_runtime.coding.episode_arc_private_adjudication`; deterministic unittest
  `tests/aippocampus/test_episode_arc_private_adjudication.py`
- **Primary evidence owner:** `docs/evidence/reports/episode-arc-private-history-adjudication-2026-06-08.md`,
  `docs/architecture/coordination/episode-arc-read-models.md`, #663

### Claude Code MCP host probe

- **Entrypoint:** `tools/aippocampus/smoke/smoke_claude_code_mcp_host.py`
- **Primary evidence owner:** `docs/evidence/readiness/public-readiness-verification.md`

### Claude Code local-history parser smoke

- **Entrypoint:** `tools/aippocampus/smoke/smoke_claude_code_history.py`
- **Primary evidence owner:** `docs/evidence/readiness/public-readiness-verification.md`

### Synthetic cross-agent continuity smoke

- **Entrypoint:** `tools/aippocampus/smoke/smoke_cross_agent_continuity.py`
- **Primary evidence owner:** `docs/evidence/readiness/public-readiness-verification.md`

### Generic JSONL ecosystem integration smoke

- **Entrypoint:** `tools/aippocampus/smoke/smoke_generic_jsonl_integration.py`
- **Primary evidence owner:** `docs/guides/ecosystem-integration-matrix.md`

### OpenAI Agents SDK function-tool contract smoke

- **Entrypoint:** `tools/aippocampus/smoke/smoke_openai_agents_sdk_tool_contract.py`, `tests/aippocampus/test_openai_agents_sdk_smoke.py`
- **Primary evidence owner:** `docs/guides/ecosystem-integration-matrix.md`

### Life-wide registry aggregate smoke

- **Entrypoint:** `tools/aippocampus/smoke/smoke_life_wide_registry.py`
- **Primary evidence owner:** `docs/evidence/readiness/stage-0-5-readiness.md`

### Real-history memory-pain prompt-hook smoke

- **Entrypoint:** `tools/aippocampus/smoke/smoke_memory_pain_prompt_hook.py`
- **Primary evidence owner:** `docs/evidence/benchmarks/design/memory-decision-benchmark-plan.md`

### Fresh-thread real-history boundary smoke

- **Entrypoint:** `tools/aippocampus/smoke/smoke_fresh_thread_real_history.py`
- **Primary evidence owner:** `docs/evidence/benchmarks/reports/fresh-thread/fresh-thread-real-history-smoke-2026-06-02.md`,
  `docs/evidence/benchmarks/reports/fresh-thread/fresh-thread-expanded-coverage-2026-06-03.md`

### Recall navigation arm comparison smoke

- **Entrypoint:** `tools/aippocampus/smoke/smoke_recall_navigation_comparison.py`
- **Primary evidence owner:** `docs/evidence/benchmarks/reports/recall-navigation/recall-navigation-comparison-2026-06-03.md`, #201, #281, #309, #248, #465

### Recall navigation promotion harness

- **Entrypoint:** `tools/aippocampus/smoke/smoke_recall_navigation_promotion.py`
- **Primary evidence owner:** `docs/evidence/benchmarks/reports/recall-navigation/recall-navigation-comparison-2026-06-03.md`, #1302, #1185, #1300, #1301

### Default-hook recall usefulness four-arm benchmark

- **Entrypoint:** `benchmarks/aippocampus/benchmark_default_hook_recall_usefulness.py` and `tests/aippocampus/test_benchmark_default_hook_recall_usefulness.py`
- **Primary evidence owner:** `docs/evidence/benchmarks/reports/recall-navigation/default-hook-recall-usefulness-2026-06-14.md`,
  `docs/evidence/current-claims.md`, #1439, #1449; separates broad default foreground context
  from the tiny `agent_recall` hook-to-agent affordance

### Real-history semantic scope smoke

- **Entrypoint:** `tools/aippocampus/smoke/smoke_semantic_scope_real_history.py`
- **Primary evidence owner:** `docs/evidence/readiness/stage-0-5-readiness.md`

### Semantic sidecar source-review smoke

- **Entrypoint:** `tools/aippocampus/smoke/smoke_semantic_scope_source_review.py`; public shadow fixture in
  `tests/fixtures/semantic_scope_source_review_shadow/`
- **Primary evidence owner:** `docs/evidence/readiness/stage-0-5-readiness.md`, `docs/evidence/readiness/public-readiness-verification.md`, #993

### Selected source-evidence recall eval and candidate-space diagnostics

- **Entrypoint:** `tools/aippocampus/smoke/smoke_source_evidence_recall_eval.py`
- **Primary evidence owner:** `docs/evidence/readiness/stage-0-5-readiness.md`, `docs/evidence/benchmarks/design/memory-decision-benchmark-plan.md`, #458

### Optional live question-confirmation smoke

- **Entrypoint:** `tools/aippocampus/smoke/smoke_question_confirmation_live.py`
- **Primary evidence owner:** `docs/architecture/recall/question-tracking-subconscious.md`, `docs/evidence/readiness/stage-0-5-readiness.md`

### Question prefilter parity smoke

- **Entrypoint:** `tools/aippocampus/smoke/smoke_question_prefilter_parity.py`
- **Primary evidence owner:** `docs/architecture/recall/question-tracking-subconscious.md`, #248

### Agency host-timing replay smoke

- **Entrypoint:** `tools/aippocampus/smoke/smoke_agency_host_timing.py`
- **Primary evidence owner:** `docs/research/agency-from-cognitive-map.md`,
  `docs/evidence/benchmarks/reports/fresh-thread/agency-host-surface-codex-desktop-2026-06-05.md`,
  #312, #763

### Route-readiness Cognitive Observatory smoke

- **Entrypoint:** `tools/aippocampus/smoke/smoke_route_readiness_observatory.py` and
  `tests/aippocampus/test_cognitive_observatory.py`; includes query-pattern and cognitive-load
  public/private summary projections
- **Primary evidence owner:** `docs/architecture/runtime/cognitive-runtime-architecture.md`, `docs/guides/public-api.md`,
  #574, #575, #576; see also AIppo working-contract Dream candidate readout in
  `tests/aippocampus/test_aippo_working_contract.py`

### Cognitive Observatory current completeness smoke

- **Entrypoint:** `tools/aippocampus/smoke/smoke_cognitive_observatory_current_completeness.py`,
  `aippocampus_runtime.ops.observatory_completeness`, and
  `tests/aippocampus/test_cognitive_observatory_current_completeness.py`
- **Primary evidence owner:** `docs/evidence/benchmarks/reports/cognitive-runtime/cognitive-observatory-current-completeness-2026-06-14.md`,
  `docs/evidence/current-claims.md`,
  `docs/architecture/runtime/cognitive-runtime-architecture.md`, #1443; includes the latest
  comment's reader contract and supported/present/validated surface-state split

### Worker-to-hook handoff smoke

- **Entrypoint:** `tools/aippocampus/smoke/smoke_worker_hook_handoff.py`
- **Primary evidence owner:** `docs/research/ambient-associative-recall.md`, `skills/aippocampus/references/ambient-hooks.md`, #574, #909

### Dream real-history structural, public shadow, topology scout, long-context atlas pack, live atlas pilot, AIppo ripening readout, and user-visible eval

- **Entrypoint:** `skills/aippocampus/scripts/aippocampus_runtime/dream/atlas_pack.py`,
  `skills/aippocampus/scripts/aippocampus_runtime/dream/atlas_live_pilot.py`,
  `skills/aippocampus/scripts/aippocampus_runtime/dream/real_history_eval.py`,
  `skills/aippocampus/scripts/aippocampus_runtime/dream/public_shadow_report.py`,
  `skills/aippocampus/scripts/aippocampus_runtime/dream/topology_scout.py`,
  `benchmarks/aippocampus/benchmark_dream_delivery_quality.py`,
  `skills/aippocampus/scripts/aippocampus_runtime/aippo/working_contract.py`,
  `tests/aippocampus/test_dream_atlas_pack.py`,
  `tests/aippocampus/test_aippo_working_contract.py`,
  `tests/aippocampus/test_benchmark_dream_delivery_quality.py`, and
  `tests/aippocampus/test_dream_live_shadow_ab.py`
- **Primary evidence owner:** `docs/evidence/dream/dream-real-history-model-backed-eval-2026-05-31.md`,
  `docs/evidence/dream/dream-atlas-live-pilot-2026-06-12.md`,
  `docs/evidence/dream/dream-public-closeout-review-2026-06-14.md`,
  `docs/evidence/dream/dream-delivery-quality-eval-2026-06-14.md`,
  `docs/evidence/current-claims.md`, `docs/research/dream-task-design.md`, #163, #248, #575,
  #576, #663, #1268, #1269, #1286, #1438

### Episode/Arc sequence usefulness workload

- **Entrypoint:** `benchmarks/aippocampus/benchmark_episode_arc_sequence_usefulness.py`,
  `skills/aippocampus/scripts/aippocampus_runtime/coding/episode_arc_route_producer.py`, and
  `tests/aippocampus/test_benchmark_episode_arc_sequence_usefulness.py`
- **Primary evidence owner:** `docs/evidence/benchmarks/reports/coordination/episode-arc-sequence-usefulness-2026-06-14.md`,
  `docs/architecture/coordination/episode-arc-read-models.md`,
  `docs/evidence/current-claims.md`, #1440

### Synthetic GB-scale capacity smoke

- **Entrypoint:** `tools/aippocampus/smoke/smoke_synthetic_scale_capacity.py`
- **Primary evidence owner:** `docs/architecture/ops/gb-scale-roadmap.md`

### Long-thread segment build/search soak

- **Entrypoint:** `tools/aippocampus/smoke/smoke_long_thread_segment_soak.py`, `tests/aippocampus/test_long_thread_segment_soak.py`
- **Primary evidence owner:** `docs/architecture/ops/gb-scale-roadmap.md`, #376

### Synthetic question-tracking scale smoke

- **Entrypoint:** `tools/aippocampus/smoke/smoke_question_tracking_scale.py`
- **Primary evidence owner:** `docs/architecture/recall/question-tracking-subconscious.md`, `docs/architecture/ops/gb-scale-roadmap.md`

### Source-backed repo familiarity smoke

- **Entrypoint:** `tools/aippocampus/smoke/smoke_repo_familiarity.py`
- **Primary evidence owner:** `docs/architecture/recall/source-backed-familiarity-map.md`

### Repo familiarity foreground experiment smoke

- **Entrypoint:** `tools/aippocampus/smoke/smoke_repo_familiarity_foreground_experiment.py`
- **Primary evidence owner:** `docs/architecture/recall/source-backed-familiarity-map.md`, #250

### Single-machine cross-device sync smoke

- **Entrypoint:** `tools/aippocampus/smoke/smoke_cross_device_sync.py`
- **Primary evidence owner:** `docs/evidence/readiness/public-readiness-verification.md`

### HTTP object-storage sync smoke

- **Entrypoint:** `tools/aippocampus/smoke/smoke_object_storage_sync.py`
- **Primary evidence owner:** `docs/evidence/readiness/public-readiness-verification.md`

### Docker / WSL alternate-runtime sync smoke

- **Entrypoint:** `tools/aippocampus/smoke/smoke_alternate_runtime_sync.py`
- **Primary evidence owner:** `docs/evidence/readiness/public-readiness-verification.md`

### Real-provider encrypted object-storage smoke

- **Entrypoint:** `tools/aippocampus/smoke/smoke_real_provider_encrypted_sync.py`
- **Primary evidence owner:** `docs/evidence/readiness/public-readiness-verification.md`

### Package-level plugin install smoke

- **Entrypoint:** `plugins/aippocampus/smoke_plugin_install.py`
- **Primary evidence owner:** `docs/evidence/readiness/public-readiness-verification.md`

### Real Codex app-server plugin smoke

- **Entrypoint:** `plugins/aippocampus/smoke_real_codex_host.py`
- **Primary evidence owner:** `docs/evidence/readiness/public-readiness-verification.md`


## Update Rules

- Add every new `benchmarks/aippocampus/benchmark_*.py` runner to this map.
- Add support builders that create benchmark case packs, such as
  `benchmarks/aippocampus/builders/build_warm_ambient_trace_cases.py`, when other docs
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
