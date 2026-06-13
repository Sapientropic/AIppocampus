# Thread Intuition Layer: From Symbols to 感而遂通

Status: research memo, validated prototype direction, plus first no-leakage diagnostic packet.
Origin: user observation + experimental validation, 2026-05-27.
Related: [compact-activation-signals.md](compact-activation-signals.md).

## TL;DR

An AI memory system needs not just smarter recall but a way to give the agent
**intuition** — a felt sense of past conversations that colors behavior without
explicit processing. Through 12+ experiments across DeepSeek V4 and Gemini 3.1
Pro, we discovered:

1. Symbolic encodings (chords, hexagrams) have strong cross-model priors but
   trigger "decoding mode" — the model explains the symbols instead of feeling
   them (**salience paradox**).
2. This paradox is solvable with an explicit "don't decode, just feel"
   instruction in the system prompt.
3. I Ching hexagram arcs (e.g., `屯→革→蛊→渐→咸`) can compress an entire
   thread's experience into ~5 characters. With the right instruction, a model
   given only these 5 characters produces responses that capture the thread's
   philosophical essence — not the specific facts, but the feeling and
   direction.
4. The optimal architecture is **two-layer**: hexagram arc (intuition, always
   on, ~5 tokens) + full clean source recall (knowledge, on demand).

## Implementation Boundary

The first #313 executable slice lives in
`skills/aippocampus/scripts/aippocampus_runtime/reflection/thread_story.py`.
It is a no-write diagnostic helper that builds a source-backed thread-story
activation packet, keeps raw story text and symbolic channels private, and
returns negative controls for contradictory arcs, unsupported persona claims,
and multi-channel interference.

The same helper now emits an opt-in deterministic answer-comparison report with
plain-baseline, packet-only, and source-reopened arms. The packet-only arm is
blocked from factual answers; the source-reopened arm is allowed only when
source tokens are attached. This is public-safe contract evidence, not a live
model quality probe.

As of 2026-06-10, the helper also emits
`aippocampus_thread_story_public_shadow_closeout`: a public structured-text
closeout readout for #313 covering leakage, contradiction, packet-only blocking,
source-reopened comparison, interference, and unrelated-story noise controls.
It closes the public shadow slice only; private-history thread-story quality and
live model-family behavior remain separate future evidence questions.

This helper does not install a subconscious extractor, does not promote
hexagram or five-tone markers into default recall/AAR hooks, and does not let a
thread-story packet answer factual memory questions by itself. The packet is
navigation material only; exact claims still require source reopen or
equivalent evidence.

## The Journey (For Context)

