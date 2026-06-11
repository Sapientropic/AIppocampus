# AMemGym Adapter Boundary

This page is the AIppocampus evidence owner for GitHub #733/#742 and the
official-runner boundary closed by the 2026-06-09 #958 blocker note. It records
what the AMemGym adapter can inspect today, what source-backed overlay metrics
mean, and what remains out of scope before any official or comparative score can
be quoted.

Decision: suitable as a staged external benchmark adapter, but not as an
official full-`v1.base` score claim yet. The repository now has a deterministic,
public-safe metadata smoke for the public `v1.base` JSON, a local
prediction-overlay smoke, and an official-runner bridge that can run an
operator-provided upstream AMemGym checkout from ignored local paths and
summarize official `Overall`, `UB`, `Random`, and normalized `Memory` outputs.

The official-runner bridge also has AIppocampus `BaseAgent` adapter arms. This
is useful only when the report keeps the lifecycle boundary visible:
`act/add_msgs` captures visible messages, `save_state` refreshes generic JSONL,
clean source, and source index, a pre-score phase materializes worker surfaces,
and `answer_question` consumes those prepared artifacts without mutating state.
If the worker/semantic sidecar surfaces are absent, the arm is explicitly a
clean-source/file-retrieval baseline, not the full AIppocampus system.
As of 2026-06-10, the official `aippocampus_semantic_sidecar` arm has a
deterministic pre-score materializer for AMemGym visible messages. It prepares
working-memory, semantic-trigger, and semantic-cue navigation surfaces before
scored `answer_question` calls; those surfaces are route hints with source refs,
not source truth or live semantic-model quality.

For Codex Desktop product evidence, keep the separate Desktop contract. It
compares native Codex without AIppocampus, AIppocampus clean-source recall
without semantic sidecars, and AIppocampus with semantic sidecar navigation
inside the actual Codex Desktop host. Its default output is only a contract
preview until a clean isolated Desktop run supplies claimable live environment
evidence.

## Official Sources

- Paper: <https://arxiv.org/abs/2603.01966>
- OpenReview: <https://openreview.net/forum?id=sfrVLzsmlf>
- Repository: <https://github.com/AGI-Eval-Official/amemgym>
- Dataset: <https://huggingface.co/datasets/AGI-Eval/AMemGym>
- Public `v1.base` JSON: <https://huggingface.co/datasets/AGI-Eval/AMemGym/raw/main/v1.base/data.json>
- `v1.base` environment config: <https://raw.githubusercontent.com/AGI-Eval-Official/amemgym/main/configs/env/v1.base.json>

Verified source facts on 2026-06-05:

- The public Hugging Face dataset exposes `default` / `v1.base` as JSON with 20
  rows and top-level fields `id`, `start_time`, `user_profile`,
  `state_schema`, `periods`, and `qas`.
- The official `v1.base` config records 20 user profiles, 10 questions, 10
  evolution periods, two states per question, four changes per period, and seed
  42.
- The official repository describes four agent arms: Native, RAG, AWI, and AWE.
- The official `Overall` path evaluates multiple-choice answers through the
  upstream prompt/parser/metric path, expecting a JSON integer answer rather
  than free-form generation.
- The official agent extension surface is `amemgym.assistants.create_agent`
  plus the `BaseAgent` methods `reset`, `act`, `add_msgs`, `load_state`,
  `save_state`, and `answer_question`; there is no separate plugin registry.
- The default official metric list currently enables `accuracy`; `hamming` and
  `jaccard` exist in the metric code but are not in the default metric list.
- The official diagnosis path writes `write_failure`, `read_failure`, and
  `memory_success`. Utilization is owned by the upper-bound/utilization path,
  so AIppocampus must not pretend `utilization_failure` is a native diagnosis
  output.
- OpenRouter's OpenAI-compatible API uses the
  `https://openrouter.ai/api/v1` base URL and organization-prefixed model ids
  such as `openai/gpt-4.1-mini`; the bridge maps a local `Open_Router`
  credential alias to the `OPENAI_API_KEY` name expected by the official
  runner, but never writes the credential value to reports.

Local download smoke on 2026-06-05:

```powershell
python benchmarks\aippocampus\benchmark_amemgym.py --download-official --skip-sha256 --json
```

The sanitized report observed 20 rows, 220 periods, 943 sessions, zero messages
inside those sessions, 1206 updates, 200 QAs, 882 answer choices, and the
expected top-level field shape. This is schema evidence only; it is not an
AMemGym score.

