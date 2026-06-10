# Field Continuity Fixture Report

Status: implemented public-safe contract-smoke fixture for GitHub #454, with
the GitHub #982 Field Continuity Eval design/runner contract and a bounded
public-safe quality-proxy readout for GitHub #281.

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
wrong-family persistence, and stale-route dominance. The eval design lives in
[`field-continuity-eval-design.md`](field-continuity-eval-design.md); this
report records the concrete fixture/runner boundary.

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

- `abstains_when_evidence_insufficient_rate`
- `source_reopen_success_rate`
- `progressive_route_recovery_rate`
- `external_state_overclaim_rate`
- `uncertainty_boundary_preserved_rate`
- `exact_prompt_or_tool_failure_recovery_rate`
- `completion_nuance_preserved_rate`
- `wrong_family_persistence_rate`
- `irrelevant_memory_drag_rate`
- `report_leakage_rate`
- `latency_budget_overrun_rate`
- `prompt_budget_overrun_rate`

The default top-level metrics describe the `active_recall_or_source_reopen`
arm. The JSON report also emits `metrics.by_arm` for `no_memory`, `fts_only`,
`summary_first`, `semantic_only`, `hook_only`,
`active_recall_or_source_reopen`, and `stale_wrong_route_control`. The active
arm is the only arm expected to preserve all boundaries in this deterministic
fixture. The other arms remain controls or baselines, not evidence that
hook-only, summary-first, semantic-only, or FTS-only continuity is sufficient.

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
`private_seed_review=contract_only`, and `closeout_eligible=false`. It remains
a supporting public fixture signal for #281, but it is not the closeout surface.
The 2026-06-10 `benchmark_fresh_thread_recall_demo.py` readout now owns #281's
public-fixture validation closeout. Neither readout proves real fresh-thread
quality or private-history recall quality.

## Command

```powershell
python benchmarks\aippocampus\benchmark_field_continuity.py --json
python -m unittest tests.aippocampus.test_benchmark_field_continuity
```

## Canonical Files

- Runner: `benchmarks/aippocampus/benchmark_field_continuity.py`
- Fixture: `benchmark_corpus/field_continuity/fixture.json`
- Mirror tests: `tests/aippocampus/test_benchmark_field_continuity.py`
- Eval design: `docs/evidence/benchmarks/field-continuity-eval-design.md`
- Field-report surface: `docs/evidence/magic-moments.md`
- Methodology owner:
  `docs/evidence/benchmarks/memory-decision-benchmark-plan.md`

## Cannot Claim

- real-history field-continuity recall quality
- universal fresh-thread recall quality
- private real-history quality for GitHub #281
- foreground-hook-only sufficiency
- live semantic-model quality
- broad FTS-only, summary-first, or semantic-only superiority
- hosted-service or cross-device production readiness
