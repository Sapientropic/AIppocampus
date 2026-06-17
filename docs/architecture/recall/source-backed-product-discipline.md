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

## Top Surfaces

| Surface | Class | Current role | Source-backed boundary | First audit check |
| --- | --- | --- | --- | --- |
| `aippocampus agent orient` | `missing_usability_counterweight` to guard | Task Orientation Packet for fresh-thread starts. | Derived read model over existing routes, not a truth store. | `python -m unittest tests.aippocampus.test_task_orientation_packet -v` |
| `aippocampus agent recall` | `useful_guard` | Source-backed route pull. | Compact packets are route selection; deepen before claims. | `tests/aippocampus/test_agent_opt_in_continuity.py` |
| `aippocampus agent deepen` | `load_bearing_guard` | Opens selected source route. | Claims are bounded to the reopened source window. | request-index and malformed-handle tests |
| `aippocampus agent aippo` | `progressive_disclosure` | Low-risk working-contract guidance. | Guidance shapes planning only; it does not prove project facts. | AIppo activation and explain tests |
| Active Path Packet | `substrate_only` by default | Chooses a few paths from existing sidecars. | Non-evidence paths require reopen; stale paths are boundaries. | `tests/aippocampus/test_active_path_packet.py` |
| Issue work guard | `useful_guard` | Prevents broad manual scaffolding before owner-route checks. | Navigation-only owner refs. | `tests/aippocampus/test_issue_work_guard.py` |
| Foreground action cards | `useful_guard` | Copyable next action for agents. | Commands must be executable or explicit templates. | `executable_command_violations` checks |
| MCP `agent_recall` / `agent_deepen` | `progressive_disclosure` | Host tool projection. | Compact default redacts private handles and local paths. | `tests/aippocampus/test_aippocampus_mcp_server.py` |
| Hook affordances | `overblocking` risk | Tiny prompt-time ignition. | No raw source, local paths, or source refs in hook output. | hook affordance tests |
| Background findings / observatory | `progressive_disclosure` | Reviewed navigation readouts. | Findings stay navigation-only until source is reopened. | foreground/output audit tests |

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
