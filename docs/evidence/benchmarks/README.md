# Benchmark Evidence

This folder holds benchmark methodology notes, public-safe reports, and dated
measurement records. It is not the current claim snapshot. Start from
[`../benchmark-evidence-map.md`](../benchmark-evidence-map.md) when you need the
complete runner, smoke, corpus, and evidence-owner map.

## Design Hub

Benchmark design rationale lives in [`design/README.md`](design/README.md).
Use that hub when you need to understand why AIppocampus benchmarks separate
gate decisions, source retrieval, payload fidelity, compaction continuity,
longitudinal hard events, and hippocampal recall-discrimination instead of
collapsing them into one leaderboard.

## Canonical Owners

| Need | Start here | Boundary |
| --- | --- | --- |
| Current claim snapshot | [`../readiness/stage-0-5-readiness.md`](../readiness/stage-0-5-readiness.md) | Can-claim / cannot-claim status only; not a dated command ledger. |
| Dated verification ledger | [`../readiness/public-readiness-verification.md`](../readiness/public-readiness-verification.md) | Summarized command evidence; old entries can be historical. |
| Full runner and smoke map | [`../benchmark-evidence-map.md`](../benchmark-evidence-map.md) | Navigation owner for benchmark and smoke entrypoints. |
| Benchmark philosophy | [`design/benchmark-design-rationale.md`](design/benchmark-design-rationale.md) | Reader-facing rationale; no raw outputs or current-status upgrades. |
| Detailed track plan | [`memory-decision-benchmark-plan.md`](memory-decision-benchmark-plan.md) | Track A-D runner details, profiles, diagnostics, and implementation notes. |
| External benchmark comparison home | [`design/external-benchmark-map.md`](design/external-benchmark-map.md) | Analysis map and blockers; not a superiority claim. |
| ATM-Bench Hard protocol boundary | [`design/atm-bench-hard-protocol-boundary.md`](design/atm-bench-hard-protocol-boundary.md) | Verified upstream-protocol boundary for #528; no adapter, score, or privacy claim. |
| Public-safe multimodal corpus fixture | [`multimodal-corpus-fixture-report.md`](multimodal-corpus-fixture-report.md) | #531 corpus-style contract smoke; not conversational upload recall or ATM-Bench score. |

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
