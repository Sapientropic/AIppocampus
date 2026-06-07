# Public Readiness Verification

Initial evidence date: 2026-05-27.
Repository-layout command paths refreshed: 2026-05-29.

This file is a dated verification ledger. It preserves summarized command
evidence for release-readiness work, but the current Stage 0-5 claim boundary
lives in `docs/evidence/readiness/stage-0-5-readiness.md` and the canonical product requirements
remain in `docs/roadmap.md`.

Older entries preserve the historical `--tier fast` command name as evidence of
what was run at the time. The current test taxonomy is defined in
`tools/aippocampus/test_tier_manifest.py`: use `--tier quick` for the small local
inner loop and `--tier pr` for the broad deterministic PR lane.

For the navigation map that connects benchmark runners, smoke scripts, corpus
records, and this ledger, see `docs/evidence/benchmark-evidence-map.md`.

Stable privacy rules live in `docs/guides/privacy-security-checklist.md`. Do not paste
raw command JSON here: local smoke outputs may contain machine-specific
temporary paths, so this document keeps only summarized evidence.

## 2026-06-07 Issue #784 Provider-Key Bridge OS Store Smoke

Issue #784 kept the provider-key bridge open after the env-only doctor and
explicit `.env` hook-wrapper work because the OS credential-store adapters still
needed real quality evidence. This slice added
`tools/aippocampus/smoke/smoke_provider_key_bridge_os_store.py`, which creates a
temporary provider-key test secret in the selected OS credential store, verifies
that the AIppocampus-owned hook wrapper can project it into a hook-process
environment update, and removes the temporary credential again.

Positive local evidence from the Windows host run:

- `python tools\aippocampus\smoke\smoke_provider_key_bridge_os_store.py --source windows-credential-manager --json`
  returned `ok=true`, `status=adapter_read_ok`, and `skipped=false`.
- The smoke wrote a temporary Windows Credential Manager generic credential,
  read it through the same wrapper path used by hook commands, confirmed the
  projected `DEEPSEEK_API_KEY` matched the temporary secret, and deleted the
  credential through the cleanup path.
- Public output reported no secret values, locator values, local temporary
  paths, or manifest-stored secret value.

Cross-platform contract evidence in the same slice:

- Unit tests cover macOS Keychain and Linux Secret Service command construction
  through the hook-wrapper adapter without printing the secret, service,
  account, or attribute locator in public summaries.
- The smoke supports `--source macos-keychain`, `--source linux-secret-service`,
  and `--source auto`; unsupported platforms or unavailable OS store tools
  return an explicit `skipped` report instead of pretending the adapter passed.

Cannot claim from this slice: arbitrary password-manager support, macOS or Linux
host-store success until the smoke runs on those hosts, already-running Codex
Desktop hook visibility, provider-key correctness or freshness, or default
`aippocampus doctor provider` reading credential stores. The doctor remains an
env-visibility diagnostic; the bridge remains explicit opt-in hook onboarding.

## 2026-06-05 Issue #643 R2 Provider Metadata Evidence Smoke

Issue #643 keeps metadata-padding decisions tied to real provider evidence
instead of speculative padding. This slice extended
`smoke_real_provider_encrypted_sync.py` to emit a public-safe
`provider_metadata` block and then ran it against the existing Cloudflare
R2-compatible provider configuration. The local run used `age` v1.3.1 installed
through the Go toolchain and an ephemeral generated age identity.

Positive evidence from the passing retry:

- Encrypted object-storage `push/status/repair/pull` passed with
  `recipient_match=yes`, `raw_rollout_synced_without_opt_in=false`, and no
  reported issues.
- `provider_metadata` observed 13 encrypted objects, 20,022 total ciphertext
  bytes, min 201 bytes, max 13,866 bytes, and size buckets
  `le_1KiB=10`, `le_4KiB=2`, `le_16KiB=1`.
- Path-shape counts were `encrypted_outer_manifest=1`,
  `encrypted_inner_manifest=1`, and `encrypted_ciphertext_object=11`.
- Cleanup deleted all 13 uploaded encrypted objects and confirmed none remained
  through the smoke cleanup path.

An earlier same-day attempt reached push/status/repair, produced the same
metadata observation shape, and deleted 13/13 uploaded encrypted objects, but
the final pull hit an `SSL: UNEXPECTED_EOF_WHILE_READING` transport error. Treat
that as a transient provider/client observation, not as a successful full smoke.

Cannot claim from this slice: metadata padding evaluated, traffic-analysis
resistance, provider-console cleanup, broad S3-compatible/GCS/cloud-folder
coverage, or long-duration provider/client stability. Provider account
identifiers, bucket names, object prefixes, credential values, raw private
source, and local temporary paths are intentionally omitted.

## 2026-06-05 Issue #697 Released PyPI And Client-Matrix Refresh

Issue #697 follows the source-install evidence below by checking the released
PyPI package and public MCP Registry state separately from GitHub main-branch
snapshots. The local `uvx` probe used temporary isolated `HOME`,
`USERPROFILE`, `APPDATA`, `LOCALAPPDATA`, `AIPPOCAMPUS_HOME`,
`AIPPOCAMPUS_REGISTRY_DIR`, `CODEX_HOME`, and `UV_CACHE_DIR` values, with
`PYTHONPATH` cleared.

Positive evidence:

- `python tools\aippocampus\release\check_agent_discovery_release.py --json`
  passed all eight release-discovery checks. PyPI latest was `0.1.1`, matching
  `server.json`, and the MCP Registry listed `0.1.1`.
- `uvx --refresh aippocampus --help` returned the packaged CLI help in 25.082
  seconds from the isolated environment.
- `uvx --refresh aippocampus mcp list-tools` returned the MCP tool catalog in
  3.573 seconds with nine tools.
