# Agency From Cognitive Maps

Status: first deterministic affordance-map and ticket-selector slice implemented;
host integration and live timing quality are not yet proven.
Origin: user/product discussion, 2026-05-28.
Related: [Ambient Associative Recall](ambient-associative-recall.md),
[Correction Reconsolidation](correction-reconsolidation.md),
[Dream Task Design](dream-task-design.md),
[Journey Tracking](journey-tracking.md),
[Memory Decision Benchmark Plan](../evidence/benchmarks/memory-decision-benchmark-plan.md).

## Thesis

Context injection is not the endpoint of AIppocampus.

The next threshold is bounded agency: an agent that can notice when work should
move forward, choose a proportionate next action, and preserve the user's
attention instead of constantly asking to be steered.

AIppocampus should not try to become the whole executive controller. Its
strongest role is hippocampal: maintain a source-backed cognitive map, then
derive compact affordance tickets that a host agent or proactive shell can
evaluate. Planning, permissions, safety, and final execution still belong to
the agent framework and the user-facing host.

Reliable agency here does **not** mean personhood, omniscience, or doing
everything for the user. It means:

- source-backed: every proactive claim has evidence refs or says it is weak
- bounded: intervention level and expiry are explicit
- reversible: backstage prep is preferred over irreversible action
- anti-nag: silence is the default unless a cue can change the next behavior
- outcome-aware: user acceptance, dismissal, and task results feed back into
  later timing

## External Landscape

There is clear external demand for agents that can actively execute or advance
tasks. The adjacent systems are real, but they mostly concentrate on execution
loops, workflows, coding environments, or multi-agent orchestration. That leaves
space for AIppocampus to specialize in source-backed continuity and timing.

