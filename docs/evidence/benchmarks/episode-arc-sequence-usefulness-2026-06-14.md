# Episode/Arc Sequence Usefulness - 2026-06-14

This public-safe benchmark closes #1440 as a sequence-usefulness workload over
the existing Episode/Arc route producer. It compares the same source budget with
and without Episode/Arc sequence route material.

## Command

```powershell
python benchmarks\aippocampus\benchmark_episode_arc_sequence_usefulness.py `
  --json `
  --output docs\evidence\benchmarks\episode-arc-sequence-usefulness-2026-06-14.json
```

Focused verification:

```powershell
python -m pytest tests\aippocampus\test_benchmark_episode_arc_sequence_usefulness.py -q
```

## Cohort

The cohort reuses the public synthetic rows from
`aippocampus_runtime.coding.episode_arc_route_producer` and projects them into
two arms:

- `baseline_no_episode_arc`: same source-ref hash budget, no ordered
  Episode/Arc route packet.
- `episode_arc_route_packet`: same source-ref hash budget plus the ordered
  route material.

Families covered:

- commit/revert failed route
- PR rejection/merge failed route
- issue reopen frontier
- patch supersession/currentness
- workaround removal no-harm control
- missing-middle negative control
- wrong-order negative control

## Result

| Metric | Value |
|---|---:|
| Cases | 7 |
| Treatment wins | 4 |
| Treatment regressions | 0 |
| Manual-search step delta | 7 |
| Repeated-mistake avoidance lift | 2 |
| Correct source-reopen lift | 4 |
| Stale-chain suppression lift | 1 |
| Quiet/no-harm controls | 2 |
| Wrong-project contamination | 0 |
| Source-truth overclaim count | 0 |
| Provider calls | 0 |

## Can Claim

- A public synthetic sequence-usefulness workload exists for #1440.
- In selected ordered-route cases, Episode/Arc route packets reduce manual
  search and avoid repeated wrong routes under the same source budget.
- Missing-middle and wrong-order sequences stay quiet/no-harm and do not become
  source-truth claims.

## Cannot Claim

- Live host behavior lift.
- Private-history generality.
- Default recall route-producer adoption.
- Episode/Arc as source truth.
- Claims without source reopen.

## Public Boundary

The committed report serializes source-ref hash counts only. It does not commit
raw source text, raw source refs, thread/message handles, local paths, provider
payloads, or private-history rows.
