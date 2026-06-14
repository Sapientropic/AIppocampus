# Benchmark Evidence Maturity Vocabulary

Role: canonical vocabulary and closure-audit ledger for benchmark/evidence
issue closeouts.
Status: current owner for deciding whether a closed benchmark/evidence issue is
a harness, pilot, contract fixture, blocker, or completed score.

Use this page when a closed issue title can be read too strongly after the
fact. It complements the runner-level maturity gates in
[`benchmarks/design/benchmark-maturity-gates.md`](benchmarks/design/benchmark-maturity-gates.md);
it does not replace current numeric claims in
[`current-claims.md`](current-claims.md).

## Vocabulary

| State | Meaning | Claim boundary |
| --- | --- | --- |
| `harness-ready` | Runner, adapter, schema, or command path exists. | No quality score is claimed. Cite as implementation readiness only. |
| `pilot-run` | Small, partial, local, or budget-bounded run produced useful evidence. | Directional evidence only; do not promote it into a representative benchmark result. |
| `contract-smoke` | Deterministic or public-safe fixture exercises the intended contract. | Red-line or schema behavior can be cited; public cohort quality, private-history quality, and live lift cannot. |
| `blocker-recorded` | A run could not complete, but the blocker, partial state, and next command or owner are reproducible. | Treat as progress and boundary evidence, not a failed or completed score. |
| `completed-score` | Dated run records sample count, command/report owner, warnings, privacy/local-path scan boundary, and claim limits. | May support the exact scoped score row only; it still does not imply adjacent QA, live, or superiority claims. |

Existing benchmark reports may use `contract_smoke` in JSON fields. In prose
closeout ledgers, use `contract-smoke` for readability and link back to the
report if the machine field matters.

## Promotion Rules

- Only `completed-score` can be promoted as a numeric score in
  [`current-claims.md`](current-claims.md).
- `harness-ready`, `pilot-run`, `contract-smoke`, and `blocker-recorded` may be
  useful current boundaries, but they must not be described as completed
  quality scores.
- Private/local artifacts can support dogfood or aggregate blocker evidence,
  but they are not a public reopenable artifact trail unless a public-safe
  trail is explicitly published.
- When closing a benchmark/evidence issue below `completed-score`, name the next
  owner issue or state that a future promotion owner is required.
- If a result is stale, partial, private-only, or produced under a different
  arm, keep it visible as evidence but do not let the issue title become the
  claim.

## 2026-06 Closure Audit

This audit records the true closeout state for a set of useful but easy to
over-read benchmark/evidence closures. It is a navigation ledger, not a
replacement for the linked reports.