| Area | What exists | What it confirms | Gap relative to AIppocampus |
|---|---|---|---|
| Continuous workflow agents | [AutoGPT](https://agpt.co/) presents an agent platform for digital workflow automation and continuous cloud-deployed agents. | Users want assistants that run beyond one chat turn and activate on relevant triggers. | The public framing is workflow automation, not life-wide cognitive continuity or anti-nag recall. |
| Chat vs agent mode products | [Manus](https://help.manus.im/en/articles/11711128-what-are-the-differences-between-chat-mode-and-agent-mode) separates lightweight chat from Agent Mode for autonomous planning and complex deliverables. | The market is converging on an explicit boundary between discussion and autonomous execution. | Mode switching alone does not solve when an agent should surface, what prior corrections matter, or how to avoid stale initiative. |
| Stateful orchestration runtimes | [LangGraph](https://docs.langchain.com/oss/javascript/langgraph/overview) focuses on long-running, stateful agents with persistence, human-in-the-loop, memory, and durable execution. | Reliable agents need runtime state, resumability, and oversight rather than pure prompt loops. | It provides orchestration infrastructure; it does not provide a personal cognitive map or user-specific affordance ranking by itself. |
| Multi-agent workflow frameworks | [AutoGen](https://microsoft.github.io/autogen/) and [CrewAI](https://docs.crewai.com/) support multi-agent systems, tasks, crews, flows, tools, memory, and human-in-the-loop patterns. | Complex work often needs composable agents and structured workflows. | These frameworks still need a continuity layer that decides which old corrections, open loops, and user attention constraints are relevant now. |
| Software engineering agents | [OpenHands](https://github.com/OpenHands/OpenHands) and [SWE-agent](https://github.com/SWE-agent/SWE-agent) give models tools for coding, shell use, browsing, issue fixing, and custom tasks. | People strongly want agents that can push real engineering work forward. | Their agency is task-environment focused; AIppocampus can supply cross-thread memory, compaction continuity, and "do not repeat this mistake" anchors. |
| Lifelong embodied learning | [Voyager](https://voyager.minedojo.org/) combines automatic curriculum, a growing skill library, and environment feedback for open-ended Minecraft learning. | Open-ended agents benefit from curricula, reusable skills, and feedback-driven accumulation. | Its world is an embodied game environment; AIppocampus's world is the user's cross-thread, cross-device life and project terrain. |
| Agent hook surfaces | [Codex hooks](https://developers.openai.com/codex/hooks) expose lifecycle moments that can trigger background or foreground behavior. | Real agent hosts are gaining event surfaces where memory can attach. | Hook timing is only a substrate; the hard product question is what to surface, at what intensity, and when to stay silent. |

The pattern is consistent: execution surfaces are arriving faster than good
continuity maps. AIppocampus can become the layer that tells an agent what is
still true, what changed, what the user already corrected, and which next move
is worth spending attention on.

## Cognitive Map To Affordance Map

A cognitive map is not a chat transcript summary. It is a navigable terrain of
source-backed relationships:

- active journeys, projects, open loops, and stalled routes
- user corrections, accepted decisions, and refuted claims
- scope boundaries, do-not-do constraints, and annoyance signals
- evidence refs, source freshness, and source thickness
- recurring values, preferences, and preferred collaboration rhythms
- tools, host capabilities, permissions, and known execution limits
- recent outcomes: accepted nudges, ignored nudges, failures, and successful
  reentries

An affordance map is the same terrain viewed through possible action:

- `silent`: no foreground change
- `backstage_prepare`: warm recall, refresh sources, draft a plan, or check a
  repo fact without interrupting
- `state_check`: ask whether an old thread should continue
- `light_nudge`: name a relevant prior anchor briefly
- `offer_next_step`: propose a concrete next move
- `push_forward`: take a reversible or already-authorized step
- `surface_warning`: warn that the current route crosses a known correction or
  high-cost failure path

The map should not be injected wholesale. It should emit a small number of
affordance tickets, and the host should decide whether to use them.

## Agency Ticket Contract

An agency ticket is a compact, source-backed proposal for possible initiative.
It is not a prompt to paste into the model and not an order to act.

```yaml
ticket_id: "agency-ticket:..."
created_at: "2026-05-28T00:00:00Z"
scope:
  kind: "thread | workspace | journey | recurring_theme"
  stable_id: "..."
intervention_level: "silent | backstage_only | state_check | light_nudge | offer_next_step | push_forward | warning"
proposed_action:
  verb: "refresh_sources | summarize_state | ask_checkin | draft_patch | schedule_revisit | warn_route | delegate_worker"
  object: "..."
why_now:
  trigger: "compaction_loss | scheduled_revisit | stale_claim | blocked_route | user_correction | unfinished_task | high_resonance"
  explanation: "One short sentence."
evidence_refs:
  - "clean-source:..."
source_thickness: "thin | usable | strong"
confidence: 0.0
annoyance_risk: "low | medium | high"
do_not_do:
  - "..."
preconditions:
  - "..."
requires_user_confirmation: true
expires_at: "2026-05-29T00:00:00Z"
outcome_feedback_expected:
  - "accepted | dismissed | corrected | ignored | tool_success | tool_failure"
```

The contract deliberately keeps agency separate from memory. AIppocampus can
say "this action appears available and relevant"; the host decides whether it
is allowed, safe, timely, and worth surfacing.

## Intervention Levels

AIppocampus should prefer small interventions. A useful ladder:

| Level | User-visible? | Use when | Example |
|---|---:|---|---|
| `silent` | No | The memory only tunes style or prevents an internal mistake. | Suppress a stale suggestion. |
| `backstage_only` | No | A likely useful next step can be prepared without consuming attention. | Refresh source refs before the next turn. |
| `state_check` | Yes, tiny | The user may want to resume, but intent is uncertain. | "This touches the agent-agency thread; should I continue from there?" |
| `light_nudge` | Yes, brief | A prior anchor materially improves the answer. | "This is the same anti-nag boundary from correction reconsolidation." |
| `offer_next_step` | Yes | The next action is concrete but still needs consent. | "I can turn this into a Track E benchmark sketch." |
| `push_forward` | Maybe | The action is reversible, authorized, low-annoyance, and strongly evidenced. | Continue a scheduled background research pass, then report results. |
| `warning` | Yes | The current route risks violating a correction, scope, or high-cost failure. | "This edit crosses a remembered do-not-touch boundary." |

`push_forward` should be rare. It requires strong source thickness, a clear
permission boundary, low annoyance risk, and a reversible or explicitly
authorized action.

## Loop Design

The agency loop should be eventful, not chatty:

```text
sources / hooks / tool outcomes / user feedback
  -> AIppocampus cognitive map update
  -> affordance selector
  -> agency ticket(s)
  -> host executive policy
  -> action or silence
  -> outcome feedback
  -> correction reconsolidation / dream work / cache refresh
```

Good trigger families:

- user correction or failed-route signal
- compaction, horizon loss, or thread resume
- successful or failed tool outcome
- scheduled revisit or explicit user commitment
- repeated project stall with a known easiest reentry step
- high-value cross-thread resonance from dream work

Bad trigger families:

- "similar words appeared" with no actionability
- vague preference reminders already visible in context
- every tool call, every prompt, or every finished answer
- unverified model-generated insight without source refs

## Anti-Nag Budget

The attention budget is part of the product.

Before surfacing anything, the selector should ask:

1. Would this change the next model or user decision?
2. Is the relevant source outside the visible context or at risk of being lost?
3. Is the cost of missing it higher than the cost of interruption?
4. Has the same cue already been surfaced in this topic epoch?
5. Has the user recently dismissed this type of initiative?

If the answer is weak, the right agency move is silence or backstage prep.

This is why AIppocampus should not become a mini prefrontal cortex. It can
mark the terrain and surface likely affordances, but the host's executive layer
must own priority, inhibition, permission, sequencing, and final action.

## First Implementable Slice

Do not begin with full autonomy.

A realistic first slice:

1. Add an `agency_affordance_map` sidecar derived from existing cognitive-map
   inputs, correction windows, ambient recall cards, and dream outputs.
2. Add a deterministic selector that emits at most one foreground ticket and a
   few backstage tickets per topic epoch.
3. Support only four trigger types at first: user correction, compaction loss,
   unfinished task reentry, and scheduled revisit.
4. Require `source_thickness != thin` for any foreground ticket except
   `state_check`.
5. Record outcome feedback: accepted, ignored, dismissed, corrected,
   `tool_success`, or `tool_failure`.
6. Evaluate with a Compaction Continuity Benchmark plus agency-specific cases:
   "should stay silent", "should remind", "should warn", and "should offer a
   next step".

This integrates naturally with a proactive shell like Codeksei: Codeksei can
own leases, wake timing, context-board refresh, intervention tiers, and host
delivery; AIppocampus can provide source-backed tickets and reconsolidated
feedback.

## Implemented First Slice

The first deterministic runtime helper is
`skills/aippocampus/scripts/agency_affordance.py`.

It builds an `aippocampus_agency_affordance_map` from existing sidecar-like
inputs: cognitive-map rows, correction windows, ambient recall cards, dream
outputs, coding continuity tickets, unfinished tasks, and scheduled revisits.
The selector emits at most one foreground `aippocampus_agency_ticket` and a
small bounded backstage set per topic epoch.

Implemented trigger families are deliberately narrow:

- `user_correction`
- `compaction_loss`
- `unfinished_task_reentry`
- `scheduled_revisit`

Foreground tickets require `source_thickness != thin`, except for tiny
`state_check` tickets that only ask whether an old task should resume. Tickets
with visible source refs, same-topic repeated source refs, or
`matched_terms_only` cues are suppressed rather than turned into reminders.
`push_forward` source rows are downgraded to `offer_next_step`, because
AIppocampus does not own permission, sequencing, priority, or safety policy.

The helper also creates append-only `aippocampus_agency_ticket_feedback` rows
for `accepted`, `ignored`, `dismissed`, `corrected`, `tool_success`, and
`tool_failure` outcomes.

Coding-continuity tickets have a narrower host contract in
`aippocampus_runtime.coding.host_contract`, with
`skills/aippocampus/scripts/coding_ticket_host_contract.py` kept as a
compatibility shim. That simulator maps coding tickets to `silent_tuning`,
`backstage_prep`, `light_nudge`, `warning`, `offer_next_step`, or `stay_silent`,
and treats source visibility as a host-supplied runtime input rather than stored
truth.

Current tests live in `tests/aippocampus/test_agency_affordance.py` and cover
the first four evaluation cases: should stay silent, should remind, should
warn, and should offer next step.

The first replayed host-timing fixture lives in
`aippocampus_runtime.coding.agency_host_timing`, with a public no-write smoke at
`tools/aippocampus/smoke/smoke_agency_host_timing.py`. It exercises
show/hold/suppress decisions for task phase, visible source context,
cross-host duplicate suppression, and recent negative feedback. This is
deterministic replay evidence only; it does not prove live host timing or real
annoyance calibration.

Still not proven:

- live host hook timing
- whether a host agent uses tickets well
- annoyance-risk calibration from real dismissals
- live multi-host duplicate suppression
- any autonomous `push_forward` behavior

## Open Questions

- How should annoyance risk be measured without overfitting to a few dismissals?
- How should the system distinguish helpful initiative from manipulative
  personalization?
- Which ticket types can safely be produced by deterministic logic, and which
  require semantic dream work?
- How fresh must evidence be before the agent is allowed to push forward?
- How should multiple hosts avoid duplicate nudges for the same open loop?
- What is the minimum source ref needed for life-wide continuity without
  leaking private material across public boundaries?

## Working Principle

AIppocampus should give agents a better memory of the terrain, not a louder
voice.

The win condition is an agent that can say, rarely and usefully, "I know where
we are, I know what was already corrected, and I can take the next small step
without making you carry the whole map again."
