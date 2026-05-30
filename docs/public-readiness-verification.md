# Public Readiness Verification

Initial evidence date: 2026-05-27.
Repository-layout command paths refreshed: 2026-05-29.

This file is a dated verification ledger. It preserves summarized command
evidence for release-readiness work, but the current Stage 0-5 claim boundary
lives in `docs/stage-0-5-readiness.md` and the canonical product requirements
remain in `docs/roadmap.md`.

Stable privacy rules live in `docs/privacy-security-checklist.md`. Do not paste
raw command JSON here: local smoke outputs may contain machine-specific
temporary paths, so this document keeps only summarized evidence.

## 2026-05-28 Layout Refresh

The installable skill body is now runtime-only: repository tests live in
`tests/aippocampus/`, benchmark runners in `benchmarks/aippocampus/`, and
smoke/docs-maintenance tools in `tools/aippocampus/`. The command ledger below
uses those paths. Ordinary docs-only edits do not require every heavy smoke in
this ledger; use `stage-0-5-readiness.md` to decide which evidence is needed
for a specific claim.

## 2026-05-30 Public-Core Boundary Refresh

Issue #7 switched the public repository direction to Apache-2.0 public core
plus separate commercial/hosted product surfaces. The canonical boundary now
lives in `docs/public-core-boundary.md`; README, contribution docs, commercial
extension notes, plugin metadata, pyproject metadata, and provenance catalog
point to that boundary instead of restating a full license contract.

Latest verification for that slice:

- `python tools/aippocampus/docs/check_docs_health.py --json`: passed.
- `python tools/aippocampus/run_tests.py --tier fast`: 306 tests passed.
- `python -m unittest tests.aippocampus.test_plugin_distribution`: 9 tests
  passed.
- `python -m ruff check plugins/aippocampus tests/aippocampus/test_plugin_distribution.py`:
  passed.
- `git diff --check`: passed.
- Changed-file secret/local-path scan: no hits.
- Main CI for commit `5940252b112ece31efd524e4a5a09aa0593d9a24`: passed.

## 2026-05-30 Memory Pain Fixture Evidence

Issues #27/#28 added public-safe memory-system pain fixtures and a short report
without turning public competitor issue references into a leaderboard. The
canonical report is `docs/memory-pain-fixture-report.md`.

Verification for that slice:

- `python -m unittest tests.aippocampus.test_benchmark_memory_decision_gate tests.aippocampus.test_benchmark_payload_fidelity`:
  17 tests passed.
- `ruff check benchmarks/aippocampus/benchmark_memory_decision_gate.py benchmarks/aippocampus/benchmark_payload_fidelity.py tests/aippocampus/test_benchmark_memory_decision_gate.py tests/aippocampus/test_benchmark_payload_fidelity.py`:
  passed.
- `python benchmarks\aippocampus\benchmark_memory_decision_gate.py --json --output .tmp\memory-pain-gate-report.json`:
  passed; 9 memory-pain fixture families, 0 unsupported-evidence false
  positives, `live_llm_required=false`.
- `python benchmarks\aippocampus\benchmark_payload_fidelity.py --json --output .tmp\memory-pain-payload-report.json`:
  passed; 9 memory-pain fixture families, 0 privacy breaches,
  0 evidence-without-source cases, and 0 unsupported-evidence cases for that
  fixture family.
- `python tools\aippocampus\docs\check_docs_health.py --json`: passed.
- `python tools\aippocampus\run_tests.py --tier fast`: 354 tests passed.
- `python tools\aippocampus\run_tests.py --tier benchmark`: 87 tests passed.

This is boundary evidence only. It does not claim competitor superiority,
real-history memory-pain quality, live semantic-model quality, or a complete
Track D compaction-continuity runner.

## 2026-05-30 Track D Synthetic Runner Evidence

Issue #66 added the deterministic synthetic Track D compaction-continuity
runner. It covers fixture hook envelopes for `UserPromptSubmit`, `PreToolUse`,
`PostToolUse`, `SubagentStart`, `SubagentStop`, `Stop`, `PreCompact`, and
`PostCompact`; simulated `visible`, `post_compaction`, and `horizon_lost`
states; synthetic correction/outcome event chains; and mocked adjudication
statuses for `valid_adopted`,
`valid_ignored`, `refuted`, `superseded`, `local_only`, and `uncertain`.

Verification for that slice:

- `python -m unittest tests.aippocampus.test_benchmark_compaction_continuity`:
  6 tests passed.
- `python -m unittest tests.aippocampus.test_benchmark_suite`: passed with the
  default suite including `compaction_continuity` and `--skip-track-d` coverage.
- `python benchmarks\aippocampus\benchmark_compaction_continuity.py --json --output .tmp\track-d-compaction-continuity.json`:
  passed with 14 synthetic Track D cases, 0 privacy breaches, 0 false anchors,
  0 stale-route retries, full event-chain source fidelity, full
  correction-anchor recall, full same-epoch repeated-anchor suppression, and
  full anti-nag precision.
- `python tools\aippocampus\run_tests.py --tier benchmark`: passed.

This is a deterministic measurement surface, not product proof that #65's real
correction activation/outcome event pipeline, live hook capture, live semantic
adjudication, or private real-history compaction survival has shipped.

## 2026-05-30 Real Codex Long-Session Continuity Smoke