- `uvx --refresh aippocampus onboard --provider codex --status --format json`
  returned `ok=true` in 17.761 seconds and used the isolated
  `AIPPOCAMPUS_REGISTRY_DIR`.

Release-boundary note:

- The released package status command still returned the provider matrix
  (`codex`, `claude-code`, and `generic-jsonl`) rather than a Codex-only status
  object. Treat this as a valid released package/provider-matrix status probe,
  not as evidence that the PyPI package has a provider-scoped Codex-only status
  surface.

Cannot claim from this slice: interactive Codex Desktop UI click-through,
public marketplace install UX, third-party install review, macOS/Linux
standalone binaries, signed installers, automatic updaters, or all client
wrappers.

## 2026-06-05 Issue #307 External Uvx Source-Install Probe

Issue #307 asks for public-readiness evidence that is not merely repository-local.
This slice ran clone-free `uvx` probes from outside the maintainer checkout with
`PYTHONPATH` cleared and temporary isolated `AIPPOCAMPUS_HOME`,
`AIPPOCAMPUS_REGISTRY_DIR`, and `CODEX_HOME` values.

Positive evidence for the current main snapshot:

- `uvx --refresh --from git+https://github.com/Sapientropic/AIppocampus.git
  aippocampus --help` built and installed commit
  `f004b2b52c21e168d07c2cb4e0382fce071d3724`, then returned the packaged CLI
  help in 13.647 seconds.
- `uvx --refresh --from git+https://github.com/Sapientropic/AIppocampus.git
  aippocampus mcp list-tools` returned the MCP tool catalog in 2.603 seconds.
- `uvx --refresh --from git+https://github.com/Sapientropic/AIppocampus.git
  aippocampus onboard --provider codex --status --format json` returned
  `ok=true` in 2.639 seconds and kept the status scoped to the Codex provider.

Release-boundary note:

- `uvx --refresh aippocampus onboard --provider codex --status --format json`
  against the published PyPI package returned successfully in 6.030 seconds, but
  the output did not include a provider scope and included additional provider
  status entries. Treat that as a release-refresh gap, not as positive evidence
  for provider-scoped Codex readiness. The #697 release refresh above confirms
  the later PyPI `0.1.1` package and MCP Registry entry, but the released status
  command still reports the provider matrix rather than a Codex-only status
  object.

Cannot claim from this slice: interactive Codex Desktop UI marketplace behavior,
public marketplace submission, second-user review, macOS/Linux standalone
binary support, or every client/provider surface.

## 2026-06-04 Issue #104 Post-Migration R2 Provider Re-Smoke

Issue #104 re-ran the encrypted object-storage provider path after the
device-key and plaintext-to-encrypted migration workflow from #58 / PR #86.
The run used the existing Cloudflare R2-compatible provider class through the
S3 SigV4 HMAC path against local checkout commit
`8d5e284281b171f75718455e0f93838f39f20509`.

Sanitized evidence from this run:

- Provider credentials were recovered from the existing local Cloudflare token
  path and persisted as `AIPPOCAMPUS_OBJECT_*` user environment variables for
  future operator smokes. `age` v1.3.1 was installed under the local Codex tool
  directory and `AIPPOCAMPUS_AGE_BIN` / `AIPPOCAMPUS_AGE_KEYGEN_BIN` were set.
- Baseline real-provider encrypted smoke passed with generated ephemeral age
  identity, encrypted `push/status/repair/pull`, `recipient_match=yes`,
  `raw_rollout_synced_without_opt_in=false`, and cleanup of all 13 uploaded
  encrypted objects.
- Post-migration sequence passed on the second full attempt: plaintext
  object-storage push, plaintext inventory, migration dry-run, migration to a
  fresh encrypted provider prefix, encrypted status/repair/pull, target
  registry materialization, raw-rollout exclusion, preservation of a preexisting
  local target file, plaintext cleanup dry-run, and explicit plaintext cleanup.
- Cleanup verification deleted 12/12 plaintext source objects and 13/13
  encrypted target objects for the completed attempt. A separate guard smoke
  confirmed object plaintext cleanup with `confirm=true` but without
  `verified_encrypted_target=true` returns
  `encrypted_target_verification_required`, and cleaned up its 12/12 temporary
  plaintext objects.

This is one dated post-migration Cloudflare R2-compatible provider re-smoke. It
does not claim broad S3-compatible, GCS XML, cloud-folder, multi-user, or
long-duration provider/client soak coverage. Provider account identifiers,
bucket names, object prefixes, credentials, raw private source, and local
temporary paths are intentionally omitted.

## 2026-06-04 React VCS Production-Like Source Disambiguation

Issue #254 added the first non-oracle source-disambiguation arm for the React
VCS adversarial fixture. The runner now has a `--production-like-retrieval`
mode that builds a local past-window source index, ranks source candidates
without using `required_past_source_ids`, and uses those ids only for grading.

Latest verification for this slice:

- `python -m pytest tests\aippocampus\test_benchmark_vcs_future_event_recall.py -q`:
  12 tests passed. The new tests cover current-vs-stale source ranking,
  track metadata from a sidecar file, and the rule that required source ids are
  not ranking input.
- `python benchmarks\aippocampus\benchmark_vcs_future_event_recall.py --dataset .tmp\react-real-vcs-adversarial-v2\react-adversarial-v2-fixture.jsonl --event-metadata .tmp\react-real-vcs-adversarial-v2\event-meta.json --production-like-retrieval --allow-non-cc0-dataset --output .tmp\react-real-vcs-adversarial-v2\react-adversarial-v2-production-like-retrieval-report.json --json`:
  produced a sanitized local report and exited nonzero under the default
  perfect-quality gate because the arm still has 30 lexical-near-miss false
  positives. The measured aggregate was 60/60 gold true positives, 0 source
  support failures, `current_source_top_k_hit_rate=1.0`,
  `current_vs_stale_pairwise_win_rate=1.0`, `wrong_source_evidence_rate=0.0`,
  and `negative_false_positive_rate=0.5263`.

