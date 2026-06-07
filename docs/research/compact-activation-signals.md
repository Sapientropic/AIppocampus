# Compact Activation Signals as Memory Surface

Status: research memo, not runtime contract. Reviewed; near-term priority
narrowed to structured text cognitive portraits. The first deterministic
structured-text benchmark now lives at
`benchmarks/aippocampus/benchmark_cognitive_portrait.py`.
Origin: conversation between user and Claude Code, 2026-05-27.
Reviewed by: gemini-researcher, kimi-reviewer (2026-05-27). See Review Credits below.
Purpose: lay out a research thread connecting several recent findings toward a
possible next-generation memory surface for AIppocampus.

## The Core Idea

Current AI memory systems store and retrieve **text**. AIppocampus stores clean
source, MemPalace stores verbatim conversations, and Anthropic Managed Agents
Dreams can reorganize memory stores from prior sessions — all operate on human
language as the memory carrier.

But human language evolved for human brains. It is not the most efficient
encoding for activating knowledge in a transformer. If models share a compact
internal concept space (evidence is growing), then memory could be stored as
**activation signals** — minimal representations that directly activate the
relevant model weights — rather than as text that the model must re-parse.

The hypothesis: there exists a more compact, more semantically precise encoding
for inter-session and inter-model memory than human natural language.

## Three Pillars of Evidence

### Pillar 1: The Platonic Representation Hypothesis

