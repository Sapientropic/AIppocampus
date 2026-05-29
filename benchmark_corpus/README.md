# Benchmark Corpus

This folder holds public conversation-corpus inputs and converters for
AIppocampus benchmark work.

## Contents

- `convert_to_aippocampus.py` converts public conversation datasets into
  AIppocampus clean-source `messages.jsonl` and `turns.jsonl`.
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

## Usage

Run a local smoke conversion:

```powershell
python benchmark_corpus\convert_to_aippocampus.py --source local --input benchmark_corpus\testdata_wildchat.jsonl --output .tmp\benchmark-corpus-smoke
```

Run a public dataset stream:

```powershell
python benchmark_corpus\convert_to_aippocampus.py --source wildchat --max-convs 200 --output .tmp\wildchat-clean-source
```

Regenerate the current ShareGPT clean-source corpora from local public JSONL
inputs:

```powershell
python benchmark_corpus\convert_to_aippocampus.py --source sharegpt --input benchmark_corpus\sharegpt_raw --min-turns 2 --output benchmark_corpus\output\sharegpt_all_multiturn
python benchmark_corpus\convert_to_aippocampus.py --source sharegpt --input benchmark_corpus\sharegpt_raw --min-turns 2 --coding-only --output benchmark_corpus\output\sharegpt_coding_multiturn
```

Run the Track A P1 gate-decision baseline over the coding corpus:

```powershell
cd skills\aippocampus
python scripts\benchmark_memory_decision_gate.py --case-set sharegpt-coding --sharegpt-conversations 100 --output ..\..\benchmark_corpus\reports\sharegpt-p1-gate-100.json
```

Run the optional public-corpus Track B source-evidence baseline over the broad
ShareGPT corpus:

```powershell
cd skills\aippocampus
python scripts\benchmark_source_evidence_retrieval.py --include-sharegpt-public --sharegpt-public-conversations 100 --sharegpt-public-cases 200 --sharegpt-public-min-cases 50 --output ..\..\benchmark_corpus\reports\sharegpt-track-b-public-100.json
```

This Track B slice reports message-level and turn-level source hits. It is a
public-corpus retrieval baseline, not a private real-history source-evidence
quality claim.

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

Latest local pilot (2026-05-29): `status=sufficient`, bounded subset 80
conversations / 160 messages / 48 label candidates, 3 reviewed
`semantic-scope-labels.jsonl` rows, 3 selected public semantic-sidecar cases,
3/3 top-5 hits. This is a public semantic-sidecar pilot only; it does not claim
human-reviewed labels, unbounded public quality, or private real-history
semantic-sidecar quality.

Run the optional standard retrieval-QA Track B adapter:

```powershell
cd skills\aippocampus
python scripts\benchmark_source_evidence_retrieval.py --include-standard-public --standard-dataset locomo --standard-questions 100 --standard-min-questions 20 --standard-top-k 10 --output ..\..\benchmark_corpus\reports\locomo-track-b-standard-100.json
python scripts\benchmark_source_evidence_retrieval.py --include-standard-public --standard-dataset longmemeval-v1-oracle --standard-questions 50 --standard-min-questions 20 --standard-top-k 10 --output ..\..\benchmark_corpus\reports\longmemeval-oracle-track-b-standard-50.json
```

The standard adapter reports retrieval-only session/source R@K and MRR. LoCoMo
uses evidence dialogue ids; LongMemEval V1 uses answer sessions and
`has_answer` message flags when present. Reports include exact evidence-line
hits, context-visible evidence-line hits, context-improved counts, and top-K
context-rescued counts; the default context radius is 5 source lines because
AIppocampus source payloads normally carry a small bounded neighboring context
window. It does not score answer generation or Track A gate decisions.
LongMemEval V2 currently lacks explicit source-evidence refs in this adapter
and is reported as skipped rather than assigned a fake R@K.

Run the optional semantic second-stage line reranker over the same source
boundary:

```powershell
cd skills\aippocampus
python scripts\benchmark_source_evidence_retrieval.py --include-standard-public --standard-dataset longmemeval-v1-oracle --standard-questions 50 --standard-min-questions 20 --standard-top-k 10 --standard-line-reranker semantic --standard-line-reranker-workers 0 --output ..\..\benchmark_corpus\reports\longmemeval-oracle-track-b-standard-50-semantic-line-reranker.json
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
cd skills\aippocampus
python scripts\benchmark_live_semantic_gate.py --sharegpt-conversations 100 --semantic-mode on --semantic-workers gate --output ..\..\benchmark_corpus\reports\live-semantic-gate-100.json
```

The live smoke is not part of the required default suite. It needs a configured
DeepSeek-compatible semantic backend and writes sanitized reports only. Use
the default case parallelism for large local runs unless provider rate limits
say otherwise: `--case-workers 0` resolves to
`ceil(sharegpt_conversations / 2)`, so 100 conversations use 50 case workers.
Parallel runs disable the local JSON semantic result cache while still
reporting provider-side prefix-cache usage.

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
