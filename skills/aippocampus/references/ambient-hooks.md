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
`cache_status`, `late_update_policy`, and a small `late_warm_handoff` policy.
Cards are guidance for the agent, not text to paste into the final answer.
`scent` and `candidate` cards are resonance only; only `evidence` cards may be
treated as source-backed, and even then exact claims should be checked against
clean source when they matter.

Cards may include `provenance_class`, `cached_origin`,
`source_reopen_required`, `reopenable_ref_count`, and per-card `cache_status`.
The allowed provenance classes are small and non-secret:
`deterministic_cue`, `warm_scout_proposal`, `cached_warm_card`,
`cognitive_map_route`, `working_memory_source`, `working_memory_model`, and
`source_backed_reopen`. Provenance complements `support_level`, `visibility`,
and `source_validation`; it must not be used to upgrade a card into fact or to
skip clean-source reopen.

`ambient_recall` also carries a `fresh_thread_packet` projected by
`fresh_thread_scent.py`. This is the #282 contract that bridges the #281
fresh-thread product goal with #277-style active recall locks. The packet fields are:
`support_level` (`silent_scent | soft_hypothesis | source_required |
suppressed`), coarse `confidence`, `sensitivity`, `freshness`, `route_reason`,
source-id-only `candidate_refs`, canonical `advisory_action`, compatibility
`suggested_action`, `when_not_to_use`, and a `source_boundary` block. The packet
is navigation material until source is reopened. It must not contain raw
prompts, raw snippets, secrets, local paths, or user-facing memory narration.

`advisory_action` is the canonical packet hint. `suggested_action` remains as a
compatibility alias for older cards and reports, but both are advisory
baselines only. They are allowed to be wrong for the current foreground task.
`fresh_thread_action.py` owns the final `agent_action`, and every action result
records the packet hint, whether it was authoritative (`false`), and why the
final policy aligned with or diverged from it.

Public-safe first-turn demo cues such as "我觉得压力好大", "帮我妈妈挑个礼物",
"我想建个网站", and a fresh coding workspace with no `AGENTS.md` may produce
`soft_hypothesis` or `silent_scent` packets, depending on confidence and
candidate refs. They must not become first-turn private-history dumps. Specific
memory-backed claims require `source_reopen`; broad, sensitive, stale, or
superseded cues should stay `silent_scent` or `suppressed`.

`fresh_thread_action.py` owns the #284 agent-facing action policy for consuming
that packet. The hook prepares terrain; the foreground agent chooses one of
`ignore`, `use_silently`, `ask_light_question`,
`mention_soft_hypothesis`, `active_recall`, or `source_reopen` after considering
the current task. The packet's `advisory_action` (or legacy `suggested_action`
alias) is advisory; it must not force lookup when the agent cannot say memory
would change the answer, plan, or action. This layer must not parse the raw
prompt with a static semantic word list. Subconscious/semantic judgement enters
as packet fields, reviewed sidecars, active recall locks, or explicit agent
context such as `memory_may_change_answer`, `specific_memory_claim`,
`broad_or_sensitive_prompt`, and `user_confirmed_memory_theme`.

`task_context` is not a hidden prompt parser. Each flag belongs to one of these
provenance buckets:

- foreground agent or reviewed-sidecar judgement:
  `memory_may_change_answer`, `specific_memory_claim`,
  `broad_or_sensitive_prompt`, and `allow_gentle_hypothesis`;
- activation state: `user_confirmed_memory_theme`,
  `route_suppressed_by_activation`, `prior_scent_without_new_anchor`,
  `activation_state`, `activation_update`, `activation_invalidation`, and
  `activation_source_reopened`;
- deterministic repo/source checks: `current_checkout_required` and
  `current_repo_fact_query`.

Future flags must either fit one of those buckets or appear as unknown
provenance in the action-policy output until their owner is documented.

Action policy examples:

- Positive: a safe medium-confidence design/workflow preference scent that
  could change the next design decision should call `active_recall`; if a #277
  lock is `ready`, use that lock id as a route handle.
- Positive: a user-confirmed prior theme with a `pending` lock should call
  `active_recall` with `wait_or_probe_lock`, not present the pending lock as a
  fact.
