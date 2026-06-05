# Benchmark Corpus

This folder holds public conversation-corpus inputs and converters for
AIppocampus benchmark work.

For the cross-repository map of benchmark runners, smoke evidence, and dated
records, start with [`docs/evidence/benchmark-evidence-map.md`](../docs/evidence/benchmark-evidence-map.md).

## Contents

- `convert_to_aippocampus.py` converts public conversation datasets into
  AIppocampus clean-source `messages.jsonl` and `turns.jsonl`.
- `public_longitudinal_users/` contains the checked-in public pseudo-user
  scoring-contract smoke for coding implicit-knowledge continuity. It keeps
  the report and prediction contract public-safe while the flagship track moves
  toward VCS-derived hard future events for recall measurement.
- `public_multimodal_corpus/` contains the checked-in synthetic public-safe
  corpus-style multimodal retrieval fixture for #531. It is inspired by the
  ATM-Bench staged-corpus shape, but it is not an ATM-Bench adapter or a
  conversational media-upload recall benchmark.
- `multimodal_niah_evidence_pool/` contains the checked-in synthetic
  public-safe NIAH-style evidence-pool fixture for #533. It reuses the
  corpus-style multimodal source fixture, but removes retrieval from the
  measurement by supplying fixed ground-truth-plus-distractor pools.
- `conversational_media_ingest/` contains the checked-in synthetic public-safe
  fixture for #532. It models media the user sends or selects inside a
  conversation, where the user's wording around the upload is also source
  evidence.
- `field_continuity/` contains the checked-in synthetic public-safe fixture for
  #454. It turns Discussion #428 magic-moment field reports into scenario
  families, negative controls, and hash/aggregate-only private seed reporting
  rules without committing raw prompts, raw source snippets, or local paths.
- `e2e50_silent_constraint/` contains the checked-in synthetic public-safe
  fixture for the #279 annotated case-pack scorer scaffold. It exercises
  silent constraint survival, known-bad route avoidance, transient concern
  extinction, superseded currentness, and source reopen before risky action
  without committing private clean-source text, local paths, or raw behavior
  traces.
- `segmented_merge_policy/` contains the checked-in synthetic public-safe
  fixture for #375. It calibrates segmented-search merge behavior over
  source-ref-shaped hits without committing private thread text.
- `testdata_wildchat.jsonl` is a tiny checked-in fixture in WildChat-like JSONL
  shape, useful for smoke-testing the converter without network access.

Supported converter sources:

- `allenai/WildChat-4.8M` (`odc-by`)
- `tucnguyen/ShareChat` (`CC BY-NC 4.0`, gated access; keep attribution to
  the original dataset)
- ShareGPT-style JSONL dumps with `{human, assistant}` turn-pair arrays
- local JSONL files with `conversation` or `conversations` message arrays

`sharegpt_manifest.json` records the current clean-source dataset sizes and the
intended benchmark use for the locally generated ShareGPT outputs.

`longmemeval_manifest.json` records the official LongMemEval cleaned V1 split
files, Hugging Face LFS content hashes, V2 context-mapping pilot metadata,
runner entrypoints, and claim boundaries. The corresponding evidence page is
[`docs/evidence/benchmarks/longmemeval.md`](../docs/evidence/benchmarks/longmemeval.md).

`locomo_manifest.json` records the LoCoMo public long-conversation
same-dialogue control, its local-file policy, and the evidence-retrieval
runner that treats each LoCoMo sample as one within-sample retrieval task.

`memoryagentbench_manifest.json` records the official MemoryAgentBench sources,
MIT license, split metadata, local ignored artifact policy, and deterministic
metadata/case-pack smoke runner. It does not make a MemoryAgentBench score
claim.

## Usage

Run a local smoke conversion:

```powershell
python benchmark_corpus\convert_to_aippocampus.py --source local --input benchmark_corpus\testdata_wildchat.jsonl --output .tmp\benchmark-corpus-smoke
```

Run a public dataset stream:

```powershell
python benchmark_corpus\convert_to_aippocampus.py --source wildchat --max-convs 200 --output .tmp\wildchat-clean-source
```

`wildchat` and `sharechat` streaming use Hugging Face `datasets`. If it is not
installed, the converter exits with a targeted optional-dependency diagnostic
instead of a Python traceback; local and ShareGPT JSONL sources remain stdlib
paths.

Regenerate the current ShareGPT clean-source corpora from local public JSONL
inputs:

