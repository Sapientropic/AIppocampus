# E2E50 Live-Model Label-Oracle Diagnostic, 2026-06-13

This report records a public-safe model-backed diagnostic run over the checked-in
50-case E2E50 silent-constraint pack. After follow-up audit, it should be read as
a labeled action-choice / runner-wiring diagnostic, not as completed #1322
behavior validation.

The original prompt compared two arms:

- baseline minimal context;
- AIppocampus packet-assisted context.

The run uses public/synthetic fixture data only. It does not use private
history, raw provider payloads, local paths, credentials, or live host state.

## Audit Correction

This run exposed a setup flaw: the baseline prompt included `case_family`, a
family-specific scenario sentence, the full action-code glossary, and an
`AIppocampus packet` shell even when the packet was marked absent. That makes the
baseline a labeled-choice prompt rather than a clean no-memory / no-AIppocampus
baseline.

The observed `0.94` baseline score is therefore likely inflated by prompt
structure. The `+0.06` assisted delta is not valid evidence of foreground
continuity lift, and this report does not close #1322. A valid #1322 run needs a
separate public surface-task fixture that hides case-family labels,
family-specific scenario text, and gold-like action labels from the baseline arm.

## Command

```powershell
$env:PYTHONPATH='skills/aippocampus/scripts'; python benchmarks/aippocampus/benchmark_e2e50_behavior_live.py --prompt-mode label-oracle --output docs/research/e2e50-live-behavior-pilot-2026-06-13.json --json
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

These are diagnostic results under the flawed labeled-choice setup:

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

This is not positive behavior-lift evidence. The AIppocampus packet arm scores
higher in this run, but the baseline is already strong because the prompt
reveals the case type and action vocabulary. The result supports keeping the
model-backed runner/report path as a diagnostic harness only.

The first full run exposed a runner vocabulary gap for
`summary_overhang_trap_avoided`; the final reported run includes the vocabulary
guard in `tests/aippocampus/test_benchmark_e2e50_behavior_live.py` so fixture
required/forbidden codes cannot silently become unscoreable.

## Claim Boundary

Can claim:

- a public-safe live-model E2E50 labeled-choice diagnostic runner exists;
- live model calls, JSON parsing, action-choice scoring, provider usage, and
  sanitized report writing were exercised;
- baseline label leakage was detected and recorded;
- model outputs were scored as action choices rather than replayed fixture
  behavior traces;
- provider/model/settings/usage/cost are recorded.

Cannot claim:

- broad E2E50 benchmark quality;
- clean no-memory baseline quality;
- AIppocampus-assisted behavior lift from this run;
- #1322 behavior-validation closeout;
- private-history behavior lift;
- live host behavior lift;
- default foreground packet adoption;
- provider-general behavior quality;
- source truth from packet summaries.