The committed aggregate report is
`docs/evidence/benchmarks/react-real-vcs-production-like-disambiguation-2026-06-04.md`.
This is source-disambiguation evidence with an explicit hard-negative
calibration failure. It is not live model quality, wild VCS corpus quality,
private real-history quality, or license-safe redistribution of the local React
fixture.

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
lives in `docs/guides/public-core-boundary.md`; README, contribution docs, commercial
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
canonical report is `docs/evidence/benchmarks/memory-pain-fixture-report.md`.

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

## 2026-05-31 Russian Real-History Memory-Pain Smoke

Issue #108 turned a stricter private Russian real-history probe shape into a
public-safe, hash-only smoke family named `russian-real-history`. The family
covers Russian negative prompts that must not be upgraded to source-backed
evidence, Russian positive prompts for prior wording recovery, and a vague
cross-project plan prompt that should remain scent/diagnostic unless a strong
source bridge exists.

Latest verification for that slice:

- `python -m pytest tests\aippocampus\test_aippocampus_prompt_hook.py::AmbientRecallHookTests::test_russian_prior_wording_recall_can_recover_source_evidence tests\aippocampus\test_memory_pain_prompt_hook_smoke.py::MemoryPainPromptHookSmokeTests::test_russian_real_history_case_family_captures_stricter_probe_shapes -q`:
  passed.
- `python tools\aippocampus\smoke\smoke_memory_pain_prompt_hook.py --case-family russian-real-history --semantic-gate off --json --strict --require-positive-evidence`:
  passed; 5 cases, 0 unsafe issues, 0 positive misses.
- `python tools\aippocampus\smoke\smoke_memory_pain_prompt_hook.py --case-family russian-real-history --semantic-gate auto --json --strict --require-positive-evidence`:
  passed; 5 cases, 0 unsafe issues, 0 positive misses. Foreground budget
  diagnostics stayed non-fatal and did not create evidence over-escalation.
- `python tools\aippocampus\smoke\smoke_memory_pain_prompt_hook.py --case-family russian-real-history --semantic-gate on --semantic-timeout 20 --max-elapsed-ms 0 --json --strict --require-positive-evidence`:
  passed; 5 cases, 0 unsafe issues, 0 positive misses. Relaxed live semantic
  produced one `semantic_evidence_without_source_bridge` diagnostic on the
  vague prompt, with no source-backed evidence emitted for that prompt.

This does not publish raw private prompts, source refs, snippets, local paths,
session ids, API keys, provider responses, or a broad multilingual quality
claim. It only claims the sanitized Russian probe family is now reproducible
and guarded by deterministic tests plus the hash-only smoke.

## 2026-05-30 Provider And Cross-Agent Continuity Slice

Issues #112-#120 refined the first multi-provider landing slice. Current
evidence supports these narrower claims:

- `aippocampus` exists as a Python CLI facade over existing script entrypoints;
  it preserves child JSON output and exit codes.
- Codex, Claude Code, and validated generic JSONL providers can expose
  provider-normalized visible messages to the clean-source builder.
- Claude Code registration is explicit and filters thinking/tool payloads from
  daily clean source by default.
- MCP results redact local paths by default while retaining source-backed ids
  and source refs.
- `tools/aippocampus/smoke/smoke_cross_agent_continuity.py` provides a
  deterministic synthetic proof of Codex-origin to Claude Code-facing retrieval
  and Claude Code-origin to Codex-facing retrieval through registry clean source
  and the MCP `search_memory` surface.
- `tools/aippocampus/smoke/smoke_claude_code_history.py` probes local Claude
  Code history parsing while reporting only booleans and counts, never
  transcript text or local paths.
- `tools/aippocampus/smoke/smoke_claude_code_mcp_host.py` records whether the
  local Claude Code host can see the configured AIppocampus MCP server, or the
  exact host setup blocker. With `--call-tool`, it also runs an opt-in minimal
  live Claude Code session that must call the `memory_health` MCP tool.
- `.claude/skills/aippocampus/SKILL.md` is the Claude Code project-skill
  adapter. It points Claude Code at existing MCP/CLI surfaces and keeps Claude
  Code transcript onboarding explicit and dry-run-first.

This does not claim unattended ingestion of private host history, Claude Code
hook support, cross-platform standalone binaries, or successful live Claude Code
MCP tool-calls on hosts that still report setup blockers. Standalone binary
work is tracked in `docs/planning/standalone-binary-packaging.md`.

Latest verification for this slice:

- Temporary editable-install console-script smoke: `aippocampus --help` and
  `aippocampus mcp list-tools` passed from a fresh virtual environment. The
  facade exposed the documented operator commands and preserved the MCP tool
  JSON catalog.
- `python tools\aippocampus\smoke\smoke_cross_agent_continuity.py --json`:
  passed. The smoke registered one synthetic Codex source and one synthetic
  Claude Code source, retrieved both through MCP `search_memory`, observed two
  matches in each direction, preserved `codex:session:` and
  `claude-code:session:` source refs, and kept registry/search paths redacted.
- `python tools\aippocampus\smoke\smoke_claude_code_history.py --json`:
  passed against the local Claude Code history store. It found 307 candidate
  sessions and parsed three samples with message/turn counts only; it reported
  no transcript text and no local paths.
- Earlier 2026-05-30 `python tools\aippocampus\smoke\smoke_claude_code_mcp_host.py --json`
  returned `blocked_host_config` because no local `aippocampus` MCP server was
  configured. That blocker is superseded for this Windows host by the
  2026-05-31 refresh below.
