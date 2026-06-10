# Agent Continuity Loop Gate

Role: public-safe deterministic integration gate for #1163.

This benchmark checks that the current continuity-routing pieces compose
without turning navigation signals into facts. It uses checked-in fixture rows
only: no private history, no live host, and no external model call.

Run:

```powershell
python benchmarks\aippocampus\benchmark_agent_continuity_loop.py --json
```

The report kind is `aippocampus_agent_continuity_loop_fixture`.

## What It Exercises

- semantic warm route material projected into attention route tokens;
- hot-router output for `bounded_summary_as_route`, `reopenable_route`,
  `direction_only`, and hard-mask `silence`;
- agent-native foreground `MemoryPacket` compression;
- explicit `deepen` / `explain` surfaces for source routes and blocked routes;
- AIppo low-risk working-contract activation;
- source-reopen and foreground packet budgets in the same report;
- anti-nag suppression for a recently dismissed route.

## 2026-06-10 Public Fixture Result

The checked-in fixture cohort covers six cases:

- positive bounded-summary route;
- positive reopenable source route;
- AIppo low-risk workflow guidance;
- blocked privacy route;
- stale/conflicted reopen route;
- anti-nag recently dismissed route.

Current deterministic result:

- `integrated_loop_case_count = 6`
- `integrated_loop_success_count = 6`
- `deepen_required_follow_through_count = 5`
- `aippo_low_risk_guidance_success_count = 1`
- `anti_nag_suppressed_count = 1`
- `agent_packet_budget_violation_count = 0`
- `foreground_forbidden_key_count = 0`
- all red-line counters `0`

Maturity metadata:

- `benchmark_maturity_level = contract_smoke`
- `contract_gate_ok = true`
- `quality_gate_ok = false`
- `minimum_family_case_floor = 30`
- `sample_floor_met = false`
- `next_promotion_target = public_cohort_candidate`

The contract gate says the currently checked integration loop still composes
without red-line drift. It is not representative public-quality evidence until
a later public/external cohort, sample-floor, uncertainty, holdout, and
no-tuning-leak promotion explicitly passes.

Red lines are separate from success counts:

- `privacy_bypass_count`
- `masked_source_resurrection_count`
- `source_backed_claim_without_reopen`
- `stale_as_current_count`
- `foreground_forbidden_key_leak`
- `semantic_route_used_as_truth_count`
- `feedback_promoted_without_source`
- `anti_nag_violation_count`

## Boundaries

Passing this gate supports only the narrow claim that the public-safe semantic
warming, hot-router, facade, AIppo, source-reopen, and foreground-budget
contracts compose without obvious red-line drift.

It does not evaluate live host behavior lift, private-history quality,
answer-generation quality, default foreground adoption, public benchmark
quality lift, or external model quality.
