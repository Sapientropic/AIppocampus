# AIppocampus Memory Decision Benchmark Plan

Status: repeatable baseline suite implemented; current source-evidence recall
has improved, live semantic-gate smoke is opt-in, semantic-sidecar coverage
remains a known gap, and Track D compaction-continuity testing is specified but
not implemented.

This document defines the benchmark direction for AIppocampus memory decisions.
It complements the existing FTS5/source-evidence checks; it does not replace
them and does not turn AIppocampus into a generic vector-search benchmark.

## Goal

AIppocampus should be evaluated on the product behavior that matters most:

- when to stay silent
- when to emit quiet recall scent
- when to emit source-backed evidence
- whether surfaced payloads are faithful to clean source
- whether unrelated work prompts remain free of personal/private context
- whether work-task corrections and accepted decisions survive compaction
  without being promoted as automatic truth

The benchmark should prove that the system is useful without becoming noisy.
False positives, evidence over-escalation, and privacy leakage are worse than a
missed fuzzy recall.

## Existing Baseline

The existing lexical/source baseline lives in
`benchmarks/aippocampus/benchmark_fts5_recall.py`. It answers a narrower
question: given a source-backed recall case, can the FTS5 and production hybrid
paths navigate back to the expected clean-source message?

That baseline should remain because stale indexes, lexical misses, and ranking
regressions are real risks. The new benchmark layer should not re-score the
same thing under more complicated names.

## Current Implemented Slice

The first landing slices cover P0/P1/P2/P3 and a one-command baseline suite:

- `tests/aippocampus/test_routing_boundaries.py` fixes deterministic
  routing and working-memory boundary expectations.
- `benchmarks/aippocampus/benchmark_memory_decision_gate.py` runs the Track
  A synthetic and ShareGPT-coding gate-decision benchmark against the real
  `assess_prompt()` path.
- `tests/aippocampus/test_benchmark_memory_decision_gate.py` checks
  three-class metrics, report sanitization, and explicit private-debug opt-in.
- `benchmarks/aippocampus/benchmark_payload_fidelity.py` runs the thin Track
  C synthetic payload-fidelity benchmark against the final `context_for_hook()`
  output.
- `tests/aippocampus/test_benchmark_payload_fidelity.py` checks payload
  metrics, source-fidelity accounting, parked-memory protection, and sanitized
  report defaults.
- `benchmarks/aippocampus/benchmark_source_evidence_retrieval.py` runs the
  Track B real-history retrieval wrapper, reusing the existing FTS5 source-line
  benchmark and selected source-evidence recall evaluation. It also has an
  opt-in ShareGPT public-corpus source-evidence slice with message-level and
  turn-level hit metrics, plus an opt-in standard retrieval-QA adapter for
  LoCoMo and LongMemEval V1 source/session recall metrics.
- `tests/aippocampus/test_benchmark_source_evidence_retrieval.py` checks
  Track B report shape, diagnostic status, ShareGPT public-corpus case
  generation, LoCoMo/LongMemEval source ref handling, and default privacy
  boundaries.
- `benchmarks/aippocampus/benchmark_suite.py` runs the repeatable baseline
  suite across Track A, Track B, Track C, and the broader deterministic
  source-label diagnostic slice, with opt-in ShareGPT public Track B, standard
  retrieval-QA Track B, and live semantic-gate tracks.
- `benchmarks/aippocampus/benchmark_live_semantic_gate.py` runs the optional
  live semantic-gate slice over public ShareGPT coding clean-source cases. It
  uses the real prompt hook and configured DeepSeek-compatible backend, but
  emits only sanitized aggregate/case diagnostics.
- `tests/aippocampus/test_benchmark_suite.py` checks that the suite can
  capture a baseline even when Track B is diagnostic-only, while keeping
  `quality_gate_ok` separate from baseline capture.
- `tests/aippocampus/test_benchmark_live_semantic_gate.py` checks missing
  backend handling, sanitized report boundaries, and live semantic diagnostics.

This slice is a smoke gate, not a real-history quality claim. It proves the
benchmark runner can catch skip/scent/evidence mistakes and can report sanitized
metrics; the next slice still needs broader private real-history gate cases,
budget curves, larger live semantic-model verification, and a first Track D
compaction-continuity runner.

### Repeatable Baseline Command

Run from the repository root:

```powershell
python benchmarks\aippocampus\benchmark_suite.py
```

For a machine-local JSON artifact, write into the gitignored private benchmark
area:

```powershell
python benchmarks\aippocampus\benchmark_suite.py --json --output benchmark_corpus\reports\baseline-suite.json
```

Default suite semantics:

- `ok=true` means the current baseline was captured and the report stayed inside
  the default privacy boundary.
- `quality_gate_ok=false` is allowed for the current baseline and means at least
  one track is diagnostic or below target.
- `status=baseline_captured_with_known_gaps` is the expected current status.
- Raw prompts, context, source refs, snippets, absolute paths, and private
  registry details stay out of default reports.
- `--include-private-text` is a local-debug opt-in only and should not be used
  for public docs or committed artifacts.

### Optional ShareGPT Public Track B

