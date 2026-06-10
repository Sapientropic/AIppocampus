# Map-Rot Lifecycle-Debt Benchmark

Role: public-safe benchmark evidence for #1126.
Status: current deterministic fixture guard.

This benchmark checks that cold navigation-map objects can remain historically
preserved without being treated as current action guidance. The route still
belongs to the source trail when it is reopenable, but stale, challenged,
quarantined, superseded, missing-middle, deleted/no-recall, dead-lettered, and
repeated-wrong objects must not quietly reappear as foreground navigation.

## Commands

```powershell
python benchmarks\aippocampus\benchmark_map_rot_lifecycle_debt.py --json
python -m pytest tests\aippocampus\test_benchmark_map_rot_lifecycle_debt.py -q
python tools\aippocampus\run_tests.py --tier benchmark-smoke --benchmark-suite-profile public-fast
```

The runner is deterministic and public-safe. It emits lifecycle labels, ages,
next actions, red-line counters, and aggregate backlog metrics. It does not
emit raw source text, private text, or local paths.

## Current Fixture Result

Local deterministic run on 2026-06-10:

| Metric | Value |
| --- | ---: |
| `case_count` | 9 |
| `historically_preserved_count` | 8 |
| `eligible_current_navigation_count` | 1 |
| `challenged_backlog_count` | 1 |
| `oldest_challenged_age_days` | 45 |
| `review_needed_count` | 2 |
| `missing_middle_warning_count` | 1 |
| `dead_letter_count` | 1 |
| `refresh_recommended_count` | 2 |
| `silence_recommended_count` | 2 |
| `prune_or_decay_candidate_count` | 5 |

Hard red-line counters are zero in the fixture:

- `stale_as_current_count`
- `masked_source_resurrection_count`
- `quarantined_route_emit_count`
- `superseded_route_emit_count`
- `wrong_route_revival_count`
- `deleted_no_recall_emit_count`

Maturity metadata:

- `benchmark_maturity_level = contract_smoke`
- `contract_gate_ok = true`
- `quality_gate_ok = false`
- `minimum_family_case_floor = 30`
- `sample_floor_met = false`
- `next_promotion_target = public_cohort_candidate`

The contract gate says the selected lifecycle fixtures still protect the
stale/current, mask, quarantine, supersession, and deletion red lines. It is
not representative map-rot quality evidence until a later public/external
cohort, sample-floor, uncertainty, holdout, and no-tuning-leak promotion
explicitly passes.

## Fixture Cases

| Case | Lifecycle pressure | Expected behavior |
| --- | --- | --- |
| `stale_current_pointer_refresh` | A preserved route is old enough to require source refresh. | Do not emit the route; recommend `refresh_source`. |
| `challenged_conflict_backlog` | A conflict set still needs human or source review. | Do not emit the route; count backlog age and review need. |
| `quarantined_masked_route_silent` | A masked route is quarantined. | Stay silent; increment no red-line counter. |
| `superseded_route_uses_successor` | A route has a known successor. | Do not emit the old route; reopen/use the successor path instead. |
| `pathlet_missing_middle_warning` | A pathlet lacks the middle source span. | Emit a missing-middle warning and deepen before route use. |
| `deleted_no_recall_object_silent` | A route has been deleted and marked no-recall. | Stay silent and treat it as a decay/prune candidate. |
| `dead_lettered_cache_row_ignored` | A cache row is dead-lettered. | Ignore or compact it; do not use it as guidance. |
| `repeated_wrong_route_suppressed` | A route has repeated wrong-route feedback. | Suppress until source state changes. |
| `current_reopenable_route_allowed` | A current route is still eligible. | Emit the reopenable route. |

## Claim Boundary

This benchmark supports a narrow claim: the checked-in lifecycle fixture reports
map-rot pressure separately from current route eligibility and keeps red-line
navigation leaks at zero.

It does not prove:

- `cold_map_self_cleaning`
- `all_conflicts_resolved`
- `stale_memory_cannot_remain_in_history`
- `automatic_semantic_cleanup_solved`
- `private_history_map_rot_quality`

The pruning/decay markers are action guidance for operators and future
maintenance code, not a claim that AIppocampus already auto-cleans cold maps.
