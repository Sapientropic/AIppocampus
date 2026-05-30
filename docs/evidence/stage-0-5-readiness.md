# Stage 0-5 Readiness Snapshot

This is a current-state evidence matrix for completing roadmap stages 0 through
5. The canonical requirements remain in `docs/roadmap.md`; this file records
what the current worktree can and cannot honestly claim.

Snapshot date: 2026-05-30.
Repository-layout command paths refreshed: 2026-05-29.
Public-core license and adapter boundary refreshed: 2026-05-30.

Keep this page focused on claim boundaries and missing proof. Dated command
evidence belongs in `docs/evidence/public-readiness-verification.md`; next-slice task
handoff belongs in `docs/planning/next-iteration-plan.md`. The benchmark and smoke
navigation map lives in `docs/evidence/benchmark-evidence-map.md`.

## Can Claim Now

- Stage 0 baseline has working clean-source, search, registry, hooks,
  lifecycle, subconscious, segment, and docs-health foundations covered by the
  current unit suite. Lifecycle hooks now enqueue subconscious scheduling as a
  detached action instead of waiting in the foreground hook timeout window.
- Stage 1 has public-facing repository docs for architecture, install,
  contribution, Apache-2.0 public-core licensing/adapter boundaries, demo
  scenarios, privacy/security, and dated public-readiness verification, plus a
  synthetic example memory bundle and a unified Stage 0-5 smoke runner. The
  package-level temporary install smoke and the real Codex app-server plugin
  manager smoke now both pass without silently enabling hooks.
- Stage 2 now has first-pass deterministic `scope_labels` in clean-source
  messages/turns, scope-label filtering in clean-source search, and a
  bounded source-backed `life_wide` timeline section in
  `project_timeline.json`. The prompt hook can use that `life_wide` sidecar as
  a quiet scent only when a prompt has both recency and life-wide scope cues.
  The public example now includes a synthetic casual-important metaphor/pivot
  turn labeled through a `semantic_scope_labels` subconscious staging finding
  and `semantic-scope-labels.jsonl`, so fuzzy life-wide judgments can come from
  a DeepSeek/subconscious-compatible sidecar instead of expanding the hard-coded
  lexical list. The `smoke_life_wide_registry.py` diagnostic can now inspect a
  real local registry and report only aggregate life-wide coverage counts,
  without emitting private text, titles, source refs, or absolute paths. The
  `smoke_semantic_scope_real_history.py` smoke can observe existing dynamic
  semantic sidecar coverage without external calls, and its explicit live mode
  can run bounded parallel DeepSeek-compatible `semantic_scope_labeling`
  samples, write source-backed staging findings, materialize real clean-source
  `semantic-scope-labels.jsonl`, and refresh the timeline. Explicit live mode
  fails on missing API keys, partial model failures, or empty model findings
  rather than falling back to deterministic sidecar observation. The
  unit suite also covers the mocked DeepSeek job-to-sidecar path for
  `semantic_scope_labeling`. The current local registry has also been refreshed
  beyond the newest slice: onboarding registered 63 additional sessions, bringing
  the aggregate local registry evidence to 949 threads with complete clean
  source/index/graph artifacts, 101 scope-labeled threads, 80 non-technical
  life-wide threads, and 142 project groups. The semantic real-history smoke now
  emits `claim_level`, coverage ratios, and `cannot_claim` fields so `sufficient`
  cannot be mistaken for full-history completion. The latest full-candidate
  live semantic run selected 609 currently unlabeled life-wide candidate turns
  across 98 threads, evaluated all of them in 26 successful parallel
  DeepSeek-compatible batches with no model failures, accepted 99 new
  source-backed staging findings, and expanded materialized dynamic semantic
  sidecars from 7 threads/20 rows to 27 threads/119 rows before strict review
  filtering. After expanded source-review, the semantic job prompt was bumped
  to `aippocampus-subconscious-jobs-v2` and now requires per-label evidence for
  every materialized label. The materializer no longer accepts row-level
  confidence as a fallback; it uses label-specific evidence thresholds and
  intentionally suppresses broad or over-inferred labels such as generic
  `relationship_continuity`, ordinary immediate `open_question`, film/media
  reactions mislabeled as `reading_notes`, and adjacent-context
  `idea_seed`/`technical_work` guesses. A fresh v2 no-write DeepSeek probe over
  32 candidate turns produced 11 accepted findings and 15 accepted labels with
  complete sufficient per-label evidence, covering seven canonical labels. The
  current strict materialization keeps only the labels that survived the
  stronger evidence gates, leaving 2 threads/5 rows and 5 latest timeline turns
  with semantic labels. A selected source-evidence recall
  eval now builds fuzzy life-wide prompts from dynamic
  low-frequency source cue terms, not a hand-expanded word list, and uses
  dynamic clean-source IDF reranking to verify that 24 of 24 selected prompts
  return the expected clean-source evidence in top-5 results
  (`top_k_hit_rate=1.0`) while emitting only hashed case ids and aggregate
  counts. A separate live source-review smoke samples semantic sidecar labels
  one label at a time, retries transient reviewer failures, and now verifies
  the current strict materialization at 5 of 5 selected labels supported by the
  matching clean-source message (`pass_rate=1.0`) with no model-call failures.
  The latest review sample covers the labels that survived the stricter
  materializer; high-risk soft labels that lack strong per-label evidence are
  intentionally suppressed rather than treated as supported. DeepSeek model
  routing now keeps flash as the default fast/background model and routes
  slower `suppressed_label_recovery` / `agentic_source_review` work to Pro. A
  live Pro-agent suppressed-label recovery smoke filtered out old
  empty-evidence sidecar candidates, inspected clean source through a tool, and
  recovered 3 labels from the currently available 8 suppressed cases / 11
  candidate labels through the unchanged strict materializer
  (`strict_gate_relaxed=false`). A broader 96-case live source-review smoke now
  passes 84 cases (`pass_rate=0.875`) with every covered label category above
  the 0.65 per-label floor and no failed label category; the remaining
  individual misses stay as ambiguous row evidence instead of relaxing gates.
  These are navigation layers over original text, not summary replacements.