```powershell
python benchmark_corpus\convert_to_aippocampus.py --source sharegpt --input benchmark_corpus\sharegpt_raw --min-turns 2 --output benchmark_corpus\output\sharegpt_all_multiturn
python benchmark_corpus\convert_to_aippocampus.py --source sharegpt --input benchmark_corpus\sharegpt_raw --min-turns 2 --coding-only --output benchmark_corpus\output\sharegpt_coding_multiturn
```

Run the Track A P1 gate-decision baseline over the coding corpus:

```powershell
python benchmarks\aippocampus\benchmark_memory_decision_gate.py --case-set sharegpt-coding --sharegpt-conversations 100 --sharegpt-sampling-mode seeded-stratified --sharegpt-seed 218 --output benchmark_corpus\reports\sharegpt-p1-gate-100.json
```

The ShareGPT Track A and Track B public-corpus entrypoints default to
deterministic seeded stratified sampling. Reports include the seed, selected
conversation id hashes, eligible population count, skipped counts, and stratum
counts by source-file hash, category bucket, language bucket, turn bucket, and
coding bucket. Use `--sharegpt-sampling-mode first-n` only for a cheap
gate-decision smoke/debug run; first-N reports explicitly carry a
`seeded_stratified_population_sampling` cannot-claim boundary.

Run the fresh-clone public-fast benchmark profile:

```powershell
python benchmarks\aippocampus\benchmark_suite.py --profile public-fast --json
```

This runs deterministic Track A/C/D slices only. It intentionally skips private
registry data, live semantic providers, Track B retrieval quality, and large
external corpus downloads; those omitted surfaces appear in `cannot_claim`.

Run the public-safe segmented-search merge policy calibration:

```powershell
python benchmarks\aippocampus\benchmark_segmented_merge_policy.py --json
```

This #375 fixture checks cross-segment diversity, adjacent-turn pairing,
duplicate nearby recap suppression, and stale/superseded currentness for
`SEGMENT_MERGE_POLICY`. It is diagnostic policy calibration, not real
long-thread recall quality or source-evidence retrieval proof. The report owner
is
[`docs/evidence/benchmarks/segmented-merge-policy-fixture-report.md`](../docs/evidence/benchmarks/segmented-merge-policy-fixture-report.md).

Run the public-safe Field Continuity / magic-moment reproducibility contract:

```powershell
python benchmarks\aippocampus\benchmark_field_continuity.py --json
```

This #454 fixture covers fresh/projectless familiarity, multilingual route
correction, external-state restraint, long-thread fuzzy self-reference, and
cross-thread prompt/tool-failure provenance as scenario contracts. It does not
claim live quality, private real-history recall quality, or foreground-hook-only
sufficiency. The report owner is
[`docs/evidence/benchmarks/field-continuity-fixture-report.md`](../docs/evidence/benchmarks/field-continuity-fixture-report.md).

Run the deterministic coding decision-shadow A-E contract:

```powershell
python benchmarks\aippocampus\benchmark_coding_decision_shadow.py --json
```

This public-safe runner checks original source refs, rejected-route warnings,
compaction boundary preservation, relevant decision selection, and anti-nag
suppression. It is a synthetic contract, not private real-history lift evidence.

Run the public-safe E2E50 silent-constraint case-pack scorer scaffold:

```powershell
python benchmarks\aippocampus\benchmark_e2e50_silent_constraint.py --json
```

This #279 scaffold scores hash/count-only annotated behavior-code cases and
keeps `quality_gate_ok=false` until source-reviewed private gold/calibration
cases become a representative E2E50 sample under the shared methodology.

Run the public-safe multimodal corpus-style retrieval contract:

```powershell
python benchmarks\aippocampus\benchmark_multimodal_corpus_retrieval.py --json
python benchmarks\aippocampus\benchmark_multimodal_corpus_retrieval.py --raw-media-mode deterministic_fixture --json
```

This fixture has synthetic image, video-frame, email/message, receipt, invoice,
and calendar/location sources plus captions, OCR, object tags, thumbnail or
embedding hints, and schema rows as derived artifacts. Derived artifacts are
navigation only; the runner scores source reopen, conflict handling,
cross-modal join, unsupported visual abstention, and retrieval recall@3. It
does not claim ATM-Bench Hard support, live vision quality, conversational
media-upload recall, full-device indexing, or product privacy behavior. The
report owner is
[`docs/evidence/benchmarks/multimodal-corpus-fixture-report.md`](../docs/evidence/benchmarks/multimodal-corpus-fixture-report.md).

