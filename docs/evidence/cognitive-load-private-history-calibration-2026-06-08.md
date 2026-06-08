# Cognitive-Load Private-History Calibration - 2026-06-08

This evidence slice records the first #575 private-history aggregate scan for
the cognitive-load sidecar. The full local runner output stayed under `.tmp/`;
the checked-in evidence is aggregate-only and contains no private text, raw
source refs, local paths, thread ids, message ids, or command text.

## Command

```powershell
python -c "import sys; sys.path.insert(0, r'skills\aippocampus\scripts'); from aippocampus_runtime.recall.cognitive_load_private_calibration import main; raise SystemExit(main(['--json','--max-threads','100','--output',r'.tmp\issue-575-private-load-calibration.json']))"
```

Privacy leak check: a local `rg` scan for drive-letter paths, user names, raw
command keys, rollout filenames, and private workspace markers returned no
matches.

## Input Surface

- Registry threads scanned: 100.
- Threads with at least one load signal: 76.
- Missing clean-source entries skipped: 2.
- Clean-source message rows scanned: 5,268.
- Clean-source event rows scanned: 82,695.
- Bad JSONL rows: 0.

## Result

- Status: `measured_public_safe_aggregate`.
- Load signal events: 26,505.
- Message-derived signals: 1,082.
- Behavior-event-derived signals: 25,423.
- Sidecar entries: 26,035.
- Load buckets: 98 high, 175 medium, 25,762 low.
- Max load boost: 0.16.
- Decay coverage: 1.0.
- High-load source reopen rate: 0.004754.
- Pitfall repetition after high-load signal rate: 0.017695.
- Load-weight false-positive rate: not measured.
- Caution hint useful rate: not measured.
- Over-personalization from load signal count: 0.

Signal kind counts:

- `failed_command`: 19,803.
- `failed_test`: 5,620.
- `high_risk_action_repaired`: 247.
- `human_intervention`: 202.
- `user_correction`: 199.
- `rejected_route_retry`: 161.
- `explicit_pitfall_marker`: 149.
- `source_conflict`: 124.

## Can Claim

- The #575 private-history calibration path can scan local clean-source
  messages/events and emit a public-safe aggregate report.
- The report marks `private_real_history_calibration` as
  `measured_public_safe_aggregate` for the scanned cohort.
- The projection keeps cognitive load as bounded routing metadata and keeps
  affect/personality truth blocked.
- The checked output omits raw private text, raw source refs, local paths, raw
  command text, raw feedback text, thread ids, and message ids.

## Cannot Claim

- Live hook capture or delivered host timing.
- Host-timing quality or annoyance-risk calibration.
- Load-weight false-positive rate or caution-hint usefulness, because no
  reviewed feedback rows were present.
- User-visible recall improvement.
- Source truth, semantic relevance, affect, stress, identity, or personality
  truth from load signals.
- That all failed-command signals should be foregrounded by default; the scan
  intentionally remains diagnostic until feedback calibration exists.

## Interpretation

This closes the earlier "private real-history calibration not measured" gap for
a bounded aggregate scan. It does not close #575 by itself. The next useful
slice is reviewed feedback or live-host telemetry that can distinguish noisy
failed-command load from genuinely helpful caution routing without turning load
into personality inference or stale-source authority.
