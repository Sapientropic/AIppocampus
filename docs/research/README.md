# Research Notes

This folder holds speculative and product-facing research notes for
AIppocampus. These notes are not runtime contracts. Stable operational rules
belong in `skills/aippocampus/SKILL.md` and its focused references; the product
north star stays in `docs/roadmap.md`.

Use this folder to explore where AIppocampus could go next while keeping the
same boundary as the rest of the project: clean source remains truth, generated
summaries and symbolic encodings remain navigation or intuition layers, and
strong claims need source-backed evidence.

## Long Garden

Use [`seeds/`](seeds/) for ideas that should be remembered but should not stand
in the active roadmap or open-issue foreground yet. A seed can graduate when it
has source-backed motivation, a clear product layer, and a 1-2 week fixture,
doc, CLI, runtime, or verification slice.

This keeps the research soul intact while protecting the ordinary user path
from looking like a control tower.

## Reading Order

1. [The Pearl of Presence](pearl-of-presence.md)
   - Why AIppocampus exists.
   - Frames the product goal as presence through sustained, source-backed
     acquaintance rather than persona construction.
2. [Source as World, Interpretation as Weather](source-as-world.md)
   - The source-fidelity foundation beneath Pearl-like presence.
   - Frames language as the agent's body/world, human memory as necessary
     compression, and clean source as the ground that interpretations must
     return to.
3. [Journey Tracking](journey-tracking.md)
   - The product ontology shift.
   - Frames long-running continuity as first-person plural journeys rather
     than third-person user modeling.
4. [Reflection Space](reflection-space.md)
   - The user-facing surface for journeys.
   - Proposes an optional map room where the interaction mode changes from
     task-solving to reflection and review.
5. [Dream Task Design](dream-task-design.md)
   - The most direct implementation path.
   - Proposes integrative subconscious jobs: compensatory analysis first, then
     prospective analysis, amplification, and active imagination.
6. [Ambient Associative Recall](ambient-associative-recall.md)
   - The user-facing recall behavior.
   - Designs active gentle nudges, private recall cards, thread ambient cache,
     and timeboxed DeepSeek scouts that warm multi-turn agent threads without
     making the foreground hook wait for a full batch.
7. [Correction Reconsolidation](correction-reconsolidation.md)
   - The reliability layer for user corrections and failed-route lessons.
   - Designs hook-triggered correction windows, outcome events, detached dream
     adjudication, and anti-nag reminder budgets for compaction continuity.
8. [Agency From Cognitive Maps](agency-from-cognitive-map.md)
   - The next-stage agency hypothesis.
   - Maps source-backed continuity into affordance tickets that a proactive
     host can use for bounded, reversible, anti-nag initiative.
9. [Agent Coding Context Blueprint](agent-coding-context-analysis.md)
   - The agent-coding market wedge.
   - Positions AIppocampus as a source-backed implicit-knowledge continuity
     layer for rejected paths, tacit constraints, and design-intent evolution,
     with Codeksei as the executive control shell.
10. [Thread Intuition Layer](affect-side-channel.md)
   - The intuition-layer candidate.
   - Explores compact thread mood markers, especially hexagram arcs plus a
     "do not decode" instruction, as a low-token background signal.
11. [Compact Activation Signals](compact-activation-signals.md)
   - The long-shot research frontier.
   - Keeps the question of activation-efficient memory alive, while current
     reviewer consensus points the near-term path back to structured text
     cognitive portraits. The first deterministic benchmark for that near-term
     slice is `benchmarks/aippocampus/benchmark_cognitive_portrait.py`.
12. [Memory-System Pain Taxonomy](memory-system-pain-taxonomy.md)
   - Public issue/user-feedback taxonomy for Mem0, Graphiti/Zep, Letta, and HN
     memory pain points.
   - Feeds public-safe benchmark fixtures without turning competitor reports
     into broad marketing claims.

## Study Packs

- [Hexagram Validation](hexagram-validation/README.md)
  - Local validation notes and deterministic helper code for the hexagram /
    five-tone intuition-layer experiments.
  - Treat this as experiment evidence for research navigation, not as a runtime
    contract.

## Evidence Levels