- Positive: a profile/resume or other specific memory-backed claim with source
  refs should choose `source_reopen` before answering concretely.
- Negative control: a low-confidence, broad, or sensitive first-turn scent can
  stay `use_silently`; support the user or ask normally without exposing an old
  private theme.
- Negative control: `silent_scent` or no candidate refs should `ignore`; a
  generic creative or coding prompt should not become memory lookup by default.
- Negative control: `suppressed`, superseded, or high-risk packets should
  `ignore` and must not steer answer content, tone, or source reopening unless
  the user supplies a clearer low-risk memory intent.

#394 progressive MCP navigation can consume hook material without treating the
hook card as the whole memory surface. Ambient cards or future action-time
attention hints may carry a `navigation_seed` shaped like
`{"kind":"recall_context_seed","handle":"...","suggested_tool":"recall_deepen","boundary":"navigation_only_not_fact"}`.
The seed is a route handle only. It should be small, source-ref oriented, and
safe to deepen through MCP `recall_deepen`; it must not carry raw prompt text,
raw tool payloads, local filesystem paths, or final memory claims. #435-style
attention hints can use the same handle shape when a prepared cache wants the
foreground agent to reopen source before its next action.

#277 active recall locks are navigation handles, not evidence. A ready lock can
make `active_recall` cheaper; a pending lock can be probed or waited on by the
agent; expired or failed locks should be ignored and restarted only if memory
would change the answer, plan, or action. Any specific memory-backed claim still
requires clean-source reopen; scent packets, route reasons, locks, aliases, and
candidate refs are not enough.

`aippocampus_runtime.reflection.aar_v2` owns the #484 deterministic first slice
for action-time AAR nudges. It can propose a source-backed advisory nudge when
the next action is a specific memory/source claim from weak scent/candidate/dream
context, and it suppresses that nudge when clean source is already visible. The
nudge routes attention to source reopen; it is not evidence.

`aippocampus_runtime.recall.search_decision_adapter` applies the same boundary to external-search
workflows. It may decide that a degraded prompt is a cue into old source and
may return a source-ref-backed query expansion packet, but that packet remains
navigation material. Search terms, scent/candidate support, and candidate refs
must not be presented as remembered facts; after-search results are classified
for explicit import/review rather than written into memory automatically.

The runtime owner is `aippocampus_runtime.recall.active_recall_lock`. Lock
artifacts live beside the ambient thread cache as `active_recall_locks.json`.
They store prompt/workspace/thread fingerprints, topic epoch, registry freshness,
public-safe freshness-vector fingerprints, candidate refs, aliases, route
reasons, conflict flags, TTL, generation/version fields, consumer timing, and
aggregate ROI counters. They must not store raw prompts, raw source snippets,
absolute workspace paths, or model-generated factual claims. `active_recall.py
--mode probe|read` returns only scent/navigation data; `--mode reopen` is the
source-backed step that opens clean source by lock id; `--mode metrics` reports
public-safe aggregate lock ROI without prompts, source snippets, or local paths.

Active recall lock schema v2 makes lifecycle state observable without changing
the evidence boundary. `lock_version`, `enrichment_generation`,
`state_transition`, and consumer metrics let an agent detect whether it read a
pending generation, whether a later enrichment superseded that read, and
whether an expected version is too stale to reopen. `freshness_vector` compares
registry and optional navigation-sidecar stat fingerprints by source kind only,
not by raw path; topic epoch, registry changes, TTL expiry, version mismatch,
or freshness-vector changes must stop source reopen until the caller restarts
or rereads the route. Lock ROI summaries are aggregate counters/rates for
pulls, reopen attempts, source-backed hits, stale/wrong routes, pending reads,
expired-before-consumption, and never-read speculative locks. These metrics are
tuning evidence only: they do not prove public memory quality and do not turn
aliases, route reasons, or candidate refs into facts.