- Stage 4 now has a first local MCP server at
  `skills/aippocampus/scripts/aippocampus_mcp_server.py`, including a
  process-level stdio JSON-RPC smoke for `initialize`, `tools/list`, and
  `tools/call`. The package-level plugin smoke also exercises the installed
  plugin `.mcp.json` as a standalone MCP stdio JSON-RPC client path, including
  the initialized notification commonly sent by MCP hosts and a `sync_status`
  tool call. A real Codex app-server smoke now installs the plugin, reloads
  Codex MCP config, lists the `aippocampus` server through the Codex MCP host,
  starts a real app-server thread, and calls `mcpServer/tool/call` for
  `sync_status`. MCP tool failures now have structured error contracts for
  malformed arguments, missing registry state, missing clean source, missing
  turn selectors, unknown ids, unsupported mutation requests, and generic tool
  failures.
- Stage 3 now has a first local-folder sync backend at
  `skills/aippocampus/scripts/sync_bundle.py`, with `status`, `push`, `pull`,
  and `repair`. The local-folder sync path includes the clean-source semantic
  scope-label sidecar, writes device-neutral bundle-relative registry locators,
  and repairs generated-artifact paths to the target registry on pull. The
  `smoke_cross_device_sync.py` smoke now models device A/device B registries on
  one machine, verifies Windows/POSIX-shaped source locator cleanup, preserves
  bidirectional conflicts, and checks raw rollout transfer remains opt-in. The
  HTTP object-storage adapter at
  `skills/aippocampus/scripts/sync_object_storage.py` reuses the same manifest
  and privacy/path-repair contract over real HTTP `PUT`/`GET` object keys. The
  `smoke_object_storage_sync.py` smoke runs that adapter against a local HTTP
  object store and proves the object protocol path without claiming a managed
  cloud provider. The
  `smoke_alternate_runtime_sync.py` smoke can also run the same bundle through
  a real Docker or WSL runtime and verify that target registry locators are
  repaired to runtime-local generated artifact paths. A dated physical
  Windows-to-MacBook smoke now verifies the same bundle contract on a real
  second device, including target path repair, bidirectional conflict
  preservation, and raw rollout exclusion. A dated managed Cloudflare R2
  encrypted object-storage smoke now verifies provider-aware signing,
  encrypted push/status/repair/pull, recipient matching, target-registry
  materialization, raw rollout exclusion, and cleanup of all uploaded encrypted
  objects.
