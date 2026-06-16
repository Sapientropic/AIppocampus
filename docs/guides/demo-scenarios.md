# Demo Scenarios

These scenarios use public-safe examples. They are meant to show product shape
without exposing private rollouts or personal registry data.

Current claim boundaries live in `docs/evidence/current-claims.md`; these demos
are command and product-shape examples, not a separate evidence ledger. The
profile boundary lives in
[public-core-boundary.md](public-core-boundary.md#product-profile-boundary).

## Scenario 1: Exact Quote Recall

Use the public example bundle:

```sh
aippocampus search "without pretending it has innate memory" --clean-source-dir ./examples/public-memory-bundle/clean-source --json
```

Expected result: matches come from original visible clean-source text, not a
summary-only memory. The first success shape is:

```text
old cue -> source-backed snippet -> reopen/source boundary -> next action
```

Boundary: summaries or model-generated findings are not the source.

## Scenario 2: Fuzzy Life-Topic Recall

Use the stable search facade first:

```sh
aippocampus search "casual sparks" --cwd . --clean-source-dir ./examples/public-memory-bundle/clean-source --json
aippocampus search "lighthouse metaphor pivot" --cwd . --clean-source-dir ./examples/public-memory-bundle/clean-source --scope-label personal_reflection --scope-label idea_seed --json
```

Maintainer diagnostic materialization, when you need to inspect the synthetic
semantic sidecar itself:

```sh
PYTHONPATH=./skills/aippocampus/scripts python -m aippocampus_runtime.source.semantic_scope_builder --jobs-output ./examples/public-memory-bundle/registry/subconscious_jobs.jsonl --clean-source-dir ./examples/public-memory-bundle/clean-source --no-write --json
```

Expected result: the public example surfaces a non-project idea seed. This
demonstrates life-wide memory shape, scope-label filtering, and a synthetic
casual-important metaphor/pivot turn without exposing private biography. The
metaphor/pivot label is backed by a synthetic `semantic_scope_labels`
subconscious finding that can be materialized into
`semantic-scope-labels.jsonl`, modeling a DeepSeek/subconscious sidecar rather
than hard-coded lexical expansion.

Boundary: semantic sidecar labels are navigational; current governed-demo
claims live in `docs/evidence/current-claims.md`.

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

Boundary: semantic labels are not source truth; live source-review mode sends
selected clean-source snippets to the configured reviewer.

## Scenario 3b: Slow Real Codex Long-Session Continuity Smoke

Run this only when a real Codex app-server host is available and slow/live
evidence is intentional:

```sh
python ./tools/aippocampus/smoke/smoke_codex_long_session_continuity.py --turn-count 50 --json
```

For long manual runs, add `--progress-jsonl .tmp/live-continuity-progress.jsonl`
to get append-only progress rows while the host is working. The progress file is
a local/private diagnostic artifact: rows contain phase names, hashes, counts,
timings, and booleans only, never raw prompts, assistant output, rollout paths,
local paths, credentials, or raw thread ids.

Expected result: the smoke reports `status=passed` only after real Codex turns,
a real `thread/compact/start` boundary, completed `preCompact` / `postCompact`
host hooks, post-compaction recall of the corrected synthetic state, and a
clean-source rebuild from the real rollout. If the host is unavailable, it
reports `status=skipped_host_unavailable`; if the host is available but
compaction or correction survival fails, it reports `status=failed`.

Boundary: this slow smoke requires a real Codex app-server host and is not part
of the fast deterministic tier.

## Scenario 4: Project Timeline

Build a source-backed project and life-wide timeline from the public example
registry:

```sh
PYTHONPATH=./skills/aippocampus/scripts python -m aippocampus_runtime.navigation.project_timeline --registry ./examples/public-memory-bundle/registry/threads.json --output ./.tmp/public-project-timeline.json --json
```

Expected result: the output contains a `life_wide` section with labeled turns
and source refs back to clean-source message ids. Timeline labels stay below
the underlying clean-source turns.

## Scenario 5: Project Continuity Recall

```sh
aippocampus mcp status
aippocampus mcp list-tools --json
```

Expected result: `search_memory`, `recall_context`, `recall_deepen`, and
`get_turn_context` are available for recovering project context from clean
source. A project thread must be onboarded before those tools can recover it.

## Scenario 6: Multilingual Recall Smoke

```sh
python ./tools/aippocampus/smoke/simulate_multilingual_prompt_hook.py --cwd .
python ./tools/aippocampus/smoke/simulate_multilingual_prompt_hook.py --cwd . --semantic-gate off --seed-semantic-cues --json
```

Expected result: multilingual hook smoke cases pass or report concrete failing
cases with semantic availability, budget, and error-bucket diagnostics. Cached
or reviewed semantic cues should be able to warm repeated multilingual recall;
the seeded command is the public-safe deterministic proof that this works
without forcing a live semantic call in the foreground hook. Seeded rows also
report `exact_cache_hit`, `semantic_cue_hit`, and `cold_model_call` separately
so operators can tell an exact prompt cache hit from reusable cue coverage.

The optional external semantic gate may be disabled; the seeded command shows
the deterministic warmed-cue path.

## Scenario 6b: Memory Pain Boundary Fixtures

```sh
python ./benchmarks/aippocampus/benchmark_memory_decision_gate.py --json --output ./.tmp/memory-pain-gate-report.json
python ./benchmarks/aippocampus/benchmark_payload_fidelity.py --json --output ./.tmp/memory-pain-payload-report.json
```

Expected result: the report includes a `memory_pain_fixtures` summary with
public-safe negative cases and no unsupported-evidence false positives for the
memory-pain fixture family. The public report is
[`memory-pain-fixture-report.md`](../evidence/benchmarks/reports/field-journey/memory-pain-fixture-report.md).

Boundary: these commands exercise public memory-pain fixtures. Use the separate
Track D synthetic runner when demonstrating compaction-continuity measurement.

## Scenario 6c: Private Memory Pain Prompt Smoke

```sh
python ./tools/aippocampus/smoke/smoke_memory_pain_prompt_hook.py --cwd . --semantic-gate off --json --strict
python ./tools/aippocampus/smoke/smoke_memory_pain_prompt_hook.py --cwd . --semantic-gate on --semantic-timeout 20 --max-elapsed-ms 4300 --json --strict
```

Use `--case-family russian` to run the small sanitized Russian boundary family.

Expected result: output is `aggregate_hash_only`, with no raw prompts, snippets,
thread ids, source refs, or candidate titles. The smoke reports negative
over-escalations, vague evidence upgrades, positive misses, semantic timeout
buckets, and semantic-evidence bridge diagnostics separately.

Boundary: a relaxed live run with `--max-elapsed-ms 0` is useful for diagnosis,
but it is not part of the fast deterministic path.

## Scenario 6d: Fresh-Thread Recall Arms

```sh
PYTHONPATH=./skills/aippocampus/scripts python -m aippocampus_runtime.recall.fresh_thread_demo --flow website_cue --arm active_recall
python ./benchmarks/aippocampus/benchmark_fresh_thread_recall_demo.py --json --output ./.tmp/fresh-thread-recall-demo.json
```

Expected result: the runtime demo prints turn-by-turn scent, action,
activation, lock-handling, and source-reopen progression for public-safe
synthetic flows. The benchmark wrapper reports 5 positive flows, 5 negative
controls, turn-depth distribution, multi-turn coverage, wrong-recall
correction coverage, threshold-edge coverage, and three arms: `no_memory`,
`hook_only`, and `active_recall`. Privacy, unsupported-evidence,
negative-control, multi-turn, correction, and threshold gates should pass.

Boundary: the fixtures model upstream semantic/subconscious output; the runner
must not be read as a prompt-keyword classifier. Use
`docs/evidence/current-claims.md` for quality claims.

## Scenario 7: Inspect MCP Tools

```sh
aippocampus mcp list-tools --json
```

Expected result: the tool list includes `search_memory`, `recall_context`,
`recall_deepen`, `latest_reply`, `get_turn_context`, `list_threads`,
`register_thread`, `sync_status`, and `memory_health`.

## Scenario 8: Build A Plugin Package

```sh
python ./plugins/aippocampus/build_plugin_package.py --repo-root . --json
```

Expected result: `dist/aippocampus-plugin/` contains `.codex-plugin`,
`.mcp.json`, and `skills/aippocampus/`. Hooks are not auto-enabled.

Boundary: package build verifies bundle shape, not every Codex client surface.

## Scenario 8b: Real Codex Plugin And MCP Host Smoke

```sh
python ./plugins/aippocampus/smoke_real_codex_host.py --repo-root . --json
```

Expected result: a run-id-scoped local marketplace is added through the real
Codex app-server, the plugin is installed with Codex `plugin/install`, the
Codex MCP host lists the `aippocampus` server, `mcpServer/tool/call` runs
`sync_status` through a real thread, and cleanup removes the plugin,
marketplace, build output, temporary marketplace root, and plugin-cache entry.

Boundary: this covers the host API path, not human Desktop marketplace
click-through or third-party machine install.

## Scenario 9: Local Sync Folder

Use a throwaway sync folder:

```sh
PYTHONPATH=./skills/aippocampus/scripts python -m aippocampus_runtime.sync.bundle push --registry-dir ./examples/public-memory-bundle/registry --sync-dir ./.tmp/demo-sync --json
PYTHONPATH=./skills/aippocampus/scripts python -m aippocampus_runtime.sync.bundle repair --sync-dir ./.tmp/demo-sync --json
PYTHONPATH=./skills/aippocampus/scripts python -m aippocampus_runtime.sync.bundle pull --sync-dir ./.tmp/demo-sync --registry-dir ./.tmp/demo-target-registry --json
```

Expected result: the sync manifest is valid and `raw_rollout_included` remains
false. The synced registry uses portable bundle-relative locators, and pull
repairs generated-artifact paths to the target registry.

Boundary: this is a plaintext throwaway demo for local protocol validation; it
does not exercise cloud, object storage, encryption, or another machine.

## Scenario 9b: Single-Machine Cross-Device Sync Smoke

```sh
python ./tools/aippocampus/smoke/smoke_cross_device_sync.py --repo-root . --json
```

Expected result: the smoke models device A and device B registries, strips or
rewrites source-device locators, repairs generated artifact paths to the target
registry, preserves conflicts in both directions, keeps raw rollouts excluded
by default, and transfers raw rollout only in the explicit opt-in branch.

Boundary: this smoke models two registries on one machine; it does not exercise
a physical second machine, cloud folder client, object storage, or encryption.

## Scenario 9c: Docker/WSL Alternate-Runtime Sync Smoke

```sh
python ./tools/aippocampus/smoke/smoke_alternate_runtime_sync.py --repo-root . --runtime all --json
```

Expected result: the host creates the sync bundle, then the alternate runtime
runs `status`, `repair`, and `pull`. The pulled registry should use
runtime-local generated-artifact locators, keep workspace unresolved, and keep
raw rollout excluded by default.

Boundary: this exercises alternate runtime behavior, not a physical second
machine, cloud client, or object-storage backend.

## Scenario 9d: HTTP Object-Storage Sync Smoke

```sh
python ./tools/aippocampus/smoke/smoke_object_storage_sync.py --repo-root . --json
```

Expected result: the smoke starts a local HTTP object store, pushes the sync
bundle through real object `PUT` calls, verifies status/repair through object
`GET` calls, and pulls into a target registry with generated-artifact paths
repaired. Raw rollout stays excluded by default.

Boundary: this uses a local HTTP object store, not a managed cloud provider or
physical second machine.

## Scenario 10: Over-Personalization Avoidance

Ask an unrelated technical question in a workspace with AIppocampus installed.

Expected result: ambient recall may stay silent when the prompt has no strong
memory scent. Strong claims require source hits, and unrelated prompts should
not include personal history by default.

## Scenario 11: Ambient Recall Boundary

Run hook status before installing anything:

```sh
PYTHONPATH="${CODEX_HOME}/skills/aippocampus/scripts" python -m aippocampus_runtime.hooks.install_prompt status --json
PYTHONPATH="${CODEX_HOME}/skills/aippocampus/scripts" python -m aippocampus_runtime.hooks.install_prompt status --last --json
```

Expected result: status is observable without enabling the hook. `--last`
reports either that no prompt-hook audit status exists yet, or a sanitized
`last_prompt_hook` object whose `memory_surface` is `no_memory`, `scent`,
`candidate`, or `source_backed_evidence`. The audit object may include counts,
cache/warm status, topic-epoch presence, source-reopen counts, and a redacted
event id; it must not include raw prompt text, raw cards, snippets, source
titles, session/turn ids, secrets, topic-epoch values, or local paths.
Installing a prompt hook is an explicit user action because it can surface
private clean source in future prompts.

Boundary: hooks are not enabled by plugin install alone. A visible
`scent`/`candidate` audit status is not claim-supporting evidence unless source
is opened or the surface reports `source_backed_evidence`.

## Scenario 12: Raw Audit Opt-In

Use raw search only when clean source is insufficient:

```sh
PYTHONPATH="${CODEX_HOME}/skills/aippocampus/scripts" python -m aippocampus_runtime.recall.rollout_search "keyword" --cwd .
```

Expected result: raw audit remains an explicit operator action.
Default stream fallback output is bounded: it returns raw-line refs, payload
class, short snippets, byte/truncation diagnostics, and hides the raw rollout
path. Full normalized raw payloads require the local audit override
`--include-raw-payload` / `--audit-raw`. Raw rollout mining is not the daily
default.