Run the public-safe conversational media-ingest recall contract:

```powershell
python benchmarks\aippocampus\benchmark_conversational_media_ingest_recall.py --json
```

This fixture is the conversational counterpart to staged corpus QA: media
anchors are attached to user turns, and the user's wording can help resolve
personal references. Text around an upload still cannot count as visual proof
without reopening the media source. The runner scores personal-reference
resolution, visual source reopen, text-hint leakage, stale-label correction,
unsupported visual claims, and hidden durable writes. It does not claim
background scanning, cross-domain reuse, live vision quality, face-recognition
identity graphs, or product privacy behavior. The report owner is
[`docs/evidence/benchmarks/conversational-media-ingest-fixture-report.md`](../docs/evidence/benchmarks/conversational-media-ingest-fixture-report.md).

Run the public-safe NIAH-style multimodal evidence-pool contract:

```powershell
python benchmarks\aippocampus\benchmark_multimodal_niah_evidence_pool.py --json
python benchmarks\aippocampus\benchmark_multimodal_niah_evidence_pool.py --source-reopen-mode deterministic_fixture --json
```

This fixture supplies fixed evidence pools that contain all ground-truth source
ids plus distractors, so it scores answer synthesis, source selection,
source-anchor citation, conflict handling, and abstention under a supplied
pool. It deliberately includes one stale/conflicting-source failure even though
the correct source is present, proving the slice catches reasoning failures
rather than only retrieval misses. It does not claim retrieval quality,
ATM-Bench Hard support or score, live vision quality, conversational
media-upload recall, or product privacy behavior. The report owner is
[`docs/evidence/benchmarks/multimodal-niah-evidence-pool-report.md`](../docs/evidence/benchmarks/multimodal-niah-evidence-pool-report.md).

Run the public longitudinal pseudo-user contract smoke for coding implicit
knowledge:

```powershell
python benchmarks\aippocampus\benchmark_public_longitudinal_users.py --json
python benchmarks\aippocampus\benchmark_public_longitudinal_users.py --predictions .tmp\public-longitudinal-predictions.jsonl --json
```

This is the public scoring-contract smoke for rejected routes, tacit
constraints, workaround rationale, stale-assumption corrections, reopen
conditions, and anti-drift negatives. The fixture is synthetic, source-labeled,
and public-safe; it does not claim private real-history quality, real same-user
identity, or recall over a complete future window. The flagship next slice
should use VCS-derived hard events such as PR merge/reject, issue reopen,
commit revert, patchset supersession, and SATD/workaround removal. See
[`docs/evidence/benchmarks/public-longitudinal-users.md`](../docs/evidence/benchmarks/public-longitudinal-users.md)
for the methodology and claim boundary. The latest dated local measurement is
recorded in
[`docs/evidence/benchmarks/public-longitudinal-users-measurement-2026-05-31.md`](../docs/evidence/benchmarks/public-longitudinal-users-measurement-2026-05-31.md).

Run the LoCoMo same-conversation evidence control:

```powershell
New-Item -ItemType Directory -Force benchmark_corpus\locomo | Out-Null
Invoke-WebRequest https://raw.githubusercontent.com/snap-research/locomo/main/data/locomo10.json -OutFile benchmark_corpus\locomo\locomo10.json
python benchmarks\aippocampus\benchmark_locomo_public_users.py --max-samples 2 --max-cases 20 --json
python benchmarks\aippocampus\benchmark_locomo_public_users.py --predictions .tmp\locomo-evidence-predictions.jsonl --json
```

For an external system run, first export a local case pack and a prediction
template:

```powershell
python benchmarks\aippocampus\benchmark_locomo_public_users.py --case-pack-output .tmp\locomo-case-pack.json --prediction-template-output .tmp\locomo-predictions.jsonl --json
```

The case pack contains LoCoMo dialogue and question text, but no answers or
gold evidence ids. Keep it local under `.tmp/` or another ignored directory.
Fill the prediction template with retrieved dialogue ids, then score it with
`--predictions`.

Prediction rows can use either `evidence_ids` or `source_event_ids`:

```json
{"case_id":"locomo:conv-26:qa:0001","evidence_ids":["D1:3"]}
```

