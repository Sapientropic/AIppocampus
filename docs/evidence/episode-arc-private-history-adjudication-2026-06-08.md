# Episode/Arc Private-History Adjudication - 2026-06-08

This evidence slice records the first #663 private-history aggregate scan for
Episode/Arc rejected-route read-models. The checked-in report is aggregate-only:
it contains no source text, raw command text, source refs, source-ref hash
samples, event ids, thread ids, local paths, or registry paths.

## Command

```powershell
aippocampus episode-arcs --max-threads 100 --json --output docs\evidence\episode-arc-private-history-adjudication-2026-06-08.json
```

Privacy leak check: a local `rg` scan for thread ids, event ids, source-ref
arrays, source-ref hash arrays/samples, drive-letter paths, user names, private
workspace markers, and raw-text true flags returned no matches.

## Input Surface

- Registry threads scanned: 100.
- Threads with clean-source messages: 100.
- Threads with clean-source events: 70.
- Clean-source message rows scanned: 5,164.
- Clean-source behavior event rows scanned: 83,221.
- Bad JSONL rows: 0.
- Max line gap for pairing rejected decisions to failed behavior: 3,000.

## Result

- Status: `measured_public_safe_aggregate`.
- Decision candidates extracted: 5,052.
- Rejected-route / do-not-repeat decision candidates: 1,851.
- Failed behavior events observed: 2,566.
- Rejected decisions with a nearby failed-behavior chain: 684.
- Episode/Arc rows built: 1,851.
- Complete rejected-route arcs: 684.
- Gappy single-point rejected-route arcs: 1,167.
- Sequence-packet reopen resolution: 1,851 complete aggregate routes.
- Safe uses: 1,851 `ask`, 1,851 `refresh_sources`, 684 `remind`.

## Can Claim

- The #663 private-history adjudication path can scan local clean-source
  messages/events and emit a public-safe aggregate Episode/Arc report.
- The current cohort contains source-backed rejected-route decision material,
  and 684 rejected-route arcs can be connected to a nearby failed behavior
  chain.
- Gappy / single-point rejected-route rows are explicitly counted instead of
  being silently upgraded into warnings or current-validity truth.
- Sequence packets remain navigation-only and current validity still requires
  source reopen.

## Cannot Claim

- The broader #663 Episode/Arc owner track is complete.
- Live host behavior lift, user-visible recall lift, or private-history
  generality beyond this registry cohort.
- That a rejected route is still rejected now without reopening source.
- That single-point/gappy arcs may warn, block, or assert current validity.
- That Episode/Arc rows are a new ground-truth memory layer.

## Interpretation

This closes the earlier "private-history adjudication not measured" gap for a
bounded aggregate scan. It does not close #663 by itself. The next useful slice
is either richer source adapters beyond rejected-route chains, or live-host
behavior evidence showing whether sequence packets help an agent reopen the
right source earlier without producing stale-route drag.