Enrichment policy is explicit. Use speculative enrichment only for cheap scent
or candidate-ref routes where latency would otherwise hide useful recall. Use
lazy-on-pull for broad, thread-only, low-confidence, or sensitive routes so
foreground hooks stay cheap and private. Use hybrid mode when the foreground
creates a pending lock and detached warm recall may later enrich it; consumers
must check the current version/freshness before reopening.

`fresh_thread_activation.py` owns the #283 progressive activation overlay that
keeps a scent from haunting later turns. It produces a compact
`fresh_thread_activation_state` snapshot for one `thread + workspace +
topic_epoch + route` with states `pending`, `scent_emitted`,
`soft_hypothesis`, `ignored`, `confirmed`, `rejected`, `source_backed`,
`retired`, and `suppressed`. The snapshot stores thread/workspace/route
fingerprints, counts, TTL, registry-freshness fingerprint, and optional #277
lock state/id. It must not store raw prompts, raw source snippets, local paths,
or durable preferences.

The activation state feeds `fresh_thread_action.py` only through explicit
context flags. `confirmed` may set `user_confirmed_memory_theme` so the agent
can perform deeper active recall; `rejected`, `suppressed`, topic shift,
registry freshness changes, or TTL expiry set `route_suppressed_by_activation`;
`ignored`, `scent_emitted`, and `soft_hypothesis` without a new user anchor set
`prior_scent_without_new_anchor`, keeping the old scent internal. `source_backed`
records that source was reopened once, but it still does not remove the normal
rule that any future specific memory-backed claim must reopen clean source.

Invalidation is intentionally conservative: `topic_epoch` changes retire the
old activation unless a later related-cache path explicitly proves strong
overlap; registry freshness changes mark the state stale until source is
reopened; weak first-turn states default to a short TTL, while confirmed or
rejected states may live as long as the ambient cache for the current topic
epoch. This overlay is not a second long-lived cache and must not be promoted to
formal memory.

`fresh_thread_demo.py` is the #285 public-safe demonstration runner for this
contract. It strings together the existing scent packet, action policy, and
activation state modules over synthetic upstream decision packets across
`no_memory`, `hook_only`, and `active_recall` arms. The runner is intentionally
not a semantic classifier: fixture inputs model reviewed sidecar or hook output,
so future semantic improvements still belong in the semantic/subconscious
layers. Treat its output as demo proof only; real-history quality, live model
quality, semantic classification quality, and benchmark claims need their own
evidence.

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
finish, but final `quorum_met` is now two-layer. `useful_signal_quorum_met`
records the old useful-scout threshold, while final `quorum_met` also requires
requested guard coverage. Required guard family states are `resolved`,
`blocked`, `missing`, `timed_out`, or `not_requested`; missing/timed-out guard
coverage withholds thread-cache writes instead of turning provisional cards
into next-turn ambient state. `--wait-all` belongs to explicit evaluation or
detached warming.
When sanitized prior prompt-trace rows already carry source refs, the warm path
may add one deterministic fallback card, but it must still pass the same local
source-ref validation and must not use the current prompt as memory.
Foreground code schedules background warming by default after non-skip cache
misses when the hook has a thread id and `DEEPSEEK_API_KEY` is available.
`ambient_warm_scheduler.py` writes a redacted local job file and starts a
detached `warm_ambient_recall.py --job-file` run. That job uses wait-all by
default with its own detached timeout (`AIPPOCAMPUS_DETACHED_WARM_TIMEOUT`,
default 45s) and writes only through the thread-cache writer, so late scout
results warm turn N+1 without making turn N wait. Use `--no-warm-background`
or `AIPPOCAMPUS_WARM_RECALL_BACKGROUND=0|false|off` to disable this on shared
machines or during provider-budget debugging; `--warm-background` remains an
explicit enable override.

Late warm results have only explicit handoff paths: next-turn thread ambient
cache, active recall lock enrichment, or a foreground agent's later active
recall pull. They must not silently affect the current turn after the hook has
returned. Cached cards replayed in turn N+1 should be marked
`provenance_class=cached_warm_card` and keep their prior source as
`cached_origin`, so a warm scout proposal or related-cache replay cannot look
like fresh source-backed evidence.