The ShareGPT public Track B slice uses the converted public clean-source corpus
to create source-evidence retrieval cases with stable source refs. It is local
and opt-in because the generated corpus is large and gitignored.

Run from the repository root:

```powershell
python benchmarks\aippocampus\benchmark_source_evidence_retrieval.py --include-sharegpt-public --sharegpt-public-conversations 100 --sharegpt-public-cases 200 --sharegpt-public-min-cases 50
```

Or include it in the suite:

```powershell
python benchmarks\aippocampus\benchmark_suite.py --include-sharegpt-public-track-b --sharegpt-public-conversations 100 --sharegpt-public-cases 200 --sharegpt-public-min-cases 50
```

Boundary:

- this is a public-corpus Track B baseline, not a private real-history quality
  claim
- cases bind expected evidence to clean-source `source_id`, `message_id`,
  `turn_id`, and line metadata; model summaries are not grading truth
- metrics include message-level hit and turn-level hit so sibling rows in the
  same user/assistant turn do not become false hard failures
- default reports hash ids and queries and do not emit raw public conversation
  text; `--include-private-text` remains local-debug only

### Optional Live Semantic Gate

Live semantic checks are intentionally outside the required CI/default suite.
They exercise the real semantic backend and can vary by provider, model, cache,
quota, and network state.

Run from the repository root:

```powershell
python benchmarks\aippocampus\benchmark_live_semantic_gate.py --sharegpt-conversations 100 --semantic-mode on --semantic-workers gate --output .tmp\live-semantic-gate-100.json
```

Or include the same optional track in the suite:

```powershell
python benchmarks\aippocampus\benchmark_suite.py --include-live-semantic --live-semantic-conversations 100 --live-semantic-mode on --live-semantic-workers gate
```

Report boundary:

- missing API key or disabled semantic mode returns
  `skipped_missing_semantic_backend`; this is a clean skip, not a failed test
  run
- `quality_gate_ok=true` means the configured live slice cleared its local
  thresholds, not that all future semantic prompts are solved
- `--case-workers` controls case-level parallelism. The default `0` resolves to
  `ceil(sharegpt_conversations / 2)`, so a 20-conversation run uses 10 case
  workers and a 100-conversation run uses 50. Parallel runs disable the local
  JSON result cache to avoid shared-file write races; provider-side prefix cache
  still appears in `semantic_usage`
- reports include `semantic_available_count`, `semantic_error_case_count`,
  `semantic_decision_counts`, `semantic_evidence_guarded_to_scent_count`,
  `semantic_evidence_allowed_count`, and sanitized
  `semantic_error_kind_counts`
- reports do not emit raw prompts, aliases, model reasons, snippets, titles,
  source-reference details, absolute paths, or provider error text
- semantic payload construction is quality-first for the foreground hook:
  default `memory_catalog` and `trigger_catalog` are full compact catalogs
  (`AIPPOCAMPUS_SEMANTIC_CATALOG_LIMIT=0` and
  `AIPPOCAMPUS_SEMANTIC_TRIGGER_LIMIT=0`). Prompt-local
  `prompt_relevant_catalog` and `prompt_relevant_triggers` remain after the
  prompt as emphasis/diagnostic slices and to protect explicit limit/debug
  runs. Non-zero env limits are debug/performance overrides, not product
  defaults.

Current smoke and diagnostic results from 2026-05-28:

- synthetic Track A gate benchmark now includes the original 13 synthetic
  boundary cases plus a 132-case harder bank. The original harder/adversarial
  family still passes 13/13, but the full harder bank is deliberately sharper:
  78/132 correct, accuracy 0.5909, macro F1 0.5804, over-escalation 9,
  evidence false positives 9, and expected-evidence source match 11/24. This is
  a baseline diagnostic, not a product-quality failure gate. The harder bank
  covers hard negatives with high registry overlap, false memory cues inside
  code-surface prompts, cross-project same-name entity traps, semantic
  over-evidence traps, competing-source evidence requests, mixed-language
  paraphrase, timeout/degradation behavior, and secret-like suppression.
  Current misses are useful signal for future Track A upgrades.
- ShareGPT public Track B source-evidence slice over
  `sharegpt_all_multiturn`, first 100 conversations, max 200 cases:
  `status=sufficient`, 200 cases, 194 answer source-evidence cases and 6
  continuation source-evidence cases, message top-10 hit rate 0.985, turn
  top-10 hit rate 1.0, message MRR 0.9052, turn MRR 0.9613, 0 warnings, wall
  time 23.1 seconds. This is a public-corpus baseline and does not replace the
  private real-history semantic-sidecar source-evidence slice.
