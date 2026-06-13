---
name: aippocampus
description: Use early when nontrivial, fresh-thread, handoff, old-decision, correction, preference, life-wide, risky, repeated, high-cost, or continuity-sensitive work could change after source-backed continuity orientation. Also use for recovering old wording, clean source, ambient recall hooks, indexes, registry, sync, MCP access, and long Desktop session audits.
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

## Agent Stance

If AIppocampus is installed, assume the user wants local, source-backed memory
to help when it may matter. Do not treat every memory use as suspicious by
default; treat unlabeled, unsourced, stale, conflicting, private, or high-risk
context as suspicious.

Before nontrivial work, fresh-thread work, handoff, correction-sensitive work,
old-decision work, or life-wide continuity work, ask one question:

Could old source, old corrections, unfinished work, route context, user
preferences, or relationship context change what I should do next?

- If no, continue normally without ceremony.
- If yes, consume the smallest useful continuity packet or route first.
- If a route already exists, follow it before broad manual search.
- If a continuity domain pointer exists, treat it as a durable route back to
  the source trail, not as a fact to repeat.
- If exact wording, sensitive facts, conflicts, stale claims, or high-risk
  action are involved, reopen source or use bounded evidence before claiming.

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

## Memory Packet Action Grammar

Packets should tell the foreground agent what kind of action they support. This
`action grammar` is the #786 projection from packet trust state; it is not a
second scoring layer and should not force rigid behavior.

| Grammar | How To Use It |
|---|---|
| `direction_only` | Background, scent, or semantic wayfinding. It may shape attention, but it cannot support factual claims. |
| `direction_with_ref` | Source-ref-backed candidate direction. It may shape route, depth, or question choice; reopen source before factual claims. |
| `reopenable_route` | Use the packet's route refs, lock id, or reopen plan before broad manual search. Do not answer from the packet itself. |
| `bounded_evidence` | Usable within the packet's declared scope. Reopen or deepen for exact quotes, wider context, conflicts, sensitive facts, or high-risk claims. |
| `source_open` | Source is already open to the host; exact wording may be used only within scope and redaction boundaries. |
| `ignore_or_blocked` | Privacy, stale, conflict, missing-source, or high-risk boundary. Do not let it shape answer content except to report/defer when that boundary matters. |

## Hook Packet Decoder

Hook packets are action hints, not facts. Decode the packet into the smallest
safe next action:

| Signal | Default action | Do not do |
|---|---|---|
| `suggested_agent_action=agent_recall`, `lead_kinds`, or `budget=recall_top_2` | Call recall/deepen or follow the provided route before broad manual search. | Treat the packet itself as evidence. |
| `not_enough_for_claim=true` | Use it as route/context only until source is reopened. | Make factual, public, numeric, stale, sensitive, or high-risk claims. |
| `direction_only` | Let it shape low-risk attention or the next search question. | Repeat it as a fact or overfit the answer to it. |
| `direction_with_ref` or `reopenable_route` | Follow refs, route handles, Active Path Packets, lock ids, or reopen plans; deepen/reopen when relevant. | Ignore route handles and invent a broad manual search first. |
| `bounded_evidence` or `source_open` | Use only inside declared scope and redaction/currentness boundaries. | Widen scope, quote exact wording, or resolve conflicts without reopening. |
| `ignore_or_blocked` | Defer, ask lightly, or explain the boundary when it matters. | Let blocked/private/stale/conflicted material shape answer content. |

When the packet is weak, proceed normally. Reopen or deepen for exact wording,
public/numeric claims, stale/conflicted material, sensitive facts, or high-risk
action.

Presence and proof are different layers. A memory atmosphere can help the agent
understand the moment; a working continuity brief can guide the next action;
source-court behavior still owns exact quotes, disputed facts, sensitive
claims, and abstention.

## First Moves

Use `aippocampus` after package install. In a raw skill checkout, run package
modules from `$CODEX_HOME/skills/aippocampus/scripts` or put that directory on
`PYTHONPATH`.

Start route-first:

- Prefer ambient cards, Active Path Packets, active locks, route handles,
  continuity domain pointers, or progressive MCP tools before inventing broad
  manual searches.
- Use `get_turn_context`, `recall_context`, `recall_deepen`, and
  `search_memory` when an agent client exposes them.
- Use direct clean-source search when the user gives exact wording, no route
  exists, or a route is blocked and a bounded manual search is still justified.
- Drop to raw/indexed rollout only for exact repair, tool provenance, byte
  accounting, missing evidence, or audit questions.

Useful portable commands:

- Check state before or after long work: `aippocampus health --cwd "$PWD"`.
- Check the local provider matrix without writing artifacts:
  `aippocampus onboard --provider auto --status`.
- Search clean source: `aippocampus search "query" --cwd "$PWD"`.
- Run deterministic active recall for vague continuity prompts:
  `python -m aippocampus_runtime.recall.active_recall "query" --cwd "$PWD" --search auto`.
- Locate the current rollout when exact source location matters:
  `python -m aippocampus_runtime.source.locate_rollout --cwd "$PWD"`.
- Recover the latest assistant closeout:
  `python -m aippocampus_runtime.source.latest_reply --cwd "$PWD"`.

Repair and setup are explicit operator actions, not ambient prompt behavior:

- Build the daily source layer:
  `python -m aippocampus_runtime.source.clean_source --cwd "$PWD"`.
- Build or refresh the index:
  `python -m aippocampus_runtime.recall.index_builder --cwd "$PWD"`.
- First-install or full-machine onboarding after explicit user consent:
  `aippocampus onboard --provider codex --all --format json`.
- Claude Code transcript onboarding uses an explicit provider; preview first,
  then register only after consent:
  `aippocampus onboard --provider claude-code --dry-run --format json`, then
  `aippocampus onboard --provider claude-code --format json`.
- For exact host boundaries, use the repository docs
  `docs/guides/ecosystem-integration-matrix.md` and
  `docs/guides/setup/claude-code-mcp.md`; Claude Code onboarding does not imply
  AIppocampus Claude hook support.
- Register an old rollout:
  `python -m aippocampus_runtime.registry.api register-rollout --rollout "<rollout.jsonl>" --project "<label>"`.
- Inspect MCP only when a plugin or agent host needs it:
  `aippocampus mcp list-tools`.

## Workflow

1. When old context might change the next action, use the smallest useful route,
   packet, MCP recall step, or clean-source search before answering from memory.
2. When a thread may outgrow the current context, keep anchors and clean source
   fresh; use hooks for routine refreshes and explicit commands for repair.
3. When the user asks for "last reply", use
   `aippocampus_runtime.source.latest_reply`; it should return the latest
   `final_answer`, or clearly mark commentary fallback.
4. When the user asks why a thread is huge, run
   `aippocampus_runtime.ops.rollout_size_audit` and answer from byte buckets
   and largest-line evidence.
5. When the user asks what can be kept, compressed, or deleted, run
   `retention_report.py --write` before `cold_archive.py`.
6. When recall must span old or separate threads, register the rollout or
   bundle first, then search through the registry.

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
