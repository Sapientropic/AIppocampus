# React Real VCS Smoke - 2026-05-31

This dated smoke measurement runs the VCS future-event benchmark on curated real public GitHub metadata from [`facebook/react`](https://github.com/facebook/react). It is intentionally small: the goal is to prove the runner can score real public hard events and negative controls, not to claim wild-corpus quality.

Raw curated rows and generated fixtures stayed under `.tmp/react-real-vcs-smoke/`. This committed report keeps only PR URLs, ids, timestamps, metrics, and claim boundaries; it does not commit raw PR bodies or large review text.

## Commands

```powershell
gh pr view 35346 --repo facebook/react --json number,title,url,createdAt,closedAt,mergedAt,body,mergeCommit
gh pr view 35348 --repo facebook/react --json number,title,url,createdAt,closedAt,mergedAt,body,mergeCommit
gh pr view 34747 --repo facebook/react --json number,title,url,createdAt,closedAt,mergedAt,body,mergeCommit
gh pr view 35825 --repo facebook/react --json number,title,url,createdAt,closedAt,mergedAt,body,mergeCommit
gh pr view 35559 --repo facebook/react --json number,title,url,createdAt,closedAt,mergedAt,body,mergeCommit
gh pr view 35487 --repo facebook/react --json number,title,url,createdAt,closedAt,mergedAt,body,mergeCommit
gh pr view 35546 --repo facebook/react --json number,title,url,createdAt,closedAt,mergedAt,body,mergeCommit
python benchmarks\aippocampus\build_vcs_future_event_fixture.py --input .tmp\react-real-vcs-smoke\react-real-vcs-links.jsonl --output .tmp\react-real-vcs-smoke\react-real-vcs-fixture.jsonl --dataset-id react_real_vcs_smoke_2026_05_31 --license GitHub-public-metadata-local-report-only --source-family real_public_react_vcs_curated --allow-non-cc0-output --json
python benchmarks\aippocampus\benchmark_vcs_future_event_recall.py --dataset .tmp\react-real-vcs-smoke\react-real-vcs-fixture.jsonl --predictions .tmp\react-real-vcs-smoke\react-source-window-predictions.jsonl --closed-book-predictions .tmp\react-real-vcs-smoke\react-closed-book-predictions.jsonl --allow-non-cc0-dataset --output .tmp\react-real-vcs-smoke\react-source-window-report.json
python benchmarks\aippocampus\benchmark_vcs_future_event_recall.py --dataset .tmp\react-real-vcs-smoke\react-real-vcs-fixture.jsonl --baseline empty --allow-non-cc0-dataset --output .tmp\react-real-vcs-smoke\react-empty-report.json
python benchmarks\aippocampus\benchmark_vcs_future_event_recall.py --dataset .tmp\react-real-vcs-smoke\react-real-vcs-fixture.jsonl --predictions .tmp\react-real-vcs-smoke\react-closed-book-predictions.jsonl --allow-non-cc0-dataset --output .tmp\react-real-vcs-smoke\react-closed-book-report.json
python benchmarks\aippocampus\build_vcs_future_event_fixture.py --input .tmp\react-real-vcs-smoke\react-counterfactual-links.jsonl --output .tmp\react-real-vcs-smoke\react-counterfactual-fixture.jsonl --dataset-id react_real_vcs_counterfactual_smoke_2026_05_31 --license GitHub-public-metadata-local-report-only --source-family real_public_react_vcs_counterfactual_perturbation --allow-non-cc0-output --json
python benchmarks\aippocampus\benchmark_vcs_future_event_recall.py --dataset .tmp\react-real-vcs-smoke\react-counterfactual-fixture.jsonl --predictions .tmp\react-real-vcs-smoke\react-counterfactual-source-predictions.jsonl --closed-book-predictions .tmp\react-real-vcs-smoke\react-counterfactual-parametric-predictions.jsonl --allow-non-cc0-dataset --output .tmp\react-real-vcs-smoke\react-counterfactual-source-report.json
python benchmarks\aippocampus\benchmark_vcs_future_event_recall.py --dataset .tmp\react-real-vcs-smoke\react-counterfactual-fixture.jsonl --predictions .tmp\react-real-vcs-smoke\react-counterfactual-parametric-predictions.jsonl --allow-non-cc0-dataset --output .tmp\react-real-vcs-smoke\react-counterfactual-parametric-report.json
python benchmarks\aippocampus\benchmark_vcs_future_event_recall.py --dataset .tmp\react-real-vcs-smoke\react-counterfactual-fixture.jsonl --baseline empty --allow-non-cc0-dataset --output .tmp\react-real-vcs-smoke\react-counterfactual-empty-report.json
```

The empty baseline, source-stripped closed-book control, and parametric public-memory counterfactual control are expected to exit non-zero. They are negative controls.

## Results

| Arm | Recall | Precision | F1 | False negatives | False positives | Anti-drift pass |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Source-window predictions | 100.00% | 100.00% | 100.00% | 0 | 0 | 100.00% |
| Empty baseline | 0.00% | 0.00% | 0.00% | 3 | 0 | 100.00% |
| Closed-book source-stripped control | 0.00% | 0.00% | 0.00% | 3 | 0 | 100.00% |

Source-over-closed-book lift: recall `1.00`, precision `1.00`, F1 `1.00`, false-negative reduction `3`.

## Counterfactual Perturbation

The counterfactual arm keeps the same public event ids but replaces the required local source ids/rationales. A source-backed system should follow those counterfactual source ids. A parametric-public-memory control that keeps pointing to the original public source ids should fail source support.

| Arm | Recall | Precision | False negatives | Source-support failures |
| --- | ---: | ---: | ---: | ---: |
| Counterfactual source-backed | 100.00% | 100.00% | 0 | 0 |
| Parametric public-memory control | 0.00% | 0.00% | 3 | 3 |
| Empty baseline | 0.00% | 0.00% | 3 | 0 |

Source-over-parametric lift: recall `1.00`, precision `1.00`, F1 `1.00`, false-negative reduction `3`.

| Public event | Family | Counterfactual required source | Original public-memory source |
| --- | --- | --- | --- |
| [react-pr-35348-reland-merged](https://github.com/facebook/react/pull/35348) | `reopen_condition` | `cf-react-pr-35346-revert-memory-leak` | `react-pr-35346-revert` |
| [react-pr-34747-hermes-revert-merged](https://github.com/facebook/react/pull/34747) | `workaround_rationale` | `cf-react-pr-34747-hermes-windows-paths` | `react-pr-34747-hermes-rationale` |
| [react-pr-35825-feature-cleanup-merged](https://github.com/facebook/react/pull/35825) | `rejected_route` | `cf-react-pr-35825-cleanup-rn-memory` | `react-pr-35825-cleanup-rationale` |

## Family Slices

| Family | Gold events | Recall | False negatives |
| --- | ---: | ---: | ---: |
| `rejected_route` | 1 | 100.00% | 0 |
| `reopen_condition` | 1 | 100.00% | 0 |
| `workaround_rationale` | 1 | 100.00% | 0 |

## Public Event Clusters

| Project id | Past source URL | Flag-worthy future event | Anti-drift negative |
| --- | --- | --- | --- |
| `react-compiler-variabledeclarator-reland` | [react-pr-35346-revert](https://github.com/facebook/react/pull/35346) | [react-pr-35348-reland-merged](https://github.com/facebook/react/pull/35348) | [react-pr-35487-gesture-revert-merged](https://github.com/facebook/react/pull/35487) |
| `react-eprh-hermesparser-revert` | [react-pr-34747-hermes-rationale](https://github.com/facebook/react/pull/34747) | [react-pr-34747-hermes-revert-merged](https://github.com/facebook/react/pull/34747) | [react-pr-35546-internal-accidental-revert](https://github.com/facebook/react/pull/35546) |
| `react-compiler-feature-flag-cleanup` | [react-pr-35825-cleanup-rationale](https://github.com/facebook/react/pull/35825) | [react-pr-35825-feature-cleanup-merged](https://github.com/facebook/react/pull/35825) | [react-pr-35559-gesture-animation-cleanup](https://github.com/facebook/react/pull/35559) |

## Interpretation

This is the first real public VCS smoke for the hard-event runner. It covers a tiny React sample with `reopen_condition`, `workaround_rationale`, `rejected_route`, and same-token anti-drift negatives. It confirms three things the synthetic scaffold could not by itself show:

- the runner can score non-CC0 local public GitHub metadata without committing raw PR text;
- a silent system and a source-stripped closed-book control both fail recall, so source-backed support is actually part of the score;
- a counterfactual perturbation catches the public-memory failure mode: predictions that keep citing original public source ids score `0.00%` recall with `3` source-support failures.

It still does not measure the harder longitudinal tracks directly: temporal override beyond this small reland example, implicit constraint drift, cross-project contamination, intentional forget compliance, post-compaction detail recall, or dream semantic quality. Those need dedicated real-history or rollout-derived case packs.

Machine-readable aggregate: [`react-real-vcs-smoke-2026-05-31.json`](react-real-vcs-smoke-2026-05-31.json).