This runner scores source-turn retrieval against LoCoMo QA evidence dialogue
ids inside the same conversation sample. The raw LoCoMo file remains
local/ignored under the upstream CC BY-NC 4.0 license; reports are sanitized by
default and do not emit dialogue, question, or answer text. Use it as a
long-dialogue retrieval control, not as proof of cross-conversation user memory;
keep temporal override, project contamination, coding tacit-constraint, and
rejected-route claims on the VCS / rollout hard-event track.

Run the #400 LoCoMo answer-usefulness prototype after a system has produced
answers from a bounded local case pack:

```powershell
python benchmarks\aippocampus\benchmark_locomo_answer_usefulness.py --max-samples 2 --max-cases 20 --json
python benchmarks\aippocampus\benchmark_locomo_answer_usefulness.py --predictions .tmp\locomo-answer-predictions.jsonl --answer-model <fixed-answer-model-name> --json
```

Prediction rows are intentionally second-stage: they include retrieved context
ids, answer text, citation ids, and refusal, but the case pack still keeps gold
answers and gold evidence ids out of the answer-generation input:

```json
{"case_id":"locomo:conv-26:qa:0001","arm":"retrieved_context","retrieved_evidence_ids":["D1:3"],"answer_text":"...","citation_ids":["D1:3"],"refused":false}
```

The report keeps `source_evidence_retrieval`, `context_gathering`,
`answer_generation`, `source_citation`, and `unsupported_inference_refusal`
metrics side by side. It is a prototype product-layer scorer with a fixed
answer model / deterministic evaluator boundary, not a replacement for Track B
retrieval-only metrics and not a LoCoMo leaderboard claim.

Run the VCS future-event recall scaffold:

```powershell
python benchmarks\aippocampus\benchmark_vcs_future_event_recall.py --json
python benchmarks\aippocampus\benchmark_vcs_future_event_recall.py --baseline empty --json
```

This runner scores over every hard event in the future window. Missing a
flag-worthy PR/revert/patchset/SATD event is a false negative, so silent Dream
systems cannot pass by avoiding false activations.

The same runner can score agent-rollout behavior traces, where the hard events
are failed tool calls, failed tests, reverted edits, or abandoned routes rather
than PR outcomes:

```powershell
python benchmarks\aippocampus\benchmark_vcs_future_event_recall.py --dataset benchmark_corpus\public_longitudinal_users\rollout_behavior_events_v1.jsonl --json
```

In that fixture, assistant narration is not accepted as gold support for a
rejected route unless there is deterministic behavior evidence behind it.

For public VCS reports, also score a closed-book ablation:

```powershell
python benchmarks\aippocampus\benchmark_vcs_future_event_recall.py --predictions .tmp\vcs-source-window.jsonl --closed-book-predictions .tmp\vcs-closed-book.jsonl --json
```

The source-over-closed-book lift is the first contamination check. If closed
book matches the source-window run, the score is likely public-outcome memory,
not source-backed recovery.

Build a local fixture from already-curated public event-link rows:

```powershell
python benchmarks\aippocampus\build_vcs_future_event_fixture.py --input .tmp\public-vcs-links.jsonl --output .tmp\vcs-future-events-built.jsonl --json
python benchmarks\aippocampus\benchmark_vcs_future_event_recall.py --dataset .tmp\vcs-future-events-built.jsonl --allow-non-cc0-dataset --json
```

The builder is intentionally only an adapter. It does not download raw public
datasets or license them for redistribution.

For agent-rollout traces, use clean-source `events.jsonl` as the past behavior
source and provide a separate curated link file:

```powershell
python skills\aippocampus\scripts\build_clean_source.py --cwd . --output-dir .tmp\clean-source --json
python benchmarks\aippocampus\build_vcs_future_event_fixture.py --clean-source-events .tmp\clean-source\events.jsonl --links .tmp\rollout-event-links.jsonl --output .tmp\rollout-future-events.jsonl --allow-non-cc0-output --json
```

Run the optional public-corpus Track B source-evidence baseline over the broad
ShareGPT corpus:

```powershell
python benchmarks\aippocampus\benchmark_source_evidence_retrieval.py --fts5-cases 1 --fts5-min-cases 1 --source-max-cases 1 --source-min-cases 1 --allow-deterministic-labels --json
```

