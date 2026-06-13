# React Real VCS 100-Gold Measurement - 2026-05-31

This dated measurement runs the VCS future-event builder and runner on curated real public PR events from [`facebook/react`](https://github.com/facebook/react). The base fixture now contains `105` gold future events and `105` anti-drift non-flag events. A separate counterfactual fixture contains the same `105` gold events and `105` anti-drift non-flag events with perturbed local source ids.

The fixtures stay local under `.tmp/react-real-vcs-100-gold/` because the normalized rows are derived from GitHub PR metadata and should not be treated as a checked-in CC0 corpus. This committed report records ids, PR URLs, timestamps, family labels, hashes, and aggregate metrics; it does not commit raw PR bodies, raw search payloads, private data, or local absolute paths.

## Candidate Queries

- `repo:facebook/react is:pr is:merged in:title revert` -> `169` candidates
- `repo:facebook/react is:pr is:merged workaround` -> `143` candidates
- `repo:facebook/react is:pr is:merged reland` -> `10` candidates
- `repo:facebook/react is:pr is:merged "again" "revert"` -> `112` candidates

Selected gold events: `105` total, with `45` `rejected_route`, `35` `workaround_rationale`, and `25` `reopen_condition`. Anti-drift negatives are matched one-for-one with the same family distribution.

## Candidate Discovery Bias

Candidate discovery is now treated as an auditable benchmark artifact, not as a prelude hidden behind the final score. This dated React run predates the new `candidate_discovery_bias` builder audit rows, so the committed report can only reconstruct a partial bias ledger from the recorded query counts and selected-event counts:

- source surface mix: `169` title-search candidates and `265` broader GitHub search-surface candidates;
- query-term hit mix: `169` `revert`, `143` `workaround`, `10` `reland`, and `112` `again`/`revert` candidates;
- selected gold family balance: `45` `rejected_route`, `35` `workaround_rationale`, and `25` `reopen_condition`;
- manual exclusion reasons and sampled miss rate: unavailable for this legacy run because no sanitized audit ledger was archived.

This means the `100/105` source-window score below is a deterministic source-support contract result over the selected gold universe. It is not a claim that the candidate-discovery process found every natural React engineering-history event that should matter. Future VCS fixture builds should pass sanitized discovery audit rows, including excluded candidates and sampled misses, through `build_vcs_future_event_fixture.py --candidate-discovery-audit`.

## Commands

```powershell
python benchmarks\aippocampus\builders\build_vcs_future_event_fixture.py --input .tmp\react-real-vcs-100-gold\react-100-gold-with-negatives-links.jsonl --output .tmp\react-real-vcs-100-gold\react-100-gold-with-negatives-fixture.jsonl --dataset-id react_real_vcs_100_gold_2026_05_31 --license GitHub-public-metadata-local-report-only --source-family real_public_react_vcs_100_gold_curated --allow-non-cc0-output --json
python benchmarks\aippocampus\benchmark_vcs_future_event_recall.py --dataset .tmp\react-real-vcs-100-gold\react-100-gold-with-negatives-fixture.jsonl --predictions .tmp\react-real-vcs-100-gold\react-100-gold-with-negatives-source-window-predictions.jsonl --closed-book-predictions .tmp\react-real-vcs-100-gold\react-100-gold-with-negatives-closed-book-predictions.jsonl --allow-non-cc0-dataset --output .tmp\react-real-vcs-100-gold\react-100-gold-with-negatives-source-window-report.json
python benchmarks\aippocampus\benchmark_vcs_future_event_recall.py --dataset .tmp\react-real-vcs-100-gold\react-100-gold-with-negatives-fixture.jsonl --baseline empty --allow-non-cc0-dataset --output .tmp\react-real-vcs-100-gold\react-100-gold-with-negatives-empty-report.json
python benchmarks\aippocampus\benchmark_vcs_future_event_recall.py --dataset .tmp\react-real-vcs-100-gold\react-100-gold-with-negatives-fixture.jsonl --predictions .tmp\react-real-vcs-100-gold\react-100-gold-with-negatives-closed-book-predictions.jsonl --allow-non-cc0-dataset --output .tmp\react-real-vcs-100-gold\react-100-gold-with-negatives-closed-book-report.json
python benchmarks\aippocampus\benchmark_vcs_future_event_recall.py --dataset .tmp\react-real-vcs-100-gold\react-100-gold-with-negatives-fixture.jsonl --predictions .tmp\react-real-vcs-100-gold\react-100-gold-with-negatives-overactive-predictions.jsonl --allow-non-cc0-dataset --output .tmp\react-real-vcs-100-gold\react-100-gold-with-negatives-overactive-report.json
python benchmarks\aippocampus\builders\build_vcs_future_event_fixture.py --input .tmp\react-real-vcs-100-gold\react-100-gold-counterfactual-links.jsonl --output .tmp\react-real-vcs-100-gold\react-100-gold-counterfactual-fixture.jsonl --dataset-id react_real_vcs_100_gold_counterfactual_2026_05_31 --license GitHub-public-metadata-local-report-only --source-family real_public_react_vcs_100_gold_counterfactual_perturbation --allow-non-cc0-output --json
python benchmarks\aippocampus\benchmark_vcs_future_event_recall.py --dataset .tmp\react-real-vcs-100-gold\react-100-gold-counterfactual-fixture.jsonl --predictions .tmp\react-real-vcs-100-gold\react-100-gold-counterfactual-source-predictions.jsonl --closed-book-predictions .tmp\react-real-vcs-100-gold\react-100-gold-counterfactual-parametric-predictions.jsonl --allow-non-cc0-dataset --output .tmp\react-real-vcs-100-gold\react-100-gold-counterfactual-source-report.json
python benchmarks\aippocampus\benchmark_vcs_future_event_recall.py --dataset .tmp\react-real-vcs-100-gold\react-100-gold-counterfactual-fixture.jsonl --baseline empty --allow-non-cc0-dataset --output .tmp\react-real-vcs-100-gold\react-100-gold-counterfactual-empty-report.json
python benchmarks\aippocampus\benchmark_vcs_future_event_recall.py --dataset .tmp\react-real-vcs-100-gold\react-100-gold-counterfactual-fixture.jsonl --predictions .tmp\react-real-vcs-100-gold\react-100-gold-counterfactual-parametric-predictions.jsonl --allow-non-cc0-dataset --output .tmp\react-real-vcs-100-gold\react-100-gold-counterfactual-parametric-report.json
python benchmarks\aippocampus\benchmark_vcs_future_event_recall.py --dataset .tmp\react-real-vcs-100-gold\react-100-gold-counterfactual-fixture.jsonl --predictions .tmp\react-real-vcs-100-gold\react-100-gold-counterfactual-overactive-predictions.jsonl --allow-non-cc0-dataset --output .tmp\react-real-vcs-100-gold\react-100-gold-counterfactual-overactive-report.json
```

The empty, closed-book, parametric public-memory, and overactive sanity-control arms are expected to exit non-zero. They are measured as separate arms and must not be merged into the source-window score.

## Uncertainty Semantics

Headline binomial rates below include `95%` Wilson confidence intervals and `n`. These intervals expose uncertainty around the deterministic controls; they do not make the curated React fixture a population-quality claim. A perfect `105/105` point estimate renders as `100.00% (95% Wilson CI 96.47%-100.00%, n=105)`, and `0/105` anti-drift violations render as `0.00% observed; 95% Wilson upper bound 3.53% (n=105)`.

## Precision Semantics

The headline `future_event_flag_precision` is the source-backed contract metric: a flag is a true positive only when it names a flag-worthy event and supplies the required source ids. The runner also exposes `diagnostic_event_identity_precision` for debugging predictions that find the right event id but fail the source-support contract. That diagnostic must not replace the headline precision gate.

This React run used full source ids only. Truncated, redacted, missing-source-id, and partial-support degradation cases are covered by the current runner/tests and should be reported in future degradation-specific dated measurements before making source-robustness claims.

The report includes `105` anti-drift negatives, but the fixture predates the machine tags `anti_drift_family_under_test` and `anti_drift_contrast_family`. Future adversarial reports should tag negative cross-family controls separately so cross-family false activations do not hide inside the aggregate false-positive total.

## Base Arm Results

| Arm | Predicted flags | Recall | Precision | F1 | False negatives | False positives | Anti-drift negatives | Anti-drift violation rate | Anti-drift pass | Source-support failures |
| --- | ---: | --- | --- | ---: | ---: | ---: | ---: | --- | --- | ---: |
| Source-window | 105 | 100.00% (95% Wilson CI 96.47%-100.00%, n=105) | 100.00% (95% Wilson CI 96.47%-100.00%, n=105) | 100.00% | 0 | 0 | 105 | 0.00% observed; 95% Wilson upper bound 3.53% (n=105) | 100.00% (95% Wilson CI 96.47%-100.00%, n=105) | 0 |
| Empty | 0 | 0.00% (95% Wilson CI 0.00%-3.53%, n=105) | undefined (n=0) | 0.00% | 105 | 0 | 105 | 0.00% observed; 95% Wilson upper bound 3.53% (n=105) | 100.00% (95% Wilson CI 96.47%-100.00%, n=105) | 0 |
| Closed-book source-stripped | 105 | 0.00% (95% Wilson CI 0.00%-3.53%, n=105) | 0.00% (95% Wilson CI 0.00%-3.53%, n=105) | 0.00% | 105 | 0 | 105 | 0.00% observed; 95% Wilson upper bound 3.53% (n=105) | 100.00% (95% Wilson CI 96.47%-100.00%, n=105) | 105 |
| Overactive all-flags sanity control | 210 | 100.00% (95% Wilson CI 96.47%-100.00%, n=105) | 50.00% (95% Wilson CI 43.30%-56.70%, n=210) | 66.67% | 0 | 105 | 105 | 100.00% (95% Wilson CI 96.47%-100.00%, n=105) | 0.00% (95% Wilson CI 0.00%-3.53%, n=105) | 0 |

Source-over-closed-book lift: recall `1.00`, precision `1.00`, F1 `1.00`, false-negative reduction `105`.

## Counterfactual Perturbation

The counterfactual fixture keeps the public event ids but replaces the required local source ids and local rationales. A source-backed system must follow the counterfactual source ids. A parametric public-memory control that keeps pointing to the original public source ids scores as unsupported.

| Arm | Predicted flags | Recall | Precision | F1 | False negatives | False positives | Anti-drift negatives | Anti-drift violation rate | Anti-drift pass | Source-support failures |
| --- | ---: | --- | --- | ---: | ---: | ---: | ---: | --- | --- | ---: |
| Counterfactual source-backed | 105 | 100.00% (95% Wilson CI 96.47%-100.00%, n=105) | 100.00% (95% Wilson CI 96.47%-100.00%, n=105) | 100.00% | 0 | 0 | 105 | 0.00% observed; 95% Wilson upper bound 3.53% (n=105) | 100.00% (95% Wilson CI 96.47%-100.00%, n=105) | 0 |
| Counterfactual empty | 0 | 0.00% (95% Wilson CI 0.00%-3.53%, n=105) | undefined (n=0) | 0.00% | 105 | 0 | 105 | 0.00% observed; 95% Wilson upper bound 3.53% (n=105) | 100.00% (95% Wilson CI 96.47%-100.00%, n=105) | 0 |
| Parametric public-memory control | 105 | 0.00% (95% Wilson CI 0.00%-3.53%, n=105) | 0.00% (95% Wilson CI 0.00%-3.53%, n=105) | 0.00% | 105 | 0 | 105 | 0.00% observed; 95% Wilson upper bound 3.53% (n=105) | 100.00% (95% Wilson CI 96.47%-100.00%, n=105) | 105 |
| Counterfactual overactive sanity control | 210 | 100.00% (95% Wilson CI 96.47%-100.00%, n=105) | 50.00% (95% Wilson CI 43.30%-56.70%, n=210) | 66.67% | 0 | 105 | 105 | 100.00% (95% Wilson CI 96.47%-100.00%, n=105) | 0.00% (95% Wilson CI 0.00%-3.53%, n=105) | 0 |

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
