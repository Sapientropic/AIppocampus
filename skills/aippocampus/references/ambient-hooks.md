# Ambient Hooks

This reference owns prompt-time recall, lifecycle upkeep, semantic gating, and
the hook-safe subconscious scheduler. `SKILL.md` should only summarize these
boundaries.

## Prompt Hook

`scripts/aippocampus_prompt_hook.py` is the Codex `UserPromptSubmit` handler.
Most prompts should produce no output.

Outcomes:

- `skip`: inject nothing. Ordinary code work without a memory cue should land
  here.
- `scent`: inject a small developer-context hint that related memory may exist.
  This is association, not evidence.
- `evidence`: run a small conclusion-first search over registered clean-source
  or SQLite indexes and inject 1-3 hits with source metadata.

Keep `scent` and `evidence` distinct. A weak association can steer the next
agent action, but it must not be reported as remembered fact.

Prompt decisions may also include a private `ambient_recall` block built by
`ambient_recall_cards.py`. This block normalizes existing hook signals into
compact cards with `mode`, `confidence`, `cards`, `avoid`, `latency_ms`,
`cache_status`, and `late_update_policy`. Cards are guidance for the agent, not
text to paste into the final answer. `scent` and `candidate` cards are
resonance only; only `evidence` cards may be treated as source-backed, and even
then exact claims should be checked against clean source when they matter.

When the hook receives a thread/session id, `ambient_thread_cache.py` may store
up to a few compact cards under a hashed `thread_id + workspace + topic_epoch`
key. The cache is a soft working surface: it expires, records source-ref
fingerprints, per-card source validation, query aliases, topic-epoch decision
metadata, and visibility bias while avoiding raw prompt text. Later warm-scout
work should update this cache through the same serial writer rather than adding
a second ambient-memory store.

`warm_ambient_recall.py` is the standalone warm-path prototype for that later
work. It defines 10 scout families across 5 candidate-window/query variants:
5 P0 families for intent/mode, privacy/boundary, deep theme, key-line, and
evidence/gap checks; plus 5 P1 families for user style, trajectory,
cross-domain bridge, nudge writing, and semantic expansion. It runs the
resulting 50 lanes concurrently, isolates malformed scout output, merges at
most 3 cards, and writes through `ambient_thread_cache.py`. Scout prompts keep
the shared payload before the lane-specific `scout_task` suffix, and each lane
combines a family task with a variant `lens_task` rather than repeating one
generic prompt. The merger dereferences candidate source refs against
clean-source messages when possible, merges similar themes before the final
card cap, drops cards whose concrete source refs are missing or unsupported,
suppresses current-thread-only echoes by default, recognizes guard blocks by
family even with `family:variant` lanes, and lets scouts vote
`reuse|rotate|suppress` for topic epoch handling. It is not part of the default
foreground hook path: quorum-first runs are allowed to return before all lanes
finish, and `--wait-all` belongs to explicit evaluation or detached warming.
When sanitized prior prompt-trace rows already carry source refs, the warm path
may add one deterministic fallback card, but it must still pass the same local
source-ref validation and must not use the current prompt as memory.
When foreground code opts into `--warm-background` or
`AIPPOCAMPUS_WARM_RECALL_BACKGROUND=1`, `ambient_warm_scheduler.py` writes a
redacted local job file and starts a detached `warm_ambient_recall.py
--job-file` run. That job uses wait-all by default and writes only through the
thread-cache writer, so late scout results warm turn N+1 without making turn N
wait.

