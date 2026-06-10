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

## Boundaries

This benchmark does not evaluate answer-generation quality, private-history
behavior, live host behavior, default foreground adoption, or calibrated score
fusion. It is a public route-safety and navigation-quality gate that can feed
future #1112 score-fusion calibration and #1102-style reliability readouts.