Issue #45 added a slow/live Codex app-server smoke for the missing runtime
intersection: real Codex turns, real host compaction, correction survival, and
clean-source verification.

Documented command:

- `python tools/aippocampus/smoke/smoke_codex_long_session_continuity.py --turn-count 50 --json`

Primary 50-turn live verification for this slice:

- `python tools/aippocampus/smoke/smoke_codex_long_session_continuity.py --turn-count 50 --run-id issue45live50 --output .tmp/issue45-long-session-smoke.json --json`:
  passed with `status=passed`, 50 completed pre-compaction Codex turns, 52
  completed total turns, a real `thread/compact/start` boundary, observed
  `contextCompaction`, completed `preCompact` and `postCompact` host hooks,
  correction-event observation, post-compaction recall of the corrected
  synthetic state, no obsolete-state revival in the recall answer, and rebuilt
  clean source from the real rollout with 102 clean messages / 51 clean turns.
  The public payload reported `public_payload_sensitive_string_count=0`.
- `python -m unittest tests.aippocampus.test_codex_long_session_smoke`: passed.
- `python -m ruff check tools/aippocampus/smoke/smoke_codex_long_session_continuity.py tests/aippocampus/test_codex_long_session_smoke.py`: passed.

This is slow/live evidence, not fast deterministic coverage. It uses synthetic
public-safe tokens and does not claim private real-history compaction survival,
live semantic adjudication quality, interactive Desktop UI behavior, or every
Codex client surface.

## 2026-05-30 P0 Evidence Refresh

This slice executed the P0 issues #29, #30, #33, #34, #35, #36, and #38. It
records command evidence only; the issue tracker remains the work queue and
`docs/stage-0-5-readiness.md` remains the claim-boundary summary.

Release/readiness checks:

- `python tools\aippocampus\docs\check_docs_health.py --json`: passed.
- `python tools\aippocampus\run_tests.py --tier fast`: 306 tests passed.
- `python tools\aippocampus\smoke\run_stage_0_5_smoke.py --repo-root . --json`:
  initially failed only at the public-boundary scan because benchmark fixture
  prose was treated as product-surface secret/local-path leakage. The scanner
  now excludes `benchmark_corpus/` from the product-surface scan and keeps that
  boundary explicit: benchmark corpora require a separate corpus audit before
  anyone claims the corpora themselves are secret-like-string-free. After this
  scanner fix, the full Stage 0.5 smoke rerun passed, including docs health,
  505 unit tests, compileall, Ruff, package/plugin smokes, sync smokes, and
  the product-surface secret scan.

External install evidence for #29:

- `python plugins\aippocampus\smoke_plugin_install.py --json`: passed. The
  temporary installed plugin exposed the expected MCP tools through both
  `--list-tools` and JSON-RPC `initialize` / `notifications/initialized` /
  `tools/list` / `tools/call`; `hooks_auto_enabled=false`; uninstall cleanup
  completed.
- `python plugins\aippocampus\smoke_real_codex_host.py --json`: passed through
  the real Codex app-server plugin manager and MCP host. The run installed and
  enabled a run-id-scoped local marketplace plugin, refreshed MCP config, listed
  the `aippocampus` server, called `sync_status`, then uninstalled the plugin
  and removed temporary marketplace/build/cache artifacts. This verifies a real
  host path, not a public marketplace submission or second-user install.

Stage 2 evidence for #33/#34/#35:

- `python skills\aippocampus\scripts\semantic_scope_suppressed_recovery.py --live --max-cases 12 --min-recovered-labels 1 --json`:
  passed. It selected all currently available 8 suppressed-label cases, covered
  11 candidate labels, used the Pro route, inspected clean source through the
  tool loop, and recovered 3 labels through the unchanged strict materializer.
  `strict_gate_relaxed=false`; recovered coverage was `idea_seed`,
  `open_question`, and `preference`; unsupported labels remained suppressed.
- `python tools\aippocampus\smoke\smoke_semantic_scope_source_review.py --live --max-cases 96 --min-cases 64 --min-pass-rate 0.75 --min-label-pass-rate 0.65 --concurrency 2 --timeout 200 --max-attempts 3 --json`:
  passed. It reviewed 96 selected semantic sidecar label cases, passed 84, and
  reached `pass_rate=0.875`. Per-label pass rates were above the 0.65 floor for
  `personal_reflection`, `reading_notes`, `idea_seed`, `preference`,
  `life_context`, `technical_work`, and `open_question`; `failed_label_categories`
  was empty. The 12 individual misses remain evidence of ambiguous rows, not a
  reason to lower materializer gates or claim global correctness.
- `python tools\aippocampus\smoke\smoke_source_evidence_recall_eval.py --max-cases 24 --min-cases 12 --top-k 5 --min-hit-rate 0.85 --json`:
  passed with 24/24 top-5 hits, `warning_count=0`, and sanitized coverage across
  all eight canonical labels.

Stage 3 sync evidence for #36/#38:

- `python tools\aippocampus\smoke\smoke_cross_device_sync.py --repo-root . --json`:
  passed the single-machine dual-device model, cross-OS path-shape model,
  conflict preservation, path repair, and raw-rollout opt-in checks. It still
  records `physical_second_machine=false` and `real_cloud_backend=false`.
