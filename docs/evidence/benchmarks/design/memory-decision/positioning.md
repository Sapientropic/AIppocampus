# Memory Decision Benchmark Positioning

Role: extracted detail page.
Status: current detail under the canonical memory-decision benchmark entrypoint.

This file preserves detail split out of
[`../memory-decision-benchmark-plan.md`](../memory-decision-benchmark-plan.md).
Keep current reader routing and cross-track summary in the entrypoint; keep
deep methodology, runner notes, and implementation detail here.

## Non-Goals

- Do not use this as a MemPalace/CraniMem comparison unless explicit adapters
  and equivalent case runners exist.
- Do not treat embedding similarity as ground truth. Similarity scores may be
  reported as analysis, but labels must come from source-backed case specs.
- Do not let an LLM generate both the cases and the grading labels.
- Do not put live LLM calls in the required CI gate.
- Do not emit raw private text, snippets, absolute paths, or local registry
  details in benchmark reports by default.


## Benchmark Positioning: Retrieval Quality vs End-to-End QA

AIppocampus benchmarks measure retrieval and decision quality, not end-to-end
question-answering accuracy. This is an intentional design choice, not a gap.
AIppocampus is the agent's little hippocampus: it decides when old memory should
surface, selects the relevant scope, and retrieves source-backed evidence. The
main agent still owns reading that evidence, reasoning with the current task,
and generating the final answer.

The dominant industry benchmarks (LoCoMo LLM-as-Judge, LongMemEval aggregate
accuracy) score the product of two independent capabilities:

1.  **Memory retrieval**: can the system find the right source?
2.  **LLM reasoning**: given the retrieved source, can the model produce the
    correct answer?

These two factors are conflated in a single percentage. Swapping the underlying
LLM changes the score without any change to the memory system itself. Published
evidence of this conflation:

- Mem0 LongMemEval: 93.4% (self-test, unspecified model) vs 49%
  (Vectorize.io independent evaluation with different model/prompt). The 44-point
  gap is a model and methodology artifact, not a memory quality difference.
- Mem0 extraction-model ablation on LongMemEval: GPT-5 scores 91.0%, Llama 4
  Maverick scores 88.6%. Same memory system, same data, 2.4-point spread from
  model choice alone.
- Exabase M-1 (96.4% LongMemEval) uses Gemini Flash. Their own analysis states
  "retrieval architecture drove performance independent of model strength," yet
  the headline number still depends on which model generates the final answer.

Because of this conflation, leaderboard rankings primarily compare
memory-system-and-LLM combinations, not memory systems in isolation. A
higher-ranked system may simply be using a stronger answer-generation model, with
no clear way to attribute the improvement.

### What AIppocampus measures instead

AIppocampus benchmarks decompose memory quality into orthogonal layers that do
not depend on answer-generation model choice:

| Layer | Metric | What it measures | Model-dependent? |
|-------|--------|-----------------|------------------|
| Track A: Gate Decision | skip/scent/evidence accuracy, macro F1, over-escalation rate | Whether the system chooses the right memory surface | No (deterministic gate + optional semantic, scored against source labels) |
| Track B: Retrieval | R@K, MRR, message/turn hit rate, context-visible hit rate | Whether the system finds the correct source row | No (retrieval-only, no answer generation) |
| Track C: Payload Fidelity | source fidelity, privacy breach rate, parked-memory injection count | Whether the final payload is correct and safe | No (synthetic fixtures, mocked semantic gate) |
| Track D: Compaction Continuity | correction retention, adjudication status, stale-anchor suppression | Whether work-task corrections survive compaction without becoming false memory | Mixed: deterministic event checks plus optional semantic adjudication, scored against source labels |
| Track S: Semantic Robustness Diagnostics | perturbation stability, retrieval invariance, hard-negative suppression | Whether Track A/B behavior remains stable under semantic rewrites and negative constraints | No by default; optional proxy/vector diagnostics are explicit and diagnostic-only |

The optional live semantic-gate track does exercise an external model, but it
evaluates the gate decision, not answer quality. The model is part of the tested
path, not part of the scoring rubric.

### Track S: no-live-judge semantic robustness

`benchmark_semantic_robustness.py` is the Track S facade for #747. It reuses
Track A prompt-hook fixtures and Track B local source-retrieval helpers, then
reports the following diagnostics separately:

- S1 gate robustness under paraphrase, register shift, typo, syntax rewrite,
  and current-task distractor prompts.
- S2 retrieval invariance for equivalent but lexically distant public-safe
  query bundles.
- S3 hard-negative and explicit-negation suppression.
- S4 offline proxy alignment only when a local reviewed model is explicitly
  configured.
- S5 representation-space health only when a local embedding index is supplied.

Track S is diagnostic evidence, not source truth. Do not average it into Track
A/B/C/D quality scores, do not use proxy-model agreement as ground truth, and
do not require live LLM calls in the default path. See
[`../../semantic-robustness-track-s.md`](../../semantic-robustness-track-s.md) for the
current runner boundary.

### When end-to-end QA benchmarks are appropriate

End-to-end LLM-as-Judge benchmarks are useful for product-level comparisons when:

- the product is a complete conversational agent, not a memory layer
- the evaluation goal is to compare full-stack systems (memory + model + prompt)
  under identical conditions, including the same LLM, the same judge, and the
  same prompt template
- the benchmark controls for model choice by running all systems with the same
  answer-generation model and the same evaluation model

AIppocampus is a memory layer, not a full-stack agent. Adding LLM-as-Judge
scores would measure something AIppocampus does not own. If a fair head-to-head
comparison is needed, the right experiment is: same LLM, same prompt, swap only
the memory system, measure answer quality delta. That delta, not the absolute
score, is the memory system's contribution.

### Summary

AIppocampus benchmark metrics are retrieval and decision metrics. They are
comparable across any system willing to report the same retrieval-only numbers
(R@K, MRR, decision accuracy) on the same datasets. They are not directly
comparable to LoCoMo or LongMemEval aggregate accuracy percentages, because
those measure a different thing. This distinction should be stated explicitly
in any public benchmark report or comparison.