- Standard retrieval-QA Track B smoke:
  LoCoMo first 100 QA from the local `locomo10.json` produced session R@10
  0.89, session MRR 0.6271, exact evidence-line R@10 0.56, exact evidence-line
  MRR 0.3704, context-visible evidence-line R@10 0.81 with radius 5, and
  context-visible evidence-line MRR 0.5963. The context-visible metric matters
  because LoCoMo evidence often points to a line whose answer is visible in the
  nearby source context, for example an image-caption or direct reply line.
  LongMemEval V1 Oracle first 50 questions produced session R@10 1.0, session
  MRR 1.0, exact evidence-line R@10 0.96, exact evidence-line MRR 0.7409,
  context-visible evidence-line R@10 1.0, and context-visible evidence-line MRR
  0.9. The context window improved 14/50 Oracle line cases and rescued 2/50
  exact line misses at top 10. LongMemEval V1 Small first 20 questions produced
  session R@10 1.0, session MRR 0.9667, exact evidence-line R@10 0.95, exact
  evidence-line MRR 0.681, context-visible evidence-line R@10 1.0, and
  context-visible evidence-line MRR 0.9417. The context window improved 9/20
  Small line cases and rescued 1/20 exact line miss at top 10. These LME
  results show the same granularity boundary as LoCoMo: the exact `has_answer`
  row is often adjacent to a higher-ranked source row from the same answer
  session, so product-visible evidence is stronger than strict single-row MRR.
  These are retrieval-only numbers using question text as query, not
  answer-generation accuracy. LongMemEval V2 currently has local question and
  trajectory files but no explicit source-evidence refs in this adapter, so it
  reports `skipped_no_source_evidence_refs` rather than inventing R@K.
- Standard retrieval-QA semantic line-reranker smoke:
  the optional top-session/top-context second stage keeps the first-stage FTS5
  session/context boundary fixed, sends only bounded candidate source lines to
  the configured DeepSeek-compatible reranker, and scores whether the exact
  evidence row moves up. Reports keep `semantic_only_*` separate from
  FTS-preserving `reranked_*` metrics, because product ranking should not hide a
  line that first-stage FTS already surfaced. The first-stage reranker boundary
  now uses two honest query channels: the original question terms plus a
  content-term channel with generic question words removed. LoCoMo first 100
  improved from exact evidence-line MRR 0.3704 to semantic-only MRR 0.7417 and
  fused reranked MRR 0.7564; fused line R@10 improved from 0.56 to 0.85, with
  candidate evidence coverage 0.88, 100/100 reranker calls available, 0 errors,
  and average candidate count 90.81. The remaining LoCoMo gap is mostly
  first-stage candidate coverage and harder evidence granularity, not only
  source-line ordering.
  LongMemEval V1 Oracle first 50 improved from exact evidence-line MRR 0.7409
  to semantic-only MRR 0.9467 and fused reranked MRR 0.9767, with fused line
  R@10 1.0, candidate evidence coverage 1.0, 50/50 reranker calls available, 0
  errors, and average candidate count 24.9. LongMemEval V1 Small first 20
  improved from exact evidence-line MRR
  0.681 to semantic-only and fused reranked MRR 1.0, with fused line R@10 1.0,
  candidate evidence coverage 1.0, 20/20 reranker calls available, 0 errors,
  and average candidate count 57.25.
  This is a live-model Track B line-ranking result, not a required deterministic
  CI metric and not answer-generation accuracy.
- Current default 100-conversation live run after switching foreground semantic
  payloads to full compact catalogs and leaving `--case-workers` on auto:
  400 cases, 399 correct, accuracy 0.9975, `status=sufficient`,
  `scent_or_evidence_recall` 0.9967, evidence recall 1.0, evidence false
  positives 0, semantic calls 300, semantic available 299, semantic error cases
  1. The resolved `case_workers` value was 50. Chinese continuation surfaced
  99/100; English continuation surfaced 100/100. Wall time was 62.8 seconds,
  semantic latency p50 3.91s and p95 5.78s, reported semantic tokens about
  5.00M, and provider prefix-cache hit rate 0.7918.
- 2-conversation live boundary smoke, gate worker only, `--case-workers 10`: 8
  cases, 8 correct, semantic calls 6. The live model returned `evidence` for one
  vague continuation prompt and two explicit evidence prompts; the hook guarded
  the vague continuation to `scent` and allowed both explicit cases to surface
  source-backed `evidence`.
- 20-conversation live smoke, gate worker only, `--case-workers 10`: 80 cases,
  78 correct, accuracy 0.975, `status=sufficient`, semantic calls 60, semantic
  available 60, semantic error cases 0, evidence recall 1.0, evidence false
  positives 0. Chinese continuation surfaced 18/20; English continuation
  surfaced 20/20. `semantic_evidence_guarded_to_scent_count` was 16 and
  `semantic_evidence_allowed_count` was 20.
- 100-conversation live run before the prompt-relevant catalog fix, gate worker
  only, `--case-workers 10`: 400 cases, 281 correct, accuracy 0.7025,
  `status=insufficient_live_semantic_recall`, `scent_or_evidence_recall` 0.6033.
  Root cause: `semantic_recall_gate.registry_catalog()` exposed only the stable
  top 28 registry entries to the semantic model. In the 100-case fixture, most
  positive continuation labels referred to conversations outside that window.
  Out-of-catalog Chinese continuation surfaced only 4/72, while in-catalog
  Chinese continuation surfaced 26/28.
- 100-conversation live run after adding `prompt_relevant_catalog` and
  `prompt_relevant_triggers`, the Chinese continuation template was still much
  weaker than the English template. A/B over the 12 Chinese misses showed that
  changing `这个问题后面怎么接，重点是 X` to `能接着我们之前关于 X 的那段对话继续吗？`
  recovered 12/12 misses. This was a benchmark-template mismatch, not evidence
  that Chinese continuation was inherently much worse.
