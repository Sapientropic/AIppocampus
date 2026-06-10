# Attention Score-Fusion Calibration

Role: public-safe calibration diagnostic for #1112.

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

## 2026-06-10 Public Fixture Result

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

The calibrated arm adds explicit source-handle support and anti-nag penalty
features while preserving hard-mask gating after score computation.

## Decision

This is an evaluation result, not a default-adoption change. The report selects
`calibrated_rule_grid` as the best public fixture arm, but default foreground
router adoption remains a separate product decision requiring broader route
quality and live/synthetic-host evidence.

## Cannot Claim

- Default foreground adoption.
- Private-history training or behavior quality.
- Answer-generation quality.
- Source truth from scores.
- Hard masks are learnable.
- Production score-fusion calibration across broad traffic.
