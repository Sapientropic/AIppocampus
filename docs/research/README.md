# Research Notes

This folder holds speculative and product-facing research notes for
AIppocampus. These notes are not runtime contracts. Stable operational rules
belong in `skills/aippocampus/SKILL.md` and its focused references; the product
north star stays in `docs/roadmap.md`.

Use this folder to explore where AIppocampus could go next while keeping the
same boundary as the rest of the project: clean source remains truth, generated
summaries and symbolic encodings remain navigation or intuition layers, and
strong claims need source-backed evidence.

## Reading Order

1. [The Pearl of Presence](pearl-of-presence.md)
   - Why AIppocampus exists.
   - Frames the product goal as presence through sustained, source-backed
     acquaintance rather than persona construction.
2. [Dream Task Design](dream-task-design.md)
   - The most direct implementation path.
   - Proposes integrative subconscious jobs: compensatory analysis first, then
     prospective analysis, amplification, and active imagination.
3. [Ambient Associative Recall](ambient-associative-recall.md)
   - The user-facing recall behavior.
   - Designs active gentle nudges, private recall cards, thread ambient cache,
     and timeboxed DeepSeek scouts that warm multi-turn agent threads without
     making the foreground hook wait for a full batch.
4. [Thread Intuition Layer](affect-side-channel.md)
   - The intuition-layer candidate.
   - Explores compact thread mood markers, especially hexagram arcs plus a
     "do not decode" instruction, as a low-token background signal.
5. [Compact Activation Signals](compact-activation-signals.md)
   - The long-shot research frontier.
   - Keeps the question of activation-efficient memory alive, while current
     reviewer consensus points the near-term path back to structured text
     cognitive portraits.

## Evidence Levels

| Level | Meaning | Examples in this folder | How to use |
|---|---|---|---|
| A. Primary-source confirmed | Backed by official docs, primary papers, or repo source. | Platonic Representation Hypothesis, universal number representations, non-surjective steering, Anthropic Managed Agents memory stores and Dreams. | Safe to cite as background, while preserving the original scope and limitations. |
| B. Locally validated experiment | Backed by project-local experiments or cross-model review, but not yet reproduced as a public benchmark. | Hexagram/five-tone leakage tests, "do not decode" mitigation, hexagram-only thread mood trials. | Treat as promising design evidence; do not present as general model science. |
| C. Product hypothesis | A coherent design claim derived from AIppocampus goals and local evidence. | Two-layer memory, ambient associative recall, cognitive portrait as structured text, compensatory dream task. | Good for roadmap and prototype planning; needs evaluation before runtime adoption. |
| D. Philosophical frame | A conceptual lens that guides product taste and positioning. | Pearl-like presence, relationship continuity, Jung-inspired integration. | Useful for direction and vocabulary; do not convert directly into implementation claims. |
| E. Long-shot research | Plausible but currently weak, blocked, or dependent on access beyond normal black-box APIs. | Cross-model numerical activation codes for personal memory; token sequences approximating white-box activation steering. | Keep as research backlog, not near-term build priority. |

## Current Assessment

The strongest near-term path is:

```text
clean source
  -> existing extractive metadata
  -> structured cognitive portrait
  -> ambient associative recall
  -> compensatory dream task
  -> optional intuition marker
```

The riskiest path is jumping straight to symbolic or numerical activation
codes as the main memory carrier. Those ideas are valuable because they name
the right problem, but the current evidence supports structured text and
source-backed integration first.

## Confirmed External Anchors

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

## Maintenance Notes

- Keep this README as an index and evidence map, not a second copy of the
  memos.
- When a claim graduates into runtime behavior, move the operational contract
  to the relevant skill reference and leave only a pointer here.
- Prefer updating source links and evidence levels over adding warning labels
  when a claim can be confirmed or narrowed.
