# Recall Navigation Comparison Smoke - 2026-06-03

This is a public-safe deterministic smoke for GitHub #465. It also carries a
narrow GitHub #201 readout for route actionability, source-reopen
follow-through, default foreground route/cache delivery, foreground packet
source-reopen follow-through, and a #201/#281/#309/#248 vague-cue candidate
funnel readout. It compares four source-navigation arms on the same synthetic
clean-source fixtures, plus one two-turn foreground-hook fixture:

- direct `search_memory`
- hook-only scent/card behavior
- progressive `recall_context -> recall_deepen`
- attention-router navigation-only over the same `recall_context` candidates
- default foreground route/cache delivery under a simulated semantic timeout

The runner is:

```powershell
python tools\aippocampus\smoke\smoke_recall_navigation_comparison.py --json
```

The promotion harness for #1302 / #1185 now routes active default-promotion
ownership through #2559:

```powershell
python tools\aippocampus\smoke\smoke_recall_navigation_promotion.py --json
```

## Fixture Coverage

The smoke uses five public synthetic cases:

- vague same-thread reference to a "magic moment" source;
- stale-handle fast rejection after clean-source fingerprint changes;
- Chinese vague life-wide cue;
- transliterated Russian vague cue;
- light Arabic continuity cue for the AIppocampus/little-hippocampus route
  family.

All cases use temporary fixtures only. The smoke writes temporary clean-source,
SQLite, and cache files, but does not write to the repository or live registry.
The report does not serialize raw cues, raw source snippets, route handles,
local paths, or private registry data.

## Promotion Harness Readout

The promotion harness is the shared gate for recall-navigation features before
they can be argued into default foreground behavior. It is intentionally stricter
than the comparison smoke:

- pre-registered arms: `baseline_flat_recall`, `feature_navigation_only`, and
  `feature_plus_deepen`;
- identical source corpus, query set, packet budget, and deepen budget across
  arms;
- required distractor families: stale, conflict, noise, and wrong-source;
- explicit feature hurt / no-op accounting;
- explicit manual-search fallback, wrong-source route, foreground byte, and
  correct-but-useless warning counters;
- hard red lines for privacy bypass, masked-source resurrection,
  claim-without-source-reopen, and stale-as-current.

The 2026-06-12 fixture run reports `promotion_decision=not_promoted`. This is
the desired behavior for now: #2559 owns the next default-promotion decision,
while #1300 Yi Macro Orientation and #1301 Attention Router remain historical
feature evidence owners. The report can close #1302 as a harness
implementation, but it does not close #1185's broader default-session /
natural-handoff usefulness gate by itself.

For the historical #1300 macro-navigation slice, the harness now includes a
public-safe `macro_navigation` fixture
case. The macro arm uses the same route set and budgets as the baseline, consumes
a scoped project macro state as a navigation prior, and reports:

- `active_layer_order_delta_count=1`;
- `hamming_fanout_delta_count=1`;
- `momentum_recheck_diagnostic_count=1`;
- `manual_search_fallback_reduction_count>=1`;
- zero `stale_as_current` and zero `claim_without_source_reopen`.

This is enough to show that scoped macro state can change route ordering,
candidate fanout, and currentness/recheck diagnostics in the agent recall path.
It is not enough to promote macro navigation to default-ready behavior.

For the historical #1301 attention-router slice, `feature_navigation_only` consumes the
`attention_router_navigation_only` comparison arm. That arm may select a
route-family and report packet cost, but it is not source-backed success until
the separate `feature_plus_deepen` arm reopens clean source. The attention
activation readout also carries a pure Arabic deictic negative control: `هل في
تصميمه عائق قاتل؟` should fall back to `clarify_or_recall`, not silently bind
to whichever context is visible.

## Result Shape

The report includes these metrics for each arm:

- `source_backed_success`
- `manual_query_invention_count`
- `tool_call_count`
- `route_actionable`
- `route_handle_present`
- `source_join_present`
- `source_reopen_attempted`
- `reopen_landed`
- `source_reopen_follow_through_eligible`
- `expected_fail_closed`
- `failure_class`
- `source_reopen_follow_through`
- `wrong_route_drag_count`
- `scent_as_fact_violation`
- `claim_without_source_reopen_count`
- `selected_route_family`
- `time_to_first_useful_source_observed_ms`
- `input_token_proxy`

The `foreground_lift` fixture also reports:

- first-turn route delivery under `semantic_provider_timeout`;
- second-turn ambient cache reuse;
- source reopen after consuming the foreground packet's candidate ref;
- evidence count and source-boundary preservation.

The schema v5 `vague_cue_candidate_funnel` fixture also reports:

