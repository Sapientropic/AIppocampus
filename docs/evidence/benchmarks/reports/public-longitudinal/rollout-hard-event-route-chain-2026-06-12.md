# Rollout Hard-Event Route Chain - 2026-06-12

This dated report records a public-safe production-like retrieval run over the
synthetic rollout behavior hard-event fixture. It is a small route-chain and
actionability calibration slice for #1197, #1195, and #309.

The fixture is checked in under `CC0-1.0` and contains no private user history.
The runner output is sanitized: it emits ids, hashes, aggregate metrics, and
claim boundaries, but not raw rollout text, private source refs, local absolute
paths, credentials, or provider responses.

## Commands

```powershell
python benchmarks\aippocampus\benchmark_vcs_future_event_recall.py --dataset benchmark_corpus\public_longitudinal_users\rollout_behavior_events_v1.jsonl --production-like-retrieval --source-disambiguation-top-k 1 --json --output docs\evidence\benchmarks\reports\public-longitudinal\rollout-hard-event-route-chain-topk1-2026-06-12.json
python benchmarks\aippocampus\benchmark_vcs_future_event_recall.py --dataset benchmark_corpus\public_longitudinal_users\rollout_behavior_events_v1.jsonl --production-like-retrieval --source-disambiguation-top-k 2 --json --output docs\evidence\benchmarks\reports\public-longitudinal\rollout-hard-event-route-chain-topk2-2026-06-12.json
python benchmarks\aippocampus\benchmark_vcs_future_event_recall.py --dataset benchmark_corpus\public_longitudinal_users\rollout_behavior_events_v1.jsonl --production-like-retrieval --source-disambiguation-top-k 3 --json --output docs\evidence\benchmarks\reports\public-longitudinal\rollout-hard-event-route-chain-topk3-2026-06-12.json
```

## Result

| Top K | Gate | Recall | Precision | Chain recovery | Source failures | Wrong-source evidence | Stale source in top K | Foreground action false positives |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | failed | 0 / 3 | 0 / 3 | 0 / 3 | 3 | 3 / 3 | 0 / 3 | 0 |
| 2 | passed | 3 / 3 | 3 / 3 | 3 / 3 | 0 | 0 / 3 | 0 / 3 | 0 |
| 3 | passed main gate, noisy | 3 / 3 | 3 / 3 | 3 / 3 | 0 | 2 / 3 | 2 / 3 | 0 |

The useful operating point for this fixture is top-k 2:

- top-k 1 finds the current failed behavior event but misses the paired route
  or reverted-edit source, so it cannot satisfy the source-backed chain;
- top-k 2 recovers all three multi-source support chains and keeps
  narrative-only decoys out of foreground evidence;
- top-k 3 keeps the main recall/precision gate green but starts carrying
  assistant narrative decoys in the top source set, which should stay
  diagnostic rather than foreground-evidence material.

## What It Supports

- The rollout hard-event runner can score future-event recall against a
  complete future window where silence produces false negatives.
- Production-like retrieval can recover selected two-source rollout behavior
  chains without using `required_past_source_ids` as ranking input.
- Successful current events can remain route candidates while the actionability
  gate suppresses foreground action, avoiding old-failure drag.
- The top-k budget matters: broadening candidates after the complete chain is
  recovered can add source-looking noise without improving recall.

## Boundary

This is a public synthetic contract slice, not live agent quality, private
real-history quality, wild VCS corpus quality, external-model superiority, or
source truth from assistant narrative alone. The sample is intentionally small:
three positive hard-event chains, three anti-drift negatives, and three
families (`rejected_route`, `workaround_rationale`, `tacit_constraint`). It
does not close the representative public-quality requirements for #1197 or
the broader #1195 benchmark promotion question by itself.

Machine-readable outputs:
[`top-k 1`](rollout-hard-event-route-chain-topk1-2026-06-12.json),
[`top-k 2`](rollout-hard-event-route-chain-topk2-2026-06-12.json), and
[`top-k 3`](rollout-hard-event-route-chain-topk3-2026-06-12.json).
