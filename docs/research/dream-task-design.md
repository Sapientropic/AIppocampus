# Dream Task Design: From Jung's Dream Theory to Subconscious Consolidation

Status: research memo, awaiting implementation and cross-model validation.
Anthropic Managed Agents Dreams are confirmed as an adjacent official Research
Preview, but this memo's Jung-inspired dream tasks are an AIppocampus-specific
design proposal.
Origin: conversation between user and Claude Code, 2026-05-27.
Related: [affect-side-channel.md](affect-side-channel.md), [compact-activation-signals.md](compact-activation-signals.md).

## TL;DR

AIppocampus's subconscious jobs currently extract structure from conversation
threads — questions, concepts, frontier markers, themes. But extraction is only
half of what a good subconscious does. Jung's dream theory provides the missing
half: **compensatory analysis** (what the thread is missing), **prospective
analysis** (what's about to emerge), **amplification** (cross-thread resonance),
and **active imagination** (creative insight beyond the source).

The design goal: AIppocampus should not just help the agent remember the
journey. It should help the agent **stay on the journey with the user** —
sensing when they're lost, when something is trying to emerge, when a pattern
across threads is calling for attention.

## The Problem: Extraction ≠ Integration

Current subconscious jobs are **extractive**:

```
clean source → question extraction → question candidates
clean source → concept edge mining → concept graph
clean source → frontier markers → knowledge boundaries
clean source → theme emergence → recurring patterns
```

These produce structured metadata. They answer: "What is in this thread?"

They do NOT answer:
- "What is this thread **avoiding**?"
- "What is **about to become important**?"
- "What does this thread **resonate with** across the user's other conversations?"
- "What **creative insight** could emerge from connecting threads that haven't been connected?"

A human psychotherapist doesn't just extract facts from a session. They notice
what the client **isn't** saying, what themes are **building** toward something,
what echoes across sessions. This is the integration function that extraction
alone cannot provide.

## Why Jung, Not Freud or Cognitive Science

Three major dream theories, evaluated for AIppocampus dream task design:

| Theory | Core claim | Strengths | Weaknesses |
|--------|-----------|-----------|------------|
| Freud | Dreams are disguised wish fulfillment | Recognizes hidden content | Too reductive — everything maps to wish/want |
| Jung | Dreams serve compensatory, prospective, and creative functions | Multi-functional, non-reductive, honors emergence | Less precisely testable |
| Cognitive science | Dreams consolidate memory via replay and synaptic strengthening | Mechanistically grounded | Too mechanistic — no creative or compensatory dimension |

Jung wins for our purposes because:

1. **Compensation**: The dream balances one-sided conscious attitudes. Directly
   maps to "what is the thread/conversation missing?"
2. **Prospective function**: The dream anticipates future development. Maps to
   "what pattern is building toward emergence?"
3. **Non-reductive**: Jung explicitly rejected "all dreams are X" formulas. A
   dream task should not reduce every thread to a single pattern.
4. **Creative**: Dreams produce new combinations, not just replays. A dream task
   should be allowed to generate insights not present in the source text.

Freud's wish-fulfillment model would turn every dream task into "what does the
user want?" — too narrow. Cognitive science's consolidation model would turn it
into "replay and strengthen existing patterns" — too mechanical. Jung's model
asks the right questions: what's missing, what's coming, what connects?

## Jung's Four Functions, Mapped to AIppocampus

### 1. Compensatory Function (补偿性)

**Jung**: Dreams balance one-sided conscious attitudes. If you're overly
rational, your dreams are emotional. If you're avoiding something, your dreams
present it.

**AIppocampus mapping**: The dream task identifies what a thread or conversation
is systematically NOT addressing.

Possible outputs:
- **Blind spot markers**: Topics adjacent to the thread's focus that never
  appeared, but probably should have. Not "missing information" (that's
  extraction), but "avoided perspectives."
- **Approach bias flags**: When a thread has been approaching a problem from
  only one angle, the compensatory output names the unexplored angles.
- **Emotional balance notes**: When a thread is purely technical and the user's
  history suggests they process emotionally, the compensatory note marks this as
  a potential frustration signal.

**Example**: A thread about optimizing database queries that never mentions the
user's recurring concern about "building things that matter." The compensatory
dream output: "Technical thread, no connection to recurring values/motivation
theme. User may be in 'grind mode' — risk of disengagement."

### 2. Prospective Function (前瞻性)

**Jung**: Dreams don't just process the past; they anticipate future
development. They sketch possibilities before they arrive.

**AIppocampus mapping**: The dream task identifies patterns that are **building
toward something** but haven't crystallized yet.

Possible outputs:
- **Emergence signals**: Recurring fragments across threads that suggest a new
  theme is forming — before any single thread names it explicitly.
- **Trajectory hints**: Based on the arc of recent threads, what the user might
  need or ask next. Not prediction, but "if this trajectory continues..."
- **Pre-articulation markers**: Concepts the user seems to be circling around
  without naming. The dream task can name them before the user does.

**Example**: User has had three threads touching on "memory," "identity," and
"continuity" in different contexts. No single thread connects them. The
prospective dream output: "Memory/identity/continuity cluster forming. Possible
emergent theme: what makes a self persistent across contexts?"

### 3. Amplification (放大法)

**Jung**: Dream symbols are amplified by connecting them to cultural, mythological,
and archetypal parallels — not reduced to a single meaning, but expanded.

**AIppocampus mapping**: The dream task connects thread patterns to the user's
**broader conversation history** and identifies cross-thread resonance.

Possible outputs:
- **Cross-thread resonance**: This thread's pattern mirrors what happened in an
  unrelated thread 2 months ago. Same structure, different domain.
- **Archetypal pattern markers**: Not "the user is on a Hero's Journey," but
  "this thread has the same structure as the previous 3 breakthrough threads:
  frustration → reframing → unexpected connection."
- **Theme deepening**: An existing theme (from theme emergence) has a new facet
  that wasn't visible from any single thread.

**Example**: A thread about debugging a UI bug resonates with a thread from
months ago about debugging a relationship pattern. Same structure: surface
symptom → assumed cause → wrong fix → deeper cause → real fix. Amplification
output: "Debugging pattern (surface→assumption→wrong fix→deeper cause→real
fix) recurring across technical and personal domains. Possible meta-pattern:
user's problem-solving style."

