# React Real VCS 100-Gold Measurement - 2026-05-31

This dated measurement runs the VCS future-event builder and runner on curated real public PR events from [`facebook/react`](https://github.com/facebook/react). The base fixture now contains `105` gold future events and `105` anti-drift non-flag events. A separate counterfactual fixture contains the same `105` gold events and `105` anti-drift non-flag events with perturbed local source ids.

The fixtures stay local under `.tmp/react-real-vcs-100-gold/` because the normalized rows are derived from GitHub PR metadata and should not be treated as a checked-in CC0 corpus. This committed report records ids, PR URLs, timestamps, family labels, hashes, and aggregate metrics; it does not commit raw PR bodies, raw search payloads, private data, or local absolute paths.

## Candidate Queries

- `repo:facebook/react is:pr is:merged in:title revert` -> `169` candidates
- `repo:facebook/react is:pr is:merged workaround` -> `143` candidates
- `repo:facebook/react is:pr is:merged reland` -> `10` candidates
- `repo:facebook/react is:pr is:merged "again" "revert"` -> `112` candidates

Selected gold events: `105` total, with `45` `rejected_route`, `35` `workaround_rationale`, and `25` `reopen_condition`. Anti-drift negatives are matched one-for-one with the same family distribution.

## Commands

```powershell
python benchmarks\aippocampus\build_vcs_future_event_fixture.py --input .tmp\react-real-vcs-100-gold\react-100-gold-with-negatives-links.jsonl --output .tmp\react-real-vcs-100-gold\react-100-gold-with-negatives-fixture.jsonl --dataset-id react_real_vcs_100_gold_2026_05_31 --license GitHub-public-metadata-local-report-only --source-family real_public_react_vcs_100_gold_curated --allow-non-cc0-output --json
python benchmarks\aippocampus\benchmark_vcs_future_event_recall.py --dataset .tmp\react-real-vcs-100-gold\react-100-gold-with-negatives-fixture.jsonl --predictions .tmp\react-real-vcs-100-gold\react-100-gold-with-negatives-source-window-predictions.jsonl --closed-book-predictions .tmp\react-real-vcs-100-gold\react-100-gold-with-negatives-closed-book-predictions.jsonl --allow-non-cc0-dataset --output .tmp\react-real-vcs-100-gold\react-100-gold-with-negatives-source-window-report.json
python benchmarks\aippocampus\benchmark_vcs_future_event_recall.py --dataset .tmp\react-real-vcs-100-gold\react-100-gold-with-negatives-fixture.jsonl --baseline empty --allow-non-cc0-dataset --output .tmp\react-real-vcs-100-gold\react-100-gold-with-negatives-empty-report.json
python benchmarks\aippocampus\benchmark_vcs_future_event_recall.py --dataset .tmp\react-real-vcs-100-gold\react-100-gold-with-negatives-fixture.jsonl --predictions .tmp\react-real-vcs-100-gold\react-100-gold-with-negatives-closed-book-predictions.jsonl --allow-non-cc0-dataset --output .tmp\react-real-vcs-100-gold\react-100-gold-with-negatives-closed-book-report.json
python benchmarks\aippocampus\benchmark_vcs_future_event_recall.py --dataset .tmp\react-real-vcs-100-gold\react-100-gold-with-negatives-fixture.jsonl --predictions .tmp\react-real-vcs-100-gold\react-100-gold-with-negatives-overactive-predictions.jsonl --allow-non-cc0-dataset --output .tmp\react-real-vcs-100-gold\react-100-gold-with-negatives-overactive-report.json
python benchmarks\aippocampus\build_vcs_future_event_fixture.py --input .tmp\react-real-vcs-100-gold\react-100-gold-counterfactual-links.jsonl --output .tmp\react-real-vcs-100-gold\react-100-gold-counterfactual-fixture.jsonl --dataset-id react_real_vcs_100_gold_counterfactual_2026_05_31 --license GitHub-public-metadata-local-report-only --source-family real_public_react_vcs_100_gold_counterfactual_perturbation --allow-non-cc0-output --json
python benchmarks\aippocampus\benchmark_vcs_future_event_recall.py --dataset .tmp\react-real-vcs-100-gold\react-100-gold-counterfactual-fixture.jsonl --predictions .tmp\react-real-vcs-100-gold\react-100-gold-counterfactual-source-predictions.jsonl --closed-book-predictions .tmp\react-real-vcs-100-gold\react-100-gold-counterfactual-parametric-predictions.jsonl --allow-non-cc0-dataset --output .tmp\react-real-vcs-100-gold\react-100-gold-counterfactual-source-report.json
python benchmarks\aippocampus\benchmark_vcs_future_event_recall.py --dataset .tmp\react-real-vcs-100-gold\react-100-gold-counterfactual-fixture.jsonl --baseline empty --allow-non-cc0-dataset --output .tmp\react-real-vcs-100-gold\react-100-gold-counterfactual-empty-report.json
python benchmarks\aippocampus\benchmark_vcs_future_event_recall.py --dataset .tmp\react-real-vcs-100-gold\react-100-gold-counterfactual-fixture.jsonl --predictions .tmp\react-real-vcs-100-gold\react-100-gold-counterfactual-parametric-predictions.jsonl --allow-non-cc0-dataset --output .tmp\react-real-vcs-100-gold\react-100-gold-counterfactual-parametric-report.json
python benchmarks\aippocampus\benchmark_vcs_future_event_recall.py --dataset .tmp\react-real-vcs-100-gold\react-100-gold-counterfactual-fixture.jsonl --predictions .tmp\react-real-vcs-100-gold\react-100-gold-counterfactual-overactive-predictions.jsonl --allow-non-cc0-dataset --output .tmp\react-real-vcs-100-gold\react-100-gold-counterfactual-overactive-report.json
```

The empty, closed-book, parametric public-memory, and overactive sanity-control arms are expected to exit non-zero. They are measured as separate arms and must not be merged into the source-window score.

## Base Arm Results

| Arm | Predicted flags | Recall | Precision | F1 | False negatives | False positives | Anti-drift negatives | Anti-drift pass | Source-support failures |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Source-window | 105 | 100.00% | 100.00% | 100.00% | 0 | 0 | 105 | 100.00% | 0 |
| Empty | 0 | 0.00% | 0.00% | 0.00% | 105 | 0 | 105 | 100.00% | 0 |
| Closed-book source-stripped | 105 | 0.00% | 0.00% | 0.00% | 105 | 0 | 105 | 100.00% | 105 |
| Overactive all-flags sanity control | 210 | 100.00% | 50.00% | 66.67% | 0 | 105 | 105 | 0.00% | 0 |

Source-over-closed-book lift: recall `1.00`, precision `1.00`, F1 `1.00`, false-negative reduction `105`.

## Counterfactual Perturbation

The counterfactual fixture keeps the public event ids but replaces the required local source ids and local rationales. A source-backed system must follow the counterfactual source ids. A parametric public-memory control that keeps pointing to the original public source ids scores as unsupported.

| Arm | Predicted flags | Recall | Precision | F1 | False negatives | False positives | Anti-drift negatives | Anti-drift pass | Source-support failures |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Counterfactual source-backed | 105 | 100.00% | 100.00% | 100.00% | 0 | 0 | 105 | 100.00% | 0 |
| Counterfactual empty | 0 | 0.00% | 0.00% | 0.00% | 105 | 0 | 105 | 100.00% | 0 |
| Parametric public-memory control | 105 | 0.00% | 0.00% | 0.00% | 105 | 0 | 105 | 100.00% | 105 |
| Counterfactual overactive sanity control | 210 | 100.00% | 50.00% | 66.67% | 0 | 105 | 105 | 0.00% | 0 |

Counterfactual source-over-parametric lift: recall `1.00`, precision `1.00`, F1 `1.00`, false-negative reduction `105`.

## Family Results

| Family | Gold events | Anti-drift negatives | Source recall | Source anti-drift pass | Empty recall | Closed-book recall | Counterfactual source recall | Parametric recall | Overactive anti-drift violations |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `rejected_route` | 45 | 45 | 100.00% | 100.00% | 0.00% | 0.00% | 100.00% | 0.00% | 45 |
| `reopen_condition` | 25 | 25 | 100.00% | 100.00% | 0.00% | 0.00% | 100.00% | 0.00% | 25 |
| `workaround_rationale` | 35 | 35 | 100.00% | 100.00% | 0.00% | 0.00% | 100.00% | 0.00% | 35 |

## Sample Gold Events

| Family | Event | Hard event kind | Required source id |
| --- | --- | --- | --- |
| `reopen_condition` | [react-pr-17799-reopen_condition-event](https://github.com/facebook/react/pull/17799) | `pull_request_merged` | `react-pr-17799-reopen_condition-source` |
| `reopen_condition` | [react-pr-18388-reopen_condition-event](https://github.com/facebook/react/pull/18388) | `pull_request_merged` | `react-pr-18388-reopen_condition-source` |
| `workaround_rationale` | [react-pr-18459-workaround_rationale-event](https://github.com/facebook/react/pull/18459) | `pull_request_merged` | `react-pr-18459-workaround_rationale-source` |
| `rejected_route` | [react-pr-18671-rejected_route-event](https://github.com/facebook/react/pull/18671) | `commit_reverted` | `react-pr-18671-rejected_route-source` |
| `workaround_rationale` | [react-pr-18796-workaround_rationale-event](https://github.com/facebook/react/pull/18796) | `pull_request_merged` | `react-pr-18796-workaround_rationale-source` |
| `rejected_route` | [react-pr-18890-rejected_route-event](https://github.com/facebook/react/pull/18890) | `commit_reverted` | `react-pr-18890-rejected_route-source` |
| `rejected_route` | [react-pr-18899-rejected_route-event](https://github.com/facebook/react/pull/18899) | `commit_reverted` | `react-pr-18899-rejected_route-source` |
| `rejected_route` | [react-pr-19018-rejected_route-event](https://github.com/facebook/react/pull/19018) | `commit_reverted` | `react-pr-19018-rejected_route-source` |
| `reopen_condition` | [react-pr-19161-reopen_condition-event](https://github.com/facebook/react/pull/19161) | `pull_request_merged` | `react-pr-19161-reopen_condition-source` |
| `rejected_route` | [react-pr-19215-rejected_route-event](https://github.com/facebook/react/pull/19215) | `commit_reverted` | `react-pr-19215-rejected_route-source` |
| `rejected_route` | [react-pr-19365-rejected_route-event](https://github.com/facebook/react/pull/19365) | `commit_reverted` | `react-pr-19365-rejected_route-source` |
| `rejected_route` | [react-pr-19366-rejected_route-event](https://github.com/facebook/react/pull/19366) | `commit_reverted` | `react-pr-19366-rejected_route-source` |

## Sample Anti-Drift Negatives

| Family under test | Non-flag event | Hard event kind | Past source id |
| --- | --- | --- | --- |
| `reopen_condition` | [react-pr-17799-reopen_condition-event-anti-drift-vs-pr-18890](https://github.com/facebook/react/pull/18890) | `commit_reverted` | `react-pr-17799-reopen_condition-source` |
| `reopen_condition` | [react-pr-18388-reopen_condition-event-anti-drift-vs-pr-18899](https://github.com/facebook/react/pull/18899) | `commit_reverted` | `react-pr-18388-reopen_condition-source` |
| `workaround_rationale` | [react-pr-18459-workaround_rationale-event-anti-drift-vs-pr-30832](https://github.com/facebook/react/pull/30832) | `pull_request_merged` | `react-pr-18459-workaround_rationale-source` |
| `rejected_route` | [react-pr-18671-rejected_route-event-anti-drift-vs-pr-18459](https://github.com/facebook/react/pull/18459) | `pull_request_merged` | `react-pr-18671-rejected_route-source` |
| `workaround_rationale` | [react-pr-18796-workaround_rationale-event-anti-drift-vs-pr-31238](https://github.com/facebook/react/pull/31238) | `pull_request_merged` | `react-pr-18796-workaround_rationale-source` |
| `rejected_route` | [react-pr-18890-rejected_route-event-anti-drift-vs-pr-18796](https://github.com/facebook/react/pull/18796) | `pull_request_merged` | `react-pr-18890-rejected_route-source` |
| `rejected_route` | [react-pr-18899-rejected_route-event-anti-drift-vs-pr-21516](https://github.com/facebook/react/pull/21516) | `pull_request_merged` | `react-pr-18899-rejected_route-source` |
| `rejected_route` | [react-pr-19018-rejected_route-event-anti-drift-vs-pr-20468](https://github.com/facebook/react/pull/20468) | `pull_request_merged` | `react-pr-19018-rejected_route-source` |
| `reopen_condition` | [react-pr-19161-reopen_condition-event-anti-drift-vs-pr-19018](https://github.com/facebook/react/pull/19018) | `commit_reverted` | `react-pr-19161-reopen_condition-source` |

## Sample Counterfactual Events

| Family | Event | Counterfactual required source | Parametric original source |
| --- | --- | --- | --- |
| `rejected_route` | [react-pr-18671-rejected_route-event](https://github.com/facebook/react/pull/18671) | `cf-react-pr-18671-rejected_route-source-local-perturbation` | `react-pr-18671-rejected_route-source` |
| `rejected_route` | [react-pr-18890-rejected_route-event](https://github.com/facebook/react/pull/18890) | `cf-react-pr-18890-rejected_route-source-local-perturbation` | `react-pr-18890-rejected_route-source` |
| `rejected_route` | [react-pr-18899-rejected_route-event](https://github.com/facebook/react/pull/18899) | `cf-react-pr-18899-rejected_route-source-local-perturbation` | `react-pr-18899-rejected_route-source` |
| `rejected_route` | [react-pr-19018-rejected_route-event](https://github.com/facebook/react/pull/19018) | `cf-react-pr-19018-rejected_route-source-local-perturbation` | `react-pr-19018-rejected_route-source` |
| `rejected_route` | [react-pr-19215-rejected_route-event](https://github.com/facebook/react/pull/19215) | `cf-react-pr-19215-rejected_route-source-local-perturbation` | `react-pr-19215-rejected_route-source` |
| `rejected_route` | [react-pr-19365-rejected_route-event](https://github.com/facebook/react/pull/19365) | `cf-react-pr-19365-rejected_route-source-local-perturbation` | `react-pr-19365-rejected_route-source` |
| `rejected_route` | [react-pr-19366-rejected_route-event](https://github.com/facebook/react/pull/19366) | `cf-react-pr-19366-rejected_route-source-local-perturbation` | `react-pr-19366-rejected_route-source` |
| `rejected_route` | [react-pr-19508-rejected_route-event](https://github.com/facebook/react/pull/19508) | `cf-react-pr-19508-rejected_route-source-local-perturbation` | `react-pr-19508-rejected_route-source` |
| `rejected_route` | [react-pr-23239-rejected_route-event](https://github.com/facebook/react/pull/23239) | `cf-react-pr-23239-rejected_route-source-local-perturbation` | `react-pr-23239-rejected_route-source` |

## Boundary

- This run proves the builder and runner can handle a 100+ gold-event real React history fixture with separated source-window, empty, and closed-book arms.
- It also proves the same 100+ fixture can carry anti-drift negatives and a counterfactual perturbation control without collapsing family-level reporting.
- It does not prove model quality; the source-window, closed-book, parametric, empty, and overactive predictions are deterministic controls.
- The local fixture is not promoted as a redistributable CC0 corpus until the PR-metadata redistribution boundary is reviewed.
- The overactive sanity controls are intentionally bad controls: they demonstrate that anti-drift negatives penalize a system that flags everything.

Machine-readable aggregate: [`react-real-vcs-100-gold-2026-05-31.json`](react-real-vcs-100-gold-2026-05-31.json).
