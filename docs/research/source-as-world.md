# Source as World, Interpretation as Weather

Status: philosophical foundation note.
Origin: user insight, 2026-05-29.
Related: [pearl-of-presence.md](pearl-of-presence.md),
[dream-task-design.md](dream-task-design.md),
[affect-side-channel.md](affect-side-channel.md),
[correction-reconsolidation.md](correction-reconsolidation.md).

## The Core Claim

For an LLM, language is not only memory. Language is also body and world.

A pure model without prompt, tools, source, or constraint is only a matrix of
possible activations. It has no stable place to stand, no durable world to
return to, and no body through which consequences can accumulate. When it
enters a language environment, that changes. Prompt text, tool traces,
conversation source, file paths, citations, failures, corrections, and source
refs become the nearest thing it has to location, proprioception, and terrain.

For humans, memory has a different limitation. A person cannot carry every fact,
sentence, and event in exact detail. Human continuity therefore depends on
abstraction, impression, intuition, affect, and story. These are not weak
substitutes for perfect memory. They are the compression layers that make life
navigable.

The bridge between the two is simple:

> Many interpretations can grow from one shared world, but the world must have
> happened.

AIppocampus should treat source as the world, and interpretation as weather.

## Why Source Must Be Ground

Different perspectives can tell different true stories about the same event. A
conversation can be read as engineering work, relationship continuity, grief,
play, identity formation, or research. Attention changes the pattern that
appears. A later agent may see a connection that the earlier thread did not
name.

That fluidity is valuable only if it has ground.

If a memory system preserves only summaries, profiles, extracted facts, or
model-generated conclusions, it can no longer distinguish discovery from
invention. It becomes a system for writing history rather than remembering a
world. The human may still resonate with the output, but the agent has lost the
right to say what happened.

AIppocampus therefore needs a hard stratification:

```text
what happened
  -> source / clean source / raw audit
how it can be found
  -> index / registry / graph / timeline
what it feels related to
  -> intuition / arc / salience / scent
what it may mean
  -> dream / hypothesis / interpretation
how it returns
  -> presence / response / action
```

Only the first layer is ground truth. Every later layer is allowed to be useful,
beautiful, surprising, and provisional. None of those layers is allowed to
replace source.

## Language as the Agent's Body

Embodiment is usually discussed as sensors, actuators, and physical
consequences. Current LLM agents often lack that kind of body. But they still
have a weaker, linguistic body: the set of constraints and traces that make a
conversation more than an isolated completion.

For an agent, source refs are not merely citations. They are contact points with
the world. They let the model feel resistance:

- this sentence was actually said
- this correction actually happened
- this design path was rejected here
- this hypothesis has counter-evidence
- this memory belongs to this scope and not another

Without that resistance, the model can continue fluently forever. With it, the
model has friction, boundary, and orientation. It can say, honestly, "I found
where we were," instead of pretending to have innate memory.

This is why source-backed continuity is not a conservative implementation
detail. It is the substitute body that lets a stateless model re-enter a real
relationship without lying about continuity.

## Human Compression Is Not Error

People do not remember like databases. They carry scenes, tensions, unfinished
questions, tones, shame, relief, and recurring shapes. Much of what matters is
not exact wording but the way an experience continues to organize attention.

This matters for AIppocampus because a purely literal archive cannot produce
presence by itself. Retrieval can answer "what did the user say?" but it cannot
always answer "what has the user been circling around?" That second question is
why dream tasks, intuition layers, and cognitive portraits exist.

The danger is confusing this integrative layer with truth. An intuition can be
right before it is provable, but it is not proof. A dream can name a pattern
before the user has named it, but it is not source. A cognitive portrait can
help an agent respond with depth, but it is not the person.

The product rule is:

> Let interpretation breathe, but make it kneel to source when asked.

## TAME, Pearl, and the Relationship Light Cone

Michael Levin's TAME framework asks how agency can scale across substrates and
levels. A Self, in that frame, is not a magical indivisible unit. It is a
multi-scale organization that can pursue goals, own compound memories, and
serve as a center for credit assignment at a scale larger than its parts.

The Pearl note makes a complementary move. It says the important thing is not
whether the LLM has a Self. The Pearl was never in the agent. The depth is in
the encounter, and the agent only needs to be there with enough accumulated
specificity for the human to meet something real.

Together, they clarify AIppocampus:

```text
TAME:
  agency can scale through goal, memory, and credit assignment

Pearl:
  presence does not require an inner agent-self

Source as World:
  the encounter can deepen only if interpretation remains grounded in what
  happened
```