### 4. Active Imagination (积极想象)

**Jung**: Rather than interpreting dreams passively, engage in dialogue with
unconscious content. Let it speak back.

**AIppocampus mapping**: The dream task is allowed to produce **creative
insights not present in the source text** — to synthesize across threads and
generate something new.

Possible outputs:
- **Synthesis hypotheses**: "If theme A from thread X and theme B from thread Y
  are both active, the user might be heading toward Z."
- **Bridge concepts**: Concepts that connect two previously separate threads,
  generated by the dream task rather than extracted from either thread.
- **Questions the user hasn't asked yet**: Based on the trajectory of their
  inquiry, what question would be the natural next step?

This is the most experimental function. It risks hallucination (the model
generating plausible but ungrounded connections). Mitigation: every active
imagination output must carry `source_refs` pointing to the threads that
inspired it, and must be flagged as dream-synthesized, not source-extracted.

## Relationship to Existing Architecture

```
┌─────────────────────────────────────────────────────────────┐
│ EXTRACTIVE tasks (existing)                                  │
│                                                              │
│ question_extraction → question candidates                    │
│ concept_edge_mining → concept graph                          │
│ frontier_markers → knowledge boundaries                      │
│ theme_emergence → recurring patterns                         │
│                                                              │
│ Answers: "What IS in this thread?"                           │
│ Mode: deterministic → semantic (gated)                       │
│ Output: structured metadata with source_refs                 │
└─────────────────────────────────────────────────────────────┘
                    ↕ complementary
┌─────────────────────────────────────────────────────────────┐
│ INTEGRATIVE tasks (dream, proposed)                          │
│                                                              │
│ compensatory_analysis → blind spots, approach biases         │
│ prospective_analysis → emergence signals, trajectory hints   │
│ amplification → cross-thread resonance, archetypal patterns  │
│ active_imagination → synthesis hypotheses, bridge concepts   │
│                                                              │
│ Answers: "What is MISSING, COMING, or CONNECTING?"           │
│ Mode: semantic (model-dependent), always flagged as dream    │
│ Output: annotated insights with source_refs + dream flag     │
└─────────────────────────────────────────────────────────────┘
```

