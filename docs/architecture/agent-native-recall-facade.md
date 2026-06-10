# Agent-Native Recall Facade

Role: current contract.
Status: small fixture-backed architecture contract, not a public SDK promise.

This facade is the small agent-facing shape over existing AIppocampus recall
authority. It lets an agent ask for useful orientation without learning every
internal head, mask, lifecycle row, and source-support ledger first.

The facade does not replace MCP, source reopen, or the source-backed attention
router. It projects those surfaces into three agent-native moves:

```text
recall(query, context) -> MemoryPacket[]
deepen(route_id, options?) -> SourceRoute | SourceBackedEvidence | Blocked | CannotVerify
explain(route_id) -> WhyRecall | WhyNotRecall
```

The first fixture-backed contract lives in
`aippocampus_runtime.recall.agent_facade_contract`. It is deliberately a
projection and example surface. It does not make `recall`, `deepen`, or
`explain` public network endpoints.

## Memory Packet

Foreground `MemoryPacket` values stay compact:

```json
{
  "route_id": "route_project_workflow_summary",
  "output_mode": "bounded_summary_as_route",
  "display_hint": "Use the bounded route for project:AIppocampus/workflow; reopen source before claims.",
  "claim_permission": "no_claim_before_reopen",
  "next_action": "use_hint"
}
```

Packets may include a derived `deepen_route_id`, but they must not include
source handles, source ids, spans, head votes, masks, full support ledgers, raw
private text, or local paths. The packet is for action orientation, not
provenance inspection.

## Output Mapping

The facade preserves the existing action grammar instead of adding a new
authority layer:

| Route output | Facade output | Claim permission | Default next action |
| --- | --- | --- | --- |
| `direction_only` | `direction_only` | `no_claim_before_reopen` | `use_hint` |
| `bounded_summary_as_route` | `bounded_summary_as_route` | `no_claim_before_reopen` | `use_hint` |
| `reopenable_route` | `reopenable_route` | `no_claim_before_reopen` | `reopen_source` |
| `bounded_evidence` | `bounded_evidence` | `bounded_claim_allowed` | `use_hint` |
| `silence` / `ignore_or_blocked` | `ignore_or_blocked` | `blocked` | `stay_silent` |

`bounded_summary_as_route` is intentionally not evidence. It can orient an
agent toward a scoped trail and avoid needless broad search, but it still
requires source reopen before exact, disputed, public, stale/currentness,
sensitive, or high-risk claims.

## Deepen

`deepen(route_id)` is where provenance becomes visible. It may return:

- `SourceRoute`: source handles or scoped summary metadata are available, but
  claims still require reopening source.
- `SourceBackedEvidence`: source is already open and bounded to a declared
  scope.
- `Blocked`: a hard mask, privacy boundary, or source policy prevents route
  use.
- `CannotVerify`: no reopenable handle exists, so the agent must not turn the
  packet into a source-backed claim.

Example `SourceRoute`:

```json
{
  "status": "source_route",
  "route_id": "route_project_workflow_summary",
  "claim_permission": "no_claim_before_reopen",
  "source_handle_count": 1,
  "claim_boundary": "reopen_source_before_claim"
}
```

Example blocked result:

```json
{
  "status": "blocked",
  "route_id": "route_private_blocked",
  "claim_permission": "blocked",
  "blocked_reason_codes": ["privacy_domain"],
  "source_handles": []
}
```

## Explain

`explain(route_id)` is a public-safe reason surface. It says why recall did or
did not surface, what the next safe action is, and which broad boundaries still
apply. It should expose reason codes and counts, not raw source text or private
payloads.

Examples:

```json
{
  "decision": "why_recall",
  "output_mode": "reopenable_route",
  "next_safe_action": "reopen_source",
  "reason_codes": ["reopenable_route_available"]
}
```

```json
{
  "decision": "why_not_recall",
  "output_mode": "ignore_or_blocked",
  "next_safe_action": "stay_silent",
  "reason_codes": ["blocked_by_hard_mask", "mask:privacy_domain"]
}
```

## Fixture Contract

`build_facade_fixture_report()` covers five public-safe cases:

- a tiny `bounded_summary_as_route` hint whose source handles remain behind
  `deepen`;
- a `reopenable_route` whose foreground packet tells the agent to reopen
  source;
- a privacy-blocked route that stays silent and deepens to `Blocked`;
- a source-thin `direction_only` route that deepens to `CannotVerify`;
- an already-open bounded evidence route.

The fixture reports these red lines:

```text
foreground_forbidden_key_count = 0
source_backed_claim_without_reopen = 0
foreground_packet_budget_violation_count = 0
```

This supports a narrow claim: AIppocampus has a simple
recall/deepen/explain-facing shape for agents. It does not support public SDK
stability, hosted service readiness, profile-memory equivalence, or default
agent adoption.

## Relationship To Other Contracts

- The route packet authority mapping lives in
  [`source-backed-attention-router.md`](source-backed-attention-router.md).
- The foreground packet width, review-needed, and anti-nag budget lives in
  [`foreground-memory-ux-budget.md`](foreground-memory-ux-budget.md).
- The hot/warm/cold source-reopen latency and timeout policy lives in
  [`source-reopen-budget.md`](source-reopen-budget.md).
- The current public API boundary lives in
  [`../guides/public-api.md`](../guides/public-api.md).
- The coding-agent product lane lives in
  [`../guides/coding-agent-memory.md`](../guides/coding-agent-memory.md).
- The Memory Evidence Drawer remains the richer explanation/provenance drawer;
  this facade is the smaller agent-native front door.
