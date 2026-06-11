# Coordination Topology Diagnostics

Role: current contract.
Status: deterministic V0 diagnostic contract for #1266.

Coordination topology diagnostics are Telepathy's first executable shape. They
do not make agents share a mind, assign work, or bypass source reopen. They
inspect public-safe coordination rows and explain where multi-agent work is
colliding, looping, orphaned, or crossing a boundary.

The runtime owner is
`aippocampus_runtime.ops.coordination_topology`.

## Input Shape

The V0 report accepts synthetic or public-safe rows that describe:

- participating agents or agent groups;
- scope ids and whether a scope is fragile or adjacent to another scope;
- visible handoff cards or coordination packets;
- route ownership and reopenability;
- bridge/cut-point signals;
- repeated stale or rejected route reopen attempts;
- privacy/candidate/source-handle crossing indicators.

Inputs may come from Telepathy coordination packets, soft locks, handoff cards,
route packets, or topology detectors. The canonical packet contract lives in
[`telepathy-coordination-packets.md`](telepathy-coordination-packets.md). V0
fixtures are checked-in and synthetic; they are not private-history evidence.

Runtime position is deliberately narrow: run these checks after packets or
handoff artifacts already exist, and expose full detail through `explain`,
debug reports, or Campus. V0 is not an every-turn Telepathy scan. Foreground
surfaces should get at most a tiny tag when the diagnostic changes action
selection.

## Diagnostics

The deterministic fixture covers:

| Diagnostic | Meaning | Operator-facing hint |
| --- | --- | --- |
| `healthy_handoff` | Ownership, packet visibility, and source reopen path are clear. | Continue with visible handoff. |
| `collision` | Two active agents touch the same fragile scope without a handoff. | Open a coordination packet or pause overlap. |
| `overlap_without_coordination` | Adjacent scopes are likely to collide, but no visible packet exists. | Explain the coordination gap. |
| `orphan` | A route or conclusion lacks owner or reopen path. | Repair owner or source route. |
| `cut_point` | One packet is the only bridge between work branches. | Review the bridge before branch work. |
| `loop` | Agents repeatedly reopen the same stale or rejected route. | Suppress the loop and reopen source before reuse. |
| `boundary_crossing` | Private, candidate, or source-handle material crossed agent/task boundary. | Review boundary before cross-agent use. |
| `handoff_knot` | Task state, source support, and ownership are entangled. | Review handoff before assignment. |

Diagnostics also project a `topology_shape` and `maintenance_action_hint` so
map-rot maintenance can consume the same shape vocabulary without treating this
report as a writer.

## Metrics

The report owns these #1266 counters:

```text
agent_collision_count
overlap_without_coordination_count
orphaned_handoff_count
cut_point_count
boundary_crossing_count
repeated_stale_route_loop_count
handoff_knot_count
healthy_handoff_count
privacy_clean_but_coordination_useless_count
```

`privacy_clean_but_coordination_useless_count` is the bridge to #1185: a row
can have no privacy leak and still be useless coordination.

## Boundary

The report is read-only and no-write:

- `navigation_only = true`
- `assignment_created = false`
- `claim_permission = no_claim_before_source_reopen`
- `write_mode = no_write_diagnostic_only`
- `runtime_position = post_packet_explain_side`
- `every_turn_scan = false`

It must not emit raw private text, local paths, source handles, chain-of-thought,
or private packet payloads. Public output uses hashes, counts, reason codes, and
bounded action hints only.

## Related Owners

- [`cross-agent-recall-isolation.md`](cross-agent-recall-isolation.md) owns the
  pre-output scope filter and leak red lines. Coordination topology may detect a
  boundary crossing, but it does not authorize cross-agent recall.
- [`telepathy-coordination-packets.md`](telepathy-coordination-packets.md) owns
  the soft-lock, handoff-card, source-support, and readiness packet shape.
- [`agent-native-recall-facade.md`](agent-native-recall-facade.md) owns compact
  recall/deepen/explain packet shape. Coordination diagnostics can be explained
  through that facade later, but V0 does not add a foreground hook.
- [`source-backed-attention-router.md`](source-backed-attention-router.md) owns
  route-packet authority. Topology shapes are route/navigation pressure, not
  source truth.
- [`topology-anchor-policy.md`](topology-anchor-policy.md) owns source-graph
  lifecycle pressure for anchors. This document owns multi-agent coordination
  topology.

## Claim Boundary

This contract supports a narrow claim:

```text
AIppocampus has deterministic public-safe diagnostics for first Telepathy
coordination topology failure shapes.
```

It does not prove distributed locks, multi-agent orchestration, live Telepathy
quality, private multi-agent history quality, shared chain-of-thought, or that
coordination diagnostics may override foreground agent judgment.
