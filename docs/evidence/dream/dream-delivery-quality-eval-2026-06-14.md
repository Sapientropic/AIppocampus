# Dream Delivery Quality Eval - 2026-06-14

This public-safe eval supported the #1438 closeout through a replayable
synthetic delivery-quality fixture. It is a substitute for non-shareable
private history, not a claim that live/default Dream delivery is ready.

## Command

```powershell
python benchmarks\aippocampus\benchmark_dream_delivery_quality.py `
  --json `
  --output docs\evidence\dream\dream-delivery-quality-eval-2026-06-14.json
```

Focused verification:

```powershell
python -m pytest tests\aippocampus\test_benchmark_dream_delivery_quality.py -q
python -m pytest tests\aippocampus\test_dream_live_shadow_ab.py tests\aippocampus\test_dream_real_history_eval.py tests\aippocampus\test_prompt_hook_dream_delivery.py -q
```

## Arms

The scoring contract pre-registers three arms before scoring:

- `baseline_no_dream`
- `dream_backstage_only`
- `dream_bounded_action_hint`

The fixture covers repeated rejected-route recovery, currentness checking,
stale route suppression, noisy generic hints, over-personalized hints, and
source-truth overclaim controls.

## Result

| Metric | Value |
|---|---:|
| Cases | 6 |
| Bounded route lift | 3 |
| Bounded action lift | 2 |
| Verification-cost delta | -3 |
| Visible wrong hints | 0 |
| Visible wrong-hint rate | 0.0 |
| Quiet/no-harm cases | 4 |
| Source-ripening cases | 2 |
| Stale route suppressions | 1 |
| Noisy hint suppressions | 1 |
| Over-personalization suppressions | 1 |
| Dream-only foreground leaks | 0 |
| Source-truth overclaims | 0 |
| Source reopen required | 6 |
| Provider calls | 0 |

## Review Next Actions

The committed JSON report includes `review_next_actions` so the positive
bounded metrics do not end as an inert `Cannot Claim` note:

- `open_dream_delivery_successor` records `successor_missing` for the closed
  historical #1438 owner path and gives the exact `gh issue create` review
  command.
- `rerun_public_dream_delivery_report` keeps the owner path on
  `benchmarks/aippocampus/benchmark_dream_delivery_quality.py` and refreshes
  the public synthetic report before any human closeout note.

For foreground product use, reviewed Dream/subconscious findings surface
through #2095's `aippocampus agent background "task cue" --json` route. This
eval remains review input and does not by itself promote Dream material to
source truth or default foreground adoption.

## Can Claim

- A public synthetic three-arm Dream delivery-quality eval exists for #1438.
- In selected delivery cases, bounded Dream hints improve route/action behavior
  over no-Dream and backstage-only arms.
- Stale, noisy, over-personalized, unsourced, and source-truth-overclaim
  controls stay quiet or reopen-only.
- Dream material remains navigation-only until source is reopened.

## Cannot Claim

- Live/default Dream delivery quality.
- Broad private-history Dream quality.
- Causal real-user lift.
- Dream-only material as source truth.
- Default foreground Dream adoption.

## Public Boundary

The committed report uses synthetic case identifiers and aggregate metrics. It
does not serialize raw prompts, raw source text, source refs, thread/message
handles, local paths, provider payloads, credentials, or private-history rows.