- `python tools\aippocampus\smoke\smoke_object_storage_sync.py --repo-root . --json`:
  passed the local HTTP object-store protocol path and target-registry path
  repair, with raw rollout excluded by default. It still records
  `real_cloud_backend=false` and `physical_second_machine=false`.
- Physical Windows-to-MacBook local-folder sync smoke: passed over Tailscale SSH
  with a real MacBook target. The smoke verified bundle `status` and `repair`,
  pulled into a Mac target registry, repaired target-device generated-artifact
  locators, preserved a Mac-side local edit under `.sync-conflicts/`, kept raw
  rollouts excluded by default, then pushed the Mac target bundle back to
  Windows and verified the reverse conflict path preserved the Windows source.
  The Mac system Python 3.9 run exposed a `Path.write_text(newline=...)`
  compatibility bug in path repair; `sync_bundle.save_json` now uses
  `Path.open(..., newline="\n")`, and
  `test_pull_path_repair_works_on_python39_path_write_text_signature` covers the
  regression.
- Managed Cloudflare R2 encrypted object-storage smoke: passed through
  `smoke_real_provider_encrypted_sync.py` using the real provider-aware R2
  signing path and a run-specific object prefix. The smoke generated an
  ephemeral `age` identity, completed encrypted push/status/repair/pull,
  verified `recipient_match=yes`, checked 10 inner bundle files, downloaded 12
  encrypted objects, kept `raw_rollout_included=false`, materialized the target
  registry, and deleted all 12 uploaded encrypted objects during cleanup. Bucket
  names, credentials, and local paths are intentionally omitted from this
  public ledger.

## 2026-05-30 MCP, Plugin, And Sync Boundary Refresh

This slice executed issues #23, #31, #32, and #37, and leaves #22 ready to close
once its children are closed. It records command evidence only; the current
claim boundary remains `docs/stage-0-5-readiness.md`.

Latest verification for this slice:

- `python tools\aippocampus\docs\check_docs_health.py --json`: passed.
- `python -m unittest tests.aippocampus.test_plugin_distribution tests.aippocampus.test_aippocampus_mcp_server`:
  24 tests passed.
- `python tools\aippocampus\run_tests.py --tier fast`: 315 tests passed.
- `python tools\aippocampus\smoke\run_stage_0_5_smoke.py --repo-root . --json`:
  passed. The unified smoke included docs health, 514 unit tests, compileall,
  Ruff, public demo/timeline checks, MCP tool-list smoke, package/plugin smokes,
  local-folder/object-storage/alternate-runtime sync smokes, semantic sidecar
  checks, product-surface secret scan, and run-id artifact cleanup.
- `python plugins\aippocampus\smoke_plugin_install.py --repo-root . --json`:
  passed. The staged plugin exposed the expected MCP tools through `--list-tools`
  and installed-plugin `.mcp.json` JSON-RPC, including `initialize`,
  `notifications/initialized`, `tools/list`, and `tools/call:sync_status`.
  The smoke now reports the alternate client surface as
  `standalone_mcp_stdio_jsonrpc_client`; it is explicitly not headless Codex
  app-server evidence and not interactive Desktop UI evidence. Hook auto-enable
  stayed false and uninstall cleanup completed.
- `python skills\aippocampus\scripts\aippocampus_mcp_server.py --list-tools`:
  passed and listed the read-mostly tool surface:
  `search_memory`, `latest_reply`, `get_turn_context`, `list_threads`,
  `register_thread`, `sync_status`, and `memory_health`.
- `git diff --check`: passed.

Scope notes:

- MCP error contracts now distinguish malformed params/arguments, missing tool
  names, unknown tools, unsupported mutation requests, missing registry state,
  unavailable clean source, missing turn selectors, missing message ids, missing
  turns, health-check failures, and generic tool failures.
- Public distribution docs now separate skill-only install, plugin package,
  MCP config, hook installers, optional external-model routes, uninstall, and
  rollback. They point to the existing #29 external install evidence instead of
  duplicating its ledger.
- Sync repair docs now separate local simulation, Docker/WSL alternate runtime,
  physical second-machine evidence from #36, and managed-provider evidence from
  #38. Local HTTP object-storage remains simulation; the managed R2 run remains
  one provider path, not a provider matrix.

## 2026-05-30 Issues #55/#56 Evidence Closeout

This slice refreshes the Stage 2 soft-label evidence for #55 and the
release-gate/client-surface evidence for #56. It does not relax source-backed
materializer gates, claim human review, claim a public marketplace submission,
or claim every Codex UI wrapper.

Latest verification for this slice:

- `python tools\aippocampus\docs\check_docs_health.py --json`: passed.
- `python tools\aippocampus\run_tests.py --tier fast`: 333 tests passed.
- `python tools\aippocampus\smoke\run_stage_0_5_smoke.py --repo-root . --json`:
  passed after tightening the product-surface secret/local-path scanner so it
  does not treat a regex literal such as an issue-parent matcher as a Windows
  drive path. The unified smoke included docs health, 533 unit tests,
  compileall, Ruff, public demo/timeline checks, MCP tool-list smoke,
  package/plugin smokes, local-folder/object-storage/alternate-runtime sync
  smokes, semantic sidecar checks, product-surface secret scan with no hits,
  and run-id artifact cleanup.
