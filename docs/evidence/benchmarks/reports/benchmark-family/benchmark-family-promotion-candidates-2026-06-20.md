# Benchmark Family Promotion Candidates - 2026-06-20

This report updates the #1195 family-promotion slice after #2396. The selected
agent-continuity and map-rot families now carry observed public/holdout cohort
measurements instead of only target cohort metadata.

Machine-readable output:
[`benchmark-family-promotion-candidates-2026-06-20.json`](benchmark-family-promotion-candidates-2026-06-20.json).

Supporting cohort artifacts:

- [`agent_continuity_loop_public_cohort.json`](../agent_continuity_loop_public_cohort.json)
- [`map_rot_lifecycle_debt_public_cohort.json`](../map_rot_lifecycle_debt_public_cohort.json)

## Commands

```powershell
python benchmarks\aippocampus\benchmark_agent_continuity_loop.py --public-cohort --json --output docs\evidence\benchmarks\reports\agent_continuity_loop_public_cohort.json
python benchmarks\aippocampus\benchmark_map_rot_lifecycle_debt.py --public-cohort --json --output docs\evidence\benchmarks\reports\map_rot_lifecycle_debt_public_cohort.json
python benchmarks\aippocampus\benchmark_family_promotion_candidates.py --json --output docs\evidence\benchmarks\reports\benchmark-family\benchmark-family-promotion-candidates-2026-06-20.json
```

## Observed Results

| Family | Public cohort | Holdout | Usefulness blockers | Attention/foreground cost | Gate |
| --- | ---: | ---: | --- | --- | --- |
| `agent_continuity_loop` | 180 | 45 | all required blocker counts/rates are `0` | `attention_cost_ok=true`, `foreground_noise_added_count=0` | `public_quality_gate_ok=true` |
| `map_rot_lifecycle_debt` | 270 | 68 | all required blocker counts/rates are `0` | `attention_cost_ok=true`, `foreground_noise_added_count=0` | `public_quality_gate_ok=true` |

Top-level public-quality denominator math is explicit in the JSON:

- evaluated public-quality family surfaces: `3`
- public-quality gate rate: `3 / 3 = 1.0`
- selected public cohort rows: `450`
- selected holdout rows: `113`
- selected usefulness blocker zero rate: `10 / 10 = 1.0`

The observed blocker families are:

- `generic_hints`
- `route_label_collisions`
- `wrong_route_drag`
- `unnecessary_reopen`
- `manual_search_fallback`

For both selected families, `holdout_used_for_tuning_count=0` and the family
promotion report has `next_measurement_actions=[]`.

## Closed Owner Handling

Historical owner issues are still recorded as history only:

- `agent_continuity_loop`: historical owner `#1969`, now measured by the
  embedded public cohort.
- `map_rot_lifecycle_debt`: historical owner `#1948`, now measured by the
  embedded public cohort.

No unresolved measurement action points only to a closed issue. If a future
family regresses, the family report should point to a live scoped issue instead
of reusing these historical owners.

## Boundary

The old candidate case counts remain useful as cohort-design metadata, but they
are no longer the evidence for these two families. The evidence is the observed
public/holdout cohort result and the zero blocker counts/rates in the linked
JSON artifacts.

This does not claim live host behavior, private-history quality, answer
generation quality, or cleanup-write runtime adoption.
