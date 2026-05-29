# Demo Scenarios

These scenarios use public-safe examples. They are meant to show product shape
without exposing private rollouts or personal registry data.

## Scenario 1: Exact Quote Recall

Use the public example bundle:

```sh
python ./skills/aippocampus/scripts/search_clean_source.py "without pretending it has innate memory" --cwd . --clean-source-dir ./examples/public-memory-bundle/clean-source --json
```

Expected result: matches come from original visible clean-source text, not a
summary-only memory.

Cannot claim: that summaries or model-generated findings are the source.

## Scenario 2: Fuzzy Life-Topic Recall

```sh
python ./skills/aippocampus/scripts/build_semantic_scope_labels.py --jobs-output ./examples/public-memory-bundle/registry/subconscious_jobs.jsonl --clean-source-dir ./examples/public-memory-bundle/clean-source --no-write --json
python ./skills/aippocampus/scripts/search_clean_source.py "casual sparks" --cwd . --clean-source-dir ./examples/public-memory-bundle/clean-source --json
python ./skills/aippocampus/scripts/search_clean_source.py "casual sparks" --cwd . --clean-source-dir ./examples/public-memory-bundle/clean-source --scope-label idea_seed --json
python ./skills/aippocampus/scripts/search_clean_source.py "lighthouse metaphor pivot" --cwd . --clean-source-dir ./examples/public-memory-bundle/clean-source --scope-label personal_reflection --scope-label idea_seed --json
```

Expected result: the public example surfaces a non-project idea seed. This
demonstrates life-wide memory shape, scope-label filtering, and a synthetic
casual-important metaphor/pivot turn without exposing private biography. The
metaphor/pivot label is backed by a synthetic `semantic_scope_labels`
subconscious finding that can be materialized into
`semantic-scope-labels.jsonl`, modeling a DeepSeek/subconscious sidecar rather
than hard-coded lexical expansion.

Cannot claim: that all personal life-wide labels are complete in the current
runtime.

## Scenario 3: Real-History Semantic Scope Sidecar Smoke

Observe existing dynamic sidecar coverage without calling an external model:

```sh
python ./tools/aippocampus/smoke/smoke_semantic_scope_real_history.py --json
```

Run a bounded live DeepSeek-compatible batch only when external-model use is
intentional:

```sh
python ./tools/aippocampus/smoke/smoke_semantic_scope_real_history.py --live --write-sidecars --require-labels --max-turns 24 --max-steps 2 --min-tool-steps 0 --concurrency 4 --samples-per-job 2 --json
```

Evaluate the currently selected full life-wide candidate slice in batches:

```sh
python ./tools/aippocampus/smoke/smoke_semantic_scope_real_history.py --live --write-sidecars --require-labels --full-candidate-coverage --candidate-batch-size 24 --samples-per-job 1 --concurrency 6 --max-steps 1 --min-tool-steps 0 --json
```

Check selected fuzzy life-wide source-evidence prompts against clean-source
search, without emitting raw private wording:

```sh
python ./tools/aippocampus/smoke/smoke_source_evidence_recall_eval.py --max-cases 24 --min-cases 12 --top-k 5 --min-hit-rate 0.85 --json
```

Review selected semantic sidecar labels against their clean-source messages:

```sh
python ./tools/aippocampus/smoke/smoke_semantic_scope_source_review.py --live --max-cases 96 --min-cases 64 --min-pass-rate 0.75 --min-label-pass-rate 0.65 --concurrency 2 --timeout 200 --max-attempts 3 --json
```

Expected result: output is aggregate-only. Live mode writes source-backed
semantic scope-label staging findings, materializes
`semantic-scope-labels.jsonl`, and refreshes the timeline. The recall eval
uses dynamic source-derived cue terms and hashed case ids; it is not a
hard-coded fuzzy word-list expansion. The source-review smoke sends selected
clean-source snippets to a DeepSeek-compatible reviewer only in explicit live
mode, retries transient reviewer failures, reports per-label pass rates, and
emits hashed case ids plus counts. Source-review-sensitive labels are filtered
unless the model supplied strong per-label evidence.

Cannot claim: that semantic labels are source truth, or that all historical
threads have been semantically labeled or perfectly ranked.

## Scenario 4: Project Timeline

Build a source-backed project and life-wide timeline from the public example
registry:

```sh
python ./skills/aippocampus/scripts/build_project_timeline.py --registry ./examples/public-memory-bundle/registry/threads.json --output ./.tmp/public-project-timeline.json --json
```

Expected result: the output contains a `life_wide` section with labeled turns
and source refs back to clean-source message ids.

Cannot claim: that timeline labels are stronger evidence than the underlying
clean-source turns.

## Scenario 5: Project Continuity Recall

```sh
python ./skills/aippocampus/scripts/aippocampus_mcp_server.py --list-tools
```

Expected result: `search_memory` and `get_turn_context` are available for
recovering project context from clean source.

Cannot claim: that every project thread has already been onboarded.

## Scenario 6: Multilingual Recall Smoke