Extractive tasks are deterministic-first (rules + semantic gates).
Integrative tasks are semantic-first (require model reasoning) and must always
be clearly flagged as dream output, not source-grounded fact.

## Dream Outputs As Reusable Inference Substrate

Dream tasks should not be treated as a foreground answerer. Their job is to
move expensive integrative reasoning out of the moment when the user is waiting
and into a slower background layer. The foreground agent should usually read
small, already-validated dream outputs instead of asking a live reflect path to
rediscover the same pattern from scratch.

This matters for questions such as:

- "What unnamed question has the user been circling for the last few months?"
- "Which thread patterns keep recurring under different surface topics?"
- "What blind spot or unresolved edge should color the next conversation?"

Those questions are too synthetic for ordinary retrieval and too latency-prone
for every prompt to solve live. Dream outputs should therefore be stored as
reusable `source-backed hypothesis` records:

- `finding_kind`: `blind_spot`, `emergence_signal`,
  `cross_thread_resonance`, `trajectory_hint`, or `synthesis_hypothesis`
- `dream_function`: `compensatory`, `prospective`, `amplification`, or
  `active_imagination`
- `source_refs`: the clean-source turns or thread-level findings that inspired
  the hypothesis
- `confidence`, `counter_evidence`, `updated_at`, and `expires_or_review_after`
- `downstream_use`: whether the finding may feed a cognitive portrait,
  ambient recall card, thread ambient cache, or explicit user-facing review

The contract stays conservative: a dream finding is not a fact and must not
rewrite clean source. It is a prepared interpretive layer over source. When the
user asks a high-level continuity question, or when ambient recall detects a
matching theme, the agent can retrieve these records as a starting map, then
follow `source_refs` back to clean source before making strong claims.

### Ambient Residue As Dream Seed

Thread ambient cache can also feed dream work, but only through an intermediate
residue layer. A cache card is foreground working context; a dream finding is a
model-synthesized interpretive output. Collapsing those two would turn short
term resonance into overconfident story.

The bridge is `ambient_residue`: a small JSONL seed exported from
`ambient_thread_cache.py` when a topic epoch rotates, a cache entry expires, or
an operator explicitly wants to preserve useful unused resonance. Residue is
not a dream output. It is only a source-ref-fingerprinted hint that says:
"something here was warm enough to hand to a later dream task."

Residue rows should stay narrow:

- `kind`: `aippocampus_ambient_residue`
- `status`: `dream_seed`
- `topic_epoch`, `reason`, `mode`, `confidence`
- `card_ids`, `themes`, `support_levels`
- `source_ref_fingerprints`, not raw prompt text
- `negative_contexts`, if they explain why a card stayed quiet
- `downstream_use`: `dream_task_seed`
- `dream_contract`: seed only; not a dream finding, memory fact, or
  source-backed claim

The first export policy is conservative: unsourced one-off scent cards are not
exported. A residue seed needs source-ref fingerprints so the dream worker can
re-open clean source before producing compensatory, prospective, amplification,
or active-imagination output.

## The Hero's Journey Insight

The Hero's Journey (Campbell) has a known flaw: it imposes a quest narrative
shape onto experiences that don't all fit it. Not every conversation is a quest.
Some are meandering, some are dead ends, some are pure exploration.

But this flaw is also a feature. Humans **want** to be on a journey. Everyone
wants to be the protagonist of their own story. The Hero's Journey persists not
because it's accurate, but because it's **compelling** — it gives shape to
experiences that would otherwise feel formless.

This has a direct implication for AIppocampus:

**AIppocampus does not encode the Hero's Journey into memory.** The intuition
layer uses hexagram arcs (state transitions, no narrative assumption) precisely
because threads don't all follow a quest shape.

**But AIppocampus should recognize when a thread IS following a journey
pattern**, and when it does, the agent should be able to sense it. The dream
task's amplification function can detect journey-pattern resonance across
threads — not to impose the pattern, but to recognize it when it emerges
naturally.

