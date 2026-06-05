---
name: aippocampus
description: Use early when nontrivial, fresh-thread, handoff, old-decision, correction, preference, life-wide, risky, repeated, high-cost, or continuity-sensitive work could change after a source-backed orientation check. Also use for recovering old wording, building clean source, ambient recall hooks, indexes, registry, sync, MCP access, and long Desktop session audits.
---

# AIppocampus

AIppocampus is a source-backed memory layer for Codex conversations. Use it
early for nontrivial, fresh-thread, handoff, old-decision, correction,
preference, life-wide, or continuity-sensitive work where a cheap orientation
could change the next move. Also use it when the task depends on old-thread
wording, clean source, ambient recall hooks, or long-session storage/audit work.

Keep this file as the stable entrypoint. Do not append changelog-style notes
here; update the relevant reference doc, script help, or tests instead.

## Operating Model

- Raw rollout is the immutable audit source. Do not rewrite, truncate, or dedupe
  live Codex Desktop JSONL unless the user explicitly asks for an archival
  cleanup route.
- Clean source is the daily memory surface: original visible user messages plus
  assistant final answers, with raw envelopes, tool payloads, attachments, and
  routine commentary removed. It is original wording, not summary memory.
- Recall is conclusion-first by default. User turns and `final_answer` messages
  outrank commentary; tool/debug provenance belongs to audit routes.
- Ambient hook output is a hint, not proof. A `scent` can tell the model old
  memory may exist; only clean-source, SQLite, or raw-rollout hits are evidence.
- DeepSeek-compatible semantic gates and subconscious jobs may organize queries,
  candidate associations, and cognitive-map routes, but local source remains
  the authority.
- External-model routes must redact credential-like material and never treat
  model-generated associations as source-backed fact.

## Proactive Recall Policy

Do not wait for the user to say "remember." At task boundaries, after context
loss, or before risky, repeated, cross-thread, high-cost, nontrivial, or
continuity-sensitive work, run cheap task-boundary orientation when prior
source-backed context could change the next action. Treat the result as routing,
not truth, until source is reopened.

Consider AIppocampus before acting when the prompt or task includes:

- vague continuity cues such as "last time," "that issue," "continue," or
  "same as before";
- repeated rejected routes, known user corrections, old decisions, preferences,
  life-wide commitments, or operation facts that could change the next action;
- compaction, fresh-thread, device, branch, or workspace boundaries where the
  current context may have lost the active constraint;
- high-risk memory-backed statements, quotes, privacy-sensitive claims, or
  decisions where being wrong is expensive;
- old source that might have been superseded, contradicted, or made local-only.

Use the smallest useful ladder:

- L0 no-op: low-risk one-off work with no continuity cue.
- L1 orientation: ambient cards, Active Path Packets, active locks, registry
  titles, route cache, familiarity cards, or known rejected-route handles.
- L2 context: `recall_context`, `recall_deepen`, `get_turn_context`,
  `search_memory`, registry search, or clean-source search to gather candidate
  source refs.
- L3 source reopen: required before quoting old wording, warning, blocking,
  asserting operation facts, or making high-risk claims.
- L4 ask/defer: source is thin, stale, conflicting, private, regulated, or not
  safely reopenable.

Prefer progressive MCP tools such as `recall_context`, `recall_deepen`,
`get_turn_context`, and `search_memory` when an agent client has them; use the
`aippocampus` facade or package modules below as portable fallbacks. Proactive
checks are normally private: surface them to the user only when they change the
next action, prevent a likely mistake, or the user asks for continuity.

Do not search every turn. Do not run heavy recall every turn. Use cheap orientation at task boundaries; deepen only when a route could change action.

## First Moves

Use `aippocampus` after package install. In a raw skill checkout, run package
modules from `$CODEX_HOME/skills/aippocampus/scripts` or put that directory on
`PYTHONPATH`.

Orient:

- Prefer ambient cards, Active Path Packets, active locks, or progressive MCP handles before inventing broad manual searches.
- Check state before/after long work: `aippocampus health --cwd "$PWD"`.
- Check the selected provider without writing artifacts: `aippocampus onboard --provider codex --status`.
- Find the current rollout when you need exact source location: `python -m aippocampus_runtime.source.locate_rollout --cwd "$PWD"`.
- Recover the latest assistant closeout: `python -m aippocampus_runtime.source.latest_reply --cwd "$PWD"`.

Recall:

- Search clean source first: `aippocampus search "query" --cwd "$PWD"`.
- Run the deterministic recall gate for vague continuity prompts:
  `python -m aippocampus_runtime.recall.active_recall "query" --cwd "$PWD" --search auto`.
- Search raw/indexed rollout only when clean source is insufficient:
  `python -m aippocampus_runtime.recall.rollout_search "query" --cwd "$PWD" --build-index --mode hybrid`.
- Discover other registered threads:
  `python -m aippocampus_runtime.registry.api list` or
  `python -m aippocampus_runtime.registry.api search "terms"`.

Guard / repair:

- Build the daily source layer:
  `python -m aippocampus_runtime.source.clean_source --cwd "$PWD"`.
- Build or refresh the index:
  `python -m aippocampus_runtime.recall.index_builder --cwd "$PWD"`.
- First-install / full-machine onboarding:
  `aippocampus onboard --provider codex --all --format json`. This registers
  local Codex sessions, repairs missing indexes, rebuilds project timeline, and
  refreshes cognitive-map sidecars only because the caller chose setup.
- Register an old rollout:
  `python -m aippocampus_runtime.registry.api register-rollout --rollout "<rollout.jsonl>" --project "<label>"`.
