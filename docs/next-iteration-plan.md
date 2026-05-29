# Next Iteration Plan

This is the short handoff for the next development slice after the current
technical-debt baseline. It points to canonical docs instead of duplicating
their full contracts.

Keep this file as a task queue and preservation checklist. Detailed Stage 0-5
evidence belongs in `stage-0-5-readiness.md`; dated command evidence belongs in
`public-readiness-verification.md`.

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
- The plugin source package exists under `plugins/aippocampus/`; build output
  is generated under `dist/` by default and must not be committed.
- The real Codex app-server smoke exists at
  `plugins/aippocampus/smoke_real_codex_host.py`; it verifies Codex
  marketplace/plugin install, MCP host discovery, `sync_status` tool calls, and
  cleanup through real app-server methods.
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
   - Next execute the split child issues: content-addressed clean-source chunks
     and delta sync (#11), registry query planning and fanout budgets (#12),
     synthetic multi-GB scale smoke and thresholds (#13), and Windows rebuild
     reliability (#14).

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
   - Next harden them with physical second-machine smoke, managed
     cloud/object-storage provider smoke, and release-oriented repair docs.

6. MCP access layer hardening
   - Source: `roadmap.md`, Stage 4.
   - The first MCP server is present and has both a stdio JSON-RPC process
     smoke and a real Codex app-server MCP host smoke through the plugin path.
   - Next add stronger error contracts and, if needed for release claims, an
     interactive Desktop UI or alternate Codex client verification.

7. Plugin distribution hardening
   - Source: `roadmap.md`, Stage 5.
   - The built plugin has been validated in a real Codex app-server
     marketplace/plugin install path with reversible cleanup.
   - Next add public distribution docs, external install review, and
     uninstall/rollback docs for skill package, MCP config, and hook
     installers.

8. Question tracking Phase 2
   - Source: `question-tracking-subconscious.md`.
   - Implement `question_tracking` only after Phase 1 `question_extraction`
     output has enough source-backed examples.
   - Start deterministic: group existing `question_candidate` findings, add
     dependency ordering, then add model confirmation for borderline links.

9. Vector index protocol
   - Source: `gb-scale-roadmap.md` and `wukong-mining-notes.md`.
   - Define the `QuestionVectorIndex` protocol with a simple local
     implementation before evaluating TurboVec.
   - Keep vectors optional and join every result back to stable source ids.

## Do Not Start With

- A generic vector database rewrite.
- A cloud service dependency.
- Phase 3 `theme_emergence` or predictive replay before Phase 2 produces stable
  links.
- Any change that treats summaries, findings, or vector neighbors as truth
  without clean-source refs.