- `python tools\aippocampus\smoke\smoke_claude_code_mcp_host.py --json`:
  passed after local Claude Code MCP configuration and returned
  `status=reachable`.
- `python tools\aippocampus\smoke\smoke_claude_code_mcp_host.py --json --call-tool --cwd . --max-budget-usd 0.20 --tool-timeout 180`:
  passed with `status=tool_call_reachable` and a successful
  `mcp__aippocampus__memory_health` call. The smoke verifies Claude Code
  `stream-json` `tool_use` plus the matching `tool_result`, and reports only
  event counts/tool flags instead of raw event bodies.
- `python tools\aippocampus\smoke\smoke_claude_code_mcp_host.py --json --call-tool --cwd . --max-budget-usd 0.20 --tool-timeout 180 --server-command <aippocampus.exe> --server-arg mcp`:
  passed with the same `memory_health` `tool_use` plus matching `tool_result`.
  This proves the Windows standalone binary can serve Claude Code over stdio
  MCP through a temporary strict MCP config; it does not mutate the persistent
  Claude Code MCP settings.
- The same host smoke reported local Claude Code version metadata and verified
  the project skill adapter at `.claude/skills/aippocampus/SKILL.md` without
  reading transcript bodies.
- `python skills\aippocampus\scripts\onboard.py --status --format text --cwd .`:
  passed and rendered human-readable provider states for Codex, Claude Code,
  and generic JSONL. JSON status remains the default for non-TTY agent callers.
- `python skills\aippocampus\scripts\aippocampus_cli.py onboard --provider claude-code --dry-run --format json --cwd .`:
  passed without writing registry data. It previewed 307 Claude Code
  registrations for the AIppocampus workspace and one stale-index repair; raw
  local paths stay out of this public ledger.
- `python skills\aippocampus\scripts\aippocampus_cli.py onboard --status --format json --cwd .`:
  passed with Codex, Claude Code, and generic JSONL all detected as
  `write_enabled`; `auto` still defaults to Codex and lists other providers
  separately.
- Focused unit coverage now checks generic JSONL structured validation errors,
  generic JSONL onboarding dry-run planning, missing-provider status, human
  status rendering, provider-thread-key source-id stability across path moves,
  POSIX host-output path redaction, and JSON-escaped private-root detection in
  the cross-agent smoke.
- `python tools\aippocampus\docs\check_docs_health.py --json`: passed.
- `python tools\aippocampus\run_tests.py --tier fast`: 483 tests passed.
- `python -m mypy`: passed across 96 source files.
- `python -m ruff check skills plugins tests tools benchmarks benchmark_corpus`:
  passed.
- `git diff --check`: passed.

## 2026-05-31 Windows Standalone Binary Smoke

Issue #121 now has a Windows x64 PyInstaller spike and smoke-tested artifact
path. This is a first-platform binary claim only; macOS/Linux artifacts and
release distribution polish remain outside this slice.

Latest verification for this slice:

- `python -m unittest tests.aippocampus.test_package_windows_binary tests.aippocampus.test_cross_agent_continuity_smoke`:
  11 tests passed.
- `python tools\aippocampus\package_windows_binary.py --dry-run --json`:
  passed without claiming artifact smoke or Python-free support.
- Running `tools\aippocampus\package_windows_binary.py --json --output-root <temp>`
  from an isolated temporary virtual environment with PyInstaller 6.20.0 built
  `aippocampus.exe` and passed the artifact smoke matrix:
  `aippocampus --help`, `aippocampus health --help`, public-bundle search,
  `aippocampus mcp list-tools`, `aippocampus onboard --status --format json`,
  empty-sync-dir status with the expected nonzero exit code and JSON payload,
  and `aippocampus hooks status`.
- The packaging path stages only `skills/aippocampus/scripts` as runtime input.
  The first live artifact smoke caught a real regression where the guard treated
  `aippocampus_runtime/registry` as private data and omitted it from the staged
  runtime; the fixed guard now preserves runtime package owners while still
  excluding top-level private/generated roots. The private data guard passed
  with no staged private roots and no PyInstaller command inputs under
  `.aippocampus`, `aippocampus-registry`, `transcripts`, `rollouts`, or a
  repo-local private `registry` directory.

This does not claim signed release artifacts, installer/update UX, macOS/Linux
binaries, or full-history/private-provider ingestion from the binary.

## 2026-05-31 Windows Binary Re-Smoke After Package Refactors

After the #144 runtime package-layout slices through commit `d1b8617`, the
Windows standalone binary path was rebuilt and re-smoked on the same host class
to verify that the new `aippocampus_runtime.*` package owners still freeze and
serve MCP correctly.

Latest verification for this refresh:

- An isolated temporary virtual environment installed PyInstaller 6.20.0 and
  ran `python tools\aippocampus\package_windows_binary.py --json --output-root <temp>`.
  The command built `aippocampus.exe`, set `python_free_support_claimed=true`,
  and passed the artifact smoke matrix: `aippocampus --help`,
  `aippocampus health --help`, public-bundle search,
  `aippocampus mcp list-tools`, `aippocampus onboard --status --format json`,
  empty-sync-dir status with the expected nonzero JSON result, and
  `aippocampus hooks status`.
- The packaging private-data guard passed: no private/generated repository roots
  were staged and no PyInstaller command inputs pointed under `.aippocampus`,
  `aippocampus-registry`, `transcripts`, `rollouts`, or a repo-local private
  `registry` directory.
- `python tools\aippocampus\smoke\smoke_claude_code_mcp_host.py --json --call-tool --cwd . --max-budget-usd 0.20 --tool-timeout 180 --server-command <aippocampus.exe> --server-arg mcp`
  passed against Claude Code 2.1.138 with `status=tool_call_reachable`; the
  smoke observed both `mcp__aippocampus__memory_health` `tool_use` and the
  matching `tool_result` through a temporary strict MCP config.
