# Cognitive-Load Sidecar

Role: active design.

Status: first deterministic sidecar, public-safe calibration report, public
behavior-trace feedback fixture, and private-history aggregate calibration
runner implemented for #575. Live hook capture, host-timing quality, and
user-visible lift remain future work.

## Purpose

The cognitive-load sidecar gives recall routing a bounded way to notice source
regions that cost the collaboration real effort: corrections, failed commands,
red tests, rollbacks, rejected-route retries, source conflicts, explicit
pitfall markers, repeated source reopen, human intervention, downstream turns
affected, or high-risk actions that had to be repaired.

This is routing metadata, not memory truth. It can ask a later agent to reopen
source earlier or use a more cautious warning tone. It must not claim the user
felt stressed, infer personality, or make a stale source current again.

## Owner

`aippocampus_runtime/recall/cognitive_load_sidecar.py` owns the reusable
deterministic sidecar:

- `build_cognitive_load_sidecar(events, now=...)` consumes observable behavior
  events and emits source-ref-keyed load hints.
- `apply_cognitive_load_boosts(candidates, sidecar)` blends a candidate's
  semantic score, source authority, and bounded load boost into an explainable
  ranking row.
- `build_cognitive_load_calibration_report(sidecar, ranked_candidates=...)`
  emits a no-write calibration readout separating routing weight, source truth,
  and affect/personality boundaries.
- `build_public_behavior_trace_feedback_report(events, candidates, now=...)`
  measures public fixture feedback for helpful caution hints, irrelevant load
  drag / false positives, and over-personalization risk without serializing
  raw source handles or notes.
- `cognitive_load_private_calibration.py` reads clean-source
  `messages.jsonl` / `events.jsonl` or the local thread registry and emits a
  public-safe private-history aggregate report. It never serializes clean-source
  text, raw source refs, raw command text, thread ids, message ids, or paths.

The E2E50 scaffold can still accept optional `cognitive_load` rows through
`aippocampus_runtime/coding/sequence_packets.py`, but that path is a benchmark
read model. It is not the recall-sidecar owner and should not grow live recall
ranking behavior.

## Source Keys

Sidecar entries are keyed by `sha256:` hashes of stable source-ref fields such
as `source_id`, `thread_id`, `turn_id`, `message_id`, and source line. Raw local
paths, raw notes, prompt snippets, and stress narratives are deliberately
excluded from the public projection.

If an upstream behavior event already carries a stable `source_ref_hash`, the
sidecar preserves it. This lets a future private pipeline pre-hash source refs
without exposing path-like material to reports.

## Weighting Contract

Each known signal has a small additive weight. The final load boost is capped at
`0.16`, decays with a 30-day half-life from the latest event timestamp, and is
zeroed when the source is superseded or explicitly invalidated.

Candidate ranking remains separable:

- `semantic_score`: text or retrieval relevance.
- `source_authority`: currentness / source trust, with a small authority boost.
- `cognitive_load_boost`: caution-routing metadata only.

The load boost is blocked when candidate `source_status` is `refuted`,
`superseded`, `untrusted`, or `forbidden`, or when `source_authority` is below
`0.5`. This protects the source-as-world rule: load can increase caution, but
it cannot override source truth.

## Calibration Report

The #575 calibration report is deterministic and public-safe. It does not read
raw behavior notes; it reads only sidecar metrics, privacy flags, and optional
ranked-candidate score breakdowns.

It reports three axes separately:

- `routing_weight`: bounded load deltas, false-positive rate, decay coverage,
  and source-reopen recommendations.
- `source_truth`: source-authority and status gates that can block load boosts
  or ask for source refresh.
- `affect_or_personality_truth`: explicitly blocked; load signals do not infer
  stress, emotion, identity, personality, or user-trait truth.

The issue readout `issue_readouts.github_575` marks the baseline as
deterministic public-safe evidence. When the private-history runner supplies a
public-safe aggregate, `private_real_history_calibration` can become
`measured_public_safe_aggregate`; live hook capture, host-timing quality,
feedback-reviewed false-positive rates, caution-hint usefulness, and
user-visible recall improvement still remain unmeasured.

`build_public_behavior_trace_feedback_report()` is the public reproducibility
bridge for reviewed feedback. Public fixtures can mark a load signal as useful,
irrelevant drag / false positive, or over-personalization risk; the report keeps
only anonymized case ids, event kinds, feedback outcomes, counts, and rates.
It does not make the private aggregate cohort public, and it does not prove live
host timing or default foreground usefulness.

`build_public_default_path_usefulness_report()` is the #1375 public replay
slice. It validates one useful cognitive-load hint, two no-hint/no-op cases,
and one safe-but-draggy regression. The current recommendation is
`dogfood_diagnostic_only`: keep the sidecar as diagnostic/ranking metadata, not
as default foreground weighting or host-timing policy.

## Projection Boundary

Model-visible and public-safe rows must use the boundary string
`routing_caution_not_affect_or_personality_truth`.

Allowed projection:

- source-ref hash key
- load bucket
- reason codes
- bounded score breakdown
- source-reopen or refresh advisory
- count/rate metrics

Forbidden projection:

- local absolute paths
- raw stress summaries
- raw private snippets
- emotion or personality claims
- claims that load weight proves semantic relevance or source truth

The sidecar always carries `cannot_claim` entries for these forbidden
interpretations so reports do not silently promote "hard-won" into "true."

## Metrics

The first deterministic payload tracks the metric names required by #575:

- `high_load_source_reopen_rate`
- `pitfall_repetition_rate_after_high_load_signal`
- `load_weight_false_positive_rate`
- `load_weight_decay_coverage`
- `caution_hint_useful_rate`
- `irrelevant_load_drag_rate`
- `overpersonalization_from_load_signal_count`

Rates that need reviewer or outcome data return `null` until corresponding
event fields are present. That unknown state is intentional; it avoids claiming
calibration before private reviewed cases exist.

## Current Verification

`tests/aippocampus/test_cognitive_load_sidecar.py` covers the first slice:

- a high-load debugging source can outrank a stronger ordinary keyword match
  without hiding the score components;
- weak, untrusted, or superseded sources receive no load boost and ask for
  source refresh instead;
- public projection omits raw paths, raw notes, and emotion/personality claims;
- the calibration report separates routing-weight diagnostics from blocked
  affect/personality truth;
- caps, decay, invalidation, source authority, and metric slots remain visible.
- the private-history aggregate runner can convert clean-source message/event
  fixtures into load signals without leaking raw private text, source refs,
  paths, command text, or assistant text.
- the public behavior-trace feedback fixture reports useful caution, irrelevant
  drag / false positive, and over-personalization-risk outcomes without leaking
  source refs, raw notes, or local paths.
- the public default-path replay records useful-hint, no-op, and regression
  cases, then recommends diagnostic-only maturity rather than default adoption.

The dated private-history aggregate report is
[`docs/evidence/reports/cognitive-load-private-history-calibration-2026-06-08.md`](../../evidence/reports/cognitive-load-private-history-calibration-2026-06-08.md).
It scanned 100 local registry threads and marked private-history calibration as
measured for that cohort, but it still found no reviewed false-positive or
caution-usefulness rows. The public behavior-trace fixture now covers selected
reviewed outcomes, and the 2026-06-14 default-path replay shows the current
evidence is not strong enough for default foreground weighting. Future work
should only wire this into a live hook or broader host policy after live/default
evidence shows that the boost reduces repeated pitfalls without raising
over-personalization, annoyance, or memory-drag risk.
