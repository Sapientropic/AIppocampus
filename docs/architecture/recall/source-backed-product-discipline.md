# Source-Backed Product Discipline

Role: current contract.
Status: audit and implementation boundary for foreground recall surfaces.

AIppocampus should make a later agent better at choosing where to reopen
source. It should not make the agent feel licensed to invent facts from
summaries, scents, embeddings, or old sidecars.

This page is the canonical recall-layer audit pointer for source-backed as a
product discipline. It does not replace the source layer or evidence ledger.

## Operating Rule

Every foreground continuity surface must answer four questions:

1. What should the agent do next?
2. Is the output route selection, bounded evidence, or source-open evidence?
3. What must be reopened before public, exact, stale, sensitive, or issue-closeout claims?
4. What private material is intentionally absent from the foreground packet?

If a surface cannot answer those, it should stay behind local diagnostics or
return a recovery card instead of expanding the public foreground shape.

Conversation-memory orientation uses a product ladder on top of the existing
source-backed trust contract:

- `working_orientation`: useful planning context, not source truth.
- `source_reachable`: compact orientation plus the smallest route to reopen
  before a load-bearing claim.
- `bounded_evidence`: reopened clean source within a declared scope.
- `source_open`: source is open to the host and still scope/redaction-bound.
- `blocked_or_retired`: stale, private, conflicted, or superseded material.

Compact/default foreground packets have an armor budget: no visible
`cannot_claim` list, at most two visible boundary/reopen prompts, and at least
two useful guidance signals such as situation, unknown, display hint, route
label, or next action. Full, explain, deepen, diagnostics, and operator views
may retain detailed source trails and boundary fields.

## Top Surfaces

| Surface | Class | Current role | Source-backed boundary | First audit check |
| --- | --- | --- | --- | --- |
| `aippocampus agent orient` | `missing_usability_counterweight` to guard | Task Orientation Packet for fresh-thread starts. | Derived read model over existing routes, not a truth store. | `python -m unittest tests.aippocampus.test_task_orientation_packet -v` |
| `aippocampus agent recall` | `useful_guard` | Source-backed route pull. | Compact packets are route selection; deepen before claims. | `tests/aippocampus/test_agent_opt_in_recall_routes.py` / `tests/aippocampus/test_agent_opt_in_cli_contracts.py` |
| `aippocampus agent deepen` | `load_bearing_guard` | Opens selected source route. | Claims are bounded to the reopened source window. | request-index and malformed-handle tests |
| `aippocampus agent aippo` | `progressive_disclosure` | Low-risk working-contract guidance. | Guidance shapes planning only; it does not prove project facts. | AIppo activation and explain tests |
| Active Path Packet | `substrate_only` by default | Chooses a few paths from existing sidecars. | Non-evidence paths require reopen; stale paths are boundaries. | `tests/aippocampus/test_active_path_packet.py` |
| Issue work guard | `useful_guard` | Prevents broad manual scaffolding before owner-route checks. | Navigation-only owner refs. | `tests/aippocampus/test_issue_work_guard.py` |
| Foreground action cards | `useful_guard` | Copyable next action for agents. | Commands must be executable or explicit templates. | `executable_command_violations` checks |
| MCP `agent_recall` / `agent_deepen` | `progressive_disclosure` | Host tool projection. | Compact default redacts private handles and local paths. | `tests/aippocampus/test_aippocampus_mcp_server_catalog.py` / `tests/aippocampus/test_aippocampus_mcp_server_recall.py` |
| Associative Path Walker diagnostics | `progressive_disclosure` | Explicit `why-recall --apw-diagnostics` sidecar plus a narrow `agent recall` recovery action for weak/no-route recall. | Current build posture is `semi_default_recovery`: APW may append one secondary source-reopen action only when ordinary recall is weak or silent and APW candidate sidecars exist. It is not default ranking. `AIPPOCAMPUS_APW_PROMOTION_MODE=opt_in` rolls back to explicit fallback; `off` suppresses recall fallback. | `tests/aippocampus/test_agent_recall_apw_fallback.py` / `tests/aippocampus/test_associative_path_inputs.py` / `tests/aippocampus/test_associative_path_source_shape.py` |
| Hook affordances | `overblocking` risk | Tiny prompt-time ignition. | No raw source, local paths, or source refs in hook output. | hook affordance tests |
| Background findings / observatory | `progressive_disclosure` | Reviewed navigation readouts. | Findings stay navigation-only until source is reopened. | foreground/output audit tests |

