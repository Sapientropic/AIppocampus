# Public Longitudinal Users Measurement - 2026-05-31

This dated report records separate deterministic measurements for the public longitudinal-users benchmark surfaces added for PR #173. Raw command outputs were written under `.tmp/public-longitudinal-measurements/`; this committed report keeps only sanitized metrics and claim boundaries.

## Commands

```powershell
python benchmarks\aippocampus\benchmark_locomo_public_users.py --output .tmp\public-longitudinal-measurements\locomo-gold.json
python benchmarks\aippocampus\benchmark_locomo_public_users.py --baseline empty --output .tmp\public-longitudinal-measurements\locomo-empty.json
python benchmarks\aippocampus\benchmark_locomo_public_users.py --max-samples 1 --max-cases 3 --case-pack-output .tmp\public-longitudinal-measurements\locomo-case-pack-smoke.json --prediction-template-output .tmp\public-longitudinal-measurements\locomo-prediction-template-smoke.jsonl --output .tmp\public-longitudinal-measurements\locomo-artifact-smoke.json
python benchmarks\aippocampus\benchmark_public_longitudinal_users.py --output .tmp\public-longitudinal-measurements\pseudo-user-gold.json
python benchmarks\aippocampus\benchmark_public_longitudinal_users.py --baseline empty --output .tmp\public-longitudinal-measurements\pseudo-user-empty.json
python benchmarks\aippocampus\benchmark_vcs_future_event_recall.py --output .tmp\public-longitudinal-measurements\vcs-gold.json
python benchmarks\aippocampus\benchmark_vcs_future_event_recall.py --baseline empty --output .tmp\public-longitudinal-measurements\vcs-empty.json
python benchmarks\aippocampus\benchmark_vcs_future_event_recall.py --dataset benchmark_corpus\public_longitudinal_users\rollout_behavior_events_v1.jsonl --output .tmp\public-longitudinal-measurements\rollout-gold.json
python benchmarks\aippocampus\benchmark_vcs_future_event_recall.py --dataset benchmark_corpus\public_longitudinal_users\rollout_behavior_events_v1.jsonl --baseline empty --output .tmp\public-longitudinal-measurements\rollout-empty.json
```

The empty baselines are expected to exit non-zero. They are negative controls that verify silent systems miss recall obligations instead of passing by saying nothing.

## Results

| Track | Positive control | Negative control | Key count | Boundary |
| --- | --- | --- | ---: | --- |
| LoCoMo public users | full recall 100.00%, exact 100.00% | empty recall 0.00%, missing ids 2789 | 1973 cases | Conversation evidence retrieval only. |
| Synthetic coding pseudo-users | score 100.00%, decisions 100.00% | empty score 30.00%, decisions 0.00% | 15 cases | Contract smoke, not flagship recall evidence. |
| VCS future events | recall 100.00%, precision 100.00% | empty recall 0.00%, false negatives 6 | 6 gold events | Hard-event recall scaffold. |
| Rollout behavior events | recall 100.00%, precision 100.00% | empty recall 0.00%, false negatives 3 | 3 gold events | Behavior-backed rollout scaffold. |

## LoCoMo Replication Smoke

The local replication artifact path was smoke-tested with `3` cases. `case_pack_written=true`, `prediction_template_written=true`. The case pack intentionally contains LoCoMo dialogue/question text for local model input, while the prediction template does not include raw text or gold evidence ids.

## Claim Boundary

- LoCoMo supports public same-conversation source-evidence retrieval, not coding tacit-constraint quality.
- Synthetic pseudo-users support scoring-contract smoke tests only.
- VCS and rollout fixtures prove recall-aware scoring semantics with hard events; wild-corpus claims still need curated public rows plus closed-book contamination reports.
- This committed report does not include raw LoCoMo text, private user data, raw rollout payloads, or local absolute paths.

Machine-readable aggregate: [`public-longitudinal-users-measurement-2026-05-31.json`](public-longitudinal-users-measurement-2026-05-31.json).
