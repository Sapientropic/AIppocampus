---
name: aippocampus
description: Use when recovering source-backed Codex conversation memory, recalling old thread wording, continuing after context compaction, building clean-source memory from raw rollouts, installing ambient recall hooks, searching or registering AIppocampus indexes, or auditing long Desktop session growth.
---

# AIppocampus

AIppocampus is a source-backed memory layer for Codex conversations. Use it when
the task depends on old-thread wording, continuity after compaction, clean
conversation source, ambient recall hooks, or long-session storage/audit work.

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

## First Moves

Use `$CODEX_HOME/skills/aippocampus/scripts` as the script root.

- Find the current rollout: `python .../locate_rollout.py --cwd "$PWD"`.
- Build the daily source layer: `python .../build_clean_source.py --cwd "$PWD"`.
- Build or refresh the index: `python .../build_index.py --cwd "$PWD"`.
- Check state before/after long work: `python .../aippocampus_health.py --cwd "$PWD"`.
- Recover the latest assistant closeout: `python .../latest_reply.py --cwd "$PWD"`.
- Search clean source first: `python .../search_clean_source.py "query" --cwd "$PWD"`.
- Search raw/indexed rollout when clean source is insufficient:
  `python .../search_rollout.py "query" --cwd "$PWD" --build-index --mode hybrid`.
- Run the deterministic recall gate for vague continuity prompts:
  `python .../active_recall.py "query" --cwd "$PWD" --search auto`.
- Inspect the local MCP tool surface for plugin/agent clients:
  `python .../aippocampus_mcp_server.py --list-tools`.
- Check or exchange a local-folder sync bundle:
  `python .../sync_bundle.py status --sync-dir "<folder>" --json`.
- Check an HTTP object-storage sync bundle:
  `python .../sync_object_storage.py status --object-store-url "<url>" --object-prefix "<prefix>" --json`.
- Manage encrypted sync device keys or plaintext migration:
  `python .../encrypted_sync_admin.py key list --registry-dir "<registry>" --json`.
- First-install / full-machine onboarding:
  `python .../onboard_codex.py --all --format json`. This is the preferred
  agent entrypoint for registering local Codex sessions, repairing missing
  indexes, rebuilding project timeline, and refreshing cognitive-map sidecars.
- Discover other registered threads: `python .../registry.py list` or
  `python .../registry.py search "terms"`.
- Register an old rollout: `python .../registry.py register-rollout --rollout "<rollout.jsonl>" --project "<label>"`.
- Scan local sessions for unregistered threads:
  `python .../registry.py scan-sessions --dry-run`, then rerun without
  `--dry-run` when the candidates look right.

Prefer clean-source search for normal recall. Drop to raw rollout only for exact
repair, tool provenance, byte accounting, missing evidence, or audit questions.

## Workflow

1. If the user asks about previous context, derive a few distinctive terms and
   search clean source or registry before answering from memory.
2. When a thread may outgrow the current context, keep anchors and clean source
   fresh; use hooks for routine refreshes and explicit commands for repair.
3. When the user asks "last reply", use `latest_reply.py`; it should return the
   latest `final_answer`, or clearly mark commentary fallback.
4. When the user asks why a thread is huge, run `rollout_size_audit.py`; answer
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
- `onboard_codex.py` is an explicit operator/agent command, not a prompt hook.
  It may perform multi-minute registration and index repair because the caller
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
- Generated artifact writers use the shared lease, versioned SQLite pointer,
  last-known-good fallback, and SQLite backup publish helpers; do not replace
  live `source_index.sqlite` files directly.
- For repository docs work, run
  `python tools/aippocampus/docs/check_docs_health.py` from the repo root so
  `SKILL.md` stays an entrypoint rather than becoming a release log.
