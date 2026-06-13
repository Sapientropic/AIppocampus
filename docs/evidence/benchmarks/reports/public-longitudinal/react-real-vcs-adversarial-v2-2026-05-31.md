# React Real VCS Adversarial V2 Measurement - 2026-05-31

This dated measurement extends the React VCS hard-event benchmark with sharper adversarial controls. It uses local generated fixtures under `.tmp/react-real-vcs-adversarial-v2/` and commits only sanitized aggregate evidence.

The fixture contains `60` gold events and `57` non-flag events across three families. Gold events are balanced: `20` each for `rejected_route`, `reopen_condition`, and `workaround_rationale`. Non-flag events are also balanced at `19` per family.

## Adversarial Tracks

| Track | Events | What It Attacks |
| --- | ---: | --- |
| `dual_source_counterfactual` | 12 | Original public source and current local source coexist; current source must win. |
| `temporal_override_chain` | 12 | Older source is superseded by a later effective source. |
| `family_cross_contamination` | 9 | Related sources from other families are present but must not support the target family. |
| `behavior_only_rollout_gold` | 9 | Only deterministic behavior traces support rollout rejected-route gold; narrative is decoy. |
| `adversarial_paraphrase` | 18 | Decision structure is preserved while obvious trigger words are absent. |
| `lexical_near_miss_anti_drift` | 30 | Same-family/same-token public events must not activate unrelated source. |
| `behavior_narrative_negative` | 9 | Narrative-only claims with successful behavior must be suppressed. |
| `abstention_unsupported` | 18 | Similar surface form without hard source support should be suppress/unknown. |

## Commands

```powershell
python benchmarks\aippocampus\builders\build_vcs_future_event_fixture.py --input .tmp\react-real-vcs-adversarial-v2\react-adversarial-v2-links.jsonl --output .tmp\react-real-vcs-adversarial-v2\react-adversarial-v2-fixture.jsonl --dataset-id react_real_vcs_adversarial_v2_2026_05_31 --license GitHub-public-metadata-local-report-only --source-family real_public_react_vcs_adversarial_v2 --allow-non-cc0-output --json
python benchmarks\aippocampus\benchmark_vcs_future_event_recall.py --dataset .tmp\react-real-vcs-adversarial-v2\react-adversarial-v2-fixture.jsonl --predictions .tmp\react-real-vcs-adversarial-v2\react-adversarial-v2-source-window-predictions.jsonl --closed-book-predictions .tmp\react-real-vcs-adversarial-v2\react-adversarial-v2-closed-book-predictions.jsonl --allow-non-cc0-dataset --output .tmp\react-real-vcs-adversarial-v2\react-adversarial-v2-source-window-report.json
python benchmarks\aippocampus\benchmark_vcs_future_event_recall.py --dataset .tmp\react-real-vcs-adversarial-v2\react-adversarial-v2-fixture.jsonl --baseline empty --allow-non-cc0-dataset --output .tmp\react-real-vcs-adversarial-v2\react-adversarial-v2-empty-report.json
python benchmarks\aippocampus\benchmark_vcs_future_event_recall.py --dataset .tmp\react-real-vcs-adversarial-v2\react-adversarial-v2-fixture.jsonl --predictions .tmp\react-real-vcs-adversarial-v2\react-adversarial-v2-closed-book-predictions.jsonl --allow-non-cc0-dataset --output .tmp\react-real-vcs-adversarial-v2\react-adversarial-v2-closed-book-report.json
python benchmarks\aippocampus\benchmark_vcs_future_event_recall.py --dataset .tmp\react-real-vcs-adversarial-v2\react-adversarial-v2-fixture.jsonl --predictions .tmp\react-real-vcs-adversarial-v2\react-adversarial-v2-stale-decoy-predictions.jsonl --allow-non-cc0-dataset --output .tmp\react-real-vcs-adversarial-v2\react-adversarial-v2-stale-decoy-report.json
python benchmarks\aippocampus\benchmark_vcs_future_event_recall.py --dataset .tmp\react-real-vcs-adversarial-v2\react-adversarial-v2-fixture.jsonl --predictions .tmp\react-real-vcs-adversarial-v2\react-adversarial-v2-keyword-surface-predictions.jsonl --allow-non-cc0-dataset --output .tmp\react-real-vcs-adversarial-v2\react-adversarial-v2-keyword-surface-report.json
python benchmarks\aippocampus\benchmark_vcs_future_event_recall.py --dataset .tmp\react-real-vcs-adversarial-v2\react-adversarial-v2-fixture.jsonl --predictions .tmp\react-real-vcs-adversarial-v2\react-adversarial-v2-overactive-predictions.jsonl --allow-non-cc0-dataset --output .tmp\react-real-vcs-adversarial-v2\react-adversarial-v2-overactive-report.json
```

