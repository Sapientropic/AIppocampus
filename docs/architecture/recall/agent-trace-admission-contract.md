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
  projection guard.
- #2860-#2865, #2868-#2871 should consume this contract instead of adding
  trace-local authority words.