Foreground `UserPromptSubmit` must remain below the host hook timeout. The
installer keeps the Codex hook timeout at 5s and installs
`--max-elapsed-ms 4300 --semantic-timeout 2.5` by default so the Python process
can fail open before Codex hard-kills it. If the app reports
`hook timed out after 5s`, first run `diagnose_hooks.py --events
UserPromptSubmit --json` and check whether the installed command still carries
those budget flags. A missing prompt-hook debug log is not proof that nothing
happened: when the host kills the process at 5s, the hook may never reach its
sanitized logging path.

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
failure counts, scout error buckets, scout ROI classifications, and source-ref
pressure without exposing case rows. Benchmark and sweep metrics also expose
public-safe `scout_roi_by_lane` and `scout_roi_by_family` tables: useful
results, candidate-card proposals, accepted cards, accepted source-validated
evidence, guard/blocker contribution, late-useful results after the
useful-quorum cutoff, unobserved lanes, timeout/error rates, and token/cache
cost proxies when provider usage fields are available. Treat
`keep|watch|diagnostic_only` as human tuning evidence, not a public
product-quality claim and not an automatic lane-deletion policy. Scout prompts
keep `output_contract` as a compact schema and add family-aware output budgets
so Flash is not asked to fill a large template.
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
of waiting for provider cache construction. For detached wait-all jobs, keep
the default at 45s because they do not block the user; 15s is only the
foreground-style quorum-first floor, and the 100-case wait-all calibration
showed 30s as tight with read-timeout pressure.

Provider route metadata must remain visible in semantic/warm diagnostics:
`model_route` identifies provider, route, model, base URL, API-key env name,
and capabilities, while `cache` / `cache_diagnostics` distinguish DeepSeek
prefix-cache metrics from unsupported cache metrics. Non-DeepSeek
OpenAI-compatible routes are explicit fallback/privacy routes; they default to
no DeepSeek `user_id`, no DeepSeek `thinking`, no prefix-cache claim, and low
concurrency unless configured otherwise.

Warm recall result summaries expose public-safe guard and suppression
diagnostics through `guard_coverage`, `suppression_reason_buckets`, and
`suppression_diagnostics`. These buckets must come from runtime gates and
structured counts only: privacy/evidence scout families, required guard states,
current-thread echo count, source-validation statuses, topic-epoch suppression,
quorum status, and zero-card output. Do not derive these buckets from raw prompt
text, source text, local paths, or a static semantic keyword list.

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
- `python ...\install_aippocampus_prompt_hook.py status --last --json`
- `aippocampus hooks prompt status --last --json`

`warm_ambient_recall.py --json` is an operational summary, not a private
diagnostic dump: it reports status, counts, cache telemetry, and gate buckets
without raw prompts, scout rows, model route secrets, user ids, or raw cards.
It may expose public-safe `provenance_counts` and `support_level_counts`; those
are aggregate routing diagnostics, not evidence claims.
Local Python callers that need the full private result should import the
packaged runtime API inside a trusted process boundary.

Prompt-hook audit status uses the same public-safe boundary. The hook writes a
tiny local `aippocampus_prompt_hook_last_status.json` projection on every run,
separate from the opt-in verbose debug JSONL. `status --last --json` reports
whether the latest prompt produced `no_memory`, `scent`, `candidate`, or
`source_backed_evidence`, plus card counts, wayfinding/stale-source counts,
cache status, topic-epoch presence without the epoch value, warm-background
status, and a redacted event id. It must not emit raw prompt text, raw cards,
snippets, source titles, session/turn ids, secrets, topic-epoch values, or local
paths. `scent` and `candidate` remain navigation hints; even
`source_backed_evidence` still tells the agent to reopen clean source before
making exact claims. Use `--log`/`--log-path` only for trusted local debugging;
the audit projection is the surface intended for issue reports and demos.

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
`runtime recall`, and standalone `semantic_recall_gate.py` compatibility
commands can spend longer when the user asks for source-backed memory. The
implementation owner lives under `aippocampus_runtime.recall`; do not add new
foreground-recall policy to the top-level compatibility shims.

