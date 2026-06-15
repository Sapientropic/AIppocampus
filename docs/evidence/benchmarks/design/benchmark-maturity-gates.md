# Benchmark Maturity And Sample-Size Gates

Role: canonical policy for #1165 benchmark maturity and promotion metadata.

Small deterministic fixtures are valuable because they catch red-line failures
early: privacy bypass, source-free claims, stale-as-current, wrong-route
revival, summary-as-truth, and foreground provenance leaks. They are not, by
themselves, representative public-quality evidence. Reports should make both
truths visible.

## Maturity Ladder

| Level | Meaning | Can support | Cannot support by itself |
| --- | --- | --- | --- |
| `contract_smoke` | Small deterministic contract or regression fixture. | Schema shape, red-line behavior, local-safe regression guard. | Representative public quality, live lift, competitor comparison. |
| `diagnostic_proxy` | Named failure families with uncertainty metadata. | Root-cause or calibration direction. | Population-quality claim or final launch proof. |
| `public_cohort_candidate` | Public/replayable cases with source-safe reports and planned floors. | Candidate cohort design and early public reproducibility. | Final cohort quality until floors and holdout rules pass. |
| `public_cohort` | Public/replayable cohort with family floors, negative controls, and uncertainty reporting. | Bounded public cohort quality for the declared surface. | Private-history or live-host quality. |
| `holdout_quality` | Held-out or externally derived cases excluded from tuning. | Stronger public quality evidence for that surface. | SOTA or market superiority without an external comparison protocol. |

## Required Report Metadata

Use `benchmarks/aippocampus/shared/benchmark_maturity.py` when a runner can emit the
shared fields directly. Otherwise mirror the same shape in the report owner.

Required fields:

- `benchmark_maturity_level`
- `case_count`
- `failure_family_count`
- `per_family_case_counts`
- `minimum_family_case_floor`
- `sample_floor_met`
- `external_or_public_cohort_case_count`
- `holdout_case_count`
- `holdout_used_for_tuning_count`
- `wilson_or_uncertainty_reported`
- `contract_gate_ok`
- `usefulness_gate_ok`
- `attention_cost_ok`
- `quality_gate_ok`
- `cannot_claim_due_to_sample_size`
- `next_promotion_target`

`contract_gate_ok=true` means the local fixture contract passed. It must not be
read as `quality_gate_ok=true` unless the report also meets its maturity,
sample-floor, public/external cohort, holdout, and no-tuning-leakage checks.

Red-line counters stay separate from aggregate rates. Passing all red lines is
necessary for promotion, but it is not sufficient evidence of public cohort
quality.

Usefulness and attention cost are separate promotion gates. A report can pass
privacy/source red lines and still leave `quality_gate_ok=false` if foreground
packets are too noisy, indistinct, over-filtered, or expensive for the user or
agent attention they save.

## Gate Vocabulary

Use the narrowest gate name that matches the evidence:

- `contract_gate_ok`: the deterministic report or safety contract ran within
  its declared scope.
- `diagnostic_gate_ok`: a local diagnostic threshold passed; this is useful
  signal, not public/product quality.
- `public_quality_gate_ok`: a public or external cohort passed with explicit
  denominator, rate, sample/family floor, and holdout/no-tuning metadata where
  applicable.
- `claim_quality_ok`: the report is safe to cite as scoped quality evidence.
- `runtime_policy_adoption_gate_ok`: the evidence is strong enough to change
  a runtime/default policy.

Legacy `quality_gate_ok` must be accompanied by `quality_gate_kind` or
`quality_gate_ok_means`. Suite aggregation treats diagnostic or contract
success as bounded positive evidence, not as public-quality proof and not as an
ordinary product failure.

## Initial Fixture Annotations

| Surface | Current level | Current sample | Next promotion target | Why not public quality yet |
| --- | --- | --- | --- | --- |
| Attention navigation quality | `public_cohort` for the explicit agent-pull path; older `contract_smoke` retained as red-line smoke | 270 public-safe cases, 9 families, 90 holdout; plus 12 selected smoke cases | Default/live foreground adoption remains separate | Public/holdout gate now passes for explicit agent pull; it still does not claim live host behavior or default foreground-hook adoption. |
| Map-rot lifecycle-debt | `contract_smoke` | 9 selected lifecycle-state cases with no-write maintenance actions | `public_cohort_candidate` | Exercises state taxonomy, red lines, and bounded operator actions, not real map-rot distribution or completed cleanup. |
| Agent continuity loop | `contract_smoke` | 8 selected integration cases | `public_cohort_candidate` | Proves composition behavior, not live host or private-history usefulness. |
| Dream public shadow | `contract_smoke` | 4 synthetic public behavior cases | `public_cohort_candidate` | Useful falsifiable behavior smoke, but too small for broad Dream quality. |

## #1195 Candidate-Family Decision

The first public cohort candidate families are now recorded by
[`benchmark-family-promotion-candidates-2026-06-12.md`](../reports/benchmark-family/benchmark-family-promotion-candidates-2026-06-12.md)
and generated by
`benchmarks/aippocampus/benchmark_family_promotion_candidates.py`.

Selected families:

- Agent continuity loop / recall degradation.
- Attention navigation quality.
- Map-rot lifecycle debt.

The report uses `benchmark_maturity.py`-shaped target metadata for sample
floors, family distribution, holdout/no-tuning leakage, uncertainty policy,
sanitization, and gate separation. The target counts are not observed scores:
`contract_gate_ok` can remain true while `usefulness_gate_ok=false` and
`quality_gate_ok=false`.

E2E50 remains with #279 because it needs behavior-pack / compaction ownership
and ablation arms. The rollout hard-event V2 cohort can seed agent-continuity
cases, but it is not by itself the #1195 promotion decision.

## Promotion Notes

Promotion should be explicit and boring:

- define the public/external cohort source and source-safety boundary;
- set per-family floors before tuning;
- keep negative controls and no-remember / stale controls visible;
- keep holdout cases out of prompt, threshold, or fixture tuning;
- report Wilson or another uncertainty measure for rates;
- leave `quality_gate_ok=false` when floors, holdout, no-leakage,
  usefulness, or attention-cost checks fail.

Do not use Wilson intervals to make selected or author-written cases
representative. Uncertainty reporting describes the observed cohort only; it
does not fix sampling bias.
