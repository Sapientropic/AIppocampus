## What Changed

-

## Why

-

## Verification

- [ ] `python tools\aippocampus\test_plan.py --json`
- [ ] Planner-named static gates (`ruff check ...` and `mypy` when listed)
- [ ] Focused tests from the changed-surface planner
- [ ] `python tools\aippocampus\run_tests.py --tier pr` when the planner names it, CI is unavailable/stale, or runtime/plugin/skill surfaces changed
- [ ] Other:

## Privacy / Source Boundary

- [ ] No raw rollouts, private registry exports, local paths, credentials, or private conversation text are included.
- [ ] New source-backed claims point to docs, fixtures, reports, or tests.

## Foreground Usefulness / De-Armor Check

Use this only when the PR touches recall, orient, aippo, ambient, MCP compact,
hook, or foreground-action surfaces.

- Foreground usefulness delta:
- Load-bearing unknown:
- Smallest useful next action or reopen route:
- [ ] Added visible caveats, `cannot_claim`, or source-open pressure only where they answer a load-bearing risk.
- [ ] Compact/default output remains action-shaped; detailed diagnostics stay behind full/explain/deepen/operator views.

## Issue / Roadmap Link

Closes or relates to:

## Optional Benchmark / Readiness Closeout

Use this only for benchmark, readiness, public-claim, default-adoption, broad live/model-backed, AIppo/source-side/LongMemEval, or scale issues.

Closeout class:

- [ ] `complete`
- [ ] `complete_with_followups`
- [ ] `blocker_recorded`
- [ ] `narrow_slice_only`

Evidence level:

- `contract_fixture`, `scripted_proxy`, `model_pilot`, `behavior_run`, `scale_run`, or `default_adoption`

Benchmark/readiness boundary:

- [ ] Public benchmark/readiness claims lead with measured result, support, and material limits.
- [ ] Benchmark reports separate actual AIppocampus runtime capabilities from benchmark-local scaffolding or isolated experiments.
- [ ] AIppocampus orientation/deepen was used for broad recall/architecture/source-side work, or this PR explains why route context would not change the patch.

Runtime/default adoption evidence:

- Runtime/default policy change:
- Benchmark outcome card or gate:
- Non-benchmark rationale / override:

Remaining gap / follow-up issue:

## Notes For Reviewers

-
