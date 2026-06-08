# Benchmark Evidence

Role: local index for benchmark methodology notes, public-safe reports, and
dated measurement files under `docs/evidence/benchmarks/`.
Status: current folder owner; global claim and readiness routing lives in
[`../benchmark-evidence-map.md`](../benchmark-evidence-map.md).

This folder holds benchmark methodology notes, public-safe reports, and dated
measurement records. It is not the current claim snapshot. Start from
[`../benchmark-evidence-map.md`](../benchmark-evidence-map.md) when you need the
complete runner, smoke, corpus, and evidence-owner map.

For current numeric claims, supersession, known negative results, and active
remediation issues, start from
[`../current-claims.md`](../current-claims.md) before opening dated reports in
this folder.

## Reader Path

| Reader need | Start here | Why |
| --- | --- | --- |
| Current claims, negative results, and remediation issues | [`../current-claims.md`](../current-claims.md) | It is the claim snapshot and links active remediation routes such as #960/#963/#958. |
| Which runner or smoke to prioritize | [`design/benchmark-priority-map.md`](design/benchmark-priority-map.md) | It names priority, maturity, default run profile, and cannot-claim boundaries. |
| Why benchmark layers are separate | [`design/README.md`](design/README.md) | It explains the benchmark philosophy without dated result noise. |
| Full maintainer directory | [`../benchmark-evidence-map.md`](../benchmark-evidence-map.md) | It maps every runner, smoke, corpus, and evidence owner. |

## Design Hub

Benchmark design rationale lives in [`design/README.md`](design/README.md).
Use that hub when you need to understand why AIppocampus benchmarks separate
gate decisions, source retrieval, payload fidelity, compaction continuity,
longitudinal hard events, and hippocampal recall-discrimination instead of
collapsing them into one leaderboard.

## Local Owners

| Need | Start here | Boundary |
| --- | --- | --- |
| Benchmark philosophy | [`design/benchmark-design-rationale.md`](design/benchmark-design-rationale.md) | Reader-facing rationale; no raw outputs or current-status upgrades. |
| Benchmark priority and run profiles | [`design/benchmark-priority-map.md`](design/benchmark-priority-map.md) | P0/P1/P2/P3 priority, maturity, default run profile, claim-level, and cannot-claim guidance. |
| Detailed track plan | [`memory-decision-benchmark-plan.md`](memory-decision-benchmark-plan.md) | Track A-D runner details, profiles, diagnostics, and implementation notes. |
| Track S semantic robustness | [`semantic-robustness-track-s.md`](semantic-robustness-track-s.md) | No-live-judge diagnostics for perturbation stability, retrieval invariance, hard negatives, and optional proxy/vector health boundaries. |
| External benchmark comparison home | [`design/external-benchmark-map.md`](design/external-benchmark-map.md) | Analysis map and blockers; not a superiority claim. |
| AMemGym adapter boundary | [`amemgym.md`](amemgym.md) | Public `v1.base` metadata smoke, local overlay metrics, cannot-claim boundary for #733/#742, and #958 official-runner remediation path. |
| Multimodal memory benchmark map | [`design/multimodal-memory-benchmark-map.md`](design/multimodal-memory-benchmark-map.md) | #528 source-shape routing across HippoCamp, MemLens, ATM-Bench, egocentric video, UniDoc, Persona, and conversation-memory benchmarks. |
| ATM-Bench Hard protocol boundary | [`design/atm-bench-hard-protocol-boundary.md`](design/atm-bench-hard-protocol-boundary.md) | Verified upstream-protocol boundary for #528; no adapter, score, or privacy claim. |
| Hippocampal private annotation protocol | [`hippocampal-private-annotation-protocol.md`](hippocampal-private-annotation-protocol.md) | Private H1/H2 real-history sampling and sanitized report rules; no committed private pack. |
| Public-safe multimodal corpus fixture | [`multimodal-corpus-fixture-report.md`](multimodal-corpus-fixture-report.md) | #531 corpus-style contract smoke; not conversational upload recall or ATM-Bench score. |
| Conversational media-ingest fixture | [`conversational-media-ingest-fixture-report.md`](conversational-media-ingest-fixture-report.md) | #532 conversational counterpart; media anchors attach to conversation turns. |
| Multimodal NIAH evidence-pool fixture | [`multimodal-niah-evidence-pool-report.md`](multimodal-niah-evidence-pool-report.md) | #533 supplied-pool answer-synthesis contract; retrieval is not scored. |
| Hippocampal recall diagnostic seed | [`hippocampal-recall-fixture-report.md`](hippocampal-recall-fixture-report.md) | #229/#230/#231 public-safe P1 seed for D/I matrix reporting, source-reopen failures, scent layers, and calibration categories; not full P1 quality. |
| Field Continuity fixture | [`field-continuity-fixture-report.md`](field-continuity-fixture-report.md) | #454 magic-moment reproducibility contract; field reports are seeds, not standalone proof. |

## Report Boundary

Dated reports can stay next to their benchmark family. Do not move or summarize
them into this README unless the summary changes navigation. Raw JSON outputs,
private real-history case packs, local registry exports, and generated report
directories stay out of git unless a small public-safe artifact is deliberately
promoted.

## Contributor Benchmark Commands

For fresh-clone benchmark work, install the stable benchmark extra and start
with the deterministic smoke tier:

```sh
python -m pip install -e ".[benchmark]"
python tools/aippocampus/run_tests.py --tier benchmark-smoke --benchmark-suite-profile public-fast
```

The `benchmark` extra is intentionally empty while this lane uses only stdlib
and checked-in public fixtures. Run `--tier benchmark` for the full benchmark
mirror test tier, and use live/provider benchmark commands only when the owning
track explicitly documents the required environment and privacy boundary.
