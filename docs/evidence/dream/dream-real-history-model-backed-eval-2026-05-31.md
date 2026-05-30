# Dream Real-History Model-Backed Eval Evidence - 2026-05-31

This evidence slice tests the next boundary after public-corpus negative
controls: selected private real-history packs, model-backed dream workers, and
the existing user-visible ablation harness. It is offline and sanitized. It
does not emit private text, raw source refs, message ids, thread ids, or local
paths.

The run uses the current local registry-derived job and working-memory rows.
The selector found all currently eligible source-backed cross-thread ready
packs. The checked-in JSON stores aggregate counts only:
`docs/evidence/dream/dream-real-history-model-backed-eval-2026-05-31.json`.

## Commands

Deterministic all-selected baseline:

```powershell
python skills\aippocampus\scripts\dream_real_history_eval.py --max-packs 100 --min-packs 1 --json --output .tmp\dream-real-history-eval-deterministic-max100-postcli-2026-05-31.json
```

Model-backed all-selected run:

```powershell
python skills\aippocampus\scripts\dream_real_history_eval.py --dream-worker-mode model-backed --model-route default --max-packs 100 --min-packs 1 --max-samples 1 --max-tokens 1200 --dream-model-timeout 120 --json --output .tmp\dream-real-history-eval-model-backed-max18-2026-05-31.json
```

Model-backed historical clean-source shadow replay:

```powershell
python skills\aippocampus\scripts\dream_live_shadow_ab.py --replay-clean-source --generate-dream-rows 100 --dream-worker-mode model-backed --model-route default --max-threads 1200 --max-user-messages 12000 --window-user-turns 6 --dream-max-samples 1 --max-tokens 1200 --dream-model-timeout 120 --output .tmp\dream-live-shadow-private-model-backed-diagnostic-2026-05-31.json --json
```

Opt-in semantic relevance gate smoke:

```powershell
python skills\aippocampus\scripts\dream_live_shadow_ab.py --replay-clean-source --generate-dream-rows 4 --dream-worker-mode model-backed --semantic-relevance-gate --model-route default --max-threads 100 --max-user-messages 100 --window-user-turns 6 --dream-max-samples 1 --max-tokens 900 --dream-model-timeout 120 --semantic-relevance-min-confidence 0.65 --semantic-relevance-max-candidates 16 --output .tmp\dream-live-shadow-private-semantic-gate-smoke-2026-05-31.json --json
```

Delivered A/B implementation contract smoke:

```powershell
python -m pytest tests/aippocampus/test_dream_live_shadow_ab.py tests/aippocampus/test_aippocampus_prompt_hook.py -q
```

## Input Surface

- Subconscious job rows: 698
- Working-memory rows: 63
- Selected source-backed cross-thread ready packs: 18
- Source seed kinds: 8 question-candidate, 6 frontier-marker, 1 question-link,
  15 working-memory
- Full private-history coverage: no
- Private text emitted: no

## Results

Deterministic all-selected baseline:

- Selected packs: 18
- Dream findings: 36
- Dream working-memory rows: 36
- Prompt hit-rate delta: 0.0
- Source-thread coverage delta: 3.5
- Reflection-ready delta: 1,296
- Bridge-claim coverage delta: 1.0
- User-visible recall hit delta: 0
- User-visible reflection-ready delta: 648
- Unsupported strong-claim suppression rate: 1.0
- Source-support correctness rate: 1.0
- Manual/source review rows: 0

Model-backed all-selected run:

- Selected packs: 18
- Dream findings: 34
- Dream working-memory rows: 32
- Model calls: 36
- Model route: DeepSeek Flash, `deepseek-v4-flash`
- DeepSeek prefix-cache hit rate: 0.4797
- Prompt hit-rate delta: 0.0
- Source-thread coverage delta: 1.6111
- Reflection-ready delta: 720
- Bridge-claim coverage delta: 1.0
- User-visible recall hit delta: 0
- User-visible reflection-ready delta: 110
- Unsupported strong-claim suppression rate: 1.0
- Source-support correctness rate: 1.0
- Manual/source review rows: 0

Model-backed historical clean-source shadow replay:

- Real clean-source user turns replayed: 5,461
- Threads: 990
- Explicit recall-reminder prompts detected: 27
- Overall reminder rate: 0.0049
- Eligible exposure rate: 0.0
- Control eligible exposures: 0
- Dream eligible exposures: 0
- Attributed reminders within the next 6 user turns: 0
- Unattributed reminders: 27
- Dream-minus-control reminder-rate delta: 0.0
- Live delivered treatment events: 0
- Baseline match events: 3,203
- Dream match events: 2
- Events where both baseline and dream matched: 2
- Dream-only non-reminder events: 0
- Dream-only reminder events: 0