## Runner

The metadata/overlay adapter lives at
`benchmarks/aippocampus/benchmark_amemgym.py` with source metadata in
`benchmark_corpus/amemgym_manifest.json`.

Fresh clones can run the missing-dataset boundary without network:

```powershell
python benchmarks\aippocampus\benchmark_amemgym.py --json
```

To inspect the public `v1.base` JSON, download it into the ignored local data
directory:

```powershell
python benchmarks\aippocampus\benchmark_amemgym.py --download-official --skip-sha256 --json
```

To exercise the source-backed overlay metrics on the checked-in public fixture:

```powershell
python benchmarks\aippocampus\benchmark_amemgym.py --dataset-path benchmark_corpus\amemgym_fixture\fixture.json --predictions benchmark_corpus\amemgym_fixture\predictions.jsonl --prediction-template-output .tmp\amemgym-predictions-template.jsonl --json
```

The default report emits only schema counts, case ids, hashes, local file
hashes, field histograms, layer names, and `cannot_claim` boundaries. It does
not emit raw profile text, session/query text, answer text, downloaded dataset
rows, local absolute paths, provider keys, or model outputs.

Downloaded official data belongs under the ignored
`benchmark_corpus/amemgym/` directory. Generated reports and prediction
templates belong under `.tmp/` or `benchmark_corpus/reports/`.

The official-runner bridge lives at
`benchmarks/aippocampus/benchmark_amemgym_official.py`. It assumes the upstream
AMemGym repository is installed or cloned in an ignored local path, defaulting
to `.tmp/amemgym-upstream`, and invokes the official modules rather than
reimplementing their scoring:

```powershell
git clone https://github.com/AGI-Eval-Official/amemgym.git .tmp\amemgym-upstream
uv sync --project .tmp\amemgym-upstream
python benchmarks\aippocampus\benchmark_amemgym_official.py --runner uv --provider openrouter --run random --json
```

For OpenRouter runs, set `Open_Router` as a local machine/user/process secret.
The bridge maps it into the official runner's `OPENAI_API_KEY` environment
variable and sets `OPENAI_BASE_URL` to OpenRouter only inside the subprocess.
The generated local agent config is written under `.tmp/amemgym-official/` and
uses `openai/gpt-4.1-mini` by default so OpenRouter receives a supported model
id. Raw official output directories stay ignored.

To verify the official-output and normalized-score plumbing without live model
cost, use the local deterministic protocol provider. It patches AMemGym's
`call_llm` in the official subprocess via an ignored `sitecustomize.py`, returns
a fixed JSON choice, and disables the upstream upper-bound sleep. This is
useful for proving full `v1.base` runner compatibility; it is not an LLM memory
quality score:

```powershell
python benchmarks\aippocampus\benchmark_amemgym_official.py --runner uv --provider local-scripted --run overall,upperbound,random --reset --overall-output-dir .tmp\amemgym-official\v1.base-local-scripted\overall --upperbound-output-dir .tmp\amemgym-official\v1.base-local-scripted\upperbound --random-output-file .tmp\amemgym-official\v1.base-local-scripted\random_metrics.json --output benchmark_corpus\reports\amemgym-official-local-scripted-2026-06-07.json --json
```

Tiny local slices may be useful while debugging provider wiring, path handling,
or output discovery, but they are not evidence numbers and must not be promoted
into public reports. Use the full public `v1.base` fixed arm before recording
`Overall`, `UB`, `Random`, or normalized `Memory` as evidence.

For bounded live-provider debugging, use `--max-cases`, `--resume`, and
`--checkpoint` together. `--max-cases` writes an ignored first-N env-data subset
under `.tmp/amemgym-official/v1.base/bounded-env/`; the report marks it as
`progressive_subset_debug_only` and keeps
`full_public_v1_base_fixed_arm_score_from_bounded_subset` in `cannot_claim`.
`--resume` skips requested surfaces whose summary artifacts are already
complete, and `--checkpoint` writes a public-safe state file containing only
phase status, elapsed subprocess time, completed counts, hashes, and redacted
labels:

```powershell
python benchmarks\aippocampus\benchmark_amemgym_official.py --runner uv --provider openrouter --arm official_native_full_history --run overall,upperbound,random --max-cases 1 --resume --checkpoint .tmp\amemgym-official\v1.base\live-native-checkpoint.json --output benchmark_corpus\reports\amemgym-official-bounded-native.json --json
```