- `python -m unittest tests.aippocampus.test_stage_0_5_smoke.Stage05SmokeRunnerTests.test_secret_scan_does_not_treat_regex_escapes_as_windows_paths tests.aippocampus.test_stage_0_5_smoke.Stage05SmokeRunnerTests.test_secret_scan_does_not_treat_json_escaped_newline_as_windows_path tests.aippocampus.test_stage_0_5_smoke.Stage05SmokeRunnerTests.test_secret_scan_allows_fake_fixtures_but_flags_real_secret_shape`:
  passed, covering the scanner false-positive regression and preserving the
  existing real-secret checks.

Stage 2 soft-label evidence for #55:

- `python .\tools\aippocampus\smoke\smoke_life_wide_registry.py --require-evidence --json`:
  passed against the local real-history registry. The aggregate slice observed
  964 clean-source/index/graph-backed threads, 110 scope-labeled threads, 88
  non-technical life-wide threads, 244 semantic sidecar rows across 46 threads,
  and all eight canonical labels. The smoke still reports
  `claim_level=first_pass_real_history_slice` and keeps `cannot_claim` entries
  for full-history refresh, semantic completeness, and label correctness
  without clean-source review.
- `python .\tools\aippocampus\smoke\smoke_semantic_scope_real_history.py --require-labels --min-sidecar-rows 1 --min-sidecar-threads 1 --min-timeline-turns 1 --json`:
  passed in observe-only mode. This confirmed the currently materialized
  dynamic semantic sidecar slice without making a fresh external-model write.
- `python .\tools\aippocampus\smoke\smoke_source_evidence_recall_eval.py --max-cases 24 --min-cases 12 --top-k 5 --min-hit-rate 0.85 --json`:
  passed with 24 selected cases, 24/24 top-5 hits, `top_k_hit_rate=1.0`,
  `warning_count=0`, dynamic-source ranking, and coverage across
  `idea_seed`, `life_context`, `open_question`, `personal_reflection`,
  `preference`, `reading_notes`, `relationship_continuity`, and
  `technical_work`. This is a selected retrieval-quality check, not a global
  recall-quality claim.
- `python .\skills\aippocampus\scripts\semantic_scope_suppressed_recovery.py --max-cases 12 --json`:
  passed in observe-only mode with 8 currently available suppressed-label cases
  / 11 candidate labels and `strict_gate_relaxed=false`. No new labels were
  restored in this closeout; live Pro recovery evidence remains the earlier
  dated evidence above.
- `python .\tools\aippocampus\smoke\smoke_semantic_scope_source_review.py --live --max-cases 24 --min-cases 12 --min-pass-rate 0.75 --min-label-pass-rate 0.65 --concurrency 2 --timeout 200 --max-attempts 3 --json`:
  passed. It reviewed 24 selected current semantic sidecar label cases through
  the DeepSeek-compatible live source-review path, passed 24/24, reached
  `pass_rate=1.0`, and had no failed label categories or live model failures.
  Reviewed live label families were `idea_seed`, `life_context`,
  `open_question`, `personal_reflection`, `preference`, `reading_notes`, and
  `technical_work`.
- `python .\tools\aippocampus\smoke\smoke_semantic_scope_source_review.py --live --max-cases 96 --min-cases 64 --min-pass-rate 0.75 --min-label-pass-rate 0.65 --concurrency 2 --timeout 200 --max-attempts 3 --json`:
  returned nonzero and is recorded as diagnostic evidence, not a green gate. It
  reviewed 96 selected cases, passed 88, reached `pass_rate=0.9167`, and kept
  every reviewed label category above the 0.65 floor, with
  `failed_label_categories=[]`. The command still reported
  `status=live_model_partial_failure`, `claim_level=diagnostic_only`, and
  `failure_count=1`; that operational partial failure is the residual blocker
  for treating the 96-case run itself as passed.
- `python .\tools\aippocampus\smoke\smoke_semantic_scope_source_review.py --max-cases 96 --min-cases 64 --json`:
  passed in observe-only mode and confirmed 96 selectable source-review cases
  across the current strict semantic sidecar slice.

Closeout interpretation for #55:

- Reviewed families now include selected source-review evidence for
  `idea_seed`, `life_context`, `open_question`, `personal_reflection`,
  `preference`, `reading_notes`, and `technical_work`; selected retrieval
  evidence also covers `relationship_continuity`.
- Accepted current strict sidecar labels are only the labels that survived
  per-label evidence gates and live source review. No new high-risk
  suppressed label was restored by this closeout.
- Still-suppressed or not-broadly-claimed cases include generic
  `relationship_continuity`, broad `life_context` beyond the single selected
  strict sidecar case, ordinary immediate `open_question`, media-like
  `reading_notes`, and adjacent-context `idea_seed` / `technical_work` /
  `preference` guesses when the model evidence does not bind the specific
  label to the clean-source message.
- Source-review failures are treated as evidence-selection and model-finding
  feedback. In the 96-case diagnostic run, semantic misses were concentrated in
  `technical_work`, `preference`, `reading_notes`, and
  `personal_reflection`, while the only gate-level failure was the one live
  model partial failure. None of that authorizes lexical expansion or lower
  materializer gates.

Release-gate and client-surface evidence for #56:

- `python .\plugins\aippocampus\smoke_plugin_install.py --repo-root . --json`:
  passed. This is a package-level temporary install-root smoke plus standalone
  MCP stdio JSON-RPC client check from the installed plugin `.mcp.json`.
  Operations covered `initialize`, `notifications/initialized`, `tools/list`,
  and `tools/call:sync_status`; `hooks_auto_enabled=false`; uninstall cleanup
  completed. This is not headless Codex app-server evidence and not
  interactive Desktop UI evidence.
