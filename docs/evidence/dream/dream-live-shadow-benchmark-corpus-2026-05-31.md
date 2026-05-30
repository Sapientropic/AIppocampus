# Dream Live Shadow Benchmark-Corpus Evidence - 2026-05-31

This run reuses the live shadow A/B reminder-frequency harness over
`benchmark_corpus` clean-source data. The goal is deliberately adversarial:
use public multi-turn conversations as a negative-control distribution and ask
whether AIppocampus dream hypotheses would over-activate on unrelated prompts,
or whether explicit "remember/forgot/as I said before" language clusters after
dream-only eligible exposures.

The public corpus run is shadow-only. It does not deliver treatment content,
change foreground recall, or prove user-visible behavior lift.

Important correction: the first large run below is a deterministic structural
ablation, not the primary dream-quality result. A second run uses the bounded
model-backed background dream worker (`dream_worker.py`) through DeepSeek Flash
over a smaller source-pack budget, then replays the same 120,000 public-corpus
user turns as the negative-control distribution.

## Commands

Fixture smoke:

```powershell
python benchmark_corpus\convert_to_aippocampus.py --source local --input benchmark_corpus\testdata_wildchat.jsonl --output .tmp\dream-benchmark-corpus-smoke
python skills\aippocampus\scripts\dream_live_shadow_ab.py --replay-clean-source-dir .tmp\dream-benchmark-corpus-smoke --dataset-id wildchat_fixture --generate-dream-rows 64 --max-threads 20 --max-user-messages 100 --window-user-turns 6 --output .tmp\dream-shadow-benchmark-fixture.json --json
```

Large local public-corpus runs:

```powershell
python skills\aippocampus\scripts\dream_live_shadow_ab.py --replay-clean-source-dir benchmark_corpus\output\sharegpt_coding_multiturn --dataset-id sharegpt_coding_multiturn --generate-dream-rows 64 --dream-worker-mode deterministic --max-threads 10000 --max-user-messages 60000 --window-user-turns 6 --output .tmp\dream-shadow-benchmark-sharegpt-coding-10000.json --json
python skills\aippocampus\scripts\dream_live_shadow_ab.py --replay-clean-source-dir benchmark_corpus\output\sharegpt_all_multiturn --dataset-id sharegpt_all_multiturn --generate-dream-rows 64 --dream-worker-mode deterministic --max-threads 10000 --max-user-messages 60000 --window-user-turns 6 --output .tmp\dream-shadow-benchmark-sharegpt-all-10000.json --json
python skills\aippocampus\scripts\dream_live_shadow_ab.py --replay-clean-source-dir benchmark_corpus\output\sharegpt_coding_multiturn --dataset-id sharegpt_coding_multiturn_model_backed --generate-dream-rows 4 --dream-worker-mode model-backed --max-threads 10000 --max-user-messages 60000 --window-user-turns 6 --output .tmp\dream-shadow-benchmark-sharegpt-coding-10000-model.json --json
python skills\aippocampus\scripts\dream_live_shadow_ab.py --replay-clean-source-dir benchmark_corpus\output\sharegpt_all_multiturn --dataset-id sharegpt_all_multiturn_model_backed --generate-dream-rows 4 --dream-worker-mode model-backed --max-threads 10000 --max-user-messages 60000 --window-user-turns 6 --output .tmp\dream-shadow-benchmark-sharegpt-all-10000-model.json --json
```

The large generated corpora are ignored local artifacts. The checked-in
evidence file stores only aggregate counts:
`docs/evidence/dream/dream-live-shadow-benchmark-corpus-2026-05-31.json`.

## Results

Combined deterministic structural ablation:

- User turns replayed: 120,000
- Conversations sampled: 18,512
- Explicit recall-reminder prompts detected: 190
- Overall reminder rate: 0.0016
- Potential public false activations: 809
- Potential public false activation rate: 0.0067
- Control eligible exposures: 405
- Dream eligible exposures: 404
- Attributed reminders within the next 6 user turns: 3
- Unattributed reminders: 187
- Live delivered treatment events: 0

Combined model-backed background dream worker:

- User turns replayed: 120,000
- Conversations sampled: 18,512
- Explicit recall-reminder prompts detected: 190
- Overall reminder rate: 0.0016
- Potential public false activations: 2,501
- Potential public false activation rate: 0.0208
- Control eligible exposures: 1,192
- Dream eligible exposures: 1,309
- Attributed reminders within the next 6 user turns: 15
- Unattributed reminders: 175
- Dream-minus-control reminder-rate delta: -0.0014
- Live delivered treatment events: 0

Per deterministic corpus:

- ShareGPT coding multiturn: 60,000 user turns, 8,794 conversations, 104
  reminders, 399 potential dream-only activations, 0 attributed reminders.
- ShareGPT all multiturn: 60,000 user turns, 9,718 conversations, 86
  reminders, 410 potential dream-only activations, 3 attributed reminders.

Per model-backed corpus:

- ShareGPT coding multiturn: 60,000 user turns, 8,794 conversations, 104
  reminders, 1,047 potential dream-only activations, 5 attributed reminders.
- ShareGPT all multiturn: 60,000 user turns, 9,718 conversations, 86
  reminders, 1,454 potential dream-only activations, 10 attributed reminders.

Reminder families in the large sample:

- `as_said_before`: 110
- `explicit_recall_en`: 80

## Interpretation

This is not positive lift evidence. The useful signal is sharper:
AIppocampus dream hypotheses did not explode on unrelated public prompts, but
they also did not stay at zero. Deterministic structural dream rows activated
on about 0.67% of public prompts. The model-backed background dream rows
activated on about 2.08% of public prompts. That is still bounded, but it is a
real over-personalization watch item and argues against loosening
source-reopen, sensitive-use, and fanout gates.

The reminder outcome signal is tiny. In deterministic mode, 3 later explicit
reminders were attributed across 809 eligible exposures. In model-backed mode,
15 later explicit reminders were attributed across 2,501 eligible exposures,
with a combined dream-minus-control reminder-rate delta of -0.0014. That delta
is directionally favorable but too small and too shadow-only to call user-visible
lift.

## Can Claim

- The live-shadow harness can replay `benchmark_corpus` clean-source directories
  directly.
- The deterministic and model-backed 120,000-turn public-corpus runs measured
  explicit reminder language and potential dream-only public false activation
  without emitting raw prompts, source ids, or local paths.
- Public-corpus negative controls now expose two over-personalization budgets:
  roughly 0.6%-0.7% for deterministic structural rows, and roughly 2.1% for the
  bounded model-backed background dream worker over this source-pack budget.

## Cannot Claim

- Causal reduction in real users saying "回忆/之前/你忘了".
- Private real-history behavior lift.
- Full benchmark-corpus coverage.
- General dream quality or safe delivered dream treatment.
