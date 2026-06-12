# Telepathy Coordination Packets

Role: current contract.
Status: deterministic V0 packet contract for #1264 and #1265.

Telepathy coordination packets are the small shared object for multi-agent
coordination. They are not shared thought. They say what is being touched, what
kind of support exists, whether a handoff is ready, and which boundary should
stop another agent from continuing.

The runtime owner is
`aippocampus_runtime.ops.telepathy_coordination_packet`.

## Canonical Terms

| Term | Meaning |
| --- | --- |
| `scope claim` | A public-safe scope label or hash showing where work is active. |
| `soft lock` | Advisory "someone is touching this" signal. It is not a transactional lock. |
| `handoff card` | A compact route card for continuing work, with support/readiness fields. |
| `coordination packet` | The full explain/debug/Campus-side object containing scope, owner, mode, support, flags, and next safe action. |
| `ownership hint` | Sanitized owner/session reference for coordination only, not identity truth. |
| `boundary crossing` | Privacy, task, source, or candidate-authority boundary that blocks safe glue. |
| `handoff readiness` | Whether another agent can continue from a route, evidence, human decision, or must stop. |

## Stable Fields

V0 packets normalize synthetic or public-safe rows into:

```json
{
  "kind": "telepathy_coordination_packet",
  "scope": "project:AIppocampus#issue:1265",
  "coordination_mode": "soft_lock|handoff|watch|blocked|human_needed",
  "owner_ref": "agent_or_session_stable_id",
  "status": "active|ready_for_handoff|stale|blocked|released",
  "source_support": "source_open|bounded_evidence|reopenable_route|candidate_only|ignore_or_blocked",
  "boundary_flags": ["source_reopen_required"],
  "handoff_readiness": "not_ready|route_ready|evidence_ready|needs_human|blocked|released",
  "claim_permission": "navigation_only_not_fact"
}
```

Every packet also carries `next_safe_action`, a small `foreground_projection`,
and a `handoff_card`. The foreground projection is intentionally much smaller
than the full packet and is not enabled as a default hook surface.

`topology_row_from_coordination_packet()` can project a packet into the existing
coordination-topology diagnostic row shape. That bridge is deliberately one
way: packet fields can be diagnosed for collision, handoff-knot, orphan, or
boundary-crossing shape, but topology diagnostics do not assign work or upgrade
packet authority.

## Opt-In Local Handoff Workflow

The first executable lifecycle surface is
`aippocampus_runtime.ops.telepathy_handoff_store` and the facade command:

```sh
aippocampus telepathy create --scope project:AIppocampus#issue:1287 --owner codex-a --json
aippocampus telepathy list --json
aippocampus telepathy deepen <card_id> --json
aippocampus telepathy release <card_id> --json
```

The store is an explicit append-only JSONL event log under the thread registry
by default, or under `--store-path` for public fixtures and local tests. It is
append-only so release/create history remains auditably visible to the local
operator; released cards no longer appear in the default active list.

MCP intentionally exposes only `list_telepathy_handoffs` and
`deepen_telepathy_handoff`. Creating and releasing cards stays a CLI-only,
local-operator action until MCP write semantics have separate proof for user
control, provenance, idempotence, and privacy. Source refs stored on a card are
sanitized to stable selector fields or fingerprints; raw source handles, local
paths, private text, and chain-of-thought are not a handoff channel.

Candidate-only handoffs remain `navigation_only_not_fact`. A card can tell the
next agent where to reopen source, but it cannot upgrade another agent's note
into evidence merely because it entered the handoff store.

## Fixture Coverage

The deterministic fixture covers:

- active soft lock;
- clean handoff with a reopenable route;
- candidate-only handoff that cannot be treated as evidence;
- privacy-blocked coordination packet;
- stale or released soft lock;
- human-needed handoff.

The report owns these counters:

```text
active_soft_lock_count
clean_handoff_count
candidate_only_handoff_count
privacy_blocked_packet_count
stale_or_released_lock_count
human_needed_count
foreground_projection_max_bytes
```

## Boundary

Telepathy packets are navigation-only coordination material:

- `soft_locks_are_advisory_not_transactional = true`
- `handoff_cards_are_source_routes_not_truth = true`
- `source_reopen_required_before_claim = true`
- `cross_agent_isolation_applies_before_output = true`
- `packet_projects_to_coordination_topology_rows = true`
- `failed_glue_is_obstruction_not_assignment = true`
- `no_shared_chain_of_thought = true`

They must not emit raw private source text, local paths, raw source handles,
chain-of-thought, or private reasoning. Candidate-only handoffs can suggest
where to reopen source; they cannot become evidence because another agent wrote
them.

## Related Owners

- [Discussion #523](https://github.com/Sapientropic/AIppocampus/discussions/523)
  defines the product stance: courtesy with memory, not a hive mind.
- [Discussion #1262](https://github.com/Sapientropic/AIppocampus/discussions/1262)
  owns positional-topology framing.
- [Discussion #1270](https://github.com/Sapientropic/AIppocampus/discussions/1270)
  owns the sheaf/local-global framing: failed glue becomes an obstruction, not
  an assignment.
- [`coordination-topology-diagnostics.md`](coordination-topology-diagnostics.md)
  diagnoses collisions, orphans, loops, cut points, boundary crossings, and
  handoff knots over coordination rows or packets.
- [`cross-agent-recall-isolation.md`](cross-agent-recall-isolation.md) owns
  pre-output scope filters and hard-negative leak tests.
- [`agent-native-recall-facade.md`](agent-native-recall-facade.md) owns compact
  recall/deepen/explain packet shape; Telepathy full detail belongs behind
  explain/debug/Campus before any foreground surface.
- [`continuity-domains.md`](continuity-domains.md) and
  [Discussion #700](https://github.com/Sapientropic/AIppocampus/discussions/700)
  own narrative/pathlet source routes that handoff cards may point toward.

## Claim Boundary

This contract supports a narrow claim:

```text
AIppocampus has deterministic public-safe Telepathy coordination packet
fixtures for soft locks, handoff cards, boundary flags, and handoff readiness.
```

It does not prove distributed lock correctness, live multi-agent orchestration
quality, shared private memory, shared chain-of-thought, central-planner
assignments, or source-reopen bypass safety.