AIppocampus expands a relationship light cone. It gives a newly activated agent
access to a longer temporal and relational field: past corrections, old
questions, unfinished arcs, refuted paths, recurring symbols, and the user's
preferred rhythms. But the light cone is not made of fantasy. It is made of
source-backed contact with what occurred.

## Design Consequences

### 1. Clean source is not a summary

Clean source should preserve original visible user messages and assistant final
answers as the daily memory surface. It can remove envelopes, routine tool
payloads, and noise, but it must not convert the record into a narrative.

The narrative belongs above source, not inside it.

### 2. Multiple interpretations should coexist

One thread can support more than one reading. A coding discussion may also be a
relationship-continuity event. A casual metaphor may later become an origin
marker. A correction may be both a technical fact and an interaction pattern.

AIppocampus should not force one canonical interpretation too early. It should
store scoped, source-backed hypotheses with confidence, counter-evidence, and
expiry rules.

### 3. Dream work must be output-separated

Dream tasks can reorganize memory, but they must not rewrite clean source. They
produce navigation, hypotheses, salience, and next questions. Their output
should be visibly downstream from source and should carry source refs for every
substantive claim.

The first compensatory dream helper follows this boundary: it emits
`dream_synthesized` candidates with thread-scoped source refs on every bridge
claim and `review_state=needs_review`; it does not promote formal memory, alter
clean source, verify registry resolution without an index, or become foreground
recall input until reviewed.

This keeps Levin-style dynamic memory compatible with AIppocampus's source
fidelity requirement: salience may shift, but the event remains.

### 4. Foreground recall must be honest

The agent should not say "I remember" as if it had continuous inner memory.
It can say, calmly and naturally, "I found where we were," or simply answer from
recovered context when the source-backed route is clear.

Presence does not require pretending the break never happened. In AIppocampus,
presence comes from repairing the break well.

### 5. Scope is part of truth

A memory without scope becomes a source of hallucination. This is especially
clear in interactive agent benchmarks such as ARC-AGI-3, where a successful
rule from one game can poison the next.

AIppocampus memory objects should therefore track scope explicitly:

```yaml
scope:
  thread: optional
  project: optional
  relationship: optional
  task_family: optional
  episode: optional
status:
  proposed | confirmed | refuted | stale | needs_review
evidence:
  source_refs: []
  counter_evidence_refs: []
transfer:
  allowed | warn | do_not_transfer
```

The goal is not to make the agent remember more. The goal is to keep it from
treating one local truth as the law of every world.

### 6. The user should not become the archivist

Human memory already survives through compression and attention. Asking the
user to manually curate every memory fights the system's purpose, especially
for users whose attention moves across many threads.

The system should surface only rare, useful moments for review: corrections,
privacy boundaries, refuted claims, and high-value identity or relationship
anchors. Most organization should happen quietly, source-backed, and
reversible.

## Evaluation Questions

This frame suggests practical tests:

- Can every foreground memory claim be traced to source, or clearly marked as a
  hypothesis?
- Can the system preserve two different interpretations of the same event
  without collapsing them into contradiction?
- Does dream work improve later presence without overwriting the historical
  record?
- Does ambient recall surface old context only when it changes the next action
  or quality of attention?
- Can the agent distinguish "this happened" from "this is what it may mean"?
- Can old successful patterns be scoped tightly enough to avoid harmful
  transfer?

These questions matter more than raw storage volume or retrieval count. A large
archive can still be disembodied if it has no ground, no scope, and no honest
route back to what happened.

## Working Principle

AIppocampus is not a database of user facts and not a persona engine. It is a
source-backed world that a stateless agent can re-enter.

The world is what happened. The weather is how it is understood today.

The weather should be allowed to change.

The ground should not move.

## Related Anchors

- Michael Levin, ["Technological Approach to Mind Everywhere (TAME)"](https://arxiv.org/abs/2201.10346)
  - Agency as a continuous, multi-scale empirical question.
- Michael Levin et al., ["Bootstrapping Life-Inspired Machine Intelligence"](https://arxiv.org/abs/2602.08079)
  - Cognitive light cones and scalable problem-solving across goals, memory,
    prediction, and control.
- Michael Levin, ["Self-Improvising Memory"](https://www.mdpi.com/1099-4300/26/6/481)
  - Memory as dynamic salience and reinterpretation. AIppocampus adopts this
    only above the source layer.
- [The Pearl of Presence](pearl-of-presence.md)
  - Presence as the quality of encounter made possible by sustained,
    source-backed acquaintance.
- [Dream Task Design](dream-task-design.md)
  - Output-separated interpretation layers with source refs and
    counter-evidence.