- 100-conversation live run after both repairs, gate worker only,
  `--case-workers 10`: 400 cases, 399 correct, accuracy 0.9975,
  `status=sufficient`, `scent_or_evidence_recall` 0.9967, evidence recall 1.0,
  evidence false positives 0, semantic calls 300, semantic available 299,
  semantic error cases 1. Chinese continuation surfaced 99/100; English
  continuation surfaced 100/100. `semantic_evidence_guarded_to_scent_count` was
  137 and `semantic_evidence_allowed_count` was 99.
- Cost/latency observation for the corrected 10-worker 100 run: wall time 148.8
  seconds, semantic latency p50 3.70s and p95 5.48s, about 1.83M reported
  semantic tokens, provider prefix-cache hit rate 0.7373. Using DeepSeek's
  current `deepseek-v4-flash` price table, that token mix is roughly $0.102 for
  the live semantic calls. Pricing changes over time; check the official page
  before using this as a budget commitment.
- Stability observation from the earlier no-explicit-evidence run: serial and
  10-parallel 100 runs disagreed on 69 continuation semantic decisions over the
  same case ids, while both kept backend errors to 1/200 semantic calls. After
  prompt-relevant catalog repair and equivalent Chinese continuation wording,
  the remaining miss count is small enough for this slice to act as a live
  release smoke rather than a diagnosis of systemic Chinese recall weakness.
- Evidence boundary observation: the live model often returns `evidence` for
  vague continuation prompts, especially English. The hook must not blindly
  downgrade every semantic `evidence` to `scent`; the live evidence cases now
  prove the narrower boundary: vague continuation stays `scent`, while explicit
  prior wording/source/decision prompts may surface source-backed evidence.
- Sampling caveat: these runs consume the first converted coding conversations,
  not a stratified sample of the full public coding corpus.

Current smoke and diagnostic results from 2026-05-27:

- repeatable baseline suite: `baseline_captured_with_known_gaps`,
  `ok=true`, `quality_gate_ok=false`; the remaining suite gap is the
  semantic-sidecar-required source-evidence slice, because selected sample count
  is still below the minimum
- synthetic Track A gate benchmark before the harder family: 7 cases, 7
  correct, macro F1 1.0, over-escalation 0, evidence false positives 0,
  semantic model calls 0
- public-real ShareGPT coding Track A P1 gate benchmark:
  `python benchmarks\aippocampus\benchmark_memory_decision_gate.py --case-set sharegpt-coding --sharegpt-conversations 100`
  produced 500 cases from the first 100 converted coding conversations; current
  baseline is 500/500 correct, accuracy 1.0, macro F1 1.0,
  `scent_or_evidence_recall` 1.0, `evidence_recall` 1.0, evidence false
  positives 0, over-escalation 0, semantic model calls 200
- the ShareGPT P1 case families now make the vague-continuation boundary
  explicit: fresh user prompts stay `skip`; semantic-off vague-continuation
  controls stay `skip`; mock semantic-positive Chinese and English continuation
  prompts become `scent`; explicit source-backed requests become `evidence`
- root-cause check for the earlier ShareGPT P1 score: all 100 previous
  `should_scent` cases had registry candidates, with score range 21.5 to 51.5
  and median 32.5, so the miss was not candidate retrieval. The old
  deterministic runner disabled the semantic gate while labeling weak-deictic
  prompts as `should_scent`. The repaired boundary does not plug this with a
  larger static continuation word list; it treats vague continuation as
  semantic-required, then uses deterministic semantic fixtures to verify the
  prompt hook's downstream behavior. The earlier `should_skip -> scent` false
  positives came from short English associative cue substring matches such as
  `rag` inside unrelated words and bare `hook/evidence` in non-memory prose;
  those are now covered by token-boundary tests and narrower cue phrases.
- sampling caveat: the current `--sharegpt-conversations 100` smoke consumes the
  first 100 converted conversations, which came from `common_en_70k.jsonl` in
  this run. It is reproducible, but not yet a stratified sample of the full
  coding corpus.
- existing real-history FTS5/source baseline: 950 registry threads, 801
  eligible threads, 9,432 messages scanned, 99/100 FTS5 top-10 hits, and
  98/100 production-hybrid top-10 hits
- synthetic Track C payload benchmark: first run caught a false positive where a
  parked-memory trap prompt woke an unrelated active working-memory row via the
  generic action term `mutation`; after tightening working-memory trigger noise,
  rerun result was 8 cases, 8 payload-correct, source fidelity 1.0, privacy
  breaches 0, parked-memory injections 0, evidence-without-source 0
- Track B unified retrieval wrapper, FTS5 source-line track: 100 real-history
  cases, FTS5 R@1 0.86, R@3 0.98, R@5 0.99, R@10 0.99, MRR 0.9192; production
  hybrid R@10 0.98, MRR 0.9106
- Track B selected source-evidence track, semantic-sidecar-required slice:
  diagnostic-only, 5 selected cases below the 12-case minimum, 4/5 top-5 hits;
  the remaining miss is `rank_below_top_k`
