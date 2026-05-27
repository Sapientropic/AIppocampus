# Next Iteration Plan

This is the short handoff for the next development slice after the current
technical-debt baseline. It points to canonical docs instead of duplicating
their full contracts.

## Current Baseline To Preserve

- Public repo boundary: no raw rollouts, registry exports, private anchors,
  generated indexes, or local paths in Git.
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
  `skills/aippocampus/scripts/smoke_cross_device_sync.py`; it verifies
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

3. Life-wide memory scope labels
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
   - The local real-history registry has been broadened to 949 registered
     threads. The full-candidate live semantic sidecar smoke selected 609
     currently unlabeled life-wide candidate turns across 98 threads, evaluated
     every selected candidate in successful DeepSeek-compatible batches, and
     expanded materialized semantic sidecars to 27 threads/119 rows before
     stricter source-review filtering. The current v2 prompt requires
     per-label evidence for every materialized label and the materializer no
     longer falls back to row-level confidence. A fresh v2 no-write DeepSeek
     probe accepted 11 findings / 15 labels with complete sufficient
     per-label evidence across seven labels, while the current strict
     materialization intentionally keeps only 2 threads/5 rows/5 timeline turns
     after suppressing labels whose evidence over-inferred beyond clean source.
     Smoke output includes claim-level, ratio, candidate-coverage, evidence
     completeness, and cannot-claim guards.
   - `smoke_source_evidence_recall_eval.py` now adds selected fuzzy life-wide
     source-evidence prompts. It chooses dynamic low-frequency source cue terms
     instead of expanding a fuzzy word list, then uses dynamic clean-source
     corpus-rarity reranking to check whether search returns the expected
     clean-source evidence; the current selected top-5 eval is 24/24 hits.
   - `smoke_semantic_scope_source_review.py` now adds a live
     DeepSeek-compatible label-case review pass. It samples one sidecar label
     per case, reports per-label pass rates, retries transient reviewer
     failures, and currently verifies 5/5 labels in the strict materialization
     as supported by clean source. Earlier broader review failures are now used
     as suppression signals instead of pass-rate dilution.
   - `semantic_scope_suppressed_recovery.py` now gives Pro an explicit
     tool-loop path for labels suppressed by strict sidecar gates. It filters
     out old empty-evidence candidates, inspects clean source through a tool,
     and the latest live smoke restored 3/5 selected candidate labels through
     the unchanged strict materializer. A stricter Pro-agent source-review run
     still flagged `personal_reflection` / `reading_notes` ambiguity, so those
     cases should guide the next evidence-generation pass rather than loosening
     sidecar gates.
   - Next broaden high-confidence recovery for suppressed soft labels
     (`relationship_continuity`, `open_question`, `idea_seed`,
     `technical_work`, `life_context`, `preference`) through better model
     evidence and selected source-review, not lexical expansion, and keep
     over-personalization boundaries tight for ordinary work prompts.

4. Cross-device sync bundle and commands
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

5. MCP access layer hardening
   - Source: `roadmap.md`, Stage 4.
   - The first MCP server is present and has both a stdio JSON-RPC process
     smoke and a real Codex app-server MCP host smoke through the plugin path.
   - Next add stronger error contracts and, if needed for release claims, an
     interactive Desktop UI or alternate Codex client verification.

6. Plugin distribution hardening
   - Source: `roadmap.md`, Stage 5.
   - The built plugin has been validated in a real Codex app-server
     marketplace/plugin install path with reversible cleanup.
   - Next add public distribution docs, external install review, and
     uninstall/rollback docs for skill package, MCP config, and hook
     installers.

7. Question tracking Phase 2
   - Source: `question-tracking-subconscious.md`.
   - Implement `question_tracking` only after Phase 1 `question_extraction`
     output has enough source-backed examples.
   - Start deterministic: group existing `question_candidate` findings, add
     dependency ordering, then add model confirmation for borderline links.

8. Vector index protocol
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
