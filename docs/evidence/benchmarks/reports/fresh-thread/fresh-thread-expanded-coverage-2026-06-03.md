# Fresh-Thread Expanded Coverage Evidence

Evidence date: 2026-06-03.
GitHub #281 public validation update: 2026-06-10.

This report records the #490 expansion of the fresh-thread public demo and the
sanitized real-history boundary smoke. The 2026-06-10 update adds the #281
public fixture validation readout from the same public-safe runner. This is
issue closeout for the public, inspectable fresh-thread fixture requirement,
not a live/private or universal fresh-thread recall quality benchmark.

## Source Map

- Issues: #490 and #281
- Demo benchmark:
  [`benchmark_fresh_thread_recall_demo.py`](../../../../../benchmarks/aippocampus/benchmark_fresh_thread_recall_demo.py)
- Runtime runner:
  [`fresh_thread_demo.py`](../../../../../skills/aippocampus/scripts/aippocampus_runtime/recall/fresh_thread_demo.py)
- Public-safe fixture catalog:
  [`fresh_thread_demo_fixtures.py`](../../../../../skills/aippocampus/scripts/aippocampus_runtime/recall/fresh_thread_demo_fixtures.py)
- Real-history smoke:
  [`smoke_fresh_thread_real_history.py`](../../../../../tools/aippocampus/smoke/smoke_fresh_thread_real_history.py)
- Tests:
  [`test_fresh_thread_demo.py`](../../../../../tests/aippocampus/test_fresh_thread_demo.py),
  [`test_benchmark_fresh_thread_recall_demo.py`](../../../../../tests/aippocampus/test_benchmark_fresh_thread_recall_demo.py), and
  [`test_fresh_thread_real_history_smoke.py`](../../../../../tests/aippocampus/test_fresh_thread_real_history_smoke.py)

## Public Demo Expansion

The deterministic public-safe demo now reports:

- 11 flows total
- 6 positive flows
- 5 negative controls
- turn-depth distribution: 7 one-turn flows, 2 two-turn flows, 2 three-turn flows
- max turn depth: 3
- 2 multi-turn flows
- 1 wrong-recall correction control
- 1 threshold-edge control
- 2 source-required turns

The new positive multi-turn flow covers a low-confidence scent that asks for a
light anchor, a confirmed route that can use active recall, and a specific
claim that still requires source reopen.

The new negative control covers plausible but wrong recall. After a user
correction rejects the route, the demo suppresses the old route instead of
turning it into personalized answer content.

The fixture catalog is separate from the runner so additional public-safe flows
do not make the runner own both evidence catalog and report projection.

## GitHub #281 Public Validation Readout

The 2026-06-10 runner exposes `issue_readouts.github_281` with
`claim_level=public_safe_fixture_validation` and `closeout_eligible=true`.
It uses public synthetic fixtures only and keeps broad live/private claims out
of scope.

Recorded metrics:

- positive public flows: 6
- negative public controls: 5
- first-turn positive route success count: 6
- first-turn false activation count: 0
- `first_turn_scent_precision=1.0`
- `progressive_activation_gain=1.0`
- `source_reopen_before_specific_claim_rate=1.0`
- `irrelevant_memory_drag_rate=0.0`
- `overpersonalization_count=0`
- `manual_query_invention_count=0`
- `manual_query_expected_count=0`
- `ready_lock_use_count=5`
- `unsupported_evidence_count=0`
- `negative_control_active_recall_count=0`

This retires #281's public-fixture validation blocker. Future live host,
private real-history, or external public-dataset fresh-thread quality work
should use a new scoped issue instead of reopening #281 as a catch-all.

## Real-History Smoke Expansion

The real-history smoke now samples multiple reopenable refs when available and
reports denominator fields without printing private prompts, source text,
thread ids, source refs, registry paths, or local workspace paths.

Current local command:

```powershell
python tools\aippocampus\smoke\smoke_fresh_thread_real_history.py --cwd . --json
```

Sanitized result summary:

- `status=passed`
- `sample_coverage_status=passed`
- `thread_count=1014`
- `clean_source_message_rows_seen=11358`
- `eligible_clean_source_row_count=11358`
- `eligible_reopenable_thread_count=1012`
- `sample_limit=3`
- `minimum_sample_count=2`
- `sampled_reopenable_ref_count=3`
- `sample_gap=0`
- ready-lock reopenability batch: 3 samples passed, `total_match_count=3`
- thread-only lock boundary batch: 3 samples passed, `lock_state_counts.pending=3`
- current-repo fact negative control: passed, `decision=skip`,
  `evidence_count=0`, `current_checkout_required=true`

If a registry has no reopenable refs, the smoke reports
`insufficient_real_history`. If it has at least one but fewer than the required
multi-ref minimum, it reports `insufficient_sample_coverage`. Both states avoid
claiming expanded real-history coverage.

## Can Claim

- The public demo now exercises multi-turn, correction, and threshold-edge
  fresh-thread controls with synthetic public-safe fixtures.
- The public #281 readout records first-turn scent precision, progressive
  activation gain, source reopen before specific claims, negative-control
  drag suppression, over-personalization suppression, and manual-query
  invention suppression for the checked-in public fixtures.
- The demo reports turn-depth distribution and correction/threshold coverage
  counts.
- The real-history smoke can sample multiple reopenable refs, report clear
  denominators, and remain aggregate/hash-only.
- On the 2026-06-03 local registry slice, the sampled ready-lock and
  thread-only boundaries passed across 3 reopenable refs, and the current-repo
  fact negative control did not surface old-project evidence.

## Cannot Claim

- No broad private real-history fresh-thread recall quality claim.
- No live fresh-thread quality claim.
- No live semantic-model quality claim.
- No live correction-extraction quality claim.
- No proof that all fresh-thread prompts or all private memory families are
  covered in production.
- No foreground-hook-only sufficiency or base-model innate memory claim.
- No public release of private prompts, source text, source refs, thread ids,
  registry paths, or local paths.