The checkpoint is a recovery/audit surface, not raw official output. Provider
cost remains `unavailable` unless a later run records a stable sanitized usage
field from official outputs or provider metadata.

The official bridge supports three arm names:

| Arm | What it measures | Claim boundary |
| --- | --- | --- |
| `official_native_full_history` | Upstream Native-style full `msg_history` in model context, using the official evaluator. | Native baseline for the chosen model/provider only after full fixed-arm outputs exist. |
| `aippocampus_clean_source_no_semantic_sidecar` | AIppocampus visible-message export through generic JSONL, clean source, source index, and source-backed snippet recall. | File/clean-source retrieval baseline; not the full AIppocampus semantic worker system. |
| `aippocampus_semantic_sidecar` | The same source-backed adapter plus adapter-prepared working-memory, semantic-trigger, and semantic-cue navigation surfaces, with source reopen. | Full semantic-worker arm only when `adapter_metadata.json` shows prepared worker surfaces for the scored period states; otherwise it degrades to the clean-source baseline. |

Example official Native baseline plan or run:

```powershell
python benchmarks\aippocampus\benchmark_amemgym_official.py --runner uv --provider openrouter --arm official_native_full_history --run random --json
```

Example AIppocampus clean-source official adapter run:

```powershell
python benchmarks\aippocampus\benchmark_amemgym_official.py --runner uv --provider openrouter --arm aippocampus_clean_source_no_semantic_sidecar --run overall --reset --json
```

Example semantic-sidecar adapter run shape:

```powershell
python benchmarks\aippocampus\benchmark_amemgym_official.py --runner uv --provider openrouter --arm aippocampus_semantic_sidecar --run overall --reset --json
```

Reports include `aippocampus_official_adapter_protocol`,
`aippocampus_agent_adapter`, and `aippocampus_agent_state` so downstream
summaries can tell whether a score came from full-history Native,
clean-source-only retrieval, or a prepared semantic-worker arm. Do not quote a
semantic-worker result unless `aippocampus_agent_state.semantic_worker_state`
is `prepared`; clean-source arms report `clean_source_only`, and missing
semantic-worker surfaces report `missing_or_degraded`.

Live official Native attempt on 2026-06-06:

```powershell
python benchmarks\aippocampus\benchmark_amemgym_official.py --runner uv --provider openrouter --arm official_native_full_history --run overall,upperbound,random --reset --output benchmark_corpus\reports\amemgym-official-summary.json --json
```

The local upstream checkout was at
`AGI-Eval-Official/amemgym@ffcd18857a3e2b2c61f00730ebdec676e27d3e87`,
matching `origin/main` at fetch time. The run used the bridge's OpenRouter
provider adapter with credentials redacted from reports. It was stopped after
roughly two hours because the official `upperbound` subprocess was still
running; the residual AMemGym subprocess tree was terminated so it would not
continue provider calls in the background.

The resulting summary is intentionally a partial-output report, not a score:
`overall` had 6 of 20 user items with `overall_metrics.json`, `upperbound` had
38 of 882 choice evaluations in `utilization_results.json` and no
`utilization_metrics.json`, and `random` was complete at `0.23076190476190475`.
The bridge records this as `partial_official_outputs` with
`official_amemgym_score=not_claimed`; normalized `Memory` remains missing until
the full fixed arm has complete `Overall`, `UB`, and `Random` outputs.

This attempt proves the local official entrypoints, uv environment, provider
wiring, and redacted summary path are real. It does not satisfy #742's full
score acceptance criteria. The #1052 bridge update added bounded subset,
resume-skip, and public-safe checkpoint support, but the full public `v1.base`
score boundary remains unclaimed until a later dated run completes and reviews
the whole fixed arm.

Checkpoint/resume audit for #1083 on 2026-06-10:

[`amemgym-official-live-provider-1083-checkpoint-2026-06-10.md`](amemgym-official-live-provider-1083-checkpoint-2026-06-10.md)
used the #1052 `--resume` / `--checkpoint` path against the existing ignored
live-provider partial outputs without restarting long provider surfaces. The
audit skipped the already-complete `random` surface, wrote a public-safe
checkpoint, and preserved the blocker state: `overall` is still partial at 6 of
20 user items, `upperbound` is still partial at 38 of 882 choice evaluations,
and provider cost remains unavailable from official outputs. This closes #1083
as a precise blocker/progress report, not as an AMemGym score.

