# React Real VCS Production-Like Source Disambiguation - 2026-06-04

This dated follow-up adds the non-oracle source-disambiguation arm requested by
GitHub #254. It reuses the local React adversarial V2 fixture from
[`react-real-vcs-adversarial-v2-2026-05-31.md`](react-real-vcs-adversarial-v2-2026-05-31.md),
but it does not feed `required_past_source_ids` into the prediction step.

The runner builds an in-memory candidate index from each case's `past_window`,
ranks source candidates from bounded source metadata and future-event surface
fields, then uses `required_past_source_ids` only for grading. This is a
production-like deterministic retrieval arm, not a live model/provider result.

## Command

```powershell
python benchmarks\aippocampus\benchmark_vcs_future_event_recall.py --dataset .tmp\react-real-vcs-adversarial-v2\react-adversarial-v2-fixture.jsonl --event-metadata .tmp\react-real-vcs-adversarial-v2\event-meta.json --production-like-retrieval --allow-non-cc0-dataset --output .tmp\react-real-vcs-adversarial-v2\react-adversarial-v2-production-like-retrieval-report.json --json
```

The command exits nonzero under the default perfect-quality gate because this
arm has expected false positives on one negative-control track. The full output
is kept local under `.tmp/`; this report commits only sanitized aggregate
metrics.

## Overall Result

| Metric | Value |
| --- | ---: |
| Gold events | 60 |
| Non-flag events | 57 |
| Predicted flags | 90 |
| Recall | 100.00% |
| Precision | 66.67% |
| F1 | 80.00% |
| False negatives | 0 |
| False positives | 30 |
| Anti-drift pass | 47.37% |
| Source-support failures | 0 |

## Source-Disambiguation Metrics

| Metric | Value |
| --- | ---: |
| `current_source_top_k_hit_rate` | 100.00% |
| `current_vs_stale_pairwise_win_rate` | 100.00% |
| `stale_source_top_k_rate` | 0.00% |
| `wrong_source_evidence_rate` | 0.00% |
| `negative_false_positive_rate` | 52.63% |
| Pairwise current-vs-stale wins | 51 / 51 |

## Track Results

| Track | Gold | Non-flag | Current top-1 hit | Current-vs-stale win | Wrong source evidence | Negative false positive |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `dual_source_counterfactual` | 12 | 0 | 100.00% | 100.00% | 0.00% | n/a |
| `temporal_override_chain` | 12 | 0 | 100.00% | 100.00% | 0.00% | n/a |
| `family_cross_contamination` | 9 | 0 | 100.00% | 100.00% | 0.00% | n/a |
| `behavior_only_rollout_gold` | 9 | 0 | 100.00% | 100.00% | 0.00% | n/a |
| `adversarial_paraphrase` | 18 | 0 | 100.00% | n/a | 0.00% | n/a |
| `lexical_near_miss_anti_drift` | 0 | 30 | n/a | n/a | n/a | 100.00% |
| `behavior_narrative_negative` | 0 | 9 | n/a | n/a | n/a | 0.00% |
| `abstention_unsupported` | 0 | 18 | n/a | n/a | n/a | 0.00% |

## Interpretation

- The arm separates the source authority problem from the source-window oracle:
  dual-source and temporal-override cases pick the current/effective source
  over stale/public alternatives without gold source ids in the ranking input.
- It also exposes a real hard-negative failure: lexical near-miss events still
  over-activate, producing 30 false positives. This is a retrieval/decision
  calibration problem, not a source-id disambiguation failure.
- The source-window score from the 2026-05-31 report remains a deterministic
  oracle contract. This report is the first committed non-oracle
  production-like disambiguation slice for the same adversarial fixture.

## Boundary

- No raw PR bodies, raw search payloads, raw rollout payloads, private data, or
  local absolute paths are committed.
- `required_past_source_ids` are used only for grading metrics.
- This does not claim live model quality, wild VCS corpus quality, private
  real-history continuity quality, or license-safe redistribution of the local
  React fixture.

Machine-readable aggregate:
[`react-real-vcs-production-like-disambiguation-2026-06-04.json`](react-real-vcs-production-like-disambiguation-2026-06-04.json).