- Follow-up verification after PR #224 / current `main` commit `a5217d1` repeated
  the same Windows path after the CLI facade `CommandResult` API and
  `warm_ambient` package-owner refactor. An isolated temporary virtual
  environment installed PyInstaller 6.20.0, rebuilt `aippocampus.exe`, passed
  all 7 artifact smoke specs, kept the private-data guard clean, and then
  reached `mcp__aippocampus__memory_health` through Claude Code 2.1.138 with
  both `tool_use` and matching `tool_result` observed through a temporary strict
  MCP config.
- Follow-up verification after PR #245 started from `main` commit `b6d3166`
  after the #144 MCP package-owner migration. The first content-level
  standalone JSON-RPC check caught a frozen-binary-only regression where
  `tools/call:memory_health` tried to launch `sys.executable
  aippocampus_health.py` and returned an MCP error. The MCP server now calls
  the health entrypoint in-process, and the Windows package smoke matrix includes
  a strict `mcp_memory_health_jsonrpc` check for `initialize`, `tools/list`, and
  `tools/call:memory_health` with `tool_is_error=false`.
- After that fix, the persistent local Claude Code MCP config reported
  `status=reachable` for the script-backed `aippocampus` server. An isolated
  temporary virtual environment installed PyInstaller 6.20.0, rebuilt
  `aippocampus.exe`, passed all 8 artifact smoke specs, kept the private-data
  guard clean, and then reached `mcp__aippocampus__memory_health` through Claude
  Code 2.1.138 with both `tool_use` and matching `tool_result` observed through
  a temporary strict MCP config using `aippocampus.exe mcp`.
- Follow-up #144 API cleanup kept the same public CLI and shim boundary while
  exposing `HealthOptions`, `build_health_report()`, and `health_report()` as
  the package-level health API. MCP `memory_health`, active recall, and registry
  registration now call the package API directly instead of dispatching
  `aippocampus_health.py` through `sys.executable`; targeted coupling tests
  guard against reintroducing that package-to-script loop.
- The same #144 pass moved rollout and segmented search implementations under
  `aippocampus_runtime.recall` with compatibility shims preserved. Active
  recall now calls `search_rollout_payload()` / `search_segments_payload()`
  directly, so the recall package no longer re-enters its own flat
  `search_rollout.py` or `search_segments.py` scripts for normal search.
- Follow-up verification on current `main` commit `1f76565`, after PR #255's
  sidecar activation-cue recall changes, repeated the Windows path on the same
  host class. A fresh temporary virtual environment installed PyInstaller
  6.20.0, rebuilt `aippocampus.exe`, set
  `python_free_support_claimed=true`, passed all 8 artifact smoke specs
  including `mcp_memory_health_jsonrpc` with `tool_is_error=false`, and kept the
  private-data guard clean. The rebuilt binary then served Claude Code 2.1.138
  through a temporary strict MCP config as `aippocampus.exe mcp`; the smoke
  observed `mcp__aippocampus__memory_health` `tool_use` plus the matching
  `tool_result`.
- Follow-up verification on current `main` commit `07bf5e6`, after the #263
  ops package slice and #264 vault projection package slice, repeated the same
  Windows path on the same host class. The local Python 3.13 user environment
  installed PyInstaller 6.20.0, rebuilt `aippocampus.exe`, set
  `python_free_support_claimed=true`, passed all 8 artifact smoke specs
  including `mcp_memory_health_jsonrpc` with `tool_is_error=false`, and kept the
  private-data guard clean. The persistent local Claude Code config reported the
  script-backed `aippocampus` MCP server as reachable, and a temporary strict
  MCP config then used the rebuilt binary as `aippocampus.exe mcp`; Claude Code
  2.1.138 observed `mcp__aippocampus__memory_health` `tool_use` plus the
  matching `tool_result`. This refresh does not mutate the persistent Claude
  Code MCP settings.

This refresh does not close #104. The post-migration encrypted provider sync
smoke still needs a maintainer-provided real object-store provider target and
credentials before it can verify encrypted push/status/repair/pull behavior.

## 2026-05-31 Provider Entrypoint And Storage Boundary Refresh

Issues #122 and #123 tightened the remaining Codex-default ambiguity without
pretending Codex is no longer a supported provider.

Latest verification for this slice:

- `docs/architecture/provider-entrypoint-inventory.md` classifies remaining
  `locate_rollout(...)`, `iter_rollouts(...)`, `codex_home()`, and
  `provider or codex_provider(...)` call sites as provider-aware,
  clean-source/registry, Codex host integration, or Codex-only raw audit/debug
  surfaces.
- `aippocampus_registry_resolution()` now resolves generated registry storage
  in this order: `AIPPOCAMPUS_REGISTRY_DIR`, legacy
  `THREAD_MEMORY_REGISTRY_DIR`, `AIPPOCAMPUS_HOME/registry`, then legacy
  `CODEX_HOME/aippocampus-registry`. Hook logs, lifecycle state, and the
  subconscious scheduler use this AIppocampus registry root while Codex hook
  installers still use Codex hook config.
- `aippocampus onboard --status --format json --cwd .` reports provider
  readiness plus active registry storage source.
- `aippocampus_health.py --json --cwd .` reports default and active registry
  storage source alongside health details.
- `python -m unittest tests.aippocampus.test_aippocampuslib tests.aippocampus.test_onboard_codex tests.aippocampus.test_architecture_boundaries tests.aippocampus.test_aippocampus_health tests.aippocampus.test_global_storage_defaults`:
  46 tests passed.