- Stage 5 now has a repo-local plugin source package under
  `plugins/aippocampus/` and a build script that copies the skill package into
  a distributable plugin directory, plus a package-level temporary
  install/MCP/uninstall smoke that launches MCP from the installed plugin
  config. The heavier `plugins/aippocampus/smoke_real_codex_host.py` smoke also
  uses real Codex `marketplace/add`, `plugin/read`, `plugin/install`,
  `plugin/uninstall`, and `marketplace/remove` app-server methods against a
  run-id-scoped local marketplace, then verifies cleanup. Public distribution,
  uninstall, and rollback docs now distinguish skill-only install, plugin
  package install, MCP config, hook installers, and optional external-model
  routes.
- Plugin packaging does not silently enable prompt or lifecycle hooks. Hook
  installers remain explicit action surfaces after privacy review.
- Hook-time subconscious work now has a clearer SLA boundary: foreground hooks
  enqueue the scheduler and read already materialized sidecars; DeepSeek-backed
  subconscious jobs run in detached workers with parallel samples, but
  same-prefix diversity samples are scheduled in warm-up waves so the first
  completed request can populate DeepSeek's server-side KV cache before
  follow-up samples launch. Hook timeout or missing background output must not
  be treated as a mechanical semantic judgment.

## Cannot Claim Yet

- Stage 1 is not fully public-release-ready until the dated local checks are
  refreshed after every code slice. Temporary plugin install and real Codex
  app-server host paths are verified, but public marketplace submission,
  third-party fresh-clone review, and second-user install are not yet claimed.
- Stage 2 life-wide memory is not complete until semantic label correctness has
  broader human/source review beyond selected automated slices. The current
  Pro-agent recovery and 96-case source-review smokes prove better selected
  coverage, but high-risk suppressed labels such as
  `relationship_continuity` and `life_context` still need stronger
  source-backed model findings before being restored. Current
  labels, timeline groups, semantic sidecars, real-registry aggregate smoke,
  dynamic semantic sidecar smoke, recall eval prompts, source-review samples,
  and ambient scents are navigation hints only.
- Stage 3 now has selected physical second-device and managed R2 provider
  evidence, but it is not a broad provider/client matrix. Do not generalize the
  R2 run into all S3-compatible/GCS/cloud-folder providers, and do not treat
  local HTTP object-storage as managed-provider evidence.
- Stage 4 still needs broader client coverage beyond the headless Codex
  app-server path and the standalone stdio JSON-RPC client if claiming every
  Codex UI wrapper. Current real-host evidence does not prove an interactive
  Desktop UI marketplace flow.
- Stage 5 still needs public marketplace submission or independent third-party
  install review if those are claimed. The real Codex app-server plugin manager
  path and package-level installed-plugin MCP path are verified locally.

## 2026-05-30 Closeout Addendum

The #55/#56 closeout refreshes evidence without changing the claim boundary
above. The canonical command details live in
`docs/evidence/public-readiness-verification.md`.

- #55 adds a 24-case live source-review pass for the current strict semantic
  sidecar slice and records a broader 96-case diagnostic live run with strong
  semantic pass-rate but one live model partial failure. Treat the broader run
  as diagnostic, not as a green gate.
- #55 also refreshes selected retrieval evidence across all eight canonical
  labels. That is selected retrieval/ranking quality evidence, not proof of
  full-history semantic completeness or global label correctness.
- #56 refreshes the package-level temporary plugin install, installed-plugin
  standalone MCP stdio JSON-RPC client, and headless Codex Desktop app-server
  local-marketplace host path. Public marketplace submission, independent
  third-party install review, second-user install, and human interactive
  Desktop UI marketplace click-through remain unclaimed unless separately
  verified.
- #27/#28 add public-safe memory pain fixture evidence and a short report in
  `docs/evidence/memory-pain-fixture-report.md`. This is Stage 2 boundary evidence for
  source-backed recall and unsupported-memory suppression, not competitor
  superiority, live semantic-model quality, real-history pain coverage, or a
  real Track D runtime compaction-continuity proof.
- #66 adds a deterministic synthetic Track D runner for compaction-continuity
  measurement. #65 adds the first deterministic correction-reconsolidation
  runtime helper for source-backed activation/outcome rows, adjudication
  candidates, and post-compaction active-anchor rendering. Together they upgrade
  the measurement and event surfaces. #45 adds a slow/live real Codex
  app-server long-session smoke that ran 50 completed pre-compaction turns,
  forced `thread/compact/start`, observed `contextCompaction` plus completed
  `preCompact` / `postCompact` hooks, verified post-compaction recall of a
  corrected synthetic state, and rebuilt clean source from the real rollout
  without exposing raw prompts or local paths. This still does not claim live
  semantic adjudication quality or private real-history correction survival.
