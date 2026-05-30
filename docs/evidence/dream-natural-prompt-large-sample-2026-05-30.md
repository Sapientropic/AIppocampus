# Dream Natural-Prompt Large-Sample Evidence - 2026-05-30

This post-#131 run tests whether adjudicated dream hypotheses reduce explicit
"please recall this" prompting under ordinary topic prompts, and whether they
create misleading or over-personalized foreground noise.

The run used real local registry rows, but the checked-in output is aggregate
and sanitized. It omits raw prompts, raw source text, source refs, message ids,
thread ids, and local paths.

## Command

```powershell
python skills\aippocampus\scripts\dream_natural_prompt_eval.py --max-packs 64 --negative-repetitions 25 --output docs\evidence\dream-natural-prompt-large-sample-2026-05-30.json --json
```

## Evidence File

- `docs/evidence/dream-natural-prompt-large-sample-2026-05-30.json`

## Results

- Selected packs: 18
- Dream working-memory rows: 36
- Effective prompt cases: 344
- Natural topic prompts: 108
- Negative / unrelated / over-personalization prompts: 200
- Strong-claim prompts: 36
- Baseline natural hit rate: 0.2778
- Augmented natural hit rate: 0.4444
- Natural hit-rate delta: +0.1666
- Manual-reminder reduction: 18 / 108 natural prompts, rate 0.1667
- Dream natural hit rate: 0.3889
- Negative dream matches: 0 / 200
- Overbroad dream prompt matches: 0
- Strong dream-claim source reopen: 14 / 14 matched prompts, rate 1.0

## Interpretation

This supports a narrow claim: in this route-level large sample, dream
hypotheses reduce some explicit recall nudges when the natural prompt already
names the relevant topic, while staying silent on the negative prompt bank.

It does not prove real user behavior lift, live model behavioral lift, general
dream quality, full-history coverage, or factual truth without reopening clean
source.

## Regression Found And Fixed

Before hardening, generic template wording such as `unresolved` could wake
multiple unrelated compensatory dream hypotheses. The foreground trigger path
now filters dream-template safety words and requires source/theme trigger terms;
`tests/aippocampus/test_dream_working_memory.py` covers that regression.
