# Journey Public Time-Sliced Replay

Status: public-safe deterministic fixture for #310.
Last checked: 2026-06-10.

This note records the public-reproducibility slice for Journey foreground hint
timing. It complements `docs/research/journey-tracking.md`; it does not replace
the Journey design memo.

## What It Measures

`build_public_time_sliced_journey_replay_report()` in
`aippocampus_runtime.journey.live` runs a replayable public-style VCS hard-event
window:

- source-backed `theme_candidate`, `question_candidate`, and `frontier_marker`
  rows visible before the replay horizon;
- one future row after the horizon that must not shape the earlier replay;
- a relevant-prompt hint case;
- source-visible and unrelated-prompt negative controls.

The public report emits aggregate case metrics and hint decisions only. It does
not serialize raw row text, source refs, message ids, future rows, or private
route handles.

## Current Result

Local run on 2026-06-10:

- `case_count=1`;
- `journey_created_count=1`;
- `included_live_row_count=3`;
- `future_row_excluded_count=1`;
- `positive_hint_count=1`;
- `negative_control_suppressed_count=2`;
- `future_leakage_count=0`.

## Verification

Run the focused regression:

```powershell
python -m pytest tests\aippocampus\test_journey_tracking.py::JourneyTrackingTests::test_public_time_sliced_journey_replay_report_keeps_public_boundary -q
```

Broader local validation for the landing PR also ran the full Journey test file,
Ruff, mypy on the touched files, docs health, and the repository PR tier.

## Claim Boundary

This fixture supports a narrow public claim: the checked Journey replay helper
can build a no-write time-sliced candidate from replayable public-style rows,
exclude future rows before the horizon, and keep foreground hints navigation-only
with no public leakage of raw source material.

It cannot claim private real-history Journey quality, live host timing quality,
default foreground usefulness, user-visible recall lift, future-state
prediction, or source evidence without reopen.
