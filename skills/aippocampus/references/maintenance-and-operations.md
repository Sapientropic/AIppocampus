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

Run maintenance writes serially on Windows. `build_index.py`,
`aippocampus_maintenance.py`, and `sync_vault.py` may all touch SQLite files.

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
