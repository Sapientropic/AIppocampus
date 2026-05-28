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
fingerprints, avoids raw prompt text, and is safe to discard. Later warm-scout
work should update this cache through the same serial writer rather than adding
a second ambient-memory store.

`warm_ambient_recall.py` is the standalone warm-path prototype for that later
work. It defines 10 scout families across 5 candidate-window/query variants,
runs the resulting 50 lanes concurrently, isolates malformed scout output,
merges at most 3 cards, and writes through `ambient_thread_cache.py`. It also
dereferences candidate source refs against clean-source messages when possible,
suppresses current-thread-only echoes by default, and lets scouts vote
`reuse|rotate|suppress` for topic epoch handling. It is not part of the default
foreground hook path: quorum-first runs are allowed to return before all lanes
finish, and `--wait-all` belongs to explicit evaluation or detached warming.

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
- `python ...\install_aippocampus_prompt_hook.py install|status|uninstall`

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