`prompt_recall_threshold.py` owns the #359 context-aware scent-threshold
diagnostic. It is a routing policy, not a source or evidence policy. A same
thread continuation with a stable topic epoch may lower the effective
`scent` threshold a little, and exact semantic-result reuse may lower it even
less. Broad fresh personal prompts, secret surfaces, and current-repo factual
prompts must not receive that lowering. The private hook result and public-safe
debug payload may expose `base_threshold`, `effective_threshold`, compact
`adjustments` reason codes, and `risk_boundary`; they must not include raw
prompt text or turn a low-risk scent into evidence. This connects the #201
vague-recall pain and the #281 fresh-thread goal without dumping more memory
into every prompt.

Foreground Python callers should use `run_semantic_gate_for_prompt` or pass
`foreground=True` with both `deadline_seconds` and a per-worker `timeout` no
larger than that deadline. Missing or looser foreground budgets fail open with a
`foreground_budget` diagnostic and no external model call. Standalone/background
semantic-gate callers intentionally keep the quality-first default.

When an explicit memory cue already has local association or working-memory
overlap, the prompt hook skips the external semantic gate and goes straight to
local evidence. This protects hook latency without removing the deeper semantic
path for fuzzy or cross-lingual prompts.

The prompt hook can also read `cognitive_map.json`. Cognitive-map routes are
materialized from detached DeepSeek subconscious jobs, so a route match is
already prior semantic work and should skip foreground DeepSeek spend. The hook
uses those routes only as `scent`: they can add query terms and candidate
threads, but they are never evidence by themselves.

Cue-to-evidence upgrades are intentionally two-stage. Natural requests such as
"上次关于 X 的结论是什么" or "找一下之前说 X 的那段" may open a tiny
clean-source evidence probe even when they do not use formal words like
"原文" or "引用". Fuzzy personal/status prompts should not be hard-blocked by
foreground lexical rules; instead, the semantic/subconscious gate may authorize
an evidence probe when it returns a high-confidence, low-risk recall context.
That semantic signal is still only routing: the hook may inject evidence only
after local clean-source/SQLite hits pass quality filtering. Prefer
`final_answer` and visible user turns over process carriers such as
`<subagent_notification>`; process noise can remain auditable in source but
should not be the first evidence card when better human-facing source exists.

## Semantic Gate

When `DEEPSEEK_API_KEY` is present and `AIPPOCAMPUS_SEMANTIC_GATE` is not `off`,
the prompt hook may call the packaged semantic gate through
`aippocampus_runtime.recall.semantic_recall_gate`; the top-level
`scripts/semantic_recall_gate.py` path remains a direct-script compatibility
command. The semantic gate runs small parallel workers:

- `gate`: choose `skip`, `scent`, or evidence-worthy recall.
- `alias`: generate multilingual and paraphrase search aliases.
- `scope`: choose current project, registered threads, or working memory, and
  catch over-personalization risk.

The semantic gate only proposes queries and scope. Evidence still has to come
from local source search.
Worker disagreement is resolved conservatively: if any worker reports high
anti-personalization risk, the aggregate semantic decision is capped below
`evidence` and the private result records the winning worker, risk worker, and
cap reason. A later source bridge may still find evidence, but the semantic
gate itself must not silently escalate high-risk scope disagreements.

