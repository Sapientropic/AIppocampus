# Field Continuity Fixture Report

Status: implemented public-safe contract-smoke fixture for GitHub #454, with
a bounded public-safe quality-proxy readout for GitHub #281.

This report records the narrow evidence boundary for
`benchmarks/aippocampus/benchmark_field_continuity.py`. The runner turns the
second-user magic-moment reports in
[Discussion #428](https://github.com/Sapientropic/AIppocampus/discussions/428)
into reproducible scenario-family contracts, negative controls, and sanitized
metric labels. The field reports are benchmark seeds, not official product
proof by themselves.

## What It Covers

- fresh/projectless familiarity with source-reopen and uncertainty boundaries
- multilingual vague recall with correction-aware route switching
- external-state restraint, separating local tool evidence from live external
  account truth
- very long same-thread fuzzy self-reference with completion nuance preserved
- cross-thread prompt/tool-failure provenance without publishing raw prompt or
  raw error text

The default fixture includes one public-safe synthetic row for each scenario
family. It also includes negative controls for overclaiming,
wrong-family persistence, and stale-route dominance.

## Private Seed Reporting

Private real-history seed runs must stay outside git. Public or shared reports
may include only aggregate rows with these fields:

- `seed_hash_sha256`
- `case_family`
- `source_kind`
- `date_bucket`
- `scenario_tags`
- `arm`
- `metric_key`
- `metric_value`
- `denominator`
- `cannot_claim`

They must not include raw prompts, source snippets, local paths, rollout ids,
thread ids, session ids, credentials, cookies, or raw tool-error text.

## Metrics

The contract exposes the issue #454 metric names without claiming live quality:

- `source_reopen_success_rate`
- `progressive_route_recovery_rate`
- `external_state_overclaim_rate`
- `uncertainty_boundary_preserved_rate`
- `exact_prompt_or_tool_failure_recovery_rate`
- `completion_nuance_preserved_rate`
- `wrong_family_persistence_rate`
- `irrelevant_memory_drag_rate`

The `active_recall_or_source_reopen` arm is the only arm expected to preserve
all boundaries in this deterministic fixture. `hook_only` and
`stale_wrong_route_control` remain controls, not evidence that hook-only
continuity is sufficient.

## GitHub #281 Readout

The benchmark report includes `issue_readouts.github_281` as a public-safe
fixture-quality proxy for fresh-thread progressive associative recall. It maps
the `fresh_projectless_familiarity` family and existing field-continuity
metrics into a small issue-local readout:

- `field_continuity_quality_proxy_measured`
- `fresh_projectless_familiarity_status`
- `source_reopen_success_rate`
- `progressive_route_recovery_rate`
- `wrong_family_persistence_rate`
- `irrelevant_memory_drag_rate`

This readout deliberately reports `live_fresh_thread_quality=not_measured`,
`private_real_history_quality=not_measured`,
`private_seed_review=contract_only`, and `closeout_eligible=false`. It helps
continue #281 with a reproducible public fixture signal, but it does not prove
real fresh-thread quality, private-history recall quality, or close the issue.

## Command

```powershell
python benchmarks\aippocampus\benchmark_field_continuity.py --json
python -m unittest tests.aippocampus.test_benchmark_field_continuity
```

## Canonical Files

- Runner: `benchmarks/aippocampus/benchmark_field_continuity.py`
- Fixture: `benchmark_corpus/field_continuity/fixture.json`
- Mirror tests: `tests/aippocampus/test_benchmark_field_continuity.py`
- Field-report surface: `docs/evidence/magic-moments.md`
- Methodology owner:
  `docs/evidence/benchmarks/memory-decision-benchmark-plan.md`

## Cannot Claim

- real-history field-continuity recall quality
- universal fresh-thread recall quality
- private real-history quality for GitHub #281
- foreground-hook-only sufficiency
- live semantic-model quality
- hosted-service or cross-device production readiness
