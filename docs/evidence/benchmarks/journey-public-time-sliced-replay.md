# Journey Public Time-Sliced Replay

Status: public-safe deterministic fixture for #310.
Last checked: 2026-06-10.

This note records the public-reproducibility slice for Journey foreground hint
timing. It complements `docs/research/journey-tracking.md`; it does not replace
the Journey design memo.

## What It Measures

`build_public_time_sliced_journey_replay_report()` in
`aippocampus_runtime.journey.live` runs a replayable public-style cohort:

- source-backed `theme_candidate`, `question_candidate`, and `frontier_marker`
  rows visible before the replay horizon;
- one future row per case after the horizon that must not shape the earlier
  replay;
- one active-hint case;
- resolved-frontier, stale-frontier, and wrong-route suppression cases;
- source-visible, unrelated-prompt, and high-risk exact-claim negative controls.

The public report emits aggregate case metrics and hint decisions only. It does
not serialize raw row text, source refs, message ids, future rows, or private
route handles.

## Current Result

Local run on 2026-06-10:

- `case_count=4`;
- `journey_created_count=4`;
- taxonomy case counts:
  - `active_hint=1`;
  - `resolved_frontier=1`;
  - `stale_frontier_demotion=1`;
  - `wrong_route_suppression=1`;
- `future_row_excluded_count=4`;
- `positive_hint_count=1`;
- `negative_control_suppressed_count=12`;
- `expected_relevant_decision_pass_count=4`;
- `false_foreground_hint_count=0`;
- `future_leakage_count=0`.

## Verification

Run the focused regression:

```powershell
python -m pytest tests\aippocampus\test_journey_tracking.py::JourneyTrackingTests::test_public_time_sliced_journey_replay_report_keeps_public_boundary -q
```

Broader local validation for the landing PR also ran the full Journey test file,
Ruff, mypy on the touched files, docs health, and the repository PR tier.

## Claim Shape

Supports: the checked Journey replay helper
can build no-write time-sliced candidates from replayable public-style rows,
exclude future rows before the horizon, keep an active Journey hint
navigation-only, and suppress resolved, stale, wrong-route, source-visible,
unrelated, and high-risk exact-claim controls without public leakage of raw
source material.

Important limits: no private real-history Journey quality, live host timing
quality, default foreground usefulness, user-visible recall lift, future-state
prediction, or source evidence without reopen.
