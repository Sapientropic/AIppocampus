# Stage 0-5 Readiness Snapshot

This is a current-state evidence matrix for completing roadmap stages 0 through
5. The canonical requirements remain in `docs/roadmap.md`; this file records
what the current worktree can and cannot honestly claim.

Snapshot date: 2026-05-27.

## Can Claim Now

- Stage 0 baseline has working clean-source, search, registry, hooks,
  lifecycle, subconscious, segment, and docs-health foundations covered by the
  current unit suite. Lifecycle hooks now enqueue subconscious scheduling as a
  detached action instead of waiting in the foreground hook timeout window.
- Stage 1 has public-facing repository docs for architecture, install,
  contribution, demo scenarios, privacy/security, and dated public-readiness
  verification, plus a synthetic example memory bundle and a unified Stage 0-5
  smoke runner.
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
  recovered 3 of 5 candidate labels across 3 real cases through the unchanged
  strict materializer (`strict_gate_relaxed=false`). A stricter Pro-agent
  source-review diagnostic also found remaining ambiguity in current
  `personal_reflection` / `reading_notes` cases, so those failures feed the
  next evidence-selection pass instead of lowering sidecar gates.
  These are navigation layers over original text, not summary replacements.
- Stage 4 now has a first local MCP server at
  `skills/aippocampus/scripts/aippocampus_mcp_server.py`, including a
  process-level stdio JSON-RPC smoke for `initialize`, `tools/list`, and
  `tools/call`. The package-level plugin smoke also exercises the installed
  plugin `.mcp.json` as a JSON-RPC client path, including the initialized
  notification commonly sent by MCP hosts. A real Codex app-server smoke now
  installs the plugin, reloads Codex MCP config, lists the `aippocampus` server
  through the Codex MCP host, starts a real app-server thread, and calls
  `mcpServer/tool/call` for `sync_status`.
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
  repaired to runtime-local generated artifact paths.
- Stage 5 now has a repo-local plugin source package under
  `plugins/aippocampus/` and a build script that copies the skill package into
  a distributable plugin directory, plus a package-level temporary
  install/MCP/uninstall smoke that launches MCP from the installed plugin
  config. The heavier `plugins/aippocampus/smoke_real_codex_host.py` smoke also
  uses real Codex `marketplace/add`, `plugin/read`, `plugin/install`,
  `plugin/uninstall`, and `marketplace/remove` app-server methods against a
  run-id-scoped local marketplace, then verifies cleanup.
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
  refreshed after every code slice and the install paths are validated outside
  this single working copy.
- Stage 2 life-wide memory is not complete until semantic label correctness is
  reviewed more broadly, especially for currently suppressed high-risk labels
  such as `relationship_continuity`, `open_question`, `idea_seed`,
  `technical_work`, `life_context`, and `preference`. The first Pro-agent
  recovery smoke proves some suppressed labels can be restored through stronger
  evidence, but it is only a selected slice. Current
  labels, timeline groups, semantic sidecars, real-registry aggregate smoke,
  dynamic semantic sidecar smoke, recall eval prompts, source-review samples,
  and ambient scents are navigation hints only.
- Stage 3 is not fully cross-device/product-ready until sync has real
  cross-machine or managed cloud/object-storage provider evidence beyond the
  single-machine local-folder and local HTTP object-store models. Docker/WSL
  alternate-runtime evidence is stronger than two folders on one host, but it
  still does not prove a second physical device or a real cloud backend.
- Stage 4 still needs broader client coverage beyond the headless Codex
  app-server path, such as an interactive Desktop UI flow or another Codex
  client surface. Current real-host evidence does not prove every UI wrapper.
- Stage 5 still needs public distribution docs and external install review.
  The real Codex app-server plugin manager path is verified locally, but a
  public marketplace submission or third-party install has not been exercised.

## Evidence Matrix

| Stage | Current evidence | Missing proof |
| --- | --- | --- |
| 0 | `python -m unittest discover -s tests -t .` passes 308 tests, docs health, hook installer tests, onboarding tests, Ruff `E9` + full Pyflakes `F`, and import-coupling guards for script cycles / hook import fan-out | Keep full suite green after each slice |
| 1 | `README.md`, `CONTRIBUTING.md`, architecture/install/demo/privacy docs, synthetic example bundle, docs health guardrails, dated full-suite/scan notes, `run_stage_0_5_smoke.py` unified smoke runner | External install review, repeated full-suite/scan evidence after each release slice |
| 2 | Registry, clean source, cognitive map, semantic triggers, subconscious jobs, deterministic `scope_labels`, mocked DeepSeek `semantic_scope_labeling` job-to-sidecar test, `build_semantic_scope_labels.py` materializer, dynamic `semantic-scope-labels.jsonl` sidecar merging with strict per-label evidence gates for every materialized label, scope-filtered clean-source search, public casual-important metaphor/pivot example, `life_wide` timeline groups with source refs, quiet life-wide ambient scent with anti-over-personalization tests, real-registry aggregate coverage smoke with claim-level/ratio guards, refreshed 949-thread local registry, full-candidate real-history semantic sidecar smoke evaluating 609 selected candidates and expanding to 27 threads/119 rows before strict filtering, v2 fresh DeepSeek probe with 11 findings / 15 accepted labels / complete per-label evidence, current strict sidecars at 2 threads/5 rows/5 timeline turns, selected source-evidence recall eval with 24/24 top-5 hits, selected source-review smoke with 5/5 supported current strict label cases, DeepSeek flash/pro route tests, and live Pro-agent suppressed-label recovery restoring 3/5 candidate labels without relaxing strict gates | Broader human/source review, broader Pro-agent recovery, and better model-side evidence to restore high-confidence coverage for suppressed soft labels |
| 3 | `sync_bundle.py`, `sync_object_storage.py`, `export_bundle.py`, `import_bundle.py`, global thread store defaults, semantic scope-label sidecar sync, device-neutral bundle registry locators, target-registry path repair on pull, conflict-preserving pull tests, single-machine dual-device/cross-OS-path-shape smoke, local HTTP object-storage adapter smoke, Docker/WSL alternate-runtime smoke when available, and install docs | Physical second-machine or managed cloud/object-storage provider smoke |
| 4 | `aippocampus_mcp_server.py`, `.mcp.json`, MCP unit tests, source stdio JSON-RPC process smoke, installed-plugin `.mcp.json` JSON-RPC smoke, real Codex app-server MCP host list and `mcpServer/tool/call sync_status` smoke | Interactive Desktop UI / alternate Codex client verification |
| 5 | `plugins/aippocampus/`, `build_plugin_package.py`, plugin contract tests, package-level temporary install/MCP JSON-RPC/uninstall smoke, real Codex app-server marketplace/plugin install/uninstall smoke | Public distribution docs and external install review |

## Next Slice

Continue Stage 2 hardening by broadening Pro-agent suppressed-label recovery
and using strict source-review failures to improve evidence generation, not
lexical expansion or looser materializer gates. Then run broader
recall-quality evaluation and physical
second-machine/managed cloud sync and external install/public distribution
smokes for Stages 3 through 5.