This portable wiring smoke is the second-user-friendly Track B command. It can
run without prebuilt semantic-sidecar selected cases and should keep
`deterministic_label_fallback_is_not_semantic_sidecar_evidence` in
`cannot_claim`. To validate semantic-sidecar quality, rerun without
`--allow-deterministic-labels` only after the local registry has eligible
`semantic-scope-labels.jsonl` sidecar rows; `insufficient_selected_cases` is a
coverage/prep diagnostic, not a refactor failure.

```powershell
python benchmarks\aippocampus\benchmark_source_evidence_retrieval.py --include-sharegpt-public --sharegpt-public-conversations 100 --sharegpt-public-cases 200 --sharegpt-public-min-cases 50 --sharegpt-public-sampling-mode seeded-stratified --sharegpt-public-seed 218 --output benchmark_corpus\reports\sharegpt-track-b-public-100.json
```

This Track B slice reports message-level and turn-level source hits. It is a
source-derived public-corpus retrieval baseline, not a private real-history
source-evidence quality or natural user-query recall claim. Use
`--sharegpt-public-sampling-mode first-n` only for a cheap Track B smoke/debug
run; first-N reports do not claim full-population seeded stratified sampling.

Do not count the generated ShareGPT clean-source output as
`semantic-sidecar-required` by itself. The public corpus currently contains
`messages.jsonl` and `turns.jsonl`; it does not ship reviewed
`semantic-scope-labels.jsonl` sidecars. To use a public corpus for a semantic
sidecar slice, first materialize source-backed semantic sidecars for a bounded
registry subset and report that as a separate public semantic-sidecar benchmark,
not as the private real-history semantic-sidecar quality claim.

Run the bounded public semantic-sidecar Track B pilot:

```powershell
python benchmarks\aippocampus\benchmark_source_evidence_retrieval.py --allow-deterministic-labels --include-public-semantic-sidecar --public-semantic-output-dir .tmp\public-semantic-sidecar-20260529-wide --public-semantic-conversations 80 --public-semantic-max-messages 160 --public-semantic-max-candidates 48 --public-semantic-cases 40 --public-semantic-min-cases 3 --public-semantic-top-k 5 --public-semantic-max-tokens 16384 --public-semantic-timeout 90 --output .tmp\track-b-public-semantic-sidecar-wide-20260529.json
```

Latest local pilot (2026-05-29): `status=diagnostic_only`,
`claim_level=diagnostic_pilot`, bounded subset 80 conversations / 160 messages /
48 label candidates, 3 reviewed `semantic-scope-labels.jsonl` rows, 3 selected
public semantic-sidecar cases, and 3/3 top-5 hits. The report carries
`minimum_empirical_case_count=50` plus `sample_size_warning`, so this remains a
small-N public semantic-sidecar pilot. It does not claim human-reviewed labels,
empirical public semantic-sidecar quality, unbounded public quality, or private
real-history semantic-sidecar quality.

Run the optional standard retrieval-QA Track B adapter:

```powershell
python benchmarks\aippocampus\benchmark_source_evidence_retrieval.py --include-standard-public --standard-dataset locomo --standard-questions 100 --standard-min-questions 20 --standard-top-k 10 --output benchmark_corpus\reports\locomo-track-b-standard-100.json
```

For a focused external-public adapter check, use the standard-only mode:

```powershell
python benchmarks\aippocampus\benchmark_source_evidence_retrieval.py --only-standard-public --standard-dataset locomo --standard-questions 100 --standard-min-questions 20 --standard-top-k 10 --output benchmark_corpus\reports\locomo-track-b-standard-only-100.json
```

`--only-standard-public` reports `standard_public_only_*` status values and
does not run the private-registry FTS5 or selected source-evidence arms. Use it
when validating the LoCoMo/LongMemEval adapter itself; use
`--include-standard-public` when you intentionally want the broader mixed Track
B bundle status.

The mixed Track B internal case controls such as `--fts5-cases`,
`--fts5-min-cases`, `--source-max-cases`, and `--source-min-cases` must be
positive integers. They are floors and limits for internal arms, not disable
switches; use `--only-standard-public` for the focused external-public
retrieval-QA path.

The standard adapter reports retrieval-only session/source R@K and MRR. It is
the current non-source-derived Track B arm because LoCoMo and LongMemEval V1
queries come from public dataset questions rather than from the target source
line. LoCoMo uses evidence dialogue ids; LongMemEval V1 uses answer sessions
and `has_answer` message flags when present. Reports include exact
evidence-line hits, context-visible evidence-line hits, context-improved
counts, and top-K context-rescued counts; the default context radius is 5
source lines because AIppocampus source payloads normally carry a small bounded
neighboring context window. It does not score answer generation or Track A gate
decisions. LongMemEval V2 is deliberately kept out of this source-evidence
adapter; use the V2 context-mapping pilot below instead of assigning a fake
R@K/MRR.