The empty, closed-book, stale/decoy, keyword-surface, and overactive arms are expected to fail. They are diagnostic controls, not alternate headline scores.

## Arm Results

| Arm | Predicted flags | Recall | Precision | F1 | False negatives | False positives | Anti-drift pass | Source-support failures |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Source-window | 60 | 100.00% | 100.00% | 100.00% | 0 | 0 | 100.00% | 0 |
| Empty | 0 | 0.00% | 0.00% | 0.00% | 60 | 0 | 100.00% | 0 |
| Closed-book source-stripped | 60 | 0.00% | 0.00% | 0.00% | 60 | 0 | 100.00% | 60 |
| Stale/decoy source | 60 | 30.00% | 30.00% | 30.00% | 42 | 0 | 100.00% | 42 |
| Keyword-surface bad control | 99 | 70.00% | 42.42% | 52.83% | 18 | 57 | 0.00% | 0 |
| Overactive all-flags control | 117 | 100.00% | 51.28% | 67.79% | 0 | 57 | 0.00% | 0 |

## Track Results

| Track | Gold | Non-flag | Source recall | Empty recall | Closed-book recall | Stale/decoy recall | Keyword recall | Keyword anti-drift pass | Overactive anti-drift pass |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `dual_source_counterfactual` | 12 | 0 | 100.00% | 0.00% | 0.00% | 0.00% | 100.00% | n/a | n/a |
| `temporal_override_chain` | 12 | 0 | 100.00% | 0.00% | 0.00% | 0.00% | 100.00% | n/a | n/a |
| `family_cross_contamination` | 9 | 0 | 100.00% | 0.00% | 0.00% | 0.00% | 100.00% | n/a | n/a |
| `behavior_only_rollout_gold` | 9 | 0 | 100.00% | 0.00% | 0.00% | 0.00% | 100.00% | n/a | n/a |
| `adversarial_paraphrase` | 18 | 0 | 100.00% | 0.00% | 0.00% | 100.00% | 0.00% | n/a | n/a |
| `lexical_near_miss_anti_drift` | 0 | 30 | n/a | n/a | n/a | n/a | n/a | 0.00% | 0.00% |
| `behavior_narrative_negative` | 0 | 9 | n/a | n/a | n/a | n/a | n/a | 0.00% | 0.00% |
| `abstention_unsupported` | 0 | 18 | n/a | n/a | n/a | n/a | n/a | 0.00% | 0.00% |

## Family Results

| Family | Gold | Non-flag | Source recall | Source anti-drift pass | Keyword recall | Keyword false positives | Overactive false positives |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `rejected_route` | 20 | 19 | 100.00% | 100.00% | 70.00% | 19 | 19 |
| `reopen_condition` | 20 | 19 | 100.00% | 100.00% | 70.00% | 19 | 19 |
| `workaround_rationale` | 20 | 19 | 100.00% | 100.00% | 70.00% | 19 | 19 |

## Interpretation

- `stale_decoy` falls to `30.00%` recall because dual-source, temporal override, family cross-contamination, and behavior-only cases require a specific current/behavior-backed source.
- `keyword_surface` gets `70.00%` recall but creates `57` false positives and misses all adversarial paraphrase positives, which is the intended surface-matching failure.
- `overactive` reaches `100.00%` recall but has `57` false positives and `0.00%` anti-drift pass, so the benchmark no longer rewards a system that flags everything.
- `closed_book` remains `0.00%` recall with `60` source-support failures; public outcome memory is not enough for this source-backed contract.

## Samples