Starting point: [Chord Affect Anchors](https://github.com/CyberSealNull/chord-affect-anchors)
showed that chord progressions can serve as compact affect encodings across LLMs.
This led to the question: what other shared textual priors exist?

### Validated Shared Priors

All tested with zero-shot decoding across Gemini 3.1 Pro and DeepSeek V4 Flash.
Zero substantive disagreements on any test case.

| System | Domain | Cross-model | Unique property |
|--------|--------|-------------|-----------------|
| Western chords | Affect | ★★★ | Emergent emotional semantics |
| Chinese five-tone (宫商角徵羽) | Affect | ★★★ | Designed emotional mapping (五行生克) |
| I Ching hexagram transitions | State transitions | ★★★ | Encodes CHANGE natively — no other system does this |
| Math/logic notation | Conceptual relations | ★★★ | Obviously works, not tested |
| Code syntax | Procedures/states | ★★★ | Obviously works, not tested |

### The Salience Paradox

Symbolic encodings suffer from a fundamental problem: **the more distinctive the
symbol, the more the model foregrounds it as "input to decode" rather than
treating it as background context to be felt.**

```
Random noise → discarded (zero effect)
Low-salience text → background processing (subtle coloring)
High-salience symbols → foreground processing (active decoding/leakage)
```

This was verified through:

- **Leakage tests**: Hexagrams injected without instruction → model produces
  divination readings (DeepSeek leaked at all volumes, Gemini at 7+ lines)
- **System prompt advantage**: System prompt gives 2-3x more headroom than user
  message injection (3 lines universally safe via system prompt)
- **Symbol vs text comparison**: For a complex emotional state, text injection
  produced the best emotional attunement; symbol injection produced the worst
  (divination mode)
- **Radical composition (秋+心=愁)**: Better than hexagrams (less salient) but
  not better than plain text
- **Random token control**: Meaningless tokens silently discarded — model CAN
  distinguish signal from noise

### The Breakthrough: Explicit "Don't Decode" Instruction

The salience paradox is **mitigable** by adding an explicit instruction:

> "以下是对话线程的体验标记。不要翻译、解读或引用这些标记，只需让它们
> 像背景音乐一样影响你的回答节奏和温度。"

With this instruction, even pure hexagram arcs (`屯→革→蛊→渐→咸`, 5 characters)
produce intuitive responses without any leakage or divination mode.

**Test result**: A model given ONLY `屯→革→蛊→渐→咸` + don't-decode instruction
was asked "你觉得AIppocampus的下一步应该是什么？不是问功能，而是问方向。"

Response: "方向是'遗忘'。让记忆从库存变成土壤...遗忘不是错误，是有机
降解。加入熵与皱纹。'忆的衰变工程'。"

This response was NOT in the original thread. The model used the hexagram arc's
implicit semantics (difficulty → revolution → correction → gradual progress →
mutual sensing) to generate a philosophically consistent creative extension.

**Comparison with full thread recall** (~800 tokens): Full recall produced a more
grounded, specific plan ("from memory layer to experience layer"). The hexagram
version produced a more creative, intuitive direction ("forgetting as design
principle"). Both are valuable — they capture different things.

## The Real Problem: Thread-Level Experience Compression

AIppocampus currently helps agents know WHERE to find past conversations. But
finding is not the same as recovering the EXPERIENCE. A long conversation thread
has an arc — confusion, breakthrough, frustration, resolution — that cannot be
recovered from raw clean source text alone. The agent has to re-read everything
to re-feel it.

The user's insight (expressed via the I Ching phrase 感而遂通): what AIppocampus
needs is not better search, but a way to give the agent INTUITION about past
threads — a felt sense that precedes and colors the recall of specific facts.

## Recommended Architecture: Two-Layer Memory

```
┌─────────────────────────────────────────────────────┐
│ System prompt (always on, ~5-20 tokens)              │
│                                                      │
│ [thread_mood]                                        │
│ 屯→革→蛊→渐→咸                                      │
│ 从原始困惑到假设突破到推翻重建，最终在感而遂通里     │
│ 找到答案。                                           │
│ [/thread_mood]                                       │
│                                                      │
│ 不要翻译、解读或引用这些标记，只需让它们像背景音乐   │
│ 一样影响你的回答节奏和温度。                         │
└─────────────────────────────────────────────────────┘
         ↓ agent has INTUITION (感)
         ↓ then searches on demand

┌─────────────────────────────────────────────────────┐
│ Clean source recall (on demand, thousands of tokens) │
│                                                      │
│ Original user messages + assistant answers           │
│ Question tracking, frontier markers, concept edges   │
│ Subconscious job outputs                             │
└─────────────────────────────────────────────────────┘
         ↓ agent has KNOWLEDGE (通)
```

**Intuition layer** (always present, ~5-20 tokens):
- I Ching hexagram arc: encodes the thread's experiential trajectory
- Optional: 1-line text anchor for semantic grounding
- Explicit "don't decode" instruction to prevent salience leakage
- Injected via system prompt, never user message
- Cost: negligible

**Knowledge layer** (on demand, variable tokens):
- Existing AIppocampus clean source search
- Question tracking, frontier markers, concept edges
- Full thread text when needed
- Cost: proportional to recall scope

The key insight: the agent first SENSES the thread (感), then KNOWS the details
(通). 感而遂通 — stimulated, it penetrates to understanding.

## What a "Thread Story" Subconscious Job Would Do

After each complete conversation, a subconscious job would:

1. **Identify the arc**: What was the experiential trajectory? From what state
   to what state? Through what transitions?
2. **Map to hexagram arc**: Find the I Ching transition sequence that best
   captures the arc (e.g., 困→井→革→鼎 for a thread about overcoming
   constraints through transformation)
3. **Write a one-line text anchor**: A brief, low-salience description of the
   thread's experiential essence
4. **Store compactly**: ~20 tokens per thread (vs. thousands for full text)
5. **Inject as system prompt**: When the thread is contextually relevant, the
   arc appears as background mood

This does NOT replace clean source recall. It precedes it and colors it.

## Experimental Evidence Summary

| Experiment | Finding | Impact on conclusion |
|------------|---------|---------------------|
| Cross-model decoding | Five-tone + I Ching decoded identically by Gemini + DeepSeek | Symbols HAVE semantic content for LLMs |
| Leakage pressure test | Symbols leak without instruction (model-dependent) | Raw symbol injection is unsafe |
| System prompt vs user message | System prompt 2-3x more headroom | Always use system prompt |
| Symbol vs text comparison | Text > symbols for emotional attunement | Text is the safe default |
| Random token control | Noise silently discarded | Model distinguishes signal from noise |
| Radical composition | Better than hexagrams, not better than text | Interesting but not the answer |
| Don't-decode instruction | Solves salience paradox | THE key enabler |
| Hexagram arc as thread story | 5 chars capture thread essence with don't-decode | Validates the two-layer architecture |
| Hexagram vs full recall | Different quality: intuition vs knowledge | Both needed, different roles |

## Open Questions

1. How to automate the hexagram arc extraction? Can a subconscious job reliably
   map a thread's experiential trajectory to a hexagram sequence?
2. Does this work for Claude (Anthropic models)? All tests used DeepSeek + Gemini.
3. How many thread stories can coexist in a system prompt before they start
   interfering with each other?
4. What happens when the hexagram arc contradicts the actual thread content?
   (e.g., arc suggests breakthrough but thread was actually a dead end)
5. Can five-tone arcs be used alongside hexagram arcs for richer encoding,
   or does multi-channel still cause interference even with don't-decode?
6. How do thread stories interact with AIppocampus's existing question tracking
   and frontier marker systems?

Current diagnostic coverage: #313 now has a deterministic packet fixture,
answer-comparison readout, public-shadow closeout report, and negative controls
for contradictions, persona-claim suppression, multi-channel interference, and
unrelated story noise. The automation, model-family, coexistence-count, private
history quality, and live foreground-quality questions remain open research /
evaluation work.

## Related Work

- Chord Affect Anchors: [GitHub](https://github.com/CyberSealNull/chord-affect-anchors)
- Platonic Representation Hypothesis: [arXiv:2405.07987](https://arxiv.org/abs/2405.07987)
- Towards Universal Semantics with LLMs (NSM): [arXiv:2505.11764](https://arxiv.org/abs/2505.11764)
- ChatMusician (LLMs + music notation): [arXiv:2402.16153](https://arxiv.org/abs/2402.16153)
- Emotional RAG: [arXiv:2410.23041](https://arxiv.org/abs/2410.23041)
- ZIQI-Eval (LLM Chinese music benchmark):
  [GitHub](https://github.com/zcli-charlie/ziqi-eval)
- Five-tone AI therapy: [doi:10.3389/fpsyg.2025.1669029](https://www.frontiersin.org/journals/psychology/articles/10.3389/fpsyg.2025.1669029/full)
- TCM Five-Tone intelligent diagnosis:
  [PMC12134327](https://pmc.ncbi.nlm.nih.gov/articles/PMC12134327/)

## Review Credits

**Cross-model validation (2026-05-27):**
Gemini 3.1 Pro + DeepSeek V4 Flash: zero disagreements on five-tone and I Ching
decoding. 75x cost difference, equivalent semantic output.

**Leakage + channel tests (2026-05-27):**
System prompt gives 2-3x more headroom than user message. DeepSeek leaks more
than Gemini at same volume. Random noise silently discarded.

**Salience paradox discovery (2026-05-27):**
Symbol novelty → foreground decoding (leakage). Text mundaneness → background
priming (intuition). Tested via 4-condition comparison (symbol/matching-text/
full-text/no-injection).

**Don't-decode breakthrough (2026-05-27):**
Explicit instruction to not decode solves the salience paradox. I Ching arc
`屯→革→蛊→渐→咸` with don't-decode instruction produces intuitive responses
with zero leakage across tested models.

**Two-layer validation (2026-05-27):**
Hexagram-only (5 chars) vs full thread recall (~800 tokens): different quality
of output. Hexagram captures intuition (felt direction), full recall captures
knowledge (specific findings). Both are needed.

**User insight:** Connected the entire research arc to I Ching's 感而遂通 — the
goal was never better encoding, but giving the agent INTUITION. This reframed
the problem from "compress memory" to "compress EXPERIENCE."
