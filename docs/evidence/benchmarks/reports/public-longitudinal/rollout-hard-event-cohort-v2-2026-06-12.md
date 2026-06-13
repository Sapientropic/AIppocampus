# Rollout Hard-Event Cohort V2 - 2026-06-12

This dated report records the first broader public-safe rollout behavior
hard-event cohort for #1197. It extends the earlier 3-chain top-k calibration
into 17 synthetic agent-behavior projects and 34 future events while keeping
the same source-backed scoring boundary: assistant narrative may orient the
case, but only behavior-backed tool/test/edit/route traces can support a
flag-worthy hard event.

The fixture is checked in under `CC0-1.0` at
`benchmark_corpus/public_longitudinal_users/rollout_behavior_events_v2.json`.
It contains no private history, raw Codex rollouts, local paths, credentials,
or provider output.

## Command

```powershell
python benchmarks\aippocampus\benchmark_vcs_future_event_recall.py --dataset benchmark_corpus\public_longitudinal_users\rollout_behavior_events_v2.json --production-like-retrieval --source-disambiguation-top-k 2 --json --output docs\evidence\benchmarks\reports\public-longitudinal\rollout-hard-event-cohort-v2-topk2-2026-06-12.json
```

## Result

| Metric | Value |
| --- | ---: |
| Projects | 17 |
| Future events | 34 |
| Flag-worthy hard events | 17 |
| Anti-drift negatives | 17 |
| Recall | 17 / 17 |
| Precision | 17 / 17 |
| Multi-source chains recovered | 17 / 17 |
| Source-support failures | 0 |
| Wrong-source evidence rate | 0.0 |
| Stale source in top-k rate | 0.0 |
| Foreground action false positives | 0 |
| Anti-drift violations | 0 |
| Current-vs-stale pairwise wins | 34 / 34 |

Family split for the 17 flag-worthy events:

| Family | Gold events | Recall |
| --- | ---: | ---: |
| `rejected_route` | 4 | 1.0 |
| `workaround_rationale` | 5 | 1.0 |
| `tacit_constraint` | 8 | 1.0 |

The cohort covers temporal override, cross-project contamination, cross-scope
drift, post-compaction gaps, intentional forget boundaries, Dream candidate
boundaries, host-surface readiness, route-topic specificity, privacy redlines,
observability boundaries, action-time latency, and tool-scope failures.

## What It Supports

- A public, reproducible #1197 hard-event pack now exists for deterministic
  rollout-behavior continuity work.
- The production-like source-disambiguation arm can recover 17 two-source
  behavior chains without using `required_past_source_ids` as ranking input.
- The same actionability gate that suppresses successful current events keeps
  old-failure route drag out of foreground action.
- The pack exercises temporal override and cross-scope/cross-project drift
  without using private history.

## Boundary

This is still synthetic public evidence. It does not claim live agent quality,
private real-history continuity quality, wild public VCS corpus quality,
external-model superiority, or #1195 benchmark-family promotion by itself.

Machine-readable output:
[`rollout-hard-event-cohort-v2-topk2-2026-06-12.json`](rollout-hard-event-cohort-v2-topk2-2026-06-12.json).
