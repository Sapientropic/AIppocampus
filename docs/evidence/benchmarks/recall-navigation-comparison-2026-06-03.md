# Recall Navigation Comparison Smoke - 2026-06-03

This is a public-safe deterministic smoke for GitHub #465. It also carries a
narrow GitHub #201 readout for route actionability and source-reopen
follow-through. It compares three source-navigation arms on the same synthetic
clean-source fixtures:

- direct `search_memory`
- hook-only scent/card behavior
- progressive `recall_context -> recall_deepen`

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

All cases are no-write and use temporary clean-source fixtures. The report does
not serialize raw cues, raw source snippets, route handles, local paths, or
private registry data.

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

The aggregate fixture run updated on 2026-06-04 showed:

- direct search: source-backed success on all 4 cases, but with manual query
  invention in the vague cases (`avg_manual_query_invention_count=1.5`);
- hook-only: no source-backed success, one scent-as-fact violation fixture, and
  one wrong-route drag fixture;
- progressive recall: actionable `recall_deepen` route on all 4 cases,
  source-backed success on the 3 non-stale cases,
  `source_reopen_follow_through_rate=0.75`, and deterministic stale-handle
  rejection before source use.

## #201 Readout

For #201, this smoke now measures only two deterministic proxy outcomes:

- `route_actionability_rate`
- `source_reopen_follow_through_rate`

The report intentionally marks these #201 outcomes as not measured:

- default foreground first-turn lift;
- default foreground second-turn lift;
- live registry quality.

So this evidence can support a narrow route-follow-through slice, but it is not
a #201 closeout signal.

## Can Claim

- The progressive navigation MCP path can be compared against direct search and
  hook-only behavior on public synthetic clean-source fixtures.
- The smoke exercises a vague source-backed deepening case, multilingual vague
  cue cases, and a stale-handle negative case.
- The comparison keeps hook scent, route handles, and report metrics as
  navigation/evidence diagnostics, not factual memory claims.

## Cannot Claim

- Live user quality improvement.
- Live token, tool-call, or wall-clock reduction.
- Production selector superiority over direct search.
- Large-sample statistical significance.
- That hook-only behavior is unsafe in all real settings; the hook-only arm is a
  boundary fixture, not a live-agent study.

Use this smoke as deterministic contract evidence for #465 and as a narrow #201
route-actionability/source-reopen proxy. Stronger user-facing claims still need
live or replay evaluations with real agent behavior and sanitized cost traces.