- #67 adds the first deterministic coding decision-event extractor and compact
  ticket renderer over clean-source messages. It upgrades rejected-route staging
  evidence, but it does not claim complete design-intent extraction, global
  validity for old branch-local decisions, or host-agent intervention timing.
- #68 adds the first deterministic agency affordance-map and ticket selector.
  It can propose one foreground source-backed ticket plus bounded backstage
  tickets for user correction, compaction loss, unfinished task reentry, and
  scheduled revisit triggers. It does not claim autonomous execution,
  host-agent timing quality, annoyance-risk calibration, or multi-host duplicate
  suppression.
- #71 adds the first internal retrieval score-fusion contract. It centralizes
  text/vector/graph ranking weights and source-join validation, while preserving
  exact/source-backed recall priority and keeping vectors/graphs optional
  ranking hints rather than source truth.
- #72 adds the first deterministic salience and adaptive threshold slice inside
  `question_tracking.py`. It reduces generic low-information question-link
  inputs and records why pair thresholds leaned toward completion or separation,
  but does not claim calibrated live semantic quality or user-confirmed
  threshold weights.
- #70 adds the first deterministic structured-text cognitive portrait
  benchmark. It compares compact portraits built from source-backed
  question/frontier/link findings against fuller clean-source injection,
  records source-ref back-pointers, quote-fidelity loss, and
  over-personalization risk, but does not claim live model behavioral
  equivalence or activation steering.
- #63 adds the first deterministic Journey Tracking P1-P3 core. It defines
  source-backed waypoint/journey structures, append-only waypoint history,
  conservative multi-thread instantiation, status transitions, expiry/TTL
  refresh, explicit feedback actions, and a fixture replay smoke comparing
  `current_frontier` against a plain summary baseline. It does not claim live
  `theme_emergence`, private real-history journey quality, predictive replay,
  or foreground Journey hint timing.
- #64 adds the first deterministic compensatory dream Phase 1 helper. It emits
  adjudication-only `dream_synthesized` candidates from source-backed single-thread
  extraction rows, carries thread-scoped source refs on every bridge claim,
  discards unsourced/prior-dream rows and cross-thread refs, preserves
  source-derived scope labels through live question extraction, and keeps
  trigger defaults lower than extraction and out of foreground hooks.
  Background-adjudicated dream hypotheses can now project onto the existing
  working-memory substrate for recall/ambient/reflection consumers. It still
  does not claim prospective analysis, amplification, active imagination, live
  dream quality, or any unadjudicated dream influence on recall/reflection
  space.
- #69 adds the first deterministic reflection-space topology/feedback MVP. It
  renders Journey/Waypoint/current-frontier topology data with
  expand/merge/revive/abandon actions and converts source-ref-carried recall
  effects, turning points, user corrections, and map feedback into
  ranking/confidence/visibility adjustments. It does not claim polished
  visualization, scheduler/AAR enforcement, live user behavior change,
  calibrated suggestion timing, clean-source rewrites, or Journey history
  mutation.

## Evidence Matrix