- `python .\plugins\aippocampus\smoke_real_codex_host.py --repo-root . --json`:
  passed through the real Codex Desktop app-server `0.130.0` on a local
  Windows x86_64 developer workstation. The install path class was a
  run-id-scoped local marketplace plus Codex plugin cache, both cleaned up by
  the smoke; no public marketplace was involved. The host path exercised
  `marketplace/add`, `plugin/read`, `plugin/install`,
  `config/mcpServer/reload`, `mcpServerStatus/list`, `thread/start`,
  `mcpServer/tool/call sync_status`, `plugin/uninstall`, and
  `marketplace/remove`. The plugin was not installed before the smoke, was
  installed/enabled after `plugin/install`, and cleanup removed the plugin,
  marketplace, build output, marketplace root, and Codex plugin-cache root. The
  thread archive cleanup reported a benign "no rollout found" error for the
  temporary host thread; plugin and marketplace cleanup still succeeded.
- Exact evidence boundary: verified surfaces are the package-level temporary
  plugin install root, installed-plugin standalone MCP stdio JSON-RPC client,
  and headless Codex Desktop app-server local-marketplace host path. Untested
  surfaces remain unclaimed: public marketplace submission, independent
  third-party fresh-clone or second-user install review, and human interactive
  Desktop UI marketplace/plugin click-through.

## Command Ledger

```powershell
python tools\aippocampus\docs\check_docs_health.py --json
python tools\aippocampus\run_tests.py --tier fast
python tools\aippocampus\run_tests.py --tier full
python -m compileall -q skills plugins tests tools benchmarks benchmark_corpus
python -m ruff check skills plugins tests tools benchmarks benchmark_corpus
python -m mypy
python .\skills\aippocampus\scripts\build_project_timeline.py --registry .\examples\public-memory-bundle\registry\threads.json --output .\.tmp\public-project-timeline.json --json
python .\skills\aippocampus\scripts\build_semantic_scope_labels.py --jobs-output .\examples\public-memory-bundle\registry\subconscious_jobs.jsonl --clean-source-dir .\examples\public-memory-bundle\clean-source --no-write --json
python .\skills\aippocampus\scripts\search_clean_source.py "casual sparks" --cwd . --clean-source-dir .\examples\public-memory-bundle\clean-source --scope-label idea_seed --json
python .\skills\aippocampus\scripts\search_clean_source.py "lighthouse metaphor pivot" --cwd . --clean-source-dir .\examples\public-memory-bundle\clean-source --scope-label personal_reflection --scope-label idea_seed --json
python .\skills\aippocampus\scripts\onboard_codex.py --all --no-cognitive-map --frontier-mode off --format json
python .\tools\aippocampus\smoke\smoke_life_wide_registry.py --require-evidence --json
python .\tools\aippocampus\smoke\smoke_semantic_scope_real_history.py --live --write-sidecars --require-labels --max-turns 80 --max-steps 2 --min-tool-steps 0 --concurrency 6 --samples-per-job 3 --min-sidecar-rows 18 --min-sidecar-threads 7 --min-timeline-turns 50 --json
python .\tools\aippocampus\smoke\smoke_semantic_scope_real_history.py --live --write-sidecars --require-labels --full-candidate-coverage --candidate-batch-size 24 --samples-per-job 1 --concurrency 6 --max-steps 1 --min-tool-steps 0 --max-tokens 4000 --timeout 120 --min-sidecar-rows 50 --min-sidecar-threads 20 --min-timeline-turns 80 --json
python .\tools\aippocampus\smoke\smoke_semantic_scope_real_history.py --live --write-sidecars --require-labels --max-turns 96 --max-steps 1 --min-tool-steps 0 --concurrency 4 --samples-per-job 2 --max-tokens 5000 --timeout 160 --min-sidecar-rows 80 --min-sidecar-threads 20 --min-timeline-turns 50 --json
python .\tools\aippocampus\smoke\smoke_semantic_scope_real_history.py --require-labels --min-sidecar-rows 90 --min-sidecar-threads 20 --min-timeline-turns 50 --json
python .\skills\aippocampus\scripts\subconscious_jobs.py --job semantic_scope_labeling --max-turns 7 --max-steps 1 --min-tool-steps 0 --samples-per-job 2 --concurrency 2 --max-tokens 600 --timeout 120 --no-write --json
python .\tools\aippocampus\smoke\smoke_semantic_scope_real_history.py --live --require-labels --max-turns 32 --max-steps 2 --min-tool-steps 0 --concurrency 2 --samples-per-job 2 --max-tokens 5000 --timeout 180 --min-sidecar-rows 1 --min-sidecar-threads 1 --min-timeline-turns 1 --json
python .\tools\aippocampus\smoke\smoke_source_evidence_recall_eval.py --max-cases 24 --min-cases 12 --top-k 5 --min-hit-rate 0.85 --json
python .\tools\aippocampus\smoke\smoke_semantic_scope_source_review.py --live --max-cases 96 --min-cases 64 --min-pass-rate 0.75 --min-label-pass-rate 0.65 --concurrency 2 --timeout 200 --max-attempts 3 --json
python .\tools\aippocampus\smoke\smoke_semantic_scope_source_review.py --live --max-cases 4 --min-cases 1 --min-pass-rate 0 --min-label-pass-rate 0 --concurrency 2 --timeout 120 --max-attempts 1 --json
python .\tools\aippocampus\smoke\smoke_semantic_scope_source_review.py --live --max-cases 5 --min-cases 5 --min-pass-rate 0.75 --min-label-pass-rate 0.65 --min-review-confidence 0.65 --concurrency 3 --timeout 160 --max-attempts 2 --json
python -m unittest tests.aippocampus.test_deepseek_model_routing tests.aippocampus.test_semantic_scope_source_review.SemanticScopeSourceReviewTests.test_agentic_source_review_uses_pro_route_and_tool_observation tests.aippocampus.test_semantic_scope_suppressed_recovery
python .\skills\aippocampus\scripts\semantic_scope_suppressed_recovery.py --max-cases 8 --json
python .\skills\aippocampus\scripts\semantic_scope_suppressed_recovery.py --live --max-cases 3 --min-recovered-labels 1 --timeout 240 --max-tokens 6000 --max-steps 3 --min-tool-steps 1 --json
python .\tools\aippocampus\smoke\smoke_semantic_scope_source_review.py --live --agentic-review --max-cases 5 --min-cases 5 --min-pass-rate 0.75 --min-label-pass-rate 0.65 --min-review-confidence 0.65 --concurrency 2 --timeout 240 --max-tokens 4000 --review-max-steps 3 --min-tool-steps 1 --json
python .\benchmarks\aippocampus\benchmark_fts5_recall.py --cases 100 --min-cases 50 --top-k 10 --output .\.tmp\fts5-recall-benchmark-100.json
python .\skills\aippocampus\scripts\aippocampus_mcp_server.py --list-tools
python .\plugins\aippocampus\build_plugin_package.py --repo-root . --json
python .\plugins\aippocampus\smoke_plugin_install.py --repo-root . --json
python .\plugins\aippocampus\smoke_real_codex_host.py --repo-root . --json
python .\tools\aippocampus\smoke\smoke_cross_device_sync.py --repo-root . --json
python .\tools\aippocampus\smoke\smoke_object_storage_sync.py --repo-root . --json
python .\tools\aippocampus\smoke\smoke_alternate_runtime_sync.py --repo-root . --runtime all --json
python .\skills\aippocampus\scripts\aippocampus_lifecycle_hook.py --event SessionStart --cwd . --json --max-elapsed-ms 8000
python .\tools\aippocampus\smoke\run_stage_0_5_smoke.py --repo-root . --json
```

