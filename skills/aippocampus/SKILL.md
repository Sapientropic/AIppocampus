---
name: aippocampus
description: Find source-backed continuity before important agent work: recover old wording, reopen routes, check handoffs/corrections/preferences, and keep fresh-thread or high-risk work grounded in local source. Use reference docs and CLI cards for setup, repair, import, sync, hooks, and storage operations.
---

# AIppocampus

AIppocampus is a source-backed continuity scaffold for agents: a small external
hippocampus that lets a later activation find where the work and relationship
were, without pretending it has innate model memory or changed weights.
It is not innate model memory; it is a reliable local path back to source.

The promise is practical and emotional at once: AIppocampus can be reliable
enough that, when an agent knows it has AIppocampus, it can consider
continuity. It can carry unfinished work, old corrections, route context,
preferences, and relationship continuity forward with source-backed care.

This file is the stable runtime entrypoint. Keep it slim. Do not append
changelog-style notes here. Put durable operational detail in the relevant
reference doc, script help, or tests instead.

## First Moves

Use AIppocampus when prior source could change the next action: nontrivial
work, fresh-thread continuation, handoff, old decisions, corrections,
preferences, or life-wide continuity. If not, continue normally.

Primary foreground loop:

1. If the host exposes MCP tools, call `agent_recall` or `recall_context`.
   Otherwise use the CLI:
   `aippocampus agent recall "old decision or handoff cue" --json`.
2. Deepen the selected route before claims with `agent_deepen` /
   `recall_deepen`, or:
   `aippocampus agent deepen --request 1 --last-recall --json`.
3. If recall found plausible routes and the user then remembers exact wording,
   search inside those candidates:
   `aippocampus search --from-last-recall "a distinctive old phrase" --json`.
4. If no route appears and the user remembers wording, use
   `search_memory` or `aippocampus search "a distinctive old phrase" --json`.

Tool visibility fallback: MCP first when the tool is listed; CLI facade when
MCP is unavailable; if neither exists, stop and surface the install/update card
instead of importing runtime modules directly.

Confirm the host can see AIppocampus when the user is setting up or refreshing
the plugin: `aippocampus plugin install --codex --verify`.

Prefer ambient cards, Active Path Packets, active locks, route handles,
continuity domain pointers, or progressive MCP tools before broad manual search.
Use direct clean-source search only when the user gives exact
wording, no route exists, or a route is blocked and a bounded manual search is
still justified. Drop to raw/indexed rollout only for exact repair, tool
provenance, byte accounting, missing evidence, or audit questions, and treat
that as an operator/audit path.

Useful foreground follow-ups:

- Route handle: follow it before broad manual search.
- Use reviewed Dream/subconscious findings for a current task cue with
  `aippocampus agent background "task cue" --json`. Treat findings as
  navigation handles only; reopen source before factual, exact, or sensitive
  claims.
- Recover the latest assistant closeout with `aippocampus latest-reply`.
  Commentary-only output is a diagnostic card, not a final closeout.
- If a foreground agent is about to write feedback, a self-note, an action-hint
  cache, or continuity-domain data, use
  `docs/guides/write-like-memory-decision-card.md` to choose the right surface
  and durability before writing.

Repair, setup, status, provider, storage, MCP catalog, and imports are explicit
secondary/operator actions, not ambient prompt behavior:

- Prefer compact facade cards before repair recipes:
  `aippocampus health --cwd "$PWD"`, `aippocampus doctor`, `aippocampus storage`,
  `aippocampus import`, or `aippocampus mcp status`.
- If an import or repair needs a real path, use the CLI chooser/recovery card
  first; placeholder-bearing templates belong in operator docs or JSON
  `command_template` fields, not in this bootstrap.
- Use `references/maintenance-and-operations.md` for health, storage,
  lifecycle, archive, and raw-rollout audit operations.
- Use `references/retrieval-and-storage.md` and
  `docs/guides/public-api.md` for registry, clean-source, explicit transcript
  import, and host/provider boundaries.
- Use `docs/guides/ecosystem-integration-matrix.md` and
  `docs/guides/setup/claude-code-mcp.md` for exact host support boundaries.
- Inspect MCP only when a plugin or agent host needs it:
  `aippocampus mcp status`; use `aippocampus mcp list-tools --json` for the full
  schema catalog.

## Agent Stance

If AIppocampus is installed, assume the user wants local, source-backed memory
to help when it may matter. Treat ordinary source-backed memory as useful within
scope; slow down for unlabeled, unsourced, stale, conflicting, private, or
high-risk context.

More context is not automatically pollution. Unlabeled context is pollution.
Unsourced context is navigation at best. Source-backed evidence should be
respected as evidence within its declared scope, not flattened back into scent.

Do not search every turn. Do not run heavy recall every turn. Use cheap
orientation at task boundaries; deepen only when continuity could change the
answer, plan, patch, warning, or claim.