| Stage | Current evidence | Missing proof |
| --- | --- | --- |
| 0 | `python tools/aippocampus/run_tests.py --tier fast` covers the default deterministic regression path, with docs health, hook installer tests, Ruff `E9` + full Pyflakes `F`, mypy coverage, retrieval/onboarding/warm recall/registry search/prompt recall/subconscious job behavior tests, and import-coupling guards for script cycles / hook import fan-out. `--tier full` remains the explicit release/readiness suite. | Keep the fast tier green after each slice; run the slow, benchmark, or full tier when claiming the surface they own |
| 1 | `README.md`, `CONTRIBUTING.md`, `docs/guides/public-core-boundary.md`, architecture/install/demo/privacy docs, synthetic example bundle, docs health guardrails, dated full-suite/scan notes, Apache-2.0 package/plugin/provenance metadata, `tools/aippocampus/smoke/run_stage_0_5_smoke.py` unified smoke runner, package-level temporary plugin install/MCP/uninstall smoke, and real Codex app-server plugin manager/MCP host smoke | Third-party fresh-clone or second-user install review, public marketplace submission if claimed, and repeated full-suite/scan evidence after each release slice |
| 2 | Registry, clean source, cognitive map, semantic triggers, subconscious jobs, deterministic `scope_labels`, mocked DeepSeek `semantic_scope_labeling` job-to-sidecar test, `build_semantic_scope_labels.py` materializer, dynamic `semantic-scope-labels.jsonl` sidecar merging with strict per-label evidence gates for every materialized label, scope-filtered clean-source search, public casual-important metaphor/pivot example, `life_wide` timeline groups with source refs, quiet life-wide ambient scent with anti-over-personalization tests, real-registry aggregate coverage smoke with claim-level/ratio guards, refreshed 949-thread local registry, full-candidate real-history semantic sidecar smoke evaluating 609 selected candidates and expanding to 27 threads/119 rows before strict filtering, v2 fresh DeepSeek probe with 11 findings / 15 accepted labels / complete per-label evidence, current strict sidecars at 2 threads/5 rows/5 timeline turns, selected source-evidence recall eval with 24/24 top-5 hits, broader selected source-review smoke with 96 cases / 84 supported / 0 failed label categories, DeepSeek flash/pro route tests, live Pro-agent suppressed-label recovery restoring 3 labels from 8 suppressed cases / 11 candidate labels without relaxing strict gates, synthetic Track D compaction-continuity benchmark coverage for event-chain source fidelity / correction-anchor recall / anti-nag / repeated-anchor and stale-anchor suppression, slow/live #45 real Codex app-server long-session smoke coverage for 50 pre-compaction turns, real compaction hooks, synthetic correction survival, and clean-source rebuild verification, deterministic #65 correction-reconsolidation event/adjudication helper coverage, deterministic #67 coding decision-event/ticket helper coverage, deterministic #68 agency affordance-map/ticket-selector coverage, deterministic #71 retrieval score-fusion policy coverage, deterministic #72 question salience/adaptive-threshold coverage, deterministic #70 structured-text cognitive portrait benchmark coverage, deterministic #63 Journey Tracking P1-P3 core coverage, deterministic #64 compensatory dream Phase 1 coverage, and deterministic #69 reflection-space topology/feedback MVP coverage | Broader human/source review and stronger model-side evidence to restore high-confidence coverage for still-suppressed soft labels; live semantic adjudication quality, private real-history compaction survival, host-agent decision-ticket timing, agency-ticket annoyance calibration, measured real vector/graph fusion quality, calibrated question salience/threshold weights, private/live portrait quality, live Journey/theme quality, adjudicated real-history dream quality before dream output influences recall/reflection space, and real reflection-space behavior/UI evidence before visual polish claims |
| 3 | `sync_bundle.py`, `sync_object_storage.py`, `export_bundle.py`, `import_bundle.py`, global thread store defaults, semantic scope-label sidecar sync, device-neutral bundle registry locators, target-registry path repair on pull, conflict-preserving pull tests, single-machine dual-device/cross-OS-path-shape smoke, local HTTP object-storage adapter smoke, Docker/WSL alternate-runtime smoke when available, physical Windows-to-MacBook sync smoke, managed Cloudflare R2 encrypted object-storage smoke, Python 3.9 sync path-repair compatibility coverage, and install docs | Broader provider matrix, cloud-folder client evidence if claimed, and longer-running multi-user/device operational soak |
| 4 | `aippocampus_mcp_server.py`, `.mcp.json`, MCP unit tests, structured MCP error-contract tests, source stdio JSON-RPC process smoke, installed-plugin `.mcp.json` standalone MCP JSON-RPC client smoke, real Codex app-server MCP host list and `mcpServer/tool/call sync_status` smoke | Interactive Desktop UI verification or additional Codex client surfaces only if claiming those wrappers |
| 5 | `plugins/aippocampus/`, `build_plugin_package.py`, plugin contract tests, public distribution/uninstall/rollback docs, package-level temporary install/MCP JSON-RPC/uninstall smoke, real Codex app-server marketplace/plugin install/uninstall smoke | Public marketplace submission or independent third-party install review if claimed |

## Next Slice

Continue Stage 2 hardening with human/source review and better source-backed
model findings for still-suppressed soft labels, not lexical expansion or
looser materializer gates. Then prioritize broader Stage 3 provider/client soak
only where claims require it, plus interactive UI, marketplace, or independent
distribution review only when those surfaces become explicit release claims.