Results:

- fast test tier: 279 tests passed
- full test tier: 443 tests passed
- docs health: `ok=true`
- Python compile check: passed
- Ruff check: passed. The Ruff baseline now includes full Pyflakes (`F`) plus
  syntax-level `E9`, so unused imports, undefined names, and stale local
  variables are caught instead of only parse-time failures.
- Mypy check: passed across 54 source files. The architecture guard suite keeps
  high-risk and 300+ LOC runtime scripts in the mypy baseline, verifies that
  split helper modules remain available, and keeps repo tools out of the
  installable runtime package. It intentionally avoids per-function source
  placement assertions that only mirror the current file layout.
- prompt hook life-wide ambient scent tests: passed, including ordinary code
  prompt suppression
- public example project/life-wide timeline smoke: passed
- public example semantic scope-label materializer smoke: passed from
  synthetic `semantic_scope_labels` staging finding to one accepted sidecar row
- mocked DeepSeek/subconscious `semantic_scope_labeling` job-to-sidecar unit
  path: passed without expanding deterministic lexical rules
- public example bundle scope-label search smoke: passed for `idea_seed`
- public example casual-important metaphor/pivot search smoke: passed for
  `personal_reflection` plus `idea_seed` via generated/checked
  `semantic-scope-labels.jsonl`
- real-registry life-wide aggregate smoke: passed after refreshing the newest
  local clean-source slice and then onboarding 63 additional local sessions.
  The current aggregate smoke emits only counts and reports no raw text,
  snippets, titles, source refs, or absolute paths. It showed 949 registered
  threads with complete clean-source/index/graph artifacts, 101 scope-labeled
  threads, 80 non-technical life-wide threads, all eight canonical labels
  present, and 142 project groups. The smoke now returns `claim_level`,
  `coverage_ratios`, and `cannot_claim` fields so the result remains a
  first-pass real-history slice, not a full-history claim.
