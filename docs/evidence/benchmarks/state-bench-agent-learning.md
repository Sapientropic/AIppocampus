# STATE-Bench Agent Learning Feasibility

This page owns the #1043 feasibility boundary for evaluating AIppocampus on the
STATE-Bench Agent Learning Track. It records the adapter path, local artifact
policy, and the material limits around official STATE-Bench score and
agent-learning lift claims.

## Benchmark Interpretation

| Field | Current answer |
| --- | --- |
| Question answered | Can AIppocampus prepare a train-only Agent Learning adapter shape without leaking held-out/test-oracle or raw trajectory material? |
| Primary metric | Adapter/readiness feasibility: observed train trajectories, extracted public-safe learning count, retrieval-contract comparison, and `official_task_run_count`. |
| Can claim | Train-only adapter generation and public-safe no-score feasibility reporting are implemented. |
| Important limits | No official STATE-Bench score, Agent Learning lift, leaderboard readiness, held-out task quality, or full submission compatibility yet. |
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

## 2026-06-10 One-Domain Execution Preflight

Machine-readable report:
`docs/evidence/benchmarks/reports/state-bench/state-bench-agent-learning-preflight-2026-06-10.json`.

Official source snapshot:

- `git ls-remote https://github.com/microsoft/STATE-Bench.git HEAD
  refs/heads/main` returned
  `83cb96de5429c43adfdb5cb9b6785439e937a3ca` for both HEAD and `main`.
- A default Windows checkout failed the official protocol prompt hash check
  because prompt files were present with CRLF working-tree line endings. The
  preflight therefore used an ignored clone whose prompt files checked out with
  LF line endings.

Preflight command shape:

```powershell
python benchmarks\aippocampus\benchmark_state_bench_agent_learning.py --state-bench-root .tmp\state-bench-upstream-lf --domain customer_support --write-adapter --adapter-output-dir .tmp\state-bench-upstream-lf\agents --learnings-output .tmp\state-bench-upstream-lf\agents\learnings.json --prepare-matched-run --matched-run-output-dir .tmp\state-bench-aippocampus\outputs --matched-task-ids 1-return_partial_order --agent-model-name gpt-5.4-mini --output docs\evidence\benchmarks\reports\state-bench\state-bench-agent-learning-preflight-2026-06-10.json --json
```

Sanitized result:

- `matched_one_domain_preflight.status=blocked_missing_locked_eval_client`.
- `official_submission_decision=no_go_missing_locked_eval_client`.
- Both matched adapters were generated into the ignored STATE-Bench checkout:
  `AIppocampusStateBenchAgent` and `NoMemoryStateBenchAgent`.
- Planned bounded task subset: `customer_support`, task
  `1-return_partial_order`, `--num-runs 5`, `--retrieve-learnings-top-k 3`,
  `--num-workers 1`.
- Agent client readiness was present for the attempted OpenAI built-in-agent
  path, but the locked evaluation client was not configured:
  `STATE_BENCH_EVAL_ENDPOINT` and `STATE_BENCH_EVAL_DEPLOYMENTS` were missing.
- `official_task_run_count=0`.

Manual official preflight attempts:

```powershell
uv sync
uv run python -m state_bench.scripts.run_batch --domain customer_support --tasks 1-return_partial_order --agent-class NoMemoryStateBenchAgent --agent-provider openai --agent-api-key-var STATE_BENCH_AGENT_API_KEY --agent-model-name gpt-5.4-mini --num-runs 1 --retrieve-learnings-top-k 3 --num-workers 1 --output-dir ..\state-bench-aippocampus\outputs\customer_support-no-memory-preflight --no-score
```

Observed blockers:

- In the default Windows checkout, `run_batch` stopped at protocol prompt hash
  mismatches caused by CRLF working-tree line endings.
- In the LF checkout, `run_batch` progressed past prompt validation and adapter
  loading, then stopped before task execution with:
  `Azure OpenAI endpoint required. Set STATE_BENCH_EVAL_ENDPOINT environment
  variable or pass endpoint parameter.`

Decision at the time: this slice turned the one-domain attempt into a concrete
operator blocker and reproducible run plan. It still did not provide a matched
no-memory vs AIppocampus task score. The 2026-06-14 recheck below supersedes
the "keep open" posture: the current #1043 path is closed as a documented
defer decision, and a new narrow official-run issue should be opened only after
the locked evaluation client endpoint/deployment names are available.

## 2026-06-14 Defer Decision

Decision report:
[`state-bench-agent-learning-decision-2026-06-14.md`](state-bench-agent-learning-decision-2026-06-14.md).
Machine-readable report:
[`state-bench-agent-learning-decision-2026-06-14.json`](state-bench-agent-learning-decision-2026-06-14.json).

Recheck summary:

- `microsoft/STATE-Bench` `main` was rechecked at
  `a0ffc655e7a36c179bfd2b037a08b0f3d75c9431`.
- The official Agent Learning Track still uses train-only learning extraction,
  `--num-runs 5`, and `--retrieve-learnings-top-k 3`.
- The locked evaluation client still requires `STATE_BENCH_EVAL_ENDPOINT` and
  `STATE_BENCH_EVAL_DEPLOYMENTS`.
- This environment does not have those two variables configured, and
  `official_task_run_count` remains `0`.

Closeout decision: defer official submission and close the current #1043 issue
path as **currently not feasible from this environment**. Reopen as a new narrow
official-run issue only when the locked eval client endpoint/deployment names
are available, then run the same task/domain/model/run-count for no-memory and
AIppocampus arms before claiming lift.

## Claim Shape

Supports:

- A local, ignored STATE-Bench checkout at the verified commit can feed a
  train-only AIppocampus learning extractor.
- The generated adapter exposes the official read-only
  `retrieve_learnings(query, top_k=3) -> list[str]` shape.
- The feasibility report stays sanitized: raw trajectory text, raw learning
  text, private registry text, provider keys, and local absolute paths are not
  emitted.

Important limits:

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