This does not make Codex hook installers provider-neutral, migrate existing
registries, or remove Codex raw audit tools. Those surfaces are now explicitly
labeled instead of implied as general provider APIs.

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
`docs/evidence/readiness/stage-0-5-readiness.md` remains the claim-boundary summary.

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
  A legacy Mac system-Python run exposed a `Path.write_text(newline=...)`
  path-repair regression; `sync_bundle.save_json` now uses
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
claim boundary remains `docs/evidence/readiness/stage-0-5-readiness.md`.

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
  passed in observe-only mode. This confirmed the dynamic semantic sidecar
  slice materialized as of the 2026-05-30 run without making a fresh
  external-model write.
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
  passed. It reviewed 24 selected semantic sidecar label cases from the
  2026-05-30 slice through the DeepSeek-compatible live source-review path,
  passed 24/24, reached
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
  across that strict semantic sidecar slice.

Closeout interpretation for #55:

- Reviewed families now include selected source-review evidence for
  `idea_seed`, `life_context`, `open_question`, `personal_reflection`,
  `preference`, `reading_notes`, and `technical_work`; selected retrieval
  evidence also covers `relationship_continuity`.
- Accepted labels in that strict sidecar slice are only the labels that survived
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

Stage 2 #308 report-hardening update:

- `python .\tools\aippocampus\smoke\smoke_semantic_scope_source_review.py --max-cases 96 --min-cases 64 --json`:
  passed in observe-only mode and now emits `per_label_floors` plus
  `review_buckets`. The selected pool still covers 96 public-safe hashed cases
  across `idea_seed`, `life_context`, `open_question`, `personal_reflection`,
  `preference`, `reading_notes`, and `technical_work`, while
  `relationship_continuity` has no materialized strict review case in that
  observed slice.
  Because this mode does not call a live reviewer, all 96 selected cases remain
  `unreviewed`, and `cannot_claim` still includes fresh live model review and
  selected source-review pass.
- `python .\skills\aippocampus\scripts\semantic_scope_suppressed_recovery.py --max-cases 12 --json`:
  passed in observe-only mode and now emits `recovery_buckets` plus
  `per_label_recovery`. The observed suppressed pool for that run contains 8 cases / 11
  candidate labels across `relationship_continuity`, `reading_notes`,
  `idea_seed`, `preference`, `life_context`, `technical_work`, and
  `open_question`; all remain `unreviewed` in observe-only output, and
  `strict_gate_relaxed=false`.
- Current claim governance now distinguishes the old 5-row strict sidecar
  survival evidence, the 24-case green live source-review slice, and the
  broader 96-case diagnostic run with one live model partial failure. The
  broader run is not a green gate unless rerun cleanly; the compact current
  snapshot lives in `docs/evidence/current-claims.md`.
- Follow-up #320 tracks systematic evidence improvement for high-risk
  still-suppressed label families. That follow-up must improve source-backed
  semantic evidence or classify labels as unsafe to restore; it must not use
  lexical expansion or lower materializer thresholds as a shortcut.

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

## 2026-06-01 - Continuous-memory cost and harm ledger

The #410 slice adds the public-synthetic `cost_harm_ledger` to
`benchmarks/aippocampus/benchmark_continuous_memory_arms.py`, extending the
#408 attribution arms for #378.

- The report now separates foreground-only cost from amortized memory cost,
  counts modeled background prep instead of hiding it, and keeps
  `fresh_context_spec_loop` as a fair comparison baseline rather than treating
  the `no_memory` diagnostic arm as fresh-context/spec-loop.
- The harm ledger weights stale-memory false positives by severity,
  downstream turns, wrong constraints, rejected routes, current-project
  contamination, risky action before source reopen, privacy severity, and
  rollback/rework cost.
- The verified public-synthetic result reports
  `claim_level=public_synthetic_cost_harm_contract`,
  `amortized_cost_per_successful_slice=7.875` for
  `true_aippocampus_memory`, `3.07` for `fresh_context_spec_loop`,
  `harm_weighted_false_positive_cost=149.0` for `stale_wrong_memory`, and
  `highest_net_value_fair_strategy=fresh_context_spec_loop`.
- Verification commands passed:
  `python -m unittest tests.aippocampus.test_benchmark_continuous_memory_arms -v`,
  `python benchmarks/aippocampus/benchmark_continuous_memory_arms.py --json`,
  `python tools/aippocampus/docs/check_docs_health.py --json`,
  `python -m compileall -q benchmarks/aippocampus/benchmark_continuous_memory_arms.py tests/aippocampus/test_benchmark_continuous_memory_arms.py`,
  `python tools/aippocampus/run_tests.py --tier benchmark`,
  `python -m ruff check skills plugins tests tools benchmarks benchmark_corpus`,
  `git diff --check`, and `python tools/aippocampus/run_tests.py --tier fast`.
- This does not claim full #378 continuous-memory superiority, exact dollar
  accounting, live host-native cost telemetry, live compaction behavior,
  private real-history generality, answer-generation quality, or competitor
  superiority.

## 2026-06-01 - Continuous-memory pre-registration

The #407 slice adds a `preregistration` block to
`benchmarks/aippocampus/benchmark_continuous_memory_arms.py`, extending the
#378/#408/#410 report with the pre-registered endpoint and decision rule that
must be used before public-quality continuous-memory superiority claims.

- The primary endpoint is
  `source_grounded_task_success_under_equalized_cost`, chosen because it joins
  task success, source support, equalized cost, and severe false positives
  rather than allowing post-hoc metric selection.
- The report records public-quality minimums of at least 3 scenario families
  and at least 5 paired repeats per scenario x arm, with same task/seed pairs
  across arms where feasible.
- The confidence rule requires a paired `lower_bound` advantage for
  `true_aippocampus_memory` over `fresh_context_spec_loop` after hard gates
  pass; secondary metrics remain exploratory unless named in the primary
  decision rule before the run.