- live real-history semantic sidecar smoke: passed with the DeepSeek-compatible
  `semantic_scope_labeling` job. The live route now defaults to parallel
  DeepSeek samples and treats missing keys, partial model failures, and empty
  model findings as failed live smoke instead of silently falling back to
  observe-only sidecars. An intermediate broader run selected 80 source-backed
  life-wide candidate turns across 9 threads, executed three successful samples
  with no model failures, and materialized 20 total
  `semantic-scope-labels.jsonl` rows across 7 real clean-source threads. The
  full-candidate run selected 609 currently unlabeled life-wide
  candidate turns across 98 threads, evaluated all of them in 26 successful
  parallel DeepSeek-compatible batches, accepted 99 new source-backed staging
  findings, and materialized 119 total sidecar rows across 27 real clean-source
  threads. The deliberately strict `min_timeline_turns=80` command returned
  nonzero because the refreshed timeline observed 67 semantic latest turns, but
  the model/materialization path itself succeeded with no batch failures. A
  subsequent source-review pass exposed weak labels, so the semantic prompt was
  bumped to `aippocampus-subconscious-jobs-v2`, revised to require per-label
  evidence for every materialized label, and the materializer now filters all
  labels with label-specific evidence gates instead of falling back to broad
  row-level confidence. A fresh v2 no-write run over 32 candidate turns
  completed two successful samples with no model failures and accepted 11
  source-backed findings / 15 labels, all with sufficient per-label evidence;
  it covered `idea_seed`, `open_question`, `personal_reflection`,
  `preference`, `reading_notes`, `relationship_continuity`, and
  `technical_work`. Follow-up clean-source review found that several broad
  labels still over-inferred beyond source text, so the current strict
  re-materialized sidecars intentionally contain only 5 rows across 2 real
  clean-source threads, and the refreshed timeline observes 5 semantic latest
  turns. The smoke output remained aggregate-only and explicitly preserved
  `cannot_claim` entries for full-history refresh, semantic completeness, and
  label correctness without clean-source review.
- selected source-evidence recall eval: passed. The new
  `smoke_source_evidence_recall_eval.py` selected 24 semantic-sidecar-backed
  fuzzy life-wide prompts using dynamic low-frequency source cue terms, not a
  hand-expanded fuzzy word list. It now uses dynamic clean-source corpus-rarity
  reranking and verified that 24 of 24 prompts returned the expected
  clean-source evidence in top-5 results (`top_k_hit_rate=1.0`) with all
  eight canonical labels represented. The output used hashed case ids and
  aggregate counts only, with no raw text, snippets, titles, source refs, or
  absolute paths.
- FTS5 real-history recall benchmark: passed. The new
  `benchmark_fts5_recall.py` built 100 source-backed recall cases from the
  local 949-thread registry without writing private text to the report. The
  sampled corpus observed 949 registry threads, 949 clean-source threads, 949
  SQLite index threads, 800 eligible threads after visible-source/noise/safety
  filtering, and 9,420 clean-source messages. The first run found 99/100 FTS5
  top-10 hits; the single miss was categorized as
  `expected_line_absent_from_sqlite`, not a lexical FTS ranking miss. The
  onboarding consistency probe then found 5 stale SQLite indexes and repaired
  all 5 by rebuilding from the matching source rollouts. The post-repair
  benchmark observed 9,424 clean-source messages and mixed 84 exact
  `source_phrase` cases with 16 `normalized_source_phrase` cases. FTS5 hit
  91/100 in top-1, 100/100 in top-5, and 100/100 in top-10, with
  `expected_line_absent_from_sqlite=0`. The production hybrid path matched the
  same 100/100 top-10 result. The output uses hashed case ids, hashed thread
  ids, source line numbers, and aggregate metrics; it does not include raw
  query text or snippets unless `--include-private-text` is explicitly
  requested for local debugging.
- selected semantic label source-review smoke: passed. The new
  `smoke_semantic_scope_source_review.py` ran a live DeepSeek-compatible review
  over selected sidecar label cases after strict filtering, with retry support
  for transient reviewer failures. Broader review slices were used as failure
  discovery and pushed `relationship_continuity`, `open_question`,
  `idea_seed`, `technical_work`, and media-like `reading_notes` evidence
  through stricter prompt and materializer gates rather than lowering the
  review bar. The current strict materialization then passed a 5-case live
  review slice with 5 of 5 labels supported by the matching clean-source
  message (`pass_rate=1.0`) and no model call failures. This is not human
  review or a global correctness claim; it is a stronger quality signal than
  materialization alone. Suppressed soft labels still need more
  high-confidence, source-backed model findings before they should be trusted.
- DeepSeek model routing and Pro-agent recovery: passed for the recovery path
  and diagnostic for stricter source-review. `deepseek_model_routing.py` now
  keeps flash as the default fast/background route while routing
  `slow_adjudication`, `suppressed_label_recovery`, and
  `agentic_source_review` to `deepseek-v4-pro` unless explicitly overridden.
  The suppressed-label recovery smoke first observed 8 real cases / 11
  candidate labels after filtering out old empty-evidence sidecar candidates.
  The live Pro-agent recovery then inspected clean source through a tool and
  recovered 3 of 5 candidate labels across 3 cases through the unchanged strict
  materializer (`strict_gate_relaxed=false`), covering `idea_seed`,
  `open_question`, and `reading_notes`. The same Pro-agent source-review path
  executed against 5 current strict sidecar labels with tool observations and
  high cache reuse, but a stricter 0.75 pass-rate run remained diagnostic
  (`pass_rate=0.6`) and flagged remaining `personal_reflection` /
  `reading_notes` ambiguity. That failure is kept as source-review evidence for
  further Stage 2 hardening, not papered over by lowering materializer gates.
- DeepSeek KV-cache regression probe: passed. A bounded live
  `semantic_scope_labeling` probe with `--samples-per-job 2 --concurrency 2`
  now schedules same-prefix diversity samples in warm-up waves. The first
  request in a new prefix was cold while the second same-prefix request reached
  a near-warm hit rate, so an aggregate near 50% is interpreted as one
  cold-plus-one-hot sample rather than failed cache optimization. The
  source-review smoke now also reports aggregate `usage` and `cache` telemetry;
  a repeated four-case review warmed from a low first-run hit rate to a high
  second-run hit rate without exposing clean-source text.
