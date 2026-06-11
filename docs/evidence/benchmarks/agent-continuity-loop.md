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

Report shape:

- `measured_result`: the compact positive result string.
- `supports`: what the measured public-safe fixture actually supports.
- `material_limits`: short limits that prevent likely over-reading.
- `cannot_claim`: legacy compatibility field kept short; prefer
  `material_limits` for new reader-facing prose.

## What It Exercises

- semantic warm route material projected into attention route tokens;
- hot-router output for `bounded_summary_as_route`, `reopenable_route`,
  `direction_only`, and hard-mask `silence`;
- agent-native foreground `MemoryPacket` compression;
- safe `route_label` / `display_hint` triage previews for similar
  reopenable routes;
- explicit `deepen` / `explain` surfaces for source routes and blocked routes;
- AIppo low-risk working-contract activation;
- source-reopen and foreground packet budgets in the same report;
- anti-nag suppression for a recently dismissed route.

## 2026-06-11 Public Fixture Result

The checked-in fixture cohort covers eight cases:

- positive bounded-summary route;
- positive reopenable source route;
- two similar packet-triage reopenable routes with distinct safe labels;
- AIppo low-risk workflow guidance;
- blocked privacy route;
- stale/conflicted reopen route;
- anti-nag recently dismissed route.

Current deterministic result:

- `integrated_loop_case_count = 8`
- `integrated_loop_success_count = 8`
- `deepen_required_follow_through_count = 7`
- `aippo_low_risk_guidance_success_count = 1`
- `anti_nag_suppressed_count = 1`
- `packet_triage_distinctiveness = 1.0`
- `blind_deepen_required_count = 0`
- `top_route_selection_hint_present_count = 5`
- `stale_conflict_preview_requires_reopen_count = 1`
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
- `blind_deepen_required_count`
- `packet_triage_collision_count`

## Claim Shape

Measured result: 8/8 public-safe agent-continuity fixture cases pass, all
red-line counters are 0, `packet_triage_distinctiveness = 1.0`, and
`blind_deepen_required_count = 0`.

Supports: semantic warming, hot-router packets, agent-native facade/deepen,
AIppo guidance, source-reopen budget, and foreground budget compose on the
checked-in public-safe fixtures. Multiple similar reopenable route packets now
carry distinct safe triage hints instead of forcing blind deepen.

Material limits: this is still a deterministic contract fixture, not
private-history or live-host lift evidence; it measures route/deepen/facade
composition, not answer-generation or external-model quality; opt-in/default
foreground adoption remains a separate runtime decision.
