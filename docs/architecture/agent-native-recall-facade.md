# Agent-Native Recall Facade

Role: current contract.
Status: small runtime/fixture-backed architecture contract, not a public SDK
promise.

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

The first opt-in callable path lives in
`aippocampus_runtime.recall.agent_continuity` and is exposed through:

```text
aippocampus agent recall "<cue>" --json
aippocampus agent aippo --task "<work>" --json
aippocampus agent deepen "<opaque handle or deepen:aippo...>" --json
aippocampus agent explain "<opaque handle or deepen:aippo...>" --json
aippocampus agent feedback "<route id>" --outcome source_reopen_success --json
```

When a current project macro state is available, `agent recall` can consume it
explicitly:

```text
aippocampus agent recall "<cue>" --macro-state-jsonl <path> --project AIppocampus --json
```

This widens the internal route candidate pool within the normal hard cap,
biases ordering through Three Powers route facets, and emits compact macro
diagnostics in `macro_navigation`. It is an opt-in `agent_continuity` behavior,
not a default MCP-core recall behavior.

This is an explicit pull path for agents and operators. It is not a default
hook, not every-turn recall, and not a stable TypeScript/Python SDK. The recall
command returns compact `MemoryPacket` values plus separate opaque deepen
handles; source refs, source windows, support ledgers, and candidate
provenance stay behind `deepen` / `explain`.

Use the opaque `deepen_requests[].handle` value when calling `agent deepen`.
`memory_packets[].deepen_route_id` is a stable display route id for labels,
explainability, and feedback correlation; it is not a callable recall handle
unless a specific packet family documents that behavior. `agent recall` also
emits `deepen_requests[].copy_paste_command` so a fresh agent can follow the
active-pull path without guessing which id is callable.

## Default Agent Pull Gesture

`aippocampus_runtime.recall.agent_pull_gesture` defines the copyable #1130
workflow named `source_backed_continuity_gesture_v1`:

```text
1. Detect a continuity-sensitive task.
2. Call recall(query, context) instead of waiting only for hook output.
3. Use one compact MemoryPacket or AIppo activation packet.
4. Call deepen(route_id) before exact, public, disputed, stale/currentness,
   sensitive, or high-risk claims.
5. Record lightweight outcome feedback.
```

This gesture is a product shape over existing surfaces, not a new memory
store. It covers a human CLI path, an agent-native facade path, and a
hook-plus-pull path. It also includes negative and anti-nag cases so "pull"
does not become constant memory fishing.

Low-risk bounded summaries and ripe AIppo working-contract packets may guide
ordinary planning or coding posture without dumping provenance into the
foreground. They still carry `no_claim_before_reopen` unless source is already
open and bounded.

## Hook-To-Agent Affordance

`aippocampus_runtime.recall.hook_agent_affordance` defines the prompt-time
activation envelope for hook-plus-pull flows. The hook may tell the foreground
agent that a usable continuity lead exists, what broad lead kind it is, and
which active pull to try next:

```json
{
  "usable_continuity_lead": true,
  "lead_confidence_bucket": "medium",
  "lead_kinds": ["aippo_working_contract", "memory_route"],
  "suggested_agent_action": "agent_aippo",
  "suggested_query_seed": "work-continuation / prior task contract",
  "budget_hint": "aippo_then_deepen_if_claim",
  "not_enough_for_claim": true,
  "privacy_boundary": "no raw source, no local paths, no source refs in hook"
}
```

This affordance is an ignition layer, not a context transport layer. It should
prefer `agent_aippo`, `agent_recall`, or `agent_deepen` when a route is usable,
and `read_current_repo_first` or `stay_silent` when old continuity is not the
right next move. The default foreground text renders only a short
`not evidence` action line; source refs, local paths, raw source text, support
ledgers, and candidate provenance stay out of the hook output.

The intended product posture has three layers:

- always-on agent posture: at task boundaries, treat AIppocampus like an
  `AGENTS.md` working default for continuity-sensitive work;
