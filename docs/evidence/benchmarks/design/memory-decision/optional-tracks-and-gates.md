# Memory Decision Optional Tracks And Gates

Role: extracted implemented-slice detail page.
Status: current detail under [`implemented-slices.md`](implemented-slices.md).

### Coding Decision-Shadow A-E Benchmark

Run the public deterministic coding-agent decision-shadow contract:

```powershell
python benchmarks\aippocampus\benchmark_coding_decision_shadow.py --json
```

This benchmark is narrower than the one-command baseline suite. It directly
exercises the coding continuity wedge: source-backed decision refs,
rejected-route warnings, compaction boundary preservation, historical decision
selection, and anti-nag suppression. Negative controls cover wrong-source
evidence, visible-source suppression, and stale authority. The default report
is sanitized and cannot claim private real-history behavior lift, full
code-index navigation quality, or live host intervention timing.


### Optional ShareGPT Public Track B

The ShareGPT public Track B slice uses the converted public clean-source corpus
to create source-evidence retrieval cases with stable source refs. It is local
and opt-in because the generated corpus is large and gitignored.

Run from the repository root:

```powershell
python benchmarks\aippocampus\benchmark_source_evidence_retrieval.py --include-sharegpt-public --sharegpt-public-conversations 100 --sharegpt-public-cases 200 --sharegpt-public-min-cases 50 --sharegpt-public-sampling-mode seeded-stratified --sharegpt-public-seed 218
```

Or include it in the suite:

```powershell
python benchmarks\aippocampus\benchmark_suite.py --include-sharegpt-public-track-b --sharegpt-public-conversations 100 --sharegpt-public-cases 200 --sharegpt-public-min-cases 50 --sharegpt-public-sampling-mode seeded-stratified --sharegpt-public-seed 218
```

Boundary:

- this is a public-corpus Track B baseline, not a private real-history quality
  claim
- cases bind expected evidence to clean-source `source_id`, `message_id`,
  `turn_id`, and line metadata; model summaries are not grading truth
- default public-corpus runs use seeded stratified conversation sampling and
  report seed, selected id hashes, eligible population count, skipped counts,
  and stratum counts; `--sharegpt-public-sampling-mode first-n` is only an
  explicit smoke/debug override and carries a cannot-claim boundary for full
  population sampling


### Optional Public Semantic Sidecar Track B

The public semantic-sidecar pilot first builds a bounded ShareGPT clean-source
registry subset, runs the live semantic labeler over a limited candidate set,
materializes reviewed `semantic-scope-labels.jsonl` rows with the existing
sidecar validator, then runs the selected source-evidence evaluator against that
subset. It is a separate `public_semantic_sidecar` track.

Run from the repository root:

```powershell
python benchmarks\aippocampus\benchmark_source_evidence_retrieval.py --allow-deterministic-labels --include-public-semantic-sidecar --public-semantic-output-dir .tmp\public-semantic-sidecar-20260529-wide --public-semantic-conversations 80 --public-semantic-max-messages 160 --public-semantic-max-candidates 48 --public-semantic-cases 40 --public-semantic-min-cases 3 --public-semantic-top-k 5 --public-semantic-max-tokens 16384 --public-semantic-timeout 90 --output .tmp\track-b-public-semantic-sidecar-wide-20260529.json
```

Boundary:

- this is a public semantic-sidecar pilot, not the private real-history
  `semantic-sidecar-required` metric
- reviewed means accepted by the source-ref/label-evidence sidecar validator;
  it does not mean human-reviewed
- generated subset, registry, sidecar, and live report stay local under `.tmp/`
  unless a curated public fixture is deliberately promoted later
- reports include `claim_level`, `minimum_empirical_case_count`, and
  `sample_size_warning`; passing top-k hits below that density stays a
  `diagnostic_pilot`, not an empirical benchmark claim
- reports include `anti_circular_controls`: the same bounded subset is evaluated
  with a no-sidecar deterministic/source-visible baseline and a wrong-message
  negative sidecar. The semantic-sidecar quality gate must not treat a passing
  wrong-message control as valid evidence; those controls are diagnostics, not
  a replacement for human-reviewed labels.
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
  `semantic_evidence_to_source_required_route_count`,
  `semantic_evidence_guarded_to_plain_scent_count`,
  `paid_semantic_hit_count`,
  `paid_semantic_hit_to_source_reopen_rate`,
  `manual_query_invention_after_paid_semantic_hit_count`,
  `useful_route_suppressed_count`, `all_scent_collapse_rate`,
  `semantic_evidence_allowed_count`, sanitized `semantic_error_kind_counts`,
  `issue_readouts.github_201.live_semantic_route_actionability`, and
  `issue_readouts.github_786.live_semantic_reopen_quality`
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