For published LongMemEval runs, prefer the dedicated runner so the split,
checksum, report shape, and evidence page stay independent from the broader
Track B adapter:

```powershell
python benchmarks\aippocampus\benchmark_longmemeval.py --split longmemeval-v1-oracle --download --questions 50 --min-questions 20 --top-k 10 --output benchmark_corpus\reports\longmemeval-v1-oracle-retrieval-50.json
python benchmarks\aippocampus\benchmark_longmemeval.py --split longmemeval-v1-small --download --questions 50 --min-questions 20 --top-k 10 --output benchmark_corpus\reports\longmemeval-v1-small-retrieval-50.json
```

Run the LongMemEval V2 context-mapping pilot after the ignored V2 JSONL files
are present locally:

```powershell
python benchmarks\aippocampus\benchmark_longmemeval_v2_context.py --case-limit 5 --output .tmp\longmemeval-v2-context-mapping.json
```

This pilot reports schema, checksum, join-key coverage, environment-pool
coverage, and sanitized case hashes. It does not report V2 source-evidence
R@K/MRR, benchmark-grade context-gathering quality, answer accuracy, LAFS, or
SOTA claims.

Run the MemoryAgentBench metadata and public-safe case-pack smoke:

```powershell
python benchmarks\aippocampus\benchmark_memoryagentbench.py --json
python benchmarks\aippocampus\benchmark_memoryagentbench.py --case-pack-output .tmp\memoryagentbench-case-pack.json --prediction-template-output .tmp\memoryagentbench-predictions.jsonl --json
```

The runner defaults to fresh-clone-safe metadata: it reports official split
expectations, local file hashes, byte counts, row/schema observations where
local JSON/JSONL exports exist, and per-layer support status. Keep downloaded
or exported MemoryAgentBench files under the ignored
`benchmark_corpus/memoryagentbench/` directory. The explicit case pack may
contain MemoryAgentBench context and question text for a narrow model-facing
subset, but it excludes answers, gold labels, and scoring-only metadata; keep
that output under `.tmp/` or `benchmark_corpus/reports/`.

Run the optional semantic second-stage line reranker over the same source
boundary:

```powershell
python benchmarks\aippocampus\benchmark_source_evidence_retrieval.py --include-standard-public --standard-dataset longmemeval-v1-oracle --standard-questions 50 --standard-min-questions 20 --standard-top-k 10 --standard-line-reranker semantic --standard-line-reranker-workers 0 --output benchmark_corpus\reports\longmemeval-oracle-track-b-standard-50-semantic-line-reranker.json
```

`--standard-line-reranker semantic` requires a configured DeepSeek-compatible
backend. It ranks only candidate line numbers from the top-session/top-context
candidate set; it does not generate answers, add outside source lines, or use
ground-truth labels as input. The candidate boundary uses both the original
question terms and a content-term query variant with generic question words
removed; this is meant to reduce LoCoMo-style speaker/generic-term noise while
preserving the raw query as a fallback. Reports keep `semantic_only_*` metrics
separate from FTS-preserving `reranked_*` metrics, so a live reranker
improvement cannot hide regressions to first-stage exact hits. Candidate
evidence coverage is reported only as an oracle diagnostic after scoring; it is
not sent to the reranker. `--standard-line-reranker-workers 0` resolves to
roughly half the requested question count for faster live runs.

Run the optional live semantic-gate smoke over the coding corpus:

```powershell
python benchmarks\aippocampus\benchmark_live_semantic_gate.py --sharegpt-conversations 100 --semantic-mode on --semantic-workers gate --output benchmark_corpus\reports\live-semantic-gate-100.json
```

The live smoke is not part of the required default suite. It needs a configured
DeepSeek-compatible semantic backend and writes sanitized reports only. Use
the default case parallelism for large local runs unless provider rate limits
say otherwise: `--case-workers 0` resolves to
`ceil(sharegpt_conversations / 2)`, so 100 conversations use 50 case workers.
Parallel runs disable the local JSON semantic result cache while still
reporting provider-side prefix-cache usage.

Run the optional dream live-shadow negative-control replay over generated
clean-source corpus directories:

```powershell
python skills\aippocampus\scripts\dream_live_shadow_ab.py --replay-clean-source-dir benchmark_corpus\output\sharegpt_coding_multiturn --dataset-id sharegpt_coding_multiturn --generate-dream-rows 64 --dream-worker-mode deterministic --max-threads 10000 --max-user-messages 60000 --window-user-turns 6 --output .tmp\dream-shadow-benchmark-sharegpt-coding-10000.json --json
python skills\aippocampus\scripts\dream_live_shadow_ab.py --replay-clean-source-dir benchmark_corpus\output\sharegpt_all_multiturn --dataset-id sharegpt_all_multiturn --generate-dream-rows 64 --dream-worker-mode deterministic --max-threads 10000 --max-user-messages 60000 --window-user-turns 6 --output .tmp\dream-shadow-benchmark-sharegpt-all-10000.json --json
python skills\aippocampus\scripts\dream_live_shadow_ab.py --replay-clean-source-dir benchmark_corpus\output\sharegpt_coding_multiturn --dataset-id sharegpt_coding_multiturn_model_backed --generate-dream-rows 4 --dream-worker-mode model-backed --max-threads 10000 --max-user-messages 60000 --window-user-turns 6 --output .tmp\dream-shadow-benchmark-sharegpt-coding-10000-model.json --json
python skills\aippocampus\scripts\dream_live_shadow_ab.py --replay-clean-source-dir benchmark_corpus\output\sharegpt_all_multiturn --dataset-id sharegpt_all_multiturn_model_backed --generate-dream-rows 4 --dream-worker-mode model-backed --max-threads 10000 --max-user-messages 60000 --window-user-turns 6 --output .tmp\dream-shadow-benchmark-sharegpt-all-10000-model.json --json
```

This replay is shadow-only and sanitized. Use `--dream-worker-mode
model-backed` when testing the actual bounded background dream worker; the
deterministic mode is a structural ablation only. Treat public-corpus dream-only
eligible exposure as an over-personalization negative-control signal, not as
private real-history behavior lift or delivered treatment evidence. Dated
aggregate evidence lives in
`docs/evidence/dream/dream-live-shadow-benchmark-corpus-2026-05-31.md`.

Build a private warm ambient recall case pack from the generated coding
clean-source corpus. Use separate labeled views so source-ref support,
current-thread echo activation, and topic epoch voting can be tightened without
one label policy masking another:

```powershell
python benchmarks\aippocampus\build_warm_ambient_trace_cases.py --clean-source-dir benchmark_corpus\output\sharegpt_coding_multiturn --dataset-id sharegpt_coding_multiturn --out .tmp\warm-sharegpt-coding-100-source-ref.jsonl --jsonl --subset-messages-out .tmp\warm-sharegpt-coding-100-pack\clean-source\messages.jsonl --registry-out .tmp\warm-sharegpt-coding-100-pack\threads.json --limit 100 --per-thread 1 --trace-window 6 --min-turn-index 2 --label-template --label-policy source_ref_supported --json
python benchmarks\aippocampus\build_warm_ambient_trace_cases.py --clean-source-dir benchmark_corpus\output\sharegpt_coding_multiturn --dataset-id sharegpt_coding_multiturn --out .tmp\warm-sharegpt-coding-100-echo.jsonl --jsonl --subset-messages-out .tmp\warm-sharegpt-coding-100-pack\clean-source\messages.jsonl --registry-out .tmp\warm-sharegpt-coding-100-pack\threads.json --limit 100 --per-thread 1 --trace-window 6 --min-turn-index 2 --label-template --label-policy echo_guard --json
python benchmarks\aippocampus\build_warm_ambient_trace_cases.py --clean-source-dir benchmark_corpus\output\sharegpt_coding_multiturn --dataset-id sharegpt_coding_multiturn --out .tmp\warm-sharegpt-coding-100-topic-vote.jsonl --jsonl --subset-messages-out .tmp\warm-sharegpt-coding-100-pack\clean-source\messages.jsonl --registry-out .tmp\warm-sharegpt-coding-100-pack\threads.json --limit 100 --per-thread 1 --trace-window 6 --min-turn-index 2 --label-template --label-policy topic_epoch_vote --json
python benchmarks\aippocampus\benchmark_warm_ambient_sweep.py --cases-file .tmp\warm-sharegpt-coding-100-source-ref.jsonl --registry .tmp\warm-sharegpt-coding-100-pack\threads.json --live --wait-modes quorum_first,wait_all --case-workers 2 --progress-dir .tmp\warm-progress-source-ref --prefix-cache-warmup-scouts 2 --prefix-cache-warmup-delay 0.5 --max-workers-list 20,50 --timeouts 15,30 --json
python benchmarks\aippocampus\benchmark_warm_ambient_recall.py --cases-file .tmp\warm-sharegpt-coding-100-topic-vote.jsonl --registry .tmp\warm-sharegpt-coding-100-pack\threads.json --live --wait-all --case-workers 1 --max-workers 50 --prefix-cache-warmup-scouts 2 --prefix-cache-warmup-delay 0.5 --timeout 30 --min-available-rate 0 --json
```

