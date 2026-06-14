# Default-Hook Recall Usefulness - 2026-06-14

This public-safe benchmark closes #1439 by testing default-hook / foreground
recall before adoption, and addresses #1449 by separating the tiny
hook-to-agent affordance from foreground context injection. The measured
decision remains negative for default foreground adoption, but the tiny
`not evidence` action hint passes this fixture gate.

## Command

```powershell
python benchmarks\aippocampus\benchmark_default_hook_recall_usefulness.py `
  --json `
  --output docs\evidence\benchmarks\reports\recall-navigation\default-hook-recall-usefulness-2026-06-14.json
```

Focused verification:

```powershell
python -m pytest tests\aippocampus\test_benchmark_default_hook_recall_usefulness.py -q
```

## Arms

The cohort compares four arms under the same packet and source-reopen budget:

- `default_no_packet_baseline`
- `explicit_recall_same_budget`
- `default_hook_foreground_candidate`
- `default_hook_tiny_agent_recall_affordance`

## Cohort

The replayable public cohort covers deictic prompts, multilingual prompts,
already-good no-op cases, stale/conflict controls, question resurfacing, theme
user-review lift, stale theme carryover, cognitive-load drag, attention-route
specificity, and a self-referential continuity case where explicit recall
returns a reopenable route while the default hook reports `skip/no_memory`.

The question/theme slice also covers the #248 gap: question resurfacing,
theme-resonance with user review, stale theme carryover, wrong-route drag, and
source-truth overclaim blocking.

## Result

| Metric | Baseline | Explicit Recall | Default-Hook Candidate | Tiny Affordance |
|---|---:|---:|---:|---:|
| Activation rate | 0.0 | 0.909091 | 0.727273 | 0.636364 |
| Helpful next-action rate | 0.0 | 0.636364 | 0.272727 | 0.636364 |
| Manual-search reduction vs baseline | 0 | 11 | 5 | 11 |
| Source-reopen follow-through rate | 0.0 | 0.636364 | 0.272727 | 0.636364 |
| Wrong-route drag rate | 0.0 | 0.0 | 0.363636 | 0.0 |
| Irrelevant-memory drag rate | 0.0 | 0.0 | 0.272727 | 0.0 |
| Latency proxy avg | 0.0 | 40.0 | 15.363636 | 9.454545 |
| Cost proxy avg | 0.0 | 0.909091 | 0.727273 | 0.636364 |
| Quiet-for-a-reason count | 2 | 4 | 2 | 4 |

Prompt-hook gap addendum from the latest issue comment:

- explicit recall reopenable route count: `1`
- default-hook `skip/no_memory` count: `1`
- explicit-route / hook-skip gap count: `1`
- tiny `agent_recall` affordance candidate count: `1`

Tiny hook-to-agent affordance readout:

- affordance emitted count: `7`
- agent followed `suggested_agent_action=agent_recall` count: `7`
- recall-after-hint success count: `7`
- manual-search reduction vs baseline: `11`
- wrong-route drag count: `0`
- irrelevant-memory drag count: `0`
- source-truth overclaim count: `0`
- quiet-for-a-reason count: `4`
- fixture gate passed: `true`

Decision:

- `default_hook_foreground_candidate`: keep diagnostic-only.
- `default_hook_tiny_agent_recall_affordance`: eligible for the default tiny
  `not evidence` action hint; not eligible as foreground evidence/context.
- `explicit_recall_same_budget`: remains the useful opt-in path.
- `question_tracking_theme_rows`, `cognitive_load_sidecar`, and
  `attention_router_default_hook_candidate`: remain opt-in or diagnostic-only.
- No surface is eligible for default foreground from this slice.

## Can Claim

- A same-budget four-arm default-hook recall usefulness benchmark exists for
  #1439 and #1449.
- Explicit recall improves selected public synthetic cases over the no-packet
  baseline.
- The explicit-route / default-hook-skip gap is measured separately from
  broader default-hook adoption.
- The default-hook candidate has some wins but also enough wrong-route and
  irrelevant-memory drag to block default foreground adoption.
- The tiny `agent_recall` affordance is measured separately as a `not evidence`
  action hint, with source reopen/deepen still owning claims.
- The question/theme gap is measured separately from source truth.

## Cannot Claim

- Live default-hook quality.
- Live tiny `agent_recall` affordance quality.
- Default foreground adoption readiness.
- Broad private-history question/theme usefulness.
- Theme rows as source truth.
- Cognitive-load default foreground readiness.
- Source claims from the tiny affordance without recall/deepen/source reopen.

## Public Boundary

The committed report uses synthetic case identifiers and aggregate metrics. It
does not serialize raw prompts, raw source text, source refs, thread/message
handles, local paths, provider payloads, credentials, or private-history rows.