Current smoke and diagnostic results from 2026-05-30:

- synthetic Track A gate benchmark now includes the original 13 synthetic
  boundary cases plus public memory-pain fixtures and a 166-case harder bank.
  The harder bank currently reports 163/166 correct, accuracy 0.9819, macro F1
  0.9839, over-escalation 0, evidence false positives 0, evidence false
  negatives 0, and expected-evidence source match 37/37. This remains a
  deterministic routing contract, not a live semantic-model quality claim: the
  mocked `positive_scent`, `overeager_evidence`, `timeout`, and paraphrase
  fixtures validate hook routing and evidence guards after a semantic decision.
  The optional live semantic-gate benchmark owns whether the configured model
  would make that decision on real prompts. The harder bank now covers hard
  negatives with high registry overlap, false memory cues inside code-surface
  prompts, cross-project same-name entity traps, semantic over-evidence traps,
  competing-source evidence requests, mixed-language paraphrase,
  timeout/degradation behavior, secret-like suppression, explicit source-free
  evidence/scent twin contracts, four alias-ablation controls, and 30 natural
  oral prompts, including 12 should-evidence cases that catch under-recall on
  weak user wording such as "上次那个 bug 怎么说的来着". The alias-ablation
  controls run with benchmark-authored exact trigger aliases removed from the
  sidecar and report `exact_prompt_alias_violation_count=0`; they prove the
  fixture is not only rewarding prompts that repeat `external hippocampus`,
  `raw history`, or `source-backed` verbatim.
- Private real-history memory-pain prompt smoke now has a hash-only runner:
  `tools/aippocampus/smoke/smoke_memory_pain_prompt_hook.py`. On 2026-05-30,
  local deterministic mode over the installed real registry reported 8 cases,
  decisions `{evidence: 2, scent: 5, skip: 1}`, 6 evidence rows, 0 unsafe
  issues, and 0 positive misses. Foreground semantic-budget mode
  (`--semantic-gate on --semantic-timeout 20 --max-elapsed-ms 4300`) kept the
  same decisions and evidence count while surfacing 9 `read_timeout` buckets.
  Relaxed live semantic mode (`--max-elapsed-ms 0`) reported decisions
  `{evidence: 2, scent: 6}`, 6 evidence rows, 0 unsafe issues, 0 positive
  misses, and one `semantic_evidence_without_source_bridge` diagnostic for a
  deliberately vague cross-project prompt. The output is aggregate/hash-only and
  is a bounded real-history regression smoke, not a full private-history quality
  claim.
- ShareGPT public Track B source-evidence slice over
  `sharegpt_all_multiturn`, first 100 conversations, max 200 cases:
  `status=sufficient`, 200 cases, 194 answer source-evidence cases and 6
  continuation source-evidence cases, message top-10 hit rate 0.985, turn
  top-10 hit rate 1.0, message MRR 0.9052, turn MRR 0.9613, 0 warnings, wall
  time 23.1 seconds. This is a public-corpus baseline and does not replace the
  private real-history semantic-sidecar source-evidence slice.
- Public semantic-sidecar Track B pilot over `sharegpt_all_multiturn`,
  bounded to 80 conversations / 160 clean-source messages / 48 label candidates:
  `status=diagnostic_only`, `claim_level=diagnostic_pilot`, 3 reviewed
  `semantic-scope-labels.jsonl` rows, 3 selected public semantic-sidecar cases,
  3/3 top-5 hits, and `minimum_empirical_case_count=50`. The generated subset
  lives under `.tmp/public-semantic-sidecar-20260529-wide/` and the sanitized
  report is `.tmp/track-b-public-semantic-sidecar-wide-20260529.json`. This is
  deliberately reported as `public_semantic_sidecar`; it does not upgrade to an
  empirical public semantic-sidecar claim or replace the private real-history
  `semantic-sidecar-required` claim.
- Private real-history semantic-sidecar refresh:
  `smoke_semantic_scope_real_history.py --live --write-sidecars
  --full-candidate-coverage --full-candidate-source-turn-cap 160
  --candidate-batch-size 16 --samples-per-job 1` evaluated 414 selected
  candidate turns in 26 successful batches. Reviewed sidecar coverage grew from
  2 threads / 5 rows to 45 threads / 243 rows, with 108 timeline latest turns
  carrying semantic sidecar labels. The live jobs accepted 238 findings and 269
  labels with `weak_or_missing_evidence_label_count=0`. This is a bounded
  private slice, not a full-history semantic completeness claim.
