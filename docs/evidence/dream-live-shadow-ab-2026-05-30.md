# Dream Live Shadow A/B Reminder Evidence - 2026-05-30

This run adds the live shadow A/B ledger for the sharper product question:
after a real user prompt, does the user later need to explicitly remind the
agent to recall prior context with wording such as "回忆", "之前说过", or "你忘了"?

The prompt hook integration is opt-in. By default it records hash-only shadow
events and does not change foreground recall. The historical replay below uses
real local clean-source user turns plus generated in-memory dream rows; it is a
smoke of the measurement design, not causal treatment evidence.

## Command

```powershell
python skills\aippocampus\scripts\dream_live_shadow_ab.py --replay-clean-source --generate-dream-rows 64 --max-threads 1200 --max-user-messages 12000 --window-user-turns 6 --output docs\evidence\dream-live-shadow-ab-2026-05-30.json --json
```

## Evidence File

- `docs/evidence/dream-live-shadow-ab-2026-05-30.json`

## Results

- Real clean-source user turns replayed: 5,409
- Threads: 984
- Explicit recall-reminder prompts detected: 26
- Overall reminder rate: 0.0048
- Shadow eligible exposures: 17
- Eligible exposure rate: 0.0031
- Control assigned eligible exposures: 9
- Dream assigned eligible exposures: 8
- Attributed reminders within the next 6 user turns: 0
- Unattributed reminders: 26
- Live delivered treatment events: 0

## Interpretation

This does not show a real user-visible reduction yet. It shows that the
measurement path can count explicit reminder language over real conversations,
keep prompt/session content out of the report, and avoid over-attributing one
reminder to many prior prompts.

The hard result is that historical replay found reminders, but not in windows
where the current selected dream hypotheses would have been the nearest
eligible treatment. The next meaningful claim requires opt-in live event
logging over future sessions, and eventually a delivered A/B mode rather than
shadow-only assignment.

## Design Guards

- Reminder classification treats "之前/previous/before" as a reminder only when
  it is paired with recall, forgotten-constraint, or prior-conversation cues.
- Ordinary code/time references such as "before calling render" and "previous
  commit" are negative controls.
- Outcome attribution uses only the nearest prior eligible exposure inside the
  configured user-turn window.
- The checked-in report stores aggregate counts and hashes only; raw prompts,
  raw thread ids, raw turn ids, source refs, and local paths are omitted.
