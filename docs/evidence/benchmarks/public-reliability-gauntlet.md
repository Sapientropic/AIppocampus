# Public Reliability Gauntlet

Status: implemented public-safe aggregate gate for GitHub #1102.

This page owns the narrow evidence boundary for
`benchmarks/aippocampus/benchmark_public_reliability_gauntlet.py`. The runner
does not create a new scorer. It projects existing public-safe benchmark and
smoke surfaces into three separate axes so future agents can see what is
covered without blending unrelated proof layers into one score.

## What It Covers

The default gauntlet reports:

- `runtime_stability`: the published LongMemEval-S 500-question aggregate plus
  synthetic scale/fanout and question-tracking scale metrics.
- `mis_recall_quality`: LongMemEval-S session/source-line/context-visible
  retrieval metrics, exact-line miss taxonomy, and public hard-negative /
  false-evidence suppression diagnostics.
- `pollution_hygiene`: knowledge-pollution, privacy-partition, and auto-hook
  pollution fixtures covering tool traces, recalled echoes, empty/run-id
  envelopes, transient state, and host metadata.

The axes are deliberately separate. Runtime pressure, exact-line citation
quality, and pollution hygiene fail in different ways; a single aggregate
number would make those failures harder to see.

Related gate: the #1111
[`attention-navigation-quality.md`](reports/recall-navigation/attention-navigation-quality.md) benchmark
separately covers route precision, hard masks, stale/currentness, conflict,
action-time, anti-nag, and bounded-evidence red lines for the attention router.
It can inform future gauntlet discussions, but it is not folded into the three
axes above or any single aggregate score.

## Current Dated Result

The current report is:
[`public-reliability-gauntlet-2026-06-10.json`](reports/public-reliability/public-reliability-gauntlet-2026-06-10.json).

Summary:

| Axis | Status | Selected metrics |
| --- | --- | --- |
| `runtime_stability` | `passed_with_warnings` | LongMemEval-S 500Q runtime `803.10s`; synthetic clean source `4 GiB`; synthetic segment count `64`; worst-case SQLite handles `192`; planned handles `64`; warnings `clean_source_gb_scale`, `sync_policy_bytes`, `query_fanout`; blockers `0`; question-tracking candidates `48`, all-pair count `1128`. |
| `mis_recall_quality` | `diagnostic_passed` | LongMemEval-S session R@10 `479/500 = 0.9580`; exact evidence-line R@10 `408/479 = 0.8518`; context-visible evidence R@10 `452/479 = 0.9436`; hard-negative suppression `1.0`; explicit-negation violations `0`; source-evidence over-escalations `0`. |
| `pollution_hygiene` | `fixture_gates_passed` | Knowledge contamination, stale-source harm, authority override, privacy partition leak, and unsupported-claim rates all `0.0`; auto-hook durable writes, bounded-evidence emissions, source-backed fact emissions, recalled-echo re-extraction, and empty-message memory emissions all `0`. |

## Command

Run the default public-safe gauntlet from the repository root:

```powershell
python benchmarks\aippocampus\benchmark_public_reliability_gauntlet.py --json
```

Write the current dated report:

```powershell
python benchmarks\aippocampus\benchmark_public_reliability_gauntlet.py --output docs\evidence\benchmarks\reports\public-reliability\public-reliability-gauntlet-2026-06-10.json
```

Optional physical-file segmented search soak:

```powershell
python benchmarks\aippocampus\benchmark_public_reliability_gauntlet.py --segment-soak --json
```

The default run skips the physical-file segment soak to keep the public
gauntlet usable as a normal benchmark-smoke surface. The report records that
skip and keeps `windows_interrupted_rebuild_recovery` and real file segment
runtime out of claim scope unless the optional arm is run.

## Public-Safe Boundary

The gauntlet emits aggregate metrics, fixture family counts, hashes, and
claim-boundary metadata only. It does not emit raw private text, raw
LongMemEval text, raw fixture text, local absolute paths, secrets, tokens, or
external-model payloads.

LongMemEval-S 500Q is referenced through the published aggregate in
[`longmemeval.md`](longmemeval.md), not by committing the generated raw report.
The raw dataset and benchmark reports stay local/gitignored because this
gauntlet only needs the aggregate runtime and retrieval-quality row.

## Can Claim

- AIppocampus has a public-safe reliability gate covering runtime pressure,
  mis-recall diagnostics, and pollution hygiene.
- The gate records LongMemEval-S 500Q aggregate retrieval metrics and exact-line
  miss taxonomy without publishing raw benchmark text.
- The gate includes public synthetic scale/fanout and question-tracking scale
  metrics with warning/blocker taxonomy.
- The gate includes hard-negative / false-evidence suppression and
  auto-hook/write-path pollution fixtures.
- The default report is sanitized and keeps claim boundaries explicit.

## Cannot Claim

- LongMemEval QA score, judge-model quality, SOTA, or answer-generation quality.
- Real GB/TB registry runtime, real private-history runtime, or hosted/cloud
  scale proof.
- Private-history quality, broad real-user recall quality, or live user-visible
  improvement.
- Exact-line citation quality being solved.
- Live hook write-path quality or durable memory-write implementation.
- Competitor superiority.
- A single aggregate reliability score.
