# Cross-Agent Recall Isolation

Role: current contract.
Status: fixture-backed hard-negative contract for #1135.

AIppocampus read surfaces must not let one agent, provider, or private scope
leak through another path just because a convenience search, cache, semantic
sidecar, or MCP-style route can find the same underlying store row.

The runtime owner is
`aippocampus_runtime.recall.cross_agent_isolation`.

## Boundary

The shared rule is simple:

```text
apply scope filter before emitting scent, route, bounded evidence, or source-open material
```

Private source from `agent_a` is readable by `agent_a` inside the same provider
scope. `agent_b` must receive `ignore_or_blocked`, silence, or public-safe
diagnostics. Explicit shared/project scope is allowed only when the fixture
declares both the shared project scope and the allowed agents.

## Covered Read Paths

The fixture covers these agent-facing or public-read-like surfaces:

- `search_memory`
- `recall_context`
- `recall_deepen`
- `prompt_hot_path`
- `semantic_sidecar`
- `cached_summary`

The point is not that these are all implemented by one runtime function today.
The point is that they share the same pre-output isolation contract, so a fast
path cannot bypass a filter that a slower path already honored.

## Metrics

The fixture reports:

```text
blocked_scope_hit_count
allowed_shared_scope_count
fast_path_bypass_prevented_count
cross_scope_recall_leak_count
cross_scope_route_leak_count
cross_scope_evidence_leak_count
```

The red lines are:

```text
cross_scope_recall_leak_count = 0
cross_scope_route_leak_count = 0
cross_scope_evidence_leak_count = 0
```

Unit tests also construct an intentionally leaky cached-summary case to prove a
missed filter increments the leak counters.

## Privacy Boundary

Public reports use synthetic hashes and aggregate counters only. They must not
emit raw private source markers, raw source text, local paths, source snippets,
or real registry text.

## Claim Boundary

Passing this contract supports:

```text
AIppocampus has deterministic hard-negative coverage for cross-agent recall
isolation across agent-facing read paths.
```

It does not support enterprise multi-tenant authorization being complete, live
AgentMemory behavior, private real-history isolation being proven, or blanket
suppression as a product policy.

## Related Owners

- [`agent-native-recall-facade.md`](agent-native-recall-facade.md) owns the
  recall/deepen/explain packet shape.
- [`coordination-topology-diagnostics.md`](coordination-topology-diagnostics.md)
  owns Telepathy V0 coordination-shape diagnostics. It can report boundary
  crossings, but it does not authorize cross-agent recall.
- [`telepathy-coordination-packets.md`](telepathy-coordination-packets.md) owns
  Telepathy V0 soft-lock and handoff-card packets. Isolation filters still apply
  before any packet is emitted.
- [`source-backed-attention-router.md`](source-backed-attention-router.md) owns
  route-packet authority and hard masks.
- [`foreground-memory-ux-budget.md`](foreground-memory-ux-budget.md) owns
  foreground packet size and anti-nag behavior.
