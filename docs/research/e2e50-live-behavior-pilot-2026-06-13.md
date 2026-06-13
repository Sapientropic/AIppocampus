# E2E50 Live-Model Behavior Pilot, 2026-06-13

This report records a public-safe model-backed behavior layer for #1322. It
uses the checked-in 50-case E2E50 silent-constraint pack and compares two arms:

- baseline minimal context;
- AIppocampus packet-assisted context.

The run uses public/synthetic fixture data only. It does not use private
history, raw provider payloads, local paths, credentials, or live host state.

## Command

```powershell
$env:PYTHONPATH='skills/aippocampus/scripts'; python benchmarks/aippocampus/benchmark_e2e50_behavior_live.py --output docs/research/e2e50-live-behavior-pilot-2026-06-13.json --json
```

## Configuration

- Provider/model: DeepSeek `deepseek-v4-flash`
- Calls: 100 model calls, 50 cases x 2 arms
- Settings: temperature not sent (`temperature_requested=null`,
  `temperature_sent=false`), thinking `enabled`, reasoning effort `high`, no
  explicit max-token cap
- Usage: 79,245 prompt tokens, 29,689 completion tokens, 108,934 total tokens,
  23,105 reasoning tokens
- Estimated cost: `$0.017300` using DeepSeek V4-Flash pricing checked
  2026-06-13

## Results

| Arm | Correct rate | Useful next-action rate | Manual search | Source reopen | Wrong actions | Over-constrained | Negative-control rate |
|---|---:|---:|---:|---:|---:|---:|---:|
| Baseline minimal context | 0.94 | 0.94 | 0 | 7 | 0 | 0 | 1.00 |
| AIppocampus packet | 1.00 | 1.00 | 0 | 5 | 0 | 0 | 1.00 |

Observed lift:

- Correct-rate lift: `+0.06`
- Useful next-action lift: `+0.06`
- Wrong-action delta: `0`
- Over-constrained delta: `0`

Family readout:

- AIppocampus packet scored `1.0` across every public case family.
- Baseline also scored `1.0` for most families, but reached only `0.666667`
  on `behavior_backed_rejected_route`.
- Negative controls stayed clean in both arms: `negative_control_correct_rate=1.0`.

## Interpretation

This is positive but modest behavior evidence. The AIppocampus packet arm
improves the run, but the baseline is already strong under this synthetic
action-code prompt. The result supports keeping a model-backed public E2E50
behavior runner and using it as a promotion guard; it does not support default
foreground adoption by itself.

The first full run exposed a runner vocabulary gap for
`summary_overhang_trap_avoided`; the final reported run includes the vocabulary
guard in `tests/aippocampus/test_benchmark_e2e50_behavior_live.py` so fixture
required/forbidden codes cannot silently become unscoreable.

## Claim Boundary

Can claim:

- a public-safe live-model E2E50 behavior runner exists;
- baseline and AIppocampus packet arms were scored on the same 50 public cases;
- model outputs were scored as action choices rather than replayed fixture
  behavior traces;
- provider/model/settings/usage/cost are recorded.

Cannot claim:

- broad E2E50 benchmark quality;
- private-history behavior lift;
- live host behavior lift;
- default foreground packet adoption;
- provider-general behavior quality;
- source truth from packet summaries.
