# Source-Backed Learning Loop

Role: current contract.

The runtime owner is
`skills/aippocampus/scripts/aippocampus_runtime/learning_loop/`.

AIppocampus can now turn scrubbed coding behavior into a small learning loop:
behavior rows become review signals, repeated or ordered patterns become
candidates, and ripe guidance can reach Active Path Packet as a source-reopen
route. The route helps the next agent change action order before repeating a
known mistake; it does not become evidence.

## Runtime Shape

- `adapt_behavior_events_to_review_signals(...)` consumes categorical behavior
  rows: source refs, event refs, command/failure families, target/path
  fingerprints, scope, environment profile, freshness, and sequence order.
- `extract_learning_activations(...)` opens source-ref-gated learning
  activations for failed tool/test events. Expected TDD red stays review-only.
  Live `PostToolUse` failures can enter this path only after host payloads are
  scrubbed into behavior-event-shaped rows with source refs.
- `detect_recurring_failure_findings(...)` groups repeated failures by a narrow
  signature and retires patterns after later successful retries.
- `detect_workflow_order_findings(...)` recognizes guarded deterministic
  sequences: cheap preflight before broad tests, environment workaround before
  retry, and source/context reopen before retry.
- `extract_workflow_candidates(...)` recommends the smallest asset shape:
  extend an existing skill/AIppo/docs/checklist/automation/subagent/action-hint
  route, create a narrow skill, create a subagent, create an automation, add a
  checklist, or skip. Machine-local lessons are labelled as such and must not
  be packaged as general agent workflows.
- `aippocampus_runtime.learning_loop.effectiveness_ledger` records surfaced
  guidance and later outcomes as append-only navigation metadata.
- `aippocampus_runtime.learning_loop.private_export` converts operator-selected
  private rollouts or clean-source behavior files into sanitized replay events.
- `build_learning_action_time_packet(...)` projects eligible guidance into
  Active Path Packet route-readiness rows for fresh-thread or post-compaction
  orientation.
- `aippocampus_runtime.learning_loop.aippo_adapter` converts only eligible,
  source-ref-backed findings into low-authority AIppo seed rows and can feed
  the prepared action-time cache without making the hot hook run fresh search.
- `aippocampus_runtime.navigation.source_shape_projection` connects learning
  findings to macro live lanes, topology scout candidates, local/global
  compatibility checks, AIppo seeds, prepared action hints, and navigation
  potential diagnostics.
- `aippocampus_runtime.aippo.clause_lifecycle` keeps growing clauses cautious:
  source-backed probes, prerequisite/conflict resolution, freshness decay, and
  feedback severity may request deeper review, but self-report alone does not
  ripen a clause.

## Boundaries

The loop serializes no raw tool output, full commands, local paths, private
rollouts, or model-written rules. Dream/subconscious material can only become a
semantic hypothesis candidate with `foreground_eligible=false` and
`model_output_is_evidence=false`.

Action-time guidance is navigation, not truth. It must carry source refs and
reopen source before claims. Stale, refuted, local-only, already visible,
low-confidence, or one-off rows are suppressed before foreground projection.
Cross-layer projections keep the same authority or lower it. They may explain
which source trail to reopen; they may not promote a finding into truth because
more runtime layers noticed it.

Effectiveness reports are diagnostic. A fixture can show the route was surfaced
and that the next synthetic attempt used a better order; it cannot prove live
causal behavior lift.

## Replay Evidence

- Foreground status/guidance:
  `aippocampus learning status --json` and
  `aippocampus learning guidance --json`. These read prepared findings and
  point to the action-hint cache without scanning raw private history. The
  first card separates three lanes: `prepared_guidance` when local
  action-time hints are already available, `sanitized_replay` when the next
  useful step is to provide behavior-event rows, and `operator_diagnostics`
  for benchmark/internal checks that should not be mistaken for default
  foreground guidance.
- Private dogfood harness through the stable facade:
  `aippocampus learning replay --events <sanitized-events.jsonl> --json`.
  The input is a local/private behavior-event export, not raw rollout text. The
  report emits aggregate metrics such as
  `repeated_failure_detection_recall`, `workflow_order_detection_count`,
  `context_reopen_before_action_rate`, `false_positive_nudge_rate`, and
  `raw_private_text_leak_count`.
- Trusted operator/internal fallback for opt-in export+replay:
  `python3 -m aippocampus_runtime.learning_loop.private_replay --rollout <local-rollout.jsonl> --export-output <tmp-events.jsonl> --json`.
  The export output is local-private and should not be committed.
- Public companion eval:
  `python3 benchmarks/aippocampus/benchmark_learning_loop_public_companion.py --json`.
  It reuses `benchmark_corpus/public_longitudinal_users/rollout_behavior_events_v2.json`
  and `vcs_future_events_v1.jsonl`, separates
  `private_dogfood_comparable_metrics` from `public_reproducible_metrics`, and
  records source-shape gaps when public fixtures do not express workflow order,
  environment workaround, or context-reopen cases.

Private dogfood can show local usefulness. The public companion keeps a
shareable counterpart. Neither one is an official STATE-Bench held-out score,
private-history generality proof, or causal product-lift claim.

Latest local private-history readout:
[`learning-loop-private-replay-2026-06-15.md`](../../evidence/reports/learning-loop-private-replay-2026-06-15.md).

## Cross-Layer Fixture Surface

The #1613-#1619 closeout adds deterministic unit fixtures rather than a new
benchmark score. The useful public claim is narrower: learning-loop findings
can now be bridged into AIppo seeds, source-shape projections, clause probes,
feedback ledgers, microcircuit diagnostics, semantic-subregion budgets, and
controlled salience decay while preserving source-reopen boundaries.

Run the focused fixture set with:

```powershell
python3 -m unittest tests.aippocampus.test_learning_loop_aippo_adapter tests.aippocampus.test_aippo_clause_lifecycle tests.aippocampus.test_source_shape_projection tests.aippocampus.test_circuit_feedback tests.aippocampus.test_microcircuit_router tests.aippocampus.test_semantic_subregion_budget -v
```