Huh et al. (2024), MIT. [arXiv:2405.07987](https://arxiv.org/abs/2405.07987).

Neural networks trained on different data, different objectives, and different
modalities converge toward a shared statistical model of reality. Bigger models
converge more. The shared representation captures something closer to "reality"
than to any single modality's encoding.

**Implication for AIppocampus:** If models share a concept space, then a memory
encoding that targets this shared space could be portable across models — not
tied to one provider's token vocabulary.

**Status:** Verified across vision, language, and audio models. Convergence is
empirical, not proven theoretically.

### Pillar 2: Universal Representations of Numbers

Štefánik et al. (2024/2026), MCML.
[arXiv:2510.26285](https://arxiv.org/abs/2510.26285).
Accepted at ACL 2026.

> **Correction note (2026-05-27):** An earlier draft cited arXiv:2410.13857,
> which is an unrelated paper on numerical precision in transformers. The
> correct arXiv ID is 2510.26285.

Different LLMs develop nearly identical internal representations of numbers.
One model's number representations can be decoded by a completely different
model to recover the same numerical concept. The representations converge by
early layers and stay stable through mid-layers.

**Implication for AIppocampus:** At minimum, numerical concepts have a universal
encoding across models. If this universality extends beyond numbers to broader
conceptual structure, then numerical sequences could serve as a cross-model
"concept language."

**Status:** Verified for numbers. Extending to general concepts is an open
research question.

### Pillar 3: Steered Activations Are Non-Surjective

arXiv, 2026. [arXiv:2604.09839](https://arxiv.org/abs/2604.09839).

Activation steering can reach model states that no token sequence can reach.
The mapping from steering directions to reachable behaviors is not onto. This
means token-level control (what API users have) is fundamentally limited
compared to activation-level control (what model owners have).

**Implication for AIppocampus:** There is a hard ceiling on how well any
token-based memory encoding can approximate true activation steering. But the
ceiling may be high enough to be practically useful — the question is how close
we can get.

**Status:** Verified. The gap is real but not yet quantified for practical
memory use cases.

## The User's Insight: Personal Memory Is Just Information

A key observation from the project's user: what we call "personal memory" is
really just a user profile — facts, preferences, patterns, recurring questions.
To the model, "the user prefers sage green" is no different from "sage green is
a warm, muted green." Both are information. The model does not "know" the user
as a person; it processes information about them.

This collapses the distinction between "activating general knowledge" and
"recalling personal memory." Both are information activation. Both can
theoretically be compressed into efficient activation signals.

Question tracking, frontier markers, and theme emergence — AIppocampus's
existing job circuits — are already building a compact "cognitive portrait" of
the user. This portrait may be a more efficient activation signal than any
amount of retrieved text.

## Comparison to Current Approaches

| Approach | Carrier | Cross-model | Compactness | Semantic precision |
|---|---|---|---|---|
| Full text retrieval | tokens | universal | low | lossy |
| Summaries / notes | tokens | universal | medium | lossy |
| Embedding vectors | floats | needs alignment | high | high |
| Model activations | floats | partial (Platonic) | highest | highest |
| Optimized token sequences | tokens | universal (hypothesis) | medium-high | medium-high |
| Numerical token codes | tokens (numbers) | testable hypothesis | medium-high | unknown |

## What Is Testable Now

### Experiment 1: Scent Efficiency Benchmark

Take a known user profile (from existing AIppocampus data). Generate multiple
candidate "activation prompts" of varying lengths. Test each against a model:
how well does the model recover the user's preferences, patterns, and recurring
questions with only the activation prompt (no full context)?

Measure: token count vs. behavioral equivalence to full-context performance.

### Experiment 2: Cross-Model Concept Transfer

Encode a concept as a numerical token sequence using one model's embedding
space. Feed this sequence to a different model. Measure whether the second
model activates the correct concept.

This tests whether the Platonic convergence extends to token-level numerical
encodings, not just activation-level representations.

### Experiment 3: Cognitive Portrait as Activation Signal

Take AIppocampus's existing question tracking output (question candidates,
frontier markers, recurring question links). Format this as a compact prompt.
Compare model behavior with this prompt against model behavior with full clean
source injection.

If the cognitive portrait activates equivalent behavior with far fewer tokens,
that validates the "user profile as activation signal" hypothesis.

**Implemented near-term slice (2026-05-30):**
`benchmark_cognitive_portrait.py` runs this as a structured-text fixture, not
as activation steering. It builds a compact portrait from source-backed
`question_candidate`, `frontier_marker`, and `question_link` rows, compares the
rendered portrait prompt with fuller clean-source injection, and reports:

- approximate token count and savings;
- whether every reusable portrait item carries source refs / source-finding
  back-pointers;
- whether selected action/guardrail prompts preserve expected cues;
- where compact portraits lose fidelity, currently exact quote recovery;
- where naive trait summaries over-personalize.

This supports a modest implementation claim: structured portraits can be a
source-backed navigation layer worth benchmarking. It does not support a claim
that token prompts reproduce white-box activation states or cross-model
activation steering.

**No-leakage diagnostic slice (2026-06-06, #313):**
`aippocampus_runtime.reflection.thread_story` adds a source-backed
thread-story / cognitive-portrait activation packet fixture. It carries
freshness, sensitivity, source back-pointers, and suppression boundaries while
keeping raw story text, symbolic affect channels, local paths, and persona-like
claims out of the agent-visible packet. Its deterministic answer-boundary probe
requires source reopen before packet-only material can support a factual answer.
The same helper also reports a public-safe deterministic answer-comparison with
plain-baseline, packet-only, and source-reopened arms so packet-only factual
answers fail independently from source-reopened answers.

This is still structured text navigation, not activation steering, live model
equivalence, default recall lift, or user/personality truth.

## Relationship to Existing AIppocampus Architecture

This research direction does not replace the current design. It suggests a
possible evolution path for the memory surface:

```
Current:  clean source → text search → text injection → model parses text
Future:   clean source → subconscious extraction → cognitive portrait →
          portrait optimized as activation signal → model activates directly
```

The subconscious job circuits (question extraction, concept edges, trigger
mining, frontier markers, theme emergence) already produce the raw material
for a cognitive portrait. The new step would be: optimize this portrait for
activation efficiency, not just information completeness.

## Open Questions

1. Does Platonic convergence extend to user-profile-level concepts, or only to
   low-level perceptual/numerical features?
2. Can token-level numerical codes approximate activation-level steering well
   enough for practical memory use?
3. Is the optimal activation encoding the same for different model families
   (Claude, GPT, Gemini, DeepSeek)?
4. How stable are activation signals across model versions (e.g., Claude 4.5
   vs 4.7)?
5. Could AIppocampus's cognitive portrait be compact enough to fit in a system
   prompt without consuming significant context budget?

## What This Is Not

- This is not a claim that models have "minds" or "understanding."
- This is not a proposal to replace all text memory with numerical codes.
- This is not something that can be implemented with current black-box API
  access alone — it requires experimentation and likely some model-level
  cooperation.
- The user profile = activation signal hypothesis is testable but not yet
  validated.

## Related Work

- Platonic Representation Hypothesis: [arXiv:2405.07987](https://arxiv.org/abs/2405.07987)
- Universal Number Representations: [arXiv:2510.26285](https://arxiv.org/abs/2510.26285)
- Non-Surjective Steering: [arXiv:2604.09839](https://arxiv.org/abs/2604.09839)
- Dynamic Steering with Episodic Memory (ACL 2025): [ACL Anthology](https://aclanthology.org/2025.findings-acl.706/)
- SPARE: SAE-Based Steering (NAACL 2025): [ACL Anthology](https://aclanthology.org/2025.naacl-long.264.pdf)
- Attention-Level Activation Steering (2026): [arXiv:2605.10664](https://arxiv.org/html/2605.10664v1)
- Representation Engineering (Zou et al., 2023): [arXiv:2310.01405](https://arxiv.org/abs/2310.01405)
- Memory Tokens: Reversible Sentence Embeddings: [ResearchGate](https://www.researchgate.net/publication/394300523)
- Awesome Activation Engineering: [GitHub](https://github.com/ZFancy/awesome-activation-engineering)
- Quanta Magazine coverage of Platonic convergence: [Quanta](https://www.quantamagazine.org/distinct-ai-models-seem-to-converge-on-how-they-encode-reality-20260107/)

## Review Credits

**kimi-reviewer (2026-05-27):**
Critical review. Key findings:
- Citation error: arXiv:2410.13857 is wrong paper (numerical precision, not
  universal representations). Corrected to arXiv:2510.26285.
- Platonic convergence is about low-level statistical structure, not user-level
  concepts. Zero evidence that user preferences have cross-model universal
  representations.
- Non-surjective steering paper actually undermines the argument: if tokens
  cannot reach activation-steered states, the entire token-encoded approach is
  mathematically blocked.
- The proposal conflicts with AIppocampus's source-backed, auditable design
  principles.
- Recommends: develop cognitive portrait as structured text, test its
  compactness against full clean-source injection, and keep activation signals
  as a "long shots" research file.

**gemini-researcher (2026-05-27):**
Balanced review. Key findings:
- Strongest claim: human language is not optimal for model activation.
  Philosophically sound.
- Weakest claim: cross-model portability ignores the tokenizer bottleneck.
  Each model's tokenizer and embedding layer are idiosyncratic.
- User profiles are sparse, arbitrary, and idiosyncratic — not the kind of
  statistical regularity that drives Platonic convergence.
- Missed related work: LLMLingua (discrete prompt compression), gist tokens
  (Mu et al. 2023), KV-cache as engineering bypass for text efficiency.
- KV-caching (Anthropic prompt caching, Gemini context caching) makes the
  "text is inefficient" argument weaker than assumed.
- Recommends: focus on information density and discrete prompt compression
  rather than cross-model activation universality.

### Consensus Convergence

Both reviewers agree on:
1. The core question is interesting but the evidence base for user-level
   concept encoding is weak.
2. The tokenizer/embedding layer is a fundamental practical barrier.
3. Non-surjective steering weakens the token-encoded approach.
4. The practical near-term value is in optimizing structured text (cognitive
   portrait) rather than numerical activation codes.
5. The memo should be classified as a long-term research direction, not a
   near-term implementation target.

### Revised Priority

The "cognitive portrait as structured text" experiment (Experiment 3) is the
most actionable next step. It tests the practical benefit (compactness) without
requiring the impossible part (activation encoding).

The first thread-story packet diagnostic now covers the leakage boundary for
that structured-text direction and includes a deterministic answer-comparison
probe. Broader live-model, model-family, and private real-history probes are
still required before claiming behavioral equivalence or user-visible recall
improvement.