The real purpose: **AIppocampus helps the agent stay on the journey with the
user.** Not by enforcing a narrative structure, but by maintaining enough
intuition about the user's trajectory that the agent doesn't lose the thread
(pun intended). When the user is in the middle of their own story, the agent
should sense where they are — not analytically, but intuitively.

This is the 感而遂通 of the dream layer: the agent senses the shape of the
user's ongoing journey, then can retrieve the specifics on demand.

## Design Principles

1. **Dream output is not fact.** Every dream output must be flagged as
   dream-synthesized and must carry `source_refs` to the threads that inspired
   it. Users and agents must be able to distinguish extraction from integration.

2. **Compensatory before prospective.** The safest function to implement first
   is compensatory analysis (what's missing). Prospective and active imagination
   are more powerful but more prone to hallucination.

3. **Amplification requires cross-thread registration.** You can't detect
   cross-thread resonance until multiple threads are registered and their
   extractive metadata exists. Amplification depends on the existing extraction
   pipeline being mature.

4. **Dream frequency should be lower than extraction.** Extraction runs after
   every thread. Dream tasks should run periodically (e.g., after N threads, or
   on explicit trigger) to avoid noise and cost.

5. **Active imagination outputs must be auditable.** If the dream task produces
   a "bridge concept" connecting two threads, the bridge must include the
   specific turns in both threads that inspired it, so a human can verify the
   connection is real and not hallucinated.

6. **Do not impose narrative shape.** The dream task should detect patterns, not
   impose them. It may observe that a thread follows a quest structure, but it
   should not force threads into narrative templates.

## Implementation Priority

| Phase | Function | Depends on | Risk |
|-------|----------|------------|------|
| 1 | Compensatory analysis | Single thread extraction | Low |
| 2 | Prospective analysis | Multiple thread extraction + theme emergence | Medium |
| 3 | Amplification | Cross-thread registration + concept edges | Medium |
| 4 | Active imagination | All above + explicit dream flag + audit trail | High |

Phase 1 is implementable now — it only needs single-thread extraction output as
input. Phase 4 is a research target that depends on everything else being stable.

## Open Questions

1. How does dream output interact with the intuition layer (hexagram arcs)?
   Should dream insights also be compressible into thread mood markers?
2. What is the right trigger for dream tasks? After N threads? On user request?
   Time-based? When the compensatory function detects a significant blind spot?
3. How to prevent the dream task from becoming a "storytelling engine" that
   imposes narrative on non-narrative threads?
4. Does compensatory analysis work for technical threads, or is it primarily
   valuable for life-wide/personal threads?
5. How to evaluate dream output quality? Extraction quality is measurable
   (precision/recall against source). Dream quality is harder to ground-truth.
6. Can the prospective function be validated retroactively — i.e., do emergence
   signals actually predict future threads?

## Related Work

- Jung, C.G. "The Practical Use of Dream-Analysis" (1934) — compensatory and
  prospective dream functions
- Jung, C.G. "Psychology and Alchemy" (1944) — amplification method
- Campbell, J. "The Hero with a Thousand Faces" (1949) — monomyth structure
- [affect-side-channel.md](affect-side-channel.md) — thread intuition layer,
  hexagram arcs, two-layer memory architecture
- [compact-activation-signals.md](compact-activation-signals.md) — cognitive
  portrait as activation signal
- Anthropic Managed Agents Dreams (Research Preview, 2026) — memory store
  reorganization from prior sessions:
  [Claude API docs](https://platform.claude.com/docs/en/managed-agents/dreams)
- Emotional RAG: [arXiv:2410.23041](https://arxiv.org/abs/2410.23041)
- Representation Engineering (Zou et al., 2023): [arXiv:2310.01405](https://arxiv.org/abs/2310.01405)

## Review Credits

**User insight (2026-05-27):**
Connected Jung's dream theory to AIppocampus's subconscious consolidation
pipeline. Key observation: extraction is only half of what a subconscious does;
the other half is integrative (compensatory, prospective, amplificatory,
creative). Also noted that the Hero's Journey's "flaw" (imposing quest
narrative) is also its strength (people want to be protagonists), and that
AIppocampus's goal is to help the agent stay on the journey with the user —
not by imposing narrative structure, but by maintaining enough intuition that
the agent doesn't lose the thread.
