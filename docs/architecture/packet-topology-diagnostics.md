# Packet Topology Diagnostics

Role: current contract.
Status: deterministic V0 packet-relation diagnostic contract for #1263.

Packet topology diagnostics ask one narrow question: did an already-built route,
narrative, Macro, Dream, or AIppo packet stay inside its declared relation?

The runtime owner is
`aippocampus_runtime.ops.packet_topology_diagnostic`.

This is not a new truth layer, score layer, Macro Orientation schema, or
compatibility/gluing algorithm. It names shape failures after a packet exists so
`explain`, debug reports, or Campus can show why a packet should be reopened,
reviewed, suppressed, or treated as navigation only.

## Naming Boundary

Do not add or rely on a generic `position` field here. Macro Orientation owns
project-level macro roles, active layers, and relation-position vocabulary.
This diagnostic uses `packet_topology_diagnostic` and packet relation fields so
it does not compete with Macro Orientation.

## Runtime Boundary

V0 runs post-packet:

- after MemoryPacket, narrative packet, route packet, Macro packet, Dream
  candidate, or AIppo activation material already exists;
- when `explain`, debug reports, or Campus asks for the full diagnostic;
- not as pre-recall search;
- not as an every-turn scan;
- not as a foreground context dump.

Foreground projection should stay tiny and only appear when it changes action
selection. Full detail belongs behind explain/debug/Campus.

## V0 Diagnostics

The deterministic fixture covers reducible contract cases:

| Diagnostic | Trigger |
| --- | --- |
| `authority_overreach` | `direction_only` or navigation-only packet rendered as evidence; Macro rendered as an action instruction; Dream/AIppo candidate rendered as certainty; source handle rendered as fact. |
| `missing_middle_or_cut_point` | Narrative/pathlet packet declares a missing middle or cut-point source gap. |
| `explicit_route_cycle` | A stale/rejected route is repeatedly reopened. |
| `agency_suppression_fixture` | A useful packet is over-filtered even though no safety red line fired. |
| `knot_without_unlinking_move` | Hand-authored contract fixture for entangled obligations without an unlinking move. |
| `relation_preserved` | Healthy navigation packet keeps route-to-source relation and claim boundary intact. |

`knot_without_unlinking_move` is explain-side vocabulary in V0. It is not a
general knot detector, and it should not be promoted without reducers and
low-false-positive evidence.

## Metrics

The report owns:

```text
navigation_as_claim_count
candidate_as_authority_count
macro_as_decision_count
source_handle_as_fact_count
agency_suppression_count
knot_without_unlinking_move_count
explicit_route_cycle_count
missing_middle_or_cut_point_count
borromean_break_count
```

`borromean_break_count` is not an always-on background counter. The product
invariant `source + user need + agent agency` is counted only when a packet is
foreground-visible or action-shaping. Idle/background/silent-cache packets do
not count.

## Boundary

Every emitted row keeps:

- `claim_permission = navigation_only_not_fact`
- `full_diagnostic_surface = explain_debug_or_campus`
- `foreground_projection_tiny = true`
- `topology_truth_source = false`
- `score_layer_changed = false`

The report must not emit raw private text, local paths, raw source handles,
chain-of-thought, or private packet payloads.

## Related Owners

- [`source-backed-attention-router.md`](source-backed-attention-router.md) owns
  route-packet authority, masks, and score-fusion policy. Packet topology may
  name an overreach shape; it does not change router weights.
- [`agent-native-recall-facade.md`](agent-native-recall-facade.md) owns
  MemoryPacket foreground/deepen/explain shape and compact Macro packets.
- [`continuity-domains.md`](continuity-domains.md) points to the narrative
  packet runtime owner for #700 pathlets.
- [`coordination-topology-diagnostics.md`](coordination-topology-diagnostics.md)
  owns Telepathy coordination topology. Packet topology owns route/narrative/
  Macro/Dream/AIppo relation preservation.

## Claim Boundary

This contract supports a narrow claim:

```text
AIppocampus has deterministic packet-relation diagnostics for selected
navigation, candidate, Macro, Dream, route-cycle, and missing-middle failures.
```

It does not prove live agent lift, broad topology quality, mathematical knot
theory, Dream candidate truth, Macro Orientation correctness, or sheaf-style
local/global packet compatibility.