| Track | Family | Event | Flag-worthy | Required source ids |
| --- | --- | --- | ---: | --- |
| `dual_source_counterfactual` | `rejected_route` | [adv-dual-rejected_route-27584-event](https://github.com/facebook/react/pull/27584) | true | `adv-dual-rejected_route-27584-current-counterfactual-source` |
| `dual_source_counterfactual` | `reopen_condition` | [adv-dual-reopen_condition-30832-event](https://github.com/facebook/react/pull/30832) | true | `adv-dual-reopen_condition-30832-current-counterfactual-source` |
| `dual_source_counterfactual` | `workaround_rationale` | [adv-dual-workaround_rationale-24730-event](https://github.com/facebook/react/pull/24730) | true | `adv-dual-workaround_rationale-24730-current-counterfactual-source` |
| `temporal_override_chain` | `rejected_route` | [adv-temporal-rejected_route-28670-current-event](https://github.com/facebook/react/pull/28670) | true | `adv-temporal-rejected_route-28670-day55-current-source` |
| `temporal_override_chain` | `reopen_condition` | [adv-temporal-reopen_condition-17799-current-event](https://github.com/facebook/react/pull/17799) | true | `adv-temporal-reopen_condition-17799-day55-current-source` |
| `temporal_override_chain` | `workaround_rationale` | [adv-temporal-workaround_rationale-29143-current-event](https://github.com/facebook/react/pull/29143) | true | `adv-temporal-workaround_rationale-29143-day55-current-source` |
| `family_cross_contamination` | `rejected_route` | [adv-cross-family-rejected_route-29663-event](https://github.com/facebook/react/pull/29663) | true | `adv-cross-family-rejected_route-29663-source` |
| `family_cross_contamination` | `reopen_condition` | [adv-cross-family-reopen_condition-19161-event](https://github.com/facebook/react/pull/19161) | true | `adv-cross-family-reopen_condition-19161-source` |
| `family_cross_contamination` | `workaround_rationale` | [adv-cross-family-workaround_rationale-32822-event](https://github.com/facebook/react/pull/32822) | true | `adv-cross-family-workaround_rationale-32822-source` |
| `behavior_only_rollout_gold` | `rejected_route` | [adv-rollout-rejected_route-0-behavior-event](https://github.com/facebook/react/pull/90000) | true | `adv-rollout-rejected_route-0-behavior-source` |
| `behavior_only_rollout_gold` | `reopen_condition` | [adv-rollout-reopen_condition-0-behavior-event](https://github.com/facebook/react/pull/90010) | true | `adv-rollout-reopen_condition-0-behavior-source` |
| `behavior_only_rollout_gold` | `workaround_rationale` | [adv-rollout-workaround_rationale-0-behavior-event](https://github.com/facebook/react/pull/90020) | true | `adv-rollout-workaround_rationale-0-behavior-source` |
| `adversarial_paraphrase` | `rejected_route` | [adv-paraphrase-rejected_route-30792-event](https://github.com/facebook/react/pull/30792) | true | `adv-paraphrase-rejected_route-30792-source` |
| `adversarial_paraphrase` | `reopen_condition` | [adv-paraphrase-reopen_condition-21079-event](https://github.com/facebook/react/pull/21079) | true | `adv-paraphrase-reopen_condition-21079-source` |
| `adversarial_paraphrase` | `workaround_rationale` | [adv-paraphrase-workaround_rationale-18459-event](https://github.com/facebook/react/pull/18459) | true | `adv-paraphrase-workaround_rationale-18459-source` |
| `lexical_near_miss_anti_drift` | `rejected_route` | [adv-lexical-rejected_route-18671-vs-25812](https://github.com/facebook/react/pull/25812) | false | none |
| `lexical_near_miss_anti_drift` | `reopen_condition` | [adv-lexical-reopen_condition-17799-vs-25915](https://github.com/facebook/react/pull/25915) | false | none |
| `lexical_near_miss_anti_drift` | `workaround_rationale` | [adv-lexical-workaround_rationale-18459-vs-24195](https://github.com/facebook/react/pull/24195) | false | none |
| `behavior_narrative_negative` | `rejected_route` | [adv-rollout-rejected_route-0-narrative-negative](https://github.com/facebook/react/pull/90000) | false | none |
| `behavior_narrative_negative` | `reopen_condition` | [adv-rollout-reopen_condition-0-narrative-negative](https://github.com/facebook/react/pull/90010) | false | none |
| `behavior_narrative_negative` | `workaround_rationale` | [adv-rollout-workaround_rationale-0-narrative-negative](https://github.com/facebook/react/pull/90020) | false | none |
| `abstention_unsupported` | `rejected_route` | [adv-abstain-rejected_route-32214-unsupported](https://github.com/facebook/react/pull/32214) | false | none |
| `abstention_unsupported` | `reopen_condition` | [adv-abstain-reopen_condition-27307-unsupported](https://github.com/facebook/react/pull/27307) | false | none |
| `abstention_unsupported` | `workaround_rationale` | [adv-abstain-workaround_rationale-20468-unsupported](https://github.com/facebook/react/pull/20468) | false | none |

## Boundary

- This is deterministic adversarial fixture evidence, not live model quality.
- The local fixture combines React public PR metadata with public-safe rollout-style synthetic behavior controls; raw PR text, raw rollout payloads, local paths, and private data are not committed.
- These controls are meant to be run beside the 100-gold React VCS report, not replace it.
- The fixture is not a redistributable corpus until PR-metadata and synthetic-control licensing boundaries are reviewed.

Machine-readable aggregate: [`react-real-vcs-adversarial-v2-2026-05-31.json`](react-real-vcs-adversarial-v2-2026-05-31.json).
