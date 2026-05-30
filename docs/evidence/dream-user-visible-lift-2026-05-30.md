# Dream User-Visible Lift Evidence - 2026-05-30

This is the source-review and selected-prompt visibility evidence for GitHub
#131. The machine-local clean source was reopened during the run, but the
checked-in evidence files intentionally omit raw source text, raw source refs,
message ids, thread ids, local paths, and private registry details.

## Command

```powershell
python skills\aippocampus\scripts\dream_real_history_eval.py --max-packs 4 --generate-manual-source-review --source-review-output docs\evidence\dream-manual-source-review-2026-05-30.json --output docs\evidence\dream-user-visible-lift-2026-05-30.json --json
```

## Evidence Files

- `docs/evidence/dream-user-visible-lift-2026-05-30.json`
- `docs/evidence/dream-manual-source-review-2026-05-30.json`

## Results

- Selected packs: 4
- Dream working-memory rows: 8
- Manual/source-review rows: 8 reviewed, 8 source-backed, 8 supported
- Recall hit-rate delta: 0.0 because the plain baseline already hit all
  selected prompts.
- Recall source-thread coverage delta: +2.5
- Recall bridge-claim coverage delta: +1.0
- Reflection-ready delta: +32 in the user-visible harness and +64 in the
  broader structural comparison.
- Unsupported strong-claim suppression: 4/4 prompts suppressed.
- Source-support correctness: 8/8 visible dream rows.

## Claims

This evidence supports:

- selected real-history packs can produce adjudicated dream hypotheses without
  emitting private text;
- selected-prompt user-visible recall/reflection lift is measurable beyond the
  plain baseline through source coverage, bridge coverage, and reflection-ready
  surfaces;
- the selected sample has clean-source reopen support.

This evidence does not support:

- general dream quality;
- live provider behavioral lift;
- full-history coverage;
- real user behavior lift;
- formal memory promotion;
- clean-source factual claims without reopening source.
