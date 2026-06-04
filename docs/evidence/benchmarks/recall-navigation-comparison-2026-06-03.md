# Recall Navigation Comparison Smoke - 2026-06-03

This is a public-safe deterministic smoke for GitHub #465. It also carries a
narrow GitHub #201 readout for route actionability, source-reopen
follow-through, and default foreground route/cache delivery. It compares three
source-navigation arms on the same synthetic clean-source fixtures, plus one
two-turn foreground-hook fixture:

- direct `search_memory`
- hook-only scent/card behavior
- progressive `recall_context -> recall_deepen`
- default foreground route/cache delivery under a simulated semantic timeout

The runner is:

```powershell
python tools\aippocampus\smoke\smoke_recall_navigation_comparison.py --json
```

## Fixture Coverage

The smoke uses four public synthetic cases:

- vague same-thread reference to a "magic moment" source;
- stale-handle fast rejection after clean-source fingerprint changes;
- Chinese vague life-wide cue;
- transliterated Russian vague cue.

All cases use temporary fixtures only. The smoke writes temporary clean-source,
SQLite, and cache files, but does not write to the repository or live registry.
The report does not serialize raw cues, raw source snippets, route handles,
local paths, or private registry data.

## Result Shape

The report includes these metrics for each arm:

- `source_backed_success`
- `manual_query_invention_count`
- `tool_call_count`
- `route_actionable`
- `source_reopen_attempted`
- `source_reopen_follow_through`
- `wrong_route_drag_count`
- `scent_as_fact_violation`
- `time_to_first_useful_source_observed_ms`
- `input_token_proxy`

The `foreground_lift` fixture also reports:

- first-turn route delivery under `semantic_provider_timeout`;
- second-turn ambient cache reuse;
- evidence count and source-boundary preservation.

The aggregate fixture run updated on 2026-06-04 showed:

- direct search: source-backed success on all 4 cases, but with manual query
  invention in the vague cases (`avg_manual_query_invention_count=1.5`);
- hook-only: no source-backed success, one scent-as-fact violation fixture, and
  one wrong-route drag fixture;
- progressive recall: actionable `recall_deepen` route on all 4 cases,
  source-backed success on the 3 non-stale cases,
  `source_reopen_follow_through_rate=0.75`, and deterministic stale-handle
  rejection before source use.
- foreground lift: first turn emitted a navigation-only `scent` route under a
  simulated semantic timeout with `evidence_count=0`; second turn reused the
  ambient cache with `cache_status=hit` and kept the source boundary intact.

## #201 Readout

For #201, this smoke now measures four deterministic proxy outcomes:

- `route_actionability_rate`
- `source_reopen_follow_through_rate`
- `default_foreground_first_turn_lift`
- `default_foreground_second_turn_lift`

The foreground fields are narrow fixture readouts. First turn means the prompt
hook can still deliver a local route when semantic provider work times out.
Second turn means the next prompt can reuse the temporary ambient cache instead
of staying purely first-turn cold.

The report intentionally keeps this #201 outcome as not measured:

- live registry quality.

So this evidence can support a narrow route/cache-delivery slice, but it is not
a #201 closeout signal.

## Can Claim

- The progressive navigation MCP path can be compared against direct search and
  hook-only behavior on public synthetic clean-source fixtures.
- The smoke exercises a vague source-backed deepening case, multilingual vague
  cue cases, and a stale-handle negative case.
- The foreground fixture exercises semantic-timeout-but-route-available and
  next-turn cache reuse without external model calls.
- The comparison keeps hook scent, route handles, and report metrics as
  navigation/evidence diagnostics, not factual memory claims.

## Cannot Claim

- Live user quality improvement.
- Live token, tool-call, or wall-clock reduction.
- Broad default foreground lift on live registries.
- Production selector superiority over direct search.
- Large-sample statistical significance.
- That hook-only behavior is unsafe in all real settings; the hook-only arm is a
  boundary fixture, not a live-agent study.

Use this smoke as deterministic contract evidence for #465 and as a narrow #201
route-actionability/source-reopen/foreground-cache proxy. Stronger user-facing
claims still need live or replay evaluations with real agent behavior and
sanitized cost traces.