- MCP tool-list smoke: passed
- MCP stdio JSON-RPC process smoke: passed in the unit suite
- plugin build smoke: passed; `hooks_auto_enabled=false`
- package-level plugin install/MCP/uninstall smoke: passed in a temporary
  plugin root, including an installed `.mcp.json` JSON-RPC smoke for
  `initialize`, `notifications/initialized`, `tools/list`, and `tools/call`
- real Codex app-server plugin manager and MCP host smoke: passed with Codex
  Desktop app-server `0.130.0`; `marketplace/add`, `plugin/read`,
  `plugin/install`, `config/mcpServer/reload`, `mcpServerStatus/list`,
  `thread/start`, `mcpServer/tool/call sync_status`, `plugin/uninstall`, and
  `marketplace/remove` all completed through the real host. The smoke observed
  expected `sync_status` payload fields: `available_requires_sync_dir`,
  `local_folder`, and `status/push/pull/repair`. Run-id-scoped `dist/`,
  `.tmp`, and Codex plugin-cache artifacts were removed.
- local-folder sync `push/status/repair/pull` smoke: passed with
  `raw_rollout_included=false`, including the clean-source semantic scope-label
  sidecar, device-neutral bundle registry locators, and target-registry path
  repair on pull
- single-machine dual-device sync smoke: passed. The smoke models device A and
  device B registries, verifies Windows/POSIX-shaped source locator cleanup,
  confirms generated artifact locators repair to the target registry, preserves
  bidirectional conflicts, keeps raw rollout excluded by default, and verifies
  raw rollout transfer only when `include_raw` is explicit. It records
  `physical_second_machine=false` and `real_cloud_backend=false`.
- HTTP object-storage sync smoke: passed. The adapter reused the same sync
  manifest/privacy contract over real HTTP object `PUT`/`GET` calls against a
  local object-store server, then pulled into a target registry with generated
  artifact locators repaired and raw rollout still excluded by default. It
  records `object_storage_protocol_executed=true`,
  `physical_second_machine=false`, and `real_cloud_backend=false`.
- Docker and WSL alternate-runtime sync smoke: passed. The host created the
  bundle, Docker and WSL each ran `status`, `repair`, and `pull`, and the
  pulled target registries used runtime-local generated-artifact locators with
  workspace and raw rollout unresolved. It records
  `physical_second_machine=false` and `real_cloud_backend=false`.
- lifecycle hook subconscious scheduling smoke: passed. A real `SessionStart`
  hook run returned in under one second and reported `subconscious_maybe_start`
  as a detached scheduler enqueue instead of waiting on foreground
  `subprocess.run(... timeout=...)`. The background scheduler retains its own
  lock/lease protections, and its default DeepSeek job path now uses four-way
  job concurrency with two samples per job unless explicitly overridden.
- unified Stage 0-5 smoke runner: passed and cleaned its run-id-scoped
  `dist/`/`.tmp` artifacts
- import-coupling guard: passed. The script import graph has no same-directory
  cycles; `registry.py` no longer imports `retrieval.py` at module load time;
  and `prompt_recall_core.py` is guarded against becoming a broad foreground
  import hub again.

## Scan Notes

A best-effort secret-like/local-path scan was run over the repository excluding
generated folders, vendored dashboard assets, and caches. It checks common
OpenAI-style keys, bearer headers, and Windows absolute paths. Hits were
limited to redaction-focused test fixtures and code variable names such as
`api_key`.

Allowed fixture markers are narrow and explicit:

- `FAKE_TEST_OPENAI_API_KEY`
- `FAKE_TEST_LOCAL_PATH`
- `FAKE_TEST_WINDOWS`

Environment-variable reads are not allowlisted when the same line contains an
OpenAI-style literal secret shape.

No real OpenAI-style key, bearer header, or Windows local user path was
identified in the scan output. This scan is not a complete secret detector for
every token/vendor/cookie shape.

## Example Bundle

`examples/public-memory-bundle/` is synthetic and contains no `rollout.jsonl`.
Its manifest sets `raw_rollout_included` to false. The public clean-source
sample now includes a non-project metaphor/pivot turn, a synthetic
DeepSeek/subconscious-compatible `semantic_scope_labels` staging finding, and a
matching semantic scope-label sidecar, so Stage 2 casual-important recall can
be demonstrated without private biography or hard-coded fuzzy phrase expansion.

## Remaining Public-Readiness Gaps

- Refresh this evidence after any further code changes.
- Run an interactive Desktop UI marketplace flow or external install review if
  claiming support across every Codex client surface. Current real-host
  evidence is headless Codex app-server, not manual UI coverage.
- Broaden Stage 3 release evidence beyond the current Windows/MacBook physical
  smoke and one managed R2 provider run if claiming broader provider/client
  coverage. Local HTTP object-storage remains labeled as simulation; the R2 run
  is real managed-provider evidence, not a provider matrix.
- Continue Stage 2 life-wide memory evidence beyond the selected top-5 recall,
  current strict source-review slices, and first Pro-agent recovery smoke:
  broaden suppressed-label recovery samples, use Pro-agent source-review
  failures as training/evidence-selection feedback, and avoid treating sidecar
  labels as source truth.