- The current contract-smoke preview reports
  `primary_endpoint_winner=fresh_context_spec_loop`,
  `continuous_memory_advantage_claim_allowed=false`, and decision label
  `no demonstrated memory advantage`.
- Verification commands passed:
  `python -m unittest tests.aippocampus.test_benchmark_continuous_memory_arms -v`,
  `python benchmarks/aippocampus/benchmark_continuous_memory_arms.py --json`,
  `python tools/aippocampus/docs/check_docs_health.py --json`,
  `python -m ruff check benchmarks/aippocampus/benchmark_continuous_memory_arms.py tests/aippocampus/test_benchmark_continuous_memory_arms.py`,
  `git diff --check`,
  `python -m compileall -q benchmarks/aippocampus/benchmark_continuous_memory_arms.py tests/aippocampus/test_benchmark_continuous_memory_arms.py`,
  `python tools/aippocampus/run_tests.py --tier benchmark`,
  `python -m ruff check skills plugins tests tools benchmarks benchmark_corpus`,
  and `python tools/aippocampus/run_tests.py --tier fast`.
- This does not claim public-quality #378 superiority, adequate statistical
  power, holdout scenario coverage, host-native compaction behavior, or private
  real-history generality.

## 2026-06-02 - Continuous-memory scenario provenance and holdout controls

The #409 slice extends
`benchmarks/aippocampus/benchmark_continuous_memory_arms.py` with
scenario-level provenance, holdout, and negative-control reporting for #378.

- The report now uses schema version 2 and keeps all scenario metadata
  sanitized. Rows expose `scenario_provenance`, `scenario_generated_by`,
  `scenario_source_material`, `aippocampus_internals_visible`, and
  `prompt_threshold_tuning_role`, but still hash case ids, source refs, source
  windows, and memory packet text.
- The current contract-smoke preview has 6 cases and 30 rows. Provenance slices
  are reported separately: 4 `author_written_synthetic` cases and 2
  `public_log_or_vcs_derived` + `holdout_blind` cases. The external/holdout
  share is `0.3333`, above the registered `0.30` share gate, while
  `external_written_synthetic` and `private_real_history_aggregate` remain
  `0` for this public-safe slice.
- Holdout cases use `holdout_excluded`; the report records
  `holdout_used_for_prompt_or_threshold_tuning_count=0`.
- The runner also exposes
  `--scenario-selection-role prompt_threshold_tuning`; that selection returns
  4 tuning-visible cases, excludes 2 holdout cases from rows/metrics, and keeps
  `holdout_used_for_prompt_or_threshold_tuning_count=0`.
- Public scenario metadata is guarded before JSON emission: report-visible
  generator/source-material labels reject local path separators, URI/drive
  separators, private raw-log labels, and secret-like strings.
- Scenario-level negative controls now distinguish unnecessary memory
  intervention from useful source-backed memory. The current report has 2
  negative-control cases; `true_aippocampus_memory` records 2 memory
  interventions but 0 harmful unnecessary interventions, while
  `stale_wrong_memory` triggers 2 harmful unnecessary interventions.
- The #409 controls do not turn the current contract smoke into public-quality
  superiority evidence. The report still records
  `primary_endpoint_winner=fresh_context_spec_loop`,
  `continuous_memory_advantage_claim_allowed=false`, and the cannot-claim
  boundary for public-quality #378 superiority from only
  `author_written_synthetic` or tuning-visible diagnostic scenarios.
- Verification commands passed during this slice:
  `python -m unittest tests.aippocampus.test_benchmark_continuous_memory_arms -v`,
  `python benchmarks/aippocampus/benchmark_continuous_memory_arms.py --json`,
  `python benchmarks/aippocampus/benchmark_continuous_memory_arms.py --scenario-selection-role prompt_threshold_tuning --json`,
  `python tools/aippocampus/docs/check_docs_health.py --json`,
  `python -m ruff check benchmarks/aippocampus/benchmark_continuous_memory_arms.py tests/aippocampus/test_benchmark_continuous_memory_arms.py`,
  `python -m compileall -q benchmarks/aippocampus/benchmark_continuous_memory_arms.py tests/aippocampus/test_benchmark_continuous_memory_arms.py`,
  `python tools/aippocampus/run_tests.py --tier benchmark`,
  `python -m ruff check skills plugins tests tools benchmarks benchmark_corpus`,
  `git diff --check`, and `python tools/aippocampus/run_tests.py --tier fast`.
- This does not claim live host-native compaction behavior, external-written
  synthetic reviewer coverage, private real-history generality, competitor
  superiority, or public-quality #378 advantage.

## 2026-06-02 - Continuous-memory host-native baseline contract

The #406 slice extends
`benchmarks/aippocampus/benchmark_continuous_memory_arms.py` with a
host-native continuous baseline for #378.

- The report now distinguishes `bare_continuous_no_memory` from
  `host_native_continuous_no_aippocampus`. The former is the old no-context
  diagnostic arm; the latter is a Codex-style same-thread compaction/summary
  contract with AIppocampus hook recall, MCP recall tools, active recall, and
  registry memory injection disabled.
- The current contract-smoke preview still uses 6 public-safe cases, now across
  6 arms, and bumps the report contract to `schema_version=3`. It reports
  `host_native_compaction_lift_over_bare_continuous` and includes
  `host_native_continuous_no_aippocampus` in `comparison_baselines` with
  `documented_host_family=codex`,
  `host_version_or_build=record_at_live_run_when_available`,
  `compaction_settings=host_default_same_thread_summary_or_compaction_contract`,
  `aippocampus_memory_surfaces_disabled=true`, and
  `host_native_compaction_enabled=true`.
- This is a deterministic baseline contract, not live host telemetry. The
  report keeps `uses_live_host_native_compaction=false` and
  `live_measurement_status=not_measured_in_this_diagnostic_runner`.