#1232 follow-up route blocker on 2026-06-11:

[`amemgym-official-live-provider-1232-blocker-2026-06-11.md`](amemgym-official-live-provider-1232-blocker-2026-06-11.md)
resumed the same OpenRouter Native fixed-arm path after provider-budget
adoption and account top-up. The follow-up diagnosis added a tiny OpenRouter
route preflight and showed the required OpenAI-family routes fail even on a
harmless fixed prompt, while non-OpenAI OpenRouter routes still accept that
prompt. The run therefore still does not complete: `overall` stayed partial at
6 of 20 user items, `upperbound` stayed partial at 38 of 882 choice
evaluations, and `random` stayed complete. This closes #1232 as
`provider-route-blocked`, not as an AMemGym score.

Official-compatible local-scripted protocol run on 2026-06-07:

```powershell
python benchmarks\aippocampus\benchmark_amemgym_official.py --runner uv --provider local-scripted --run overall,upperbound,random --reset --overall-output-dir .tmp\amemgym-official\v1.base-local-scripted\overall --upperbound-output-dir .tmp\amemgym-official\v1.base-local-scripted\upperbound --random-output-file .tmp\amemgym-official\v1.base-local-scripted\random_metrics.json --output benchmark_corpus\reports\amemgym-official-local-scripted-2026-06-07.json --json
```

The local upstream checkout was still
`AGI-Eval-Official/amemgym@ffcd18857a3e2b2c61f00730ebdec676e27d3e87`. The run
called upstream `amemgym.eval.overall`, `amemgym.eval.upperbound`, and
`amemgym.eval.random` against the full public `v1.base` data. All official
output surfaces were complete: 20 of 20 overall items, 2200 of 2200 overall
score leaves, 882 of 882 upper-bound choice evaluations, and the random matrix.

The public-safe summary reported:

| Score | Value |
| --- | ---: |
| Overall | 0.25681818181818183 |
| UB | 0.25681818181818183 |
| Random | 0.23076190476190475 |
| normalized Memory | 1.0 |

Cost/latency boundary: no provider credentials or live model calls were used.
The subprocess elapsed times were roughly 13.9s for `overall`, 0.6s for
`upperbound`, 0.6s for `random`, and 15.3s for the full bridge report.

This satisfies the official-output compatibility slice: the bridge can run the
official entrypoints to completion, discover official output files, and compute
the normalized Memory formula on full public `v1.base`. It is deliberately not
a live-model AMemGym score. `local-scripted` always returns the same JSON choice,
so `Overall` and `UB` match by construction and normalized `Memory=1.0` is a
protocol artifact, not evidence that a model or AIppocampus remembered
anything. The report therefore keeps
`real_llm_memory_quality_or_provider_model_score_from_local_scripted_provider`
and `leaderboard_parity_or_sota` in `cannot_claim`.

The Codex Desktop AMemGym-style benchmark lives at
`benchmarks/aippocampus/benchmark_codex_desktop_amemgym.py`. It does not invoke
the official AMemGym runner and does not implement `BaseAgent`; it reuses the
AMemGym evaluation idea of state evolution, later multiple-choice questions,
random baseline, oracle upper bound, and normalized memory score:

```powershell
python benchmarks\aippocampus\benchmark_codex_desktop_amemgym.py --json
```

The default command is a public-safe contract preview. Live Desktop scores can
be claimed only when each arm proves `openai/gpt-4.1-mini`, a disposable clean
workspace, an isolated Codex home, and no loaded skills/plugins beyond the
intended surface. The native arm must observe `loaded_skill_names=[]`; the two
AIppocampus arms must observe only `loaded_skill_names=["aippocampus"]`, with
semantic sidecar disabled or enabled according to the arm.

The Desktop contract now treats five score-distortion risks as hard gates:

- Scored question turns must not mutate later scored turns. Each question must
  run through per-question fork/rollback or restart from the same
  post-compaction checkpoint, with answer writes discarded.
- Answer choices must be personalized natural-language recommendations. Raw
  state-key recall, route codes, color/shelf/code slots, or other direct memory
  recitation questions are not claimable Desktop evidence.
- Setup state must be exposed through implicit natural sessions. Explicit
  bullet lists such as "X is now Y", raw state labels, or answer options that
  reveal state keys invalidate the run.