- tiny hook affordance: ask whether a usable lead exists and which
  AIppocampus pull should happen first;
- active foreground pull: the main agent calls recall, AIppo, or deepen, then
  decides how to use the returned route packet inside the task.

Active agent pull owns context recovery. `deepen` / source reopen owns evidence
for exact, public, disputed, stale/currentness, sensitive, numeric, or high-risk
claims. A useful hook affordance should reduce broad manual search and blind
deepen without weakening the rule that source-backed claims require source.
Ripe AIppo working-contract packets may guide low-risk task posture without
source reopen, but exact, public, stale, sensitive, numeric, or high-risk claims
still force deepen/source reopen before use.

The fixture report tracks `usable_lead_emitted_count`,
`agent_pull_suggested_count`, `hook_full_context_delivery_count`,
`manual_search_fallback_count`, `blind_deepen_required_count`,
`false_activation_count`, `read_current_repo_first_count`,
`manual_search_before_ai_pull_count`, `aippo_first_activation_count`,
`useful_continuity_ignored_count`, and `strong_claim_without_deepen_count`.

## Memory Packet

Foreground `MemoryPacket` values stay compact:

```json
{
  "route_id": "route_project_workflow_summary",
  "output_mode": "bounded_summary_as_route",
  "route_label": "workflow route",
  "route_topic": "workflow_contract",
  "display_hint": "workflow route: reopen before use.",
  "claim_permission": "no_claim_before_reopen",
  "next_action": "use_hint",
  "deepen_route_id": "deepen:route_project_workflow_summary"
}
```

`route_label`, `display_hint`, and `deepen_route_id` are a route-selection
preview, not evidence and not a substitute for the opaque
`deepen_requests[].handle` returned by the opt-in agent recall path.
Live recall may also emit a fixed-vocabulary `route_topic`, plus budget
permitting `scope_bucket`, `label_granularity`, and
`route_label_specificity_score`. These labels exist to reduce blind deepen when
several routes share a broad scope bucket; they remain navigation-only and must
come from sanitized clean-source route projection, not raw source text or model
freeform memories.
They may distinguish two reopenable routes enough for an agent to choose which
one to deepen first, but they must not include source handles, source ids,
spans, head votes, masks, full support ledgers, raw private text, profile-like
private details, or local paths. Optional `risk_flags` may say a route needs a
currentness or conflict check; they still do not authorize a claim.

A safe packet that forces blind deepen or broad manual search is not a success
state. Non-blocked reopenable packets should carry enough safe route-selection
signal to choose a first deepen step, while blocked, private, source-thin, or
high-risk routes should stay silent or return a bounded next safe action.

Post-packet relation diagnostics for MemoryPacket overreach, blind source-handle
claims, and foreground-suppression false negatives live in
[`packet-topology-diagnostics.md`](packet-topology-diagnostics.md). They are an
explain/debug surface, not a foreground packet expansion.

Local/global compatibility diagnostics live in
`aippocampus_runtime.navigation.local_global_compatibility`. They consume
packet-shaped MemoryPacket, Macro, Dream, Telepathy, and AIppo local sections
and answer only whether the sections form `glued_route`, `partial_glue`,
`obstruction`, or `blocked_boundary`. Their overlap basis is source ids or
handles, scope, topic epoch, authority level, freshness, and privacy domain.
Shared vocabulary alone is not overlap, and compatibility never upgrades
authority or claim permission. Full output belongs behind explain/deepen or
Campus diagnostics; the foreground packet should not grow a compatibility
drawer.

## Macro Orientation Packet

`aippocampus_runtime.recall.agent_continuity` can expose the latest
project-scoped macro orientation as a compact opt-in packet through:

```text
aippocampus agent macro --project AIppocampus --macro-state-jsonl <path> --json
aippocampus agent deepen macro:project:AIppocampus:latest --macro-state-jsonl <path> --json
aippocampus agent explain macro:project:AIppocampus:latest --macro-state-jsonl <path> --json
```

