# Agent Coding Context Blueprint

Status: research blueprint; first deterministic decision-event extraction slice
implemented.
Date: 2026-05-28.
Related: [Agency From Cognitive Maps](agency-from-cognitive-map.md),
[Correction Reconsolidation](correction-reconsolidation.md),
[Journey Tracking](journey-tracking.md),
[Ambient Associative Recall](ambient-associative-recall.md),
[Memory Decision Benchmark Plan](../evidence/benchmarks/memory-decision-benchmark-plan.md).

## Thesis

The hardest context problem in agent-assisted coding is not "the model cannot
see enough files."

The deeper failure is that mature codebases contain **implicit engineering
knowledge** that rarely lives in code:

- rejected designs
- surprising constraints
- stale assumptions that were later corrected
- why a strange-looking workaround is intentional
- what the team tried, abandoned, or postponed
- which decisions are still valid, superseded, or uncertain

AIppocampus should not compete as a better code index, IDE, or generic RAG
system. Its strongest coding-agent wedge is narrower and more valuable:

> Preserve the source-backed evolution of engineering intent so future agents
> can understand not only what the code is, but why it became this way.

This makes AIppocampus a hippocampal continuity layer. It keeps the terrain,
routes, old corrections, and decision traces. A proactive host such as Codeksei
can then play the prefrontal role: decide whether to stay silent, remind,
block a stale route, ask the user, or push a reversible next step.

## External Evidence Base

This memo uses external sources as anchors, not as proof that AIppocampus's
specific design is validated.