- Measured scoring must start from a separate cold Desktop thread with setup
  context hidden from the model context. Same-thread native context or visible
  setup history can make the Native baseline unrealistically strong.
- Temperature must either be request-verified as `0.0`, matching official
  Native, or the run must be labeled `variance_bounded_not_official_same_param`
  with at least three repeated runs and reported variance. Unverified
  temperature is a blocker, not a footnote.

Hook evidence is part of that gate, not an implementation detail. In an
isolated temporary `CODEX_HOME`, installing `hooks.json` and launching Codex
with hooks enabled is insufficient by itself: Codex lists those hooks as
`untrusted` until the matching `hooks.state` entries in `config.toml` trust the
current hook hashes. A claimable AIppocampus Desktop arm must therefore show
trusted AIppocampus hooks and observed `sessionStart`, `userPromptSubmit`, and
`stop` hook notifications. The native arm must show no AIppocampus hooks
installed, trusted, or observed.

Cache preparation is a separate pre-score phase. Before measured questions, the
AIppocampus arms must rebuild or refresh clean source, source indexes, and the
ambient route cache; the semantic arm must also materialize the semantic
sidecar. Then a non-scored warmup turn must prove `userPromptSubmit` completes
inside the foreground budget currently used by the hook command
(`--max-elapsed-ms 4300`). Formal Desktop scores must report cold-start /
precache cost separately and must not treat a timed-out cold hook as memory
quality evidence.

## Metric Layers

Keep these layers separate:

| Layer | Current adapter support | Not the same as |
| --- | --- | --- |
| AMemGym native score | The official bridge can summarize official `overall_metrics.json`, `utilization_metrics.json`, and `random_metrics.json`; the metadata adapter still supports only local exact answer-choice match when an explicit prediction JSONL is supplied. | Full public `v1.base` AMemGym leaderboard score unless all official outputs are produced for the full fixed arm. |
| Official diagnosis | The adapter can carry operator prediction flags for write/read failures, but it does not parse official diagnosis logs yet. | A verified `amemgym.eval.diagnosis` result. |
| Utilization | `utilization_failure_rate` is an AIppocampus overlay flag in the local prediction JSONL. | Official diagnosis output; utilization belongs to the official upper-bound/utilization path. |
| Official AIppocampus `BaseAgent` adapter | The official bridge can register ignored local AIppocampus adapter arms by Pythonpath overlay while leaving upstream eval modules, prompts, parser, and metric code unchanged. | Full AIppocampus capability when only clean source is present, or when semantic worker artifacts are missing/degraded. |
| Source-backed overlay | `source_reopen_success`, `current_state_source_hit`, `stale_state_as_current_rate`, `unsupported_personalization_rate`, `scent_as_evidence_rate`, and `answer_correct_but_unsupported_rate`. | Native accuracy, answer quality, or SOTA. |
| Cost/latency | `elapsed_ms` for deterministic helpers and official subprocess elapsed time for the bridge. | Provider billing unless token/cost metadata is extracted from raw official outputs under an explicit raw-artifact policy. |
| Codex Desktop AMemGym-style score | A separate contract runner can compare native Codex, AIppocampus without semantic sidecar, and AIppocampus with semantic sidecar under an isolated Desktop-host protocol. It now requires non-mutating scored turns, natural recommendation choices, implicit state exposure, cross-thread cold-start scoring, and temperature parity or variance reporting before a live score is claimable. | Official AMemGym score, same-thread Codex context quality, direct state recall, or live Desktop evidence before every environment and score-distortion gate passes. |

The checked-in fixture deliberately includes one current-vs-stale control, one
unsupported-personalization control, and one local utilization/read/write
failure flag so the report shape cannot collapse into a single accuracy number.

## Claim Boundary

Can claim now:

- AIppocampus has a deterministic AMemGym metadata smoke that can read the
  public `v1.base` JSON with the Python standard library.
- The repository has a public-safe fixture and local prediction-overlay path
  for source-backed AMemGym-style diagnostics.
- AIppocampus has a narrow official-runner bridge that can call the upstream
  `amemgym.eval.overall`, `amemgym.eval.upperbound`, and
  `amemgym.eval.random` modules from an ignored local checkout and summarize
  official output files into `Overall`, `UB`, `Random`, and normalized
  `Memory`.
- The same bridge has one full public `v1.base` protocol run for the
  deterministic `local-scripted` provider, proving complete official output
  discovery and normalized-score calculation without live provider calls.
