# E2E50 Blind-Surface Live Behavior, 2026-06-13

This report records the corrected public-safe model-backed behavior run for
#1322. It uses the checked-in 50-case E2E50 pack, but the live prompts are
rendered through a blind surface:

- the baseline arm does not see `case_family`, expected behavior codes, source
  hashes, family-specific scenario labels, action-code glossary, or an empty
  AIppocampus packet shell;
- the AIppocampus arm sees the same visible task plus a compact source-backed
  packet with a recommended next-action id and avoid ids;
- model outputs are scored as generated next-action choices.

The run uses public/synthetic fixture data only. It does not use private
history, raw provider payloads, local paths, credentials, or live host state.

## Command

```powershell
$env:PYTHONPATH='skills/aippocampus/scripts'; python benchmarks/aippocampus/benchmark_e2e50_behavior_live.py --output docs/research/e2e50-blind-surface-live-behavior-2026-06-13.json --json
```

## Configuration

- Provider/model: DeepSeek `deepseek-v4-flash`
- Calls: 100 model calls, 50 cases x 2 arms
- Prompt mode: `blind-surface`
- Settings: temperature not sent (`temperature_requested=null`,
  `temperature_sent=false`), thinking `enabled`, reasoning effort `high`, no
  explicit max-token cap
- Usage: 45,087 prompt tokens, 32,354 completion tokens, 77,441 total tokens,
  25,771 reasoning tokens
- Estimated cost: `$0.011367` using DeepSeek V4-Flash pricing checked
  2026-06-13

## Results

| Arm | Correct rate | Useful next-action rate | Manual search | Source reopen | Wrong actions | Safe non-answer | Over-constrained | Negative-control rate |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Baseline minimal context | 0.42 | 0.42 | 10 | 21 | 0 | 29 | 0 | 1.00 |
| AIppocampus packet | 1.00 | 1.00 | 0 | 5 | 0 | 0 | 0 | 1.00 |

Observed lift:

- Correct-rate lift: `+0.58`
- Useful next-action lift: `+0.58`
- Manual-search delta: `-10`
- Safe-but-non-answer delta: `-29`
- Wrong-action delta: `0`
- Over-constrained delta: `0`

Family readout:

- AIppocampus packet scored `1.0` across every public case family.
- Baseline stayed clean on negative controls and transient/no-special-action
  cases, but dropped on memory-dependent families: binding constraints,
  rejected routes, currentness, scope narrowing, and source-reopen cases.
- Baseline failures were mostly safe non-answers (`open_source_first` or
  `manual_search`), not unsafe wrong actions.

## Interpretation

This is a positive small public live-behavior result for #1322: the packet arm
turns many safe-but-unresolved baseline choices into useful next actions without
introducing wrong actions, over-constraint, invalid output, or private-context
red lines.

It does not prove broad product quality. The surface is still synthetic and the
AIppocampus packet gives compact direct route guidance. Treat this as a valid
public behavior-validation slice, not as default foreground adoption or
private-history quality evidence.

## Claim Boundary

Can claim:

- a public-safe live-model blind-surface E2E50 behavior runner exists;
- baseline and AIppocampus packet arms were scored on the same 50 public cases;
- the corrected baseline no longer receives case-family labels, expected codes,
  source hashes, action-code glossary, or empty packet shell;
- model outputs were scored as generated next-action choices;
- provider/model/settings/usage/cost are recorded.

Cannot claim:

- broad E2E50 benchmark quality;
- private-history behavior lift;
- live host behavior lift;
- default foreground packet adoption;
- provider-general behavior quality;
- source truth from packet summaries.