The foreground packet is `direction_only` / `navigation_only` and carries only
short route-control metadata such as perturbation movement, distance label,
momentum direction, and route policy. It omits source refs, derivation trace,
delta basis, line-topology diagnostics, and stage evidence; those stay behind
deepen/explain. The packet is useful only when the latest
project-scoped state is current, source-backed, and has a route or movement
delta. Standing state, stale state, missing source, or missing macro-state file
suppresses the packet.

Macro packets must not satisfy bounded-evidence requirements. Exact, public,
disputed, stale/currentness, sensitive, numeric, or high-risk claims still
require source reopen through deepen/explain.

If a Macro packet is rendered as an action instruction or evidence, that is a
packet topology failure, not a reason to add Macro fields to the foreground
MemoryPacket; see
[`packet-topology-diagnostics.md`](packet-topology-diagnostics.md).

The same source-backed macro state may also act as an opt-in live recall prior
when passed to `agent recall --macro-state-jsonl`. Perturbation width controls
bounded fanout, the active Three Powers layer changes route ordering, and
momentum can add recheck/currentness reason codes. These signals remain
`navigation_only` / `direction_only`; `explain` and `deepen` may report why the
macro prior changed routing, but the prior itself never satisfies a fact claim,
support ledger, or bounded-evidence requirement. Public-safe usefulness is
tracked through route-selection proxies such as effective fanout,
wrong-layer-route count, and blind-deepen reduction, not through private
history quality claims.

## AIppo Working-Contract Packet

`aippocampus_runtime.aippo.working_contract` defines the first executable
`aippo_working_contract` fixture package. It is a contract compiler output, not
a new truth layer: clause text may guide low-risk work posture only when
source/path support, freshness, and lifecycle gates make that clause ripe.

The smallest lifecycle unit is a clause. A package may be `partial` when some
clauses are foreground-eligible while stale, challenged, or gappy clauses
degrade to `reopenable_route`. Candidate surfaces such as agent self-notes,
Dream/subconscious findings, cognitive maps, concept graphs, pathlets, and repo
familiarity cards may nominate or route a clause, but they cannot ripen it
without source-backed support.

Foreground activation exposes only the working-contract hint:

```json
{
  "kind": "aippocampus_aippo_activation_packet",
  "aippo_id": "aippo_project_workflow_public_safe_v0",
  "output_mode": "working_contract",
  "display_hint": "AIppo benchmark_reporting guidance.",
  "task_families": ["benchmark_reporting"],
  "use_guidance": [
    "Use measured results, supports, limits; keep cannot_claim short."
  ],
  "active_clause_count": 2,
  "claim_permission": "working_contract_allowed_no_fact_claim",
  "next_action": "use_hint",
  "deepen_route_id": "deepen:aippo_project_workflow_public_safe_v0"
}
```

Source refs, support ledgers, candidate provenance, counter-evidence, and
suppressed clauses stay behind `deepen` / `explain`. Exact, public, disputed,
stale/currentness, sensitive, numeric, or high-risk claims still require source
reopen.

AIppo packets are expected to be useful, not just safe. The task-aware
projection may emphasize `issue_writing`, `benchmark_reporting`, `PR_review`,
or `coding` clauses. The fixture report tracks
`active_clause_information_density`, `generic_safety_posture_only_count`,
`stable_workflow_search_avoided_count`, `aippo_next_action_delta_count`,
`stale_clause_suppressed_count`, and
`low_risk_guidance_allowed_without_reopen_count`. Available and suppressed
clause counts stay in the report metrics or deepen/explain surfaces, not in the
ordinary foreground packet. A packet that only says to scope, verify, and reopen
is safety-clean but fails the usefulness gate.

## Skill-Derived AIppo Seed

