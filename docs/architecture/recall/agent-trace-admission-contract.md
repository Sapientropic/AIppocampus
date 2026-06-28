# Agent Trace Admission Contract

Role: current contract.
Status: canonical boundary for trace-derived navigation reuse.

Agent traces can help a future agent reopen the right source, but they are not
source truth. This contract is the shared vocabulary for route-note, closeout,
receipt, breadcrumb, alias, trajectory, graph, and training-signal work.

## Admission Levels

| Level | Foreground | Graph Ingress | Candidate Funnel |
| --- | --- | --- | --- |
| `ignore` | Not surfaced. | Never enters graph. | Cannot enter. |
| `operator_only` | Count/report only in detail/operator. | No graph edge. | Cannot enter. |
| `navigation_candidate` | Staging or low-confidence route only. | Staging contribution only. | Draft candidate. |
| `reopenable_route` | May expose one reopen action/boundary. | Typed contribution after owner gate. | Actionable reopenable route. |
| `bounded_evidence_after_open` | Only after source is opened, within scope. | Typed contribution after source open. | Source-open claim-ready within scope. |

## Trace Families

Admissible families:

- assistant final-answer closeout metadata;
- successful recall/deepen/source-open follow-through;
- current-thread recall cue positioning;
- bounded test/check/source-open/GitHub receipts;
- public-safe repo-relative breadcrumbs;
- joined route notes and trajectory packets.

Ignored or operator-only by default:

- routine commentary and chain-of-thought-like process prose;
- raw stdout/stderr, raw tool output, full command args, raw local paths, and
  secret-shaped material;
- selector/cache internals, policy/gate matrices, full receipt inventories, and
  suppressed candidates.

## Authority Joins

- `reported_and_receipted_navigation`: final answer report plus matching
  behavior/source receipt. Usually `reopenable_route`.
- `agent_reported_navigation_only`: final answer report with source refs but no
  receipt. Usually `navigation_candidate`.
- `behavior_receipt_navigation`: source-open/check/tool receipt with bounded
  source refs. Usually `reopenable_route` or `bounded_evidence_after_open`.
- Later contradiction, failure, stale source, or wrong-route feedback degrades
  the row to recheck, parked, hard-negative, or operator-only according to the
  owning lifecycle.

## Training Signal Role

Every durable behavior-derived row should name one role:

- `positive_demo`;
- `hard_negative`;
- `process_supervision`;
- `replay_sample`;
- `hindsight_relabel`;
- `none`.

The role is training/eval metadata, not factual authority. Compact foreground
output must translate the row into a small action/boundary and must not dump a
training ledger.

## Behavior Training Signal Ledger

The executable owner is
`aippocampus_runtime.source.agent_trace_admission`. It projects trace and
feedback rows into public-safe `aippocampus_behavior_training_signal` rows.

Ledger rows may carry cue hashes, source-ref digests, source-ref counts,
learning / replay priority, contrastive preferred-vs-rejected route pairs, and
micro data-card fields. They must not carry raw prompts, raw commentary, raw
tool output, full command args, local absolute paths, or private source text.

Learning priority is a promotion / replay queue hint, not foreground ranking
magic. Higher priority belongs to low-frequency, previously missed,
manual-recovered, multilingual / non-obvious cues that later source-opened with
anchors or reduced manual search. Generic successes should not crowd out rare
high-information rows.

Contrastive pairs should stay cue- and scope-local. A rejected route should be
demoted against the route that won for the same cue/scope; it should not become
a global memory blacklist.

## Current-Thread Recall Positioning

Explicit `agent recall` cues also position the current thread. This is a
navigation side effect, not an old-memory alias and not source truth.

`recall/semantic_cue_cache.py` owns `aippocampus_recall_semantic_position`
rows in the same semantic-cue owner file so agents do not create another
semantic sidecar family. Rows store prompt hashes, sanitized cue terms,
script/language buckets, intent buckets, recall-status counts, and a source
generation hash when available. They must not store raw prompt text, raw local
paths, secret-shaped terms, or source text.

No-hit / low-confidence recall attempts stay `draft_candidate_staging` with
`training_role=replay_sample` and `authority_level=direction_only`.
Registry-wide search may use these rows to surface one current-thread
source-open action as `recall_semantic_position_candidate`, but that action is
navigation-only until the source window is opened. It must not promote a
source-backed answer, a semantic alias, or a concept-graph edge by itself.

## Speculative Candidate Funnel

Draft recall, graph, semantic, trace, and feedback candidates should pass
through the shared candidate lifecycle before compact foreground exposure:

1. `draft_candidate`: producer emitted a bounded proposal with a stable dedupe
   key and intended-use boundary.
2. `actionable_reopenable_route`: verifier or owner evidence says a foreground
   agent can open the route.
3. `source_open_claim_ready`: source opened and claims are bounded to that
   source window.
4. `rejected_hard_negative`: wrong-route, dismissed, or manual-search-after-
   route evidence demotes the candidate for the same cue/scope.
5. `parked_privacy_blocked`, `parked_stale_recheck`, `deduped_duplicate`,
   `staging_needs_refine`, or `replay_only_missed_opportunity`: not compact
   foreground material.

Compact projection may expose one verified action and one boundary. Generated
candidate counts, verifier splits, reason inventories, source-ref digests, and
training data cards belong to detail/operator output.

## Graph Ingress And Adoption

Trace-derived graph ingress consumes admitted training signals, not raw trace
rows. Positive demos and process-supervision rows may become typed graph
candidates after source/reopen evidence. Hard negatives park or demote edges.
Replay samples stay evaluation material until a later source-open verifier
promotes them.

Graph adoption is gated on useful source-open lift and quality metrics, not
edge volume. The guard should report generated, foreground-exposed,
verifier-seen, source-open-hit, wrong-route, false-accept, missed-opportunity,
and bytes-per-useful-candidate counts. A trace-derived graph row that improves
edge count but not source-open usefulness remains staging/detail-only.

## Micro Data Card

Detail/operator rows may carry:

- `intended_use`;
- `not_for`;
- `freshness` or recheck trigger;
- `authority_after_open`;
- `training_role`;
- `source_state` / receipt state.

Compact output shows at most one decision, one next action/handle, and one
claim boundary. Receipt inventories, source refs, proof gates, and data-card
details stay in detail/operator surfaces.

## Owners

- `recall/route_notes.py` owns commentary-derived route-note extraction.
- `source/source_texture.py` owns source-texture projection.
- `source/behavior_events.py` owns bounded behavior event extraction.
- `source/agent_trace_admission.py` owns this executable vocabulary and compact
  projection guard, behavior training-signal ledger, and speculative candidate
  lifecycle.
- `recall/semantic_cue_cache.py` consumes positive-demo rows for cue alias
  promotion without treating aliases as source truth, and owns
  current-thread recall semantic-positioning rows.
- `recall/feedback/events.py` consumes hard-negative and positive-demo rows for
  reversible, route-local suppression.
- `navigation/concept_graph_contributions.py` and
  `navigation/data_quality_guard.py` own trace-derived graph candidates and
  source-open adoption metrics.
- #2860-#2865, #2868-#2871 should consume this contract instead of adding
  trace-local authority words.