Use `benchmarks/aippocampus/benchmark_warm_ambient_recall.py` for calibration.
Deterministic mode is CI-safe and now runs 13 synthetic trace cases behind
quality gates, including a source-backed deep archival recall case;
`--cases-file` accepts larger sanitized JSON/JSONL trace suites. For real-trace
or public-corpus calibration,
`benchmarks/aippocampus/build_warm_ambient_trace_cases.py` can export sanitized
cases from registered clean source or from an explicit clean-source
`messages.jsonl` / directory. When sampling `benchmark_corpus/output/...`, pass
`--subset-messages-out` and `--registry-out`, then pass that registry to the
benchmark; this gives source-ref validation a tiny sampled dereference surface
without exposing the full generated corpus. Use `--min-turn-index 2` when the
calibration target needs real prior context. Add `--label-template` when
preparing a private review pack; then use focused `--label-policy` values for
automated gates: `source_ref_supported` requires a supported source-ref card
only when prior trace context overlaps the prompt, `echo_guard` requires the
current-thread echo penalty to fire at least once for short continuation turns,
and `topic_epoch_vote` requires an explicit LLM `reuse|rotate|suppress` topic
vote.
`topic_epoch_heuristic` is a review-only aid because topic epoch rotation must
not be hard-coded to a lexical rule. Generated exports are private working
artifacts and should not be committed. The runner also supports optional
`--max-missing-source-refs-count` for stricter source-ref tuning runs; leave it
unset when measuring broad candidate/scent recall where unsourced hints are
expected.
For source-ref live sweeps, keep `--max-false-evidence-count 0` strict and
treat `case_pass_rate` as recall coverage; safe no-card misses are preferable
to unsupported citation-shaped evidence.
Use `trace_fallback_card_count` to separate deterministic prior-trace fallback
coverage from model-generated scout coverage.
Live mode may call the configured external model but must keep output sanitized
to prompt hashes, aggregate metrics, validation status counts, error-kind
buckets, and cache usage only. Use
`benchmarks/aippocampus/benchmark_warm_ambient_sweep.py` to compare
quorum-first/wait-all, worker caps, and timeout values over the same private
case pack. The sweep ranks quality gates, case pass rate, false evidence, and
source-ref health before latency, so it does not accidentally choose the fastest
configuration that degrades recall. Its `analysis` block is the first place to
read after a large run: it names foreground and detached recommendations, gate
failure counts, scout error buckets, and source-ref pressure without exposing
case rows. Scout prompts keep `output_contract` as a compact schema and add
family-aware output budgets so Flash is not asked to fill a large template.
`--max-tokens` remains an explicit diagnostic override, not the default way to
control scout length. Current public-corpus live smoke points to 15s and 20-50
workers as the first real tuning band for quorum-first evaluation; 8s
under-samples useful scouts, and 5/10 workers can make Flash look worse by not
launching enough lanes in time. Keep lower worker caps as explicit 429/shared
account diagnostics, not as the quality baseline.
DeepSeek-compatible calls include a stable
hashed `user_id` by default so the 50 lanes share the same privacy-safe
scheduling/KV-cache bucket; callers may override it only with an already
sanitized `[a-zA-Z0-9_-]` id. Treat `429` and read timeouts as different
calibration signals: the former means rate/concurrency pressure, the latter
means the foreground budget is too short for wait-all.
`AIPPOCAMPUS_WARM_RECALL_MAX_WORKERS` may cap the default live worker count for
shared accounts or pro-model experiments; keep the normal foreground behavior
quorum-first.
For long labeled packs, keep case-level and scout-level concurrency separate:
`--max-workers` is the per-case 10x5 scout lane cap, while `--case-workers` is
outer case parallelism. Use small outer values such as 2-4 plus
`--case-offset`, `--case-limit`, and `--progress-jsonl` / `--progress-dir` for
resumable long runs. A `service_unavailable_503` bucket means the provider was
too busy; do not read it as a source-ref, echo, or topic-epoch quality signal.
Detached warm jobs use a small prefix-cache warmup wave by default before the
rest of the 10x5 lanes launch. Benchmark callers can tune this with
`--prefix-cache-warmup-scouts` and `--prefix-cache-warmup-delay`; foreground
direct runs should usually leave it at zero and use cached thread cards instead
of waiting for provider cache construction.

Callers may opt into residue export by passing a residue output path to the
thread-cache writer. This writes `aippocampus_ambient_residue` JSONL rows for
source-ref-fingerprinted cards so future dream jobs can inspect unused
resonance. Residue is only a dream seed: it is not formal memory, not a dream
finding, and not source-backed text by itself. Unsourced one-off scent cards
are skipped by default.

Useful commands:

- `python ...\aippocampus_prompt_hook.py --prompt "hook 机制像人类联想" --json`
- `python ...\aippocampus_prompt_hook.py --prompt "ambient recall" --session-id dry-run --json`
- `python ...\diagnose_hooks.py --events UserPromptSubmit,Stop`
- `python ...\simulate_prompt_hook.py --cwd "$PWD" --strict`
- `python ...\simulate_prompt_hook.py --cwd "$PWD" --compare-concept-graph`
- `python ...\simulate_multilingual_prompt_hook.py --cwd "$PWD"`
- `python ...\warm_ambient_recall.py --prompt "继续 ambient recall" --cwd "$PWD" --thread-id dry-run --json`
- `python ...\warm_ambient_recall.py --job-file <redacted-job.json> --json`
- `python benchmarks\aippocampus\build_warm_ambient_trace_cases.py --out .tmp\warm-traces.jsonl --jsonl --label-template --json`
- `python benchmarks\aippocampus\build_warm_ambient_trace_cases.py --clean-source-dir benchmark_corpus\output\sharegpt_coding_multiturn --dataset-id sharegpt_coding_multiturn --out .tmp\warm-sharegpt-coding-100-source-ref.jsonl --jsonl --subset-messages-out .tmp\warm-sharegpt-coding-100-pack\clean-source\messages.jsonl --registry-out .tmp\warm-sharegpt-coding-100-pack\threads.json --limit 100 --per-thread 1 --trace-window 6 --min-turn-index 2 --label-template --label-policy source_ref_supported --json`
- `python benchmarks\aippocampus\benchmark_warm_ambient_recall.py --json`
- `python benchmarks\aippocampus\benchmark_warm_ambient_recall.py --cases-file traces.jsonl --json`
- `python benchmarks\aippocampus\benchmark_warm_ambient_recall.py --cases-file traces.jsonl --registry .tmp\warm-sharegpt-coding-pack\threads.json --live --quorum-first --case-offset 0 --case-limit 10 --case-workers 2 --max-workers 50 --prefix-cache-warmup-scouts 2 --prefix-cache-warmup-delay 0.5 --timeout 15 --progress-jsonl .tmp\warm-progress-source-ref-000.jsonl --json`
- `python benchmarks\aippocampus\benchmark_warm_ambient_recall.py --cases-file .tmp\warm-sharegpt-coding-100-topic-vote.jsonl --registry .tmp\warm-sharegpt-coding-100-pack\threads.json --live --wait-all --case-workers 1 --max-workers 50 --prefix-cache-warmup-scouts 2 --prefix-cache-warmup-delay 0.5 --timeout 30 --min-available-rate 0 --json`
- `python benchmarks\aippocampus\benchmark_warm_ambient_sweep.py --cases-file traces.jsonl --registry .tmp\warm-sharegpt-coding-pack\threads.json --live --wait-modes quorum_first,wait_all --case-workers 2 --progress-dir .tmp\warm-progress --prefix-cache-warmup-scouts 2 --prefix-cache-warmup-delay 0.5 --max-workers-list 20,50 --timeouts 15,30 --json`
- `python ...\install_aippocampus_prompt_hook.py install|status|uninstall`

`deep_archival_recall` is an escalation request, not a license to dump history:
the foreground agent should open clean source first using the card's
`source_refs`, and only use raw audit paths when clean source cannot settle an
exact wording or provenance dispute.

On Windows, installers prefix generated hook commands with PowerShell's call
operator (`&`) so quoted Python paths execute instead of being parsed as string
expressions. This is an invocation fix only: it must not broaden prompt
triggering, write prompt text to logs, or blur the `scent` versus `evidence`
boundary.

The global prompt hook has a small foreground budget. Its default
`--semantic-timeout` is lower than the standalone semantic gate so optional
semantic work cannot consume the whole Codex `UserPromptSubmit` timeout. Do not
raise this default unless the hook timeout is raised and fresh, uncached memory
prompts still complete within budget.

The foreground default is about one second for fresh semantic calls, plus a
whole-hook fail-open budget below the Codex hook timeout. Treat that as a
scent/cache pass, not as the full recall budget; explicit `active_recall.py`,
`runtime recall`, and standalone `semantic_recall_gate.py` can spend longer
when the user asks for source-backed memory.

When an explicit memory cue already has local association or working-memory
overlap, the prompt hook skips the external semantic gate and goes straight to
local evidence. This protects hook latency without removing the deeper semantic
path for fuzzy or cross-lingual prompts.

The prompt hook can also read `cognitive_map.json`. Cognitive-map routes are
materialized from detached DeepSeek subconscious jobs, so a route match is
already prior semantic work and should skip foreground DeepSeek spend. The hook
uses those routes only as `scent`: they can add query terms and candidate
threads, but they are never evidence by themselves.

## Semantic Gate

When `DEEPSEEK_API_KEY` is present and `AIPPOCAMPUS_SEMANTIC_GATE` is not `off`,
the prompt hook may call `scripts/semantic_recall_gate.py`. The semantic gate
runs small parallel workers:

- `gate`: choose `skip`, `scent`, or evidence-worthy recall.
- `alias`: generate multilingual and paraphrase search aliases.
- `scope`: choose current project, registered threads, or working memory, and
  catch over-personalization risk.

