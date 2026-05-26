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

Useful commands:

- `python ...\aippocampus_prompt_hook.py --prompt "hook 机制像人类联想" --json`
- `python ...\simulate_prompt_hook.py --cwd "$PWD" --strict`
- `python ...\simulate_prompt_hook.py --cwd "$PWD" --compare-concept-graph`
- `python ...\simulate_multilingual_prompt_hook.py --cwd "$PWD"`
- `python ...\install_aippocampus_prompt_hook.py install|status|uninstall`

The global prompt hook has a small foreground budget. Its default
`--semantic-timeout` is lower than the standalone semantic gate so optional
semantic work cannot consume the whole Codex `UserPromptSubmit` timeout. Do not
raise this default unless the hook timeout is raised and fresh, uncached memory
prompts still complete within budget.

The foreground default is three seconds. Treat that as a scent/cache pass, not
as the full recall budget; explicit `active_recall.py`, `runtime recall`, and
standalone `semantic_recall_gate.py` can spend longer when the user asks for
source-backed memory.

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
- `python ...\install_aippocampus_lifecycle_hook.py install|status|uninstall`

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
hook. `subconscious_jobs.py` can run multiple job/sample calls concurrently, but
staging JSONL and sidecar materialization remain serialized and atomic.

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
