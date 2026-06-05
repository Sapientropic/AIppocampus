# Maintenance And Operations

This reference owns manual repair, health checks, storage safety, and audit
routes.

## Health

Use `aippocampus_runtime/health` at the start of a long follow-up, after
compaction, before closeout, or when the user says a thread should be preserved.

Health checks include:

- rollout growth beyond stale-message or stale-byte thresholds
- advisory stale age, unindexed ratio, and activity-class diagnostics
- clean-source freshness
- anchor changes since the last index
- missing or stale segment indexes for large rollouts
- checkpoint due state
- Graphify corpus readiness
- whether the thread is large enough to consider deeper graph work

`aippocampus_runtime.ops.maintenance` is a threshold-style maintenance command, not a
daemon. It can rebuild stale source/indexes, prepare graphify corpus, refresh
segments, and produce checkpoint candidates. It should not append checkpoints
unless called with `--append-checkpoint`.
Activation payload compaction is available only as an explicit operator
delegation: pass `--activation-dead-letter-manifest` plus the intended owner
paths, and add `--apply-activation-payload-compaction` only when owner files
should be rewritten. Dry-run is the default, and the maintenance report records
a path-free command shape rather than local manifest or owner paths.

Maintenance defaults to a degraded-report contract: failed actions are recorded
in `action_failures`, safe independent actions can still run, `health_final` is
re-read, and `remaining_recommended_actions` states what still needs attention.
Use `--fail-fast` only for strict CI/operator paths that need the old first
failure to stop the command.

`aippocampus health --registry-wide --json` gives a lightweight registry rollup:
thread health counts, recommended-action counts, storage totals, and top
hashed thread refs by risk. It reads registry and generated manifests only, not
raw or clean-source message bodies. Default output must not expose private
thread titles, raw snippets, or absolute local paths; `--include-paths` is a
local maintainer diagnostic switch.

Generated artifact writers must coordinate through same-directory leases instead
of relying on users to run commands serially. `aippocampus_runtime.recall.index_builder` holds
`.index-publish.lock` while publishing `messages.jsonl`, `source_index.sqlite`,
`graph.json`, and `manifest.json`. `make_sqlite()` builds a unique temporary
SQLite database, copies it to
`generations/gen_*/source_index.sqlite`, updates `source_index.pointer.json`
with `current_generation` and `last_known_good_generation`, and then tries to
refresh the stable `source_index.sqlite` compatibility file through SQLite's
backup API with WAL enabled. New readers should resolve the pointer once per
query and keep using that generation path, then fall back to last-known-good,
then to the stable file. Legacy `versions/source_index-*.sqlite` pointers must
remain readable during migration. Do not reintroduce `unlink()` /
`Path.replace()` publishing for live `source_index.sqlite`; Windows readers can
hold that file open, and locked stable refreshes must degrade to the pointer
generation path rather than failing the whole index publish.
The publish fast path does not delete generation directories. Foreground
readers create short-lived `.reader-pins/*.json` files beside the generation
pointer while a query is using a resolved generation. Storage GC may delete an
old generation only after apply-time checks prove the target is not current or
last-known-good, no active reader pin remains, and the conservative TTL window
has elapsed. This protects foreground readers that resolved an older generation
before a background publish swung the pointer.
`aippocampus_runtime.artifacts.publish.index_generation_diagnostics` is the
shared read-only report helper for this boundary. Health and capacity reports
use it to expose pointer status, fallback used, current/LKG generation ids,
old generation bytes, pointer load time, publish latency, active reader-pin
counts, TTL status, and old generation GC candidates. Those candidates are
rebuildable-cache evidence; deletion still belongs to storage GC apply's
source, lease, active-thread, pointer, reader-pin, and TTL checks.

`aippocampus_runtime.ops.maintenance`, `aippocampus_runtime.hooks.lifecycle`, and
`aippocampus_runtime.vault.sync` should keep delegating SQLite writes to the index builders. If a
future entrypoint writes generated SQLite directly, it must reuse
`aippocampus_runtime/artifacts/publish` rather than creating a parallel lock or retry
scheme.

Registry/control-plane writes have a narrower #590 contract. `register_thread`,
`register-rollout`, and `register-source` still write JSON registry metadata,
not a SQLite truth store. They use the same-directory `.threads-registry.lock`
around the registry `load -> upsert -> save` window so concurrent local agents
do not lose updates. The JSON and Markdown registry files are both published
through temporary files plus replace. Read-only MCP tools and registry searches
do not take this writer lease; they either see the previous complete registry or
the next complete registry. If the registry writer lease cannot be acquired,
MCP reports `registry_writer_busy` as retryable writer contention. This remains
separate from #111's generated SQLite writer coordination: generated indexes are
still rebuildable caches, and registry metadata remains the control-plane
source for thread discovery.

Writer coordination entrypoints:

- `aippocampus_runtime.recall.index_builder`: owns main index publish; uses `.index-publish.lock`,
  generation SQLite pointer, last-known-good fallback, and stable SQLite backup.