- `core_candidate_count`
- `sentinel_candidate_count`
- `verifier_pool_size`
- `source_ref_rejoin_rate`
- `sentinel_source_ref_coverage_rate`
- `golden_association_rescued_by_sentinel_count`
- `sentinel_false_positive_rate`
- `wrong_route_drag_from_sentinel_count`
- `frontier_marker_helpfulness_rate`
- `intersection_bridge_lift`

The aggregate fixture run updated on 2026-06-09 showed:

- direct search: source-backed success on all 4 cases, but with manual query
  invention in the vague cases (`avg_manual_query_invention_count=1.5`);
- hook-only: no source-backed success, one scent-as-fact violation fixture, and
  one wrong-route drag fixture;
- progressive recall: actionable `recall_deepen` route on all 4 cases,
  source-backed success on the 3 non-stale cases,
  eligible `source_reopen_follow_through_rate=1.0` across the 3 eligible
  source-reopen cases, plus `source_reopen_fail_closed_count=1` with
  `failure_class=stale_handle_rejected_before_source_use` for the deterministic
  stale-handle rejection before source use.
- foreground lift: first turn emitted a navigation-only `scent` route under a
  simulated semantic timeout with `evidence_count=0`; second turn reused the
  ambient cache with `cache_status=hit`; the packet candidate ref reopened the
  expected fixture source with `manual_query_invention_count=0`; the source
  boundary stayed intact.
- vague-cue candidate funnel: 4 core candidates plus 2 sentinel candidates
  formed a 6-item verifier pool; all candidates rejoined to source refs
  (`source_ref_rejoin_rate=1.0`), sentinel coverage was 1.0, one
  cross-vocabulary association was rescued by a sentinel candidate, and
  sentinel wrong-route drag stayed at 0.

## #201 Readout

For #201, this smoke now measures five deterministic proxy outcomes:

- `route_actionability_rate`
- `source_reopen_follow_through_rate`
- `source_reopen_follow_through_eligible_count`
- `source_reopen_fail_closed_count`
- `source_reopen_failure_classes`
- `default_foreground_first_turn_lift`
- `default_foreground_second_turn_lift`
- `foreground_source_reopen_follow_through`
- `vague_cue_candidate_funnel_measured`

The foreground fields are narrow fixture readouts. First turn means the prompt
hook can still deliver a local route when semantic provider work times out.
Second turn means the next prompt can reuse the temporary ambient cache instead
of staying purely first-turn cold.
Foreground source reopen means a simulated agent consumes the foreground
packet's candidate ref and reopens the fixture source without inventing fresh
grep/search terms. It does not mean hook scent is source evidence.

The report intentionally keeps this #201 outcome as not measured:

- live registry quality.

So this evidence can support a narrow route/cache-delivery slice, but it is not
a #201 closeout signal.

## #281 / #309 / #248 Readout

For #281, this smoke measures whether fresh-thread multilingual vague cues can
enter a small source-joined sentinel pool without becoming source-backed facts.
It does not measure live fresh-thread quality.

For #309, this smoke measures the source-joined core/sentinel verifier-pool
shape requested for cross-vocabulary and frontier-like cues:

- `core_candidate_count=4`
- `sentinel_candidate_count=2`
- `verifier_pool_size=6`
- `golden_association_rescued_by_sentinel_count=1`
- `sentinel_false_positive_rate=0.0`
- `wrong_route_drag_from_sentinel_count=0`

For #248, this smoke measures source-ref rejoin coverage on the same verifier
pool while keeping `default_prefilter_adoption=not_enabled`. It is not
answer-quality calibration and does not enable the optional question/vector
prefilter by default.

## Can Claim

- The progressive navigation MCP path can be compared against direct search and
  hook-only behavior on public synthetic clean-source fixtures.
- The smoke exercises a vague source-backed deepening case, multilingual vague
  cue cases, and a stale-handle negative case.
- The foreground fixture exercises semantic-timeout-but-route-available and
  next-turn cache reuse without external model calls.
- A foreground packet candidate ref can be consumed to reopen the expected
  fixture source with zero manual query invention.
- A source-joined core/sentinel verifier pool can be reported for vague
  multilingual cues without promoting candidates to evidence or enabling a
  default prefilter.
- The comparison keeps hook scent, route handles, and report metrics as
  navigation/evidence diagnostics, not factual memory claims.

## Cannot Claim

- Live user quality improvement.
- Live token, tool-call, or wall-clock reduction.
- Broad default foreground lift on live registries.
- Production selector superiority over direct search.
- Default vector or question-prefilter safety.
- Answer-quality lift from sentinel candidates.
- Large-sample statistical significance.
- That hook-only behavior is unsafe in all real settings; the hook-only arm is a
  boundary fixture, not a live-agent study.

Use this smoke as deterministic contract evidence for #465 and as a narrow #201
route-actionability/source-reopen/foreground-cache proxy. Stronger user-facing
claims still need live or replay evaluations with real agent behavior and
sanitized cost traces.
