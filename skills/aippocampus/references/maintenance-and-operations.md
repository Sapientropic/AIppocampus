# Maintenance And Operations

This reference owns manual repair, health checks, storage safety, and audit
routes.

## Health

Use `scripts/aippocampus_health.py` at the start of a long follow-up, after
compaction, before closeout, or when the user says a thread should be preserved.

Health checks include:

- rollout growth beyond stale-message or stale-byte thresholds
- clean-source freshness
- anchor changes since the last index
- missing or stale segment indexes for large rollouts
- checkpoint due state
- Graphify corpus readiness
- whether the thread is large enough to consider deeper graph work

`aippocampus_maintenance.py` is a threshold-style maintenance command, not a
daemon. It can rebuild stale source/indexes, prepare graphify corpus, refresh
segments, and produce checkpoint candidates. It should not append checkpoints
unless called with `--append-checkpoint`.

Generated artifact writers must coordinate through same-directory leases instead
of relying on users to run commands serially. `build_index.py` holds
`.index-publish.lock` while publishing `messages.jsonl`, `source_index.sqlite`,
`graph.json`, and `manifest.json`. `make_sqlite()` builds a unique temporary
SQLite database, copies it to `versions/source_index-*.sqlite`, updates
`source_index.pointer.json`, and then tries to refresh the stable
`source_index.sqlite` compatibility file through SQLite's backup API with WAL
enabled. New readers should resolve the pointer first, then fall back to
last-known-good, then to the stable file. Do not reintroduce `unlink()` /
`Path.replace()` publishing for live `source_index.sqlite`; Windows readers can
hold that file open, and locked stable refreshes must degrade to the versioned
pointer path rather than failing the whole index publish.

`aippocampus_maintenance.py`, `aippocampus_lifecycle_hook.py`, and
`sync_vault.py` should keep delegating SQLite writes to the index builders. If a
future entrypoint writes generated SQLite directly, it must reuse
`scripts/artifact_publish.py` rather than creating a parallel lock or retry
scheme.

Writer coordination entrypoints:

- `build_index.py`: owns main index publish; uses `.index-publish.lock`,
  versioned SQLite pointer, last-known-good fallback, and stable SQLite backup.
- `build_segments.py`: owns segment shard publish; uses `.rebuild.lock`, staged
  segment dirs, and the shared lease helper.
- `aippocampus_lifecycle_hook.py`: orchestrates `build_index.py`,
  `build_segments.py`, and registry commands; it must not write generated
  SQLite directly.
- `aippocampus_maintenance.py`: threshold-style operator command; it delegates
  main and segment SQLite writes to the builders.
- `sync_vault.py`: runs maintenance first unless `--no-hook`, then reads health,
  messages JSONL, anchors, and registry metadata for vault/dashboard output.
- `aippocampus_runtime.sync.bundle`: syncs manifests, graph metadata, and
  content-addressed clean source by default; `sync_bundle.py` remains the
  direct-script compatibility shim. Generated SQLite, pointer files, and
  versioned caches are not portable source files.
- `export_bundle.py` / `import_bundle.py`: explicit portable bundle path; export
  may include generated index files inside the bundle, and import reports both
  the stable search path and the pointer-resolved current SQLite path.

## Checkpoints And Anchors

Use `checkpoint.py` for hippocampus-like consolidation. By default it suggests a
candidate anchor from recent messages and records that a check happened. Use
`--append` only when the candidate is durable enough to preserve.

Use `append_anchor.py` for concise durable anchors. Anchors should be short,
source-searchable, and written for future agents who need to know what to look
for after compaction or thread switching.

## Rollout Size Audit

Use `rollout_size_audit.py` when growth itself is the question. It reports byte
buckets by raw JSONL item type, payload class, large lines, deduped visible
message size, and repeated injected instructions.

Do not speculate that "system prompts are the problem" unless the audit shows
that bucket. Codex rollouts can include event envelopes, assistant outputs, tool
calls, tool outputs, images, injected instructions, duplicate visible messages,
and compaction snapshots.

Audit routes are also where tool/debug provenance belongs. Default recall should
not rank tool payloads as memory content.

Use `storage_capacity_report.py` when growth is a registry-level or sync-level
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
two `build_segments.py` writers against the same output directory. If a process
dies, the next run may recover a stale lease after the configured age, but
operators should first verify no live writer is still using the directory. New
segments are staged before publish, and failed publish restores last-known-good
`seg-*` dirs and manifest metadata.

Cross-device sync treats SQLite as a rebuildable generated cache, not durable
truth. `aippocampus_runtime.sync.bundle` syncs registry manifests, graph
metadata, and content-addressed clean source by default; `sync_bundle.py` is the
compatibility shim for the same command. It does not require generated SQLite
files, pointer files, or versioned SQLite caches to move between devices. Target
devices repair registry locators to local generated caches only when those
caches already exist locally; otherwise `paths.sqlite` stays unresolved and the
target should rebuild from clean source or raw rollout rather than trusting a
stale source-device lock state.

## Retention And Cold Archive

Use `retention_report.py --write` before proposing cleanup. The report
classifies files as:

- `must_keep`
- `compress_in_cold_archive_only`
- `rebuildable_delete_under_disk_pressure`
- `archive_or_delete_after_human_review`

`cold_archive.py` creates a gzip raw-rollout copy plus manifests, anchors, index
manifests, and reports under the global thread store's `cold-archives/`
directory by default. Passing `--output-dir .aippocampus/cold-archives` is an
explicit local audit/export path, not a public commit surface. It must not
delete or rewrite the live rollout. Verify decompressed SHA-256 before any
manual cleanup outside the script.

For smaller/private migration, prefer `export_bundle.py --no-raw` when raw
history is not needed.

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

- `python ...\aippocampus_health.py --cwd "$PWD"`
- `python ...\aippocampus_maintenance.py --cwd "$PWD"`
- `python ...\build_clean_source.py --cwd "$PWD"`
- `python ...\build_index.py --cwd "$PWD"`
- `python ...\build_segments.py --cwd "$PWD"`
- `python ...\search_segments.py "query" --cwd "$PWD" --build-segments --mode hybrid`

Audit and archive commands:

- `python ...\rollout_size_audit.py --cwd "$PWD"`
- `python ...\storage_capacity_report.py --json`
- `python tools\aippocampus\smoke\smoke_synthetic_scale_capacity.py --json`
- `python ...\retention_report.py --cwd "$PWD" --write`
- `python ...\cold_archive.py --cwd "$PWD"`
- `python ...\export_bundle.py --cwd "$PWD"`
- `python ...\import_bundle.py "<bundle.zip>"`

Graph and vault commands:

- `python ...\prepare_graphify_corpus.py --cwd "$PWD"`
- `python ...\sync_vault.py --cwd "$PWD" --vault "<vault path>"`

## Operational Safety

- Prefer narrow searches and short excerpts.
- Treat bundles, registry rows, vault notes, and rollouts as local private
  history.
- Do not search secrets or unrelated private logs without explicit user scope.
- Do not run multiple writers against the same generated artifact output
  directory in parallel.
- Rebuild generated JSONL/SQLite artifacts instead of migrating them in place
  unless the migration has tests.
