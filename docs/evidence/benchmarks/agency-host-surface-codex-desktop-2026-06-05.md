# Codex Desktop Agency Host Surface Evidence - 2026-06-05

This public-safe evidence slice records the #763 host-surface validation step
for agency affordance tickets. It extends the earlier #312 deterministic
replay by naming one host surface and adding a host-faithful timing and feedback
ledger contract.

## Named Surface

- Surface: `codex-desktop-hidden-route-lifecycle`
- Host: Codex Desktop
- Timing model: hidden-route lifecycle
- Host-supplied runtime inputs: task phase, current user action, visible source
  refs, surface history, and feedback history.

## Command

```powershell
python tools\aippocampus\smoke\smoke_agency_host_timing.py --json
```

## Result

- Status: passed.
- Cases: 5.
- Decisions: 1 show, 1 hold, 3 suppress.
- Reasons: actionable host moment, task phase not actionable, source visible,
  duplicate surface history, and recent negative feedback.
- Feedback ledger rows: 3 public-safe rows for accepted/useful/low-annoyance,
  dismissed/not-useful/medium-annoyance, and corrected/prevented-repeat/high
  annoyance.
- Privacy boundary: no raw source text, raw feedback text, local paths, private
  thread ids, or credentials serialized.

## Can Claim

- One named Codex Desktop host surface is documented for agency affordance
  tickets.
- The smoke covers show, hold, source-visible suppression, same-surface
  duplicate suppression, and recent negative-feedback suppression under a
  host-faithful timing model.
- The feedback ledger contract can record bounded usefulness, annoyance,
  dismissal, and later-correction signals without changing source truth.

## Cannot Claim

- Live delivered host timing.
- Real user-visible usefulness or annoyance lift.
- Autonomous push-forward behavior.
- Cross-host production duplicate suppression.
- Source truth changes from feedback ledger rows.

## Interpretation

This is enough to close #763's named-host-surface validation gap as a
host-faithful replay slice. It should not be used as evidence that live Codex
Desktop users saw better timing or less annoyance. Any future live-host claim
needs a separate opt-in delivered/control or host telemetry run.