| Issue | Closeout state | Reusable asset | Must not claim | Next owner |
| --- | --- | --- | --- | --- |
| [#958](https://github.com/Sapientropic/AIppocampus/issues/958) AMemGym official-runner evidence | `blocker-recorded` | Official AMemGym live-provider blocker report and command boundary in [`amemgym-official-live-provider-blocker-2026-06-09.md`](benchmarks/reports/amemgym/amemgym-official-live-provider-blocker-2026-06-09.md). | Completed live-provider AMemGym score, leaderboard parity, or quality from local-scripted/protocol compatibility. | Superseded by [#1083](https://github.com/Sapientropic/AIppocampus/issues/1083) blocker/progress audit; current open owner is [#1232](https://github.com/Sapientropic/AIppocampus/issues/1232). |
| [#982](https://github.com/Sapientropic/AIppocampus/issues/982) Field Continuity Eval design | `contract-smoke` | Public-track design, fixture schema, runner, and negative-control fixture reports in [`field-continuity-eval-design.md`](benchmarks/field-continuity-eval-design.md) and [`field-continuity-fixture-report.md`](benchmarks/reports/field-journey/field-continuity-fixture-report.md). | Real-history continuity quality, universal fresh-thread recall, live semantic-model quality, or Beta classifier approval. | Future public-cohort promotion needs a new owner before a score claim. |
| [#994](https://github.com/Sapientropic/AIppocampus/issues/994) E2E50 seed pack shortfall | `contract-smoke` | Historical public-safe 20-case scaffold; current public behavior-pack coverage is the 50-case #279 row in Current Claims / public-readiness verification. | Representative E2E50 quality, private-history behavior lift, completed private 20-case quality, or live/representative 50-case quality. | Broader E2E50 owner remains [#279](https://github.com/Sapientropic/AIppocampus/issues/279); private/local shortfall was audited by [#1086](https://github.com/Sapientropic/AIppocampus/issues/1086). |
| [#998](https://github.com/Sapientropic/AIppocampus/issues/998) Claude Code dogfood | `pilot-run` | Sanitized Claude Code local-history / MCP dogfood evidence in [`readiness/claude-code-dogfood-2026-06-09.md`](readiness/claude-code-dogfood-2026-06-09.md) plus checked synthetic cross-agent smokes. | Claude Code hooks, persistent local MCP config health, cross-device sync, hosted/cloud continuity, or broad private-history generality. | Persistent MCP diagnostic blocker is tracked by [#1235](https://github.com/Sapientropic/AIppocampus/issues/1235). |
| [#1082](https://github.com/Sapientropic/AIppocampus/issues/1082) State-dependent preactivation | `contract-smoke` | Public-safe deterministic warm-ambient preactivation fixture in [`state-dependent-preactivation-2026-06-10.md`](benchmarks/reports/fresh-thread/state-dependent-preactivation-2026-06-10.md). | Live foreground preactivation rollout, proactive memory truth, live latency savings, ADHD productivity lift, or private-history quality. | Future public-cohort or live-host promotion needs a new owner. |
| [#1083](https://github.com/Sapientropic/AIppocampus/issues/1083) AMemGym live-provider fixed arm | `blocker-recorded` | Checkpoint/resume audit in [`amemgym-official-live-provider-1083-checkpoint-2026-06-10.md`](benchmarks/reports/amemgym/amemgym-official-live-provider-1083-checkpoint-2026-06-10.md): `overall` remains partial at 6/20 user items and `upperbound` partial at 38/882 choice evaluations. | Completed AMemGym score, normalized `Memory`, parity-arm readiness, or product quality from partial/checkpoint output. | Current open owner is [#1232](https://github.com/Sapientropic/AIppocampus/issues/1232). |
| [#1232](https://github.com/Sapientropic/AIppocampus/issues/1232) AMemGym live-provider fixed-arm closeout | `provider-route-blocked` | Post-top-up resume audit and route diagnosis in [`amemgym-official-live-provider-1232-blocker-2026-06-11.md`](benchmarks/reports/amemgym/amemgym-official-live-provider-1232-blocker-2026-06-11.md): provider-budget preflight passed, then the new route preflight showed the required OpenAI-family routes fail even on a harmless fixed prompt; `overall` remains partial at 6/20 user items and `upperbound` partial at 38/882 choice evaluations. | Completed AMemGym score, normalized `Memory`, parity-arm readiness, product quality from partial/checkpoint output, or treating provider-budget / route-preflight adoption as a score. | Future promotion needs a new owner with a declared provider/model condition and complete fixed-arm outputs. |
| [#1085](https://github.com/Sapientropic/AIppocampus/issues/1085) LongMemEval-S 500Q retrieval-only diagnostic | `completed-score` for the sanitized retrieval-only summary; public artifact trail pending | Current 500-question retrieval-only score row in [`longmemeval.md`](benchmarks/longmemeval.md#current-published-result) and [`current-claims.md`](current-claims.md). | QA answer quality, judge score, LongMemEval-V2 quality, SOTA/superiority, exact-line citation being solved, or public reopenability of the full generated artifact trail. | Public reopenable artifact trail is tracked by [#1234](https://github.com/Sapientropic/AIppocampus/issues/1234). |
| [#1086](https://github.com/Sapientropic/AIppocampus/issues/1086) E2E50 private/local shortfall | `blocker-recorded` | Sanitized private/local follow-up in [`e2e50-private-local-seed-followup-2026-06-10.md`](benchmarks/reports/e2e50/e2e50-private-local-seed-followup-2026-06-10.md): wide scan found 23 candidates, but annotation retained only 7 control/seed cases against the 20-case private target. | Private-history behavior lift, completed private 20-case quality, representative E2E50 quality, live/representative 50-case quality, or live host behavior. | Broader E2E50 owner remains [#279](https://github.com/Sapientropic/AIppocampus/issues/279). |
| [#1092](https://github.com/Sapientropic/AIppocampus/issues/1092) LongMemEval-S semantic rerank arm | `pilot-run` | 25-question semantic LLM rerank pilot analysis in [`longmemeval-semantic-rerank-analysis-2026-06-10.json`](benchmarks/reports/longmemeval/semantic-cache/longmemeval-semantic-rerank-analysis-2026-06-10.json) and bounded summary in [`longmemeval.md`](benchmarks/longmemeval.md#current-published-result). | 500-question LLM-reranker quality, default exact-line citation quality, answer-generation quality, provider-independent quality, or LongMemEval QA/SOTA claims. | Broader exact-line gap owner is [#1193](https://github.com/Sapientropic/AIppocampus/issues/1193). |

## Closeout Checklist

Before closing a future benchmark/evidence issue, record:

- state from the vocabulary above;
- public/private/source boundary;
- sample count and command/report owner when a score is claimed;
- blocker and next command when a run is incomplete;
- next owner issue for any deferred promotion;
- exact `must not claim` language for adjacent scores, live behavior, private
  generality, source truth, or artifact reopenability.
