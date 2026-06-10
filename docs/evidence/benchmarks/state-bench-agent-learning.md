# STATE-Bench Agent Learning Feasibility

This page owns the #1043 feasibility boundary for evaluating AIppocampus on the
STATE-Bench Agent Learning Track. It records the adapter path, local artifact
policy, and why AIppocampus cannot yet claim an official STATE-Bench score or
agent-learning lift.

## Benchmark Interpretation

| Field | Current answer |
| --- | --- |
| Question answered | Can AIppocampus prepare a train-only Agent Learning adapter shape without leaking held-out/test-oracle or raw trajectory material? |
| Primary metric | Adapter/readiness feasibility: observed train trajectories, extracted public-safe learning count, retrieval-contract comparison, and `official_task_run_count`. |
| Can claim | Train-only adapter generation and public-safe no-score feasibility reporting are implemented. |
| Still cannot claim | Official STATE-Bench score, Agent Learning lift, leaderboard readiness, held-out task quality, or full submission compatibility. |
| Best next benchmark | One-domain matched no-memory vs AIppocampus task run under the official harness/settings. |

Decision: suitable as a staged external benchmark adapter, but **not ready for
official submission**. The repository now has a deterministic feasibility
runner that can inspect an operator-provided STATE-Bench checkout, derive
train-only learning strings, and generate a read-only
`retrieve_learnings(query, top_k=3) -> list[str]` adapter. It has not run the
official simulator/judge, held-out test tasks, or matched no-memory task
baseline.

## Official Sources

- Repository: <https://github.com/microsoft/STATE-Bench>
- Agent Learning Track:
  <https://github.com/microsoft/STATE-Bench/blob/main/docs/AGENT_LEARNING_TRACK.md>
- Submit docs:
  <https://github.com/microsoft/STATE-Bench/blob/main/docs/SUBMIT.md>
- Leaderboard: <https://microsoft.github.io/STATE-Bench/leaderboard/>

Verified source facts on 2026-06-10:

- `microsoft/STATE-Bench` `main` HEAD was
  `83cb96de5429c43adfdb5cb9b6785439e937a3ca`; GitHub reported the repository
  pushed at 2026-06-08T18:53:53Z.
- The Agent Learning Track exposes reusable learning through
  `retrieve_learnings(query, top_k=3) -> list[str]`.
- Learning extraction should use `datasets/train_task_trajectories/<domain>/`.
  Held-out test task definitions and environments must not be used as oracle
  inputs for learning extraction.
- Official domains are `travel`, `customer_support`, and
  `shopping_assistant`; docs state 100 train trajectories and 50 held-out test
  tasks per domain.
- Protocol-compatible settings include `--num-runs 5`,
  `--retrieve-learnings-top-k 3`, scored trajectories, and per-domain
  `metrics.json` outputs before submission.

## Runner

The feasibility runner lives at:

```powershell
python benchmarks\aippocampus\benchmark_state_bench_agent_learning.py --json
```

With no local STATE-Bench checkout, it emits a public-safe no-go plan:
`status=skipped_missing_state_bench_checkout`,
`official_submission_decision=no_go_missing_state_bench_checkout`, and no
score/lift claim.

To inspect a local ignored upstream checkout and generate adapter artifacts:

```powershell
git clone --depth 1 https://github.com/microsoft/STATE-Bench.git .tmp\state-bench-upstream
python benchmarks\aippocampus\benchmark_state_bench_agent_learning.py `
  --state-bench-root .tmp\state-bench-upstream `
  --domain customer_support `
  --write-adapter `
  --adapter-output-dir .tmp\state-bench-aippocampus\agents `
  --learnings-output .tmp\state-bench-aippocampus\learnings.json `
  --output .tmp\state-bench-aippocampus\feasibility.json `
  --json
```

Generated adapter files and learning JSON belong under `.tmp/` or another
ignored operator-controlled path. Do not commit upstream STATE-Bench datasets,
raw train trajectories, generated learning files, official outputs, provider
keys, or local absolute paths.

## 2026-06-10 Local Feasibility Slice

Command shape:

```powershell
python benchmarks\aippocampus\benchmark_state_bench_agent_learning.py --state-bench-root .tmp\state-bench-upstream --domain customer_support --write-adapter --adapter-output-dir .tmp\state-bench-aippocampus\agents --learnings-output .tmp\state-bench-aippocampus\learnings.json --output .tmp\state-bench-aippocampus\feasibility.json --json
```

Sanitized result:

- `status=adapter_dry_run_ready`.
- `official_submission_decision=no_go_adapter_only_no_official_run`.
- `observed_train_trajectory_count=100` for `customer_support`.
- `extracted_learning_count=100`.
- `source_raw_text_field_count_observed_but_not_emitted=795`.
- Adapter retrieval-contract comparison used 3 train-derived fixture queries:
  no-memory retrieved 0 learnings; AIppocampus retrieval returned 9 total
  learning strings across 3 nonempty cases.
- `official_task_run_count=0`.

Interpretation: the adapter shape and train-only extraction path are real. This
is still **not** a STATE-Bench task-performance result, because it does not run
held-out tasks, the locked simulator/judge, scored trajectories, or a matched
no-memory task baseline.

## Claim Boundary

Can claim:

- A local, ignored STATE-Bench checkout at the verified commit can feed a
  train-only AIppocampus learning extractor.
- The generated adapter exposes the official read-only
  `retrieve_learnings(query, top_k=3) -> list[str]` shape.
- The feasibility report stays sanitized: raw trajectory text, raw learning
  text, private registry text, provider keys, and local absolute paths are not
  emitted.

Cannot claim:

- Official STATE-Bench score.
- Agent Learning Track lift over no-memory.
- Leaderboard readiness or submission compatibility.
- Held-out task quality.
- End-to-end task performance, UX, cost, or pass-rate improvement.
- SOTA or external memory-system superiority.

## Next Slice

The next useful slice is a bounded one-domain run that keeps the same model,
harness, `--num-runs`, `--retrieve-learnings-top-k`, worker settings, and
pricing assumptions for both no-memory and AIppocampus-enabled agents. Promote
only a sanitized report with command shape, model, domain, run count, cost,
failures, output paths, and metrics. Attempt full official submission only
after the one-domain result is clean and the claim boundary is reviewed.