The semantic gate only proposes queries and scope. Evidence still has to come
from local source search.

The local pre-gate avoids unnecessary external calls. Obvious code-surface
prompts such as "fix dashboard hover and run tests" should not call the semantic
model just because registry associations contain broad terms. Explicit recall,
working-memory matches, and strong source-backed triggers bypass this brake.

Multilingual behavior should be semantic, not a pile of hard-coded words.
Non-English natural-language prompts in Russian, Arabic, Japanese, Korean, Thai,
Spanish, French, German, Portuguese, and similar languages can reach the
semantic gate when they look like memory questions. Short daily chatter and
simple commands such as "好，开干" should not become triggers.

Useful commands:

- `python ...\semantic_recall_gate.py --prompt "那个脑内续接器现在怎么样了？" --cwd "$PWD" --json`
- `python ...\semantic_trigger_router.py --json`

## Redaction And Logging

Prompt-time external-model calls must redact credential-like substrings before
the model sees them:

- API keys, bearer tokens, cookies, password-like assignments
- credentialed URLs and connection-string secrets
- private-key blocks

The hook should hard-skip only when the prompt is mostly credential material or
contains private-key blocks. Otherwise redact sensitive substrings and continue
when recall is useful.

Do not write prompt text to hook debug logs. Optional logs may record decision,
timing, candidate thread ids/titles, evidence line numbers, and query aliases.

## Lifecycle Hook

`scripts/aippocampus_lifecycle_hook.py` handles deterministic maintenance. It
is separate from prompt recall because lifecycle events can tolerate bounded
fixed work.

Installed events:

- `SessionStart`: refresh the global registry at most once per hour when an
  index already exists; optionally ask the scheduler whether background work is
  due.
- `Stop`: at most once per 15 minutes per workspace, run health; refresh stale
  clean source, main index, existing segment indexes, registry rows, and
  scheduler state.
- `PreCompact`: refresh clean source, index, and registry before compaction.
- `PostCompact`: refresh after compaction unless a compact pass just ran.

Useful commands:

- `python ...\aippocampus_lifecycle_hook.py --event Stop --cwd "$PWD" --dry-run --json`
- `python ...\diagnose_hooks.py --events UserPromptSubmit,Stop`
- `python ...\install_aippocampus_lifecycle_hook.py install|status|uninstall`

`build_associations.py` scans the global registry and can exceed a lifecycle
hook timeout on real archives. Lifecycle hooks enqueue that rebuild detached and
write its output through the normal atomic association writer. Do not move a
full association rebuild back into the foreground hook path; prompt hooks should
consume the latest completed sidecar and fail open when it is stale.

## Scheduler Boundary

`scripts/subconscious_scheduler.py --maybe-start` is the only subconscious route
that lifecycle hooks should call. It must return quickly, check lock/cooldown
state, require `DEEPSEEK_API_KEY`, and start detached work only when enough new
clean-source turns exist.

Multiple Codex threads may hit lifecycle hooks around the same time. The
scheduler keeps `--maybe-start` hook-safe by taking a short enqueue lock and by
leasing each due project before starting detached work. Later hook calls should
see the active lease and skip instead of launching duplicate DeepSeek workers.
The detached worker clears the lease when it finishes; stale leases expire.

The detached worker may run timeline prep, subconscious jobs, review,
semantic-trigger materialization, working-memory routing, cognitive-map
materialization, and concept graph rebuilds. It still writes only staging,
navigation, or soft-memory artifacts.

DeepSeek concurrency belongs inside the detached worker, not in the foreground
hook. Lifecycle hooks enqueue `subconscious_scheduler.py --maybe-start` as a
detached process, then return; scheduler locks and project leases collapse
duplicates. `subconscious_jobs.py` defaults to parallel samples, can run
multiple job/sample calls concurrently, and keeps staging JSONL plus sidecar
materialization serialized and atomic. A hook budget miss or model delay should
mean "background semantic work is not ready yet", not "replace it with a
mechanical semantic judgment".

Useful commands:

- `python ...\subconscious_scheduler.py --maybe-start --cwd "$PWD" --json`
- `python ...\subconscious_scheduler.py --maybe-start --cwd "$PWD" --dry-run --json`

## Never From Hooks

- Do not mutate raw rollouts.
- Do not cold-archive or delete files.
- Do not append checkpoint candidates automatically.
- Do not run full Graphify automatically.
- Do not run DeepSeek synchronously inside lifecycle hooks.
- Do not place tool/debug provenance into ambient recall output.