```sh
python ./tools/aippocampus/smoke/simulate_multilingual_prompt_hook.py --cwd .
```

Expected result: multilingual hook smoke cases pass or report concrete failing
cases.

Cannot claim: that optional external semantic gates are enabled.

## Scenario 7: Inspect MCP Tools

```sh
python ./skills/aippocampus/scripts/aippocampus_mcp_server.py --list-tools
```

Expected result: the tool list includes `search_memory`, `latest_reply`,
`get_turn_context`, `list_threads`, `register_thread`, `sync_status`, and
`memory_health`.

## Scenario 8: Build A Plugin Package

```sh
python ./plugins/aippocampus/build_plugin_package.py --repo-root . --json
```

Expected result: `dist/aippocampus-plugin/` contains `.codex-plugin`,
`.mcp.json`, and `skills/aippocampus/`. Hooks are not auto-enabled.

Cannot claim: that the plugin has been installed through every Codex client.

## Scenario 8b: Real Codex Plugin And MCP Host Smoke

```sh
python ./plugins/aippocampus/smoke_real_codex_host.py --repo-root . --json
```

Expected result: a run-id-scoped local marketplace is added through the real
Codex app-server, the plugin is installed with Codex `plugin/install`, the
Codex MCP host lists the `aippocampus` server, `mcpServer/tool/call` runs
`sync_status` through a real thread, and cleanup removes the plugin,
marketplace, build output, temporary marketplace root, and plugin-cache entry.

Cannot claim: that a human clicked through the Desktop marketplace UI or that a
third-party machine installed the public package.

## Scenario 9: Local Sync Folder

Use a throwaway sync folder:

```sh
python ./skills/aippocampus/scripts/sync_bundle.py push --registry-dir ./examples/public-memory-bundle/registry --sync-dir ./.tmp/demo-sync --json
python ./skills/aippocampus/scripts/sync_bundle.py repair --sync-dir ./.tmp/demo-sync --json
python ./skills/aippocampus/scripts/sync_bundle.py pull --sync-dir ./.tmp/demo-sync --registry-dir ./.tmp/demo-target-registry --json
```

Expected result: the sync manifest is valid and `raw_rollout_included` remains
false. The synced registry uses portable bundle-relative locators, and pull
repairs generated-artifact paths to the target registry.

Cannot claim: that a real second machine, cross-OS path behavior, cloud,
object-storage backend, or cloud-safe encrypted sync path has been exercised.
This is a plaintext throwaway demo for local protocol validation.

## Scenario 9b: Single-Machine Cross-Device Sync Smoke

```sh
python ./tools/aippocampus/smoke/smoke_cross_device_sync.py --repo-root . --json
```

Expected result: the smoke models device A and device B registries, strips or
rewrites source-device locators, repairs generated artifact paths to the target
registry, preserves conflicts in both directions, keeps raw rollouts excluded
by default, and transfers raw rollout only in the explicit opt-in branch.

Cannot claim: that a physical second machine, real alternate OS runtime, cloud
folder client, object-storage backend, or cloud-safe encrypted sync path has
been exercised.

## Scenario 9c: Docker/WSL Alternate-Runtime Sync Smoke

```sh
python ./tools/aippocampus/smoke/smoke_alternate_runtime_sync.py --repo-root . --runtime all --json
```

Expected result: the host creates the sync bundle, then the alternate runtime
runs `status`, `repair`, and `pull`. The pulled registry should use
runtime-local generated-artifact locators, keep workspace unresolved, and keep
raw rollout excluded by default.

Cannot claim: that a physical second machine, real cloud client, or
object-storage backend has been exercised.

## Scenario 9d: HTTP Object-Storage Sync Smoke

```sh
python ./tools/aippocampus/smoke/smoke_object_storage_sync.py --repo-root . --json
```

Expected result: the smoke starts a local HTTP object store, pushes the sync
bundle through real object `PUT` calls, verifies status/repair through object
`GET` calls, and pulls into a target registry with generated-artifact paths
repaired. Raw rollout stays excluded by default.

Cannot claim: that a physical second machine or managed cloud object-storage
provider has been exercised.

## Scenario 10: Over-Personalization Avoidance

Ask an unrelated technical question in a workspace with AIppocampus installed.

Expected result: ambient recall may stay silent when the prompt has no strong
memory scent. Strong claims require source hits.

Cannot claim: that every prompt should include personal history.

## Scenario 11: Ambient Recall Boundary

Run hook status before installing anything:

```sh
python "${CODEX_HOME}/skills/aippocampus/scripts/install_aippocampus_prompt_hook.py" status --json
```

Expected result: status is observable without enabling the hook. Installing a
prompt hook is an explicit user action because it can surface private clean
source in future prompts.

Cannot claim: that hooks are enabled by plugin install alone.

## Scenario 12: Raw Audit Opt-In

Use raw search only when clean source is insufficient:

```sh
python "${CODEX_HOME}/skills/aippocampus/scripts/search_rollout.py" "keyword" --cwd .
```

Expected result: raw audit remains an explicit operator action.

Cannot claim: that raw rollout mining is the daily default.
