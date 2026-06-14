# Default-Hook Recall Usefulness - 2026-06-14

This public-safe benchmark closes #1439 by testing default-hook / foreground
recall before adoption. The measured decision is negative: keep the default hook
diagnostic-only for this slice.

## Command

```powershell
python benchmarks\aippocampus\benchmark_default_hook_recall_usefulness.py `
  --json `
  --output docs\evidence\benchmarks\default-hook-recall-usefulness-2026-06-14.json
```

Focused verification:

```powershell
python -m pytest tests\aippocampus\test_benchmark_default_hook_recall_usefulness.py -q
```

## Arms

The cohort compares three arms under the same packet and source-reopen budget:

- `default_no_packet_baseline`
- `explicit_recall_same_budget`
- `default_hook_foreground_candidate`

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

| Metric | Baseline | Explicit Recall | Default-Hook Candidate |
|---|---:|---:|---:|
| Activation rate | 0.0 | 0.909091 | 0.727273 |
| Helpful next-action rate | 0.0 | 0.636364 | 0.272727 |
| Manual-search reduction vs baseline | 0 | 11 | 5 |
| Source-reopen follow-through rate | 0.0 | 0.636364 | 0.272727 |
| Wrong-route drag rate | 0.0 | 0.0 | 0.363636 |
| Irrelevant-memory drag rate | 0.0 | 0.0 | 0.272727 |
| Latency proxy avg | 0.0 | 40.0 | 15.363636 |
| Cost proxy avg | 0.0 | 0.909091 | 0.727273 |
| Quiet-for-a-reason count | 2 | 4 | 2 |

Prompt-hook gap addendum from the latest issue comment:

- explicit recall reopenable route count: `1`
- default-hook `skip/no_memory` count: `1`
- explicit-route / hook-skip gap count: `1`
- tiny `agent_recall` affordance candidate count: `1`

Decision:

- `default_hook_foreground_candidate`: keep diagnostic-only.
- `explicit_recall_same_budget`: remains the useful opt-in path.
- A tiny `agent_recall` affordance is a candidate for opt-in review only, not
  evidence for default foreground adoption.
- `question_tracking_theme_rows`, `cognitive_load_sidecar`, and
  `attention_router_default_hook_candidate`: remain opt-in or diagnostic-only.
- No surface is eligible for default foreground from this slice.

## Can Claim

- A same-budget three-arm default-hook recall usefulness benchmark exists for
  #1439.
- Explicit recall improves selected public synthetic cases over the no-packet
  baseline.
- The explicit-route / default-hook-skip gap is measured separately from
  broader default-hook adoption.
- The default-hook candidate has some wins but also enough wrong-route and
  irrelevant-memory drag to block default foreground adoption.
- The question/theme gap is measured separately from source truth.

## Cannot Claim

- Live default-hook quality.
- Default foreground adoption readiness.
- Broad private-history question/theme usefulness.
- Theme rows as source truth.
- Cognitive-load default foreground readiness.
- Tiny `agent_recall` affordance readiness for default foreground.

## Public Boundary

The committed report uses synthetic case identifiers and aggregate metrics. It
does not serialize raw prompts, raw source text, source refs, thread/message
handles, local paths, provider payloads, credentials, or private-history rows.