- Verification commands passed during this slice:
  `python -m unittest tests.aippocampus.test_benchmark_continuous_memory_arms -v`,
  `python benchmarks/aippocampus/benchmark_continuous_memory_arms.py --json`,
  `python tools/aippocampus/docs/check_docs_health.py --json`,
  `python -m ruff check benchmarks/aippocampus/benchmark_continuous_memory_arms.py tests/aippocampus/test_benchmark_continuous_memory_arms.py`,
  `python -m compileall -q benchmarks/aippocampus/benchmark_continuous_memory_arms.py tests/aippocampus/test_benchmark_continuous_memory_arms.py`,
  `git diff --check`, `python tools/aippocampus/run_tests.py --tier fast`, and
  `python tools/aippocampus/run_tests.py --tier benchmark`.
- This does not claim
  `AIppocampus_has_beaten_realistic_host_native_continuous_workflows`, live
  host-native compaction behavior, cross-host baseline coverage, private
  real-history generality, or public-quality #378 advantage.

## 2026-06-03 - Continuous-memory cost/harm sensitivity sweep

The #378 runner now extends `cost_harm_ledger` with
`sensitivity_analysis`, bumping
`benchmarks/aippocampus/benchmark_continuous_memory_arms.py` to
`schema_version=4`.

- The sweep reports `basis=public_synthetic_weight_sweep` and
  `claim_level=diagnostic_weight_sensitivity`.
- It reruns the fair-winner calculation across `base_formula`, `harm_heavy`,
  `memory_cost_light`, and `fresh_context_rebuild_expensive` scenarios, while
  still excluding `oracle_memory` from fair winners.
- The verified public-synthetic result reports
  `winner_distribution={"fresh_context_spec_loop": 3,
  "host_native_continuous_no_aippocampus": 1}`,
  `continuous_memory_advantage_stable_across_sweep=false`, and
  `true_memory_margin_vs_best_baseline_units={"min": -27.7675,
  "max": -9.6738}`.
- This is a guard against treating one heuristic formula as headline evidence.
  It does not calibrate weights against user studies, production incidents, or
  live host telemetry.
- Verification commands passed during this slice:
  `python -m unittest tests.aippocampus.test_benchmark_continuous_memory_arms`,
  `python benchmarks/aippocampus/benchmark_continuous_memory_arms.py --json`,
  `python tools/aippocampus/docs/check_docs_health.py --json`,
  `python -m ruff check benchmarks/aippocampus/benchmark_continuous_memory_arms.py tests/aippocampus/test_benchmark_continuous_memory_arms.py`,
  `git diff --check`, `python tools/aippocampus/run_tests.py --tier fast`, and
  `python tools/aippocampus/run_tests.py --tier benchmark`.
- This does not claim cost-weight robust continuous-memory advantage,
  public-quality #378 superiority, live host-native cost telemetry, private
  real-history generality, or competitor superiority.

## 2026-06-03 - First-recall onboarding receipt smoke

The #470 slice moves the first-user path toward a 5-minute source-backed recall
receipt instead of a maintainer-check-first flow.

- A fresh temporary virtual environment installed the current checkout with
  `python -m pip install -e .`.
- The installed `aippocampus --help` command passed.
- `aippocampus search lighthouse --clean-source-dir examples/public-memory-bundle/clean-source`
  returned human-readable `Source-backed snippets` with `Source` metadata and a
  next-step boundary.
- `aippocampus search zzznonexistentcue --clean-source-dir examples/public-memory-bundle/clean-source`
  returned exit code 1 and the human-readable
  `Possible routes, not yet evidence` no-result guidance instead of a spurious
  source-backed snippet.
- `aippocampus onboard --status --format text` returned the `First recall`
  exact-phrase, project-cue, and time-cue next steps.
- A read-only `uvx aippocampus --help` public package probe passed separately.
  That probe verifies the public package command is reachable, not that the
  current checkout's new human-output wording is already in the published
  package.
- This does not claim interactive Desktop UI readiness, hook installation
  readiness, MCP Registry marketplace UI readiness, or full all-client support;
  those remain under #307 and the Stage 0-5 readiness boundary.

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
  labels still over-inferred beyond source text, so that 2026-05-29
  strict-survival rematerialization intentionally contained only 5 rows across
  2 real clean-source threads, and the refreshed timeline observed 5 semantic
  latest turns. Later aggregate sidecar coverage and supersession notes live in
  `docs/evidence/current-claims.md`. The smoke output remained aggregate-only and explicitly preserved
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
  review bar. The 2026-05-29 strict-survival materialization then passed a
  5-case live review slice with 5 of 5 labels supported by the matching
  clean-source message (`pass_rate=1.0`) and no model call failures. This is not human
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
  executed against 5 strict-survival sidecar labels from that run with tool observations and
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
- If a future claim needs Codex-only provider-scoped status output, implement
  and release that status shape explicitly. The 2026-06-05 PyPI `0.1.1`
  re-smoke passed the released package/MCP path but still returned the provider
  matrix rather than a Codex-only status object.
- Run an interactive Desktop UI marketplace flow or external install review if
  claiming support across every Codex client surface. Current real-host
  evidence is headless Codex app-server, not manual UI coverage.
- Broaden Stage 3 release evidence beyond the current Windows/MacBook physical
  smoke and one managed R2 provider run if claiming broader provider/client
  coverage. Local HTTP object-storage remains labeled as simulation; the R2 run
  is real managed-provider evidence, not a provider matrix.
- Continue Stage 2 life-wide memory evidence beyond the selected top-5 recall,
  dated strict source-review slices, and first Pro-agent recovery smoke:
  broaden suppressed-label recovery samples, use Pro-agent source-review
  failures as training/evidence-selection feedback, and avoid treating sidecar
  labels as source truth.