- The official bridge can register AIppocampus `BaseAgent` arms through an
  ignored Pythonpath overlay, keep upstream eval modules unchanged, and report
  whether the arm is Native full-history, clean-source-only retrieval, or a
  prepared semantic-worker arm.
- The official `aippocampus_semantic_sidecar` adapter can now materialize
  working-memory, semantic-trigger, and semantic-cue navigation surfaces from
  visible AMemGym messages before scoring, then load those prepared surfaces
  during `answer_question` without appending to scored state.
- AIppocampus has a separate AMemGym-style Codex Desktop benchmark contract for
  native/no-sidecar/semantic-sidecar arms, with hard gates for clean workspace,
  isolated Codex home, expected skill/plugin loading, and AIppocampus hook
  trust/notification plus precache/warmup proof before live scores can be
  claimed. The same contract also blocks scoring-turn state pollution, direct
  state-recall questions, explicit state-bullet setup, same-thread native
  context visibility, and unverified temperature.
- Reports separate native answer-choice exact match, source-backed overlay
  fidelity, diagnosis-like flags, utilization overlay flags, cost/latency, and
  public claim boundaries.

Cannot claim now:

- AIppocampus has a full official AMemGym `v1.base` score.
- The 2026-06-07 `local-scripted` protocol values are a real LLM/provider
  memory score, a Native baseline, or AIppocampus product quality evidence.
- The 2026-06-06 partial official Native attempt is not a score; it is only
  execution/progress evidence.
- AIppocampus clean-source-only official adapter results are full
  semantic-worker AIppocampus results.
- AIppocampus semantic-sidecar official adapter results are claimable when
  `adapter_metadata.json` is absent or records missing/degraded worker
  surfaces.
- A hookless `BaseAgent` wrapper is equivalent to AIppocampus Desktop product
  behavior; it is only an official-runner surrogate with explicit lifecycle
  gates.
- AIppocampus is leaderboard-compatible with the official AMemGym runner beyond
  the local summary bridge until the full public `v1.base` arm is run and
  reviewed.
- AIppocampus has evaluated or beaten Native, RAG, AWI, AWE, Mem0, or any other
  official/external baseline on AMemGym.
- The AMemGym visible-message sidecar materializer is a live semantic model,
  a source-truth layer, or evidence of product memory quality by itself.
- AIppocampus has beaten Codex Desktop native behavior in live use; the Desktop
  runner currently defaults to a contract preview unless a clean isolated live
  run is attached and validated.
- A Codex Desktop run is comparable to official Native temperature unless the
  request path proves `temperature=0.0`; otherwise it is only variance-bounded
  evidence after repeated runs.
- A Desktop score from answer turns that remain in the thread, natural-session
  setup that was actually explicit state bullets, same-thread native context,
  or raw state-key choices is not claimable.
- Cold-start cache build or hook-timeout behavior is a valid readiness signal,
  but it is not the same metric as warmed memory recall quality.
- The local overlay metrics are official AMemGym accuracy.
- The structured LLM-simulated AMemGym users prove real human life-wide
  continuity.
- `utilization_failure_rate` is an official diagnosis output.

## Deferred Work

The 2026-06-09 blocker note
[`amemgym-official-live-provider-blocker-2026-06-09.md`](amemgym-official-live-provider-blocker-2026-06-09.md)
closes #958 as the ownerless deferred slice. #1052 added the bounded/resumable
execution shell and public-safe checkpoint report, but full live-provider
official-runner evidence remains blocked until a later dated note records a
complete full public `v1.base` fixed arm, pinned model/provider versions,
complete `overall` / `upperbound` / `random` outputs, sanitized cost/latency,
and an explicit Native/RAG/AWI/AWE parity decision without leaking raw rows,
model outputs, local paths, or keys.

The semantic-sidecar pre-score materializer is in place for the official
adapter prep slice. Remaining AMemGym semantic-sidecar evidence is still
deferred until a later full fixed-arm run records complete official outputs and
reviewed reports. Future richer semantic-worker surfaces may be added only when
their source-review boundary is explicit; the current materializer remains
navigation over visible AMemGym messages, not source truth.

The commentary/action-summary write-material arm is deliberately deferred to
the source-backed situation/work-material design work in #701 and #703. That
arm should only be added after the producer/consumer contract says which
source-backed action summaries can be written, reopened, demoted as stale, and
excluded from over-personalization.