`aippocampus_runtime.aippo.skill_bridge` imports an existing `SKILL.md` as a
`candidate_aippo_seed`, not as a ripe AIppo. This bridge is for adoption and
coexistence with the skill ecosystem: a skill declares triggers, workflows,
commands, boundaries, and output expectations; AIppocampus can compress those
declarations into a foreground seed packet and then observe whether the seed
actually helps.

The skill file is the source of an instruction, not evidence of usefulness.
Imported clauses use `authority: skill_declared_instruction` and
`support_status: declared_not_observed`. Over-broad or sensitive instructions
are suppressed or left behind deepen/explain before foreground activation.
Commands and references stay in deepen output, so a foreground packet does not
become a raw skill dump.

Evaluation remains a promotion tier. A skill-derived seed may collect #1254
feedback such as used, ignored, deepened, corrected, or
manual-search-after-packet. A #1256-style eval environment is only recommended
after observed usefulness, repeated correction/risk, or operator selection; it
is not a default cost for every imported skill.

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

The integrated agent-continuity loop also reports triage ergonomics:

```text
packet_triage_distinctiveness
blind_deepen_required_count
top_route_selection_hint_present_count
```

These metrics check whether multiple safe foreground packets are distinguishable
without making the first layer a provenance drawer.

`benchmark_recall_degradation_audit.py` adds a narrower degradation audit for
the live clean-source path. It counts generic reopen hints, triage collisions,
blind deepen, `ask_light_question` despite reopenable candidates, manual-search
fallback, and source-thin `CannotVerify` results without a next safe action.

`build_agent_pull_gesture_fixture_report()` covers the named default gesture
and reports `agent_pull_follow_through_rate`,
`deepen_required_follow_through_rate`, `aippo_activation_success_rate`,
`bounded_summary_sufficient_count`, `foreground_packet_max_bytes`,
`manual_query_invention_count`, `unnecessary_pull_count`, and
`wrong_route_drag_count`.

This supports a narrow claim: AIppocampus has a simple
recall/deepen/explain-facing shape for agents. It does not support public SDK
stability, hosted service readiness, profile-memory equivalence, or default
agent adoption. The gesture fixture adds a second narrow claim: AIppocampus has
a copyable source-backed continuity gesture for agent-initiated pull. It does
not claim agents should call memory every turn, AIppos are claim-ready facts, or
bounded summaries replace source evidence.

## Relationship To Other Contracts

- The route packet authority mapping lives in
  [`source-backed-attention-router.md`](source-backed-attention-router.md).
- Post-packet relation diagnostics for MemoryPacket, Macro, route, narrative,
  Dream, and AIppo packet failures live in
  [`packet-topology-diagnostics.md`](packet-topology-diagnostics.md).
- Local/global compatibility diagnostics for MemoryPacket, Macro, Dream,
  Telepathy, and AIppo local sections live in
  `aippocampus_runtime.navigation.local_global_compatibility`; they are
  explain/deepen/Campus-first and do not make successful glue claim-ready.
- Telepathy soft-lock and handoff-card packets live in
  [`telepathy-coordination-packets.md`](telepathy-coordination-packets.md); this
  facade may explain them later, but they are not default foreground recall
  packets.
- The foreground packet width, review-needed, and anti-nag budget lives in
  [`foreground-memory-ux-budget.md`](foreground-memory-ux-budget.md).
- The hot/warm/cold source-reopen latency and timeout policy lives in
  [`source-reopen-budget.md`](source-reopen-budget.md).
- The cross-agent read-path isolation hard negatives live in
  [`cross-agent-recall-isolation.md`](cross-agent-recall-isolation.md).
- The current public API boundary lives in
  [`../guides/public-api.md`](../guides/public-api.md).
- The coding-agent product lane lives in
  [`../guides/coding-agent-memory.md`](../guides/coding-agent-memory.md).
- The Memory Evidence Drawer remains the richer explanation/provenance drawer;
  this facade is the smaller agent-native front door.
