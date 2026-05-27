# Public Readiness Verification

Initial evidence date: 2026-05-27.
Repository-layout command paths refreshed: 2026-05-28.

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

## Command Ledger

```powershell
python tools\aippocampus\docs\check_docs_health.py --json
python -m unittest discover -s tests -t .
python -m compileall -q skills plugins tests tools benchmarks benchmark_corpus
python -m ruff check skills plugins tests tools benchmarks
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

- full unit suite: 308 tests passed
- docs health: `ok=true`
- Python compile check: passed
- Ruff check: passed. The Ruff baseline now includes full Pyflakes (`F`) plus
  syntax-level `E9`, so unused imports, undefined names, and stale local
  variables are caught instead of only parse-time failures.
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
- Run cross-device sync smoke outside the single-machine host entirely,
  preferably on a physical second machine or managed cloud/object-storage
  provider. Docker alternate-runtime and local HTTP object-storage evidence are
  now available locally, but they are not a real second device or cloud
  provider.
- Continue Stage 2 life-wide memory evidence beyond the selected top-5 recall,
  current strict source-review slices, and first Pro-agent recovery smoke:
  broaden suppressed-label recovery samples, use Pro-agent source-review
  failures as training/evidence-selection feedback, and avoid treating sidecar
  labels as source truth.
