# Next Iteration Plan

This is the short handoff for the next development slice after the current
technical-debt baseline. It points to canonical docs instead of duplicating
their full contracts.

Keep this file as a task queue and preservation checklist. Detailed Stage 0-5
evidence belongs in `stage-0-5-readiness.md`; dated command evidence belongs in
`public-readiness-verification.md`.

Active planning view: the public GitHub Project
[`AIppocampus Roadmap`](https://github.com/users/Sapientropic/projects/1)
tracks the issue slices extracted from this file and related roadmap/readiness
docs. Use the Project for status/filtering; keep this file as the source-backed
handoff context.

## Current Baseline To Preserve

- Public repo boundary: no raw rollouts, registry exports, private anchors,
  generated indexes, or local paths in Git.
- Public-core licensing and adapter boundaries live in
  `docs/public-core-boundary.md`; do not mirror that contract into release
  notes, package metadata, or roadmap prose beyond a short pointer.
- Default generated artifacts live under
  `$CODEX_HOME/aippocampus-registry/threads/<thread>/...`.
- `.aippocampus/` remains explicit compatibility/export/debug output only.
- The local MCP server exists at
  `skills/aippocampus/scripts/aippocampus_mcp_server.py` and currently exposes
  read-mostly clean-source/registry tools plus explicit `register_thread`.
  Common tool failures return stable JSON error codes/details for client use.
- The plugin source package exists under `plugins/aippocampus/`; build output
  is generated under `dist/` by default and must not be committed.
- The real Codex app-server smoke exists at
  `plugins/aippocampus/smoke_real_codex_host.py`; it verifies Codex
  marketplace/plugin install, MCP host discovery, `sync_status` tool calls, and
  cleanup through real app-server methods.
- The package-level plugin install smoke also records an alternate client
  surface: a standalone MCP stdio JSON-RPC client launched from the installed
  plugin `.mcp.json`, not the headless Codex app-server.
- The single-machine dual-device sync smoke exists at
  `tools/aippocampus/smoke/smoke_cross_device_sync.py`; it verifies
  portable locators, target-registry path repair, bidirectional conflict
  preservation, cross-OS-shaped source locator cleanup, and raw rollout
  opt-in boundaries without claiming a real second machine or cloud backend.
- Plugin install must not silently enable prompt or lifecycle hooks. Hook
  installers remain explicit consent/action surfaces.
- External-model paths must pass through shared redaction before leaving the
  process.
- DeepSeek-backed subconscious jobs preserve the KV-cache contract: stable
  job/schema/tool prefixes come before source turns, variable objectives stay
  last, and same-prefix diversity samples run in warm-up waves rather than all
  launching cold at once.
- DeepSeek model routing preserves the latency boundary: flash is the default
  fast/background route, while Pro is reserved for slow adjudication,
  suppressed-label recovery, and agentic source-review. Pro must stay out of
  foreground hooks.
- Ruff now runs syntax-level `E9` plus full Pyflakes `F`; keep that baseline
  green before considering noisier style/import-order rules. The import-coupling
  test guards against same-directory script cycles, `registry.py` pulling
  `retrieval.py` at module load time, and `prompt_recall_core.py` becoming a
  broad foreground import hub again.
- The real-history FTS5 recall benchmark exists at
  `benchmarks/aippocampus/benchmark_fts5_recall.py`. Preserve the distinction
  between lexical/ranking misses and stale-index consistency misses; detailed
  dated metrics belong in the readiness snapshot or verification ledger.
- Segment rebuilds must preserve the last-known-good manifest and segment dirs
  when a rebuild fails.

## Recommended Next Slices

1. Stage 0-5 completion matrix
   - Source: `roadmap.md` and `stage-0-5-readiness.md`.
   - Keep the matrix current while closing blockers. Do not claim Stage 0-5
     completion until every explicit requirement has evidence, not just tests.

2. Public readiness hardening
   - Source: `roadmap.md`, Stage 1 and Stage 7.
   - Public install/demo docs, privacy checklist, contribution notes, and a
     synthetic public example bundle now exist.
   - Next keep the dated verification fresh after every release slice and
     validate install paths outside this single working copy.

3. GB/TB-scale storage, search, and sync track
   - Source: `gb-scale-roadmap.md` and issue #4.
   - This is now an active near-term track, not a distant optimization. The
     first foundation exists in `storage_capacity_report.py`, and the default
     sync policy no longer treats generated SQLite indexes as mandatory portable
     source.
   - Current executable evidence covers content-addressed clean-source chunk
     delta sync (#11) and registry-metadata query planning with fanout budgets
     (#12).
   - Next execute the remaining split child issues: synthetic multi-GB scale
     smoke and thresholds (#13), and Windows rebuild reliability (#14).

4. Life-wide memory scope labels
   - Source: `roadmap.md`, Stage 2.
   - Clean-source messages and turns now carry deterministic `scope_labels`
     for personal reflection, relationship continuity, reading notes, idea
     seeds, preferences, life context, technical work, and open questions.
   - Fuzzy casual-important labels now have a DeepSeek/subconscious-compatible
     path: `semantic_scope_labeling` findings are materialized by
     `build_semantic_scope_labels.py` into `semantic-scope-labels.jsonl`, then
     search and timelines merge that sidecar as navigation metadata.
   - `project_timeline.json` now also carries a `life_wide` section that groups
     bounded recent labeled clean-source turns across registered
     threads/projects with `source_refs`.
   - Current real-history coverage numbers, strict source-review results, and
     Pro-agent recovery evidence live in `stage-0-5-readiness.md`. Do not mirror
     those metrics here unless this file becomes a release changelog.
   - Next broaden high-confidence recovery for suppressed soft labels
     (`relationship_continuity`, `open_question`, `idea_seed`,
     `technical_work`, `life_context`, `preference`) through better model
     evidence and selected source-review, not lexical expansion, and keep
     over-personalization boundaries tight for ordinary work prompts.

5. Cross-device sync bundle and commands
   - Source: `roadmap.md`, Stage 3.
   - The local-folder `sync status`, `sync push`, `sync pull`, and
     `sync repair` flows now exist in `sync_bundle.py`; pushed registry rows
     use portable bundle-relative locators, and pull repairs generated-artifact
     paths to the target registry. The local cross-device smoke now models two
     device registries, cross-OS-shaped source paths, bidirectional conflicts,
     and raw opt-in. `sync_object_storage.py` now exercises the same contract
     over HTTP object `PUT`/`GET`, with a local object-store smoke.
   - Current P0 evidence now includes a physical Windows-to-MacBook sync smoke
     and a managed Cloudflare R2 encrypted object-storage smoke. Release-oriented
     repair boundaries are documented in `encrypted-sync-v1.md`. Next harden
     them with broader provider/client soak only where a release claim needs it.

6. MCP access layer hardening
   - Source: `roadmap.md`, Stage 4.
   - The first MCP server is present and has both a stdio JSON-RPC process
     smoke and a real Codex app-server MCP host smoke through the plugin path.
   - Error contracts now cover common client failures. Next run an interactive
     Desktop UI flow or another named Codex client only if a release claim needs
     that wrapper.

7. Plugin distribution hardening
   - Source: `roadmap.md`, Stage 5.
   - The built plugin has been validated in a real Codex app-server
     marketplace/plugin install path with reversible cleanup.
   - Public distribution, uninstall, and rollback docs now cover the skill
     package, MCP config, plugin package, hook installers, and optional
     external-model routes. Next pursue marketplace submission or independent
     third-party install review only if those claims are needed.

8. Question tracking Phase 2
   - Source: `question-tracking-subconscious.md`.
   - First deterministic slice is implemented in
     `skills/aippocampus/scripts/question_tracking.py`: it groups existing
     `question_candidate` findings, writes `question_link` rows to
     `subconscious_jobs.jsonl`, records auditable ordering edges, skips stale
     refs when registry clean-source resolution is available, and requires
     explicit confirmation artifacts for borderline pairs.
   - Next hardening: add live model-confirmation plumbing only for borderline
     pairs, tune thresholds on more real clean-source examples, and decide
     whether dormancy detection belongs in Phase 2 or a later hook-facing slice.

9. Vector index protocol
   - Source: `gb-scale-roadmap.md` and `wukong-mining-notes.md`.
   - First slice is implemented in
     `skills/aippocampus/scripts/question_vector_index.py`.
   - Keep vectors optional and join every result back to stable source ids.
   - `question_tracking` now has a deterministic local hash-vector baseline;
     TurboVec or sqlite vector evaluation remains deferred until the current
     source-backed baseline shows a scale bottleneck.

10. Correction reconsolidation events
   - Source: `docs/research/correction-reconsolidation.md` and
     `docs/memory-decision-benchmark-plan.md`.
   - First runtime helper is implemented in
     `skills/aippocampus/scripts/correction_reconsolidation.py`: it builds and
     appends source-backed `correction_activation_event` /
     `correction_outcome_event` rows, privacy-scans correction/evidence
     surfaces, emits detached `correction_adjudication_candidate` hypotheses,
     and renders active anchors only after compaction or horizon loss.
   - Next hardening: wire live hook capture in a fail-open way, then add private
     real-history correction packs before making compaction-survival claims.

11. Coding decision events
   - Source: `docs/research/agent-coding-context-analysis.md` and
     `docs/memory-decision-benchmark-plan.md`.
   - First deterministic extractor is implemented in
     `skills/aippocampus/scripts/coding_decision_events.py`: it reads clean
     source messages, emits staging `decision_event` candidates with source
     refs, flags accepted decisions / rejected routes / scope narrowing /
     do-not-repeat notes / user corrections, and renders at most one compact
     `coding_continuity_ticket` after the shared anti-nag gate.
   - Next hardening: review private real-history decision packs and measure
     whether host agents use tickets correctly before claiming intervention
     timing quality.

## Do Not Start With

- A generic vector database rewrite.
- A cloud service dependency.
- Phase 3 `theme_emergence` or predictive replay before Phase 2 produces stable
  links.
- Any change that treats summaries, findings, or vector neighbors as truth
  without clean-source refs.
