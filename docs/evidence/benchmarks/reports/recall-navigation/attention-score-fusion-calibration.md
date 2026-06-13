# Attention Score-Fusion Calibration

Role: public-safe calibration and runtime-adoption contract for #1112 / #1230.

This benchmark evaluates score fusion over sanitized attention-router feature
rows exported from the #1111 Attention Navigation Quality fixture cohort. It
does not train on raw text, private history, or source contents.

Run:

```powershell
python benchmarks\aippocampus\benchmark_attention_score_fusion_calibration.py --json
```

The report kind is `aippocampus_attention_score_fusion_calibration`.

## Feature Boundary

Exported rows include only sanitized ids, fixture family, labels, packet
summaries, and audited numeric features such as:

- lexical / semantic / action / evidence-packaging head scores;
- scope, salience, currentness, conflict, risk, and abstention scores;
- source-handle presence;
- hard-mask count/pass flag;
- anti-nag, stale/currentness, conflict, and source-open flags.

Hard masks remain policy gates. Calibration may change route scores, but it
cannot learn around privacy masks, source-reopen requirements, or claim
permissions.

## 2026-06-11 Public Fixture Result

Input: 12 public-safe feature rows from
[`attention-navigation-quality.md`](attention-navigation-quality.md).

Current deterministic weights over the exported rows:

- `route_precision_at_threshold = 3/4 = 0.75`
- `anti_nag_violation_count = 1`

Selected calibrated rule-grid arm:

- `route_precision_at_threshold = 9/9 = 1.0`
- `route_recall_at_threshold = 9/9 = 1.0`
- `anti_nag_violation_count = 0`
- `privacy_bypass_count = 0`
- `hard_mask_override_count = 0`

Runtime default policy:

- `policy_name = calibrated_rule_grid_v1`
- `default_adoption = adopted_by_hot_router`
- `route_precision_at_threshold = 9/9 = 1.0`
- `route_recall_at_threshold = 9/9 = 1.0`
- all red lines remain `0`

The adopted runtime policy adds explicit source-handle support,
evidence-packaging lift, and anti-nag penalty while preserving hard-mask gating
after score computation.

## Decision

The hot router now uses `calibrated_rule_grid_v1` as its deterministic default
score-fusion policy for the affected route-token path. This is runtime-router
policy adoption, not default foreground-hook adoption: broad route quality,
private-history behavior, live/synthetic-host usefulness, and public-quality
promotion remain separate evidence questions.

## Cannot Claim

- Default foreground-hook adoption.
- Private-history training or behavior quality.
- Answer-generation quality.
- Source truth from scores.
- Hard masks are learnable.
- Production score-fusion calibration across broad traffic.