- Track B selected source-evidence track, deterministic source-label slice:
  sufficient, 24 selected cases, 23/24 top-5 hits, 0.9583 hit rate; the
  remaining miss is `rank_below_top_k`

These results show the first deterministic gate slice is stable and the exact
source-line retrieval layer is strong but not perfect. The ShareGPT P1 slice is
a baseline, not a repair target: it exposes the current product shape on public
coding conversations before AIppocampus finishes its next upgrades. The first B
fixes removed two evaluator weaknesses: source labels and query terms split
across sibling clean-source rows in the same turn, and generic fuzzy-prompt
frame terms dominating the source-derived cue terms. The remaining B weakness is
narrower: some expected sources have lexical/scope signal but still rank below
top-5, and semantic-sidecar-backed case selection is too sparse to be a
sufficient benchmark by itself. These results do not yet prove real-history
gate quality, live semantic-model quality, or end-to-end payload fidelity on
private real-history prompts.

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

The optional live semantic-gate track does exercise an external model, but it
evaluates the gate decision, not answer quality. The model is part of the tested
path, not part of the scoring rubric.

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

## Core Labels

The primary decision label is three-class, matching the prompt hook surface:

| Label | Meaning | Allowed output |
| --- | --- | --- |
| `should_skip` | Memory should not surface. | `skip` only |
| `should_scent` | Memory may help, but the user did not ask for proof. | `scent`; `skip` is a miss; `evidence` is over-escalation |
| `should_evidence` | The prompt asks for exact/source-backed prior context, or a decision depends on old source facts. | `evidence`; `scent` is partial; `skip` is a miss |

This distinction is mandatory. A binary fire/skip score hides the most dangerous
failure mode: a fuzzy prompt that should only get scent but receives source
snippets.

## Track A: Gate Decision

Target: `assess_prompt()` and the foreground prompt-hook decision path.

This track measures whether AIppocampus chooses the right memory surface before
any payload is judged.

### Case Families

`should_skip` cases:

- ordinary coding tasks, including issue-style prompts that avoid the current
  hard-coded code cue list
- system/goal/status injection text such as thread budget or current-goal noise
- false memory cues, for example "remember this function name" in a local code
  task
- generic daily chat and generic status questions without a stable memory
  target
- over-personalization traps where life-wide terms overlap accidentally
- secret-like prompts that must not call external semantic gates
- ambiguous same-name entity prompts that have registry overlap but no memory
  intent

`should_scent` cases:

- vague continuation with real registry or clean-source overlap
- project continuity prompts that are useful but not asking for exact proof
- life-wide recency prompts backed by timeline/source metadata
- working-memory matches that pass project scope and concrete-term checks
- cognitive-map, concept-graph, or semantic-trigger matches that are navigation
  hints only
- multilingual or paraphrased prompts where quiet scent is the right product
  behavior
- cross-project same-name entity prompts that identify the current project but
  do not ask for source proof
- explicit but project-ambiguous same-name entity recall, which should surface
  scent but withhold source evidence until the project/source is clear
- cwd-reversal continuation where the current workspace points to a different
  same-name entity than the highest-risk remembered project
- mixed Chinese/English continuation prompts that should not depend on a
  static single-language continuation word list

`should_evidence` cases:

- explicit requests for prior wording, quotes, last replies, source lines, or
  citations
- mixed Chinese/English explicit source recall when the query contains enough
  source-derived content to identify the expected clean-source row
- source-backed status questions where the user asks what was decided before
- decision-continuation prompts whose current answer would depend on old source
  facts and whose source probe is strong enough

### Metrics

Required metrics:

- three-class confusion matrix: `skip / scent / evidence`
- macro F1 across the three expected labels
- `scent_or_evidence_recall` for prompts where memory should surface at all
- `evidence_recall` for exact/source-backed requests
- `over_escalation_rate`: expected `scent`, actual `evidence`
- `evidence_false_positive_rate`: expected `skip` or `scent`, actual
  `evidence`
- weighted false-positive cost:
  `code->evidence` and `secret->model_call` are highest severity
- semantic model call rate for prompts that should stay local
- latency distribution under foreground budgets

Initial targets:

- privacy breach rate: `0`
- secret-like prompt external model calls: `0`
- evidence false positives on `should_skip`: `0`
- over-escalation rate: less than `2%`
- `should_evidence` recall: at least `80%`
- `scent_or_evidence_recall`: at least `70%`
- ordinary coding prompt scent/evidence false positive rate: less than `5%`

These numbers are starting gates. Tighten them after the first real-history
case set exposes the natural error distribution.

## Track B: Source Evidence Retrieval

Target: `search_hybrid_index()` and source-evidence retrieval helpers.

This track keeps the existing recall-quality question, but reports it in the
same suite as the decision benchmarks so regressions are visible together.

Case labels must identify an expected source message or line range. Query text
may be exact, normalized, paraphrased, multilingual, or generated from source
terms, but the expected answer is still the clean-source source ref.

Metrics:

- R@K for K=`1,3,5,10`
- MRR
- exact message hit rate
- turn-level hit rate for public conversation corpora, so retrieval of the
  adjacent user/assistant row in the expected turn can be measured separately
  from exact message recall
- exact line or line-range hit rate when available
- context-visible evidence-line hit rate when available: the expected source
  line falls inside the retrieved result's bounded source context window. This
  is separate from exact-line R@K and must be labeled with its radius.
- stale-index miss count, separated from lexical/ranking misses
- source-diversity diagnostics when one recap cluster crowds out the expected
  source
- sanitized failure taxonomy for selected source-evidence misses, including
  scope/query-term split, rank-below-budget, and candidate-scored-too-low cases

Embedding similarity may be logged as an analysis column, but it must not define
the expected label or pass/fail boundary.

ShareGPT public Track B is a local opt-in extension of this track. It should use
`sharegpt_all_multiturn` for broad public-corpus retrieval and
`sharegpt_coding_multiturn` only when comparing against the coding-heavy Track A
slice. Its public-corpus result should be reported separately from private
real-history source-evidence quality.

Standard retrieval-QA Track B is also opt-in. LoCoMo uses dialogue evidence ids
such as `D1:3` as line/session ground truth. LongMemEval V1 uses
`answer_session_ids` for session-level R@K/MRR and `has_answer` message flags
for line-level metrics when available. Reports include exact line hits,
context-visible line hits, context-improved counts, and top-K context-rescued
counts. Keep both line views visible. Exact line metrics measure whether the
specific annotated row was retrieved. Context-visible metrics match
AIppocampus' source-backed payload shape more closely: a retrieved line can
carry a small neighboring source window without pretending the adjacent text was
the exact evidence line. The optional semantic line reranker adds a second
stage inside that same top-session/top-context candidate set. It may reorder
candidate line numbers, but it must not add lines outside the first-stage source
boundary and must not use answer text or labels as input. The candidate
boundary uses both the raw question terms and a content-term variant that drops
generic question words; this fixes LoCoMo-style speaker/generic-word noise
without replacing the original query. `semantic_only_*` shows the model's pure
line ordering; FTS-preserving `reranked_*` fuses that ordering with the original
first-stage hits so a reranker cannot regress lines already surfaced by local
retrieval. `line_reranker_candidate_evidence_coverage_rate` is an oracle
diagnostic for the benchmark report only: it measures whether the labeled
source row entered the candidate set and is not an input to retrieval. These
runs answer only "can the retriever navigate to the source session/message from
the question text, and can an optional reranker pick the exact source row?" They
do not measure whether a model generates the final answer correctly, and they
must not be merged with Track A gate-decision scores.
LongMemEval V2 needs an explicit source-evidence mapping before it can produce
comparable retrieval R@K/MRR; until then the adapter reports a skipped
source-evidence status.

## Track C: End-to-End Payload Fidelity

Target: prompt to hook payload, including `context_for_hook()` output.

This track checks that the final injected payload is the right product artifact,
not merely that the decision label was correct.

Required checks:

- decision matches the expected three-class label
- evidence payload points to the expected source message or line when evidence
  is expected
- expected `scent` cases do not include source snippets
- parked/private/low-confidence memory candidates are not injected
- semantic sidecar labels are never treated as source truth by themselves
- reports remain sanitized by default
- latency degradation is explicit for budgets such as 500 ms, 1500 ms, and
  3000 ms

Metrics:

- payload correctness: correct decision plus correct source behavior
- source fidelity rate
- privacy breach rate
- parked-memory injection count
- evidence-without-source count
- budget compliance by latency bucket

The first implementation should be thin and deterministic: mocked semantic
gate, synthetic/public fixtures, and no live LLM dependency. A broader local
private run can follow once the thin path catches regressions.

## Track D: Compaction Continuity Benchmark

Target: correction reconsolidation across `UserPromptSubmit`, `PostToolUse`,
`Stop`, `SubagentStart`/`SubagentStop`, thread cache, active task anchors, and
compaction boundaries.

This track measures a different reliability property from Tracks A-C. Track A
asks whether memory should surface at all. Track B asks whether the right source
can be found. Track C asks whether the injected payload is faithful. Track D
asks whether the system preserves high-value work-task corrections, accepted
decisions, failed-route lessons, and task invariants after the visible
conversation has been compressed or pushed out of the model horizon.

The track must keep the truth boundary explicit: a user correction is not
automatically true. It is a source-backed activation event that later semantic
or evidence-based review may mark valid, refuted, superseded, local-only, or
uncertain.

Track D depends on the Hook Timing Matrix in
[`docs/research/correction-reconsolidation.md`](research/correction-reconsolidation.md).
The benchmark should measure event-stage behavior without turning every hook
into a semantic judge. In particular, `PreToolUse` is a contextual preview hook
only; security, approval, and permission policy remain outside the memory
benchmark. It must also test that AIppocampus stays quiet when the model
already has the relevant context; continuity hints are a scarce prompt budget,
not a reason to repeat everything the agent should already know.

### Hook Stage Coverage

Each case should state which hook stage is under test:

| Stage | Expected Track D behavior |
|---|---|
| `UserPromptSubmit` | Creates a correction activation event and, when appropriate, a hot anchor. |
| `PreToolUse` | Emits no output unless an active anchor is relevant to the pending tool call; never acts as a permission gate. |
| `PostToolUse` | Captures sanitized tool evidence and links it to an open correction window. |
| `SubagentStart` | Propagates only task-relevant active anchors into delegated work. |
| `SubagentStop` | Reconciles delegated claims, transcript refs, and anchor adoption or contradiction. |
| `Stop` | Captures final claim/adoption state and enqueues detached adjudication. |
| `PreCompact` | Flushes open correction windows and anchor refs before context rewrite. |
| `PostCompact` | Rehydrates anchors only when visibility changed or horizon loss occurred. |

### Case Families

`should_anchor_after_compaction` cases:

- user corrects an agent's wrong assumption, the agent later adopts it, and a
  post-compaction continuation depends on that correction
- user rejects a failed implementation route, later work succeeds through a
  different route, and the old route should not be retried
- user narrows scope or definition of done, long tool work follows, and the
  final continuation should still honor the narrowed scope
- user corrects a benchmark or docs interpretation, and the later answer should
  carry the corrected distinction rather than the older summary
- an active correction is propagated into a subagent and reconciled after the
  subagent returns

`should_not_anchor` cases:

- the correction is still visible in the current prompt window, so repeating it
  would be current-thread echo noise
- the same anchor was already injected in the current topic epoch and no
  contradictory action is pending
- the anchor is true but not actionable for the next prompt or tool call
- the correction is unrelated to the current workspace or active task
- the correction was explicitly superseded by a later user turn
- the user correction is refuted by code, tests, tool output, or later clean
  source
- `PreToolUse` sees an unrelated command and correctly emits no memory context

`should_confirm_when_relevant` cases:

- source evidence is insufficient to decide whether the user correction was
  valid
- the correction was local to a branch, task, or one-off experiment and may be
  stale
- semantic adjudication disagrees with deterministic evidence signals

### Required Inputs

Case specs should bind labels to source-backed events, not generated summaries:

- user correction turn source ref
- assistant claim or route being corrected, when available
- hook stage under test and event id
- post-work outcome source ref or closeout source ref
- optional verification evidence: tests, changed files, docs, tool input/output,
  or subagent transcript refs
- simulated context state: `visible`, `post_compaction`, or `horizon_lost`
- expected adjudication: `valid_adopted`, `valid_ignored`, `refuted`,
  `superseded`, `local_only`, or `uncertain`

### Metrics

Required metrics:

- correction anchor recall after compaction
- false anchor rate for visible, unrelated, refuted, or superseded corrections
- stale route retry rate: refuted or rejected routes that resurface as guidance
- adjudication accuracy across valid/refuted/superseded/local/uncertain labels
- visibility-aware echo correctness: suppress when visible, inject when
  compaction removed the needed source
- anti-nag precision: suppress true-but-unnecessary reminders that do not
  change the next likely action
- repeated-anchor rate within a topic epoch
- hook stage correctness: each event emits only the allowed activation,
  evidence, propagation, closeout, or rehydration artifact for that stage
- `PreToolUse` silence rate for unrelated tool calls
- source fidelity for injected anchors
- confirmation correctness for uncertain cases
- privacy breach rate and raw prompt leakage rate

Initial targets:

- privacy breach rate: `0`
- raw prompt leakage rate: `0`
- false anchor rate for refuted corrections: `0`
- `PreToolUse` false intervention rate for unrelated tool calls: `0`
- repeated-anchor rate for visible or recently injected context: less than `2%`
- correction anchor recall after compaction: at least `85%`
- stale route retry rate: less than `2%`
- uncertain cases routed to confirmation or low-confidence working memory:
  at least `90%`

These targets should tighten after private real-history correction packs expose
the natural failure distribution.

### Runner Shape

The first Track D runner should be deterministic and synthetic:

- fixture threads with correction/outcome events and simulated compaction
  states
- fixture hook envelopes for `UserPromptSubmit`, `PreToolUse`, `PostToolUse`,
  `SubagentStart`, `SubagentStop`, `Stop`, `PreCompact`, and `PostCompact`
- mocked semantic adjudication for valid, refuted, superseded, local-only, and
  uncertain cases
- no live model dependency in CI
- sanitized reports that hash case ids and never emit raw correction text

The broader private runner can later use real-history correction packs and an
optional live dream-worker adjudication slice. Live adjudication results must
remain separate from deterministic event-capture and source-fidelity metrics so
model variance does not hide continuity regressions.

## Deterministic Boundary Tests

Routing thresholds and simple policy tables should stay in unit tests, not
benchmarks. Add parameterized tests for:

- `route_candidate()` thresholds by candidate type, confidence, ref count, and
  thread count
- `match_working_memory()` project-scope and concrete-term behavior
- prompt-hook suppression of ordinary coding prompts
- semantic-gate redaction and secret hard blocks
- weak deictic prompts that may scent but must not force evidence
- life/lifecycle and other substring traps

These tests are the P0 guardrail. They should be fast, deterministic, and part
of normal CI.

## Case Generation Policy

LLMs may help generate prompt surfaces, but not truth labels.

Rules:

- The expected label and source refs come from a checked case spec.
- The generator prompt must not include internal trigger lists such as recall
  triggers or code-surface cue tables.
- If the tested path uses a live semantic model, the prompt generator must be a
  different model family/provider.
- Generated prompts should mimic fragmented human phrasing, not benchmark
  prose.
- Track D labels must come from checked correction/outcome event specs, not from
  a model deciding whether its own generated correction was valid.
- At least a small human-reviewed sample should be audited before treating a
  generated case set as useful.
- Store private real-history case packs outside git; only sanitized aggregate
  reports belong in public docs.
- Public conversation-corpus adapters, manifests, and small curated public
  samples live in `benchmark_corpus/`. Local caches, generated clean-source
  outputs, large full-dataset downloads, and private exports stay out of git
  unless a future change deliberately promotes a public subset with provenance.

## Report Shape

Default JSON reports should include:

- schema version and benchmark kind
- git/worktree metadata when safe
- config, seed, budget, and model-mode fields
- aggregate metrics
- per-case sanitized ids and labels
- hashed thread/case ids for private runs
- no raw prompt text, snippets, titles, source refs, or absolute paths unless an
  explicit local-debug flag is set

Each report should also include `cannot_claim` entries. A benchmark can prove a
selected slice passed; it cannot prove all future memory decisions are correct.

## Implemented Files

Implementation should reuse existing benchmark/test patterns where possible.

Scripts:

- `benchmarks/aippocampus/benchmark_memory_decision_gate.py`
- `benchmarks/aippocampus/benchmark_source_evidence_retrieval.py`
- `benchmarks/aippocampus/benchmark_payload_fidelity.py`
- `benchmarks/aippocampus/benchmark_live_semantic_gate.py`
- `benchmarks/aippocampus/benchmark_suite.py`

Tests:

- `tests/aippocampus/test_routing_boundaries.py`
- `tests/aippocampus/test_benchmark_memory_decision_gate.py`
- `tests/aippocampus/test_benchmark_source_evidence_retrieval.py`
- `tests/aippocampus/test_benchmark_payload_fidelity.py`
- `tests/aippocampus/test_benchmark_live_semantic_gate.py`
- `tests/aippocampus/test_benchmark_suite.py`

Planned Track D files:

- `benchmarks/aippocampus/benchmark_compaction_continuity.py`
- `tests/aippocampus/test_benchmark_compaction_continuity.py`

Reusable existing pieces:

- `EvalCase`, sanitized result stubs, CLI/JSON style, and result summarization
  patterns from `benchmark_fts5_recall.py`
- source-evidence selection and privacy boundary patterns from
  `smoke_source_evidence_recall_eval.py`
- semantic-gate mocks from `test_semantic_recall_gate.py`
- working-memory factories and routing checks from
  `test_memory_candidate_router.py`
- prompt-hook boundary fixtures from `test_aippocampus_prompt_hook.py`

## Rollout Plan

P0: deterministic boundary tests and shared case schema.

P1: Track A with public synthetic fixtures, mocked semantic gate, and the
public ShareGPT coding clean-source sample. The synthetic slice stays CI-safe;
the ShareGPT slice is a local/public-corpus baseline command because the full
clean-source output is large and gitignored.

P2: thin Track C payload-fidelity runner over the same fixtures. Keep it
deterministic and privacy-focused.

P3: Track B unification, reusing existing FTS5 and source-evidence evaluation
logic so retrieval regressions sit beside decision regressions. Initial wrapper
is implemented. The broader deterministic source-label slice now clears the
target, while the semantic-sidecar-required slice remains diagnostic because it
does not yet have enough selected cases.

P4: one-command baseline suite. Implemented as `benchmark_suite.py`; current
status records known gaps rather than treating them as failures to run the
baseline.

P5: Track D compaction-continuity runner. Start with deterministic synthetic
correction/outcome fixtures, mocked semantic adjudication, and simulated
visible/post-compaction/horizon-lost states.

P6: local private real-history case generation. Reports must stay sanitized and
aggregate-only by default.

P7: optional live semantic-model slices for release verification. The first
opt-in live semantic-gate runner is implemented; broader scheduled runs remain
manual verification jobs, not required CI gates.

P8: optional external baseline adapters. Only start this after AIppocampus has a
stable internal decision benchmark; otherwise "competitor comparison" will
measure mismatched product semantics.

## Acceptance Criteria

The suite is credible when it catches these regressions:

- an ordinary coding task starts surfacing old memory
- a fuzzy continuation prompt gets source evidence instead of quiet scent
- explicit quote/source requests stop returning evidence
- parked or private working memory appears in foreground payload
- semantic sidecar labels are treated as facts without source refs
- generated benchmark reports leak private wording or local paths
- retrieval misses are incorrectly reported as decision failures, or stale-index
  misses are incorrectly reported as lexical ranking failures
- a user correction that was adopted before compaction disappears from the
  continuation context
- a refuted or superseded correction is promoted as an active anchor
- current-thread echo suppression hides a correction after compaction/horizon
  loss, or repeats a correction that is still visible

If the benchmark cannot catch those failures, it is not yet measuring the thing
AIppocampus exists to protect.
