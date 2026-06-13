# Natural Handoff Usefulness Validation

This is the bounded public/synthetic validation report for #1384 under the
#1185 usefulness-first owner. It does not use private history and does not claim
broad default-session product lift.

Run:

```powershell
python benchmarks\aippocampus\benchmark_natural_handoff_usefulness.py --json
python -m unittest tests.aippocampus.test_benchmark_natural_handoff_usefulness -v
```

## What It Measures

The cohort separates three outcome classes:

- wins: compact actionable continuity packets that reduce foreground work;
- no-help: ambiguous prompts where the safe behavior is clarification rather
  than promotion;
- regressions: correct but noisy packets, safe routes demoted to scent, and
  stale-route drag before recall.

The runner reuses the canonical `continuity_usefulness` metric group, so safety,
usefulness, and attention cost remain separate gates.

## Current Public-Safe Readout

- case count: 6
- wins: 2
- no-help: 1
- regressions: 3
- provider calls: 0
- private history used: false
- raw source text emitted: false

This makes #1384 closeable as a bounded validation artifact. #1185 should remain
open until broader default-path/live-host evidence exists.

## Claim Boundary

Can claim:

- the bounded synthetic cohort records wins, no-help cases, and regressions;
- safe-but-noisy and demoted-route packets are blocked by usefulness gates;
- natural handoff and lightly cued multilingual continuity have replayable
  public-safe contract cases.

Cannot claim:

- broad default-session product lift;
- private-history user-visible lift;
- live hook activation rate;
- that every deictic prompt should trigger recall without clarification.