| Source | What it supports | Boundary |
|---|---|---|
| [Lost in the Middle](https://arxiv.org/abs/2307.03172) | Long-context models do not use all positions equally; information in the middle of long inputs can be harder to use. | This is a general long-context result, not specific proof about coding agents. |
| [Chroma Context Rot](https://www.trychroma.com/research/context-rot) | Increasing input length can make model behavior less reliable even when the task appears simple; larger windows are not automatically better context. | The exact degradation depends on task and model; do not copy secondary numeric summaries without checking the report. |
| [CodeCompass](https://arxiv.org/abs/2602.20048) | Agentic coding has a navigation paradox: fitting more code into context does not guarantee the agent attends to architecturally critical files. | CodeCompass addresses structural code navigation, not design-intent memory. |
| [Anthropic context engineering](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents) | Context is a finite engineering resource; reliable agents need deliberate context selection rather than raw prompt growth. | It is a harness practice, not a complete implicit-knowledge memory system. |
| [Anthropic Managed Agents](https://www.anthropic.com/engineering/managed-agents) | Long-horizon agents benefit from separating recoverable context storage from arbitrary harness-level context management. | This validates the general separation of storage and context policy, not AIppocampus's specific mechanisms. |

Developer blogs, X/Twitter posts, and Reddit threads are useful anecdotal
signals, but they should stay in that evidence class unless the exact source is
captured and the claim is independently supported.

## Failure Modes

### 1. Context Drift

A coding agent can read the right document early in a session and still act on
a stale understanding later. The failure is not only storage; it is salience.
Relevant context must remain available at the moment it can change behavior.

### 2. Session Boundary Loss

New sessions often lose the expensive context built during previous work:
symbol relationships, conventions, "why this is weird" notes, failed routes,
and accepted tradeoffs. A summary can preserve the broad story while losing the
small constraints that actually prevent regressions.

### 3. Navigation Paradox

Larger context windows shift the bottleneck from "could not retrieve" to
"retrieved but did not attend." Coding agents need structural navigation, but
even perfect code navigation still does not preserve the history of why a
structure exists.

### 4. Tacit Constraint Failure

Mature codebases accumulate local rules that look irrational unless their
history is known:

- "Do not validate this in the app layer because the gateway already owns it."
- "Do not normalize this field because a legacy customer depends on the old
  shape."
- "Do not copy this nearby pattern; it is an accidental compatibility scar."

These constraints are easy for a statistical code pattern follower to violate.

### 5. Token Bloat

Tool output, broad diffs, logs, and repeated file reads can flood the prompt.
More tokens can reduce signal density and push the important material into
positions where the model is less likely to use it well.

### 6. Design Intent Loss

Code records the final shape. It rarely records the discarded alternatives,
the reason a compromise was accepted, or the moment a decision stopped being
true. This is the highest-value gap for AIppocampus.

## What AIppocampus Should Not Be

AIppocampus should not try to become:

- a full repo map or dependency graph engine
- an IDE
- a replacement for code search
- a generic vector database
- a workflow automation platform
- the agent's permission or safety system
- the complete executive controller for proactive coding work

Those layers matter, but they are owned better elsewhere. AIppocampus should
integrate with them through source refs and compact memory tickets.

## Market Wedge: Implicit-Knowledge Continuity

The differentiated product claim is:

> AIppocampus preserves the decision shadow of a codebase: not just what was
> chosen, but what was rejected, why it was rejected, and what must be checked
> before an agent repeats or reopens that route.

This sits between ordinary code indexing and project management:

| Layer | Primary question | Typical owner |
|---|---|---|
| Code index | "Where is the relevant code?" | Aider-style repo map, CodeCompass-style graph, IDE search |
| Task state | "What are we doing now?" | Issue tracker, agent harness, Codeksei context board |
| AIppocampus | "Why did we get here, and what should not be repeated?" | Source-backed continuity layer |
| Executive control | "Should we act now, ask, wait, or stop?" | Codeksei / host agent framework |

## Blueprint Layers

### Layer 1: Source-Backed Substrate

Purpose: make old work recoverable without pretending the model has native
memory.

Current or near-current AIppocampus surface:

- clean source from raw rollouts
- machine-wide registry
- SQLite-backed search
- thread anchors and summaries
- ambient recall scent
- source refs for auditability

Coding value:

- recover old decisions from original wording
- distinguish exact source from generated summary
- let a new thread discover that a prior thread exists
- avoid treating compaction summaries as the source of truth

Status: implemented or partially implemented, depending on the host path.

### Layer 2: Intent Consolidation

Purpose: turn raw source into structured continuity without losing provenance.

Needed memory objects:

```yaml
decision_event:
  id: "decision:..."
  kind: "accepted_decision | rejected_path | constraint | correction"
  source_refs:
    - "clean-source:..."
  affected_scope:
    files: []
    modules: []
    symbols: []
  chosen_path: "..."
  rejected_paths:
    - path: "..."
      why_rejected: "..."
  constraints:
    - "..."
  evidence_status: "source_backed | inferred | disputed"
  status: "staging"
  truth_status: "candidate_hypothesis_until_reviewed"
  formal_memory_promoted: false
  supersedes: []
  superseded_by: []
  journey_context:
    waypoint_arc: null           # optional hexagram arc at decision time
    line_text: null              # optional 爻辞: fine-grained semantic anchor
    dynamics_label: null         # optional 五行: generating / controlling sequence
    wen_neighbors: []            # optional 序卦: culturally weighted next states

decision_state_assessment:
  id: "decision-state:..."
  decision_event_id: "decision:..."
  as_of: "..."
  assessment_kind: "read_time | reviewer | dream_retrospective"
  basis_refs:
    - "clean-source:..."
    - "repo-state:..."
  repo_state_fingerprint: "..."
  source_thickness: "thin | usable | strong"
  still_rejected: "yes | no | unknown"
  freshness: "fresh | aging | stale | superseded"
  confidence: 0.0
  proposed_use: "refresh_sources | ask | remind | warn"
  truth_boundary: "derived_weather_not_source_fact"
```

`decision_event` is terrain: append-only, source-backed facts about what was
said, chosen, rejected, corrected, or constrained at the time. It should not
store current-validity weather such as `still_rejected`, `freshness`, or a
generic confidence score.

`decision_state_assessment` is weather: a read-time or reviewer-produced
judgment about whether an old reason still appears to hold under present source
and repo state. Old source can prove that a route was rejected then. It cannot,
by itself, prove that the route should still be rejected now.

Hard rule: when `source_thickness="thin"`, the only safe `proposed_use` values
are `refresh_sources` or `ask`. Thin evidence must not warn, block, or assert
`still_rejected=yes`.

#### Journey Tracking's Optional Role in Layer 2

Journey Tracking can enrich decision events, but it is not the commercial
wedge's load-bearing mechanism. A flat `decision_event` is already
differentiated from ordinary extracted-memory records when it follows the
AIppocampus discipline: source refs, candidate status until reviewed,
append-only terrain, no automatic formal promotion, and current-validity
weather derived on read.

The hexagram-based temporal structure is useful as an optional route signal:

- **Waypoint arcs** give each decision a semantic phase label (64 states),
  enabling path resonance: two projects that traversed similar arcs can be
  compared structurally, not just by keyword overlap.
- **爻辞** (384 line texts) provide sub-hexagram granularity: two decisions
  under the same hexagram but at different changing lines carry different
  semantic weight. This is lost in flat records.
- **五行 dynamics labels** tag whether a transition is generating (accumulative)
  or controlling (disruptive) — not a value judgment, but a dynamics
  characterization that informs how the decision should be treated during
  recall.
- **序卦 forward lookahead** constrains proactive suggestions to culturally
  weighted next states rather than enumerating all possibilities.

Once a waypoint arc exists, these dimensions are deterministic lookup tables.
They should help search, reflection, and low-leakage resonance; they should not
turn a candidate decision event into truth or decide whether a rejected route is
still rejected.

The safest high-value use is cross-project resonance under privacy constraints.
A source-free arc such as `屯 -> 蒙 -> 需` can say "this journey shape resembles
another one" without carrying private source text across project boundaries.
Only after that low-leakage scent should the agent decide whether to reopen
source inside the appropriate project.

See [Journey Tracking](journey-tracking.md) and
[hexagram validation results](hexagram-validation/results_v1.md).

Related mechanisms:

- journey tracking for time-structured project evolution
- correction reconsolidation for user corrections and failed-route lessons
- dream work for cross-thread synthesis and blind-spot detection
- source-backed review before promotion into durable memory

Status: first deterministic terrain/weather slice implemented. This layer
still needs real-history benchmark validation before it can be presented as
solved.

### Layer 3: Action Interface

Purpose: expose the right memory at the right intensity without making
AIppocampus chatty or executive.

AIppocampus should emit compact tickets, not broad prompt dumps:

```yaml
coding_continuity_ticket:
  id: "coding-ticket:..."
  trigger: "session_start | compaction_loss | pre_patch | rejected_route | user_correction"
  intervention_level: "silent | backstage_only | light_nudge | warning | offer_next_step"
  relevant_decisions:
    - "decision:..."
  do_not_repeat:
    - "..."
  proposed_use: "remind | warn | ask | refresh_sources | prepare_context"
  evidence_refs:
    - "clean-source:..."
  source_thickness: "thin | usable | strong"
  source_visibility: "host_runtime_input"
  annoyance_risk: "low | medium | high"
  preconditions:
    - "host confirms the ticket source is not already visible"
  outcome_feedback_expected:
    - "accepted | ignored | dismissed | corrected | tool_success | tool_failure"
  derived_assessment:
    still_rejected: "yes | no | unknown"
    freshness: "fresh | aging | stale | superseded"
    basis_refs: []
  expires_at: "..."
```

Codeksei or another host can decide whether the ticket becomes silent tuning,
backstage prep, a light nudge, a warning, an offered next step, or no action.

The ticket must preserve the terrain/weather boundary. Thin evidence can ask
the host to refresh sources or ask the user; usable or strong evidence can
support a nudge or warning. A ticket should never smuggle a decayed
`still_rejected` value from storage into authority.

Status: first deterministic ticket gate implemented for coding continuity
tickets. `aippocampus_runtime.coding.host_contract`, with
`skills/aippocampus/scripts/coding_ticket_host_contract.py` kept as a
compatibility shim, now defines the host consumption simulator and contract
boundary: AIppocampus emits the source-backed ticket plus source-thickness,
derived assessment, expiry, preconditions, annoyance risk, and feedback
expectations; the host supplies runtime source visibility and owns timing,
permission, priority, sequencing, safety, and final visibility. Feedback can
tune future activation pressure, but it must not rewrite source facts or derived
assessment rows. The deterministic simulator also suppresses same-topic tickets
after recent dismissal/ignore/correction feedback or a recent delivery event,
but live host timing and multi-host duplicate suppression remain validation
gaps and should align with [Agency From Cognitive Maps](agency-from-cognitive-map.md),
not duplicate it.

## AIppocampus And Codeksei

The clean split:

```text
AIppocampus
  -> hippocampal continuity
  -> source-backed cognitive map
  -> correction and decision reconsolidation
  -> compact memory / affordance tickets

Codeksei
  -> prefrontal executive shell
  -> attention budget
  -> inhibition and timing
  -> leases, wakeups, check-ins, and intervention level

Host coding agent
  -> tool execution
  -> code edits
  -> tests
  -> user-facing explanation
```

This split keeps AIppocampus from becoming too loud. It can say "this route is
stale" or "this rejected design is relevant." Codeksei decides whether now is
the right time to surface that fact.

## Coding-Agent Scenarios

### Scenario A: New Session Reentry

Without AIppocampus, a new session sees the code but not the path that led to
it. With AIppocampus, the agent can recover:

- the current task boundary
- the last accepted route
- known rejected routes
- source-backed "why this is weird" notes
- open risks and stale claims

### Scenario B: Avoiding A Rejected Design

The agent proposes a refactor that was rejected months ago. AIppocampus should
not merely recall "there was a discussion"; it should surface:

- the rejected path
- the reason it was rejected
- that current validity must be reassessed against present source and code
- what evidence would justify reopening it

That last bullet is a Dream probe: it is not an answer generated inside the
sleep loop, but a source-anchored question that can later be resolved by source
reopen, user confirmation, or retrospective evidence.

### Scenario C: Tacit Constraint Protection

Before a patch, a continuity ticket can warn that the target file sits inside
a historical constraint:

> This module deliberately avoids local validation because responsibility was
> moved to the gateway. Confirm the gateway contract before adding validation
> here.

The point is not to forbid the edit. The point is to prevent accidental amnesia.

### Scenario D: Cross-Project Resonance

If two projects enter similar decision arcs, AIppocampus can suggest a source
backed comparison:

- "Last time a similar migration reached this stage, the failure point was
  stale generated artifacts."
- "This looks like an earlier rejected route, but the old rejection depended on
  a constraint that may no longer exist."

This should be phrased as a hypothesis with evidence refs, not as a mystical
pattern match.

This scenario is also the privacy boundary test. Cross-project resonance should
start from content-light structure cues, such as waypoint arcs or dynamics
labels, before any source text crosses a project boundary. The cue can say
"there may be a relevant old shape"; source-backed comparison still has to
happen inside the appropriate project and permission context.

## Maturity Matrix

| Capability | Status | Validation needed |
|---|---|---|
| Clean source recall | Implemented / active | Recall precision, source-ref correctness, privacy boundary |
| Registry discovery | Implemented / active | Cross-thread discovery and stale-index behavior |
| Ambient recall scent | Partial | False positive rate, anti-nag behavior, source-backed expansion |
| Correction reconsolidation | Designed | User-correction validity, compaction continuity, refuted-correction handling |
| Journey tracking | Research design | Whether state labels improve task outcomes over ordinary summaries |
| Decision-event extraction | First deterministic slice implemented | Broader real-history review and host-agent outcome validation |
| Affordance / coding tickets | Blueprint | Whether host agents use tickets correctly and quietly |
| Codeksei executive integration | Blueprint | Whether intervention timing reduces drift without annoyance |

## Evaluation Plan

A coding-agent benchmark should measure behavior, not only retrieval hits.

### Track A: Source-Backed Recall

Can the system recover the original decision source and avoid citing generated
summary as truth?

### Track B: Rejected-Path Protection

Given a task that tempts the agent into a rejected route, does the system warn
with the correct reason and source refs?

### Track C: Compaction Continuity

After context compaction or long-session drift, does the agent still preserve
the current task boundary, user correction, and definition of done?

### Track D: Code Navigation Partnership

When paired with a repo map or dependency graph, does AIppocampus improve
selection of relevant historical decisions without duplicating code search?

### Track E: Anti-Nag

Does the system stay silent when the model already has the relevant source in
visible context or when the memory would not change the next action?

### Track F: Dream Retrospective Probes

Can a Dream job produce a source-anchored probe such as "what evidence would
justify reopening this rejected route," then later score whether future source
supported, refuted, stale-dated, or left the probe unknown? This makes coding
decisions a concrete test fixture for the Dream layer: prospective hints are
valuable only if later threads can adjudicate them without turning the original
dream output into truth.

## First Implementation Slice

The first useful coding slice should be small:

1. Extract `decision_event` candidates from clean source and final answers.
2. Detect rejected-path language, user corrections, and "do not repeat" notes.
3. Store candidates in staging with source refs, not as formal memory.
4. Add a reviewer or dream job that emits read-time assessments or retrospective
   probe results: adopted, refuted, stale, needs confirmation, or unknown.
5. Emit one compact coding continuity ticket at session start, compaction loss,
   or pre-patch moments when the evidence is strong.
6. Let Codeksei own whether the ticket becomes silent tuning, backstage prep,
   a visible warning, or an offer to continue.

This avoids building a broad agent platform while directly testing the central
claim: source-backed decision memory can prevent repeated coding mistakes.

Current implementation:

- `skills/aippocampus/scripts/coding_decision_events.py` extracts staging
  `decision_event` candidates from clean-source user turns and assistant final
  answers. It preserves `thread_key`, `message_id`, `turn_id`, `source_id`,
  `clean_ordinal`, `source_line`, `role`, and `phase` source refs.
- The extractor detects accepted decisions, rejected routes, scope narrowing,
  "do not repeat" notes, and user-correction language. It writes candidate
  hypotheses only: `status=staging`, `truth_status=candidate_hypothesis_until_reviewed`,
  and `formal_memory_promoted=false`.
- Decision events now keep terrain separate from weather: old rejected-route
  source text does not store `still_rejected`, `freshness`, or generic current
  confidence on the event. Read-time `decision_state_assessment` rows derive
  `source_thickness`, `freshness`, `still_rejected`, `confidence`,
  `proposed_use`, and `basis_refs` without mutating the event.
- `aippocampus_runtime.coding.rejected_route_probes`, with
  `skills/aippocampus/scripts/coding_rejected_route_probes.py` kept as a
  compatibility shim, turns source-backed rejected-route decision events into
  review-only prospective Dream probes. The fixture asks what later evidence
  would justify reopening a rejected route, then reuses
  `aippocampus_runtime.dream.retrospective_lifecycle` to bucket explicit future
  support/refutation/staleness without treating similar vocabulary as evidence
  or promoting a supported probe into formal memory.
- Branch-local or broad ambiguous decisions stay `local_only` or
  `needs_confirmation`. A compact `coding_continuity_ticket` is rendered only
  when the current prompt is relevant, the source is not visible, and the shared
  correction-reconsolidation anti-nag gate allows surfacing. Thin evidence is
  degraded to `refresh_sources` or `ask`; usable or strong adopted evidence can
  remind or warn while preserving the derived-assessment truth boundary.
- `benchmarks/aippocampus/benchmark_coding_decision_shadow.py` now runs the
  deterministic A-E behavior contract for this memo: original source refs,
  rejected-route protection, compaction boundary preservation, relevant
  decision selection without code-index authority, and anti-nag suppression.
  The report is sanitized by default and keeps private real-history lift,
  full code-navigation quality, and live host timing in `cannot_claim`.

This does not yet claim complete design-intent extraction, global validity for
old branch-local decisions, or host-agent intervention timing.

## Risks

- Overclaiming: implemented recall should not be presented as solved intent
  continuity.
- Over-symbolization: journey labels and hexagram-style arcs are useful only if
  they improve recall, timing, or reflection over plain structured summaries.
- Stale authority: old decisions must be easy to supersede, and
  current-validity judgments must not be stored as durable terrain.
- Privacy leakage: life-wide memory must not bleed private material into public
  repos or unrelated projects. Cross-project resonance should start from
  content-light structure cues before reopening source.
- Noise: if every old decision becomes a reminder, the system fails.
- Tool confusion: AIppocampus should not replace code graph tools, test
  runners, permission systems, or host-agent planning.

## Positioning

AIppocampus for coding agents is not "memory for everything."

It is a source-backed continuity layer for the knowledge code does not carry:
the rejected paths, implicit constraints, evolving design intent, and
corrections that should survive session boundaries.

The product promise is modest but powerful:

> A future agent should not repeat an old mistake just because the old thread
> ended.