- Private real-history Track B wrapper after that refresh:
  `.tmp/track-b-private-semantic-after-live-20260529.json` reports
  `status=sufficient`. The `semantic-sidecar-required` source-evidence track now
  has 100 selected cases, 97/100 top-5 hits, 0.97 hit rate, and 3 failures, all
  `rank_below_top_k` with extended ranks 6, 8, and 10. The same wrapper reports
  959 registry threads, 810 eligible threads, 9,699 messages scanned, 97/100
  FTS5 top-10 hits, and 98/100 production-hybrid top-10 hits.
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
  answer-generation accuracy. They are the current deterministic
  non-source-derived Track B arm because the query comes from public dataset
  questions rather than from the target source line. LongMemEval V2 now has a
  dedicated context-mapping pilot that inspects the public questions and
  trajectories without emitting raw text. The 2026-06-03 local pilot observed
  451 questions, 1,870 trajectories, 0 exact question/trajectory id matches,
  and 0 question or trajectory rows with gold evidence refs. The standard
  source-evidence adapter therefore still reports V2 as skipped rather than
  inventing R@K, while the V2 pilot reports only schema, checksum, join-key
  coverage, environment-pool ambiguity, and `cannot_claim` boundaries. The
  #1155 official-harness pilot decision is the separate answer/latency path:
  it adds a text-only Memory adapter contract and fixed-reader/evaluator plan,
  but does not turn V2 into a Track B source-evidence score.
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
- #201 / #786 live semantic route-actionability smoke on 2026-06-07: public
  checked-in local corpus converted to clean source, 4 conversations / 8 cases,
  DeepSeek-compatible live semantic route enabled with `--semantic-workers
  default`, `--case-workers 1`, and sanitized JSON output under `.tmp`. Result:
  `status=sufficient`, `quality_gate_ok=true`, 8/8 correct, semantic available
  4/4, evidence false positives 0, and `semantic_evidence_guarded_to_scent_count=3`.
  All 3 high-confidence paid/live semantic `evidence -> scent` continuation
  cases carried `source_required` / `reopenable_route`,
  `semantic_evidence_guarded_to_plain_scent_count=0`,
  `paid_semantic_hit_to_source_reopen_rate=1.0`,
  `manual_query_invention_after_paid_semantic_hit_count=0`,
  `all_scent_collapse_rate=0.0`, and
  `live_semantic_route_actionability=source_required_reopen_route`. This proves
  the source-reopen route projection and no-manual-query handoff for this public
  live smoke only. It pairs with the deterministic recall-navigation
  follow-through fixture for bounded-evidence-after-reopen behavior; the live
  smoke itself reports `bounded_evidence_after_semantic_reopen_rate` as not
  measured and does not claim all future semantic prompts or private-registry
  vague recall are solved.
- #786 semantic-reopen smoke on 2026-06-06: public checked-in local corpus
  converted to clean source, 4 conversations / 8 cases, DeepSeek-compatible
  live semantic route enabled with `--semantic-workers default`,
  `--case-workers 1`, and sanitized JSON output under `.tmp`. Result:
  `status=sufficient`, `quality_gate_ok=true`, 8/8 correct,
  semantic available 4/4, evidence false positives 0, and
  `semantic_evidence_guarded_to_scent_count=3`. All 3 guarded semantic
  `evidence -> scent` continuation cases now carried
  `source_required` / `reopenable_route`, with
  `semantic_evidence_guarded_to_plain_scent_count=0` and
  `live_semantic_reopen_quality=source_required_reopen_route`. This proves the
  source-reopen route projection for this public smoke only; it does not claim
  all future semantic prompts are correct.
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
- public-real ShareGPT coding Track A P1 gate benchmark now defaults to seeded
  stratified sampling:
  `python benchmarks\aippocampus\benchmark_memory_decision_gate.py --case-set sharegpt-coding --sharegpt-conversations 100 --sharegpt-sampling-mode seeded-stratified --sharegpt-seed 218`;
  reports include sampling seed, selected conversation id hashes, eligible
  population count, skipped counts, and stratum counts. The earlier 2026-05-29
  baseline used the first 100 converted coding conversations and was 500/500
  correct, accuracy 1.0, macro F1 1.0,
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
- historical sampling caveat: pre-#218 `--sharegpt-conversations 100` smoke
  reports consumed the first 100 converted conversations, which came from
  `common_en_70k.jsonl` in that run. Those older reports remain reproducible
  smoke evidence, but not stratified samples of the full coding corpus.
- existing real-history FTS5/source baseline after the 2026-05-29 rerun: 959
  registry threads, 810 eligible threads, 9,699 messages scanned, 97/100 FTS5
  top-10 hits, and 98/100 production-hybrid top-10 hits. This is a
  source-derived sparse-query sanity line for index health and stale-SQLite
  detection; by itself it does not claim natural user-query, paraphrase, or
  cross-language recall.
