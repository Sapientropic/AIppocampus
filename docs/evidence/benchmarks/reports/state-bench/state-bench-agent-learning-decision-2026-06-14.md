# STATE-Bench Agent Learning Decision - 2026-06-14

Role: evidence.

This is the #1043 / #1379 / #1381 closeout decision for the current STATE-Bench
Agent Learning Track attempt. It does not report a task score.

## Decision

Defer official submission and close the current owner track as currently not
feasible in this environment.

The repository already has the train-only AIppocampus adapter, matched
no-memory adapter, and one-domain run plan from the 2026-06-10 preflight. The
remaining blocker is external/configuration access to the official locked
evaluation client.

## Rechecked Sources

- Official repository: <https://github.com/microsoft/STATE-Bench>
- Agent Learning Track:
  <https://github.com/microsoft/STATE-Bench/blob/main/docs/AGENT_LEARNING_TRACK.md>
- Locked Evaluation Client:
  <https://github.com/microsoft/STATE-Bench/blob/main/docs/setup/eval-client.md>

Local recheck on 2026-06-14:

- `git ls-remote https://github.com/microsoft/STATE-Bench.git refs/heads/main`
  returned `a0ffc655e7a36c179bfd2b037a08b0f3d75c9431`.
- The Agent Learning Track still requires the official protocol shape:
  `--num-runs 5`, `--retrieve-learnings-top-k 3`, read-only
  `retrieve_learnings(query, top_k=3) -> list[str]`, and train-only learning
  extraction from `datasets/train_task_trajectories/`.
- The locked evaluation client still requires
  `STATE_BENCH_EVAL_ENDPOINT` and `STATE_BENCH_EVAL_DEPLOYMENTS`.

Current local environment:

- `STATE_BENCH_EVAL_ENDPOINT`: not configured.
- `STATE_BENCH_EVAL_DEPLOYMENTS`: not configured.
- `official_task_run_count`: `0`.

## Closeout Interpretation

This closes the current issue path as a documented defer decision:

- #1379: access blocker recorded; no fake one-domain run.
- #1381: defer decision recorded.
- #1043: official submission is not currently feasible from this environment.

Future work should be a new narrow official-run issue only after the locked eval
client endpoint and deployment names are available. That issue should run the
same domain/task/model/run-count for no-memory and AIppocampus arms before
claiming lift.

Cannot claim:

- official STATE-Bench score;
- Agent Learning lift;
- matched one-domain task quality;
- leaderboard readiness;
- STATE-Bench SOTA or external memory-system superiority.
