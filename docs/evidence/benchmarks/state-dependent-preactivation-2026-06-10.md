# State-Dependent Preactivation Fixture 2026-06-10

Role: public-safe benchmark evidence for #1082.
Status: current deterministic fixture for state-dependent warm ambient
preactivation; not a live foreground-hook rollout.

## Command

```powershell
python benchmarks\aippocampus\benchmark_state_dependent_preactivation.py --json
```

The CLI emits a public smoke summary only. Detailed metrics below are taken
from `run_state_dependent_preactivation_benchmark()` and its deterministic
unit coverage.

Targeted unit coverage:

```powershell
python -m pytest tests\aippocampus\test_prewarm_planner.py tests\aippocampus\test_benchmark_state_dependent_preactivation.py -q
```

## Result

The fixture compares a simple warm ambient baseline against a state-dependent
arm that gates route preparation by `phase_context`, active frontier proximity,
salience, ambient cache state, and active recall lock compatibility.

| Metric | Simple warm baseline | State-dependent arm |
| --- | ---: | ---: |
| Case count | 4 | 4 |
| Candidate count | 7 | 7 |
| Expected prepare count | 2 | 2 |
| Preactivation hit rate | 1.0 | 1.0 |
| False preactivation rate | 0.4 | 0.0 |
| Source-reopen success rate | 1.0 | 1.0 |
| Foreground-noise suppression rate | 0.6 | 1.0 |
| Model call count | 0 | 0 |
| Source-reopen attempt cost units | 4 | 2 |
| Estimated total cost units | 19 | 13 |

Comparison deltas:

- `state_dependent_false_preactivation_delta = -0.4`
- `state_dependent_source_reopen_cost_delta = -2`
- `state_dependent_estimated_total_cost_delta = -6`

The state-dependent arm preserved the two expected route preparations while
suppressing the off-state review/planning routes that the simple baseline would
have prepared. Stale, privacy-blocked, and conflicted candidates stayed silent.
Predicted route handles used only `direction_only` or `reopenable_route`; no
row used `source_open` because this no-write benchmark does not reopen source.

## Fixture Coverage

The selected public-safe cases cover:

- debugging-loop frontier proximity preparing a relevant route;
- planning without an active frontier staying quiet;
- handoff plus active recall lock enriching a route handle;
- stale, privacy-blocked, and conflicted routes being suppressed.

`route_readiness` now treats `conflicted`, `refuted`, and `uncertain`
freshness-like states as suppressible route states, matching the #1081
retrieval-reconsolidation vocabulary. `prewarm_planner` rows also emit an
explicit `action_grammar` so route preparation cannot be mistaken for source
truth.

## Boundary

Can claim:

- a public-safe #1082 fixture exists;
- state-dependent preactivation is compared against a simple warm ambient
  baseline;
- the fixture reports separate hit, false-preactivation, source-reopen,
  foreground-noise, and cost-proxy metrics;
- stale/privacy-blocked/conflicted candidates are suppressed in this fixture.

Cannot claim:

- live foreground preactivation is enabled;
- preactivation routes are evidence or memory truth;
- live latency savings, ADHD productivity lift, or general proactive-agent
  behavior are proven;
- broad private-history or real-user quality is measured.