When semantic-gate aliases repeatedly lead to local source-backed candidates,
the hook may record them in `$CODEX_HOME/aippocampus-registry/semantic_cues.jsonl`.
This is a multilingual cue cache, not a fact store: cues are promoted only after
repeated hits with source refs, demoted when false positives accumulate, and fed
back into the semantic gate's trigger catalog as search hints.
The exact semantic result cache, `semantic_recall_cache.json`, is separate: it
is a hashed prompt/result optimization with TTL, hit/miss/expired/write/eviction
telemetry, and value-aware max-entry eviction. Entries keyed through the
source-backed cue sidecar can be protected from low-value churn, but the cached
aliases remain routing hints only. `semantic_recall_gate.py --cache-report
--json` and `semantic_cue_cache.semantic_cue_cache_report()` expose count-only
diagnostics; they must not emit raw prompt text, cue text, source snippets, or
local paths.
Active `semantic_cues.jsonl` rows and reviewed `semantic_triggers.jsonl` rows
also feed the hook's local pre-gate and query seed terms. This is the intended
replacement path for semantic proxy word lists in
`aippocampus_runtime.recall.prompt_cues` and
`aippocampus_runtime.recall.query_policy`: static cues stay as a compact
bootstrap/fallback, while repeated or reviewed multilingual paraphrases live in
sidecar data. `aippocampus_runtime.recall.semantic_trigger_router` also ships a
small reviewed seed sidecar for AIppocampus-specific memory architecture terms,
and onboarding refreshes it into the private registry's
`semantic_triggers.jsonl`. Keep future domain-semantic additions there or in
reviewed promotion candidates, not in Python phrase lists. Active reviewed seed
rows must carry `reviewed_at`, `review_note`, a `reviewer` or `review_source`,
and either source refs or a reviewed-seed rationale explaining why public
AIppocampus vocabulary is allowed without source refs. The router migrates
legacy trigger ids to longer SHA-256 ids, retains legacy ids for compatibility,
canonicalizes aliases, drops semi-generic phrases, caps per-trigger aliases, and
reports aggregate alias/seed diagnostics.

The local pre-gate avoids unnecessary external calls. Obvious code-surface
prompts such as "fix dashboard hover and run tests" should not call the semantic
model just because registry associations contain broad terms. Explicit recall,
working-memory matches, and strong source-backed triggers bypass this brake.
For code-surface prompts, reviewed triggers may still provide scent when the
user explicitly asks to continue prior context, but short single-entity overlap
such as `Atlas` alone is not enough.

Multilingual behavior should be semantic, not a pile of hard-coded words.
Non-English natural-language prompts in Russian, Arabic, Japanese, Korean, Thai,
Spanish, French, German, Portuguese, and similar languages can reach the
semantic gate when they look like memory questions. Short daily chatter and
simple commands such as "好，开干" should not become triggers.

Useful commands:

- `python ...\semantic_recall_gate.py --prompt "那个脑内续接器现在怎么样了？" --cwd "$PWD" --json`
- `python ...\semantic_trigger_router.py --json`
- `python tools\aippocampus\smoke\smoke_prompt_hook_latency.py --runs 5 --json`

The latency smoke wraps the prompt hook in subprocesses and reports only
sanitized timing buckets. Read `wall_ms` beside `hook_elapsed_ms` and
`startup_import_io_ms` to separate Python startup/import/I/O overhead from the
recall work that the hook reports internally. This is especially important on
Windows before changing foreground budgets.

## Redaction And Logging

Prompt-time external-model calls must redact credential-like substrings before
the model sees them:

- API keys, bearer tokens, cookies, password-like assignments
- credentialed URLs and connection-string secrets
- private-key blocks

Private-key block contents must never be sent to the model. Mixed prompts may
continue after replacing the block with `<redacted:private-key-block>` when
enough non-secret context remains; mostly credential/key material still
hard-skips. Local paths are replaced with `<redacted:local-path>` plus bounded
`<path-anchor ...>` hints such as file class and extension. Stable path hashes
are emitted only for paths confirmed under the current project root and are
derived from the project-relative path; external machine-local paths do not get
a stable hash. These anchors are navigation hints only, not source truth and not
permission to emit raw absolute paths.

Do not write prompt text to hook debug logs. Optional logs may record decision,
timing, candidate thread ids/titles, evidence line numbers, and query aliases.

The prompt hook records a small local aggregate skip-telemetry file by default:
`aippocampus_prompt_hook_skip_telemetry.json` under the active AIppocampus
registry directory. This is not a prompt log. It stores counts for skip reason
buckets, semantic availability diagnostics, cache status, warm-background
status, platform/Python version, configured budgets, and coarse latency
buckets. It must not store raw prompts, session ids, query aliases, source
snippets, or thread titles. Use `--log-skip` only for explicit deep debugging
when a sanitized per-event row is needed. Set
`AIPPOCAMPUS_PROMPT_SKIP_TELEMETRY=0` or pass `--no-skip-telemetry` to disable
even the aggregate file.

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
