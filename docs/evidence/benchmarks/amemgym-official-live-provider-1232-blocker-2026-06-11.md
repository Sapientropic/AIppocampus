# AMemGym Official Live-Provider #1232 Route Blocker - 2026-06-11

Role: dated closeout note for #1232.
Status: `provider-route-blocked`, not a completed AMemGym score.

## Source And Run Boundary

- Official upstream commit:
  `AGI-Eval-Official/amemgym@ffcd18857a3e2b2c61f00730ebdec676e27d3e87`.
- Dataset/config: full public `v1.base`, 20 public user items,
  `item_ids_sha1=4de568295e151638`.
- Arm/provider: `official_native_full_history` through the OpenRouter bridge,
  pinned to the generated `native-gpt-4.1-mini-openrouter` agent config.
- Shared provider execution budget: declared before execution with
  `max_provider_calls=5000`, `max_provider_total_tokens=50000000`,
  `provider_cost_unknown=true`, and a public-safe budget checkpoint.
- Raw official rows, model transcripts, local absolute paths, provider
  credentials, provider user ids, and raw provider error payloads remain
  uncommitted.

The attempted resume command shape was:

```powershell
python benchmarks\aippocampus\benchmark_amemgym_official.py `
  --runner uv `
  --provider openrouter `
  --arm official_native_full_history `
  --run overall,upperbound,random `
  --resume `
  --checkpoint .tmp\amemgym-official\v1.base\issue-1232-live-after-recharge\checkpoint.json `
  --provider-budget-checkpoint .tmp\amemgym-official\v1.base\issue-1232-live-after-recharge\provider-budget.json `
  --provider-timeout-seconds 10800 `
  --max-provider-calls 5000 `
  --max-provider-total-tokens 50000000 `
  --provider-cost-unknown `
  --output .tmp\amemgym-official\v1.base\issue-1232-live-after-recharge\summary.json `
  --json
```

## Observed State

The public-safe post-attempt summary generated at `2026-06-11T20:45:42Z`
reported `status=partial_official_outputs`, `ok=true`, and
`fixed_arm_execution.status=partial_resumable_outputs`.

| Surface | State | Counts |
| --- | --- | --- |
| `overall` | partial | 6 of 20 user items complete; 7 result files; 760 of 770 observed score leaves in the partial output tree. |
| `upperbound` | partial | 38 of 882 choice evaluations complete; one result file; no complete utilization metrics file. |
| `random` | complete | One random metrics file present; `official_random=0.23076190476190475`. |

The resume did not produce a new official score. It entered the same partial
`overall` item and continued to hit provider-side refusal before any new
claimable result file was written.

## Provider Route Diagnosis

The first #1232 attempt before account top-up reproduced the prior provider
credit / max-token ceiling: the official agent config requests up to `8192`
tokens per call, and OpenRouter refused the request before completion.

After the account was topped up, the blocker changed: OpenRouter returned
provider policy refusals for the same pinned official request shape. The local
log shows repeated `403` provider-policy errors after the #1232 restart.

The post-interruption diagnosis separated route policy from AMemGym content:

- A harmless fixed prompt, `Reply with exactly OK.`, returned `403` for
  `gpt-4.1`, `openai/gpt-4.1`, and `openai/gpt-4.1-mini`.
- The same harmless prompt returned `200` for non-OpenAI OpenRouter routes
  including a Qwen route and a Mistral route.
- A Gemini route returned the same `403` provider-policy refusal.
- The runner-level route preflight added after this diagnosis checks only the
  required official routes before starting AMemGym subprocesses. On the current
  public `overall` condition it reports
  `status=skipped_provider_route_preflight_failed` with:
  - `gpt-4.1` for `environment_low_temp`: `403`;
  - `openai/gpt-4.1-mini` for `agent`: `403`;
  - OpenRouter metadata summarized as `available=2`, `is_byok=false`, and no
    raw provider user id or prompt body emitted.

Interpretation:

- The live-provider blocker is no longer only a missing-credit problem.
- The blocker is not explained by the AMemGym public prompt content, because
  unrelated harmless prompts fail on the same OpenAI routes.
- The blocker is not explained by OpenRouter being globally unusable, because
  at least two non-OpenAI routes accepted the same harmless prompt.
- The pinned official Native/OpenRouter condition cannot currently complete the
  remaining fixed-arm calls because its required OpenAI-family routes are
  provider-policy blocked for this account / route / origin condition.
- Lowering `max_tokens`, choosing a different provider/model route, or changing
  the official agent config would be a new benchmark condition and must be
  recorded as such before any score is compared.

## Runner Change

`benchmarks/aippocampus/benchmark_amemgym_official.py` now performs a tiny
OpenRouter route preflight after provider-budget validation and before any
official subprocess starts. This avoids burning time in AMemGym's exponential
provider retry loop when the required route is already policy-blocked.

The preflight is intentionally narrow:

- `overall` probes the evaluated agent model and the low-temperature
  environment simulator model;
- `upperbound` probes the evaluated agent model;
- `random` does not probe a provider route;
- probe reports include only model ids, roles, status codes, sanitized
  OpenRouter metadata, and error summaries.

## Closeout Decision

#1232 is closed as `provider-route-blocked`.

This is the right state because the issue requested either a completed
fixed-arm score or a first-class blocker trail. The run trail now shows:

- official checkout, public dataset, generated agent config, and prior partial
  outputs are available;
- the shared provider execution budget preflight works before live execution;
- live provider route preflight now identifies the OpenAI-family route block
  before official AMemGym subprocesses start;
- `random` is complete, but `overall` and `upperbound` remain partial;
- the post-top-up live resume is blocked by provider policy refusal on required
  model routes, not by missing local files, missing dataset, or AMemGym prompt
  content.

## Required Before Any Score Claim

Before any AMemGym live-provider Current Claim Snapshot row is added, produce a
later dated note with:

- the upstream commit and dataset/config identifiers;
- the provider/model route and whether it is the same pinned condition or a new
  benchmark condition;
- complete `overall`, `upperbound`, and `random` outputs for one fixed arm;
- sanitized `Overall`, `UB`, `Random`, normalized `Memory`, and cost/latency or
  explicit unavailable-provider-field reason;
- no committed raw official rows, model transcripts, local absolute paths,
  provider credentials, provider user ids, or raw billing payloads;
- a parity-arm decision after the fixed arm passes review.