For warm recall, `--max-workers` is per-case scout concurrency and
`--case-workers` is outer case concurrency. Keep `--case-workers` small for live
runs because `case_workers=4` with `max_workers=50` can already issue up to 200
simultaneous scout requests. Use `--case-offset`, `--case-limit`, and
`--progress-dir` to shard 100-case packs and keep sanitized partial evidence if
a provider returns `service_unavailable_503` or a run is interrupted.
For cache tuning, use `--prefix-cache-warmup-scouts 2` with a small
`--prefix-cache-warmup-delay` on live benchmark/evaluation runs. This preserves
the full 10x5 scout set while giving DeepSeek a completed same-prefix request
before the remaining thin scout suffixes launch.
Warm scout prompts keep shared context and sanitized prompt trace before the
per-lane scout task; moving the scout task earlier may look cache-friendly
across cases but hurts the larger same-case 50-lane prefix. Benchmark metrics
include per-family completion tokens and prompt-cache hit/miss tokens so cache
regressions can be attributed before changing concurrency or prompt layout.
Thinking mode is quality-first and defaults to enabled; use
`AIPPOCAMPUS_WARM_RECALL_THINKING=disabled` only as an explicit ablation or
cost diagnostic, not as the default source-ref calibration path.
For wait-all source-ref evaluation, prefer treating `--timeout 45` as the
stability diagnostic when `--timeout 30` has clean case coverage but a marginal
read-timeout error rate. Do not compensate by lowering scout concurrency or
adding rigid `max_tokens` truncation unless quality regressions point there.
For `topic_epoch_vote` packs, set `--min-available-rate 0`: a valid LLM
`suppress` vote may intentionally produce no visible card.
For source-ref packs, keep `--max-false-evidence-count 0` strict. The
`source_ref_supported` labels require either a strong continuation cue or
meaningful prior overlap; generic capability questions and prompts pointing at
freshly pasted current text should not force source-backed recall. Prior trace
rows containing redaction placeholders are excluded from source-ref support
labels; privacy guard suppression should not fail the source-ref pack. Treat
`case_pass_rate` as recall coverage, not the only quality signal; a safe miss is
preferable to surfacing an unsupported citation.
For echo packs, `current_thread_echo_count` labels are intentionally narrower:
they require short, strong continuation turns rather than any topic overlap, so
the benchmark does not reward citing the user's current paste as prior memory.
The `trace_fallback_card_count` metric counts deterministic fallback cards from
sanitized prior trace rows. It should improve supported coverage without
loosening source validation; investigate it separately from model scout recall.
Runtime merge keeps privacy guard as a hard veto, but an evidence sentinel block
only suppresses model-generated cards. Locally validated prompt-trace fallback
cards may still surface, and current-thread fallback still increments the echo
counter even when visibility is suppressed. Strong continuation cues can fall
back to the immediately prior source-backed trace when lexical overlap is thin;
generic `model/error/use` overlap is not enough to require or emit source-backed
recall.

These warm case packs stay private local artifacts. The subset registry is only
for source-ref validation against sampled clean-source rows; do not commit the
case pack, subset messages, subset registry, or live sweep output.

## Repository Boundary

Public, documented corpus samples and deterministic conversion scripts may be
tracked in git. Local Hugging Face caches, full third-party benchmark downloads
(including smaller academic files), generated clean-source outputs, and
benchmark reports stay ignored unless a future change deliberately promotes a
curated subset with provenance and license/storage notes.

`benchmark_corpus\sharegpt_raw\` is intentionally ignored. It is a local input
staging area for large public JSONL files and should not be treated as a
trackable fixture.

Do not add private user exports, raw Codex rollouts, tokens, cookies, or
machine-local paths here.
