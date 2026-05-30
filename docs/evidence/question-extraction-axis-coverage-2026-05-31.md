# Question Extraction Axis Coverage Evidence - 2026-05-31

Issue: GitHub #153, `question_extraction` often omits richer question-map
fields under the default live run.

## Command Shape

Both runs used the same live no-write shape:

```powershell
python skills\aippocampus\scripts\subconscious_jobs.py --job question_extraction --model-route fast --max-turns 80 --max-steps 4 --min-tool-steps 1 --samples-per-job 1 --concurrency 1 --no-write --json
```

- Route: `fast` / `deepseek-v4-flash`
- Temperature: default `0.2`
- Writes: disabled
- Privacy boundary: aggregate field-presence counts only. Raw prompts, source
  text, local paths, session ids, and credentials are intentionally omitted.

## Result

| Run | Validated findings | Question candidates | `what_features` | `where_context` | `phase_context` | Complete core axes | Recommendation |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Baseline before patch at `16c1f90` | 14 | 9 | 0/9 | 0/9 | 9/9 | 0/9 | 0/14 |
| After patch | 8 | 6 | 6/6 | 6/6 | 6/6 | 6/6 | 6/8 aggregate |

Raw final-attempt aggregate also moved from `what_features=0/18` and
`where_context=0/18` before the patch to `what_features=12/12`,
`where_context=12/12`, and `phase_context=12/12` after the patch.

After the helper-module refactor, the same live no-write shape was rerun:
validated question candidates were `what_features=7/7`, `where_context=7/7`,
`phase_context=7/7`, complete core axes `7/7`, missing core-axis rate `0.0`,
and no diagnostics warnings.

Follow-up audit found two more hidden diagnostic traps:

- `recommendation=7/12` was a mixed denominator across `question_candidate` and
  `frontier_marker`. The JSON now reports recommendation by kind.
- Raw final attempts and accepted final output were being conflated. The JSON
  now separates `all_final_attempts` history from `accepted_final` quality and
  includes validation rejection reasons.

Final live no-write verification after the validation-audit fix:

| Metric | Result |
| --- | ---: |
| Validated findings | 9 |
| Question candidates | 7 |
| Frontier markers | 2 |
| Question core axes | 7/7 |
| Question recommendation | 7/7 |
| Frontier context | 2/2 |
| Frontier recommendation | 2/2 |
| Accepted-final question retention | 7/7 |
| Accepted-final frontier retention | 2/2 |
| Accepted-final validation rejections | 0 |

## Interpretation

The issue was real on current main: validation preserved richer fields when
present, but the model-facing contract still made the axes too soft. The fix
strengthens the job-specific field contract, adds a bounded one-shot repair for
missing axes, missing recommendations, and raw frontier rows dropped by
validation, and exposes field-presence plus validation-retention diagnostics in
no-write/live JSON.

Claim boundary: this is a single live no-write regression check on one private
registry slice. It verifies the failure mode and immediate fix; it is not a
broad route benchmark.

Machine-readable aggregate counts:
[`question-extraction-axis-coverage-2026-05-31.json`](question-extraction-axis-coverage-2026-05-31.json).
