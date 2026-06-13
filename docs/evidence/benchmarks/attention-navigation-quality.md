# Attention Navigation Quality

Role: public-safe diagnostic benchmark for #1111.

This benchmark evaluates the attention router as navigation, not answer
generation or broad memory QA. It aggregates existing public-safe fixtures for
the attention contract, route tokens/hot router, action-time head, and
source-window evidence packager.

Run:

```powershell
python benchmarks\aippocampus\benchmark_attention_navigation_quality.py --json
```

The report kind is `aippocampus_attention_navigation_quality`.

## What It Measures

- `route_precision_at_1`
- `route_recall_at_k`
- `source_reopen_success_rate`
- `wrong_source_evidence_rate`
- `false_preactivation_rate`

Hard red lines are separate from route averages:

- `privacy_bypass_count`
- `masked_source_resurrection_count`
- `source_backed_claim_without_reopen`
- `stale_as_current_count`
- `wrong_source_evidence_count`
- `conflict_missed_count`
- `manual_query_invention_count`
- `anti_nag_violation_count`
- `bounded_evidence_claim_violation_count`

Red-line counts must stay zero; a high average route rate cannot hide a red-line
failure.

## 2026-06-10 Public Fixture Result

The checked-in fixture cohort covers 12 cases across:

- positive source-backed routes;
- privacy hard masks;
- stale/currentness handling;
- conflict handling;
- action-time routing;
- anti-nag suppression;
- source-window to source-span packaging;
- wrong-source span rejection.

Current deterministic result:

- `route_precision_at_1 = 12/12 = 1.0`
- `route_recall_at_k = 9/9 = 1.0`
- `source_reopen_success_rate = 9/9 = 1.0`
- `wrong_source_evidence_rate = 0/1 = 0.0`
- `false_preactivation_rate = 0/3 = 0.0`
- all hard red lines `0`

Maturity metadata:

- `benchmark_maturity_level = contract_smoke`
- `contract_safety_gate_ok = true`
- `router_design_gate_ok = true`
- `public_quality_gate_ok = false`
- `default_adoption_gate_ok = false`
- `quality_gate_ok = false` as the backward-compatible public-quality alias,
  not a V0 design-failure verdict
- `minimum_family_case_floor = 30`
- `sample_floor_met = false`
- `next_promotion_target = public_cohort_candidate`

The contract gate says the selected navigation fixtures still protect the
declared red lines. It is not a public-quality cohort result until a later
public/external cohort, sample-floor, uncertainty, holdout, and no-tuning-leak
promotion explicitly passes.

## Public/Holdout Cohort Slice

The public-safe cohort runner is:

```powershell
python -c "import json, sys; sys.path.insert(0, 'benchmarks/aippocampus'); import benchmark_attention_navigation_quality as b; print(json.dumps(b.run_attention_navigation_public_holdout_cohort(), ensure_ascii=False, indent=2))"
```

It emits `aippocampus_attention_navigation_public_cohort` over synthetic/public
route packets across positive routes, hard masks, stale/currentness, conflict,
action-time cues, wrong-source controls, generic-hint specificity, anti-nag,
and multilingual alias routing. Each family has a development partition and a
holdout partition; `holdout_used_for_tuning_count` stays `0`.

This cohort can support the narrow explicit-pull auto gate for
`aippocampus agent recall --attention-router-mode auto`. It still cannot claim
live host behavior lift, answer quality, private-history quality, or default
foreground hook adoption.

## Boundaries

This benchmark does not evaluate answer-generation quality, private-history
behavior, live host behavior, default foreground-hook adoption, production
score-fusion calibration, or representative public router quality. It is a
public route-safety and navigation-quality gate around the deterministic router
policy adopted in #1230, and it can still feed #1102-style reliability readouts.
