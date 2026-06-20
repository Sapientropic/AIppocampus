# Default-Hook Recall Usefulness - 2026-06-20

This report updates the #1439/#1449 default-hook benchmark after #2397. The
full default foreground packet path remains diagnostic-only, while the tiny
`suggested_agent_action=agent_recall` affordance now has a host-faithful replay
readout instead of relying only on proxy-derived follow-through.

Machine-readable output:
[`default-hook-recall-usefulness-2026-06-20.json`](default-hook-recall-usefulness-2026-06-20.json).

## Command

```powershell
python benchmarks\aippocampus\benchmark_default_hook_recall_usefulness.py --json --output docs\evidence\benchmarks\reports\recall-navigation\default-hook-recall-usefulness-2026-06-20.json
```

## Decision

| Surface | Decision | Why |
| --- | --- | --- |
| `default_hook_foreground_candidate` | keep diagnostic-only | `wrong_route_drag_count=4`, `irrelevant_memory_drag_count=3`, and helpfulness remains below explicit recall. |
| `default_hook_tiny_agent_recall_affordance` | action-only runtime-policy candidate | Host-faithful replay follows `agent_recall` for all emitted hints and keeps source truth out of the hook packet. |
| `explicit_recall_same_budget` | useful opt-in path | Same-budget explicit recall still avoids wrong-route and irrelevant-memory drag on this cohort. |

The full foreground candidate is not a runtime path from this slice. The tiny
affordance is eligible only as an action hint, not as foreground evidence.

## Tiny Affordance Replay

Host-faithful replay result:

- `affordance_emitted_count=7`
- `host_followed_action_count=7`
- `agent_recall_call_count=7`
- `recall_after_hint_success_count=7`
- `source_truth_from_affordance_count=0`
- `raw_handle_or_provenance_dump_count=0`
- `broad_manual_search_before_recall_count=0`
- `wrong_route_drag_count=0`
- `irrelevant_memory_drag_count=0`

The retained proxy arm still exists for comparison, but the tiny-affordance
decision now uses the host-faithful replay gate.

## Regression Coverage

The public fixture covers stale/conflict route drag, stale theme carryover,
cognitive-load irrelevant drag, generic attention-route specificity, deictic
quiet cases, multilingual prompts, prompt-hook skip/no-memory, question
resurfacing, and theme user-review lift.

## Boundary

This report does not claim live default-hook quality, live tiny-affordance
quality, broad private-history question quality, source truth from hook packets,
or default foreground adoption readiness.
