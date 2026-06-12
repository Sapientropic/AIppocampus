# Benchmark Family Promotion Candidates - 2026-06-12

This report closes the #1195 decision slice: pick the first benchmark families
that should move from contract-smoke fixtures toward public cohort candidates,
and make the promotion blockers machine-readable. It does not promote any
family to public-quality evidence.

Machine-readable output:
[`benchmark-family-promotion-candidates-2026-06-12.json`](benchmark-family-promotion-candidates-2026-06-12.json).

## Command

```powershell
python benchmarks\aippocampus\benchmark_family_promotion_candidates.py --json --output docs\evidence\benchmarks\benchmark-family-promotion-candidates-2026-06-12.json
```

## Selected Families

| Family | Current contract | Candidate target | Why selected |
| --- | --- | --- | --- |
| Agent continuity loop / recall degradation | 8 public-safe contract cases; `contract_gate_ok=true`; `quality_gate_ok=false` | 180 public-safe target cases across 6 failure families, with 45 held out | Highest user-facing composition risk across recall packets, deepen handles, AIppo guidance, stale/conflict boundaries, and anti-nag behavior. |
| Attention navigation quality | 12 public-safe contract cases; `contract_gate_ok=true`; `quality_gate_ok=false` | 240 public-safe target cases across 8 route/control families, with 60 held out | The source-backed router cannot become a live route producer until route precision, masks, stale/currentness, conflict, action-time, wrong-source, and generic-hint controls have a public cohort path. |
| Map-rot lifecycle debt | 9 public-safe lifecycle-state contract cases; `contract_gate_ok=true`; `quality_gate_ok=false` | 270 public-safe target cases across 9 lifecycle families, with 68 held out | Cold navigation maps can harm usefulness by reviving stale, challenged, quarantined, deleted, dead-lettered, or repeated-wrong routes. |

E2E50 is deferred to #279 because it needs behavior-pack ownership,
compaction-boundary evidence, and ablation arms rather than a generic
family-promotion row. The rollout hard-event V2 cohort is used as a seed for
agent-continuity route-chain cases, but it is not by itself the #1195
contract-smoke promotion decision.

## Required Usefulness Blockers

Each selected family must report these negative controls before moving beyond
candidate status:

| Blocker | Promotion threshold |
| --- | ---: |
| `generic_hints` | 0 |
| `route_label_collisions` | 0 |
| `wrong_route_drag` | 0 |
| `unnecessary_reopen` | 0 |
| `manual_search_fallback` | 0 |

These are usefulness blockers, not only safety counters. A family can keep
`contract_gate_ok=true` while `usefulness_gate_ok=false` and
`quality_gate_ok=false`.

## Gate Boundary

- `contract_gate_ok`: the current deterministic contract still passes.
- `usefulness_gate_ok`: false until the candidate cohort proves the usefulness
  blockers above are zero and the attention-cost gate is measured.
- `quality_gate_ok`: false until the candidate cohort is actually built,
  measured, kept source-safe, and evaluated against held-out cases excluded
  from prompt, threshold, or fixture tuning.

The candidate case counts in the JSON are target metadata, not observed
pass/fail results. Wilson intervals are required on measured candidate rates,
but confidence intervals cannot repair selected-sample bias.

## Sanitization

The report is public-safe and synthetic / public-replayable only. It emits no
raw text, private text, raw source refs, local paths, provider output, or
credentials.

## Cannot Claim

Do not cite this report as representative public quality, holdout quality,
private-history quality, live host behavior lift, answer-generation quality, or
external-system superiority.