- `aippocampus_runtime.recall.segment_builder`: owns segment shard publish; uses `.rebuild.lock`, staged
  segment dirs, `segments/generations/gen_*`, `segments.pointer.json`, and the
  shared lease helper.
- `aippocampus_runtime.hooks.lifecycle`: orchestrates `aippocampus_runtime.recall.index_builder`,
  `aippocampus_runtime.recall.segment_builder`, and registry commands; it must not write generated
  SQLite directly.
- `aippocampus_runtime.ops.maintenance`: threshold-style operator command; it delegates
  main and segment SQLite writes to the builders.
- `aippocampus_runtime.vault.sync`: runs maintenance first unless `--no-hook`, then reads health,
  messages JSONL, anchors, and registry metadata for vault/dashboard output.
- `aippocampus_runtime.sync.bundle`: syncs manifests, graph metadata, and
  content-addressed clean source by default; `aippocampus_runtime.sync.bundle` remains the
  package-owner command. Generated SQLite, pointer files, and
  generation caches are not portable source files.
- `aippocampus_runtime.artifacts.export_bundle` /
  `aippocampus_runtime.artifacts.import_bundle`, with `aippocampus_runtime.artifacts.export_bundle` /
  `aippocampus_runtime.artifacts.import_bundle` as package owners: explicit portable bundle path;
  export may include generated index files inside the bundle, and import
  reports both the stable search path and the pointer-resolved current SQLite
  path.
- `aippocampus_runtime.registry.api` / `source_registration.py`: own
  control-plane registry writes for MCP `register_thread`, `register-rollout`,
  and `register-source`; use `.threads-registry.lock` only around registry
  metadata updates and return retryable busy diagnostics instead of widening the
  MCP write surface.

## Checkpoints And Anchors

Use `aippocampus_runtime.artifacts.checkpoint` for hippocampus-like consolidation. By default it suggests a
candidate anchor from recent messages and records that a check happened. Use
`--append` only when the candidate is durable enough to preserve.

Use `aippocampus_runtime.source.anchors` for concise durable anchors. Anchors should be short,
source-searchable, and written for future agents who need to know what to look
for after compaction or thread switching.

## Rollout Size Audit

Use `aippocampus_runtime.ops.rollout_size_audit` when growth itself is the question. It reports byte
buckets by raw JSONL item type, payload class, large lines, deduped visible
message size, and repeated injected instructions.

Do not speculate that "system prompts are the problem" unless the audit shows
that bucket. Codex rollouts can include event envelopes, assistant outputs, tool
calls, tool outputs, images, injected instructions, duplicate visible messages,
and compaction snapshots.

Audit routes are also where tool/debug provenance belongs. Default recall should
not rank tool payloads as memory content.

Use `aippocampus_runtime.ops.storage_capacity_report` when growth is a registry-level or sync-level
question. It stats registry files, clean-source canonical files, generated
indexes, semantic sidecars, current sync-policy files, and SQLite fanout without
reading clean-source message bodies or raw rollout bodies. This is the right
first command before deciding whether GB/TB-scale work needs source chunking,
delta sync, or a query planner.

Use `tools/aippocampus/smoke/smoke_synthetic_scale_capacity.py --json` when you
need a CI-safe multi-GB threshold model without creating large files. Its output
is synthetic aggregate capacity evidence only; it cannot prove real GB/TB
runtime, Windows interrupted rebuild recovery, or physical sync behavior.

Segmented index rebuilds use the same shared lease helper with a
same-directory `.rebuild.lock` before building or publishing segment SQLite
shards. This is the single-writer discipline for segment rebuilds: do not run
two `aippocampus_runtime.recall.segment_builder` writers against the same output directory. If a process
dies, the next run may recover a stale lease after the configured age, but
operators should first verify no live writer is still using the directory. New
segments are staged into `segments/generations/gen_*`, `segments.pointer.json`
is updated only after the generation manifest and compatibility
`segments/manifest.json` are written, and failed publish leaves the previous
pointer/manifest/generation available. The publish fast path must not delete old
segment generations or legacy flat `seg-*` dirs. Segment search pins the
resolved generation manifest for the duration of a query, and storage GC may
delete old segment generation directories only after the same reader-pin/TTL,
current/LKG pointer, source, lease, and active-thread checks pass. Health and
storage-capacity reports may surface old segment generations as GC candidates,
but deletion remains an explicit apply action.

Cross-device sync treats SQLite as a rebuildable generated cache, not durable
truth. `aippocampus_runtime.sync.bundle` syncs registry manifests, graph
metadata, and content-addressed clean source by default; `aippocampus_runtime.sync.bundle` is the
package owner for the same command. It does not require generated SQLite
files, pointer files, generation directories, or legacy versioned SQLite caches
to move between devices. Target devices repair registry locators to local
generated caches only when those caches already exist locally; otherwise
`paths.sqlite` stays unresolved and the target should rebuild from clean source
or raw rollout rather than trusting a stale source-device lock state.

## Retention And Cold Archive

Use `retention_report.py --write` before proposing cleanup. The report
classifies files as:

- `must_keep`
- `compress_in_cold_archive_only`
- `rebuildable_delete_under_disk_pressure`
- `archive_or_delete_after_human_review`

`aippocampus_runtime.ops.cold_archive` creates a gzip raw-rollout copy plus manifests, anchors, index
manifests, and reports under the global thread store's `cold-archives/`
directory by default. Passing `--output-dir .aippocampus/cold-archives` is an
explicit local audit/export path, not a public commit surface. It must not
delete or rewrite the live rollout. Verify decompressed SHA-256 before any
manual cleanup outside the script.

For smaller/private migration, prefer `aippocampus export --no-raw` when raw
history is not needed.

Use `aippocampus storage gc --dry-run --json` as the governance bridge after
capacity/retention evidence exists. The dry-run command may generate the
registry-scale capacity report because that report only stats files and reads
manifests, but it does not generate a retention report implicitly. If no
existing `retention_report.json` is found or passed with `--retention-report`,
the command reports aggregate rebuildable bytes from capacity data and marks
path-level candidates as unavailable. `aippocampus storage gc --apply --class
rebuildable` has a narrow v1 apply path for the main `source_index.sqlite`
cache when a retention report supplies path-level evidence, and for old
main-index / segment generation directories when the capacity report supplies a
concrete path. It checks source evidence, live writer/export leases,
active-thread opt-in, last-known-good/current pointer protection, and the
reader-pin/TTL contract, then writes an eviction manifest under
`index/evictions/` with rebuild instructions. Capacity aggregates, segment
indexes, Graphify corpus caches, review artifacts, and source files remain
plan-only/manual.

Codex Desktop's own thread archive is a different mechanism: the app may move
raw rollout JSONL files from `$CODEX_HOME/sessions/` into
`$CODEX_HOME/archived_sessions/`. AIppocampus scans that directory read-only so
health, locate, and search keep working after a thread is archived. Do not treat
that app-owned location as a cold-archive output, and do not delete, compress,
or rewrite those files from AIppocampus maintenance commands.

## Thread Slimming Policy

Do not slim live Desktop rollout JSONL by default. The app owns that file, and
live mutation can break recovery, image/tool provenance, or future migrations.

Use non-destructive slimming:

- keep raw rollout immutable as the source of truth
- keep daily search slim through clean source, anchors, SQLite, segment indexes,
  and vault/dashboard surfaces
- open a new thread when UI/render pressure becomes high, then use registry and
  source-backed search for continuity
- cold-archive only after user intent and retention evidence are clear

Likely bloat drivers are compaction snapshots, embedded images, tool outputs,
and app event envelopes. Measure before advising.

## Manual Command Groups

Common health and repair commands:

- `python -m aippocampus_runtime.health --cwd "$PWD"`
- `aippocampus health --registry-wide --json`
- `python -m aippocampus_runtime.ops.maintenance --cwd "$PWD"`
- `python -m aippocampus_runtime.ops.maintenance --cwd "$PWD" --activation-dead-letter-manifest "<manifest.json>" --activation-working-memory "<working_memory.jsonl>" --json`
- `python -m aippocampus_runtime.source.clean_source --cwd "$PWD"`
- `python -m aippocampus_runtime.recall.index_builder --cwd "$PWD"`
- `python -m aippocampus_runtime.recall.segment_builder --cwd "$PWD"`
- `python -m aippocampus_runtime.recall.segment_search "query" --cwd "$PWD" --mode hybrid --fanout-budget 8`
- `python -m aippocampus_runtime.recall.segment_search "query" --cwd "$PWD" --mode hybrid --full-fanout`

Audit and archive commands:

- `python -m aippocampus_runtime.ops.rollout_size_audit --cwd "$PWD"`
- `python -m aippocampus_runtime.ops.storage_capacity_report --json`
- `aippocampus storage gc --dry-run --json`
- `aippocampus storage gc --apply --class rebuildable --retention-report "<retention_report.json>" --json`
- `python tools\aippocampus\smoke\smoke_synthetic_scale_capacity.py --json`
- `python -m aippocampus_runtime.ops.retention_report --cwd "$PWD" --write`
- `python -m aippocampus_runtime.ops.cold_archive --cwd "$PWD"`
- `aippocampus export --cwd "$PWD"` or `python -m aippocampus_runtime.artifacts.export_bundle --cwd "$PWD"`
- `aippocampus import "<bundle.zip>"` or `python -m aippocampus_runtime.artifacts.import_bundle "<bundle.zip>"`

Graph and vault commands:

- `python -m aippocampus_runtime.ops.graphify_corpus --cwd "$PWD"`
- `python -m aippocampus_runtime.vault.sync --cwd "$PWD" --vault "<vault path>"`

## Operational Safety

- Prefer narrow searches and short excerpts.
- Treat bundles, registry rows, vault notes, and rollouts as local private
  history.
- Do not search secrets or unrelated private logs without explicit user scope.
- Do not run multiple writers against the same generated artifact output
  directory in parallel.
- Rebuild generated JSONL/SQLite artifacts instead of migrating them in place
  unless the migration has tests.