- synthetic Track C payload benchmark: first run caught a false positive where a
  parked-memory trap prompt woke an unrelated active working-memory row via the
  generic action term `mutation`; after tightening working-memory trigger noise,
  rerun result was 8 cases, 8 payload-correct, source fidelity 1.0, privacy
  breaches 0, parked-memory injections 0, evidence-without-source 0
- Track B unified retrieval wrapper, FTS5 source-line track: 100 real-history
  cases, FTS5 R@1 0.86, R@3 0.96, R@5 0.97, R@10 0.97, MRR 0.9073; production
  hybrid R@10 0.98, MRR 0.8898. In the unified report this track is classified
  as `source_derived_sparse`, and its hit rates must be reported beside, not
  averaged into, non-source-derived query arms.
- Track B selected source-evidence track, semantic-sidecar-required slice after
  the bounded 2026-05-29 private sidecar refresh:
  sufficient, 100 selected cases, 97/100 top-5 hits, 0.97 hit rate. The 3 misses
  were all `rank_below_top_k` with extended ranks 6, 8, and 10. This fixed the
  earlier sparse-pool problem without weakening the sidecar validator: accepted
  semantic labels still require exact message refs and per-label evidence.
  `benchmark_corpus/` can feed public Track B retrieval baselines, but it should
  not be counted into this private real-history slice unless it is reported as a
  separate bounded public semantic-sidecar track.
- #963 Track B selected private rerun and repair:
  a same-day pre-repair rerun on current main observed 100 selected cases,
  95/100 top-5 hits, and 5 sanitized misses. All five had the gold source in
  the raw candidate pool but below top-5, so the miss taxonomy was
  `candidate_pruned_before_verifier` / `candidate_generated_rank_below_top_k`,
  not candidate generation failure or source reopen failure. A public
  deterministic analogue now covers the actionable class where repeated use of
  one cue term outranks the correct source that covers several source-derived
  cues. After bounding repeat scoring and preferring distinct source-term
  coverage in the local `dynamic_source` diagnostic ranking path, the selected
  private rerun reports 100/100 top-5 hits, `top_k_hit_rate=1.0`,
  `failed_count=0`, and an empty sanitized taxonomy. This supersedes the
  97/100 selected-private Track B row only for this bounded slice.
- Track B public semantic-sidecar track:
  implemented as a separate optional wrapper track. Current 2026-05-29 pilot
  uses a bounded ShareGPT public registry subset with generated/reviewed
  `semantic-scope-labels.jsonl`; result is 3 reviewed sidecar rows, 3 selected
  cases, 3/3 top-5 hits, `claim_level=diagnostic_pilot`, and
  `minimum_empirical_case_count=50`. Keep this as a public pilot until the
  sidecar-reviewed public sample is materially larger; do not merge it into the
  private `semantic-sidecar-required` metric. Current runner reports also carry
  no-sidecar and wrong-message anti-circular controls, so a future larger pilot
  must show sidecar lift without a matching negative-control pass.
- Track B selected source-evidence track, deterministic source-label slice:
  sufficient, 100 selected cases, 97/100 top-5 hits, 0.97 hit rate. The
  remaining misses are 2 `rank_below_top_k` cases and 1
  `scope_term_split_across_expected_turn` case. The default selected-source
  sample is now 100 max / 50 min cases for this deterministic slice.

These results show the first deterministic gate slice is stable and the exact
source-line retrieval layer is strong but not perfect. The ShareGPT P1 slice is
a baseline, not a repair target: it exposes the current product shape on public
coding conversations before AIppocampus finishes its next upgrades. The first B
fixes removed two evaluator weaknesses: source labels and query terms split
across sibling clean-source rows in the same turn, and generic fuzzy-prompt
frame terms dominating the source-derived cue terms. The latest private
semantic-sidecar refresh removed the sparse-pool blocker, and #963 removed the
current selected-slice top-k pruning misses by preventing repeated single-cue
decoys from outranking broader source-term coverage. These results do not yet
prove real-history gate quality, live semantic-model quality, full semantic
completeness, or end-to-end payload fidelity on private real-history prompts.

- #400 LoCoMo answer-usefulness prototype:
  `benchmark_locomo_answer_usefulness.py` adds a second-stage public
  retrieval-QA scorer over LoCoMo. It keeps Track B source-evidence retrieval,
  context gathering, answer generation, source citation, and unsupported
  inference refusal as separate report layers. The runner consumes external
  answer predictions with retrieved context ids, answer text, citation ids, and
  refusal flags; it also ships a deterministic contract baseline for CI. Gold
  answers and gold evidence ids stay out of answer-generation inputs, while the
  deterministic judge can use them only for scoring. This is product-layer
  usefulness telemetry under fixed answer-model/evaluator settings, not a
  replacement for retrieval-only Track B metrics and not a SOTA or competitor
  comparison.