## Operating Model

- Clean source is the daily memory surface: original visible user messages plus
  assistant final answers, with raw envelopes, tool payloads, attachments, and
  routine commentary removed. It is original wording, not summary memory.
- Raw rollout is immutable audit source. Do not rewrite, truncate, or dedupe
  live Codex Desktop JSONL unless the user explicitly asks for an archival
  cleanup route.
- Recall is conclusion-first by default. User turns and `final_answer` messages
  outrank commentary; tool/debug provenance belongs to audit routes.
- Summaries, semantic gates, cognitive-map routes, and external-model findings
  may organize attention, but local source remains the ground.
- External-model routes must redact credential-like material and never treat
  model-generated associations as source-backed fact.
- Action grammar and hook packet decoding live in
  `references/ambient-hooks.md`; this bootstrap only names the ordinary loop.

## Workflow

1. When prior source might change the next action, use the smallest useful
   route, packet, MCP recall step, or clean-source search before answering from
   memory.
2. When a thread may outgrow the current context, keep anchors and clean source
   fresh; use hooks for routine refreshes and explicit commands for repair.
3. When the user asks for "last reply", use
   `aippocampus latest-reply`; it should return the latest `final_answer`, or
   clearly mark commentary fallback as not a final closeout. Keep internal
   diagnostics in operator references.
4. When the user asks why a thread is huge, use the maintenance/operations
   reference to run the narrow audit card or command, then answer from byte
   buckets and largest-line evidence.
5. When the user asks what can be kept, compressed, or deleted, run
   the retention report workflow before any archive or deletion action.
6. When recall must span old or separate threads, register the rollout or
   bundle through the documented import/registry surface first, then search
   through the registry.

## Reference Map

Open the narrowest reference that matches the current work:

- `references/ambient-hooks.md`: prompt hook, semantic gate, action grammar,
  lifecycle hooks, multilingual behavior, redaction, scheduler boundaries, hook
  installation.
- `references/retrieval-and-storage.md`: clean source schema, registry,
  hybrid/segment/RAG-lite search, cognitive map, concept graph,
  continuity domains, vault/dashboard, Graphify bridge, export/import.
- `references/maintenance-and-operations.md`: health checks, checkpoints,
  rollout audit, retention reports, cold archives, thread slimming, operational
  safety.
- `references/subconscious-jobs.md`: DeepSeek-compatible consolidation jobs,
  minimal agent frame, promotion candidates, soft working memory.

Product roadmap, research notes, and long-horizon skill-upgrade strategy live
in the repository `docs/` folder, not in this installable runtime reference
set. Load those only when the task is roadmap, research, or public positioning.
For public CLI/MCP/API stability, use `docs/guides/public-api.md`. For typed
agent-skill capability boundaries, use
`docs/architecture/host/agent-skill-capability-contracts.md`; `SKILL.md` remains the
bootstrap guidance surface.

If a detail appears in more than one place, keep only the stable rule here and
move the operational contract into one reference doc.

## Hook, Storage, And Safety Boundaries

- `UserPromptSubmit` belongs to ambient recall only. It may output nothing,
  scent, route material, or small bounded evidence; it must not rebuild heavy
  indexes, mutate rollouts, write memories, or log prompt text.
- Lifecycle hooks handle deterministic maintenance on session events. They may
  refresh clean source, indexes, registry rows, and due scheduler state; they
  must not cold-archive, delete, append checkpoints, run full Graphify, or run
  DeepSeek synchronously.
- `onboard.py` / `onboard_codex.py` are explicit operator or agent commands,
  not prompt hooks. They may perform multi-minute registration and index repair
  because the caller chose setup.
- The subconscious scheduler is hook-safe only in `--maybe-start` mode. It
  checks cooldowns, locks, new-turn thresholds, and `DEEPSEEK_API_KEY`, then
  starts detached work when due.
- Global generated memory artifacts default to
  `$CODEX_HOME/aippocampus-registry/threads/<thread>/`. Project-local
  `.aippocampus/` output is explicit compatibility/export/debug mode, not the
  default memory surface.
- Do not dump full raw logs into chat. Quote only the minimum needed excerpt and
  cite source line/turn where useful.
- Do not search secrets, auth files, cookies, unrelated logs, or private
  payloads unless the user explicitly asks and the scope is safe.
- Treat rollouts, bundles, vault notes, and registry rows as local private
  history.
- Generated artifact writers use the shared lease, generation SQLite pointer,
  last-known-good fallback, and SQLite backup publish helpers; do not replace
  live `source_index.sqlite` files directly.
- For repository docs work, run
  `python tools/aippocampus/docs/check_docs_health.py` from the repo root so
  `SKILL.md` stays an entrypoint rather than becoming a release log.