## Recall Quality Gates

Two public-safe gates guard the foreground usability boundary:

- `benchmark_associative_path_walker.py` checks the Associative Path Walker
  promotion gate: source-reopenable bridge rescue, no generic wrong-hop drag,
  no projected source-free scent, no irrelevant drag, no manual-search-before-APW
  fixture regression, no cross-scope positive-feedback lift, Chinese dogfood cue
  coverage, and no default recall-ranking influence.
- `benchmark_conversation_orientation_usefulness.py` checks that compact
  working orientation can beat safe-but-useless caveat output without source
  truth overclaim.

Score-fusion calibration also reports a public-safe retrieval quality slice in
`live_score_fusion_quality`; that slice is measured, but it still cannot claim
production, private-history, or broad live ranking lift without a separate
dogfood/live run.

## APW Recall Promotion Boundary

APW is promoted only to `semi_default_recovery` in the current build. The
default `agent recall` ranking path remains unchanged; APW can only append one
secondary deepen request after ordinary recall is weak or silent and a
navigation-potential or active-lock APW candidate sidecar exists. Missing
candidate sidecars stay silent in compact foreground output.

The recall payload exposes `associative_path_policy` with:

- `current_build_posture`: `semi_default_recovery`, `opt_in`, or `off`;
- `run_reason`: why APW did or did not run;
- `rollback_env`: `AIPPOCAMPUS_APW_PROMOTION_MODE=opt_in`;
- `applied_to_default_ranking = false`.

The benchmark report exposes `promotion_gate`. Semi-default recovery is blocked
when wrong-hop drag, irrelevant drag, projected source-free scent,
manual-search-before-APW, route-without-action, action-without-source-reopen,
decision mismatch, scope violation, or default-ranking influence exceed their
listed thresholds. That gate permits only the recovery surface above. Default
ranking or claim-authority promotion still requires separate live/private-history
evidence and issue review.

## Task Orientation Packet Boundary

`aippocampus agent orient "<task>" --json` is the current fresh-thread
orientation layer. It exists to reduce blind search and blind deepen for
issue-scale work by combining:

- issue-work guard owner refs;
- AIppo working-contract constraints;
- external source anchor roles;
- Active Path Packet selection;
- the compact projection of `aippocampus_understanding_state.v1`.

The packet is intentionally derived and no-write. It may say which source route
to try first, which stale anchors should not rank as current, and which private
replay aggregate could be used later. It must not serialize raw private
history, local paths, source handles, or live quality-lift claims.

The full Understanding State read model is richer than the default foreground
packet. It may compose continuity domains, pathlets, Journey, Episode/Arc,
repo familiarity, external anchors, and mature learning constraints, but the
default packet should carry only component status, the small foreground route
projection, and the short boundary needed to start well. Detailed lifecycle,
gap, and audit fields belong behind progressive disclosure.

`aippocampus agent orient --eval --json` is a deterministic public fixture. It
compares route-only recall, static summary context, Task Orientation Packets,
and Task Orientation Packets plus mature constraints. It can show that the
packet shape reduces broad manual search inside the fixture while preserving
source-truth overclaim rate. It cannot claim live recall improvement. Private
history replay remains opt-in, aggregate-only, and outside the default
foreground packet; `--private-replay-aggregate` and
`--private-replay-events <sanitized-events.jsonl>` project only aggregate
learning-loop replay metrics.

## Closing Issues

Before closing recall, AIppo, benchmark, source-side, or architecture issues,
the agent should reopen current issue comments and run the relevant source route
or owner test. A Task Orientation Packet can guide the first route, but issue
closure still needs fresh evidence from source, code, tests, or verified
GitHub state.

For PRs that touch recall, orient, AIppo, ambient, MCP compact, hook, or
foreground-action surfaces, closeout should also name the foreground usefulness
delta. The useful check is not "did we add more caveat fields?" but "does the
next foreground agent know the situation, the load-bearing unknown, and the
smallest useful next action or reopen route?" Visible `cannot_claim`,
`claim_boundary`, or source-open pressure belongs in compact/default output only
when it answers that load-bearing risk; otherwise keep the detail behind
full/explain/deepen/operator views.
