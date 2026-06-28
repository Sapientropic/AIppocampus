# Recall Navigation Reports

Role: dated recall-navigation and attention-router report router.
Status: report layer; current claim boundaries live in
[`../../../current-claims.md`](../../../current-claims.md).

Use this folder for reports about active recall routing, attention navigation,
score fusion, continuity-loop integration, default-hook recall usefulness,
cognitive-load default-path behavior, and recall degradation. These reports are
evidence provenance; the current runner map lives in
[`../../../benchmark-evidence-map.md`](../../../benchmark-evidence-map.md).

## Current State

- Recommended default explicit path: `aippocampus agent recall ... --json`,
  then `aippocampus agent deepen --request N --last-recall --json`.
- Optional attention-auto path: use only the explicit-pull attention-router
  cohort named in [`../../../current-claims.md`](../../../current-claims.md).
- Default hook full foreground: still diagnostic-only; do not enable it by
  documentation alone.
- Tiny hook-to-agent affordance: safer action-only candidate when it only tells
  the host to call `agent_recall`, not when it acts as source evidence.
- Activation dogfood usefulness: bounded replay evidence shows warm replay
  signals can reduce manual search and route drag, but this is not live default
  foreground or Dream promotion evidence.
- Source-joined/text-first remains the default decision boundary before quoting
  exact, stale, sensitive, or disputed claims.
- Current owners: default-hook adoption boundaries are in
  [`default-hook-recall-usefulness-2026-06-20.md`](default-hook-recall-usefulness-2026-06-20.md)
  and #2397; broader runner routing stays in
  [`../../../benchmark-evidence-map.md`](../../../benchmark-evidence-map.md).

## Reports

| Report | Boundary |
| --- | --- |
| [`agent-continuity-loop.md`](agent-continuity-loop.md) | Agent continuity integration gate report. |
| [`activation-dogfood-usefulness-2026-06-28.md`](activation-dogfood-usefulness-2026-06-28.md) | Bounded dogfood/replay activation usefulness probe; reduces manual search and route drag without promoting live defaults. |
| [`attention-navigation-quality.md`](attention-navigation-quality.md) | Public-safe attention navigation quality gate. |
| [`attention-score-fusion-calibration.md`](attention-score-fusion-calibration.md) | Score-fusion calibration/adoption report. |
| [`cognitive-load-default-path-usefulness-2026-06-14.md`](cognitive-load-default-path-usefulness-2026-06-14.md) | Public-safe default-path cognitive-load replay; diagnostic-only maturity. |
| [`cjk-local-recall-fixture-report.md`](cjk-local-recall-fixture-report.md) | CJK local recall fixture report. |
| [`default-hook-recall-usefulness-2026-06-20.md`](default-hook-recall-usefulness-2026-06-20.md) | Same-budget default-hook recall benchmark plus host-faithful tiny `agent_recall` replay; keeps full default foreground diagnostic-only. |
| [`recall-degradation-audit.md`](recall-degradation-audit.md) | Recall degradation audit report. |
| [`recall-navigation-comparison-2026-06-03.md`](recall-navigation-comparison-2026-06-03.md) | Recall navigation comparison smoke. |
| [`source-joined-routing-decision-2026-06-14.md`](source-joined-routing-decision-2026-06-14.md) | Consumer decision for source-joined routing and post-source-join score fusion. |