| Level | Meaning | Examples in this folder | How to use |
|---|---|---|---|
| A. Primary-source confirmed | Backed by official docs, primary papers, or repo source. | Platonic Representation Hypothesis, universal number representations, non-surjective steering, Anthropic Managed Agents memory stores and Dreams. | Safe to cite as background, while preserving the original scope and limitations. |
| B. Locally validated experiment | Backed by project-local experiments or cross-model review, but not yet reproduced as a public benchmark. | Hexagram/five-tone leakage tests, "do not decode" mitigation, hexagram-only thread mood trials, deterministic structured-text cognitive portrait benchmark. | Treat as promising design evidence; do not present as general model science. |
| C. Product hypothesis | A coherent design claim derived from AIppocampus goals and local evidence. | Two-layer memory, ambient associative recall, cognitive portrait as structured text, compensatory dream task. | Good for roadmap and prototype planning; needs evaluation before runtime adoption. |
| D. Philosophical frame | A conceptual lens that guides product taste and positioning. | Pearl-like presence, source as world, relationship continuity, Jung-inspired integration. | Useful for direction and vocabulary; do not convert directly into implementation claims. |
| E. Long-shot research | Plausible but currently weak, blocked, or dependent on access beyond normal black-box APIs. | Cross-model numerical activation codes for personal memory; token sequences approximating white-box activation steering. | Keep as research backlog, not near-term build priority. |

## Current Assessment

The strongest near-term path is:

```text
clean source
  -> existing extractive metadata
  -> journey tracking / structured cognitive portrait
     (benchmark compactness and source-fidelity before runtime promotion)
  -> ambient associative recall
  -> compensatory dream task / reflection space
  -> optional intuition marker
```

The riskiest path is jumping straight to symbolic or numerical activation
codes as the main memory carrier. Those ideas are valuable because they name
the right problem, but the current evidence supports structured text and
source-backed integration first.

## Confirmed External Anchors

- [Michael Levin's TAME framework](https://arxiv.org/abs/2201.10346)
  anchors the multi-scale agency lens: agency can be studied as a continuous,
  empirical question across substrates and scales. For AIppocampus, this is a
  philosophical frame, not evidence that current LLMs have inner selves.
- [Bootstrapping Life-Inspired Machine Intelligence](https://arxiv.org/abs/2602.08079)
  anchors the "cognitive light cone" vocabulary: goals, memory, prediction,
  and control can expand across time and space. AIppocampus adapts this as
  relationship-continuity language, not as a direct implementation claim.
- [Self-Improvising Memory](https://www.mdpi.com/1099-4300/26/6/481)
  supports the idea that memory can shift through salience and
  reinterpretation. In AIppocampus this applies only to dream, intuition, and
  hypothesis layers; clean source remains fidelity-grounded.
- [The Platonic Representation Hypothesis](https://arxiv.org/abs/2405.07987)
  supports the background idea that model representations can converge across
  domains, with limitations and counterexamples.
- [Language Models Learn Universal Representations of Numbers and Here's Why
  You Should Care](https://arxiv.org/abs/2510.26285) supports a narrower claim:
  number representations can be highly systematic and transferable across
  LLMs.
- [Steered LLM Activations are Non-Surjective](https://arxiv.org/abs/2604.09839)
  supports the caution that white-box activation steering can reach states that
  black-box prompting cannot reproduce.
- [Claude Managed Agents memory stores](https://platform.claude.com/docs/en/managed-agents/memory)
  confirm persistent memory stores for Managed Agents, including versioned
  memory changes.
- [Claude Managed Agents Dreams](https://platform.claude.com/docs/en/managed-agents/dreams)
  confirm an official Research Preview where Dreams read memory stores and
  past sessions to produce a reorganized output memory store.
- [LangGraph](https://docs.langchain.com/oss/javascript/langgraph/overview),
  [AutoGPT](https://agpt.co/), [Manus Agent Mode](https://help.manus.im/en/articles/11711128-what-are-the-differences-between-chat-mode-and-agent-mode),
  [AutoGen](https://microsoft.github.io/autogen/), [CrewAI](https://docs.crewai.com/),
  [OpenHands](https://github.com/OpenHands/OpenHands), [SWE-agent](https://github.com/SWE-agent/SWE-agent),
  and [Voyager](https://voyager.minedojo.org/) confirm broad external demand
  for stateful, workflow-capable, and task-executing agents. They are execution
  and orchestration anchors rather than evidence that AIppocampus's agency
  ticket design is already validated.
- [Lost in the Middle](https://arxiv.org/abs/2307.03172),
  [Chroma Context Rot](https://www.trychroma.com/research/context-rot),
  [CodeCompass](https://arxiv.org/abs/2602.20048), and
  [Anthropic context engineering](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)
  anchor the coding-agent context problem: long context, code navigation, and
  harness-level context selection are active problems. They support the problem
  framing, not a claim that AIppocampus's implicit-knowledge blueprint is
  validated.

## Maintenance Notes

- Keep this README as an index and evidence map, not a second copy of the
  memos.
- When a claim graduates into runtime behavior, move the operational contract
  to the relevant skill reference and leave only a pointer here.
- Prefer updating source links and evidence levels over adding warning labels
  when a claim can be confirmed or narrowed.