- Scan local sessions for unregistered threads:
  `python -m aippocampus_runtime.registry.api scan-sessions --dry-run`, then
  rerun without `--dry-run` when the candidates look right.

Agent-host / operator surfaces:

- Inspect MCP only when a plugin or agent host needs it:
  `aippocampus mcp list-tools`.
- Check or exchange a local-folder sync bundle:
  `aippocampus sync status --sync-dir "<folder>" --json`.
- Check an HTTP object-storage sync bundle:
  `aippocampus object-sync status --object-store-url "<url>" --object-prefix "<prefix>" --json`.
- Manage encrypted sync device keys or plaintext migration:
  `python -m aippocampus_runtime.sync.encrypted.admin key list --registry-dir "<registry>" --json`.
Prefer clean-source search for normal recall. Drop to raw rollout only for exact
repair, tool provenance, byte accounting, missing evidence, or audit questions.

## Workflow

1. If old context might change the next action, derive a few distinctive terms
   and run the smallest useful orientation or recall step before answering from
   memory.
2. When a thread may outgrow the current context, keep anchors and clean source
   fresh; use hooks for routine refreshes and explicit commands for repair.
3. When the user asks "last reply", use `aippocampus_runtime.source.latest_reply`;
   it should return the latest `final_answer`, or clearly mark commentary fallback.
4. When the user asks why a thread is huge, run `aippocampus_runtime.ops.rollout_size_audit`; answer
   from byte buckets and largest-line evidence.
5. When the user asks what can be kept, compressed, or deleted, run
   `retention_report.py --write` before `cold_archive.py`.
6. When recall must span old or separate threads, register the rollout or bundle
   first, then search through the registry.
7. When fuzzy, multilingual, or associative prompts need help, rely on the
   prompt hook and semantic trigger layer as a cue; verify with source hits
   before making claims.

## Reference Map

Open the narrowest reference that matches the current work:

- `references/ambient-hooks.md`: prompt hook, semantic gate, lifecycle hooks,
  multilingual behavior, redaction, scheduler boundaries, hook installation.
- `references/retrieval-and-storage.md`: clean source schema, registry,
  hybrid/segment/RAG-lite search, cognitive map, concept graph,
  vault/dashboard, Graphify bridge, export/import.
- `references/maintenance-and-operations.md`: health checks, checkpoints,
  rollout audit, retention reports, cold archives, thread slimming, operational
  safety.
- `references/subconscious-jobs.md`: DeepSeek-compatible consolidation jobs,
  minimal agent frame, promotion candidates, soft working memory.

Product roadmap, research notes, and long-horizon skill-upgrade strategy live
in the repository `docs/` folder, not in this installable runtime reference
set. Load those only when the task is roadmap, research, or public positioning.
For public CLI/MCP/API stability, use `docs/guides/public-api.md` in the repository.
For typed agent-skill capability boundaries, use
`docs/architecture/agent-skill-capability-contracts.md` in the repository;
`SKILL.md` remains the bootstrap guidance surface.

If a detail appears in more than one place, keep only the stable rule here and
move the operational contract into one reference doc.

## Hook Boundaries

- `UserPromptSubmit` belongs to ambient recall only. It may output nothing,
  `scent`, or small source-backed `evidence`; it must not rebuild heavy indexes,
  mutate rollouts, write memories, or log prompt text.
- Lifecycle hooks handle deterministic maintenance on session events. They may
  refresh clean source, indexes, registry rows, and due scheduler state; they
  must not cold-archive, delete, append checkpoints, run full Graphify, or run
  DeepSeek synchronously.
- `onboard.py` / `onboard_codex.py` are explicit operator/agent commands, not prompt hooks.
  They may perform multi-minute registration and index repair because the caller
  chose that setup flow. Keep hooks on the cheap maintenance path.
- The subconscious scheduler is hook-safe only in `--maybe-start` mode. It
  checks cooldowns, locks, new-turn thresholds, and `DEEPSEEK_API_KEY`, then
  starts detached work when due.

## Storage And Search

- Global baseline: generated clean source, `source_index.sqlite`, graph
  metadata, and optional segment indexes default to
  `$CODEX_HOME/aippocampus-registry/threads/<thread>/`.
- Project-local `.aippocampus/` output is explicit compatibility/export mode,
  not the default memory surface.
- Machine-wide discovery: `$CODEX_HOME/aippocampus-registry/threads.json`,
  associations, cognitive map, concept graph, semantic triggers, and
  working-memory staging.
- For large threads, keep monolithic indexes as the portable baseline and add
  `build_segments.py` / `search_segments.py` when health says segments are due.
- Embeddings, Graphify, DWM-style token-location indexes, and LLM consolidation
  are optional adapters. They must join back to stable `message_id`/`turn_id`
  source keys instead of replacing exact source.

## Safety Rules

- Do not dump full raw logs into chat.
- Quote only the minimum needed excerpt and cite source line/turn where useful.
- Do not search secrets, auth files, cookies, unrelated logs, or private payloads
  unless the user explicitly asks and the scope is safe.
- Treat rollouts, bundles, vault notes, and registry rows as local private
  history.
- Generated artifact writers use the shared lease, generation SQLite pointer,
  last-known-good fallback, and SQLite backup publish helpers; do not replace
  live `source_index.sqlite` files directly.
- For repository docs work, run
  `python tools/aippocampus/docs/check_docs_health.py` from the repo root so
  `SKILL.md` stays an entrypoint rather than becoming a release log.