Opt-in semantic relevance gate smoke:

- Real clean-source user turns replayed: 100
- Threads: 9
- Explicit recall-reminder prompts detected: 2
- Semantic relevance model calls: 20
- Semantic relevance match events: 0
- Baseline match events: 79
- Dream match events: 0
- Eligible exposures: 0
- Live delivered treatment events: 0

Delivered A/B implementation contract smoke:

- Default hook delivery mode filters dream hypotheses from foreground context.
- `dry_run` records `would_deliver_arm` but leaves `delivered_arm` unset and does
  not insert dream context.
- `delivered` control arms act as holdback: `delivered_arm="control"` and no
  dream context is inserted.
- `delivered` dream arms set `delivered_arm="dream"` and insert at most one
  private `Dream hypothesis, not source fact` context item.
- Thread/topic assignment is stable for true delivered A/B; legacy prompt-level
  shadow assignment remains unchanged for historical replay.
- Semantic relevance model errors fail closed for dream delivery.

## Interpretation

This is positive offline private-history substrate evidence, not real-user
causal evidence. On the selected real-history slice, the model-backed dream
worker produced accepted source-backed dream hypotheses and improved structural
reflection/bridge surfaces over plain rows.

The recall metric did not improve because the selected recall prompts were
already saturated: plain recall hit rate was 1.0 and augmented visible recall
hit rate stayed 1.0. This is a ceiling effect, not evidence that dream recall
is useless.

The user-visible ablation is mixed but useful. It showed reflection-ready lift
and 1.0 unsupported strong-claim suppression on the selected slice, while still
listing `real_user_behavior`, `general_dream_quality`, and
`manual_source_review_support` as non-claims.

The historical shadow replay counted real reminder language over clean-source
history, but it observed zero eligible exposures. That means this run cannot
estimate behavior lift: there were real reminders, but no prior dream-only
eligible treatment/control moments for the nearest-prior attribution window.
The match diagnostics explain the zero: the model-backed dream rows matched
only 2 historical user turns, and both of those turns were already matched by
the plain baseline surface. Since this shadow A/B defines eligibility as
`not reminder` + `baseline miss` + `dream match`, it produced no dream-only
exposure windows.

The zero delivered-treatment count in the historical replay is a separate and
expected boundary of that run. `--replay-clean-source` is historical shadow
replay; it does not set a `delivered_arm`. The live prompt hook now has an
explicit opt-in delivery policy, but default/shadow/dry-run modes still do not
count as delivered treatment.

The semantic relevance gate is now an explicit opt-in replay mode. It uses the
configured model to judge prompt-to-dream relevance only when the baseline
surface misses, lexical dream matching misses, and the prompt is not already a
reminder. This keeps semantic judgment with the LLM, while avoiding a default
path that silently sends private clean-source prompts to an external model. The
100-turn smoke verified the gate and aggregate counters end to end; it did not
produce semantic matches and should not be read as lift evidence.

This run still cannot prove general dream quality. The source-support
correctness metric is structural: visible dream rows carry source support and
render with the not-a-source-fact/reopen-source boundary. It is not a human
judgment that the dream is insightful, useful, or worth surfacing.

This run also cannot prove safe delivered treatment outcomes. The implementation
contract now supports opt-in holdback/treatment events, but no real user live
run has yet collected treatment/control outcomes. Safe delivery still needs
opt-in live delivered events in the same hash-only ledger.

## Can Claim

- The selected private real-history offline eval can run model-backed dream
  workers without emitting private text.
- On the current selected source-backed ready-pack slice, model-backed dream
  rows produced structural lift: source-thread coverage delta 1.6111,
  reflection-ready delta 720, and bridge-claim coverage delta 1.0.
- The user-visible ablation layer ran on the same selected slice and reported
  reflection-ready delta 110, unsupported strong-claim suppression rate 1.0, and
  source-support correctness rate 1.0.
- The model-backed historical clean-source shadow replay counted 27 explicit
  real reminder prompts over 5,461 user turns, but found zero eligible exposures
  and therefore no attributable reminder outcomes. Match diagnostics show this
  was because both dream matches were also baseline matches.
- The opt-in semantic relevance gate can run in replay mode and reports
  semantic model-call and match counts without checked-in raw prompts.
- The prompt hook now has an opt-in delivered A/B contract: default/off and
  dry-run do not insert dream context, control is holdback, and dream treatment
  inserts at most one private dream hypothesis context item.

## Cannot Claim

- Causal real-user behavior lift.
- Full private-history coverage.
- General dream quality without manual/source review.
- Safe delivered treatment outcomes or user-behavior lift without live opt-in
  delivered treatment/control events.
- Semantic relevance lift from the 100-turn smoke.
- Formal memory promotion.
